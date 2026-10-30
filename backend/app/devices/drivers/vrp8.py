"""Huawei VRP8 driver (Target Architecture §3 & Step 3.1).

VRP8 (e.g. NE40E/NE8000/NetEngine/CloudEngine) uses candidate + commit semantics
and netmiko device_type 'huawei_vrpv8'.
"""
from backend.app.devices.drivers.base import BaseVRPDriver


class VRP8Driver(BaseVRPDriver):
    """Driver for Huawei VRP8 devices."""
    os_family: str = "vrp8"
    netmiko_device_type: str = "huawei_vrpv8"
    commit_required: bool = True
