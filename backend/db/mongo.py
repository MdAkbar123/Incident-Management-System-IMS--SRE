from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
import structlog

log = structlog.get_logger()

_client: AsyncIOMotorClient | None = None

def get_mongo_client() -> AsyncIOMotorClient:
    return _client

def get_db():
    return _client[settings.mongo_db]

async def connect_mongo():
    global _client
    _client = AsyncIOMotorClient(
        settings.mongo_uri,
        maxPoolSize=50,
        serverSelectionTimeoutMS=5000,
    )
    # Create indexes on startup — safe to call repeatedly
    db = _client[settings.mongo_db]
    await db.signals.create_index("work_item_id")
    await db.signals.create_index([("component_id", 1), ("timestamp", -1)])
    log.info("mongo_connected")

async def check_mongo() -> bool:
    try:
        await _client.admin.command("ping")
        return True
    except Exception as e:
        log.error("mongo_health_check_failed", error=str(e))
        return False

async def close_mongo():
    _client.close()
    log.info("mongo_connection_closed")
