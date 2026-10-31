"""API Token model for programmatic authentication (Target Architecture §3 & Step 5.14)."""
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class ApiToken(Base):
    """Secure, hashed API tokens with expiration and scopes."""
    __tablename__ = "api_tokens"
    __table_args__ = (
        Index("ix_api_tokens_token_hash", "token_hash"),
        Index("ix_api_tokens_user_id", "user_id"),
        Index("ix_api_tokens_revoked", "revoked"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # SHA-256
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "wbd_abc123..."
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scopes: Mapped[List[str]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", lazy="selectin")

    def is_active(self) -> bool:
        """Return True if token is not revoked and not expired."""
        if self.revoked:
            return False
        if self.expires_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if self.expires_at < now:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "token_prefix": self.token_prefix,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "scopes": self.scopes if isinstance(self.scopes, list) else [],
            "revoked": self.revoked,
            "is_active": self.is_active(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }
