from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, timezone
from typing import Literal
from models import RootCauseCategory


class RCACreate(BaseModel):
    """
    All five fields are mandatory.
    The API returns 422 if any field is missing or blank.
    MTTR is calculated server-side — never accepted from the client.

    Valid root_cause_category values:
    - INFRASTRUCTURE
    - CODE_BUG
    - CONFIG_CHANGE
    - DEPENDENCY_FAILURE
    - UNKNOWN
    """
    start_time: datetime = Field(
        ...,
        description="When the incident actually started (first impact)"
    )
    end_time: datetime = Field(
        ...,
        description="When the incident was fully resolved"
    )
    root_cause_category: RootCauseCategory = Field(
        ...,
        description="High-level category of the root cause (enum value)"
    )
    fix_applied: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Describe what fix was applied to resolve the incident"
    )
    prevention_steps: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Steps to prevent recurrence"
    )

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def normalize_to_utc(cls, v: object) -> datetime:
        """
        Normalise any incoming datetime to UTC-aware.

        Handles three cases:
          1. Already UTC-aware datetime  → convert to UTC (no-op if already UTC)
          2. Naive datetime              → assume UTC and attach tzinfo
          3. ISO-8601 string with offset → parsed by Pydantic, then normalised here
        """
        if isinstance(v, datetime):
            if v.tzinfo is None:
                # Naive — brand as UTC (consistent with server assumption)
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        # Non-datetime values (e.g. raw strings) fall through to Pydantic's
        # own datetime parser; the validator runs again on the parsed result.
        return v

    @model_validator(mode="after")
    def end_must_be_after_start(self) -> "RCACreate":
        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time.isoformat()}) must be after "
                f"start_time ({self.start_time.isoformat()}). "
                f"Check your timestamps."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_time": "2026-05-03T10:00:00Z",
                "end_time":   "2026-05-03T11:30:00Z",
                "root_cause_category": "INFRASTRUCTURE",
                "fix_applied": (
                    "Increased MySQL connection pool size from 100 to 300. "
                    "Restarted the connection pool manager."
                ),
                "prevention_steps": (
                    "Set up connection pool exhaustion alerts at 70% threshold. "
                    "Add auto-scaling policy for DB connections under load."
                )
            }
        }
    }


class RCAResponse(BaseModel):
    id: str
    work_item_id: str
    start_time: datetime
    end_time: datetime
    root_cause_category: str
    fix_applied: str
    prevention_steps: str
    mttr_seconds: float
    mttr_human: str          # e.g. "1h 30m 00s" — computed on read
    submitted_at: datetime

    model_config = {"from_attributes": True}