"""Zabbix Telemetry and Router Database Blueprint."""
import json
import logging
import os
import threading
from flask import Blueprint, request, jsonify, session, current_app

from services.zabbix_service import ZabbixService, create_zabbix_service
from auth import login_required, permission_required
from audit import record_audit
from validators import validate_host_or_ip
from backend.app.api.common import get_client_ip, get_json_payload
from backend.app.extensions import get_db_session
from backend.app.services.monitoring import MonitoringHubService

telemetry_bp = Blueprint("telemetry_api", __name__)
logger = logging.getLogger(__name__)

_ZABBIX_INI = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "zabbix_config.ini"))
_ZABBIX_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "zabbix_router_db.json"))
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


@telemetry_bp.route("/admin/zabbix-groups", methods=["GET"])
@permission_required("zabbix_db_refresh")
def admin_get_zabbix_groups():
    try:
        svc = _get_zabbix_service()
        groups = svc.get_groups()
        return jsonify({"groups": [{"name": g.name, "id": g.groupid} for g in groups]})
    except Exception as e:
        logger.exception("Failed to get Zabbix groups")
        return jsonify({"error": f"Failed to get Zabbix groups: {e}"}), 500


@telemetry_bp.route("/admin/refresh-zabbix-db", methods=["POST"])
@permission_required("zabbix_db_refresh")
def admin_refresh_zabbix_db():
    data = get_json_payload(silent=True)
    group_names = data.get("groups")
    replace = data.get("replace", False)
    if not group_names or not isinstance(group_names, list):
        return jsonify({"error": "No Zabbix groups specified for refresh"}), 400

    if not _zabbix_refresh_lock.acquire(blocking=False):
        return jsonify({"error": "Refresh already in progress"}), 429

    def _run_refresh_task(groups_to_refresh, do_replace):
        try:
            if do_replace and os.path.isfile(_ZABBIX_DB):
                os.remove(_ZABBIX_DB)
                logger.info("Deleted existing DB for full rebuild")
            svc = _get_zabbix_service()
            for group_name in groups_to_refresh:
                logger.info("Refreshing Zabbix DB for group: %s", group_name)
                svc.refresh_router_db(group_name=group_name, db_path=_ZABBIX_DB)
            logger.info("Zabbix DB refresh completed for all selected groups.")
        except Exception:
            logger.exception("Zabbix DB refresh failed")
        finally:
            _zabbix_refresh_lock.release()

    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "zabbix_db_refresh", "groups": group_names, "replace": replace},
    )
    t = threading.Thread(target=_run_refresh_task, args=(group_names, replace), daemon=True)
    t.start()
    action = "Rebuild" if replace else "Refresh"
    return jsonify({
        "status": "started",
        "message": f"{action} started for groups: {', '.join(group_names)}",
    }), 202


@telemetry_bp.route("/admin/delete-zabbix-db", methods=["POST"])
@permission_required("zabbix_db_refresh")
def admin_delete_zabbix_db():
    if os.path.isfile(_ZABBIX_DB):
        os.remove(_ZABBIX_DB)
        return jsonify({"status": "deleted"})
    return jsonify({"status": "not_found"})


@telemetry_bp.route("/refresh-zabbix-progress", methods=["GET"])
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


@telemetry_bp.route("/search-zabbix-interfaces", methods=["POST"])
@permission_required("zabbix_search")
def search_zabbix_interfaces():
    data = get_json_payload()
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
        logger.exception("Zabbix search failed")
        return jsonify({"error": f"Search failed: {e}"}), 500


@telemetry_bp.route("/search-zabbix-ip", methods=["POST"])
@permission_required("zabbix_search")
def search_zabbix_ip():
    data = get_json_payload()
    ip_raw = (data.get("ip") or "").strip()

    if not ip_raw:
        return jsonify({"error": "IP address is required"}), 400

    ip = validate_host_or_ip(ip_raw)

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
        logger.exception("Zabbix search failed")
        return jsonify({"error": f"Search failed: {e}"}), 500


# ---------------------------------------------------------------------------
# Modern Phase 5 REST Endpoints (/api/v1/telemetry/*)
# ---------------------------------------------------------------------------

@telemetry_bp.route("/api/v1/telemetry/fleet-health", methods=["GET"])
@login_required
def api_v1_fleet_health():
    """Fleet-wide health overview aggregated from Zabbix telemetry."""
    province = request.args.get("province")
    role = request.args.get("role")
    with get_db_session() as s:
        health = MonitoringHubService.get_fleet_health(
            db_session=s,
            filter_province=province,
            filter_role=role,
        )
        return jsonify(health), 200


@telemetry_bp.route("/api/v1/telemetry/device/<device_identifier>", methods=["GET"])
@login_required
def api_v1_device_monitoring(device_identifier):
    """Device monitoring tab data: interfaces, metrics, CPU/mem series, Grafana URLs."""
    t_from = request.args.get("from", "now-6h")
    t_to = request.args.get("to", "now")
    with get_db_session() as s:
        mon = MonitoringHubService.get_device_monitoring(
            db_session=s,
            device_identifier=device_identifier,
            t_from=t_from,
            t_to=t_to,
        )
        return jsonify(mon), 200


@telemetry_bp.route("/api/v1/telemetry/search-interfaces", methods=["POST"])
@login_required
def api_v1_search_interfaces():
    """Modern interface search endpoint using TelemetryProvider with legacy fallback."""
    data = get_json_payload()
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"error": "Keyword is required", "results": []}), 400

    with get_db_session() as s:
        res = MonitoringHubService.search_interfaces(
            db_session=s,
            keyword=keyword,
        )
        return jsonify(res), 200


@telemetry_bp.route("/api/v1/telemetry/merge-alarms", methods=["POST"])
@login_required
def api_v1_merge_alarms():
    """Merge SSH alarms with Zabbix problems and return device selection shortcuts."""
    data = get_json_payload()
    ssh_alarms = data.get("ssh_alarms", [])
    with get_db_session() as s:
        merged = MonitoringHubService.merge_alarms(
            db_session=s,
            ssh_alarms=ssh_alarms,
        )
        return jsonify(merged), 200


@telemetry_bp.route("/api/v1/telemetry/doctor", methods=["GET"])
@login_required
def api_v1_telemetry_doctor():
    """Diagnostic doctor suite testing Zabbix API, Grafana health, and mapping coverage."""
    with get_db_session() as s:
        diag = MonitoringHubService.test_integrations(db_session=s)
        return jsonify(diag), 200


@telemetry_bp.route("/api/v1/telemetry/webhook", methods=["POST"])
def api_v1_telemetry_webhook():
    """Intake endpoint for external alert webhooks from Zabbix, Grafana, or alerting bots."""
    data = get_json_payload(silent=True) or {}
    with get_db_session() as s:
        res = MonitoringHubService.process_webhook(data, db_session=s)
        return jsonify(res), 200

