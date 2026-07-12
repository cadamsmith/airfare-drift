# CLAUDE.md

Working brief for the **Airfare Drift** repo.

## What this is

A data-engineering **portfolio/interview showcase** — not a consumer product. It ingests messy, real-world flight fare data for **one route (ATL–CMN)** from heterogeneous sources and builds a governed, tested, dimensional warehouse (Dataform + BigQuery) on top. The centerpiece is an **incrementally-computed anomaly layer** that flags when the route's observed fares deviate from a *fitted expectation* (booking curve + seasonality) — not just from a flat historical mean.

**Depth, not breadth (the core design bet).** The project deliberately covers a *single* route in depth rather than many routes shallowly. Ten near-identical route pipelines read as one pipeline copy-pasted; one route modeled richly — booking curve, seasonality, routing/carrier competition, price dispersion, event correlation — reads as genuine analytical engineering. The whole thing is shaped to *need* Dataform's real strengths (multi-table DAG, incremental models, SCD2, assertions, docs-as-code). Narrative: *"I built a warehouse that models the full pricing microstructure of one thin transatlantic market and detects when it's pricing abnormally, correlated with Moroccan holiday events."* When a decision is ambiguous, favor the option that best demonstrates **engineering rigor** (incremental correctness, data governance, honest modeling) over the one that ships fastest.

## Detailed docs (load on demand — read the file when its trigger fires)

This brief is deliberately thin. The deep context lives in `docs/` — **read the relevant file before doing that kind of work**, don't work from memory of it:

- **`docs/decisions.md`** — *why one route*, what the signal is/isn't, dropped-plan history (10 routes, "should I book now?", Amadeus), maturity discipline. **Read before** proposing anything that reverses a settled choice, or when a decision feels ambiguous.
- **`docs/data-model.md`** — verbatim shape of the `raw_response` payload (offers, legs, `price_insights`, cabin cost). **Read before** writing staging SQL / unnesting raw.
- **`docs/warehouse.md`** — the 5 modeling layers and the Dataform SQLX layer structure (staging/intermediate/marts/assertions/environments). **Read before** building the Dataform warehouse.
- **`docs/consumers.md`** — Looker Studio + ASP.NET Core app, serving-layer commitment, OLTP scope, build ordering. **Read before** building either consumer.

## Non-negotiable constraints (getting these wrong wastes weeks or money)

1. **Stay inside the SerpApi free-tier budget (250 searches/month).** Fares come from SerpApi's Google Flights engine (live, real Google Flights data). A round-trip total price + the full offer cross-section arrive in a **single** call — never burn a second `departure_token` call. Budget: the deployed cron `0 9 */2 * *` is odd-days-of-month = **15–16 runs/month**, so **~16 calls/run** are available. **All of it now flows to ATL–CMN**: a **panel** of fixed future departure dates × staggered lead times (booking curve), spanning the calendar (seasonality), plus a few stay-length variants — target ~14 calls/run (~210/mo) with ~40/mo margin for dev/testing. No on-demand consumer call (feature dropped), so the whole pool is the panel. Cabins, extra runs, or a daily cadence push past 250 and start costing money ($25/mo for 1,000).
2. **Incremental scans, not full-table scans.** Simultaneously the main cost risk (blows the BigQuery free tier) and the core technical challenge the project exists to demonstrate. Incremental models must scan only new partitions. With one route the fact grows by *many rows per run* (offers × legs × panel dates), so incremental discipline matters *more*, not less. The residual z-scores and the SCD2 dimension are both incremental-correctness problems — treat them that way.
3. **Keep raw data messy.** Do not clean at ingestion time. Duplicate snapshots, late arrivals, the deeply-nested offer arrays, and API quirks are preserved in raw tables *on purpose* — parsing/unnesting/dedup downstream in Dataform is what makes that layer worth writing. Derive `days_to_departure`, `stay_length`, stop count, routing, etc. **downstream**, never at ingestion.
4. **Ingestion goes live first.** The anomaly layer needs weeks of accumulated snapshots to mean anything. The every-2-day Cloud Function + Scheduler starts the wall-clock timer; the warehouse and web app are built *in parallel while history accumulates*. Baselines and rolling windows count **observations**, not calendar days (panel dates re-observed every ~2 days).
5. **Cost target: $0–5/month.** Stay within free tiers (SerpApi 250 searches/mo, BigQuery 10 GB storage / 1 TB query, Cloud Functions + Scheduler, Dataform is free). Any consumer surface must read a small serving table or cached result — never re-scan marts per page load.

## The route: ATL–CMN

Single route, modeled in depth. Atlanta → Casablanca: a **thin, connecting-only** long-haul leisure market (no nonstop; RAM doesn't fly it). Queried with one consistent convention **per panel slot** (round-trip, USD, economy, fixed return gap), varying only the departure date and lead time so the panel spans the booking curve and the calendar. Both endpoints are major airports with reliable Google Flights coverage. (Panel design & rationale: `docs/decisions.md`.)

## Tech stack

- **Warehouse/transform:** BigQuery + Dataform (SQLX, incremental models, assertions, environment config)
- **Ingestion:** Python Cloud Function on Cloud Scheduler (every 2 days) → date-partitioned raw BigQuery tables
- **Sources:** SerpApi Google Flights engine (live fares; 250 searches/mo free tier), OpenFlights reference data (airport/carrier reference), a Moroccan holiday/events calendar (Ramadan/Eid/school holidays — still to be chosen; the Eid lunar-drift is the marquee wrinkle)
- **Consumption:** Looker Studio (native BQ connector) + ASP.NET Core MVC (controllers + Razor reading BQ via `Google.Cloud.BigQuery.V2`, a JS charting lib for viz, EF Core / Npgsql over Postgres for OLTP) — see `docs/consumers.md`

## Current status

**The analytics/engineering spine is complete and self-scheduling**, committed + pushed through `08b9988`. Ingestion → Dataform warehouse (staging → intermediate → baselines → residual-anomaly centerpiece → event correlation → governance assertions) runs automatically every 2 days; all 11 assertions green. Architecture is settled: single route ATL–CMN, depth over breadth; centerpiece = residual anomaly of observed vs. fitted booking-curve + seasonality surface, with Moroccan-event correlation and the Eid lunar-drift wrinkle. **Read `docs/warehouse.md` before touching models** — it holds the layer design and modeling decisions.

**Next: consumption** — Looker Studio deep-dive first (BI quick-win on the auto-refreshed marts), then the ASP.NET Core bespoke front-end + OLTP (`docs/consumers.md`). Open consumption-phase choices (serving layer: cached query vs. serving table; JS charting lib; web-app hosting) get picked during the app build.

### Deployed topology (GCP project `airfare-drift`, region us-central1)

- **Ingestion** — Cloud Function `ingest` (Gen2 HTTP, python312, entry point `ingest`, source `ingestion/`). Runtime SA `ingest-fn@` (BigQuery jobUser + dataEditor only). Env `BQ_PROJECT/BQ_DATASET/BQ_TABLE`; `SERPAPI_KEY` from Secret Manager secret `serpapi-key`. Per-call error isolation: a failed fetch records an error row (`http_status` NULL, `raw_response` = `REQUEST_ERROR: ...`) instead of dropping the run; staging treats `http_status IS NULL` as a failed fetch.
- **Raw table** — `airfare-drift.airfare_raw.fare_snapshots`: partitioned by `snapshot_date` (DAY), clustered `(origin, destination)`, append-only, full API body in `raw_response` (STRING). Schema carries `outbound_date/return_date/advance_days/return_gap_days` per row.
- **Ingest schedule** — Cloud Scheduler `airfare-ingest-2daily`, cron `0 9 */2 * *` America/New_York, invoked OIDC as `scheduler-invoker@` (run.invoker). `retryConfig`: 3 retries, 30–300s backoff.
- **Transform** — native managed Dataform: repo `airfare-drift-warehouse` (git @ `main`, token from secret `dataform-git-token`) → release config `prod` (compile, cron `0 11 */2 * *`) → workflow config `prod-2daily` (full graph incl. all assertions, cron `0 12 */2 * *`, `fullyRefreshIncrementalTablesEnabled=false` so incremental discipline holds). Runner SA `dataform-runner@` (BQ jobUser + dataEditor). Phase-locked to ingestion: ingest 09:00 → compile 11:00 → transform 12:00 ET.

### Local dev & CLI

- **Ingestion:** `.venv` has `requests` + `google-cloud-bigquery`. Dry run: `./.venv/bin/python ingestion/main.py --dry-run` (needs `SERPAPI_KEY`, no BQ write). Redeploy: `gcloud functions deploy ingest --gen2 --source=ingestion ...`. (`scripts/verify_serpapi.py` is a standalone smoke test carrying a stale 10-route copy — update opportunistically.)
- **Dataform:** run `dataform run` directly (global binary; auth via gitignored `.df-credentials.json` = projectId + location only, falls back to ADC). Not `npx` + ADC-export.

### Design invariants — don't regress these

Hard-won incremental-correctness fixes, easy to helpfully undo; see git history for full reasoning.

- **No `updatePartitionFilter` anywhere.** A fixed target-prune window can drift below the `>= MAX(self)` source watermark after a multi-day pipeline gap and INSERT duplicates on the reprocessed boundary partition. The costly scan is the source (bounded by the watermark); the target is one thin route, so an unbounded uniqueKey MERGE is cheap and always correct. Do not re-add a partition filter as a "cost optimization."
- **`uniqueKey` drives the MERGE but does NOT assert uniqueness** — a dup would be silent. Hence the standalone uniqueness assertions on `stg_fare_offers` + `int_fare_offers`; keep them.
- **Expected surface = JOINT `(lead_bucket, month)` cell mean, LEAVE-ONE-OUT** from sufficient stats — never additive marginals (the panel makes lead-time and month collinear, so additive main-effects are biased ~18% and sign-inverted on the cheapest class). Additive marginals are a sparse-cell fallback / EDA views only.
- **Reliability gate = DISTINCT ANCHORS (`COUNT(DISTINCT outbound_date)`), not observation count** — the re-observing panel inflates obs count and would grant false reliability + collapse loo_std into spurious high-σ. Thresholds in `includes/anomaly.js`; lead buckets in `includes/lead_time.js` (residual + baselines must bucket identically).
- **`departure_time_bucket` is NULL-guarded** — an unparseable time must not be mislabeled `red_eye`.

### Panel & data notes

- **Panel is live** (`ingestion/config.py` + `main.py`, `build_panel`): fixed month-anchor departure dates re-observed every run to trace booking curves and span seasonality, plus 14/21-day stay variants on the nearest anchor. Hard-capped `MAX_CALLS_PER_RUN=12` (~192/mo, inside the 250 budget). Booking-curve accumulation clock started with the first panel batch (2026-07-11).
- **Do NOT clean raw** (constraint #3). The table also retains 40 pre-pivot rows from 2026-07-09 (10 routes × 4 dedup batches) as a deliberate staging fixture that exercises dedup + convention-drift reconciliation; staging scopes to ATL–CMN so orphaned routes are never selected. Keep them — distinguish panel-era rows by shape/date, never by deleting raw.
- **An offer's legs are OUTBOUND-ONLY** (the return is behind a `departure_token` we never call); the design stays outbound-only + round-trip total price (`docs/data-model.md`).
- **Scores are honestly `insufficient_data` today** — the distinct-anchor gate is anchor-sparse; the anomaly + event layers light up as history accumulates. (The event layer is a **correlation** layer, not a predictor, until anchors span the lunar phases.)

### Deferred (not dropped)

- **Event-relative seasonal baseline** — needs many anchors per lunar phase; build when the panel spans them (maturity discipline).
- **Return-trip data** — user requested + authorized paying (~$25/mo, reverses constraint #1); DEFERRED as breadth-vs-depth, feeds no model yet. Revisit as a `departure_token`-chaining ingestion showcase after the spine.
- **SCD2 `dim_itinerary`** (confirm churn exists first), **leg-grain `fct_fare_offers` mart**, **per-segment baselines** (`--full-refresh` when samples support).
- **Terraform/IaC** — parked until after consumption; import-only capstone when built.
