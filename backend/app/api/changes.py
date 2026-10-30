"""Change Pipeline REST API endpoints (Target Architecture §3 & Step 4.1)."""
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any, List

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.models.config_change import ChangeRequest
from backend.app.models.device import Device
from backend.app.jobs.change import (
    ChangePipelineService,
    ChangeState,
    evaluate_change_risk,
)

changes_bp = Blueprint("changes", __name__)


@changes_bp.route("", methods=["GET"])
@login_required
def list_changes():
    """List change requests with optional filters."""
    device_id = request.args.get("device_id", type=int)
    status = request.args.get("status")
    limit = request.args.get("limit", default=50, type=int)

    with get_db_session() as session:
        query = session.query(ChangeRequest)
        if device_id:
            query = query.filter(ChangeRequest.device_id == device_id)
        if status:
            query = query.filter(ChangeRequest.status == status)

        records = query.order_by(ChangeRequest.created_at.desc()).limit(limit).all()
        return jsonify([r.to_dict() for r in records]), 200


@changes_bp.route("/<change_id>", methods=["GET"])
@login_required
def get_change(change_id: str):
    """Retrieve details of a specific change request."""
    with get_db_session() as session:
        cr = session.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
        if not cr:
            return jsonify({"error": "NOT_FOUND", "message": f"Change request '{change_id}' not found"}), 404
        return jsonify(cr.to_dict()), 200


@changes_bp.route("/plan", methods=["POST"])
@login_required
def plan_change():
    """Create a planned change request without modifying device state."""
    data = request.get_json() or {}
    device_id = data.get("device_id")
    device_name = data.get("device_name")
    lines = data.get("lines", [])
    inverse_lines = data.get("inverse_lines", [])
    reason = data.get("reason", "")
    risk_override = data.get("risk_level")

    if not lines or not isinstance(lines, list):
        return jsonify({"error": "INVALID_PARAM", "message": "'lines' list is required"}), 400

    username = getattr(g, "user_id", "unknown")

    with get_db_session() as session:
        target_device_id = device_id
        if not target_device_id and device_name:
            dev = session.query(Device).filter(Device.name == device_name).first()
            if dev:
                target_device_id = dev.id

        if not target_device_id:
            return jsonify({"error": "DEVICE_NOT_FOUND", "message": "Valid device_id or device_name required"}), 400

        cr = ChangePipelineService.create_change_request(
            db_session=session,
            device_id=target_device_id,
            creator_id=username,
            lines=lines,
            inverse_lines=inverse_lines,
            reason=reason,
            risk_level=risk_override,
            job_id=data.get("job_id"),
            devices_count=data.get("devices_count", 1),
            interfaces_count=data.get("interfaces_count", 1),
        )
        return jsonify(cr.to_dict()), 201


@changes_bp.route("/<change_id>/precheck", methods=["POST"])
@login_required
def run_precheck(change_id: str):
    """Run pre-checks for a change request."""
    with get_db_session() as session:
        try:
            passed, results = ChangePipelineService.run_precheck(session, change_id)
            cr = session.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
            return jsonify({"passed": passed, "change": cr.to_dict()}), 200
        except KeyError as ke:
            return jsonify({"error": "NOT_FOUND", "message": str(ke)}), 404
        except ValueError as ve:
            return jsonify({"error": "INVALID_STATE", "message": str(ve)}), 400


@changes_bp.route("/<change_id>/approve", methods=["POST"])
@login_required
def approve_change(change_id: str):
    """Approve a change request enforcing RBAC and separation of duties."""
    username = getattr(g, "user_id", "unknown")
    user_role = getattr(g, "user_role", "operator")

    data = request.get_json() or {}
    confirmation = data.get("confirmation")

    with get_db_session() as session:
        try:
            cr = ChangePipelineService.approve(
                db_session=session,
                change_id=change_id,
                approver_username=username,
                approver_role=user_role,
                confirmation_token=confirmation,
            )
            return jsonify({"status": "approved", "change": cr.to_dict()}), 200
        except KeyError as ke:
            return jsonify({"error": "NOT_FOUND", "message": str(ke)}), 404
        except PermissionError as pe:
            return jsonify({"error": "FORBIDDEN", "message": str(pe)}), 403
        except ValueError as ve:
            return jsonify({"error": "INVALID_STATE", "message": str(ve)}), 400


@changes_bp.route("/<change_id>/reject", methods=["POST"])
@login_required
def reject_change(change_id: str):
    """Reject a change request."""
    username = getattr(g, "user_id", "unknown")
    data = request.get_json() or {}
    reason = data.get("reason", "")

    with get_db_session() as session:
        try:
            cr = ChangePipelineService.reject(session, change_id, rejecter_username=username, reason=reason)
            return jsonify({"status": "rejected", "change": cr.to_dict()}), 200
        except KeyError as ke:
            return jsonify({"error": "NOT_FOUND", "message": str(ke)}), 404
        except ValueError as ve:
            return jsonify({"error": "INVALID_STATE", "message": str(ve)}), 400


@changes_bp.route("/<change_id>/apply", methods=["POST"])
@login_required
def apply_change(change_id: str):
    """Apply an approved change request."""
    user_role = getattr(g, "user_role", "operator")
    if user_role == "viewer":
        return jsonify({"error": "FORBIDDEN", "message": "Viewers cannot apply changes"}), 403

    data = request.get_json() or {}
    save_after_apply = data.get("save_after_apply", False)

    with get_db_session() as session:
        cr = session.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
        if not cr:
            return jsonify({"error": "NOT_FOUND", "message": f"Change request '{change_id}' not found"}), 404

        # Idempotency check: if already verified/applied, return 409
        if cr.status == ChangeState.VERIFIED:
            return jsonify({"error": "ALREADY_APPLIED", "message": "Change is already applied and verified"}), 409

        if cr.status != ChangeState.APPLYING:
            return jsonify({"error": "INVALID_STATE", "message": f"Change status is '{cr.status}', must be 'applying'"}), 400

        try:
            # When testing or simulating without live SSH, create fake session or invoke service
            from backend.app.devices.pool import create_device_session
            device = session.query(Device).filter(Device.id == cr.device_id).first()
            dev_session = create_device_session(device.name, db_session=session, jitter=False) if device else None

            res = ChangePipelineService.apply(session, change_id, device_session=dev_session, save_after_apply=save_after_apply)
            return jsonify(res), 200
        except Exception as exc:
            return jsonify({"error": "APPLY_FAILED", "message": str(exc)}), 500


@changes_bp.route("/<change_id>/rollback", methods=["POST"])
@login_required
def rollback_change(change_id: str):
    """Rollback a change request using inverse lines."""
    user_role = getattr(g, "user_role", "operator")
    if user_role == "viewer":
        return jsonify({"error": "FORBIDDEN", "message": "Viewers cannot rollback changes"}), 403

    with get_db_session() as session:
        cr = session.query(ChangeRequest).filter(ChangeRequest.id == change_id).first()
        if not cr:
            return jsonify({"error": "NOT_FOUND", "message": f"Change request '{change_id}' not found"}), 404

        try:
            from backend.app.devices.pool import create_device_session
            device = session.query(Device).filter(Device.id == cr.device_id).first()
            dev_session = create_device_session(device.name, db_session=session, jitter=False) if device else None

            res = ChangePipelineService.rollback(session, change_id, device_session=dev_session)
            return jsonify(res), 200
        except Exception as exc:
            return jsonify({"error": "ROLLBACK_FAILED", "message": str(exc)}), 500
