from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import structlog

from db.mysql   import check_mysql, close_mysql
from db.mongo   import connect_mongo, close_mongo
from db.redis   import connect_redis, close_redis
from db.influx  import connect_influx, close_influx

from workers.queue    import create_queue
from workers.consumer import start_worker_pool, stop_worker_pool
from metrics          import metrics_printer

from middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from routers.health    import router as health_router
from routers.ingest    import router as ingest_router
from routers.incidents import router as incidents_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    log.info("ims_starting")

    # 1. Connect all stores
    await connect_mongo()
    await connect_redis()
    await connect_influx()
    mysql_ok = await check_mysql()
    if not mysql_ok:
        raise RuntimeError("MySQL unreachable on startup. Aborting.")
    log.info("all_stores_connected")

    # 2. Create the shared queue
    queue = create_queue()
    log.info("queue_created", maxsize=queue.maxsize)

    # 3. Start worker pool
    worker_tasks = await start_worker_pool()

    # 4. Start throughput metrics printer
    import asyncio
    metrics_task = asyncio.create_task(
        metrics_printer(queue),
        name="ims-metrics"
    )

    log.info("ims_ready")
    yield  # ── App runs here ──

    # ── Shutdown ──
    log.info("ims_shutting_down")

    # Stop metrics printer first
    metrics_task.cancel()

    # Drain queue then stop workers
    await stop_worker_pool(worker_tasks)

    # Close all DB connections
    await close_mongo()
    await close_redis()
    await close_influx()
    await close_mysql()

    log.info("ims_stopped")


app = FastAPI(
    title="Incident Management System",
    version="0.3.0",
    lifespan=lifespan,
)

# ── Rate limiter setup ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Routers ──
app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(incidents_router)


@app.get("/", tags=["root"])
async def root():
    return {"service": "IMS", "version": "0.3.0", "docs": "/docs"}
