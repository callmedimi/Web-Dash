"""Alarm Clear and Noconf Shutdown Pipeline Handler (Target Architecture §3, Plan 06 Step 4.2).

Replaces legacy process_one from auto_clear_noconf.py with enterprise pipeline contract.
Enforces strict decision table:
- Admin DOWN -> CLEAR_ONLY (risk: low).
- Unreadable config (error or EMPTY_OUTPUT) -> SKIP (reason: CONFIG_UNREADABLE) (F-20).
- Sub-interface -> operates on sub-interface ONLY, never parent (F-21).
- Unambiguous clearing -> success ONLY when device output confirms success; not found is NOT_PRESENT (F-23).
- Alarm view check -> fails task with ALARM_VIEW_UNAVAILABLE if alarm MDP view is not accessible (F-24).
"""
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.app.devices.session import DeviceSession
from backend.app.devices.parsers import (
    parse_active_alarms,
    parse_display_interface,
    parse_interface_config,
    extract_interface,
)
from backend.app.devices.errors import DeviceError, ConfigRejected
from backend.app.jobs.worker import TaskContext
import settings


def parse_down_minutes(last_change_str: Optional[str]) -> Optional[int]:
    """Parse minutes interface has been down from last change string if possible."""
    if not last_change_str:
        return None
    try:
        # Expected formats like '2026-10-30 14:00:00'
        dt = datetime.strptime(last_change_str.strip()[:19], "%Y-%m-%d %H:%M:%S")
        diff_minutes = int((datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds() / 60)
        return max(0, diff_minutes)
    except Exception:
        return None


class AlarmClearHandler:
    """Safe Change Pipeline implementation of Alarm Clear + Noconf Shutdown."""

    @staticmethod
    def run_task(ctx: TaskContext, session: Optional[DeviceSession] = None) -> Dict[str, Any]:
        """Entry point called by JobEngine worker."""
        device_name = ctx.device_name
        mode = ctx.mode or "apply"
        params = ctx.params or {}
        min_down_minutes = int(params.get("noconf_min_down_minutes", getattr(settings, "noconf_min_down_minutes", 60)))

        ctx.log("info", f"Executing alarm_clear pipeline on {device_name} (mode: {mode})")

        # 1. Acquire DeviceSession (injected or created via pool)
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

        report_entries: List[Dict[str, Any]] = []
        alarms_cleared = 0
        interfaces_shutdown = 0
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        with dev_session:
            # Step A: Fetch active alarms
            ctx.log("info", "Fetching active alarms from device...")
            raw_alarms = dev_session.run("display_alarm_active")
            all_alarms = parse_active_alarms(raw_alarms, device_name=device_name)
            ctx.log("info", f"Parsed {len(all_alarms)} active alarm(s)")

            if not all_alarms:
                return {
                    "device_name": device_name,
                    "status": "skipped",
                    "reason": "NO_ACTIVE_ALARMS",
                    "alarms_cleared": 0,
                    "interfaces_shutdown": 0,
                    "entries": [],
                }

            # Step B: Group alarms by interface
            interface_map: Dict[str, List[Dict[str, Any]]] = {}
            for alarm in all_alarms:
                ref = extract_interface(alarm["description"])
                if not ref or ref.ambiguous:
                    report_entries.append({
                        "ne_name": device_name,
                        "interface": "UNKNOWN",
                        "sequence": alarm["sequence"],
                        "alarm_description": alarm["description"][:120],
                        "decision": "SKIP",
                        "reason_code": "AMBIGUOUS_OR_NO_INTERFACE",
                        "action": "none",
                        "status": "SKIPPED",
                        "verified": False,
                        "timestamp": now_iso,
                        "job_id": ctx.job_id,
                        "approved_by": "system",
                    })
                    continue

                # F-21: Sub-interface alarm operates strictly on sub-interface
                target_iface = ref.name
                interface_map.setdefault(target_iface, []).append(alarm)

            # Step C: Evaluate each interface against strict decision table
            targets_to_clear: List[Tuple[str, str, List[Dict[str, Any]]]] = []

            for iface, alarms in sorted(interface_map.items()):
                # 1. Check interface status
                try:
                    iface_raw = dev_session.run("display_interface", interface=iface)
                    iface_status = parse_display_interface(iface_raw)
                except Exception as exc:
                    iface_status = {"physical_state": "UNKNOWN", "is_admin_down": False, "description": ""}

                # 2. Check running config of interface
                try:
                    cfg_raw = dev_session.run("display_current_config_interface", interface=iface)
                    cfg_status = parse_interface_config(cfg_raw)
                except Exception as exc:
                    cfg_status = {"lines": [], "is_empty": True, "error": str(exc), "is_trivial": False}

                is_admin_down = iface_status.get("is_admin_down", False)

                # Strict Decision Table:
                if is_admin_down:
                    decision = "CLEAR_ONLY"
                    reason = "ALREADY_ADMIN_DOWN"
                    action = "clear_alarm"
                    targets_to_clear.append((iface, action, alarms))

                elif cfg_status.get("error") is not None:
                    # F-20: Unreadable config (CLI error or EMPTY_OUTPUT) -> NEVER shutdown!
                    decision = "SKIP"
                    reason = "CONFIG_UNREADABLE"
                    action = "none"

                elif cfg_status.get("is_trivial", False) is True or cfg_status.get("is_empty", False) is True:
                    # Check safeguards: not trunk, no description
                    has_desc = bool(iface_status.get("description", "").strip())
                    is_trunk = "eth-trunk" in iface.lower()

                    if has_desc:
                        decision = "SKIP"
                        reason = "HAS_DESCRIPTION"
                        action = "none"
                    elif is_trunk:
                        decision = "SKIP"
                        reason = "TRUNK_MEMBER"
                        action = "none"
                    else:
                        decision = "SHUTDOWN_THEN_CLEAR"
                        reason = "NOCONF_VERIFIED"
                        action = "shutdown"
                        targets_to_clear.append((iface, action, alarms))
                else:
                    decision = "SKIP"
                    reason = "HAS_CONFIG_OR_UP"
                    action = "none"

                for alarm in alarms:
                    report_entries.append({
                        "ne_name": device_name,
                        "interface": iface,
                        "sequence": alarm["sequence"],
                        "alarm_description": alarm["description"][:120],
                        "decision": decision,
                        "reason_code": reason,
                        "action": action,
                        "status": "PLANNED" if mode in ("plan", "dry_run") else "PENDING",
                        "verified": False,
                        "timestamp": now_iso,
                        "job_id": ctx.job_id,
                        "approved_by": "system",
                    })

            # If mode is dry_run or plan, return results without modifying device
            if mode in ("dry_run", "plan"):
                ctx.log("info", f"Plan generated: {len(targets_to_clear)} interface(s) targeted (dry_run)")
                return {
                    "device_name": device_name,
                    "status": "planned",
                    "alarms_cleared": 0,
                    "interfaces_shutdown": sum(1 for _, act, _ in targets_to_clear if act == "shutdown"),
                    "entries": report_entries,
                }

            # Step D: Apply phase (if mode == "apply")
            # 1. Execute shutdowns with verify + rollback
            for iface, action, alarms in targets_to_clear:
                if action == "shutdown":
                    ctx.log("info", f"Applying shutdown on noconf interface {iface}...")
                    try:
                        dev_session.config_block([f"interface {iface}", "shutdown"], dry_run=False)
                        # Verify shutdown took effect
                        v_raw = dev_session.run("display_interface", interface=iface)
                        v_stat = parse_display_interface(v_raw)
                        if v_stat.get("is_admin_down"):
                            interfaces_shutdown += 1
                            ctx.log("info", f"Shutdown verified for {iface}")
                        else:
                            ctx.log("warning", f"Shutdown verification failed for {iface} — rolling back")
                            dev_session.config_block([f"interface {iface}", "undo shutdown"], dry_run=False)
                            # Remove from clear targets
                            targets_to_clear = [t for t in targets_to_clear if t[0] != iface]
                    except Exception as exc:
                        ctx.log("error", f"Error during shutdown of {iface}: {exc}")
                        targets_to_clear = [t for t in targets_to_clear if t[0] != iface]

            # 2. Enter alarm view (F-24 check)
            if targets_to_clear:
                ctx.log("info", "Entering alarm management view...")
                try:
                    dev_session.conn.send_command("system-view", expect_string=r"\[.*\]")
                    alarm_out = dev_session.conn.send_command("alarm", expect_string=r"\[.*\]")
                    if "unrecognized" in alarm_out.lower() or "error:" in alarm_out.lower():
                        dev_session.conn.send_command("return")
                        raise DeviceError("Alarm MDP view unavailable on this router (F-24)", device_name=device_name)
                except Exception as exc:
                    ctx.log("error", f"Alarm view unavailable: {exc}")
                    for entry in report_entries:
                        if entry["status"] == "PENDING":
                            entry["status"] = "ALARM_VIEW_UNAVAILABLE"
                    return {
                        "device_name": device_name,
                        "status": "failed",
                        "error": "ALARM_VIEW_UNAVAILABLE",
                        "alarms_cleared": 0,
                        "interfaces_shutdown": interfaces_shutdown,
                        "entries": report_entries,
                    }

                # 3. Clear targeted alarms
                try:
                    for iface, action, alarms in targets_to_clear:
                        for alarm in alarms:
                            seq = alarm["sequence"]
                            cmd = f"clear alarm active sequence-number {seq}"
                            out = dev_session.conn.send_command(cmd)
                            lo = out.lower() if out else ""

                            # F-23: Explicit confirmation check
                            status = "FAILED"
                            if "success" in lo or "successfully" in lo:
                                status = "CLEARED"
                                alarms_cleared += 1
                            elif "not exist" in lo or "not found" in lo or "no alarm" in lo:
                                status = "NOT_PRESENT"  # F-23: Never counted as cleared!
                            else:
                                status = "FAILED"

                            # Update report entry
                            for entry in report_entries:
                                if entry["interface"] == iface and entry["sequence"] == seq:
                                    entry["status"] = status
                                    entry["verified"] = (status == "CLEARED")
                finally:
                    # Return back to user view
                    try:
                        dev_session.conn.send_command("return")
                    except Exception:
                        pass

        ctx.log("info", f"Finished: {alarms_cleared} alarm(s) cleared, {interfaces_shutdown} interface(s) shutdown")
        return {
            "device_name": device_name,
            "status": "success",
            "alarms_cleared": alarms_cleared,
            "interfaces_shutdown": interfaces_shutdown,
            "entries": report_entries,
        }
