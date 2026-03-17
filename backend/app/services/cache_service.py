"""In-memory TTL cache for reconciliation results."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class InMemoryCache:
    """Thread-compatible in-memory store with per-entry TTL."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def _evict_expired(self) -> None:
        """Remove all entries whose TTL has elapsed."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if v.expires_at <= now]
        for key in expired:
            del self._store[key]

    def get(self, key: str) -> Any | None:
        """Return cached value or None if missing / expired."""
        self._evict_expired()
        entry = self._store.get(key)
        return entry.value if entry else None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store value under key with a TTL in seconds."""
        self._evict_expired()
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl_seconds,
        )

    def delete(self, key: str) -> None:
        """Explicitly remove a key."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Flush all entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Number of non-expired entries currently cached."""
        self._evict_expired()
        return len(self._store)


def build_cache_key(patient_context: dict, sources: list[dict]) -> str:
    """
    Deterministic cache key from patient context + source list.

    Uses SHA-256 of a canonical JSON representation.
    """
    payload = json.dumps(
        {"patient": patient_context, "sources": sources},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# Module-level singleton — shared across all requests in the process
_cache_instance: InMemoryCache | None = None


def get_cache() -> InMemoryCache:
    """Return the application-wide cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache()
    return _cache_instance
