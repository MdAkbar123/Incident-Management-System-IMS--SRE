from sqlalchemy import Column, String, Integer, Float, Enum, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from db.mysql import Base
import enum

class ComponentType(str, enum.Enum):
    API         = "API"
    MCP_HOST    = "MCP_HOST"
    CACHE       = "CACHE"
    ASYNC_QUEUE = "ASYNC_QUEUE"
    RDBMS       = "RDBMS"
    NOSQL       = "NOSQL"

class Priority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"

class WorkItemStatus(str, enum.Enum):
    OPEN          = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED      = "RESOLVED"
    CLOSED        = "CLOSED"

class RootCauseCategory(str, enum.Enum):
    INFRASTRUCTURE     = "INFRASTRUCTURE"
    CODE_BUG           = "CODE_BUG"
    CONFIG_CHANGE      = "CONFIG_CHANGE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    UNKNOWN            = "UNKNOWN"

class WorkItem(Base):
    __tablename__ = "work_items"

    id               = Column(String(26), primary_key=True)
    component_id     = Column(String(100), nullable=False, index=True)
    component_type   = Column(Enum(ComponentType), nullable=False)
    priority         = Column(Enum(Priority), nullable=False)
    status           = Column(Enum(WorkItemStatus), default=WorkItemStatus.OPEN, nullable=False)
    first_signal_id  = Column(String(36), nullable=True)
    signal_count     = Column(Integer, default=1, nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    resolved_at      = Column(DateTime(timezone=True), nullable=True)

class RCA(Base):
    __tablename__ = "rca"

    id                  = Column(String(26), primary_key=True)
    work_item_id        = Column(String(26), ForeignKey("work_items.id"), nullable=False, unique=True)
    start_time          = Column(DateTime(timezone=True), nullable=False)
    end_time            = Column(DateTime(timezone=True), nullable=False)
    root_cause_category = Column(Enum(RootCauseCategory), nullable=False)
    fix_applied         = Column(Text, nullable=False)
    prevention_steps    = Column(Text, nullable=False)
    mttr_seconds        = Column(Float, nullable=False)
    submitted_at        = Column(DateTime(timezone=True), server_default=func.now())


class IncidentCorrelation(Base):
    __tablename__ = "incident_correlations"

    id                   = Column(String(26), primary_key=True)
    root_incident_id     = Column(String(26), ForeignKey("work_items.id"), nullable=False, index=True)
    cascaded_incident_id = Column(String(26), ForeignKey("work_items.id"), nullable=False, index=True)
    correlation_reason   = Column(String(200), nullable=False)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
