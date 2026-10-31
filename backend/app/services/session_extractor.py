"""SecureCRT & SSH Session Extractor Service (Phase 5 Step 5.8).

Features:
- Secure generation of SecureCRT SSH2 session (.ini) archives.
- Strict security verification: NO passwords embedded in generated files (prompt on connect).
- Multiple hierarchy presets:
    - 'subnet_path': NMS subnet folder structure (e.g. IPBH/Hormozgan/Router1.ini)
    - 'province_role': Hierarchical by province and role (e.g. TEH/AGG/TEH-AGG01.ini)
    - 'province': Grouped by province (e.g. TEH/TEH-AGG01.ini)
    - 'role': Grouped by role (e.g. AGG/TEH-AGG01.ini)
    - 'flat': Single root directory
- Dual input mode: Parse from NMS export CSV, or directly extract from Device inventory.
"""
from __future__ import annotations
import csv
import io
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from backend.app.models.device import Device
from backend.app.services.inventory import derive_province_and_site


def sanitize_filename(name: str) -> str:
    """Replace invalid path/filename characters with underscores."""
    if not name:
        return "unnamed"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name)).strip()


def derive_role_from_name(ne_name: str) -> str:
    """Derive router network role (PE, AGG, CORE, ACC, CE, RR) from hostname."""
    upper = (ne_name or "").upper()
    if "-AGG" in upper or "_AGG" in upper or "AGG" in upper:
        return "AGG"
    if "-PE" in upper or "_PE" in upper or "PE" in upper:
        return "PE"
    if "-CORE" in upper or "_CORE" in upper or "CORE" in upper or "-CX" in upper:
        return "CORE"
    if "-RR" in upper or "_RR" in upper:
        return "RR"
    if "-CE" in upper or "_CE" in upper:
        return "CE"
    if "-ACC" in upper or "_ACC" in upper:
        return "ACC"
    return "OTHER"


def make_zip_entry_path(folder_path: str, ne_name: str) -> str:
    """Convert folder path and router name into a sanitized zip entry path."""
    parts = []
    if folder_path and str(folder_path).strip() not in ('ROOT', '', '/'):
        raw_parts = str(folder_path).replace('\\', '/').split('/')
        if raw_parts and raw_parts[0] == 'ROOT':
            raw_parts = raw_parts[1:]
        parts = [sanitize_filename(p) for p in raw_parts if p]

    safe_name = sanitize_filename(ne_name) or "unnamed_device"
    parts.append(f"{safe_name}.ini")
    return "/".join(parts)


def build_securecrt_ini(ip_address: str, username: str = "", port: int = 22) -> str:
    """Build SecureCRT SSH2 session .ini configuration content with CRLF line endings.
    
    SECURITY MANDATE:
    Never include or embed passwords in generated session files.
    'Session Password Saved' is explicitly set to 0 to require interactive prompt or key.
    """
    safe_user = str(username or "").strip()
    safe_port_hex = f"{port:08x}"

    lines = [
        f'S:"Hostname"={ip_address}',
        'S:"Protocol Name"=SSH2',
        f'D:"[SSH2] Port"={safe_port_hex}',
        'D:"Is Session"=00000001',
        'S:"Emulation"=Linux',
        'D:"Rows"=0000002a',
        'D:"Cols"=00000078',
        'D:"Request pty"=00000001',
        'D:"Request Shell"=00000001',
        'D:"Send Initial Carriage Return"=00000001',
        'D:"Idle Timeout"=0000001e',
        'S:"SSH2 Authentications V2"=password,publickey,keyboard-interactive',
        'S:"Key Exchange Algorithms"=curve25519-sha256,ecdh-sha2-nistp256,diffie-hellman-group14-sha256',
        'S:"Cipher List"=aes256-ctr,aes192-ctr,aes128-ctr,chacha20-poly1305@openssh.com',
        'S:"MAC List"=hmac-sha2-512,hmac-sha2-256',
        'D:"Enable Agent Forwarding"=00000000',
        'D:"Forward X11"=00000000',
        'D:"Session Password Saved"=00000000',
        f'S:"Username"={safe_user}',
        '',
    ]
    return '\r\n'.join(lines)


class SessionExtractorService:
    """Service to parse routers and generate SecureCRT session tree ZIP archives."""

    PRESETS = ["subnet_path", "province_role", "province", "role", "flat"]

    @classmethod
    def parse_csv(cls, file_content_bytes: bytes) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], Optional[str]]:
        """Parse uploaded CSV containing NE Name, NE IP Address, and optional Subnet Path."""
        try:
            text = file_content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = file_content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = file_content_bytes.decode("latin-1")

        lines = text.splitlines()

        def _clean(line: str) -> str:
            return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line)

        header_idx = -1
        for i, line in enumerate(lines):
            clean_l = _clean(line).strip().lower()
            if "ne name" in clean_l or clean_l.startswith("name,") or clean_l.startswith("ne,"):
                header_idx = i
                break

        if header_idx == -1:
            if len(lines) > 3 and "ip" in lines[3].lower():
                header_idx = 3
            elif len(lines) > 0:
                header_idx = 0
            else:
                return [], [], "Empty file or unable to find header row."

        cleaned_lines = [_clean(l) for l in lines[header_idx:] if _clean(l).strip()]
        if not cleaned_lines:
            return [], [], "No CSV data rows found."

        reader = csv.DictReader(cleaned_lines)
        if not reader.fieldnames:
            return [], [], "Could not read CSV column headers."

        ne_name_col = None
        ne_ip_col = None
        subnet_path_col = None

        for col in reader.fieldnames:
            c_clean = col.strip().lower()
            if c_clean in ("ne name", "nename", "name", "ne"):
                ne_name_col = col
            elif "ip" in c_clean:
                ne_ip_col = col
            elif "subnet" in c_clean or "path" in c_clean:
                subnet_path_col = col

        if not ne_name_col or not ne_ip_col:
            return [], [], f"CSV missing required columns ('NE Name', 'NE IP Address'). Found: {reader.fieldnames}"

        routers = []
        subnet_counts: Dict[str, int] = {}

        for row in reader:
            name = (row.get(ne_name_col) or "").strip()
            ip = (row.get(ne_ip_col) or "").strip()
            subnet = (row.get(subnet_path_col) or "").strip() if subnet_path_col else "ROOT"
            if not name or not ip:
                continue

            province, site, derived_role = derive_province_and_site(name)
            role = derived_role or derive_role_from_name(name)

            routers.append({
                "name": name,
                "ip": ip,
                "subnet_path": subnet,
                "province": province,
                "site": site,
                "role": role,
            })
            subnet_counts[subnet] = subnet_counts.get(subnet, 0) + 1

        if not routers:
            return [], [], "No valid records with both NE Name and NE IP Address found."

        subnets_summary = [
            {"path": path, "count": count}
            for path, count in sorted(subnet_counts.items(), key=lambda x: x[0].lower())
        ]

        return routers, subnets_summary, None

    @classmethod
    def resolve_entry_path(cls, router: Dict[str, Any], preset: str = "subnet_path") -> str:
        """Resolve directory path within ZIP file based on chosen organizational preset."""
        ne_name = router.get("name", "unnamed")
        province = router.get("province") or derive_province_and_site(ne_name)[0] or "TEH"
        role = router.get("role") or derive_role_from_name(ne_name) or "PE"
        subnet = router.get("subnet_path", "ROOT")

        if preset == "province_role":
            folder = f"{province}/{role}"
        elif preset == "province":
            folder = province
        elif preset == "role":
            folder = role
        elif preset == "flat":
            folder = ""
        else:
            # Default: subnet_path
            folder = subnet

        return make_zip_entry_path(folder, ne_name)

    @classmethod
    def generate_zip(
        cls,
        routers: List[Dict[str, Any]],
        preset: str = "subnet_path",
        selected_subnets: Optional[List[str]] = None,
        username: str = "",
    ) -> io.BytesIO:
        """Create an in-memory ZIP containing SecureCRT session .ini files."""
        if selected_subnets is not None and preset == "subnet_path":
            subnet_set = set(selected_subnets)
            filtered = [r for r in routers if r.get("subnet_path") in subnet_set]
        else:
            filtered = routers

        mem = io.BytesIO()
        seen_paths: Set[str] = set()

        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r in filtered:
                ne_name = r.get("name", "")
                ip_address = r.get("ip", "")
                if not ip_address:
                    continue

                zip_entry = cls.resolve_entry_path(r, preset=preset)
                if zip_entry in seen_paths:
                    base_no_ext = zip_entry[:-4]
                    counter = 2
                    candidate = f"{base_no_ext}_{ip_address}.ini"
                    if candidate in seen_paths:
                        while f"{base_no_ext}_{counter}.ini" in seen_paths:
                            counter += 1
                        candidate = f"{base_no_ext}_{counter}.ini"
                    zip_entry = candidate

                seen_paths.add(zip_entry)
                ini_content = build_securecrt_ini(ip_address=ip_address, username=username)
                zf.writestr(zip_entry, ini_content)

        mem.seek(0)
        return mem

    @classmethod
    def extract_from_inventory(
        cls,
        db_session: Session,
        preset: str = "province_role",
        filter_province: Optional[str] = None,
        filter_role: Optional[str] = None,
        username: str = "",
    ) -> Tuple[List[Dict[str, Any]], io.BytesIO]:
        """Extract routers directly from the Device inventory database without requiring a CSV upload."""
        query = db_session.query(Device).filter(Device.enabled.is_(True))

        if filter_province:
            query = query.filter(Device.province.ilike(filter_province.strip()))
        if filter_role:
            query = query.filter(Device.role.ilike(filter_role.strip()))

        devices = query.order_by(Device.province.asc(), Device.name.asc()).all()

        routers = []
        for d in devices:
            prov = d.province or derive_province_and_site(d.name)[0]
            role = d.role or derive_role_from_name(d.name)
            routers.append({
                "name": d.name,
                "ip": d.mgmt_ip,
                "subnet_path": f"{prov}/{role}",
                "province": prov,
                "site": d.site or "",
                "role": role,
            })

        zip_buffer = cls.generate_zip(
            routers=routers,
            preset=preset,
            username=username,
        )
        return routers, zip_buffer
