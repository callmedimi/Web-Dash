"""Device, Credential, and DeviceLock models (Target Architecture §3 & §5)."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

# DB-agnostic JSON type that maps to JSONB on PostgreSQL
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # ssh_password, ssh_key, etc.
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    meta_info: Mapped[Dict[str, Any]] = mapped_column("meta", JSON_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    devices: Mapped[List["Device"]] = relationship("Device", back_populates="credential")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_mgmt_ip", "mgmt_ip"),
        Index("ix_devices_site", "site"),
        Index("ix_devices_zabbix_hostid", "zabbix_hostid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    mgmt_ip: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor: Mapped[str] = mapped_column(String(50), default="huawei", nullable=False)
    os_family: Mapped[str] = mapped_column(String(20), default="vrp8", nullable=False)  # vrp5, vrp8
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    esn: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    site: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    zabbix_hostid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    grafana_vars: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    credential_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    credential: Mapped[Optional["Credential"]] = relationship("Credential", back_populates="devices")


class DeviceLock(Base):
    """Distributed device lock ensuring one active config session per device."""
    __tablename__ = "device_locks"

    device_name: Mapped[str] = mapped_column(String(150), primary_key=True)
    owner_task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
