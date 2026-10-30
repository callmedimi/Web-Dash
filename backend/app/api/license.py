"""License Check, Matching, Renewal, and Archive Blueprint."""
import csv
import io
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

from werkzeug.utils import secure_filename
from flask import (
    Blueprint,
    request,
    jsonify,
    Response,
    stream_with_context,
    send_file,
    session,
    current_app,
)

from license_check import check_license_on_router
from license_renewal_logic import LicenseRenewalProcessor
from services.license_db import add_renewal_report, get_all_renewal_reports, get_renewal_report
from auth import login_required, permission_required
from audit import record_audit
from validators import validate_routers_list
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    read_only_blocked,
    parse_csv_to_routers,
)

license_bp = Blueprint("license_api", __name__)

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
                check_license_on_router,
                r["name"],
                r["ip"],
                username,
                password,
                _log,
                conn_timeout=30,
                cmd_timeout=90,
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


GRACE_DAYS = 60
WARNING_AFTER_DAYS = 45


def _parse_date(date_str: str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def compute_grace_status(expiry_str: str):
    if not expiry_str or expiry_str.upper() in ("PERMANENT", "UNKNOWN", ""):
        return "", "", "", "Permanent"
    dt = _parse_date(expiry_str)
    if dt is None:
        return "", "", "", "Unknown"

    now = datetime.now()
    grace_end = dt + timedelta(days=GRACE_DAYS)

    if now < dt:
        days = (dt - now).days
        return expiry_str, grace_end.strftime("%Y-%m-%d"), str(days), "Active"

    days_since_expiry = (now - dt).days
    if days_since_expiry >= GRACE_DAYS:
        return expiry_str, grace_end.strftime("%Y-%m-%d"), "0", "Expired"

    days_remaining = (grace_end - now).days
    if days_since_expiry >= WARNING_AFTER_DAYS:
        return expiry_str, grace_end.strftime("%Y-%m-%d"), str(days_remaining), "Warning"
    else:
        return expiry_str, grace_end.strftime("%Y-%m-%d"), str(days_remaining), "Grace"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@license_bp.route("/run-license-check", methods=["POST"])
@permission_required("license_check")
def run_license_check():
    data = get_json_payload()
    routers_raw = data.get("routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = validate_routers_list(routers_raw, max_items=2000)

    sid = create_license_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "license_check", "router_count": len(routers)},
    )
    t = threading.Thread(
        target=_run_license_check, args=(sid, routers, username, password), daemon=True
    )
    t.start()
    return jsonify({"session_id": sid, "router_count": len(routers)})


@license_bp.route("/stream-license/<sid>")
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
                yield f"event: done\ndata: {json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@license_bp.route("/license-session/<sid>")
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


@license_bp.route("/download-license-summary/<sid>")
@login_required
def download_license_summary(sid):
    sess = get_license_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["license_data"]:
        return "No license data available", 404

    fieldnames = [
        "Router Name",
        "IP",
        "Product Name",
        "Product Version",
        "License State",
        "License Mode",
        "Overall Expiry",
        "Grace End",
        "Days Remaining",
        "Grace Status",
        "Active License File",
        "Error",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in sess["license_data"]:
        li = row.get("license_info", {})
        features = li.get("features", [])
        overall_expiry = features[0].get("expired_date", "") if features else ""
        exp_str, grace_end, days_rem, grace_status = compute_grace_status(overall_expiry)
        if li.get("license_mode", "").upper() == "PERMANENT":
            exp_str = "Permanent"
            grace_end = "N/A"
            days_rem = "N/A"
            grace_status = "Permanent"
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


@license_bp.route("/license-report/<sid>")
@login_required
def license_report(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    if not sess["license_data"]:
        return jsonify({"error": "No license data"}), 404

    routers = []
    status_counts = {
        "Active": 0,
        "Grace": 0,
        "Warning": 0,
        "Expired": 0,
        "Permanent": 0,
        "Failed": 0,
        "Unknown": 0,
    }

    for row in sess["license_data"]:
        lv = row.get("license_verbose_info", {})
        li = row.get("license_info", {})
        features = li.get("features", [])

        if row["status"] != "success":
            overall_status = "Failed"
            exp_str = row.get("error", "")
            grace_end = ""
            overall_days = ""
        else:
            overall_expiry = features[0].get("expired_date", "") if features else ""
            exp_str, grace_end, overall_days, overall_status = compute_grace_status(overall_expiry)

        items = []
        for feat in lv.get("features", []):
            for item in feat.get("items", []):
                item_exp = item.get("item_expired_date", "")
                ie_str, ie_grace, ie_days, ie_status = compute_grace_status(item_exp)
                items.append({
                    "item_name": item.get("item_name", ""),
                    "item_type": item.get("item_type", ""),
                    "sale_name": item.get("sale_name", ""),
                    "control_value": item.get("control_value", ""),
                    "used_value": item.get("used_value", ""),
                    "item_state": item.get("item_state", ""),
                    "expiry": ie_str,
                    "grace_end": ie_grace,
                    "days_remaining": ie_days,
                    "grace_status": ie_status,
                    "description": item.get("description", ""),
                })

        if overall_status in status_counts:
            status_counts[overall_status] += 1

        routers.append({
            "name": row["name"],
            "ip": row["host"],
            "status": row["status"],
            "error": row.get("error", ""),
            "product_name": li.get("product_name", ""),
            "product_version": li.get("product_version", ""),
            "license_state": li.get("license_state", ""),
            "license_mode": li.get("license_mode", ""),
            "overall_expiry": exp_str,
            "overall_grace_end": grace_end,
            "overall_days_remaining": overall_days,
            "overall_grace_status": overall_status,
            "items": items,
            "total_items": len(items),
            "warning_items": sum(1 for i in items if i["grace_status"] in ("Warning", "Expired")),
        })

    total_warnings = sum(s.get("Warning", 0) + s.get("Expired", 0) for s in [status_counts])
    item_warnings = sum(r["warning_items"] for r in routers)

    return jsonify({
        "routers": routers,
        "summary": {
            "total_routers": len(routers),
            "total_failed": sum(1 for r in routers if r["status"] != "success"),
            "status_distribution": status_counts,
            "total_items": sum(r["total_items"] for r in routers),
            "total_item_warnings": item_warnings,
            "total_warnings": total_warnings,
        },
    })


@license_bp.route("/license-warnings/<sid>")
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
        if grace_status == "Warning":
            warnings.append({
                "type": "License",
                "router": router_name,
                "ip": router_ip,
                "item": "Overall License",
                "expiry": overall_expiry,
                "days_remaining": days_rem,
                "grace_status": grace_status,
            })

        for feat in lv.get("features", []):
            for item in feat.get("items", []):
                item_exp = item.get("item_expired_date", "")
                _, _, ie_days, ie_status = compute_grace_status(item_exp)
                if ie_status in ("Warning", "Expired"):
                    warnings.append({
                        "type": "Item",
                        "router": router_name,
                        "ip": router_ip,
                        "item": item.get("item_name", "") or item.get("sale_name", ""),
                        "item_type": item.get("item_type", ""),
                        "expiry": item_exp,
                        "days_remaining": ie_days,
                        "grace_status": ie_status,
                    })

    return jsonify({
        "warnings": warnings,
        "total_warnings": len(warnings),
    })


@license_bp.route("/cancel-license-session/<sid>", methods=["POST"])
@login_required
def cancel_license_session(sid):
    sess = get_license_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    sess["cancel_flag"] = True
    return jsonify({"status": "cancelling"})


@license_bp.route("/download-license-items/<sid>")
@login_required
def download_license_items(sid):
    sess = get_license_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["license_data"]:
        return "No license data available", 404

    fieldnames = [
        "Router Name",
        "IP",
        "Item Name",
        "Item Type",
        "Item State",
        "Control Value",
        "Used Value",
        "Item Expired Date",
        "Item Grace End",
        "Item Days Remaining",
        "Item Grace Status",
        "Sale Name",
        "Feature Name",
        "Feature Expiry",
        "Item Trial Days",
        "Description",
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


@license_bp.route("/match-licenses", methods=["POST"])
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

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "./data/uploads")
    os.makedirs(upload_folder, exist_ok=True)
    saved_paths = []
    session_dir = tempfile.mkdtemp(dir=upload_folder)

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
        log_callback=_dummy_log,
    )
    matched, unmatched = processor.run_matching()

    return jsonify({
        "matched": matched,
        "unmatched": unmatched,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
    })


@license_bp.route("/start-renewal", methods=["POST"])
@permission_required("license_check")
@read_only_blocked
def start_renewal():
    data = get_json_payload()
    selected_routers_raw = data.get("selected_routers", [])
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    selected_routers = validate_routers_list(selected_routers_raw, max_items=2000)

    sid = create_lic_renewal_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "license_renewal", "router_count": len(selected_routers)},
    )

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
            push_lic_renewal_log(
                sid, f"NEED_CONFIRMATION:{cid}:{router_name}:{json.dumps(issues)}", "warn"
            )

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
            confirm_callback=_confirm,
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


@license_bp.route("/download-renewal-report/<path:sid>")
@login_required
def download_renewal_report(sid):
    safe_filename = os.path.basename(sid)
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "reports"))

    # 1. Direct file check in reports directory
    file_path = os.path.join(reports_dir, safe_filename)
    if os.path.isfile(file_path):
        return send_file(
            file_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name=safe_filename,
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
                download_name=report["csv_file"],
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
                        download_name=fname,
                    )

    # 4. Dynamic CSV generation from JSON DB report_data or session
    rows = []
    if report:
        rows = report.get("report_data", [])
    else:
        sess = get_lic_renewal_session(sid)
        if sess and sess.get("report_data"):
            rows = sess["report_data"]

    if not rows:
        return "Report not found or empty", 404

    out = io.StringIO()
    fieldnames = [
        "router_name",
        "ip",
        "esn",
        "license_file",
        "current_expiry",
        "new_expiry",
        "status",
        "details",
    ]
    if rows and isinstance(rows[0], dict):
        for k in rows[0].keys():
            if k not in fieldnames:
                fieldnames.append(k)
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    safe_name = re.sub(r"[^\w\-]", "_", sid)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"license_renewal_report_{safe_name}.csv",
    )


@license_bp.route("/confirm-renewal/<sid>", methods=["POST"])
@login_required
@read_only_blocked
def confirm_renewal(sid):
    data = get_json_payload()
    cid = data.get("confirmation_id")
    action = data.get("action")  # 'proceed' or 'skip'

    sess = get_lic_renewal_session(sid)
    if not sess:
        return jsonify({"error": "Session not found"}), 404

    if cid not in sess.get("confirmation_events", {}):
        return jsonify({"error": "Confirmation request not found or expired"}), 404

    sess["confirmation_results"][cid] = action == "proceed"
    evt = sess["confirmation_events"][cid]
    evt.set()

    user = session.get("username") or "unknown"
    record_audit(
        "renewal_confirmed",
        user,
        get_client_ip(),
        status="success",
        detail={"action": action, "session_id": sid},
    )
    return jsonify({"status": "received", "action": action})


@license_bp.route("/stream-lic-renewal/<sid>")
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
                yield f"event: done\ndata: {json.dumps({'status': sess['status'], 'error': sess['error']})}\n\n"
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@license_bp.route("/admin/renewal-reports", methods=["GET"])
@permission_required("license_renewal_admin")
def admin_get_renewal_reports():
    reports = get_all_renewal_reports()
    return jsonify(reports)


@license_bp.route("/admin/license-archive-files", methods=["GET"])
@permission_required("license_renewal_admin")
def admin_get_license_archive_files():
    archive_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "license_archive")
    )
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
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return jsonify(files)


@license_bp.route("/download-archived-license/<filename>", methods=["GET"])
@login_required
def download_archived_license(filename):
    safe_filename = os.path.basename(filename)
    archive_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "license_archive")
    )
    file_path = os.path.join(archive_dir, safe_filename)
    if not os.path.isfile(file_path):
        if os.path.isfile(safe_filename):
            file_path = safe_filename
        else:
            return "License file not found", 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_filename,
    )
