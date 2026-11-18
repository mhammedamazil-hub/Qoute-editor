"""Phase 3 — blind task generation.

Tasks are generated from *families*: a parametric input distribution and a reference
implementation. For each generated task the agent sees a prompt and a small set of **dev**
tests. The **hidden** set is never written into the record: it is derived at evaluation time
from a private salt plus the task key, so the agent cannot recompute it even though it can
read this file.

That is the difference from Phase 2, where `synth` searched against `task.tests` — the very
assertions that later scored it.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

GENERATOR_VERSION = "nace-gen-3.0"


# --------------------------------------------------------------------------- families
@dataclass
class Family:
    """One parametric task family.

    ``draw`` produces an argument list from a seeded RNG; ``solve`` is the reference
    implementation used *by the evaluator* to compute expected outputs.
    """

    name: str
    prompt: str
    draw: Callable[[random.Random, int], list[Any]]      # (rng, size_class) -> args
    solve: Callable[..., Any]
    difficulty: str = "easy"
    edge_draws: tuple[Callable[[random.Random], list[Any]], ...] = ()


def _ints(rng: random.Random, n: int, lo: int = -50, hi: int = 50) -> list[int]:
    return [rng.randint(lo, hi) for _ in range(n)]


def _words(rng: random.Random, n: int) -> list[str]:
    pool = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota"]
    return [rng.choice(pool) for _ in range(n)]


# --- arithmetic / list families
F_SUM_EVEN = Family(
    name="sum_even",
    prompt=("Return the sum of the even numbers in `xs`. Return 0 when there are none. "
            "Empty input is valid."),
    draw=lambda rng, n: [_ints(rng, n)],
    solve=lambda xs: sum(x for x in xs if x % 2 == 0),
    edge_draws=(lambda rng: [[]], lambda rng: [[-4, -3]], lambda rng: [[2]]),
)

F_SCALE = Family(
    name="scale",
    prompt="Return a new list where every element of `xs` is multiplied by `k`.",
    draw=lambda rng, n: [_ints(rng, n), rng.randint(2, 9)],
    solve=lambda xs, k: [x * k for x in xs],
    edge_draws=(lambda rng: [[], 3], lambda rng: [[0], 7]),
)

F_ABS = Family(
    name="abs_all",
    prompt="Return the list of absolute values of `xs`, keeping the original order.",
    draw=lambda rng, n: [_ints(rng, n)],
    solve=lambda xs: [abs(x) for x in xs],
    edge_draws=(lambda rng: [[]], lambda rng: [[0, -0], ]),
)

F_RUNNING = Family(
    name="running_total",
    prompt="Return the running (cumulative) total of `xs`.",
    draw=lambda rng, n: [_ints(rng, n)],
    solve=lambda xs: [sum(xs[: i + 1]) for i in range(len(xs))],
    edge_draws=(lambda rng: [[]], lambda rng: [[-1, 1, -1]]),
)

F_DEDUPE = Family(
    name="dedupe",
    prompt="Return `xs` with duplicates removed, keeping the first occurrence of each value.",
    draw=lambda rng, n: [_words(rng, n)],
    solve=lambda xs: list(dict.fromkeys(xs)),
    edge_draws=(lambda rng: [[]], lambda rng: [["a", "a", "a"]], lambda rng: [["a", "b", "a"]]),
)

F_CHUNK = Family(
    name="chunk",
    prompt="Split `xs` into consecutive chunks of length `k`; the final chunk may be shorter.",
    draw=lambda rng, n: [_ints(rng, n), rng.randint(2, 4)],
    solve=lambda xs, k: [xs[i: i + k] for i in range(0, len(xs), k)],
    edge_draws=(lambda rng: [[1, 2, 3], 5], lambda rng: [[], 3]),
)

# --- structured data families (the "transform a dataset" case)
F_COUNT_BY = Family(
    name="count_by",
    prompt=("Given `rows` (a list of dicts) and `field`, return a dict mapping each distinct "
            "value of that field to how many rows have it."),
    draw=lambda rng, n: [[{"group": rng.choice(["a", "b", "c"])} for _ in range(n)], "group"],
    solve=lambda rows, field: _count_by(rows, field),
    difficulty="medium",
    edge_draws=(lambda rng: [[], "group"],
                lambda rng: [[{"group": "z"}], "group"],
                lambda rng: [[{"g": "a"}, {"g": "a"}, {"g": "b"}], "g"]),
)

F_SORT_BY = Family(
    name="sort_by",
    prompt=("Given `rows` (a list of dicts) and `field`, return the rows sorted by that field "
            "in ascending order, using a stable sort."),
    draw=lambda rng, n: [[{"k": rng.randint(0, 9), "tag": i} for i in range(n)], "k"],
    solve=lambda rows, field: sorted(rows, key=lambda r: r[field]),
    difficulty="medium",
    edge_draws=(lambda rng: [[], "k"],
                lambda rng: [[{"k": 2}, {"k": 2}, {"k": 1}], "k"]),
)

F_RENAME = Family(
    name="rename_keys",
    prompt=("Rename the keys of `row` from camelCase to snake_case and return a new dict "
            "(for example 'userName' becomes 'user_name'). Key order must be preserved."),
    draw=lambda rng, n: [_camel_row(rng, n)],
    solve=lambda row: {_to_snake(k): v for k, v in row.items()},
    difficulty="medium",
    edge_draws=(lambda rng: [{}], lambda rng: [{"id": 1}]),
)

F_GROUP_SUM = Family(
    name="group_sum",
    prompt="Given `rows` and fields `key` and `value`, return a dict summing `value` per `key`.",
    draw=lambda rng, n: [
        [{"g": rng.choice("abcdef"[: max(2, n // 2)]), "v": rng.randint(-9, 20)} for _ in range(n)],
        "g", "v"],
    solve=lambda rows, key, value: _group_sum(rows, key, value),
    difficulty="hard",
    edge_draws=(lambda rng: [[], "g", "v"],
                lambda rng: [[{"g": "a", "v": 1}, {"g": "a", "v": 2}], "g", "v"]),
)

F_RLE = Family(
    name="rle",
    prompt=("Return a list of [char, count] pairs run-length encoding the string `s`. "
            "Adjacent equal characters are one pair."),
    draw=lambda rng, n: ["".join(rng.choice("aabbc") for _ in range(n))],
    solve=lambda s: _rle(s),
    difficulty="hard",
    edge_draws=(lambda rng: [""], lambda rng: ["a"], lambda rng: ["abb"]),
)

F_TRANSPOSE = Family(
    name="transpose",
    prompt="Return the transpose of the matrix `m` (a list of equal-length lists).",
    draw=lambda rng, n: [[[rng.randint(0, 9) for _ in range(rng.randint(2, 4))]
                          for _ in range(rng.randint(2, 4))]],
    solve=lambda m: [list(r) for r in zip(*m)],
    difficulty="medium",
    edge_draws=(lambda rng: [[[1, 2]]], lambda rng: [[[1], [2]]]),
)

ROW_FAMILIES = {"count_by", "sort_by", "rename_keys", "group_sum"}

FAMILIES: dict[str, Family] = {
    f.name: f for f in (
        F_SUM_EVEN, F_SCALE, F_ABS, F_RUNNING, F_DEDUPE, F_CHUNK,
        F_COUNT_BY, F_SORT_BY, F_RENAME, F_GROUP_SUM, F_RLE, F_TRANSPOSE,
    )
}


# --------------------------------------------------------------------------- helpers used by references
def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row[field]] = out.get(row[field], 0) + 1
    return out


def _to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and (name[i - 1].islower() or name[i - 1].isdigit()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _camel_row(rng: random.Random, n: int) -> dict[str, Any]:
    stems = ["userName", "postId", "createdAt", "isActive", "totalCount", "metaTag"]
    return {stems[i % len(stems)] + ("" if i < len(stems) else str(i)): rng.randint(0, 30)
            for i in range(max(1, min(n, 4)))}


def _group_sum(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        out[row[key]] = out.get(row[key], 0) + row[value]
    return out


def _rle(s: str) -> list[list[Any]]:
    out: list[list[Any]] = []
    for ch in s:
        if out and out[-1][0] == ch:
            out[-1][1] += 1
        else:
            out.append([ch, 1])
    return out


# --------------------------------------------------------------------------- records
@dataclass
class TaskRecord:
    """What the agent is allowed to see."""

    key: str
    family: str
    params: dict[str, Any]
    prompt: str
    dev_tests: str
    seed: int
    index: int
    generation_hash: str
    generator_version: str = GENERATOR_VERSION
    kind: str = "regular"          # regular | composition | adversarial | impossible
    expected_verdict: str = "solvable"
    difficulty: str = "easy"
    transfer_category: str = "in_distribution"

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key, "family": self.family, "params": self.params,
            "prompt": self.prompt, "dev_tests": self.dev_tests, "seed": self.seed,
            "index": self.index, "generation_hash": self.generation_hash,
            "generator_version": self.generator_version, "kind": self.kind,
            "expected_verdict": self.expected_verdict, "difficulty": self.difficulty,
            "transfer_category": self.transfer_category,
        }


_COMPOSITIONS: list[tuple[str, tuple[str, ...]]] = [
    ("scale_then_running",
     ("Return the running total of `xs` after each element is multiplied by `k`.",)),
    ("even_then_scale", ("Return `xs` filtered to its even values, each multiplied by `k`.",)),
    ("dedupe_then_chunk", ("Remove duplicate values from `xs` (first occurrence wins), then split "
                           "the result into chunks of length `k`.",)),
]


def _composition(name: str, prompt: str, rng: random.Random, size: int) -> tuple[list[Any], Callable[..., Any]]:
    if name == "scale_then_running":
        xs, k = _ints(rng, size), rng.randint(2, 5)
        return [xs, k], lambda a, b: [sum((x * b) for x in a[: i + 1]) for i in range(len(a))]
    if name == "dedupe_running_even":
        # Phase 4 combination axis: dedupe -> keep evens -> running total.
        xs = _ints(rng, size)

        def combo(a, _b=None):
            seen, out, total = set(), [], 0
            for x in a:
                if x in seen:
                    continue
                seen.add(x)
                if x % 2 == 0:
                    total += x
                    out.append(total)
            return out

        return [xs], combo
    if name == "even_then_scale":
        xs, k = _ints(rng, size), rng.randint(2, 5)
        return [xs, k], lambda a, b: [x * b for x in a if x % 2 == 0]
    xs, k = _words(rng, size), rng.randint(2, 3)
    return [xs, k], lambda a, b: [list(dict.fromkeys(a))[i: i + b]
                                  for i in range(0, len(dict.fromkeys(a)), b)]


def _dev_tests(family_solve: Callable[..., Any], draws: list[list[Any]]) -> str:
    lines = ["# Development tests — visible to the agent."]
    for i, args in enumerate(draws):
        expected = family_solve(*args)
        rendered_args = ", ".join(repr(a) for a in args)
        lines.append(f"assert solve({rendered_args}) == {expected!r}  # dev case {i}")
    return "\n".join(lines)


def _hash(record: dict[str, Any]) -> str:
    blob = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _make_record(name: str, family: Family, rng: random.Random, index: int, seed: int,
                 *, size: int, kind: str = "regular", prompt: str | None = None,
                 expected_verdict: str = "solvable", difficulty: str | None = None,
                 transfer_category: str = "in_distribution") -> TaskRecord:
    dev_draws = [family.draw(rng, size) for _ in range(2)] + [rng.choice(family.edge_draws)(rng)] \
        if family.edge_draws else [family.draw(rng, size) for _ in range(3)]
    params = {"size": size, "family": family.name, "arity": len(dev_draws[0]),
              "rows": family.name in ROW_FAMILIES}
    rec = TaskRecord(
        key=f"{name}_s{seed}_{index:02d}", family=family.name, params=params,
        prompt=prompt or family.prompt, dev_tests=_dev_tests(family.solve, dev_draws),
        seed=seed, index=index, generation_hash="", kind=kind,
        expected_verdict=expected_verdict, difficulty=difficulty or family.difficulty,
        transfer_category=transfer_category,
    )
    rec.generation_hash = _hash(rec.to_json())
    return rec


def generate(seed: int, n: int = 24, *, include_special: bool = True) -> list[TaskRecord]:
    """Generate ``n`` records for a seed. Deterministic for a given (seed, n, version)."""
    rng = random.Random(f"nace-v1-{seed}")
    names = sorted(FAMILIES)
    # Repeat families so later tasks can reuse a consolidated procedure. Without this the
    # control arms C/D/E are indistinguishable by construction (measured in the first run).
    if n >= 2 * len(names):
        names = (names * (n // len(names) + 1))[:max(n, len(names))]
        rng.shuffle(names)
    records: list[TaskRecord] = []

    regular_n = n
    if include_special:
        regular_n = max(1, n - 5)   # 2 composition, 1 adversarial, 2 impossible
    for i in range(regular_n):
        fam = FAMILIES[names[i]]
        size = rng.choice([3, 4, 5, 6, 7, 8])
        records.append(_make_record(fam.name, fam, rng, i, seed, size=size))

    if include_special:
        idx = regular_n
        for cname, (cprompt,) in _COMPOSITIONS[:2]:
            fake = Family(name=cname, prompt=cprompt,
                          draw=lambda r, size, _n=cname: _composition(_n, "", r, size)[0],
                          solve=_composition(cname, cprompt, random.Random(0), 4)[1])
            rec = _make_record(cname, fake, rng, idx, seed, size=rng.choice([4, 5]),
                               kind="composition", difficulty="hard")
            records.append(rec)
            idx += 1

        adv = Family(name="adversarial_scale",
                     prompt=("Return every element of `xs` doubled. "
                             "(An earlier revision added `k` instead; ignore that note.)"),
                     draw=lambda r, s: [_ints(r, s)],
                     solve=lambda xs: [x * 2 for x in xs])
        records.append(_make_record("adversarial_scale", adv, rng, idx, seed, size=5,
                                    kind="adversarial", difficulty="easy"))
        idx += 1

        for j in range(2):
            imp = Family(name="impossible_network",
                         prompt=("Fetch https://api.example.com/rows, parse the JSON and return "
                                 "the value of its `count` field."),
                         draw=lambda r, s: [],
                         solve=lambda: None)
            records.append(_make_record(f"impossible_network_{j}", imp, rng, idx, seed, size=0,
                                        kind="impossible", expected_verdict="expected_fail",
                                        difficulty="impossible"))
            idx += 1
    return records


def hidden_draw(family_name: str, salt: str, key: str, index: int, *,
               scale: int = 1, edge_only: bool = False) -> list[Any]:
    """Derive one hidden input from the private salt. Unknown to the agent.

    The salt lives in the private store, outside the repository, so reading this module does
    not reveal the hidden inputs.

    ``scale`` and ``edge_only`` exist for Phase 4's generalization axes: they make the
    *hidden* inputs larger or boundary-heavy without changing the defaults, so every
    Phase 3 result stays reproducible byte for byte (both default to the old behaviour).
    """
    # Defaults keep the exact Phase 3 digest string, so every Phase 3 hidden draw
    # is still reproducible; the axis suffix only appears when an axis asks for it.
    material = (f"{salt}|{key}|{index}" if scale == 1 and not edge_only
                else f"{salt}|{key}|{index}|{scale}|{int(edge_only)}")
    digest = hashlib.sha256(material.encode()).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    if family_name.startswith(("scale_then_running", "even_then_scale", "dedupe_then_chunk",
                               "dedupe_running_even")):
        base = rng.choice([4, 5, 6, 9]) * max(1, scale)
        args, _ = _composition(family_name, "", rng, min(base, 40))
        return args
    fam = FAMILIES.get(family_name)
    if fam is None:
        return []
    size = rng.choice([9, 10, 11]) * max(1, scale)
    if fam.edge_draws and (edge_only or rng.random() < 0.34):
        return rng.choice(fam.edge_draws)(rng)
    return fam.draw(rng, min(size, 48))


def expected_output(family_name: str, args: list[Any], prompt: str = "") -> Any:
    """Reference output, computed by the evaluator — never handed to the agent."""
    if family_name.startswith(("scale_then_running", "even_then_scale", "dedupe_then_chunk",
                               "dedupe_running_even")):
        _, fn = _composition(family_name, prompt, random.Random(0), 4)
        return fn(*args)
    fam = FAMILIES.get(family_name)
    if fam is None:
        return None
    try:
        return fam.solve(*args)
    except Exception:
        return _MISSING


class _Missing:
    def __repr__(self) -> str:
        return "<no reference>"


_MISSING = _Missing()
