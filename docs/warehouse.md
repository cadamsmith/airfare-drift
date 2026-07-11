# Warehouse: modeling layers & Dataform structure

Read this when **building the Dataform warehouse** (build-order step 3). It covers the
analytical modeling layers and the concrete Dataform SQLX layout. The raw payload these
consume is documented in `docs/data-model.md`; the rationale for modeling one route this
richly is in `docs/decisions.md`.

## Modeling layers (the depth that makes one route a real project)

1. **Cross-sectional microstructure** (free every call): routing path / connecting hub, operating carrier, stop count, departure time-of-day, and **price dispersion** across itineraries. Feeds a within-route analog of the old "learned per-route, not globally": baselines are learned **per routing/carrier segment**, not pooled across the whole market.
2. **Booking curve** — expected fare as a function of **days-to-departure**, fit from the fixed-date panel re-observed over successive runs *and* seeded cross-sectionally (many departure dates at staggered lead times observed simultaneously, so curve coverage arrives in weeks, not months).
3. **Seasonality** — a departure-date seasonal component (Morocco summer, school holidays, **Ramadan/Eid**). Accumulates over a year; the **lunar-calendar Eid drift (~11 days/year)** is the marquee modeling wrinkle. Honest about maturity: seasonality is *designed-for and accumulating*, not claimed complete early.
4. **Residual anomaly — THE centerpiece.** Deviation of the observed fare from the fitted (curve + seasonality) surface → z-score / flag. "Fares rise near departure" impresses nobody; *"this fare is 2.6σ above the fitted expectation for this lead time and season"* is the signal. Not the curve itself — the residual.
5. **Event correlation** — join Moroccan holidays / Ramadan / Eid / school-holiday windows and test whether residual spikes line up. Keeps the DAG multi-source and honest.

(Maturity discipline — infra ships now, signals mature over weeks/a year — lives in `docs/decisions.md`.)

## Dataform layer structure

*(Model list is directional; grain/columns finalized during the build.)*

- **Staging** — parse the deeply-nested `raw_response`: `UNNEST` `best_flights`/`other_flights` → offers → legs into tidy rows (semi-structured parsing is itself a showcase); dedup the duplicate/late snapshots; cast; standardize airport/carrier codes; treat `http_status IS NULL` as a failed fetch.
- **Intermediate** — `fare_offers` (every offer × leg seen per departure_date × observation), `booking_curve_baseline` and `seasonal_baseline` (expected fare by lead-time / season, computed **incrementally**).
- **Marts** — `fct_fare_offers` (fact, grain: departure_date × observation_date × offer × leg, a genuine incremental problem with many rows/run), `dim_itinerary` (**SCD Type 2** — tracks schedule / aircraft / routing churn at the itinerary level, where real change happens; confirm churn exists in the accumulating data before making it a centerpiece), `fct_fare_anomaly` (**the differentiator** — residual of observed fare vs. the fitted curve+seasonal surface, flags anomalous windows), plus price-dispersion / routing-mix marts and an event-enriched anomaly view.
- **Assertions** — freshness (did this run's snapshot land?), referential integrity (every offer maps to valid airports/carriers; every leg to a valid itinerary), reasonableness bounds (no $0 or $50,000 fares — the observed typical range ~$770–1,300 informs sane bounds), unnest integrity (leg counts consistent).
- **Environments** — proper dev/prod separation via Dataform environment config. Never hardcode dataset names.
