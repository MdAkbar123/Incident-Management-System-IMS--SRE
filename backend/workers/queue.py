import asyncio


# maxsize=50000 — if queue fills up, /ingest returns 503
# This is the backpressure mechanism
_signal_queue: asyncio.Queue | None = None


def create_queue() -> asyncio.Queue:
    global _signal_queue
    _signal_queue = asyncio.Queue(maxsize=50_000)
    return _signal_queue


def get_queue() -> asyncio.Queue:
    if _signal_queue is None:
        raise RuntimeError("Queue not initialized. Call create_queue() in lifespan.")
    return _signal_queue
