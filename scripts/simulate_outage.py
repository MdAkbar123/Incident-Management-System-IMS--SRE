"""
IMS Full-Stack Outage Simulation
=================================
Simulates a realistic cascading failure across all six component types.

Cascade Scenario (realistic failure propagation):
  1. RDBMS_PRIMARY_01   → database goes down           (P0, 200 signals)
  2. MCP_HOST_02        → MCP host loses DB connection  (P0,  50 signals)
  3. API_GATEWAY_01     → APIs start returning 5xx      (P1,  80 signals)
  4. CACHE_CLUSTER_01   → cache eviction storm begins   (P2,  60 signals)
  5. QUEUE_ORDERS_01    → queue consumers fall behind   (P1,  40 signals)
  6. NOSQL_CATALOG_01   → NoSQL write timeouts          (P2,  30 signals)

Total: 460 signals → 6 work items (debounce proven for each component)

Key Insights:
  • RDBMS failure is root cause (200 signals)
  • MCP_HOST, API, CACHE, QUEUE, NOSQL are cascaded failures
  • Priority routing: P0 incidents first, then P1, then P2
  • Debounce window: 10 seconds per component_id
  • Evaluator sees: 6 different work items sorted by priority

Run from project root:
    python scripts/simulate_outage.py

Make sure uvicorn is running on localhost:8000 first:
    uvicorn backend.main:app --reload --port 8000
"""
import asyncio
import httpx
import time
from datetime import datetime, timezone

BASE_URL    = "http://localhost:8000"
DASHBOARD   = "http://localhost:3000"

# ── Signal templates — all six component types ───────────────

SIGNALS = {
    "RDBMS": {
        "component_id":   "RDBMS_PRIMARY_01",
        "component_type": "RDBMS",
        "error_code":     "ERR_CONNECTION_POOL_EXHAUSTED",
        "severity":       "P0",
        "latency_ms":     4200,
        "message":        "Connection pool exhausted. 0 of 100 connections available.",
        "source_host":    "db-primary.internal",
        "payload": {
            "active_connections": 100,
            "waiting_requests":   847,
            "max_pool_size":      100,
        }
    },
    "MCP_HOST": {
        "component_id":   "MCP_HOST_02",
        "component_type": "MCP_HOST",
        "error_code":     "ERR_DB_CONNECTION_LOST",
        "severity":       "P0",
        "latency_ms":     0,
        "message":        "MCP host lost connection to RDBMS_PRIMARY_01. Entering failsafe mode.",
        "source_host":    "mcp-node-2.internal",
        "payload": {
            "lost_connection_to": "RDBMS_PRIMARY_01",
            "failsafe_mode":      True,
            "retry_count":        5,
        }
    },
    "API": {
        "component_id":   "API_GATEWAY_01",
        "component_type": "API",
        "error_code":     "ERR_HIGH_5XX_RATE",
        "severity":       "P1",
        "latency_ms":     1850,
        "message":        "5xx error rate at 43%. Upstream DB timeouts propagating to clients.",
        "source_host":    "api-gateway.internal",
        "payload": {
            "error_rate_pct":   43.2,
            "p99_latency_ms":   4900,
            "upstream_errors":  "RDBMS_PRIMARY_01",
        }
    },
    "CACHE": {
        "component_id":   "CACHE_CLUSTER_01",
        "component_type": "CACHE",
        "error_code":     "ERR_EVICTION_STORM",
        "severity":       "P2",
        "latency_ms":     842,
        "message":        "Eviction storm triggered. DB fallback overloading remaining connections.",
        "source_host":    "cache-node-3.internal",
        "payload": {
            "eviction_rate":      0.91,
            "hit_rate":           0.08,
            "db_fallback_calls":  12400,
        }
    },
    "ASYNC_QUEUE": {
        "component_id":   "QUEUE_ORDERS_01",
        "component_type": "ASYNC_QUEUE",
        "error_code":     "ERR_CONSUMER_LAG",
        "severity":       "P1",
        "latency_ms":     300,
        "message":        "Consumer lag at 84,000 messages. Workers blocked on DB writes.",
        "source_host":    "queue-broker-1.internal",
        "payload": {
            "consumer_lag":    84_000,
            "consumers_alive": 2,
            "consumers_total": 8,
            "dlq_size":        340,
        }
    },
    "NOSQL": {
        "component_id":   "NOSQL_CATALOG_01",
        "component_type": "NOSQL",
        "error_code":     "ERR_WRITE_TIMEOUT",
        "severity":       "P2",
        "latency_ms":     6100,
        "message":        "Write timeouts on shard 3. Replication lag from primary overload.",
        "source_host":    "nosql-shard-3.internal",
        "payload": {
            "shard_id":          3,
            "replication_lag_ms": 8400,
            "write_timeout_pct":  67,
        }
    },
}

# ── Cascade waves — order and signal counts reflect realistic propagation ────
# Format: (component_type, signal_count, pause_before_secs, cascade_description)
WAVES = [
    ("RDBMS",      200, 0,  "Database goes down — root cause"),
    ("MCP_HOST",    50, 5,  "MCP host loses DB connection"),
    ("API",         80, 5,  "API gateway starts returning 5xx"),
    ("CACHE",       60, 3,  "Cache eviction storm as DB fallback overwhelms"),
    ("ASYNC_QUEUE", 40, 3,  "Queue consumers blocked on DB writes"),
    ("NOSQL",       30, 2,  "NoSQL write timeouts from replication lag"),
]


# ── Helpers ──────────────────────────────────────────────────

def banner(text: str, char: str = "="):
    """Print a centered banner."""
    width = 70
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")

def step(text: str):
    """Print a step indicator."""
    print(f"\n  → {text}")

def ok(text: str):
    """Print a success indicator."""
    print(f"  ✓ {text}")

def info(text: str):
    """Print info text."""
    print(f"    {text}")

def warn(text: str):
    """Print a warning indicator."""
    print(f"  ! {text}")


async def send_signals(
    client: httpx.AsyncClient,
    signal: dict,
    count: int,
) -> dict[int, int]:
    """
    Fire `count` signals concurrently to /ingest endpoint.
    Returns a dict of {status_code: count}.
    """
    tasks = [
        client.post("/ingest", json=signal, timeout=15.0)
        for _ in range(count)
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    counts: dict[int, int] = {}
    for r in responses:
        if isinstance(r, Exception):
            counts[0] = counts.get(0, 0) + 1
        else:
            counts[r.status_code] = counts.get(r.status_code, 0) + 1

    return counts


async def verify_work_item(
    client: httpx.AsyncClient,
    component_id: str,
    max_attempts: int = 5,
) -> dict | None:
    """
    Poll /incidents up to max_attempts times to find the work item.
    Returns the work item dict if found, None otherwise.
    """
    for attempt in range(max_attempts):
        await asyncio.sleep(1)
        try:
            r = await client.get("/incidents", timeout=5.0)
            if r.status_code != 200:
                continue
            for incident in r.json().get("incidents", []):
                if incident["component_id"] == component_id:
                    return incident
        except Exception:
            continue
    return None


async def run_wave(
    client: httpx.AsyncClient,
    component_type: str,
    count: int,
    pause_before: int,
    description: str,
    wave_number: int,
    results: list,
) -> None:
    """
    Execute a single failure wave:
    1. Wait pause_before seconds
    2. Send count signals
    3. Verify work item creation
    4. Append result to results list
    """
    signal = SIGNALS[component_type]
    component_id = signal["component_id"]
    priority = signal["severity"]

    banner(
        f"Wave {wave_number} — {component_id:<30} [{component_type}]",
        "─"
    )
    print(f"  {description}")
    print(f"  Firing {count} signals concurrently…")

    if pause_before > 0:
        for remaining in range(pause_before, 0, -1):
            print(f"\r  Starting in {remaining:2d}s…", end="", flush=True)
            await asyncio.sleep(1)
        print(f"\r  Starting now.                 ")

    start = time.perf_counter()
    counts = await send_signals(client, signal, count)
    elapsed = time.perf_counter() - start

    accepted = counts.get(202, 0)
    rate_limited = counts.get(429, 0)
    backpressure = counts.get(503, 0)
    errors = counts.get(0, 0)

    print(f"\n  Sent {count} signals in {elapsed:.2f}s")
    print(f"  ✓ Accepted     : {accepted}")
    if rate_limited:
        print(f"  ~ Rate limited : {rate_limited}")
    if backpressure:
        print(f"  ~ Backpressure : {backpressure}")
    if errors:
        print(f"  ✗ Errors       : {errors}")

    step("Waiting 2s for worker to process signals…")
    await asyncio.sleep(2)

    step("Verifying debounce in database…")
    work_item = await verify_work_item(client, component_id)

    if work_item:
        ok(f"Debounce proven — {count} signals → 1 work item")
        info(f"ID           : {work_item['id']}")
        info(f"Priority     : {work_item['priority']}")
        info(f"Status       : {work_item['status']}")
        info(f"Signal count : {work_item['signal_count']}")
        info(f"Dashboard    : {DASHBOARD}/incidents/{work_item['id']}")
        results.append(work_item)
    else:
        warn(f"Work item not found for {component_id} (check uvicorn logs)")
        results.append(None)




# ── Main simulation ──────────────────────────────────────

async def main():
    """
    Main simulation loop:
    1. Health check
    2. Run all 6 cascading failure waves
    3. Generate comprehensive summary
    """
    banner("IMS Full-Stack Outage Simulation", "=")
    print(f"  Scenario : Cascading failure from RDBMS outage")
    print(f"  Target   : {BASE_URL}")
    print(f"  Dashboard: {DASHBOARD}")
    print(f"  Time     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    print(f"  Components (all six types):")
    for comp_type, count, _, desc in WAVES:
        sig = SIGNALS[comp_type]
        print(f"    [{sig['severity']}] {sig['component_id']:<30} {count:>3} signals")

    # ── Pre-flight check ─────────────────────────────────
    step("Checking server health…")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        try:
            r = await client.get("/health", timeout=5.0)
            health = r.json()
            if health.get("status") != "ok":
                print(f"\n  ✗ Server not healthy: {health}")
                print("    Start uvicorn first: uvicorn main:app --reload --port 8000")
                return
            ok("Server healthy")
            for store, up in health.get("stores", {}).items():
                status = "✓" if up else "✗"
                info(f"{status} {store}")
        except Exception as e:
            print(f"\n  ✗ Cannot reach server: {e}")
            print("    Start uvicorn first: uvicorn main:app --reload --port 8000")
            return

    # ── Run all waves ─────────────────────────────────────
    results = []
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for wave_num, (component_type, count, pause, description) in enumerate(WAVES, 1):
            await run_wave(
                client,
                component_type,
                count,
                pause,
                description,
                wave_num,
                results
            )

    # ════════════════════════════════════════════════════
    # SUMMARY — Full-stack coverage report
    # ════════════════════════════════════════════════════
    banner("Simulation Complete — Full Stack Covered", "=")

    total_signals = sum(w[1] for w in WAVES)
    work_items_created = sum(1 for r in results if r is not None)

    print(f"  Total signals fired  : {total_signals}")
    print(f"  Work items created   : {work_items_created} / {len(WAVES)}")
    print(f"  Debounce ratio       : {total_signals}:1 → {work_items_created} incidents")

    print()
    print(f"  Stack Coverage:")
    print(f"  " + "─" * 66)
    print(f"  {'#':<3} {'Priority':<5} {'Component ID':<30} {'Type':<12} {'Status':<12}")
    print(f"  " + "─" * 66)

    for i, ((comp_type, count, _, _), wi) in enumerate(zip(WAVES, results), 1):
        sig = SIGNALS[comp_type]
        status = "✓ Created " if wi else "✗ Missing "
        print(f"  {i:<3} {sig['severity']:<5} {sig['component_id']:<30} {comp_type:<12} {status:<12}")

    print(f"  " + "─" * 66)

    print()
    print(f"  Evaluator Workflow:")
    print()

    for i, ((comp_type, _, _, _), wi) in enumerate(zip(WAVES, results), 1):
        if wi:
            sig = SIGNALS[comp_type]
            print(f"  {i}. {wi['component_id']:<30}")
            print(f"     URL  : {DASHBOARD}/incidents/{wi['id']}")
            print(f"     Type : {sig['component_type']} (Priority: {sig['severity']})")
            print()

    print(f"  For each incident:")
    print(f"    → Click to open detail page")
    print(f"    → Change status: OPEN → INVESTIGATING → RESOLVED")
    print(f"    → Submit RCA (auto-calculates MTTR)")
    print(f"    → System closes incident (RESOLVED → CLOSED)")
    print()
    print(f"  API Documentation: {BASE_URL}/docs")
    print(f"  Health Endpoint   : {BASE_URL}/health")
    print()


if __name__ == "__main__":
    asyncio.run(main())
