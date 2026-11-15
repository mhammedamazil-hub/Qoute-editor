"""Shared fixtures.

Every test runs against a throwaway MiniCoder home. The suite seeds memories,
pushes skills and writes snapshots, and none of that may touch the developer's
live brain (an earlier version of the eval suites did, and it polluted the
production database with dozens of duplicate episodes).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from minicoder import config as config_mod


@pytest.fixture()
def home(tmp_path: Path):
    """Redirect the whole process at an isolated home, then restore it."""
    prev = config_mod.activate_home(tmp_path)
    try:
        yield tmp_path
    finally:
        config_mod.activate_home(prev)


@pytest.fixture()
def db(home: Path):
    from minicoder.memory.db import BrainDB

    return BrainDB()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture()
def checkpoint_copy(tmp_path: Path) -> Path:
    """A copy of the real checkpoints so model tests never mutate the originals."""
    from minicoder.config import CONFIG

    dst = tmp_path / "checkpoints"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("tokenizer.json", "lm.pt", "embedder.pt", "vision.pt"):
        path = CONFIG.paths.checkpoints / name
        if path.exists():
            shutil.copy2(path, dst / name)
    return dst


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: heavy training/eval tests")
