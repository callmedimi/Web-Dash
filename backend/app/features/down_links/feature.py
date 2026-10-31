"""Down-Links Report Automation Catalog Feature (Step 5.3)."""
from datetime import datetime
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.reporting import (
    DownLinksService,
    compute_analytics,
    validate_age_threshold,
)
from backend.app.devices.session import DeviceSession
from backend.app.models.device import Device, TargetSet
from backend.app.models.down_link import DownLinkReport



class DownLinksFeature(BaseFeature):
    """Automation catalog feature for down-links scanning and analytics."""

    spec = FeatureSpec(
        name="Down-Links Report",
        feature_key="down_links",
        risk="low",
        needs_ssh=True,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "province": {"type": "string", "required": False, "description": "Filter by province code (e.g. TH, IS)"},
            "target_set_id": {"type": "int", "required": False, "description": "TargetSet ID to resolve devices"},
            "device_ids": {"type": "list[int]", "required": False, "description": "Explicit list of device IDs"},
            "age_value": {"type": "int", "default": 0, "description": "Filter links down for at least N units"},
            "age_unit": {"type": "string", "default": "hours", "description": "Age unit: minutes, hours, days"},
            "compare_with_report_id": {"type": "int", "required": False, "description": "Historical report ID to diff against"},
            "save_report": {"type": "bool", "default": True, "description": "Persist report snapshot to database"},
        },
        outputs={
            "report_id": {"type": "int"},
            "total_down_links": {"type": "int"},
            "service_down_count": {"type": "int"},
            "noconf_down_count": {"type": "int"},
            "analytics": {"type": "object"},
            "comparison": {"type": "object"},
        },
        device_commands=[
            "display alarm active",
            "display interface",
            "display current-configuration interface ...",
        ],
        failure_modes={
            "DEVICE_UNREACHABLE": "Could not connect to router via SSH",
            "INVALID_AGE_PARAMETERS": "Invalid age value or unit",
        },
        report_columns=[
            "NE NAME",
            "interface name",
            "interface description",
            "admin down or not",
            "alarm occur time",
            "Category",
            "Trunk Memberships",
        ],
        permission_key="operator",
        description="Automated link health scan per province, sliding-window burst detection, and historical day-over-day diffing.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        age_val = params.get("age_value", 0)
        age_unit = params.get("age_unit", "hours")
        try:
            val, delta = validate_age_threshold(age_val, age_unit)
        except ValueError as exc:
            return {"status": "failed", "error": "INVALID_AGE_PARAMETERS", "message": str(exc)}

        # 1. Resolve target devices
        province = params.get("province")
        target_set_id = params.get("target_set_id")
        device_ids = params.get("device_ids")

        devices: List[Device] = []
        target_name = None
        if target_set_id:
            tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
            if tset:
                target_name = tset.name
                devices = tset.resolve_devices(session)
        elif device_ids:
            devices = session.query(Device).filter(Device.id.in_(device_ids), Device.enabled == True).all()
        elif province:
            devices = session.query(Device).filter(Device.province == province, Device.enabled == True).all()
        else:
            devices = session.query(Device).filter(Device.enabled == True).limit(50).all()

        # 2. Scan devices
        all_service = []
        all_noconf = []
        all_trunks = []
        errors = []

        mock_session = params.get("_session_mock")

        for dev in devices:
            try:
                if mock_session is not None:
                    s_links, nc_links, trunks = DownLinksService.scan_device_down_links(
                        device=dev,
                        device_session=mock_session,
                        age_value=val,
                        age_unit=age_unit,
                    )
                else:
                    with DeviceSession(
                        ip=dev.mgmt_ip,
                        os_family=dev.os_family,
                        device_name=dev.name,
                    ) as dsess:
                        s_links, nc_links, trunks = DownLinksService.scan_device_down_links(
                            device=dev,
                            device_session=dsess,
                            age_value=val,
                            age_unit=age_unit,
                        )
                all_service.extend(s_links)
                all_noconf.extend(nc_links)
                all_trunks.extend(trunks)
            except Exception as e:
                errors.append({"device_name": dev.name, "error": str(e)})

        # 3. Compute Analytics
        analytics = compute_analytics(all_service, all_noconf, all_trunks)

        # 4. Historical comparison
        comparison = None
        compare_id = params.get("compare_with_report_id")
        if not compare_id and province:
            # Auto-find most recent previous report for province
            prev = (
                session.query(DownLinkReport)
                .filter(DownLinkReport.province == province)
                .order_by(DownLinkReport.created_at.desc())
                .first()
            )
            if prev:
                compare_id = prev.id

        if compare_id:
            prev_report = session.query(DownLinkReport).filter(DownLinkReport.id == compare_id).first()
            if prev_report:
                comparison = DownLinksService.compare_reports(
                    current_report={"report_data": all_service, "noconf_data": all_noconf},
                    previous_report={"report_data": prev_report.report_data, "noconf_data": prev_report.noconf_data},
                )
                comparison["previous_report_id"] = prev_report.id
                comparison["previous_created_at"] = prev_report.created_at.isoformat()

        # 5. Persist report snapshot if requested
        report_id = None
        if params.get("save_report", True):
            saved = DownLinkReport(
                job_id=ctx.job_id,
                province=province,
                target_set_name=target_name,
                total_down=len(all_service) + len(all_noconf),
                service_down=len(all_service),
                noconf_down=len(all_noconf),
                report_data=all_service,
                noconf_data=all_noconf,
                trunk_data=all_trunks,
                analytics=analytics,
                created_at=datetime.utcnow(),
            )
            session.add(saved)
            session.commit()
            report_id = saved.id

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "report_id": report_id,
            "devices_queried": len(devices),
            "total_down_links": len(all_service) + len(all_noconf),
            "service_down_count": len(all_service),
            "noconf_down_count": len(all_noconf),
            "report_data": all_service,
            "noconf_data": all_noconf,
            "trunk_data": all_trunks,
            "analytics": analytics,
            "comparison": comparison,
            "errors": errors,
        }


down_links_feature = DownLinksFeature()
feature_registry.register(down_links_feature)
