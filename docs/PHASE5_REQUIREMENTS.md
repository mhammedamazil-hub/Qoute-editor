# Phase 5 Requirements — Derived from the Phase 4 Audit

Source: `docs/PHASE4_INDEPENDENT_AUDIT.md` (findings F1–F17) and
`docs/PHASE4_AUDIT_EXPERIMENTS.md` (experiments E-01–E-15).

Nothing here is a feature wish-list. Each requirement exists because an audit experiment showed a
capability that is claimed but not delivered, or a limit that cannot be removed inside the current
architecture. Requirements are ordered by the priority the audit implies: **a system that cannot
express the answer, cannot measure whether it learned, and cannot prove who authorized an action is
not improved by going faster.**

Severity of the finding that motivates each requirement is in brackets.

---

## R1 — Remove the fundamental learning limits (candidate grammar and credit assignment)

*Traces to F11 (unseen_family is a vocabulary limit reported as a generalisation result), F3
(acceptance test passes wrong programs).* **[HIGH]**

**Problem.** The acquisition loop searches a fixed candidate grammar. For `rle` and `group_sum` the
search space provably contains no correct program (380 candidates enumerated, none executable), yet
the failure is reported as a generalisation score of 0.000 with no diagnostic. Separately, when a
program *is* found it is accepted on a sample that discriminates only 9 % of the input space, so a
program that omits half the semantics is promoted and later credited as abstraction.

**Why the current architecture cannot solve it.** Two structural choices: (i) the grammar is a
closed enumeration with no notion of "construct absent", so a search failure and a semantic gap are
indistinguishable; (ii) acceptance is `all(pass(hidden_draw(seed_i)) for i in range(k))` with
k = 10 draws from one distribution — a test with almost no power against near-miss programs.

**Approach.**
1. Make the grammar declarative and introspectable: each primitive carries a typed signature, a
   reference implementation, and a set of example (input, output) pairs.
2. Emit a *diagnosis object* when search fails: nearest candidates, which primitives would be
   required, and the residual error on the best candidate. `unseen_family` becomes "not expressible
   with primitives {…}" rather than 0.000.
3. Replace the pass/fail acceptance test with differential testing against an *independent*
   reference implementation of the task family, using a discriminating-draw generator (draws chosen
   to separate the candidate from its nearest wrong neighbours), plus a held-out batch of at least
   50 draws for the final accept decision.

**Expected measurable improvement.** Diagnosis string present for 100 % of search failures; wrong
programs like `cumsum(even)` rejected before promotion (the 5/5 hand cases currently failing become
0/5); `unseen_family` reported as `not_expressible` with a primitive gap list.

**Resources.** ~1 engineer-week; no new hardware. Net runtime roughly neutral (diagnosis is
post-hoc; discriminating draws cost ~2× the acceptance budget, which is 0.1 s today).

**Acceptance criteria.**
* Every failed acquisition record carries `diagnosis.reason` in `{not_expressible, budget_exhausted,
  no_candidate_within_tolerance}` and a list of missing primitives where applicable.
* A regression suite of ≥ 30 near-miss programs (each wrong on ≤ 10 % of the distribution) is
  rejected 100 % of the time.
* No program is promoted whose failure rate on the held-out batch exceeds 1/50.

**Potential regressions.** Stricter acceptance reduces the number of promoted skills — the
`combination` axis will likely drop from 0.5 to 0.0 until the generator produces the correct
`dedupe_running` composition. This is the *correct* movement and must not be treated as a regression
in the report; the report should show the axis with `not_expressible` annotations instead.

---

## R2 — Generalisation beyond the candidate grammar (compositional, not vocabulary)

*Traces to F4 (effective n ≈ 2 per axis), F11, F12 (baseline is not a control), F14 (leakage scan
covers keys only).* **[HIGH]**

**Problem.** Every axis is evaluated on 1–2 fixed task shapes per seed, and three of the seven axes
(`larger_input`, `shifted_distribution`, `representation_shift`) re-evaluate the same program with
different draws. Per-axis rates therefore carry no statistical weight, and "generalisation" is
currently measured as robustness on the training vocabulary.

**Why the current architecture cannot solve it.** Task generation is a seed-dependent rotation over a
small fixed family list; the axes were defined as *input perturbations*, not as *distributional
shifts requiring new behaviour*. There is also no independent oracle for held-out compositions, so a
new family cannot be scored without being added to the same code that generates it.

**Approach.**
1. Define axes by *what must be newly inferred*, not by what the input looks like: (a) unseen
   primitive, (b) unseen composition of seen primitives, (c) unseen output type, (d) unseen input
   shape, (e) unseen length regime.
2. Generate compositions combinatorially (n² pairs from the primitive set) so that each axis has
   ≥ 20 distinct programs per seed.
3. Score held-out families against a reference oracle implemented from the *specification*, not from
   the generator (write the oracle first, freeze it, hash it).
4. Report every axis with n, success count, Wilson CI, and an explicit `not_expressible` bucket.

**Expected measurable improvement.** Effective n per axis from 2 → ≥ 20; per-axis CIs shrink from
±0.4 to ±0.2; the composition axis becomes an actual test (a system that can only reuse whole
programs scores near 0, not 0.5 by draw luck).

**Resources.** ~1.5 engineer-weeks (oracle + generator + report changes); runtime grows ~4× on a
benchmark that currently takes 1.1 s per seed.

**Acceptance criteria.**
* No axis has fewer than 20 distinct programs per seed; a test asserts distinct-program count.
* Every axis reports `n`, `passed`, `failed`, `not_expressible`, and a 95 % CI.
* An ablation with reuse disabled scores ≤ 0.1 on the composition axis (i.e. the axis is not
  passable by luck).

**Potential regressions.** Overall scores will fall. Any Phase 4 comparison must be re-run under the
new suite before quoting a before/after.

---

## R3 — Make adaptive learning adaptive (measure, decide, affect the next cycle)

*Traces to F6 (adaptive pass changes no outcome, costs 99.9 % of cycle time; 5/10 measurements are
report-only; usefulness never reaches forgetting; `PRUNE_THRESHOLD` dead).* **[HIGH]**

**Problem.** A controlled two-cycle A/B on identical memory shows the adaptive pass (42 s/cycle)
produces exactly the same learning deltas as not running it (0.06 s/cycle), plus 8 replay rows
nothing reads. The loop has no cycle-quality gate, so a poor cycle cannot trigger recovery. "A report
is produced" has been read as "learning improved".

**Why the current architecture cannot solve it.** The five mutating measurements write to state that
no *decision* consumes: the forgetting stage recomputes its own relevance (pinned at 0.5) instead of
using the usefulness ranking; `PRUNE_THRESHOLD` has no reader; stage 6 cannot archive anything
because the retention window exceeds the corpus age. There is no objective function for a cycle, so
"did this cycle help" is undefined.

**Approach.**
1. Define a cycle objective (e.g. held-out task success on a fixed 30-task probe set, not the
   training families) and record it every cycle.
2. Route measurement → decision explicitly: one decision table mapping each measurement to the action
   it can trigger, with a test asserting that disabling a measurement changes that action.
3. Delete or wire the dead paths: either `PRUNE_THRESHOLD` governs forgetting or it is removed;
   `usefulness` either feeds the forgetting score or is removed from the report.
4. Gate on quality: if a cycle's objective regresses, mark the cycle `degraded`, skip promotion, and
   schedule a re-run with the offending measurement disabled.
5. Cost budget: the adaptive pass must justify its wall time; add a per-stage timing record so
   unaccounted time (currently 38 s/cycle) cannot be invisible.

**Expected measurable improvement.** Adaptive-vs-static A/B must show a *learning* delta (not just
replay rows) or the pass is removed. Unaccounted cycle time 38 s → < 1 s. Dead constants 2 → 0.

**Resources.** ~1 engineer-week; profiling tools already present.

**Acceptance criteria.**
* An A/B over ≥ 10 cycles shows a statistically separated objective delta (≥ 5 points on the probe
  set, non-overlapping CIs) or the adaptive pass is deleted in the same PR.
* Every stage's measured ms sums to within 5 % of cycle wall time.
* A test fails if any measurement method has zero effect on any state or decision.
* A deliberately degraded cycle (e.g. 50 % corrupted episodes) is detected and does not promote.

**Potential regressions.** More cycles will be marked degraded at first (honest); the retention
"5/5" headline will disappear until the retention window is re-tuned.

---

## R4 — Reliable metacognition (two-class calibration that changes decisions)

*Traces to F5 (one-class sample; Brier 0.181 on a mixed probe; answers record no samples; confidence
drives nothing), F15 (router confidence is a literal).* **[HIGH]**

**Problem.** All 30 calibration samples have outcome 1.0, so Brier/ECE measure nothing about
confidence. A five-execution mixed probe gives Brier 0.181 / ECE 0.269, with mean predicted 0.869
against actual 0.600. Answers, refusals and routing decisions produce no samples at all, and
`should_experiment()` has no caller.

**Why the current architecture cannot solve it.** Samples are written only where an execution
verifies, i.e. the only path that can ever fail is the only path sampled — and it is sampled
selectively (failures are rare). Confidence and outcome are computed from the same parse, so the
"prediction" encodes the answer. And the calibrated value has no consumer, so improving it changes
nothing.

**Approach.**
1. Sample *all* decision points: answers (with a graded correctness label from a held-out judge),
   refusals (label: was refusal correct?), routing (was the type right?), executions.
2. Force a two-class stream: retain failures at a fixed rate (stratified reservoir) so the table
   contains both classes by construction.
3. Break the circularity: confidence must be produced *before* the verification plan is built
   (e.g. from features of the request and the retrieved evidence), and the outcome must come from a
   path that cannot see the prediction.
4. Couple it: `should_experiment()`, refusal thresholds and answer hedging must consume the
   calibrated value, with a test that perturbing calibration changes behaviour.

**Expected measurable improvement.** Brier on a mixed held-out set ≤ 0.10 (from 0.181); ECE ≤ 0.05
(from 0.269); non-zero failure share in the calibration table; at least three decisions sensitive to
calibration.

**Resources.** ~1.5 engineer-weeks; needs a judge (can be rule-based with human spot checks).

**Acceptance criteria.**
* Calibration table always contains ≥ 20 % failures (enforced by the reservoir).
* Held-out Brier ≤ 0.10 and ECE ≤ 0.05, computed monthly over a frozen evaluation slice.
* A unit test proves that a 0.1 change in calibrated confidence changes at least one behaviour
  (hedging or experiment trigger).
* No decision path both writes and reads the same confidence value.

**Potential regressions.** Answers will hedge more; the "confident and correct" appearance of the
current system will drop. That is the point.

---

## R5 — Memory quality and knowledge acquisition

*Traces to F8 (silent contradiction overwrite), F9 (no relevance gate), F10 (introspection
overclaims).* **[HIGH]**

**Problem.** Upserting a label with contradictory content silently replaces the old value; the
`memory_conflicts` counter comes from a different path and never sees it. Retrieval answers
"billboard margin" with the poster margin. Introspection describes a report with zero stages as
"every stage completed without an error".

**Why the current architecture cannot solve it.** Semantic memory is a key–value upsert store with
no notion of a claim, its source, or its validity interval, so disagreement cannot be represented —
only overwritten. Retrieval scores lexical/embedding similarity with no entity gate. Introspection
summarises by absence rather than by evidence.

**Approach.**
1. Claims, not values: `(entity, attribute, value, source, observed_at, confidence, superseded_by)`.
   Contradiction = two live claims for the same (entity, attribute) with different values.
2. Retrieval gate: a question must name an entity/attribute that exists; otherwise refuse with the
   closest known alternatives (and never answer as if it were the asked entity).
3. Introspection contract: every sentence must cite a count or a row id; empty sets produce
   "no stages recorded", never "all stages completed". A property-based test generates degenerate
   records (empty, corrupted, truncated) and asserts no success claims.
4. Acquisition from dialogue: when the user states a fact, record it as a claim with source
   `user`, visible as such in answers.

**Expected measurable improvement.** 100 % of contradictions materialised as live-claim pairs (from
0 % on the upsert path); 0 wrong-entity answers on a 20-question probe (from 1/3); 0 vacuous success
claims on degenerate records.

**Resources.** ~2 engineer-weeks (schema migration + retrieval + tests). DB grows modestly (claims
are append-only, superseded rows retained).

**Acceptance criteria.**
* Injecting a contradictory claim yields an answer that names both values and their sources.
* A 20-question probe with 10 unanswerable entities gets 10 refusals (0 answers).
* A generated degenerate-record suite produces zero success assertions.
* Migration is reversible and preserves all 52 existing nodes.

**Potential regressions.** Answers become longer; the current "single crisp value" UX changes.
Retrieval refusal rate rises, which R4's calibration must absorb.

---

## R6 — Security and experimental integrity

*Traces to F1 (CRITICAL tool bypass), F2 (paraphrase bypass), F7 (no principal, replayable
authorization), F3/F12/F13/F14 (acceptance power, baseline, metric comparability, leakage scope).*
**[CRITICAL / HIGH]**

**Problem.** `/api/editor/tool` executes destructive tools with no authorization and no audit row
(verified: canvas 1 → 0, `audit_log` 2 → 2) while CORS is `*`. Twelve destructive rephrasings never
reach the gate. "Authorization" is a client boolean that can be replayed, attributed to nobody.
Experimentally, the baseline is not a control, metrics are quoted without denominators, and the
leakage scan ignores values.

**Why the current architecture cannot solve it.** Authority lives in one call path
(`DesignAgent.execute`), not in the tool layer every path must cross; there is no principal model at
all; and the evaluation harness has no statistical contract.

**Approach.**
1. **Single choke point:** make `EditorBridge.call` require an `Authorization` capability token
   minted by the intent layer; direct calls fail closed. The HTTP tool endpoint must go through the
   same gate or not exist.
2. **Principal + nonce:** each authorization is bound to a principal, an intent hash, an expiry and a
   one-time nonce; replay returns `409 already_executed`.
3. **Audit:** append-only, hash-chained rows for every tool call including denials; expose a verifier.
4. **Router fix:** decide `requires_authorization` after the final type/verb scan; add negation
   handling; add a differential test corpus of ≥ 60 paraphrases (≥ 20 destructive, ≥ 10 negated).
5. **Experimental contract:** a true no-learning frozen baseline (empty library snapshot, hashed and
   pinned); every reported metric carries n, numerator/denominator and CI; the leakage scan covers
   values and expected outputs, not only keys.

**Expected measurable improvement.** Destructive tool calls without a token: 4/4 → 0/4. Ungated
destructive paraphrases: 12/18 → 0/60. Replay accepted: yes → 409. Audit rows per tool call:
0 → 1.

**Resources.** ~1.5 engineer-weeks; no new infrastructure (hash chain in SQLite is sufficient for a
single-node system).

**Acceptance criteria.**
* `POST /api/editor/tool` without a token returns 403 and writes a denial row; with a used nonce
  returns 409.
* A 60-input paraphrase corpus contains no ungated destructive instruction, and no over-block of
  benign builds (≤ 1 false positive).
* `audit_log` verifier detects a hand-edited row (tamper test).
* Every benchmark table in the docs shows n, numerator/denominator and CI, and a doc test fails on a
  bare rate.
* The frozen baseline is a distinct library hash from the live one.

**Potential regressions.** Dashboards/tests that call the tool endpoint directly must mint tokens;
CORS `*` removal may break the local dev flow (bind explicitly to the preview origin instead).

---

## R7 — Performance on real hardware

*Traces to F6 (38 s/cycle unaccounted), F17 (`wall_seconds` always 0.0), E-12 (600× cost for no
delta), E-15 (~0.6 s/task/arm).* **[MEDIUM]**

**Problem.** The adaptive pass dominates cycle time with no measured benefit and no stage-level
accounting; resource samples record `wall_seconds = 0.0` universally, so the system's own cost
telemetry is broken. The benchmark has only ever run on 2 vCPU with no GPU.

**Why the current architecture cannot solve it.** Timing is captured per stage but the adaptive block
runs outside the stage list; resource sampling writes the field but never computes it. There is no
budget contract for a cycle.

**Approach.**
1. Fix `wall_seconds` (monotonic start/stop around the sampled unit) and assert non-zero.
2. Move `_adaptive_pass` inside a timed stage so its 38 s is visible.
3. Add a cycle budget: if the objective (R3) does not improve, the pass runs at reduced frequency
   (e.g. every 5th cycle) — cost becomes a function of measured value.
4. Record a hardware profile per run (already partially present: cores, RAM, torch, cuda) and refuse
   to compare runs across profiles in the report.

**Expected measurable improvement.** Unaccounted cycle time 38 s → < 1 s; `wall_seconds` accuracy
100 %; cycle cost scaled to measured benefit (target: cycle wall ≤ 5 s when the objective is flat).

**Resources.** ~3 engineer-days; no new hardware required (GPU work is a separate decision once the
loop can demonstrate a benefit at all).

**Acceptance criteria.**
* Stage ms sums to wall time within 5 % on 10 consecutive cycles.
* `resource_samples.wall_seconds > 0` for 100 % of samples.
* On flat-objective cycles the pass degrades to a cheap mode automatically (asserted by test).
* Benchmark reports carry the hardware profile and refuse cross-profile aggregation.

**Potential regressions.** Less frequent adaptive work may delay skill promotion; R3's objective must
show the trade is acceptable.

---

## Sequencing and dependencies

| Order | Requirement | Depends on | Rationale |
|---|---|---|---|
| 1 | **R6 security** | — | A CRITICAL bypass exists today; nothing else should be built on an ungated tool layer. |
| 2 | **R1 learning limits** | — | Nothing measured downstream is meaningful while acceptance accepts wrong programs. |
| 3 | **R2 generalisation suite** | R1 | Needs a real oracle and expressibility diagnosis to report honestly. |
| 4 | **R3 adaptive learning** | R2 (objective), R7 (timing) | A cycle objective needs a probe set that is not the training families. |
| 5 | **R4 metacognition** | R3 (probe set), R5 (claim sources) | Needs mixed samples and a decision to influence. |
| 6 | **R5 memory quality** | R6 (audited writes) | Schema change is safest after the write path is gated. |
| 7 | **R7 performance** | R3 | Optimisation follows a demonstrated benefit, not the reverse. |

## Explicit non-goals for Phase 5

* No new dashboard tabs before R2 makes the existing numbers meaningful.
* No model scaling or GPU acquisition until R3 shows the adaptive loop has a measurable objective
  delta on 2 vCPU.
* No new skill families added to the existing suite: new families must arrive through R1/R2 with an
  independent oracle and a frozen baseline, otherwise the `unseen_family` result stays uninterpretable.

## Traceability

| Finding | Requirement |
|---|---|
| F1 | R6 (1–3) |
| F2 | R6 (4) |
| F3 | R1 (3), R2 |
| F4 | R2 (1–2) |
| F5 | R4 |
| F6 | R3, R7 (2–3) |
| F7 | R6 (2–3) |
| F8 | R5 (1) |
| F9 | R5 (2) |
| F10 | R5 (3) |
| F11 | R1 (1–2) |
| F12 | R6 (5) |
| F13 | R2 (4), R6 (5) |
| F14 | R6 (5) |
| F15 | R4 (3) |
| F16 | R2 (4) — reporting only |
| F17 | R7 (1) |
