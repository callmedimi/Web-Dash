"""Comprehensive tests for Phase 5 Step 5.10: Config Backup, Diff & Compliance."""
import os
import yaml
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.models.job import Job
from backend.app.models.config_change import ConfigSnapshot, ChangeRequest
from backend.app.services.config_backup import (
    ConfigBackupService,
    normalize_vrp_config,
    compute_config_hash,
    encrypt_config_content,
    decrypt_config_content,
    generate_config_diff,
)
from backend.app.services.compliance import (
    evaluate_compliance_on_config,
    evaluate_device_compliance,
    evaluate_fleet_compliance,
    load_compliance_rules,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


# Sample VRP Configurations for Testing
SAMPLE_VRP_CONFIG_A = """
#
!Software Version V800R012C10SPC300
#
# Last physical up time: 2026-10-30 14:22:10
# Current configuration generated on 2026-10-31 03:00:00
# Info: Current terminal time: 2026-10-31 03:00:01
sysname TEH-AGG01
#
stelnet server enable
ssh user noc_admin authentication-type password
#
ntp-service unicast-server 10.255.255.10
#
snmp-agent sys-info version v3
snmp-agent group v3 noc_sec_group privacy
#
interface GigabitEthernet0/1/0
 description Primary-Uplink-To-CR01
 ip address 10.10.10.1 255.255.255.252
#
interface GigabitEthernet0/2/0
 description Access-Facing-Trunk
 shutdown
#
interface Loopback0
 ip address 10.255.0.1 255.255.255.255
#
return
<TEH-AGG01>
"""

SAMPLE_VRP_CONFIG_B = """
#
!Software Version V800R012C10SPC300
#
# Last physical up time: 2026-10-31 08:15:00
# Current configuration generated on 2026-10-31 09:30:00
sysname TEH-AGG01
#
stelnet server enable
ssh user noc_admin authentication-type password
#
ntp-service unicast-server 10.255.255.10
ntp-service unicast-server 10.255.255.11
#
snmp-agent sys-info version v3
snmp-agent group v3 noc_sec_group privacy
#
interface GigabitEthernet0/1/0
 description Primary-Uplink-To-CR01-Upgraded
 ip address 10.10.10.1 255.255.255.252
#
interface GigabitEthernet0/2/0
 description Access-Facing-Trunk
 undo shutdown
#
interface GigabitEthernet0/3/0
 ip address 10.10.20.1 255.255.255.252
#
interface Loopback0
 ip address 10.255.0.1 255.255.255.255
#
return
---- More ----
"""

NON_COMPLIANT_VRP_CONFIG = """
#
sysname BAD-ROUTER01
#
telnet server enable
#
snmp-agent sys-info version v2c
snmp-agent community read public
#
interface GigabitEthernet0/1/0
 ip address 192.168.1.1 255.255.255.0
#
return
"""


@pytest.fixture
def test_db_session(tmp_path, monkeypatch):
    """Provide a fresh SQLite test session with Fernet test vault key."""
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))

    db_file = tmp_path / "test_config_compliance.db"
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
    db_file = tmp_path / "test_app_configs.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_cfg", role="admin", password_hash="dummy_hash")
            s.add(admin)

            dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
            s.add(dev)
            s.commit()

            # Add two snapshots
            ConfigBackupService.create_snapshot(s, device_id=dev.id, config_text=SAMPLE_VRP_CONFIG_A, kind="running")
            ConfigBackupService.create_snapshot(s, device_id=dev.id, config_text=SAMPLE_VRP_CONFIG_B, kind="running")

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_cfg",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_vrp_config_normalization():
    """Verify that volatile headers, pagination artifacts, and prompts are stripped deterministically."""
    norm = normalize_vrp_config(SAMPLE_VRP_CONFIG_A)
    assert "# Last physical up time:" not in norm
    assert "# Current configuration generated on" not in norm
    assert "# Info: Current terminal time:" not in norm
    assert "<TEH-AGG01>" not in norm
    assert "stelnet server enable" in norm
    assert "interface GigabitEthernet0/1/0" in norm
    assert "description Primary-Uplink-To-CR01" in norm

    norm_b = normalize_vrp_config(SAMPLE_VRP_CONFIG_B)
    assert "---- More ----" not in norm_b
    assert "undo shutdown" in norm_b


def test_snapshot_hashing_and_deduplication(test_db_session):
    """Verify that identical configs do not create duplicate DB rows, but update last_checked_at."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    # 1. First snapshot
    snap1, is_new1 = ConfigBackupService.create_snapshot(
        test_db_session, device_id=dev.id, config_text=SAMPLE_VRP_CONFIG_A, kind="running"
    )
    assert is_new1 is True
    assert snap1.sha256 == compute_config_hash(normalize_vrp_config(SAMPLE_VRP_CONFIG_A))
    first_snap_id = snap1.id

    # Content encrypted at rest
    assert snap1.content_encrypted_or_text != normalize_vrp_config(SAMPLE_VRP_CONFIG_A)
    # But decrypted cleanly
    decrypted = ConfigBackupService.get_snapshot_decrypted(test_db_session, snap1.id)
    assert "sysname TEH-AGG01" in decrypted

    # 2. Duplicate snapshot with different volatile timestamp comments
    diff_timestamp_config = SAMPLE_VRP_CONFIG_A.replace("2026-10-31 03:00:00", "2026-10-31 11:22:33")
    snap2, is_new2 = ConfigBackupService.create_snapshot(
        test_db_session, device_id=dev.id, config_text=diff_timestamp_config, kind="running"
    )
    assert is_new2 is False
    assert snap2.id == first_snap_id

    # Check total count in DB remains 1
    count = test_db_session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert count == 1

    # 3. Modified config creates new snapshot
    snap3, is_new3 = ConfigBackupService.create_snapshot(
        test_db_session, device_id=dev.id, config_text=SAMPLE_VRP_CONFIG_B, kind="running"
    )
    assert is_new3 is True
    assert snap3.id != first_snap_id
    count2 = test_db_session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert count2 == 2


def test_snapshot_retention_pruning(test_db_session):
    """Verify retention policy keeps 30 recent snapshots + 1/month up to 12 months, deleting extras."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Insert 35 snapshots:
    # 25 in current month
    # 10 spanning older months
    for i in range(25):
        snap = ConfigSnapshot(
            device_id=dev.id,
            kind="running",
            sha256=f"hash_{i}",
            content_encrypted_or_text=f"config_{i}",
            taken_at=now - timedelta(hours=i),
        )
        test_db_session.add(snap)

    for m in range(1, 15):
        snap = ConfigSnapshot(
            device_id=dev.id,
            kind="running",
            sha256=f"hash_old_{m}",
            content_encrypted_or_text=f"config_old_{m}",
            taken_at=now - timedelta(days=35 * m),
        )
        test_db_session.add(snap)

    test_db_session.commit()
    total_before = test_db_session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert total_before == 39

    # Prune with keep_recent_count=20, max_monthly_history=10
    pruned = ConfigBackupService.prune_snapshots(
        test_db_session, device_id=dev.id, kind="running", keep_recent_count=20, max_monthly_history=10
    )
    test_db_session.commit()
    assert pruned > 0

    total_after = test_db_session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert total_after <= 30


def test_config_diff_unified_and_hunks(test_db_session):
    """Verify diff calculation produces unified diff and structured add/delete/context hunks."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    snap_a, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_A)
    snap_b, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_B)

    diff_res = ConfigBackupService.diff_snapshots(test_db_session, snap_a.id, snap_b.id)
    assert diff_res is not None
    assert diff_res["changed"] is True
    assert diff_res["additions"] > 0
    assert diff_res["deletions"] > 0
    assert "Primary-Uplink-To-CR01-Upgraded" in diff_res["unified_diff"]
    assert any(h["type"] == "add" for h in diff_res["hunks"])
    assert any(h["type"] == "delete" for h in diff_res["hunks"])


def test_device_timeline_with_job_and_change_correlation(test_db_session):
    """Verify timeline correlates snapshots with Job and ChangeRequest metadata ('who/what changed')."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    # Baseline snapshot (no job)
    snap1, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_A)

    # Job & Change Request
    job = Job(id="job-1001", type="config_apply", status="succeeded", created_by="noc_operator", mode="apply")
    test_db_session.add(job)
    test_db_session.commit()

    cr = ChangeRequest(
        id="cr-501",
        job_id="job-1001",
        device_id=dev.id,
        creator_id="noc_operator",
        approver_id="noc_lead",
        risk_level="medium",
        status="verified",
    )
    test_db_session.add(cr)
    test_db_session.commit()

    # Second snapshot linked to job
    snap2, _ = ConfigBackupService.create_snapshot(
        test_db_session, dev.id, SAMPLE_VRP_CONFIG_B, job_id=job.id
    )

    timeline = ConfigBackupService.get_device_timeline(test_db_session, dev.id)
    assert len(timeline) == 2

    # Newest entry (snap2)
    entry_new = timeline[0]
    assert entry_new["snapshot_id"] == snap2.id
    assert entry_new["job_id"] == "job-1001"
    assert entry_new["job"]["created_by"] == "noc_operator"
    assert "noc_lead" in entry_new["who_changed"]
    assert "changed" in entry_new["what_changed"]
    assert entry_new["diff_summary"]["changed"] is True

    # Oldest entry (snap1)
    entry_old = timeline[1]
    assert entry_old["snapshot_id"] == snap1.id
    assert entry_old["who_changed"] == "system/scheduled"
    assert entry_old["what_changed"] == "Initial configuration baseline"


def test_config_download_metadata_and_decrypted_content(test_db_session):
    """Verify download metadata formatting and decrypted payload."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    snap, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_A, kind="running")

    dl_data = ConfigBackupService.get_download_data(test_db_session, dev.id, snap.id)
    assert dl_data is not None
    assert dl_data["filename"].startswith("TEH-AGG01_running_")
    assert dl_data["filename"].endswith(".cfg")
    assert "sysname TEH-AGG01" in dl_data["content"]
    assert dl_data["mimetype"] == "text/plain; charset=utf-8"


def test_compliance_engine_builtin_rules():
    """Verify built-in rule evaluation (SSH, NTP, SNMPv3, Interface descriptions)."""
    # 1. Compliant Config
    norm_a = normalize_vrp_config(SAMPLE_VRP_CONFIG_A)
    results_a = evaluate_compliance_on_config(norm_a)
    assert all(r["status"] == "PASS" for r in results_a)

    # 2. Non-compliant Config
    norm_bad = normalize_vrp_config(NON_COMPLIANT_VRP_CONFIG)
    results_bad = evaluate_compliance_on_config(norm_bad)
    sec001 = next(r for r in results_bad if r["rule_id"] == "SEC-001")
    assert sec001["status"] == "FAIL"
    assert "telnet" in sec001["details"].lower()

    sec002 = next(r for r in results_bad if r["rule_id"] == "SEC-002")
    assert sec002["status"] == "FAIL"
    assert "snmp-agent" in sec002["details"].lower()

    ops001 = next(r for r in results_bad if r["rule_id"] == "OPS-001")
    assert ops001["status"] == "FAIL"

    ops002 = next(r for r in results_bad if r["rule_id"] == "OPS-002")
    assert ops002["status"] == "FAIL"
    assert "GigabitEthernet0/1/0" in ops002["details"]


def test_custom_yaml_compliance_rule(tmp_path):
    """Verify loading custom YAML compliance rules from DATA_DIR/compliance."""
    rules_dir = tmp_path / "compliance"
    rules_dir.mkdir(parents=True, exist_ok=True)

    custom_rule = [
        {
            "id": "SEC-CUST-01",
            "name": "Header Banner Required",
            "severity": "medium",
            "must_contain": [r"(?i)\bheader\s+shell\s+information\b"],
            "must_not_contain": [],
            "remediation_hint": "Configure authorized access banner.",
        }
    ]
    rule_file = rules_dir / "banner.yml"
    with open(rule_file, "w", encoding="utf-8") as f:
        yaml.dump(custom_rule, f)

    rules = load_compliance_rules(rules_dir=str(rules_dir))
    assert any(r["id"] == "SEC-CUST-01" for r in rules)

    # Test evaluation with custom rule
    eval_res = evaluate_compliance_on_config(SAMPLE_VRP_CONFIG_A, rules=rules)
    cust_res = next(r for r in eval_res if r["rule_id"] == "SEC-CUST-01")
    assert cust_res["status"] == "FAIL"


def test_fleet_compliance_calculation_and_province_breakdown(test_db_session):
    """Verify fleet compliance summary, per-rule % and per-province % breakdown."""
    dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
    dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", role="PE", province="ISF", enabled=True)
    dev3 = Device(name="KHR-PE01", mgmt_ip="10.30.1.1", role="PE", province="KHR", enabled=True)
    test_db_session.add_all([dev1, dev2, dev3])
    test_db_session.commit()

    # dev1 is compliant
    ConfigBackupService.create_snapshot(test_db_session, dev1.id, SAMPLE_VRP_CONFIG_A)
    # dev2 is non-compliant
    ConfigBackupService.create_snapshot(test_db_session, dev2.id, NON_COMPLIANT_VRP_CONFIG)
    # dev3 has no snapshot (unbacked)

    fleet = evaluate_fleet_compliance(test_db_session)
    summary = fleet["summary"]
    assert summary["total_devices"] == 3
    assert summary["evaluated_devices"] == 2
    assert summary["compliant_devices"] == 1
    assert summary["non_compliant_devices"] == 1
    assert summary["unbacked_devices"] == 1
    assert summary["overall_compliance_pct"] == 50.0

    # Rules breakdown
    sec001 = next(r for r in fleet["rules_breakdown"] if r["rule_id"] == "SEC-001")
    assert sec001["passed_devices"] == 1
    assert sec001["failed_devices"] == 1
    assert sec001["compliance_pct"] == 50.0

    # Province breakdown
    teh_prov = next(p for p in fleet["province_breakdown"] if p["province"] == "TEH")
    assert teh_prov["compliance_pct"] == 100.0

    isf_prov = next(p for p in fleet["province_breakdown"] if p["province"] == "ISF")
    assert isf_prov["compliance_pct"] == 0.0

    # Test filtering by province
    fleet_teh = evaluate_fleet_compliance(test_db_session, province="TEH")
    assert fleet_teh["summary"]["total_devices"] == 1
    assert fleet_teh["summary"]["overall_compliance_pct"] == 100.0


def test_catalog_feature_config_compliance(test_db_session):
    """Verify execution of ConfigComplianceFeature via catalog registry."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    snap_a, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_A)
    snap_b, _ = ConfigBackupService.create_snapshot(test_db_session, dev.id, SAMPLE_VRP_CONFIG_B)

    feature = feature_registry.get("config_compliance")
    assert feature is not None

    # 1. Timeline action
    ctx_timeline = FeatureContext(
        db_session=test_db_session,
        params={"action": "timeline", "device_id": dev.id},
    )
    res_timeline = feature.run(ctx_timeline)
    assert res_timeline["status"] == "success"
    assert res_timeline["count"] == 2

    # 2. Diff action
    ctx_diff = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "diff",
            "from_snapshot_id": snap_a.id,
            "to_snapshot_id": snap_b.id,
        },
    )
    res_diff = feature.run(ctx_diff)
    assert res_diff["status"] == "success"
    assert res_diff["diff"]["changed"] is True

    # 3. Compliance device action
    ctx_dev = FeatureContext(
        db_session=test_db_session,
        params={"action": "compliance_device", "device_id": dev.id},
    )
    res_dev = feature.run(ctx_dev)
    assert res_dev["status"] == "success"
    assert res_dev["report"]["compliance_score"] > 0

    # 4. Compliance fleet action
    ctx_fleet = FeatureContext(
        db_session=test_db_session,
        params={"action": "compliance_fleet"},
    )
    res_fleet = feature.run(ctx_fleet)
    assert res_fleet["status"] == "success"
    assert "summary" in res_fleet

    # 5. Download action
    ctx_dl = FeatureContext(
        db_session=test_db_session,
        params={"action": "download", "device_id": dev.id, "snapshot_id": snap_a.id},
    )
    res_dl = feature.run(ctx_dl)
    assert res_dl["status"] == "success"
    assert res_dl["download"]["filename"].endswith(".cfg")


def test_configs_and_compliance_rest_api(app_client):
    """Verify REST API endpoints for configs timeline, diff, download, and compliance dashboard."""
    # 1. Timeline endpoint
    t_res = app_client.get("/api/v1/devices/1/configs/timeline")
    assert t_res.status_code == 200
    t_data = t_res.get_json()
    assert t_data["count"] >= 2
    assert "timeline" in t_data

    # 2. Diff endpoint
    diff_res = app_client.get("/api/v1/devices/1/configs/diff")
    assert diff_res.status_code == 200
    d_data = diff_res.get_json()
    assert d_data["changed"] is True
    assert "hunks" in d_data

    # 3. Download endpoint
    snap_id = t_data["timeline"][0]["snapshot_id"]
    dl_res = app_client.get(f"/api/v1/devices/1/configs/{snap_id}/download")
    assert dl_res.status_code == 200
    assert "attachment" in dl_res.headers.get("Content-Disposition", "")
    assert b"sysname TEH-AGG01" in dl_res.data

    # 4. Compliance dashboard endpoint
    dash_res = app_client.get("/api/v1/compliance/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()
    assert "summary" in dash_data
    assert "rules_breakdown" in dash_data
    assert "province_breakdown" in dash_data

    # 5. Compliance rules endpoint
    rules_res = app_client.get("/api/v1/compliance/rules")
    assert rules_res.status_code == 200
    assert rules_res.get_json()["count"] >= 4

    # 6. Single device compliance endpoint
    dev_comp_res = app_client.get("/api/v1/compliance/device/1")
    assert dev_comp_res.status_code == 200
    assert "compliance_score" in dev_comp_res.get_json()
