"""Integration and Acceptance tests for Step 9.10: Configs & Compliance Screen.
Tests configuration snapshots, timeline, diff viewer, attachment downloads, and compliance matrix.
"""
import pytest
import uuid
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.device import Device
from backend.app.services.config_backup import ConfigBackupService

CONFIG_A = """#
sysname PE-CORE-01
#
stelnet server enable
ntp-service unicast-server 10.10.10.1
#
interface GigabitEthernet0/1/0
 description Trunk-to-Aggregation
 ip address 10.1.1.1 255.255.255.252
#
return
"""

CONFIG_B = """#
sysname PE-CORE-01
#
stelnet server enable
ntp-service unicast-server 10.10.10.1
ntp-service unicast-server 10.10.10.2
#
interface GigabitEthernet0/1/0
 description Trunk-to-Aggregation-Upgraded
 ip address 10.1.1.1 255.255.255.252
#
return
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / f"webdash_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WEBDASH_DB_URL", db_url)
    monkeypatch.setenv("WEBDASH_SECRET_KEY", "test-secret-phase7-step10")
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        with app.app_context():
            yield client


def _login(client, username="config_admin", role="admin"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "username": username,
            "role": role,
            "permissions": {"configs": True, "compliance": True, "admin": True},
            "display_name": username.title(),
            "must_change_password": False,
        }
        sess["user_id"] = username
        sess["csrf_token"] = "valid_csrf"
        sess["last_seen"] = 9999999999.0


def test_configs_screen_snapshots_and_diff(client):
    _login(client)

    dev_name = f"PE-CFG-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create a device and store two config snapshots
    with get_db_session() as db:
        dev = Device(
            name=dev_name,
            mgmt_ip="10.50.1.1",
            vendor="huawei",
            province="TEH",
            role="PE",
            enabled=True,
        )
        db.add(dev)
        db.commit()
        dev_id = dev.id

        snap1, _ = ConfigBackupService.create_snapshot(
            db_session=db,
            device_id=dev_id,
            config_text=CONFIG_A,
            kind="running",
        )
        snap2, _ = ConfigBackupService.create_snapshot(
            db_session=db,
            device_id=dev_id,
            config_text=CONFIG_B,
            kind="running",
        )
        snap1_id = snap1.id
        snap2_id = snap2.id

    # 2. Query list of snapshots
    resp = client.get(f"/api/v1/devices/{dev_id}/configs")
    assert resp.status_code == 200
    snaps = resp.get_json()
    assert len(snaps) >= 2
    snap_ids = [s["id"] for s in snaps]
    assert snap1_id in snap_ids
    assert snap2_id in snap_ids

    # 3. Query single snapshot details and decrypted content
    resp_detail = client.get(f"/api/v1/devices/{dev_id}/configs/{snap1_id}")
    assert resp_detail.status_code == 200
    detail = resp_detail.get_json()
    assert "content" in detail
    assert "PE-CORE-01" in detail["content"]

    # 4. Query diff between snap1 and snap2
    resp_diff = client.get(f"/api/v1/devices/{dev_id}/configs/diff?from={snap1_id}&to={snap2_id}")
    assert resp_diff.status_code == 200
    diff_res = resp_diff.get_json()
    assert "unified_diff" in diff_res
    assert "additions" in diff_res or "stats" in diff_res
    additions = diff_res.get("additions", diff_res.get("stats", {}).get("additions", 0))
    assert additions >= 1

    # 5. Download snapshot configuration attachment
    resp_dl = client.get(f"/api/v1/devices/{dev_id}/configs/{snap1_id}/download")
    assert resp_dl.status_code == 200
    assert "attachment" in resp_dl.headers.get("Content-Disposition", "")
    assert b"PE-CORE-01" in resp_dl.data


def test_compliance_screen_matrix_and_rules(client):
    _login(client)

    # 1. Query fleet compliance dashboard
    resp = client.get("/api/v1/compliance/dashboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "summary" in data
    assert "rules_breakdown" in data or "rules" in data
    assert "province_breakdown" in data or "province_stats" in data
    summary = data["summary"]
    assert "overall_compliance_pct" in summary or "compliance_pct" in summary

    # 2. Query compliance rules endpoint
    resp_rules = client.get("/api/v1/compliance/rules")
    assert resp_rules.status_code == 200
    rules_data = resp_rules.get_json()
    assert "rules" in rules_data
    assert len(rules_data["rules"]) >= 3
    rule_ids = [r["id"] for r in rules_data["rules"]]
    assert "SEC-001" in rule_ids
