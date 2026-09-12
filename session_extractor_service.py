import csv
import io
import os
import re
import zipfile
from datetime import datetime


def sanitize_filename(name: str) -> str:
    """Replace invalid filename characters with underscores."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name)).strip()


def make_zip_entry_path(subnet_path: str, ne_name: str) -> str:
    """
    Convert 'ROOT/IPBH/Hormozgan' and 'Router1' into a safe zip entry path like:
    'IPBH/Hormozgan/Router1.ini'
    """
    parts = []
    if subnet_path and str(subnet_path).strip() != 'ROOT':
        raw_parts = str(subnet_path).split('/')
        if raw_parts and raw_parts[0] == 'ROOT':
            raw_parts = raw_parts[1:]
        parts = [sanitize_filename(p) for p in raw_parts if p]

    safe_name = sanitize_filename(ne_name) or "unnamed_device"
    parts.append(f"{safe_name}.ini")
    return "/".join(parts)


def parse_session_csv(file_content_bytes: bytes) -> tuple[list[dict], list[dict], str | None]:
    """
    Parses CSV containing NE Name, NE IP Address, Subnet Path.
    Returns (routers, subnets_summary, error_message).
    """
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
        if "ne name" in clean_l:
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
        if c_clean == "ne name" or c_clean == "nename" or "ne name" in c_clean:
            ne_name_col = col
        elif "ip address" in c_clean or c_clean == "ne ip" or c_clean == "ip":
            ne_ip_col = col
        elif "subnet path" in c_clean or c_clean == "subnet":
            subnet_path_col = col

    if not ne_name_col or not ne_ip_col:
        return [], [], f"CSV missing required columns ('NE Name', 'NE IP Address'). Found: {reader.fieldnames}"

    routers = []
    subnet_counts: dict[str, int] = {}

    for row in reader:
        name = (row.get(ne_name_col) or "").strip()
        ip = (row.get(ne_ip_col) or "").strip()
        subnet = (row.get(subnet_path_col) or "").strip() if subnet_path_col else "ROOT"
        if not subnet:
            subnet = "ROOT"

        if not name or not ip:
            continue

        routers.append({
            "name": name,
            "ip": ip,
            "subnet_path": subnet,
        })
        subnet_counts[subnet] = subnet_counts.get(subnet, 0) + 1

    if not routers:
        return [], [], "No valid records with both NE Name and NE IP Address found."

    subnets_summary = [
        {"path": path, "count": count}
        for path, count in sorted(subnet_counts.items(), key=lambda x: x[0].lower())
    ]

    return routers, subnets_summary, None


def build_securecrt_ini(ip_address: str, username: str = "") -> str:
    """Build SecureCRT SSH2 session .ini configuration content with CRLF line endings."""
    lines = [
        f'S:"Hostname"={ip_address}',
        'S:"Protocol Name"=SSH2',
        'D:"[SSH2] Port"=00000016',
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
        f'S:"Username"={username}',
        '',
    ]
    return '\r\n'.join(lines)


def generate_sessions_zip(routers: list[dict], selected_subnets: list[str] | set[str] | None = None, username: str = "") -> io.BytesIO:
    """Creates an in-memory zip archive containing SecureCRT session .ini files organized by subnet path."""
    if selected_subnets is not None:
        subnet_set = set(selected_subnets)
        filtered = [r for r in routers if r["subnet_path"] in subnet_set]
    else:
        filtered = routers

    mem = io.BytesIO()
    seen_paths: set[str] = set()

    with zipfile.ZipFile(mem, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for r in filtered:
            ne_name = r["name"]
            ip_address = r["ip"]
            subnet_path = r["subnet_path"]

            zip_entry = make_zip_entry_path(subnet_path, ne_name)
            if zip_entry in seen_paths:
                zip_entry = make_zip_entry_path(subnet_path, f"{ne_name}_{ip_address}")
                if zip_entry in seen_paths:
                    counter = 2
                    base_entry = zip_entry[:-4]
                    while f"{base_entry}_{counter}.ini" in seen_paths:
                        counter += 1
                    zip_entry = f"{base_entry}_{counter}.ini"

            seen_paths.add(zip_entry)
            ini_content = build_securecrt_ini(ip_address, username)
            zf.writestr(zip_entry, ini_content)

    mem.seek(0)
    return mem
