"""Monitoring Hub Automation Catalog Feature (Phase 5 Step 5.9)."""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.monitoring import MonitoringHubService


class MonitoringHubFeature(BaseFeature):
    """Automation catalog feature for Zabbix & Grafana telemetry fleet health and monitoring."""

    spec = FeatureSpec(
        name="Monitoring Hub (Telemetry)",
        feature_key="monitoring_hub",
        risk="low",
        needs_ssh=False,
        needs_telemetry=True,
        read_only=True,
        inputs={
            "action": {"type": "string", "default": "fleet_health", "description": "Action: fleet_health | device_monitoring | search_interfaces | merge_alarms | test_integrations"},
            "device": {"type": "string", "required": False, "description": "Target device name or IP for device_monitoring"},
            "province": {"type": "string", "required": False, "description": "Optional filter by province"},
            "role": {"type": "string", "required": False, "description": "Optional filter by device role"},
            "keyword": {"type": "string", "required": False, "description": "Keyword for interface search"},
            "ssh_alarms": {"type": "list", "required": False, "description": "SSH alarms list to merge with Zabbix problems"},
            "t_from": {"type": "string", "default": "now-6h", "description": "Time range start (Grafana syntax)"},
            "t_to": {"type": "string", "default": "now", "description": "Time range end (Grafana syntax)"},
        },
        outputs={
            "status": {"type": "string"},
            "action": {"type": "string"},
            "data": {"type": "object"},
        },
        device_commands=[],
        failure_modes={
            "TELEMETRY_UNAVAILABLE": "Zabbix or Grafana service unreachable",
            "DEVICE_NOT_FOUND": "Target device not found in inventory",
            "INVALID_ACTION": "Unknown monitoring action requested",
        },
        report_columns=[
            "name",
            "mgmt_ip",
            "province",
            "role",
            "telemetry_status",
            "problem_count",
        ],
        permission_key="operator",
        description="Fleet health overview, live interface metrics, CPU/memory time-series, Grafana deep-links, and alarm merging without SSH.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        action = params.get("action", "fleet_health").strip().lower()
        provider = params.get("_telemetry_provider")
        grafana = params.get("_grafana_client")

        if action == "fleet_health":
            data = MonitoringHubService.get_fleet_health(
                db_session=session,
                provider=provider,
                filter_province=params.get("province"),
                filter_role=params.get("role"),
            )
        elif action == "device_monitoring":
            dev = params.get("device") or params.get("target") or ""
            if not dev:
                return {
                    "feature": self.spec.feature_key,
                    "status": "failed",
                    "error": "DEVICE_NOT_FOUND",
                    "message": "Device name or IP address is required for device_monitoring.",
                }
            data = MonitoringHubService.get_device_monitoring(
                db_session=session,
                device_identifier=dev,
                provider=provider,
                grafana_client=grafana,
                t_from=params.get("t_from", "now-6h"),
                t_to=params.get("t_to", "now"),
            )
        elif action == "search_interfaces":
            kw = params.get("keyword") or ""
            data = MonitoringHubService.search_interfaces(
                db_session=session,
                keyword=kw,
                provider=provider,
            )
        elif action == "merge_alarms":
            ssh_alarms = params.get("ssh_alarms") or []
            data = MonitoringHubService.merge_alarms(
                db_session=session,
                ssh_alarms=ssh_alarms,
                provider=provider,
            )
        elif action == "test_integrations":
            data = MonitoringHubService.test_integrations(
                provider=provider,
                grafana_client=grafana,
                db_session=session,
            )
        else:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "INVALID_ACTION",
                "message": f"Action '{action}' is not supported.",
            }

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "action": action,
            "data": data,
        }


# Register feature
monitoring_hub_feature = MonitoringHubFeature()
feature_registry.register(monitoring_hub_feature)
