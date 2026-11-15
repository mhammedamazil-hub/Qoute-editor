"""minicoder — command-line interface. Works fully offline."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init(args) -> int:
    from .db import init_db
    path = init_db()
    print(f"MiniCoder brain initialised at {path}")
    return 0


def cmd_doctor(args) -> int:
    from .api.routes import build_router  # noqa: F401 (import sanity)
    from .brain import hardware_profile
    from .llm import provider_status
    from .db import counts
    _print_json({"hardware": hardware_profile(), "provider": provider_status(),
                 "memory": counts()})
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    from .api.app import create_app
    print(f"MiniCoder Brain API → http://{args.host}:{args.port}  (docs at /docs)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_chat(args) -> int:
    from .brain import get_brain
    brain = get_brain()
    if args.message:
        _print_json(brain.chat(" ".join(args.message)))
        return 0
    print("MiniCoder interactive chat (Ctrl-D to exit). Try: /sleep, /stats, /memories")
    while True:
        try:
            msg = input("you › ").strip()
        except EOFError:
            print()
            break
        if not msg:
            continue
        if msg == "/sleep":
            _print_json(brain.sleep(trigger="user_requested"))
            continue
        if msg == "/stats":
            _print_json(brain.status())
            continue
        if msg == "/memories":
            from .episodic import list_episodes
            for ep in list_episodes(limit=10):
                print(f"· [{ep.verification_status:10s}] {ep.situation[:100]}")
            continue
        resp = brain.chat(msg)
        print(f"minicoder › {resp['reply']}")
        if resp.get("citations"):
            print(f"    citations: {', '.join(resp['citations'])}  (confidence {resp['confidence']})")
    return 0


def cmd_remember(args) -> int:
    from .episodic import record_episode
    ep = record_episode(situation=" ".join(args.text), source=args.source,
                        verification_status=args.status, confidence=args.confidence,
                        tags=args.tags.split(",") if args.tags else [])
    _print_json(ep.model_dump(mode="json"))
    return 0


def cmd_search(args) -> int:
    from .episodic import search_episodes
    for ep, score in search_episodes(" ".join(args.query), top_k=args.top_k):
        print(f"{score:.3f} [{ep.verification_status:10s}] {ep.id}  {ep.situation[:110]}")
    return 0


def cmd_skills(args) -> int:
    from .procedural import list_skills
    skills = list_skills(status=args.status, domain=args.domain)
    if args.json:
        _print_json([s.model_dump(mode="json") for s in skills])
        return 0
    if not skills:
        print("(no skills)")
        return 0
    for s in skills:
        print(f"· {s.id}  [{s.verification_status:10s}] conf={s.confidence:.2f} used={s.times_used}  {s.name}")
    return 0


def cmd_verify_code(args) -> int:
    from .brain import get_brain
    task = Path(args.task_file).read_text(encoding="utf-8") if args.task_file else args.task
    solution = Path(args.solution).read_text(encoding="utf-8")
    tests = Path(args.tests).read_text(encoding="utf-8")
    result = get_brain().run_coding_task(task=task, solution=solution, tests=tests, domain=args.domain)
    _print_json({"verified": result["verified"], "skill_id": result["skill"]["id"],
                 "gates": [(g["name"], g["passed"]) for g in result["gates"]]})
    return 0 if result["verified"] else 1


def cmd_sleep(args) -> int:
    from .brain import get_brain
    _print_json(get_brain().sleep(trigger=args.trigger))
    return 0


def cmd_report(args) -> int:
    from .sleep import latest_sleep_report
    report = latest_sleep_report()
    _print_json(report or {"note": "no sleep has run yet"})
    return 0


def cmd_stats(args) -> int:
    from .db import counts
    _print_json(counts())
    return 0


def cmd_export(args) -> int:
    from .snapshot import export_snapshot
    path = export_snapshot(Path(args.dest) if args.dest else None)
    print(path)
    return 0


def cmd_import(args) -> int:
    from .snapshot import import_snapshot
    _print_json(import_snapshot(Path(args.archive)))
    return 0


def cmd_ingest_image(args) -> int:
    from .visual import ingest_image
    _print_json(ingest_image(args.path, description=args.description,
                             tags=args.tags.split(",") if args.tags else []))
    return 0


def cmd_demo(args) -> int:
    """Seed a realistic demo: verified skill + failures → sleep → shard → print report."""
    from .brain import get_brain
    from .tools.coding import verify_python_solution
    from .procedural import register_skill
    from .episodic import record_episode

    print("== demo: solving & verifying coding tasks ==")
    demo_skills = [
        ("fibonacci-iteration", "algorithms",
         "Write an O(n) Fibonacci function that returns the n-th Fibonacci number.",
         "def fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
         "from solution import fibonacci\n\ndef test_zero(): assert fibonacci(0) == 0\ndef test_one(): assert fibonacci(1) == 1\ndef test_ten(): assert fibonacci(10) == 55\n",
         ["Avoid recursion blow-up", "Track (a, b) rolling pair", "Loop n times", "Return a"]),
        ("clamp-number", "algorithms",
         "Write clamp(value, lo, hi) that bounds value to the [lo, hi] interval.",
         "def clamp(v, lo, hi):\n    if lo > hi:\n        raise ValueError('lo must be <= hi')\n    return max(lo, min(hi, v))\n",
         "from solution import clamp\nimport pytest\n\ndef test_inside(): assert clamp(5, 0, 10) == 5\ndef test_below(): assert clamp(-3, 0, 10) == 0\ndef test_above(): assert clamp(99, 0, 10) == 10\ndef test_inverted():\n    with pytest.raises(ValueError): clamp(1, 10, 0)\n",
         ["Reject inverted bounds explicitly", "Return max(lo, min(hi, v))"]),
        ("is-palindrome", "strings",
         "Write is_palindrome(text) ignoring case, spaces and punctuation.",
         "import re\n\ndef is_palindrome(text):\n    cleaned = re.sub(r'[^a-z0-9]', '', text.lower())\n    return cleaned == cleaned[::-1]\n",
         "from solution import is_palindrome\n\ndef test_simple(): assert is_palindrome('level')\ndef test_phrase(): assert is_palindrome('A man, a plan, a canal: Panama')\ndef test_negative(): assert not is_palindrome('minicoder')\n",
         ["Normalise to lowercase alphanumerics", "Compare string to its reverse"]),
        ("chunk-list", "lists",
         "Write chunk_list(items, size) yielding successive chunks of length size.",
         "def chunk_list(items, size):\n    if size < 1:\n        raise ValueError('size must be >= 1')\n    for i in range(0, len(items), size):\n        yield items[i:i + size]\n",
         "from solution import chunk_list\nimport pytest\n\ndef test_even(): assert list(chunk_list([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]\ndef test_remainder(): assert list(chunk_list([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]\ndef test_bad_size():\n    with pytest.raises(ValueError): list(chunk_list([1], 0))\n",
         ["Validate chunk size", "Slice by stepping range", "Yield, don't materialise eagerly"]),
        ("merge-dedup-sorted", "lists",
         "Write merge_dedup_sorted(a, b) merging two sorted lists into a sorted list without duplicates.",
         "def merge_dedup_sorted(a, b):\n    out = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            nxt = a[i]; i += 1\n        else:\n            nxt = b[j]; j += 1\n        if not out or out[-1] != nxt:\n            out.append(nxt)\n    for nxt in a[i:] + b[j:]:\n        if out and out[-1] == nxt:\n            continue\n        out.append(nxt)\n    return out\n",
         "from solution import merge_dedup_sorted\n\ndef test_basic(): assert merge_dedup_sorted([1, 3, 5], [2, 3, 4]) == [1, 2, 3, 4, 5]\ndef test_empty(): assert merge_dedup_sorted([], [1, 1, 2]) == [1, 2]\ndef test_dups(): assert merge_dedup_sorted([1, 1], [1, 1]) == [1]\n",
         ["Two-pointer linear merge", "Skip duplicates via last-emitted comparison"]),
    ]
    for name, domain, task, solution, tests, trace in demo_skills:
        steps = verify_python_solution(solution=solution, tests=tests)
        ok = all(s.passed for s in steps)
        print(f"  {name}: gates={[(s.name, s.passed) for s in steps]}")
        register_skill(name=name, domain=domain, description=task, final_output=solution,
                       inputs={"task": task}, reasoning_trace=trace,
                       verification=steps, confidence=0.9 if ok else 0.2)
    for situation, status, lessons in [
        ("Fixed flexbox overflow on dashboard screenshot", "VERIFIED", ["overflow:hidden on wrong axis", "check parent min-width first"]),
        ("CSS grid columns collapsed on mobile", "FAILED", ["viewport units interact with 100% columns"]),
        ("CSS grid columns collapsed on mobile — second project", "FAILED", ["viewport units interact with 100% columns"]),
        ("CSS grid columns collapsed on mobile — third project", "FAILED", ["viewport units interact with 100% columns"]),
        ("Refactored API client to async httpx", "VERIFIED", ["timeout on every request"]),
    ]:
        record_episode(situation=situation, modality="mixed", result=status,
                       verification_status=status, lessons=lessons,
                       tags=["css", "ui"] if "CSS" in situation or "flexbox" in situation else ["python"],
                       confidence=0.8 if status == "VERIFIED" else 0.3,
                       source="verified_execution" if status == "VERIFIED" else "unverified_hypothesis")
    print("== demo: sleep cycle ==")
    report = get_brain().sleep(trigger="demo")
    _print_json(report)
    return 0


def cmd_eval(args) -> int:
    """Train the from-scratch Nano model on the compiled shards; report honest metrics."""
    from .nano import NanoLM, NanoConfig
    shard_dir = Path(args.shards)
    texts = []
    for f in sorted(shard_dir.glob("shard_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                texts.append(line)
    if len(texts) < 20:
        print(f"not enough shard data ({len(texts)} examples); run `minicoder demo` first", file=sys.stderr)
        return 1
    cut = int(len(texts) * 0.8)
    train, holdout = texts[:cut], texts[cut:]
    model = NanoLM(NanoConfig())
    base_ppl = model.perplexity(holdout)
    stats = model.train_on_texts(train, steps=args.steps, batch_size=32, lr=3e-3, log_every=max(1, args.steps // 5))
    tuned_ppl = model.perplexity(holdout)
    out = {
        "examples_total": len(texts), "train": len(train), "holdout": len(holdout),
        "baseline_perplexity": round(base_ppl, 3), "trained_perplexity": round(tuned_ppl, 3),
        "improvement_ratio": round(base_ppl / tuned_ppl, 3) if tuned_ppl > 0 else None,
        "training": stats,
    }
    if args.save:
        model.save(Path(args.save))
        out["saved_to"] = str(Path(args.save).with_suffix(".npz"))
    _print_json(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minicoder", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="initialise the brain (dirs + db)"); sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("doctor", help="hardware, provider and memory check"); sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("serve", help="run the brain API + dashboard host")
    sp.add_argument("--host", default="0.0.0.0"); sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(fn=cmd_serve)
    sp = sub.add_parser("chat", help="interactive chat; -m one-shot")
    sp.add_argument("message", nargs="*"); sp.set_defaults(fn=cmd_chat)
    sp = sub.add_parser("remember", help="store an episode")
    sp.add_argument("text", nargs="+"); sp.add_argument("--source", default="user_instruction")
    sp.add_argument("--status", default="UNVERIFIED"); sp.add_argument("--confidence", type=float, default=0.6)
    sp.add_argument("--tags", default=""); sp.set_defaults(fn=cmd_remember)
    sp = sub.add_parser("search", help="search episodic memory")
    sp.add_argument("query", nargs="+"); sp.add_argument("--top-k", type=int, default=6); sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("skills", help="list procedural memory")
    sp.add_argument("--status", default=None); sp.add_argument("--domain", default=None)
    sp.add_argument("--json", action="store_true"); sp.set_defaults(fn=cmd_skills)
    sp = sub.add_parser("verify-code", help="run the verification gate on a solution")
    sp.add_argument("--task", default="ad-hoc task"); sp.add_argument("--task-file", default=None)
    sp.add_argument("--solution", required=True); sp.add_argument("--tests", required=True)
    sp.add_argument("--domain", default="python"); sp.set_defaults(fn=cmd_verify_code)
    sp = sub.add_parser("sleep", help="run the full 7-stage sleep cycle")
    sp.add_argument("--trigger", default="user_requested"); sp.set_defaults(fn=cmd_sleep)
    sp = sub.add_parser("report", help="print the latest sleep report"); sp.set_defaults(fn=cmd_report)
    sp = sub.add_parser("stats", help="memory counts"); sp.set_defaults(fn=cmd_stats)
    sp = sub.add_parser("export", help="export brain snapshot zip"); sp.add_argument("--dest", default=None); sp.set_defaults(fn=cmd_export)
    sp = sub.add_parser("import", help="import brain snapshot zip (merged; backup first)")
    sp.add_argument("archive"); sp.set_defaults(fn=cmd_import)
    sp = sub.add_parser("ingest-image", help="add an image to the visual buffer")
    sp.add_argument("path"); sp.add_argument("--description", default=""); sp.add_argument("--tags", default="")
    sp.set_defaults(fn=cmd_ingest_image)
    sp = sub.add_parser("demo", help="end-to-end: verify → remember → sleep → shard"); sp.set_defaults(fn=cmd_demo)
    sp = sub.add_parser("eval", help="train Nano on compiled shards; report honest perplexity")
    sp.add_argument("--shards", default=str(Path(__file__).resolve().parent.parent.parent / "datasets" / "sleep_skills"))
    sp.add_argument("--steps", type=int, default=400); sp.add_argument("--save", default=None)
    sp.set_defaults(fn=cmd_eval)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
