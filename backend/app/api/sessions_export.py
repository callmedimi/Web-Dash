"""SecureCRT / SSH Session Extractor Blueprint."""
import os
import re
import uuid
import threading
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file

from session_extractor_service import parse_session_csv, generate_sessions_zip
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
    routers, subnets, err = parse_session_csv(content)
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

    job = get_session_extractor_job(sid)
    if job is None:
        return jsonify({"error": "Session expired or not found. Please re-upload CSV."}), 404

    if not selected_subnets:
        return jsonify({"error": "No subnet paths selected."}), 400

    routers = job["routers"]
    zip_buffer = generate_sessions_zip(routers, selected_subnets=selected_subnets, username=username)

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
