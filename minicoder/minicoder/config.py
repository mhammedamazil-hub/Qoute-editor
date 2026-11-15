"""Central configuration. Everything is local-first and offline-capable.

Environment variables:
  MINICODER_HOME     — root of the persistent brain (default: <repo>/memory)
  MINICODER_DATASETS — where compiled training shards go (default: <repo>/datasets/sleep_skills)
  MINICODER_GITHUB_REPO — owner/name for sleep-skill dispatch (default: detected from git remote)
  MINICODER_GEMINI_KEY  — optional; enables the Gemini provider (never required)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _default_home() -> Path:
    env = os.environ.get("MINICODER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return _REPO_ROOT / "memory"


def _default_datasets() -> Path:
    env = os.environ.get("MINICODER_DATASETS")
    if env:
        return Path(env).expanduser().resolve()
    return _REPO_ROOT / "datasets" / "sleep_skills"


@dataclass(frozen=True)
class Settings:
    home: Path = field(default_factory=_default_home)
    datasets: Path = field(default_factory=_default_datasets)
    github_repo: str = field(default_factory=lambda: os.environ.get("MINICODER_GITHUB_REPO", ""))
    gemini_key: str = field(default_factory=lambda: os.environ.get("MINICODER_GEMINI_KEY", ""))
    github_token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", ""))
    github_dispatch: bool = field(default_factory=lambda: os.environ.get("MINICODER_GITHUB_DISPATCH", "") == "1")
    # working memory
    wm_capacity: int = 24            # max items held in working memory
    wm_pinned_max: int = 8           # max pinned (protected) items
    wm_expire_seconds: int = 3600    # unpinned items older than this may be evicted first
    # memory decay / forgetting
    decay_half_life_days: float = 14.0
    archive_threshold: float = 0.18  # decay score below → archived (recoverable)
    # retrieval
    embedding_dim: int = 384
    top_k: int = 6
    # metacognition
    clarification_threshold: float = 0.34  # below this confidence → ask a clarifying question

    # --- derived paths -------------------------------------------------------
    @property
    def db_path(self) -> Path: return self.home / "brain.db"
    @property
    def working_dir(self) -> Path: return self.home / "working"
    @property
    def procedural_dir(self) -> Path: return self.home / "procedural"
    @property
    def visual_cache(self) -> Path: return self.home / "visual_cache"
    @property
    def graph_dir(self) -> Path: return self.home / "knowledge_graph"
    @property
    def archived_dir(self) -> Path: return self.home / "archived"
    @property
    def sleep_logs(self) -> Path: return self.home / "sleep_logs"
    @property
    def checkpoints(self) -> Path: return self.home / "checkpoints"
    @property
    def backups(self) -> Path: return self.home / "backups"

    def ensure_dirs(self) -> None:
        for d in (self.home, self.working_dir, self.procedural_dir, self.visual_cache,
                  self.graph_dir, self.archived_dir, self.sleep_logs,
                  self.checkpoints, self.backups, self.datasets):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    global _settings
    if _settings is None or refresh:
        _settings = Settings()
    return _settings
