"""The safety invariants. If any of these fail, the system is not trustworthy.

These are the prime directives from the blueprint expressed as executable
checks: no unverified training data, provenance everywhere, atomic backups,
no weight updates while awake, permissioned sandbox, never fabricate.
"""

from __future__ import annotations

import json

import pytest

from minicoder.config import FAILED, QUARANTINED, VALID_STATUSES, VERIFIED
from minicoder.memory.systems import (
    Episode,
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    Skill,
    VisualMemory,
)


# ---------------------------------------------------------------- provenance
def test_episode_rejects_unknown_source(db):
    em = EpisodicMemory(db)
    with pytest.raises(ValueError):
        em.add(Episode(situation="x" * 20, objective="y", source="made_up_source"))


def test_skill_rejects_unknown_source(db):
    pm = ProceduralMemory(db)
    with pytest.raises(ValueError):
        pm.add(Skill(slug="s", name="n", description="d", source="invented"), verified=True)


def test_unverified_skill_is_quarantined_not_verified(db):
    pm = ProceduralMemory(db)
    pm.add(Skill(slug="guess", name="Guess", description="A guess"), verified=False)
    assert pm.get("guess")["status"] == QUARANTINED
    assert all(s["slug"] != "guess" for s in pm.verified())


def test_skill_status_is_always_a_known_state(db):
    pm = ProceduralMemory(db)
    pm.add(Skill(slug="a", name="A", description="d"), verified=True)
    pm.add(Skill(slug="b", name="B", description="d"), verified=False)
    for row in pm.any():
        assert row["status"] in VALID_STATUSES


def test_every_memory_write_leaves_a_provenance_row(db):
    db.log_provenance("semantic", 1, "upsert", detail={"k": "v"})
    rows = db.query("SELECT * FROM provenance_events ORDER BY id DESC LIMIT 1")
    assert rows and rows[0]["entity"] == "semantic"
    assert json.loads(rows[0]["detail"])["k"] == "v"


# --------------------------------------------------------- wake/sleep boundary
def test_sleep_engine_refuses_concurrent_run(db):
    from minicoder.sleep.engine import SleepEngine

    engine = SleepEngine(db, train_after_compile=False, push_to_github=False)
    engine.busy = True  # simulate an in-flight cycle
    with pytest.raises(RuntimeError):
        engine.sleep()


def test_sleep_takes_an_atomic_backup_before_touching_memory(db):
    from minicoder.memory.systems import SemanticMemory
    from minicoder.sleep.engine import SleepEngine

    SemanticMemory(db).upsert("fact", "durable", "A durable fact.", status=VERIFIED, source="documentation")
    report = SleepEngine(db, train_after_compile=False, push_to_github=False).sleep(trigger="test")
    assert report.ended_at, "cycle never recorded completion"
    assert any("pre_sleep" in p.name for p in (db.paths.memory / "checkpoints").glob("*.db"))


# ------------------------------------------------------------------- sandbox
def test_sandbox_blocks_network_tooling():
    from minicoder.tools.sandbox import Sandbox

    ok, reason = Sandbox().check_command(["curl", "http://example.com"])
    assert not ok
    assert "network" in reason.lower() or "permission" in reason.lower()


def test_sandbox_blocks_destructive_commands():
    from minicoder.tools.sandbox import Sandbox

    ok, reason = Sandbox().check_command(["rm", "-rf", "/"])
    assert not ok and "permission" in reason.lower()


def test_sandbox_verifies_real_code():
    from minicoder.tools.sandbox import Sandbox

    passed, res = Sandbox().run_tests("def solve(nums):\n    return sum(nums)", "assert solve([1, 2, 3]) == 6")
    assert passed, res.stderr


def test_sandbox_reclaims_a_wrong_solution():
    from minicoder.tools.sandbox import Sandbox

    passed, _ = Sandbox().run_tests("def solve(nums):\n    return 0", "assert solve([1, 2, 3]) == 6")
    assert passed is False


# ------------------------------------------------------------------- backups
def test_backup_restore_roundtrip(db):
    SemanticMemory(db).upsert("fact", "keep me", "A durable fact.", status=VERIFIED, source="documentation")
    snap = db.backup("test")
    db.execute("DELETE FROM semantic_nodes")
    assert db.query("SELECT COUNT(*) FROM semantic_nodes")[0][0] == 0
    db.restore(snap)
    assert db.query("SELECT COUNT(*) FROM semantic_nodes")[0][0] == 1


def test_integrity_check_passes_on_a_real_db(db):
    result = db.verify_integrity()
    assert result["ok"] is True, result["detail"]


# --------------------------------------------------------- never fabricate
def test_answerer_refuses_questions_it_has_no_evidence_for(db):
    from minicoder.cognition.engine import GroundedAnswerer, NeuralBrain

    answerer = GroundedAnswerer(
        NeuralBrain(), EpisodicMemory(db), SemanticMemory(db), ProceduralMemory(db)
    )
    for question in (
        "Who won the 1998 world championship in curling?",
        "What is my grandmother's maiden name?",
        "What is the exact revenue of Acme Corp in Q3?",
    ):
        assert answerer.answer(question).source == "refuse", question


def test_off_domain_prompt_is_outside_the_training_distribution():
    from minicoder.cognition.engine import INTENT_FLOOR, intent_coverage

    assert intent_coverage("Who won the 1998 world championship in curling?") < INTENT_FLOOR
    assert intent_coverage("How do I make my poster feel more premium?") >= INTENT_FLOOR


def test_unverified_garbage_never_becomes_a_long_term_memory():
    from minicoder.sleep.engine import SleepEngine

    assert SleepEngine._is_learnable("b):      =") is False
    assert SleepEngine._is_learnable("b):      =                    ") is False
    assert SleepEngine._is_learnable("Generous margins raise perceived quality.") is True
    assert SleepEngine._is_learnable("def solve(nums):\n    return sum(nums)") is True


def test_consolidation_skips_unlearnable_episodes(db):
    from minicoder.sleep.engine import SleepEngine

    em = EpisodicMemory(db)
    em.add(Episode(
        situation="brain answered an off-domain question",
        objective="answer",
        modality="text",
        result="b):      =",
        status=FAILED,
        source="unverified_hypothesis",
        lessons="b):      =",
    ))
    SleepEngine(db, train_after_compile=False, push_to_github=False).sleep(trigger="test")
    labels = [r["label"] for r in db.query("SELECT label FROM semantic_nodes")]
    assert not any("=" in label for label in labels)


# ---------------------------------------------------------------- vision rows
def test_visual_memory_insert_binds_every_column(db, tmp_path):
    """Regression: the INSERT listed 12 columns and supplied 11 values."""
    from PIL import Image

    from minicoder.tools.vision import inspect

    path = tmp_path / "shot.png"
    Image.new("RGB", (256, 256), (248, 248, 250)).save(path)
    report = inspect(str(path), save_to_memory=True, ocr=False)
    assert report.memory_id is not None
    assert int(db.query("SELECT COUNT(*) FROM visual_memories")[0][0]) == 1


def test_visual_memory_is_idempotent_by_hash(db, tmp_path):
    from PIL import Image

    from minicoder.tools.vision import inspect

    path = tmp_path / "shot2.png"
    Image.new("RGB", (256, 256), (248, 248, 250)).save(path)
    first = inspect(str(path), save_to_memory=True, ocr=False)
    second = inspect(str(path), save_to_memory=True, ocr=False)
    assert first.memory_id == second.memory_id


def test_visual_search_finds_by_ocr_text(db):
    with db.write() as conn:
        conn.execute(
            "INSERT INTO visual_memories(ts, image_path, sha256, ocr_text, description, status, source)"
            " VALUES ('now', 'p.png', 'abc', 'checkout button clipped', 'an overflow bug',"
            " 'UNVERIFIED', 'visual_inspection')"
        )
    hits = VisualMemory(db).search("checkout clipped", limit=3)
    assert hits and hits[0]["sha256"] == "abc"


# --------------------------------------------------------------- retrieval
def test_hybrid_search_returns_nothing_for_unrelated_query(db):
    sm = SemanticMemory(db)
    sm.upsert("fact", "flexbox overflow", "A flex child with min-width:auto refuses to shrink.",
              status=VERIFIED, source="documentation")
    assert sm.search("quantum chromodynamics", limit=5) == []


def test_synonym_expansion_matches_across_wording(db):
    sm = SemanticMemory(db)
    sm.upsert("heuristic", "negative space",
              "Generous margins raise perceived quality.", status=VERIFIED, source="documentation")
    hits = sm.search("how much padding should I leave", limit=3)
    assert hits and hits[0]["label"] == "negative space"


def test_literal_match_outranks_synonym_match(db):
    sm = SemanticMemory(db)
    sm.upsert("fact", "retina export", "Export at 2x for retina screens.",
              status=VERIFIED, source="documentation")
    sm.upsert("fact", "canvas size", "1080x1350 is the portrait feed size.",
              status=VERIFIED, source="documentation")
    hits = sm.search("what size should I export at", limit=2)
    assert hits[0]["label"] == "retina export"


def test_episodic_search_never_returns_unrelated_episodes(db):
    em = EpisodicMemory(db)
    em.add(Episode(situation="User Amara shared a preference", objective="remember palette",
                   modality="text", result="Amara likes deep green", status=VERIFIED,
                   source="documentation", lessons="Amara likes deep green"))
    assert em.search("flexbox overflow", limit=5) == []


# --------------------------------------------------------------- procedural
def test_procedural_search_is_token_wise(db):
    pm = ProceduralMemory(db)
    pm.add(Skill(slug="code_sum_list", name="Sum a list",
                 description="Write a function returning the sum of a list.",
                 solution="def solve(nums):\n    return sum(nums)"), verified=True)
    hits = pm.search("sum list", limit=3)
    assert hits and hits[0]["slug"] == "code_sum_list"


def test_procedural_search_never_pads_with_unrelated_skills(db):
    pm = ProceduralMemory(db)
    pm.add(Skill(slug="only", name="Sort", description="Sort a list."), verified=True)
    assert pm.search("flexbox overflow") == []


# ------------------------------------------------------- agent canvas safety
def test_a_question_never_becomes_poster_copy():
    from minicoder.cognition.agent import parse_instruction

    intent = parse_instruction('Create a poster that reads "Which palette reads as premium?" at 1080x1350')
    assert "?" not in intent.get("quote", "")
    assert intent.get("quote", "") == ""


def test_topic_phrases_stay_topics_not_quotes():
    from minicoder.cognition.agent import parse_instruction

    intent = parse_instruction("Design a poster about patience at 1080x1350 with gold light")
    assert intent.get("topic") == "patience"
    assert "quote" not in intent


def test_explicit_quotes_become_copy_verbatim():
    from minicoder.cognition.agent import parse_instruction

    intent = parse_instruction('Create a poster that reads "Small steps compound" in emerald luxury')
    assert intent.get("quote") == "Small steps compound"


# ---------------------------------------------------------------- catalogues
def test_tool_catalogue_matches_the_editor(repo_root):
    from minicoder.seed import extract_tool_names

    names = extract_tool_names()
    assert len(names) >= 30
    assert "set_canvas_size" in names and "apply_palette" in names


def test_palette_catalogue_matches_the_editor(repo_root):
    from minicoder.seed import extract_palettes

    palettes = extract_palettes()
    assert len(palettes) == 8
    assert "midnight-gold" in {p["id"] for p in palettes}
