"""Unit and integration tests for Step 4.3: Config Backup, Normalization, Encryption, and Diff Service.

Verifies:
1. Normalization: strips pagination artifacts, volatile timestamps, prompts, trailing spaces.
2. SHA-256 checksumming & deduplication (identical config does not create new row, updates last_checked_at).
3. Secret protection: configuration content encrypted at rest via Fernet vault key.
4. Retention policy: preserves latest 30 snapshots + 1 per month up to 12 months, prunes redundant rows.
5. Unified and structured diff generation between snapshots.
6. Execution via ConfigBackupHandler on JobEngine.
7. REST API: GET /api/v1/devices/<id>/configs, GET /configs/<id>, GET /configs/diff.
"""
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.config_backup import (
    normalize_vrp_config,
    compute_config_hash,
    encrypt_config_content,
    decrypt_config_content,
    generate_config_diff,
    ConfigBackupService,
)
from backend.app.models.config_change import ConfigSnapshot
from backend.app.models.device import Device
from backend.app.jobs.handlers.config_backup import ConfigBackupHandler
from backend.app.jobs.worker import TaskContext
from backend.app.jobs.engine import JobEngine
from backend.app.db.base import Base
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def setup_vault_env(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv("WEBDASH_VAULT_KEY", test_key)
    monkeypatch.setenv("TESTING", "1")


SAMPLE_VRP_CONFIG_RAW = """
# Current configuration: 2026-10-30 18:22:15+03:30
# Configuration generated on Huawei VRP V800R012
# Info: Current terminal time: 2026-10-30 18:22:15
sysname NE-CORE-01
#
interface GigabitEthernet0/1/0
 description Uplink-to-Provider
 ip address 192.168.1.1 255.255.255.252
#
  ---- More ----
# Last physical up time: 2026-10-25 09:12:00
interface GigabitEthernet0/1/1
 shutdown
#
<NE-CORE-01>
"""

SAMPLE_VRP_CONFIG_V2 = """
# Current configuration: 2026-10-31 09:00:00+03:30
sysname NE-CORE-01
#
interface GigabitEthernet0/1/0
 description Uplink-to-Provider-Renamed
 ip address 192.168.1.1 255.255.255.252
#
interface GigabitEthernet0/1/1
 undo shutdown
 description Customer-Access
#
"""


def test_normalize_vrp_config():
    """Verify normalization strips pagination, prompts, and volatile timestamps."""
    normalized = normalize_vrp_config(SAMPLE_VRP_CONFIG_RAW)
    assert "---- More ----" not in normalized
    assert "Last physical up time" not in normalized
    assert "Current configuration" not in normalized
    assert "<NE-CORE-01>" not in normalized
    assert "sysname NE-CORE-01" in normalized
    assert "interface GigabitEthernet0/1/0" in normalized
    assert "ip address 192.168.1.1 255.255.255.252" in normalized


def test_fernet_encryption_and_decryption_at_rest():
    """Verify secrets and configuration content are encrypted with Fernet."""
    plain = "sysname TEST-ROUTER\nsnmp-agent community read public123\n"
    encrypted = encrypt_config_content(plain)
    assert encrypted != plain
    assert "snmp-agent community" not in encrypted

    decrypted = decrypt_config_content(encrypted)
    assert decrypted == plain


def test_generate_config_diff():
    """Verify unified diff text and structured hunks calculation."""
    before = "interface GE0/1/0\n shutdown\n"
    after = "interface GE0/1/0\n undo shutdown\n description NewLink\n"

    diff = generate_config_diff(before, after)
    assert diff["changed"] is True
    assert diff["additions"] == 2
    assert diff["deletions"] == 1
    assert "- shutdown" in diff["unified_diff"]
    assert "+ undo shutdown" in diff["unified_diff"]

    types = [h["type"] for h in diff["hunks"]]
    assert "delete" in types
    assert "add" in types


def test_config_backup_service_deduplication():
    """Verify deduplication: unchanged configuration updates last_checked_at without inserting new row."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.0.0.1")
    session.add(dev)
    session.commit()

    # 1. Initial backup
    snap1, is_new1 = ConfigBackupService.create_snapshot(session, dev.id, SAMPLE_VRP_CONFIG_RAW)
    assert is_new1 is True
    assert snap1.id is not None
    assert snap1.sha256 is not None
    snap1_id = snap1.id
    snap1_sha = snap1.sha256

    # 2. Second backup with identical content (even with different volatile timestamps)
    raw_v1_different_time = SAMPLE_VRP_CONFIG_RAW.replace("2026-10-30", "2026-10-31")
    snap2, is_new2 = ConfigBackupService.create_snapshot(session, dev.id, raw_v1_different_time)
    assert is_new2 is False
    assert snap2.id == snap1_id
    assert snap2.sha256 == snap1_sha
    assert snap2.last_checked_at is not None

    count = session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert count == 1

    # 3. Third backup with changed content
    snap3, is_new3 = ConfigBackupService.create_snapshot(session, dev.id, SAMPLE_VRP_CONFIG_V2)
    assert is_new3 is True
    assert snap3.id != snap1_id
    assert snap3.sha256 != snap1_sha

    count2 = session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    assert count2 == 2


def test_config_backup_retention_pruning():
    """Verify retention policy keeps latest 30 snapshots + 1/month up to 12 months."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.0.0.1")
    session.add(dev)
    session.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Insert 35 snapshots spaced 1 day apart
    for i in range(35):
        s = ConfigSnapshot(
            device_id=dev.id,
            kind="running",
            sha256=f"hash_{i}",
            content_encrypted_or_text="enc",
            taken_at=now - timedelta(days=i),
        )
        session.add(s)
    session.commit()

    # Total before pruning: 35
    assert session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count() == 35

    # Prune: keep 30 latest
    deleted = ConfigBackupService.prune_snapshots(session, device_id=dev.id, keep_recent_count=30)
    session.commit()

    remaining = session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev.id).count()
    # 30 recent kept + 1 per older calendar month
    assert remaining <= 32
    assert deleted > 0


def test_config_backup_handler_execution():
    """Verify ConfigBackupHandler executes on JobEngine and saves snapshot."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="NE-CORE-01", mgmt_ip="10.10.10.1")
    session.add(dev)
    session.commit()

    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.__exit__.return_value = False
    fake_session.run.return_value = SAMPLE_VRP_CONFIG_RAW

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "NE-CORE-01"
    ctx.session = session
    ctx.params = {"kind": "running"}
    ctx.job_id = "backup-job-123"

    res = ConfigBackupHandler.run_task(ctx, session=fake_session)
    assert res["status"] == "created"
    assert res["is_new"] is True
    assert res["device_name"] == "NE-CORE-01"

    # Verify snapshot in DB
    snap = session.query(ConfigSnapshot).filter(ConfigSnapshot.id == res["snapshot_id"]).first()
    assert snap is not None
    assert snap.device_id == dev.id


def test_diff_snapshots_between_two_versions():
    """Verify diff_snapshots produces unified diff between two snapshot IDs."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.0.0.1")
    session.add(dev)
    session.commit()

    s1, _ = ConfigBackupService.create_snapshot(session, dev.id, SAMPLE_VRP_CONFIG_RAW)
    s2, _ = ConfigBackupService.create_snapshot(session, dev.id, SAMPLE_VRP_CONFIG_V2)

    diff = ConfigBackupService.diff_snapshots(session, from_snapshot_id=s1.id, to_snapshot_id=s2.id)
    assert diff is not None
    assert diff["changed"] is True
    assert "Uplink-to-Provider-Renamed" in diff["unified_diff"]
    assert diff["from_snapshot"]["id"] == s1.id
    assert diff["to_snapshot"]["id"] == s2.id


def test_job_engine_has_config_backup_handler():
    """Verify JobEngine has config_backup handler registered."""
    engine = JobEngine(max_workers=1)
    assert "config_backup" in engine._handlers
    assert engine._handlers["config_backup"] == ConfigBackupHandler.run_task


def test_configs_rest_api(monkeypatch):
    """Verify REST API: list configs, get config with content, diff configs, trigger backup."""
    from backend.app import create_app
    from backend.app.db.session import get_db_session
    import auth

    test_pass = "ComplexSecret!987654"
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", test_pass)

    app = create_app({"TESTING": True})
    client = app.test_client()

    auth.clear_all_rate_limits()
    auth._load_users()
    u = auth.get_user("admin")
    if not u:
        auth.create_user("admin", test_pass, role="god")
    auth.update_user("admin", {"password": test_pass, "must_change_password": False, "is_active": True})

    login_res = client.post("/login", json={"username": "admin", "password": test_pass})
    assert login_res.status_code == 200
    csrf_token = login_res.get_json().get("csrf_token")
    headers = {"X-CSRF-Token": csrf_token}

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.name == "API-ROUTER").first()
        if not dev:
            dev = Device(name="API-ROUTER", mgmt_ip="10.20.30.40")
            session.add(dev)
            session.commit()
        dev_id = dev.id

        session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev_id).delete()
        session.commit()

        s1, _ = ConfigBackupService.create_snapshot(session, dev_id, SAMPLE_VRP_CONFIG_RAW)
        s2, _ = ConfigBackupService.create_snapshot(session, dev_id, SAMPLE_VRP_CONFIG_V2)
        s1_id = s1.id
        s2_id = s2.id

    # 1. List configs
    res_list = client.get(f"/api/v1/devices/{dev_id}/configs")
    assert res_list.status_code == 200
    data_list = res_list.get_json()
    assert len(data_list) == 2

    # 2. Get single config with decrypted content
    res_get = client.get(f"/api/v1/devices/{dev_id}/configs/{s1_id}")
    assert res_get.status_code == 200
    data_get = res_get.get_json()
    assert "content" in data_get
    assert "sysname NE-CORE-01" in data_get["content"]

    # 3. Diff configs
    res_diff = client.get(f"/api/v1/devices/{dev_id}/configs/diff?from={s1_id}&to={s2_id}")
    assert res_diff.status_code == 200
    data_diff = res_diff.get_json()
    assert data_diff["changed"] is True
    assert "Uplink-to-Provider-Renamed" in data_diff["unified_diff"]
    assert len(data_diff["hunks"]) > 0

    # 4. Trigger backup endpoint
    res_backup = client.post(f"/api/v1/devices/{dev_id}/configs/backup", json={"kind": "running"}, headers=headers)
    assert res_backup.status_code == 202
    data_backup = res_backup.get_json()
    assert data_backup["status"] == "queued"
    assert "job_id" in data_backup
