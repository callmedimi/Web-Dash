"""VRF and BGP Routing Check Blueprint."""
import netmiko
from flask import Blueprint, request, jsonify, session

from check_vrf_routing import (
    parse_interface_config,
    batch_check_routing,
    check_bgp_route,
    query_vrf_route_and_configs,
    transform_originator_ip,
    get_sysname,
    HARDCODED_ROUTER_NAME,
    HARDCODED_ROUTER_IP,
)
from auth import login_required, permission_required
from audit import record_audit
from validators import (
    validate_target_ip,
    validate_timeout,
    validate_host_or_ip,
    validate_vrf_name,
)
from backend.app.api.common import get_client_ip, get_json_payload

routing_bp = Blueprint("routing_api", __name__)


@routing_bp.route("/vrf-router-info")
@login_required
def vrf_router_info():
    return jsonify({"name": HARDCODED_ROUTER_NAME, "ip": HARDCODED_ROUTER_IP})


@routing_bp.route("/parse-interface-config", methods=["POST"])
@permission_required("vrf_routing")
def parse_interface_config_route():
    data = get_json_payload()
    config_text = data.get("config", "")
    if not config_text.strip():
        return jsonify({"error": "No interface configuration provided"}), 400
    parsed = parse_interface_config(config_text)
    return jsonify(parsed)


@routing_bp.route("/check-vrf-routing", methods=["POST"])
@permission_required("vrf_routing")
def check_vrf_routing_route():
    data = get_json_payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    config_text = data.get("config", "")

    # 1. Extract and validate target_ip from the request
    target_ip_raw = (data.get("target_ip") or "").strip()
    target_ip = validate_target_ip(target_ip_raw) if target_ip_raw else ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not config_text.strip():
        return jsonify({"error": "No interface configuration provided"}), 400

    conn_to = validate_timeout(data.get("conn_timeout", 20), default=20)
    cmd_to = validate_timeout(data.get("cmd_timeout", 60), default=60)

    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "vrf_routing"},
    )
    result = batch_check_routing(
        username=username,
        password=password,
        config_text=config_text,
        target_ip=target_ip,
        conn_timeout=conn_to,
        cmd_timeout=cmd_to,
    )
    return jsonify(result)


@routing_bp.route("/check-bgp-route", methods=["POST"])
@permission_required("vrf_routing")
def check_bgp_route_route():
    data = get_json_payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    target_ip_raw = (data.get("target_ip") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not target_ip_raw:
        return jsonify({"error": "Target IP address is required"}), 400

    target_ip = validate_target_ip(target_ip_raw)

    user = session.get("username") or "unknown"
    record_audit(
        "job_started",
        user,
        get_client_ip(),
        status="success",
        detail={"feature": "bgp_routing", "target_ip": target_ip},
    )

    try:
        conn = netmiko.ConnectHandler(
            device_type="huawei",
            host=HARDCODED_ROUTER_IP,
            username=username,
            password=password,
            timeout=20,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to connect to {HARDCODED_ROUTER_NAME} ({HARDCODED_ROUTER_IP}): {e}"}), 502

    try:
        entries, _ = check_bgp_route(conn, target_ip, cmd_timeout=90)
        conn.disconnect()
    except Exception as e:
        try:
            conn.disconnect()
        except Exception:
            pass
        return jsonify({"error": f"BGP query failed: {e}"}), 502

    return jsonify({
        "status": "success",
        "router": {"name": HARDCODED_ROUTER_NAME, "ip": HARDCODED_ROUTER_IP},
        "target_ip": target_ip,
        "entries": entries,
        "entry_count": len(entries),
    })


@routing_bp.route("/show-originator-interfaces", methods=["POST"])
@permission_required("vrf_routing")
def show_originator_interfaces_route():
    data = get_json_payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    originator_ip_raw = (data.get("originator_ip") or "").strip()
    target_ip_raw = (data.get("target_ip") or "").strip()
    prefix_raw = (data.get("prefix") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if not originator_ip_raw:
        return jsonify({"error": "Originator IP is required"}), 400
    if not target_ip_raw:
        return jsonify({"error": "Target IP is required"}), 400
    vrf_raw = (data.get("vrf") or "").strip()
    if not vrf_raw:
        return jsonify({"error": "VRF name is required"}), 400

    originator_ip = validate_host_or_ip(originator_ip_raw)
    target_ip = validate_target_ip(target_ip_raw.split("/")[0])
    vrf = validate_vrf_name(vrf_raw)
    prefix = validate_target_ip(prefix_raw) if prefix_raw else ""

    connect_ip = transform_originator_ip(originator_ip)

    try:
        conn = netmiko.ConnectHandler(
            device_type="huawei",
            host=connect_ip,
            username=username,
            password=password,
            timeout=20,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to connect to {originator_ip}: {e}"}), 502

    try:
        sysname = get_sysname(conn, cmd_timeout=10)
        result = query_vrf_route_and_configs(conn, vrf, target_ip, prefix=prefix, cmd_timeout=60)
        conn.disconnect()
    except Exception as e:
        try:
            conn.disconnect()
        except Exception:
            pass
        return jsonify({"error": f"Query failed: {e}"}), 502

    return jsonify({
        "status": "success",
        "originator_ip": originator_ip,
        "connect_ip": connect_ip if connect_ip != originator_ip else None,
        "target_ip": target_ip,
        "sysname": sysname,
        "result": result,
    })
