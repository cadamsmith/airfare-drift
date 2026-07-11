"""
Single-route (ATL–CMN) panel definition and query convention.
See CLAUDE.md "The route: ATL–CMN" and "Modeling layers".

Ingestion is the source of truth for the route and for how each run's panel of
(departure, return) queries is built.
"""

from datetime import date, timedelta
from typing import NamedTuple

# --- The single route -------------------------------------------------------
# Depth over breadth: the whole SerpApi budget funds ONE route. ATL–CMN is a
# thin, connecting-only transatlantic market (no nonstop — RAM doesn't fly it),
# so a single call already returns a routing/carrier/price-dispersion cross-
# section worth modeling. Economy only (travel_class is a paid request param).
ORIGIN = "ATL"
DESTINATION = "CMN"
CURRENCY = "USD"

# --- Panel convention -------------------------------------------------------
# Each run queries a PANEL of fixed future departure dates, re-observed every
# run. Because the same calendar anchors recur across runs, each anchor's lead
# time shrinks ~2 days per run and traces its own booking curve down toward
# departure; as an anchor nears departure it drops out (MIN_LEAD_DAYS) and a new
# far anchor rotates in. The spread of anchors gives cross-sectional lead-time
# coverage from day one; spanning several months gives seasonality coverage that
# fills over the year. Panel generation is deterministic and STATELESS (a pure
# function of the run date) — no cursor table to keep in sync.
#
# This RESOLVES the earlier "conscious omission": the old rolling-30-day-advance
# convention never re-observed a fixed trip, so it captured no booking curve.
# The panel does — that is the whole point of the single-route pivot.
MIN_LEAD_DAYS = 14           # don't track inside 2 weeks (near-departure noise / fare fences)
NEAR_MONTHS = 3              # months 0..2: anchors on the 1st AND 15th (dense near-term leads)
FAR_MONTHS = 6               # next 6 months: 15th only (seasonal spread)
DEFAULT_RETURN_GAP_DAYS = 7  # baseline stay length
STAY_LENGTH_VARIANTS = (14, 21)  # extra return gaps, applied to the nearest anchor only

# Hard budget guard (constraint #1). 15–16 runs/mo × MAX_CALLS_PER_RUN must stay
# well under the 250 SerpApi searches/mo free tier, leaving margin for dev/testing
# that draws from the same pool: 12 × 16 = 192/mo → ~58/mo headroom.
MAX_CALLS_PER_RUN = 12


class PanelSlot(NamedTuple):
    """One (departure, return) query for a run. advance_days/return_gap_days are
    the request parameters we chose — recorded per row, not derived analytics."""
    outbound_date: date
    return_date: date
    return_gap_days: int
    advance_days: int  # lead time at request = outbound_date - snapshot_date


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = (month - 1) + n
    return year + idx // 12, idx % 12 + 1


def build_panel(snapshot_date: date) -> list[PanelSlot]:
    """
    Deterministic, stateless panel for one run: fixed month-anchor departure
    dates (1st + 15th near-term, 15th far-term), filtered to >= MIN_LEAD_DAYS
    out, plus stay-length variants on the nearest anchor — capped to
    MAX_CALLS_PER_RUN, dropping the FARTHEST anchors first so near-term booking-
    curve density (the most valuable, fastest-moving region) is preserved.
    """
    anchors: list[tuple[date, int]] = []
    for offset in range(NEAR_MONTHS + FAR_MONTHS):
        year, month = _add_months(snapshot_date.year, snapshot_date.month, offset)
        anchor_days = (1, 15) if offset < NEAR_MONTHS else (15,)
        for day in anchor_days:
            dep = date(year, month, day)
            lead = (dep - snapshot_date).days
            if lead >= MIN_LEAD_DAYS:
                anchors.append((dep, lead))
    anchors.sort(key=lambda a: a[1])  # nearest lead first

    slots = [
        PanelSlot(dep, dep + timedelta(days=DEFAULT_RETURN_GAP_DAYS),
                  DEFAULT_RETURN_GAP_DAYS, lead)
        for dep, lead in anchors
    ]
    if anchors:  # stay-length cross-section on the single nearest anchor
        nearest_dep, nearest_lead = anchors[0]
        for gap in STAY_LENGTH_VARIANTS:
            slots.append(PanelSlot(nearest_dep, nearest_dep + timedelta(days=gap),
                                   gap, nearest_lead))

    # Budget guard: keep nearest-lead slots (incl. the nearest anchor's stay
    # variants), drop the farthest.
    slots.sort(key=lambda s: (s.advance_days, s.return_gap_days))
    return slots[:MAX_CALLS_PER_RUN]
