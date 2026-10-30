"""Base classes for Web-Dash Automation Catalog Features (Target Architecture §2 & Phase 5)."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import logging
from sqlalchemy.orm import Session


@dataclass
class FeatureSpec:
    """Standardized metadata specification for an automation catalog feature."""
    name: str
    feature_key: str
    risk: str = "low"  # low, medium, high
    needs_ssh: bool = False
    needs_telemetry: bool = False
    read_only: bool = True
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    device_commands: List[str] = field(default_factory=list)
    failure_modes: Dict[str, str] = field(default_factory=dict)
    report_columns: List[str] = field(default_factory=list)
    permission_key: str = "operator"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "feature_key": self.feature_key,
            "risk": self.risk,
            "needs_ssh": self.needs_ssh,
            "needs_telemetry": self.needs_telemetry,
            "read_only": self.read_only,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "device_commands": self.device_commands,
            "failure_modes": self.failure_modes,
            "report_columns": self.report_columns,
            "permission_key": self.permission_key,
            "description": self.description,
        }


@dataclass
class FeatureContext:
    """Execution context provided to a feature during run."""
    db_session: Session
    user_id: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    job_id: Optional[str] = None
    task_id: Optional[str] = None
    logger: Optional[logging.Logger] = None
    dry_run: bool = False


class BaseFeature:
    """Abstract base class for all automation features."""
    spec: FeatureSpec

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        """Execute the feature logic using the provided context."""
        raise NotImplementedError("Feature execution not implemented")
