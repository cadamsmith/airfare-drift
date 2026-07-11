# CLAUDE.md

Working brief for the **Airfare Drift** repo.

## What this is

A data-engineering **portfolio/interview showcase** — not a consumer product. It ingests messy, real-world flight fare data for **one route (ATL–CMN)** from heterogeneous sources and builds a governed, tested, dimensional warehouse (Dataform + BigQuery) on top. The centerpiece is an **incrementally-computed anomaly layer** that flags when the route's observed fares deviate from a *fitted expectation* (booking curve + seasonality) — not just from a flat historical mean.

**Depth, not breadth (the core design bet).** The project deliberately covers a *single* route in depth rather than many routes shallowly. Ten near-identical route pipelines read as one pipeline copy-pasted; one route modeled richly — booking curve, seasonality, routing/carrier competition, price dispersion, event correlation — reads as genuine analytical engineering. The whole thing is shaped to *need* Dataform's real strengths (multi-table DAG, incremental models, SCD2, assertions, docs-as-code). Narrative: *"I built a warehouse that models the full pricing microstructure of one thin transatlantic market and detects when it's pricing abnormally, correlated with Moroccan holiday events."* When a decision is ambiguous, favor the option that best demonstrates **engineering rigor** (incremental correctness, data governance, honest modeling) over the one that ships fastest.

*(History: an earlier plan covered 10 routes to demonstrate an anomaly detector "firing selectively" across a diverse portfolio, with a consumer "should I book now?" feature. Both were dropped — see "Why one route".)*

## Why one route (and why it's the stronger portfolio piece)

- **The control moved inside the route.** The multi-route version needed a *portfolio* of routes as its control group (stable routes stay quiet, spiky ones fire). Here the control is the model's own expectation: **observed fare vs. the fitted booking-curve + seasonality surface**, and the anomaly is the residual. That's a cleaner statistical story — deviation from a fitted model, not a comparison across heterogeneous routes.
- **ATL–CMN is a genuinely interesting market to model.** Verified against real captured data: **no nonstop exists** (Royal Air Maroc doesn't fly it), so it's a *connecting market* — the same trip routes via Montreal (Air Canada), Paris (Air France), JFK, etc., across multiple carriers, with wide price dispersion ($1,132→$1,769 in one snapshot). The competitive microstructure is **routing/hub/carrier competition**, richer than a single-carrier price series.
- **The whole SerpApi budget now funds one route**, so we can sample a dense fixed-date **panel** (many departure dates × lead times) — the exact data a booking-curve model is starved for. Single-route focus and the model's data-hunger resolve each other.
- **Authentic hook:** the personal motivation (family in Morocco) is a real interview story, but the deliverable is an *analytics/engineering* showcase — not a booking tool.

## What the signal is (and isn't)

The batch pipeline is **not** a live price quote and must never be presented as one — Google Flights/Hopper own "what's the price right now." What this project owns, computed transparently with warehouse rigor: **"is ATL–CMN pricing normally, given the lead time, the season, and the route's own history — and if not, why?"** Every number in any UI carries an explicit **"as of <observation timestamp>"**. The every-2-day cadence is fine for this: a fitted surface + regime signal moves slowly, so a ≤2-day-old observation is a valid statement about *behavior*, not a transaction price. There is **no consumer buy/wait recommendation** (dropped with the multi-route plan) — the deliverable is the model and its visualization, and any guidance ends in a handoff to Google Flights.

## What one ATL–CMN call actually returns (verified — the raw depth we model)

A single economy round-trip SerpApi `google_flights` call returns a whole cross-section, stored verbatim in `raw_response`:

- **Per offer (itinerary):** `price`, `type`, `total_duration`, `layovers` (airport id/name/duration → **routing/hub**), stop count (derivable from `flights` legs), `carbon_emissions`, `departure_token`.
- **Per leg:** `airline` (operating carrier), `flight_number`, `airplane` (**aircraft type**), `travel_class`, `departure_airport`/`arrival_airport` with **timestamps** (departure time-of-day), `duration`, `legroom`, `extensions`, `plane_and_crew_by` / `ticket_also_sold_by` (**codeshare**).
- **Cross-offer dispersion:** several offers per call → price spread, carrier mix, routing mix — a market cross-section on *every* call.
- **`price_insights`:** Google's own `price_level`, `typical_price_range`, and a `price_history` array — captured as a **free external comparison signal** for our baseline (never the centerpiece; our own computed baseline is the differentiator).
- **`airports`:** reference block for the queried airports.

**Cabin is NOT free.** `travel_class` is a *request parameter* (1/2/3/4), so covering premium/business would be 3–4× the calls. Ingestion stays **economy-only**; the microstructure story leans on the axes that are free in one response (routing, carrier, stops, time-of-day, dispersion), not cabin.

## Modeling layers (the depth that makes one route a real project)

1. **Cross-sectional microstructure** (free every call): routing path / connecting hub, operating carrier, stop count, departure time-of-day, and **price dispersion** across itineraries. Feeds a within-route analog of the old "learned per-route, not globally": baselines are learned **per routing/carrier segment**, not pooled across the whole market.
2. **Booking curve** — expected fare as a function of **days-to-departure**, fit from the fixed-date panel re-observed over successive runs *and* seeded cross-sectionally (many departure dates at staggered lead times observed simultaneously, so curve coverage arrives in weeks, not months).
3. **Seasonality** — a departure-date seasonal component (Morocco summer, school holidays, **Ramadan/Eid**). Accumulates over a year; the **lunar-calendar Eid drift (~11 days/year)** is the marquee modeling wrinkle. Honest about maturity: seasonality is *designed-for and accumulating*, not claimed complete early.
4. **Residual anomaly — THE centerpiece.** Deviation of the observed fare from the fitted (curve + seasonality) surface → z-score / flag. "Fares rise near departure" impresses nobody; *"this fare is 2.6σ above the fitted expectation for this lead time and season"* is the signal. Not the curve itself — the residual.
5. **Event correlation** — join Moroccan holidays / Ramadan / Eid / school-holiday windows and test whether residual spikes line up. Keeps the DAG multi-source and honest.

**Maturity discipline (mirrors the ingestion "clock started" rule):** the *infra and DAG ship now*; the booking-curve signal matures in weeks (dense cross-sectional panel), and seasonality over a year. Until a layer's data fills in, the UI **shows context and hands off** — it must never over-promise a call the data can't yet support.

## Non-negotiable constraints (getting these wrong wastes weeks or money)

1. **Stay inside the SerpApi free-tier budget (250 searches/month).** Fares come from SerpApi's Google Flights engine (live, real Google Flights data). A round-trip total price + the full offer cross-section arrive in a **single** call — never burn a second `departure_token` call. Budget: the deployed cron `0 9 */2 * *` is odd-days-of-month = **15–16 runs/month**, so **~16 calls/run** are available. **All of it now flows to ATL–CMN**: a **panel** of fixed future departure dates × staggered lead times (booking curve), spanning the calendar (seasonality), plus a few stay-length variants — target ~14 calls/run (~210/mo) with ~40/mo margin for dev/testing. No on-demand consumer call (feature dropped), so the whole pool is the panel. Cabins, extra runs, or a daily cadence push past 250 and start costing money ($25/mo for 1,000). *(History: the original plan used Amadeus self-service production; that portal was decommissioned July 17, 2026. Enterprise-only Amadeus is paid and out of scope.)*
2. **Incremental scans, not full-table scans.** Simultaneously the main cost risk (blows the BigQuery free tier) and the core technical challenge the project exists to demonstrate. Incremental models must scan only new partitions. With one route the fact grows by *many rows per run* (offers × legs × panel dates), so incremental discipline matters *more*, not less. The residual z-scores and the SCD2 dimension are both incremental-correctness problems — treat them that way.
3. **Keep raw data messy.** Do not clean at ingestion time. Duplicate snapshots, late arrivals, the deeply-nested offer arrays, and API quirks are preserved in raw tables *on purpose* — parsing/unnesting/dedup downstream in Dataform is what makes that layer worth writing. Derive `days_to_departure`, `stay_length`, stop count, routing, etc. **downstream**, never at ingestion.
4. **Ingestion goes live first.** The anomaly layer needs weeks of accumulated snapshots to mean anything. The every-2-day Cloud Function + Scheduler starts the wall-clock timer; the warehouse and web app are built *in parallel while history accumulates*. Baselines and rolling windows count **observations**, not calendar days (panel dates re-observed every ~2 days). **Note:** the current ingestion samples a rolling 30-day advance (one call/run) and captures **no booking curve** (see `config.py`); realizing this brief requires the **panel refactor** below — the one open implementation step.
5. **Cost target: $0–5/month.** Stay within free tiers (SerpApi 250 searches/mo, BigQuery 10 GB storage / 1 TB query, Cloud Functions + Scheduler, Dataform is free). Any consumer surface must read a small serving table or cached result — never re-scan marts per page load.

## The route: ATL–CMN

Single route, modeled in depth. Atlanta → Casablanca: a **thin, connecting-only** long-haul leisure/VFR market (no nonstop; RAM doesn't fly it). Queried with one consistent convention **per panel slot** (round-trip, USD, economy, fixed return gap), varying only the departure date and lead time so the panel spans the booking curve and the calendar. Both endpoints are major airports with reliable Google Flights coverage.

**Ingestion panel (the open implementation step — needs sign-off before touching live code).** Replace the 10-route rolling-advance loop with a single-route **panel**: a set of **fixed future departure dates** (e.g. spanning ~+30 to ~+180 days to cover several lead-time buckets and seasons), each re-observed every run so it traces its own booking curve down to departure, refreshed with new far-out dates as near ones depart; optionally a couple of stay-length variants (7/14/21-day). ~14 calls/run. Rationale for cutting now with ~no data loss: the ~2 days of accumulated 10-route rolling-advance data doesn't fit the panel design anyway, so pivoting the loop is cheap. **Exact panel dates/lead-times/stay-lengths: to be chosen** (a principled modeling grid — no personal travel dates needed anymore).

## Dataform layer structure

*(Model list is directional; grain/columns finalized during the build.)*

- **Staging** — parse the deeply-nested `raw_response`: `UNNEST` `best_flights`/`other_flights` → offers → legs into tidy rows (semi-structured parsing is itself a showcase); dedup the duplicate/late snapshots; cast; standardize airport/carrier codes; treat `http_status IS NULL` as a failed fetch.
- **Intermediate** — `fare_offers` (every offer × leg seen per departure_date × observation), `booking_curve_baseline` and `seasonal_baseline` (expected fare by lead-time / season, computed **incrementally**).
- **Marts** — `fct_fare_offers` (fact, grain: departure_date × observation_date × offer × leg, a genuine incremental problem with many rows/run), `dim_itinerary` (**SCD Type 2** — tracks schedule / aircraft / routing churn at the itinerary level, where real change happens; confirm churn exists in the accumulating data before making it a centerpiece), `fct_fare_anomaly` (**the differentiator** — residual of observed fare vs. the fitted curve+seasonal surface, flags anomalous windows), plus price-dispersion / routing-mix marts and an event-enriched anomaly view.
- **Assertions** — freshness (did this run's snapshot land?), referential integrity (every offer maps to valid airports/carriers; every leg to a valid itinerary), reasonableness bounds (no $0 or $50,000 fares — the observed typical range ~$770–1,300 informs sane bounds), unnest integrity (leg counts consistent).
- **Environments** — proper dev/prod separation via Dataform environment config. Never hardcode dataset names.

## Tech stack

- **Warehouse/transform:** BigQuery + Dataform (SQLX, incremental models, assertions, environment config)
- **Ingestion:** Python Cloud Function on Cloud Scheduler (every 2 days) → date-partitioned raw BigQuery tables
- **Sources:** SerpApi Google Flights engine (live fares; 250 searches/mo free tier), OpenFlights reference data (airport/carrier reference), a Moroccan holiday/events calendar (Ramadan/Eid/school holidays — still to be chosen; the Eid lunar-drift is the marquee wrinkle)
- **Consumption:** Looker Studio (native BQ connector — a single-route deep-dive: booking-curve heatmap, seasonality ribbon, residual-anomaly flags, event overlays); ASP.NET Core MVC (controllers + Razor, server-rendered) reading BQ via `Google.Cloud.BigQuery.V2`, with EF Core / Npgsql over Postgres for app state (OLAP-vs-OLTP split — never write app state to BigQuery)

## Current status

Decided: **single route (ATL–CMN), depth over breadth** — dropped the 10-route portfolio and the consumer "should I book now?" feature; the deliverable is a richly-modeled analytics/engineering showcase whose centerpiece is the **residual anomaly** (observed vs. fitted booking-curve + seasonality surface), with Moroccan-event correlation and the Eid lunar-drift wrinkle. Fare source SerpApi Google Flights (economy only — cabins cost extra calls), cadence every 2 days, whole budget → a fixed-date ATL–CMN **panel**. Open: exact panel dates/lead-times/stay-lengths; events/holiday calendar API; ASP.NET serving strategy; web-app hosting; Dataform grain/mart shape (finalized during build).

**✅ Panel refactor is LIVE (deployed 2026-07-11T03:21Z).** `ingestion/config.py` + `main.py` build a single-route ATL–CMN panel (`build_panel`): fixed month-anchor departure dates (1st/15th near-term, 15th far-term) ≥14d out, re-observed every run to trace booking curves, plus 14/21-day stay variants on the nearest anchor, hard-capped at `MAX_CALLS_PER_RUN=12` (~192/mo worst case). Confirmed by a live dry-run on 2026-07-11: all 12 panel queries returned HTTP 200 with real offers, and the data already shows booking-curve + seasonality + stay-length structure (near-term premium, ~$918 mid-range trough, a December holiday bump, longer stays sometimes cheaper). First scheduled panel batch lands on the next fire (07-11 09:00 ET); `.dryrun_output.json` holds a captured 12-query panel response as a staging fixture. (`scripts/verify_serpapi.py` still has its own stale 10-route copy — smoke test only, not on the pipeline; update opportunistically.)

**Raw table — do NOT clean (constraint #3, append-only/messy on purpose).** As of the pivot the table holds only the 40 pre-pivot rows from 2026-07-09 (10 routes × 4 deploy-test batches, rolling-advance). These are retained deliberately as a staging fixture: they exercise **dedup** (4 intra-day dup batches) and **convention-drift reconciliation** (old 10-route rolling-advance vs. new single-route panel). Staging scopes to `origin='ATL' AND destination='CMN'` and dedups; the 9 orphaned routes simply never get selected. The 4 old ATL–CMN rows are real route history under the old convention — keep them; distinguish panel-era rows downstream by shape (many `outbound_date`/`advance_days` per snapshot) or `snapshot_date >=` first panel run, not by deleting raw.

**✅ INGESTION PATH IS LIVE — now on the single-route panel convention (deployed 2026-07-11).** The every-2-days Cloud Scheduler job is enabled and the full SerpApi → Cloud Function → BigQuery → Scheduler(OIDC) path is verified end-to-end. The booking-curve accumulation clock effectively (re)starts with the first panel batch (07-11 09:00 ET); pre-pivot rows from 2026-07-09 remain as a staging fixture (see below).

**Deployed topology (GCP project `airfare-drift`, region us-central1):**
- **Function:** `ingest` (Gen2 HTTP, python312), source in `ingestion/`, entry point `ingest`. Runtime SA `ingest-fn@` (BigQuery jobUser + dataEditor only). SerpApi key injected from Secret Manager secret `serpapi-key` as env `SERPAPI_KEY`; also `BQ_PROJECT/BQ_DATASET/BQ_TABLE`.
- **Raw table:** `airfare-drift.airfare_raw.fare_snapshots` — partitioned by `snapshot_date` (DAY), clustered by `(origin, destination)`. Full raw API body in `raw_response` (STRING), append-only. (Schema already carries `outbound_date`/`return_date`/`advance_days`/`return_gap_days` per row, so the panel refactor needs no schema change — only different query values and more rows/run.)
- **Scheduler:** job `airfare-ingest-2daily`, cron `0 9 */2 * *` America/New_York (09:00 ET odd days), invokes via OIDC as SA `scheduler-invoker@` (run.invoker on the ingest service).

**Ingestion resilience (hardened — the whole point is *continuous* accumulation):**
- Per-call error isolation: `collect_snapshot` wraps each fetch; a network timeout/ConnectionError records an error row (`http_status` NULL, `raw_response` = `REQUEST_ERROR: ...`) instead of dropping the rest of the run. Staging treats `http_status IS NULL` as a failed fetch. (HTTP 4xx/5xx are captured as normal rows.) Per-call timeout is 30s. (Still per-call under the panel — more calls/run, same isolation.)
- Scheduler retries: `retryConfig` `retryCount: 3` with bounded backoff (30s–300s, ≤600s total), so a transient failed fire retries rather than silently skipping ~2 days.
- Relies on the planned freshness assertion as a *detection* backstop for any snapshot that never lands.

**Local dev:** `.venv` has `requests`+`google-cloud-bigquery`; dry run `./.venv/bin/python ingestion/main.py --dry-run` (needs `SERPAPI_KEY`, no BQ write). Redeploy: `gcloud functions deploy ingest --gen2 --source=ingestion ...`. `scripts/verify_serpapi.py` is the standalone smoke test.

**Build order:** (1) ✅ ingestion path live; (2) ✅ panel refactor deployed (2026-07-11) → booking-curve clock started; (3) **← NEXT: Dataform warehouse** — scaffold, staging (unnest/dedup/cast `raw_response`, scope to ATL–CMN, reconcile the pre-pivot rows), then the incremental booking-curve/seasonal baselines and residual-anomaly SQLX (trickiest), then assertions; (4) consumption (Looker deep-dive, then web app) once history is meaningful.
