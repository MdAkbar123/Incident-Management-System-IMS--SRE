import redis.asyncio as aioredis
from config import settings
import structlog

log = structlog.get_logger()

_redis: aioredis.Redis | None = None

def get_redis() -> aioredis.Redis:
    return _redis

async def connect_redis():
    global _redis
    _redis = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,  # always get strings back, not bytes
    )
    log.info("redis_connected")

async def check_redis() -> bool:
    try:
        await _redis.ping()
        return True
    except Exception as e:
        log.error("redis_health_check_failed", error=str(e))
        return False

async def close_redis():
    await _redis.aclose()
    log.info("redis_connection_closed")
