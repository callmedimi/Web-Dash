"""Admin Schedules API Blueprint for managing periodic cron network tasks."""
from flask import Blueprint, jsonify, request, session

from auth import login_required, permission_required
from backend.app.api.common import get_json_payload, get_client_ip
from backend.app.jobs.scheduler import scheduler
from audit import record_audit

schedules_bp = Blueprint("schedules_api", __name__)


@schedules_bp.route("", methods=["GET"])
@login_required
@permission_required("admin_schedule_manage")
def list_schedules():
    """List all configured cron schedules."""
    items = scheduler.list_schedules()
    return jsonify({"schedules": items, "count": len(items)})


@schedules_bp.route("", methods=["POST"])
@login_required
@permission_required("admin_schedule_manage")
def create_schedule():
    """Create a new cron schedule."""
    data = get_json_payload()
    job_type = (data.get("job_type") or "").strip()
    cron_expr = (data.get("cron") or data.get("cron_expression") or data.get("cron_expr") or "").strip()
    params = data.get("params") or {}
    enabled = bool(data.get("enabled", True))

    if not job_type or not cron_expr:
        return jsonify({"error": "job_type and cron expression are required"}), 400

    try:
        sid = scheduler.add_schedule(
            job_type=job_type,
            cron_expression=cron_expr,
            params=params,
            enabled=enabled,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "VALIDATION_ERROR"}), 400

    user = session.get("username") or "admin"
    record_audit(
        "schedule_created",
        user,
        get_client_ip(),
        status="success",
        detail={"schedule_id": sid, "job_type": job_type, "cron": cron_expr},
    )

    return jsonify({"status": "created", "schedule_id": sid}), 201


@schedules_bp.route("/<int:schedule_id>", methods=["DELETE"])
@login_required
@permission_required("admin_schedule_manage")
def delete_schedule(schedule_id: int):
    """Delete a schedule."""
    ok = scheduler.delete_schedule(schedule_id)
    if not ok:
        return jsonify({"error": "Schedule not found"}), 404

    user = session.get("username") or "admin"
    record_audit(
        "schedule_deleted",
        user,
        get_client_ip(),
        status="success",
        detail={"schedule_id": schedule_id},
    )
    return jsonify({"status": "deleted", "schedule_id": schedule_id})


@schedules_bp.route("/<int:schedule_id>/toggle", methods=["POST"])
@login_required
@permission_required("admin_schedule_manage")
def toggle_schedule(schedule_id: int):
    """Enable or disable a schedule."""
    data = get_json_payload()
    enabled = bool(data.get("enabled", True))

    ok = scheduler.toggle_schedule(schedule_id, enabled)
    if not ok:
        return jsonify({"error": "Schedule not found"}), 404

    user = session.get("username") or "admin"
    record_audit(
        "schedule_toggled",
        user,
        get_client_ip(),
        status="success",
        detail={"schedule_id": schedule_id, "enabled": enabled},
    )
    return jsonify({"status": "updated", "schedule_id": schedule_id, "enabled": enabled})


@schedules_bp.route("/<int:schedule_id>/run", methods=["POST"])
@login_required
@permission_required("admin_schedule_manage")
def trigger_schedule_now(schedule_id: int):
    """Run a schedule immediately on demand."""
    user = session.get("username") or "admin"
    job_id = scheduler.trigger_now(schedule_id, user=user)
    if not job_id:
        return jsonify({"error": "Schedule not found"}), 404

    record_audit(
        "schedule_triggered_manually",
        user,
        get_client_ip(),
        status="success",
        detail={"schedule_id": schedule_id, "triggered_job_id": job_id},
    )
    return jsonify({"status": "triggered", "schedule_id": schedule_id, "job_id": job_id})
