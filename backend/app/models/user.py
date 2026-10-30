"""User and Permission models (Target Architecture §3)."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="operator", nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def has_permission(self, feature: str) -> bool:
        if self.role == "god":
            return True
        for p in self.permissions:
            if p.feature == feature:
                return p.granted
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "display_name": self.display_name or self.username,
            "is_active": self.is_active,
            "must_change_password": self.must_change_password,
            "failed_logins": self.failed_logins,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "features": [p.feature for p in self.permissions if p.granted],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "feature", name="uq_user_feature"),
        Index("ix_permissions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="permissions")
