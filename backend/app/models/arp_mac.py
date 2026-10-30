"""ARP/MAC current records, historical snapshots, and Unified Sites models."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ArpMacRecord(Base):
    """Current live state of ARP and MAC table (20,000+ records)."""
    __tablename__ = "arp_mac_records"
    __table_args__ = (
        Index("ix_arp_mac_arp_ip", "arp_ip"),
        Index("ix_arp_mac_arp_mac", "arp_mac"),
        Index("ix_arp_mac_ne_name", "ne_name"),
        Index("ix_arp_mac_lookup", "arp_ip", "arp_mac"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    ne_name: Mapped[str] = mapped_column(String(150), nullable=False)
    ne_ip: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    arp_ip: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    arp_mac: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    vlan: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vrf: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    arp_interface: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    mac_port: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "ne_name": self.ne_name,
            "ne_ip": self.ne_ip,
            "arp_ip": self.arp_ip,
            "arp_mac": self.arp_mac,
            "vlan": self.vlan or "",
            "vrf": self.vrf or "",
            "arp_interface": self.arp_interface or "",
            "mac_port": self.mac_port or "",
            "collected_at": self.collected_at.isoformat() if self.collected_at else "",
        }


class ArpMacSnapshot(Base):
    """Historical archive header for each ARP/MAC collector scan."""
    __tablename__ = "arp_mac_snapshots"
    __table_args__ = (
        Index("ix_arp_mac_snapshots_scanned_at", "scanned_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    scanned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    total_routers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    archive_csv_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    history_records: Mapped[List["ArpMacHistory"]] = relationship(
        "ArpMacHistory", back_populates="snapshot", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scanned_at": self.scanned_at.isoformat(),
            "scanned_by": self.scanned_by,
            "total_routers": self.total_routers,
            "total_records": self.total_records,
            "source_filename": self.source_filename,
            "archive_csv_path": self.archive_csv_path,
            "status": self.status,
            "notes": self.notes,
        }


class ArpMacHistory(Base):
    """Archived ARP/MAC records associated with a specific historical snapshot."""
    __tablename__ = "arp_mac_history"
    __table_args__ = (
        Index("ix_arp_mac_history_snapshot_id", "snapshot_id"),
        Index("ix_arp_mac_history_arp_ip", "arp_ip"),
        Index("ix_arp_mac_history_arp_mac", "arp_mac"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("arp_mac_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    ne_name: Mapped[str] = mapped_column(String(150), nullable=False)
    ne_ip: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    arp_ip: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    arp_mac: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    vlan: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vrf: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    arp_interface: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    mac_port: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    snapshot: Mapped["ArpMacSnapshot"] = relationship("ArpMacSnapshot", back_populates="history_records")


class SiteInventory(Base):
    """Site inventory model mapping to unified_sites.csv."""
    __tablename__ = "sites_inventory"
    __table_args__ = (
        Index("ix_sites_inventory_site_code", "site_code"),
        Index("ix_sites_inventory_ip", "ip"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    ip: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ne_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "site_code": self.site_code,
            "ip": self.ip,
            "model": self.model or "",
            "ne_name": self.ne_name or self.site_code,
            "province": self.province or "",
        }
