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

    def to_dict(self) -> dict:
        meta = self.meta_info if isinstance(self.meta_info, dict) else {}
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "username": meta.get("username", ""),
            "meta": meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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
    software_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lsr_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    site: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    health_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    zabbix_hostid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    grafana_vars: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    credential_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    credential: Mapped[Optional["Credential"]] = relationship("Credential", back_populates="devices")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mgmt_ip": self.mgmt_ip,
            "vendor": self.vendor,
            "os_family": self.os_family,
            "model": self.model,
            "esn": self.esn,
            "software_version": self.software_version,
            "lsr_id": self.lsr_id,
            "role": self.role,
            "site": self.site,
            "province": self.province,
            "tags": self.tags if isinstance(self.tags, list) else [],
            "health_status": self.health_status or "unknown",
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "zabbix_hostid": self.zabbix_hostid,
            "grafana_vars": self.grafana_vars if isinstance(self.grafana_vars, dict) else {},
            "credential_id": self.credential_id,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TargetSet(Base):
    """Saved set of target devices based on filter criteria or explicit selection."""
    __tablename__ = "target_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filter_criteria: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    device_ids: Mapped[List[int]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "filter_criteria": self.filter_criteria if isinstance(self.filter_criteria, dict) else {},
            "device_ids": self.device_ids if isinstance(self.device_ids, list) else [],
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def resolve_devices(self, session) -> List[Device]:
        """Resolve criteria against current active devices."""
        query = session.query(Device).filter(Device.enabled == True)
        crit = self.filter_criteria or {}

        provinces = crit.get("provinces") or ([crit["province"]] if crit.get("province") else None)
        if provinces:
            query = query.filter(Device.province.in_(provinces))

        roles = crit.get("roles") or ([crit["role"]] if crit.get("role") else None)
        if roles:
            query = query.filter(Device.role.in_(roles))

        os_families = crit.get("os_families") or ([crit["os_family"]] if crit.get("os_family") else None)
        if os_families:
            query = query.filter(Device.os_family.in_(os_families))

        sites = crit.get("sites") or ([crit["site"]] if crit.get("site") else None)
        if sites:
            query = query.filter(Device.site.in_(sites))

        models = crit.get("models") or ([crit["model"]] if crit.get("model") else None)
        if models:
            query = query.filter(Device.model.in_(models))

        health_statuses = crit.get("health_statuses") or ([crit["health_status"]] if crit.get("health_status") else None)
        if health_statuses:
            query = query.filter(Device.health_status.in_(health_statuses))

        results = query.all()

        # Tag filtering
        req_tags = set(crit.get("tags") or [])
        if req_tags:
            results = [d for d in results if req_tags.issubset(set(d.tags or []))]

        # Explicitly pinned IDs
        if self.device_ids:
            pinned = (
                session.query(Device)
                .filter(Device.id.in_(self.device_ids), Device.enabled == True)
                .all()
            )
            seen_ids = {d.id for d in results}
            for p in pinned:
                if p.id not in seen_ids:
                    results.append(p)

        return sorted(results, key=lambda d: d.name)


class DeviceLock(Base):
    """Distributed device lock ensuring one active config session per device."""
    __tablename__ = "device_locks"

    device_name: Mapped[str] = mapped_column(String(150), primary_key=True)
    owner_task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

