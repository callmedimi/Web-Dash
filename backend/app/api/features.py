"""Automation Catalog Features REST API (Phase 5)."""
from flask import Blueprint, request, jsonify, g
from typing import Dict, Any

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app.jobs.engine import engine

features_bp = Blueprint("features", __name__)


@features_bp.route("", methods=["GET"])
@features_bp.route("/", methods=["GET"])
@login_required
def list_features():
    """List all available automation catalog features with metadata."""
    features = feature_registry.list_features()
    return jsonify(features), 200


@features_bp.route("/<feature_key>", methods=["GET"])
@login_required
def get_feature(feature_key: str):
    """Retrieve metadata and parameter specification for a specific feature."""
    feature = feature_registry.get(feature_key)
    if not feature:
        return jsonify({"error": "NOT_FOUND", "message": f"Feature '{feature_key}' not found"}), 404
    return jsonify(feature.spec.to_dict()), 200


@features_bp.route("/<feature_key>/run", methods=["POST"])
@login_required
def run_feature(feature_key: str):
    """Execute a feature synchronously or trigger via JobEngine."""
    feature = feature_registry.get(feature_key)
    if not feature:
        return jsonify({"error": "NOT_FOUND", "message": f"Feature '{feature_key}' not found"}), 404

    payload = request.get_json(silent=True) or {}
    as_job = payload.get("as_job", False)
    dry_run = payload.get("dry_run", False)

    user_id = getattr(g, "user_id", None)

    if as_job:
        job = engine.create_job(
            name=f"Feature: {feature.spec.name}",
            job_type=f"feature_{feature_key}",
            created_by_id=user_id,
            meta_info={"feature_key": feature_key, "dry_run": dry_run},
        )
        task = engine.add_task(
            job_id=job.id,
            task_type="inventory_sync" if feature_key == "inventory_discovery" else f"feature_{feature_key}",
            device_name=None,
            params=payload,
        )
        engine.start_job(job.id)
        return jsonify({
            "status": "queued",
            "job_id": job.id,
            "task_id": task.id,
            "feature": feature_key,
        }), 202

    # Synchronous execution
    with get_db_session() as session:
        ctx = FeatureContext(
            db_session=session,
            user_id=user_id,
            params=payload,
            dry_run=dry_run,
        )
        try:
            result = feature.run(ctx)
            return jsonify(result), 200
        except Exception as e:
            return jsonify({
                "error": "EXECUTION_ERROR",
                "message": str(e),
                "feature": feature_key,
            }), 500
