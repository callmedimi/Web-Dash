"""Config Backup Pipeline Handler (Target Architecture §3, Plan 06 Step 4.3).

Executes automated configuration backup for Huawei VRP devices:
- Fetches running or saved configuration via SSH driver (read-only).
- Deduplicates using SHA-256 (no duplicate row if unchanged).
- Encrypts configuration at rest using Fernet key.
- Enforces snapshot retention.
"""
from typing import Dict, Any, Optional

from backend.app.devices.session import DeviceSession
from backend.app.jobs.worker import TaskContext
from backend.app.models.device import Device
from backend.app.services.config_backup import ConfigBackupService


class ConfigBackupHandler:
    """Safe Change Pipeline handler for device configuration backups."""

    @staticmethod
    def run_task(ctx: TaskContext, session: Optional[DeviceSession] = None) -> Dict[str, Any]:
        """Entrypoint invoked by JobEngine worker."""
        device_name = ctx.device_name
        kind = (ctx.params or {}).get("kind", "running")
        cmd = "display saved-configuration" if kind == "saved" else "display current-configuration"

        ctx.log("info", f"Executing config_backup ({kind}) for {device_name}")

        # 1. Resolve Device record from DB
        dev = ctx.session.query(Device).filter(Device.name == device_name).first()
        if not dev:
            ctx.log("error", f"Device '{device_name}' not found in database inventory")
            return {
                "device_name": device_name,
                "status": "failed",
                "error": f"Device '{device_name}' not found in inventory",
            }

        # 2. Acquire DeviceSession
        dev_session = session
        if dev_session is None:
            from backend.app.devices.pool import create_device_session
            creds = ctx.creds or {}
            dev_session = create_device_session(
                device_name=device_name,
                db_session=ctx.session,
                username=creds.get("username"),
                password=creds.get("password"),
                jitter=False,
            )

        with dev_session:
            ctx.log("info", f"Fetching {kind} configuration via '{cmd}'...")
            raw_output = dev_session.run(cmd)

            if not raw_output or len(raw_output.strip()) == 0:
                ctx.log("error", "Device returned empty configuration output")
                return {
                    "device_name": device_name,
                    "status": "failed",
                    "error": "EMPTY_CONFIG_OUTPUT",
                }

            snapshot, is_new = ConfigBackupService.create_snapshot(
                db_session=ctx.session,
                device_id=dev.id,
                config_text=raw_output,
                kind=kind,
                job_id=ctx.job_id,
            )

            status_str = "created" if is_new else "unchanged"
            ctx.log(
                "info",
                f"Config backup complete ({status_str}). Snapshot ID: {snapshot.id}, SHA-256: {snapshot.sha256[:12]}...",
            )

            return {
                "device_name": device_name,
                "status": status_str,
                "snapshot_id": snapshot.id,
                "sha256": snapshot.sha256,
                "size_bytes": snapshot.size_bytes,
                "is_new": is_new,
            }
