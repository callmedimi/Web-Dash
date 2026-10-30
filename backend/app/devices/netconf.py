"""NETCONF driver interface stub (Target Architecture §3 & Step 3.6).

Huawei VRP8 supports structured configuration and RPCs via NETCONF/YANG.
This interface stub is prepared for future NETCONF integration and is
disabled by default via settings.ENABLE_NETCONF=False.
"""
from typing import Dict, Any, Optional


class NetconfStubDriver:
    """Stub driver for future Huawei VRP8 NETCONF/YANG operations."""

    def __init__(self, host: str, port: int = 830, username: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.enabled = False

    def get_config(self, source: str = "running", filter_xml: Optional[str] = None) -> Dict[str, Any]:
        """Fetch XML configuration from device datastore."""
        raise NotImplementedError("NETCONF is currently disabled (ENABLE_NETCONF=False).")

    def edit_config(self, target: str = "candidate", config_xml: str = "") -> Dict[str, Any]:
        """Apply structured XML configuration changes to target datastore."""
        raise NotImplementedError("NETCONF is currently disabled (ENABLE_NETCONF=False).")

    def commit(self) -> Dict[str, Any]:
        """Commit candidate configuration."""
        raise NotImplementedError("NETCONF is currently disabled (ENABLE_NETCONF=False).")
