import pytest
from minicoder import procedural
from minicoder.models import VerificationStep
from minicoder.tools.coding import verify_python_solution

GOOD_SOLUTION = "def add(a, b):\n    return a + b\n"
GOOD_TESTS = "from solution import add\ndef test_add():\n    assert add(2, 3) == 5\n"
BAD_SOLUTION = "def add(a, b):\n    return a - b\n"


def test_verification_gate_promotes_passing_skill(brain_home):
    steps = verify_python_solution(solution=GOOD_SOLUTION, tests=GOOD_TESTS)
    assert all(s.passed for s in steps)
    skill = procedural.register_skill(name="add-integers", description="add two ints",
                                      domain="python", final_output=GOOD_SOLUTION,
                                      verification=steps)
    assert skill.verification_status == "VERIFIED"
    procedural.gate_check(skill)  # must not raise


def test_verification_gate_quarantines_failing_skill(brain_home):
    steps = verify_python_solution(solution=BAD_SOLUTION, tests=GOOD_TESTS)
    assert not all(s.passed for s in steps)
    skill = procedural.register_skill(name="broken-add", description="intentionally wrong",
                                      domain="python", final_output=BAD_SOLUTION,
                                      verification=steps)
    assert skill.verification_status == "FAILED"
    with pytest.raises(procedural.SkillGateError):
        procedural.gate_check(skill)


def test_skill_without_verification_never_verified(brain_home):
    skill = procedural.register_skill(name="no-proof", description="unproven",
                                      domain="chat", final_output="???")
    assert skill.verification_status == "UNVERIFIED"
    with pytest.raises(procedural.SkillGateError):
        procedural.gate_check(skill)


def test_reverify_failed_skill_promotes_on_pass(brain_home):
    steps = verify_python_solution(solution=BAD_SOLUTION, tests=GOOD_TESTS)
    skill = procedural.register_skill(name="fixme", description="starts broken",
                                      domain="python", final_output=BAD_SOLUTION,
                                      verification=steps)
    # simulate a human supplying the fix, then re-verify with a stub runner
    skill.verification = [VerificationStep(name=s.name, command=s.command, exit_code=0,
                                           output_sha256="0" * 64, passed=True)
                          for s in skill.verification]
    skill = procedural.reverify_skill(skill, lambda cmd: (0, "ok"))
    assert skill.verification_status == "VERIFIED"
