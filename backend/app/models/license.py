"""License models: records and renewal reports (Phase 5 Step 5.4)."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LicenseRecord(Base):
    """Current fleet license state per router."""
    __tablename__ = "license_records"
    __table_args__ = (
        Index("ix_license_records_device_id", "device_id"),
        Index("ix_license_records_alert_level", "alert_level"),
        Index("ix_license_records_days_to_expiry", "days_to_expiry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    product_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    product_version: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    license_state: Mapped[str] = mapped_column(String(50), default="Unknown", nullable=False)
    active_license: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    license_serial_no: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    esn: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    days_to_expiry: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expiry_date: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_level: Mapped[str] = mapped_column(String(50), default="OK", nullable=False)  # OK, WARN_90, WARN_60, WARN_30, CRITICAL_7, EXPIRED
    features: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    items: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    items_used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    device: Mapped["Device"] = relationship("Device", backref="license_record")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device.name if self.device else None,
            "mgmt_ip": self.device.mgmt_ip if self.device else None,
            "province": self.device.province if self.device else None,
            "site": self.device.site if self.device else None,
            "product_name": self.product_name,
            "product_version": self.product_version,
            "license_state": self.license_state,
            "active_license": self.active_license,
            "license_serial_no": self.license_serial_no,
            "esn": self.esn,
            "days_to_expiry": self.days_to_expiry,
            "expiry_date": self.expiry_date,
            "is_expired": self.is_expired,
            "alert_level": self.alert_level,
            "features_count": len(self.features) if isinstance(self.features, list) else 0,
            "items_used_count": self.items_used_count,
            "items_total_count": self.items_total_count,
            "features": self.features if isinstance(self.features, list) else [],
            "items": self.items if isinstance(self.items, list) else [],
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LicenseRenewalReport(Base):
    """Archived license renewal reports."""
    __tablename__ = "license_renewal_reports"
    __table_args__ = (
        Index("ix_license_renewals_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False)
    csv_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    report_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "csv_file": self.csv_file,
            "report_data": self.report_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
