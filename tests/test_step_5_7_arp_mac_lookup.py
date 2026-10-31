"""Comprehensive tests for Phase 5 Step 5.7: Site ARP & MAC Lookup."""
import time
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.arp_mac import (
    ArpMacRecord,
    ArpMacSnapshot,
    ArpMacHistory,
    SiteInventory,
)
from backend.app.services.arp import (
    normalize_mac,
    SiteArpService,
    ArpCollectorManager,
    arp_cache,
)
from site_arp_service import (
    parse_arp,
    parse_mac_table,
    enrich_from_mac_table,
    parse_ne_csv_content,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


SAMPLE_ARP_OUTPUT = """
IP ADDRESS      MAC ADDRESS     EXPIRE(M) TYPE        INTERFACE   VPN-INSTANCE
------------------------------------------------------------------------------
10.10.1.50      0018-82ab-cd01  19        D-0         GE0/1/0     MCCI_Internet
                    100 / -
10.10.1.51      0018-82ab-cd02  15        D-0         GE0/1/1     
                    200 / -
"""

SAMPLE_MAC_OUTPUT = """
MAC Address    VLAN/VSI/BD   Learned-From        Type
------------------------------------------------------------------------------
0018-82ab-cd01 100           10GE0/0/1           dynamic
0018-82ab-cd02 200           10GE0/0/2           dynamic
"""


class MockCollectorSession:
    """Mock session for collector CLI commands."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.commands_sent = []

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if self.delay > 0:
            time.sleep(self.delay)

        if "display arp" in cmd:
            return SAMPLE_ARP_OUTPUT
        if "display mac-address" in cmd:
            return SAMPLE_MAC_OUTPUT
        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_arp.db"
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
    db_file = tmp_path / "test_app_arp.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_arp", role="admin", password_hash="dummy_hash")
            s.add(admin)

            site = SiteInventory(site_code="TEH-0392", ip="10.10.1.50", model="ATN950B")
            rec1 = ArpMacRecord(
                ne_name="TEH-AGG01",
                ne_ip="10.255.0.1",
                arp_ip="10.10.1.50",
                arp_mac="0018-82ab-cd01",
                vlan="100",
                vrf="MCCI_Internet",
                arp_interface="GE0/1/0",
                mac_port="10GE0/0/1",
                collected_at=datetime.utcnow(),
            )
            s.add_all([site, rec1])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_arp",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_normalize_mac():
    """Verify MAC address normalization across multiple delimiters."""
    assert normalize_mac("0018-82ab-cd01") == "001882abcd01"
    assert normalize_mac("00:18:82:AB:CD:01") == "001882abcd01"
    assert normalize_mac("00-18-82-AB-CD-01") == "001882abcd01"
    assert normalize_mac("001882.abcd01") == "001882abcd01"
    assert normalize_mac("") == ""
    assert normalize_mac(None) == ""


def test_arp_and_mac_parsers():
    """Verify CLI parsing for display arp all and display mac-address."""
    arp_entries = parse_arp(SAMPLE_ARP_OUTPUT)
    assert len(arp_entries) == 2
    assert arp_entries[0]["arp_ip"] == "10.10.1.50"
    assert arp_entries[0]["arp_mac"] == "0018-82ab-cd01"
    assert arp_entries[0]["interface"] == "GE0/1/0"
    assert arp_entries[0]["vrf"] == "MCCI_Internet"
    assert arp_entries[0]["vlan"] == "100"

    mac_table = parse_mac_table(SAMPLE_MAC_OUTPUT)
    assert "0018-82ab-cd01" in mac_table
    assert mac_table["0018-82ab-cd01"][0]["vlan"] == "100"
    assert mac_table["0018-82ab-cd01"][0]["port"] == "10GE0/0/1"

    # Test enrichment
    entry = dict(arp_entries[0])
    entry["vlan"] = ""
    enrich_from_mac_table(entry, mac_table)
    assert entry["vlan"] == "100"
    assert entry["mac_port"] == "10GE0/0/1"


def test_lookup_by_site_and_ip_db(test_db_session):
    """Verify database-backed lookup resolving Site Code and IP with shared MAC aggregation."""
    # 1. Seed test data
    site = SiteInventory(site_code="TEH-0392", ip="10.10.1.50", model="ATN950B")
    test_db_session.add(site)

    # Primary router record for site
    rec1 = ArpMacRecord(
        ne_name="TEH-AGG01",
        ne_ip="10.255.0.1",
        arp_ip="10.10.1.50",
        arp_mac="0018-82ab-cd01",
        vlan="100",
        vrf="MCCI_Internet",
        arp_interface="GE0/1/0",
        mac_port="10GE0/0/1",
        collected_at=datetime.utcnow(),
    )
    # Secondary router record sharing the exact same MAC
    rec2 = ArpMacRecord(
        ne_name="TEH-AGG02",
        ne_ip="10.255.0.2",
        arp_ip="10.10.1.51",
        arp_mac="0018-82ab-cd01",
        vlan="100",
        vrf="MCCI_Internet",
        arp_interface="GE0/2/0",
        mac_port="10GE0/0/2",
        collected_at=datetime.utcnow(),
    )
    test_db_session.add_all([rec1, rec2])
    test_db_session.commit()

    # 2. Lookup by Site Code
    res_site = SiteArpService.lookup(test_db_session, "TEH-0392", force_refresh=True)
    assert res_site["success"] is True
    assert res_site["count"] == 2
    assert "0018-82ab-cd01" in res_site["macs"]

    # Verify field schema
    row0 = res_site["results"][0]
    assert row0["Site_Code"] == "TEH-0392"
    assert row0["Site_Model"] == "ATN950B"
    assert row0["Vlan"] == "100"
    assert row0["VRF"] == "MCCI_Internet"

    # 3. Lookup by IP Address
    res_ip = SiteArpService.lookup(test_db_session, "10.10.1.50", force_refresh=True)
    assert res_ip["success"] is True
    assert res_ip["count"] == 2
    assert res_ip["site_code"] == "TEH-0392"


def test_ttl_cache_and_freshness(test_db_session):
    """Verify in-memory TTL caching and freshness metadata reporting."""
    arp_cache.clear()

    site = SiteInventory(site_code="ISF-0100", ip="10.20.1.1", model="CX600")
    rec = ArpMacRecord(
        ne_name="ISF-PE01",
        ne_ip="10.20.0.1",
        arp_ip="10.20.1.1",
        arp_mac="0018-8200-1111",
        vlan="50",
        arp_interface="GE0/1/0",
        mac_port="GE0/1/0",
        collected_at=datetime.utcnow(),
    )
    test_db_session.add_all([site, rec])
    test_db_session.commit()

    # 1. First lookup (cache miss -> cached)
    res1 = SiteArpService.lookup(test_db_session, "ISF-0100", ttl_seconds=2)
    assert res1["success"] is True
    assert res1["freshness"]["is_fresh"] is True

    # 2. Second lookup (cache hit)
    res2 = SiteArpService.lookup(test_db_session, "ISF-0100", ttl_seconds=2)
    assert res2["success"] is True
    assert res2["freshness"]["is_fresh"] is True

    # 3. Wait for TTL expiry
    time.sleep(2.1)
    cached = arp_cache.get("query:ISF-0100", ttl_seconds=2)
    assert cached is None  # expired


def test_collector_job_execution_and_cancellation(test_db_session):
    """Verify background collector job progress tracking and real cancellation."""
    manager = ArpCollectorManager()
    mock_sess = MockCollectorSession(delay=0.0)

    routers = [
        {"name": "BR-AGG01", "ip": "10.10.1.1", "ne_type": "huawei"},
        {"name": "BR-AGG02", "ip": "10.10.1.2", "ne_type": "huawei"},
    ]

    SessionLocal = sessionmaker(bind=test_db_session.bind)

    # 1. Normal run to completion
    started = manager.start_job(
        routers=routers,
        username="admin",
        password="pwd",
        max_workers=2,
        db_session_factory=SessionLocal,
        session_mock=mock_sess,
    )
    assert started is True

    # Wait for completion
    for _ in range(50):
        st = manager.get_status()
        if st["status"] in ("done", "error", "stopped"):
            break
        time.sleep(0.05)

    status = manager.get_status()
    assert status["status"] == "done"
    assert status["completed"] == 2
    assert status["rows_collected"] == 4  # 2 rows per router

    # Verify records written to DB
    db_records = test_db_session.query(ArpMacRecord).filter(
        ArpMacRecord.ne_name.in_(["BR-AGG01", "BR-AGG02"])
    ).all()
    assert len(db_records) == 4

    # 2. Test cancellation
    mock_slow_sess = MockCollectorSession(delay=0.1)
    slow_routers = [{"name": f"IL-PE{i:02d}", "ip": f"10.20.1.{i}"} for i in range(10)]

    started_cancel = manager.start_job(
        routers=slow_routers,
        username="admin",
        password="pwd",
        max_workers=1,
        db_session_factory=SessionLocal,
        session_mock=mock_slow_sess,
    )
    assert started_cancel is True

    time.sleep(0.05)
    # Trigger cancellation
    stopped = manager.stop()
    assert stopped is True

    # Wait for cancellation confirmation
    for _ in range(50):
        st = manager.get_status()
        if st["status"] in ("stopped", "done"):
            break
        time.sleep(0.05)

    final_st = manager.get_status()
    assert final_st["status"] == "stopped"


def test_filter_results_and_csv_export():
    """Verify result table filtering and UTF-8-SIG CSV export."""
    records = [
        {"Site_Code": "TEH-01", "IP": "10.1.1.1", "Model": "NE40E", "NE": "TEH-AGG01", "NE_IP": "10.0.0.1", "ARP_MAC": "0018-8201-0001", "Vlan": "100", "VRF": "MCCI", "ARP_Interface": "GE0/1/0", "MAC_Port": "10GE0/0/1", "collected_at": "2026-10-31 03:00:00"},
        {"Site_Code": "TEH-02", "IP": "10.1.1.2", "Model": "NE40E", "NE": "TEH-AGG02", "NE_IP": "10.0.0.2", "ARP_MAC": "0018-8201-0002", "Vlan": "200", "VRF": "INTERNET", "ARP_Interface": "GE0/1/1", "MAC_Port": "10GE0/0/2", "collected_at": "2026-10-31 03:00:00"},
    ]

    # Filter by VLAN
    f_vlan = SiteArpService.filter_results(records, vlan="100")
    assert len(f_vlan) == 1
    assert f_vlan[0]["Site_Code"] == "TEH-01"

    # Filter by keyword
    f_kw = SiteArpService.filter_results(records, keyword="INTERNET")
    assert len(f_kw) == 1
    assert f_kw[0]["Site_Code"] == "TEH-02"

    # CSV Export
    csv_str = SiteArpService.export_csv(records)
    assert "Site_Code,IP,Model,NE,NE_IP,ARP_MAC,Vlan,VRF,ARP_Interface,MAC_Port" in csv_str
    assert "TEH-01,10.1.1.1,NE40E" in csv_str


def test_site_arp_feature_run(test_db_session):
    """Verify SiteArpLookupFeature execution via catalog registry."""
    site = SiteInventory(site_code="KRD-0500", ip="10.30.1.1", model="ATN950")
    rec = ArpMacRecord(
        ne_name="KRD-AGG01",
        ne_ip="10.30.0.1",
        arp_ip="10.30.1.1",
        arp_mac="0018-8230-0001",
        vlan="300",
        vrf="MCCI",
        arp_interface="GE0/1/0",
        mac_port="10GE0/0/1",
        collected_at=datetime.utcnow(),
    )
    test_db_session.add_all([site, rec])
    test_db_session.commit()

    feature = feature_registry.get("site_arp_lookup")
    assert feature is not None

    ctx = FeatureContext(
        db_session=test_db_session,
        params={
            "query": "KRD-0500",
            "ttl_seconds": 120,
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "success"
    assert res["count"] == 1
    assert res["results"][0]["Site_Code"] == "KRD-0500"
    assert "freshness" in res
    assert "csv_preview" in res


def test_arp_api_endpoints(app_client):
    """Verify REST API endpoints /api/v1/arp/lookup, collector, and export."""
    # 1. Lookup API
    lookup_res = app_client.post(
        "/api/v1/arp/lookup",
        json={"query": "TEH-0392"},
    )
    assert lookup_res.status_code == 200
    lookup_data = lookup_res.get_json()
    assert lookup_data["success"] is True
    assert lookup_data["count"] >= 1
    assert any(r["Site_Code"] == "TEH-0392" for r in lookup_data["results"])

    # 2. Collector Status API
    status_res = app_client.get("/api/v1/arp/collector/status")
    assert status_res.status_code == 200
    st_data = status_res.get_json()
    assert "status" in st_data
    assert "progress_pct" in st_data

    # 3. Collector Stop API
    stop_res = app_client.post("/api/v1/arp/collector/stop")
    assert stop_res.status_code == 200

    # 4. Export CSV API
    export_res = app_client.get("/api/v1/arp/export?query=TEH-0392")
    assert export_res.status_code == 200
    assert "text/csv" in export_res.content_type
    assert b"TEH-0392" in export_res.data
