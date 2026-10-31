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
    ov._CACHE_DATA = None
    ov._CACHE_TIMESTAMP = 0.0

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
    assert data["recent_jobs"][0]["id"] == j1_id
    assert data["recent_jobs"][0]["status"] == "failed"

    # Fleet health has province breakdown
    assert len(data["fleet_health"]["provinces"]) >= 1
