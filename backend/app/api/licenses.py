"""License Management REST API Blueprint (Target Architecture §3 & Phase 5 Step 5.4)."""
from flask import Blueprint, request, jsonify, g, session
from typing import Dict, Any, List

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.services.license import LicenseService
from backend.app.models.device import Device
from backend.app.models.license import LicenseRecord
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext

licenses_bp = Blueprint("licenses", __name__)


@licenses_bp.route("/fleet", methods=["GET"])
@login_required
def get_fleet_table():
    """Retrieve paginated router fleet license table with filters."""
    province = request.args.get("province")
    alert_level = request.args.get("alert_level")
    product = request.args.get("product")
    state = request.args.get("state")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 50)), 200)

    with get_db_session() as db_sess:
        res = LicenseService.list_fleet_licenses(
            db_session=db_sess,
            province=province,
            alert_level=alert_level,
            product=product,
            state=state,
            search=search,
            page=page,
            page_size=page_size,
        )
        return jsonify(res), 200


@licenses_bp.route("/summary", methods=["GET"])
@login_required
def get_fleet_summary():
    """Retrieve high-level fleet license statistics and alert breakdowns."""
    province = request.args.get("province")
    with get_db_session() as db_sess:
        summary = LicenseService.get_fleet_summary(db_sess, province=province)
        return jsonify(summary), 200


@licenses_bp.route("/check", methods=["POST"])
@login_required
def run_license_check():
    """Run on-demand license scan across target routers."""
    feature = feature_registry.get("license_management")
    if not feature:
        return jsonify({"error": "FEATURE_UNAVAILABLE", "message": "License feature not registered"}), 500

    payload = request.get_json(silent=True) or {}
    user_id = session.get("user", {}).get("id") or getattr(g, "user_id", None)

    with get_db_session() as db_sess:
        ctx = FeatureContext(
            db_session=db_sess,
            user_id=user_id,
            params=payload,
        )
        res = feature.run(ctx)
        return jsonify(res), 200


@licenses_bp.route("/devices/<int:device_id>", methods=["GET"])
@login_required
def get_device_license_detail(device_id: int):
    """Retrieve full license details, features, and capacity items for a specific device."""
    with get_db_session() as db_sess:
        dev = db_sess.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        rec = db_sess.query(LicenseRecord).filter(LicenseRecord.device_id == device_id).first()
        if not rec:
            return jsonify({
                "device_id": dev.id,
                "device_name": dev.name,
                "mgmt_ip": dev.mgmt_ip,
                "license_state": "Not Scanned",
                "alert_level": "UNSCANNED",
                "days_to_expiry": None,
                "features": [],
                "items": [],
            }), 200

        return jsonify(rec.to_dict()), 200


@licenses_bp.route("/alerts", methods=["GET"])
@login_required
def get_license_alerts():
    """Retrieve current expiring and expired license alerts (<= 90/60/30/7 days)."""
    with get_db_session() as db_sess:
        alerts = LicenseService.check_expiring_licenses(db_sess)
        return jsonify({"alerts": alerts, "total_alerts": len(alerts)}), 200


@licenses_bp.route("/renewal/match", methods=["POST"])
@login_required
def match_renewal_license_file():
    """Upload XML or ZIP license file and match to inventory routers by ESN."""
    if "file" not in request.files:
        return jsonify({"error": "NO_FILE", "message": "No file uploaded in form data 'file'"}), 400

    uploaded = request.files["file"]
    filename = uploaded.filename or "license.xml"
    content = uploaded.read()

    with get_db_session() as db_sess:
        parsed_entries = LicenseService.parse_license_file_content(content, filename)
        matched, unmatched = LicenseService.match_license_to_devices(db_sess, parsed_entries)
        return jsonify({
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
            "matched": matched,
            "unmatched": unmatched,
        }), 200


@licenses_bp.route("/renewal/plan", methods=["POST"])
@login_required
def plan_license_renewal():
    """Create planned ChangeRequest for activating license file via Safe Change Pipeline."""
    payload = request.get_json(silent=True) or {}
    device_id = payload.get("device_id")
    license_filename = payload.get("license_filename")
    reason = payload.get("reason", "Scheduled License Renewal")

    if not device_id or not license_filename:
        return jsonify({"error": "MISSING_PARAMS", "message": "device_id and license_filename are required"}), 400

    user_name = session.get("user", {}).get("username") or "admin"

    with get_db_session() as db_sess:
        dev = db_sess.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        cr = LicenseService.plan_license_renewal(
            db_session=db_sess,
            device=dev,
            license_filename=license_filename,
            creator_id=user_name,
            reason=reason,
        )
        return jsonify({
            "change_request_id": cr.id,
            "status": cr.status.value if hasattr(cr.status, "value") else str(cr.status),
            "device_id": dev.id,
            "device_name": dev.name,
            "commands": cr.plan.get("lines", []),
            "diff": cr.diff,
        }), 201
