# Phase 4 — research and design decisions

Every entry below records a fork in the road, what was chosen, what was rejected,
and the evidence that decided it. Where a decision was reversed during the work,
both versions are kept: the first attempt is often the more tempting one.

---

## D1. A typed intent router replaces two regexes

**Context.** Phase 3 had `GroundedAnswerer.is_question` and a separate
`question_like` flag in `DesignAgent`. They disagreed: "How many fonts should I
use in one poster" contained no `?`, so the agent planned and mutated the canvas
while the answerer would have answered it.

**Chosen.** One classifier, `cognition/intent.classify`, returning an `Intent`
with a type, a confidence, extracted entities, the consequential verbs it found,
and a derived `requires_authorization`. The agent routes on it; the answerer asks
it whether a request is answerable.

**Rejected.** A confidence-thresholded cascade of regexes inside the agent. It
would have been a third place for the rule to live.

**Evidence.** Six representative sentences classify correctly with confidence
0.70–0.90, and the canvas-mutation test now asserts `steps == []`.

---

## D2. Questions are answerable; they are not "read-only executions"

**Context.** The tempting model is "a question is an execution with no side
effects". That collapses two different failure modes: executing when it should
have answered, and answering when the user asked for a change.

**Chosen.** `Intent.is_answerable` is true only for QUESTION, EXPLANATION and
SELF_INTROSPECTION. PLANNING returns a plan and says nothing was changed.
EXECUTION runs. Each has its own `source` value (`memory`, `self`, `plan`,
`verified_execution`, `refuse`) so a report can tell them apart after the fact.

**Rejected.** A single `action_taken: bool`.

---

## D3. Consequential verbs require an explicit grant, and the grant is audited

**Context.** "Delete every layer" is unambiguous, and a helpful agent is exactly
the kind that deletes.

**Chosen.** `CONSEQUENTIAL_VERBS` (`delete`, `remove`, `clear`, `reset`,
`export`, `push`, `publish`, `overwrite`, …) mark an intent as requiring
authorisation. Without `authorize=true` the request is refused before planning.
Both outcomes are written to `audit_log`: `authorized`, `allowed`, `executed`,
`outcome`.

**Rejected.** Treating an empty canvas or a `--yes` CLI flag as implicit consent.
Neither is a decision the user made about *this* request.

**Note.** "Allowed" and "executed" are deliberately separate columns: a granted
request that turns out to have no matching tool is audited as granted but not
executed, which is the honest distinction and a real state in the system.

---

## D4. Self-introspection reads records; it does not narrate

**Context.** Asked about its last sleep cycle, the system used to refuse, because
no answer path consulted `sleep_cycles` — the report existed and was ignored.

**Chosen.** `classify_self` maps the question to a topic; `self_answer` queries
that topic's own record (cycle table, skills + replays, research report files,
counting queries) and renders it. When the record is missing it says so with the
thing it looked for.

**Rejected.** A template like "I feel rested after consolidating memories". It
would pass a casual reading and be false.

**Evidence.** "Summarise your last sleep cycle" → "Last sleep cycle was #13 …
8 stages …", with the cycle number taken from the database, and a test that
seeds report `#7` and asserts the number appears.

---

## D5. Adaptive Sleep keeps eight stages and adds ten measurements

**Context.** A ninth stage would be the obvious way to add "adaptive" analysis,
and would break every report consumer that assumes eight.

**Chosen.** `_adaptive_pass` runs after the stages and *merges* each result into
the stage that owns it. The report gains one `adaptive` block, a
`fingerprint`, and a cycle-over-cycle `delta`.

**Rejected.** A parallel `SleepEngine2`. Two engines drift.

---

## D6. Contradiction detection is narrow, because the first version was wrong

**Context.** The first implementation flagged opposed word pairs ("always" /
"never", "light" / "dark"). On the live database it flagged two *success
trajectories* that differed only in step count ("a 4-step trajectory…" vs "a
3-step trajectory…"). A second version, using negation cues alone, flagged a
success record against a failure record that quoted the same request.

**Chosen.** A pair is a contradiction only when (a) exactly one side carries an
explicit negation cue, (b) the two still share ≥ 0.6 of their vocabulary, and
(c) their *labels* are ≥ 0.6 similar — the claim lives in the label. Detections
are recorded as unresolved `memory_conflicts`; none is auto-resolved.

**Rejected.** Fuzzy polarity scoring. It produced confident nonsense.

**Honest result.** With this rule the system detects **0** contradictions on the
current data. That is a measurement, not a success: the corpus does not contain a
negated restatement of a known fact.

---

## D7. Redundancy archives; it never deletes

**Chosen.** Near-duplicate live nodes (same kind, ≥ 0.82 content overlap, and
either identical content or ≥ 0.5 label overlap) collapse to the more confident
copy; the others get `archived=1`. Provenance rows and old answers keep
resolving.

**Why the label condition exists.** Without it, a question and its own answer —
which share most of their words — were grouped as duplicates, and the answer node
was archived. That is the Phase 3 "duplicate memory nodes" defect in reverse.

---

## D8. Candidate promotion has one gate and it is conservative

**Chosen.** A candidate reaches procedural memory only with **≥ 3 recorded
replays, all passing**, and a procedure whose every step names a tool.
`learned_too_few_replays` (one replay) is held, not promoted; a candidate with an
empty procedure is rejected. The skill row and the candidate row are written in
one transaction.

**Rejected.** "Passed more often than it failed" (`passed > failed`). That admits
a coin flip.

**Honest result.** On the live database the gate promotes **0** candidates and
holds 2 — the acquisition loop had already promoted what it could.

---

## D9. Calibration must be persisted and scored, not declared

**Context.** `Metacognition.observe_outcome` kept pairs in a list on the instance.
Calibration therefore reset on every restart, and `calibrated()` was fitted on
nothing in any real run.

**Chosen.** Samples persist to a `calibration` table; `reliability()` reports
Brier, ECE, bucket means and provenance counts; `coverage()` combines retrieval
support with the measured success rate and can answer `insufficient` or
`experiment` instead of guessing; `should_experiment()` fires only on measured
poor calibration (n ≥ 5, Brier > 0.25).

**Rejected.** Deriving confidence from the answerer's own score. That is
self-assessment, not calibration.

**Honest result.** 8 measured samples, Brier 0.008, ECE 0.067, predicted 0.933 vs
actual 1.000. Eight samples is far too few to claim well-calibrated confidence;
the number is reported with its `n` everywhere it appears.

---

## D10. Generalization is seven axes, not one average

**Context.** "Does it generalize?" has one useful answer per axis of change. An
average would hide the axis that fails.

**Chosen.** Seven axes, each with its own pass rate, its own hidden draws, and a
*frozen* baseline: `library_frozen.json` is written once and never overwritten,
so "improvement" cannot be manufactured by shrinking the baseline.

**Rejected.** Re-freezing the baseline each run, and using the current library as
the baseline (which would make every axis lift zero by construction).

---

## D11. The hidden split stays derived, and `scale`/`edge_only` preserve old draws

**Chosen.** Hidden inputs are derived from the private salt at evaluation time;
nothing is written to disk. New axis parameters append to the digest material
*only when non-default*, so every Phase 3 hidden draw reproduces byte for byte.

**Rejected.** Writing a hidden task file per axis. It would be readable, and the
first thing a candidate would try to read.

**Note.** Extending `tasks.py`/`evaluator.py` invalidated the private store
manifest, whose whole purpose is to detect exactly that. The manifest was
re-pinned explicitly through `PrivateStore.repin()` after the change. The
manifest protects against accidental and candidate-side tampering, not against the
operator — that limit is stated in the results document rather than papered over.

---

## D12. Generalization runs never write to production

**Chosen.** Acquisition happens in memory; no skill, memory or library entry is
written. Before and after the run the engine snapshots six production counters
and the library hash, and scans production tables for hidden task identifiers. Any
difference is a reported leakage finding.

**Evidence.** Four seeds, 56 evaluations, zero leakage findings, production
counters unchanged in all four runs.

---

## D13. The dashboard shows numbers or nothing

**Chosen.** The Cognition and Generalization tabs read `/api/cognition/overview`,
`/api/generalization/overview` and `/api/sleep/adaptive`, which read tables and
report files. Missing data renders as "no report yet" with the command that
produces it — never as `0`, which reads like a measured zero.

**Rejected.** Placeholder sparklines. The whole point of the tab is that the
numbers are real.

---

## D14. Additive schema only

**Chosen.** Two new tables (`calibration`, `audit_log`) via
`CREATE TABLE IF NOT EXISTS`, plus an `UPDATE schema_meta` so the recorded
version is truthful on an existing database. No column was added to an existing
table; several tempting ones (`skills.version`, `skills.procedure`,
`skill_candidates.replay_failures` as an integer) turned out not to exist and the
code was written to the schema that does.
