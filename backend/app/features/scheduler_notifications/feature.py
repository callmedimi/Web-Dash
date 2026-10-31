"""Scheduler & Multi-Channel Notifications Catalog Feature (Automation Catalog Step 5.12)."""
from typing import Dict, Any, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.jobs.scheduler import scheduler
from backend.app.services.notifications import NotificationService


class SchedulerNotificationsFeature(BaseFeature):
    """Catalog feature for automated recurring schedules, leader lease status, and multi-channel notifications."""

    spec = FeatureSpec(
        name="Scheduler & Multi-Channel Notifications",
        feature_key="scheduler_notifications",
        risk="low",
        needs_ssh=False,
        needs_telemetry=False,
        read_only=False,
        description="Manage recurring cron network schedules, inspect leader DB lease, and dispatch multi-channel alerts.",
        permission_key="admin",
        inputs={
            "action": "list_schedules | add_schedule | toggle_schedule | delete_schedule | trigger_now | get_leader_status | send_notification | history",
            "schedule_id": "Integer ID of the schedule record",
            "job_type": "Logical job type to trigger (e.g. config_backup, license_check, site_arp_collector)",
            "cron": "Standard 5-field cron expression (e.g. '0 2 * * *')",
            "params": "JSON dictionary of parameters passed to triggered job",
            "enabled": "Boolean enabled status",
            "event_type": "Trigger type: job_failed | change_awaiting_approval | license_expiring | device_flapping | compliance_regression",
            "title": "Alert title",
            "message": "Alert message body",
            "severity": "Severity: info | warning | critical",
            "channels": "List of channels: ['webhook', 'email', 'syslog']",
        },
        outputs={
            "schedules": "List of configured cron schedules",
            "leader": "Status of the single-leader DB lease",
            "notification": "Result of dispatched alert",
        },
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        """Execute schedule management or notification action."""
        params = ctx.params or {}
        action = params.get("action", "list_schedules")

        if action == "list_schedules":
            items = scheduler.list_schedules(db_session=ctx.db_session)
            return {
                "status": "success",
                "action": "list_schedules",
                "count": len(items),
                "schedules": items,
            }

        elif action == "add_schedule":
            job_type = params.get("job_type")
            cron_expr = params.get("cron")
            if not job_type or not cron_expr:
                return {
                    "status": "error",
                    "error": "PARAMS_REQUIRED",
                    "message": "Both 'job_type' and 'cron' are required",
                }
            try:
                sid = scheduler.add_schedule(
                    job_type=job_type,
                    cron_expression=cron_expr,
                    params=params.get("params"),
                    enabled=params.get("enabled", True),
                    db_session=ctx.db_session,
                )
                return {
                    "status": "success",
                    "action": "add_schedule",
                    "schedule_id": sid,
                }
            except ValueError as val_err:
                return {
                    "status": "error",
                    "error": "INVALID_CRON",
                    "message": str(val_err),
                }

        elif action == "toggle_schedule":
            sid = params.get("schedule_id")
            if sid is None:
                return {
                    "status": "error",
                    "error": "SCHEDULE_ID_REQUIRED",
                    "message": "Parameter 'schedule_id' is required",
                }
            enabled = bool(params.get("enabled", True))
            ok = scheduler.toggle_schedule(int(sid), enabled, db_session=ctx.db_session)
            if not ok:
                return {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "message": f"Schedule #{sid} not found",
                }
            return {
                "status": "success",
                "action": "toggle_schedule",
                "schedule_id": sid,
                "enabled": enabled,
            }

        elif action == "delete_schedule":
            sid = params.get("schedule_id")
            if sid is None:
                return {
                    "status": "error",
                    "error": "SCHEDULE_ID_REQUIRED",
                    "message": "Parameter 'schedule_id' is required",
                }
            ok = scheduler.delete_schedule(int(sid), db_session=ctx.db_session)
            if not ok:
                return {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "message": f"Schedule #{sid} not found",
                }
            return {
                "status": "success",
                "action": "delete_schedule",
                "schedule_id": sid,
            }

        elif action == "trigger_now":
            sid = params.get("schedule_id")
            if sid is None:
                return {
                    "status": "error",
                    "error": "SCHEDULE_ID_REQUIRED",
                    "message": "Parameter 'schedule_id' is required",
                }
            job_id = scheduler.trigger_now(int(sid), db_session=ctx.db_session)
            if not job_id:
                return {
                    "status": "error",
                    "error": "NOT_FOUND",
                    "message": f"Schedule #{sid} not found",
                }
            return {
                "status": "success",
                "action": "trigger_now",
                "schedule_id": sid,
                "job_id": job_id,
            }

        elif action == "get_leader_status":
            status = scheduler.get_leader_status(db_session=ctx.db_session)
            return {
                "status": "success",
                "action": "get_leader_status",
                "leader": status,
            }

        elif action == "send_notification":
            ev_type = params.get("event_type", "manual_alert")
            title = params.get("title", "Web-Dash Notification")
            msg = params.get("message", "")
            sev = params.get("severity", "info")
            channels = params.get("channels")
            res = NotificationService.dispatch_notification(
                event_type=ev_type,
                title=title,
                message=msg,
                severity=sev,
                data=params.get("data"),
                channels=channels,
            )
            return {
                "status": "success",
                "action": "send_notification",
                "notification": res,
            }

        elif action == "history":
            history = NotificationService.get_recent_history(params.get("limit", 50))
            return {
                "status": "success",
                "action": "history",
                "count": len(history),
                "history": history,
            }

        else:
            return {
                "status": "error",
                "error": "UNKNOWN_ACTION",
                "message": f"Unsupported action '{action}'",
            }


# Register feature with catalog registry
scheduler_notifications_feature = SchedulerNotificationsFeature()
feature_registry.register(scheduler_notifications_feature)
