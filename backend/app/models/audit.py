"""Audit Log model (Target Architecture §3)."""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    DateTime,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class AuditLog(Base):
    """Append-only audit log table."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_ts", "ts"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ip: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat(),
            "user_id": self.user_id,
            "ip": self.ip,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
        }
