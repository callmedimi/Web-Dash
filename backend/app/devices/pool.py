"""Device session factory, rate limiting, and circuit breaker (Target Architecture §3 & Step 3.2)."""
import random
import time
from collections import defaultdict
from typing import Dict, List, Optional, Any, Tuple, Callable
from sqlalchemy.orm import Session

from backend.app.devices.session import DeviceSession
from backend.app.devices.errors import DeviceError, ConnectTimeout, AuthFailed
import settings


class DeviceCircuitBreaker:
    """
    Per-device circuit breaker:
    - Tripped after 3 consecutive connection failures within 10 minutes (600s).
    - Remains open for 5 minutes (300s), during which requests return SKIPPED_UNREACHABLE.
    - Transitions to half-open after 5 minutes; successful connection resets breaker.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        window_seconds: float = 600.0,
        cooldown_seconds: float = 300.0,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock or time.time
        # Maps device_name -> list of failure timestamps
        self._failures: Dict[str, List[float]] = defaultdict(list)
        # Maps device_name -> cooldown until timestamp
        self._cooldown_until: Dict[str, float] = {}

    def is_available(self, device_name: str) -> Tuple[bool, Optional[str]]:
        """Check if device is available or currently tripped/cooling down."""
        now = self._clock()

        if device_name in self._cooldown_until:
            cooldown = self._cooldown_until[device_name]
            if now < cooldown:
                return False, "SKIPPED_UNREACHABLE"
            # Cooldown passed, allow one trial (half-open)
            del self._cooldown_until[device_name]
            self._failures[device_name] = []

        return True, None

    def record_failure(self, device_name: str) -> bool:
        """
        Record a connect failure. Returns True if circuit breaker has just tripped.
        """
        now = self._clock()
        # Clean failures older than window_seconds
        cutoff = now - self.window_seconds
        recent = [t for t in self._failures[device_name] if t >= cutoff]
        recent.append(now)
        self._failures[device_name] = recent

        if len(recent) >= self.failure_threshold:
            self._cooldown_until[device_name] = now + self.cooldown_seconds
            return True
        return False

    def record_success(self, device_name: str) -> None:
        """Reset failures and cooldown upon successful communication."""
        self._failures.pop(device_name, None)
        self._cooldown_until.pop(device_name, None)

    def reset_all(self) -> None:
        """Clear all breaker states (useful in test teardown)."""
        self._failures.clear()
        self._cooldown_until.clear()


# Global circuit breaker instance
device_breaker = DeviceCircuitBreaker()


class SiteRateLimiter:
    """Per-site concurrency limiter with configurable parallel connection caps."""

    def __init__(self, default_site_cap: int = 5):
        self.default_site_cap = default_site_cap
        self._site_active: Dict[str, int] = defaultdict(int)

    def can_acquire(self, site: Optional[str], cap: Optional[int] = None) -> bool:
        """Check if site has available connection capacity."""
        if not site:
            return True
        max_allowed = cap if cap is not None else self.default_site_cap
        return self._site_active[site] < max_allowed

    def acquire(self, site: Optional[str]) -> bool:
        """Increment active connection counter for site."""
        if not site:
            return True
        if not self.can_acquire(site):
            return False
        self._site_active[site] += 1
        return True

    def release(self, site: Optional[str]) -> None:
        """Decrement active connection counter for site."""
        if not site:
            return
        if self._site_active[site] > 0:
            self._site_active[site] -= 1


# Global site rate limiter
site_limiter = SiteRateLimiter()


def create_device_session(
    device_name: str,
    db_session: Optional[Session] = None,
    mgmt_ip: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    os_family: Optional[str] = None,
    jitter: bool = True,
    max_jitter_ms: int = 500,
    connect_factory: Optional[Callable] = None,
    **kwargs: Any,
) -> DeviceSession:
    """
    Factory creating a configured DeviceSession for a device.
    Resolves IP, OS family, and credentials from DB/Vault if not explicitly passed.
    Enforces circuit breaker check and login jitter.
    """
    # 1. Check circuit breaker
    available, reason = device_breaker.is_available(device_name)
    if not available:
        raise DeviceError(f"Device circuit breaker open ({reason})", device_name=device_name)

    # 2. Resolve device details from DB if available
    device_obj = None
    if db_session is not None:
        from backend.app.models.device import Device
        device_obj = db_session.query(Device).filter(Device.name == device_name).first()

    ip = mgmt_ip or (device_obj.mgmt_ip if device_obj else device_name)
    family = os_family or (device_obj.os_family if device_obj else "vrp8")

    # 3. Resolve credentials from vault if not provided
    resolved_user = username
    resolved_pass = password
    if (not resolved_user or not resolved_pass) and db_session is not None:
        try:
            from backend.app.security.vault import VaultService
            creds = VaultService.resolve_credentials(db_session, device_name=device_name)
            if creds:
                resolved_user = resolved_user or creds.get("username")
                resolved_pass = resolved_pass or creds.get("password")
        except Exception:
            pass

    resolved_user = resolved_user or getattr(settings, "router_username", "admin")
    resolved_pass = resolved_pass or getattr(settings, "router_password", "")

    # 4. Apply jittered start (0-500ms) to avoid login storms
    if jitter and max_jitter_ms > 0:
        sleep_sec = random.uniform(0.0, max_jitter_ms / 1000.0)
        time.sleep(sleep_sec)

    return DeviceSession(
        device_name=device_name,
        host=ip,
        username=resolved_user,
        password=resolved_pass,
        os_family=family,
        connect_factory=connect_factory,
        **kwargs,
    )
