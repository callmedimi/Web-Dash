#!/usr/bin/env python3
import csv
import io
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

import netmiko
from werkzeug.utils import secure_filename

from flask import (
    Flask, render_template, request, jsonify, Response, stream_with_context, send_file, session
)

from auto_clear_noconf import process_one
from reporting_logic import (
    process_one_report, extract_provinces, filter_routers_by_province,
    compute_analytics, FIELD_NAMES
)
from check_vrf_routing import (
    parse_interface_config, batch_check_routing,
    check_bgp_route, query_vrf_route_and_configs, transform_originator_ip,
    get_sysname,
    HARDCODED_ROUTER_NAME, HARDCODED_ROUTER_IP, HARDCODED_RR_IP,
)
from license_check import check_license_on_router
from license_renewal_logic import LicenseRenewalProcessor
from services.zabbix_service import ZabbixService, create_zabbix_service
from services.license_db import add_renewal_report, get_all_renewal_reports, get_renewal_report
from auth import (
    authenticate, login_required, permission_required, get_accessible_features,
    get_all_users, create_user, update_user, delete_user,
)
from site_arp_service import (
    lookup_site_arp_mac_details,
    parse_ne_csv_content,
    start_collector_job,
    get_collector_job_status,
    stop_collector_job,
    TARGET_NE_PREFIXES,
)

app = Flask(__name__)
_secret_key_file = os.path.join(os.path.dirname(__file__), ".secret_key")
if os.environ.get("FLASK_SECRET_KEY"):
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
elif os.path.exists(_secret_key_file):
    with open(_secret_key_file, "r") as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(_secret_key_file, "w") as f:
        f.write(app.secret_key)

app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'noc_uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------------------------------------------------------------------------
# License renewal session store
# ---------------------------------------------------------------------------
lic_renewal_sessions: dict[str, dict] = {}
LIC_RENEWAL_LOCK = threading.Lock()


def create_lic_renewal_session() -> str:
    sid = uuid.uuid4().hex[:12]
    with LIC_RENEWAL_LOCK:
        lic_renewal_sessions[sid] = {
            "log_queue": Queue(),
            "logs": [],
            "report_data": [],
            "status": "pending",
            "error": None,
            "router_count": 0,
            "completed_count": 0,
            "pending_confirmations": {},
            "confirmation_events": {},
            "confirmation_results": {},
        }
    return sid


def get_lic_renewal_session(sid: str) -> dict | None:
    with LIC_RENEWAL_LOCK:
        return lic_renewal_sessions.get(sid)


def push_lic_renewal_log(sid: str, message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    sess = get_lic_renewal_session(sid)
    if sess is None:
        return
    sess["log_queue"].put(entry)
    sess["logs"].append(entry)


def finish_lic_renewal_session(sid: str, error: str | None = None) -> None:
    sess = get_lic_renewal_session(sid)
    if sess is None:
        return
    if error:
        sess["status"] = "error"
        sess["error"] = error
    else:
        sess["status"] = "done"
    sess["log_queue"].put(None)

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Report session store (separate from alarm-clear sessions)
# ---------------------------------------------------------------------------
report_sessions: dict[str, dict] = {}
REPORT_LOCK = threading.Lock()


def create_report_session() -> str:
    sid = uuid.uuid4().hex[:12]
    with REPORT_LOCK:
        report_sessions[sid] = {
            "log_queue": Queue(),
            "logs": [],
            "report_data": [],
            "noconf_data": [],
            "status": "pending",
            "error": None,
            "router_count": 0,
            "completed_count": 0,
        }
    return sid


def get_report_session(sid: str) -> dict | None:
    with REPORT_LOCK:
        return report_sessions.get(sid)


def push_report_log(sid: str, message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    sess = get_report_session(sid)
    if sess is None:
        return
    sess["log_queue"].put(entry)
    sess["logs"].append(entry)


def finish_report_session(sid: str, error: str | None = None) -> None:
    sess = get_report_session(sid)
    if sess is None:
        return
    if error:
        sess["status"] = "error"
        sess["error"] = error
    else:
        sess["status"] = "done"
    sess["log_queue"].put(None)


# ---------------------------------------------------------------------------
# License-check session store
# ---------------------------------------------------------------------------
license_sessions: dict[str, dict] = {}
LICENSE_LOCK = threading.Lock()


def create_license_session() -> str:
    sid = uuid.uuid4().hex[:12]
    with LICENSE_LOCK:
        license_sessions[sid] = {
            "log_queue": Queue(),
            "logs": [],
            "license_data": [],
            "status": "pending",
            "error": None,
            "router_count": 0,
            "completed_count": 0,
            "cancel_flag": False,
        }
    return sid


def get_license_session(sid: str) -> dict | None:
    with LICENSE_LOCK:
        return license_sessions.get(sid)


def push_license_log(sid: str, message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    sess = get_license_session(sid)
    if sess is None:
        return
    sess["log_queue"].put(entry)
    sess["logs"].append(entry)


def finish_license_session(sid: str, error: str | None = None) -> None:
    sess = get_license_session(sid)
    if sess is None:
        return
    if error:
        sess["status"] = "error"
        sess["error"] = error
    else:
        sess["status"] = "done"
    sess["log_queue"].put(None)


def _run_license_check(sid: str, routers: list[dict], username: str, password: str) -> None:
    sess = get_license_session(sid)
    if sess is None:
        return
    sess["status"] = "running"
    sess["router_count"] = len(routers)
    sess["result_lock"] = threading.Lock()

    def _log(msg, level="info"):
        push_license_log(sid, msg, level)

    def _cancelled():
        s = get_license_session(sid)
        return s is not None and s["cancel_flag"]

    _log(f"Starting license check for {len(routers)} device(s) ...", "info")

    with ThreadPoolExecutor(max_workers=10) as executor:
        fut_map = {}
        for r in routers:
            if _cancelled():
                break
            fut = executor.submit(
                check_license_on_router, r["name"], r["ip"], username, password, _log,
                conn_timeout=30, cmd_timeout=90
            )
            fut_map[fut] = r["name"]

        for future in as_completed(fut_map):
            if _cancelled():
                for f in fut_map:
                    f.cancel()
                break
            res = future.result()
            with sess["result_lock"]:
                sess["license_data"].append(res)
                sess["completed_count"] += 1
                completed = sess["completed_count"]
            status_icon = "OK" if res["status"] == "success" else "FAIL"
            lic = res.get("license_info", {})
            items_count = len(res.get("license_verbose_info", {}).get("items", []))
            _log(
                f"[{completed}/{sess['router_count']}] "
                f"{res['name']}: {status_icon} — "
                f"{lic.get('product_name', '?')} | State: {lic.get('license_state', '?')} | {items_count} items",
                "success" if res["status"] == "success" else "error",
            )

    sess = get_license_session(sid)
    if sess and sess["cancel_flag"]:
        _log("License check cancelled by user", "warn")

    finish_license_session(sid)


# ---------------------------------------------------------------------------
# CSV parsing (reproduces node_data_struct.py logic)
# ---------------------------------------------------------------------------
def parse_csv_to_routers(file_storage) -> tuple[list[dict], str | None]:
    raw = file_storage.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    lines = text.splitlines()

    def _clean(line: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)

    header_idx = -1
    for i, line in enumerate(lines):
        if _clean(line).strip().startswith("NE Name,"):
            header_idx = i
            break

    if header_idx == -1:
        return [], "Could not find header row starting with 'NE Name,'"

    cleaned = [_clean(l) for l in lines]
    reader = csv.DictReader(cleaned[header_idx:])
    if "NE Name" not in (reader.fieldnames or []):
        return [], f"'NE Name' not in parsed headers: {reader.fieldnames}"

    routers = []
    for row in reader:
        ne = row.get("NE Name", "").strip()
        ip = row.get("NE IP Address", "").strip()
        if not ne or not ip:
            continue
        esn_val = (
            row.get("ESN") or row.get("esn") or row.get("Serial Number") or
            row.get("Equipment ESN") or row.get("NE ESN") or ""
        ).strip()
        routers.append({
            "name": ne,
            "ip": ip,
            "ne_type": row.get("NE Type (MPU Type)", "").strip(),
            "version": row.get("Software Version", "").strip(),
            "lsr_id": row.get("LSR ID", "").strip(),
            "esn": esn_val,
        })

    return routers, None


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------
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
            executor.submit(process_one, r["name"], r["host"], username, password, _log,
                           conn_timeout=r.get("conn_timeout", 30),
                           cmd_timeout=r.get("cmd_timeout", 90)): r["name"]
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
            executor.submit(process_one, r["name"], r["ip"], username, password, _log,
                           conn_timeout=30, cmd_timeout=90): r["name"]
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


# ---------------------------------------------------------------------------
# Report background runner
# ---------------------------------------------------------------------------
def _run_report(sid: str, routers: list[dict], username: str, password: str, age_value=2, age_unit='days') -> None:
    sess = get_report_session(sid)
    if sess is None:
        return
    sess["status"] = "running"
    sess["router_count"] = len(routers)
    sess["result_lock"] = threading.Lock()

    def _log(msg, level="info"):
        push_report_log(sid, msg, level)

    _log(f"Starting down-links report for {len(routers)} device(s) ...", "info")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(
                process_one_report, r["name"], r["ip"], username, password, _log,
                conn_timeout=30, cmd_timeout=90,
                age_value=age_value, age_unit=age_unit
            ): r["name"]
            for r in routers
        }
        for future in as_completed(futures):
            res = future.result()
            with sess["result_lock"]:
                sess["report_data"].extend(res["data"])
                sess["noconf_data"].extend(res["noconf_data"])
                sess["completed_count"] += 1
                completed = sess["completed_count"]
            _log(
                f"[{completed}/{sess['router_count']}] "
                f"{res['name']}: {res['status']} — "
                f"{len(res['data'])} service, {len(res['noconf_data'])} noconf",
                "info",
            )

    sess["analytics"] = compute_analytics(sess["report_data"], sess["noconf_data"])
    finish_report_session(sid)


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    user_info = authenticate(username, password)
    if user_info is None:
        return jsonify({"error": "Invalid credentials"}), 401
    session["user"] = user_info
    return jsonify({
        "username": username,
        "role": user_info["role"],
        "display_name": user_info["display_name"],
        "features": get_accessible_features(user_info),
    })


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"status": "logged_out"})


@app.route("/me")
def current_user():
    user_info = session.get("user")
    if user_info is None:
        return jsonify({"authenticated": False}), 200
    return jsonify({
        "authenticated": True,
        "username": user_info["username"],
        "role": user_info["role"],
        "display_name": user_info["display_name"],
        "features": get_accessible_features(user_info),
    })


@app.route("/admin/users", methods=["GET"])
@permission_required("user_management")
def admin_list_users():
    users = get_all_users()
    return jsonify({"users": users})


@app.route("/admin/users", methods=["POST"])
@permission_required("user_management")
def admin_create_user():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()
    display_name = (data.get("display_name") or "").strip()
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if role not in ("god", "admin", "user"):
        return jsonify({"error": "Invalid role"}), 400
    err = create_user(username, password, role, display_name)
    if err:
        return jsonify({"error": err}), 409
    return jsonify({"status": "created"})


@app.route("/admin/users/<username>", methods=["PUT"])
@permission_required("user_management")
def admin_update_user(username):
    data = request.get_json(force=True)
    current_info = session.get("user", {})
    if username == current_info.get("username") and data.get("role") and data["role"] != current_info.get("role"):
        return jsonify({"error": "Cannot change your own role"}), 403
    err = update_user(username, data)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"status": "updated"})


@app.route("/admin/users/<username>", methods=["DELETE"])
@permission_required("user_management")
def admin_delete_user(username):
    current_info = session.get("user", {})
    if username == current_info.get("username"):
        return jsonify({"error": "Cannot delete yourself"}), 403
    err = delete_user(username)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"status": "deleted"})


@app.route("/admin/permissions", methods=["GET"])
@permission_required("permission_management")
def admin_get_permissions():
    users = get_all_users()
    clean = {}
    for username, info in users.items():
        clean[username] = {
            "role": info["role"],
            "display_name": info["display_name"],
            "permissions": info.get("permissions", {}),
        }
    return jsonify({"users": clean})


@app.route("/admin/permissions/<username>", methods=["PUT"])
@permission_required("permission_management")
def admin_set_permissions(username):
    data = request.get_json(force=True)
    permissions = data.get("permissions", {})
    users = get_all_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    update_user(username, {"permissions": permissions})
    return jsonify({"status": "updated"})


# ---------------------------------------------------------------------------
# Feature routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run-manual", methods=["POST"])
@permission_required("alarm_clear_manual")
def run_manual():
    data = request.get_json(force=True)
    routers_raw = data.get("routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = []
    for r in routers_raw:
        host = (r.get("host") or "").strip()
        name = (r.get("name") or "").strip() or host
        if host:
            routers.append({"name": name, "host": host})

    if not routers:
        return jsonify({"error": "At least one valid router entry is required"}), 400

    sid = create_session()
    t = threading.Thread(target=_run_manual, args=(sid, routers, username, password), daemon=True)
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@app.route("/parse-csv", methods=["POST"])
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


@app.route("/run-bulk", methods=["POST"])
@permission_required("alarm_clear_bulk")
def run_bulk():
    data = request.get_json(force=True)
    routers_raw = data.get("routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = []
    for r in routers_raw:
        name = (r.get("name") or "").strip()
        ip = (r.get("ip") or "").strip()
        if name and ip:
            routers.append({"name": name, "ip": ip})

    if not routers:
        return jsonify({"error": "At least one valid router entry is required"}), 400

    sid = create_session()
    t = threading.Thread(target=_run_bulk, args=(sid, routers, username, password), daemon=True)
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@app.route("/stream/<sid>")
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
                yield f": keepalive\n\n"
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


@app.route("/download/<sid>")
@login_required
def download(sid):
    sess = get_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["report_data"]:
        return "No report data available", 404

    fieldnames = [
        "NE_Name", "Interface", "Sequence_Number", "Alarm_Description",
        "Action", "Clear_Status", "Timestamp",
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


@app.route("/session/<sid>")
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


# ---------------------------------------------------------------------------
# Reporting Routes
# ---------------------------------------------------------------------------
@app.route("/parse-csv-nodes", methods=["POST"])
@login_required
def parse_csv_nodes():
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
    provinces = extract_provinces(routers)
    return jsonify({"routers": routers, "provinces": provinces, "count": len(routers)})


@app.route("/run-report", methods=["POST"])
@permission_required("reporting")
def run_report():
    data = request.get_json(force=True)
    routers_raw = data.get("routers", [])
    province = (data.get("province") or "").strip().upper()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    age_value = int(data.get("age_value", 2))
    age_unit = data.get("age_unit", "days")

    if not province:
        return jsonify({"error": "Province code is required"}), 400
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    filtered = filter_routers_by_province(routers_raw, province)
    if not filtered:
        return jsonify({"error": f"No routers found matching province '_{province}'"}), 422

    sid = create_report_session()
    t = threading.Thread(
        target=_run_report, args=(sid, filtered, username, password),
        kwargs={"age_value": age_value, "age_unit": age_unit}, daemon=True
    )
    t.start()
    return jsonify({
        "session_id": sid,
        "router_count": len(filtered),
        "province": province,
    })


@app.route("/run-full-report", methods=["POST"])
@permission_required("reporting")
def run_full_report():
    data = request.get_json(force=True)
    routers_raw = data.get("routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    age_value = int(data.get("age_value", 2))
    age_unit = data.get("age_unit", "days")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not routers_raw:
        return jsonify({"error": "No routers provided"}), 400

    sid = create_report_session()
    t = threading.Thread(
        target=_run_report, args=(sid, routers_raw, username, password),
        kwargs={"age_value": age_value, "age_unit": age_unit}, daemon=True
    )
    t.start()
    return jsonify({
        "session_id": sid,
        "router_count": len(routers_raw),
        "province": "ALL",
    })


@app.route("/stream-report/<sid>")
@login_required
def stream_report(sid):
    sess = get_report_session(sid)
    if sess is None:
        return "Session not found", 404

    def generate():
        q = sess["log_queue"]
        while True:
            try:
                entry = q.get(timeout=30)
            except Empty:
                yield f": keepalive\n\n"
                continue
            if entry is None:
                yield (
                    f"event: done\ndata: "
                    f"{json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                )
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download-report/<sid>")
@login_required
def download_report(sid):
    sess = get_report_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["report_data"] and not sess["noconf_data"]:
        return "No report data available", 404

    all_rows = sess["report_data"] + sess["noconf_data"]
    all_rows.sort(key=lambda x: (x.get('NE NAME', ''), x.get('interface name', '')))

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELD_NAMES)
    writer.writeheader()
    writer.writerows(all_rows)

    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"down_links_report_{sid}.csv",
    )


@app.route("/report-session/<sid>")
@login_required
def report_session_status(sid):
    sess = get_report_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
        "status": sess["status"],
        "router_count": sess["router_count"],
        "completed_count": sess["completed_count"],
        "service_count": len(sess["report_data"]),
        "noconf_count": len(sess["noconf_data"]),
        "error": sess["error"],
    })


@app.route("/report-analytics/<sid>")
@login_required
def report_analytics(sid):
    sess = get_report_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    analytics = sess.get("analytics")
    if analytics is None:
        return jsonify({"error": "Analytics not yet available"}), 425
    return jsonify(analytics)


# ---------------------------------------------------------------------------
# License Check Routes
# ---------------------------------------------------------------------------
@app.route("/run-license-check", methods=["POST"])
@permission_required("license_check")
def run_license_check():
    data = request.get_json(force=True)
    routers_raw = data.get("routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = []
    for r in routers_raw:
        name = (r.get("name") or "").strip()
        ip = (r.get("ip") or "").strip()
        if name and ip:
            routers.append({"name": name, "ip": ip})

    if not routers:
        return jsonify({"error": "At least one valid router entry is required"}), 400

    sid = create_license_session()
    t = threading.Thread(
        target=_run_license_check, args=(sid, routers, username, password), daemon=True
    )
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@app.route("/stream-license/<sid>")
@login_required
def stream_license(sid):
    sess = get_license_session(sid)
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
                yield (
                    f"event: done\ndata: "
                    f"{json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                )
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/license-session/<sid>")
@login_required
def license_session_status(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
        "status": sess["status"],
        "router_count": sess["router_count"],
        "completed_count": sess["completed_count"],
        "licenses_count": len(sess["license_data"]),
        "failed_count": sum(1 for d in sess["license_data"] if d["status"] != "success"),
        "error": sess["error"],
    })


GRACE_DAYS = 60
WARNING_AFTER_DAYS = 45


def _parse_date(date_str: str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S%z']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def compute_grace_status(expiry_str: str):
    if not expiry_str or expiry_str.upper() in ('PERMANENT', 'UNKNOWN', ''):
        return '', '', '', 'Permanent'
    dt = _parse_date(expiry_str)
    if dt is None:
        return '', '', '', 'Unknown'

    now = datetime.now()
    grace_end = dt + timedelta(days=GRACE_DAYS)

    if now < dt:
        days = (dt - now).days
        return expiry_str, grace_end.strftime('%Y-%m-%d'), str(days), 'Active'

    days_since_expiry = (now - dt).days
    if days_since_expiry >= GRACE_DAYS:
        return expiry_str, grace_end.strftime('%Y-%m-%d'), '0', 'Expired'

    days_remaining = (grace_end - now).days
    if days_since_expiry >= WARNING_AFTER_DAYS:
        return expiry_str, grace_end.strftime('%Y-%m-%d'), str(days_remaining), 'Warning'
    else:
        return expiry_str, grace_end.strftime('%Y-%m-%d'), str(days_remaining), 'Grace'


@app.route("/download-license-summary/<sid>")
@login_required
def download_license_summary(sid):
    sess = get_license_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["license_data"]:
        return "No license data available", 404

    fieldnames = [
        "Router Name", "IP", "Product Name", "Product Version",
        "License State", "License Mode", "Overall Expiry",
        "Grace End", "Days Remaining", "Grace Status",
        "Active License File", "Error",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in sess["license_data"]:
        li = row.get("license_info", {})
        features = li.get("features", [])
        overall_expiry = features[0].get("expired_date", "") if features else ""
        exp_str, grace_end, days_rem, grace_status = compute_grace_status(overall_expiry)
        if li.get("license_mode", "").upper() == 'PERMANENT':
            exp_str = 'Permanent'
            grace_end = 'N/A'
            days_rem = 'N/A'
            grace_status = 'Permanent'
        writer.writerow({
            "Router Name": row["name"],
            "IP": row["host"],
            "Product Name": li.get("product_name", ""),
            "Product Version": li.get("product_version", ""),
            "License State": li.get("license_state", ""),
            "License Mode": li.get("license_mode", ""),
            "Overall Expiry": exp_str,
            "Grace End": grace_end,
            "Days Remaining": days_rem,
            "Grace Status": grace_status,
            "Active License File": li.get("active_license", ""),
            "Error": row.get("error", ""),
        })
    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"license_summary_{sid}.csv",
    )


@app.route("/license-report/<sid>")
@login_required
def license_report(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    if not sess["license_data"]:
        return jsonify({"error": "No license data"}), 404

    routers = []
    status_counts = {'Active': 0, 'Grace': 0, 'Warning': 0, 'Expired': 0, 'Permanent': 0, 'Failed': 0, 'Unknown': 0}

    for row in sess["license_data"]:
        lv = row.get("license_verbose_info", {})
        li = row.get("license_info", {})
        features = li.get("features", [])

        if row['status'] != 'success':
            overall_status = 'Failed'
            exp_str = row.get("error", "")
            grace_end = ''
            overall_days = ''
        else:
            overall_expiry = features[0].get("expired_date", "") if features else ""
            exp_str, grace_end, overall_days, overall_status = compute_grace_status(overall_expiry)

        items = []
        for feat in lv.get("features", []):
            for item in feat.get("items", []):
                item_exp = item.get("item_expired_date", "")
                ie_str, ie_grace, ie_days, ie_status = compute_grace_status(item_exp)
                items.append({
                    'item_name': item.get("item_name", ""),
                    'item_type': item.get("item_type", ""),
                    'sale_name': item.get("sale_name", ""),
                    'control_value': item.get("control_value", ""),
                    'used_value': item.get("used_value", ""),
                    'item_state': item.get("item_state", ""),
                    'expiry': ie_str,
                    'grace_end': ie_grace,
                    'days_remaining': ie_days,
                    'grace_status': ie_status,
                    'description': item.get("description", ""),
                })

        if overall_status in status_counts:
            status_counts[overall_status] += 1

        routers.append({
            'name': row["name"],
            'ip': row["host"],
            'status': row["status"],
            'error': row.get("error", ""),
            'product_name': li.get("product_name", ""),
            'product_version': li.get("product_version", ""),
            'license_state': li.get("license_state", ""),
            'license_mode': li.get("license_mode", ""),
            'overall_expiry': exp_str,
            'overall_grace_end': grace_end,
            'overall_days_remaining': overall_days,
            'overall_grace_status': overall_status,
            'items': items,
            'total_items': len(items),
            'warning_items': sum(1 for i in items if i['grace_status'] in ('Warning', 'Expired')),
        })

    total_warnings = sum(s.get('Warning', 0) + s.get('Expired', 0) for s in [status_counts])
    item_warnings = sum(r['warning_items'] for r in routers)

    return jsonify({
        'routers': routers,
        'summary': {
            'total_routers': len(routers),
            'total_failed': sum(1 for r in routers if r['status'] != 'success'),
            'status_distribution': status_counts,
            'total_items': sum(r['total_items'] for r in routers),
            'total_item_warnings': item_warnings,
            'total_warnings': total_warnings,
        }
    })


@app.route("/license-warnings/<sid>")
@login_required
def license_warnings(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    if not sess["license_data"]:
        return jsonify({"error": "No license data"}), 404

    warnings = []
    for row in sess["license_data"]:
        lv = row.get("license_verbose_info", {})
        li = row.get("license_info", {})
        router_name = row["name"]
        router_ip = row["host"]

        features = li.get("features", [])
        overall_expiry = features[0].get("expired_date", "") if features else ""
        _, _, days_rem, grace_status = compute_grace_status(overall_expiry)
        if grace_status == 'Warning':
            warnings.append({
                'type': 'License',
                'router': router_name, 'ip': router_ip,
                'item': 'Overall License',
                'expiry': overall_expiry,
                'days_remaining': days_rem,
                'grace_status': grace_status,
            })

        for feat in lv.get("features", []):
            for item in feat.get("items", []):
                item_exp = item.get("item_expired_date", "")
                _, _, ie_days, ie_status = compute_grace_status(item_exp)
                if ie_status in ('Warning', 'Expired'):
                    warnings.append({
                        'type': 'Item',
                        'router': router_name, 'ip': router_ip,
                        'item': item.get("item_name", "") or item.get("sale_name", ""),
                        'item_type': item.get("item_type", ""),
                        'expiry': item_exp,
                        'days_remaining': ie_days,
                        'grace_status': ie_status,
                    })

    return jsonify({
        'warnings': warnings,
        'total_warnings': len(warnings),
    })


@app.route("/cancel-license-session/<sid>", methods=["POST"])
@login_required
def cancel_license_session(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    sess["cancel_flag"] = True
    return jsonify({"status": "cancelling"})


@app.route("/download-license-items/<sid>")
@login_required
def download_license_items(sid):
    sess = get_license_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["license_data"]:
        return "No license data available", 404

    fieldnames = [
        "Router Name", "IP",
        "Item Name", "Item Type", "Item State",
        "Control Value", "Used Value",
        "Item Expired Date", "Item Grace End", "Item Days Remaining", "Item Grace Status",
        "Sale Name", "Feature Name", "Feature Expiry",
        "Item Trial Days", "Description",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in sess["license_data"]:
        lv = row.get("license_verbose_info", {})
        for feat in lv.get("features", []):
            for item in feat.get("items", []):
                item_exp = item.get("item_expired_date", "")
                ie_str, ie_grace, ie_days, ie_status = compute_grace_status(item_exp)
                writer.writerow({
                    "Router Name": row["name"],
                    "IP": row["host"],
                    "Item Name": item.get("item_name", ""),
                    "Item Type": item.get("item_type", ""),
                    "Item State": item.get("item_state", ""),
                    "Control Value": item.get("control_value", ""),
                    "Used Value": item.get("used_value", ""),
                    "Item Expired Date": ie_str,
                    "Item Grace End": ie_grace,
                    "Item Days Remaining": ie_days,
                    "Item Grace Status": ie_status,
                    "Sale Name": item.get("sale_name", ""),
                    "Feature Name": feat.get("feature_name", ""),
                    "Feature Expiry": feat.get("expired_date", ""),
                    "Item Trial Days": item.get("item_trial_days", ""),
                    "Description": item.get("description", ""),
                })
    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"license_items_{sid}.csv",
    )


@app.route("/match-licenses", methods=["POST"])
@permission_required("license_check")
def match_licenses():
    if "csv_file" not in request.files:
        return jsonify({"error": "Router CSV file is required"}), 400
    
    csv_file = request.files["csv_file"]
    routers, err = parse_csv_to_routers(csv_file)
    if err or not routers:
        return jsonify({"error": err or "Invalid CSV file"}), 400

    uploaded_files = request.files.getlist("license_files")
    if not uploaded_files:
        return jsonify({"error": "No license files uploaded"}), 400

    saved_paths = []
    session_dir = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
    
    for f in uploaded_files:
        if f.filename:
            filename = secure_filename(f.filename)
            filepath = os.path.join(session_dir, filename)
            f.save(filepath)
            saved_paths.append(filepath)

    if not saved_paths:
        return jsonify({"error": "No valid license files saved"}), 400

    def _dummy_log(msg, level="info"):
        pass

    processor = LicenseRenewalProcessor(
        routers_data=routers,
        license_files_paths=saved_paths,
        network_creds={},
        log_callback=_dummy_log
    )
    matched, unmatched = processor.run_matching()

    return jsonify({
        "matched": matched,
        "unmatched": unmatched,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched)
    })


@app.route("/start-renewal", methods=["POST"])
@permission_required("license_check")
def start_renewal():
    data = request.get_json(force=True)
    selected_routers = data.get("selected_routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not selected_routers:
        return jsonify({"error": "No routers selected for renewal"}), 400

    sid = create_lic_renewal_session()

    def _worker():
        sess = get_lic_renewal_session(sid)
        if sess is None:
            return
        sess["status"] = "running"
        sess["router_count"] = len(selected_routers)

        def _log(msg, level="info"):
            push_lic_renewal_log(sid, msg, level)

        def _confirm(router_name, issues):
            sess = get_lic_renewal_session(sid)
            if not sess:
                return False
            evt = threading.Event()
            cid = uuid.uuid4().hex[:8]
            sess["pending_confirmations"][cid] = {
                "router_name": router_name,
                "issues": issues,
            }
            sess["confirmation_events"][cid] = evt
            
            # Notify frontend via log queue event
            push_lic_renewal_log(sid, f"NEED_CONFIRMATION:{cid}:{router_name}:{json.dumps(issues)}", "warn")
            
            # Wait for user response (timeout 5 minutes)
            got_resp = evt.wait(timeout=300)
            result = sess["confirmation_results"].get(cid, False)
            
            # Clean up
            sess["pending_confirmations"].pop(cid, None)
            sess["confirmation_events"].pop(cid, None)
            sess["confirmation_results"].pop(cid, None)
            
            return got_resp and result

        processor = LicenseRenewalProcessor(
            routers_data=[],
            license_files_paths=[],
            network_creds={"username": username, "password": password},
            log_callback=_log,
            confirm_callback=_confirm
        )
        reports, csv_file = processor.run_renewal(selected_routers)
        sess["report_data"] = reports
        if csv_file:
            sess["csv_file"] = csv_file
        finish_lic_renewal_session(sid)

        add_renewal_report(sid, reports, datetime.now().isoformat(), csv_file=csv_file)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return jsonify({"session_id": sid, "router_count": len(selected_routers)})


@app.route("/download-renewal-report/<path:sid>")
@login_required
def download_renewal_report(sid):
    safe_filename = os.path.basename(sid)
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")

    # 1. Direct file check in reports directory
    file_path = os.path.join(reports_dir, safe_filename)
    if os.path.isfile(file_path):
        return send_file(
            file_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name=safe_filename
        )

    # 2. Check if DB record defines associated csv_file
    report = get_renewal_report(sid)
    if report and report.get("csv_file"):
        db_csv_path = os.path.join(reports_dir, report["csv_file"])
        if os.path.isfile(db_csv_path):
            return send_file(
                db_csv_path,
                mimetype="text/csv",
                as_attachment=True,
                download_name=report["csv_file"]
            )

    # 3. Fallback lookup in reports directory for matching ID in filename
    if os.path.isdir(reports_dir):
        for fname in os.listdir(reports_dir):
            if sid in fname or fname.endswith(f"{sid}.csv"):
                fp = os.path.join(reports_dir, fname)
                if os.path.isfile(fp):
                    return send_file(
                        fp,
                        mimetype="text/csv",
                        as_attachment=True,
                        download_name=fname
                    )

    # 4. Dynamic CSV generation from JSON DB report_data or session
    rows = []
    if report:
        rows = report.get('report_data', [])
    else:
        sess = get_lic_renewal_session(sid)
        if sess and sess.get("report_data"):
            rows = sess["report_data"]
    
    if not rows:
        return "Report not found or empty", 404
    
    out = io.StringIO()
    fieldnames = ['router_name', 'ip', 'esn', 'license_file', 'current_expiry', 'new_expiry', 'status', 'details']
    if rows and isinstance(rows[0], dict):
        for k in rows[0].keys():
            if k not in fieldnames:
                fieldnames.append(k)
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)

    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    safe_name = re.sub(r'[^\w\-]', '_', sid)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"license_renewal_report_{safe_name}.csv",
    )





@app.route("/confirm-renewal/<sid>", methods=["POST"])
@login_required
def confirm_renewal(sid):
    data = request.get_json(force=True)
    cid = data.get("confirmation_id")
    action = data.get("action")  # 'proceed' or 'skip'

    sess = get_lic_renewal_session(sid)
    if not sess:
        return jsonify({"error": "Session not found"}), 404

    if cid not in sess.get("confirmation_events", {}):
        return jsonify({"error": "Confirmation request not found or expired"}), 404

    sess["confirmation_results"][cid] = (action == "proceed")
    evt = sess["confirmation_events"][cid]
    evt.set()

    return jsonify({"status": "received", "action": action})
@app.route("/stream-lic-renewal/<sid>")
@login_required
def stream_lic_renewal(sid):
    sess = get_lic_renewal_session(sid)
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
                yield (
                    f"event: done\ndata: "
                    f"{json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                )
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# VRF Routing Check Routes
# ---------------------------------------------------------------------------
@app.route("/vrf-router-info")
@login_required
def vrf_router_info():
    return jsonify({"name": HARDCODED_ROUTER_NAME, "ip": HARDCODED_ROUTER_IP})
@app.route("/parse-interface-config", methods=["POST"])
@permission_required("vrf_routing")
def parse_interface_config_route():
    data = request.get_json(force=True)
    config_text = data.get("config", "")
    if not config_text.strip():
        return jsonify({"error": "No interface configuration provided"}), 400
    parsed = parse_interface_config(config_text)
    return jsonify(parsed)


@app.route("/check-vrf-routing", methods=["POST"])
@permission_required("vrf_routing")
def check_vrf_routing_route():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    config_text = data.get("config", "")
    
    # 1. Extract target_ip from the frontend request
    target_ip = (data.get("target_ip") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not config_text.strip():
        return jsonify({"error": "No interface configuration provided"}), 400

    conn_to = data.get("conn_timeout", 20)
    cmd_to = data.get("cmd_timeout", 60)

    # 2. Pass target_ip explicitly as a keyword argument
    result = batch_check_routing(
        username=username,
        password=password,
        config_text=config_text,
        target_ip=target_ip,  # <--- THIS IS THE CRITICAL FIX
        conn_timeout=conn_to,
        cmd_timeout=cmd_to
    )
    return jsonify(result)

@app.route("/check-bgp-route", methods=["POST"])
@permission_required("vrf_routing")
def check_bgp_route_route():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    target_ip = (data.get("target_ip") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not target_ip:
        return jsonify({"error": "Target IP address is required"}), 400

    try:
        conn = netmiko.ConnectHandler(
            device_type='huawei',
            host=HARDCODED_ROUTER_IP,
            username=username,
            password=password,
            timeout=20,
        )
    except Exception as e:
        return jsonify({'error': f'Failed to connect to {HARDCODED_ROUTER_NAME} ({HARDCODED_ROUTER_IP}): {e}'}), 502

    try:
        entries, raw_output = check_bgp_route(conn, target_ip, cmd_timeout=90)
        conn.disconnect()
    except Exception as e:
        try:
            conn.disconnect()
        except Exception:
            pass
        return jsonify({'error': f'BGP query failed: {e}'}), 502

    return jsonify({
        'status': 'success',
        'router': {'name': HARDCODED_ROUTER_NAME, 'ip': HARDCODED_ROUTER_IP},
        'target_ip': target_ip,
        'entries': entries,
        'entry_count': len(entries),
    })


@app.route("/show-originator-interfaces", methods=["POST"])
@permission_required("vrf_routing")
def show_originator_interfaces_route():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    originator_ip = (data.get("originator_ip") or "").strip()
    target_ip = (data.get("target_ip") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not originator_ip:
        return jsonify({"error": "Originator IP is required"}), 400
    if not target_ip:
        return jsonify({"error": "Target IP is required"}), 400
    target_ip = target_ip.split('/')[0]
    vrf = (data.get("vrf") or "").strip()

    if not vrf:
        return jsonify({"error": "VRF name is required"}), 400

    connect_ip = transform_originator_ip(originator_ip)

    try:
        conn = netmiko.ConnectHandler(
            device_type='huawei',
            host=connect_ip,
            username=username,
            password=password,
            timeout=20,
        )
    except Exception as e:
        return jsonify({'error': f'Failed to connect to {originator_ip}: {e}'}), 502

    try:
        sysname = get_sysname(conn, cmd_timeout=10)
        result = query_vrf_route_and_configs(conn, vrf, target_ip, cmd_timeout=60)
        conn.disconnect()
    except Exception as e:
        try:
            conn.disconnect()
        except Exception:
            pass
        return jsonify({'error': f'Query failed: {e}'}), 502

    return jsonify({
        'status': 'success',
        'originator_ip': originator_ip,
        'connect_ip': connect_ip if connect_ip != originator_ip else None,
        'target_ip': target_ip,
        'sysname': sysname,
        'result': result,
    })


# ---------------------------------------------------------------------------
# Zabbix Router Database (local JSON, weekly refresh)
# ---------------------------------------------------------------------------
_ZABBIX_INI = os.path.join(os.path.dirname(__file__), "zabbix_config.ini")
_ZABBIX_DB = os.path.join(os.path.dirname(__file__), "zabbix_router_db.json")
_zabbix_service_lock = threading.Lock()
_zabbix_service_instance = None
_zabbix_refresh_lock = threading.Lock()


def _get_zabbix_service():
    global _zabbix_service_instance
    if _zabbix_service_instance is None:
        with _zabbix_service_lock:
            if _zabbix_service_instance is None:
                _zabbix_service_instance = create_zabbix_service(
                    ini_path=_ZABBIX_INI if os.path.isfile(_ZABBIX_INI) else None,
                    **({"url": os.environ["ZABBIX_URL"]} if os.environ.get("ZABBIX_URL") else {}),
                )
    return _zabbix_service_instance


@app.route("/admin/zabbix-groups", methods=["GET"])
@permission_required("zabbix_db_refresh")
def admin_get_zabbix_groups():
    try:
        svc = _get_zabbix_service()
        groups = svc.get_groups()
        return jsonify({"groups": [{"name": g.name, "id": g.groupid} for g in groups]})
    except Exception as e:
        app.logger.exception("Failed to get Zabbix groups")
        return jsonify({"error": f"Failed to get Zabbix groups: {e}"}), 500


@app.route("/admin/refresh-zabbix-db", methods=["POST"])
@permission_required("zabbix_db_refresh")
def admin_refresh_zabbix_db():
    data = request.get_json(silent=True) or {}
    group_names = data.get('groups')
    replace = data.get('replace', False)
    if not group_names or not isinstance(group_names, list):
        return jsonify({"error": "No Zabbix groups specified for refresh"}), 400

    if not _zabbix_refresh_lock.acquire(blocking=False):
        return jsonify({"error": "Refresh already in progress"}), 429

    def _run_refresh_task(groups_to_refresh, do_replace):
        try:
            if do_replace and os.path.isfile(_ZABBIX_DB):
                os.remove(_ZABBIX_DB)
                app.logger.info("Deleted existing DB for full rebuild")
            svc = _get_zabbix_service()
            for group_name in groups_to_refresh:
                app.logger.info("Refreshing Zabbix DB for group: %s", group_name)
                svc.refresh_router_db(group_name=group_name, db_path=_ZABBIX_DB)
            app.logger.info("Zabbix DB refresh completed for all selected groups.")
        except Exception:
            app.logger.exception("Zabbix DB refresh failed")
        finally:
            _zabbix_refresh_lock.release()

    t = threading.Thread(target=_run_refresh_task, args=(group_names, replace), daemon=True)
    t.start()
    action = "Rebuild" if replace else "Refresh"
    return jsonify({"status": "started", "message": f"{action} started for groups: {', '.join(group_names)}"}), 202


@app.route("/admin/renewal-reports", methods=["GET"])
@permission_required("license_renewal_admin")
def admin_get_renewal_reports():
    reports = get_all_renewal_reports()
    return jsonify(reports)


@app.route("/admin/license-archive-files", methods=["GET"])
@permission_required("license_renewal_admin")
def admin_get_license_archive_files():
    archive_dir = os.path.join(os.path.dirname(__file__), "license_archive")
    if not os.path.isdir(archive_dir):
        return jsonify([])
    files = []
    for f in os.listdir(archive_dir):
        fp = os.path.join(archive_dir, f)
        if os.path.isfile(fp):
            stat = os.stat(fp)
            files.append({
                "filename": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    return jsonify(files)


@app.route("/download-archived-license/<filename>", methods=["GET"])
@login_required
def download_archived_license(filename):
    safe_filename = os.path.basename(filename)
    archive_dir = os.path.join(os.path.dirname(__file__), "license_archive")
    file_path = os.path.join(archive_dir, safe_filename)
    if not os.path.isfile(file_path):
        # Fallback to checking root or uploaded location if exact match exists by base name
        if os.path.isfile(safe_filename):
            file_path = safe_filename
        else:
            return "License file not found", 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_filename
    )


@app.route("/admin/delete-zabbix-db", methods=["POST"])
@permission_required("zabbix_db_refresh")
def admin_delete_zabbix_db():
    if os.path.isfile(_ZABBIX_DB):
        os.remove(_ZABBIX_DB)
        return jsonify({"status": "deleted"})
    return jsonify({"status": "not_found"})


@app.route("/refresh-zabbix-progress", methods=["GET"])
@login_required
def refresh_zabbix_progress():
    running = _zabbix_refresh_lock.locked()
    if not os.path.isfile(_ZABBIX_DB):
        return jsonify({"running": running, "exists": False})
    try:
        with open(_ZABBIX_DB, "r", encoding="utf-8") as f:
            db = json.load(f)
        progress = db.get("_progress")
        if progress:
            return jsonify({"running": True, "progress": progress})
        return jsonify({
            "running": False,
            "exists": True,
            "summary": db.get("summary"),
            "refreshed_at_iso": db.get("refreshed_at_iso"),
        })
    except Exception:
        return jsonify({"running": running, "exists": False})


@app.route("/search-zabbix-interfaces", methods=["POST"])
@permission_required("zabbix_search")
def search_zabbix_interfaces():
    data = request.get_json(force=True)
    keyword = (data.get("keyword") or "").strip()

    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400

    if not os.path.isfile(_ZABBIX_DB):
        return jsonify({
            "keyword": keyword,
            "count": 0,
            "results": [],
            "db_missing": True,
            "message": "Router database not found. An admin must refresh it first.",
        })

    try:
        results = ZabbixService.search_router_db(
            keyword=keyword,
            db_path=_ZABBIX_DB,
            search_host=True,
            search_interface=True,
            case_sensitive=False,
            partial=True,
        )
        return jsonify({
            "keyword": keyword,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        app.logger.exception("Zabbix search failed")
        return jsonify({"error": f"Search failed: {e}"}), 500


@app.route("/search-zabbix-ip", methods=["POST"])
@permission_required("zabbix_search")
def search_zabbix_ip():
    data = request.get_json(force=True)
    ip = (data.get("ip") or "").strip()

    if not ip:
        return jsonify({"error": "IP address is required"}), 400

    if not os.path.isfile(_ZABBIX_DB):
        return jsonify({
            "ip": ip,
            "count": 0,
            "results": [],
            "db_missing": True,
            "message": "Router database not found. An admin must refresh it first.",
        })

    try:
        results = ZabbixService.search_router_db(
            keyword=ip,
            db_path=_ZABBIX_DB,
            search_host=False,
            search_interface=False,
            search_ip=True,
            case_sensitive=False,
            partial=True,
        )
        return jsonify({
            "ip": ip,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        app.logger.exception("Zabbix search failed")
        return jsonify({"error": f"Search failed: {e}"}), 500


@app.route("/search-site-arp-mac", methods=["POST"])
@permission_required("zabbix_search")
def search_site_arp_mac():
    data = request.get_json(force=True)
    site_code = (data.get("site_code") or data.get("keyword") or "").strip()

    if not site_code:
        return jsonify({"error": "Site code is required", "success": False}), 400

    try:
        result = lookup_site_arp_mac_details(site_code)
        return jsonify(result)
    except Exception as e:
        app.logger.exception("Site ARP/MAC lookup failed")
        return jsonify({"error": f"Lookup failed: {e}", "success": False}), 500


@app.route("/admin/parse-ne-csv", methods=["POST"])
@login_required
def admin_parse_ne_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    content = f.read()
    matched, skipped, total = parse_ne_csv_content(content)
    return jsonify({
        "matched": matched,
        "matched_count": len(matched),
        "skipped_count": len(skipped),
        "total_count": total,
        "prefixes": TARGET_NE_PREFIXES,
    })


@app.route("/admin/run-arp-mac-collector", methods=["POST"])
@login_required
def admin_run_arp_mac_collector():
    username = ""
    password = ""
    threads = 10
    routers = []

    if request.content_type and "multipart/form-data" in request.content_type:
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        try:
            threads = int(request.form.get("threads", 10))
        except Exception:
            threads = 10

        if "file" in request.files and request.files["file"].filename:
            content = request.files["file"].read()
            matched, _, _ = parse_ne_csv_content(content)
            routers = matched
    else:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        try:
            threads = int(data.get("threads", 10))
        except Exception:
            threads = 10
        routers = data.get("routers", [])

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if not routers:
        return jsonify({"error": f"No target routers found starting with {', '.join(TARGET_NE_PREFIXES)}"}), 400

    started = start_collector_job(routers, username, password, max_workers=threads)
    if not started:
        return jsonify({"error": "Collector job is already running"}), 409

    return jsonify({
        "status": "started",
        "message": f"Collector started for {len(routers)} routers",
        "router_count": len(routers),
    })


@app.route("/admin/arp-mac-collector-status", methods=["GET"])
@login_required
def admin_arp_mac_collector_status():
    status = get_collector_job_status()
    return jsonify(status)


@app.route("/admin/arp-mac-collector-stop", methods=["POST"])
@login_required
def admin_arp_mac_collector_stop():
    stop_collector_job()
    return jsonify({"status": "stopping"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
