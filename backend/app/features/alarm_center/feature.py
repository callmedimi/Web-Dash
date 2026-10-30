"""Alarm Center Automation Catalog Feature (Step 5.2)."""
from typing import Dict, Any, List

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.alarm_center import AlarmCenterService
from backend.app.models.device import Device, TargetSet


class AlarmCenterFeature(BaseFeature):
    """Automation catalog feature for unified alarm table and noisy statistics."""

    spec = FeatureSpec(
        name="Alarm Center",
        feature_key="alarm_center",
        risk="low",
        needs_ssh=True,
        needs_telemetry=True,
        read_only=True,
        inputs={
            "device_ids": {"type": "list[int]", "required": False, "description": "List of device IDs to query"},
            "device_names": {"type": "list[str]", "required": False, "description": "List of device names to query"},
            "target_set_id": {"type": "int", "required": False, "description": "Saved TargetSet ID to resolve devices from"},
            "province": {"type": "string", "required": False, "description": "Filter by province code"},
            "level": {"type": "string", "required": False, "description": "Filter by alarm level (Critical, Major, Minor, Warning)"},
            "interface": {"type": "string", "required": False, "description": "Filter by interface name"},
            "search_text": {"type": "string", "required": False, "description": "Free-text search in alarm description"},
            "min_age_minutes": {"type": "int", "required": False, "description": "Filter alarms active for at least N minutes"},
            "max_age_minutes": {"type": "int", "required": False, "description": "Filter alarms active for at most N minutes"},
        },
        outputs={
            "total_alarms": {"type": "int"},
            "devices_queried": {"type": "int"},
            "alarms": {"type": "list[object]"},
            "statistics": {"type": "object"},
        },
        device_commands=["display alarm active"],
        failure_modes={
            "DEVICE_UNREACHABLE": "Could not connect to router via SSH",
            "PARSE_ERROR": "Output from device could not be parsed safely",
        },
        report_columns=[
            "device_name",
            "sequence",
            "level_name",
            "date",
            "time",
            "age_minutes",
            "interface",
            "description",
        ],
        permission_key="operator",
        description="Unified active alarm table, multi-dimensional filtering, and noisy device/interface analytics.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        # 1. Resolve Target Devices
        target_set_id = params.get("target_set_id")
        device_ids = params.get("device_ids") or []
        device_names = params.get("device_names") or []
        province = params.get("province")

        devices: List[Device] = []
        if target_set_id:
            tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
            if tset:
                devices = tset.resolve_devices(session)
        elif device_ids:
            devices = session.query(Device).filter(Device.id.in_(device_ids), Device.enabled == True).all()
        elif device_names:
            devices = session.query(Device).filter(Device.name.in_(device_names), Device.enabled == True).all()
        elif province:
            devices = session.query(Device).filter(Device.province == province, Device.enabled == True).all()
        else:
            # Default: all active devices up to a sensible batch limit
            devices = session.query(Device).filter(Device.enabled == True).limit(50).all()

        # 2. Query alarms from devices
        all_alarms: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        # Allow passing mock session for testing
        session_mock = params.get("_session_mock")

        for dev in devices:
            alarms, err = AlarmCenterService.query_device_alarms(dev, device_session=session_mock)
            if err:
                errors.append({"device_name": dev.name, "error": err})
            else:
                all_alarms.extend(alarms)

        # 3. Apply Filters
        filtered = AlarmCenterService.filter_alarms(
            alarms=all_alarms,
            device_name=params.get("filter_device_name"),
            province=params.get("level_province") or params.get("filter_province"),
            site=params.get("filter_site"),
            level=params.get("level"),
            interface=params.get("interface"),
            search_text=params.get("search_text"),
            min_age_minutes=params.get("min_age_minutes"),
            max_age_minutes=params.get("max_age_minutes"),
        )

        # 4. Compute Statistics
        stats = AlarmCenterService.compute_statistics(filtered)

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "devices_queried": len(devices),
            "total_alarms": len(filtered),
            "alarms": filtered,
            "statistics": stats,
            "errors": errors,
        }


alarm_center_feature = AlarmCenterFeature()
feature_registry.register(alarm_center_feature)
