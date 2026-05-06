import structlog
from redis.asyncio import Redis

log = structlog.get_logger()

DEBOUNCE_WINDOW_SECONDS = 10


async def check_debounce(
    redis: Redis,
    component_id: str,
    signal_id: str,
) -> tuple[bool, str | None]:
    """
    Check whether this signal should create a new work item
    or link to an existing one.

    Returns:
        (True, None)          — first signal in window, create work item
        (False, work_item_id) — duplicate in window, link to existing

    How it works:
        Key: debounce:{component_id}
        Value: the work_item_id created for this window

        First signal:
            SET debounce:CACHE_CLUSTER_01 "" NX EX 10
            → returns "OK" (key didn't exist)
            → caller creates work item, then stores its ID
            → SET work_item_ref:CACHE_CLUSTER_01 {work_item_id} EX 12

        Subsequent signals within 10s:
            SET debounce:CACHE_CLUSTER_01 "" NX EX 10
            → returns None (key exists)
            → caller fetches work_item_ref key and links to it
    """
    debounce_key = f"debounce:{component_id}"
    ref_key = f"work_item_ref:{component_id}"

    # Atomic: set only if key doesn't exist, expire in 10 seconds
    set_result = await redis.set(debounce_key, "1", nx=True, ex=DEBOUNCE_WINDOW_SECONDS)
    is_first = bool(set_result)
    
    log.debug(
        "debounce_check",
        component_id=component_id,
        signal_id=signal_id,
        set_result=set_result,
        is_first=is_first,
    )

    if is_first:
        # This is the first signal for this component in this window
        log.debug(
            "debounce_first_signal",
            component_id=component_id,
            signal_id=signal_id,
        )
        return True, None
    else:
        # Duplicate — fetch the existing work item ID
        existing_work_item_id = await redis.get(ref_key)
        log.debug(
            "debounce_duplicate",
            component_id=component_id,
            signal_id=signal_id,
            existing_work_item_id=existing_work_item_id,
        )
        return False, existing_work_item_id


async def store_work_item_ref(
    redis: Redis,
    component_id: str,
    work_item_id: str,
):
    """
    After creating a work item, store its ID so duplicate
    signals in the same window can link to it.
    TTL is slightly longer than the debounce window to avoid
    a race where debounce key expires but ref key doesn't yet.
    """
    ref_key = f"work_item_ref:{component_id}"
    await redis.set(ref_key, work_item_id, ex=DEBOUNCE_WINDOW_SECONDS + 2)


async def cache_incident_summary(redis: Redis, work_item: dict):
    """
    Store a lightweight summary of the work item in Redis
    so GET /incidents doesn't need to hit MySQL on every request.

    Key: incident:summary:{work_item_id}
    TTL: 300 seconds (5 minutes) — refreshed on every status update
    """
    import json
    key = f"incident:summary:{work_item['id']}"
    await redis.set(key, json.dumps(work_item), ex=300)
    # Also add to the active incidents sorted set
    # Score: P0=0, P1=1, P2=2 (lower score = higher priority, shown first)
    priority_score = {"P0": 0, "P1": 1, "P2": 2}.get(work_item["priority"], 9)
    await redis.zadd("incidents:active", {work_item["id"]: priority_score})


async def update_incident_cache(redis: Redis, work_item_id: str, updates: dict):
    """
    Update specific fields in the cached incident summary.
    Called on every state transition.
    """
    import json
    key = f"incident:summary:{work_item_id}"
    existing = await redis.get(key)
    if existing:
        data = json.loads(existing)
        data.update(updates)
        await redis.set(key, json.dumps(data), ex=300)
    # If incident is CLOSED, remove from active set
    if updates.get("status") == "CLOSED":
        await redis.zrem("incidents:active", work_item_id)
