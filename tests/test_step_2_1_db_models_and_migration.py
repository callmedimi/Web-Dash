"""Unit tests for Step 2.1: Relational DB, Schema, Models, and File Migration ETL."""
import os
import json
import csv
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import AppConfig
from backend.app.db.base import Base
from backend.app.db.session import init_db
from backend.app.models.user import User, Permission
from backend.app.models.device import Device, Credential, DeviceLock
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.models.audit import AuditLog
from backend.app.models.arp_mac import (
    ArpMacRecord,
    ArpMacSnapshot,
    ArpMacHistory,
    SiteInventory,
)
from backend.app.models.telemetry_cache import ZabbixInventoryCache
from backend.app.models.license import LicenseRenewalReport
from backend.app.db.migrate_files import (
    migrate_users_from_json,
    migrate_arp_mac_from_csv,
    migrate_unified_sites_from_csv,
    migrate_zabbix_cache_from_json,
    migrate_license_renewals_from_json,
    migrate_all_files,
)
from backend.app import create_app


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for unit tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_config_initialization(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBDASH_ENV", "testing")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_MAX_SSH_WORKERS", "35")

    cfg = AppConfig()
    assert cfg.env == "testing"
    assert cfg.max_ssh_workers == 35
    assert cfg.get_data_dir() == str(tmp_path)
    assert cfg.is_sqlite() is True


def test_user_permission_model_lifecycle(db_session):
    user = User(
        username="netadmin",
        password_hash="scrypt:mockedhash",
        role="admin",
        display_name="Network Administrator",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    perm1 = Permission(user_id=user.id, feature="alarm_clear_bulk", granted=True)
    perm2 = Permission(user_id=user.id, feature="user_management", granted=False)
    db_session.add_all([perm1, perm2])
    db_session.commit()

    queried = db_session.query(User).filter(User.username == "netadmin").first()
    assert queried is not None
    assert queried.has_permission("alarm_clear_bulk") is True
    assert queried.has_permission("user_management") is False
    assert queried.has_permission("non_existent") is False

    d = queried.to_dict()
    assert d["username"] == "netadmin"
    assert "alarm_clear_bulk" in d["features"]


def test_job_and_event_lifecycle(db_session):
    job = Job(
        type="arp_collector",
        status="running",
        mode="apply",
        created_by="secadmin",
        params={"target": "all"},
    )
    db_session.add(job)
    db_session.flush()

    task = JobTask(
        job_id=job.id,
        device_name="T-KRN-NE40-1",
        status="running",
    )
    db_session.add(task)
    db_session.flush()

    event = JobEvent(
        job_id=job.id,
        task_id=task.id,
        level="info",
        message="Connected to T-KRN-NE40-1 via SSH",
    )
    db_session.add(event)
    db_session.commit()

    assert job.id is not None
    assert len(job.tasks) == 1
    assert len(job.events) == 1
    assert job.events[0].message == "Connected to T-KRN-NE40-1 via SSH"


def test_arp_mac_record_and_snapshot_lifecycle(db_session):
    snap = ArpMacSnapshot(
        scanned_by="admin",
        total_routers=1,
        total_records=2,
        notes="Automated test snapshot",
    )
    db_session.add(snap)
    db_session.flush()

    rec1 = ArpMacRecord(
        ne_name="T-KRN-NE40-1",
        ne_ip="10.10.1.1",
        arp_ip="192.168.1.10",
        arp_mac="00e0fc112233",
        vlan="100",
        vrf="MGMT",
        arp_interface="GigabitEthernet0/1/0.100",
    )
    hist1 = ArpMacHistory(
        snapshot_id=snap.id,
        ne_name="T-KRN-NE40-1",
        ne_ip="10.10.1.1",
        arp_ip="192.168.1.10",
        arp_mac="00e0fc112233",
    )
    db_session.add_all([rec1, hist1])
    db_session.commit()

    recs = db_session.query(ArpMacRecord).filter(ArpMacRecord.arp_ip == "192.168.1.10").all()
    assert len(recs) == 1
    assert recs[0].arp_mac == "00e0fc112233"

    saved_snap = db_session.query(ArpMacSnapshot).filter(ArpMacSnapshot.id == snap.id).first()
    assert len(saved_snap.history_records) == 1


def test_migration_etl_from_files(tmp_path, db_session):
    # 1. Mock users.json
    users_file = tmp_path / "users.json"
    users_data = {
        "migrated_admin": {
            "password": "hashed_password_123",
            "role": "admin",
            "display_name": "Migrated Admin",
            "features": ["reporting", "vrf_routing"],
            "must_change_password": False,
            "is_active": True,
            "failed_logins": 0,
            "token_version": 2,
        }
    }
    users_file.write_text(json.dumps(users_data), encoding="utf-8")

    # 2. Mock arp_mac.csv
    arp_file = tmp_path / "arp_mac.csv"
    with open(arp_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ne_name", "ne_ip", "arp_ip", "arp_mac", "vlan", "vrf", "arp_interface", "mac_port", "collected_at"])
        writer.writerow(["ROUTER-A", "10.0.0.1", "172.16.0.5", "00-11-22-33-44-55", "50", "CORP", "GE0/0/1.50", "Port1", "2026-10-30T12:00:00"])
        writer.writerow(["ROUTER-B", "10.0.0.2", "172.16.0.6", "00-11-22-33-44-66", "60", "CORP", "GE0/0/2.60", "Port2", "2026-10-30T12:00:00"])

    # 3. Mock unified_sites.csv
    sites_file = tmp_path / "unified_sites.csv"
    with open(sites_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["site_code", "ip", "model", "ne_name"])
        writer.writerow(["TEH001", "10.200.1.1", "NE40E-X8", "TEH-CORE-1"])

    # 4. Mock zabbix_router_db.json
    zabbix_file = tmp_path / "zabbix_router_db.json"
    zabbix_data = {
        "routers": [
            {
                "hostid": "10050",
                "name": "ZABBIX-ROUTER-1",
                "host": "10.10.10.1",
                "group_name": "Huawei BH Routers",
                "interfaces": [{"interfaceid": "1", "ip": "10.10.10.1"}],
                "items": [{"itemid": "501", "name": "CPU Utilization", "key_": "huawei.cpu", "lastvalue": "15"}],
            }
        ]
    }
    zabbix_file.write_text(json.dumps(zabbix_data), encoding="utf-8")

    # 5. Mock license_renewals.json
    license_file = tmp_path / "license_renewals.json"
    license_data = {
        "renewals": [
            {
                "id": "lic-rep-001",
                "timestamp": "2026-10-30T10:00:00",
                "csv_file": "license_batch_1.csv",
                "report_data": [{"device": "ROUTER-A", "status": "Success"}],
            }
        ]
    }
    license_file.write_text(json.dumps(license_data), encoding="utf-8")

    # Run migrations
    users_migrated = migrate_users_from_json(db_session, str(users_file))
    assert users_migrated == 1

    arp_count, snap_id = migrate_arp_mac_from_csv(db_session, str(arp_file))
    assert arp_count == 2
    assert snap_id is not None

    sites_count = migrate_unified_sites_from_csv(db_session, str(sites_file))
    assert sites_count == 1

    zabbix_count = migrate_zabbix_cache_from_json(db_session, str(zabbix_file))
    assert zabbix_count == 1

    lic_count = migrate_license_renewals_from_json(db_session, str(license_file))
    assert lic_count == 1

    db_session.commit()

    # Verify DB contents
    user = db_session.query(User).filter(User.username == "migrated_admin").first()
    assert user is not None
    assert user.role == "admin"
    assert user.has_permission("reporting") is True

    records = db_session.query(ArpMacRecord).all()
    assert len(records) == 2

    site = db_session.query(SiteInventory).filter(SiteInventory.site_code == "TEH001").first()
    assert site.ip == "10.200.1.1"

    z_cache = db_session.query(ZabbixInventoryCache).filter(ZabbixInventoryCache.hostid == "10050").first()
    assert z_cache.name == "ZABBIX-ROUTER-1"
    assert len(z_cache.items) == 1

    lic_rep = db_session.query(LicenseRenewalReport).filter(LicenseRenewalReport.id == "lic-rep-001").first()
    assert lic_rep.csv_file == "license_batch_1.csv"

    # Test Idempotency (running second time should not fail or produce duplicate users/sites)
    assert migrate_users_from_json(db_session, str(users_file)) == 1
    assert db_session.query(User).filter(User.username == "migrated_admin").count() == 1
    assert migrate_unified_sites_from_csv(db_session, str(sites_file)) == 1
    assert db_session.query(SiteInventory).filter(SiteInventory.site_code == "TEH001").count() == 1


def test_app_health_and_ready_probes(client=None):
    test_app = create_app()
    with test_app.test_client() as c:
        res_h = c.get("/healthz")
        assert res_h.status_code == 200
        assert res_h.get_json()["status"] == "ok"

        res_r = c.get("/readyz")
        assert res_r.status_code in (200, 503)
        assert "read_only" in res_r.get_json()
