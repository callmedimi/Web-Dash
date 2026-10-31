"""DownLinkReport model for historical reporting and trend comparison (Step 5.3)."""
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class DownLinkReport(Base):
    """Persisted snapshot of a down-links scan for historical comparison and analytics."""
    __tablename__ = "down_link_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    target_set_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_down: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    service_down: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    noconf_down: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    noconf_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    trunk_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    analytics: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self, include_details: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "job_id": self.job_id,
            "province": self.province,
            "target_set_name": self.target_set_name,
            "total_down": self.total_down,
            "service_down": self.service_down,
            "noconf_down": self.noconf_down,
            "analytics": self.analytics if isinstance(self.analytics, dict) else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_details:
            data["report_data"] = self.report_data if isinstance(self.report_data, list) else []
            data["noconf_data"] = self.noconf_data if isinstance(self.noconf_data, list) else []
            data["trunk_data"] = self.trunk_data if isinstance(self.trunk_data, list) else []
        return data
