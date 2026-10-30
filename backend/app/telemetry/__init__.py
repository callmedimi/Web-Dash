"""Telemetry layer exports (Target Architecture §3 & Step 3.4)."""
from backend.app.telemetry.models import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryItemValue,
    TelemetrySeriesPoint,
    TelemetrySeries,
    TelemetryInterface,
)
from backend.app.telemetry.base import (
    TelemetryError,
    TelemetryProvider,
    DisabledProvider,
    NullProvider,
)
from backend.app.telemetry.cache import TelemetryCache, telemetry_cache
from backend.app.telemetry.zabbix import ZabbixProvider, ZabbixCircuitBreaker
from backend.app.telemetry.grafana import GrafanaClient
from backend.app.telemetry.mapping import sync_devices_with_telemetry

__all__ = [
    "TelemetryHost",
    "TelemetryProblem",
    "TelemetryItemValue",
    "TelemetrySeriesPoint",
    "TelemetrySeries",
    "TelemetryInterface",
    "TelemetryError",
    "TelemetryProvider",
    "DisabledProvider",
    "NullProvider",
    "TelemetryCache",
    "telemetry_cache",
    "ZabbixProvider",
    "ZabbixCircuitBreaker",
    "GrafanaClient",
    "sync_devices_with_telemetry",
]
