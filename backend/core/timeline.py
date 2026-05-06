"""
Timeline Service
================
Collects and stores signal processing events in real-time.

Timeline tracks the journey of signals through the system:
  - Signal received (batch)
  - Debounce check performed
  - Work item created
  - Alert dispatched
  - Cache updated
  - Data persisted

This provides visualization of concurrency & debounce in action.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import structlog

log = structlog.get_logger()


class TimelineEvent:
    """Single event in the timeline."""
    
    def __init__(
        self,
        event_type: str,
        timestamp: Optional[datetime] = None,
        **kwargs: Any,
    ):
        self.event_type = event_type
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.data = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }


class TimelineCollector:
    """
    In-memory timeline collector during signal processing.
    Events are stored in Redis and persisted to MongoDB on incident close.
    """
    
    def __init__(self, work_item_id: str):
        self.work_item_id = work_item_id
        self.events: List[TimelineEvent] = []
        self.start_time = datetime.now(timezone.utc)
    
    def add_event(
        self,
        event_type: str,
        **kwargs: Any,
    ) -> None:
        """
        Record a timeline event.
        
        Args:
            event_type: Type of event (signal_received, debounce_check, work_item_created, etc.)
            **kwargs: Event-specific data (count, result, alert_type, etc.)
        """
        event = TimelineEvent(event_type, **kwargs)
        self.events.append(event)
        
        log.debug(
            "timeline_event_recorded",
            work_item_id=self.work_item_id,
            event_type=event_type,
            **kwargs,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert timeline to JSON-serializable dict."""
        duration_ms = (
            (datetime.now(timezone.utc) - self.start_time).total_seconds() * 1000
        )
        
        return {
            "work_item_id": self.work_item_id,
            "started_at": self.start_time.isoformat(),
            "duration_ms": int(duration_ms),
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get timeline summary (for quick stats)."""
        signal_events = [e for e in self.events if e.event_type == "signal_received"]
        total_signals = sum(e.data.get("count", 1) for e in signal_events)
        
        return {
            "total_signals": total_signals,
            "total_events": len(self.events),
            "signal_batches": len(signal_events),
            "created_at": self.start_time.isoformat(),
        }


# Global timeline registry (in-memory during processing)
_timelines: Dict[str, TimelineCollector] = {}


def get_or_create_timeline(work_item_id: str) -> TimelineCollector:
    """Get or create a timeline collector for a work item."""
    if work_item_id not in _timelines:
        _timelines[work_item_id] = TimelineCollector(work_item_id)
    return _timelines[work_item_id]


def get_timeline(work_item_id: str) -> Optional[TimelineCollector]:
    """Get existing timeline or None."""
    return _timelines.get(work_item_id)


def remove_timeline(work_item_id: str) -> Optional[TimelineCollector]:
    """Remove and return timeline (after persisting)."""
    return _timelines.pop(work_item_id, None)


async def persist_timeline_to_redis(
    redis_client: Any,
    work_item_id: str,
) -> None:
    """
    Persist timeline to Redis for quick retrieval.
    Expires after 1 hour.
    """
    timeline = get_timeline(work_item_id)
    if not timeline:
        return
    
    key = f"timeline:{work_item_id}"
    value = json.dumps(timeline.to_dict())
    
    await redis_client.setex(key, 3600, value)  # TTL: 1 hour
    
    log.debug(
        "timeline_persisted_to_redis",
        work_item_id=work_item_id,
        events=len(timeline.events),
    )


async def persist_timeline_to_mongo(
    mongo_db: Any,
    work_item_id: str,
) -> None:
    """
    Persist timeline to MongoDB for permanent history.
    Called when incident moves to CLOSED.
    """
    timeline = get_timeline(work_item_id)
    if not timeline:
        return
    
    timeline_doc = timeline.to_dict()
    timeline_doc["created_at"] = datetime.now(timezone.utc)
    
    await mongo_db.timelines.insert_one(timeline_doc)
    
    log.info(
        "timeline_persisted_to_mongo",
        work_item_id=work_item_id,
        events=len(timeline.events),
    )
