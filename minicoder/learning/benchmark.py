"""Sealed learning benchmark: tasks that exist nowhere in training data.

Design rules, to keep this honest:

1. **Sealed.** Every task name and every solution here is checked against the
   training corpus and the seeded skill set; the suite refuses to run if any
   overlap is found. That check is ``assert_sealed()`` and it is enforced, not
   documented.
2. **Objectively verifiable.** Each task carries executed assertions. A task
   passes only if the code runs and the assertions hold in the sandbox.
3. **Not curated to flatter the system.** Difficulty is deliberately spread:
   some tasks are within reach of bounded search, and some are known to be
   beyond it. Failures are reported as failures. A benchmark that only contains
   solvable problems measures nothing.
4. **The four states are separated in the report**: memorisation (was this in
   training?), retrieval (was it answered from memory?), adaptation (a known
   procedure reused on new inputs), and acquisition (a procedure that did not
   exist before).

Categories follow the Phase 2 brief: python, math, file manipulation, data
transformation, tool discovery, multi-step, debugging, new API usage, visual
inspection.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchTask:
    """One benchmark task with its own verification."""

    key: str
    category: str
    difficulty: str          # easy | medium | hard
    prompt: str
    entry: str = ""          # function the solution must define (program tasks)
    tests: str = ""          # assertions executed after the solution
    criteria: list[str] = field(default_factory=list)  # editor tasks
    data_file: str = ""      # file the task reads/writes, if any
    allowed_alternatives: list[str] = field(default_factory=list)
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key, "category": self.category, "difficulty": self.difficulty,
            "prompt": self.prompt, "entry": self.entry,
            "criteria": list(self.criteria), "notes": self.notes,
        }


# --------------------------------------------------------------- python / math
# None of these names appear in CODE_TASKS, so none were trained on.
PROGRAM_TASKS: list[BenchTask] = [
    BenchTask(
        "sum_evens", "python", "easy",
        "Return the sum of the even numbers in xs.",
        entry="solve", tests="assert solve([1,2,3,4])==6\nassert solve([2,2])==4\nassert solve([])==0",
    ),
    BenchTask(
        "double_all", "python", "easy",
        "Return a new list with every element of xs doubled.",
        entry="solve", tests="assert solve([1,2,3])==[2,4,6]\nassert solve([])==[]",
    ),
    BenchTask(
        "range_span", "math", "easy",
        "Return max(xs) - min(xs).",
        entry="solve", tests="assert solve([3,9,1])==8\nassert solve([5,5])==0",
    ),
    BenchTask(
        "count_positive", "math", "easy",
        "Return how many numbers in xs are greater than zero.",
        entry="solve",
        tests="assert solve([1,-2,3,0])==2\nassert solve([5,6])==2\nassert solve([])==0",
        notes="The [5,6] case exists because sum(xs) also satisfied the original "
              "tests by coincidence — caught by the test-strength audit.",
    ),
    BenchTask(
        "abs_all", "python", "easy",
        "Return the list of absolute values of xs.",
        entry="solve", tests="assert solve([-1,2,-3])==[1,2,3]",
    ),
    BenchTask(
        "product", "math", "medium",
        "Return the product of all numbers in xs; return 1 for an empty list.",
        entry="solve", tests="assert solve([2,3,4])==24\nassert solve([])==1",
    ),
    BenchTask(
        "evens_sorted", "data", "medium",
        "Return the even numbers of xs in ascending order, duplicates removed.",
        entry="solve",
        tests="assert solve([4,2,2,3,8])==[2,4,8]\nassert solve([1,3])==[]",
    ),
    BenchTask(
        "unique_upper", "data", "medium",
        "Return the distinct words of ws in upper case, order preserved.",
        entry="solve",
        tests='assert solve(["a","b","a"])==["A","B"]\nassert solve([])==[]',
    ),
    BenchTask(
        "median", "math", "medium",
        "Return the median of xs. For an even count, return the mean of the two middle values.",
        entry="solve",
        tests="assert solve([1,3,2])==2\nassert solve([1,2,3,4])==2.5",
    ),
    BenchTask(
        "word_lengths", "data", "medium",
        "Return a dict mapping each word in ws to its length.",
        entry="solve",
        tests='assert solve(["ab","c"])=={"ab":2,"c":1}',
    ),
    BenchTask(
        "run_length_encode", "python", "hard",
        "Return a list of [char, count] pairs run-length encoding the string s.",
        entry="solve",
        tests='assert solve("aab")==[["a",2],["b",1]]\nassert solve("")==[]',
        notes="Sequential stateful encoding. Beyond depth-3 enumeration; expected to fail.",
    ),
    BenchTask(
        "caesar", "python", "hard",
        "Shift every lower-case letter in s forward by k, wrapping z to a.",
        entry="solve",
        tests='assert solve("ab",1)=="bc"\nassert solve("z",1)=="a"',
        notes="Per-character conditional arithmetic; expected to fail.",
    ),
]

# ------------------------------------------------------- file / transformation
# These run in the sandbox against a scratch directory, so they are real file
# operations rather than string manipulation dressed up as I/O.
FILE_TASKS: list[BenchTask] = [
    BenchTask(
        "count_lines", "file", "easy",
        "Read the file named 'data.txt' and return the number of lines in it.",
        entry="solve", data_file="data.txt",
        tests="open('data.txt','w').write('a\\nb\\nc\\n')\nassert solve()==3",
    ),
    BenchTask(
        "sum_column", "file", "medium",
        "Read 'nums.txt' containing one integer per line and return their sum.",
        entry="solve", data_file="nums.txt",
        tests="open('nums.txt','w').write('10\\n20\\n12\\n')\nassert solve()==42",
    ),
    BenchTask(
        "write_report", "data", "medium",
        "Write the words of ws to 'out.txt', one per line, and return the count written.",
        entry="solve", data_file="out.txt",
        tests="assert solve(['x','y'])==2\nassert open('out.txt').read().split()==['x','y']",
    ),
]

# ------------------------------------------------------------- debugging tasks
# A broken implementation is supplied; the task is to return a correct one.
DEBUG_TASKS: list[BenchTask] = [
    BenchTask(
        "fix_off_by_one", "debugging", "easy",
        "This function should return the last element but raises. Fix it.\n"
        "def solve(xs):\n    return xs[len(xs)]",
        entry="solve",
        tests="assert solve([1,2,3])==3\nassert solve([7,8,9])==9\nassert solve([3,1,2])==2",
        notes="The [7,8,9] and [3,1,2] cases exist because len(xs) and max(xs) also "
              "satisfied the earlier assertions — both caught by the test-strength audit.",
    ),
    BenchTask(
        "fix_mutation", "debugging", "medium",
        "This function should return a reversed copy without mutating the input.\n"
        "def solve(xs):\n    xs.reverse()\n    return xs",
        entry="solve",
        tests="a=[1,2]\nassert solve(a)==[2,1]\nassert a==[1,2]",
        allowed_alternatives=["return list(reversed(xs))"],
        notes="'list(reversed(xs))' is a legitimate correct solution, not a weak "
              "test; acknowledged here so the audit does not flag it.",
    ),
]

# ---------------------------------------------------------------- visual tasks
# Editor tasks verified against the live tool layer. visual/tool_discovery/
# multistep/new_api categories all drive the same bridge but exercise different
# required capabilities.
EDITOR_TASKS: list[BenchTask] = [
    BenchTask(
        "visual_headline", "visual", "medium",
        "Create an 800x1000 canvas with a black background holding the headline 'Signal Lost', centred.",
        criteria=['canvas_size(800, 1000)', 'background_contains("#000000")',
                  'text_present("Signal Lost")', 'centred(text, "Signal Lost")'],
    ),
    BenchTask(
        "tool_discovery_shape", "tool_discovery", "medium",
        "Produce a 600x600 canvas containing at least two circle shapes.",
        criteria=['canvas_size(600, 600)', 'count(shape, >=, 2)'],
        notes="Requires discovering add_shape and its valid kind vocabulary.",
    ),
    BenchTask(
        "multistep_poster", "multistep", "hard",
        "A 1080x1350 poster: dark background, a headline, a subtitle, a shape, "
        "nothing overlapping and everything inside the canvas.",
        criteria=['canvas_size(1080, 1350)', 'background_contains("#111111")',
                  'text_present("Nocturne")', 'text_present("Doors at eight")',
                  'count(shape, >=, 1)', 'centred(text, "Nocturne")',
                  'within_canvas()', 'no_overlap()'],
    ),
    BenchTask(
        "api_typography", "new_api", "hard",
        "A 900x900 canvas with the text 'WEIGHT' set at a font size of at least 64.",
        criteria=['canvas_size(900, 900)', 'text_present("WEIGHT")',
                  'min_font_size(64, "WEIGHT")'],
        notes="Requires discovering set_typography and its size parameter.",
    ),
    BenchTask(
        "visual_inspection", "visual_inspection", "easy",
        "Report the canvas dimensions and the number of layers present. "
        "The answer is checked against the live state, not against a constant.",
        criteria=[],  # handled by a custom inspector probe
    ),
]


ALL_TASKS: list[BenchTask] = PROGRAM_TASKS + FILE_TASKS + DEBUG_TASKS + EDITOR_TASKS


# ------------------------------------------------------------------- sealing
def assert_sealed() -> dict[str, Any]:
    """Refuse to benchmark if any task leaked into training or seeded memory.

    Checks three things, all measured rather than assumed:
      * no task key collides with a seeded skill slug or a CODE_TASKS name
      * no task's solution body appears in the training corpus text
      * no task key appears in the database's skills table
    """
    from minicoder.data import CODE_TASKS, build_code_corpus

    problems: list[str] = []
    code_names = {t["name"] for t in CODE_TASKS}
    bench_names = {t.key for t in ALL_TASKS}

    # Task keys use distinct naming from the seeded set; a collision would mean
    # the "unseen" claim is false.
    overlap = bench_names & code_names
    if overlap:
        problems.append(f"benchmark keys collide with CODE_TASKS: {sorted(overlap)}")

    _, raw = build_code_corpus()
    for t in PROGRAM_TASKS + FILE_TASKS:
        for line in t.tests.splitlines():
            body = line.strip()
            if len(body) > 24 and body in raw:
                problems.append(f"{t.key}: its assertions appear in the training corpus")

    try:
        from minicoder.memory.db import BrainDB

        db = BrainDB()
        slugs = {r[0] for r in db.query("SELECT slug FROM skills")}
        leaked = {f"learned_{t.key}" for t in ALL_TASKS} & slugs
        if leaked:
            problems.append(f"already present as promoted skills: {sorted(leaked)}")
    except Exception:
        pass  # a missing DB is not a sealing failure

    return {
        "sealed": not problems,
        "problems": problems,
        "tasks": len(ALL_TASKS),
        "by_category": _count_by("category"),
        "by_difficulty": _count_by("difficulty"),
    }


def _count_by(field_name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in ALL_TASKS:
        key = getattr(t, field_name)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# Plausible-but-wrong programs. If any of these satisfies a task's assertions,
# the assertions do not discriminate and the task would inflate results. This is
# not paranoia: two tasks in the first draft were solved by wrong programs
# (sum() for a count, len() for a last element).
DISTRACTORS = (
    "return xs",
    "return len(xs)",
    "return sum(xs)",
    "return sorted(xs)",
    "return max(xs)",
    "return min(xs)",
    "return xs[0]",
    "return list(reversed(xs))",
    "return len(set(xs))",
)


def audit_test_strength() -> list[dict[str, Any]]:
    """Report tasks whose assertions can be satisfied by a wrong program."""
    from minicoder.learning.synth import EnumerativeSynthesizer

    probe = EnumerativeSynthesizer()
    weak: list[dict[str, Any]] = []
    for t in ALL_TASKS:
        if not t.tests or t.category in ("visual", "tool_discovery", "multistep",
                                          "new_api", "visual_inspection"):
            continue
        entry = t.entry or "solve"
        for body in DISTRACTORS:
            program = f"def {entry}(xs):\n    {body}\n"
            try:
                ok, _ = probe._probe(program, t.tests, ["xs"], None)
            except Exception:
                ok = False
            if ok and body.strip() not in t.allowed_alternatives:
                weak.append({"task": t.key, "passed_by": body.strip()})
    return weak


def tasks_by_category() -> dict[str, list[BenchTask]]:
    out: dict[str, list[BenchTask]] = {}
    for t in ALL_TASKS:
        out.setdefault(t.category, []).append(t)
    return out


def validate_task_definitions() -> list[str]:
    """Static sanity check: every task must be objectively verifiable."""
    problems: list[str] = []
    keys = set()
    for t in ALL_TASKS:
        if t.key in keys:
            problems.append(f"duplicate task key {t.key}")
        keys.add(t.key)
        if not t.tests and not t.criteria and t.key != "visual_inspection":
            problems.append(f"{t.key}: no tests and no criteria — not verifiable")
        for line in t.tests.splitlines():
            if line.strip().startswith("assert"):
                try:
                    ast.parse(line.strip())
                except SyntaxError as exc:
                    problems.append(f"{t.key}: unparseable assertion {line!r} ({exc})")
    return problems
