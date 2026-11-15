"""Verification runners used by the skill gate: real commands, real exit codes."""
from __future__ import annotations
import hashlib
import sys
from ..models import VerificationStep
from .sandbox import run_sandboxed


def verify_python_solution(*, solution: str, tests: str, timeout: float = 30.0) -> list[VerificationStep]:
    """Write solution.py + test_solution.py into a sandbox, run pytest.
    Returns verification steps with REAL exit codes and output hashes."""
    steps: list[VerificationStep] = []
    # 1) syntax gate
    syntax = run_sandboxed([sys.executable, "-c",
        "import ast,sys; ast.parse(open('solution.py').read()); print('syntax-ok')"],
        timeout=10.0, files={"solution.py": solution, "test_solution.py": tests})
    steps.append(VerificationStep(
        name="syntax", command="python -c ast.parse(solution.py)",
        exit_code=syntax.exit_code,
        output_sha256=hashlib.sha256((syntax.stdout + syntax.stderr).encode()).hexdigest(),
        passed=syntax.exit_code == 0))
    # 2) test gate — only if syntax passed (no point running broken code)
    if syntax.exit_code == 0:
        test = run_sandboxed([sys.executable, "-m", "pytest", "-q", "test_solution.py"],
                             timeout=timeout, files={"solution.py": solution, "test_solution.py": tests})
        steps.append(VerificationStep(
            name="pytest", command="python -m pytest -q test_solution.py",
            exit_code=test.exit_code,
            output_sha256=hashlib.sha256((test.stdout + test.stderr).encode()).hexdigest(),
            passed=test.exit_code == 0))
    else:
        steps.append(VerificationStep(
            name="pytest", command="python -m pytest -q test_solution.py",
            exit_code=-1,
            output_sha256=hashlib.sha256(b"skipped: syntax gate failed").hexdigest(),
            passed=False))
    return steps
