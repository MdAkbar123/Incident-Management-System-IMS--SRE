from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from config import settings
import structlog

log = structlog.get_logger()

_client: InfluxDBClientAsync | None = None

def get_influx() -> InfluxDBClientAsync:
    return _client

async def connect_influx():
    global _client
    _client = InfluxDBClientAsync(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )
    log.info("influx_connected")

async def check_influx() -> bool:
    try:
        ready = await _client.ping()
        return ready
    except Exception as e:
        log.error("influx_health_check_failed", error=str(e))
        return False

async def close_influx():
    await _client.close()
    log.info("influx_connection_closed")
