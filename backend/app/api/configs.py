"""Device Configuration Snapshots and Diff REST API (Target Architecture §3 & Step 4.3)."""
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any, List

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.models.config_change import ConfigSnapshot
from backend.app.models.device import Device
from backend.app.services.config_backup import ConfigBackupService
from backend.app.jobs.engine import engine

configs_bp = Blueprint("configs", __name__)


@configs_bp.route("/<int:device_id>/configs", methods=["GET"])
@login_required
def list_device_configs(device_id: int):
    """List configuration snapshots for a given device."""
    kind = request.args.get("kind")
    limit = request.args.get("limit", default=50, type=int)

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        query = session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == device_id)
        if kind:
            query = query.filter(ConfigSnapshot.kind == kind)

        snapshots = query.order_by(ConfigSnapshot.taken_at.desc()).limit(limit).all()
        return jsonify([s.to_dict() for s in snapshots]), 200


@configs_bp.route("/<int:device_id>/configs/<snapshot_id>", methods=["GET"])
@login_required
def get_device_config(device_id: int, snapshot_id: str):
    """Retrieve metadata and decrypted configuration content for a snapshot."""
    with get_db_session() as session:
        snap = (
            session.query(ConfigSnapshot)
            .filter(ConfigSnapshot.id == snapshot_id, ConfigSnapshot.device_id == device_id)
            .first()
        )
        if not snap:
            return jsonify({"error": "NOT_FOUND", "message": f"Snapshot '{snapshot_id}' not found"}), 404

        decrypted = ConfigBackupService.get_snapshot_decrypted(session, snapshot_id)
        res = snap.to_dict()
        res["content"] = decrypted
        return jsonify(res), 200


@configs_bp.route("/<int:device_id>/configs/diff", methods=["GET"])
@login_required
def get_config_diff(device_id: int):
    """
    Generate unified text diff and structured JSON hunks between two snapshots.
    Query params:
        from: snapshot_id (optional, defaults to second-most recent)
        to: snapshot_id (optional, defaults to most recent)
    """
    from_id = request.args.get("from")
    to_id = request.args.get("to")

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        # If from/to not specified, resolve from latest two snapshots
        if not to_id or not from_id:
            latest_snaps = (
                session.query(ConfigSnapshot)
                .filter(ConfigSnapshot.device_id == device_id)
                .order_by(ConfigSnapshot.taken_at.desc())
                .limit(2)
                .all()
            )
            if len(latest_snaps) < 2:
                return jsonify({
                    "error": "INSUFFICIENT_SNAPSHOTS",
                    "message": "At least two snapshots are required to produce a diff",
                }), 400

            if not to_id:
                to_id = latest_snaps[0].id
            if not from_id:
                from_id = latest_snaps[1].id

        diff_result = ConfigBackupService.diff_snapshots(session, from_snapshot_id=from_id, to_snapshot_id=to_id)
        if not diff_result:
            return jsonify({"error": "NOT_FOUND", "message": "One or both snapshots could not be found"}), 404

        return jsonify(diff_result), 200


@configs_bp.route("/<int:device_id>/configs/backup", methods=["POST"])
@login_required
@role_required("admin")
def trigger_backup(device_id: int):
    """Submit a background job to backup configuration for this device."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "running")

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404
        device_name = dev.name

    username = getattr(g, "current_user", "system")
    job_id = engine.submit(
        job_type="config_backup",
        params={"kind": kind},
        user=username,
        mode="apply",
        target_devices=[device_name],
    )

    return jsonify({
        "status": "queued",
        "job_id": job_id,
        "device_id": device_id,
        "device_name": device_name,
        "kind": kind,
    }), 202


@configs_bp.route("/<int:device_id>/configs/timeline", methods=["GET"])
@login_required
def get_device_config_timeline(device_id: int):
    """Retrieve enriched snapshot timeline with who/what changed correlation."""
    kind = request.args.get("kind")
    limit = request.args.get("limit", default=50, type=int)

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        timeline = ConfigBackupService.get_device_timeline(session, device_id, kind=kind, limit=limit)
        return jsonify({
            "device_id": device_id,
            "device_name": dev.name,
            "count": len(timeline),
            "timeline": timeline,
        }), 200


@configs_bp.route("/<int:device_id>/configs/<snapshot_id>/download", methods=["GET"])
@login_required
def download_device_config(device_id: int, snapshot_id: str):
    """Download decrypted configuration as attachment text file."""
    with get_db_session() as session:
        dl_data = ConfigBackupService.get_download_data(session, device_id, snapshot_id)
        if not dl_data:
            return jsonify({"error": "NOT_FOUND", "message": f"Snapshot '{snapshot_id}' not found"}), 404

        from flask import Response
        return Response(
            dl_data["content"],
            mimetype=dl_data["mimetype"],
            headers={
                "Content-Disposition": f'attachment; filename="{dl_data["filename"]}"',
                "X-Checksum-SHA256": dl_data["sha256"],
            },
        )


@configs_bp.route("/<int:device_id>/compliance", methods=["GET"])
@login_required
def get_device_compliance(device_id: int):
    """Evaluate compliance rules against the latest configuration snapshot."""
    from backend.app.services.compliance import evaluate_device_compliance

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        report = evaluate_device_compliance(session, device_id)
        return jsonify(report), 200


# Dedicated Compliance Blueprint
compliance_bp = Blueprint("compliance", __name__)


@compliance_bp.route("/dashboard", methods=["GET"])
@login_required
def get_compliance_dashboard():
    """Evaluate fleet compliance dashboard with overall, rule, and province percentages."""
    from backend.app.services.compliance import evaluate_fleet_compliance
    province = request.args.get("province")

    with get_db_session() as session:
        data = evaluate_fleet_compliance(session, province=province)
        return jsonify(data), 200


@compliance_bp.route("/rules", methods=["GET"])
@login_required
def get_compliance_rules():
    """List all active compliance rules."""
    from backend.app.services.compliance import load_compliance_rules
    rules = load_compliance_rules()
    return jsonify({"count": len(rules), "rules": rules}), 200


@compliance_bp.route("/device/<int:device_id>", methods=["GET"])
@login_required
def get_device_compliance_route(device_id: int):
    """Evaluate compliance for a single device."""
    from backend.app.services.compliance import evaluate_device_compliance
    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404
        report = evaluate_device_compliance(session, device_id)
        return jsonify(report), 200

