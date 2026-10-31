"""Comprehensive tests for Phase 5 Step 5.4: License Management."""
import io
import zipfile
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device, TargetSet
from backend.app.models.license import LicenseRecord, LicenseRenewalReport
from backend.app.models.config_change import ChangeRequest
from backend.app.services.license import LicenseService
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


MOCK_DISPLAY_LICENSE = """
Active License                  : lic_ne8000_2026.dat
License State                   : Normal
Revoke Ticket                   : No ticket
License Mode                    : Common
Product Name                    : NetEngine 8000 M8
Product Version                 : V800R019C00SPC600
License Serial No               : LIC202410310001
Creator                         : Huawei Technologies Co., Ltd.
Created Time                    : 2024-10-31 10:00:00
Country                         : Iran
Custom                          : NOC
Office                          : TEH

Feature name: CR8BM8BGP00
Authorize type: demo
Expired date: 2026-12-31
Trial days: 60

Item name          Item type     Value       Description
----------------------------------------------------------------------
CR8M00BGP00        Function      1           BGP Feature
CR8M00MPLS0        Function      1           MPLS Feature
"""

MOCK_DISPLAY_LICENSE_VERBOSE = """
Active License                  : lic_ne8000_2026.dat
License State                   : Normal
Revoke Ticket                   : No ticket
License Mode                    : Common
Product Name                    : NetEngine 8000 M8
Product Version                 : V800R019C00SPC600
License File ESN                : 2102353GBH10N9000001
License Serial No               : LIC202410310001
Creator                         : Huawei Technologies Co., Ltd.
Created Time                    : 2024-10-31 10:00:00
Country                         : Iran
Custom                          : NOC
Office                          : TEH

Feature name: CR8BM8BGP00
Authorize type: demo
Expired date: 2026-11-20
Trial days: 20

Sale name          : CR8M00BGP00
Item name          : CR8M00BGP00
Item type          : Function
Control value      : 1
Used value         : 1
Item state         : Normal
Item expired date  : 2026-11-20
Description        : Border Gateway Protocol
"""

MOCK_XML_LICENSE = """<?xml version="1.0" encoding="UTF-8"?>
<LicFile>
    <NodeInfo>
        <ESN>2102353GBH10N9000001</ESN>
    </NodeInfo>
    <Product>
        <Name>NetEngine 8000 M8</Name>
        <Version>V800R019C00SPC600</Version>
    </Product>
    <Feature>
        <Name>CR8BM8BGP00</Name>
        <ExpiredDate>2027-10-31</ExpiredDate>
    </Feature>
</LicFile>
"""


class MockLicenseSession:
    """Mock session returning display license outputs."""

    def __init__(self, verbose_ok: bool = True):
        self.verbose_ok = verbose_ok
        self.commands_sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if "display license verbose" in cmd:
            if self.verbose_ok:
                return MOCK_DISPLAY_LICENSE_VERBOSE
            raise RuntimeError("Verbose not supported on this VRP version")
        if "display license" in cmd:
            return MOCK_DISPLAY_LICENSE
        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_licenses.db"
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
    db_file = tmp_path / "test_app_licenses.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_license", role="admin", password_hash="dummy_hash")
            s.add(admin)
            dev1 = Device(
                name="TEH-PE01_TH",
                mgmt_ip="10.10.1.1",
                vendor="huawei",
                os_family="vrp8",
                province="TH",
                site="TEH-PE01",
                role="PE",
                esn="2102353GBH10N9000001",
                enabled=True,
            )
            dev2 = Device(
                name="ISF-PE02_IS",
                mgmt_ip="10.20.1.1",
                vendor="huawei",
                os_family="vrp8",
                province="IS",
                site="ISF-PE02",
                role="PE",
                esn="2102353GBH10N9000002",
                enabled=True,
            )
            s.add(dev1)
            s.add(dev2)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_license",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_parse_display_license():
    """Verify parsing of standard display license output."""
    parsed = LicenseService.parse_display_license(MOCK_DISPLAY_LICENSE)
    assert parsed["active_license"] == "lic_ne8000_2026.dat"
    assert parsed["license_state"] == "Normal"
    assert parsed["product_name"] == "NetEngine 8000 M8"
    assert parsed["product_version"] == "V800R019C00SPC600"
    assert parsed["license_serial_no"] == "LIC202410310001"
    assert len(parsed["features"]) == 1
    assert parsed["features"][0]["feature_name"] == "CR8BM8BGP00"
    assert parsed["features"][0]["expired_date"] == "2026-12-31"
    assert len(parsed["items"]) == 2
    assert parsed["items"][0]["item_name"] == "CR8M00BGP00"


def test_parse_display_license_verbose():
    """Verify parsing of verbose display license output."""
    parsed = LicenseService.parse_display_license_verbose(MOCK_DISPLAY_LICENSE_VERBOSE)
    assert parsed["license_esn"] == "2102353GBH10N9000001"
    assert parsed["product_name"] == "NetEngine 8000 M8"
    assert len(parsed["features"]) == 1
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["item_name"] == "CR8M00BGP00"
    assert parsed["items"][0]["used_value"] == "1"
    assert parsed["items"][0]["control_value"] == "1"


def test_calculate_days_to_expiry_and_alerts():
    """Verify days to expiry and alert thresholds (<=90/60/30/7 days, expired, permanent)."""
    ref_dt = datetime(2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc)

    # 1. Permanent / Unlimited
    days, is_exp, norm = LicenseService.calculate_days_to_expiry("PERMANENT", reference_date=ref_dt)
    assert days is None
    assert not is_exp
    assert norm == "PERMANENT"
    assert LicenseService.determine_alert_level(days, is_exp) == "OK"

    # 2. OK (> 90 days, e.g. 100 days)
    target_ok = (ref_dt + timedelta(days=100)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_ok, reference_date=ref_dt)
    assert days == 100
    assert not is_exp
    assert LicenseService.determine_alert_level(days, is_exp) == "OK"

    # 3. WARN_90 (80 days)
    target_90 = (ref_dt + timedelta(days=80)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_90, reference_date=ref_dt)
    assert days == 80
    assert LicenseService.determine_alert_level(days, is_exp) == "WARN_90"

    # 4. WARN_60 (50 days)
    target_60 = (ref_dt + timedelta(days=50)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_60, reference_date=ref_dt)
    assert days == 50
    assert LicenseService.determine_alert_level(days, is_exp) == "WARN_60"

    # 5. WARN_30 (25 days)
    target_30 = (ref_dt + timedelta(days=25)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_30, reference_date=ref_dt)
    assert days == 25
    assert LicenseService.determine_alert_level(days, is_exp) == "WARN_30"

    # 6. CRITICAL_7 (5 days)
    target_7 = (ref_dt + timedelta(days=5)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_7, reference_date=ref_dt)
    assert days == 5
    assert LicenseService.determine_alert_level(days, is_exp) == "CRITICAL_7"

    # 7. EXPIRED (-10 days)
    target_past = (ref_dt - timedelta(days=10)).strftime("%Y-%m-%d")
    days, is_exp, _ = LicenseService.calculate_days_to_expiry(target_past, reference_date=ref_dt)
    assert days == -10
    assert is_exp is True
    assert LicenseService.determine_alert_level(days, is_exp) == "EXPIRED"


def test_xml_license_parsing_and_matching(test_db_session):
    """Verify parsing XML/ZIP license files and matching them to inventory devices by ESN."""
    dev = Device(
        name="TEH-PE01_TH",
        mgmt_ip="10.10.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
        esn="2102353GBH10N9000001",
        enabled=True,
    )
    test_db_session.add(dev)
    test_db_session.commit()

    # 1. Parse raw XML
    raw_bytes = MOCK_XML_LICENSE.encode("utf-8")
    parsed_entries = LicenseService.parse_license_file_content(raw_bytes, "license_ne8000.xml")
    assert len(parsed_entries) == 1
    assert parsed_entries[0]["esn"] == "2102353GBH10N9000001"
    assert parsed_entries[0]["product_name"] == "NetEngine 8000 M8"
    assert len(parsed_entries[0]["features"]) == 1

    # 2. Match to DB device
    matched, unmatched = LicenseService.match_license_to_devices(test_db_session, parsed_entries)
    assert len(matched) == 1
    assert len(unmatched) == 0
    assert matched[0]["device_name"] == "TEH-PE01_TH"
    assert matched[0]["matched_esn"] == "2102353GBH10N9000001"

    # 3. Parse ZIP archive containing XML
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("unmatched_router.xml", """<?xml version="1.0"?>
        <LicFile><NodeInfo><ESN>UNKNOWN_ESN_99999</ESN></NodeInfo></LicFile>
        """)
        zf.writestr("matched_router.xml", MOCK_XML_LICENSE)
    zip_bytes = zip_buf.getvalue()

    zip_entries = LicenseService.parse_license_file_content(zip_bytes, "batch_licenses.zip")
    assert len(zip_entries) == 2
    matched_zip, unmatched_zip = LicenseService.match_license_to_devices(test_db_session, zip_entries)
    assert len(matched_zip) == 1
    assert len(unmatched_zip) == 1
    assert unmatched_zip[0]["esn"] == "UNKNOWN_ESN_99999"


def test_scan_device_license_and_db_upsert(test_db_session):
    """Verify scanning device license, calculation, and database record upsert."""
    dev = Device(
        name="TEH-PE01_TH",
        mgmt_ip="10.10.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
        esn="2102353GBH10N9000001",
        enabled=True,
    )
    test_db_session.add(dev)
    test_db_session.commit()

    mock_sess = MockLicenseSession(verbose_ok=True)
    ref_dt = datetime(2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc)

    # Scan
    scanned = LicenseService.scan_device_license(dev, mock_sess, reference_date=ref_dt)
    assert scanned["product_name"] == "NetEngine 8000 M8"
    assert scanned["license_state"] == "Normal"
    assert scanned["active_license"] == "lic_ne8000_2026.dat"
    assert scanned["days_to_expiry"] == 20  # from verbose 2026-11-20
    assert scanned["alert_level"] == "WARN_30"
    assert scanned["items_used_count"] == 1
    assert scanned["items_total_count"] == 1

    # Save to DB
    rec = LicenseService.save_device_license(test_db_session, dev.id, scanned)
    assert rec.id is not None
    assert rec.days_to_expiry == 20
    assert rec.alert_level == "WARN_30"

    # Upsert again with new data (e.g. permanent)
    scanned["days_to_expiry"] = None
    scanned["expiry_date"] = "PERMANENT"
    scanned["alert_level"] = "OK"
    rec2 = LicenseService.save_device_license(test_db_session, dev.id, scanned)
    assert rec2.id == rec.id
    assert rec2.alert_level == "OK"
    assert rec2.expiry_date == "PERMANENT"


def test_fleet_summary_and_filtering(test_db_session):
    """Verify fleet summary aggregates and filtering options."""
    # Create 3 devices
    dev1 = Device(name="D1_TH", mgmt_ip="10.1.1.1", vendor="huawei", province="TH", enabled=True)
    dev2 = Device(name="D2_TH", mgmt_ip="10.1.1.2", vendor="huawei", province="TH", enabled=True)
    dev3 = Device(name="D3_IS", mgmt_ip="10.2.1.1", vendor="huawei", province="IS", enabled=True)
    test_db_session.add_all([dev1, dev2, dev3])
    test_db_session.commit()

    # Add license records: dev1 OK, dev2 WARN_90, dev3 CRITICAL_7
    rec1 = LicenseRecord(
        device_id=dev1.id, product_name="NE8000", alert_level="OK", days_to_expiry=150, license_state="Normal"
    )
    rec2 = LicenseRecord(
        device_id=dev2.id, product_name="NE8000", alert_level="WARN_90", days_to_expiry=85, license_state="Normal"
    )
    rec3 = LicenseRecord(
        device_id=dev3.id, product_name="ATN950B", alert_level="CRITICAL_7", days_to_expiry=4, license_state="Demo"
    )
    test_db_session.add_all([rec1, rec2, rec3])
    test_db_session.commit()

    # 1. Fleet summary for all
    summary_all = LicenseService.get_fleet_summary(test_db_session)
    assert summary_all["total_devices"] == 3
    assert summary_all["scanned_devices"] == 3
    assert summary_all["unscanned_devices"] == 0
    assert summary_all["counts_by_alert"]["OK"] == 1
    assert summary_all["counts_by_alert"]["WARN_90"] == 1
    assert summary_all["counts_by_alert"]["CRITICAL_7"] == 1
    assert summary_all["products"]["NE8000"] == 2
    assert summary_all["products"]["ATN950B"] == 1

    # 2. Province summary (TH only)
    summary_th = LicenseService.get_fleet_summary(test_db_session, province="TH")
    assert summary_th["total_devices"] == 2
    assert summary_th["counts_by_alert"]["CRITICAL_7"] == 0

    # 3. List fleet licenses with alert filter
    list_res = LicenseService.list_fleet_licenses(test_db_session, alert_level="CRITICAL_7")
    assert list_res["total"] == 1
    assert list_res["items"][0]["device_name"] == "D3_IS"

    # 4. Search query
    search_res = LicenseService.list_fleet_licenses(test_db_session, search="ATN950B")
    assert search_res["total"] == 1
    assert search_res["items"][0]["device_name"] == "D3_IS"

    # 5. Nightly expiry alerts
    alerts = LicenseService.check_expiring_licenses(test_db_session)
    assert len(alerts) == 2  # D2_TH (WARN_90) and D3_IS (CRITICAL_7)


def test_license_feature_run(test_db_session):
    """Verify LicenseManagementFeature catalog feature execution."""
    dev = Device(
        name="TEH-PE01_TH",
        mgmt_ip="10.10.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
        esn="2102353GBH10N9000001",
        enabled=True,
    )
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("license_management")
    assert feature is not None

    mock_sess = MockLicenseSession(verbose_ok=True)
    ctx = FeatureContext(
        db_session=test_db_session,
        params={
            "province": "TH",
            "save_to_db": True,
            "_session_mock": mock_sess,
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "success"
    assert res["devices_scanned"] == 1
    assert len(res["results"]) == 1
    assert res["results"][0]["product_name"] == "NetEngine 8000 M8"
    assert res["summary"]["total_devices"] == 1


def test_plan_license_renewal(test_db_session):
    """Verify license renewal planning via Safe Change Pipeline."""
    dev = Device(
        name="TEH-PE01_TH",
        mgmt_ip="10.10.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
        esn="2102353GBH10N9000001",
        enabled=True,
    )
    test_db_session.add(dev)
    test_db_session.commit()

    cr = LicenseService.plan_license_renewal(
        db_session=test_db_session,
        device=dev,
        license_filename="lic_ne8000_2027.dat",
        creator_id="admin_user",
        reason="Annual License Extension",
    )
    assert cr.id is not None
    assert "license active lic_ne8000_2027.dat" in cr.plan["lines"]
    status_str = cr.status.value if hasattr(cr.status, "value") else str(cr.status)
    assert status_str == "planned"


def test_licenses_api_endpoints(app_client):
    """Verify all REST API endpoints under /api/v1/licenses."""
    from unittest.mock import patch

    mock_sess = MockLicenseSession(verbose_ok=True)

    # 1. Run license check via feature mock
    with patch("backend.app.features.license.feature.DeviceSession", return_value=mock_sess):
        check_res = app_client.post(
            "/api/v1/licenses/check",
            json={"province": "TH", "save_to_db": True},
        )
        assert check_res.status_code == 200
        check_data = check_res.get_json()
        assert check_data["status"] == "success"
        assert check_data["devices_scanned"] == 1

    # 2. Get fleet table
    fleet_res = app_client.get("/api/v1/licenses/fleet")
    assert fleet_res.status_code == 200
    fleet_data = fleet_res.get_json()
    assert fleet_data["total"] == 2
    assert len(fleet_data["items"]) == 2

    # 3. Get fleet summary
    summary_res = app_client.get("/api/v1/licenses/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.get_json()
    assert summary_data["total_devices"] == 2
    assert summary_data["scanned_devices"] == 1

    # 4. Get device detail
    dev1_res = app_client.get("/api/v1/licenses/devices/1")
    assert dev1_res.status_code == 200
    dev1_data = dev1_res.get_json()
    assert dev1_data["product_name"] == "NetEngine 8000 M8"
    assert dev1_data["alert_level"] == "WARN_30"

    # 5. Get alerts
    alerts_res = app_client.get("/api/v1/licenses/alerts")
    assert alerts_res.status_code == 200
    alerts_data = alerts_res.get_json()
    assert alerts_data["total_alerts"] >= 1

    # 6. Renewal file match
    file_bytes = io.BytesIO(MOCK_XML_LICENSE.encode("utf-8"))
    match_res = app_client.post(
        "/api/v1/licenses/renewal/match",
        data={"file": (file_bytes, "license_ne8000.xml")},
        content_type="multipart/form-data",
    )
    assert match_res.status_code == 200
    match_data = match_res.get_json()
    assert match_data["matched_count"] == 1
    assert match_data["matched"][0]["device_name"] == "TEH-PE01_TH"

    # 7. Renewal plan creation
    plan_res = app_client.post(
        "/api/v1/licenses/renewal/plan",
        json={
            "device_id": 1,
            "license_filename": "lic_ne8000_2027.dat",
            "reason": "Test renewal plan",
        },
    )
    assert plan_res.status_code == 201
    plan_data = plan_res.get_json()
    assert plan_data["status"] == "planned"
    assert "license active lic_ne8000_2027.dat" in plan_data["commands"]
