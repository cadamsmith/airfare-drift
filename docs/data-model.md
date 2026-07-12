# Raw data shape: what one ATL–CMN call returns

Read this **before writing staging SQL** — it documents the verbatim structure of the
`raw_response` payload you'll be unnesting. See `docs/warehouse.md` for how these fields
flow into the Dataform layers.

## What one ATL–CMN call actually returns (verified — the raw depth we model)

A single economy round-trip SerpApi `google_flights` call returns a whole cross-section, stored verbatim in `raw_response`:

- **Per offer (itinerary):** `price`, `type`, `total_duration`, `layovers` (airport id/name/duration → **routing/hub**), stop count (derivable from `flights` legs), `carbon_emissions`, `departure_token`.
  - **⚠️ `flights` is the OUTBOUND journey only.** Verified against live data (238/238 legs fall before the return date, every offer's first leg is ATL). Google Flights returns return-leg options *only* behind a second `departure_token` call — which we never make (constraint #1). So `total_duration`, the legs, and `layovers` all describe the outbound; `price` is nonetheless the full **round-trip total**. Decided 2026-07-11 to stay outbound-only (getting inbound itinerary detail needs the paid SerpApi tier or halves the panel — see `docs/decisions.md` intent / CLAUDE.md constraint #1). Model the outbound routing/carrier/hub microstructure + round-trip total price; there is no inbound itinerary in the warehouse.
- **Per leg:** `airline` (operating carrier), `flight_number`, `airplane` (**aircraft type**), `travel_class`, `departure_airport`/`arrival_airport` with **timestamps** (departure time-of-day), `duration`, `legroom`, `extensions`, `plane_and_crew_by` / `ticket_also_sold_by` (**codeshare**).
- **Cross-offer dispersion:** several offers per call → price spread, carrier mix, routing mix — a market cross-section on *every* call.
- **`price_insights`:** Google's own `price_level`, `typical_price_range`, and a `price_history` array — captured as a **free external comparison signal** for our baseline (never the centerpiece; our own computed baseline is the differentiator).
- **`airports`:** reference block for the queried airports.

**Cabin is NOT free.** `travel_class` is a *request parameter* (1/2/3/4), so covering premium/business would be 3–4× the calls. Ingestion stays **economy-only**; the microstructure story leans on the axes that are free in one response (routing, carrier, stops, time-of-day, dispersion), not cabin.
