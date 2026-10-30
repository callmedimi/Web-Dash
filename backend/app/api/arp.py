"""Site/IP ARP and MAC Address Lookup and Collector Blueprint."""
import csv
import io
import os
import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, send_file, current_app

from site_arp_service import (
    lookup_site_arp_mac_details,
    lookup_ip_arp_mac_details,
    parse_ne_csv_content,
    start_collector_job,
    get_collector_job_status,
    stop_collector_job,
    TARGET_NE_PREFIXES,
)
from auth import login_required, permission_required, user_has_access
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    resolve_request_credentials,
)
from backend.app.extensions import get_db_session
from backend.app.models.arp_mac import ArpMacRecord, ArpMacSnapshot, ArpMacHistory

arp_bp = Blueprint("arp_api", __name__)
logger = logging.getLogger(__name__)


@arp_bp.route("/search-site-arp-mac", methods=["POST"])
@arp_bp.route("/search-ip-arp-mac", methods=["POST"])
@login_required
def search_site_arp_mac():
    user_info = session.get("user", {})
    if not (user_has_access(user_info, "zabbix_search") or user_has_access(user_info, "code_site_search")):
        return jsonify({"error": "Forbidden"}), 403

    data = get_json_payload()
    ip_val = (data.get("ip") or "").strip()
    site_code = (data.get("site_code") or data.get("keyword") or "").strip()

    if not ip_val and not site_code:
        return jsonify({"error": "Site code or IP address is required", "success": False}), 400

    try:
        if ip_val:
            result = lookup_ip_arp_mac_details(ip_val)
        elif re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", site_code):
            result = lookup_ip_arp_mac_details(site_code)
        else:
            result = lookup_site_arp_mac_details(site_code)
        return jsonify(result)
    except Exception as e:
        logger.exception("Site/IP ARP/MAC lookup failed")
        return jsonify({"error": f"Lookup failed: {e}", "success": False}), 500


@arp_bp.route("/admin/parse-ne-csv", methods=["POST"])
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


@arp_bp.route("/admin/run-arp-mac-collector", methods=["POST"])
@login_required
def admin_run_arp_mac_collector():
    threads = 10
    routers = []

    if request.content_type and "multipart/form-data" in request.content_type:
        username, password = resolve_request_credentials(request.form)
        try:
            threads = int(request.form.get("threads", 10))
        except Exception:
            threads = 10

        if "file" in request.files and request.files["file"].filename:
            content = request.files["file"].read()
            matched, _, _ = parse_ne_csv_content(content)
            routers = matched
    else:
        data = get_json_payload()
        username, password = resolve_request_credentials(data)
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


@arp_bp.route("/admin/arp-mac-collector-status", methods=["GET"])
@login_required
def admin_arp_mac_collector_status():
    status = get_collector_job_status()
    return jsonify(status)


@arp_bp.route("/admin/arp-mac-collector-stop", methods=["POST"])
@login_required
def admin_arp_mac_collector_stop():
    stop_collector_job()
    return jsonify({"status": "stopping"})


# ---------------------------------------------------------------------------
# Historical Snapshots & Archive Endpoints (Step 2.1 User Request)
# ---------------------------------------------------------------------------
@arp_bp.route("/admin/arp-mac/snapshots", methods=["GET"])
@login_required
def list_arp_mac_snapshots():
    """List historical ARP/MAC scan snapshots."""
    with get_db_session() as s:
        snapshots = (
            s.query(ArpMacSnapshot)
            .order_by(ArpMacSnapshot.scanned_at.desc())
            .all()
        )
        return jsonify([snap.to_dict() for snap in snapshots])


@arp_bp.route("/admin/arp-mac/snapshots/<snapshot_id>/download", methods=["GET"])
@login_required
def download_arp_mac_snapshot(snapshot_id):
    """Download historical ARP/MAC scan data as a CSV file."""
    with get_db_session() as s:
        snapshot = s.query(ArpMacSnapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            return jsonify({"error": "Snapshot not found"}), 404

        records = (
            s.query(ArpMacHistory)
            .filter_by(snapshot_id=snapshot_id)
            .order_by(ArpMacHistory.ne_name.asc(), ArpMacHistory.arp_ip.asc())
            .all()
        )

        fieldnames = [
            "ne_name",
            "ne_ip",
            "arp_ip",
            "arp_mac",
            "vlan",
            "vrf",
            "arp_interface",
            "mac_port",
            "collected_at",
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()

        for rec in records:
            writer.writerow({
                "ne_name": rec.ne_name,
                "ne_ip": rec.ne_ip,
                "arp_ip": rec.arp_ip,
                "arp_mac": rec.arp_mac,
                "vlan": rec.vlan or "",
                "vrf": rec.vrf or "",
                "arp_interface": rec.arp_interface or "",
                "mac_port": rec.mac_port or "",
                "collected_at": rec.collected_at.isoformat() if rec.collected_at else "",
            })

        mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
        mem.seek(0)
        scanned_str = snapshot.scanned_at.strftime("%Y%m%d_%H%M%S")
        return send_file(
            mem,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"arp_mac_snapshot_{scanned_str}_{snapshot_id[:8]}.csv",
        )


@arp_bp.route("/admin/arp-mac/current/download", methods=["GET"])
@login_required
def download_current_arp_mac():
    """Download current live ARP/MAC table as CSV."""
    with get_db_session() as s:
        records = (
            s.query(ArpMacRecord)
            .order_by(ArpMacRecord.ne_name.asc(), ArpMacRecord.arp_ip.asc())
            .all()
        )
        if not records:
            # Fallback to local arp_mac.csv if DB is empty
            csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "arp_mac.csv"))
            if os.path.isfile(csv_path):
                return send_file(
                    csv_path,
                    mimetype="text/csv",
                    as_attachment=True,
                    download_name="arp_mac.csv",
                )
            return jsonify({"error": "No ARP/MAC records found"}), 404

        fieldnames = [
            "ne_name",
            "ne_ip",
            "arp_ip",
            "arp_mac",
            "vlan",
            "vrf",
            "arp_interface",
            "mac_port",
            "collected_at",
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.to_dict())

        mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
        mem.seek(0)
        return send_file(
            mem,
            mimetype="text/csv",
            as_attachment=True,
            download_name="arp_mac_current.csv",
        )
