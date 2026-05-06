from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
import json
import ulid
import structlog
from datetime import timezone

from db.mysql import AsyncSessionLocal
from db.redis import get_redis
from db.mongo import get_db
from db.influx_writer import write_incident_resolution
from models import WorkItem, RCA, RootCauseCategory
from schemas.incident import (
    StatusUpdate,
    WorkItemResponse,
    WorkItemDetailResponse,
    WorkItemListResponse,
    RCASummary,
)
from schemas.rca import RCACreate, RCAResponse
from schemas.timeline import TimelineResponse
from schemas.correlation import IncidentCorrelationResponse
from core.state_machine import (
    get_state,
    InvalidTransitionError,
    RCAMissingError,
)
from core.retry import with_retry
from core.debounce import update_incident_cache
from core.timeline import get_timeline
from core.correlation import find_related_incidents

log = structlog.get_logger()
router = APIRouter(prefix="/incidents", tags=["incidents"])


# ── Helpers ──────────────────────────────────────────────

def _mttr_human(seconds: float) -> str:
    """Convert seconds to human-readable string e.g. '1h 30m 22s'."""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _allowed_transitions(from_state: str) -> str:
    allowed = {
        "OPEN":          "INVESTIGATING",
        "INVESTIGATING": "RESOLVED",
        "RESOLVED":      "CLOSED (requires RCA submission)",
        "CLOSED":        "none — terminal state",
    }
    return allowed.get(from_state, "unknown")


@with_retry(max_attempts=3, backoff=0.5, exceptions=(SQLAlchemyError, IOError))
async def _write_rca_and_close(
    incident_id: str,
    body: RCACreate,
) -> tuple[WorkItem, RCA]:
    """
    Transactional: write RCA + transition work item to CLOSED.
    Both succeed or both roll back.
    Retried up to 3 times on DB errors.
    """
    mttr_seconds = (body.end_time - body.start_time).total_seconds()

    async with AsyncSessionLocal() as session:
        async with session.begin():

            # Load work item with row lock
            result = await session.execute(
                select(WorkItem)
                .where(WorkItem.id == incident_id)
                .with_for_update()
            )
            work_item = result.scalar_one_or_none()
            if not work_item:
                log.warning("work_item_not_found", incident_id=incident_id)
                raise ValueError(f"Work item {incident_id} not found")

            log.debug(
                "work_item_loaded",
                incident_id=incident_id,
                status=work_item.status.value if work_item.status else None
            )

            # Enforce: only RESOLVED work items can receive an RCA
            if work_item.status.value not in ("RESOLVED", "OPEN", "INVESTIGATING"):
                log.warning(
                    "work_item_wrong_state_for_rca",
                    incident_id=incident_id,
                    current_status=work_item.status.value
                )
                raise ValueError(
                    f"Work item is already {work_item.status.value}. "
                    f"Transition to RESOLVED before submitting RCA."
                )

            # Check for duplicate RCA
            existing = await session.execute(
                select(RCA).where(RCA.work_item_id == incident_id)
            )
            existing_rca = existing.scalar_one_or_none()
            if existing_rca:
                log.warning(
                    "duplicate_rca_submission",
                    incident_id=incident_id,
                    existing_rca_id=existing_rca.id
                )
                raise ValueError(
                    f"An RCA already exists for incident {incident_id}."
                )

            # Create RCA record
            # body.root_cause_category is already the correct RootCauseCategory enum from models
            # Pass it directly — no conversion needed
            rca = RCA(
                id=str(ulid.new()),
                work_item_id=incident_id,
                start_time=body.start_time,
                end_time=body.end_time,
                root_cause_category=body.root_cause_category,
                fix_applied=body.fix_applied,
                prevention_steps=body.prevention_steps,
                mttr_seconds=mttr_seconds,
            )
            session.add(rca)

            # Transition work item to CLOSED
            work_item.status = "CLOSED"

            await session.flush()
            await session.refresh(work_item)
            await session.refresh(rca)

            log.info(
                "rca_and_close_committed",
                incident_id=incident_id,
                rca_id=rca.id,
                mttr_seconds=mttr_seconds
            )

    return work_item, rca


# ── GET /incidents ────────────────────────────────────────

@router.get("", response_model=WorkItemListResponse)
async def list_incidents():
    """
    Returns active incidents sorted by priority (P0 first).
    Reads from Redis cache. Falls back to MySQL on cache miss.
    """
    redis = get_redis()
    work_item_ids = await redis.zrange("incidents:active", 0, -1)

    if work_item_ids:
        incidents = []
        for wi_id in work_item_ids:
            raw = await redis.get(f"incident:summary:{wi_id}")
            if raw:
                incidents.append(json.loads(raw))
        if incidents:
            return WorkItemListResponse(total=len(incidents), incidents=incidents)

    log.info("incidents_cache_miss_fallback_to_mysql")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkItem)
            .where(WorkItem.status != "CLOSED")
            .order_by(WorkItem.priority, WorkItem.created_at.desc())
        )
        work_items = result.scalars().all()

    return WorkItemListResponse(
        total=len(work_items),
        incidents=[WorkItemResponse.model_validate(wi) for wi in work_items],
    )


# ── GET /incidents/{id} ───────────────────────────────────

@router.get("/{incident_id}", response_model=WorkItemDetailResponse)
async def get_incident(incident_id: str):
    """
    Returns full work item detail including RCA if present.
    """
    async with AsyncSessionLocal() as session:
        wi_result = await session.execute(
            select(WorkItem).where(WorkItem.id == incident_id)
        )
        work_item = wi_result.scalar_one_or_none()

        if not work_item:
            raise HTTPException(
                status_code=404,
                detail=f"Incident {incident_id} not found."
            )

        rca_result = await session.execute(
            select(RCA).where(RCA.work_item_id == incident_id)
        )
        rca = rca_result.scalar_one_or_none()

    rca_summary = None
    if rca:
        rca_summary = RCASummary(
            id=rca.id,
            start_time=rca.start_time,
            end_time=rca.end_time,
            root_cause_category=rca.root_cause_category.value,
            fix_applied=rca.fix_applied,
            prevention_steps=rca.prevention_steps,
            mttr_seconds=rca.mttr_seconds,
            mttr_human=_mttr_human(rca.mttr_seconds),
            submitted_at=rca.submitted_at,
        )

    return WorkItemDetailResponse(
        id=work_item.id,
        component_id=work_item.component_id,
        component_type=work_item.component_type.value,
        priority=work_item.priority.value,
        status=work_item.status.value,
        first_signal_id=work_item.first_signal_id,
        signal_count=work_item.signal_count,
        created_at=work_item.created_at,
        updated_at=work_item.updated_at,
        rca=rca_summary,
    )


# ── PUT /incidents/{id}/status ────────────────────────────

@router.put("/{incident_id}/status", response_model=WorkItemResponse)
async def update_status(incident_id: str, body: StatusUpdate):
    """
    Transition work item status via state machine.
    RESOLVED → CLOSED is blocked here — use POST /rca instead.
    """
    target_status = body.status.upper()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(WorkItem)
                .where(WorkItem.id == incident_id)
                .with_for_update()
            )
            work_item = result.scalar_one_or_none()

            if not work_item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Incident {incident_id} not found."
                )

            rca_result = await session.execute(
                text("SELECT id FROM rca WHERE work_item_id = :id"),
                {"id": incident_id}
            )
            has_rca = rca_result.first() is not None

            current_state = get_state(work_item.status.value)
            try:
                new_state = current_state.transition(target_status, has_rca=has_rca)
            except RCAMissingError as e:
                raise HTTPException(status_code=422, detail=str(e))
            except InvalidTransitionError as e:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid transition: {e.from_state} → {e.to_state}. "
                        f"Allowed from {e.from_state}: "
                        f"{_allowed_transitions(e.from_state)}"
                    )
                )

            work_item.status = new_state.name
            await session.flush()
            await session.refresh(work_item)

    redis = get_redis()
    await update_incident_cache(redis, incident_id, {
        "status": new_state.name,
        "updated_at": work_item.updated_at.isoformat(),
    })

    log.info("status_updated", incident_id=incident_id, new_status=new_state.name)
    return WorkItemResponse.model_validate(work_item)


# ── POST /incidents/{id}/rca ──────────────────────────────

@router.post(
    "/{incident_id}/rca",
    response_model=RCAResponse,
    status_code=201,
    summary="Submit RCA and close the incident",
    description=(
        "All five fields are required. Incomplete submissions are rejected with 422. "
        "end_time must be after start_time. "
        "MTTR is calculated server-side. "
        "This call atomically writes the RCA and transitions the work item to CLOSED."
    )
)
async def submit_rca(incident_id: str, body: RCACreate):
    """
    The only way to close an incident.
    Validates RCA completeness, calculates MTTR, writes both
    RCA and CLOSED status in a single MySQL transaction.
    Then writes a resolution metric to InfluxDB.
    """
    try:
        work_item, rca = await _write_rca_and_close(incident_id, body)
    except ValueError as e:
        log.warning("rca_validation_failed", incident_id=incident_id, error=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.error(
            "rca_submission_failed",
            incident_id=incident_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to submit RCA. Please retry."
        )

    # Update Redis — remove from active set, update summary
    redis = get_redis()
    await update_incident_cache(redis, incident_id, {
        "status": "CLOSED",
        "updated_at": work_item.updated_at.isoformat(),
    })

    # Write resolution metric to InfluxDB (non-blocking on failure)
    try:
        await write_incident_resolution(
            work_item_id=incident_id,
            component_type=work_item.component_type.value,
            priority=work_item.priority.value,
            mttr_seconds=rca.mttr_seconds,
            signal_count=work_item.signal_count,
            root_cause_category=rca.root_cause_category.value,
        )
    except Exception as e:
        # InfluxDB failure must never block incident closure
        log.warning("influx_write_failed_non_fatal", error=str(e))

    log.info(
        "incident_closed",
        incident_id=incident_id,
        mttr_seconds=rca.mttr_seconds,
        mttr_human=_mttr_human(rca.mttr_seconds),
        priority=work_item.priority.value,
    )

    return RCAResponse(
        id=rca.id,
        work_item_id=rca.work_item_id,
        start_time=rca.start_time,
        end_time=rca.end_time,
        root_cause_category=rca.root_cause_category.value,
        fix_applied=rca.fix_applied,
        prevention_steps=rca.prevention_steps,
        mttr_seconds=rca.mttr_seconds,
        mttr_human=_mttr_human(rca.mttr_seconds),
        submitted_at=rca.submitted_at,
    )


# ── GET /incidents/{id}/signals ───────────────────────────

@router.get("/{incident_id}/signals")
async def get_signals(
    incident_id: str,
    limit: int = 50,
    skip: int = 0,
):
    """
    Returns raw signals linked to this incident from MongoDB.
    Sorted by timestamp descending (newest first).
    """
    db = get_db()
    cursor = (
        db.signals
        .find({"work_item_id": incident_id}, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    signals = await cursor.to_list(length=limit)
    total = await db.signals.count_documents({"work_item_id": incident_id})

    return {
        "incident_id": incident_id,
        "total": total,
        "limit": limit,
        "skip": skip,
        "signals": signals,
    }


# ── GET /incidents/{id}/timeline ───────────────────────────

@router.get("/{incident_id}/timeline", response_model=TimelineResponse)
async def get_timeline_endpoint(incident_id: str):
    """
    Returns the timeline of events for this incident.
    Shows: signal batches received → debounce check → work item creation → alerts.
    
    Timeline is collected during processing and stored in Redis (1 hour TTL)
    or MongoDB (permanent history after incident closes).
    """
    redis = get_redis()
    
    # Try Redis first (fast path for recent incidents)
    key = f"timeline:{incident_id}"
    timeline_json = await redis.get(key)
    
    if timeline_json:
        import json
        data = json.loads(timeline_json)
        
        # Query incident to get ended_at if closed
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WorkItem).where(WorkItem.id == incident_id)
            )
            work_item = result.scalar_one_or_none()
            if work_item and work_item.status.value == "CLOSED":
                result_rca = await session.execute(
                    select(RCA).where(RCA.work_item_id == incident_id)
                )
                rca = result_rca.scalar_one_or_none()
                if rca:
                    data["ended_at"] = rca.submitted_at.isoformat()
        
        return TimelineResponse(**data)
    
    # Fall back to MongoDB for closed incidents
    db = get_db()
    timeline_doc = await db.timelines.find_one({"work_item_id": incident_id})
    
    if timeline_doc:
        # Remove MongoDB _id field
        timeline_doc.pop("_id", None)
        return TimelineResponse(**timeline_doc)
    
    # Timeline not found (incident too old or not yet closed)
    raise HTTPException(
        status_code=404,
        detail=f"Timeline not found for incident {incident_id}. "
               "Timeline is available for active incidents (1 hour retention) "
               "or permanently after closure."
    )


# ── GET /incidents/{id}/related ──────────────────────────

@router.get("/{incident_id}/related", response_model=IncidentCorrelationResponse)
async def get_related_incidents(
    incident_id: str,
    time_window_seconds: int = 30,
):
    """
    Returns incidents related to this incident via root cause or cascade relationships.
    
    Detection methods:
    - Dependency Graph: Component dependencies (hardcoded topology)
    - Temporal: Incidents within 30 seconds of each other
    - Semantic: Similar error patterns
    
    Returns:
    - root_causes: Incidents that likely caused this one
    - cascaded_incidents: Incidents likely caused by this one
    - related_incidents: Other temporal/semantic correlations
    """
    root_causes, cascades = await find_related_incidents(incident_id, time_window_seconds)
    
    return IncidentCorrelationResponse(
        incident_id=incident_id,
        root_causes=[
            {
                "id": r.id,
                "source_incident_id": r.source_incident_id,
                "target_incident_id": r.target_incident_id,
                "relationship_type": r.relationship_type.value,
                "confidence": r.confidence,
                "detection_method": r.detection_method,
                "reason": r.reason,
                "created_at": r.created_at,
            }
            for r in root_causes
        ],
        cascaded_incidents=[
            {
                "id": r.id,
                "source_incident_id": r.source_incident_id,
                "target_incident_id": r.target_incident_id,
                "relationship_type": r.relationship_type.value,
                "confidence": r.confidence,
                "detection_method": r.detection_method,
                "reason": r.reason,
                "created_at": r.created_at,
            }
            for r in cascades
        ],
        related_incidents=[],
    )
