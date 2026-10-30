"""PTP Live Hop-by-Hop Troubleshooting Blueprint."""
import json
import logging
import threading
import uuid
from datetime import datetime
from queue import Queue, Empty

from flask import Blueprint, request, jsonify, Response, stream_with_context, session

from ptp_troubleshoot_service import search_candidate_routers, run_ptp_troubleshoot_traceback
from auth import login_required, permission_required
from audit import record_audit
from validators import sanitize_cli_arg, validate_timeout
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    resolve_request_credentials,
)

ptp_bp = Blueprint("ptp_api", __name__)
logger = logging.getLogger(__name__)

ptp_sessions: dict[str, dict] = {}
PTP_LOCK = threading.Lock()


def create_ptp_session(target: str) -> str:
    sid = uuid.uuid4().hex[:12]
    with PTP_LOCK:
        ptp_sessions[sid] = {
            "target": target,
            "log_queue": Queue(),
            "logs": [],
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.now(),
        }
    return sid


def get_ptp_session(sid: str) -> dict | None:
    with PTP_LOCK:
        return ptp_sessions.get(sid)


def push_ptp_log(sid: str, message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    sess = get_ptp_session(sid)
    if sess is None:
        return
    sess["log_queue"].put(entry)
    sess["logs"].append(entry)


def finish_ptp_session(sid: str, result: dict | None = None, error: str | None = None) -> None:
    sess = get_ptp_session(sid)
    if sess is None:
        return
    if error:
        sess["status"] = "error"
        sess["error"] = error
    else:
        sess["status"] = "done"
        sess["result"] = result
    sess["log_queue"].put(None)


def _run_ptp_worker(sid: str, target: str, username: str, password: str, max_hops: int = 5):
    def _log(msg: str, level: str = "info"):
        push_ptp_log(sid, msg, level)

    try:
        sess = get_ptp_session(sid)
        if sess:
            sess["status"] = "running"

        push_ptp_log(sid, f"Diagnostic job initialized for target '{target}'.", "info")
        report = run_ptp_troubleshoot_traceback(
            target_identifier=target,
            username=username,
            password=password,
            log_callback=_log,
            max_hops=max_hops,
        )
        finish_ptp_session(sid, result=report)
    except Exception as exc:
        logger.exception("PTP troubleshooting job failed")
        push_ptp_log(sid, f"Fatal error during diagnostic traceback: {exc}", "error")
        finish_ptp_session(sid, error=str(exc))


@ptp_bp.route("/ptp/search-targets", methods=["POST"])
@login_required
@permission_required("ptp_troubleshoot")
def ptp_search_targets():
    data = get_json_payload(silent=True)
    keyword = (data.get("keyword") or "").strip()

    if not keyword:
        return jsonify({"candidates": [], "count": 0})

    try:
        candidates = search_candidate_routers(keyword)
        return jsonify({"candidates": candidates, "count": len(candidates)})
    except Exception as e:
        logger.exception("PTP target search failed")
        return jsonify({"error": f"Search failed: {e}", "candidates": []}), 500


@ptp_bp.route("/ptp/start-troubleshoot", methods=["POST"])
@login_required
@permission_required("ptp_troubleshoot")
def ptp_start_troubleshoot():
    data = get_json_payload(silent=True)
    target_raw = (data.get("target") or data.get("host") or "").strip()
    if not target_raw:
        return jsonify({"error": "Target router name, Site Code, or IP is required"}), 400
    target = sanitize_cli_arg(target_raw, "target")

    username, password = resolve_request_credentials(data)

    # Fallback to active Flask session credentials
    if not username or not password:
        sess_creds = session.get("network_creds") or session.get("creds") or {}
        if not username:
            username = (sess_creds.get("username") or "").strip()
        if not password:
            password = sess_creds.get("password") or ""

    max_hops = validate_timeout(data.get("max_hops", 5), default=5, min_val=1, max_val=20)

    if not username or not password:
        return jsonify({
            "error": "Network credentials (Username and Password) are required for live SSH diagnostic."
        }), 400

    sid = create_ptp_session(target)
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "ptp_troubleshoot", "target": target},
    )
    worker_t = threading.Thread(
        target=_run_ptp_worker,
        args=(sid, target, username, password, max_hops),
        daemon=True,
    )
    worker_t.start()

    return jsonify({
        "status": "started",
        "session_id": sid,
        "target": target,
    })


@ptp_bp.route("/ptp/stream/<sid>")
@login_required
@permission_required("ptp_troubleshoot")
def ptp_stream(sid):
    sess = get_ptp_session(sid)
    if sess is None:
        return "Session not found", 404

    def generate():
        q = sess["log_queue"]
        while True:
            try:
                entry = q.get(timeout=30)
            except Empty:
                yield ": keepalive\n\n"
                continue
            if entry is None:
                yield f"event: done\ndata: {json.dumps({'status': sess['status'], 'error': sess['error'], 'result': sess['result']})}\n\n"
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Credentials": "true",
        },
    )


@ptp_bp.route("/ptp/session/<sid>", methods=["GET"])
@login_required
@permission_required("ptp_troubleshoot")
def ptp_session_details(sid):
    sess = get_ptp_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "session_id": sid,
        "target": sess.get("target"),
        "status": sess.get("status"),
        "error": sess.get("error"),
        "logs": sess.get("logs", []),
        "result": sess.get("result"),
    })
