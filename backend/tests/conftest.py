import pytest
from datetime import datetime, timezone, timedelta
from schemas.rca import RCACreate
from models import RootCauseCategory


# ── Reusable datetime fixtures ───────────────────────────

@pytest.fixture
def valid_start():
    return datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)

@pytest.fixture
def valid_end():
    return datetime(2026, 5, 3, 11, 30, 0, tzinfo=timezone.utc)

@pytest.fixture
def valid_rca_payload(valid_start, valid_end):
    """A fully valid RCACreate payload. Use as baseline in tests."""
    return {
        "start_time":          valid_start,
        "end_time":            valid_end,
        "root_cause_category": RootCauseCategory.INFRASTRUCTURE,
        "fix_applied":         "Increased connection pool size from 100 to 300.",
        "prevention_steps":    "Added alert at 70% pool usage threshold.",
    }
