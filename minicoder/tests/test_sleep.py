import json
import time
from minicoder import episodic
from minicoder.brain import get_brain
from minicoder.sleep import latest_sleep_report


def test_full_sleep_cycle_compiles_shard(brain_home):
    brain = get_brain()
    result = brain.run_coding_task(
        task="Write a clamp(value, lo, hi) function",
        solution="def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n",
        tests=("from solution import clamp\n"
               "def test_clamp():\n    assert clamp(5, 0, 10) == 5\n    assert clamp(-3, 0, 10) == 0\n    assert clamp(99, 0, 10) == 10\n"),
        domain="python", skill_name="clamp-number")
    assert result["verified"]
    for i, tags in enumerate([["css", "ui"], ["css", "ui"], ["css", "ui"], ["api"]]):
        episodic.record_episode(situation=f"CSS grid collapsed on mobile project {i}",
                                modality="vision" if i < 3 else "text",
                                result="failed" if i < 3 else "done",
                                verification_status="FAILED" if i < 3 else "VERIFIED",
                                mistakes=["viewport units with 100% columns"] if i < 3 else [],
                                tags=tags, confidence=0.3 if i < 3 else 0.8)
    report = brain.sleep(trigger="test")
    assert report["episodes_reviewed"] > 0
    assert report["skills_compiled"] >= 1
    assert report["shard_path"] and report["shard_examples"] > 0
    assert report["github_dispatch"] == "pending_dispatch"  # tests never push
    assert report["weakness_domains"], "expected the css failure pattern to surface"
    assert "css" in report["weakness_domains"]
    stored = latest_sleep_report()
    assert stored and stored["id"] == report["id"]


def test_sleep_with_nothing_new_is_clean(brain_home):
    brain = get_brain()
    report = brain.sleep(trigger="test")
    assert report["skills_compiled"] == 0
    assert report["github_dispatch"] == "not_configured"
