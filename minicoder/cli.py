"""MiniCoder command line: one entry point for the whole lifecycle.

    minicoder init                 create/verify the brain database
    minicoder chat "..."           talk to the brain (grounded answers)
    minicoder act "..."            drive the real editor and verify the result
    minicoder inspect <image>      visual inspection (OCR, layout, ML class)
    minicoder train [--profile]    train the multimodal backbone from scratch
    minicoder sleep [--push] [--train]   run a sleep cycle
    minicoder eval                 benchmark suites + ablation
    minicoder serve                API + dashboard on :8000
    minicoder status               brain state, memory counts, calibration
    minicoder memory search "..."  query every memory system
    minicoder skills               list procedural memory
    minicoder snapshots            backup / restore the brain
    minicoder doctor               environment + dependency audit
    minicoder learn "<task>" ...   acquire, verify by replay, promote a new skill
    minicoder benchmark [--json]   run the sealed learning benchmark
    minicoder acceptance           run the eight Phase 2 acceptance criteria
    minicoder safeguard <action>   baseline / evaluate / rollback a model update
    minicoder neural [--quick]     controlled study of training changes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG


# --------------------------------------------------------------------------
# tiny terminal helpers (no external deps required)
# --------------------------------------------------------------------------
class C:
    R = "\033[0m"
    B = "\033[1m"
    DIM = "\033[2m"
    G = "\033[38;5;72m"
    Y = "\033[38;5;179m"
    RED = "\033[38;5;167m"
    B_ = "\033[38;5;67m"
    M = "\033[38;5;140m"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def head(msg: str) -> None:
    say(f"\n{C.B}{C.Y}{msg}{C.R}")


def ok(msg: str) -> None:
    say(f"  {C.G}✓{C.R} {msg}")


def warn(msg: str) -> None:
    say(f"  {C.Y}!{C.R} {msg}")


def bad(msg: str) -> None:
    say(f"  {C.RED}✗{C.R} {msg}")


def kv(key: str, value: Any) -> None:
    say(f"  {C.DIM}{key:<24}{C.R}{value}")


def table(rows: list[list[str]], headers: list[str]) -> None:
    if not rows:
        warn("nothing to show")
        return
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    say("  " + "  ".join(f"{C.B}{h.upper():<{widths[i]}}{C.R}" for i, h in enumerate(headers)))
    for r in rows:
        say("  " + "  ".join(f"{cell:<{widths[i]}}" for i, cell in enumerate(r)))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB

    head("Initialising the brain")
    db = BrainDB()
    integrity = db.verify_integrity()
    ok(f"database at {db.db_path} ({integrity['detail']})")
    for table, n in integrity["counts"].items():
        kv(table, n)
    if args.seed:
        from minicoder.seed import seed_brain

        out = seed_brain(db)
        head("Seeded from the local corpus")
        for k, v in out.items():
            kv(k, v)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB
    from minicoder.seed import seed_brain

    head("Seeding the brain with verified knowledge")
    out = seed_brain(BrainDB())
    for k, v in out.items():
        kv(k, v)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from minicoder.api.app import service

    svc = service()
    head("Chat")
    message = " ".join(args.message).strip()
    if not message:
        bad("no message")
        return 2
    t0 = time.time()
    reply = svc.agent.execute(message) if args.act else None
    if reply is None:
        gen = svc.agent.answerer.answer(message)
        say(f"\n{C.B}brain{C.R} {gen.text}\n")
        kv("source", gen.source)
        kv("confidence", f"{svc.agent.mc.calibrated(0.6):.2f}")
        if gen.grounding:
            kv("grounding", json.dumps(gen.grounding[:3], default=str)[:200])
    else:
        say(f"\n{C.B}brain{C.R} {reply.summary}\n")
        kv("verified", reply.verified)
        kv("confidence", f"{reply.confidence:.2f}")
        for i, step in enumerate(reply.steps, 1):
            mark = f"{C.G}✓{C.R}" if step.ok else f"{C.RED}✗{C.R}"
            say(f"  {mark} {i}. {C.B_}{step.tool}{C.R} — {step.summary[:110]}")
            for c in step.checks[:2]:
                say(f"       {C.DIM}{c}{C.R}")
    kv("elapsed", f"{(time.time() - t0) * 1000:.0f} ms")
    return 0


def cmd_act(args: argparse.Namespace) -> int:
    args.act = True
    return cmd_chat(args)


def cmd_inspect(args: argparse.Namespace) -> int:
    from minicoder.tools.vision import inspect

    head("Visual inspection")
    path = Path(args.image)
    if not path.exists():
        bad(f"no such file: {path}")
        return 2
    rep = inspect(path, save_to_memory=not args.no_store, ocr=not args.no_ocr)
    kv("size", f"{rep.width}x{rep.height}")
    kv("sha256", rep.sha256[:16])
    if rep.ui_class:
        kv("ui class", f"{rep.ui_class} ({rep.ui_class_confidence * 100:.1f}%)")
        for cls, score in sorted(rep.class_scores.items(), key=lambda x: -x[1])[:4]:
            kv(f"  {cls}", f"{score * 100:.1f}%")
    if rep.ocr_text:
        kv("ocr", rep.ocr_text[:150])
    kv("regions", len(rep.boxes))
    kv("palette", ", ".join(rep.palette[:4]))
    if rep.findings:
        head("Findings")
        for f in rep.findings:
            warn(f)
    else:
        ok("no layout or contrast findings")
    say(f"\n{C.DIM}{rep.description}{C.R}")
    if rep.memory_id:
        ok(f"stored as visual memory #{rep.memory_id}")
    if args.json:
        say(json.dumps(rep.to_json(), indent=2)[:4000])
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    from minicoder.model.pipeline import run

    head(f"Training the compact backbone ({args.profile})")
    stages = [s.strip() for s in args.stages.split(",")] if args.stages else None
    out = run(args.profile, stages, args.resume)
    head("Summary")
    for stage, data in out["stages"].items():
        if isinstance(data, dict) and "metrics" in data:
            m = data["metrics"]
            ok(f"{stage}: {json.dumps({k: m.get(k) for k in ('train_loss', 'val_loss', 'val_ppl') if k in m})}")
        else:
            ok(f"{stage}: {json.dumps(data, default=str)[:120]}")
    kv("total seconds", out["seconds"])
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB
    from minicoder.sleep.engine import SleepEngine

    head("Entering sleep")
    engine = SleepEngine(
        BrainDB(),
        on_stage=lambda name, payload: say(
            f"  {C.M}stage {payload.get('stage')}{C.R} {name} {C.DIM}{payload.get('status')}{C.R}"
        ),
        push_to_github=args.push,
        train_after_compile=args.train,
    )
    report = engine.sleep(trigger="cli")
    say("")
    say(report.markdown())
    kv("report", str(CONFIG.paths.sleep_logs / f"sleep_{report.cycle_id:04d}.md"))
    return 0


def cmd_shard_train(args: argparse.Namespace) -> int:
    """Train + gate one JSONL shard. This is the call the CI workflow makes."""
    import json as _json
    from pathlib import Path as _Path

    from minicoder.memory.db import BrainDB
    from minicoder.sleep.trainer import load_shard, train_from_shard

    path = _Path(args.shard)
    if not path.exists():
        say(f"{C.R}! shard not found: {path}{C.R}")
        return 2
    rows = load_shard(path)
    head(f"Training on {path.name}")
    kv("examples", len(rows))
    out = train_from_shard(
        path,
        db=BrainDB(),
        epochs=args.epochs,
        lr=args.lr,
        promote=not args.no_promote,
    )
    say("")
    kv("trained", out.get("trained"))
    kv("gate_passed", out.get("gate_passed"))
    kv("promoted", out.get("promoted", False))
    kv("reason", out.get("reason", "-"))
    for k, v in (out.get("metrics") or {}).items():
        kv(f"metric.{k}", v)
    if args.report:
        _Path(args.report).write_text(_json.dumps(out, indent=2, default=str), encoding="utf-8")
        kv("report", args.report)
    # A rejected candidate is a *successful* run: the gate did its job.
    return 0 if out.get("trained") else 1


def cmd_shard_verify(args: argparse.Namespace) -> int:
    """Refuse to train on a shard that is not provably verified.

    This is prime directive #1 enforced at the CI boundary: a shard must carry a
    checksum sidecar and every example must name its provenance and, where it is
    a skill, a verification hash.
    """
    import hashlib
    import json as _json
    from pathlib import Path as _Path

    path = _Path(args.shard)
    if not path.exists():
        say(f"{C.R}! shard not found: {path}{C.R}")
        return 2
    problems: list[str] = []
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        problems.append("missing checksum sidecar (.sha256)")
    else:
        want = sidecar.read_text(encoding="utf-8").split()[0].strip()
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if want != got:
            problems.append(f"checksum mismatch: expected {want[:12]}… got {got[:12]}…")
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(_json.loads(line))
        except Exception as exc:
            problems.append(f"line {i}: not JSON ({exc})")
    for i, r in enumerate(rows, 1):
        if not r.get("source"):
            problems.append(f"row {i}: no provenance 'source'")
        if r.get("skill") not in (None, "", "replay_buffer") and not r.get("verification_hash"):
            problems.append(f"row {i}: skill example without verification_hash")
    head(f"Verifying {path.name}")
    kv("examples", len(rows))
    if problems:
        say("")
        for p_ in problems[:20]:
            say(f"  {C.R}! {p_}{C.R}")
        say(f"\n{C.R}REJECTED{C.R}: {len(problems)} problem(s)")
        return 1
    ok("shard is verified and hash-pinned")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from minicoder.eval.suites import run_all

    head("Running benchmark suites")
    _payload = run_all(args.suites.split(",") if args.suites else None,
                       skip_heavy=not args.heavy)
    path = CONFIG.paths.training_runs / "eval_report.json"
    kv("report", str(path))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from minicoder.api.app import service

    svc = service()
    st = svc.status()
    head("Brain")
    kv("state", st["state"])
    kv("checkpoint", f"{st['brain']['params']:,} params ({st['brain']['backend']})")
    kv("vocab", st["brain"]["vocab"])
    kv("embedder", st["embedder"])
    kv("editor bridge", "online" if st["editor"]["online"] else "offline")
    m = st["memory"]
    head("Memory")
    kv("episodes", m["episodes"])
    kv("semantic nodes", f"{m['semantic_nodes']} ({m['semantic_edges']} edges)")
    kv("skills", f"{m['skills_verified']} verified, {m['skills_pending_export']} pending export")
    kv("visual memories", m["visual_memories"])
    kv("vectors", m["embeddings"])
    kv("working memory", f"{m['working']['items']}/{m['working']['capacity']} ({m['working']['load'] * 100:.0f}%)")
    kv("sleep cycles", m["sleep_cycles"])
    kv("dataset shards", m["shards"])
    kv("conflicts open", m["conflicts_open"])
    cal = st["calibration"]
    head("Metacognition")
    kv("calibration samples", cal["n"])
    if cal["n"]:
        kv("expected calibration error", cal["ece"])
        kv("Brier score", cal["brier"])
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import EpisodicMemory, ProceduralMemory, SemanticMemory, VisualMemory

    db = BrainDB()
    if args.action == "search":
        query = " ".join(args.query)
        head(f"Recall: {query}")
        sem = SemanticMemory(db).search(query, limit=5)
        epi = EpisodicMemory(db).search(query, limit=5)
        vis = VisualMemory(db).search(query, limit=3)
        sk = [s for s in ProceduralMemory(db).verified() if query.lower() in (s["description"] + s["name"]).lower()]
        say(f"\n{C.B}semantic{C.R}")
        table([[str(r["id"]), r["kind"], r["label"][:58], f"{r.get('score', 0):.3f}"] for r in sem],
              ["id", "kind", "label", "score"])
        say(f"\n{C.B}episodic{C.R}")
        table([[str(r["id"]), r["status"], r["situation"][:58]] for r in epi], ["id", "status", "situation"])
        say(f"\n{C.B}procedural{C.R}")
        table([[s["slug"][:40], s["status"]] for s in sk], ["slug", "status"])
        say(f"\n{C.B}visual{C.R}")
        table([[str(r["id"]), (r["description"] or "")[:58]] for r in vis], ["id", "description"])
        return 0
    if args.action == "graph":
        from minicoder.memory.systems import SemanticMemory as SM

        g = SM(db).export_graph()
        head(f"Knowledge graph: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
        from collections import Counter

        for kind, n in Counter(n["kind"] for n in g["nodes"]).most_common():
            kv(kind, n)
        rel = Counter(e["relation"] for e in g["edges"])
        say("")
        for r, n in rel.most_common():
            kv(f"relation {r}", n)
        return 0
    bad("unknown memory action")
    return 2


def cmd_skills(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB
    from minicoder.memory.systems import ProceduralMemory

    pm = ProceduralMemory(BrainDB())
    stats = pm.stats()
    head("Procedural memory")
    for k, v in stats.items():
        if k != "by_status":
            kv(k, v)
    rows = pm.any()
    say("")
    table(
        [[str(s["id"]), s["slug"][:34], s["domain"], s["status"], "yes" if s["exported"] else "no",
          f"{s['confidence']:.2f}"] for s in rows[:40]],
        ["id", "slug", "domain", "status", "exported", "conf"],
    )
    return 0


def cmd_snapshots(args: argparse.Namespace) -> int:
    from minicoder.memory.db import BrainDB

    db = BrainDB()
    if args.restore:
        db.restore(Path(args.restore))
        ok(f"restored from {args.restore}")
        return 0
    if args.list:
        head("Snapshots")
        snaps = sorted(CONFIG.paths.checkpoints.glob("brain_*.db"))
        table([[p.name, f"{p.stat().st_size / 1e6:.1f} MB"] for p in snaps], ["file", "size"])
        return 0
    path = db.backup(tag="cli")
    ok(f"snapshot written to {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from minicoder.api.app import run

    head(f"Serving the brain on http://{args.host}:{args.port}")
    kv("dashboard", f"http://localhost:{args.port}/")
    kv("api docs", f"http://localhost:{args.port}/docs")
    run(host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import os
    import platform
    import shutil

    head("Environment")
    kv("python", platform.python_version())
    kv("platform", f"{platform.system()} {platform.machine()}")
    kv("cpu cores", os.cpu_count())
    try:
        import psutil

        vm = psutil.virtual_memory()
        kv("ram", f"{vm.total / 1e9:.1f} GB total, {vm.available / 1e9:.1f} GB available")
    except Exception:
        pass
    kv("repo", str(CONFIG.paths.home))
    head("Accelerators")
    try:
        import torch

        kv("torch", torch.__version__)
        kv("threads", torch.get_num_threads())
        kv("cuda", torch.cuda.is_available())
        kv("mps", getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception as exc:
        warn(f"torch unavailable: {exc}")
    head("Optional tools")
    for tool in ("docker", "npx", "git", "gh", "sqlite3"):
        path = shutil.which(tool)
        ok(f"{tool}: {path}") if path else warn(f"{tool}: not found")
    head("Models")
    for name, path in (
        ("lm.pt", CONFIG.paths.checkpoints / "lm.pt"),
        ("tokenizer.json", CONFIG.paths.checkpoints / "tokenizer.json"),
        ("vision.pt", CONFIG.paths.checkpoints / "vision.pt"),
        ("embedder.pt", CONFIG.paths.checkpoints / "embedder.pt"),
    ):
        if path.exists():
            ok(f"{name}: {path.stat().st_size / 1e6:.1f} MB")
        else:
            warn(f"{name}: missing (run `minicoder train`)")
    head("Optional python deps")
    db = __import__("minicoder.memory.db", fromlist=["BrainDB"]).BrainDB()
    kv("sqlite_vec", db.query_one("SELECT vec_version()")[0])
    for mod in ("rapidocr_onnxruntime", "cv2", "tree_sitter", "github", "git"):
        try:
            __import__(mod)
            ok(mod)
        except Exception:
            warn(f"{mod}: missing (optional)")
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="minicoder",
        description="Project MiniCoder — a compact, multimodal, self-evolving cognitive system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="create/verify the brain database")
    s.add_argument("--seed", action="store_true", help="also seed verified knowledge")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("seed", help="seed verified knowledge from the local corpus")
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("chat", help="talk to the brain (grounded, refuses when unknown)")
    s.add_argument("message", nargs="+")
    s.add_argument("--act", action="store_true", help="also allow editor actions")
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser("act", help="drive the real editor and verify every action")
    s.add_argument("message", nargs="+")
    s.set_defaults(func=cmd_act)

    s = sub.add_parser("inspect", help="inspect an image (OCR, layout, ML class)")
    s.add_argument("image")
    s.add_argument("--no-store", action="store_true")
    s.add_argument("--no-ocr", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("train", help="train the compact multimodal backbone")
    s.add_argument("--profile", choices=["quick", "standard"], default="standard")
    s.add_argument("--stages", default="", help="tokenizer,lm,sft,embedder,vision")
    s.add_argument("--resume", action="store_true")
    s.set_defaults(func=cmd_train)

    s = sub.add_parser("sleep", help="run a sleep cycle")
    s.add_argument("--push", action="store_true", help="commit+push the shard to GitHub")
    s.add_argument("--train", action="store_true", help="train + gate an adapter immediately")
    s.set_defaults(func=cmd_sleep)

    shard = sub.add_parser("shard", help="verify / train a JSONL shard (CI entry point)")
    shard_sub = shard.add_subparsers(dest="shard_cmd", required=True)
    sv = shard_sub.add_parser("verify", help="check provenance + checksum before training")
    sv.add_argument("shard")
    sv.set_defaults(func=cmd_shard_verify)
    st_ = shard_sub.add_parser("train", help="train a LoRA adapter and run the validation gate")
    st_.add_argument("shard")
    st_.add_argument("--epochs", type=int, default=None)
    st_.add_argument("--lr", type=float, default=None)
    st_.add_argument("--no-promote", action="store_true", help="gate but never promote")
    st_.add_argument("--report", default="", help="write the result JSON here")
    st_.set_defaults(func=cmd_shard_train)

    s = sub.add_parser("eval", help="run the benchmark suites")
    s.add_argument("--suites", default="", help="comma separated subset")
    s.add_argument("--heavy", action="store_true",
                   help="include the expensive suites (the base/+memory/+sleep/+LoRA ablation)")
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("status", help="brain state and memory counts")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("memory", help="query memory systems")
    s.add_argument("action", choices=["search", "graph"])
    s.add_argument("query", nargs="*")
    s.set_defaults(func=cmd_memory)

    s = sub.add_parser("skills", help="list procedural memory")
    s.set_defaults(func=cmd_skills)

    s = sub.add_parser("snapshots", help="backup / list / restore the brain")
    s.add_argument("--list", action="store_true")
    s.add_argument("--restore", default="")
    s.set_defaults(func=cmd_snapshots)

    s = sub.add_parser("serve", help="serve the API and dashboard")
    s.add_argument("--host", default=CONFIG.api.host)
    s.add_argument("--port", type=int, default=CONFIG.api.port)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("learn", help="acquire a skill, verify it by replay, promote it")
    s.add_argument("--criteria", action="append", default=[],
                   help="machine-checkable criterion (repeatable), e.g. 'canvas_size(900,1200)'")
    s.add_argument("--key", help="stable task key (default: timestamped)")
    s.add_argument("--title")
    s.add_argument("--goal")
    s.add_argument("--from-file", help="JSON task spec with key/criteria")
    s.add_argument("--attempts", type=int, default=4)
    s.add_argument("--promote", action="store_true", help="promote if replay passes")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_learn)

    s = sub.add_parser("benchmark", help="run the sealed learning benchmark")
    s.add_argument("--no-editor", action="store_true",
                   help="skip editor tasks (no bridge subprocess needed)")
    s.add_argument("--check", action="store_true",
                   help="fail if a previously solved task regressed (CI gate)")
    s.add_argument("--write-baseline", action="store_true",
                   help="record this run as the regression baseline")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_benchmark)

    s = sub.add_parser("acceptance", help="run the eight Phase 2 acceptance criteria")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_acceptance)

    s = sub.add_parser("research", help="Phase 3: blind tasks, arms, transfer, retention")
    s.add_argument("action", choices=["generate", "run", "reproduce", "security"])
    s.add_argument("--seed", type=int, default=11)
    s.add_argument("--seeds", default="")
    s.add_argument("--n", type=int, default=24)
    s.add_argument("--budget", type=float, default=45.0)
    s.add_argument("--warmup-seed", dest="warmup_seed", type=int, default=5)
    s.add_argument("--report", default="")
    s.add_argument("--out", default="")
    s.set_defaults(func=cmd_research)
    s = sub.add_parser("neural", help="controlled study of training changes")
    s.add_argument("--quick", action="store_true", help="4 epochs per variant")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_neural)

    s = sub.add_parser("safeguard", help="baseline / evaluate / rollback a model update")
    s.add_argument("action", choices=["baseline", "verify", "evaluate", "rollback"])
    s.add_argument("--name", default="baseline")
    s.set_defaults(func=cmd_safeguard)

    s = sub.add_parser("doctor", help="environment and dependency audit")
    s.set_defaults(func=cmd_doctor)
    return p



# ----------------------------------------------------------------- phase 2
def cmd_learn(args: argparse.Namespace) -> int:
    """Acquire a skill for a task, verify it by replay, optionally promote it."""
    from minicoder.learning.engine import LearningLoop, TaskSpec

    if args.from_file:
        spec = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        task = TaskSpec(
            key=spec["key"], title=spec.get("title", spec["key"]),
            goal=spec.get("goal", ""), criteria=spec["criteria"],
            domain=spec.get("domain", "editor"),
        )
    else:
        if not args.criteria:
            print("need --criteria (repeatable) or --from-file", file=sys.stderr)
            return 2
        key = args.key or "task_" + str(int(time.time()))
        task = TaskSpec(key=key, title=args.title or key,
                        goal=args.goal or key, criteria=args.criteria)

    loop = LearningLoop()
    try:
        print(f"{C.B}Acquiring{C.R} {task.key}")
        for c in task.criteria:
            print(f"  · {c}")
        rep = loop.acquire(task, max_attempts=args.attempts)
        print()
        print(f"  solved          {C.G if rep.solved else C.RED}{rep.solved}{C.R}")
        print(f"  attempts        {rep.attempts}")
        print(f"  first attempt   {rep.first_attempt_ok}")
        print(f"  progress        {rep.final_progress:.2f}")
        print(f"  seconds         {rep.seconds:.1f}")
        print(f"  replay          {rep.replay_runs}/{rep.replay_runs if rep.replay_passed else 0}"
              f" {'(fresh process)' if rep.replay_passed else ''}")
        if rep.failure_classes:
            print(f"  failures        {', '.join(rep.failure_classes)}")
        if rep.candidate_id and args.promote and rep.solved:
            out = loop.promote(rep.candidate_id, task)
            if out.get("promoted"):
                print(f"  {C.G}promoted{C.R}      {out['slug']} (skill {out['skill_id']})")
            else:
                print(f"  {C.Y}not promoted{C.R}  {out.get('reason')}")
        elif rep.candidate_id:
            print(f"  {C.DIM}candidate {rep.candidate_id} kept; pass --promote to admit it{C.R}")
        if args.json:
            print(json.dumps(rep.to_json(), indent=2))
    finally:
        loop.close()
    return 0 if rep.solved else 1


BASELINE_BENCH = Path("datasets/learning/benchmark_baseline.json")


def cmd_benchmark(args: argparse.Namespace) -> int:
    from minicoder.learning.runner import render_markdown, run_benchmark

    gate_run = getattr(args, "check", False) or getattr(args, "write_baseline", False)
    report = run_benchmark(editor=not args.no_editor, write_latest=not gate_run)
    if getattr(args, "check", False):
        # Regression gate for CI: a change must not reduce the number of sealed
        # tasks the system can acquire. Compared against a committed baseline so
        # the check is meaningful, not self-referential.
        if not BASELINE_BENCH.exists():
            print(f"{C.Y}no baseline at {BASELINE_BENCH}; run with --write-baseline{C.R}")
            return 0
        base = json.loads(BASELINE_BENCH.read_text(encoding="utf-8"))
        base_ok = set(base.get("solved_keys", []))
        now_ok = {t["key"] for t in report["tasks"] if t["final_ok"]}
        regressed = sorted(base_ok - now_ok)
        gained = sorted(now_ok - base_ok)
        print(f"\n{C.B}benchmark gate{C.R} baseline {len(base_ok)} solved, "
              f"now {len(now_ok)} solved")
        if gained:
            print(f"  {C.G}gained{C.R} {gained}")
        if regressed:
            print(f"  {C.RED}REGRESSED{C.R} {regressed}")
            return 1
        print(f"  {C.G}no regression{C.R}")
        return 0
    if getattr(args, "write_baseline", False):
        payload = {
            "generated_at": report["generated_at"],
            "solved_keys": sorted(t["key"] for t in report["tasks"] if t["final_ok"]),
            "summary": report["summary"],
        }
        BASELINE_BENCH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_BENCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"{C.G}baseline written{C.R} {BASELINE_BENCH} "
              f"({len(payload['solved_keys'])} solved)")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_markdown(report))
    s = report["summary"]
    print(f"\n{C.B}{s['final_success']}/{s['n']}{C.R} solved · "
          f"first-attempt {s['first_attempt_success']}/{s['n']} · "
          f"replay {s['replay_passed']}/{s['replay_attempted']} · "
          f"{s['total_seconds']}s · report {report['report_path']}")
    return 0


def cmd_acceptance(args: argparse.Namespace) -> int:
    from minicoder.learning.acceptance import run

    report = run()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_passed"] else 1


def cmd_safeguard(args: argparse.Namespace) -> int:
    from minicoder.learning.safeguard import BaselineRegistry, ImprovementGate, quick_metrics

    registry = BaselineRegistry()
    gate = ImprovementGate()
    if args.action == "baseline":
        snap = registry.snapshot(args.name)
        if snap.get("created"):
            metrics = quick_metrics()
            gate.record_baseline_metrics(metrics, name=args.name)
            print(f"{C.G}baseline{C.R} {args.name}: {', '.join(snap['files'])}")
            print(f"  metrics {json.dumps(metrics)}")
        else:
            print(f"{C.Y}exists{C.R} {snap.get('reason')}")
            print(f"  integrity {json.dumps(registry.verify_baseline(args.name))}")
        return 0
    if args.action == "verify":
        print(json.dumps(registry.verify_baseline(args.name), indent=2))
        return 0
    if args.action == "evaluate":
        metrics = quick_metrics()
        man = registry.manifest(args.name) or {}
        base = man.get("metrics")
        if not base:
            print(f"no baseline metrics recorded for {args.name}; run "
                  f"`safeguard baseline --name {args.name}` first", file=sys.stderr)
            return 2
        out = gate.evaluate(metrics, base, label="cli")
        print(json.dumps({"metrics": metrics, **out}, indent=2))
        return 0 if out["admitted"] else 1
    if args.action == "rollback":
        out = gate.revert(label="cli")
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("rolled_back") else 1
    print(f"unknown action {args.action}", file=sys.stderr)
    return 2


def cmd_research(args: argparse.Namespace) -> int:
    """Phase 3 experiments: blind generation, acquisition arms, transfer, retention."""
    import json

    action = args.action
    out_dir = Path(args.out or "datasets/research")

    if action == "generate":
        from minicoder.research.tasks import generate

        records = generate(args.seed, args.n)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"tasks_s{args.seed}.json"
        path.write_text(json.dumps([r.to_json() for r in records], indent=2), encoding="utf-8")
        kinds: dict[str, int] = {}
        for r in records:
            kinds[r.kind] = kinds.get(r.kind, 0) + 1
        print(f"{C.G}generated{C.R} {len(records)} tasks -> {path}")
        print(f"  kinds {kinds} | families {len({r.family for r in records})}")
        print(f"  first hash {records[0].generation_hash[:16]}")
        return 0

    if action == "security":
        from minicoder.research.isolation import available_modes, probe_escapes

        report = {"modes": [{"name": m.name, "os_boundary": m.os_boundary, "note": m.note}
                            for m in available_modes()], "probes": {}}
        failures = 0
        for mode in [m.name for m in available_modes()]:
            rows = probe_escapes(mode)
            report["probes"][mode] = rows
            bad = [r["probe"] for r in rows if r["escaped"]]
            failures += len(bad)
            print(f"  {mode:10s} probes={len(rows)} escapes={len(bad)} {bad}")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "security_latest.json").write_text(json.dumps(report, indent=2),
                                                      encoding="utf-8")
        print(f"{C.RED if failures else C.G}escape failures: {failures}{C.R}")
        return 0 if failures == 0 else 1

    if action == "run":
        from minicoder.research.experiment import load_library, render_markdown, run_experiment
        from minicoder.research.private import PrivateStore
        from minicoder.research.transfer import meta_report, retention_report, transfer_report, write_reports

        seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else [11]
        report = run_experiment(seeds=seeds, n_tasks=args.n, budget=args.budget,
                               warmup_seed=args.warmup_seed)
        library = load_library()
        store = PrivateStore.open(create=True)
        transfer = transfer_report(library, store)
        retention = retention_report(library, store)
        meta = meta_report(report)
        paths = write_reports(out_dir, report, transfer, retention, meta)
        (out_dir / "acquisition_latest.md").write_text(render_markdown(report), encoding="utf-8")
        print(f"\n{C.B}hidden-test pass rate by arm{C.R}")
        for arm, rate in report["rates"].items():
            print(f"  {arm:4s} {rate:.3f}")
        print(f"  transfer {json.dumps(transfer['summary'])}")
        print(f"  retention {retention['retained']}/{retention['families']} "
              f"(verified {retention['verified_retained']}/{retention['verified_at_acquisition']})")
        print(f"  production memory unchanged: {report['production_memory']['unchanged']}")
        print(f"  {paths['acquisition']}")
        return 0

    if action == "reproduce":
        from minicoder.research.experiment import load_library
        from minicoder.research.private import PrivateStore
        from minicoder.research.tasks import generate
        from minicoder.research.transfer import retention_report

        published = json.loads(Path(args.report).read_text(encoding="utf-8"))
        seeds = published["config"]["seeds"]
        n_tasks = published["config"]["n_tasks"]
        mismatches = []
        for seed in seeds:
            records = generate(seed, n_tasks)
            recorded = {t["key"]: t["hash"] for t in published["tasks_generated"][str(seed)]}
            for rec in records:
                if recorded.get(rec.key) != rec.generation_hash:
                    mismatches.append(rec.key)
        store = PrivateStore.open(create=True)
        integrity = store.verify()
        retention = retention_report(load_library(), store)
        ok = not mismatches and integrity["ok"]
        print(f"tasks reproduced: {sum(len(v) for v in published['tasks_generated'].values())} "
              f"recorded, mismatches {len(mismatches)}")
        print(f"evaluator integrity: {integrity['ok']}")
        print(f"retention replay: {retention['retained']}/{retention['families']}")
        print(f"{C.G if ok else C.RED}{'reproduced' if ok else 'NOT reproduced'}{C.R}")
        return 0 if ok else 1

    print(f"unknown research action {action!r}")
    return 2


def cmd_neural(args: argparse.Namespace) -> int:
    """Controlled before/after study of training changes."""
    from minicoder.learning.neural import run_study

    print(f"{C.B}Neural learning study{C.R} — one variable at a time")
    report = run_study(quick=args.quick)
    print(f"\n{C.B}{'variant':16s} {'val_ce':>8s} {'sft_val':>8s} {'indist':>7s} "
          f"{'holdout':>8s} {'retain':>7s}{C.R}")
    for e in report["results"]:
        print(f"{e['variant']:16s} {e.get('val_ce', 0):8.3f} "
              f"{e.get('sft_val_loss', 0):8.3f} {e['indist_exact']:7.3f} "
              f"{e['holdout_exact']:8.3f} {e['retention_exact']:7.3f}")
    print(f"\n{C.B}What the numbers show{C.R}")
    for line in report["conclusion"]:
        print(f"  · {line}")
    print(f"\nreport {report['report_path']}")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        say("\ninterrupted")
        return 130
    except Exception as exc:
        bad(f"{type(exc).__name__}: {exc}")
        if "--traceback" in (argv or sys.argv):
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
