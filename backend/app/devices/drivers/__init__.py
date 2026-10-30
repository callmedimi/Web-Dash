"""Huawei VRP drivers package."""
from typing import Dict, Type
from backend.app.devices.drivers.base import BaseVRPDriver
from backend.app.devices.drivers.vrp5 import VRP5Driver
from backend.app.devices.drivers.vrp8 import VRP8Driver

_DRIVERS: Dict[str, Type[BaseVRPDriver]] = {
    "vrp5": VRP5Driver,
    "vrp8": VRP8Driver,
}


def get_driver(os_family: str) -> BaseVRPDriver:
    """Instantiate appropriate driver for OS family with vrp8 as default."""
    cls = _DRIVERS.get(os_family.lower(), VRP8Driver)
    return cls()
