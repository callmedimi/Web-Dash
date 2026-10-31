"""SecureCRT / SSH Session Extractor Blueprint."""
import os
import re
import uuid
import threading
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file

from session_extractor_service import parse_session_csv, generate_sessions_zip
from backend.app.services.session_extractor import SessionExtractorService
from backend.app.extensions import get_db_session
from auth import login_required, permission_required
from backend.app.api.common import get_json_payload

sessions_export_bp = Blueprint("sessions_export_api", __name__)

session_extractor_jobs: dict[str, dict] = {}
SESSION_EXTRACTOR_LOCK = threading.Lock()


def create_session_extractor_job(routers: list[dict], subnets: list[dict], filename: str) -> str:
    sid = uuid.uuid4().hex[:12]
    with SESSION_EXTRACTOR_LOCK:
        now = datetime.now()
        expired = [
            k for k, v in session_extractor_jobs.items()
            if now - v.get("created_at", now) > timedelta(hours=2)
        ]
        for k in expired:
            session_extractor_jobs.pop(k, None)

        session_extractor_jobs[sid] = {
            "created_at": now,
            "filename": filename,
            "routers": routers,
            "subnets": subnets,
        }
    return sid


def get_session_extractor_job(sid: str) -> dict | None:
    with SESSION_EXTRACTOR_LOCK:
        return session_extractor_jobs.get(sid)


@sessions_export_bp.route("/session-extractor/parse", methods=["POST"])
@login_required
@permission_required("session_extractor")
def session_extractor_parse():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    content = f.read()
    routers, subnets, err = SessionExtractorService.parse_csv(content)
    if err:
        return jsonify({"error": err}), 422

    sid = create_session_extractor_job(routers, subnets, secure_filename(f.filename))
    return jsonify({
        "sid": sid,
        "filename": f.filename,
        "total_routers": len(routers),
        "subnets": subnets,
        "routers": routers[:200],
    })


@sessions_export_bp.route("/session-extractor/download", methods=["POST"])
@login_required
@permission_required("session_extractor")
def session_extractor_download():
    data = get_json_payload()
    sid = (data.get("sid") or "").strip()
    selected_subnets = data.get("selected_subnets")
    username = (data.get("username") or "").strip()
    preset = (data.get("preset") or "subnet_path").strip().lower()

    job = get_session_extractor_job(sid)
    if job is None:
        return jsonify({"error": "Session expired or not found. Please re-upload CSV."}), 404

    routers = job["routers"]
    zip_buffer = SessionExtractorService.generate_zip(
        routers=routers,
        preset=preset,
        selected_subnets=selected_subnets,
        username=username,
    )

    base_name = os.path.splitext(job.get("filename") or "sessions")[0]
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_filename = f"{safe_base}_sessions_{timestamp}.zip"

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_filename,
    )


# ---------------------------------------------------------------------------
# Modern Phase 5 REST Endpoints (/api/v1/sessions/*)
# ---------------------------------------------------------------------------

@sessions_export_bp.route("/api/v1/sessions/presets", methods=["GET"])
@login_required
def api_v1_sessions_presets():
    """List available folder hierarchy presets."""
    return jsonify({
        "presets": [
            {"id": "province_role", "name": "Province / Role", "description": "e.g. TEH/AGG/TEH-AGG01.ini"},
            {"id": "subnet_path", "name": "Subnet Path", "description": "NMS export folder path e.g. IPBH/Hormozgan/Router1.ini"},
            {"id": "province", "name": "Province Only", "description": "e.g. TEH/TEH-AGG01.ini"},
            {"id": "role", "name": "Role Only", "description": "e.g. AGG/TEH-AGG01.ini"},
            {"id": "flat", "name": "Flat Root", "description": "All session files in the root folder"},
        ]
    })


@sessions_export_bp.route("/api/v1/sessions/parse", methods=["POST"])
@login_required
def api_v1_sessions_parse():
    """Modern endpoint to parse CSV and initialize session extraction job."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    content = f.read()
    routers, subnets, err = SessionExtractorService.parse_csv(content)
    if err:
        return jsonify({"error": err, "status": "failed"}), 422

    sid = create_session_extractor_job(routers, subnets, secure_filename(f.filename))
    return jsonify({
        "status": "success",
        "sid": sid,
        "filename": f.filename,
        "total_routers": len(routers),
        "subnets": subnets,
        "sample": routers[:10],
    })


@sessions_export_bp.route("/api/v1/sessions/generate", methods=["POST"])
@login_required
def api_v1_sessions_generate():
    """Generate and stream SecureCRT sessions ZIP archive from job ID or inventory."""
    data = get_json_payload()
    sid = (data.get("sid") or "").strip()
    from_inventory = bool(data.get("from_inventory", False))
    preset = (data.get("preset") or "province_role").strip().lower()
    selected_subnets = data.get("selected_subnets")
    username = (data.get("username") or "").strip()
    filter_province = data.get("province")
    filter_role = data.get("role")

    if from_inventory or not sid:
        with get_db_session() as s:
            routers, zip_buffer = SessionExtractorService.extract_from_inventory(
                db_session=s,
                preset=preset,
                filter_province=filter_province,
                filter_role=filter_role,
                username=username,
            )
            base_name = f"inventory_{filter_province or 'fleet'}"
    else:
        job = get_session_extractor_job(sid)
        if job is None:
            return jsonify({"error": "Session expired or not found. Please re-upload CSV."}), 404

        routers = job["routers"]
        zip_buffer = SessionExtractorService.generate_zip(
            routers=routers,
            preset=preset,
            selected_subnets=selected_subnets,
            username=username,
        )
        base_name = os.path.splitext(job.get("filename") or "sessions")[0]

    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_filename = f"{safe_base}_securecrt_{preset}_{timestamp}.zip"

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_filename,
    )

