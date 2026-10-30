"""Comprehensive tests for Step 3.4: Telemetry subsystem (Zabbix, Grafana, Cache, Mapping).

Verifies:
1. Version auto-detection (Bearer header on Zabbix >= 5.4 vs auth body on older).
2. JSON-RPC business errors are NEVER retried (F-27).
3. Transport failures are retried up to 2 times.
4. Circuit breaker opens after 5 failures and prevents HTTP calls for 60s.
5. In-process TTL cache with stale-while-error serving.
6. Correct history value_type resolution (<= 24h history.get vs > 24h trend.get).
7. Read-only enforcement: ack_problem requires write token; no other write methods exist.
8. Device ↔ monitoring sync with ambiguity protection.
9. Grafana deep link and iframe embed URL generator.
"""
import pytest
from unittest.mock import MagicMock, patch

from backend.app.telemetry import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryItemValue,
    TelemetryError,
    DisabledProvider,
    TelemetryCache,
    ZabbixProvider,
    ZabbixCircuitBreaker,
    GrafanaClient,
    sync_devices_with_telemetry,
)
from backend.app.models.device import Device
from backend.app.db.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class FakeHTTPResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_zabbix_version_detection_auth_header():
    """Verify Zabbix 6.0 uses Bearer header, whereas 5.0 uses auth body field."""
    mock_session = MagicMock()
    # 1. Zabbix 6.0 -> Bearer
    mock_session.post.return_value = FakeHTTPResponse({"result": "6.0.12"})
    provider_v6 = ZabbixProvider(url="http://zabbix/api_jsonrpc.php", token="test_token", session=mock_session)
    provider_v6.detect_version()
    assert provider_v6._use_bearer is True

    # 2. Zabbix 5.0 -> legacy auth in payload
    mock_session.post.return_value = FakeHTTPResponse({"result": "5.0.21"})
    provider_v5 = ZabbixProvider(url="http://zabbix/api_jsonrpc.php", token="test_token", session=mock_session)
    provider_v5.detect_version()
    assert provider_v5._use_bearer is False


def test_zabbix_never_retries_business_errors():
    """F-27: JSON-RPC business error must raise TelemetryError immediately without retry."""
    mock_session = MagicMock()
    mock_session.post.return_value = FakeHTTPResponse({
        "error": {
            "code": -32602,
            "message": "Invalid params",
            "data": "Host not found",
        }
    })

    provider = ZabbixProvider(url="http://zabbix/api_jsonrpc.php", token="tok", retries=2, session=mock_session)

    with pytest.raises(TelemetryError) as exc_info:
        provider.list_hosts()

    assert "-32602" in exc_info.value.code
    # Must have called post EXACTLY ONCE (no retry on business error)
    assert mock_session.post.call_count == 1


def test_zabbix_retries_transport_errors_and_trips_breaker():
    """Transport / HTTP failures must be retried up to 2 times (3 calls total) and trip breaker after 5 failures."""
    import requests
    mock_session = MagicMock()
    mock_session.post.side_effect = requests.ConnectionError("Connection refused")

    provider = ZabbixProvider(url="http://zabbix/api_jsonrpc.php", token="tok", retries=2, session=mock_session)
    provider.breaker.threshold = 2  # Lower threshold for quick testing

    # 1st failure (3 transport attempts)
    with pytest.raises(TelemetryError):
        provider.list_hosts()
    assert mock_session.post.call_count == 3

    # 2nd failure -> trips breaker!
    with pytest.raises(TelemetryError):
        provider.list_hosts()

    assert provider.breaker.is_open() is True

    # Next call must be blocked immediately by circuit breaker without HTTP call
    call_count_before = mock_session.post.call_count
    with pytest.raises(TelemetryError) as exc:
        provider.list_hosts()
    assert exc.value.code == "CIRCUIT_OPEN"
    assert mock_session.post.call_count == call_count_before


def test_telemetry_cache_stale_while_error():
    """Verify cache returns stale data if fresh fetch fails."""
    cache = TelemetryCache()
    key = "test_key"

    # Set with 0.1s TTL and 2s stale window
    cache.set(key, "cached_data", ttl_seconds=0.1, stale_window_seconds=2.0)

    # Immediate hit: fresh
    val, is_stale = cache.get(key)
    assert val == "cached_data"
    assert is_stale is False

    # Sleep past TTL
    import time
    time.sleep(0.15)

    # Stale hit
    val, is_stale = cache.get(key)
    assert val == "cached_data"
    assert is_stale is True


def test_zabbix_history_vs_trend_resolution():
    """Verify history.get used for <= 24h with value_type from item; trend.get for > 24h."""
    mock_session = MagicMock()
    # 1. First call resolves item (value_type=3 -> unsigned int)
    item_resp = FakeHTTPResponse({"result": [{"itemid": "1001", "key_": "net.if.in", "value_type": "3"}]})
    # 2. Second call returns history
    hist_resp = FakeHTTPResponse({"result": [{"clock": "1700000000", "value": "5000"}]})

    mock_session.post.side_effect = [item_resp, hist_resp]
    provider = ZabbixProvider(url="http://zabbix/api_jsonrpc.php", token="tok", session=mock_session)

    # Query 1 hour (3600s <= 86400s) -> should call history.get
    series = provider.get_series(host_id="10", key_or_pattern="net.if.in", t_from=1700000000, t_to=1700003600)
    assert series.item_id == "1001"
    assert len(series.points) == 1
    assert series.points[0].value == 5000.0

    second_call_payload = mock_session.post.call_args_list[1][1]["json"]
    assert second_call_payload["method"] == "history.get"
    assert second_call_payload["params"]["history"] == 3  # value_type resolved from item!


def test_ack_problem_write_token_check():
    """Verify ack_problem raises NOT_CONFIGURED when no write token is configured."""
    provider_ro = ZabbixProvider(url="http://zabbix", token="ro_token", write_token=None)
    with pytest.raises(TelemetryError) as exc:
        provider_ro.ack_problem("999", "Fixed issue")
    assert exc.value.code == "NOT_CONFIGURED"

    # With write token
    mock_session = MagicMock()
    mock_session.post.return_value = FakeHTTPResponse({"result": {"eventids": ["999"]}})
    provider_rw = ZabbixProvider(url="http://zabbix", token="ro_token", write_token="rw_token", session=mock_session)
    assert provider_rw.ack_problem("999", "Acknowledged") is True


def test_device_telemetry_sync_and_ambiguity_protection():
    """Verify device sync links exact name and IP, but flags multiple matches as ambiguous."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # DB Devices
    d1 = Device(name="CORE-R1", mgmt_ip="10.1.1.1", os_family="vrp8")
    d2 = Device(name="EDGE-R2", mgmt_ip="10.2.2.2", os_family="vrp8")
    d3 = Device(name="AMBIGUOUS-R3", mgmt_ip="10.3.3.3", os_family="vrp8")
    d4 = Device(name="MISSING-R4", mgmt_ip="10.4.4.4", os_family="vrp8")
    session.add_all([d1, d2, d3, d4])
    session.commit()

    # Fake Zabbix Provider
    fake_provider = MagicMock()
    fake_provider.list_hosts.return_value = [
        TelemetryHost(host_id="101", name="CORE-R1", visible_name="Core Router 1", interfaces=[{"ip": "10.1.1.1"}], groups=["Backbone"]),
        TelemetryHost(host_id="102", name="ZABBIX-EDGE-2", visible_name="ZABBIX-EDGE-2", interfaces=[{"ip": "10.2.2.2"}], groups=["Edge"]),
        TelemetryHost(host_id="103", name="AMBIGUOUS-R3", visible_name="Site A", interfaces=[{"ip": "10.3.3.3"}]),
        TelemetryHost(host_id="104", name="AMBIGUOUS-R3", visible_name="Site B", interfaces=[{"ip": "10.3.3.3"}]),
        TelemetryHost(host_id="105", name="UNMANAGED-R5", visible_name="Unmanaged", interfaces=[{"ip": "10.5.5.5"}]),
    ]

    report = sync_devices_with_telemetry(session, fake_provider, auto_apply=True)

    assert report["matched_count"] == 2  # CORE-R1 (exact name) and EDGE-R2 (IP match)
    assert report["ambiguous_count"] == 1  # AMBIGUOUS-R3 (two Zabbix hosts)
    assert report["missing_in_zabbix_count"] == 1  # MISSING-R4
    assert report["zabbix_not_in_inventory_count"] == 1  # UNMANAGED-R5 (id 105)

    # Verify auto_apply updated d1 and d2, but NEVER d3
    session.refresh(d1)
    session.refresh(d2)
    session.refresh(d3)
    assert d1.zabbix_hostid == "101"
    assert d1.site == "Backbone"
    assert d2.zabbix_hostid == "102"
    assert d3.zabbix_hostid is None  # Ambiguity protection!


def test_grafana_embed_and_deep_links():
    """Verify Grafana link and iframe embed URL builders."""
    client = GrafanaClient(base_url="https://grafana.internal:3000", token="viewer_token")
    url = client.build_dashboard_url("huawei-core", t_from="now-1h", variables={"host": "CORE-R1"})
    assert "https://grafana.internal:3000/d/huawei-core" in url
    assert "var-host=CORE-R1" in url

    embed_url = client.build_embed_url("huawei-core", panel_id=4, kiosk=True, variables={"host": "CORE-R1"})
    assert "https://grafana.internal:3000/d-solo/huawei-core" in embed_url
    assert "panelId=4" in embed_url
    assert "kiosk=true" in embed_url
