"""Zabbix inventory cache model (storing 500+ items per router)."""
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


class ZabbixInventoryCache(Base):
    """Local cache of Zabbix routers, interfaces, and metric items."""
    __tablename__ = "zabbix_inventory_cache"
    __table_args__ = (
        Index("ix_zabbix_cache_name", "name"),
        Index("ix_zabbix_cache_host_ip", "host_ip"),
        Index("ix_zabbix_cache_group_name", "group_name"),
    )

    hostid: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    host_ip: Mapped[str] = mapped_column(String(50), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    interfaces: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    items: Mapped[List[Dict[str, Any]]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "hostid": self.hostid,
            "name": self.name,
            "host": self.host_ip,
            "group_name": self.group_name,
            "interfaces": self.interfaces,
            "items": self.items,
            "updated_at": self.updated_at.isoformat(),
        }
