"""Typed exception hierarchy for network device interactions (Target Architecture §3)."""
import re
from typing import Optional


class DeviceError(Exception):
    """Base exception for all device operations."""
    def __init__(self, message: str, device_name: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.device_name = device_name

    def __str__(self) -> str:
        if self.device_name:
            return f"[{self.device_name}] {self.message}"
        return self.message


class ConnectTimeout(DeviceError):
    """Raised when connection to device times out."""
    pass


class AuthFailed(DeviceError):
    """Raised when authentication (SSH username/password/key) fails."""
    pass


class CommandTimeout(DeviceError):
    """Raised when a command execution exceeds timeout."""
    pass


class ViewError(DeviceError):
    """Raised when failing to enter or exit a CLI view (e.g., system-view)."""
    pass


class ParseError(DeviceError):
    """Raised when output parser fails to extract required structured data."""
    def __init__(self, message: str, raw_output: str = "", device_name: Optional[str] = None):
        super().__init__(message, device_name=device_name)
        self.raw_output = raw_output


class DeviceLocked(DeviceError):
    """Raised when a device is currently locked by another job/task."""
    pass


class ConfigRejected(DeviceError):
    """Raised when a device rejects a configuration command (e.g. Error: banner)."""
    def __init__(self, message: str, command: str = "", error_banner: str = "", device_name: Optional[str] = None):
        super().__init__(message, device_name=device_name)
        self.command = command
        self.error_banner = error_banner


# Huawei VRP common error banner patterns
VRP_ERROR_PATTERNS = [
    re.compile(r"Error:\s*(.*)", re.IGNORECASE),
    re.compile(r"Unrecognized command\s*(.*)", re.IGNORECASE),
    re.compile(r"Incomplete command\s*(.*)", re.IGNORECASE),
    re.compile(r"Wrong parameter\s*(.*)", re.IGNORECASE),
    re.compile(r"Ambiguous command\s*(.*)", re.IGNORECASE),
]


def check_vrp_banner_errors(output: str) -> Optional[str]:
    """Inspect CLI output for Huawei VRP error banners. Returns matched error line if found."""
    if not output:
        return None
    for line in output.splitlines():
        line_clean = line.strip()
        for pat in VRP_ERROR_PATTERNS:
            m = pat.search(line_clean)
            if m:
                return line_clean
    return None


def map_netmiko_exception(exc: Exception, device_name: Optional[str] = None) -> DeviceError:
    """Map Netmiko/Paramiko/socket exceptions to typed DeviceError hierarchy."""
    if isinstance(exc, DeviceError):
        if device_name and not exc.device_name:
            exc.device_name = device_name
        return exc

    exc_type = type(exc).__name__
    msg = str(exc)

    if "Authentication" in exc_type or "Auth" in exc_type:
        return AuthFailed(f"Authentication failed: {msg}", device_name=device_name)
    if "Timeout" in exc_type or "timed out" in msg.lower():
        if "command" in msg.lower() or "read" in msg.lower():
            return CommandTimeout(f"Command execution timed out: {msg}", device_name=device_name)
        return ConnectTimeout(f"Connection timed out: {msg}", device_name=device_name)
    if "ConnectionRefused" in exc_type or "refused" in msg.lower():
        return ConnectTimeout(f"Connection refused: {msg}", device_name=device_name)

    return DeviceError(f"Unexpected device error ({exc_type}): {msg}", device_name=device_name)
