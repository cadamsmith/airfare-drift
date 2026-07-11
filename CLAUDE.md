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

Single route, modeled in depth. Atlanta → Casablanca: a **thin, connecting-only** long-haul leisure/VFR market (no nonstop; RAM doesn't fly it). Queried with one consistent convention **per panel slot** (round-trip, USD, economy, fixed return gap), varying only the departure date and lead time so the panel spans the booking curve and the calendar. Both endpoints are major airports with reliable Google Flights coverage. (Panel design & rationale: `docs/decisions.md`.)

## Tech stack

- **Warehouse/transform:** BigQuery + Dataform (SQLX, incremental models, assertions, environment config)
- **Ingestion:** Python Cloud Function on Cloud Scheduler (every 2 days) → date-partitioned raw BigQuery tables
- **Sources:** SerpApi Google Flights engine (live fares; 250 searches/mo free tier), OpenFlights reference data (airport/carrier reference), a Moroccan holiday/events calendar (Ramadan/Eid/school holidays — still to be chosen; the Eid lunar-drift is the marquee wrinkle)
- **Consumption:** Looker Studio (native BQ connector) + ASP.NET Core MVC (controllers + Razor reading BQ via `Google.Cloud.BigQuery.V2`, a JS charting lib for viz, EF Core / Npgsql over Postgres for OLTP) — see `docs/consumers.md`

## Current status

Decided: **single route (ATL–CMN), depth over breadth** — dropped the 10-route portfolio and the consumer "should I book now?" feature; the deliverable is a richly-modeled analytics/engineering showcase whose centerpiece is the **residual anomaly** (observed vs. fitted booking-curve + seasonality surface), with Moroccan-event correlation and the Eid lunar-drift wrinkle. Fare source SerpApi Google Flights (economy only — cabins cost extra calls), cadence every 2 days, whole budget → a fixed-date ATL–CMN **panel**. Web app reframed as a **bespoke analytical front-end (custom viz) + OLTP (alerts/annotations)** with a committed serving layer (cache or serving table), Looker as the built-first BI quick-win — see `docs/consumers.md`. Open: exact panel dates/lead-times/stay-lengths; events/holiday calendar API; serving layer (cached query vs. serving table — pick during app build); JS charting lib; web-app hosting; Dataform grain/mart shape (finalized during build).

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
