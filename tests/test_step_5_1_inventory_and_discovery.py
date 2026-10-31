"""Tests for Step 5.1: Inventory & Discovery, Target Sets, Health Badges, and Feature Catalog."""
import io
import os
import pytest
from datetime import datetime
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.device import Device, TargetSet
from backend.app.models.user import User
from backend.app.services.inventory import (
    InventoryService,
    derive_province_and_site,
    derive_os_family,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite in-memory/file session for testing."""
    db_file = tmp_path / "test_inventory.db"
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
    db_file = tmp_path / "test_app_inventory.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_test", role="admin", password_hash="argon2_fake_hash")
            s.add(admin)
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_test",
                "role": "admin",
                "id": 1,
            }
        yield client


SAMPLE_NMS_CSV = """NE Name,NE IP Address,NE Type (MPU Type),Software Version,LSR ID,ESN
TEH-MHD-PE01_TH,10.100.1.1,NetEngine 40E,VRP (R) Software, Version 8.180,10.100.1.1,2102350AAA1011111111
ISF-CR01_IS,10.100.2.1,NetEngine 8000,VRP (R) Software, Version 8.210,10.100.2.1,2102350AAA1022222222
KRM-AGG01_KM,10.100.3.1,AR2200,VRP (R) Software, Version 5.170,10.100.3.1,2102350AAA1033333333
"""


def test_derive_province_and_site():
    """Verify naming convention parser extracts province, site, and role."""
    prov, site, role = derive_province_and_site("TEH-MHD-PE01_TH")
    assert prov == "TH"
    assert site == "TEH-MHD"
    assert role == "PE"

    prov2, site2, role2 = derive_province_and_site("ISF-P02_IS")
    assert prov2 == "IS"
    assert site2 == "ISF"
    assert role2 == "P"

    prov3, site3, role3 = derive_province_and_site("KERMAN-BRAS01_KM")
    assert prov3 == "KM"
    assert role3 == "BRAS"

    prov4, site4, role4 = derive_province_and_site("UNKNOWN-ROUTER")
    assert prov4 is None
    assert role4 is None


def test_derive_os_family():
    """Verify OS family detection from model and software version."""
    assert derive_os_family("NetEngine 40E", "Version 8.180") == "vrp8"
    assert derive_os_family("NE8000", "Version 8.210") == "vrp8"
    assert derive_os_family("AR2200", "Version 5.170") == "vrp5"
    assert derive_os_family("S5700", "VRP5") == "vrp5"
    assert derive_os_family("Generic", "") == "vrp8"


def test_import_from_csv_and_diff(test_db_session):
    """Verify CSV import creates devices, derives fields, and computes diff on update."""
    f = io.BytesIO(SAMPLE_NMS_CSV.encode("utf-8-sig"))
    res = InventoryService.import_from_csv(test_db_session, f, update_existing=True)

    assert res["total"] == 3
    assert res["added_count"] == 3
    assert res["updated_count"] == 0
    assert res["unchanged_count"] == 0

    dev = test_db_session.query(Device).filter(Device.name == "TEH-MHD-PE01_TH").first()
    assert dev is not None
    assert dev.mgmt_ip == "10.100.1.1"
    assert dev.province == "TH"
    assert dev.site == "TEH-MHD"
    assert dev.role == "PE"
    assert dev.os_family == "vrp8"
    assert "province:TH" in dev.tags
    assert "role:PE" in dev.tags

    # Re-import identical CSV -> all unchanged
    f_same = io.BytesIO(SAMPLE_NMS_CSV.encode("utf-8-sig"))
    res_same = InventoryService.import_from_csv(test_db_session, f_same, update_existing=True)
    assert res_same["added_count"] == 0
    assert res_same["updated_count"] == 0
    assert res_same["unchanged_count"] == 3

    # Import modified CSV (change IP and model)
    updated_csv = """NE Name,NE IP Address,NE Type (MPU Type),Software Version,LSR ID,ESN
TEH-MHD-PE01_TH,10.100.1.99,NetEngine 40E-X8,VRP (R) Software, Version 8.180,10.100.1.1,2102350AAA1011111111
"""
    f_up = io.BytesIO(updated_csv.encode("utf-8-sig"))
    res_up = InventoryService.import_from_csv(test_db_session, f_up, update_existing=True)
    assert res_up["updated_count"] == 1
    assert "mgmt_ip" in res_up["updated"][0]["diff"]
    assert res_up["updated"][0]["diff"]["mgmt_ip"]["new"] == "10.100.1.99"

    test_db_session.refresh(dev)
    assert dev.mgmt_ip == "10.100.1.99"
    assert dev.model == "NetEngine 40E-X8"


def test_list_devices_and_filters(test_db_session):
    """Verify listing devices with province, role, and search filters."""
    f = io.BytesIO(SAMPLE_NMS_CSV.encode("utf-8-sig"))
    InventoryService.import_from_csv(test_db_session, f)

    # Filter by province
    th_devs, th_tot = InventoryService.list_devices(test_db_session, province="TH")
    assert th_tot == 1
    assert th_devs[0].name == "TEH-MHD-PE01_TH"

    # Filter by role
    pe_devs, pe_tot = InventoryService.list_devices(test_db_session, role="PE")
    assert pe_tot == 1
    assert pe_devs[0].name == "TEH-MHD-PE01_TH"

    # Search filter
    s_devs, s_tot = InventoryService.list_devices(test_db_session, search="8000")
    assert s_tot == 1
    assert s_devs[0].name == "ISF-CR01_IS"

    # Tag filter
    t_devs, t_tot = InventoryService.list_devices(test_db_session, tag="role:PE")
    assert t_tot == 1


def test_target_set_crud_and_resolution(test_db_session):
    """Verify saved target sets filter and resolve active devices dynamically."""
    f = io.BytesIO(SAMPLE_NMS_CSV.encode("utf-8-sig"))
    InventoryService.import_from_csv(test_db_session, f)

    tset = TargetSet(
        name="All Tehran Routers",
        description="Core & PE devices in Tehran province",
        filter_criteria={"provinces": ["TH"]},
        device_ids=[],
    )
    test_db_session.add(tset)
    test_db_session.commit()

    resolved = tset.resolve_devices(test_db_session)
    assert len(resolved) == 1
    assert resolved[0].name == "TEH-MHD-PE01_TH"

    # Pinned device inclusion
    other_dev = test_db_session.query(Device).filter(Device.name == "ISF-CR01_IS").first()
    tset.device_ids = [other_dev.id]
    test_db_session.commit()

    resolved_with_pinned = tset.resolve_devices(test_db_session)
    assert len(resolved_with_pinned) == 2
    names = {d.name for d in resolved_with_pinned}
    assert "TEH-MHD-PE01_TH" in names
    assert "ISF-CR01_IS" in names


def test_device_health_badge(test_db_session):
    """Verify health status evaluation."""
    dev = Device(
        name="ROUTER-TEST_TH",
        mgmt_ip="192.168.1.1",
        vendor="huawei",
        os_family="vrp8",
        health_status="unknown",
    )
    test_db_session.add(dev)
    test_db_session.commit()

    # Initial check without zabbix_hostid -> not-in-zabbix
    res = InventoryService.check_health(test_db_session, dev, probe_ssh=False)
    assert res["health_status"] == "not-in-zabbix"

    # Add zabbix_hostid -> monitored-ok
    dev.zabbix_hostid = "10550"
    test_db_session.commit()
    res2 = InventoryService.check_health(test_db_session, dev, probe_ssh=False)
    assert res2["health_status"] == "monitored-ok"


def test_devices_rest_api_lifecycle(app_client):
    """Verify REST API for devices listing, creation, update, CSV import, and export."""
    # 1. Create a device
    post_res = app_client.post(
        "/api/v1/devices",
        json={
            "name": "TEH-REST-PE01_TH",
            "mgmt_ip": "10.200.1.1",
            "model": "NetEngine 40E",
            "province": "TH",
            "site": "TEH-REST",
            "role": "PE",
            "tags": ["critical", "core"],
        },
    )
    assert post_res.status_code == 201
    dev_data = post_res.get_json()
    dev_id = dev_data["id"]

    # 2. Get device
    get_res = app_client.get(f"/api/v1/devices/{dev_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["name"] == "TEH-REST-PE01_TH"

    # 3. List devices
    list_res = app_client.get("/api/v1/devices?province=TH")
    assert list_res.status_code == 200
    assert list_res.get_json()["total"] >= 1

    # 4. Update device
    put_res = app_client.put(
        f"/api/v1/devices/{dev_id}",
        json={"role": "RR", "model": "NetEngine 8000"},
    )
    assert put_res.status_code == 200
    assert put_res.get_json()["role"] == "RR"

    # 5. Import CSV via multipart upload
    csv_bytes = SAMPLE_NMS_CSV.encode("utf-8-sig")
    imp_res = app_client.post(
        "/api/v1/devices/import-csv",
        data={"file": (io.BytesIO(csv_bytes), "nms_export.csv")},
        content_type="multipart/form-data",
    )
    assert imp_res.status_code == 200
    assert imp_res.get_json()["total"] == 3

    # 6. Export devices
    exp_res = app_client.get("/api/v1/devices/export?format=csv")
    assert exp_res.status_code == 200
    assert "attachment; filename=devices_export.csv" in exp_res.headers.get("Content-Disposition", "")
    assert b"TEH-REST-PE01_TH" in exp_res.data


def test_target_sets_rest_api(app_client):
    """Verify Target Sets REST API endpoints."""
    # Create target set
    create_res = app_client.post(
        "/api/v1/devices/target-sets",
        json={
            "name": "Tehran PEs",
            "description": "All PEs in Tehran",
            "filter_criteria": {"provinces": ["TH"], "roles": ["PE"]},
        },
    )
    assert create_res.status_code == 201
    ts_data = create_res.get_json()
    ts_id = ts_data["id"]

    # List target sets
    list_res = app_client.get("/api/v1/devices/target-sets")
    assert list_res.status_code == 200
    assert len(list_res.get_json()) >= 1

    # Resolve devices
    resolve_res = app_client.get(f"/api/v1/devices/target-sets/{ts_id}/devices")
    assert resolve_res.status_code == 200
    assert "devices" in resolve_res.get_json()

    # Delete target set
    del_res = app_client.delete(f"/api/v1/devices/target-sets/{ts_id}")
    assert del_res.status_code == 200


def test_features_catalog_api_and_run(app_client):
    """Verify Feature Catalog discovery and synchronous run."""
    # List features
    list_res = app_client.get("/api/v1/features")
    assert list_res.status_code == 200
    features = list_res.get_json()
    keys = {f["feature_key"] for f in features}
    assert "inventory_discovery" in keys

    # Get single feature spec
    spec_res = app_client.get("/api/v1/features/inventory_discovery")
    assert spec_res.status_code == 200
    spec = spec_res.get_json()
    assert spec["name"] == "Inventory & Discovery"
    assert spec["risk"] == "low"

    # Run feature with CSV content
    run_res = app_client.post(
        "/api/v1/features/inventory_discovery/run",
        json={
            "csv_content": SAMPLE_NMS_CSV,
            "update_existing": True,
            "sync_zabbix": False,
        },
    )
    assert run_res.status_code == 200
    res_data = run_res.get_json()
    assert res_data["status"] == "success"
    assert "import_summary" in res_data
    assert res_data["import_summary"]["total"] == 3
