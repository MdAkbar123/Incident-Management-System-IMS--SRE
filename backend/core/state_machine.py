from __future__ import annotations
from abc import ABC, abstractmethod
import structlog

log = structlog.get_logger()


class InvalidTransitionError(Exception):
    """
    Raised when a transition is attempted that the current
    state does not allow. Caught in the API layer and
    returned as HTTP 422.
    """
    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Cannot transition from {from_state} to {to_state}. "
            f"Invalid transition."
        )


class RCAMissingError(Exception):
    """
    Raised when CLOSED is attempted without a completed RCA.
    Separate from InvalidTransitionError so the API can
    return a more specific error message.
    """
    pass


# ── Base state ──────────────────────────────────────────

class WorkItemState(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """String name of this state — matches the DB enum value."""
        pass

    @abstractmethod
    def transition(self, target: str, has_rca: bool = False) -> WorkItemState:
        """
        Attempt to move to target state.
        Returns the new state object on success.
        Raises InvalidTransitionError or RCAMissingError on failure.
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}>"


# ── Concrete states ─────────────────────────────────────

class OpenState(WorkItemState):
    """
    Initial state. Set when the work item is first created.
    Can only move forward to INVESTIGATING.
    Cannot skip states.
    """

    @property
    def name(self) -> str:
        return "OPEN"

    def transition(self, target: str, has_rca: bool = False) -> WorkItemState:
        if target == "INVESTIGATING":
            log.info("state_transition", from_state=self.name, to_state=target)
            return InvestigatingState()
        raise InvalidTransitionError(self.name, target)


class InvestigatingState(WorkItemState):
    """
    An engineer has acknowledged the incident and is working on it.
    Can move to RESOLVED once a fix is applied.
    Cannot jump directly to CLOSED.
    """

    @property
    def name(self) -> str:
        return "INVESTIGATING"

    def transition(self, target: str, has_rca: bool = False) -> WorkItemState:
        if target == "RESOLVED":
            log.info("state_transition", from_state=self.name, to_state=target)
            return ResolvedState()
        raise InvalidTransitionError(self.name, target)


class ResolvedState(WorkItemState):
    """
    Fix has been applied. System is recovering.
    Can move to CLOSED only if a complete RCA exists.
    RCA submission (Phase 4) triggers this automatically.
    """

    @property
    def name(self) -> str:
        return "RESOLVED"

    def transition(self, target: str, has_rca: bool = False) -> WorkItemState:
        if target == "CLOSED":
            if not has_rca:
                raise RCAMissingError(
                    "Cannot close an incident without a completed RCA. "
                    "Submit the RCA form first."
                )
            log.info("state_transition", from_state=self.name, to_state=target)
            return ClosedState()
        raise InvalidTransitionError(self.name, target)


class ClosedState(WorkItemState):
    """
    Terminal state. No further transitions allowed.
    RCA is mandatory before reaching this state.
    """

    @property
    def name(self) -> str:
        return "CLOSED"

    def transition(self, target: str, has_rca: bool = False) -> WorkItemState:
        raise InvalidTransitionError(self.name, target)


# ── State registry ──────────────────────────────────────
# Maps DB enum string → state object.
# Used when loading a work item from MySQL to restore its state.

STATE_MAP: dict[str, WorkItemState] = {
    "OPEN":          OpenState(),
    "INVESTIGATING": InvestigatingState(),
    "RESOLVED":      ResolvedState(),
    "CLOSED":        ClosedState(),
}


def get_state(status_str: str) -> WorkItemState:
    """
    Restore state object from a string loaded from MySQL.
    Example: get_state("INVESTIGATING") → InvestigatingState()
    """
    state = STATE_MAP.get(status_str)
    if state is None:
        raise ValueError(f"Unknown status: {status_str!r}")
    return state
