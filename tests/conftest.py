"""Pytest fixtures and environment mocks for unit tests."""
import sys
from unittest.mock import MagicMock

# Mock netmiko and paramiko if not installed in the testing environment
if "netmiko" not in sys.modules:
    netmiko_mock = MagicMock()
    sys.modules["netmiko"] = netmiko_mock
if "paramiko" not in sys.modules:
    paramiko_mock = MagicMock()
    sys.modules["paramiko"] = paramiko_mock
