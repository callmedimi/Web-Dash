"""Alarm Clear Blueprint (manual run, bulk run, CSV parsing, SSE streaming, CSV download)."""
import csv
import io
import json
import threading
import uuid
from datetime import datetime
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file, session

from auto_clear_noconf import process_one
from auth import login_required, permission_required
from audit import record_audit
from validators import validate_routers_list
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    read_only_blocked,
    parse_csv_to_routers,
    resolve_request_credentials,
)

alarm_clear_bp = Blueprint("alarm_clear_api", __name__)

# In-memory session store (legacy parity)
sessions: dict[str, dict] = {}
LOCK = threading.Lock()


def create_session() -> str:
    sid = uuid.uuid4().hex[:12]
    with LOCK:
        sessions[sid] = {
            "log_queue": Queue(),
            "logs": [],
            "report_data": [],
            "status": "pending",  # pending | running | done | error
            "error": None,
            "router_count": 0,
            "completed_count": 0,
        }
    return sid


def get_session(sid: str) -> dict | None:
    with LOCK:
        return sessions.get(sid)


def push_log(sid: str, message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    sess = get_session(sid)
    if sess is None:
        return
    sess["log_queue"].put(entry)
    sess["logs"].append(entry)


def finish_session(sid: str, error: str | None = None) -> None:
    sess = get_session(sid)
    if sess is None:
        return
    if error:
        sess["status"] = "error"
        sess["error"] = error
    else:
        sess["status"] = "done"
    sess["log_queue"].put(None)  # sentinel


def _run_manual(sid: str, routers: list[dict], username: str, password: str) -> None:
    sess = get_session(sid)
    if sess is None:
        return
    sess["status"] = "running"
    sess["router_count"] = len(routers)
    sess["result_lock"] = threading.Lock()

    def _log(msg, level="info"):
        push_log(sid, msg, level)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                process_one,
                r["name"],
                r["host"],
                username,
                password,
                _log,
                conn_timeout=r.get("conn_timeout", 30),
                cmd_timeout=r.get("cmd_timeout", 90),
            ): r["name"]
            for r in routers
        }
        for future in as_completed(futures):
            res = future.result()
            with sess["result_lock"]:
                sess["report_data"].extend(res["entries"])
                sess["completed_count"] += 1
                completed = sess["completed_count"]
            _log(
                f"[{completed}/{sess['router_count']}] "
                f"{res['name']}: {res['status']} — "
                f"{res['alarms_cleared']} cleared, {res['interfaces_shutdown']} shutdown",
                "info",
            )

    finish_session(sid)


def _run_bulk(sid: str, routers: list[dict], username: str, password: str) -> None:
    sess = get_session(sid)
    if sess is None:
        return
    sess["status"] = "running"
    sess["router_count"] = len(routers)
    sess["result_lock"] = threading.Lock()

    def _log(msg, level="info"):
        push_log(sid, msg, level)

    _log(f"Starting bulk processing of {len(routers)} router(s) ...", "info")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                process_one,
                r["name"],
                r["ip"],
                username,
                password,
                _log,
                conn_timeout=30,
                cmd_timeout=90,
            ): r["name"]
            for r in routers
        }
        for future in as_completed(futures):
            res = future.result()
            with sess["result_lock"]:
                sess["report_data"].extend(res["entries"])
                sess["completed_count"] += 1
                completed = sess["completed_count"]
            _log(
                f"[{completed}/{sess['router_count']}] "
                f"{res['name']}: {res['status']} — "
                f"{res['alarms_cleared']} cleared, {res['interfaces_shutdown']} shutdown",
                "info",
            )

    finish_session(sid)


@alarm_clear_bp.route("/run-manual", methods=["POST"])
@permission_required("alarm_clear_manual")
@read_only_blocked
def run_manual():
    data = get_json_payload()
    routers_raw = data.get("routers", [])
    username, password = resolve_request_credentials(data)

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = validate_routers_list(routers_raw, max_items=2000)

    sid = create_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "alarm_clear_manual", "router_count": len(routers)},
    )
    t = threading.Thread(target=_run_manual, args=(sid, routers, username, password), daemon=True)
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@alarm_clear_bp.route("/parse-csv", methods=["POST"])
@login_required
def parse_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    routers, err = parse_csv_to_routers(f)
    if err:
        return jsonify({"error": err}), 422
    if not routers:
        return jsonify({"error": "No valid router entries found in CSV"}), 422
    return jsonify({"routers": routers, "count": len(routers)})


@alarm_clear_bp.route("/run-bulk", methods=["POST"])
@permission_required("alarm_clear_bulk")
@read_only_blocked
def run_bulk():
    data = get_json_payload()
    routers_raw = data.get("routers", [])
    username, password = resolve_request_credentials(data)

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = validate_routers_list(routers_raw, max_items=2000)

    sid = create_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "alarm_clear_bulk", "router_count": len(routers)},
    )
    t = threading.Thread(target=_run_bulk, args=(sid, routers, username, password), daemon=True)
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@alarm_clear_bp.route("/stream/<sid>")
@login_required
def stream(sid):
    sess = get_session(sid)
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
            if entry is None:  # sentinel
                yield f"event: done\ndata: {json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@alarm_clear_bp.route("/download/<sid>")
@login_required
def download(sid):
    sess = get_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["report_data"]:
        return "No report data available", 404

    fieldnames = [
        "NE_Name",
        "Interface",
        "Sequence_Number",
        "Alarm_Description",
        "Action",
        "Clear_Status",
        "Timestamp",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in sess["report_data"]:
        row["Timestamp"] = now
        writer.writerow(row)

    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"alarm_clear_report_{sid}.csv",
    )


@alarm_clear_bp.route("/session/<sid>")
@login_required
def session_status(sid):
    sess = get_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
        "status": sess["status"],
        "router_count": sess["router_count"],
        "completed_count": sess["completed_count"],
        "report_count": len(sess["report_data"]),
        "error": sess["error"],
    })
