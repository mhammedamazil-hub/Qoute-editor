"""Adaptive Sleep 2.0 — the measurements that turn a sleep cycle into a report.

Phase 3's sleep loop had eight stages but it could only say *that* it ran them.
It could not say whether consolidation produced anything worth keeping, whether
two nodes said the same thing, whether a skill survived replay, or how this
cycle differed from the last one. This module adds those measurements.

Everything here is an *analysis* over the live database, not a new stage type:
``SleepEngine`` still runs the same eight stages and calls into these helpers at
the point where their answer is meaningful. Each helper returns a plain dict so
it can be embedded in a stage payload and written to the cycle report.

Design rules:

* **Read before write.** Redundancy and contradiction detection only report;
  they mutate memory only through narrow, guarded paths.
* **Idempotent where it can be.** Running a cycle twice must not create a second
  copy of an abstraction, a conflict, or a promoted skill.
* **Candidates never enter production unverified.** ``promote_candidates``
  requires a recorded replay with more passes than failures *and* a structurally
  valid procedure. A candidate with zero replay runs is never promoted.
* **No empty examples, ever.** Skill validation rejects a procedure with no
  steps or a step with no tool name, which is what produced the stage-7
  ``ValueError`` in Phase 3.
* **Reproducible.** ``fingerprint`` hashes the parts of a report that should be
  identical for identical input, so a re-run can be compared honestly.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

STOPWORDS = frozenset(
    """a an the and or but if then than that this these those of to in on for with by
    from as at is are was were be been being it its their there here what which who
    when where why how do does did can could should would may might will just into
    over under about more most less least very much many any some such same own
    """.split()
)

# Nodes below this usefulness score are candidates for pruning, not deleted here:
# stage 6 (forgetting) owns deletion and needs the score to justify it.
PRUNE_THRESHOLD = 0.28
REDUNDANCY_THRESHOLD = 0.82
ABSTRACTION_MIN_MEMBERS = 4
# Abstractions are unverified scaffolding: a handful per cycle is enough, and the
# total is capped so repeated cycles cannot slowly flood semantic memory with
# derivative nodes. Verified knowledge still outranks them in retrieval.
ABSTRACTIONS_PER_CYCLE = 2
ABSTRACTION_CAP = 8
# Matches the acquisition loop's ``min_replay_runs`` default: three recorded
# replays is the bar for production. A single lucky replay is not evidence.
MIN_PROMOTION_RUNS = 3


def _rows(db: Any, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    """Rows as plain dicts — the rest of this module uses ``.get`` freely."""
    return [dict(r) for r in db.query(sql, params)]


def _int(value: Any) -> int:
    """Count from a column that may hold an int, a numeric string, or a JSON list.

    ``skill_candidates.replay_failures`` stores the *messages* ("[\"run 1: …\"]"),
    so a plain ``int()`` raised ValueError on the live database. A list counts by
    its length; anything unparseable counts as zero, which can only make the
    promotion gate stricter.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return len(parsed) if isinstance(parsed, list) else 0
        except json.JSONDecodeError:
            return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def tokens(text: str) -> set[str]:
    """Content tokens, lowercased, stopwords and one-letter fragments dropped."""
    return {
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 1 and t not in STOPWORDS
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _age_days(ts: str | None) -> float:
    if not ts:
        return 365.0
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            when = datetime.strptime(str(ts)[:26].replace("+00:00", ""), fmt)
            return max(0.0, (datetime.now(UTC).replace(tzinfo=None) - when).total_seconds() / 86400)
        except ValueError:
            continue
    return 365.0


def usefulness(node: dict[str, Any]) -> float:
    """How much a semantic node is earning its place.

    A node is useful if it is *used* (access count), *trusted* (source confidence)
    and *current* (recent access). Deliberately simple and inspectable: a learned
    weighting would need outcome labels that Phase 4 does not have yet, and
    inventing those would be the fake-learning failure mode.
    """
    access = min(1.0, float(node.get("access_count") or 0) / 8.0)
    conf = min(1.0, max(0.0, float(node.get("confidence") or 0.5)))
    recency = max(0.0, 1.0 - _age_days(node.get("last_access") or node.get("updated_at")) / 45.0)
    return round(0.45 * access + 0.35 * conf + 0.20 * recency, 4)


class AdaptiveAnalysis:
    """The eight Adaptive Sleep 2.0 analyses, each a pure-ish DB query."""

    def __init__(self, db: Any, semantic: Any = None) -> None:
        self.db = db
        # Optional canonical semantic store. When present, abstraction goes
        # through SemanticMemory.upsert so it inherits dedupe, provenance and
        # conflict recording instead of hand-rolling an INSERT.
        self.semantic = semantic

    # ------------------------------------------------------------ 1. usefulness
    def score_nodes(self, limit: int = 400) -> dict[str, Any]:
        rows = _rows(self.db,
            "SELECT id, kind, label, content, confidence, access_count, last_access,"
            " updated_at FROM semantic_nodes WHERE archived = 0 LIMIT ?", (limit,))
        scored = [{**r, "usefulness": usefulness(r)} for r in rows]
        if not scored:
            return {"scored": 0, "mean": 0.0, "below_threshold": 0, "weakest": []}
        below = [s for s in scored if s["usefulness"] < PRUNE_THRESHOLD]
        weakest = sorted(scored, key=lambda s: s["usefulness"])[:5]
        return {
            "scored": len(scored),
            "mean": round(sum(s["usefulness"] for s in scored) / len(scored), 3),
            "below_threshold": len(below),
            "threshold": PRUNE_THRESHOLD,
            "weakest": [{"id": s["id"], "label": str(s["label"])[:60],
                         "usefulness": s["usefulness"]} for s in weakest],
        }

    # ------------------------------------------------------------ 2. redundancy
    def find_redundant(self, limit: int = 300) -> list[list[dict[str, Any]]]:
        """Groups of live nodes that say the same thing, by token overlap.

        Compared within a kind only: a ``lesson`` and a ``fact`` can share words
        without being duplicates.
        """
        rows = _rows(self.db,
            "SELECT id, kind, label, content, confidence FROM semantic_nodes"
            " WHERE archived = 0 LIMIT ?", (limit,))
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by_kind[r["kind"]].append(r)
        groups: list[list[dict[str, Any]]] = []
        for members in by_kind.values():
            toks = {m["id"]: tokens(f"{m['label']} {m['content']}") for m in members}
            used: set[int] = set()
            for i, a in enumerate(members):
                if a["id"] in used:
                    continue
                group = [a]
                for b in members[i + 1:]:
                    if b["id"] in used:
                        continue
                    if _same_claim(a, b, toks[a["id"]], toks[b["id"]]):
                        group.append(b)
                        used.add(b["id"])
                if len(group) > 1:
                    used.add(a["id"])
                    groups.append(group)
        return groups

    def dedupe(self, groups: list[list[dict[str, Any]]]) -> dict[str, Any]:
        """Archive the weaker copy in each redundant group. Never hard-deletes.

        Nodes are archived rather than removed so provenance for old answers
        still resolves, and the action is recorded in the cycle report.
        """
        archived: list[int] = []
        for group in groups:
            keeper = max(group, key=lambda n: (float(n.get("confidence") or 0), -int(n["id"])))
            for node in group:
                if node["id"] == keeper["id"]:
                    continue
                self.db.execute(
                    "UPDATE semantic_nodes SET archived = 1, updated_at = ? WHERE id = ?",
                    (_now_iso(), node["id"]))
                archived.append(int(node["id"]))
        return {"groups": len(groups), "archived": len(archived), "ids": archived[:20]}

    # -------------------------------------------------------- 3. contradiction
    def find_contradictions(self) -> list[dict[str, Any]]:
        """Node pairs where one side explicitly negates what the other asserts.

        The test is narrow on purpose. Two memories that differ in a number
        ("a 4-step trajectory…" vs "a 3-step trajectory…") are *refinements*, not
        contradictions, and an earlier word-list version of this check flagged
        exactly that pair on the live database. So a pair qualifies only if one
        content carries a negation cue, the other does not, and the two say the
        same thing once the negation is removed. Findings are recorded as
        unresolved conflicts for the engine and the report — never auto-resolved.
        """
        rows = _rows(self.db,
            "SELECT id, kind, label, content FROM semantic_nodes WHERE archived = 0 LIMIT 300")
        pairs = []
        toks = {r["id"]: tokens(f"{r['label']} {r['content']}") for r in rows}
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a["kind"] != b["kind"]:
                    continue
                sim = jaccard(toks[a["id"]], toks[b["id"]])
                if sim < 0.5:
                    continue
                # A contradiction is about the *same claim*, and the claim lives
                # in the label. Without this, a success record and a failure
                # record that quote the same request look "opposed" — they are
                # simply different events.
                if jaccard(tokens(str(a["label"])), tokens(str(b["label"]))) < 0.6:
                    continue
                reason = _negation_conflict(f"{a['content']}", f"{b['content']}")
                if reason:
                    pairs.append({"a": a["id"], "b": b["id"], "similarity": round(sim, 3),
                                  "reason": reason})
        return pairs

    def record_conflicts(self, pairs: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist new contradictions; idempotent on the (a, b) pair."""
        added = 0
        for pair in pairs:
            lo, hi = sorted((pair["a"], pair["b"]))
            exists = self.db.query_one(
                "SELECT id FROM memory_conflicts WHERE node_a = ? AND node_b = ?", (lo, hi))
            if exists:
                continue
            self.db.execute(
                "INSERT INTO memory_conflicts(ts, node_a, node_b, reason, resolved)"
                " VALUES (?,?,?,?,0)", (_now_iso(), lo, hi, pair["reason"]))
            added += 1
        return {"detected": len(pairs), "recorded": added}

    # ---------------------------------------------------------- 4. abstraction
    def abstract(self, min_members: int = ABSTRACTION_MIN_MEMBERS) -> dict[str, Any]:
        """Create one higher-level node per well-supported topic cluster.

        A cluster is a token that appears in at least ``min_members`` distinct
        node labels. The abstraction summarises what those nodes agree on. It is
        idempotent by label: re-running finds the existing node and skips it.
        """
        rows = _rows(self.db,
            "SELECT id, kind, label, content FROM semantic_nodes WHERE archived = 0"
            " AND kind != 'abstraction' LIMIT 300")
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            for tok in tokens(str(r["label"])):
                clusters[tok].append(r)
        existing_n = self.db.query_one(
            "SELECT COUNT(*) c FROM semantic_nodes WHERE kind = 'abstraction' AND archived = 0")
        room = ABSTRACTION_CAP - int(existing_n["c"] if existing_n else 0)
        if room <= 0:
            return {"created": 0, "items": [], "capped": True,
                    "cap": ABSTRACTION_CAP}
        created = []
        for tok, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
            if len(members) < min_members:
                continue
            label = f"abstract:{tok}"
            if self.db.query_one("SELECT id FROM semantic_nodes WHERE label = ?", (label,)):
                continue
            lines = []
            seen = set()
            for m in members:
                snippet = " ".join(str(m["content"]).split())[:140]
                if snippet and snippet not in seen:
                    seen.add(snippet)
                    lines.append(f"- {snippet}")
                if len(lines) >= 4:
                    break
            if not lines:
                continue
            content = (f"{len(members)} memories about '{tok}'. Common content:\n"
                       + "\n".join(lines))
            if self.semantic is not None:
                nid = self.semantic.upsert(
                    "abstraction", label, content, status="UNVERIFIED",
                    source="learning_loop", confidence=0.6,
                    meta={"members": [m["id"] for m in members][:12], "token": tok,
                          "by": "adaptive_sleep"})
            else:
                nid = self.db.execute(
                    "INSERT INTO semantic_nodes(kind, label, content, status, source,"
                    " confidence, created_at, updated_at, access_count, last_access,"
                    " archived, meta)"
                    " VALUES ('abstraction', ?, ?, 'UNVERIFIED', 'learning_loop', 0.6,"
                    " ?, ?, 0, ?, 0, ?)",
                    (label, content, _now_iso(), _now_iso(), _now_iso(),
                     json.dumps({"members": [m["id"] for m in members][:12], "token": tok})))
            created.append({"label": label, "members": len(members), "id": int(nid)})
            if len(created) >= min(ABSTRACTIONS_PER_CYCLE, room):
                break
        return {"created": len(created), "items": created}

    # ------------------------------------------------------ 5. skill verification
    def verify_skills(self, limit: int = 300) -> dict[str, Any]:
        """Verification of every skill, using the compiler's own admissions rules.

        A skill yields a training example only if it is ``VERIFIED``, its stored
        verification passed, and it has a non-empty solution. Phase 3's stage 7
        raised ``ValueError`` because such a check was missing. Editor skills
        additionally need at least one callable step.
        """
        rows = _rows(self.db,
            "SELECT id, slug, domain, tool_calls, solution, verification, status"
            " FROM skills LIMIT ?", (limit,))
        broken, checked, verified = [], 0, 0
        for r in rows:
            checked += 1
            if str(r["status"]).upper() != "VERIFIED":
                continue
            verified += 1
            try:
                ver = json.loads(r["verification"] or "{}")
            except json.JSONDecodeError:
                broken.append({"slug": r["slug"], "why": "unparseable verification"})
                continue
            if not isinstance(ver, dict) or not ver.get("passed"):
                broken.append({"slug": r["slug"], "why": "not marked passed"})
                continue
            if not str(r["solution"] or "").strip():
                broken.append({"slug": r["slug"], "why": "empty solution -> empty example"})
                continue
            try:
                calls = json.loads(r["tool_calls"] or "[]")
            except json.JSONDecodeError:
                broken.append({"slug": r["slug"], "why": "unparseable tool_calls"})
                continue
            if r["domain"] == "editor" and not calls:
                broken.append({"slug": r["slug"], "why": "editor skill with no steps"})
                continue
            if calls and not all(isinstance(c, dict) and c.get("tool") for c in calls):
                broken.append({"slug": r["slug"], "why": "step without a tool name"})
        return {"checked": checked, "verified": verified, "ok": verified - len(broken),
                "broken": broken[:10], "broken_count": len(broken)}

    # --------------------------------------------------- 6. retention testing
    def retention_probe(self, replay, limit: int = 4) -> dict[str, Any]:
        """Replay a small random-ish sample of verified skills and count passes.

        ``replay`` is the engine's existing retention replay callable, so the
        measurement uses the same path that already writes ``skill_replays``.
        Sampling is by lowest-recent-use so coverage rotates across cycles
        instead of re-testing the same three skills forever.
        """
        rows = _rows(self.db,
            "SELECT slug, tool_calls FROM skills WHERE UPPER(status) = 'VERIFIED'"
            " AND tool_calls IS NOT NULL AND tool_calls != '[]'"
            " ORDER BY COALESCE(last_used, created_at) ASC LIMIT ?", (limit,))
        passed, failed, details = 0, 0, []
        for r in rows:
            try:
                proc = json.loads(r["tool_calls"] or "[]")
            except json.JSONDecodeError:
                failed += 1
                details.append({"slug": r["slug"], "ok": False, "why": "bad procedure json"})
                continue
            if not proc:
                failed += 1
                details.append({"slug": r["slug"], "ok": False, "why": "empty procedure"})
                continue
            try:
                ok = bool(replay(r["slug"], proc))
            except Exception as exc:  # a broken replay is a failed test, not a crash
                ok = False
                details.append({"slug": r["slug"], "ok": False, "why": type(exc).__name__})
            if ok:
                passed += 1
            else:
                failed += 1
            details.append({"slug": r["slug"], "ok": ok})
        total = passed + failed
        return {"tested": total, "passed": passed, "failed": failed,
                "pass_rate": round(passed / total, 3) if total else None,
                "details": details[:8]}

    # ---------------------------------------------------- 7. forgetting analysis
    def forgetting_analysis(self, cycle_id: int | None = None,
                            exclude_ids: tuple[int, ...] | list[int] = ()) -> dict[str, Any]:
        """What was forgotten, and whether forgetting was a mistake in hindsight.

        "Regret" counts archived nodes that were accessed in the last 14 days:
        those are the ones the system may have needed again.
        """
        archived = [r for r in _rows(self.db,
            "SELECT id, label, kind, confidence, last_access, updated_at FROM semantic_nodes"
            " WHERE archived = 1") if r["id"] not in set(exclude_ids)]
        if not archived:
            return {"archived": 0, "regret": 0, "by_kind": {}, "rate": 0.0}
        regret = [a for a in archived if _age_days(a.get("last_access") or a.get("updated_at")) <= 14]
        by_kind: dict[str, int] = defaultdict(int)
        for a in archived:
            by_kind[str(a["kind"])] += 1
        live = self.db.query_one("SELECT COUNT(*) c FROM semantic_nodes WHERE archived = 0")
        live_n = int(live["c"]) if live else 0
        total = live_n + len(archived)
        return {
            "archived": len(archived),
            "regret": len(regret),
            "regret_rate": round(len(regret) / len(archived), 3),
            "by_kind": dict(by_kind),
            "compression": round(len(archived) / total, 3) if total else 0.0,
        }

    # ------------------------------------------------- 8. safe candidate promotion
    def promote_candidates(self, limit: int = 20) -> dict[str, Any]:
        """Promote only candidates with a *recorded, passing* replay.

        The gate is deliberately strict:

        * ``replay_runs > 0`` — an untested candidate never ships;
        * ``replay_passed > replay_failures`` — a coin flip is not verification;
        * the procedure must parse, be non-empty, and every step must name a tool.

        Promotion happens inside one transaction so the candidate row and the
        skill row cannot disagree if the process dies mid-write.
        """
        rows = _rows(self.db,
            "SELECT id, slug, procedure, replay_runs, replay_passed, replay_failures, status"
            " FROM skill_candidates WHERE status NOT IN ('promoted','rejected') LIMIT ?", (limit,))
        promoted, rejected, held = [], [], []
        for r in rows:
            try:
                proc = json.loads(r["procedure"] or "[]")
            except json.JSONDecodeError:
                rejected.append({"slug": r["slug"], "why": "bad procedure"})
                continue
            steps = [s for s in proc if isinstance(s, dict) and s.get("tool")] if isinstance(proc, list) else []
            runs = _int(r["replay_runs"])
            good = _int(r["replay_passed"])
            bad = _int(r["replay_failures"])
            if not steps:
                rejected.append({"slug": r["slug"], "why": "no callable steps"})
                continue
            if runs < MIN_PROMOTION_RUNS or good < runs or good <= bad:
                held.append({"slug": r["slug"], "runs": runs, "passed": good, "failed": bad,
                             "why": f"needs >= {MIN_PROMOTION_RUNS} recorded passes"})
                continue

            def _tx(conn, r=r, steps=steps, runs=runs, good=good):
                exists = conn.execute("SELECT id FROM skills WHERE slug = ?", (r["slug"],)).fetchone()
                if not exists:
                    conn.execute(
                        # ``skills`` has no ``procedure`` column: the executable steps
                        # belong in ``tool_calls`` and the rendered form in ``solution``.
                        "INSERT INTO skills(slug, name, domain, description, tool_calls,"
                        " solution, verification, status, source, confidence, created_at,"
                        " updated_at)"
                        " VALUES (?, ?, 'editor', ?, ?, ?, ?, 'VERIFIED', 'learning_loop',"
                        " 0.7, ?, ?)",
                        (r["slug"], r["slug"].replace("_", " "),
                         f"promoted from candidate {r['id']}",
                         json.dumps(steps), json.dumps(steps),
                         json.dumps({"passed": True, "promoted_from_candidate": r["id"],
                                     "replay_runs": runs, "replay_passed": good}),
                         _now_iso(), _now_iso()))
                conn.execute(
                    "UPDATE skill_candidates SET status='promoted', promoted_skill=? WHERE id=?",
                    (r["slug"], r["id"]))

            try:
                with self.db.write() as conn:  # one transaction: candidate + skill agree
                    _tx(conn)
                promoted.append({"slug": r["slug"], "runs": runs, "passed": good})
            except Exception as exc:
                held.append({"slug": r["slug"],
                             "why": f"promotion failed: {type(exc).__name__}: {exc}"[:200]})
        return {"promoted": len(promoted), "items": promoted,
                "held": len(held), "held_items": held[:6], "rejected": len(rejected),
                "rejected_items": rejected[:6]}

    # ----------------------------------------------------- 9. cycle-over-cycle
    def cycle_delta(self, prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
        """Numeric change in headline metrics between the previous and this cycle."""
        if not prev:
            return {"first_cycle": True, "changes": {}}
        before = (prev.get("metrics") or {})
        after = (cur.get("metrics") or {})
        keys = ["episodes_consolidated", "nodes_added", "learning_extracted",
                "learning_retention_passed", "duration_seconds"]
        changes = {}
        for k in keys:
            a, b = before.get(k), after.get(k)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                changes[k] = {"before": a, "after": b, "delta": round(b - a, 3)}
        stats_before = (before.get("db_stats") or {})
        stats_after = (after.get("db_stats") or {})
        for k in ("episodes", "semantic_nodes", "skills", "conflicts"):
            if k in stats_before and k in stats_after:
                changes[k] = {"before": stats_before[k], "after": stats_after[k],
                              "delta": stats_after[k] - stats_before[k]}
        return {"first_cycle": False, "changes": changes}

    # ------------------------------------------------------- 10. reproducibility
    @staticmethod
    def fingerprint(report: dict[str, Any]) -> str:
        """Stable hash of the parts of a report that should not vary run to run.

        Timings, durations and absolute timestamps are excluded on purpose: they
        differ every cycle and would make every fingerprint unique.
        """
        keep = []
        for stage in report.get("stages", []):
            payload = {k: v for k, v in stage.items()
                       if k not in ("ms", "duration_ms", "started_at", "ended_at", "fingerprint")}
            keep.append({"stage": stage.get("stage"), "name": stage.get("name"),
                         "payload": _stable(payload)})
        blob = json.dumps(keep, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


NEGATION_CUES = ("not", "never", "cannot", "can't", "don't", "doesn't", "no longer",
                 "isn't", "aren't", "won't", "should not", "must not")


def _has_negation(text: str) -> bool:
    low = f" {(text or '').lower()} "
    return any(f" {cue} " in low or f" {cue}," in low or f" {cue}." in low
               for cue in NEGATION_CUES)


def _negation_conflict(a: str, b: str) -> str:
    """Reason string when one side explicitly negates the other, else "".

    Deliberately narrow: a pair counts only when exactly one side carries a
    negation cue and the two still share most of their vocabulary. Numbers that
    differ ("4-step" vs "3-step") are refinements, not contradictions — the
    earlier word-list version of this check flagged precisely that pair on the
    live database, which is why it is gone.
    """
    na, nb = _has_negation(a), _has_negation(b)
    if na == nb:
        return ""
    if jaccard(tokens(a), tokens(b)) < 0.6:
        return ""
    negated = (a if na else b)[:80]
    return f"one memory negates the other on the same topic (negated side: {negated!r})"


def _same_claim(a: dict[str, Any], b: dict[str, Any], ta: set[str], tb: set[str]) -> bool:
    """True when two nodes make the same claim.

    Word overlap alone is too loose: a question and its answer share vocabulary
    while being different memories. Require the labels to agree as well, or the
    contents to be equal up to whitespace/punctuation.
    """
    ca = " ".join(str(a.get("content") or "").lower().split())
    cb = " ".join(str(b.get("content") or "").lower().split())
    if ca and ca == cb:
        return True
    if jaccard(ta, tb) < REDUNDANCY_THRESHOLD:
        return False
    la = tokens(str(a.get("label") or ""))
    lb = tokens(str(b.get("label") or ""))
    return jaccard(la, lb) >= 0.5



def _stable(obj: Any) -> Any:
    """Strip volatile fields recursively so fingerprinting ignores noise."""
    if isinstance(obj, dict):
        return {k: _stable(v) for k, v in sorted(obj.items())
                if k not in ("ms", "seconds", "duration_seconds", "started_at", "ended_at",
                             "backup", "ts", "timestamp")}
    if isinstance(obj, list):
        return [_stable(v) for v in obj[:40]]
    return obj
