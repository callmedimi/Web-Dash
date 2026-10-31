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
from backend.app.api.common import (
    get_client_ip,
    get_json_payload,
    resolve_request_credentials,
)
from backend.app.devices.session import DeviceSession

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
    username, password = resolve_request_credentials(data)
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
    username, password = resolve_request_credentials(data)
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
    username, password = resolve_request_credentials(data)
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


# --- Step 5.5 Modern Automation Catalog VRF Routing Endpoints ---

@routing_bp.route("/api/v1/routing/vrfs", methods=["GET"])
@routing_bp.route("/routing/vrfs", methods=["GET"])
@login_required
def get_known_vrfs():
    """Retrieve list of recognized VRF names and their associated Route Targets."""
    from backend.app.services.routing import VRF_RT_MAP, RT_TO_VRF_MAP
    return jsonify({
        "vrfs": sorted(VRF_RT_MAP.keys()),
        "vrf_count": len(VRF_RT_MAP),
        "vrf_rt_map": VRF_RT_MAP,
    }), 200


@routing_bp.route("/api/v1/routing/trace", methods=["POST"])
@routing_bp.route("/routing/trace", methods=["POST"])
@login_required
def trace_vrf_routing_hop():
    """Trace a VRF route hop-by-hop and return the per-hop result table and topology path graph."""
    from backend.app.features.registry import feature_registry
    from backend.app.features.base import FeatureContext
    from backend.app.db.session import get_db_session

    feature = feature_registry.get("vrf_routing_check")
    if not feature:
        return jsonify({"error": "FEATURE_UNAVAILABLE", "message": "VRF routing feature not registered"}), 500

    payload = request.get_json(silent=True) or {}
    user_id = session.get("user", {}).get("id")

    with get_db_session() as db_sess:
        ctx = FeatureContext(
            db_session=db_sess,
            user_id=user_id,
            params=payload,
        )
        res = feature.run(ctx)
        status_code = 200 if res.get("status") != "failed" else 400
        return jsonify(res), status_code


@routing_bp.route("/api/v1/routing/check-prefix", methods=["POST"])
@routing_bp.route("/routing/check-prefix", methods=["POST"])
@login_required
def check_prefix_in_vrf():
    """Quick lookup of a prefix in a specific VRF on a designated router."""
    from backend.app.services.routing import VrfRoutingService
    from backend.app.db.session import get_db_session
    from backend.app.models.device import Device

    payload = request.get_json(silent=True) or {}
    vrf = payload.get("vrf", "")
    target = payload.get("target_ip", "")
    device_id = payload.get("device_id")

    if not vrf or not target:
        return jsonify({"error": "MISSING_PARAMS", "message": "Both 'vrf' and 'target_ip' are required"}), 400

    try:
        clean_vrf, clean_target = VrfRoutingService.validate_vrf_and_target(vrf, target)
    except ValueError as exc:
        return jsonify({"error": "VALIDATION_FAILED", "message": str(exc)}), 400

    target_host = clean_target.split("/")[0]

    with get_db_session() as db_sess:
        device = None
        if device_id:
            device = db_sess.query(Device).filter(Device.id == device_id).first()
        if not device:
            device = db_sess.query(Device).filter(Device.enabled == True).first()

        if not device:
            return jsonify({"error": "NO_DEVICE", "message": "No suitable router found to execute route check"}), 404

        vrf_cmd = f"display ip routing-table vpn-instance {clean_vrf} {target_host}"
        with DeviceSession(ip=device.mgmt_ip, os_family=device.os_family, device_name=device.name) as ds:
            out = ds.run(vrf_cmd)

        parsed = VrfRoutingService.parse_routing_table(out)
        matching = [
            r for r in parsed
            if VrfRoutingService.ip_matches_route(target_host, r.get("destination", ""), r.get("mask", ""))
        ]

        return jsonify({
            "device_name": device.name,
            "mgmt_ip": device.mgmt_ip,
            "vrf": clean_vrf,
            "target": clean_target,
            "has_route": len(matching) > 0,
            "routes_count": len(matching),
            "matching_routes": matching,
        }), 200

