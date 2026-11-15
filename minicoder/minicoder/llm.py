"""LLM provider layer.

The from-scratch, offline-first default is the **HeuristicMemoryProvider**:
it answers from verified memory retrieval and skill lookup — and says plainly
when it does not know. It is NOT a large language model and never pretends to
be one. Optional providers (Gemini via key, llama.cpp GGUF if installed) can
be enabled for richer prose; selection is explicit and logged.
"""
from __future__ import annotations
import json
import urllib.request
from typing import Protocol
from .config import get_settings


class Provider(Protocol):
    name: str
    def generate(self, prompt: str, *, context: str = "", max_chars: int = 1600) -> str: ...


class HeuristicMemoryProvider:
    """From-scratch offline brain: memory-grounded, citation-carrying, honest.

    Generation = retrieval + deterministic templated synthesis from *stored,
    provenance-tracked* knowledge. No invented facts: if nothing relevant is
    found, it says so and asks what the user wants to teach it.
    """
    name = "heuristic-memory"

    def generate(self, prompt: str, *, context: str = "", max_chars: int = 1600) -> str:
        from .episodic import search_episodes
        from .semantic import search_concepts, RELATIONS
        from .procedural import list_skills
        from .util import tokenize

        q = prompt.strip()
        memories = search_episodes(q, top_k=4)
        concepts = search_concepts(q, top_k=4)
        skills = [s for s in list_skills(status="VERIFIED")
                  if any(t in (s.name + " " + s.description + " " + s.domain).lower()
                         for t in tokenize(q)[:8])][:2]
        parts: list[str] = []
        if skills:
            s = skills[0]
            steps = "\n".join(f"  {i+1}. {line}" for i, line in enumerate(s.reasoning_trace[:6]))
            parts.append(f"Matched verified skill **{s.name}** ({s.domain}, "
                         f"confidence {s.confidence:.2f}, {len(s.verification)} passing checks):\n"
                         f"{s.description}\nTrace:\n{steps}\n"
                         f"Verified output:\n{s.final_output[:600]}\n[skill:{s.id}]")
        if memories:
            lines = []
            for ep, score in memories:
                lines.append(f"- ({score:.2f}, {ep.verification_status}) {ep.situation[:180]} "
                            f"→ {ep.result[:160]} [mem:{ep.id}]")
            parts.append("Relevant memories:\n" + "\n".join(lines))
        if concepts:
            cl = ", ".join(f"{c['label']} ({c['confidence']:.2f}) [concept:{c['id']}]"
                           for c, _ in concepts)
            parts.append(f"Related knowledge: {cl}")
        if not parts:
            return ("I don't have verified knowledge about that yet. I won't invent an answer. "
                    "Tell me the facts, show me the code or screenshot, or let me attempt it with tools — "
                    "then I'll remember it (with provenance) for next time.")
        answer = "\n\n".join(parts)
        if context.strip():
            answer += f"\n\nWorking context considered:\n{context[:600]}"
        return answer[:max_chars]


class GeminiProvider:
    """Optional cloud provider. Only active when MINICODER_GEMINI_KEY is set."""
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, *, context: str = "", max_chars: int = 1600) -> str:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
               f":generateContent?key={self.api_key}")
        body = {"contents": [{"parts": [{"text":
            (f"You are MiniCoder's reasoning voice. Use only the supplied context and verified "
             f"memory; if unsure, say so.\n\nCONTEXT:\n{context}\n\nUSER:\n{prompt}")}]}]}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        candidates = data.get("candidates") or []
        text = "".join(p.get("text", "") for c in candidates
                       for p in (c.get("content", {}).get("parts", [])))
        return text[:max_chars] if text else "(empty response from Gemini)"


class LlamaCppProvider:
    """Optional local GGUF provider via llama-cpp-python (pip install llama-cpp-python)."""
    name = "llama.cpp"

    def __init__(self, model_path: str) -> None:
        from llama_cpp import Llama  # type: ignore
        self.llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)

    def generate(self, prompt: str, *, context: str = "", max_chars: int = 1600) -> str:
        out = self.llm.create_completion(
            prompt=f"### Context:\n{context}\n\n### User:\n{prompt}\n\n### MiniCoder:\n",
            max_tokens=512, temperature=0.4)
        text = out["choices"][0]["text"] if out.get("choices") else ""
        return text.strip()[:max_chars]


def get_provider():
    settings = get_settings()
    if settings.gemini_key:
        try:
            return GeminiProvider(settings.gemini_key)
        except Exception:
            pass
    return HeuristicMemoryProvider()


def provider_status() -> dict:
    settings = get_settings()
    return {
        "default": "gemini" if settings.gemini_key else "heuristic-memory",
        "gemini_configured": bool(settings.gemini_key),
        "llama_cpp_available": _module_available("llama_cpp"),
        "note": "heuristic-memory is the from-scratch offline brain; cloud/local LLMs are opt-in via env vars",
    }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False
