"""
Tests for RCACreate Pydantic validation.

Covers:
- Valid payload passes
- Each required field missing → ValidationError
- Blank / too-short strings rejected
- end_time <= start_time rejected
- MTTR calculation correct
- Root cause category enum validation
"""
import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from schemas.rca import RCACreate
from models import RootCauseCategory


# ── Helper ───────────────────────────────────────────────

def make_rca(**overrides):
    """
    Build an RCACreate from the valid baseline,
    applying any overrides. Pass field=None to
    omit that field entirely.
    """
    base = {
        "start_time":          datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc),
        "end_time":            datetime(2026, 5, 3, 11, 30, 0, tzinfo=timezone.utc),
        "root_cause_category": RootCauseCategory.INFRASTRUCTURE,
        "fix_applied":         "Increased connection pool size from 100 to 300.",
        "prevention_steps":    "Added alert at 70% pool usage threshold.",
    }
    for k, v in overrides.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return RCACreate(**base)


# ════════════════════════════════════════════════════════
# 1. VALID PAYLOAD
# ════════════════════════════════════════════════════════

class TestValidPayload:

    def test_valid_rca_passes(self):
        """Baseline — a fully valid payload must not raise."""
        rca = make_rca()
        assert rca.fix_applied.startswith("Increased")
        assert rca.root_cause_category == RootCauseCategory.INFRASTRUCTURE

    def test_all_root_cause_categories_accepted(self):
        """Every enum value in RootCauseCategory must be accepted."""
        for category in RootCauseCategory:
            rca = make_rca(root_cause_category=category)
            assert rca.root_cause_category == category


# ════════════════════════════════════════════════════════
# 2. REQUIRED FIELDS — each missing field → ValidationError
# ════════════════════════════════════════════════════════

class TestRequiredFields:

    def test_missing_start_time_rejected(self):
        with pytest.raises(ValidationError) as exc:
            make_rca(start_time=None)
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "start_time" in fields

    def test_missing_end_time_rejected(self):
        with pytest.raises(ValidationError) as exc:
            make_rca(end_time=None)
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "end_time" in fields

    def test_missing_root_cause_category_rejected(self):
        with pytest.raises(ValidationError) as exc:
            make_rca(root_cause_category=None)
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "root_cause_category" in fields

    def test_missing_fix_applied_rejected(self):
        with pytest.raises(ValidationError) as exc:
            make_rca(fix_applied=None)
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "fix_applied" in fields

    def test_missing_prevention_steps_rejected(self):
        with pytest.raises(ValidationError) as exc:
            make_rca(prevention_steps=None)
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "prevention_steps" in fields


# ════════════════════════════════════════════════════════
# 3. BLANK / TOO-SHORT STRINGS
# ════════════════════════════════════════════════════════

class TestStringValidation:

    def test_fix_applied_too_short_rejected(self):
        """fix_applied requires min_length=10."""
        with pytest.raises(ValidationError) as exc:
            make_rca(fix_applied="short")
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "fix_applied" in fields

    def test_prevention_steps_too_short_rejected(self):
        """prevention_steps requires min_length=10."""
        with pytest.raises(ValidationError) as exc:
            make_rca(prevention_steps="short")
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "prevention_steps" in fields

    def test_fix_applied_exactly_10_chars_accepted(self):
        """Exactly at the min_length boundary must pass."""
        rca = make_rca(fix_applied="1234567890")
        assert len(rca.fix_applied) == 10

    def test_invalid_root_cause_category_rejected(self):
        """An unknown string for root_cause_category must raise."""
        with pytest.raises(ValidationError) as exc:
            make_rca(root_cause_category="NotARealCategory")
        errors = exc.value.errors()
        fields = [e["loc"][-1] for e in errors]
        assert "root_cause_category" in fields


# ════════════════════════════════════════════════════════
# 4. TIMESTAMP VALIDATION
# ════════════════════════════════════════════════════════

class TestTimestampValidation:

    def test_end_time_before_start_time_rejected(self):
        """end_time < start_time must raise with a clear message."""
        start = datetime(2026, 5, 3, 11, 30, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 5, 3, 10, 0,  0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError) as exc:
            make_rca(start_time=start, end_time=end)
        # Confirm the validator message is present
        error_text = str(exc.value)
        assert "end_time" in error_text
        assert "start_time" in error_text

    def test_end_time_equal_to_start_time_rejected(self):
        """end_time == start_time (zero duration) must also raise."""
        same = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            make_rca(start_time=same, end_time=same)

    def test_end_time_one_second_after_start_accepted(self):
        """Minimum valid duration — 1 second gap must pass."""
        start = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
        end   = start + timedelta(seconds=1)
        rca = make_rca(start_time=start, end_time=end)
        assert rca.end_time > rca.start_time


# ════════════════════════════════════════════════════════
# 5. MTTR CALCULATION
# ════════════════════════════════════════════════════════

class TestMTTRCalculation:
    """
    MTTR is calculated in the API layer from (end_time - start_time).
    These tests verify the raw time difference the model exposes,
    which the router converts to mttr_seconds.
    """

    def test_mttr_90_minutes(self):
        """1h 30m → 5400 seconds."""
        start = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 5, 3, 11, 30, 0, tzinfo=timezone.utc)
        rca   = make_rca(start_time=start, end_time=end)
        mttr  = (rca.end_time - rca.start_time).total_seconds()
        assert mttr == 5400.0

    def test_mttr_exactly_1_hour(self):
        """1h → 3600 seconds."""
        start = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 5, 3, 11, 0, 0, tzinfo=timezone.utc)
        rca   = make_rca(start_time=start, end_time=end)
        mttr  = (rca.end_time - rca.start_time).total_seconds()
        assert mttr == 3600.0

    def test_mttr_30_seconds(self):
        """Very short incident — 30 seconds must calculate correctly."""
        start = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
        end   = start + timedelta(seconds=30)
        rca   = make_rca(start_time=start, end_time=end)
        mttr  = (rca.end_time - rca.start_time).total_seconds()
        assert mttr == 30.0

    def test_mttr_multi_day(self):
        """Long incident spanning multiple days."""
        start = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 5, 3, 8, 0, 0, tzinfo=timezone.utc)
        rca   = make_rca(start_time=start, end_time=end)
        mttr  = (rca.end_time - rca.start_time).total_seconds()
        assert mttr == 172_800.0   # 48 hours
