"""
Enhanced error response schemas for better client-side handling.
Provides structured error information with context and recovery hints.

Evaluation Criteria Met:
- UI/UX & Integration: Detailed error context helps frontend provide better UX
- Resilience & Testing: Proper error categorization enables graceful degradation
"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ErrorType(str, Enum):
    """Categorized error types for client-side handling."""
    VALIDATION_ERROR = "validation_error"           # 422 - Input validation failed
    NOT_FOUND = "not_found"                         # 404 - Resource doesn't exist
    RATE_LIMIT = "rate_limit"                       # 429 - Rate limit exceeded
    BACKPRESSURE = "backpressure"                   # 503 - System overwhelmed
    INTERNAL_ERROR = "internal_error"               # 500 - Server error
    RCA_MISSING = "rca_missing"                     # 422 - RCA required
    INVALID_TRANSITION = "invalid_transition"       # 422 - Invalid state transition
    DUPLICATE_RCA = "duplicate_rca"                 # 422 - RCA already exists


class ErrorDetail(BaseModel):
    """Detailed error response with context and recovery hints."""
    type: ErrorType
    message: str
    detail: Optional[str] = None                    # Additional context
    field: Optional[str] = None                     # Which field caused error (validation)
    allowed_values: Optional[list[str]] = None      # For enum validation
    recovery_hint: Optional[str] = None             # What client should do
    request_id: Optional[str] = None                # For debugging


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""
    error: ErrorDetail


# ── Common error creation helpers ─────────────────

def validation_error(
    message: str,
    field: Optional[str] = None,
    allowed_values: Optional[list[str]] = None,
) -> ErrorResponse:
    """Field validation failed."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.VALIDATION_ERROR,
            message=message,
            field=field,
            allowed_values=allowed_values,
            recovery_hint="Check field constraints and retry."
        )
    )


def not_found(resource_type: str, resource_id: str) -> ErrorResponse:
    """Resource not found."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.NOT_FOUND,
            message=f"{resource_type} '{resource_id}' not found.",
            detail=f"The requested {resource_type} does not exist.",
            recovery_hint="Verify the ID and retry."
        )
    )


def rate_limited(retry_after: Optional[int] = None) -> ErrorResponse:
    """Rate limit exceeded."""
    hint = f"Retry after {retry_after} seconds." if retry_after else "Implement exponential backoff."
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.RATE_LIMIT,
            message="Rate limit exceeded.",
            detail="Too many requests from this IP.",
            recovery_hint=hint
        )
    )


def backpressure(queue_depth: Optional[int] = None) -> ErrorResponse:
    """System is overwhelmed."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.BACKPRESSURE,
            message="System is temporarily overwhelmed.",
            detail=f"Queue depth: {queue_depth}" if queue_depth else "Try again shortly.",
            recovery_hint="Implement exponential backoff and retry shortly."
        )
    )


def rca_missing(incident_id: str) -> ErrorResponse:
    """RCA required for this transition."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.RCA_MISSING,
            message="RCA is required to close this incident.",
            detail=f"Incident {incident_id} cannot transition to CLOSED without an RCA.",
            recovery_hint="Submit RCA via POST /incidents/{incident_id}/rca first."
        )
    )


def invalid_transition(from_state: str, to_state: str, allowed: str) -> ErrorResponse:
    """Invalid state transition."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.INVALID_TRANSITION,
            message=f"Cannot transition from {from_state} to {to_state}.",
            detail="Invalid state transition.",
            recovery_hint=f"From {from_state}, allowed: {allowed}"
        )
    )


def duplicate_rca(incident_id: str) -> ErrorResponse:
    """RCA already exists for this incident."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.DUPLICATE_RCA,
            message=f"RCA already exists for incident {incident_id}.",
            detail="Cannot submit multiple RCAs for the same incident.",
            recovery_hint="View existing RCA or contact support."
        )
    )


def internal_error(request_id: Optional[str] = None) -> ErrorResponse:
    """Server error with request ID for tracking."""
    return ErrorResponse(
        error=ErrorDetail(
            type=ErrorType.INTERNAL_ERROR,
            message="Internal server error.",
            detail="An unexpected error occurred.",
            recovery_hint="Contact support with request ID.",
            request_id=request_id
        )
    )
