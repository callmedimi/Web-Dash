"""Inventory & Discovery Automation Catalog Feature (Step 5.1)."""
import io
from typing import Dict, Any

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.inventory import InventoryService
from backend.app.telemetry import get_telemetry_provider
from backend.app.telemetry.mapping import sync_devices_with_telemetry


class InventoryDiscoveryFeature(BaseFeature):
    """Automation catalog feature for inventory onboarding and telemetry linking."""

    spec = FeatureSpec(
        name="Inventory & Discovery",
        feature_key="inventory_discovery",
        risk="low",
        needs_ssh=False,
        needs_telemetry=True,
        read_only=False,
        inputs={
            "csv_content": {"type": "string", "required": False, "description": "Raw CSV text or file stream"},
            "update_existing": {"type": "bool", "default": True, "description": "Update existing device attributes"},
            "sync_zabbix": {"type": "bool", "default": False, "description": "Run Zabbix host matching sync"},
            "auto_apply_zabbix": {"type": "bool", "default": True, "description": "Link matched Zabbix host IDs to devices"},
        },
        outputs={
            "total": {"type": "int"},
            "added_count": {"type": "int"},
            "updated_count": {"type": "int"},
            "zabbix_sync": {"type": "object"},
        },
        device_commands=[],
        failure_modes={
            "CSV_PARSE_ERROR": "Malformed or missing CSV header starting with 'NE Name,'",
            "TELEMETRY_UNAVAILABLE": "Zabbix service is disabled or unreachable",
        },
        report_columns=[
            "name",
            "mgmt_ip",
            "model",
            "province",
            "site",
            "role",
            "health_status",
            "zabbix_hostid",
        ],
        permission_key="operator",
        description="Onboard devices via NMS CSV, auto-derive provinces/sites/roles, and sync with Zabbix.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "feature": self.spec.feature_key,
            "status": "success",
            "dry_run": ctx.dry_run,
        }

        # 1. Process CSV import if provided
        csv_data = ctx.params.get("csv_content")
        if csv_data:
            if isinstance(csv_data, str):
                file_obj = io.BytesIO(csv_data.encode("utf-8-sig"))
            else:
                file_obj = csv_data

            update_existing = ctx.params.get("update_existing", True)
            import_res = InventoryService.import_from_csv(
                session=ctx.db_session,
                file_storage_or_content=file_obj,
                update_existing=update_existing,
            )
            result["import_summary"] = import_res
            if import_res.get("error"):
                result["status"] = "failed"
                result["error"] = import_res["error"]
                result["message"] = import_res.get("message")
                return result

        # 2. Process Zabbix telemetry synchronization if requested
        if ctx.params.get("sync_zabbix", False):
            provider = get_telemetry_provider()
            auto_apply = ctx.params.get("auto_apply_zabbix", True) and not ctx.dry_run
            sync_res = sync_devices_with_telemetry(
                db_session=ctx.db_session,
                provider=provider,
                auto_apply=auto_apply,
            )
            result["zabbix_sync"] = sync_res

        return result


# Automatically register on module import
inventory_feature = InventoryDiscoveryFeature()
feature_registry.register(inventory_feature)
