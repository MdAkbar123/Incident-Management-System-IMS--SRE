"""
Tests for the WorkItem state machine.

Covers:
- All valid transitions pass and return the correct next state
- All invalid transitions raise InvalidTransitionError
- RESOLVED → CLOSED without RCA raises RCAMissingError
- RESOLVED → CLOSED with RCA passes
- CLOSED is a terminal state — no further transitions
- get_state() restores correct state from string
"""
import pytest

from core.state_machine import (
    OpenState,
    InvestigatingState,
    ResolvedState,
    ClosedState,
    InvalidTransitionError,
    RCAMissingError,
    get_state,
)


# ════════════════════════════════════════════════════════
# 1. VALID TRANSITIONS
# ════════════════════════════════════════════════════════

class TestValidTransitions:

    def test_open_to_investigating(self):
        state = OpenState()
        next_state = state.transition("INVESTIGATING")
        assert isinstance(next_state, InvestigatingState)
        assert next_state.name == "INVESTIGATING"

    def test_investigating_to_resolved(self):
        state = InvestigatingState()
        next_state = state.transition("RESOLVED")
        assert isinstance(next_state, ResolvedState)
        assert next_state.name == "RESOLVED"

    def test_resolved_to_closed_with_rca(self):
        """RESOLVED → CLOSED must succeed when has_rca=True."""
        state = ResolvedState()
        next_state = state.transition("CLOSED", has_rca=True)
        assert isinstance(next_state, ClosedState)
        assert next_state.name == "CLOSED"

    def test_full_lifecycle(self):
        """Walk through the entire OPEN → CLOSED lifecycle."""
        state = OpenState()
        state = state.transition("INVESTIGATING")
        state = state.transition("RESOLVED")
        state = state.transition("CLOSED", has_rca=True)
        assert state.name == "CLOSED"


# ════════════════════════════════════════════════════════
# 2. INVALID TRANSITIONS — must raise InvalidTransitionError
# ════════════════════════════════════════════════════════

class TestInvalidTransitions:

    def test_open_cannot_go_to_resolved(self):
        with pytest.raises(InvalidTransitionError) as exc:
            OpenState().transition("RESOLVED")
        assert exc.value.from_state == "OPEN"
        assert exc.value.to_state   == "RESOLVED"

    def test_open_cannot_go_to_closed(self):
        with pytest.raises(InvalidTransitionError) as exc:
            OpenState().transition("CLOSED")
        assert exc.value.from_state == "OPEN"
        assert exc.value.to_state   == "CLOSED"

    def test_open_cannot_go_to_open(self):
        """Self-transition must be rejected."""
        with pytest.raises(InvalidTransitionError):
            OpenState().transition("OPEN")

    def test_investigating_cannot_go_to_open(self):
        """Backward transition must be rejected."""
        with pytest.raises(InvalidTransitionError) as exc:
            InvestigatingState().transition("OPEN")
        assert exc.value.from_state == "INVESTIGATING"
        assert exc.value.to_state   == "OPEN"

    def test_investigating_cannot_go_to_closed(self):
        """Cannot skip RESOLVED."""
        with pytest.raises(InvalidTransitionError) as exc:
            InvestigatingState().transition("CLOSED")
        assert exc.value.from_state == "INVESTIGATING"
        assert exc.value.to_state   == "CLOSED"

    def test_resolved_cannot_go_to_open(self):
        with pytest.raises(InvalidTransitionError):
            ResolvedState().transition("OPEN")

    def test_resolved_cannot_go_to_investigating(self):
        with pytest.raises(InvalidTransitionError):
            ResolvedState().transition("INVESTIGATING")

    def test_closed_cannot_go_anywhere(self):
        """CLOSED is terminal — every transition must raise."""
        terminal = ClosedState()
        for target in ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"]:
            with pytest.raises(InvalidTransitionError) as exc:
                terminal.transition(target)
            assert exc.value.from_state == "CLOSED"

    def test_unknown_target_state_rejected(self):
        """An unrecognised target string must raise."""
        with pytest.raises(InvalidTransitionError):
            OpenState().transition("BANANA")


# ════════════════════════════════════════════════════════
# 3. RCA GUARD
# ════════════════════════════════════════════════════════

class TestRCAGuard:

    def test_resolved_to_closed_without_rca_raises(self):
        """
        The most critical business rule:
        RESOLVED → CLOSED without RCA must raise RCAMissingError,
        NOT InvalidTransitionError.
        """
        with pytest.raises(RCAMissingError) as exc:
            ResolvedState().transition("CLOSED", has_rca=False)
        assert "RCA" in str(exc.value)

    def test_resolved_to_closed_rca_missing_is_not_invalid_transition(self):
        """
        RCAMissingError and InvalidTransitionError are distinct.
        The caller needs to return different HTTP responses for each.
        """
        with pytest.raises(RCAMissingError):
            ResolvedState().transition("CLOSED", has_rca=False)
        # Confirm it does NOT raise InvalidTransitionError for this case
        # (InvalidTransitionError would mean the transition is structurally wrong,
        #  RCAMissingError means it's valid but a precondition is unmet)

    def test_resolved_to_closed_default_has_rca_false(self):
        """
        has_rca defaults to False — calling without it
        must also raise RCAMissingError.
        """
        with pytest.raises(RCAMissingError):
            ResolvedState().transition("CLOSED")


# ════════════════════════════════════════════════════════
# 4. STATE REGISTRY — get_state()
# ════════════════════════════════════════════════════════

class TestStateRegistry:

    @pytest.mark.parametrize("status,expected_class", [
        ("OPEN",          OpenState),
        ("INVESTIGATING", InvestigatingState),
        ("RESOLVED",      ResolvedState),
        ("CLOSED",        ClosedState),
    ])
    def test_get_state_returns_correct_type(self, status, expected_class):
        """
        get_state() is called when loading a work item from MySQL.
        Every valid status string must restore the correct state object.
        """
        state = get_state(status)
        assert isinstance(state, expected_class)

    def test_get_state_unknown_raises(self):
        """Unknown status strings must raise ValueError."""
        with pytest.raises(ValueError) as exc:
            get_state("NONEXISTENT")
        assert "NONEXISTENT" in str(exc.value)

    def test_state_names_match_strings(self):
        """Each state's .name must match the string used to look it up."""
        for status in ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"]:
            state = get_state(status)
            assert state.name == status
