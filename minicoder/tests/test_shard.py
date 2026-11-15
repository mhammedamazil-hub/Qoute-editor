import json
from minicoder import shard, procedural
from minicoder.tools.coding import verify_python_solution

SOLUTION = "def double(x):\n    return 2 * x\n"
TESTS = "from solution import double\ndef test_double():\n    assert double(21) == 42\n"


def _verified_skill():
    steps = verify_python_solution(solution=SOLUTION, tests=TESTS)
    assert all(s.passed for s in steps)
    return procedural.register_skill(name="double-value", domain="python",
                                     description="Return twice the input value",
                                     final_output=SOLUTION, inputs={"task": "double a number"},
                                     reasoning_trace=["read input", "multiply by two", "return"],
                                     verification=steps)


def test_compile_shard_and_validate(brain_home, tmp_path):
    skill = _verified_skill()
    out_dir = tmp_path / "shards"
    summary = shard.compile_shard([skill], out_dir=out_dir)
    assert summary["examples"] == 6  # instruction + cot + 3 variations + edge_case
    report = shard.validate_shard_file(out_dir / summary["shard_path"].split("/")[-1])
    assert report.passed, report.errors
    line = json.loads(open(summary["shard_path"]).read().splitlines()[0])
    prov = line["provenance"]
    assert prov["verification_status"] == "VERIFIED"
    assert prov["source"] == "verified_execution"
    assert len(prov["verification_hash"]) == 64


def test_dedup_across_compiles(brain_home, tmp_path):
    skill = _verified_skill()
    first = shard.compile_shard([skill], out_dir=tmp_path / "s")
    second = shard.compile_shard([skill], out_dir=tmp_path / "s")
    assert first["examples"] == 6
    assert second["examples"] == 0  # identical content → deduplicated


def test_validator_rejects_unverified_line(brain_home, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "id": "x" * 16, "skill_id": "skill_x", "kind": "instruction",
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
        "provenance": {"source": "verified_execution", "skill_id": "skill_x",
                       "verification_status": "UNVERIFIED", "license": "MIT",
                       "verification_hash": "a" * 64, "example_hash": "b" * 16},
    }) + "\n")
    report = shard.validate_shard_file(bad)
    assert not report.passed and any("VERIFIED" in e for e in report.errors)


def test_validator_rejects_bad_license(brain_home, tmp_path):
    skill = _verified_skill()
    out = tmp_path / "s2"
    summary = shard.compile_shard([skill], out_dir=out)
    lines = open(summary["shard_path"]).read().splitlines()
    obj = json.loads(lines[0])
    obj["provenance"]["license"] = "Proprietary-All-Rights-Reserved"
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text(json.dumps(obj) + "\n")
    assert not shard.validate_shard_file(tampered).passed
