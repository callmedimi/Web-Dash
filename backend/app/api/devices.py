"""Device Inventory & Target Sets REST API (Target Architecture §3 & Phase 5 Step 5.1)."""
import csv
import io
from flask import Blueprint, request, jsonify, g, Response
from typing import Dict, Any, List

from auth import login_required, role_required
from backend.app.db.session import get_db_session
from backend.app.models.device import Device, TargetSet
from backend.app.services.inventory import InventoryService
from backend.app.telemetry import get_telemetry_provider
from backend.app.telemetry.mapping import sync_devices_with_telemetry

devices_bp = Blueprint("devices_inventory", __name__)


@devices_bp.route("", methods=["GET"])
@devices_bp.route("/", methods=["GET"])
@login_required
def list_devices():
    """List devices with filtering and search."""
    province = request.args.get("province")
    site = request.args.get("site")
    role = request.args.get("role")
    os_family = request.args.get("os_family")
    health_status = request.args.get("health_status")
    tag = request.args.get("tag")
    search = request.args.get("search")
    enabled_only = request.args.get("enabled_only", "true").lower() == "true"
    limit = request.args.get("limit", default=200, type=int)
    offset = request.args.get("offset", default=0, type=int)

    with get_db_session() as session:
        devices, total = InventoryService.list_devices(
            session=session,
            province=province,
            site=site,
            role=role,
            os_family=os_family,
            health_status=health_status,
            tag=tag,
            search=search,
            enabled_only=enabled_only,
            limit=limit,
            offset=offset,
        )
        return jsonify({
            "total": total,
            "count": len(devices),
            "offset": offset,
            "limit": limit,
            "devices": [d.to_dict() for d in devices],
        }), 200


@devices_bp.route("/<int:device_id>", methods=["GET"])
@login_required
def get_device(device_id: int):
    """Retrieve single device details."""
    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404
        return jsonify(dev.to_dict()), 200


@devices_bp.route("", methods=["POST"])
@devices_bp.route("/", methods=["POST"])
@login_required
@role_required("admin", "operator")
def create_device():
    """Create a new device."""
    payload = request.get_json() or {}
    name = (payload.get("name") or "").strip()
    mgmt_ip = (payload.get("mgmt_ip") or "").strip()

    if not name or not mgmt_ip:
        return jsonify({"error": "VALIDATION_ERROR", "message": "name and mgmt_ip are required"}), 400

    with get_db_session() as session:
        existing = session.query(Device).filter(Device.name == name).first()
        if existing:
            return jsonify({"error": "ALREADY_EXISTS", "message": f"Device '{name}' already exists"}), 409

        dev = Device(
            name=name,
            mgmt_ip=mgmt_ip,
            vendor=payload.get("vendor", "huawei"),
            os_family=payload.get("os_family", "vrp8"),
            model=payload.get("model"),
            software_version=payload.get("software_version"),
            lsr_id=payload.get("lsr_id"),
            role=payload.get("role"),
            site=payload.get("site"),
            province=payload.get("province"),
            tags=payload.get("tags") or [],
            credential_id=payload.get("credential_id"),
            enabled=payload.get("enabled", True),
        )
        session.add(dev)
        session.commit()
        return jsonify(dev.to_dict()), 201


@devices_bp.route("/<int:device_id>", methods=["PUT"])
@login_required
@role_required("admin", "operator")
def update_device(device_id: int):
    """Update existing device."""
    payload = request.get_json() or {}
    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        for field in [
            "mgmt_ip", "vendor", "os_family", "model", "software_version",
            "lsr_id", "role", "site", "province", "tags", "credential_id",
            "enabled", "zabbix_hostid", "grafana_vars"
        ]:
            if field in payload:
                setattr(dev, field, payload[field])

        session.commit()
        return jsonify(dev.to_dict()), 200


@devices_bp.route("/<int:device_id>", methods=["DELETE"])
@login_required
@role_required("admin", "god")
def delete_device(device_id: int):
    """Delete device or disable it."""
    hard_delete = request.args.get("hard", "false").lower() == "true"
    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        if hard_delete:
            session.delete(dev)
            session.commit()
            return jsonify({"status": "deleted", "device_id": device_id}), 200
        else:
            dev.enabled = False
            session.commit()
            return jsonify({"status": "disabled", "device_id": device_id}), 200


@devices_bp.route("/import-csv", methods=["POST"])
@login_required
@role_required("admin", "operator")
def import_csv():
    """Import devices from Huawei NMS CSV export."""
    update_existing = request.form.get("update_existing", "true").lower() == "true"
    f = request.files.get("file")

    if not f:
        # Check raw JSON payload
        data = request.get_json(silent=True) or {}
        raw_csv = data.get("csv_content")
        if raw_csv:
            f = io.BytesIO(raw_csv.encode("utf-8-sig"))

    if not f:
        return jsonify({"error": "MISSING_FILE", "message": "No file or csv_content provided"}), 400

    with get_db_session() as session:
        summary = InventoryService.import_from_csv(
            session=session,
            file_storage_or_content=f,
            update_existing=update_existing,
        )
        if summary.get("error"):
            return jsonify(summary), 400
        return jsonify(summary), 200


@devices_bp.route("/export", methods=["GET"])
@login_required
def export_devices():
    """Export devices to CSV or JSON."""
    fmt = request.args.get("format", "csv").lower()
    with get_db_session() as session:
        devices = session.query(Device).filter(Device.enabled == True).order_by(Device.name).all()

        if fmt == "json":
            return jsonify([d.to_dict() for d in devices]), 200

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "NE Name", "NE IP Address", "NE Type (MPU Type)", "Software Version",
            "LSR ID", "ESN", "Province", "Site", "Role", "OS Family", "Health Status", "Zabbix HostID"
        ])
        for d in devices:
            writer.writerow([
                d.name, d.mgmt_ip, d.model or "", d.software_version or "",
                d.lsr_id or "", d.esn or "", d.province or "", d.site or "",
                d.role or "", d.os_family, d.health_status, d.zabbix_hostid or ""
            ])

        return Response(
            output.getvalue().encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=devices_export.csv"},
        )


@devices_bp.route("/<int:device_id>/health-check", methods=["POST"])
@login_required
def check_device_health(device_id: int):
    """Run on-demand health check for a device."""
    probe_ssh = request.args.get("probe_ssh", "false").lower() == "true"
    with get_db_session() as session:
        dev = session.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return jsonify({"error": "NOT_FOUND", "message": f"Device {device_id} not found"}), 404

        result = InventoryService.check_health(session, dev, probe_ssh=probe_ssh)
        return jsonify(result), 200


@devices_bp.route("/sync-zabbix", methods=["POST"])
@login_required
@role_required("admin", "operator")
def sync_zabbix():
    """Match devices with Zabbix hosts and report results."""
    payload = request.get_json(silent=True) or {}
    auto_apply = payload.get("auto_apply", True)

    provider = get_telemetry_provider()
    with get_db_session() as session:
        report = sync_devices_with_telemetry(
            db_session=session,
            provider=provider,
            auto_apply=auto_apply,
        )
        return jsonify(report), 200


# --- Saved Target Sets Endpoints ---

@devices_bp.route("/target-sets", methods=["GET"])
@login_required
def list_target_sets():
    """List all saved target sets."""
    with get_db_session() as session:
        tsets = session.query(TargetSet).order_by(TargetSet.name).all()
        return jsonify([t.to_dict() for t in tsets]), 200


@devices_bp.route("/target-sets", methods=["POST"])
@login_required
@role_required("admin", "operator")
def create_target_set():
    """Create a new saved target set."""
    payload = request.get_json() or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "VALIDATION_ERROR", "message": "name is required"}), 400

    with get_db_session() as session:
        existing = session.query(TargetSet).filter(TargetSet.name == name).first()
        if existing:
            return jsonify({"error": "ALREADY_EXISTS", "message": f"TargetSet '{name}' already exists"}), 409

        tset = TargetSet(
            name=name,
            description=payload.get("description"),
            filter_criteria=payload.get("filter_criteria") or {},
            device_ids=payload.get("device_ids") or [],
            created_by_id=getattr(g, "user_id", None),
        )
        session.add(tset)
        session.commit()
        return jsonify(tset.to_dict()), 201


@devices_bp.route("/target-sets/<int:target_set_id>", methods=["GET"])
@login_required
def get_target_set(target_set_id: int):
    """Retrieve target set by ID."""
    with get_db_session() as session:
        tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
        if not tset:
            return jsonify({"error": "NOT_FOUND", "message": f"TargetSet {target_set_id} not found"}), 404
        return jsonify(tset.to_dict()), 200


@devices_bp.route("/target-sets/<int:target_set_id>", methods=["PUT"])
@login_required
@role_required("admin", "operator")
def update_target_set(target_set_id: int):
    """Update saved target set."""
    payload = request.get_json() or {}
    with get_db_session() as session:
        tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
        if not tset:
            return jsonify({"error": "NOT_FOUND", "message": f"TargetSet {target_set_id} not found"}), 404

        if "name" in payload:
            tset.name = payload["name"].strip()
        if "description" in payload:
            tset.description = payload["description"]
        if "filter_criteria" in payload:
            tset.filter_criteria = payload["filter_criteria"]
        if "device_ids" in payload:
            tset.device_ids = payload["device_ids"]

        session.commit()
        return jsonify(tset.to_dict()), 200


@devices_bp.route("/target-sets/<int:target_set_id>", methods=["DELETE"])
@login_required
@role_required("admin", "operator")
def delete_target_set(target_set_id: int):
    """Delete saved target set."""
    with get_db_session() as session:
        tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
        if not tset:
            return jsonify({"error": "NOT_FOUND", "message": f"TargetSet {target_set_id} not found"}), 404

        session.delete(tset)
        session.commit()
        return jsonify({"status": "deleted", "target_set_id": target_set_id}), 200


@devices_bp.route("/target-sets/<int:target_set_id>/devices", methods=["GET"])
@login_required
def resolve_target_set_devices(target_set_id: int):
    """Resolve and return list of devices matched by target set criteria."""
    with get_db_session() as session:
        tset = session.query(TargetSet).filter(TargetSet.id == target_set_id).first()
        if not tset:
            return jsonify({"error": "NOT_FOUND", "message": f"TargetSet {target_set_id} not found"}), 404

        devices = tset.resolve_devices(session)
        return jsonify({
            "target_set": tset.to_dict(),
            "count": len(devices),
            "devices": [d.to_dict() for d in devices],
        }), 200
