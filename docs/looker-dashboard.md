# Looker Studio dashboard — build spec (ATL–CMN deep-dive)

Build-order **step 4a**: the zero-code BI consumer (`docs/consumers.md`). Looker Studio
points its **native BigQuery connector straight at the marts** — no serving table, no app
code, no new modeling layer. That "the warehouse already did the work, BI is a thin view
over it" property is the talking point; do not build a reporting schema to feed it.

This file is the **build spec** you execute in the Looker Studio UI (the report itself is
authored in a GUI, not in this repo). Every chart is keyed to a real column and carries a
**graceful-degradation** note, because the panel only started accumulating 2026-07-11 — the
dashboard must read as intentional on thin data and *fill in* as history lands, not render
empty axes.

## Getting started from zero (first 15 minutes)

Looker Studio is a free, point-and-click web app — nothing to install. Start with the
**booking-curve line**: it has real data today, so you get a genuine result and know the
connection works (unlike the anomaly scatter, which is empty until anchors accumulate).

1. **Open Looker Studio** — [lookerstudio.google.com](https://lookerstudio.google.com), sign
   in with the Google account that owns the `airfare-drift` GCP project (permissions then
   just work). Accept terms on first visit.
2. **Create a blank report** — **Create → Report** (or the **Blank Report** template).
3. **Connect BigQuery** — in the "Add data" panel pick the **BigQuery** connector, authorize
   if prompted, then drill **My Projects → `airfare-drift` → `airfare_intermediate` →
   `booking_curve_baseline`** and click **Add**. A default table showing the rows appears —
   that means it's connected (delete it or reshape it).
4. **First chart (booking-curve line)** — **Add a chart → Line chart**, draw it, then in the
   **Setup** panel set **Dimension** = `lead_time_bucket`, **Metric** = `mean_fare`, **Sort**
   = `lead_bucket_min` ascending. The curve appears (near-term premium → mid dip → gentle far
   rise) — real ATL–CMN data.
5. **Rename & save** — click the report title, name it e.g. *ATL–CMN Fare Drift* (autosaves).

That's the whole loop: **Add data → Add a chart → set Dimension + Metric.** Every chart below
is the same three moves against a different table. Add the remaining sources via **Resource →
Manage added data sources → Add a data source**. Suggested build order (real data → sparse):
booking-curve line ✓ → seasonality ribbon → offer scatter (page 2) → heatmap → anomaly
scatter (build the frame; it fills in as history lands).

## Data sources to add (BigQuery connector, one per table)

All in project `airfare-drift`. Add each as a separate data source (Resource → Manage added
data sources → BigQuery → your project):

| # | Table | Powers |
|---|-------|--------|
| 1 | `airfare_intermediate.fare_surface_baseline` | Booking-curve **heatmap** (joint lead × month) |
| 2 | `airfare_intermediate.booking_curve_baseline` | Booking-curve line (fare vs lead time) |
| 3 | `airfare_intermediate.seasonal_baseline` | Seasonality ribbon (fare vs departure month) |
| 4 | `airfare_marts.fct_fare_anomaly_events` | Residual-anomaly flags + Moroccan-event overlay |
| 5 | `airfare_intermediate.int_fare_offers` | Offer cross-section (routing / carrier / price dispersion) |

Leave connector caching at default (these are 10–120 row tables; bytes scanned are
negligible — the "never re-scan per page load" constraint is the *app's* problem, not
Looker's). Do **not** enable auto-refresh faster than the pipeline: transforms land every
2 days (~12:00 ET odd days), so a 12h data-freshness setting is plenty.

## Dashboard layout

One report, two pages. Page 1 is the analytical story; page 2 is the raw offer explorer.

```
┌─ PAGE 1: The pricing microstructure ──────────────────────────┐
│  [ KPI scorecard row ]                                         │
│  [ Booking-curve heatmap ]        [ Seasonality ribbon ]      │
│  [ Booking-curve line     ]        [ Residual-anomaly + events ]│
└───────────────────────────────────────────────────────────────┘
┌─ PAGE 2: Offer cross-section explorer ────────────────────────┐
│  [ filter bar: outbound_date · hub · carrier · stops ]        │
│  [ price-vs-lead scatter ]  [ hub/carrier dispersion table ]  │
└───────────────────────────────────────────────────────────────┘
```

### 0. KPI scorecard row (source 4 or a blend; top of page 1)

Scorecards, left to right. Keeps the "what am I looking at" frame honest on thin data.

- **Distinct anchors tracked** — `COUNT_DISTINCT(outbound_date)` on source 4. (~11 today.)
- **Snapshots collected** — `COUNT_DISTINCT(snapshot_date)`. (2 today; this is the number
  that has to grow before the anomaly layer lights up — surfacing it *is* the maturity story.)
- **Latest cheapest fare** — `observed_fare`, sorted by `snapshot_date` desc, record limit 1.
- **Anomalies flagged** — `COUNT` where `is_anomaly = true`. (0 today — see the maturity
  banner; this is expected, not a bug.)

Add a **text box maturity banner** beside the scorecards:
> *Anomaly detection activates once each (lead × month) cell has ≥5 independent departure
> anchors. The panel began accumulating 2026-07-11; today the surface is intentionally
> sparse — the booking-curve and seasonality shapes below are already real.*

### 1. Booking-curve HEATMAP — the flagship (source 1: `fare_surface_baseline`)

The one chart that needed a new view: the **joint** (lead × month) expected-fare surface.
The two marginal baselines (charts 2–3) each collapse one axis; only this cell mean is
un-confounded — it's literally the surface the residual model scores against.

- **Chart type:** Pivot table with heatmap (or Table → conditional-format the metric cell as
  a color scale; Looker has no native continuous heatmap, a heatmap-styled pivot is the idiom).
- **Row dimension:** `month_name` (order by `departure_month`).
- **Column dimension:** `lead_time_bucket` (order by `lead_bucket_min`).
- **Metric:** `mean_fare` (color scale: low = green/cheap → high = red/expensive).
- **Optional overlay metric:** `n_distinct_anchors` as the cell label so sparse cells read
  as sparse.

**Graceful degradation — lean in, don't hide it.** Today the surface is a **sparse
diagonal** (Aug@21-29 → Sep@45-89 → … → Mar@180+): a mid-July snapshot forces near-term
departures to be summer and far departures to be next spring, so lead and month move
together. That diagonal is the *visual argument* for why an additive marginal model is
biased and the joint cell is the honest expectation. Put a caption saying exactly that. As
more snapshot months accrue, off-diagonal cells fill and the surface becomes a true 2-D
booking-curve × seasonality map.

### 2. Booking-curve line (source 2: `booking_curve_baseline`)

- **Chart type:** Line (or combo: line = mean, bars = `n_distinct_anchors`).
- **Dimension (X):** `lead_time_bucket` (sort by `lead_bucket_min` ascending — this is the
  booking curve left-to-right, far-out → last-minute).
- **Metric (Y):** `mean_fare`. Optionally band with `min_fare` / `max_fare`.
- **Reliability styling:** add `is_reliable` as a breakdown or filter control so the viewer
  can hide unreliable buckets; keep them shown-but-muted by default so the shape is visible.

**Real today:** shows genuine structure now — near-term premium (~$1450 @ 21-29d), a mid
trough (~$918), a gentle far-out rise (~$979). This is a chart to feature immediately, not a
placeholder.

### 3. Seasonality ribbon (source 3: `seasonal_baseline`)

- **Chart type:** Line / area.
- **Dimension (X):** `month_name` (sort by `departure_month`, Jan→Dec).
- **Metric (Y):** `mean_fare`; band with `min_fare`/`max_fare` for the ribbon.
- **Caption:** note this captures **fixed-calendar** seasonality (summer peak, school
  holidays) but *not* the lunar Ramadan/Eid effect — that drifts ~11 days/yr and is the job
  of chart 4's event overlay. Naming the fixed-vs-lunar seam is a deliberate modeling point.

**Real today:** Aug summer peak (~$1365), Sep trough (~$918), a December holiday bump
(~$1123). Feature it.

### 4. Residual-anomaly flags + event overlay — the centerpiece (source 4: `fct_fare_anomaly_events`)

The whole reason the DAG is multi-source: do fare residuals spike near Moroccan holidays?

- **Chart type:** Scatter.
- **Dimension (X):** `days_to_nearest_eid` (signed: negative = before Eid, positive = after)
  — the marquee demand-proximity axis. Alternative X: `snapshot_date` for a time series once
  more snapshots exist.
- **Metric (Y):** `z_score` (residual vs the leave-one-out joint-cell expectation).
- **Color / shape:** `is_anomaly` (or `anomaly_direction`: high/low), plus `in_ramadan` as a
  second series or a shape.
- **Tooltip:** `outbound_date`, `observed_fare`, `expected_fare`, `residual_usd`,
  `score_status`, `nearest_eid_category`.
- **Filter control:** `score_status` (so a viewer can isolate `scored` vs `insufficient_data`).

**Graceful degradation:** today `z_score` is NULL for every row (`score_status =
'insufficient_data'`) because no cell yet has ≥3 obs and ≥2 anchors, so this scatter is
**empty of scored points**. Rather than show an empty chart, default its filter to
`score_status = scored` and pair it with a text note: *"lights up as anchors accumulate; one
anchor (2027-02-15) already sits inside Ramadan 2027."* Once cells fill, this becomes the
money chart. As an *interim* substitute you can plot `observed_fare` vs `days_to_nearest_eid`
(no scoring needed) to show the raw fare-vs-event-proximity relationship today.

**⚠️ Consumer caveat (from the mart docs):** every re-observation of an anchor is its own
row, so one anomaly episode spans many correlated rows. Before charting *counts* of
anomalies, dedup to anchor-episodes (e.g. `COUNT_DISTINCT(outbound_date)` where
`is_anomaly`), or you multi-count.

### 5. Offer cross-section explorer (page 2, source 5: `int_fare_offers`)

The richest data *today* — 110 offers with real routing/carrier/price variety. Two charts +
a filter bar.

- **Filter controls (bar):** `outbound_date`, `primary_hub`, `primary_operating_carrier`,
  `stop_count`.
- **Price-vs-lead scatter:** X = `days_to_departure`, Y = `offer_price`, color =
  `primary_hub` (or `stop_count`). Shows price dispersion and the connecting-hub competition
  that defines this thin market. Optional bubble size = `outbound_duration_min`.
- **Dispersion table:** dimension `primary_hub` (or `primary_operating_carrier`), metrics
  `MIN/AVG/MAX(offer_price)`, `COUNT` offers, `AVG(carbon_emissions_g)`. Sort by min price —
  reads as "cheapest routings and who flies them."

**Real today:** fully populated (CDG/IST/LGA/YUL/AMS… hubs, $918–$3152 spread). This page is
demo-ready immediately and carries the dashboard while the anomaly layer matures.

## Maintenance notes

- **New view dependency:** the heatmap depends on `airfare_intermediate.fare_surface_baseline`
  (added for this dashboard). It's a plain view over `int_daily_fare_stats` + `int_trip_fares`,
  runs on the normal 2-day workflow, needs no incremental handling.
- **Sharing:** grant the Looker Studio viewer/service identity BigQuery Data Viewer +
  Job User on the datasets it reads; keep the report itself link-shared, not public.
- **When history matures:** revisit chart 4's default filter (drop the `scored`-only default
  once most cells score) and add a snapshot-over-time booking-curve line for a single anchor
  (impossible today at 2 snapshots; compelling once a dozen land).
