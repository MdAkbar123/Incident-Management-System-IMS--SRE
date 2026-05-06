"""
Incident Relationship Schema
=============================
Tracks parent-child relationships between incidents for root cause analysis.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class IncidentRelationshipResponse(BaseModel):
    """Single relationship between two incidents."""
    id: str = Field(..., description="Relationship ID")
    source_incident_id: str = Field(..., description="Source incident (parent or cascaded)")
    target_incident_id: str = Field(..., description="Target incident (child or root cause)")
    relationship_type: str = Field(
        ...,
        description="Type: root_cause, cascaded_from, related_to"
    )
    confidence: float = Field(
        ...,
        description="Confidence score 0.0-1.0 (based on detection method)"
    )
    detection_method: str = Field(
        ...,
        description="How relationship was detected: dependency_graph, temporal, semantic"
    )
    reason: str = Field(..., description="Human-readable explanation")
    created_at: datetime = Field(..., description="When relationship was detected")


class IncidentCorrelationResponse(BaseModel):
    """Incidents related to a specific incident."""
    incident_id: str = Field(..., description="The reference incident")
    root_causes: list[IncidentRelationshipResponse] = Field(
        default_factory=list,
        description="Incidents that caused this one (if cascaded)"
    )
    cascaded_incidents: list[IncidentRelationshipResponse] = Field(
        default_factory=list,
        description="Incidents caused by this one"
    )
    related_incidents: list[IncidentRelationshipResponse] = Field(
        default_factory=list,
        description="Other related incidents (temporal, semantic)"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "incident_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "root_causes": [
                    {
                        "id": "rel_001",
                        "source_incident_id": "01ARZ3NDEKTSV4RRFFQ69G5FB0",
                        "target_incident_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                        "relationship_type": "root_cause",
                        "confidence": 0.95,
                        "detection_method": "dependency_graph",
                        "reason": "RDBMS failure caused API cascade",
                        "created_at": "2026-05-05T10:30:15.123Z"
                    }
                ],
                "cascaded_incidents": [
                    {
                        "id": "rel_002",
                        "source_incident_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                        "target_incident_id": "01ARZ3NDEKTSV4RRFFQ69G5FB1",
                        "relationship_type": "cascaded_from",
                        "confidence": 0.90,
                        "detection_method": "temporal",
                        "reason": "Cache failure 2 seconds after API degradation",
                        "created_at": "2026-05-05T10:30:17.456Z"
                    }
                ],
                "related_incidents": []
            }
        }
    }
