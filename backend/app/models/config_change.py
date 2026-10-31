"""Configuration snapshot, change request, intake event, and schedule models (Target Architecture §3)."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    BigInteger,
    DateTime,
    Text,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class ConfigSnapshot(Base):
    __tablename__ = "config_snapshots"
    __table_args__ = (
        Index("ix_config_snapshots_device_id", "device_id"),
        Index("ix_config_snapshots_taken_at", "taken_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running | saved
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_encrypted_or_text: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "kind": self.kind,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "job_id": self.job_id,
        }


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        Index("ix_change_requests_status", "status"),
        Index("ix_change_requests_device_id", "device_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    creator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)  # low, medium, high
    plan: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    diff: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="planned", nullable=False
    )  # planned, prechecked, awaiting_approval, applying, verifying, verified, rolled_back, rejected, failed_needs_attention
    precheck_results: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    verification_results: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "device_id": self.device_id,
            "creator_id": self.creator_id,
            "risk_level": self.risk_level,
            "status": self.status,
            "plan": self.plan,
            "diff": self.diff,
            "precheck_results": self.precheck_results,
            "verification_results": self.verification_results,
            "snapshot_id": self.snapshot_id,
            "approver_id": self.approver_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Event(Base):
    """Problem intake and external monitoring event table."""
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_ts", "ts"),
        Index("ix_events_source", "source"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # zabbix, webdash, ssh
    device_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    cron: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SchedulerLease(Base):
    __tablename__ = "scheduler_leases"

    name: Mapped[str] = mapped_column(String(50), primary_key=True, default="scheduler_leader")
    holder_id: Mapped[str] = mapped_column(String(100), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "holder_id": self.holder_id,
            "acquired_at": self.acquired_at.isoformat() if self.acquired_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

