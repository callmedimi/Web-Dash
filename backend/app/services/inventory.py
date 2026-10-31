"""Inventory and Discovery Service (Target Architecture §3 & Phase 5 Step 5.1).

Handles NMS CSV import, province/site/role derivation, groups/tags,
device health status, and saved target sets.
"""
from datetime import datetime
import re
import socket
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models.device import Device, TargetSet
from backend.app.api.common import parse_csv_to_routers
from backend.app.telemetry.mapping import sync_devices_with_telemetry
from backend.app.telemetry.base import DisabledProvider
from backend.app.telemetry.zabbix import ZabbixProvider

PROVINCE_CODES: Dict[str, str] = {
    "TEH": "Tehran", "TH": "Tehran", "TE": "Tehran",
    "ISF": "Isfahan", "IS": "Isfahan", "ESF": "Isfahan",
    "KHR": "Khorasan Razavi", "KH": "Khorasan",
    "KZH": "Khuzestan", "KZ": "Khuzestan",
    "FRS": "Fars", "FR": "Fars",
    "AZS": "East Azerbaijan", "EAZ": "East Azerbaijan",
    "AZG": "West Azerbaijan", "WAZ": "West Azerbaijan",
    "GIL": "Gilan", "GL": "Gilan",
    "MAZ": "Mazandaran", "MZ": "Mazandaran",
    "QOM": "Qom", "QM": "Qom",
    "MRK": "Markazi", "MK": "Markazi",
    "KRD": "Kurdistan", "KD": "Kurdistan",
    "SBN": "Sistan and Baluchestan", "SB": "Sistan and Baluchestan",
    "KRM": "Kerman", "KM": "Kerman",
    "YZD": "Yazd", "YZ": "Yazd",
    "HRZ": "Hormozgan", "HR": "Hormozgan",
    "BHR": "Bushehr", "BH": "Bushehr",
    "CHB": "Chaharmahal and Bakhtiari", "CB": "Chaharmahal and Bakhtiari",
    "KHB": "South Khorasan", "SKH": "South Khorasan",
    "LRS": "Lorestan", "LR": "Lorestan",
    "SMN": "Semnan", "SM": "Semnan",
    "ZNJ": "Zanjan", "ZN": "Zanjan",
    "GLS": "Golestan", "GS": "Golestan",
    "ARD": "Ardabil", "AR": "Ardabil",
    "ILM": "Ilam", "IL": "Ilam",
    "KBD": "Kermanshah", "KS": "Kermanshah",
    "NKH": "North Khorasan",
    "QZV": "Qazvin", "QZ": "Qazvin",
    "ALB": "Alborz", "AB": "Alborz",
}

ROLE_KEYWORDS: List[str] = ["PE", "BRAS", "RR", "AGG", "ACC", "P"]


def derive_province_and_site(device_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Derive (province, site, role) from standard Huawei NOC naming conventions.
    Examples:
      - 'TEH-MHD-PE01_TH' -> province='TH', site='TEH-MHD', role='PE'
      - 'ISF-P01_IS'     -> province='IS', site='ISF', role='P'
      - 'KERMAN-AGG02'    -> province='KRM', site='KERMAN', role='AGG'
    """
    clean_name = (device_name or "").strip()
    if not clean_name:
        return None, None, None

    # 1. Derive Province from suffix '_XXX' or known tokens
    province = None
    suffix_match = re.search(r'_([A-Za-z0-9]{2,4})$', clean_name)
    if suffix_match:
        cand = suffix_match.group(1).upper()
        if cand in PROVINCE_CODES:
            province = cand
        else:
            # Fallback: check 2-letter prefix
            cand2 = cand[:2]
            if cand2 in PROVINCE_CODES:
                province = cand2

    if not province:
        # Check token-based search for province code
        tokens = re.split(r'[-_]', clean_name.upper())
        for token in tokens:
            if token in PROVINCE_CODES:
                province = token
                break

    # 2. Derive Role
    role = None
    upper_name = clean_name.upper()
    for kw in ROLE_KEYWORDS:
        # Match as distinct token or adjacent to digits (e.g. PE01, P02, BRAS-1)
        if re.search(rf'(?:[-_]|^){kw}(?:\d+|[-_]|$)', upper_name):
            role = kw
            break

    # 3. Derive Site
    # Site is typically the segment before role or first 1-2 hyphen segments
    base_name = re.sub(r'_[A-Za-z0-9]{2,4}$', '', clean_name)  # remove province suffix
    parts = base_name.split('-')
    site = None
    if len(parts) >= 2:
        # If last part is role or role+num, site is prefix
        if role and any(kw in parts[-1].upper() for kw in ROLE_KEYWORDS):
            site = "-".join(parts[:-1])
        else:
            site = parts[0]
    elif len(parts) == 1:
        # Try splitting by underscore
        subparts = base_name.split('_')
        if len(subparts) > 1:
            site = subparts[0]
        else:
            site = base_name

    return province, site, role


def derive_os_family(model: Optional[str] = None, version: Optional[str] = None) -> str:
    """Derive os_family (vrp8 vs vrp5) from model name or software version."""
    haystack = f"{model or ''} {version or ''}".upper()
    if any(k in haystack for k in ["VRP8", "V8", "NE40E", "NETENGINE 40E", "NE8000", "NETENGINE 8000", "CX600"]):
        return "vrp8"
    if any(k in haystack for k in ["VRP5", "V5", "AR12", "AR22", "S5700", "S6700"]):
        return "vrp5"
    return "vrp8"  # Default to VRP8 for Huawei IP/MPLS core/PE routers


class InventoryService:
    """Core inventory, discovery, and device lifecycle management."""

    @staticmethod
    def import_from_csv(
        session: Session,
        file_storage_or_content,
        update_existing: bool = True,
    ) -> Dict[str, Any]:
        """
        Import or synchronize devices from NMS CSV export.
        Upserts by device name and reports what was added, updated, or unchanged.
        """
        routers, err = parse_csv_to_routers(file_storage_or_content)
        if err:
            return {"error": "CSV_PARSE_ERROR", "message": err, "total": 0}

        added: List[Dict[str, Any]] = []
        updated: List[Dict[str, Any]] = []
        unchanged: List[str] = []
        errors: List[Dict[str, Any]] = []

        for row in routers:
            name = row.get("name", "").strip()
            ip = row.get("ip", "").strip()
            if not name or not ip:
                errors.append({"row": row, "reason": "Missing NE Name or IP Address"})
                continue

            model = row.get("ne_type") or None
            version = row.get("version") or None
            lsr_id = row.get("lsr_id") or None
            esn = row.get("esn") or None

            existing = session.query(Device).filter(Device.name == name).first()
            if existing:
                diff = {}
                if existing.mgmt_ip != ip:
                    diff["mgmt_ip"] = {"old": existing.mgmt_ip, "new": ip}
                if model and existing.model != model:
                    diff["model"] = {"old": existing.model, "new": model}
                if version and existing.software_version != version:
                    diff["software_version"] = {"old": existing.software_version, "new": version}
                if lsr_id and existing.lsr_id != lsr_id:
                    diff["lsr_id"] = {"old": existing.lsr_id, "new": lsr_id}
                if esn and existing.esn != esn:
                    diff["esn"] = {"old": existing.esn, "new": esn}

                if diff and update_existing:
                    existing.mgmt_ip = ip
                    if model:
                        existing.model = model
                    if version:
                        existing.software_version = version
                    if lsr_id:
                        existing.lsr_id = lsr_id
                    if esn:
                        existing.esn = esn

                    # Re-evaluate province/site/role if unset
                    p, s, r = derive_province_and_site(name)
                    if not existing.province and p:
                        existing.province = p
                    if not existing.site and s:
                        existing.site = s
                    if not existing.role and r:
                        existing.role = r

                    existing.updated_at = datetime.utcnow()
                    updated.append({"name": name, "diff": diff})
                elif diff and not update_existing:
                    unchanged.append(name)
                else:
                    unchanged.append(name)
            else:
                province, site, role = derive_province_and_site(name)
                os_fam = derive_os_family(model, version)

                tags = []
                if province:
                    tags.append(f"province:{province}")
                if role:
                    tags.append(f"role:{role}")
                if os_fam:
                    tags.append(f"vendor-os:{os_fam}")

                new_dev = Device(
                    name=name,
                    mgmt_ip=ip,
                    vendor="huawei",
                    os_family=os_fam,
                    model=model,
                    software_version=version,
                    lsr_id=lsr_id,
                    esn=esn,
                    province=province,
                    site=site,
                    role=role,
                    tags=tags,
                    health_status="unknown",
                    enabled=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(new_dev)
                added.append({
                    "name": name,
                    "mgmt_ip": ip,
                    "province": province,
                    "site": site,
                    "role": role,
                    "os_family": os_fam,
                })

        session.commit()
        return {
            "total": len(routers),
            "added_count": len(added),
            "updated_count": len(updated),
            "unchanged_count": len(unchanged),
            "error_count": len(errors),
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "errors": errors,
        }

    @staticmethod
    def list_devices(
        session: Session,
        province: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None,
        os_family: Optional[str] = None,
        health_status: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        enabled_only: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> Tuple[List[Device], int]:
        """List devices matching search and filter criteria with pagination."""
        query = session.query(Device)
        if enabled_only:
            query = query.filter(Device.enabled == True)

        if province:
            query = query.filter(Device.province == province)
        if site:
            query = query.filter(Device.site == site)
        if role:
            query = query.filter(Device.role == role)
        if os_family:
            query = query.filter(Device.os_family == os_family)
        if health_status:
            query = query.filter(Device.health_status == health_status)

        if search:
            pat = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Device.name.ilike(pat),
                    Device.mgmt_ip.ilike(pat),
                    Device.model.ilike(pat),
                    Device.site.ilike(pat),
                    Device.province.ilike(pat),
                    Device.esn.ilike(pat),
                    Device.lsr_id.ilike(pat),
                )
            )

        all_devices = query.all()
        # In-memory filter for JSON tags if requested
        if tag:
            all_devices = [d for d in all_devices if tag in (d.tags or [])]

        total = len(all_devices)
        paginated = all_devices[offset: offset + limit]
        return paginated, total

    @staticmethod
    def check_health(
        session: Session,
        device: Device,
        probe_ssh: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate and update device health badge.
        Returns diagnostic dictionary and updates device.health_status.
        """
        diag = {
            "device_id": device.id,
            "name": device.name,
            "mgmt_ip": device.mgmt_ip,
            "previous_status": device.health_status,
        }

        # 1. Zabbix monitoring status
        if device.zabbix_hostid:
            new_status = "monitored-ok"
        else:
            new_status = "not-in-zabbix"

        # 2. Optional SSH / TCP Reachability probe
        if probe_ssh and device.mgmt_ip:
            try:
                # Fast TCP connection check to port 22
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                result = sock.connect_ex((device.mgmt_ip, 22))
                sock.close()
                if result == 0:
                    new_status = "ssh-ok" if not device.zabbix_hostid else "monitored-ok"
                    diag["ssh_port_open"] = True
                else:
                    new_status = "unreachable"
                    diag["ssh_port_open"] = False
            except Exception as e:
                new_status = "unreachable"
                diag["ssh_error"] = str(e)

        device.health_status = new_status
        device.last_health_check = datetime.utcnow()
        session.commit()

        diag["health_status"] = new_status
        diag["last_health_check"] = device.last_health_check.isoformat()
        return diag
