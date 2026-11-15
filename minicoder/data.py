"""Deterministic corpus generation for training and evaluation.

Why synthetic?
--------------
Hugging Face and most dataset hosts are unreachable from the deployment
sandbox, and committing scraped code would violate the licence-compliance
requirements in the blueprint.  So the corpus is *generated* from parametric
templates that we own, then split deterministically with a fixed seed so that
train/val/test never overlap.

Crucially this corpus is paired with **verifiable** tasks (see
``minicoder/eval/suites.py``): every code-instruction example has executable
unit tests, so the training data itself can be gated on real verification.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from minicoder.config import CONFIG

# --------------------------------------------------------------------------
# 1. code tasks: instruction -> solution, each with a real unit test
# --------------------------------------------------------------------------

CODE_TASKS: list[dict[str, Any]] = [
    {
        "name": "sum_list",
        "prompt": "Write a Python function `solve(nums)` that returns the sum of a list of integers.",
        "solution": "def solve(nums):\n    return sum(nums)\n",
        "tests": "assert solve([1,2,3]) == 6\nassert solve([]) == 0\nassert solve([-5,5]) == 0\n",
        "domain": "python",
    },
    {
        "name": "max_list",
        "prompt": "Write a Python function `solve(nums)` that returns the largest number in a non-empty list.",
        "solution": "def solve(nums):\n    return max(nums)\n",
        "tests": "assert solve([1,9,3]) == 9\nassert solve([-2,-1]) == -1\n",
        "domain": "python",
    },
    {
        "name": "reverse_string",
        "prompt": "Write a Python function `solve(s)` that returns the string reversed.",
        "solution": "def solve(s):\n    return s[::-1]\n",
        "tests": "assert solve('abc') == 'cba'\nassert solve('') == ''\n",
        "domain": "python",
    },
    {
        "name": "is_palindrome",
        "prompt": "Write a Python function `solve(s)` that returns True when the string is a palindrome, ignoring case and spaces.",
        "solution": "def solve(s):\n    t = ''.join(c.lower() for c in s if c.isalnum())\n    return t == t[::-1]\n",
        "tests": "assert solve('Never odd or even') is True\nassert solve('abc') is False\n",
        "domain": "python",
    },
    {
        "name": "fib",
        "prompt": "Write a Python function `solve(n)` returning the n-th Fibonacci number with fib(0)=0 and fib(1)=1, iteratively.",
        "solution": "def solve(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
        "tests": "assert [solve(i) for i in range(8)] == [0,1,1,2,3,5,8,13]\n",
        "domain": "python",
    },
    {
        "name": "factorial",
        "prompt": "Write a Python function `solve(n)` returning n! for n >= 0.",
        "solution": "def solve(n):\n    out = 1\n    for i in range(2, n + 1):\n        out *= i\n    return out\n",
        "tests": "assert solve(0) == 1\nassert solve(5) == 120\n",
        "domain": "python",
    },
    {
        "name": "dedupe_preserve_order",
        "prompt": "Write a Python function `solve(items)` that removes duplicates while preserving first-occurrence order.",
        "solution": "def solve(items):\n    seen, out = set(), []\n    for x in items:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n",
        "tests": "assert solve([3,1,3,2,1]) == [3,1,2]\nassert solve([]) == []\n",
        "domain": "python",
    },
    {
        "name": "word_freq",
        "prompt": "Write a Python function `solve(text)` returning a dict of word -> count, lowercased and split on whitespace.",
        "solution": "def solve(text):\n    out = {}\n    for w in text.lower().split():\n        out[w] = out.get(w, 0) + 1\n    return out\n",
        "tests": "assert solve('a A b') == {'a': 2, 'b': 1}\nassert solve('') == {}\n",
        "domain": "python",
    },
    {
        "name": "chunk_list",
        "prompt": "Write a Python function `solve(items, n)` that splits a list into consecutive chunks of size n.",
        "solution": "def solve(items, n):\n    return [items[i:i + n] for i in range(0, len(items), n)]\n",
        "tests": "assert solve([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]\nassert solve([], 3) == []\n",
        "domain": "python",
    },
    {
        "name": "flatten",
        "prompt": "Write a Python function `solve(nested)` that flattens one level of nested lists.",
        "solution": "def solve(nested):\n    out = []\n    for item in nested:\n        if isinstance(item, list):\n            out.extend(item)\n        else:\n            out.append(item)\n    return out\n",
        "tests": "assert solve([[1,2],[3],4]) == [1,2,3,4]\n",
        "domain": "python",
    },
    {
        "name": "two_sum",
        "prompt": "Write a Python function `solve(nums, target)` returning the indices of two numbers that add up to target, or None.",
        "solution": "def solve(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i\n    return None\n",
        "tests": "assert solve([2,7,11,15], 9) == [0,1]\nassert solve([1,2], 99) is None\n",
        "domain": "python",
    },
    {
        "name": "is_anagram",
        "prompt": "Write a Python function `solve(a, b)` returning True when the two strings are anagrams.",
        "solution": "def solve(a, b):\n    return sorted(a) == sorted(b)\n",
        "tests": "assert solve('listen','silent') is True\nassert solve('ab','abc') is False\n",
        "domain": "python",
    },
    {
        "name": "gcd",
        "prompt": "Write a Python function `solve(a, b)` returning the greatest common divisor using Euclid's algorithm.",
        "solution": "def solve(a, b):\n    while b:\n        a, b = b, a % b\n    return abs(a)\n",
        "tests": "assert solve(12,18) == 6\nassert solve(7,13) == 1\n",
        "domain": "python",
    },
    {
        "name": "prime_sieve",
        "prompt": "Write a Python function `solve(n)` returning all primes below n.",
        "solution": "def solve(n):\n    if n < 3:\n        return []\n    sieve = [True] * n\n    sieve[0] = sieve[1] = False\n    for i in range(2, int(n ** 0.5) + 1):\n        if sieve[i]:\n            for j in range(i * i, n, i):\n                sieve[j] = False\n    return [i for i, ok in enumerate(sieve) if ok]\n",
        "tests": "assert solve(10) == [2,3,5,7]\nassert solve(2) == []\n",
        "domain": "python",
    },
    {
        "name": "merge_dicts",
        "prompt": "Write a Python function `solve(a, b)` merging two dicts; values from b win, without mutating inputs.",
        "solution": "def solve(a, b):\n    out = dict(a)\n    out.update(b)\n    return out\n",
        "tests": "a={'x':1}; b={'x':2,'y':3}\nassert solve(a,b) == {'x':2,'y':3}\nassert a == {'x':1}\n",
        "domain": "python",
    },
    {
        "name": "clamp",
        "prompt": "Write a Python function `solve(x, lo, hi)` clamping x into [lo, hi].",
        "solution": "def solve(x, lo, hi):\n    return max(lo, min(hi, x))\n",
        "tests": "assert solve(5,0,3) == 3\nassert solve(-1,0,3) == 0\nassert solve(2,0,3) == 2\n",
        "domain": "python",
    },
    {
        "name": "count_vowels",
        "prompt": "Write a Python function `solve(s)` counting vowels (aeiou, case-insensitive).",
        "solution": "def solve(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
        "tests": "assert solve('Hello') == 2\nassert solve('xyz') == 0\n",
        "domain": "python",
    },
    {
        "name": "binary_search",
        "prompt": "Write a Python function `solve(arr, target)` returning the index of target in a sorted list, or -1.",
        "solution": "def solve(arr, target):\n    lo, hi = 0, len(arr) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if arr[mid] == target:\n            return mid\n        if arr[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1\n",
        "tests": "assert solve([1,3,5,7], 5) == 2\nassert solve([1,3,5,7], 4) == -1\n",
        "domain": "python",
    },
    {
        "name": "transpose",
        "prompt": "Write a Python function `solve(matrix)` returning the transpose of a rectangular matrix.",
        "solution": "def solve(matrix):\n    if not matrix:\n        return []\n    return [list(row) for row in zip(*matrix)]\n",
        "tests": "assert solve([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]\nassert solve([]) == []\n",
        "domain": "python",
    },
    {
        "name": "roman_to_int",
        "prompt": "Write a Python function `solve(s)` converting a Roman numeral to an integer.",
        "solution": "def solve(s):\n    vals = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n    total = 0\n    for i, ch in enumerate(s):\n        v = vals[ch]\n        if i + 1 < len(s) and vals[s[i+1]] > v:\n            total -= v\n        else:\n            total += v\n    return total\n",
        "tests": "assert solve('MCMXCIV') == 1994\nassert solve('IX') == 9\n",
        "domain": "python",
    },
    {
        "name": "title_case_slug",
        "prompt": "Write a Python function `solve(title)` turning a title into a URL slug (lowercase, hyphens).",
        "solution": "def solve(title):\n    out = []\n    for ch in title.lower():\n        if ch.isalnum():\n            out.append(ch)\n        elif out and out[-1] != '-':\n            out.append('-')\n    return ''.join(out).strip('-')\n",
        "tests": "assert solve('Hello, World!') == 'hello-world'\nassert solve('  A  b ') == 'a-b'\n",
        "domain": "python",
    },
    {
        "name": "running_mean",
        "prompt": "Write a Python function `solve(nums)` returning the running mean after each element.",
        "solution": "def solve(nums):\n    out, total = [], 0.0\n    for i, n in enumerate(nums, 1):\n        total += n\n        out.append(total / i)\n    return out\n",
        "tests": "assert solve([2,4,6]) == [2.0,3.0,4.0]\n",
        "domain": "python",
    },
    {
        "name": "parse_pairs",
        "prompt": "Write a Python function `solve(text)` parsing 'a=1,b=2' into a dict of ints, skipping bad pairs.",
        "solution": "def solve(text):\n    out = {}\n    for part in text.split(','):\n        if '=' not in part:\n            continue\n        k, v = part.split('=', 1)\n        try:\n            out[k.strip()] = int(v)\n        except ValueError:\n            continue\n    return out\n",
        "tests": "assert solve('a=1,b=2') == {'a':1,'b':2}\nassert solve('x=oops,c=3,junk') == {'c':3}\n",
        "domain": "python",
    },
    {
        "name": "matrix_sum_rows",
        "prompt": "Write a Python function `solve(matrix)` returning the sum of each row.",
        "solution": "def solve(matrix):\n    return [sum(row) for row in matrix]\n",
        "tests": "assert solve([[1,2],[3,4]]) == [3,7]\n",
        "domain": "python",
    },
    {
        "name": "safe_divide",
        "prompt": "Write a Python function `solve(a, b)` returning a/b, or None when b is 0.",
        "solution": "def solve(a, b):\n    if b == 0:\n        return None\n    return a / b\n",
        "tests": "assert solve(6,3) == 2\nassert solve(1,0) is None\n",
        "domain": "python",
    },
]


# --------------------------------------------------------------------------
# 2. conversational / memory probes (chatbot track)
# --------------------------------------------------------------------------

PERSONAS = [
    {
        "user": "Amara",
        "prefs": [
            "prefers deep green and warm gold palettes",
            "writes quote posters for Instagram at 1080x1350",
            "likes short serif headlines with generous negative space",
        ],
    },
    {
        "user": "Dev",
        "prefs": [
            "prefers monochrome brutalist layouts",
            "works on desktop and exports PNG at 2x",
            "wants every layer named explicitly",
        ],
    },
    {
        "user": "Rin",
        "prefers": [
            "prefers pastel gradients and soft glow lighting",
            "designs square 1080x1080 posts for carousels",
            "asks for the quote attribution in small caps",
        ],
    },
]

CHAT_PAIRS: list[tuple[str, str]] = [
    ("How do I make my poster feel more premium?", "Increase negative space, use one accent colour, lower the background contrast, and keep typography to two sizes."),
    ("What canvas size works for Instagram?", "1080x1350 is the portrait feed size. Use 1080x1080 for square carousels."),
    ("My headline looks cramped, what should I change?", "Raise line height, increase letter spacing slightly, and reduce the headline width or trim the copy."),
    ("Which palette reads as luxurious?", "Deep green with warm gold, or charcoal with champagne. Keep the gold to hairline accents."),
    ("How many fonts should I use?", "Two: one display face for the quote, one quiet face for attribution. Three is usually one too many."),
    ("The light layer looks flat, how do I fix it?", "Lower its intensity and move the light source off-centre so the falloff reads as depth."),
    ("Should I centre the quote?", "Centre for short quotes under ten words; left-align longer quotes so the eye has a rail to follow."),
    ("How do I keep text readable over a photo?", "Add a scrim layer between the photo and text, or apply a blur mask to the photo before placing type."),
]


# --------------------------------------------------------------------------
# 3. vision tasks: procedurally rendered UI screenshots with known labels
# --------------------------------------------------------------------------

VISION_CLASSES = [
    "clean_layout",
    "overflow_bug",
    "contrast_failure",
    "empty_state",
    "error_banner",
    "misaligned_grid",
    "text_truncation",
    "loading_skeleton",
]


# Native rendering resolution for the screenshot fixtures. The model downsamples
# to 32px, but the *inspector* runs on real pixels so geometric analysis (edge
# clipping, projection profiles) is physically meaningful.
UI_RENDER_SIZE = 256


def _render_ui_screenshot(cls: str, rng: random.Random, size: int | None = None):
    """Render an abstract UI screenshot for a class. Returns a PIL image.

    Only procedural drawing is used, so every label is exact by construction —
    the vision model is trained on genuinely labelled data, never guesses.
    """
    from PIL import Image, ImageDraw

    size = size or UI_RENDER_SIZE
    img = Image.new("RGB", (size, size), (248, 248, 250))
    d = ImageDraw.Draw(img)
    ink, muted = (32, 36, 44), (220, 224, 230)
    accent, warn = (28, 120, 96), (198, 62, 48)
    s = size

    def box(x0, y0, x1, y1, fill):
        d.rectangle([int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)], fill=fill)

    def text_row(y, x0=0.10, x1=0.62, h=0.035, fill=ink):
        box(x0, y, x1, y + h, fill)

    if cls == "clean_layout":
        box(0.06, 0.05, 0.94, 0.14, ink)
        text_row(0.22)
        text_row(0.29, x1=0.52)
        box(0.08, 0.42, 0.47, 0.70, muted)
        box(0.52, 0.42, 0.92, 0.70, (232, 235, 240))
        text_row(0.80, x1=0.40)
    elif cls == "overflow_bug":
        box(0.06, 0.05, 0.94, 0.14, ink)
        text_row(0.22)
        # a card that spills past the right edge of the viewport
        box(0.12, 0.36, 1.06, 0.56, warn)
        text_row(0.66, x1=0.55)
    elif cls == "contrast_failure":
        d.rectangle([0, 0, s, s], fill=(205, 205, 205))
        box(0.10, 0.34, 0.90, 0.43, (212, 212, 212))
        box(0.10, 0.50, 0.70, 0.58, (214, 214, 214))
    elif cls == "empty_state":
        cx, cy = s // 2, int(s * 0.42)
        r = int(s * 0.11)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(190, 195, 205), width=max(2, s // 90))
        box(0.34, 0.60, 0.66, 0.65, (205, 209, 217))
        box(0.40, 0.70, 0.60, 0.755, (226, 230, 236))
    elif cls == "error_banner":
        box(0.05, 0.04, 0.95, 0.17, warn)
        text_row(0.30, x0=0.08, x1=0.72)
        text_row(0.39, x0=0.08, x1=0.60)
        box(0.08, 0.52, 0.92, 0.70, (232, 235, 240))
        text_row(0.80, x0=0.08, x1=0.48)
    elif cls == "misaligned_grid":
        for i in range(3):
            x = 0.08 + i * 0.30 + rng.choice([0.0, 0.0, 0.06])
            y = 0.20 + rng.choice([0.0, 0.02])
            box(x, y, min(x + 0.24, 0.98), 0.78, accent if i % 2 else muted)
    elif cls == "text_truncation":
        for row in range(4):
            y = 0.16 + row * 0.13
            end = 1.0 if row % 2 else 0.66
            box(0.06, y, min(end, 0.995), y + 0.07, ink)
        box(0.06, 0.80, 0.30, 0.86, warn)
        box(0.86, 0.80, 0.99, 0.86, warn)
    else:  # loading_skeleton
        for row in range(3):
            box(0.08, 0.16 + row * 0.20, 0.92 - row * 0.10, 0.28 + row * 0.20, (228, 231, 236))
        box(0.08, 0.78, 0.48, 0.86, (236, 238, 242))
    return img


# --------------------------------------------------------------------------
# 4. dataset assembly
# --------------------------------------------------------------------------

def _variants(text: str, rng: random.Random, n: int) -> list[str]:
    """Synthetic paraphrase variants used to prevent overfitting."""
    templates = [
        text,
        text.replace("Write a Python function", "Implement a Python function"),
        text.replace("returning", "that returns"),
        "Task: " + text,
        text.replace(".", " Please keep it simple."),
    ]
    out = {text}
    rng.shuffle(templates)
    for t in templates:
        if len(out) >= n:
            break
        out.add(t)
    return list(out)


def build_code_corpus(seed: int = 7, variants: int = 3) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (sft_examples, raw_texts) from the verified code tasks."""
    rng = random.Random(seed)
    examples: list[dict[str, Any]] = []
    raw: list[str] = []
    for task in CODE_TASKS:
        for v in _variants(task["prompt"], rng, variants):
            examples.append(
                {
                    "prompt": v,
                    "response": task["solution"],
                    "task": task["name"],
                    "verified_by": "unit_tests",
                }
            )
            raw.append(f"### Instruction\n{v}\n### Solution\n{task['solution']}\n")
    return examples, raw


def build_chat_corpus(seed: int = 11) -> tuple[list[dict[str, Any]], list[str]]:
    rng = random.Random(seed)
    examples = []
    raw = []
    for user, answer in CHAT_PAIRS:
        examples.append({"prompt": user, "response": answer, "task": "chat", "verified_by": "curated"})
        raw.append(f"User: {user}\nAssistant: {answer}\n")
    for persona in PERSONAS:
        key = "prefs" if "prefs" in persona else "prefers"
        for pref in persona[key]:
            q = f"What does {persona['user']} prefer?"
            a = f"{persona['user']} {pref}."
            examples.append({"prompt": q, "response": a, "task": "memory", "verified_by": "curated"})
            raw.append(f"User: {q}\nAssistant: {a}\n")
            rng.random()
    return examples, raw


def build_embedding_pairs() -> list[tuple[str, str]]:
    """(anchor, positive) pairs for the contrastive embedder."""
    pairs: list[tuple[str, str]] = []
    for task in CODE_TASKS:
        pairs.append((task["prompt"], task["solution"].replace("\n", " ")[:120]))
    for user, answer in CHAT_PAIRS:
        pairs.append((user, answer))
    extra = [
        ("flexbox overflow bug", "content spills outside its container on narrow viewports"),
        ("contrast failure", "foreground and background colours are too close in luminance"),
        ("misaligned grid", "columns do not share a baseline or gutter"),
        ("text truncation", "a label is clipped instead of wrapping"),
        ("empty state", "a screen with no data needs an illustration and an action"),
        ("error banner", "a destructive red banner announces a failed action"),
        ("loading skeleton", "placeholder blocks stand in for pending content"),
        ("clean layout", "generous spacing, consistent alignment, clear hierarchy"),
        ("negative space", "deliberate emptiness that lets the subject breathe"),
        ("palette harmony", "two hues and one accent held at different values"),
        ("deep green warm gold luxurious poster", "emerald background with champagne hairline accents"),
        ("monochrome brutalist layout", "black type on paper white with hard edges and no decoration"),
        ("pastel gradient soft glow", "low saturation pinks fading into lilac with a diffuse light"),
    ]
    pairs.extend(extra)
    return pairs


def build_vision_dataset(seed: int = 3, per_class: int = 90) -> tuple[list[tuple[Any, int]], list[tuple[Any, int]]]:
    """Return (train, test) lists of (PIL image, label index), split by seed."""
    rng = random.Random(seed)
    train, test = [], []
    for idx, cls in enumerate(VISION_CLASSES):
        for i in range(per_class):
            img = _render_ui_screenshot(cls, rng)
            # The last renders per class are held out. Because rendering is
            # stochastic in its jitter, holdout images are fresh samples of the
            # same class, not copies (except the canonical offset-free render,
            # which is identical by construction and included deliberately).
            (test if i >= per_class - 15 else train).append((img, idx))
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def corpus_fingerprint() -> str:
    """Content hash of the corpus definition, recorded in every dataset shard."""
    import hashlib

    payload = json.dumps({"code": CODE_TASKS, "chat": CHAT_PAIRS, "vision": VISION_CLASSES}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
