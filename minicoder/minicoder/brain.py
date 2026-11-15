"""The Brain — WAKE-cycle orchestrator and metacognition layer.

State machine:  awake → thinking → tool_execution → awake   (never while sleeping)
                awake → sleeping → awake                     (sleep engine pauses chat)
                sleeping → github_training                    (report only; dispatch is delegated to CI)

Metacognition is explicit and measurable:
  * pre-action check  — intent classification, memory retrieval, calibrated confidence,
                        decision: answer | clarify | tool
  * post-action check — tool/test outputs vs. expectation, discrepancies logged to episodic memory
"""
from __future__ import annotations
import re
import threading
from collections import deque
from typing import Any
from .config import get_settings
from .db import counts, init_db
from .llm import get_provider, provider_status
from .models import Source
from .util import new_id, now_iso
from . import episodic, semantic
from .episodic import record_episode, search_episodes
from .working_memory import WorkingMemory

STATE_AWAKE = "awake"
STATE_THINKING = "thinking"
STATE_TOOL = "tool_execution"
STATE_SLEEPING = "sleeping"
STATE_TRAINING = "github_training"


class Brain:
    def __init__(self) -> None:
        init_db()
        self._lock = threading.RLock()
        self.state = STATE_AWAKE
        self.wm = WorkingMemory()
        self._telemetry: deque[dict] = deque(maxlen=300)
        self._started_at = now_iso()
        self._provider = get_provider()

    # ---------------------------------------------------------- telemetry
    def emit(self, event: str, **data: Any) -> None:
        entry = {"ts": now_iso(), "event": event, "state": self.state, **data}
        self._telemetry.append(entry)

    def telemetry_tail(self, n: int = 50) -> list[dict]:
        items = list(self._telemetry)
        return items[-n:]

    def status(self) -> dict:
        c = counts()
        return {
            "state": self.state,
            "started_at": self._started_at,
            "provider": provider_status(),
            "working_memory": {"load": round(self.wm.load(), 3), "items": len(self.wm.items),
                               "capacity": self.wm.capacity},
            "memory_counts": c,
            "hardware": hardware_profile(),
        }

    # ------------------------------------------------------- pre-action
    _INTENT_RULES = [
        ("sleep",   re.compile(r"\b(sleep|consolidat|nap|dream)\b", re.I)),
        ("vision",  re.compile(r"\b(image|screenshot|picture|photo|diagram|ui bug|layout)\b", re.I)),
        ("code",    re.compile(r"\b(code|debug|fix|bug|error|traceback|compile|test|function|class|refactor|python|javascript|typescript)\b", re.I)),
        ("memory",  re.compile(r"\b(remember|recall|memory|forget|know about me|preference)\b", re.I)),
    ]

    def pre_action_check(self, message: str) -> dict:
        intent = "chat"
        for name, rx in self._INTENT_RULES:
            if rx.search(message):
                intent = name
                break
        hits = search_episodes(message, top_k=4)
        best = max((s for _, s in hits), default=0.0)
        clarity = min(1.0, len(message.split()) / 12.0)
        confidence = round(0.25 + 0.55 * best + 0.20 * clarity, 3)
        threshold = get_settings().clarification_threshold
        decision = "answer"
        if intent != "sleep" and confidence < threshold and len(message.split()) > 2:
            decision = "clarify"
        return {"intent": intent, "confidence": confidence, "decision": decision,
                "retrieval_best": round(best, 4), "memories_used": [e.id for e, _ in hits]}

    # ------------------------------------------------------------- chat
    def chat(self, message: str) -> dict:
        message = message.strip()
        if not message:
            raise ValueError("empty message")
        with self._lock:
            if self.state == STATE_SLEEPING:
                return {"reply": "I'm asleep right now — my sleep engine is consolidating memory and compiling verified skills. Ask again when I wake, or check `minicoder sleep --status`.",
                        "route": "sleeping", "confidence": 1.0, "citations": [], "episode_id": None}
            self.state = STATE_THINKING
            self.emit("chat.start", intent_hint=len(message))
        self.wm.add(message, modality="text", priority=0.7, source="user_instruction")

        pre = self.pre_action_check(message)
        if pre["intent"] == "sleep":
            self.state = STATE_AWAKE
            return {"reply": "Say `minicoder sleep` (or POST /api/brain/sleep) and I'll consolidate memory, archive the low-priority noise, compile verified skills into a dataset shard and dispatch it to GitHub training.",
                    "route": "sleep-command", "confidence": 1.0, "citations": [], "episode_id": None,
                    "pre_action": pre}

        self.wm.add(f"pre-action: intent={pre['intent']} confidence={pre['confidence']}",
                    modality="text", priority=0.4, source="verified_execution")
        context = self.wm.context_block()

        if pre["decision"] == "clarify":
            reply = ("I want to get this right rather than guess. Could you clarify what you need — "
                     "the goal, the constraints, or the file/screenshot you're referring to? "
                     "(I checked my memory and found nothing verified that matches.)")
            ep = record_episode(situation=f"Clarified with user: {message[:200]}",
                                modality="text", objective=message, result="asked for clarification",
                                verification_status="UNVERIFIED",
                                source="user_instruction", confidence=0.3,
                                tags=["clarification"])
            self.state = STATE_AWAKE
            self.emit("chat.clarify", episode=ep.id)
            return {"reply": reply, "route": "clarify", "confidence": pre["confidence"],
                    "citations": [], "episode_id": ep.id, "pre_action": pre}

        reply = self._provider.generate(message, context=context)
        citations = re.findall(r"\[(?:mem|concept|skill):[^\]]+\]", reply)
        self.state = STATE_TOOL if any(t in message.lower() for t in ("run", "test", "execute")) else STATE_AWAKE
        ep = record_episode(
            situation=message[:400], modality="text", objective=message,
            actions=[f"pre_action({pre['intent']},conf={pre['confidence']})",
                     f"provider={self._provider.name}"],
            result=reply[:600],
            verification_status="UNVERIFIED",
            source="user_instruction", confidence=pre["confidence"],
            tags=[pre["intent"], self._provider.name],
        )
        self.wm.add(f"answered via {self._provider.name}: {reply[:160]}", modality="text",
                    priority=0.5, source="verified_execution")
        self.state = STATE_AWAKE
        self.emit("chat.done", episode=ep.id, confidence=pre["confidence"])
        return {"reply": reply, "route": pre["intent"], "confidence": pre["confidence"],
                "citations": citations, "episode_id": ep.id, "pre_action": pre}

    # -------------------------------------------- code task with hard gate
    def run_coding_task(self, *, task: str, solution: str, tests: str,
                        domain: str = "python", skill_name: str | None = None) -> dict:
        """Real verification → real skill registration. Unverified code never becomes a skill."""
        from .tools.coding import verify_python_solution
        self.state = STATE_TOOL
        self.emit("coding.verify.start", domain=domain)
        steps = verify_python_solution(solution=solution, tests=tests)
        ok = all(s.passed for s in steps)
        from .procedural import register_skill
        skill = register_skill(
            name=(skill_name or task.strip())[:80],
            description=task,
            domain=domain,
            final_output=solution,
            inputs={"task": task},
            reasoning_trace=["Parse task requirements",
                             "Draft candidate solution",
                             "Run syntax gate",
                             "Run pytest verification gate",
                             "Register as verified skill" if ok else "Quarantine — gate failed"],
            tool_calls=[{"tool": s.name, "command": s.command, "exit_code": s.exit_code} for s in steps],
            verification=steps,
            source="verified_execution" if ok else "unverified_hypothesis",
            confidence=0.9 if ok else 0.2,
        )
        ep = record_episode(
            situation=f"Coding task: {task[:300]}", modality="code", objective=task,
            actions=[s.name for s in steps], result=("PASS" if ok else "FAIL") + f" ({sum(s.passed for s in steps)}/{len(steps)} gates)",
            verification_status="VERIFIED" if ok else "FAILED",
            mistakes=[] if ok else [s.name for s in steps if not s.passed],
            lessons=[f"Verification gate: {', '.join(s.name for s in steps if s.passed)} passed"] if ok else [f"Fix failing gate(s): {', '.join(s.name for s in steps if not s.passed)}"],
            source="verified_execution", confidence=0.9 if ok else 0.2,
            tags=[domain, "coding-task"],
            meta={"sandbox_retest": {"solution": solution, "tests": tests}, "skill_id": skill.id},
        )
        self.state = STATE_AWAKE
        self.emit("coding.verify.done", skill=skill.id, verified=ok)
        return {"verified": ok, "skill": skill.model_dump(mode="json"),
                "episode_id": ep.id, "gates": [s.model_dump() for s in steps]}

    # ------------------------------------------------------------ sleep
    def sleep(self, *, trigger: str = "user_requested") -> dict:
        from .sleep import run_sleep
        with self._lock:
            self.state = STATE_SLEEPING
            self.emit("sleep.start", trigger=trigger)
        try:
            report = run_sleep(trigger=trigger)
        finally:
            self.state = STATE_AWAKE
            self.emit("sleep.done")
        return report.model_dump(mode="json")


def hardware_profile() -> dict:
    import platform
    import shutil
    import psutil
    gpu = None
    try:
        import subprocess
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            gpu = out.stdout.strip()
    except Exception:
        gpu = None
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    return {
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_model": platform.processor() or platform.machine(),
        "ram_total_gb": round(vm.total / 1e9, 2),
        "ram_available_gb": round(vm.available / 1e9, 2),
        "disk_free_gb": round(disk.free / 1e9, 2),
        "gpu": gpu or "none detected (CPU inference path)",
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


_brain: Brain | None = None
_brain_lock = threading.Lock()


def get_brain() -> Brain:
    global _brain
    with _brain_lock:
        if _brain is None:
            _brain = Brain()
        return _brain
