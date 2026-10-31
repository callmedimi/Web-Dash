"""Down-links and Trunk Reporting Blueprint."""
import csv
import io
import json
import threading
import uuid
from datetime import datetime
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file, session

from reporting_logic import (
    process_one_report,
    extract_provinces,
    filter_routers_by_province,
    compute_analytics,
    FIELD_NAMES,
    TRUNK_FIELD_NAMES,
)
from auth import login_required, permission_required
from audit import record_audit
from validators import validate_province, validate_age, validate_routers_list
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    parse_csv_to_routers,
    resolve_request_credentials,
)

reports_bp = Blueprint("reports_api", __name__)

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
            "trunk_data": [],
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


def _run_report(
    sid: str,
    routers: list[dict],
    username: str,
    password: str,
    age_value: int = 2,
    age_unit: str = "days",
) -> None:
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
                process_one_report,
                r["name"],
                r["ip"],
                username,
                password,
                _log,
                conn_timeout=30,
                cmd_timeout=90,
                age_value=age_value,
                age_unit=age_unit,
            ): r["name"]
            for r in routers
        }
        for future in as_completed(futures):
            res = future.result()
            with sess["result_lock"]:
                sess["report_data"].extend(res["data"])
                sess["noconf_data"].extend(res["noconf_data"])
                sess["trunk_data"].extend(res.get("trunk_data", []))
                sess["completed_count"] += 1
                completed = sess["completed_count"]
            _log(
                f"[{completed}/{sess['router_count']}] "
                f"{res['name']}: {res['status']} — "
                f"{len(res['data'])} service, {len(res['noconf_data'])} noconf",
                "info",
            )

    sess["analytics"] = compute_analytics(
        sess["report_data"], sess["noconf_data"], sess.get("trunk_data", [])
    )
    finish_report_session(sid)


@reports_bp.route("/parse-csv-nodes", methods=["POST"])
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


@reports_bp.route("/run-report", methods=["POST"])
@permission_required("reporting")
def run_report():
    data = get_json_payload()
    routers_raw = data.get("routers", [])
    province_raw = data.get("province")
    if not province_raw:
        return jsonify({"error": "Province code is required"}), 400
    province = validate_province(province_raw)
    username, password = resolve_request_credentials(data)
    age_value, age_unit = validate_age(data.get("age_value", 2), data.get("age_unit", "days"))

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = validate_routers_list(routers_raw, max_items=2000)
    filtered = filter_routers_by_province(routers, province)
    if not filtered:
        return jsonify({"error": f"No routers found matching province '_{province}'"}), 422

    sid = create_report_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "reporting", "province": province, "router_count": len(filtered)},
    )
    t = threading.Thread(
        target=_run_report,
        args=(sid, filtered, username, password),
        kwargs={"age_value": age_value, "age_unit": age_unit},
        daemon=True,
    )
    t.start()
    return jsonify({
        "session_id": sid,
        "router_count": len(filtered),
        "province": province,
    })


@reports_bp.route("/run-full-report", methods=["POST"])
@permission_required("reporting")
def run_full_report():
    data = get_json_payload()
    routers_raw = data.get("routers", [])
    username, password = resolve_request_credentials(data)
    age_value, age_unit = validate_age(data.get("age_value", 2), data.get("age_unit", "days"))

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    routers = validate_routers_list(routers_raw, max_items=2000)

    sid = create_report_session()
    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "reporting_full", "router_count": len(routers)},
    )
    t = threading.Thread(
        target=_run_report,
        args=(sid, routers, username, password),
        kwargs={"age_value": age_value, "age_unit": age_unit},
        daemon=True,
    )
    t.start()
    return jsonify({
        "session_id": sid,
        "router_count": len(routers),
        "province": "ALL",
    })


@reports_bp.route("/stream-report/<sid>")
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


@reports_bp.route("/download-report/<sid>")
@login_required
def download_report(sid):
    sess = get_report_session(sid)
    if sess is None:
        return "Session not found", 404
    if not sess["report_data"] and not sess["noconf_data"]:
        return "No report data available", 404

    all_rows = sess["report_data"] + sess["noconf_data"]
    all_rows.sort(key=lambda x: (x.get("NE NAME", ""), x.get("interface name", "")))

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


@reports_bp.route("/download-trunk-report/<sid>")
@login_required
def download_trunk_report(sid):
    sess = get_report_session(sid)
    if sess is None:
        return "Session not found", 404
    trunk_data = sess.get("trunk_data", [])
    if not trunk_data:
        return "No trunk data available", 404

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=TRUNK_FIELD_NAMES)
    writer.writeheader()
    writer.writerows(trunk_data)

    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"eth_trunks_report_{sid}.csv",
    )


@reports_bp.route("/report-session/<sid>")
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


@reports_bp.route("/report-analytics/<sid>")
@login_required
def report_analytics(sid):
    sess = get_report_session(sid)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404
    analytics = sess.get("analytics")
    if analytics is None:
        return jsonify({"error": "Analytics not yet available"}), 425
    return jsonify(analytics)


# --- Step 5.3 Modern Automation Catalog Down-Links Endpoints ---

@reports_bp.route("/api/v1/reports/down-links/run", methods=["POST"])
@login_required
def run_down_links_report():
    """Run a down-links scan across target devices or province."""
    from backend.app.features.registry import feature_registry
    from backend.app.features.base import FeatureContext
    from backend.app.db.session import get_db_session

    feature = feature_registry.get("down_links")
    if not feature:
        return jsonify({"error": "FEATURE_UNAVAILABLE", "message": "Down-links feature not registered"}), 500

    payload = request.get_json(silent=True) or {}
    user_id = session.get("user", {}).get("id")

    with get_db_session() as db_sess:
        ctx = FeatureContext(
            db_session=db_sess,
            user_id=user_id,
            params=payload,
        )
        res = feature.run(ctx)
        return jsonify(res), 200


@reports_bp.route("/api/v1/reports/down-links/latest", methods=["GET"])
@login_required
def get_latest_down_links_report():
    """Retrieve the most recent down-links report (optionally filtered by province)."""
    from backend.app.db.session import get_db_session
    from backend.app.models.down_link import DownLinkReport

    province = request.args.get("province")
    with get_db_session() as db_sess:
        query = db_sess.query(DownLinkReport)
        if province:
            query = query.filter(DownLinkReport.province == province.upper())
        report = query.order_by(DownLinkReport.created_at.desc()).first()
        if not report:
            return jsonify({"error": "NOT_FOUND", "message": "No down-links report found"}), 404
        return jsonify(report.to_dict(include_details=True)), 200


@reports_bp.route("/api/v1/reports/down-links/<int:report_id>", methods=["GET"])
@login_required
def get_down_links_report_by_id(report_id: int):
    """Retrieve a specific down-links report by ID."""
    from backend.app.db.session import get_db_session
    from backend.app.models.down_link import DownLinkReport

    with get_db_session() as db_sess:
        report = db_sess.query(DownLinkReport).filter(DownLinkReport.id == report_id).first()
        if not report:
            return jsonify({"error": "NOT_FOUND", "message": f"Report {report_id} not found"}), 404
        return jsonify(report.to_dict(include_details=True)), 200


@reports_bp.route("/api/v1/reports/down-links/<int:report_id>/compare", methods=["GET"])
@login_required
def compare_down_links_report(report_id: int):
    """Compare a down-links report with another report or previous day's report."""
    from backend.app.db.session import get_db_session
    from backend.app.models.down_link import DownLinkReport
    from backend.app.services.reporting import DownLinksService

    with get_db_session() as db_sess:
        current = db_sess.query(DownLinkReport).filter(DownLinkReport.id == report_id).first()
        if not current:
            return jsonify({"error": "NOT_FOUND", "message": f"Report {report_id} not found"}), 404

        other_id = request.args.get("compare_with_id", type=int)
        if other_id:
            previous = db_sess.query(DownLinkReport).filter(DownLinkReport.id == other_id).first()
        else:
            # Query the latest report created before current report
            query = db_sess.query(DownLinkReport).filter(DownLinkReport.id < report_id)
            if current.province:
                query = query.filter(DownLinkReport.province == current.province)
            previous = query.order_by(DownLinkReport.created_at.desc()).first()

        if not previous:
            return jsonify({
                "message": "No previous report found for comparison",
                "current_report_id": current.id,
                "comparison": None,
            }), 200

        diff = DownLinksService.compare_reports(
            current_report={"report_data": current.report_data, "noconf_data": current.noconf_data},
            previous_report={"report_data": previous.report_data, "noconf_data": previous.noconf_data},
        )
        diff["current_report_id"] = current.id
        diff["previous_report_id"] = previous.id
        diff["previous_created_at"] = previous.created_at.isoformat()
        return jsonify(diff), 200


@reports_bp.route("/api/v1/reports/down-links/<int:report_id>/export", methods=["GET"])
@login_required
def export_down_links_report(report_id: int):
    """Export down-links report to CSV or multi-tab XLSX."""
    from backend.app.db.session import get_db_session
    from backend.app.models.down_link import DownLinkReport
    from backend.app.services.reporting import DownLinksService

    fmt = request.args.get("format", "csv").lower()
    with get_db_session() as db_sess:
        report = db_sess.query(DownLinkReport).filter(DownLinkReport.id == report_id).first()
        if not report:
            return jsonify({"error": "NOT_FOUND", "message": f"Report {report_id} not found"}), 404

        if fmt == "xlsx":
            xlsx_bytes = DownLinksService.export_xlsx(
                report_data=report.report_data,
                noconf_data=report.noconf_data,
                trunk_data=report.trunk_data,
                analytics=report.analytics,
            )
            return send_file(
                io.BytesIO(xlsx_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"down_links_report_{report_id}.xlsx",
            )
        else:
            csv_bytes = DownLinksService.export_csv(
                report_data=report.report_data,
                noconf_data=report.noconf_data,
                trunk_data=report.trunk_data,
            )
            return send_file(
                io.BytesIO(csv_bytes),
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"down_links_report_{report_id}.csv",
            )

