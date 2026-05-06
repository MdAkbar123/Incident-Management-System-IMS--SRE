from pydantic import BaseModel
from datetime import datetime
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

    model_config = {"from_attributes": True}


class WorkItemDetailResponse(WorkItemResponse):
    """
    Extended response for GET /incidents/{id}.
    Includes the RCA record if the incident is RESOLVED or CLOSED.
    """
    rca: Optional[RCASummary] = None
