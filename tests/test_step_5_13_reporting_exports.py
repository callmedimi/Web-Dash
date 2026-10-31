"""Comprehensive tests for Phase 5 Step 5.13: Reporting, Unified Exports & Daily NOC Digest."""
import io
import json
import uuid
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import pytest
import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.models.license import LicenseRecord
from backend.app.models.job import Job
from backend.app.models.config_change import Event
from backend.app.models.down_link import DownLinkReport
from backend.app.services.export_service import UnifiedExportService
from backend.app.services.noc_digest import NocDigestService
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


@pytest.fixture
def test_db_session(tmp_path, monkeypatch):
    """Provide a fresh SQLite test session."""
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    db_file = tmp_path / "test_reporting_exports.db"
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
    db_file = tmp_path / "test_app_reports.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_rep", role="admin", password_hash="dummy_hash")
            s.add(admin)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_rep",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_unified_export_csv_utf8_sig():
    """Verify CSV export produces valid UTF-8-SIG BOM with Unicode (Persian) characters and quoting."""
    data = [
        {"device": "TEH-AGG01", "province": "تهران", "ip": "10.10.1.1", "status": "UP"},
        {"device": "ISF-PE01", "province": "اصفهان", "ip": "10.20.1.1", "status": "DOWN, ALARM"},
    ]

    csv_bytes = UnifiedExportService.export_csv(data)
    # Check UTF-8-SIG preamble (BOM)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")

    # Decode and verify contents
    decoded = csv_bytes.decode("utf-8-sig")
    assert "device,province,ip,status" in decoded
    assert "تهران" in decoded
    assert "اصفهان" in decoded
    # Field with comma must be quoted
    assert '"DOWN, ALARM"' in decoded


def test_unified_export_streaming_csv():
    """Verify streaming CSV generator yields UTF-8-SIG BOM first followed by headers and chunked rows."""
    data = [
        {"id": 1, "name": "Device A", "role": "AGG"},
        {"id": 2, "name": "Device B", "role": "PE"},
        {"id": 3, "name": "Device C", "role": "RR"},
    ]

    stream = list(UnifiedExportService.stream_csv(data))
    assert len(stream) == 5  # BOM, Header, Row1, Row2, Row3
    assert stream[0] == b"\xef\xbb\xbf"
    assert b"id,name,role" in stream[1]
    assert b"Device A" in stream[2]
    assert b"Device B" in stream[3]
    assert b"Device C" in stream[4]


def test_unified_export_xlsx_multi_sheet():
    """Verify multi-sheet XLSX workbook generation with openpyxl styling and column width adjustment."""
    sheets = {
        "Devices Overview": [
            {"Name": "TEH-AGG01", "IP": "10.10.1.1", "Role": "AGG", "Province": "TEH"},
            {"Name": "ISF-PE01", "IP": "10.20.1.1", "Role": "PE", "Province": "ISF"},
        ],
        "Alarms Active": [
            {"Alarm ID": "ALM-1", "Level": "Critical", "Desc": "Optical link failure"},
        ],
    }

    xlsx_bytes = UnifiedExportService.export_xlsx(sheets)
    assert len(xlsx_bytes) > 0

    # Load with openpyxl to verify contents
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert "Devices Overview" in wb.sheetnames
    assert "Alarms Active" in wb.sheetnames

    ws1 = wb["Devices Overview"]
    assert ws1.cell(row=1, column=1).value == "Name"
    assert ws1.cell(row=2, column=1).value == "TEH-AGG01"
    # Verify column width was set
    assert ws1.column_dimensions["A"].width >= 12

    ws2 = wb["Alarms Active"]
    assert ws2.cell(row=1, column=2).value == "Level"
    assert ws2.cell(row=2, column=2).value == "Critical"


def test_unified_export_json_extended_serializer():
    """Verify extended JSON serializer handles datetimes, dates, UUIDs, Decimals, and sets."""
    sample_data = {
        "report_id": uuid.uuid4(),
        "timestamp": datetime(2026, 10, 31, 12, 0, 0),
        "target_date": date(2026, 10, 31),
        "score": Decimal("99.95"),
        "tags": {"huawei", "vrp8", "core"},
    }

    json_bytes = UnifiedExportService.export_json(sample_data)
    decoded = json.loads(json_bytes.decode("utf-8"))

    assert isinstance(decoded["report_id"], str)
    assert decoded["timestamp"] == "2026-10-31T12:00:00"
    assert decoded["target_date"] == "2026-10-31"
    assert decoded["score"] == 99.95
    assert set(decoded["tags"]) == {"huawei", "vrp8", "core"}


def test_noc_digest_aggregation(test_db_session):
    """Verify NocDigestService aggregates multi-source metrics into unified daily digest."""
    now = datetime(2026, 10, 31, 14, 0, 0)

    # 1. Seed Devices and LicenseRecords
    dev1 = Device(
        name="TEH-AGG01",
        mgmt_ip="10.10.1.1",
        role="AGG",
        province="TEH",
        enabled=True,
    )
    dev2 = Device(
        name="ISF-PE01",
        mgmt_ip="10.20.1.1",
        role="PE",
        province="ISF",
        enabled=True,
    )
    test_db_session.add_all([dev1, dev2])
    test_db_session.flush()

    lic1 = LicenseRecord(
        device_id=dev1.id,
        product_name="NetEngine",
        license_state="Warning",
        days_to_expiry=5,  # <= 7 days
        expiry_date="2026-11-05",
        is_expired=False,
    )
    lic2 = LicenseRecord(
        device_id=dev2.id,
        product_name="NetEngine",
        license_state="Normal",
        days_to_expiry=45,  # <= 90 days
        expiry_date="2026-12-15",
        is_expired=False,
    )
    test_db_session.add_all([lic1, lic2])


    # 2. Seed Events (Alarms)
    ev1 = Event(
        ts=now - timedelta(hours=2),
        source="zabbix",
        device_id=dev1.id,
        severity="critical",
        title="BGP Peer Teardown",
        data={},
    )
    ev2 = Event(
        ts=now - timedelta(hours=5),
        source="ssh",
        device_id=dev1.id,
        severity="minor",
        title="Interface CRC Errors",
        data={},
    )
    test_db_session.add_all([ev1, ev2])

    # 3. Seed Jobs
    job1 = Job(
        id="job-success-1",
        type="config_backup",
        status="succeeded",
        mode="apply",
        created_by="system_cron",
        created_at=now - timedelta(hours=4),
        summary={"backup_count": 2},
    )
    job2 = Job(
        id="job-fail-1",
        type="alarm_clear",
        status="failed",
        mode="apply",
        created_by="operator1",
        created_at=now - timedelta(hours=1),
        summary={"error": "SSH connection refused"},
    )
    test_db_session.add_all([job1, job2])

    # 4. Seed DownLinkReport
    dl_report = DownLinkReport(
        total_down=3,
        service_down=2,
        noconf_down=1,
        created_at=now - timedelta(hours=3),
        analytics={"province_summary": [{"province": "TEH", "total_count": 3}]},
    )
    test_db_session.add(dl_report)
    test_db_session.commit()

    # Generate digest for trailing 24h
    digest = NocDigestService.generate_digest(
        db_session=test_db_session,
        hours=24,
        target_date=now,
    )

    # Assertions on metrics
    assert digest["status"] == "ATTENTION_NEEDED"
    assert digest["metrics"]["total_devices"] == 2
    assert digest["metrics"]["total_events"] == 2
    assert digest["metrics"]["critical_alarms"] == 1
    assert digest["metrics"]["failed_jobs"] == 1
    assert digest["metrics"]["service_down_links"] == 2
    assert digest["metrics"]["licenses_expiring_7d"] == 1

    # Assertions on sections
    assert digest["alarms"]["severity_counts"]["critical"] == 1
    assert len(digest["alarms"]["recent_critical"]) == 1
    assert digest["down_links"]["service_down"] == 2
    assert digest["licenses"]["expiring_7d_count"] == 1
    assert digest["jobs"]["total_executed"] == 2
    assert len(digest["jobs"]["failed_jobs"]) == 1
    assert digest["jobs"]["failed_jobs"][0]["id"] == "job-fail-1"

    # Highlights
    assert len(digest["highlights"]) >= 3
    assert any("critical" in h.lower() for h in digest["highlights"])
    assert any("failed" in h.lower() for h in digest["highlights"])


def test_noc_digest_export_formats(test_db_session):
    """Verify exporting NOC digest into XLSX, CSV, and JSON formats."""
    digest = NocDigestService.generate_digest(db_session=test_db_session, hours=24)

    # 1. XLSX Export
    xlsx_bytes, xlsx_mime, xlsx_name = NocDigestService.export_digest(digest, format_type="xlsx")
    assert xlsx_mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert xlsx_name.endswith(".xlsx")
    assert len(xlsx_bytes) > 0
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert "Executive Summary" in wb.sheetnames

    # 2. CSV Export
    csv_bytes, csv_mime, csv_name = NocDigestService.export_digest(digest, format_type="csv")
    assert "text/csv" in csv_mime
    assert csv_name.endswith(".csv")
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert "Overall Status" in csv_bytes.decode("utf-8-sig")

    # 3. JSON Export
    json_bytes, json_mime, json_name = NocDigestService.export_digest(digest, format_type="json")
    assert json_mime == "application/json"
    assert json_name.endswith(".json")
    parsed = json.loads(json_bytes.decode("utf-8"))
    assert "metrics" in parsed


def test_catalog_feature_reporting_digest(test_db_session):
    """Verify ReportingDigestFeature execution via catalog registry."""
    feature = feature_registry.get("reporting_digest")
    assert feature is not None

    # 1. Action: generate_digest
    ctx_gen = FeatureContext(db_session=test_db_session, params={"action": "generate_digest", "hours": 12})
    res_gen = feature.run(ctx_gen)
    assert res_gen["status"] == "success"
    assert "digest" in res_gen

    # 2. Action: export_digest
    ctx_exp = FeatureContext(db_session=test_db_session, params={"action": "export_digest", "format": "xlsx"})
    res_exp = feature.run(ctx_exp)
    assert res_exp["status"] == "success"
    assert res_exp["export_size_bytes"] > 0
    assert res_exp["filename"].endswith(".xlsx")

    # 3. Action: export_data
    sample_records = [
        {"rule": "SEC-001", "status": "PASS"},
        {"rule": "OPS-001", "status": "FAIL"},
    ]
    ctx_data = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "export_data",
            "format": "csv",
            "data": sample_records,
            "filename": "compliance_summary.csv",
        },
    )
    res_data = feature.run(ctx_data)
    assert res_data["status"] == "success"
    assert res_data["filename"] == "compliance_summary.csv"
    assert res_data["export_size_bytes"] > 0


def test_reports_digest_and_export_rest_api(app_client):
    """Verify REST API endpoints for daily NOC digest and unified data exports."""
    # 1. GET daily NOC digest JSON
    res_digest = app_client.get("/api/v1/reports/digest?hours=24")
    assert res_digest.status_code == 200
    digest_json = res_digest.get_json()
    assert "metrics" in digest_json
    assert "status" in digest_json

    # 2. GET daily NOC digest export (XLSX)
    res_exp_xlsx = app_client.get("/api/v1/reports/digest/export?format=xlsx")
    assert res_exp_xlsx.status_code == 200
    assert "application/vnd.openxmlformats" in res_exp_xlsx.headers.get("Content-Type", "")
    assert len(res_exp_xlsx.data) > 0

    # 3. GET daily NOC digest export (CSV)
    res_exp_csv = app_client.get("/api/v1/reports/digest/export?format=csv")
    assert res_exp_csv.status_code == 200
    assert "text/csv" in res_exp_csv.headers.get("Content-Type", "")
    assert res_exp_csv.data.startswith(b"\xef\xbb\xbf")

    # 4. POST unified data export (JSON & CSV)
    export_payload = {
        "format": "csv",
        "filename": "test_devices.csv",
        "data": [
            {"device": "TEH-AGG01", "ip": "10.10.1.1"},
            {"device": "ISF-PE01", "ip": "10.20.1.1"},
        ],
    }
    res_export = app_client.post("/api/v1/reports/export", json=export_payload)
    assert res_export.status_code == 200
    assert "test_devices.csv" in res_export.headers.get("Content-Disposition", "")
    assert res_export.data.startswith(b"\xef\xbb\xbf")

    # 5. POST streaming data export
    res_stream = app_client.post("/api/v1/reports/export/stream", json=export_payload)
    assert res_stream.status_code == 200
    assert res_stream.data.startswith(b"\xef\xbb\xbf")
    assert b"TEH-AGG01" in res_stream.data
