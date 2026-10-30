"""Device to Telemetry Host mapping and synchronization (Target Architecture §3 & Step 3.4.4)."""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.models.device import Device
from backend.app.telemetry.base import TelemetryProvider
from backend.app.telemetry.models import TelemetryHost


def sync_devices_with_telemetry(
    db_session: Session,
    provider: TelemetryProvider,
    auto_apply: bool = False,
) -> Dict[str, Any]:
    """
    Match database Device records with Zabbix monitoring hosts.

    Matching precedence:
    1. Exact host name == device.name
    2. Visible name == device.name
    3. Management IP matches any host interface IP

    Rules:
    - Unambiguous matches are linked (zabbix_hostid set) if auto_apply is True.
    - Ambiguous matches (multiple candidates) are NEVER auto-linked.
    - Returns structured synchronization report.
    """
    db_devices = db_session.query(Device).all()
    zabbix_hosts = provider.list_hosts()

    # Index Zabbix hosts
    by_host_name: Dict[str, List[TelemetryHost]] = {}
    by_visible_name: Dict[str, List[TelemetryHost]] = {}
    by_ip: Dict[str, List[TelemetryHost]] = {}

    for zh in zabbix_hosts:
        by_host_name.setdefault(zh.name.strip().lower(), []).append(zh)
        if zh.visible_name:
            by_visible_name.setdefault(zh.visible_name.strip().lower(), []).append(zh)
        for iface in zh.interfaces:
            ip = iface.get("ip", "").strip()
            if ip:
                by_ip.setdefault(ip, []).append(zh)

    matched: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []
    missing_in_zabbix: List[str] = []
    claimed_zabbix_ids = set()

    for dev in db_devices:
        dev_name_clean = dev.name.strip().lower()
        candidates: List[TelemetryHost] = []

        # 1. Exact host name
        if dev_name_clean in by_host_name:
            candidates.extend(by_host_name[dev_name_clean])

        # 2. Visible name
        if not candidates and dev_name_clean in by_visible_name:
            candidates.extend(by_visible_name[dev_name_clean])

        # 3. IP address
        if not candidates and dev.mgmt_ip and dev.mgmt_ip.strip() in by_ip:
            candidates.extend(by_ip[dev.mgmt_ip.strip()])

        # Deduplicate candidates by host_id
        unique_candidates = {c.host_id: c for c in candidates}

        if len(unique_candidates) == 1:
            candidate = list(unique_candidates.values())[0]
            claimed_zabbix_ids.add(candidate.host_id)
            matched.append({
                "device_id": dev.id,
                "device_name": dev.name,
                "mgmt_ip": dev.mgmt_ip,
                "zabbix_host_id": candidate.host_id,
                "zabbix_name": candidate.name,
                "groups": candidate.groups,
            })
            if auto_apply:
                dev.zabbix_hostid = candidate.host_id
                if not dev.site and candidate.groups:
                    # Suggest site from group if available
                    dev.site = candidate.groups[0]
        elif len(unique_candidates) > 1:
            for c in unique_candidates.values():
                claimed_zabbix_ids.add(c.host_id)
            ambiguous.append({
                "device_id": dev.id,
                "device_name": dev.name,
                "candidate_host_ids": [c.host_id for c in unique_candidates.values()],
                "candidate_names": [c.name for c in unique_candidates.values()],
            })
        else:
            missing_in_zabbix.append(dev.name)

    if auto_apply and matched:
        db_session.commit()

    zabbix_not_in_inventory = [
        {"host_id": zh.host_id, "name": zh.name, "visible_name": zh.visible_name}
        for zh in zabbix_hosts
        if zh.host_id not in claimed_zabbix_ids
    ]

    return {
        "total_devices": len(db_devices),
        "total_zabbix_hosts": len(zabbix_hosts),
        "matched_count": len(matched),
        "matched": matched,
        "ambiguous_count": len(ambiguous),
        "ambiguous": ambiguous,
        "missing_in_zabbix_count": len(missing_in_zabbix),
        "missing_in_zabbix": missing_in_zabbix,
        "zabbix_not_in_inventory_count": len(zabbix_not_in_inventory),
        "zabbix_not_in_inventory": zabbix_not_in_inventory,
    }
