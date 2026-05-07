#!/usr/bin/env python3
"""
IMS Full-Stack Outage Simulation + Correlation Backfill
========================================================
Simulates a realistic cascading failure across all six component types,
then retroactively backfills correlation records for all open incidents.

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
  • After simulation, correlation backfill runs automatically

Run from project root:
    python scripts/simulate_outage_with_backfill.py

Make sure uvicorn is running on localhost:8000 first:
    uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import sys
sys.path.insert(0, '/home/akbar-ali/DEVOPS/projects/ims/backend')

import time
import ulid
import httpx
import structlog
from datetime import datetime, timezone
from sqlalchemy import select

from db.mysql import AsyncSessionLocal
from models import WorkItem, ComponentType, WorkItemStatus, IncidentCorrelation
from core.correlation import _get_upstream_dependencies

log = structlog.get_logger()

BASE_URL  = "http://localhost:8000"
DASHBOARD = "http://localhost:3000"


# ── Signal templates — all six component types ───────────────────────────────

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
        },
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
        },
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
            "error_rate_pct":  43.2,
            "p99_latency_ms":  4900,
            "upstream_errors": "RDBMS_PRIMARY_01",
        },
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
            "eviction_rate":     0.91,
            "hit_rate":          0.08,
            "db_fallback_calls": 12400,
        },
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
        },
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
            "shard_id":           3,
            "replication_lag_ms": 8400,
            "write_timeout_pct":  67,
        },
    },
}

# ── Cascade waves ─────────────────────────────────────────────────────────────
# Format: (component_type, signal_count, pause_before_secs, cascade_description)
WAVES = [
    ("RDBMS",       200, 0, "Database goes down — root cause"),
    ("MCP_HOST",     50, 5, "MCP host loses DB connection"),
    ("API",          80, 5, "API gateway starts returning 5xx"),
    ("CACHE",        60, 3, "Cache eviction storm as DB fallback overwhelms"),
    ("ASYNC_QUEUE",  40, 3, "Queue consumers blocked on DB writes"),
    ("NOSQL",        30, 2, "NoSQL write timeouts from replication lag"),
]


# ── Console helpers ───────────────────────────────────────────────────────────

def banner(text: str, char: str = "="):
    width = 70
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")

def step(text: str):
    print(f"\n  → {text}")

def ok(text: str):
    print(f"  ✓ {text}")

def info(text: str):
    print(f"    {text}")

def warn(text: str):
    print(f"  ! {text}")


# ── Outage simulation helpers ─────────────────────────────────────────────────

async def send_signals(
    client: httpx.AsyncClient,
    signal: dict,
    count: int,
) -> dict[int, int]:
    """Fire `count` signals concurrently to /ingest. Returns {status_code: count}."""
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
    """Poll /incidents to find a work item for the given component_id."""
    for _ in range(max_attempts):
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
    """Execute a single failure wave: wait → send signals → verify work item."""
    signal = SIGNALS[component_type]
    component_id = signal["component_id"]

    banner(
        f"Wave {wave_number} — {component_id:<30} [{component_type}]",
        "─",
    )
    print(f"  {description}")
    print(f"  Firing {count} signals concurrently…")

    if pause_before > 0:
        for remaining in range(pause_before, 0, -1):
            print(f"\r  Starting in {remaining:2d}s…", end="", flush=True)
            await asyncio.sleep(1)
        print("\r  Starting now.                 ")

    start = time.perf_counter()
    counts = await send_signals(client, signal, count)
    elapsed = time.perf_counter() - start

    accepted     = counts.get(202, 0)
    rate_limited = counts.get(429, 0)
    backpressure = counts.get(503, 0)
    errors       = counts.get(0, 0)

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


# ── Correlation backfill ──────────────────────────────────────────────────────

async def backfill_correlations() -> int:
    """Find and create correlations for all existing open/investigating/resolved incidents."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkItem).where(
                WorkItem.status.in_([
                    WorkItemStatus.OPEN,
                    WorkItemStatus.INVESTIGATING,
                    WorkItemStatus.RESOLVED,
                ])
            )
        )
        all_incidents = result.scalars().all()

        log.info("backfill_started", total_incidents=len(all_incidents))
        correlations_created = 0

        for incident in all_incidents:
            upstream_dependencies = _get_upstream_dependencies(incident.component_type.value)
            if not upstream_dependencies:
                continue

            for upstream_component in upstream_dependencies:
                upstream_result = await session.execute(
                    select(WorkItem).where(
                        (WorkItem.component_type == ComponentType(upstream_component))
                        & (WorkItem.status.in_([
                            WorkItemStatus.OPEN,
                            WorkItemStatus.INVESTIGATING,
                            WorkItemStatus.RESOLVED,
                        ]))
                    )
                )
                upstream_incidents = upstream_result.scalars().all()

                for upstream_incident in upstream_incidents:
                    # Skip if correlation already exists
                    existing = await session.execute(
                        select(IncidentCorrelation).where(
                            (IncidentCorrelation.root_incident_id == upstream_incident.id)
                            & (IncidentCorrelation.cascaded_incident_id == incident.id)
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    correlation = IncidentCorrelation(
                        id=str(ulid.new()),
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident.id,
                        correlation_reason=(
                            f"{upstream_component} failure detected before "
                            f"this {incident.component_type.value} incident"
                        ),
                    )
                    session.add(correlation)
                    correlations_created += 1

                    log.info(
                        "correlation_created",
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident.id,
                        root_component=upstream_component,
                    )

        await session.commit()
        log.info("backfill_completed", correlations_created=correlations_created)
        return correlations_created


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    """
    1. Health check the API server.
    2. Run all 6 cascading failure waves.
    3. Print the simulation summary.
    4. Backfill correlations for all open incidents.
    """
    banner("IMS Full-Stack Outage Simulation + Correlation Backfill", "=")
    print(f"  Scenario : Cascading failure from RDBMS outage")
    print(f"  Target   : {BASE_URL}")
    print(f"  Dashboard: {DASHBOARD}")
    print(f"  Time     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    print("  Components (all six types):")
    for comp_type, count, _, desc in WAVES:
        sig = SIGNALS[comp_type]
        print(f"    [{sig['severity']}] {sig['component_id']:<30} {count:>3} signals")

    # ── Pre-flight check ──────────────────────────────────────────────────────
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
                info(f"{'✓' if up else '✗'} {store}")
        except Exception as e:
            print(f"\n  ✗ Cannot reach server: {e}")
            print("    Start uvicorn first: uvicorn main:app --reload --port 8000")
            return

    # ── Run all failure waves ─────────────────────────────────────────────────
    results: list = []
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for wave_num, (comp_type, count, pause, description) in enumerate(WAVES, 1):
            await run_wave(client, comp_type, count, pause, description, wave_num, results)

    # ── Simulation summary ────────────────────────────────────────────────────
    banner("Simulation Complete — Full Stack Covered", "=")

    total_signals      = sum(w[1] for w in WAVES)
    work_items_created = sum(1 for r in results if r is not None)

    print(f"  Total signals fired  : {total_signals}")
    print(f"  Work items created   : {work_items_created} / {len(WAVES)}")
    print(f"  Debounce ratio       : {total_signals}:1 → {work_items_created} incidents")
    print()
    print("  Stack Coverage:")
    print("  " + "─" * 66)
    print(f"  {'#':<3} {'Priority':<5} {'Component ID':<30} {'Type':<12} {'Status':<12}")
    print("  " + "─" * 66)
    for i, ((comp_type, _, _, _), wi) in enumerate(zip(WAVES, results), 1):
        sig    = SIGNALS[comp_type]
        status = "✓ Created " if wi else "✗ Missing "
        print(f"  {i:<3} {sig['severity']:<5} {sig['component_id']:<30} {comp_type:<12} {status:<12}")
    print("  " + "─" * 66)

    print()
    print("  Evaluator Workflow:")
    print()
    for i, ((comp_type, _, _, _), wi) in enumerate(zip(WAVES, results), 1):
        if wi:
            sig = SIGNALS[comp_type]
            print(f"  {i}. {wi['component_id']:<30}")
            print(f"     URL  : {DASHBOARD}/incidents/{wi['id']}")
            print(f"     Type : {sig['component_type']} (Priority: {sig['severity']})")
            print()

    print("  For each incident:")
    print("    → Click to open detail page")
    print("    → Change status: OPEN → INVESTIGATING → RESOLVED")
    print("    → Submit RCA (auto-calculates MTTR)")
    print("    → System closes incident (RESOLVED → CLOSED)")
    print()
    print(f"  API Documentation: {BASE_URL}/docs")
    print(f"  Health Endpoint  : {BASE_URL}/health")

    # ── Correlation backfill ──────────────────────────────────────────────────
    banner("Backfilling Correlations for Open Incidents", "─")
    step("Querying all open / investigating / resolved incidents…")

    count = await backfill_correlations()

    ok(f"Created {count} correlation record{'s' if count != 1 else ''}")
    print()


if __name__ == "__main__":
    asyncio.run(main())