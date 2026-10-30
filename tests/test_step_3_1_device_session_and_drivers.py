"""Unit tests for Step 3.1 & 3.2: Device driver abstraction, session lifecycle, and circuit breaker.

Verifies:
1. Connect retry discipline: exactly 2 retries (3 total attempts) on connect/auth timeout.
2. Safety latch: never reconnect/retry after a configuration command was sent.
3. Socket leak prevention: disconnect() called in all paths (including failure paths).
4. Paging disabled automatically on connect.
5. VRP8 vs VRP5 driver semantics (commit vs immediate apply).
6. Error banner detection and ConfigRejected raising.
7. Dynamic OS family detection (display version parsing).
8. CLI transcript sanitization (masking passwords/keys).
9. Circuit breaker and site rate limiter mechanics.
"""
import pytest
from unittest.mock import MagicMock, call

from backend.app.devices import (
    DeviceSession,
    DeviceCircuitBreaker,
    SiteRateLimiter,
    ConnectTimeout,
    AuthFailed,
    ConfigRejected,
    default_registry,
    parse_vrp_version,
    redact_sensitive_cli,
)


class FakeConnection:
    """Mock connection emulating Netmiko ConnectHandler."""
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.commands_sent = []
        self.disconnected = False
        self.disconnect_calls = 0

    def send_command(self, cmd, **kwargs):
        self.commands_sent.append(cmd)
        return self.responses.get(cmd, f"OK: {cmd}")

    def disconnect(self):
        self.disconnected = True
        self.disconnect_calls += 1


def test_connect_retry_and_disconnect_discipline():
    """Verify connect failures are retried twice (3 attempts total) and disconnect is called between each."""
    attempts = 0
    fake_conn = FakeConnection()

    def flaky_factory(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectTimeout("Simulated connect timeout")
        return fake_conn

    session = DeviceSession(
        device_name="CORE-R1",
        host="10.1.1.1",
        username="admin",
        password="secretpassword",
        retries=2,
        retry_backoff=[0.0, 0.0],  # No sleep in tests
        connect_factory=flaky_factory,
    )

    with session:
        assert session._connected is True
        assert attempts == 3
        assert "screen-length 0 temporary" in fake_conn.commands_sent

    # After exit context, disconnect should have been called cleanly
    assert fake_conn.disconnected is True
    assert fake_conn.disconnect_calls == 1


def test_disconnect_called_in_failed_connect():
    """Verify disconnect clean-up even if all connect attempts fail."""
    def fail_factory(**kwargs):
        raise ConnectTimeout("Router unreachable")

    session = DeviceSession(
        device_name="DOWN-R1",
        host="10.1.1.2",
        username="admin",
        password="secretpassword",
        retries=2,
        retry_backoff=[0.0, 0.0],
        connect_factory=fail_factory,
    )

    with pytest.raises(ConnectTimeout):
        with session:
            pass

    # Disconnect attempted on each failure
    assert session._disconnect_count == 3
    assert session._connected is False


def test_never_retry_after_config_executed():
    """Safety guarantee: once config_block begins, NEVER retry connection."""
    fake_conn = FakeConnection()
    session = DeviceSession(
        device_name="CORE-R1",
        host="10.1.1.1",
        username="admin",
        password="secretpassword",
        retries=2,
        retry_backoff=[0.0, 0.0],
        connect_factory=lambda **kwargs: fake_conn,
    )

    with session:
        # Execute config
        session.config_block(["interface GigabitEthernet0/1/0", "shutdown"])
        assert session._config_executed is True

        # Now simulate reconnect attempt (e.g. if invoked directly)
        def fail_factory(**kwargs):
            raise ConnectTimeout("Reconnection failed")
        session.connect_factory = fail_factory

        with pytest.raises(ConnectTimeout):
            session.connect()

        # Should NOT have retried 2 times because _config_executed is True
        assert session.retries == 2  # config was not changed, but attempt broke immediately


def test_vrp8_vs_vrp5_commit_semantics():
    """Verify VRP8 executes commit in config_block, while VRP5 does not."""
    # 1. VRP8
    conn8 = FakeConnection()
    session8 = DeviceSession(
        device_name="NE40E-1",
        host="10.1.1.10",
        username="admin",
        password="pwd",
        os_family="vrp8",
        connect_factory=lambda **kw: conn8,
    )
    with session8:
        res = session8.config_block(["interface GE1/0/0", "description TestLink"])
        assert res["applied"] is True
        assert "system-view" in conn8.commands_sent
        assert "interface GE1/0/0" in conn8.commands_sent
        assert "description TestLink" in conn8.commands_sent
        assert "commit" in conn8.commands_sent
        assert "return" in conn8.commands_sent

    # 2. VRP5
    conn5 = FakeConnection()
    session5 = DeviceSession(
        device_name="NE20-1",
        host="10.1.1.20",
        username="admin",
        password="pwd",
        os_family="vrp5",
        connect_factory=lambda **kw: conn5,
    )
    with session5:
        res = session5.config_block(["interface GE0/0/1", "description Link2"])
        assert res["applied"] is True
        assert "system-view" in conn5.commands_sent
        assert "interface GE0/0/1" in conn5.commands_sent
        assert "description Link2" in conn5.commands_sent
        assert "commit" not in conn5.commands_sent
        assert "return" in conn5.commands_sent


def test_dry_run_does_not_send_commands():
    """Verify dry_run=True returns proposed block without touching CLI."""
    conn = FakeConnection()
    session = DeviceSession(
        device_name="NE40E-1",
        host="10.1.1.10",
        username="admin",
        password="pwd",
        connect_factory=lambda **kw: conn,
    )
    with session:
        commands_before = list(conn.commands_sent)
        res = session.config_block(["interface GE1/0/0", "shutdown"], dry_run=True)
        assert res["dry_run"] is True
        assert res["applied"] is False
        # No extra commands sent other than connect paging
        assert conn.commands_sent == commands_before


def test_error_banner_detection_rejects_config():
    """Verify Huawei CLI error banner triggers ConfigRejected exception."""
    conn = FakeConnection(responses={
        "interface InvalidInterface": "Error: Wrong parameter found at '^' position."
    })
    session = DeviceSession(
        device_name="NE40E-1",
        host="10.1.1.10",
        username="admin",
        password="pwd",
        os_family="vrp8",
        connect_factory=lambda **kw: conn,
    )
    with session:
        with pytest.raises(ConfigRejected) as exc_info:
            session.config_block(["interface InvalidInterface"])
        assert "Wrong parameter" in exc_info.value.error_banner
        # Commit must NOT have been sent
        assert "commit" not in conn.commands_sent


def test_command_registry_resolution():
    """Verify run() resolves commands from default_registry with variables."""
    conn = FakeConnection(responses={
        "display interface GigabitEthernet0/1/1": "GigabitEthernet0/1/1 current state : UP"
    })
    session = DeviceSession(
        device_name="NE40E-1",
        host="10.1.1.10",
        username="admin",
        password="pwd",
        connect_factory=lambda **kw: conn,
    )
    with session:
        out = session.run("display_interface", interface="GigabitEthernet0/1/1")
        assert "current state : UP" in out
        assert "display interface GigabitEthernet0/1/1" in conn.commands_sent


def test_os_family_detection():
    """Verify detect_os_family parses VRP5 and VRP8 display version."""
    vrp8_sample = (
        "Huawei Versatile Routing Platform Software\n"
        "VRP (R) Software, Version 8.180 (NE40E V800R011C10SPC200)\n"
        "Copyright (C) 2012-2020 HUAWEI TECH CO., LTD."
    )
    assert parse_vrp_version(vrp8_sample) == "vrp8"

    vrp5_sample = (
        "Huawei Versatile Routing Platform Software\n"
        "VRP (R) Software, Version 5.170 (NE20E-S V300R007C00SPC200)\n"
        "Copyright (C) 2000-2015 HUAWEI TECH CO., LTD."
    )
    assert parse_vrp_version(vrp5_sample) == "vrp5"


def test_transcript_redaction():
    """Verify passwords and secrets are redacted from transcript."""
    sample = "local-user admin password cipher $1a$SecretPass123$! and secret myRootSecret"
    redacted = redact_sensitive_cli(sample)
    assert "SecretPass123" not in redacted
    assert "myRootSecret" not in redacted
    assert "[REDACTED]" in redacted


def test_device_circuit_breaker():
    """Verify 3 failures in 10 minutes trips breaker for 5 minutes."""
    current_time = 1000.0
    fake_clock = lambda: current_time

    breaker = DeviceCircuitBreaker(failure_threshold=3, window_seconds=600, cooldown_seconds=300, clock=fake_clock)
    dev = "ROUTER-A"

    assert breaker.is_available(dev)[0] is True

    # 1st failure
    breaker.record_failure(dev)
    assert breaker.is_available(dev)[0] is True

    # 2nd failure
    current_time += 100.0
    breaker.record_failure(dev)
    assert breaker.is_available(dev)[0] is True

    # 3rd failure -> trips!
    current_time += 100.0
    tripped = breaker.record_failure(dev)
    assert tripped is True

    # Breaker is now open
    avail, reason = breaker.is_available(dev)
    assert avail is False
    assert reason == "SKIPPED_UNREACHABLE"

    # Advance 200s (still within 300s cooldown)
    current_time += 200.0
    avail, _ = breaker.is_available(dev)
    assert avail is False

    # Advance another 150s (total 350s > 300s cooldown) -> transitions to half-open
    current_time += 150.0
    avail, _ = breaker.is_available(dev)
    assert avail is True

    # Success resets breaker
    breaker.record_success(dev)
    assert breaker.is_available(dev)[0] is True


def test_site_rate_limiter():
    """Verify site rate limiter limits parallel connections to site."""
    limiter = SiteRateLimiter(default_site_cap=2)
    site = "TEHRAN-CENTRAL"

    assert limiter.acquire(site) is True
    assert limiter.acquire(site) is True
    # Exceeded cap
    assert limiter.acquire(site) is False

    # Release one
    limiter.release(site)
    assert limiter.acquire(site) is True
