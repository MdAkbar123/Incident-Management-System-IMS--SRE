from pydantic import BaseModel, field_serializer
from datetime import datetime, timezone
from typing import Optional


class StatusUpdate(BaseModel):
    status: str

    model_config = {
        "json_schema_extra": {
            "example": {"status": "INVESTIGATING"}
        }
    }


class WorkItemResponse(BaseModel):
    id: str
    component_id: str
    component_type: str
    priority: str
    status: str
    first_signal_id: Optional[str] = None
    signal_count: int
    created_at: datetime
    updated_at: datetime
    # Stamped server-side when status transitions to RESOLVED.
    # None until that transition occurs — the frontend must not
    # fall back to created_at if this is None.
    resolved_at: Optional[datetime] = None

    # Serialise all datetime fields as UTC ISO-8601 strings with explicit
    # 'Z' suffix (e.g. "2026-05-06T10:30:00Z") so the frontend always
    # receives unambiguous UTC, never a bare naive timestamp it could
    # misinterpret as local time.
    @field_serializer("created_at", "updated_at", "resolved_at")
    def serialize_as_utc(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            # Naive datetime from DB — brand as UTC (safe after the
            # MySQL SET time_zone = '+00:00' fix in mysql.py)
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    model_config = {"from_attributes": True}


class WorkItemListResponse(BaseModel):
    total: int
    incidents: list[WorkItemResponse]


class RCASummary(BaseModel):
    """Embedded in WorkItemDetailResponse."""
    id: str
    start_time: datetime
    end_time: datetime
    root_cause_category: str
    fix_applied: str
    prevention_steps: str
    mttr_seconds: float
    mttr_human: str
    submitted_at: datetime

    # Same UTC serialisation applied to all RCA timestamps so the
    # "Detected at / Resolved at" display in the RCA form is consistent
    # with the values shown in the incident list.
    @field_serializer("start_time", "end_time", "submitted_at")
    def serialize_as_utc(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    model_config = {"from_attributes": True}


class CorrelationInfo(BaseModel):
    """Embedded in WorkItemDetailResponse when incident is cascaded from root."""
    is_cascaded_from: str  # root incident ID
    root_component: str  # component type of root
    reason: str  # correlation reason


class WorkItemDetailResponse(WorkItemResponse):
    """
    Extended response for GET /incidents/{id}.
    Includes the RCA record if the incident is RESOLVED or CLOSED.
    Includes correlation metadata if this is a cascaded incident.
    """
    rca: Optional[RCASummary] = None
    correlation: Optional[CorrelationInfo] = None
    cascaded_incidents: list[str] = []  # list of incident IDs cascaded from this one