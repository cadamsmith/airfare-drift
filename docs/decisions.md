# Design decisions & rationale

Load-on-demand background for **Airfare Drift**. Read this when onboarding, when a
decision feels ambiguous, or before proposing anything that would reverse a settled
choice (route count, fare source, consumer scope). CLAUDE.md carries the live
constraints and status; this file carries the *why*.

## Why one route (and why it's the stronger portfolio piece)

- **The control moved inside the route.** The multi-route version needed a *portfolio* of routes as its control group (stable routes stay quiet, spiky ones fire). Here the control is the model's own expectation: **observed fare vs. the fitted booking-curve + seasonality surface**, and the anomaly is the residual. That's a cleaner statistical story — deviation from a fitted model, not a comparison across heterogeneous routes.
- **ATL–CMN is a genuinely interesting market to model.** Verified against real captured data: **no nonstop exists** (Royal Air Maroc doesn't fly it), so it's a *connecting market* — the same trip routes via Montreal (Air Canada), Paris (Air France), JFK, etc., across multiple carriers, with wide price dispersion ($1,132→$1,769 in one snapshot). The competitive microstructure is **routing/hub/carrier competition**, richer than a single-carrier price series.
- **The whole SerpApi budget now funds one route**, so we can sample a dense fixed-date **panel** (many departure dates × lead times) — the exact data a booking-curve model is starved for. Single-route focus and the model's data-hunger resolve each other.
- **Authentic hook:** the personal motivation (family in Morocco) is a real interview story, but the deliverable is an *analytics/engineering* showcase — not a booking tool.

## What the signal is (and isn't)

The batch pipeline is **not** a live price quote and must never be presented as one — Google Flights/Hopper own "what's the price right now." What this project owns, computed transparently with warehouse rigor: **"is ATL–CMN pricing normally, given the lead time, the season, and the route's own history — and if not, why?"** Every number in any UI carries an explicit **"as of <observation timestamp>"**. The every-2-day cadence is fine for this: a fitted surface + regime signal moves slowly, so a ≤2-day-old observation is a valid statement about *behavior*, not a transaction price. There is **no consumer buy/wait recommendation** (dropped with the multi-route plan) — the deliverable is the model and its visualization, and any guidance ends in a handoff to Google Flights.

## History (dropped plans — do not re-suggest)

- An earlier plan covered **10 routes** to demonstrate an anomaly detector "firing selectively" across a diverse portfolio, with a consumer **"should I book now?"** feature. Both were dropped in favor of single-route depth (see above).
- The original plan used **Amadeus self-service production**; that portal was decommissioned July 17, 2026. Enterprise-only Amadeus is paid and out of scope. Fares now come from SerpApi's Google Flights engine.

## Resolved: the ingestion panel (was the last open implementation step)

Now **live** (deployed 2026-07-11 — see CLAUDE.md "Current status"). Recorded verbatim
for context on what was decided and why:

> **Ingestion panel (the open implementation step — needs sign-off before touching live code).** Replace the 10-route rolling-advance loop with a single-route **panel**: a set of **fixed future departure dates** (e.g. spanning ~+30 to ~+180 days to cover several lead-time buckets and seasons), each re-observed every run so it traces its own booking curve down to departure, refreshed with new far-out dates as near ones depart; optionally a couple of stay-length variants (7/14/21-day). ~14 calls/run. Rationale for cutting now with ~no data loss: the ~2 days of accumulated 10-route rolling-advance data doesn't fit the panel design anyway, so pivoting the loop is cheap. **Exact panel dates/lead-times/stay-lengths: to be chosen** (a principled modeling grid — no personal travel dates needed anymore).

## Maturity discipline (mirrors the ingestion "clock started" rule)

The *infra and DAG ship now*; the booking-curve signal matures in weeks (dense cross-sectional panel), and seasonality over a year. Until a layer's data fills in, the UI **shows context and hands off** — it must never over-promise a call the data can't yet support.
