#!/usr/bin/env python3
"""CI gate 3 — regression & integrity audit across the whole dataset dir.

  1. every shard validates (delegates to validate_shard)
  2. no duplicate example_hash ACROSS shards (dedup audit)
  3. no example whose provenance chain is broken
Exits non-zero on any failure. Prints JSON.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from minicoder.shard import validate_shard_file  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "datasets/sleep_skills")
    shards = sorted(root.glob("shard_*.jsonl"))
    errors: list[str] = []
    seen: dict[str, str] = {}
    total = 0
    for shard_path in shards:
        r = validate_shard_file(shard_path)
        if not r.passed:
            errors.extend(f"{shard_path.name}: {e}" for e in r.errors)
        for lineno, raw in enumerate(shard_path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            total += 1
            try:
                prov = json.loads(raw).get("provenance", {})
            except json.JSONDecodeError:
                errors.append(f"{shard_path.name}:{lineno}: unparseable line")
                continue
            h = prov.get("example_hash")
            if h:
                if h in seen:
                    errors.append(f"duplicate example_hash {h} in {shard_path.name} (first seen in {seen[h]})")
                seen[h] = shard_path.name
    report = {"shards": len(shards), "total_examples": total,
              "unique_examples": len(seen), "errors": errors[:50],
              "passed": not errors}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
