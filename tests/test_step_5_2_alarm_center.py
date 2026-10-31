"""Tests for Step 5.2: Alarm Center, Unified Table, Filters, Statistics, and Clear Planning."""
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.device import Device
from backend.app.models.user import User
from backend.app.models.alarm import AlarmFilter
from backend.app.services.alarm_center import (
    AlarmCenterService,
    calculate_alarm_age_minutes,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


SAMPLE_VRP_ALARMS_OUTPUT = """
Sequence  AlarmId    Level Date       Time     Description
----------------------------------------------------------------------------------------------------
101       0x08520003 1     2026-10-31 01:00:00 The interface GigabitEthernet0/1/0 physical status is Down
102       0x08520003 2     2026-10-31 02:00:00 The interface GigabitEthernet0/1/1 physical status is Down
103       0x08520003 1     2026-10-31 02:30:00 The interface GigabitEthernet0/1/0 physical status is Down
104       0x08210001 4     2026-10-30 10:00:00 Power supply module 1 failure
"""


class MockDeviceSession:
    """Mock device session for testing CLI alarm output."""

    def __init__(self, output: str = SAMPLE_VRP_ALARMS_OUTPUT):
        self.output = output
        self.commands_sent = []

    def run(self, cmd: str, **kwargs) -> str:
        self.commands_sent.append(cmd)
        if "display alarm active" in cmd:
            return self.output
        if "display current-configuration" in cmd:
            return "interface GigabitEthernet0/1/0\n shutdown\n"
        return "OK"


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_alarms.db"
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
    db_file = tmp_path / "test_app_alarms.db"
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
            dev1 = Device(
                name="TEH-MHD-PE01_TH",
                mgmt_ip="10.100.1.1",
                vendor="huawei",
                os_family="vrp8",
                province="TH",
                site="TEH-MHD",
                role="PE",
            )
            dev2 = Device(
                name="ISF-CR01_IS",
                mgmt_ip="10.100.2.1",
                vendor="huawei",
                os_family="vrp8",
                province="IS",
                site="ISF",
                role="P",
            )
            s.add_all([dev1, dev2])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_test",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_alarm_age_calculation():
    """Verify age calculation handles ISO and space-separated date/time strings."""
    age = calculate_alarm_age_minutes("2026-10-31", "01:00:00")
    assert age is not None
    assert age >= 0

    age_tz = calculate_alarm_age_minutes("2026-10-31", "01:00:00+03:30")
    assert age_tz is not None
    assert age_tz >= 0


def test_parse_and_enrich_alarm_output():
    """Verify raw CLI alarm lines are correctly enriched with metadata and normalized interface."""
    dev = Device(
        id=1,
        name="TEH-MHD-PE01_TH",
        mgmt_ip="10.100.1.1",
        province="TH",
        site="TEH-MHD",
    )
    alarms = AlarmCenterService.parse_device_alarm_output(SAMPLE_VRP_ALARMS_OUTPUT, dev)
    assert len(alarms) == 4

    first = alarms[0]
    assert first["sequence"] == 101
    assert first["alarm_id"] == "0x08520003"
    assert first["level"] == 1
    assert first["level_name"] == "Critical"
    assert first["interface"] == "GigabitEthernet0/1/0"
    assert first["device_name"] == "TEH-MHD-PE01_TH"
    assert first["province"] == "TH"

    fourth = alarms[3]
    assert fourth["level"] == 4
    assert fourth["level_name"] == "Warning"
    assert fourth["interface"] is None


def test_filter_alarms():
    """Verify multi-dimensional alarm filtering."""
    dev = Device(id=1, name="TEH-MHD-PE01_TH", mgmt_ip="10.100.1.1", province="TH", site="MHD")
    all_alarms = AlarmCenterService.parse_device_alarm_output(SAMPLE_VRP_ALARMS_OUTPUT, dev)

    # 1. Filter by level
    crit_only = AlarmCenterService.filter_alarms(all_alarms, level="Critical")
    assert len(crit_only) == 2
    for a in crit_only:
        assert a["level_name"] == "Critical"

    # 2. Filter by interface
    ge011 = AlarmCenterService.filter_alarms(all_alarms, interface="GigabitEthernet0/1/1")
    assert len(ge011) == 1
    assert ge011[0]["sequence"] == 102

    # 3. Filter by search text
    power_alarms = AlarmCenterService.filter_alarms(all_alarms, search_text="power")
    assert len(power_alarms) == 1
    assert power_alarms[0]["sequence"] == 104


def test_compute_statistics():
    """Verify analytics and statistics calculation (top noisy, histogram, levels)."""
    dev = Device(id=1, name="TEH-MHD-PE01_TH", mgmt_ip="10.100.1.1", province="TH", site="MHD")
    alarms = AlarmCenterService.parse_device_alarm_output(SAMPLE_VRP_ALARMS_OUTPUT, dev)

    stats = AlarmCenterService.compute_statistics(alarms)
    assert stats["total_alarms"] == 4
    assert stats["level_breakdown"]["Critical"] == 2
    assert stats["level_breakdown"]["Major"] == 1
    assert stats["level_breakdown"]["Warning"] == 1

    assert len(stats["top_noisy_devices"]) == 1
    assert stats["top_noisy_devices"][0]["device_name"] == "TEH-MHD-PE01_TH"
    assert stats["top_noisy_devices"][0]["count"] == 4

    top_ifaces = stats["top_noisy_interfaces"]
    assert len(top_ifaces) >= 1
    # GigabitEthernet0/1/0 had 2 alarms
    target_ge0 = "TEH-MHD-PE01_TH:GigabitEthernet0/1/0"
    match = next((item for item in top_ifaces if item["target"] == target_ge0), None)
    assert match is not None
    assert match["count"] == 2


def test_plan_alarm_clears(test_db_session):
    """Verify selected alarms plan safe changes through the pipeline."""
    dev = Device(
        name="TEH-MHD-PE01_TH",
        mgmt_ip="10.100.1.1",
        vendor="huawei",
        os_family="vrp8",
        province="TH",
    )
    test_db_session.add(dev)
    test_db_session.commit()

    alarm_items = [
        {"device_id": dev.id, "sequence": 101, "description": "GE0/1/0 down"},
        {"device_id": dev.id, "sequence": 102, "description": "GE0/1/1 down"},
    ]

    plans = AlarmCenterService.plan_alarm_clears(
        session=test_db_session,
        alarm_items=alarm_items,
        creator_id="admin_test",
        noconf_shutdown=False,
    )

    assert len(plans) == 1
    plan_req = plans[0]
    assert plan_req["status"] == "planned"
    assert plan_req["device_id"] == dev.id
    assert "clear alarm active sequence 101" in plan_req["plan"]["lines"]
    assert "clear alarm active sequence 102" in plan_req["plan"]["lines"]


def test_alarm_center_feature_run(test_db_session):
    """Verify AlarmCenterFeature execution with mock device session."""
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

    feature = feature_registry.get("alarm_center")
    assert feature is not None

    ctx = FeatureContext(
        db_session=test_db_session,
        user_id=1,
        params={
            "device_ids": [dev.id],
            "_session_mock": MockDeviceSession(SAMPLE_VRP_ALARMS_OUTPUT),
            "level": "Critical",
        },
    )

    result = feature.run(ctx)
    assert result["status"] == "success"
    assert result["devices_queried"] == 1
    assert result["total_alarms"] == 2  # Only 2 Critical alarms
    assert "statistics" in result


def test_alarms_api_lifecycle(app_client):
    """Verify Alarm Center REST API endpoints."""
    # 1. Statistics endpoint
    stats_res = app_client.post(
        "/api/v1/alarms/statistics",
        json={
            "alarms": [
                {"device_name": "R1", "level_name": "Critical", "age_minutes": 10},
                {"device_name": "R1", "level_name": "Major", "age_minutes": 100},
            ]
        },
    )
    assert stats_res.status_code == 200
    stats = stats_res.get_json()
    assert stats["total_alarms"] == 2
    assert stats["level_breakdown"]["Critical"] == 1

    # 2. Clear-plan endpoint
    plan_res = app_client.post(
        "/api/v1/alarms/clear-plan",
        json={
            "alarms": [
                {"device_id": 1, "sequence": 101},
            ],
            "noconf_shutdown": False,
        },
    )
    assert plan_res.status_code == 201
    plan_data = plan_res.get_json()
    assert plan_data["status"] == "planned"
    assert plan_data["count"] == 1

    # 3. Saved Filters CRUD
    create_flt = app_client.post(
        "/api/v1/alarms/filters",
        json={
            "name": "Tehran Criticals",
            "description": "Critical alarms in Tehran",
            "criteria": {"province": "TH", "level": "Critical"},
        },
    )
    assert create_flt.status_code == 201
    flt_id = create_flt.get_json()["id"]

    list_flt = app_client.get("/api/v1/alarms/filters")
    assert list_flt.status_code == 200
    assert len(list_flt.get_json()) >= 1

    del_flt = app_client.delete(f"/api/v1/alarms/filters/{flt_id}")
    assert del_flt.status_code == 200
