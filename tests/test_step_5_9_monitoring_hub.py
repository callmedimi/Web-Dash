"""Comprehensive tests for Phase 5 Step 5.9: Monitoring Hub (Zabbix & Grafana)."""
import time
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.telemetry.models import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryInterface,
    TelemetryItemValue,
    TelemetrySeriesPoint,
    TelemetrySeries,
)
from backend.app.telemetry.base import TelemetryProvider
from backend.app.telemetry.grafana import GrafanaClient
from backend.app.services.monitoring import MonitoringHubService
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


class MockTelemetryProvider(TelemetryProvider):
    """Mock telemetry provider returning pre-configured hosts, metrics, problems, and series."""

    def __init__(self):
        self._version = "6.4.5"
        self._hosts = [
            TelemetryHost(
                host_id="10001",
                name="TEH-AGG01",
                visible_name="TEH-AGG01-Main",
                interfaces=[{"ip": "10.10.1.1", "main": "1"}],
                groups=["Routers", "Tehran"],
                status="enabled",
                available=True,
            ),
            TelemetryHost(
                host_id="10002",
                name="ISF-PE01",
                visible_name="ISF-PE01",
                interfaces=[{"ip": "10.20.1.1", "main": "1"}],
                groups=["Routers", "Isfahan"],
                status="enabled",
                available=True,
            ),
        ]
        self._problems = [
            TelemetryProblem(
                event_id="9001",
                host_id="10001",
                host_name="TEH-AGG01",
                name="BGP session down: Peer 10.255.0.2",
                severity=4,  # High
                clock=int(time.time()) - 3600,
                acknowledged=False,
                tags={"interface": "GigabitEthernet0/1/0"},
            ),
            TelemetryProblem(
                event_id="9002",
                host_id="10002",
                host_name="ISF-PE01",
                name="High CPU utilization > 85%",
                severity=2,  # Warning
                clock=int(time.time()) - 1800,
                acknowledged=True,
            ),
        ]

    def detect_version(self) -> str:
        return self._version

    def list_hosts(self, filters: dict | None = None) -> list[TelemetryHost]:
        return self._hosts

    def get_hosts(self, group_name: str | None = None) -> list[TelemetryHost]:
        return self._hosts

    def get_problems(
        self,
        host_ids: list[str] | None = None,
        groups: list[str] | None = None,
        severity_min: int = 0,
        since: int | None = None,
    ) -> list[TelemetryProblem]:
        if host_ids:
            return [p for p in self._problems if p.host_id in host_ids]
        return self._problems

    def get_item_value(self, host_id: str, key_or_pattern: str) -> TelemetryItemValue | None:
        if "cpu" in key_or_pattern:
            return TelemetryItemValue(item_id="2001", key="cpu.util", name="CPU Utilization", value=42.5, clock=int(time.time()), units="%")
        if "memory" in key_or_pattern:
            return TelemetryItemValue(item_id="2002", key="vm.memory.util", name="Memory Usage", value=68.0, clock=int(time.time()), units="%")
        if "temp" in key_or_pattern:
            return TelemetryItemValue(item_id="2003", key="sensor.temp", name="Board Temperature", value=38.0, clock=int(time.time()), units="C")
        return None

    def get_series(
        self,
        host_id: str,
        key_or_pattern: str,
        t_from: int,
        t_to: int,
        max_points: int = 100,
    ) -> TelemetrySeries:
        points = [
            TelemetrySeriesPoint(clock=t_from + i * 360, value=35.0 + (i % 10))
            for i in range(10)
        ]
        return TelemetrySeries(item_id="2001", key=key_or_pattern, points=points)

    def get_interface_table(self, host_id: str) -> list[TelemetryInterface]:
        return [
            TelemetryInterface(
                name="GigabitEthernet0/1/0",
                admin_status="UP",
                oper_status="UP",
                in_rate=125000000.0,
                out_rate=85000000.0,
                errors_in=0.0,
                errors_out=0.0,
            ),
            TelemetryInterface(
                name="GigabitEthernet0/2/0",
                admin_status="UP",
                oper_status="DOWN",
                in_rate=0.0,
                out_rate=0.0,
                errors_in=12.0,
                errors_out=0.0,
            ),
        ]

    def ack_problem(self, event_id: str, message: str) -> bool:
        return True


class MockGrafana(GrafanaClient):
    """Mock Grafana client simulating healthy API."""

    def __init__(self):
        super().__init__(base_url="http://grafana.corp.internal:3000")

    def check_health(self) -> dict:
        return {"database": "ok", "version": "10.1.0"}


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_monitoring.db"
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
    db_file = tmp_path / "test_app_monitoring.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_mon", role="admin", password_hash="dummy_hash")
            s.add(admin)

            dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", zabbix_hostid="10001", enabled=True)
            dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", role="PE", province="ISF", zabbix_hostid="10002", enabled=True)
            s.add_all([dev1, dev2])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_mon",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_fleet_health_calculation(test_db_session):
    """Verify fleet health aggregation, problem counts by severity, and province grouping."""
    dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", zabbix_hostid="10001", enabled=True)
    dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", role="PE", province="ISF", zabbix_hostid="10002", enabled=True)
    dev3 = Device(name="SHZ-ACC01", mgmt_ip="10.30.1.1", role="ACC", province="SHZ", enabled=True)
    test_db_session.add_all([dev1, dev2, dev3])
    test_db_session.commit()

    provider = MockTelemetryProvider()

    health = MonitoringHubService.get_fleet_health(
        db_session=test_db_session,
        provider=provider,
    )

    summary = health["summary"]
    assert summary["total_devices"] == 3
    assert summary["monitored_devices"] == 2
    assert summary["unmonitored_devices"] == 1
    assert summary["available_devices"] == 2
    assert summary["availability_pct"] == 100.0
    assert summary["total_active_problems"] == 2
    assert summary["problems_by_severity"]["High"] == 1
    assert summary["problems_by_severity"]["Warning"] == 1

    # Check device rows and telemetry status
    devices = health["devices"]
    teh_dev = next(d for d in devices if d["name"] == "TEH-AGG01")
    assert teh_dev["telemetry_status"] == "CRITICAL"
    assert teh_dev["problem_count"] == 1

    shz_dev = next(d for d in devices if d["name"] == "SHZ-ACC01")
    assert shz_dev["telemetry_status"] == "UNMONITORED"


def test_device_monitoring_data_and_grafana_links(test_db_session):
    """Verify device-specific interface table, metrics, time series, and Grafana URLs."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", zabbix_hostid="10001", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    provider = MockTelemetryProvider()
    grafana = MockGrafana()

    data = MonitoringHubService.get_device_monitoring(
        db_session=test_db_session,
        device_identifier="TEH-AGG01",
        provider=provider,
        grafana_client=grafana,
        t_from="now-12h",
        t_to="now",
    )

    assert data["device"]["name"] == "TEH-AGG01"
    assert len(data["interfaces"]) == 2
    assert data["interfaces"][0]["name"] == "GigabitEthernet0/1/0"
    assert data["interfaces"][0]["oper_status"] == "UP"

    # Metrics
    assert data["metrics"]["cpu"]["value"] == 42.5
    assert data["metrics"]["memory"]["value"] == 68.0
    assert data["metrics"]["temperature"]["value"] == 38.0

    # Series
    assert len(data["series"]) == 10

    # Grafana links
    assert "d/huawei-routers" in data["grafana"]["deep_link"]
    assert "var-host=TEH-AGG01" in data["grafana"]["deep_link"]
    assert "d-solo/huawei-routers" in data["grafana"]["embed_url"]


def test_search_interfaces_telemetry(test_db_session):
    """Verify keyword interface search across telemetry hosts."""
    provider = MockTelemetryProvider()

    res = MonitoringHubService.search_interfaces(
        db_session=test_db_session,
        keyword="GigabitEthernet0/1/0",
        provider=provider,
    )

    assert res["count"] >= 1
    assert any(r["interface"] == "GigabitEthernet0/1/0" for r in res["results"])
    assert res["results"][0]["in_rate_bps"] == 125000000.0


def test_alarm_center_merge_and_shortcuts(test_db_session):
    """Verify combining SSH alarms with Zabbix problems and generating device selection shortcut."""
    provider = MockTelemetryProvider()

    ssh_alarms = [
        {"device_name": "MHD-PE01", "level": "CRITICAL", "text": "Optical power degraded", "interface": "10GE0/1/0"},
        {"device_name": "TEH-AGG01", "level": "WARNING", "text": "PTP clock jitter high", "interface": "GE0/1/0"},
    ]

    merged = MonitoringHubService.merge_alarms(
        db_session=test_db_session,
        ssh_alarms=ssh_alarms,
        provider=provider,
    )

    assert merged["total_alarms"] == 4  # 2 SSH + 2 Zabbix
    assert merged["ssh_alarms_count"] == 2
    assert merged["zabbix_problems_count"] == 2
    assert merged["unique_affected_devices"] == 3  # MHD-PE01, TEH-AGG01, ISF-PE01

    # Verify shortcut device list
    shortcuts = merged["device_selection_shortcut"]
    assert "MHD-PE01" in shortcuts
    assert "TEH-AGG01" in shortcuts
    assert "ISF-PE01" in shortcuts


def test_telemetry_doctor_integrations(test_db_session):
    """Verify integrations health check, Zabbix version detection, and mapping coverage %."""
    dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", zabbix_hostid="10001", enabled=True)
    dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", enabled=True)
    test_db_session.add_all([dev1, dev2])
    test_db_session.commit()

    provider = MockTelemetryProvider()
    grafana = MockGrafana()

    diag = MonitoringHubService.test_integrations(
        provider=provider,
        grafana_client=grafana,
        db_session=test_db_session,
    )

    assert diag["doctor_verdict"] == "HEALTHY"
    assert diag["zabbix"]["status"] == "ok"
    assert diag["zabbix"]["version"] == "6.4.5"
    assert diag["grafana"]["status"] == "ok"
    assert diag["coverage"]["total_devices"] == 2
    assert diag["coverage"]["mapped_devices"] == 1
    assert diag["coverage"]["coverage_pct"] == 50.0


def test_monitoring_webhook_intake(test_db_session):
    """Verify webhook payload intake, device correlation, and event normalization."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    payload = {
        "event_name": "Interface GigabitEthernet0/1/0 is DOWN",
        "hostname": "TEH-AGG01",
        "severity": "high",
        "clock": "2026-10-31T03:00:00",
    }

    res = MonitoringHubService.process_webhook(payload, test_db_session)
    assert res["status"] == "accepted"
    assert res["event_name"] == "Interface GigabitEthernet0/1/0 is DOWN"
    assert res["device_id"] == dev.id
    assert res["severity"] == "HIGH"


def test_monitoring_feature_run(test_db_session):
    """Verify MonitoringHubFeature execution via catalog registry."""
    dev = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", zabbix_hostid="10001", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("monitoring_hub")
    assert feature is not None

    provider = MockTelemetryProvider()
    grafana = MockGrafana()

    # 1. Action: fleet_health
    ctx_fleet = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "fleet_health",
            "_telemetry_provider": provider,
            "_grafana_client": grafana,
        },
    )
    res_fleet = feature.run(ctx_fleet)
    assert res_fleet["status"] == "success"
    assert "summary" in res_fleet["data"]

    # 2. Action: device_monitoring
    ctx_dev = FeatureContext(
        db_session=test_db_session,
        params={
            "action": "device_monitoring",
            "device": "TEH-AGG01",
            "_telemetry_provider": provider,
            "_grafana_client": grafana,
        },
    )
    res_dev = feature.run(ctx_dev)
    assert res_dev["status"] == "success"
    assert res_dev["data"]["device"]["name"] == "TEH-AGG01"
    assert "interfaces" in res_dev["data"]


def test_monitoring_rest_api_endpoints(app_client):
    """Verify REST API endpoints /api/v1/telemetry/*."""
    # 1. Fleet Health
    health_res = app_client.get("/api/v1/telemetry/fleet-health")
    assert health_res.status_code == 200
    h_data = health_res.get_json()
    assert "summary" in h_data
    assert "devices" in h_data

    # 2. Device Monitoring
    dev_res = app_client.get("/api/v1/telemetry/device/TEH-AGG01")
    assert dev_res.status_code == 200
    dev_data = dev_res.get_json()
    assert "device" in dev_data
    assert "grafana" in dev_data

    # 3. Search Interfaces
    search_res = app_client.post(
        "/api/v1/telemetry/search-interfaces",
        json={"keyword": "GigabitEthernet"},
    )
    assert search_res.status_code == 200

    # 4. Merge Alarms
    merge_res = app_client.post(
        "/api/v1/telemetry/merge-alarms",
        json={
            "ssh_alarms": [
                {"device_name": "TEH-AGG01", "level": "WARNING", "text": "Test Alarm"}
            ]
        },
    )
    assert merge_res.status_code == 200
    m_data = merge_res.get_json()
    assert "device_selection_shortcut" in m_data

    # 5. Doctor Integrations
    doc_res = app_client.get("/api/v1/telemetry/doctor")
    assert doc_res.status_code == 200
    d_data = doc_res.get_json()
    assert "coverage" in d_data

    # 6. Webhook Intake
    hook_res = app_client.post(
        "/api/v1/telemetry/webhook",
        json={
            "event_name": "Test Webhook Alert",
            "hostname": "TEH-AGG01",
            "severity": "average",
        },
    )
    assert hook_res.status_code == 200
    hook_data = hook_res.get_json()
    assert hook_data["status"] == "accepted"
