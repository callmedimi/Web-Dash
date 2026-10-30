"""Network device abstraction layer (Target Architecture §3)."""
from backend.app.devices.errors import (
    DeviceError,
    ConnectTimeout,
    AuthFailed,
    CommandTimeout,
    ViewError,
    ParseError,
    DeviceLocked,
    ConfigRejected,
    check_vrp_banner_errors,
    map_netmiko_exception,
)
from backend.app.devices.registry import (
    DeviceCommand,
    CommandRegistry,
    default_registry,
)
from backend.app.devices.drivers import (
    BaseVRPDriver,
    VRP5Driver,
    VRP8Driver,
    get_driver,
)
from backend.app.devices.session import DeviceSession, redact_sensitive_cli, parse_vrp_version
from backend.app.devices.pool import (
    DeviceCircuitBreaker,
    device_breaker,
    SiteRateLimiter,
    site_limiter,
    create_device_session,
)

__all__ = [
    "DeviceError",
    "ConnectTimeout",
    "AuthFailed",
    "CommandTimeout",
    "ViewError",
    "ParseError",
    "DeviceLocked",
    "ConfigRejected",
    "check_vrp_banner_errors",
    "map_netmiko_exception",
    "DeviceCommand",
    "CommandRegistry",
    "default_registry",
    "BaseVRPDriver",
    "VRP5Driver",
    "VRP8Driver",
    "get_driver",
    "DeviceSession",
    "redact_sensitive_cli",
    "parse_vrp_version",
    "DeviceCircuitBreaker",
    "device_breaker",
    "SiteRateLimiter",
    "site_limiter",
    "create_device_session",
]
