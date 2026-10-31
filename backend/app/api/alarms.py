"""Alarm Center REST API Blueprint (Target Architecture §3 & Phase 5 Step 5.2)."""
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any, List

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.services.alarm_center import AlarmCenterService
from backend.app.models.alarm import AlarmFilter
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext

alarms_bp = Blueprint("alarm_center", __name__)


@alarms_bp.route("/active", methods=["POST", "GET"])
@login_required
def get_active_alarms():
    """
    Query active alarms on target routers with rich filtering.
    Accepts criteria in JSON body (POST) or query string (GET).
    """
    if request.method == "POST":
        params = request.get_json(silent=True) or {}
    else:
        params = request.args.to_dict()

    feature = feature_registry.get("alarm_center")
    if not feature:
        return jsonify({"error": "FEATURE_UNAVAILABLE", "message": "Alarm Center feature not registered"}), 500

    user_id = getattr(g, "user_id", None)
    with get_db_session() as session:
        ctx = FeatureContext(
            db_session=session,
            user_id=user_id,
            params=params,
        )
        result = feature.run(ctx)
        return jsonify(result), 200


@alarms_bp.route("/statistics", methods=["POST"])
@login_required
def get_alarm_statistics():
    """Compute statistics (noisy devices/interfaces, age histogram) on provided alarms."""
    payload = request.get_json() or {}
    alarm_items = payload.get("alarms") or []
    stats = AlarmCenterService.compute_statistics(alarm_items)
    return jsonify(stats), 200


@alarms_bp.route("/clear-plan", methods=["POST"])
@login_required
@role_required("admin", "operator")
def plan_alarm_clear():
    """
    Plan an alarm clear change through the Safe Change Pipeline.
    Enforces Plan -> Precheck -> Approve -> Apply -> Verify.
    """
    payload = request.get_json() or {}
    alarm_items = payload.get("alarms") or []
    noconf_shutdown = payload.get("noconf_shutdown", False)

    if not alarm_items:
        return jsonify({"error": "VALIDATION_ERROR", "message": "alarms list cannot be empty"}), 400

    creator = getattr(g, "username", "operator")
    with get_db_session() as session:
        change_requests = AlarmCenterService.plan_alarm_clears(
            session=session,
            alarm_items=alarm_items,
            creator_id=creator,
            noconf_shutdown=noconf_shutdown,
        )
        return jsonify({
            "status": "planned",
            "count": len(change_requests),
            "change_requests": change_requests,
        }), 201


# --- Saved Alarm Filters CRUD ---

@alarms_bp.route("/filters", methods=["GET"])
@login_required
def list_alarm_filters():
    """List saved alarm filter presets."""
    with get_db_session() as session:
        filters = session.query(AlarmFilter).order_by(AlarmFilter.name).all()
        return jsonify([f.to_dict() for f in filters]), 200


@alarms_bp.route("/filters", methods=["POST"])
@login_required
def create_alarm_filter():
    """Save an alarm filter preset."""
    payload = request.get_json() or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "VALIDATION_ERROR", "message": "name is required"}), 400

    with get_db_session() as session:
        existing = session.query(AlarmFilter).filter(AlarmFilter.name == name).first()
        if existing:
            return jsonify({"error": "ALREADY_EXISTS", "message": f"Filter '{name}' already exists"}), 409

        flt = AlarmFilter(
            name=name,
            description=payload.get("description"),
            criteria=payload.get("criteria") or {},
            created_by_id=getattr(g, "user_id", None),
        )
        session.add(flt)
        session.commit()
        return jsonify(flt.to_dict()), 201


@alarms_bp.route("/filters/<int:filter_id>", methods=["GET"])
@login_required
def get_alarm_filter(filter_id: int):
    """Retrieve saved alarm filter by ID."""
    with get_db_session() as session:
        flt = session.query(AlarmFilter).filter(AlarmFilter.id == filter_id).first()
        if not flt:
            return jsonify({"error": "NOT_FOUND", "message": f"Filter {filter_id} not found"}), 404
        return jsonify(flt.to_dict()), 200


@alarms_bp.route("/filters/<int:filter_id>", methods=["DELETE"])
@login_required
def delete_alarm_filter(filter_id: int):
    """Delete saved alarm filter."""
    with get_db_session() as session:
        flt = session.query(AlarmFilter).filter(AlarmFilter.id == filter_id).first()
        if not flt:
            return jsonify({"error": "NOT_FOUND", "message": f"Filter {filter_id} not found"}), 404
        session.delete(flt)
        session.commit()
        return jsonify({"status": "deleted", "filter_id": filter_id}), 200
