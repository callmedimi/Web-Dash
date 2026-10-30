"""Telemetry data models and typed containers (Target Architecture §3 & Step 3.4)."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class TelemetryHost:
    """Represents a monitored host in Zabbix/monitoring."""
    host_id: str
    name: str
    visible_name: str
    interfaces: List[Dict[str, str]] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    status: str = "enabled"  # enabled, disabled
    available: bool = True


@dataclass
class TelemetryProblem:
    """Represents an active monitoring problem/alarm in Zabbix."""
    event_id: str
    host_id: str
    host_name: str
    name: str
    severity: int  # 0: Not classified, 1: Info, 2: Warning, 3: Average, 4: High, 5: Disaster
    clock: int
    acknowledged: bool = False
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TelemetryItemValue:
    """Represents the latest scalar value of an item."""
    item_id: str
    key: str
    name: str
    value: Any
    clock: int
    units: str = ""


@dataclass
class TelemetrySeriesPoint:
    """Single point in a time series."""
    clock: int
    value: float


@dataclass
class TelemetrySeries:
    """Time-series metric data points."""
    item_id: str
    key: str
    points: List[TelemetrySeriesPoint] = field(default_factory=list)


@dataclass
class TelemetryInterface:
    """Per-interface telemetry overview."""
    name: str
    admin_status: str = "unknown"
    oper_status: str = "unknown"
    in_rate: Optional[float] = None
    out_rate: Optional[float] = None
    errors_in: Optional[float] = None
    errors_out: Optional[float] = None
    last_change: Optional[str] = None
