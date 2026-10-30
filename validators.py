"""Strict input validation and CLI sanitization for Web-Dash (Step 1.6).

Enforces schema limits and strict regex patterns before any value is processed
or sent to network device CLIs to prevent command injection (F-90, F-09, F-10).
"""
import ipaddress
import re
from typing import Any

# Dangerous delimiters that must NEVER appear in any CLI-bound parameter
DANGEROUS_CLI_CHARS = re.compile(r"[\r\n;|&$`\"'<>\\!]")

# Router Name: 1-64 chars, alphanumeric, dots, underscores, hyphens
ROUTER_NAME_REGEX = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Hostname: standard RFC 1123 hostname (up to 64 chars)
HOSTNAME_REGEX = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")

# Province: 2 to 6 uppercase ASCII letters
PROVINCE_REGEX = re.compile(r"^[A-Z]{2,6}$")

# Interface Name: alphanumeric, slashes, hyphens, colons, dots (1 to 64 chars)
# Matches Huawei interfaces such as: GE0/0/1, GigabitEthernet0/0/1, Eth-Trunk1, Eth-Trunk1.100,
# LoopBack0, Vlanif100, NULL0, Serial1/0/0:0, 100GE1/0/1, XGigabitEthernet0/0/1
INTERFACE_NAME_REGEX = re.compile(r"^[A-Za-z0-9]+(?:[/-][A-Za-z0-9]+)*(?:\.[0-9]+)?(?::[0-9]+)?$")

# VRF Name: 1-31 chars, alphanumeric, dots, underscores, hyphens
VRF_NAME_REGEX = re.compile(r"^[A-Za-z0-9_.-]{1,31}$")


def sanitize_cli_arg(val: Any, field_name: str = "parameter") -> str:
    """Validate that val contains no dangerous CLI delimiters or whitespace/newlines."""
    if not isinstance(val, str):
        raise ValueError(f"{field_name} must be a string")
    if DANGEROUS_CLI_CHARS.search(val):
        raise ValueError(f"Dangerous characters detected in {field_name}")
    clean = val.strip()
    if not clean:
        raise ValueError(f"{field_name} cannot be empty")
    if any(c.isspace() for c in clean):
        raise ValueError(f"Whitespace not allowed in {field_name}")
    return clean


def validate_router_name(name: Any) -> str:
    """Validate router name (<= 64 chars, [A-Za-z0-9._-])."""
    clean = sanitize_cli_arg(name, "router name")
    if len(clean) > 64 or not ROUTER_NAME_REGEX.match(clean):
        raise ValueError("Router name must be 1-64 alphanumeric characters, dots, underscores, or hyphens")
    return clean


def is_valid_hostname(hostname: str) -> bool:
    """Validate RFC 1123 hostname (up to 64 chars, labels separated by dots)."""
    if len(hostname) > 64 or not hostname:
        return False
    if ".." in hostname:
        return False
    labels = hostname.split(".")
    # If 4 numeric parts, it was an attempted IPv4 that failed ipaddress parsing
    if len(labels) == 4 and all(l.isdigit() for l in labels):
        return False
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-") or label.startswith("_") or label.endswith("_"):
            return False
        if not re.match(r"^[A-Za-z0-9_-]+$", label):
            return False
    return True


def validate_host_or_ip(host_or_ip: Any) -> str:
    """Validate IP address (IPv4/IPv6) or valid RFC 1123 hostname."""
    clean = sanitize_cli_arg(host_or_ip, "host or IP")
    # First try parsing as IP
    try:
        ipaddress.ip_address(clean)
        return clean
    except ValueError:
        pass
    # If not IP, check hostname
    if not is_valid_hostname(clean):
        raise ValueError(f"Invalid host or IP address: '{clean}'")
    return clean


def validate_target_ip(ip_str: Any) -> str:
    """Validate IP address or prefix (e.g., 10.0.0.1 or 10.0.0.0/24)."""
    clean = sanitize_cli_arg(ip_str, "target IP")
    base_ip = clean.split("/")[0]
    try:
        ipaddress.ip_address(base_ip)
    except ValueError:
        raise ValueError(f"Invalid target IP address: '{clean}'")
    if "/" in clean:
        try:
            ipaddress.ip_network(clean, strict=False)
        except ValueError:
            raise ValueError(f"Invalid CIDR prefix in target IP: '{clean}'")
    return clean


def validate_interface_name(iface: Any) -> str:
    """Validate interface name against strict Huawei interface pattern."""
    clean = sanitize_cli_arg(iface, "interface name")
    if len(clean) > 64 or not INTERFACE_NAME_REGEX.match(clean):
        raise ValueError(f"Invalid interface name format: '{clean}'")
    return clean


def validate_vrf_name(vrf: Any) -> str:
    """Validate VRF (VPN instance) name."""
    clean = sanitize_cli_arg(vrf, "VRF name")
    if len(clean) > 31 or not VRF_NAME_REGEX.match(clean):
        raise ValueError(f"Invalid VRF name: '{clean}'. Must be 1-31 alphanumeric characters, dots, underscores, or hyphens.")
    return clean


def validate_province(prov: Any) -> str:
    """Validate province code (2-6 uppercase letters)."""
    clean = sanitize_cli_arg(prov, "province")
    upper = clean.upper()
    if not PROVINCE_REGEX.match(upper):
        raise ValueError(f"Invalid province code: '{prov}'. Must be 2-6 uppercase letters.")
    return upper


def validate_age(age_val: Any, age_unit: Any) -> tuple[int, str]:
    """Validate age value (int 1..3650) and age unit ('hours' or 'days')."""
    try:
        val = int(age_val)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid age_value: '{age_val}'. Must be an integer.")
    if val < 1 or val > 3650:
        raise ValueError(f"age_value must be between 1 and 3650, got {val}")
    unit_str = str(age_unit).lower().strip()
    if unit_str not in ("hours", "days"):
        raise ValueError(f"age_unit must be either 'hours' or 'days', got '{age_unit}'")
    return val, unit_str


def validate_timeout(val: Any, default: int = 20, min_val: int = 1, max_val: int = 300) -> int:
    """Validate a timeout integer within min_val..max_val."""
    if val is None:
        return default
    try:
        t = int(val)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid timeout value: '{val}'. Must be an integer.")
    if t < min_val or t > max_val:
        raise ValueError(f"Timeout must be between {min_val} and {max_val} seconds, got {t}")
    return t


def validate_routers_list(routers: Any, max_items: int = 2000) -> list[dict]:
    """Validate routers list: must be a list with 1..max_items entries."""
    if not isinstance(routers, list):
        raise ValueError("routers must be a list")
    if len(routers) == 0:
        raise ValueError("routers list cannot be empty")
    if len(routers) > max_items:
        raise ValueError(f"Too many routers: {len(routers)}. Maximum allowed is {max_items}.")

    clean_list = []
    for idx, r in enumerate(routers):
        if not isinstance(r, dict):
            raise ValueError(f"Router at index {idx} must be an object")
        host = (r.get("host") or r.get("ip") or "").strip()
        name = (r.get("name") or "").strip() or host
        if not host:
            raise ValueError(f"Router at index {idx} is missing 'host' or 'ip'")
        clean_host = validate_host_or_ip(host)
        clean_name = validate_router_name(name) if name else clean_host
        item = {"name": clean_name, "host": clean_host}
        if "ip" in r:
            item["ip"] = clean_host
        clean_list.append(item)
    return clean_list
