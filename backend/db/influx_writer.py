from influxdb_client import Point
from datetime import datetime, timezone
import structlog

from db.influx import get_influx
from config import settings
from core.retry import with_retry

log = structlog.get_logger()


@with_retry(max_attempts=3, backoff=0.5)
async def write_incident_resolution(
    work_item_id: str,
    component_type: str,
    priority: str,
    mttr_seconds: float,
    signal_count: int,
    root_cause_category: str,
):
    """
    Write a resolution metric to InfluxDB when an incident is CLOSED.
    Tagged by component_type and priority for aggregation queries.
    """
    client = get_influx()
    write_api = client.write_api()

    point = (
        Point("incident_resolution")
        .tag("component_type", component_type)
        .tag("priority", priority)
        .field("mttr_seconds", float(mttr_seconds))
        .field("signal_count", int(signal_count))
        .field("root_cause_category", root_cause_category)
        .field("work_item_id", work_item_id)
        .time(datetime.now(timezone.utc))
    )

    await write_api.write(
        bucket=settings.influx_bucket,
        org=settings.influx_org,
        record=point,
    )

    log.info(
        "influx_resolution_written",
        work_item_id=work_item_id,
        priority=priority,
        mttr_seconds=mttr_seconds,
    )


@with_retry(max_attempts=3, backoff=0.5)
async def write_throughput_metric(
    signals_per_sec: float,
    queue_depth: int,
    dropped_count: int,
):
    """
    Write throughput metrics every 5 seconds.
    Called from metrics.py metrics_printer task.
    """
    client = get_influx()
    write_api = client.write_api()

    point = (
        Point("signal_throughput")
        .field("signals_per_sec", float(signals_per_sec))
        .field("queue_depth", int(queue_depth))
        .field("dropped_503s", int(dropped_count))
        .time(datetime.now(timezone.utc))
    )

    await write_api.write(
        bucket=settings.influx_bucket,
        org=settings.influx_org,
        record=point,
    )
