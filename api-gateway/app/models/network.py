import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.session import Base


class NetworkNode(Base):
    __tablename__ = "network_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address = Column(String(45), nullable=False, unique=True)
    mac_address = Column(String(17))
    hostname = Column(String(255))
    os_family = Column(String(100))
    os_version = Column(String(200))
    device_type = Column(String(50), default="unknown")
    open_ports = Column(JSONB, default=list)
    services = Column(JSONB, default=list)
    status = Column(String(20), default="active")
    network_range = Column(String(50))
    last_scan_id = Column(UUID(as_uuid=True))
    first_discovered_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)


class NetworkScan(Base):
    __tablename__ = "network_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_type = Column(String(50), nullable=False)
    target = Column(String(255))
    network_range = Column(String(50))
    status = Column(String(20), default="pending")
    nodes_found = Column(Integer, default=0)
    result = Column(JSONB, default=dict)
    error = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
