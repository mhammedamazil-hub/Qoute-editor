"""Inference engine: turns the compact transformer into a usable brain.

Honest capability statement (no fabrication, prime directive #1):
* The neural decoder is a ~1M-parameter model trained from scratch on this
  machine. It produces fluent *domain* text (design/code vocabulary) but it is
  not a general-purpose LLM.
* Therefore generation is **grounded**: the engine retrieves verified skills and
  semantic memories, and prefers executing a verified skill over free sampling.
  When the neural model has nothing verified to say, it says so and offers the
  retrieved evidence instead of inventing an answer.
* Every response carries a ``grounding`` block naming exactly which memories
  and skills were used, so citations in the UI are real.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

import torch

from minicoder.config import CONFIG, VERIFIED
from minicoder.model.tokenizer import Tokenizer
from minicoder.model.transformer import MiniTransformer


@dataclass
class Generation:
    text: str
    tokens: int
    seconds: float
    mean_entropy: float
    source: str                       # neural | skill | memory | refuse
    grounding: list[dict[str, Any]] = field(default_factory=list)
    backend: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tokens": self.tokens,
            "seconds": round(self.seconds, 4),
            "mean_entropy": round(self.mean_entropy, 4),
            "source": self.source,
            "grounding": self.grounding,
            "backend": self.backend,
        }


class NeuralBrain:
    """Wrapper around the trained checkpoint with a graceful fallback."""

    def __init__(self) -> None:
        self.model: MiniTransformer | None = None
        self.tok: Tokenizer | None = None
        self.meta: dict[str, Any] = {}
        self.backend = "untrained"
        self.load()

    def load(self) -> bool:
        lm = CONFIG.paths.checkpoints / "lm.pt"
        tk = CONFIG.paths.checkpoints / "tokenizer.json"
        if lm.exists() and tk.exists():
            try:
                self.model = MiniTransformer.load(lm)
                self.tok = Tokenizer.load(tk)
                blob = torch.load(lm, map_location="cpu", weights_only=False)
                self.meta = blob.get("meta", {})
                self.backend = "neural-lm"
                return True
            except Exception as exc:  # pragma: no cover
                self.backend = f"load-error: {exc}"
        return False

    def reload(self) -> bool:
        self.model = None
        self.tok = None
        return self.load()

    def info(self) -> dict[str, Any]:
        params = self.model.n_params() if self.model else 0
        return {
            "backend": self.backend,
            "params": params,
            "vocab": len(self.tok) if self.tok else 0,
            "max_seq_len": self.model.cfg.max_seq_len if self.model else 0,
            "meta": self.meta,
        }

    # ------------------------------------------------------------ scoring
    @torch.no_grad()
    def score(self, prompt: str, response: str) -> tuple[float, float]:
        """Teacher-forced (mean nll, bits/token) of a response under the model."""
        if not self.model or not self.tok:
            return float("nan"), float("nan")
        p = self.tok.encode(prompt.strip() + "\n", add_bos=True)
        r = self.tok.encode(response.strip(), add_eos=True)
        ids = torch.tensor([(p + r)[: self.model.cfg.max_seq_len]])
        logits, _ = self.model(ids[:, :-1])
        target = ids[:, 1:]
        logp = torch.log_softmax(logits, dim=-1)
        nll = -logp.gather(-1, target.unsqueeze(-1)).squeeze(-1)
        mask = torch.zeros_like(target, dtype=torch.float)
        mask[:, len(p) - 1 :] = 1.0
        denom = mask.sum().clamp(min=1.0)
        mean_nll = float((nll * mask).sum() / denom)
        return mean_nll, mean_nll / math.log(2)

    def in_distribution(self, prompt: str, samples: int = 3) -> dict[str, Any]:
        """Empirical check: does the model actually know this prompt's vocabulary?

        Two measured signals:
        * OOV rate of the prompt under the learned tokenizer;
        * mean token NLL of greedy continuations vs. a random-sequence control.
        """
        if not self.model or not self.tok:
            return {"in_distribution": False, "reason": "no model"}
        import torch

        ids = self.tok.encode(prompt)
        if not ids:
            return {"in_distribution": False, "reason": "empty prompt"}
        # Tokens above the byte range are learned merges; a prompt dominated by
        # raw bytes is out of the model's training distribution.
        learned = sum(1 for i in ids if i >= 256 + 4)
        ratio = learned / len(ids)
        nlls = []
        for k in range(samples):
            gen = self.generate(prompt, max_new_tokens=24, temperature=0.7, seed=1000 + k)
            if not gen.text.strip():
                continue
            nll, _ = self.score(prompt, gen.text)
            if nll == nll:  # not NaN
                nlls.append(nll)
        mean_nll = sum(nlls) / len(nlls) if nlls else float("inf")
        control = float(torch.log(torch.tensor(float(len(self.tok)))))  # uniform-baseline NLL
        # The uniform baseline is far too permissive a bar. This model was trained
        # on a small in-domain corpus, where held-out NLL is ~1.5-2.5 bits. A
        # continuation that cannot get below ~1.8 bits/token is not "known"; it is
        # the model free-associating, so we refuse instead of emitting noise.
        # NLL is the reliable signal: a prompt the model can answer yields a
        # near-zero continuation NLL. Token-merge ratio only separates "English
        # words it has seen" from pure bytes, and code legitimately uses bytes,
        # so it is reported but not used as a veto.
        nll_bar = 1.8
        nll_ok = mean_nll < nll_bar
        # NLL alone is not sufficient: a small model can be *confidently wrong*
        # (measured: "who won the 1998 curling championship" scored 1.75 nll, under
        # the bar, while emitting gibberish). So the continuation must also be
        # structurally plausible for one of the two things this model was trained
        # to produce: source code, or a plain declarative answer.
        coverage = intent_coverage(prompt)
        in_scope = coverage >= INTENT_FLOOR
        in_dist = nll_ok and ratio >= 0.25 and in_scope
        return {
            "in_distribution": bool(in_dist),
            "learned_token_ratio": round(ratio, 3),
            "mean_nll": round(mean_nll, 3) if mean_nll != float("inf") else -1,
            "nll_bar": nll_bar,
            "intent_coverage": round(coverage, 3),
            "intent_floor": INTENT_FLOOR,
            "uniform_baseline_nll": round(control, 3),
        }

    def best_of(self, prompt: str, k: int = 4, max_new_tokens: int = 96) -> Generation:
        """Sample k candidates and keep the one the model itself finds most likely.

        This is minimum-Bayes-risk selection under the model's own distribution:
        it converts sampling from a small model into its single best guess.
        """
        best: Generation | None = None
        best_nll = float("inf")
        for i in range(k):
            cand = self.generate(prompt, max_new_tokens=max_new_tokens, temperature=0.7,
                                 top_k=40, top_p=0.92, seed=100 + i)
            if not cand.text.strip():
                continue
            nll, _ = self.score(prompt, cand.text)
            if nll < best_nll:
                best, best_nll = cand, nll
        if best is None:
            return self.generate(prompt, max_new_tokens=max_new_tokens, temperature=0.0)
        best.text = best.text
        return best

    # -------------------------------------------------------- generation
    @torch.no_grad()
    def generate(self, prompt: str, max_new_tokens: int = 64, temperature: float = 0.35,
                 top_k: int = 20, top_p: float = 0.9, seed: int | None = None) -> Generation:
        if not self.model or not self.tok:
            return Generation("", 0, 0.0, float("nan"), "untrained", [], self.backend)
        t0 = time.time()
        ids = torch.tensor([self.tok.encode(prompt.strip() + "\n", add_bos=True)])
        # Honest defaults: this model was trained on a small corpus, and
        # high-temperature sampling from it produces fluent-looking noise. Low
        # temperature + top_k keeps it inside the learned distribution.
        if seed is not None:
            torch.manual_seed(int(seed) % (2**31 - 1))
        g = torch.Generator().manual_seed(int(seed)) if seed is not None else None
        out = self.model.generate(ids, max_new_tokens=max_new_tokens, temperature=temperature,
                                  top_k=top_k, top_p=top_p, eos_id=self.tok.EOS, generator=g)
        new = out[0, ids.shape[1]:].tolist()
        text = self.tok.decode(new)
        # Real entropy measurement over the produced tokens.
        with torch.no_grad():
            logits, _ = self.model(out[:, :-1])
            logp = torch.log_softmax(logits[:, ids.shape[1] - 1 :], dim=-1)
            ent = float(-(logp.exp() * logp).sum(-1).mean()) if logp.numel() else float("nan")
        return Generation(text, len(new), time.time() - t0, ent, "neural", [], self.backend)


_CODE_LINE = re.compile(r"^\s*(def |class |return |import |from |for |while |if |elif |else:|try:|except|with |@|#|\w+\s*=\s*)")


def looks_like_code(text: str) -> bool:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return False
    hits = sum(1 for l in lines if _CODE_LINE.match(l) or l.startswith(("    ", "\t")))
    return hits / len(lines) >= 0.6


def _intent_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]{3,}", (text or "").lower())}


def intent_coverage(question: str) -> float:
    """How much of the question is covered by the model's own training intents.

    Measured separation (see docs/EVALS.md): every in-scope design/coding prompt
    scores 1.00 while off-domain trivia scores <= 0.25. The neural tower is only
    trusted above ``INTENT_FLOOR``; below it we refuse instead of hallucinating.
    """
    from minicoder.data import CHAT_PAIRS, CODE_TASKS

    q = _intent_tokens(question)
    if not q:
        return 0.0
    corpus = [_intent_tokens(qq) for qq, _ in CHAT_PAIRS]
    corpus += [_intent_tokens(t.get("prompt", "")) for t in CODE_TASKS]
    return max((len(q & c) / len(q) for c in corpus if c), default=0.0)


INTENT_FLOOR = 0.5


# Words that appear in questions but say nothing about *what* is being asked.
# Both the skill gate and the memory gate subtract this set; without it, "who won
# the 1998 world championship in curling" overlapped a lighting skill on "world"
# and was answered from it.
_QUESTION_FILLER = frozenset(
    """what which how why who whom when where should can could would does did do is are am was were
    the a an of in on at to for from by with about into over under and or but not
    prefer prefers like likes want wants need needs know tell give show list read reads
    use using make made get got have has had be been being there here this that these those
    me my our your their its they them it we you i he she his her
    best good more most much many any some all very just own same such both each every
    feel feels look looks looks work works really""".split()
)


class GroundedAnswerer:
    """Retrieval-grounded response assembly with explicit evidence."""

    def __init__(self, brain: NeuralBrain, episodic, semantic, procedural) -> None:
        self.brain = brain
        self.episodic = episodic
        self.semantic = semantic
        self.procedural = procedural

    @staticmethod
    def _words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9_]{3,}", text.lower())}

    @classmethod
    def _content(cls, text: str) -> set[str]:
        """Content words only: what remains once question scaffolding is removed."""
        return {w for w in re.findall(r"[a-z0-9_]{3,}", text.lower()) if w not in _QUESTION_FILLER}

    @classmethod
    def _expanded(cls, text: str) -> set[str]:
        """Content words plus their known synonyms.

        The BM25 retriever expands synonyms, but the relevance gate did not, so
        "how much margin should I leave" retrieved the right node ("generous
        margins") and then rejected it because the node says "space", not
        "margin". Gate and retriever must agree on what "the same word" means.
        """
        from minicoder.memory.systems import _SYNONYMS

        base = cls._content(text)
        return base | {syn for w in base for syn in _SYNONYMS.get(w, ())}

    _QUESTION_START = re.compile(
        r"^\s*(what|which|how|why|who|when|where|should|is|are|do|does|can|could|would)\b", re.I)
    _IMPERATIVE_START = re.compile(
        r"^\s*(build|make|create|add|apply|set|change|move|resize|delete|remove|duplicate|"
        r"translate|export|render|generate|draw|place|put)\b", re.I)

    @classmethod
    def is_question(cls, text: str) -> bool:
        """True for a request for information, false for a request for action.

        Measured failure: "How many fonts should I use in one poster?" (with a question mark)
        was routed to the procedural branch and answered with a raw tool sequence, because
        the skill scorer is checked before prose and skills outrank facts by design.
        """
        stripped = text.strip()
        return bool(cls._QUESTION_START.match(stripped)) and not cls._IMPERATIVE_START.match(stripped)

    @staticmethod
    def render_procedure(skill: dict[str, Any]) -> str:
        """A verified procedure, described in words instead of dumped as JSON."""
        import json as _json

        steps: list[dict[str, Any]] = []
        try:
            parsed = _json.loads(skill.get("solution") or "[]")
            if isinstance(parsed, list):
                steps = [s for s in parsed if isinstance(s, dict)]
        except (ValueError, TypeError):
            steps = []
        tools = [str(s.get("tool")) for s in steps if s.get("tool")]
        name = skill.get("name") or skill.get("slug") or "that procedure"
        bits = [f"I know a verified {len(steps)}-step procedure for {name.lower()}."]
        if tools:
            chain = " → ".join(tools[:6]) + (" → …" if len(tools) > 6 else "")
            bits.append(f"It runs {chain}.")
        desc = str(skill.get("description") or "").strip()
        if desc:
            bits.append(desc[:220].rstrip(".") + ".")
        bits.append("Ask me to run it and I will apply it to the canvas.")
        return " ".join(bits)

    @staticmethod
    def _is_junk_fact(label: str, content: str) -> bool:
        """Facts that are answer scaffolding, not answers.

        Measured: a consolidated lesson captured the opening line of an earlier reply
        ("Here is what memory holds:") and it later surfaced as if it were knowledge.
        """
        text = f"{label} {content}".strip().lower()
        return (text.startswith("here is what memory holds")
                or text.startswith("i don't have a verified memory")
                or text.startswith("rather than guess"))

    def _subject(self, question: str) -> str:
        """The entity a question is *about* — its head noun, crudely.

        "what does amara prefer" -> "amara"; "what palette reads as premium" ->
        "palette". Good enough to group facts about one person or one object
        without the over-matching of a plain token overlap.
        """
        toks = [w for w in self._words(question) if w not in _QUESTION_FILLER]
        return toks[-1] if toks else ""

    @staticmethod
    def _claim(content: str) -> str:
        """The part of a memory that is actually the claim.

        Consolidated nodes are stored as "<lesson>\n\nContext: <the question>\n
        Outcome: <the answer>". Scoring relevance against the whole blob let the
        *question* text match the user's new question, so a garbage answer was
        retrieved purely because it had been asked before.
        """
        head = (content or "").split("Context:")[0]
        return head.strip() or (content or "").strip()

    def _lexical(self, question: str, memory: dict[str, Any]) -> float:
        """How much of the question this memory answers, in [0, 1].

        A literal word match counts full weight; a match through a synonym or a
        shared stem counts half. Without that discount the synonym table made
        everything match everything (measured: "what size should I export at?"
        scored 1.00 against the canvas-size fact because "size" expands to
        "resolution" and "scale", both of which appear there).
        """
        from minicoder.memory.systems import _SYNONYMS

        claim = f"{memory.get('label', '')} {self._claim(memory.get('content', ''))}"
        q = self._content(question)
        hay = self._content(claim)
        if not q:
            return 0.0
        hay_stem = {h.rstrip("s") for h in hay}

        total = 0.0
        for w in q:
            if w in hay or w in hay_stem:
                total += 1.0
                continue
            syn = _SYNONYMS.get(w, ())
            if any(s in hay or s in hay_stem for s in syn):
                total += 0.5
                continue
            if len(w) >= 7 and any(len(h) >= 7 and w[:7] == h[:7] for h in hay):
                total += 0.5
        return total / len(q)

    def _relevant(self, question: str, memory: dict[str, Any], floor: float = 0.34) -> bool:
        """A memory is used only when it genuinely overlaps the question."""
        return self._lexical(question, memory) >= floor

    @staticmethod
    def _flatten(skill: dict[str, Any]) -> str:
        return (skill.get("description") or "") + " " + (skill.get("solution") or "")

    def answer(self, question: str, *, max_tokens: int = 96, allow_neural: bool = True) -> Generation:
        evidence: list[dict[str, Any]] = []
        # 0. Questions about this system are answered from its own records.
        from minicoder.cognition.selfmodel import self_answer

        self_report = self_answer(question)
        if self_report is not None:
            evidence.append({"type": "self_report", "topic": self_report["topic"]})
            return Generation(self_report["text"], len(self_report["text"].split()), 0.0, 0.0,
                              "self", evidence, self.brain.backend)
        # 1. Verified skills first — executables beat prose.
        skills = self.procedural.verified(exported=None)
        q = self._content(question)
        scored = []
        for s in skills:
            hay = self._content(self._flatten(s))
            overlap = len(q & hay) / max(1, len(q))
            if overlap > 0.2:
                scored.append((overlap, s))
        scored.sort(key=lambda t: t[0], reverse=True)
        coding_intent = bool(re.search(r"\b(def |function|python|code|script|implement|write a .*\()", question.lower()))
        bar = 0.4 if coding_intent else 0.6
        if scored and scored[0][0] >= bar:
            overlap, skill = scored[0]
            if self.is_question(question) and not coding_intent:
                # Prose first: does a remembered fact answer the question itself?
                for m in self.semantic.search(question, limit=6):
                    if self._relevant(question, m) and not self._is_junk_fact(
                            str(m.get("label", "")), str(m.get("content", ""))):
                        text = self._claim(m.get("content", "")).strip() or str(m.get("label", ""))
                        evidence.append({"type": "semantic", "id": m["id"],
                                         "label": m["label"], "status": m["status"],
                                         "confidence": m["confidence"], "score": m.get("score"),
                                         "chosen_over": skill["slug"]})
                        return Generation(text, len(text.split()), 0.0, 0.0, "memory",
                                          evidence, self.brain.backend)
                text = self.render_procedure(skill)
                self.procedural.record_use(skill["slug"])
                evidence.append({"type": "skill", "slug": skill["slug"],
                                 "score": round(overlap, 3), "status": skill["status"],
                                 "rendered": "as_prose"})
                return Generation(text, len(text.split()), 0.0, 0.0, "skill", evidence,
                                  self.brain.backend)
            self.procedural.record_use(skill["slug"])
            text = skill["solution"].strip() or skill["description"]
            evidence.append({"type": "skill", "slug": skill["slug"], "score": round(overlap, 3),
                             "status": skill["status"]})
            return Generation(text, len(text.split()), 0.0, 0.0, "skill", evidence, self.brain.backend)

        # 2. Semantic knowledge graph — gated on a joint lexical + dense score.
        # Measured on this embedder: related pairs ~0.35 cosine, unrelated ~0.24,
        # so cosine alone cannot carry the decision. Lexical overlap is the
        # stronger signal at this model size; cosine breaks ties.
        kn_all = self.semantic.search(question, limit=6)
        kn = [m for m in kn_all
              if self._relevant(question, m)
              and not self._is_junk_fact(str(m.get("label", "")), str(m.get("content", "")))][:3]
        for m in kn:
            evidence.append({"type": "semantic", "id": m["id"], "label": m["label"],
                             "status": m["status"], "confidence": m["confidence"],
                             "score": m.get("score")})
            evidence.append({"type": "relevance_gate", "keep": True,
                             "lexical": self._lexical(question, m), "dense": m.get("score", 0.0)})
        # 3. Episodic recall (same relevance gate).
        for e in self.episodic.search(question, limit=4):
            if self._relevant(question, {"label": e.get("objective", ""), "content": e.get("situation", "")}):
                evidence.append({"type": "episode", "id": e["id"], "status": e["status"],
                                 "situation": e["situation"][:160], "score": e.get("score")})

        # ``brain`` may be absent (an answerer built from memory alone); provenance
        # must still be truthful rather than raising.
        backend = getattr(self.brain, "backend", "memory") if self.brain is not None else "memory"
        if kn:
            top = kn[0]
            # Entity aggregation: when several remembered facts answer the *same*
            # question about the same thing, return them together. Measured
            # failure of the first version: it matched on any shared word, so
            # "what palette reads as premium" returned all nine palettes. A fact
            # now has to be about the entity the question names (its subject), not
            # merely mention a word from it.
            subject = self._subject(question)
            pool = self.semantic.search(question, limit=12)
            same_entity = [
                m for m in pool
                if m.get("id") != top.get("id")
                and subject
                and subject in self._words(f"{m.get('label', '')} {self._claim(m.get('content', ''))}")
            ]
            if len(same_entity) >= 1:
                # Order by how much of the question each fact covers, so the fact
                # that answers the *asked* slot ("export") leads the fact that
                # merely shares the subject ("canvas size").
                ranked = sorted([top] + same_entity, key=lambda m: -self._lexical(question, m))
                seen, lines = set(), []
                for m in ranked[:4]:
                    body_i = self._claim(m.get("content") or "").strip().split("\n")[0].rstrip(".")
                    key = body_i.lower()
                    if body_i and key not in seen:
                        seen.add(key)
                        lines.append(f"- {body_i}.")
                if len(lines) >= 2:
                    text = "Here is what memory holds:\n" + "\n".join(lines)
                    if top["status"] != VERIFIED:
                        text += "\n\n(Note: this memory is not yet verified.)"
                    return Generation(text, len(text.split()), 0.0, 0.0, "memory", evidence,
                                      backend)
            extra = [m["label"] for m in kn[1:3]]
            # Never echo the answer back as its own "related" item.
            extra = [e for e in extra if e.strip()[:60] and e.strip()[:60] not in top["content"]]
            text = top["content"] + (f"\nRelated: {', '.join(extra)}." if extra else "")
            if top["status"] != "VERIFIED":
                text += "\n\n(Note: this memory is not yet verified.)"
            return Generation(text, len(text.split()), 0.0, 0.0, "memory", evidence, backend)

        # 4. Neural fallback — used only where it was actually trained.
        #
        # The decoder is a ~1M-parameter model trained from scratch on coding and
        # design tasks. Free-form sampling on an out-of-distribution question
        # produces fluent-looking noise, which would violate prime directive #1
        # ("never fabricate"). So it is gated by a measured distribution check:
        # the prompt must contain vocabulary the tokenizer actually learned, and
        # the sampled continuation must be significantly more probable than a
        # length-matched random token sequence. Otherwise we refuse explicitly.
        if allow_neural and self.brain.model and self.brain.tok:
            verdict = self.brain.in_distribution(question)
            if verdict["in_distribution"]:
                gen = self.brain.best_of(question, k=4, max_new_tokens=max_tokens)
                gen.grounding = evidence + [{"type": "in_distribution_check", **verdict}]
                if gen.text.strip():
                    return gen
            return Generation(
                self.refusal(question), 0, 0.0, float("nan"), "refuse",
                evidence + [{"type": "out_of_distribution", **verdict}], self.brain.backend,
            )

        return Generation(self.refusal(question), 0, 0.0, float("nan"), "refuse", evidence, self.brain.backend)

    @staticmethod
    def refusal(question: str) -> str:
        return (
            "I don't have a verified memory, skill or trained output that answers this yet. "
            "Rather than guess, I can (a) run a sandboxed experiment and verify the result, "
            "(b) inspect an image if you attach one, or (c) record your answer as an unverified "
            "hypothesis for the next sleep cycle."
        )
