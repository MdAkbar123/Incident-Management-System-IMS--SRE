"""
Phase 2 load test.
Run from the project root:
    python scripts/load_test.py
"""
import asyncio
import httpx
import time
from collections import Counter

BASE_URL = "http://localhost:8000"

SAMPLE_SIGNALS = [
    {
        "component_id": "CACHE_CLUSTER_01",
        "component_type": "CACHE",
        "error_code": "ERR_EVICTION_STORM",
        "severity": "P2",
        "latency_ms": 842,
        "message": "Eviction rate exceeded 90% threshold",
    },
    {
        "component_id": "RDBMS_PRIMARY_01",
        "component_type": "RDBMS",
        "error_code": "ERR_CONNECTION_POOL_EXHAUSTED",
        "severity": "P0",
        "latency_ms": 4200,
        "message": "Connection pool exhausted",
    },
    {
        "component_id": "API_GATEWAY_01",
        "component_type": "API",
        "error_code": "ERR_HIGH_5XX_RATE",
        "severity": "P1",
        "latency_ms": 1200,
        "message": "5xx error rate exceeded 10%",
    },
    {
        "component_id": "MCP_HOST_02",
        "component_type": "MCP_HOST",
        "error_code": "ERR_PROCESS_CRASH",
        "severity": "P0",
        "latency_ms": 0,
        "message": "MCP host process died unexpectedly",
    },
    {
        "component_id": "QUEUE_ORDERS_01",
        "component_type": "ASYNC_QUEUE",
        "error_code": "ERR_CONSUMER_LAG",
        "severity": "P1",
        "latency_ms": 300,
        "message": "Consumer lag exceeded 50,000 messages",
    },
]


async def send_signal(client: httpx.AsyncClient, signal: dict) -> int:
    try:
        r = await client.post("/ingest", json=signal, timeout=10.0)
        return r.status_code
    except Exception:
        return 0  # connection error


# ──────────────────────────────────────────────
# Test 1: Throughput — 10,000 concurrent signals
# ──────────────────────────────────────────────
async def test_throughput():
    print("\n" + "="*55)
    print("TEST 1: Throughput — 10,000 concurrent signals")
    print("="*55)

    signals = [
        SAMPLE_SIGNALS[i % len(SAMPLE_SIGNALS)]
        for i in range(10_000)
    ]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        start = time.perf_counter()
        results = await asyncio.gather(
            *[send_signal(client, s) for s in signals]
        )
        elapsed = time.perf_counter() - start

    counts = Counter(results)
    throughput = len(signals) / elapsed

    print(f"\nCompleted in : {elapsed:.2f}s")
    print(f"Throughput   : {throughput:,.0f} requests/sec")
    print(f"Status codes : {dict(counts)}")
    print(f"\n{'✓' if counts.get(202, 0) > 8000 else '✗'} "
          f"202 Accepted : {counts.get(202, 0):,}")
    print(f"{'~' if counts.get(503, 0) > 0 else '✓'} "
          f"503 Backpressure : {counts.get(503, 0):,}  "
          f"(expected only if queue filled)")
    print(f"{'✗' if counts.get(0, 0) > 0 else '✓'} "
          f"Connection errors : {counts.get(0, 0)}")


# ──────────────────────────────────────────────────
# Test 2: Rate limiter — 600 requests from one IP
# Expected: ~500 pass, ~100 get 429
# ──────────────────────────────────────────────────
async def test_rate_limiter():
    print("\n" + "="*55)
    print("TEST 2: Rate limiter — 600 requests from one IP")
    print("Expected: ~500 pass (202), ~100 blocked (429)")
    print("="*55)

    signal = SAMPLE_SIGNALS[0]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        results = await asyncio.gather(
            *[send_signal(client, signal) for _ in range(600)]
        )

    counts = Counter(results)
    accepted = counts.get(202, 0)
    rate_limited = counts.get(429, 0)

    print(f"\nStatus codes : {dict(counts)}")
    print(f"{'✓' if 400 <= accepted <= 600 else '✗'} "
          f"202 Accepted     : {accepted}")
    print(f"{'✓' if rate_limited > 0 else '✗'} "
          f"429 Rate limited : {rate_limited}  "
          f"(limiter {'working' if rate_limited > 0 else 'NOT triggered — check slowapi setup'})")


# ──────────────────────────────────────────────
# Test 3: Single signal — check response shape
# ──────────────────────────────────────────────
async def test_single_signal():
    print("\n" + "="*55)
    print("TEST 3: Single signal — response shape")
    print("="*55)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/ingest", json=SAMPLE_SIGNALS[0])

    print(f"\nStatus  : {r.status_code}")
    print(f"Response: {r.json()}")
    assert r.status_code == 202, f"Expected 202, got {r.status_code}"
    body = r.json()
    assert body["accepted"] is True
    assert "signal_id" in body
    assert "queue_depth" in body
    print("✓ Response shape correct")


# ──────────────────────────────────────────────
# Test 4: Invalid payload — should get 422
# ──────────────────────────────────────────────
async def test_validation():
    print("\n" + "="*55)
    print("TEST 4: Invalid payload — expect 422")
    print("="*55)

    bad_signals = [
        {},  # completely empty
        {"component_id": "X", "component_type": "INVALID_TYPE",
         "error_code": "E", "severity": "P0", "latency_ms": 0, "message": "test"},
        {"component_id": "X", "component_type": "CACHE",
         "error_code": "E", "severity": "P0", "latency_ms": -1, "message": "test"},
    ]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for bad in bad_signals:
            r = await client.post("/ingest", json=bad)
            status = "✓" if r.status_code == 422 else "✗"
            print(f"{status} Payload {str(bad)[:50]!r}... → {r.status_code}")


async def main():
    print("\nIMS Phase 2 — Load Test Suite")
    print("Make sure uvicorn is running on localhost:8000\n")

    # Verify server is up
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        try:
            r = await client.get("/health")
            print(f"Server health: {r.json()['status']}")
        except Exception:
            print("✗ Server not reachable. Start uvicorn first.")
            return

    await test_single_signal()
    await test_validation()
    await test_rate_limiter()
    await test_throughput()

    print("\n" + "="*55)
    print("Load test complete.")
    print("="*55 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
