"""TelemetryProvider interface and base classes (Target Architecture §3 & Step 3.4).

All telemetry consumers MUST interact through this provider interface.
Direct SNMP is prohibited per platform architecture constraints.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from backend.app.telemetry.models import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryItemValue,
    TelemetrySeries,
    TelemetryInterface,
)


class TelemetryError(Exception):
    """Exception raised by telemetry providers with standardized error code."""
    def __init__(self, message: str, code: str = "TELEMETRY_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class TelemetryProvider(ABC):
    """Abstract base provider for reading telemetry and monitoring data."""

    @abstractmethod
    def list_hosts(self, filters: Optional[Dict[str, Any]] = None) -> List[TelemetryHost]:
        """Fetch list of monitored hosts."""
        pass

    @abstractmethod
    def get_problems(
        self,
        host_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        severity_min: int = 0,
        since: Optional[int] = None,
    ) -> List[TelemetryProblem]:
        """Fetch active monitoring alarms/problems."""
        pass

    @abstractmethod
    def get_item_value(self, host_id: str, key_or_pattern: str) -> Optional[TelemetryItemValue]:
        """Fetch latest scalar metric value for an item."""
        pass

    @abstractmethod
    def get_series(
        self,
        host_id: str,
        key_or_pattern: str,
        t_from: int,
        t_to: int,
        max_points: int = 100,
    ) -> TelemetrySeries:
        """Fetch historical time series."""
        pass

    @abstractmethod
    def get_interface_table(self, host_id: str) -> List[TelemetryInterface]:
        """Fetch per-interface operational state and metrics table."""
        pass

    @abstractmethod
    def ack_problem(self, event_id: str, message: str) -> bool:
        """Acknowledge problem in monitoring system (requires write-scoped token)."""
        pass


class DisabledProvider(TelemetryProvider):
    """Provider used when telemetry integration is disabled or unconfigured."""

    def list_hosts(self, filters: Optional[Dict[str, Any]] = None) -> List[TelemetryHost]:
        return []

    def get_problems(
        self,
        host_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        severity_min: int = 0,
        since: Optional[int] = None,
    ) -> List[TelemetryProblem]:
        return []

    def get_item_value(self, host_id: str, key_or_pattern: str) -> Optional[TelemetryItemValue]:
        return None

    def get_series(
        self,
        host_id: str,
        key_or_pattern: str,
        t_from: int,
        t_to: int,
        max_points: int = 100,
    ) -> TelemetrySeries:
        return TelemetrySeries(item_id="", key=key_or_pattern, points=[])

    def get_interface_table(self, host_id: str) -> List[TelemetryInterface]:
        return []

    def ack_problem(self, event_id: str, message: str) -> bool:
        raise TelemetryError("Telemetry provider is disabled or unconfigured", code="NOT_CONFIGURED")


class NullProvider(DisabledProvider):
    """Stub placeholder for future adapters (e.g. SNMP null provider)."""
    pass
