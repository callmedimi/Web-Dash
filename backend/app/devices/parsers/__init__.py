"""Huawei device parsers package."""
from backend.app.devices.parsers.interface_ref import (
    InterfaceRef,
    extract_interface,
    normalize_interface_name,
)
from backend.app.devices.parsers.alarms import parse_active_alarms
from backend.app.devices.parsers.interface import (
    parse_display_interface,
    parse_interface_config,
)
from backend.app.devices.parsers.license import (
    parse_display_license,
    parse_display_license_verbose,
)
from backend.app.devices.parsers.routing import (
    parse_routing_table,
    parse_bgp_received_routes,
)
from backend.app.devices.parsers.arp_mac import (
    parse_display_arp,
    parse_display_mac,
    normalize_mac,
)
from backend.app.devices.parsers.ptp import parse_display_ptp_all

__all__ = [
    "InterfaceRef",
    "extract_interface",
    "normalize_interface_name",
    "parse_active_alarms",
    "parse_display_interface",
    "parse_interface_config",
    "parse_display_license",
    "parse_display_license_verbose",
    "parse_routing_table",
    "parse_bgp_received_routes",
    "parse_display_arp",
    "parse_display_mac",
    "normalize_mac",
    "parse_display_ptp_all",
]
