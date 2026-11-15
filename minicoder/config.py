"""Central configuration for Project MiniCoder.

Every knob that affects behaviour, capacity or safety lives here so that the
dashboard, the CLI and the tests all agree on one source of truth.  Paths are
resolved relative to the repository root (or ``MINICODER_HOME`` when set).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def install_root() -> Path:
    """Where the shipped code lives (the editor source, node_modules, dashboard).

    Distinct from ``Paths.home``, which is where *state* lives. Redirecting the
    state home (tests, evals) must not make the editor bridge disappear.
    """
    return Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    """Repository root: the folder that contains this package."""
    env = os.environ.get("MINICODER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


_ACTIVE_HOME: list[Path | None] = [None]


@dataclass(frozen=True, eq=False)
class Paths:
    """Filesystem layout for one MiniCoder home.

    ``home`` is usually fixed, but tests and evaluation suites need to redirect
    every subsystem at a throwaway directory. Modules bind ``CONFIG`` at import
    time, so instead of mutating each of them the path *derivations* below check
    the process-wide active home first. That keeps isolation honest: a suite
    that seeds memories cannot touch the live brain.
    """

    _home: Path
    _memory: Path
    _brain_db: Path
    @property
    def home(self) -> Path:
        """The active root.

        This must follow ``_ACTIVE_HOME`` like every derived path: code that
        computes ``relative_to(CONFIG.paths.home)`` for a stored file breaks when
        the files moved to a temp home but ``home`` still names the repo.
        """
        return _ACTIVE_HOME[0] or self._home

    @property
    def _root(self) -> Path:
        return self.home

    @property
    def memory(self) -> Path:
        return self._root / "memory"

    @property
    def brain_db(self) -> Path:
        return self.memory / "brain.db"

    @property
    def working(self) -> Path:
        return self.memory / "working"

    @property
    def procedural(self) -> Path:
        return self.memory / "procedural"

    @property
    def visual_cache(self) -> Path:
        return self.memory / "visual_cache"

    @property
    def knowledge_graph(self) -> Path:
        return self.memory / "knowledge_graph"

    @property
    def archived(self) -> Path:
        return self.memory / "archived"

    @property
    def sleep_logs(self) -> Path:
        return self.memory / "sleep_logs"

    @property
    def checkpoints(self) -> Path:
        return self.memory / "checkpoints"

    @property
    def datasets(self) -> Path:
        return self._root / "datasets"

    @property
    def sleep_skills(self) -> Path:
        return self.datasets / "sleep_skills"

    @property
    def training_runs(self) -> Path:
        return self.datasets / "training_runs"

    @property
    def dashboard(self) -> Path:
        return self._root / "minicoder" / "dashboard"

    @classmethod
    def build(cls, home: Path | None = None) -> Paths:
        root = (home or repo_root()).resolve()
        return cls(_home=root, _memory=root / "memory", _brain_db=root / "memory" / "brain.db")

    def ensure(self) -> Paths:
        for p in (
            self.memory,
            self.working,
            self.procedural,
            self.visual_cache,
            self.knowledge_graph,
            self.archived,
            self.sleep_logs,
            self.checkpoints,
            self.datasets,
            self.sleep_skills,
            self.training_runs,
        ):
            p.mkdir(parents=True, exist_ok=True)
        return self


# --------------------------------------------------------------------------
# memory
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryConfig:
    """Capacities and decay constants for the five memory systems."""

    db_name: str = "brain.db"
    # Working memory is a token/priority bounded scratchpad.
    working_capacity: int = 24          # max live items
    working_token_budget: int = 1800    # approximate tokens of pinned+recent text
    working_ttl_seconds: int = 60 * 45  # items expire unless pinned or reused
    # Episodic memory.
    episodic_retention_days: float = 365.0
    # Vector search.
    embedding_dim: int = 128
    # Semantic graph.
    graph_max_nodes: int = 20_000
    # Forgetting / decay: score = relevance*w1 + frequency*w2 + confidence*w3 + recency*w4
    decay_weights: tuple[float, float, float, float] = (0.35, 0.20, 0.25, 0.20)
    decay_half_life_days: float = 30.0
    archive_threshold: float = 0.22      # below this a memory is compressed into archives
    forget_threshold: float = 0.05       # below this (and unused) it is dropped
    # Sleep triggers.
    idle_sleep_seconds: int = 60 * 20
    episodic_capacity: int = 400         # soft cap that can trigger a sleep cycle


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """The compact multimodal backbone, trained locally from scratch.

    ``decoder``  : causal text/code transformer (the chat + coder brain)
    ``vision``   : ViT-style patch encoder + classifier heads (the image viewer)
    ``embedder`` : contrastive text embedder used by semantic memory retrieval
    """

    vocab_size: int = 1024
    d_model: int = 160
    n_layers: int = 5
    n_heads: int = 5
    d_ff: int = 448
    max_seq_len: int = 192
    dropout: float = 0.0
    tie_embeddings: bool = True

    vision_image_size: int = 32
    vision_patch: int = 4
    vision_d_model: int = 96
    vision_layers: int = 2
    vision_heads: int = 3

    embed_dim: int = 128
    seed: int = 1337


# --------------------------------------------------------------------------
# tools / sandbox
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxConfig:
    """Execution limits for the code sandbox (prime directive #5)."""

    timeout_seconds: float = 10.0
    memory_limit_mb: int = 768
    max_output_bytes: int = 40_000
    allow_network: bool = False
    allowed_write_roots: tuple[str, ...] = ()  # empty = scratch dir only
    require_approval_for_writes: bool = True
    max_file_bytes: int = 512_000


# --------------------------------------------------------------------------
# continual learning
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TrainingConfig:
    """Sleep compilation, dataset export and adapter training."""

    dataset_format: str = "jsonl"
    replay_ratio: float = 0.25           # replay buffer mixed into every shard
    min_verified_confidence: float = 0.75
    synthetic_variants_per_skill: int = 3
    shard_max_examples: int = 4000
    # Adapter training defaults chosen by measurement, not taste: at lr 5e-5 with
    # an 8:1 replay:new ratio the adapter retains 100% of the base model's known
    # tasks (0.88 -> 0.88). Higher LRs measurably destroy prior capability.
    lora_rank: int = 4
    lora_alpha: float = 8.0
    lr: float = 5e-5
    epochs: int = 6
    batch_size: int = 8
    replay_anchor_ratio: int = 8
    seed: int = 7
    # Level 5 validation gate: a candidate adapter ships only if it wins here.
    max_regression_drop: float = 0.005
    min_skill_gain: float = 0.01


@dataclass(frozen=True)
class ApiConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("*",)
    ws_telemetry_hz: float = 2.0


@dataclass(frozen=True)
class Config:
    paths: Paths = field(default_factory=Paths.build)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def load(cls, home: Path | None = None) -> Config:
        cfg = cls(paths=Paths.build(home))
        cfg.paths.ensure()
        return cfg


CONFIG = Config.load()


def activate_home(home: Path | str | None) -> Path | None:
    """Process-wide redirect used by tests/evals; returns the previous home."""
    prev = _ACTIVE_HOME[0]
    _ACTIVE_HOME[0] = Path(home).expanduser().resolve() if home is not None else None
    if _ACTIVE_HOME[0] is not None:
        for sub in ("memory", "datasets"):
            (_ACTIVE_HOME[0] / sub).mkdir(parents=True, exist_ok=True)
        Paths.build(_ACTIVE_HOME[0]).ensure()
    return prev


def reload(home: Path | str | None = None) -> Config:
    """Point the global config at a different home (tests, evals, per-run sandboxes).

    ``CONFIG`` is a frozen singleton read by every subsystem, so redirecting it
    is the only supported way to keep experiment data out of the live brain.
    """
    global CONFIG
    home_path = Path(home).expanduser().resolve() if home is not None else None
    CONFIG = Config(paths=Paths.build(home_path))
    CONFIG.paths.ensure()
    return CONFIG

# Provenance labels (prime directive #4). Every memory row must use one.
SOURCE_USER_INSTRUCTION = "user_instruction"
SOURCE_VERIFIED_EXECUTION = "verified_execution"
SOURCE_VISUAL_INSPECTION = "visual_inspection"
SOURCE_DOCUMENTATION = "documentation"
SOURCE_TRAINING_DATA = "training_data"
SOURCE_UNVERIFIED_HYPOTHESIS = "unverified_hypothesis"

VALID_SOURCES = frozenset(
    {
        SOURCE_USER_INSTRUCTION,
        SOURCE_VERIFIED_EXECUTION,
        SOURCE_VISUAL_INSPECTION,
        SOURCE_DOCUMENTATION,
        SOURCE_TRAINING_DATA,
        SOURCE_UNVERIFIED_HYPOTHESIS,
    }
)

# Verification states.
VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
FAILED = "FAILED"
QUARANTINED = "QUARANTINED"
VALID_STATUSES = frozenset({VERIFIED, UNVERIFIED, FAILED, QUARANTINED})

# Brain lifecycle states (mirrored by the dashboard).
STATE_WAKE = "WAKE"
STATE_PERCEIVE = "PERCEIVE"
STATE_THINK = "THINK"
STATE_ACT = "ACT"
STATE_LEARN = "LEARN"
STATE_REMEMBER = "REMEMBER"
STATE_SLEEP = "SLEEP"
STATE_COMPILE = "COMPILE_SKILLS"
STATE_GITHUB_TRAIN = "GITHUB_TRAINING"
BROADCAST_STATES = (
    STATE_WAKE,
    STATE_PERCEIVE,
    STATE_THINK,
    STATE_ACT,
    STATE_LEARN,
    STATE_REMEMBER,
    STATE_SLEEP,
    STATE_COMPILE,
    STATE_GITHUB_TRAIN,
)
