#!/usr/bin/env python3
"""CI gate 1 — validate every shard in datasets/sleep_skills/.

Checks, per line: schema, verification_status == VERIFIED, source allowlist,
licence allowlist, verification hash shape, example-hash uniqueness.
Exit 0 only if every shard is valid. Prints a JSON report.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from minicoder.shard import validate_shard_file  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "datasets/sleep_skills")
    shards = sorted(root.glob("shard_*.jsonl"))
    report = {"shards": [], "passed": True}
    if not shards:
        report = {"shards": [], "passed": False,
                  "errors": [f"no shard_*.jsonl files found under {root}"]}
        print(json.dumps(report, indent=2))
        return 1
    for shard_path in shards:
        r = validate_shard_file(shard_path)
        report["shards"].append(r.to_dict())
        if not r.passed:
            report["passed"] = False
    total = sum(s["total"] for s in report["shards"])
    ok = sum(s["ok"] for s in report["shards"])
    report["total_examples"] = total
    report["valid_examples"] = ok
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
