import asyncio
import structlog
from datetime import datetime, timezone
from typing import Optional, Coroutine

from workers.queue import get_queue
from db.mongo import get_db
from db.redis import get_redis
from db.mysql import AsyncSessionLocal
from metrics import record_processed
from schemas.signal import SignalIngest
from core.debounce import (
    check_debounce,
    store_work_item_ref,
    cache_incident_summary,
)
from core.alert_strategy import alert_dispatcher, PRIORITY_MAP, WorkItemSummary
from core.retry import with_retry
from core.timeline import get_or_create_timeline, persist_timeline_to_redis
from core.correlation import detect_and_store_correlations
from models import WorkItem, ComponentType, Priority, WorkItemStatus
import ulid

log = structlog.get_logger()

WORKER_COUNT = 12


# ── Retried DB writes ────────────────────────────────────

@with_retry(max_attempts=3, backoff=0.5)
async def _create_work_item(signal: SignalIngest) -> WorkItem:
    """Create a new WorkItem in MySQL. Retried up to 3 times."""
    priority_str = PRIORITY_MAP.get(signal.component_type, "P2")

    work_item = WorkItem(
        id=str(ulid.new()),
        component_id=signal.component_id,
        component_type=ComponentType(signal.component_type),
        priority=Priority(priority_str),
        status=WorkItemStatus.OPEN,
        first_signal_id=signal.signal_id,
        signal_count=1,
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(work_item)
        await session.refresh(work_item)

    log.info(
        "work_item_created",
        work_item_id=work_item.id,
        component_id=work_item.component_id,
        priority=priority_str,
    )
    return work_item


@with_retry(max_attempts=3, backoff=0.5)
async def _increment_signal_count(work_item_id: str):
    """Increment signal_count atomically. Retried up to 3 times."""
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE work_items "
                    "SET signal_count = signal_count + 1 "
                    "WHERE id = :id"
                ),
                {"id": work_item_id},
            )


@with_retry(max_attempts=3, backoff=0.5)
async def _persist_signal_to_mongo(doc: dict):
    """Write raw signal to MongoDB. Retried up to 3 times."""
    db = get_db()
    await db.signals.insert_one(doc)


# ── Signal processing ───────────────────────────────────

async def _process_signal(signal: SignalIngest):
    redis = get_redis()
    
    # Start timeline collection for this component
    # If this is a new incident, we'll create timeline for work_item_id later
    temp_timeline_id = f"component_{signal.component_id}_{signal.signal_id}"

    is_first, existing_work_item_id = await check_debounce(
        redis, signal.component_id, signal.signal_id
    )

    work_item_id: str | None = None

    if is_first:
        try:
            work_item = await _create_work_item(signal)
            work_item_id = work_item.id
            
            # Now that we have work_item_id, get the real timeline collector
            timeline = get_or_create_timeline(work_item_id)
            timeline.add_event(
                "work_item_created",
                work_item_id=work_item.id,
                component_id=work_item.component_id,
                priority=work_item.priority.value,
            )

            await store_work_item_ref(redis, signal.component_id, work_item_id)
            
            # Record cache update in timeline
            timeline.add_event(
                "cache_updated",
                cache_type="incident_summary",
                ttl_seconds=12,
            )
            
            await cache_incident_summary(redis, {
                "id": work_item.id,
                "component_id": work_item.component_id,
                "component_type": work_item.component_type.value,
                "priority": work_item.priority.value,
                "status": work_item.status.value,
                "signal_count": work_item.signal_count,
                "created_at": work_item.created_at.isoformat(),
                "updated_at": work_item.updated_at.isoformat(),
            })

            summary = WorkItemSummary(
                id=work_item.id,
                component_id=work_item.component_id,
                component_type=work_item.component_type.value,
                priority=work_item.priority.value,
                first_signal_id=signal.signal_id,
                created_at=work_item.created_at,
            )
            
            # Record alert dispatch in timeline
            timeline.add_event(
                "alert_dispatched",
                priority=work_item.priority.value,
                alert_type="pagerduty",
            )
            
            await alert_dispatcher.dispatch(summary)
            
            # Persist timeline to Redis for quick access (1 hour TTL)
            await persist_timeline_to_redis(redis, work_item_id)
            
            # Detect correlations: non-blocking, logs internally
            correlation_count = await detect_and_store_correlations(
                incident_id=work_item_id,
                component_type=work_item.component_type.value,
                component_id=work_item.component_id,
            )
            timeline.add_event(
                "correlation_detection_completed",
                correlations_found=correlation_count,
            )

        except Exception as e:
            # Log exception but avoid structlog parameter binding conflict
            try:
                incident_context = work_item_id if work_item_id else "N/A"
                log.error(
                    "work_item_processing_failed",
                    incident_id=incident_context,
                    signal_id=signal.signal_id,
                    error_type=type(e).__name__,
                    error_detail=str(e)[:200],
                )
            except Exception as log_err:
                # If logging fails, print directly to stderr
                import sys
                print(f"LOGGING ERROR: {log_err}", file=sys.stderr)
                print(f"ORIGINAL ERROR: {e}", file=sys.stderr)
    else:
        work_item_id = existing_work_item_id
        if work_item_id:
            # Get existing timeline and record signal accumulation
            timeline = get_or_create_timeline(work_item_id)
            timeline.add_event(
                "signal_received",
                count=1,
                signal_id=signal.signal_id,
            )
            
            try:
                await _increment_signal_count(work_item_id)
                
                # Re-persist timeline to Redis with updated signal count
                await persist_timeline_to_redis(redis, work_item_id)
            except Exception as e:
                log.error("signal_count_increment_failed", error=str(e))

    # Persist raw signal to MongoDB
    doc = signal.model_dump()
    doc["work_item_id"] = work_item_id
    doc["ingested_at"] = datetime.now(timezone.utc)

    try:
        await _persist_signal_to_mongo(doc)
        record_processed()
    except Exception as e:
        log.error(
            "signal_persist_failed",
            signal_id=signal.signal_id,
            error=str(e)
        )


# ── Worker loop ─────────────────────────────────────────

async def worker(worker_id: int):
    """
    Single worker coroutine.
    Runs forever, pulling from the shared queue.
    """
    queue = get_queue()
    log.info("worker_started", worker_id=worker_id)

    while True:
        try:
            signal: SignalIngest = await queue.get()
            await _process_signal(signal)
            queue.task_done()
        except asyncio.CancelledError:
            log.info("worker_stopped", worker_id=worker_id)
            break
        except Exception as e:
            log.error("worker_unexpected_error", worker_id=worker_id, error=str(e))
            continue


async def start_worker_pool() -> list[asyncio.Task]:
    """
    Launch all workers as asyncio tasks.
    Returns the task list so lifespan can cancel them on shutdown.
    """
    tasks = [
        asyncio.create_task(worker(i), name=f"ims-worker-{i}")
        for i in range(WORKER_COUNT)
    ]
    log.info("worker_pool_started", count=WORKER_COUNT)
    return tasks


async def stop_worker_pool(tasks: list[asyncio.Task]):
    """
    Gracefully cancel all workers on shutdown.
    Waits for the queue to drain first (up to 10 seconds).
    """
    queue = get_queue()
    log.info("draining_queue", remaining=queue.qsize())

    try:
        await asyncio.wait_for(queue.join(), timeout=10.0)
        log.info("queue_drained")
    except asyncio.TimeoutError:
        log.warning("queue_drain_timeout", remaining=queue.qsize())

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("worker_pool_stopped")
