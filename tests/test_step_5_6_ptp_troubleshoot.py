"""Comprehensive tests for Phase 5 Step 5.6: PTP & Sync Troubleshooting."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.services.ptp import PtpTroubleshootService
from ptp_troubleshoot_service import (
    parse_display_ptp_all,
    parse_display_ptp_interface,
    parse_display_clock_source,
    parse_display_interface,
    parse_display_alarm_active,
    parse_lldp_neighbor_brief,
    evaluate_hop_health,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


MOCK_PTP_ALL_HOP0 = """
  PTP state           : enabled
  Domain value        : 24
  Device type         : oc
  Local clock ID      : 001882-fffe-000001
  Time lock success   : yes
  PTP profile         : ITU-T G.8275.1
  Grand clock ID      : 001882-fffe-000099
  Receive number      : GigabitEthernet0/1/0
  Parent clock ID     : 001882-fffe-000002
  Parent portnumber   : 1
  Step removed        : 2
  Clock class         : 6
  Time Source         : ptp
  Realtime(T2-T1)     : 42.5
  Pathdelay           : 1200.0
  Time offset         : 42.5
"""

MOCK_PTP_ALL_HOP1 = """
  PTP state           : enabled
  Domain value        : 24
  Device type         : bc
  Local clock ID      : 001882-fffe-000002
  Time lock success   : yes
  PTP profile         : ITU-T G.8275.1
  Grand clock ID      : 001882-fffe-000099
  Receive number      : GigabitEthernet0/2/0
  Parent clock ID     : 001882-fffe-000099
  Step removed        : 1
  Clock class         : 6
  Time Source         : ptp
  Realtime(T2-T1)     : 15.0
  Pathdelay           : 850.0
  Time offset         : 15.0
"""

MOCK_PTP_ALL_FAULTY = """
  PTP state           : enabled
  Domain value        : 24
  Device type         : bc
  Local clock ID      : 001882-fffe-000002
  Time lock success   : no
  PTP profile         : ITU-T G.8275.1
  Grand clock ID      : 001882-fffe-000002
  Receive number      : 
  Step removed        : 0
  Clock class         : 248
  Time Source         : free-running
  Realtime(T2-T1)     : 1250.0
  Pathdelay           : 0.0
  Time offset         : 1250.0
"""

MOCK_CLOCK_SOURCE_LOCKED = """
System trace source State: lock mode
Current system trace source: ptp
Frequency lock success: yes
Source   Pri    In-SSM  Out-SSM  State     Ref
ptp      1/---  prc     --       normal    yes
"""

MOCK_CLOCK_SOURCE_UNLOCKED = """
System trace source State: free-run
Current system trace source: none
Frequency lock success: no
Source   Pri    In-SSM  Out-SSM  State     Ref
local    255/--- dnu    --       normal    yes
"""

MOCK_PTP_INTERFACE = """
  Interface name        : GigabitEthernet0/1/0
  Port state            : slave
  Path delay            : 1200.0
  Realtime(T2-T1)       : 42.5
  Time offset           : 42.5
  Port asymmetry delay  : 0
"""

MOCK_TRANSCEIVER_VERBOSE = """GigabitEthernet0/1/0 current state : UP
Line protocol current state : UP
Description: PTP_TRUNK
Transceiver Identifier : SFP
Rx Power: -12.45dBm, Working range: [-14.400, 0.499]dBm
Tx Power: -4.50dBm, Working range: [-8.198, 0.499]dBm
"""

MOCK_LLDP_HOP0 = """
Local Intf             Neighbor Dev                     Neighbor Intf             Exptime(s)
GigabitEthernet0/1/0   TEH-AGG01                        GigabitEthernet0/3/0      105
"""


class MockPtpTraceSession:
    """Mock session switching responses based on active target router or fault injection."""

    def __init__(self, inject_fault_at_hop1: bool = False):
        self.inject_fault_at_hop1 = inject_fault_at_hop1
        self.current_router = "TEH-PE01"
        self.commands_sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if "display ptp all" in cmd:
            if self.current_router == "TEH-AGG01":
                return MOCK_PTP_ALL_FAULTY if self.inject_fault_at_hop1 else MOCK_PTP_ALL_HOP1
            return MOCK_PTP_ALL_HOP0

        if "display clock source" in cmd:
            if self.current_router == "TEH-AGG01" and self.inject_fault_at_hop1:
                return MOCK_CLOCK_SOURCE_UNLOCKED
            return MOCK_CLOCK_SOURCE_LOCKED

        if "display ptp interface" in cmd:
            return MOCK_PTP_INTERFACE

        if "display interface" in cmd:
            return MOCK_TRANSCEIVER_VERBOSE

        if "display alarm active" in cmd:
            return "No active alarm"

        if "display lldp neighbor" in cmd:
            if self.current_router == "TEH-PE01":
                # Advance simulated connection to Hop 1
                self.current_router = "TEH-AGG01"
                return MOCK_LLDP_HOP0
            return ""

        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_ptp.db"
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
    db_file = tmp_path / "test_app_ptp.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_ptp", role="admin", password_hash="dummy_hash")
            s.add(admin)
            dev1 = Device(
                name="TEH-PE01",
                mgmt_ip="10.10.1.1",
                vendor="huawei",
                os_family="vrp8",
                role="PE",
                province="TH",
                site="TEH-PE01",
                enabled=True,
            )
            dev2 = Device(
                name="TEH-AGG01",
                mgmt_ip="10.10.2.1",
                vendor="huawei",
                os_family="vrp8",
                role="AGG",
                province="TH",
                site="TEH-AGG01",
                enabled=True,
            )
            s.add_all([dev1, dev2])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_ptp",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_ptp_parsers():
    """Verify parsing of PTP status, interface, clock source, and optics."""
    # 1. PTP All
    ptp = parse_display_ptp_all(MOCK_PTP_ALL_HOP0)
    assert ptp["ptp_state"] == "enabled"
    assert ptp["domain_value"] == 24
    assert ptp["receive_number"] == "GigabitEthernet0/1/0"
    assert ptp["clock_class"] == 6
    assert ptp["step_removed"] == 2
    assert ptp["realtime_t2_t1"] == 42.5

    # 2. PTP Interface
    ptp_iface = parse_display_ptp_interface(MOCK_PTP_INTERFACE)
    assert ptp_iface["interface_name"] == "GigabitEthernet0/1/0"
    assert ptp_iface["port_state"] == "slave"
    assert ptp_iface["realtime_t2_t1"] == 42.5

    # 3. Clock Source Locked
    clk_locked = parse_display_clock_source(MOCK_CLOCK_SOURCE_LOCKED)
    assert clk_locked["trace_source_state"] == "lock mode"
    assert clk_locked["current_trace_source"] == "ptp"

    # 4. Clock Source Unlocked
    clk_unlocked = parse_display_clock_source(MOCK_CLOCK_SOURCE_UNLOCKED)
    assert clk_unlocked["trace_source_state"] == "free-run"

    # 5. Transceiver Optics
    optics = parse_display_interface(MOCK_TRANSCEIVER_VERBOSE)
    assert optics["rx_power_dbm"] == -12.45
    assert optics["tx_power_dbm"] == -4.50

    # 6. LLDP Neighbor
    lldp = parse_lldp_neighbor_brief(MOCK_LLDP_HOP0, target_local_iface="GigabitEthernet0/1/0")
    assert len(lldp) == 1
    assert lldp[0]["neighbor_device"] == "TEH-AGG01"


def test_router_and_neighbor_resolution_db(test_db_session):
    """Verify DB-backed router identification and LLDP neighbor resolution."""
    dev1 = Device(name="TEH-PE01", mgmt_ip="10.10.1.1", site="TEH-PE", lsr_id="10.255.1.1", enabled=True)
    dev2 = Device(name="TEH-AGG01", mgmt_ip="10.10.2.1", site="TEH-AGG", lsr_id="10.255.2.1", enabled=True)
    test_db_session.add_all([dev1, dev2])
    test_db_session.commit()

    # 1. Resolve router by Name
    r1 = PtpTroubleshootService.resolve_router(test_db_session, "TEH-PE01")
    assert r1 is not None
    assert r1["host"] == "10.10.1.1"

    # 2. Resolve router by IP
    r2 = PtpTroubleshootService.resolve_router(test_db_session, "10.10.2.1")
    assert r2 is not None
    assert r2["name"] == "TEH-AGG01"

    # 3. Resolve router by Site Code
    r3 = PtpTroubleshootService.resolve_router(test_db_session, "TEH-PE")
    assert r3 is not None
    assert r3["name"] == "TEH-PE01"

    # 4. Resolve neighbor IP from LLDP device name
    n_ip = PtpTroubleshootService.resolve_neighbor_ip(test_db_session, "TEH-AGG01.corp")
    assert n_ip == "10.10.2.1"


def test_run_traceback_healthy_chain(test_db_session):
    """Verify healthy upstream PTP clock traceback with topology graph and verdict."""
    dev1 = Device(name="TEH-PE01", mgmt_ip="10.10.1.1", role="PE", enabled=True)
    dev2 = Device(name="TEH-AGG01", mgmt_ip="10.10.2.1", role="AGG", enabled=True)
    test_db_session.add_all([dev1, dev2])
    test_db_session.commit()

    mock_sess = MockPtpTraceSession(inject_fault_at_hop1=False)

    report = PtpTroubleshootService.run_traceback(
        db_session=test_db_session,
        target_identifier="TEH-PE01",
        max_hops=5,
        session_mock=mock_sess,
    )

    assert report["overall_status"] == "HEALTHY"
    assert "healthy and in-sync" in report["text_verdict"]
    assert report["hop_count"] == 2

    # Verify Topology Graph
    graph = report["topology_graph"]
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["nodes"][0]["name"] == "TEH-PE01"
    assert graph["nodes"][0]["status"] == "HEALTHY"
    assert graph["nodes"][1]["name"] == "TEH-AGG01"
    assert graph["nodes"][1]["status"] == "HEALTHY"
    assert graph["edges"][0]["state"] == "HEALTHY"
    assert graph["edges"][0]["port"] == "GigabitEthernet0/1/0"


def test_run_traceback_faulty_clock_loss(test_db_session):
    """Verify fault detection at Hop 1, verdict generation, and team demarcation."""
    dev1 = Device(name="TEH-PE01", mgmt_ip="10.10.1.1", role="PE", enabled=True)
    dev2 = Device(name="TEH-AGG01", mgmt_ip="10.10.2.1", role="AGG", enabled=True)
    test_db_session.add_all([dev1, dev2])
    test_db_session.commit()

    # Fault injected at Hop 1 (free-run unlocked source)
    mock_sess = MockPtpTraceSession(inject_fault_at_hop1=True)

    report = PtpTroubleshootService.run_traceback(
        db_session=test_db_session,
        target_identifier="TEH-PE01",
        max_hops=5,
        session_mock=mock_sess,
    )

    assert report["overall_status"] == "CRITICAL"
    assert "Hop 1 (TEH-AGG01)" in report["text_verdict"]
    assert "Best clock lost at hop 1" in report["text_verdict"]

    demarcation = report["demarcation"]
    assert "IP Team" in demarcation["responsible_team"]

    # Verify faulty node in topology graph
    graph = report["topology_graph"]
    assert graph["nodes"][1]["status"] == "CRITICAL"
    assert graph["nodes"][1]["is_faulty"] is True


def test_ptp_feature_run(test_db_session):
    """Verify PtpTroubleshootFeature execution via catalog registry."""
    dev = Device(name="TEH-PE01", mgmt_ip="10.10.1.1", role="PE", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("ptp_troubleshoot")
    assert feature is not None

    mock_sess = MockPtpTraceSession(inject_fault_at_hop1=False)
    ctx = FeatureContext(
        db_session=test_db_session,
        params={
            "target": "TEH-PE01",
            "max_hops": 3,
            "_session_mock": mock_sess,
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "success"
    assert res["overall_status"] == "HEALTHY"
    assert "topology_graph" in res
    assert "text_verdict" in res


def test_ptp_api_endpoints(app_client):
    """Verify REST API endpoint /api/v1/ptp/trace."""
    from unittest.mock import patch

    mock_sess = MockPtpTraceSession(inject_fault_at_hop1=False)

    with patch("backend.app.services.ptp.DeviceSession", return_value=mock_sess):
        trace_res = app_client.post(
            "/api/v1/ptp/trace",
            json={
                "target": "TEH-PE01",
                "max_hops": 3,
            },
        )
        assert trace_res.status_code == 200
        trace_data = trace_res.get_json()
        assert trace_data["status"] == "success"
        assert trace_data["overall_status"] == "HEALTHY"
        assert "nodes" in trace_data["topology_graph"]
        assert len(trace_data["topology_graph"]["nodes"]) >= 1
        assert "text_verdict" in trace_data

