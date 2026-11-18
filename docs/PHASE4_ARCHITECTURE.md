# Phase 4 — Cognitive Integration: architecture

Phase 3 proved that a capability can be absent, acquired, verified and replayed.
Phase 4 changes what happens *around* that capability: what kind of request the
system thinks it received, how it decides it knows enough to answer, what it says
when it does not, what it measures about itself, and what it refuses to do
without permission.

Nothing in Phase 3 was removed. Every new module is additive, and each one either
reads existing records or writes to a table that did not previously exist
(`calibration`, `audit_log`).

```
                        ┌───────────────────────────────────────┐
   user message ───────▶ │ M1  intent router  (cognition/intent) │
                        └───────────────┬───────────────────────┘
              ┌─────────────┬───────────┼────────────┬──────────────┐
              ▼             ▼           ▼            ▼              ▼
         QUESTION     EXPLANATION   PLANNING    EXECUTION   SELF_INTROSPECTION
              │             │           │            │              │
              ▼             ▼           ▼            ▼              ▼
        ┌───────────────────────────┐  │   ┌────────────────┐  ┌────────────────┐
        │ M2 answerer (engine.py)   │  │   │ authorisation  │  │ M3 self-model  │
        │ retrieve → combine →       │  │   │ gate (M7)      │  │ (selfmodel.py) │
        │ separate fact/hypothesis → │  │   └───────┬────────┘  └────────────────┘
        │ refuse when unsupported    │  │           │
        └─────────────┬─────────────┘  └───────────▼─────────────┐
                      │                    │ DesignAgent.execute │
                      │                    └──────────┬──────────┘
                      ▼                               ▼
        ┌────────────────────────────┐   ┌────────────────────────────┐
        │ M6 metacognition           │   │ M7 audit + calibration     │
        │ calibration/coverage       │   │ (audit_log, calibration)   │
        └────────────┬───────────────┘   └────────────┬───────────────┘
                     │                                │
                     ▼                                ▼
        ┌────────────────────────────────────────────────────────────┐
        │ memory: episodic / semantic / procedural  (unchanged API)   │
        └──────────────────────────────┬─────────────────────────────┘
                                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │ M5 Adaptive Sleep 2.0  (sleep/adaptive.py, 8 stages kept)  │
        └──────────────────────────────┬─────────────────────────────┘
                                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │ M4 generalization engine (research/generalization.py)      │
        │ 7 axes · frozen baseline · hidden draws from private salt   │
        └──────────────────────────────┬─────────────────────────────┘
                                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │ M8 dashboard: Cognition + Generalization tabs (real rows)  │
        └────────────────────────────────────────────────────────────┘
```

## Module map

| # | Module | File(s) | Owns |
|---|---|---|---|
| M1 | Intent router | `cognition/intent.py`, `cognition/agent.py` | six request types, confidence, entities, required permission |
| M2 | Natural-language reasoning | `cognition/engine.py` (`GroundedAnswerer`) | retrieval, combination, contradiction surfacing, prose rendering, refusal |
| M3 | Self-introspection | `cognition/selfmodel.py` | answers about sleep cycles, skills, experiments, memory, research |
| M4 | Generalization | `research/generalization.py`, `research/tasks.py` (`scale`/`edge_only`) | seven axes, train/dev/hidden split, frozen baseline, leakage guards |
| M5 | Adaptive Sleep 2.0 | `sleep/adaptive.py`, `sleep/engine.py` | ten measurements attached to the eight existing stages |
| M6 | Metacognition | `cognition/metacognition.py` | persisted calibration (Brier/ECE), coverage estimate, experiment decision |
| M7 | Security & isolation | `cognition/agent.py`, `memory/schema.sql` (`audit_log`), `research/private.py`, `research/isolation.py` | authorisation, audit, atomic promotion, eval/production separation |
| M8 | Dashboard | `dashboard/src/CognitionView.tsx`, `GeneralizationView.tsx`, `api/app.py` | real rows only; missing data renders as missing |

## Data flow, by request shape

**A question** (`IntentType.QUESTION`, `EXPLANATION`). `DesignAgent.execute`
classifies first and, for these types, never calls the planner. The answerer
searches semantic memory, then procedures, then episodes, applies a relevance
gate, and renders prose. `_unmet_requirements` and verification are not involved
because nothing was changed. The trajectory records `steps=[]`, which is the
machine-checkable statement "this request did not act".

**A planning request.** `plan()` is invoked and its steps are rendered as a
numbered prose list with an explicit "nothing has been changed yet". No tool is
called.

**An execution request.** If the request contains a consequential verb
(`delete`, `export`, `push`, `reset`, …) and `authorize` is false, the router
refuses before the planner sees it, writes an `audit_log` row with
`authorized=0`, and returns. With `authorize=true` the plan runs, each step is
checked, and a second audit row records `executed` and `verified`.

**A self-introspection request.** `classify_self()` matches the topic, then
`self_answer()` reads the specific record: `sleep_cycles` for cycles,
`skills`/`skill_replays` for capabilities, `datasets/research/*_latest.json` for
research, counting queries for memory. If the record is absent the answer says
so; it does not describe an experience it did not have.

## Measurements and where they live

| Measurement | Written by | Read by |
|---|---|---|
| `calibration(predicted, outcome)` | `DesignAgent._observe_outcome` | `/api/cognition/overview`, `Metacognition.reliability` |
| `audit_log(action, intent, authorized, allowed, detail)` | `_observe_outcome`, `cognition.metacognition.audit` | dashboard Cognition tab |
| adaptive sleep section | `SleepEngine._adaptive_pass` → `sleep_cycles.report.adaptive` | `/api/sleep/adaptive`, `memory/sleep_logs/latest.md` |
| generalization report | `GeneralizationEngine.write` | `/api/generalization/overview` |
| cycle fingerprint | `AdaptiveAnalysis.fingerprint` | report + dashboard |

## Deliberate structural choices

* **The eight sleep stages are still eight.** The new analyses attach to the
  stage that owns them (`stage 2 → hygiene`, `4 → contradictions/abstractions`,
  `5 → verification/rotation retention`, `6 → forgetting`, `8 → promotion`).
  Adding a ninth stage would have broken every existing report reader for no gain.
* **One route decision, in one place.** Phase 3 had a regex in `agent.py` and a
  second rule in `engine.py`, and they disagreed. `intent.classify` is now the
  only classifier; the answerer's rule delegates to it.
* **Hidden inputs are never materialised.** They are derived from the private
  salt at evaluation time. `scale`/`edge_only` keep the exact Phase 3 digest
  string when unused, so old draws reproduce byte for byte.
* **Refusal is a first-class outcome.** `source="refuse"` carries a reason, not
  an apology, and it is never counted as a calibration success or failure.

## Failure containment

Every new analysis in `_adaptive_pass` is wrapped: an exception becomes
`{"error"} in the report and the cycle still completes, because the memory work
already committed by that point. Promotion is the exception — it runs inside one
`db.write()` transaction, so a failure leaves neither a skill nor a promoted
candidate.
