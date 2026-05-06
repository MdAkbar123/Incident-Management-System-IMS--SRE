from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from config import settings
import structlog

log = structlog.get_logger()

# The engine connects to the database; it creates a Connection Pool.
# This acts as a protective shield for MySQL.
engine = create_async_engine(
    settings.mysql_url_async,
    pool_size=20,           # max 20 persistent connections
    max_overflow=10,        # 10 extra under burst
    pool_pre_ping=True,     # test connections before using them
    echo=False,
)

# Force every raw DBAPI connection to operate in UTC the moment it is
# checked out of the pool.  This fires synchronously on the underlying
# sync driver (e.g. aiomysql / pymysql) before any async query runs,
# which is why we listen on engine.sync_engine.
#
# Without this, MySQL returns DATETIME columns in the server's local
# timezone (e.g. IST +05:30).  SQLAlchemy returns those values as
# naive datetimes (no tzinfo), so when our code later does
# `replace(tzinfo=timezone.utc)` it silently mislabels an IST timestamp
# as UTC — inflating MTTR by the UTC offset (~5h30m for IST).
#
# Setting the session timezone to UTC means:
#   - All DATETIME values written are stored as UTC.
#   - All DATETIME values read back are returned as UTC.
#   - naive datetimes from SQLAlchemy are genuinely UTC, so
#     `replace(tzinfo=timezone.utc)` is correct rather than harmful.
@event.listens_for(engine.sync_engine, "connect")
def _force_utc(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET time_zone = '+00:00'")
    cursor.close()
    log.debug("mysql_session_timezone_set_to_utc")


# Session is used to query and commit data (e.g., session.add(work_item)).
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# SQLAlchemy 2.0 base class that every database table definition
# (like WorkItem and RCA) inherits from, so SQLAlchemy knows how to
# map Python objects to MySQL tables.
class Base(DeclarativeBase):
    pass


# Exposes /health endpoint.
# Executes SELECT 1 — the lightest possible query.
# If MySQL is up it returns True; if it has crashed it returns False.
async def check_mysql() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("mysql_health_check_failed", error=str(e))
        return False


# Graceful shutdown.
# engine.dispose() waits for current queries to finish, closes all
# connections gracefully, and releases memory.
async def close_mysql():
    await engine.dispose()
    log.info("mysql_connection_closed")