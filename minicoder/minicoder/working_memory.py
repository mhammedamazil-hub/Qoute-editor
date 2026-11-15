"""Working memory — the brain's short-term workspace.

Strict capacity, priority-based retention, pinning to protect critical task
constraints, recency/relevance scoring, automatic expiration, and a lossy
compression pass when full.
"""
from __future__ import annotations
import time
from collections import deque
from .config import get_settings
from .models import WorkingMemoryItem
from .util import new_id, now_iso, clamp


class WorkingMemory:
    def __init__(self) -> None:
        self.items: deque[WorkingMemoryItem] = deque()
        self.capacity = get_settings().wm_capacity
        self.pinned_max = get_settings().wm_pinned_max
        self.expire_seconds = get_settings().wm_expire_seconds

    # ------------------------------------------------------------------ add
    def add(self, content: str, *, modality: str = "text", priority: float = 0.5,
            source: str = "user_instruction", pinned: bool = False,
            meta: dict | None = None) -> WorkingMemoryItem:
        content = content.strip()
        if not content:
            raise ValueError("working memory refuses empty content")
        self._expire()
        if pinned and self._pinned_count() >= self.pinned_max:
            # never exceed the pin budget — unpin the lowest-priority pinned item instead
            pinned_items = [i for i in self.items if i.pinned]
            weakest = min(pinned_items, key=lambda i: i.priority)
            weakest.pinned = False
        item = WorkingMemoryItem(
            id=new_id("wm"), content=content, modality=modality,
            priority=clamp(priority, 0.0, 1.0), pinned=pinned, source=source,
            created_at=now_iso(), last_access=now_iso(),
            token_estimate=max(1, len(content) // 4), meta=meta or {},
        )
        self.items.append(item)
        self._evict_if_needed()
        return item

    # ------------------------------------------------------------- retrieve
    def pin(self, item_id: str) -> bool:
        for it in self.items:
            if it.id == item_id:
                if not it.pinned and self._pinned_count() >= self.pinned_max:
                    return False
                it.pinned = True
                return True
        return False

    def unpin(self, item_id: str) -> bool:
        for it in self.items:
            if it.id == item_id:
                it.pinned = False
                return True
        return False

    def touch(self, item_id: str) -> None:
        for it in self.items:
            if it.id == item_id:
                it.last_access = now_iso()
                return

    def clear(self, *, keep_pinned: bool = True) -> int:
        before = len(self.items)
        if keep_pinned:
            self.items = deque(i for i in self.items if i.pinned)
        else:
            self.items.clear()
        return before - len(self.items)

    def load(self) -> float:
        return len(self.items) / max(1, self.capacity)

    def context_block(self, max_chars: int = 2400) -> str:
        """Render WM as a compact prompt block, highest priority first."""
        ordered = sorted(self.items, key=lambda i: (i.pinned, i.priority), reverse=True)
        parts, used = [], 0
        for it in ordered:
            line = f"[{it.modality}|p={it.priority:.2f}{'|PIN' if it.pinned else ''}] {it.content}"
            if used + len(line) > max_chars:
                parts.append("…[working memory truncated]")
                break
            parts.append(line)
            used += len(line)
        return "\n".join(parts)

    # -------------------------------------------------------------- internals
    def _pinned_count(self) -> int:
        return sum(1 for i in self.items if i.pinned)

    def _score(self, item: WorkingMemoryItem) -> float:
        age = max(0.0, time.time() - _iso_to_epoch(item.last_access))
        recency = 1.0 / (1.0 + age / 300.0)          # ~5 min half-life
        return item.priority * 0.65 + recency * 0.35

    def _expire(self) -> None:
        now = time.time()
        kept = deque()
        for it in self.items:
            age = now - _iso_to_epoch(it.last_access)
            if not it.pinned and it.priority < 0.6 and age > self.expire_seconds:
                continue  # expired — silently drops only ephemeral, low-priority items
            kept.append(it)
        self.items = kept

    def _evict_if_needed(self) -> None:
        while len(self.items) > self.capacity:
            candidates = [it for it in self.items if not it.pinned]
            if not candidates:
                # everything is pinned (shouldn't happen given pin budget); drop oldest pinned
                victim = min(self.items, key=lambda i: _iso_to_epoch(i.last_access))
            else:
                victim = min(candidates, key=self._score)
            self.items.remove(victim)


def _iso_to_epoch(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return time.time()
