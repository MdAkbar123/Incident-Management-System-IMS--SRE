import asyncio
import structlog
from collections import deque
from datetime import datetime, timezone

log = structlog.get_logger()

# Thread-safe counters using simple ints
# (all asyncio — no threading, no locks needed)
_processed_count: int = 0
_dropped_count: int = 0
_start_time: datetime = datetime.now(timezone.utc)
    
# Rolling window — store (timestamp, count) pairs for accurate rate
_window: deque = deque()


def record_processed(n: int = 1):
    """Call this from the worker each time a signal is processed."""
    global _processed_count
    _processed_count += n
    _window.append((asyncio.get_event_loop().time(), n))


def record_dropped(n: int = 1):
    """Call this from the ingest endpoint when 503 is returned."""
    global _dropped_count
    _dropped_count += n


def get_signals_per_sec() -> float:
    """Calculate signals/sec over the last 5 seconds."""
    now = asyncio.get_event_loop().time()
    cutoff = now - 5.0
    # Remove entries older than 5 seconds
    while _window and _window[0][0] < cutoff:
        _window.popleft()
    total = sum(count for _, count in _window)
    return total / 5.0


async def metrics_printer(queue: asyncio.Queue):
    """
    Background task — prints throughput every 5 seconds.
    Also writes to InfluxDB (Phase 4 addition).
    """
    # Import here to avoid circular import at module load
    from db.influx_writer import write_throughput_metric

    log.info("metrics_task_started")
    while True:
        await asyncio.sleep(5)
        sps = get_signals_per_sec()
        log.info(
            "throughput_metrics",
            signals_per_sec=round(sps, 1),
            queue_depth=queue.qsize(),
            total_processed=_processed_count,
            total_dropped_503=_dropped_count,
        )
        # Also print plainly so it's visible in uvicorn output
        print(
            f"[METRICS] "
            f"signals/sec: {sps:.1f} | "
            f"queue depth: {queue.qsize()} | "
            f"total processed: {_processed_count} | "
            f"dropped (503): {_dropped_count}"
        )

        # Write to InfluxDB — failure here must never crash the metrics task
        try:
            await write_throughput_metric(sps, queue.qsize(), _dropped_count)
        except Exception as e:
            log.warning("influx_throughput_write_failed", error=str(e))
