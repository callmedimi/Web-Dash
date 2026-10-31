"""Tests for Step 5.3: Down-Links Report, Analytics, Day-over-Day Diffing, and XLSX/CSV Exports."""
import io
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.device import Device
from backend.app.models.user import User
from backend.app.models.down_link import DownLinkReport
from backend.app.services.reporting import (
    DownLinksService,
    compute_analytics,
    classify_category,
    validate_age_threshold,
    FIELD_NAMES,
    TRUNK_FIELD_NAMES,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


class MockReportingSession:
    """Mock session returning active physical down alarms and interface configs."""

    def __init__(self):
        self.commands_sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if "display alarm active" in cmd:
            return """
Sequence  AlarmId    Level Date       Time     Description
----------------------------------------------------------------------------------------------------
101       0x08520003 1     2026-10-31 01:00:00 The interface GigabitEthernet0/1/0 physical status is Down
102       0x08520003 1     2026-10-31 01:02:00 The interface GigabitEthernet0/1/1 physical status is Down
103       0x08520003 1     2026-10-31 01:04:00 The interface GigabitEthernet0/1/2 physical status is Down
"""
        if "display current-configuration interface GigabitEthernet0/1/0" in cmd:
            return "#\ninterface GigabitEthernet0/1/0\n description TO_OSN_NODE_10\n ip address 10.1.1.1 30\n#"
        if "display current-configuration interface GigabitEthernet0/1/1" in cmd:
            return "#\ninterface GigabitEthernet0/1/1\n description SPO_LINK_2\n eth-trunk 33\n#"
        if "display current-configuration interface GigabitEthernet0/1/2" in cmd:
            # Genuine noconf link
            return "#\ninterface GigabitEthernet0/1/2\n shutdown\n#"
        if "display interface" in cmd:
            return "GigabitEthernet0/1/0 current state : Administratively DOWN"
        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_down_links.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client with test configuration and logged in user."""
    db_file = tmp_path / "test_app_down_links.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_test", role="admin", password_hash="dummy_hash")
            s.add(admin)
            dev = Device(
                name="TEH-MHD-PE01_TH",
                mgmt_ip="10.100.1.1",
                vendor="huawei",
                os_family="vrp8",
                province="TH",
                site="TEH-MHD",
                role="PE",
            )
            s.add(dev)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_test",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_validate_age_threshold():
    """Verify age parameter validation and timedelta conversion."""
    val, delta = validate_age_threshold(15, "minutes")
    assert val == 15
    assert delta == timedelta(minutes=15)

    val2, delta2 = validate_age_threshold(2, "hours")
    assert val2 == 2
    assert delta2 == timedelta(hours=2)

    val3, delta3 = validate_age_threshold(1, "days")
    assert val3 == 1
    assert delta3 == timedelta(days=1)

    with pytest.raises(ValueError):
        validate_age_threshold(-5, "hours")

    with pytest.raises(ValueError):
        validate_age_threshold(10, "centuries")


def test_classify_category():
    """Verify keyword classification for OSN, SPO, HRAN, and Other."""
    assert classify_category("Uplink to OSN 1800 Ring") == "OSN"
    assert classify_category("SPO Transmission link 4") == "SPO"
    assert classify_category("HRAN eNodeB 550") == "HRAN"
    assert classify_category("Customer Internet Access") == "Other"
    assert classify_category(None) == "Other"


def test_compute_analytics_burst_detection():
    """Verify sliding-window burst detection triggers when >= 3 down links occur in 300s."""
    report_data = [
        {"NE NAME": "ROUTER-01_TH", "Category": "OSN", "alarm occur time": "2026-10-31 01:00:00+00:00"},
        {"NE NAME": "ROUTER-01_TH", "Category": "OSN", "alarm occur time": "2026-10-31 01:02:00+00:00"},
        {"NE NAME": "ROUTER-02_TH", "Category": "SPO", "alarm occur time": "2026-10-31 01:04:00+00:00"},
    ]
    noconf_data = [
        {"NE NAME": "ROUTER-03_IS", "Category": "Other", "alarm occur time": "2026-10-31 03:00:00+00:00"},
    ]

    analytics = compute_analytics(report_data, noconf_data)
    assert analytics["total_down_links"] == 4
    assert analytics["service_down_count"] == 3
    assert analytics["noconf_down_count"] == 1

    # Check TH province summary (3 events within 4 minutes -> burst detected!)
    th_sum = next((p for p in analytics["province_summary"] if p["province"] == "TH"), None)
    assert th_sum is not None
    assert th_sum["total_count"] == 3
    assert th_sum["burst_detected"] is True
    assert th_sum["burst_count"] == 3

    # Check IS province (1 event -> no burst)
    is_sum = next((p for p in analytics["province_summary"] if p["province"] == "IS"), None)
    assert is_sum is not None
    assert is_sum["burst_detected"] is False


def test_compare_reports_diff():
    """Verify historical report diff correctly calculates new, recovered, and persistent down links."""
    # Day 1: Links A, B, C down
    day1_report = {
        "report_data": [
            {"NE NAME": "R1", "interface name": "GE0/1/0", "Category": "OSN"},
            {"NE NAME": "R1", "interface name": "GE0/1/1", "Category": "SPO"},
        ],
        "noconf_data": [
            {"NE NAME": "R2", "interface name": "GE0/1/2", "Category": "Other"},
        ],
    }

    # Day 2: Links B, C, D down (A recovered, D is newly down)
    day2_report = {
        "report_data": [
            {"NE NAME": "R1", "interface name": "GE0/1/1", "Category": "SPO"},
            {"NE NAME": "R2", "interface name": "GE0/1/3", "Category": "OSN"},  # New
        ],
        "noconf_data": [
            {"NE NAME": "R2", "interface name": "GE0/1/2", "Category": "Other"},
        ],
    }

    diff = DownLinksService.compare_reports(day2_report, day1_report)
    summary = diff["comparison_summary"]

    assert summary["new_down_count"] == 1
    assert summary["recovered_count"] == 1
    assert summary["persistent_count"] == 2

    assert diff["new_down_links"][0]["interface name"] == "GE0/1/3"
    assert diff["recovered_links"][0]["interface name"] == "GE0/1/0"


def test_export_csv_and_xlsx():
    """Verify CSV and multi-tab XLSX binary generation."""
    report_data = [
        {
            "NE NAME": "TEH-MHD-PE01_TH",
            "Interface type": "GE",
            "interface name": "GigabitEthernet0/1/0",
            "interface description": "OSN_NODE_10",
            "admin down or not": "Admin DOWN",
            "alarm occur time": "2026-10-31 01:00:00",
            "Down Reason": "Physical Link Down",
            "Trunk Memberships": "None",
            "Category": "OSN",
            "full configuration of the link": "interface GigabitEthernet0/1/0\n shutdown",
        }
    ]
    noconf_data = [
        {
            "NE NAME": "TEH-MHD-PE01_TH",
            "Interface type": "GE",
            "interface name": "GigabitEthernet0/1/2",
            "interface description": "No Description",
            "admin down or not": "UP (Oper DOWN)",
            "alarm occur time": "2026-10-31 01:04:00",
            "Down Reason": "Physical Link Down",
            "Trunk Memberships": "None",
            "Category": "Other",
            "full configuration of the link": "interface GigabitEthernet0/1/2\n shutdown",
        }
    ]
    analytics = compute_analytics(report_data, noconf_data)

    # 1. Test CSV export
    csv_bytes = DownLinksService.export_csv(report_data, noconf_data)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    assert b"TEH-MHD-PE01_TH" in csv_bytes
    assert b"GigabitEthernet0/1/0" in csv_bytes

    # 2. Test XLSX export
    xlsx_bytes = DownLinksService.export_xlsx(report_data, noconf_data, analytics=analytics)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    sheet_names = wb.sheetnames
    assert "Service Down Links" in sheet_names
    assert "NoConf Down Links" in sheet_names
    assert "Trunk Status" in sheet_names
    assert "Analytics Summary" in sheet_names

    ws1 = wb["Service Down Links"]
    assert ws1.cell(row=2, column=1).value == "TEH-MHD-PE01_TH"


def test_scan_device_down_links_mock():
    """Verify scan_device_down_links identifies service vs noconf links."""
    dev = Device(
        name="TEH-MHD-PE01_TH",
        mgmt_ip="10.100.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
    )
    mock_session = MockReportingSession()

    s_links, nc_links, trunks = DownLinksService.scan_device_down_links(
        device=dev,
        device_session=mock_session,
        age_value=0,
        age_unit="hours",
    )

    # GE0/1/0 (OSN) and GE0/1/1 (SPO) have descriptions/ip/trunk -> service
    # GE0/1/2 has shutdown only -> noconf
    assert len(s_links) == 2
    assert len(nc_links) == 1
    assert nc_links[0]["interface name"] == "GigabitEthernet0/1/2"


def test_down_links_feature_run(test_db_session):
    """Verify DownLinksFeature execution and persistence in database."""
    dev = Device(
        name="TEH-MHD-PE01_TH",
        mgmt_ip="10.100.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
        enabled=True,
    )
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("down_links")
    assert feature is not None

    ctx = FeatureContext(
        db_session=test_db_session,
        user_id=1,
        params={
            "device_ids": [dev.id],
            "_session_mock": MockReportingSession(),
            "save_report": True,
            "province": "TH",
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "success"
    assert res["service_down_count"] == 2
    assert res["noconf_down_count"] == 1
    assert res["total_down_links"] == 3
    assert res["report_id"] is not None

    # Verify persisted report
    saved = test_db_session.query(DownLinkReport).filter(DownLinkReport.id == res["report_id"]).first()
    assert saved is not None
    assert saved.service_down == 2
    assert saved.noconf_down == 1


def test_down_links_api_endpoints(app_client):
    """Verify Down-Links REST API endpoints for run, latest, compare, and exports."""
    from unittest.mock import patch

    mock_sess = MockReportingSession()

    with patch("backend.app.features.down_links.feature.DeviceSession", return_value=mock_sess):
        run_res = app_client.post(
            "/api/v1/reports/down-links/run",
            json={
                "province": "TH",
                "age_value": 0,
                "age_unit": "hours",
                "save_report": True,
            },
        )
        assert run_res.status_code == 200
        run_data = run_res.get_json()
        rep_id = run_data["report_id"]
        assert rep_id is not None

    # 2. Get latest report
    latest_res = app_client.get("/api/v1/reports/down-links/latest?province=TH")
    assert latest_res.status_code == 200
    assert latest_res.get_json()["id"] == rep_id

    # 3. Get report by ID
    get_res = app_client.get(f"/api/v1/reports/down-links/{rep_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["total_down"] == 3

    # 4. Compare report
    cmp_res = app_client.get(f"/api/v1/reports/down-links/{rep_id}/compare")
    assert cmp_res.status_code == 200

    # 5. Export CSV
    csv_res = app_client.get(f"/api/v1/reports/down-links/{rep_id}/export?format=csv")
    assert csv_res.status_code == 200
    assert "attachment; filename=down_links_report_" in csv_res.headers.get("Content-Disposition", "")
    assert b"TEH-MHD-PE01_TH" in csv_res.data

    # 6. Export XLSX
    xlsx_res = app_client.get(f"/api/v1/reports/down-links/{rep_id}/export?format=xlsx")
    assert xlsx_res.status_code == 200
    assert "application/vnd.openxmlformats" in xlsx_res.headers.get("Content-Type", "")
    assert len(xlsx_res.data) > 1000
