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


def cmd_eval(args: argparse.Namespace) -> int:
    from minicoder.eval.suites import run_all

    head("Running benchmark suites")
    _payload = run_all(args.suites.split(",") if args.suites else None)
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

    s = sub.add_parser("eval", help="run the benchmark suites")
    s.add_argument("--suites", default="", help="comma separated subset")
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

    s = sub.add_parser("doctor", help="environment and dependency audit")
    s.set_defaults(func=cmd_doctor)
    return p


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
