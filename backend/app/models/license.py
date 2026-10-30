"""License renewal report model (replacing license_renewals.json)."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    String,
    DateTime,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "csv_file": self.csv_file,
            "report_data": self.report_data,
            "created_at": self.created_at.isoformat(),
        }
