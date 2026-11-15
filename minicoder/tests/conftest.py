import os
import sys
from pathlib import Path
import pytest

# Must happen BEFORE any minicoder import touches get_settings().
@pytest.fixture()
def brain_home(tmp_path, monkeypatch):
    home = tmp_path / "memory"
    datasets = tmp_path / "datasets" / "sleep_skills"
    monkeypatch.setenv("MINICODER_HOME", str(home))
    monkeypatch.setenv("MINICODER_DATASETS", str(datasets))
    monkeypatch.setenv("MINICODER_GITHUB_DISPATCH", "")  # never push from tests
    from minicoder.config import get_settings
    get_settings(refresh=True)
    from minicoder.db import init_db
    init_db()
    yield home
    get_settings(refresh=True)
