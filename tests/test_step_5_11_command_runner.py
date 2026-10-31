"""Comprehensive tests for Phase 5 Step 5.11: Command Runner (Read-only Allowlist & Regex Search)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.devices.registry import default_registry, DeviceCommand, CommandRegistry
from backend.app.devices.session import DeviceSession
from backend.app.services.command_runner import (
    CommandRunnerService,
    CommandRunnerSecurityError,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


# Sample CLI Outputs
MOCK_NTP_SYNCED_OUTPUT = """
clock status: synchronized
clock stratum: 2
reference clock ID: 10.255.255.10
nominal frequency: 100.0000 Hz
actual frequency: 100.0001 Hz
clock precision: 2^18
"""

MOCK_NTP_UNSYNCED_OUTPUT = """
clock status: unsynchronized
clock stratum: 16
reference clock ID: none
nominal frequency: 100.0000 Hz
actual frequency: 100.0000 Hz
clock precision: 2^18
"""

MOCK_BGP_PEER_OUTPUT = """
 BGP local router ID : 10.255.0.1
 Local AS number : 65001
 Total number of peers : 2                 Peers in established state : 2

  Peer            V    AS  MsgRcvd  MsgSent  OutQ  Up/Down       State  PrefRcv
  10.255.0.2      4 65001    12543    12540     0 05:22:18 Established     1250
  10.255.0.3      4 65001    12541    12539     0 05:22:15 Established     1180
"""


class MockDeviceSession(DeviceSession):
    """Mock device session returning predictable outputs without network SSH."""

    def __init__(self, device_name: str):
        super().__init__(device_name=device_name)
        self.device_name = device_name
        self._connected = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, command: str, timeout: int | None = None) -> str:
        if "ntp status" in command:
            if "TEH-AGG01" in self.device_name:
                return MOCK_NTP_SYNCED_OUTPUT
            else:
                return MOCK_NTP_UNSYNCED_OUTPUT
        if "bgp peer" in command:
            return MOCK_BGP_PEER_OUTPUT
        if "version" in command:
            return f"Huawei Versatile Routing Platform Software\nVRP (R) software, Version 8.180\n{self.device_name}"
        return f"Mock response for {command} on {self.device_name}"


@pytest.fixture
def test_db_session(tmp_path, monkeypatch):
    """Provide a fresh SQLite test session."""
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    db_file = tmp_path / "test_cmd_runner.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client with test configuration and logged-in user."""
    db_file = tmp_path / "test_app_cmd_runner.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_cmd", role="admin", password_hash="dummy_hash")
            s.add(admin)

            dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
            dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", role="PE", province="ISF", enabled=True)
            s.add_all([dev1, dev2])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_cmd",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_allowlist_commands_and_security_guard():
    """Verify allowlist only returns read_only=True commands; mutating commands raise SecurityError."""
    # 1. Allowlisted commands check
    commands = CommandRunnerService.list_allowlisted_commands()
    assert len(commands) > 0
    assert all(c["read_only"] is True for c in commands)
    assert any(c["name"] == "display_version" for c in commands)
    assert any(c["name"] == "display_ntp_status" for c in commands)

    # 2. Mutating command rejected by security guard
    with pytest.raises(CommandRunnerSecurityError) as exc_info:
        CommandRunnerService.validate_command("commit")
    assert "NOT read-only" in str(exc_info.value)

    # 3. Non-existent command rejected
    with pytest.raises(KeyError):
        CommandRunnerService.validate_command("non_existent_command_xyz")


def test_parameterized_command_template_formatting():
    """Verify template variable interpolation for commands with parameters."""
    cmd = default_registry.get("display_interface")
    assert cmd.read_only is True

    rendered_vrp8 = cmd.format("vrp8", interface="GigabitEthernet0/1/0")
    assert rendered_vrp8 == "display interface GigabitEthernet0/1/0"

    routing_cmd = default_registry.get("display_ip_routing_table_vpn")
    rendered_routing = routing_cmd.format("vrp8", vrf="INTERNET_VRF", prefix="10.100.0.0")
    assert rendered_routing == "display ip routing-table vpn-instance INTERNET_VRF 10.100.0.0"


def test_multi_device_execution_with_mock_sessions(test_db_session):
    """Verify parallel multi-device execution and per-device output collection."""
    dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", enabled=True)
    test_db_session.add_all([dev1, dev2])
    test_db_session.commit()

    def mock_factory(dev: Device) -> DeviceSession:
        return MockDeviceSession(dev.name)

    res = CommandRunnerService.execute_on_devices(
        db_session=test_db_session,
        command_name="display_ntp_status",
        target_devices=["TEH-AGG01", "ISF-PE01"],
        session_factory=mock_factory,
    )

    assert res["command"] == "display_ntp_status"
    assert res["total_devices"] == 2
    assert res["succeeded"] == 2
    assert res["failed"] == 0
    assert len(res["results"]) == 2

    teh_out = next(r for r in res["results"] if r["device_name"] == "TEH-AGG01")
    assert "clock status: synchronized" in teh_out["output"]

    isf_out = next(r for r in res["results"] if r["device_name"] == "ISF-PE01")
    assert "clock status: unsynchronized" in isf_out["output"]


def test_grep_and_regex_search_across_outputs():
    """Verify substring and regex search across multi-device output strings."""
    results = [
        {"device_name": "TEH-AGG01", "device_id": 1, "output": MOCK_NTP_SYNCED_OUTPUT},
        {"device_name": "ISF-PE01", "device_id": 2, "output": MOCK_NTP_UNSYNCED_OUTPUT},
        {"device_name": "SHZ-PE01", "device_id": 3, "output": MOCK_BGP_PEER_OUTPUT},
    ]

    # 1. Search for 'unsynchronized'
    search_sync = CommandRunnerService.search_outputs(results, pattern="unsynchronized")
    assert search_sync["matched_devices_count"] == 1
    assert search_sync["matches"][0]["device_name"] == "ISF-PE01"
    assert any("unsynchronized" in line["line"] for line in search_sync["matches"][0]["lines"])

    # 2. Search regex for stratum numbers
    search_regex = CommandRunnerService.search_outputs(
        results, pattern=r"clock stratum:\s*(\d+)", is_regex=True
    )
    assert search_regex["matched_devices_count"] == 2
    assert search_regex["total_matches_count"] == 2

    # 3. Invalid regex handling
    with pytest.raises(ValueError) as val_err:
        CommandRunnerService.search_outputs(results, pattern=r"(unclosed_bracket", is_regex=True)
    assert "Invalid regular expression" in str(val_err.value)


def test_jinja2_config_template_rendering():
    """Verify safe Jinja2 config template rendering for change plan preview."""
    template = """
    # Proposed change for {{ interface_name }}
    interface {{ interface_name }}
     description {{ description }}
     ip address {{ ip_address }} {{ subnet_mask }}
    #
    """
    vars_dict = {
        "interface_name": "GigabitEthernet0/1/0",
        "description": "Uplink-To-Core",
        "ip_address": "10.0.0.1",
        "subnet_mask": "255.255.255.252",
    }

    res = CommandRunnerService.render_config_template(template, vars_dict)
    assert res["status"] == "success"
    assert "interface GigabitEthernet0/1/0" in res["rendered_config"]
    assert "description Uplink-To-Core" in res["rendered_config"]
    assert res["direct_execution_blocked"] is True

    # Malformed template test
    bad_res = CommandRunnerService.render_config_template("interface {{ bad syntax", {})
    assert bad_res["status"] == "error"
    assert bad_res["error"] == "TEMPLATE_SYNTAX_ERROR"


def test_csv_export_multi_device_results():
    """Verify exporting multi-device outputs and search matches to CSV."""
    results = [
        {"device_name": "TEH-AGG01", "status": "success", "duration_ms": 120, "error": None, "output": MOCK_NTP_SYNCED_OUTPUT},
        {"device_name": "ISF-PE01", "status": "success", "duration_ms": 145, "error": None, "output": MOCK_NTP_UNSYNCED_OUTPUT},
    ]
    search_matches = CommandRunnerService.search_outputs(results, pattern="unsynchronized")

    csv_data = CommandRunnerService.export_results_csv(results, search_matches=search_matches)
    assert "Device Name,Status,Duration (ms),Error,Match Count,Matched Lines Snippet,Output" in csv_data
    assert "ISF-PE01,success,145,,1" in csv_data
    assert "TEH-AGG01,success,120,,0" in csv_data


def test_catalog_feature_command_runner(test_db_session):
    """Verify CommandRunnerFeature execution via catalog registry."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("command_runner")
    assert feature is not None

    def mock_factory(d: Device) -> DeviceSession:
        return MockDeviceSession(d.name)

    # 1. Action: list
    ctx_list = FeatureContext(db_session=test_db_session, params={"action": "list"})
    res_list = feature.run(ctx_list)
    assert res_list["status"] == "success"
    assert res_list["count"] > 0

    # 2. Action: run
    ctx_run = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "run",
            "command": "display_ntp_status",
            "target_devices": ["TEH-AGG01"],
            "_session_factory": mock_factory,
        },
    )
    res_run = feature.run(ctx_run)
    assert res_run["status"] == "success"
    assert res_run["data"]["succeeded"] == 1

    # 3. Action: search
    ctx_search = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "search",
            "pattern": "synchronized",
            "results": res_run["data"]["results"],
        },
    )
    res_search = feature.run(ctx_search)
    assert res_search["status"] == "success"
    assert res_search["data"]["matched_devices_count"] == 1

    # 4. Action: render_template
    ctx_tpl = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "render_template",
            "template_content": "sysname {{ hostname }}",
            "variables": {"hostname": "ROUTER-NEW"},
        },
    )
    res_tpl = feature.run(ctx_tpl)
    assert res_tpl["status"] == "success"
    assert res_tpl["rendered_config"] == "sysname ROUTER-NEW"

    # 5. Action: export
    ctx_exp = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "export",
            "results": res_run["data"]["results"],
        },
    )
    res_exp = feature.run(ctx_exp)
    assert res_exp["status"] == "success"
    assert "TEH-AGG01" in res_exp["csv_data"]


def test_command_runner_rest_api(app_client):
    """Verify REST API endpoints /api/v1/commands/*."""
    # 1. Allowlist
    list_res = app_client.get("/api/v1/commands/allowlist")
    assert list_res.status_code == 200
    l_data = list_res.get_json()
    assert l_data["count"] > 0
    assert any(c["name"] == "display_version" for c in l_data["commands"])

    # 2. Search
    search_payload = {
        "results": [
            {"device_name": "TEH-AGG01", "output": MOCK_NTP_SYNCED_OUTPUT},
            {"device_name": "ISF-PE01", "output": MOCK_NTP_UNSYNCED_OUTPUT},
        ],
        "pattern": "synchronized",
    }
    s_res = app_client.post("/api/v1/commands/search", json=search_payload)
    assert s_res.status_code == 200
    s_data = s_res.get_json()
    assert s_data["data"]["matched_devices_count"] >= 1

    # 3. Render Template
    tpl_payload = {
        "template_content": "interface {{ iface }}\n shutdown",
        "variables": {"iface": "GigabitEthernet0/1/0"},
    }
    t_res = app_client.post("/api/v1/commands/render-template", json=tpl_payload)
    assert t_res.status_code == 200
    t_data = t_res.get_json()
    assert "interface GigabitEthernet0/1/0" in t_data["rendered_config"]
    assert t_data["direct_execution_blocked"] is True

    # 4. Export
    exp_res = app_client.post(
        "/api/v1/commands/export",
        json={"results": search_payload["results"]},
    )
    assert exp_res.status_code == 200
    assert "text/csv" in exp_res.headers.get("Content-Type", "")
    assert b"TEH-AGG01" in exp_res.data
