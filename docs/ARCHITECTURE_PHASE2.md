# Phase 2 architecture — learning that can be measured

This document describes the subsystem added in Phase 2 and how it fits the
engine that already existed. It is written against the code, not the intent.

## The problem it solves

The Phase 1 audit (`docs/AUDIT_PHASE2.md`) found that no component acquired a
skill. There were three ways a skill could appear in procedural memory, and all
three were re-execution or transcription:

| Path | What it did |
|---|---|
| `seed.py` | stored human-written solutions with human-written tests, plus invented "reasoning" text |
| `agent.py` | regex keyword → fixed tool sequence |
| `sleep._compile` | re-ran stored tests against stored solutions |

Phase 2 adds the missing loop, and — more importantly — adds the ability to
*prove* a loop ran, by recording what it tried and refusing to promote anything
that has not survived independent replay.

## Data model

Seven tables were added, all additive (`CREATE TABLE IF NOT EXISTS`), so an
existing brain upgrades in place. Nothing was dropped or rewritten.

```
experiments ──< hypotheses
     │
     ├──< attempts            one execution: plan, result, failure class
     │
     └──< skill_candidates    a procedure that satisfied the criteria once
                │
                │  replay in a FRESH PROCESS, ≥3 runs
                ▼
            skills (procedural memory)     only here, only after replay

skill_replays        pass/fail history per skill  → retention curves
resource_samples     RSS / CPU per experiment     → real budget accounting
skill_dependencies   skill → tool edges           → dependency-aware forgetting
```

The brief's requirement that a hypothesis, an attempted solution, a successful
execution and a verified skill must never be confused is enforced structurally:
each is a different table, and `SkillPromoter` is the only writer to `skills`.

## The acquisition loop

`minicoder/learning/engine.py`

```
acquire(task)
  ├── open an experiment with machine-checkable criteria
  ├── for each attempt (bounded):
  │     ├── state a hypothesis
  │     ├── SearchPlanner.plan(criteria, bridge)
  │     ├── record the attempt with its failure class
  │     └── stop if every criterion passed
  ├── if solved → create a skill_candidate (NOT a skill)
  └── verify(candidate)
        ├── replay run 1 in a separate interpreter (minicoder.learning.replay)
        ├── replay runs 2..3 in-process from an empty canvas
        └── pass only if all runs pass
promote(candidate)  refuses unless replay passed and runs ≥ 3
reuse(skill, variant)  substitute literals → run → repair failing criteria
```

### Planning is search, not a template

`SearchPlanner` (`learning/planner.py`) parses each criterion into a
*requirement*, asks tool discovery which tools might satisfy it, derives the
arguments from the requirement and the observed state, executes the step for
real, and keeps it only if criterion progress strictly increased.

Points that are load-bearing, each of which was a bug first:

* **Tool names come from the live catalogue.** `ToolIndex` reads
  `bridge.list_tools()` at runtime. There is no embedded list.
* **Vocabulary comes from the tool's own description.** `add_shape` declares its
  valid kinds in prose; discovery extracts them. Guessing produced
  `shape='shape'`, which the editor rejected.
* **Progress is partial credit.** `count(shape, >=, 2)` scores zero until two
  shapes exist, so the first shape looked like no progress and was reverted — a
  deadlock. `partial_credit()` scores the fraction satisfied.
* **Undo only reverts what changed.** Undoing unconditionally popped the
  previous *accepted* step, silently discarding the canvas resize.
* **Requirements and results are matched by text.** The requirement list is
  priority-sorted and the result list follows criteria order, so `zip()`
  paired the wrong requirement with the wrong result.
* **Procedures state their own assumptions.** A canvas requirement is always
  emitted as an explicit step, never inherited from the editor's default,
  otherwise the stored procedure cannot be re-flown at another size.

### Program tasks: synthesis, honestly labelled

`learning/synth.py` is enumerative program synthesis: candidates are compositions
of single-operation primitives, accepted only if they execute and pass the
task's assertions. Search runs in-process for speed; the winner is re-verified
in the guarded sandbox, and a candidate that fails there is rejected.

What it is not: understanding. Depth-3 enumeration provably cannot reach tasks
that need sequential state, and the two such benchmark tasks fail and are
reported as failures.

### Adaptation is distinct from acquisition

`reuse()` substitutes the new task's literals into a stored procedure, runs it,
and — if criteria fail — repairs *only* those criteria against the live state,
looping because fixing one can break another. The report distinguishes:

| mode | meaning |
|---|---|
| `direct` | the stored procedure worked unchanged |
| `repaired` | the stored procedure worked after targeted repair |
| `reacquired` | the procedure could not be adapted; the task was solved from scratch |
| `failed` | neither worked, and it says so |

## Containment

`minicoder/tools/guard.py` installs a PEP 578 audit hook inside the child
process before candidate code runs. It refuses filesystem access outside the
run directory, process spawning, sockets and `ctypes.dlopen`.

Before this existed, measured: `open('/etc/passwd').read()` succeeded and
`os.system(...)` spawned a shell. The old defence was a substring blocklist over
command lines, which cannot constrain `run_python`.

The guard is defence in depth, not a hypervisor, and the sandbox reports which
backend confined a run so no result claims confinement it did not have.

## Consolidation

Sleep now has eight stages. The new stage 5 reads *only solved* experiments and:

* de-duplicates against existing semantic nodes;
* records contradictions in `memory_conflicts` rather than overwriting;
* calibrates confidence from the measured replay rate, not from optimism;
* stamps `valid_from` / `supersedes` for temporal validity;
* writes `skill_dependencies` edges for every tool the procedure used;
* re-replays each procedure and records the outcome in `skill_replays`.

Retention is therefore a measurement, not a claim.

## Safeguards

`learning/safeguard.py`

* `BaselineRegistry` — named snapshots, SHA-256 manifest, files `chmod 0444`,
  `verify_baseline()` re-hashes. A second snapshot of the same name is refused.
* `RegressionGuard` — directional tolerances per metric (accuracy and retention
  higher-is-better, losses lower-is-better), absolute deltas.
* `ImprovementGate` — admit or revert, with a provenance row for each decision.
* `SkillVersionGuard` — archives a skill's previous row before replacement.

Demonstrated on a deliberately wrecked model: `skill_accuracy` 0.875 → 0.0,
`retention` 0.875 → 0.0, `val_ce` 5.68 → 356.10, all three caught, rollback
restored every value exactly and the baseline re-verified intact.

## Observability

`/api/learning/overview`, `/api/learning/skills`, `/api/learning/experiments`,
and the dashboard's **Acquisition** tab. Every figure is a recorded row or a
report file; when a report is missing the UI says "not run" rather than showing a
zero that looks like a measurement.

## What is still weak

Stated plainly, because the alternative is a system that only looks intelligent:

1. **Holdout generalisation is 0.0** for the 1.3M decoder, under every training
   variant tried. It reproduces its training tasks and nothing beyond them.
2. **Program acquisition is depth-bounded.** Two of 22 benchmark tasks fail; a
   task needing sequential state is out of reach of this search.
3. **Geometric variation has a limit.** A 3:4 skill adapts to another 3:4 canvas;
   a flipped 4:3 canvas fails, because two full-width text layers cannot stack
   in 768 px. Reported as failed, not averaged away.
4. **The planner's heuristics are crude.** Inflection and shared-prefix matching
   stand in for stemming; they work on the current probe set and are commented
   as such.
5. **Reduced-scale study.** The neural comparison uses 12 epochs of pretraining
   and 20 of SFT, not the shipped 40/40, so it is a controlled comparison
   between variants rather than a claim about the shipped checkpoint.
