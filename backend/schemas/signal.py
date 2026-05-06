from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Any, Literal
from uuid import uuid4


class SignalIngest(BaseModel):
    signal_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique signal identifier, auto-generated if not provided"
    )
    component_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The component emitting this signal e.g. CACHE_CLUSTER_01"
    )
    component_type: Literal["API", "MCP_HOST", "CACHE", "ASYNC_QUEUE", "RDBMS", "NOSQL"]
    error_code: str = Field(..., min_length=1, max_length=100)
    severity: Literal["P0", "P1", "P2"]
    latency_ms: int = Field(..., ge=0, description="0 if not applicable")
    message: str = Field(..., min_length=1, max_length=500)
    source_host: Optional[str] = Field(default=None, max_length=200)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    payload: Optional[dict[str, Any]] = Field(
        default=None,
        description="Freeform component-specific metrics"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "component_id": "CACHE_CLUSTER_01",
                "component_type": "CACHE",
                "error_code": "ERR_EVICTION_STORM",
                "severity": "P2",
                "latency_ms": 842,
                "message": "Eviction rate exceeded 90% threshold",
                "source_host": "cache-node-3.internal",
                "payload": {
                    "eviction_rate": 0.91,
                    "hit_rate": 0.12,
                    "connected_clients": 847
                }
            }
        }
    }


class SignalAccepted(BaseModel):
    accepted: bool = True
    signal_id: str
    queue_depth: int
