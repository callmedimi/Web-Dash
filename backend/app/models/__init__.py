"""SQLAlchemy Models Registry."""
from backend.app.db.base import Base
from backend.app.models.user import User, Permission
from backend.app.models.device import Device, Credential, DeviceLock, TargetSet
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.models.audit import AuditLog
from backend.app.models.config_change import (
    ConfigSnapshot,
    ChangeRequest,
    Event,
    Schedule,
)
from backend.app.models.arp_mac import (
    ArpMacRecord,
    ArpMacSnapshot,
    ArpMacHistory,
    SiteInventory,
)
from backend.app.models.telemetry_cache import ZabbixInventoryCache
from backend.app.models.license import LicenseRenewalReport, LicenseRecord
from backend.app.models.alarm import AlarmFilter
from backend.app.models.down_link import DownLinkReport
from backend.app.models.api_token import ApiToken

__all__ = [
    "Base",
    "User",
    "Permission",
    "ApiToken",
    "Device",
    "Credential",
    "DeviceLock",
    "TargetSet",
    "AlarmFilter",
    "DownLinkReport",
    "Job",
    "JobTask",
    "JobEvent",
    "AuditLog",
    "ConfigSnapshot",
    "ChangeRequest",
    "Event",
    "Schedule",
    "ArpMacRecord",
    "ArpMacSnapshot",
    "ArpMacHistory",
    "SiteInventory",
    "ZabbixInventoryCache",
    "LicenseRenewalReport",
    "LicenseRecord",
]



