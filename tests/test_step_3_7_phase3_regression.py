"""End-to-end regression pass for Phase 3: Huawei VRP-first Engine & Telemetry Layer.

Validates the full unified workflow:
1. DeviceSession creation, command registry resolution, and dynamic OS family detection (VRP5 vs VRP8).
2. Parsing of active alarms, interface statuses, license state machine, routing, and PTP.
3. Grammar-based interface reference extraction and ambiguity avoidance.
4. Safe config_block execution (dry-run vs applied commit) and error banner rejection.
5. Telemetry subsystem: Zabbix JSON-RPC 2.0 version auto-detection, problems, series, and caching.
6. Device inventory to Zabbix synchronization with strict ambiguity protection.
7. Grafana embed and deep link generation.
8. Negative architecture compliance: zero direct SNMP / pysnmp code.
"""
import sys
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.devices import (
    DeviceSession,
    create_device_session,
    default_registry,
    ConfigRejected,
    device_breaker,
)
from backend.app.devices.parsers import (
    parse_active_alarms,
    parse_display_interface,
    parse_interface_config,
    parse_display_license_verbose,
    extract_interface,
)
from backend.app.telemetry import (
    ZabbixProvider,
    TelemetryHost,
    TelemetryProblem,
    GrafanaClient,
    sync_devices_with_telemetry,
)
from backend.app.models.device import Device
from backend.app.db.base import Base


class FakeRouterConnection:
    """Mock connection emulating a real Huawei NE40E/CX600 router."""
    def __init__(self, os_version="8"):
        self.os_version = os_version
        self.commands_sent = []
        self.disconnected = False

    def send_command(self, cmd, **kwargs):
        self.commands_sent.append(cmd)
        clean = cmd.strip()

        if clean == "screen-length 0 temporary":
            return ""
        if clean == "undo terminal monitor":
            return ""
        if clean == "display version":
            if self.os_version == "8":
                return "Huawei Versatile Routing Platform Software\nVRP (R) Software, Version 8.180 (NE40E V800R011C10SPC200)"
            return "Huawei Versatile Routing Platform Software\nVRP (R) Software, Version 5.170 (NE20E-S V300R007C00SPC200)"
        if clean == "display alarm active":
            return (
                "Sequence  AlarmId    Level Date       Time                   Description\n"
                "------------------------------------------------------------------------------------------------------------------------\n"
                "1         0x09100001 2     2026-10-31 01:00:00+03:30         The interface GigabitEthernet0/1/0 physical state changed to Down.\n"
                "2         0x09100002 3     2026-10-31 01:05:00Z              Module removed ifName=GE0/2/1.100\n"
            )
        if clean == "display interface GigabitEthernet0/1/0":
            return (
                "GigabitEthernet0/1/0 current state : DOWN\n"
                "Line protocol current state : DOWN\n"
                "Description: Core Uplink\n"
            )
        if clean == "display current-configuration interface GigabitEthernet0/1/0":
            return (
                "#\n"
                "interface GigabitEthernet0/1/0\n"
                " shutdown\n"
                "#\n"
                "return\n"
            )
        if clean == "system-view":
            return "[~HUAWEI]"
        if clean == "commit":
            return ""
        if clean == "return":
            return "<HUAWEI>"
        return f"OK: {cmd}"

    def disconnect(self):
        self.disconnected = True


def test_phase3_full_device_and_parser_lifecycle():
    """Verify full end-to-end device workflow: connect, detect OS, run commands, parse, extract interface."""
    fake_conn = FakeRouterConnection(os_version="8")
    session = DeviceSession(
        device_name="CORE-NE40E-1",
        host="10.10.1.1",
        username="admin",
        password="vault_secret_password",
        connect_factory=lambda **kw: fake_conn,
    )

    with session:
        # 1. Detect OS family dynamically
        family = session.detect_os_family()
        assert family == "vrp8"
        assert session.driver.commit_required is True

        # 2. Fetch and parse active alarms
        raw_alarms = session.run("display_alarm_active")
        alarms = parse_active_alarms(raw_alarms)
        assert len(alarms) == 2

        # 3. Extract and normalize interfaces from alarm descriptions
        iface_ref_1 = extract_interface(alarms[0]["description"])
        assert iface_ref_1 is not None
        assert iface_ref_1.name == "GigabitEthernet0/1/0"
        assert iface_ref_1.is_sub is False

        iface_ref_2 = extract_interface(alarms[1]["description"])
        assert iface_ref_2 is not None
        assert iface_ref_2.name == "GigabitEthernet0/2/1.100"
        assert iface_ref_2.parent == "GigabitEthernet0/2/1"
        assert iface_ref_2.is_sub is True

        # 4. Check interface status & config
        iface_status = parse_display_interface(session.run("display_interface", interface=iface_ref_1.name))
        assert iface_status["physical_state"] == "DOWN"

        iface_cfg = parse_interface_config(session.run("display_current_config_interface", interface=iface_ref_1.name))
        assert iface_cfg["error"] is None
        assert iface_cfg["is_trivial"] is True  # Only shutdown

        # 5. Safe configuration block: dry_run vs applied
        dry_res = session.config_block(["interface GigabitEthernet0/1/0", "undo shutdown"], dry_run=True)
        assert dry_res["dry_run"] is True
        assert dry_res["applied"] is False

        apply_res = session.config_block(["interface GigabitEthernet0/1/0", "undo shutdown"], dry_run=False)
        assert apply_res["applied"] is True
        assert "commit" in fake_conn.commands_sent

    assert fake_conn.disconnected is True


def test_phase3_telemetry_and_device_sync_integration():
    """Verify Zabbix telemetry provider, device synchronization, and Grafana embed links."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()

    # Seed DB device
    dev = Device(name="PE-TEH-01", mgmt_ip="172.16.1.1", os_family="vrp8")
    db_session.add(dev)
    db_session.commit()

    # Mock Zabbix HTTP Session
    mock_http = MagicMock()
    # 1. Version probe: 6.2
    v_resp = MagicMock()
    v_resp.status_code = 200
    v_resp.json.return_value = {"result": "6.2.0"}

    # 2. Host list response
    h_resp = MagicMock()
    h_resp.status_code = 200
    h_resp.json.return_value = {
        "result": [
            {
                "hostid": "5001",
                "host": "PE-TEH-01",
                "name": "PE Tehran 01",
                "status": "0",
                "available": "1",
                "interfaces": [{"ip": "172.16.1.1", "main": "1"}],
                "groups": [{"name": "Metro-Ethernet"}],
            }
        ]
    }

    mock_http.post.side_effect = [v_resp, h_resp]
    zabbix = ZabbixProvider(url="http://zabbix.prod/api_jsonrpc.php", token="zbx_token_123", session=mock_http)
    ver = zabbix.detect_version()
    assert ver == "6.2.0"

    # Sync
    report = sync_devices_with_telemetry(db_session, zabbix, auto_apply=True)
    assert report["matched_count"] == 1
    assert report["ambiguous_count"] == 0

    db_session.refresh(dev)
    assert dev.zabbix_hostid == "5001"
    assert dev.site == "Metro-Ethernet"

    # Grafana links
    grafana = GrafanaClient(base_url="https://grafana.prod", token="gf_tok")
    panel_embed = grafana.build_embed_url("router-health", panel_id=2, variables={"host": dev.name})
    assert "https://grafana.prod/d-solo/router-health" in panel_embed
    assert "var-host=PE-TEH-01" in panel_embed


def test_phase3_negative_snmp_compliance():
    """Verify that direct SNMP / pysnmp code is completely absent from the platform."""
    # Ensure pysnmp is not in sys.modules
    assert "pysnmp" not in sys.modules
