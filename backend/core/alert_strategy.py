from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()


@dataclass
class WorkItemSummary:
    """
    Minimal data the alert strategies need.
    Passed in from the worker after work item creation.
    """
    id: str
    component_id: str
    component_type: str
    priority: str
    first_signal_id: str
    created_at: datetime


# ── Base strategy ───────────────────────────────────────

class AlertStrategy(ABC):

    @abstractmethod
    async def send(self, work_item: WorkItemSummary) -> None:
        """
        Send an alert for the given work item.
        In production: call PagerDuty / Slack / OpsGenie APIs.
        In this project: structured log output.
        """
        pass


# ── Concrete strategies ─────────────────────────────────

class P0Strategy(AlertStrategy):
    """
    P0 — Critical. RDBMS and MCP_HOST failures.
    In production: wake the on-call engineer immediately (phone call).
    Simulated here as a CRITICAL log + webhook stub.
    """

    async def send(self, work_item: WorkItemSummary) -> None:
        log.critical(
            "ALERT_P0_CRITICAL",
            work_item_id=work_item.id,
            component_id=work_item.component_id,
            component_type=work_item.component_type,
            message=(
                f"[P0 — CRITICAL] {work_item.component_id} is DOWN. "
                f"Immediate response required. Page on-call now."
            ),
            triggered_at=datetime.now(timezone.utc).isoformat(),
        )
        print(
            f"\n{'='*60}\n"
            f"  🚨 P0 ALERT — {work_item.component_id} IS DOWN\n"
            f"  Work Item : {work_item.id}\n"
            f"  Type      : {work_item.component_type}\n"
            f"  Action    : Page on-call immediately\n"
            f"{'='*60}\n"
        )


class P1Strategy(AlertStrategy):
    """
    P1 — High severity. API and ASYNC_QUEUE failures.
    In production: Slack alert + OpsGenie notification.
    """

    async def send(self, work_item: WorkItemSummary) -> None:
        log.error(
            "ALERT_P1_HIGH",
            work_item_id=work_item.id,
            component_id=work_item.component_id,
            component_type=work_item.component_type,
            message=(
                f"[P1 — HIGH] {work_item.component_id} is degraded. "
                f"Investigate within 15 minutes."
            ),
            triggered_at=datetime.now(timezone.utc).isoformat(),
        )
        print(
            f"\n{'─'*60}\n"
            f"  ⚠️  P1 ALERT — {work_item.component_id} DEGRADED\n"
            f"  Work Item : {work_item.id}\n"
            f"  Type      : {work_item.component_type}\n"
            f"  Action    : Investigate within 15 minutes\n"
            f"{'─'*60}\n"
        )


class P2Strategy(AlertStrategy):
    """
    P2 — Medium severity. CACHE and NOSQL failures.
    In production: Slack notification only, no page.
    """

    async def send(self, work_item: WorkItemSummary) -> None:
        log.warning(
            "ALERT_P2_MEDIUM",
            work_item_id=work_item.id,
            component_id=work_item.component_id,
            component_type=work_item.component_type,
            message=(
                f"[P2 — MEDIUM] {work_item.component_id} is impacted. "
                f"Monitor and investigate when able."
            ),
            triggered_at=datetime.now(timezone.utc).isoformat(),
        )
        print(
            f"\n{'·'*60}\n"
            f"  📋 P2 ALERT — {work_item.component_id} IMPACTED\n"
            f"  Work Item : {work_item.id}\n"
            f"  Type      : {work_item.component_type}\n"
            f"  Action    : Monitor, investigate when able\n"
            f"{'·'*60}\n"
        )


# ── Dispatcher ──────────────────────────────────────────

# Priority mapping — component_type → priority
# Used by the worker to set work item priority
PRIORITY_MAP: dict[str, str] = {
    "RDBMS":       "P0",
    "MCP_HOST":    "P0",
    "API":         "P1",
    "ASYNC_QUEUE": "P1",
    "CACHE":       "P2",
    "NOSQL":       "P2",
}


class AlertDispatcher:
    """
    Selects and executes the correct alert strategy
    based on the work item's priority.
    """

    _strategies: dict[str, AlertStrategy] = {
        "P0": P0Strategy(),
        "P1": P1Strategy(),
        "P2": P2Strategy(),
    }

    async def dispatch(self, work_item: WorkItemSummary) -> None:
        strategy = self._strategies.get(work_item.priority)
        if strategy is None:
            log.error("unknown_priority", priority=work_item.priority)
            return
        await strategy.send(work_item)


# Singleton — import this everywhere
alert_dispatcher = AlertDispatcher()
