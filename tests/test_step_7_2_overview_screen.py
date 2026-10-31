"""Tests for Step 9.2: Overview Screen API and Aggregates."""
import pytest
from datetime import datetime, timezone, timedelta
from backend.app import create_app
from backend.app.models.device import Device
from backend.app.models.job import Job
from backend.app.models.config_change import ChangeRequest
from backend.app.models.license import LicenseRecord
from backend.app.extensions import get_db_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_overview.db"
    db_url = f"sqlite:///{db_file}"
    app = create_app({"TESTING": True, "DATABASE_URL": db_url})
    with app.test_client() as client:
        with app.app_context():
            yield client


def test_overview_requires_auth(client):
    """Anonymous requests to /api/v1/overview must return 401."""
    res = client.get("/api/v1/overview")
    assert res.status_code == 401


def test_overview_aggregates_and_graceful_degradation(client, monkeypatch):
    """Authenticated request returns complete aggregates even if Zabbix is unavailable."""
    # Authenticate via test user
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": "noc_operator",
            "role": "operator",
            "permissions": {"overview": True},
            "display_name": "NOC Operator",
            "must_change_password": False,
        }
        sess["user_id"] = "noc_operator"
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0

    # Seed mock data
    with get_db_session() as db:
        d1 = db.query(Device).filter(Device.name == "DEV-OV-TEH-01").first()
        if not d1:
            d1 = Device(name="DEV-OV-TEH-01", mgmt_ip="10.200.1.1", province="TEH", role="PE", enabled=True)
            db.add(d1)
            db.commit()

        # Job in last 24h (failed)
        j1 = Job(
            type="alarm_clear",
            status="failed",
            mode="dry_run",
            created_by="noc_operator",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
            summary={"reason": "SSH connection timeout"},
        )
        # Pending change request
        c1 = ChangeRequest(
            device_id=d1.id,
            creator_id="noc_operator",
            risk_level="medium",
            status="awaiting_approval",
            plan={"action": "shutdown"},
            diff="- interface GE0/1/0\n+ shutdown",
            precheck_results={},
            verification_results={},
        )
        # Expiring license
        lic1 = db.query(LicenseRecord).filter(LicenseRecord.device_id == d1.id).first()
        if not lic1:
            lic1 = LicenseRecord(
                device_id=d1.id,
                product_name="NetEngine 40E",
                days_to_expiry=15,
                is_expired=False,
                alert_level="WARN_30",
            )
            db.add(lic1)
        else:
            lic1.days_to_expiry = 15
            lic1.is_expired = False

        db.add_all([j1, c1])
        db.commit()
        j1_id = j1.id

    # Clear cache to force fresh build
    import backend.app.api.overview as ov
    ov._CACHE_STORE.clear()

    res = client.get("/api/v1/overview")
    assert res.status_code == 200
    data = res.get_json()

    assert "fleet_health" in data
    assert "needs_attention" in data
    assert "recent_jobs" in data
    assert "problems_by_severity" in data
    assert "problems_timeline" in data

    # Needs attention must capture failed job, pending change, and expiring license
    attention_ids = [item["id"] for item in data["needs_attention"]]
    assert "failed-jobs" in attention_ids
    assert "pending-changes" in attention_ids
    assert "expiring-licenses" in attention_ids

    # Recent jobs must include j1
    assert len(data["recent_jobs"]) >= 1
    recent_ids = [rj["id"] for rj in data["recent_jobs"]]
    assert j1_id in recent_ids
    j1_item = next(rj for rj in data["recent_jobs"] if rj["id"] == j1_id)
    assert j1_item["status"] == "failed"

    # Fleet health has province breakdown
    assert len(data["fleet_health"]["provinces"]) >= 1


def test_overview_host_group_filter_and_alarms(client, monkeypatch):
    """Zabbix host groups filter isolates active alarms, fleet health, and severity distribution."""
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": "noc_operator",
            "role": "operator",
            "permissions": {"overview": True},
            "display_name": "NOC Operator",
            "must_change_password": False,
        }
        sess["user_id"] = "noc_operator"
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0

    mock_fleet_result = {
        "summary": {
            "total_devices": 13,
            "monitored_devices": 13,
            "unmonitored_devices": 0,
            "available_devices": 12,
            "availability_pct": 92.3,
            "total_active_problems": 3,
            "problems_by_severity": {"Disaster": 0, "High": 1, "Average": 1, "Warning": 1, "Information": 0, "Not classified": 0},
        },
        "province_stats": [],
        "devices": [],
        "host_groups": [
            {
                "name": "Tehran_Core",
                "host_count": 5,
                "available_hosts": 4,
                "problem_count": 2,
                "severity_counts": {"High": 1, "Warning": 1},
            },
            {
                "name": "Shiraz_Agg",
                "host_count": 8,
                "available_hosts": 8,
                "problem_count": 1,
                "severity_counts": {"Average": 1},
            },
        ],
        "active_problems": [
            {
                "event_id": "1001",
                "host_id": "10101",
                "host_name": "DEV-TEH-01",
                "device_name": "DEV-TEH-01",
                "name": "BGP Peer Down (AS64512)",
                "severity": 4,
                "severity_name": "High",
                "clock": 1700000000,
                "clock_iso": "2023-11-14T22:13:20",
                "acknowledged": False,
                "groups": ["Tehran_Core"],
                "tags": {"peer": "10.0.0.1"},
            },
            {
                "event_id": "1002",
                "host_id": "10102",
                "host_name": "DEV-TEH-02",
                "device_name": "DEV-TEH-02",
                "name": "Optical Power Low on GE0/1/0",
                "severity": 2,
                "severity_name": "Warning",
                "clock": 1700000100,
                "clock_iso": "2023-11-14T22:15:00",
                "acknowledged": True,
                "groups": ["Tehran_Core"],
                "tags": {"interface": "GE0/1/0"},
            },
            {
                "event_id": "1003",
                "host_id": "10103",
                "host_name": "DEV-SHZ-01",
                "device_name": "DEV-SHZ-01",
                "name": "Power Module 2 Redundancy Lost",
                "severity": 3,
                "severity_name": "Average",
                "clock": 1700000200,
                "clock_iso": "2023-11-14T22:16:40",
                "acknowledged": False,
                "groups": ["Shiraz_Agg"],
                "tags": {"module": "PWR-2"},
            },
        ],
    }

    import backend.app.api.overview as ov
    monkeypatch.setattr(ov.MonitoringHubService, "get_fleet_health", lambda *a, **kw: mock_fleet_result)
    ov._CACHE_STORE.clear()

    # 1. Unfiltered request returns all host groups and all problems
    res_all = client.get("/api/v1/overview")
    assert res_all.status_code == 200
    data_all = res_all.get_json()
    assert data_all["selected_group"] == "all"
    assert len(data_all["host_groups"]) == 2
    assert len(data_all["group_problems"]) == 3
    assert data_all["problems_by_severity"]["high"] == 1
    assert data_all["problems_by_severity"]["warning"] == 1
    assert data_all["problems_by_severity"]["average"] == 1

    # 2. Filtered request by "Tehran_Core" isolates Tehran_Core alarms and stats
    res_filtered = client.get("/api/v1/overview?group=Tehran_Core")
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.get_json()
    assert data_filtered["selected_group"] == "Tehran_Core"
    assert len(data_filtered["group_problems"]) == 2
    for prob in data_filtered["group_problems"]:
        assert "Tehran_Core" in prob["groups"]

    # Tehran_Core has 1 High, 1 Warning, and 0 Average (Shiraz problem filtered out)
    assert data_filtered["problems_by_severity"]["high"] == 1
    assert data_filtered["problems_by_severity"]["warning"] == 1
    assert data_filtered["problems_by_severity"]["average"] == 0

    # Fleet health stats tailored to Tehran_Core (5 total, 4 available)
    assert data_filtered["fleet_health"]["total_devices"] == 5
    assert data_filtered["fleet_health"]["available_devices"] == 4
    assert data_filtered["fleet_health"]["availability_pct"] == 80.0

