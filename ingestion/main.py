"""
Airfare Drift — fare ingestion Cloud Function.

Fetches current round-trip fares for the fixed route list from SerpApi's Google
Flights engine and appends the RAW responses to a date-partitioned BigQuery
table. One row per route per run, storing the full API response body verbatim.

Design rules (see CLAUDE.md):
  - Constraint #3 (keep raw data messy): we store the ENTIRE response body as-is
    (STRING), never reducing to "cheapest" or reshaping. All parsing/dedup/
    cleaning happens downstream in Dataform staging. This is the one irreversible
    decision here — once you drop the offer distribution at ingestion you can
    never recover it.
  - Constraint #1 (SerpApi budget): one call per route (the round-trip total
    arrives in a single response). 10 routes/run.
  - Append-only: duplicate/late snapshots are preserved on purpose (staging
    dedups). We never upsert.

Run modes:
  - Deployed: HTTP-triggered Cloud Function (Gen2), invoked by Cloud Scheduler
    every 2 days. Entry point: `ingest` (deploy with --target ingest).
  - Local dry run (no GCP needed, only `requests`):
        ./.venv/bin/python ingestion/main.py --dry-run
    Fetches all routes, writes rows to ingestion/.dryrun_output.json, and prints
    a console summary — validates the loop before any BigQuery/Scheduler setup.
    It does NOT write to BigQuery and does NOT start the accumulation clock.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

from config import ADVANCE_DAYS, CURRENCY, RETURN_GAP_DAYS, ROUTES

SERPAPI_URL = "https://serpapi.com/search"

# BigQuery destination is configured entirely by env vars so the same code runs
# in dev and prod without hardcoded dataset names.
DEFAULT_DATASET = "airfare_raw"
DEFAULT_TABLE = "fare_snapshots"


def query_dates(snapshot_date: date) -> tuple[date, date]:
    """The one consistent convention: fixed advance + fixed return gap."""
    outbound = snapshot_date + timedelta(days=ADVANCE_DAYS)
    return outbound, outbound + timedelta(days=RETURN_GAP_DAYS)


def fetch_route(api_key, origin, dest, outbound_date, return_date, timeout=30):
    """
    Return (http_status, raw_body_text). We keep the raw body verbatim — the
    api_key lives only in the request params, never in the response, so nothing
    sensitive is stored.
    """
    resp = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": dest,
            "outbound_date": outbound_date.isoformat(),
            "return_date": return_date.isoformat(),
            "type": "1",  # round trip; total round-trip price arrives in this one call
            "currency": CURRENCY,
            "hl": "en",
            "api_key": api_key,
        },
        timeout=timeout,
    )
    return resp.status_code, resp.text


def collect_snapshot(api_key, routes=ROUTES, snapshot_dt=None):
    """
    Fetch every route once and build one raw row per route. snapshot_date is
    fixed at run start (so all rows share a partition); captured_at is per-row.
    """
    snapshot_dt = snapshot_dt or datetime.now(timezone.utc)
    snapshot_date = snapshot_dt.date()
    outbound, return_date = query_dates(snapshot_date)

    rows = []
    for origin, dest in routes:
        try:
            status, body = fetch_route(api_key, origin, dest, outbound, return_date)
        except requests.exceptions.RequestException as exc:
            # Network-level failure (timeout, connection drop). Isolate it so one
            # bad route doesn't drop the other 9's snapshot for this run: record an
            # error row with a NULL http_status. Staging treats http_status IS NULL
            # as a failed fetch. (HTTP 4xx/5xx never reach here — requests only
            # raises on transport errors, so those are already captured as rows.)
            status, body = None, f"REQUEST_ERROR: {exc!r}"
        rows.append(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "snapshot_date": snapshot_date.isoformat(),
                "origin": origin,
                "destination": dest,
                "outbound_date": outbound.isoformat(),
                "return_date": return_date.isoformat(),
                "advance_days": ADVANCE_DAYS,
                "return_gap_days": RETURN_GAP_DAYS,
                "currency": CURRENCY,
                "http_status": status,
                "raw_response": body,  # full response body, stored as-is
            }
        )
    return rows


def _bq_schema():
    # Imported lazily so the dry run doesn't require google-cloud-bigquery.
    from google.cloud import bigquery

    return [
        bigquery.SchemaField("captured_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("snapshot_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("origin", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("destination", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("outbound_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("return_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("advance_days", "INTEGER"),
        bigquery.SchemaField("return_gap_days", "INTEGER"),
        bigquery.SchemaField("currency", "STRING"),
        bigquery.SchemaField("http_status", "INTEGER"),
        bigquery.SchemaField("raw_response", "STRING"),
    ]


def write_to_bigquery(rows, project, dataset, table):
    """
    Append rows via a load job (free tier) — not a streaming insert. Auto-creates
    the table (partitioned by snapshot_date, clustered by route) on first load;
    the dataset must already exist.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    table_id = f"{project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        schema=_bq_schema(),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field="snapshot_date"
        ),
        clustering_fields=["origin", "destination"],
    )
    client.load_table_from_json(rows, table_id, job_config=job_config).result()
    return len(rows)


def ingest(request):  # noqa: ARG001 — Cloud Functions HTTP entry point
    """
    HTTP-triggered entry point for the deployed Cloud Function. Cloud Scheduler
    hits this every 2 days. Deploy with `--target ingest --signature-type http`.
    """
    api_key = os.environ["SERPAPI_KEY"]
    project = os.environ["BQ_PROJECT"]
    dataset = os.environ.get("BQ_DATASET", DEFAULT_DATASET)
    table = os.environ.get("BQ_TABLE", DEFAULT_TABLE)

    rows = collect_snapshot(api_key)
    n = write_to_bigquery(rows, project, dataset, table)
    return (f"Ingested {n} route snapshots for {rows[0]['snapshot_date']}\n", 200)


# --- Local dry run ----------------------------------------------------------


def _summarize(row):
    """Parse offers for the console only — NOT stored; storage stays raw."""
    try:
        data = json.loads(row["raw_response"])
    except (ValueError, TypeError):
        return 0, "n/a"
    if isinstance(data, dict) and "error" in data:
        return 0, f"error: {data['error']}"
    offers = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    prices = [o["price"] for o in offers if o.get("price") is not None]
    return len(prices), (min(prices) if prices else "n/a")


def _dry_run():
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("Set SERPAPI_KEY for the dry run (spends 10 SerpApi searches).")

    rows = collect_snapshot(api_key)
    out_path = os.path.join(os.path.dirname(__file__), ".dryrun_output.json")
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)

    outbound = rows[0]["outbound_date"]
    print(f"Fetched {len(rows)} routes (depart {outbound}) -> {out_path}\n")
    any_zero = False
    for r in rows:
        n_offers, cheapest = _summarize(r)
        flag = ""
        if r["http_status"] != 200:
            flag = "  <-- HTTP ERROR"
            any_zero = True
        elif n_offers == 0:
            flag = "  <-- ZERO OFFERS"
            any_zero = True
        print(
            f"  {r['origin']}-{r['destination']}: http {r['http_status']}, "
            f"{n_offers} offers, cheapest {cheapest} {r['currency']}{flag}"
        )

    if any_zero:
        print(
            "\n⚠️  Some routes returned no offers / an error — inspect "
            ".dryrun_output.json before building on this."
        )
    else:
        print(
            "\n✅ All 10 routes returned offers. Loop is sound. This did NOT write "
            "to BigQuery — the accumulation clock starts only once deployed."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Airfare Drift ingestion")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch all routes and summarize locally; no BigQuery write.",
    )
    args = parser.parse_args()
    if args.dry_run:
        _dry_run()
    else:
        sys.exit(
            "Refusing to write to BigQuery from local __main__. "
            "Use --dry-run, or deploy as a Cloud Function."
        )
