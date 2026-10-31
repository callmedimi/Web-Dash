"""Comprehensive tests for Phase 5 Step 5.5: VRF & Routing Check."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.services.routing import (
    VrfRoutingService,
    VRF_RT_MAP,
    RT_TO_VRF_MAP,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


MOCK_BGP_VPNV4_OUTPUT = """
 Route Distinguisher: 65000:1001

 BGP routing table entry information of 10.10.1.1/32:
 From: 10.255.0.1
 Route Duration: 4d12h
 Original nexthop: 10.10.91.5
 Ext-Community: RT <65000:500>, Color <100>
 AS-path: (65000)
 Originator: 10.10.91.5
 Cluster list: 10.255.0.1
"""

MOCK_VRF_ROUTING_OUTPUT = """
Route Flags: R - relay, D - download to fib
------------------------------------------------------------------------------
Routing Table : VRF_Internet
Destinations : 2        Routes : 2

Destination/Mask    Proto   Pre  Cost      Flags NextHop         Interface

      10.10.1.0/24  Direct  0    0           D   10.10.1.254     GigabitEthernet0/1/0
      10.10.1.1/32  Direct  0    0           D   127.0.0.1       InLoopBack0
"""

MOCK_INTERFACE_CONFIG_OUTPUT = """
#
interface GigabitEthernet0/1/0
 description TO_CUSTOMER_INTERNET_LINK
 ip binding vpn-instance VRF_Internet
 ip address 10.10.1.254 255.255.255.0
#
"""


class MockRoutingSession:
    """Mock device session for VRF routing investigation."""

    def __init__(self):
        self.commands_sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if "display bgp vpnv4 all routing-table" in cmd:
            return MOCK_BGP_VPNV4_OUTPUT
        if "display ip routing-table vpn-instance" in cmd:
            return MOCK_VRF_ROUTING_OUTPUT
        if "display current-configuration interface" in cmd:
            return MOCK_INTERFACE_CONFIG_OUTPUT
        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_routing.db"
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
    db_file = tmp_path / "test_app_routing.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_routing", role="admin", password_hash="dummy_hash")
            s.add(admin)
            rr_dev = Device(
                name="TEH-RR01",
                mgmt_ip="10.255.0.1",
                vendor="huawei",
                os_family="vrp8",
                role="RR",
                province="TH",
                enabled=True,
            )
            pe_dev = Device(
                name="TEH-PE01",
                mgmt_ip="10.10.101.5",
                lsr_id="10.10.91.5",
                vendor="huawei",
                os_family="vrp8",
                role="PE",
                province="TH",
                enabled=True,
            )
            s.add(rr_dev)
            s.add(pe_dev)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_routing",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_validate_vrf_and_target():
    """Verify input validation for VRF names and Target IP / CIDR."""
    # Valid VRF and Target IP
    vrf, target = VrfRoutingService.validate_vrf_and_target("VRF_Internet", "10.10.1.1")
    assert vrf == "VRF_Internet"
    assert target == "10.10.1.1"

    # Valid CIDR
    vrf, target = VrfRoutingService.validate_vrf_and_target("VRF_B2B_A", "192.168.1.0/24")
    assert target == "192.168.1.0/24"

    # Invalid VRF name with dangerous characters
    with pytest.raises(ValueError):
        VrfRoutingService.validate_vrf_and_target("VRF_TEST; rm -rf", "10.10.1.1")

    # Invalid IP address
    with pytest.raises(ValueError):
        VrfRoutingService.validate_vrf_and_target("VRF_Internet", "999.1.1.1")

    # Invalid CIDR prefix
    with pytest.raises(ValueError):
        VrfRoutingService.validate_vrf_and_target("VRF_Internet", "10.10.1.0/35")


def test_transform_originator_ip():
    """Verify originator IP remapping to management IP."""
    # Special mapped octets
    assert VrfRoutingService.transform_originator_ip("10.10.91.5") == "10.10.101.5"
    assert VrfRoutingService.transform_originator_ip("10.10.92.20") == "10.10.102.20"
    assert VrfRoutingService.transform_originator_ip("10.10.157.1") == "10.10.86.1"
    # General rule: third octet + 100
    assert VrfRoutingService.transform_originator_ip("10.10.50.1") == "10.10.150.1"


def test_parse_bgp_received_routes():
    """Verify parsing BGP received routes, RT extraction, and VRF matching."""
    entries = VrfRoutingService.parse_bgp_received_routes(MOCK_BGP_VPNV4_OUTPUT)
    assert len(entries) == 1
    e = entries[0]
    assert e["route_distinguisher"] == "65000:1001"
    assert e["prefix"] == "10.10.1.1/32"
    assert e["originator"] == "10.10.91.5"
    assert "65000:500" in e["rt_values"]
    assert "VRF_Internet" in e["matched_vrf_names"]


def test_parse_routing_table_and_ip_matching():
    """Verify parsing VRP routing table and checking subnet containment."""
    routes = VrfRoutingService.parse_routing_table(MOCK_VRF_ROUTING_OUTPUT)
    assert len(routes) == 2
    r1 = routes[0]
    assert r1["destination"] == "10.10.1.0"
    assert r1["mask"] == "24"
    assert r1["proto_category"] == "Direct"
    assert r1["interface"] == "GigabitEthernet0/1/0"

    # IP match checks
    assert VrfRoutingService.ip_matches_route("10.10.1.1", "10.10.1.0", "24") is True
    assert VrfRoutingService.ip_matches_route("10.10.1.254", "10.10.1.0", "24") is True
    assert VrfRoutingService.ip_matches_route("10.10.2.1", "10.10.1.0", "24") is False


def test_parse_interface_config():
    """Verify parsing of interface configuration snippet."""
    parsed = VrfRoutingService.parse_interface_config(MOCK_INTERFACE_CONFIG_OUTPUT)
    assert parsed["interface_name"] == "GigabitEthernet0/1/0"
    assert parsed["description"] == "TO_CUSTOMER_INTERNET_LINK"
    assert parsed["vpn_instance"] == "VRF_Internet"
    assert parsed["ip_address"] == "10.10.1.254"
    assert parsed["subnet_mask"] == "255.255.255.0"


def test_trace_vrf_route_hop_by_hop(test_db_session):
    """Verify full hop-by-hop tracing, per-hop results, and path graph assembly."""
    rr = Device(
        name="TEH-RR01",
        mgmt_ip="10.255.0.1",
        vendor="huawei",
        os_family="vrp8",
        role="RR",
        enabled=True,
    )
    pe = Device(
        name="TEH-PE01",
        mgmt_ip="10.10.101.5",
        lsr_id="10.10.91.5",
        vendor="huawei",
        os_family="vrp8",
        role="PE",
        enabled=True,
    )
    test_db_session.add_all([rr, pe])
    test_db_session.commit()

    mock_sess = MockRoutingSession()

    res = VrfRoutingService.trace_vrf_route(
        db_session=test_db_session,
        vrf="VRF_Internet",
        target_ip_or_prefix="10.10.1.1",
        ingress_device_id=rr.id,
        session_mock=mock_sess,
    )

    assert res["status"] == "resolved"
    assert res["vrf"] == "VRF_Internet"
    assert res["target"] == "10.10.1.1"

    # Verify 3 hops
    hops = res["hops"]
    assert len(hops) == 3
    assert hops[0]["role"] == "RR"
    assert hops[0]["device_name"] == "TEH-RR01"
    assert hops[0]["route_distinguisher"] == "65000:1001"

    assert hops[1]["role"] == "PE"
    assert hops[1]["device_name"] == "TEH-PE01"
    assert hops[1]["interface"] == "GigabitEthernet0/1/0"

    assert hops[2]["role"] == "CE"
    assert hops[2]["device_name"] == "TO_CUSTOMER_INTERNET_LINK"
    assert hops[2]["interface"] == "GigabitEthernet0/1/0"

    # Verify Path Graph
    graph = res["path_graph"]
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 2
    assert graph["nodes"][0]["role"] == "RR"
    assert graph["nodes"][1]["role"] == "PE"
    assert graph["nodes"][2]["role"] == "CE"


def test_vrf_routing_feature_run(test_db_session):
    """Verify execution of VrfRoutingCheckFeature catalog feature."""
    rr = Device(
        name="TEH-RR01",
        mgmt_ip="10.255.0.1",
        vendor="huawei",
        os_family="vrp8",
        role="RR",
        enabled=True,
    )
    test_db_session.add(rr)
    test_db_session.commit()

    feature = feature_registry.get("vrf_routing_check")
    assert feature is not None

    mock_sess = MockRoutingSession()
    ctx = FeatureContext(
        db_session=test_db_session,
        params={
            "vrf": "VRF_Internet",
            "target_ip": "10.10.1.1",
            "ingress_device_id": rr.id,
            "_session_mock": mock_sess,
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "resolved"
    assert res["feature"] == "vrf_routing_check"
    assert len(res["hops"]) == 3
    assert res["summary"]["route_reflector"] == "TEH-RR01"


def test_vrf_routing_api_endpoints(app_client):
    """Verify REST API endpoints for VRF routing."""
    from unittest.mock import patch

    mock_sess = MockRoutingSession()

    # 1. Get known VRFs
    vrfs_res = app_client.get("/api/v1/routing/vrfs")
    assert vrfs_res.status_code == 200
    vrfs_data = vrfs_res.get_json()
    assert "VRF_Internet" in vrfs_data["vrfs"]
    assert "VRF_B2B_A" in vrfs_data["vrfs"]
    assert vrfs_data["vrf_count"] > 10

    # 2. Trace VRF routing
    with patch("backend.app.services.routing.DeviceSession", return_value=mock_sess):
        trace_res = app_client.post(
            "/api/v1/routing/trace",
            json={
                "vrf": "VRF_Internet",
                "target_ip": "10.10.1.1",
            },
        )
        assert trace_res.status_code == 200
        trace_data = trace_res.get_json()
        assert trace_data["status"] == "resolved"
        assert len(trace_data["hops"]) == 3
        assert len(trace_data["path_graph"]["nodes"]) == 3

    # 3. Check prefix in VRF
    with patch("backend.app.api.routing.DeviceSession", return_value=mock_sess):
        prefix_res = app_client.post(
            "/api/v1/routing/check-prefix",
            json={
                "vrf": "VRF_Internet",
                "target_ip": "10.10.1.1",
            },
        )
        assert prefix_res.status_code == 200
        prefix_data = prefix_res.get_json()
        assert prefix_data["has_route"] is True
        assert prefix_data["routes_count"] >= 1
