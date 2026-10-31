"""Config Backup, Diff & Compliance Feature (Automation Catalog Step 5.10).

Catalog feature providing:
- Timeline of device snapshots with 'who/what changed' Job and ChangeRequest correlation.
- Side-by-side unified text and structured hunk diffs between snapshots.
- Direct configuration file download.
- Enterprise compliance audit for single device or entire fleet with per-province % breakdown.
"""
from typing import Dict, Any, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.models.device import Device
from backend.app.services.config_backup import ConfigBackupService
from backend.app.services.compliance import (
    evaluate_device_compliance,
    evaluate_fleet_compliance,
    load_compliance_rules,
)


class ConfigComplianceFeature(BaseFeature):
    """Automation catalog feature for configuration backup timeline, diffs, and compliance."""

    spec = FeatureSpec(
        name="Config Backup, Diff & Compliance",
        feature_key="config_compliance",
        risk="low",
        needs_ssh=False,
        needs_telemetry=False,
        read_only=True,
        description="Inspect device configuration timeline with job correlation, visual diffs, and enterprise compliance audits.",
        permission_key="operator",
        inputs={
            "action": "timeline | diff | compliance_device | compliance_fleet | download | backup",
            "device_id": "Device primary key ID (optional if device_name provided)",
            "device_name": "Device hostname (optional if device_id provided)",
            "from_snapshot_id": "Base snapshot ID for diff comparison",
            "to_snapshot_id": "Target snapshot ID for diff comparison",
            "province": "Filter province code for fleet compliance (optional)",
            "kind": "running or saved (default: running)",
            "limit": "Max timeline entries to retrieve (default: 50)",
            "config_text": "Raw configuration text for direct backup snapshot creation (optional)",
        },
        outputs={
            "timeline": "Chronological list of snapshots with job and change correlation",
            "diff": "Unified diff text and structured hunks",
            "compliance_device": "Per-rule audit results and compliance score for single device",
            "compliance_fleet": "Fleet overview, per-rule and per-province compliance percentages",
            "download": "Decrypted configuration text and file metadata",
        },
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        """Execute config timeline, diff, or compliance action."""
        params = ctx.params or {}
        action = params.get("action", "timeline")
        session = ctx.db_session

        device_id = params.get("device_id")
        device_name = params.get("device_name")

        # Resolve device if name or id given
        dev: Optional[Device] = None
        if device_id is not None:
            dev = session.query(Device).filter(Device.id == int(device_id)).first()
        elif device_name:
            dev = session.query(Device).filter(Device.name == str(device_name).strip()).first()

        resolved_dev_id = dev.id if dev else (int(device_id) if device_id is not None else None)

        if action == "timeline":
            if not resolved_dev_id:
                return {
                    "status": "error",
                    "error": "DEVICE_REQUIRED",
                    "message": "device_id or device_name is required for timeline action",
                }
            timeline = ConfigBackupService.get_device_timeline(
                db_session=session,
                device_id=resolved_dev_id,
                kind=params.get("kind"),
                limit=params.get("limit", 50),
            )
            return {
                "status": "success",
                "action": "timeline",
                "device_id": resolved_dev_id,
                "device_name": dev.name if dev else None,
                "count": len(timeline),
                "timeline": timeline,
            }

        elif action == "diff":
            from_id = params.get("from_snapshot_id")
            to_id = params.get("to_snapshot_id")

            # Fallback to latest two if device is provided but from/to are not
            if resolved_dev_id and (not from_id or not to_id):
                timeline = ConfigBackupService.get_device_timeline(
                    db_session=session, device_id=resolved_dev_id, limit=2
                )
                if len(timeline) >= 2:
                    to_id = to_id or timeline[0]["snapshot_id"]
                    from_id = from_id or timeline[1]["snapshot_id"]

            if not from_id or not to_id:
                return {
                    "status": "error",
                    "error": "SNAPSHOTS_REQUIRED",
                    "message": "Both from_snapshot_id and to_snapshot_id are required for diff",
                }

            diff_data = ConfigBackupService.diff_snapshots(
                db_session=session,
                from_snapshot_id=from_id,
                to_snapshot_id=to_id,
            )
            if not diff_data:
                return {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "message": "One or both snapshots could not be found",
                }

            return {
                "status": "success",
                "action": "diff",
                "from_snapshot_id": from_id,
                "to_snapshot_id": to_id,
                "diff": diff_data,
            }

        elif action == "compliance_device":
            if not resolved_dev_id:
                return {
                    "status": "error",
                    "error": "DEVICE_REQUIRED",
                    "message": "device_id or device_name is required for compliance_device action",
                }
            report = evaluate_device_compliance(session, resolved_dev_id)
            return {
                "status": "success",
                "action": "compliance_device",
                "device_id": resolved_dev_id,
                "device_name": dev.name if dev else None,
                "report": report,
            }

        elif action == "compliance_fleet":
            fleet_data = evaluate_fleet_compliance(
                db_session=session,
                province=params.get("province"),
                rules_dir=params.get("rules_dir"),
            )
            return {
                "status": "success",
                "action": "compliance_fleet",
                "province": params.get("province"),
                "summary": fleet_data["summary"],
                "rules_breakdown": fleet_data["rules_breakdown"],
                "province_breakdown": fleet_data["province_breakdown"],
                "devices": fleet_data["devices"],
            }

        elif action == "download":
            snapshot_id = params.get("snapshot_id")
            if not resolved_dev_id or not snapshot_id:
                return {
                    "status": "error",
                    "error": "DEVICE_AND_SNAPSHOT_REQUIRED",
                    "message": "Both device_id and snapshot_id are required for download action",
                }
            dl_data = ConfigBackupService.get_download_data(
                db_session=session,
                device_id=resolved_dev_id,
                snapshot_id=snapshot_id,
            )
            if not dl_data:
                return {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "message": f"Snapshot {snapshot_id} not found for device {resolved_dev_id}",
                }
            return {
                "status": "success",
                "action": "download",
                "download": dl_data,
            }

        elif action == "backup":
            config_text = params.get("config_text")
            if not resolved_dev_id or not config_text:
                return {
                    "status": "error",
                    "error": "INVALID_PARAMS",
                    "message": "device_id and config_text are required to create a snapshot",
                }
            snap, is_new = ConfigBackupService.create_snapshot(
                db_session=session,
                device_id=resolved_dev_id,
                config_text=config_text,
                kind=params.get("kind", "running"),
                job_id=params.get("job_id"),
            )
            return {
                "status": "success",
                "action": "backup",
                "snapshot_id": snap.id,
                "sha256": snap.sha256,
                "is_new": is_new,
            }

        else:
            return {
                "status": "error",
                "error": "UNKNOWN_ACTION",
                "message": f"Unsupported action '{action}'",
            }


# Register with catalog registry
config_compliance_feature = ConfigComplianceFeature()
feature_registry.register(config_compliance_feature)
