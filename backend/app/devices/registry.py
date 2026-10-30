"""Device Command Registry (Target Architecture §3 & Step 3.1).

Features reference device commands by logical name, never by raw string.
Each command specifies OS-family specific syntax, timeout, read-only flag,
and whether it has been verified on target hardware.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any


@dataclass
class DeviceCommand:
    """Represents a declared network device CLI command."""
    name: str
    family_commands: Dict[str, str] = field(default_factory=dict)
    parser: Optional[str] = None
    timeout: int = 30
    read_only: bool = True
    verified: bool = True
    description: str = ""

    def get_template(self, os_family: str) -> str:
        """Get command template for specified OS family with fallback."""
        if os_family in self.family_commands:
            return self.family_commands[os_family]
        if "default" in self.family_commands:
            return self.family_commands["default"]
        if "vrp8" in self.family_commands:
            return self.family_commands["vrp8"]
        if "vrp5" in self.family_commands:
            return self.family_commands["vrp5"]
        raise KeyError(f"No command template for OS family '{os_family}' in command '{self.name}'")

    def format(self, os_family: str, **vars: Any) -> str:
        """Render command string with variables."""
        template = self.get_template(os_family)
        return template.format(**vars)


class CommandRegistry:
    """Registry holding all approved CLI commands."""

    def __init__(self):
        self._commands: Dict[str, DeviceCommand] = {}

    def register(self, command: DeviceCommand) -> None:
        """Register a new device command."""
        self._commands[command.name] = command

    def get(self, name: str) -> DeviceCommand:
        """Retrieve a registered command by logical name."""
        if name not in self._commands:
            raise KeyError(f"Command '{name}' not found in registry")
        return self._commands[name]

    def has(self, name: str) -> bool:
        """Check if command is registered."""
        return name in self._commands

    def get_command_string(self, name: str, os_family: str = "vrp8", **vars: Any) -> str:
        """Convenience method to retrieve and format command in one call."""
        cmd = self.get(name)
        return cmd.format(os_family, **vars)

    def is_read_only(self, name: str) -> bool:
        """Check if command is declared read-only."""
        return self.get(name).read_only

    def list_commands(self) -> List[DeviceCommand]:
        """List all registered commands."""
        return list(self._commands.values())


# Global default registry with standard Huawei VRP commands
default_registry = CommandRegistry()

_STANDARD_COMMANDS = [
    DeviceCommand(
        name="display_version",
        family_commands={"vrp5": "display version", "vrp8": "display version"},
        parser="version",
        timeout=15,
        read_only=True,
        verified=True,
        description="Display system version and patch information",
    ),
    DeviceCommand(
        name="display_alarm_active",
        family_commands={"vrp5": "display alarm active", "vrp8": "display alarm active"},
        parser="alarm_active",
        timeout=45,
        read_only=True,
        verified=True,
        description="Display all active alarms on the router",
    ),
    DeviceCommand(
        name="display_interface",
        family_commands={
            "vrp5": "display interface {interface}",
            "vrp8": "display interface {interface}",
        },
        parser="interface_brief",
        timeout=20,
        read_only=True,
        verified=True,
        description="Display interface status and operational state",
    ),
    DeviceCommand(
        name="display_interface_description",
        family_commands={
            "vrp5": "display interface description",
            "vrp8": "display interface description",
        },
        parser="interface_description",
        timeout=30,
        read_only=True,
        verified=True,
        description="Display interface descriptions",
    ),
    DeviceCommand(
        name="display_current_config_interface",
        family_commands={
            "vrp5": "display current-configuration interface {interface}",
            "vrp8": "display current-configuration interface {interface}",
        },
        parser="interface_config",
        timeout=25,
        read_only=True,
        verified=True,
        description="Display running configuration of a specific interface",
    ),
    DeviceCommand(
        name="display_license",
        family_commands={"vrp5": "display license", "vrp8": "display license"},
        parser="license",
        timeout=30,
        read_only=True,
        verified=True,
        description="Display license summary and activated items",
    ),
    DeviceCommand(
        name="display_license_verbose",
        family_commands={"vrp5": "display license verbose", "vrp8": "display license verbose"},
        parser="license_verbose",
        timeout=45,
        read_only=True,
        verified=True,
        description="Display verbose license item breakdown",
    ),
    DeviceCommand(
        name="display_ip_routing_table_vpn",
        family_commands={
            "vrp5": "display ip routing-table vpn-instance {vrf} {prefix}",
            "vrp8": "display ip routing-table vpn-instance {vrf} {prefix}",
        },
        parser="routing_table",
        timeout=25,
        read_only=True,
        verified=True,
        description="Display VRF routing table entry for destination prefix",
    ),
    DeviceCommand(
        name="display_bgp_vpnv4_routing_table",
        family_commands={
            "vrp5": "display bgp vpnv4 vpn-instance {vrf} routing-table {prefix}",
            "vrp8": "display bgp vpnv4 vpn-instance {vrf} routing-table {prefix}",
        },
        parser="bgp_vpnv4",
        timeout=25,
        read_only=True,
        verified=True,
        description="Display BGP VPNv4 routing details for destination prefix",
    ),
    DeviceCommand(
        name="display_arp",
        family_commands={"vrp5": "display arp", "vrp8": "display arp"},
        parser="arp",
        timeout=60,
        read_only=True,
        verified=True,
        description="Display ARP table entries",
    ),
    DeviceCommand(
        name="display_mac_address",
        family_commands={"vrp5": "display mac-address", "vrp8": "display mac-address"},
        parser="mac_address",
        timeout=60,
        read_only=True,
        verified=True,
        description="Display MAC address forwarding table",
    ),
    DeviceCommand(
        name="display_ptp_all",
        family_commands={"vrp5": "display ptp all", "vrp8": "display ptp all"},
        parser="ptp_all",
        timeout=30,
        read_only=True,
        verified=True,
        description="Display IEEE 1588 PTP protocol status and interface states",
    ),
    DeviceCommand(
        name="display_device",
        family_commands={"vrp5": "display device", "vrp8": "display device"},
        parser="device_chassis",
        timeout=20,
        read_only=True,
        verified=True,
        description="Display hardware board and slot statuses",
    ),
    DeviceCommand(
        name="display_cpu_usage",
        family_commands={"vrp5": "display cpu-usage", "vrp8": "display cpu-usage"},
        parser="cpu_usage",
        timeout=15,
        read_only=True,
        verified=True,
        description="Display CPU utilization",
    ),
    DeviceCommand(
        name="display_memory_usage",
        family_commands={"vrp5": "display memory-usage", "vrp8": "display memory-usage"},
        parser="memory_usage",
        timeout=15,
        read_only=True,
        verified=True,
        description="Display memory utilization",
    ),
    DeviceCommand(
        name="display_temperature_all",
        family_commands={"vrp5": "display temperature all", "vrp8": "display temperature all"},
        parser="temperature",
        timeout=15,
        read_only=True,
        verified=True,
        description="Display board and sensor temperatures",
    ),
    DeviceCommand(
        name="display_optical_module",
        family_commands={
            "vrp5": "display optical-module",
            "vrp8": "display optical-module",
        },
        parser="optical_module",
        timeout=30,
        read_only=True,
        verified=True,
        description="Display transceiver DOM info",
    ),
    DeviceCommand(
        name="commit",
        family_commands={"vrp8": "commit"},
        parser=None,
        timeout=30,
        read_only=False,
        verified=True,
        description="Commit candidate configuration on VRP8",
    ),
    DeviceCommand(
        name="rollback",
        family_commands={"vrp8": "rollback configuration to file {file}"},
        parser=None,
        timeout=60,
        read_only=False,
        verified=False,  # Unverified until tested on physical lab gear (Step 3.1 spec)
        description="Rollback configuration to specified backup file",
    ),
]

for _cmd in _STANDARD_COMMANDS:
    default_registry.register(_cmd)
