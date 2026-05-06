from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import structlog

from middleware.rate_limiter import limiter
from workers.queue import get_queue
from metrics import record_dropped
from schemas.signal import SignalIngest, SignalAccepted

log = structlog.get_logger()
router = APIRouter()


@router.post(
    "/ingest",
    status_code=202,
    response_model=SignalAccepted,
    summary="Ingest a signal from a monitored component",
    description=(
        "Accepts a signal and places it on the internal processing queue. "
        "Returns 202 immediately — never blocks on DB writes. "
        "Returns 429 if the per-IP rate limit is exceeded. "
        "Returns 503 if the internal queue is full (backpressure)."
    )
)
@limiter.limit("500/second")   # per-IP limit
async def ingest_signal(
    request: Request,          # required first param for slowapi
    signal: SignalIngest,
):
    queue = get_queue()

    # ── Backpressure check ──
    # If the queue is full, all DB stores are overwhelmed.
    # Return 503 so the client backs off.
    if queue.full():
        record_dropped()
        log.warning(
            "queue_full_backpressure",
            queue_depth=queue.qsize(),
            component_id=signal.component_id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "backpressure",
                "message": "System is temporarily overwhelmed. Retry shortly.",
                "queue_depth": queue.qsize(),
            }
        )

    # ── Enqueue ──
    # put_nowait is safe here because we checked full() above.
    # We don't use await queue.put() because that would block
    # the request if the queue fills between the check and the put.
    try:
        queue.put_nowait(signal)
    except Exception:
        # Extremely rare race between full() check and put_nowait
        record_dropped()
        return JSONResponse(
            status_code=503,
            content={
                "error": "backpressure",
                "message": "Queue rejected signal. Retry shortly.",
                "queue_depth": queue.qsize(),
            }
        )

    log.debug(
        "signal_enqueued",
        signal_id=signal.signal_id,
        component_id=signal.component_id,
        component_type=signal.component_type,
        queue_depth=queue.qsize(),
    )

    return SignalAccepted(
        accepted=True,
        signal_id=signal.signal_id,
        queue_depth=queue.qsize(),
    )
