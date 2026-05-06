from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings
import structlog

log = structlog.get_logger()

#The engine connects to the database; it creates a Connection Pool. This acts as a protective shield for MySQL
engine = create_async_engine(
    settings.mysql_url_async,
    pool_size=20,           # max 20 persistent connections
    max_overflow=10,        # 10 extra under burst
    pool_pre_ping=True,     # test connections before using them
    echo=False,
)
#Session is used to query and commit data (e.g., session.add(work_item)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

#SQLAlchemy 2.0 setup base class that every database table define (like WorkItem and RCA tables) will inherit from this Base class so SQLAlchemy knows how to map Python objects to MySQL tables
class Base(DeclarativeBase):
    pass

#exposes /health endpoint, This function executes SELECT 1, which is the lightest possible query you can send to a database. If MySQL is up, it returns 1. If it has crashed, it returns False
async def check_mysql() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        log.error("mysql_health_check_failed", error=str(e))
        return False
#Graceful Shutdown,engine.dispose() politely tells the connection pool to wait for current queries to finish, close all connections gracefully, and release the memory.
async def close_mysql():
    await engine.dispose()
    log.info("mysql_connection_closed")
