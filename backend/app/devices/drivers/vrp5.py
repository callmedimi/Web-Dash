"""Huawei VRP5 driver (Target Architecture §3 & Step 3.1).

VRP5 (e.g. older NE20/ATN/CX600) uses immediate apply config semantics
and netmiko device_type 'huawei'.
"""
from backend.app.devices.drivers.base import BaseVRPDriver


class VRP5Driver(BaseVRPDriver):
    """Driver for Huawei VRP5 devices."""
    os_family: str = "vrp5"
    netmiko_device_type: str = "huawei"
    commit_required: bool = False
