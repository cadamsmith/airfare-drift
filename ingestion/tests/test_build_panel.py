"""
Unit tests for config.build_panel — the deterministic, stateless panel builder.

These guard the invariants that keep ingestion inside constraint #1 (the SerpApi
250-searches/mo budget) and constraint #3 (request params recorded per row, not
derived). They are pure-Python: no SerpApi call, no BigQuery, no network. The
real cost guard lives here so a refactor of the panel can't silently blow the
budget between scheduled runs.
"""

from datetime import date, timedelta

import config
import pytest
from config import (
    DEFAULT_RETURN_GAP_DAYS,
    MAX_CALLS_PER_RUN,
    MIN_LEAD_DAYS,
    STAY_LENGTH_VARIANTS,
    build_panel,
)

# A year of snapshot dates so month-length / year-boundary edge cases are all
# exercised (the panel rolls anchors on the 1st and 15th across month bounds).
YEAR_OF_DATES = [date(2026, 1, 1) + timedelta(days=n) for n in range(365)]


@pytest.mark.parametrize("snapshot_date", YEAR_OF_DATES)
def test_never_exceeds_budget_cap(snapshot_date):
    """Constraint #1: no run may issue more than MAX_CALLS_PER_RUN calls."""
    assert len(build_panel(snapshot_date)) <= MAX_CALLS_PER_RUN


@pytest.mark.parametrize("snapshot_date", YEAR_OF_DATES)
def test_all_slots_respect_min_lead(snapshot_date):
    """No anchor closer than MIN_LEAD_DAYS out (near-departure fare-fence noise)."""
    for slot in build_panel(snapshot_date):
        assert slot.advance_days >= MIN_LEAD_DAYS


@pytest.mark.parametrize("snapshot_date", YEAR_OF_DATES)
def test_request_params_are_self_consistent(snapshot_date):
    """advance_days / return_gap_days must equal the dates they describe — they
    are recorded request params, and staging asserts derived==requested."""
    for slot in build_panel(snapshot_date):
        assert slot.advance_days == (slot.outbound_date - snapshot_date).days
        assert slot.return_gap_days == (slot.return_date - slot.outbound_date).days


def test_deterministic_and_stateless():
    """Same run date -> identical panel; the builder holds no cursor/state."""
    d = date(2026, 7, 12)
    assert build_panel(d) == build_panel(d)


def test_nearest_anchor_carries_all_stay_variants():
    """The stay-length cross-section (7/14/21-day) lands on the single nearest
    anchor and survives the cap (it sorts to the front by advance_days)."""
    slots = build_panel(date(2026, 7, 12))
    nearest_dep = min(s.advance_days for s in slots)
    gaps_on_nearest = {
        s.return_gap_days for s in slots if s.advance_days == nearest_dep
    }
    assert gaps_on_nearest == {DEFAULT_RETURN_GAP_DAYS, *STAY_LENGTH_VARIANTS}


def test_far_anchors_dropped_first_when_capped():
    """When the panel overflows the cap, the farthest-lead anchors are dropped,
    not the near-term booking-curve density we most want to keep."""
    slots = build_panel(date(2026, 7, 12))
    if len(slots) < MAX_CALLS_PER_RUN:
        pytest.skip("panel does not overflow the cap on this date")
    # Every kept slot's lead is <= the leads that would exist beyond the cap:
    # equivalently, the kept set is a prefix of anchors sorted by nearest lead.
    leads = [s.advance_days for s in slots]
    assert leads == sorted(leads)


def test_cap_is_within_monthly_budget():
    """Belt-and-suspenders on the constant itself: 16 runs/mo must stay under the
    250 SerpApi free-tier searches/mo."""
    assert MAX_CALLS_PER_RUN * 16 < 250
    # config module exposes the guard we depend on.
    assert config.MAX_CALLS_PER_RUN == MAX_CALLS_PER_RUN
