"""
Fixed route list and the one shared query convention (see CLAUDE.md "Route list").
Ingestion is the source of truth for these constants.
"""

# --- The one consistent query convention ------------------------------------
# ~30-day advance purchase, fixed 1-week return gap, USD, round-trip. Identical
# for every route so snapshots are comparable across routes. 30 days sits in the
# active revenue-management zone (prices actually move day-to-day, so there's a
# signal to detect) for both the domestic and international routes, and off the
# 21-day advance-purchase fare fence.
#
# CONSCIOUS OMISSION (un-backfillable — decided, not overlooked): because the
# advance window is a rolling constant, every run queries a DIFFERENT travel_date.
# We never re-observe the same trip as it approaches departure, so there is NO
# booking-curve signal — only a constant-advance regime series ("is this route
# anomalous vs. its own history"). Adding booking curves later means ALSO
# capturing a set of FIXED future dates (extra API cost, multiplicative); it
# cannot be reconstructed after the fact. Deliberately deferred to Phase 2.
ADVANCE_DAYS = 30
RETURN_GAP_DAYS = 7
CURRENCY = "USD"

# --- The 10 routes, chosen for behavioral diversity -------------------------
# Controls that should stay quiet + spiky/seasonal routes the anomaly layer
# should fire on. (origin, destination).
ROUTES = [
    ("ATL", "CMN"),  # anchor — thin seasonal intl, anomaly-rich
    ("JFK", "CMN"),  # natural-experiment pair with ATL-CMN (per-route baselines)
    ("BOS", "KEF"),  # extreme seasonality → clear regime changes
    ("LAX", "JFK"),  # competitive trunk — stable baseline (control)
    ("ATL", "LAX"),  # high-volume domestic — low volatility (control)
    ("ATL", "ORD"),  # business trunk — minimal seasonality (control)
    ("ATL", "MCO"),  # LCC-heavy leisure — holiday spikes
    ("DEN", "CUN"),  # intl leisure — strong holiday seasonality
    ("ATL", "SJU"),  # caribbean leisure — high variance
    ("ATL", "LHR"),  # long-haul premium — fuel/currency exposure
]
