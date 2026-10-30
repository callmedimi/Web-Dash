"""In-process TTL cache with stale-while-error (Target Architecture §3 & Step 3.4)."""
import time
from typing import Dict, Any, Optional, Tuple, NamedTuple


class CacheEntry(NamedTuple):
    value: Any
    expires_at: float
    stale_until: float


class TelemetryCache:
    """
    In-memory cache supporting time-to-live and stale-while-error serving.
    Defaults:
    - host list: 5 min TTL, 10 min stale
    - problems: 15s TTL, 5 min stale
    - latest values: 30s TTL, 5 min stale
    - series: 60s TTL, 10 min stale
    """

    def __init__(self):
        self._entries: Dict[str, CacheEntry] = {}

    def get(self, key: str, allow_stale: bool = True) -> Tuple[Optional[Any], bool]:
        """
        Retrieve value by key.
        Returns:
            (value, is_stale)
            If not found or fully expired beyond stale window: (None, False)
        """
        now = time.time()
        entry = self._entries.get(key)
        if not entry:
            return None, False

        # Fresh hit
        if now < entry.expires_at:
            return entry.value, False

        # Stale hit (if allowed and within stale window)
        if allow_stale and now < entry.stale_until:
            return entry.value, True

        # Evict fully expired
        self._entries.pop(key, None)
        return None, False

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float = 60.0,
        stale_window_seconds: float = 600.0,
    ) -> None:
        """Store value with specific TTL and stale grace window."""
        now = time.time()
        self._entries[key] = CacheEntry(
            value=value,
            expires_at=now + ttl_seconds,
            stale_until=now + ttl_seconds + stale_window_seconds,
        )

    def invalidate(self, key: str) -> None:
        """Explicitly clear cache entry."""
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Clear entire cache."""
        self._entries.clear()


# Global telemetry cache singleton
telemetry_cache = TelemetryCache()
