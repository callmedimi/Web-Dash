"""Configuration snapshot, change request, intake event, and schedule models (Target Architecture §3)."""
import uuid
from datetime import datetime
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
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running | saved
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_encrypted_or_text: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        Index("ix_change_requests_status", "status"),
        Index("ix_change_requests_device_id", "device_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    diff: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="proposed", nullable=False
    )  # proposed, approved, applied, verified, rolled_back, rejected
    approver_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


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
