"""
Timeline API Schemas
====================
Response schemas for timeline endpoints.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class TimelineEventResponse(BaseModel):
    """Single timeline event."""
    event_type: str = Field(
        ...,
        description="Type: signal_received, debounce_check, work_item_created, alert_dispatched, etc."
    )
    timestamp: datetime = Field(..., description="When event occurred (ISO 8601)")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (count, result, priority, etc.)"
    )


class TimelineResponse(BaseModel):
    """Complete timeline for an incident."""
    work_item_id: str = Field(..., description="The incident ID")
    component_id: str = Field(..., description="Which component (RDBMS_PRIMARY_01, etc.)")
    started_at: datetime = Field(..., description="When timeline started (first signal)")
    ended_at: Optional[datetime] = Field(None, description="When incident closed (if closed)")
    total_signals: int = Field(..., description="Total signals received")
    total_events: int = Field(..., description="Total timeline events recorded")
    duration_ms: int = Field(..., description="Total duration in milliseconds")
    events: List[TimelineEventResponse] = Field(
        ...,
        description="Ordered list of events from first signal to work item creation"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "work_item_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "component_id": "RDBMS_PRIMARY_01",
                "started_at": "2026-05-05T10:30:00.123Z",
                "ended_at": "2026-05-05T10:31:45.567Z",
                "total_signals": 200,
                "total_events": 5,
                "duration_ms": 2147,
                "events": [
                    {
                        "event_type": "signal_received",
                        "timestamp": "2026-05-05T10:30:00.123Z",
                        "data": {"count": 1, "batch_id": 1}
                    },
                    {
                        "event_type": "signal_received",
                        "timestamp": "2026-05-05T10:30:00.456Z",
                        "data": {"count": 52, "batch_id": 2}
                    },
                    {
                        "event_type": "debounce_check",
                        "timestamp": "2026-05-05T10:30:02.100Z",
                        "data": {"result": "first_occurrence", "attempt": 200}
                    },
                    {
                        "event_type": "work_item_created",
                        "timestamp": "2026-05-05T10:30:02.150Z",
                        "data": {"work_item_id": "01...", "total_signals": 200}
                    },
                    {
                        "event_type": "alert_dispatched",
                        "timestamp": "2026-05-05T10:30:02.200Z",
                        "data": {"priority": "P0", "alert_type": "pagerduty"}
                    }
                ]
            }
        }
    }
