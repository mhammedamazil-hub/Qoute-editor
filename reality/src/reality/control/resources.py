"""Resource budgets for headless runs and previews (see RESOURCE_LIMITS.md).

Every limit is a hard stop that raises ``OperationError(resource_limit)`` with the value that was exceeded. Nothing is
silently truncated. Memory is the process peak resident set size reported by the operating system, so it bounds the
whole Python process, not only one operation.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .errors import OperationError

DEFAULTS: Dict[str, Any] = {
    "max_steps": 2_000_000,          # integration steps per run (about 100 s of wall time at 1e-4 s steps here)
    "max_records": 200_000,          # stored time samples per run
    "max_wall_seconds": 120.0,       # wall-clock budget per run
    "max_memory_mb": 1024.0,         # process peak RSS budget
    "max_pixels": 1_000_000,         # preview pixels (width x height)
    "max_image_side": 2048,          # preview side length in pixels
    "threads": 1,                    # the only supported value in this release
}


@dataclass(frozen=True)
class ResourceLimits:
    max_steps: int = DEFAULTS["max_steps"]
    max_records: int = DEFAULTS["max_records"]
    max_wall_seconds: float = DEFAULTS["max_wall_seconds"]
    max_memory_mb: float = DEFAULTS["max_memory_mb"]
    max_pixels: int = DEFAULTS["max_pixels"]
    max_image_side: int = DEFAULTS["max_image_side"]
    threads: int = DEFAULTS["threads"]

    @classmethod
    def from_dict(cls, values: Optional[Dict[str, Any]]) -> "ResourceLimits":
        merged = dict(DEFAULTS)
        for key, value in (values or {}).items():
            if key not in DEFAULTS:
                raise OperationError("invalid_argument", f"unknown resource limit {key!r}",
                                     {"allowed": sorted(DEFAULTS)})
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise OperationError("invalid_argument", f"resource limit {key} must be a finite number")
            if float(value) <= 0:
                raise OperationError("invalid_argument", f"resource limit {key} must be > 0")
            merged[key] = value
        if merged["threads"] != 1:
            raise OperationError("unsupported", "only threads=1 is supported in this release "
                                 "(pure Python; see RESOURCE_LIMITS.md)")
        return cls(
            max_steps=int(merged["max_steps"]),
            max_records=int(merged["max_records"]),
            max_wall_seconds=float(merged["max_wall_seconds"]),
            max_memory_mb=float(merged["max_memory_mb"]),
            max_pixels=int(merged["max_pixels"]),
            max_image_side=int(merged["max_image_side"]),
            threads=1,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def peak_memory_mb() -> Optional[float]:
    """Peak resident set size of this process in MiB, or None where the OS does not report it."""
    try:
        import resource  # POSIX only
    except ImportError:  # pragma: no cover - non-POSIX platforms
        return None
    kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux
    return round(kib / 1024.0, 2)


class Deadline:
    """Checks the wall-clock and memory budgets. Call ``check`` every few hundred steps."""

    def __init__(self, limits: ResourceLimits) -> None:
        self.limits = limits
        self.start = time.monotonic()

    def check(self, where: str = "") -> None:
        elapsed = time.monotonic() - self.start
        if elapsed > self.limits.max_wall_seconds:
            raise OperationError("resource_limit",
                                 f"wall-clock budget {self.limits.max_wall_seconds} s exceeded {where}",
                                 {"limit": "max_wall_seconds", "value": self.limits.max_wall_seconds,
                                  "elapsed_s": round(elapsed, 3)})
        mem = peak_memory_mb()
        if mem is not None and mem > self.limits.max_memory_mb:
            raise OperationError("resource_limit",
                                 f"peak memory {mem} MiB exceeded budget {self.limits.max_memory_mb} MiB {where}",
                                 {"limit": "max_memory_mb", "value": self.limits.max_memory_mb, "peak_mb": mem})
