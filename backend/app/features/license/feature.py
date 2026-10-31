"""License Management Automation Catalog Feature (Step 5.4)."""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.license import LicenseService
from backend.app.devices.session import DeviceSession
from backend.app.models.device import Device, TargetSet


class LicenseManagementFeature(BaseFeature):
    """Automation catalog feature for router license checking and fleet status tracking."""

    spec = FeatureSpec(
        name="License Management",
        feature_key="license_management",
        risk="low",
        needs_ssh=True,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "province": {"type": "string", "required": False, "description": "Filter by province code (e.g. TH, IS)"},
            "target_set_id": {"type": "int", "required": False, "description": "TargetSet ID to resolve devices"},
            "device_ids": {"type": "list[int]", "required": False, "description": "Explicit list of device IDs"},
            "alert_threshold_days": {"type": "int", "default": 90, "description": "Flag licenses expiring within N days"},
            "save_to_db": {"type": "bool", "default": True, "description": "Save license records to database"},
        },
        outputs={
            "devices_scanned": {"type": "int"},
            "summary": {"type": "object"},
            "expiring_devices": {"type": "list"},
            "results": {"type": "list"},
        },
        device_commands=[
            "display license",
            "display license verbose",
        ],
        failure_modes={
            "DEVICE_UNREACHABLE": "Could not connect to router via SSH",
            "LICENSE_COMMAND_FAILED": "Failed to retrieve license output",
        },
        report_columns=[
            "device_name",
            "mgmt_ip",
            "province",
            "product_name",
            "product_version",
            "license_state",
            "days_to_expiry",
            "expiry_date",
            "alert_level",
            "items_used",
            "items_total",
        ],
        permission_key="operator",
        description="Fleet license scanner, days to expiry tracking (<=90/60/30/7 days), items capacity usage, and renewal staging.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        # 1. Resolve devices
        province = params.get("province")
        target_set_id = params.get("target_set_id")
        device_ids = params.get("device_ids")
        save_to_db = params.get("save_to_db", True)

        devices: List[Device] = []
        if target_set_id:
            tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
            if tset:
                devices = tset.resolve_devices(session)
        elif device_ids:
            devices = session.query(Device).filter(Device.id.in_(device_ids), Device.enabled == True).all()
        elif province:
            devices = session.query(Device).filter(Device.province == province, Device.enabled == True).all()
        else:
            devices = session.query(Device).filter(Device.enabled == True).limit(100).all()

        mock_session = params.get("_session_mock")
        results = []
        errors = []
        expiring = []

        for dev in devices:
            try:
                if mock_session is not None:
                    scanned = LicenseService.scan_device_license(
                        device=dev,
                        device_session=mock_session,
                    )
                else:
                    with DeviceSession(
                        ip=dev.mgmt_ip,
                        os_family=dev.os_family,
                        device_name=dev.name,
                    ) as dsess:
                        scanned = LicenseService.scan_device_license(
                            device=dev,
                            device_session=dsess,
                        )

                if save_to_db:
                    LicenseService.save_device_license(
                        db_session=session,
                        device_id=dev.id,
                        data=scanned,
                    )

                results.append(scanned)
                if scanned.get("alert_level") != "OK":
                    expiring.append({
                        "device_id": dev.id,
                        "device_name": dev.name,
                        "mgmt_ip": dev.mgmt_ip,
                        "province": dev.province,
                        "product_name": scanned.get("product_name"),
                        "license_state": scanned.get("license_state"),
                        "days_to_expiry": scanned.get("days_to_expiry"),
                        "expiry_date": scanned.get("expiry_date"),
                        "alert_level": scanned.get("alert_level"),
                    })

            except Exception as exc:
                errors.append({"device_name": dev.name, "device_id": dev.id, "error": str(exc)})

        # Compute summary
        summary = LicenseService.get_fleet_summary(session, province=province)

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "devices_scanned": len(results),
            "expiring_devices": expiring,
            "summary": summary,
            "results": results,
            "errors": errors,
        }


# Register feature
feature_registry.register(LicenseManagementFeature())
