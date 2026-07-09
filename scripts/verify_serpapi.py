#!/usr/bin/env python3
"""
Smoke test for SerpApi Google Flights before building the ingestion function.

Confirms three things we're relying on (see CLAUDE.md "Fare source"):
  1. Auth works and the free tier responds.
  2. A round-trip (type=1) search returns the total round-trip price in ONE
     call — so each route costs 1 search, not 2. This is what keeps 10 routes
     every 2 days (~150/mo) inside the 250/mo free tier.
  3. We can extract a single "cheapest fare" number per route to snapshot.

Usage:
    export SERPAPI_KEY=...            # serpapi.com free tier = 250 searches/mo
    pip install requests
    python scripts/verify_serpapi.py

Each run consumes 1 SerpApi search per route below — mind the monthly budget.
"""

import os
import sys
from datetime import date, timedelta

import requests

BASE_URL = "https://serpapi.com/search"

# --- The one consistent query convention (see CLAUDE.md "Route list"). ------
# The real ingestion function reuses these exact constants across all routes.
ADVANCE_DAYS = 30    # ~30-day advance purchase (active revenue-management zone)
RETURN_GAP_DAYS = 7  # fixed return gap
CURRENCY = "USD"

# Small sample: one stable control + the required volatile anchor.
TEST_ROUTES = [
    ("LAX", "JFK"),  # competitive trunk — should be relatively stable
    ("ATL", "CMN"),  # required anchor — thin/seasonal, should be volatile
]


def cheapest_fare(api_key: str, origin: str, dest: str, depart: date, ret: date):
    resp = requests.get(
        BASE_URL,
        params={
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": dest,
            "outbound_date": depart.isoformat(),
            "return_date": ret.isoformat(),
            "type": "1",  # round trip; total round-trip price arrives in this one call
            "currency": CURRENCY,
            "hl": "en",
            "api_key": api_key,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    if "error" in data:
        return None, f"API error: {data['error']}"
    # Google Flights splits results into best_flights + other_flights; the
    # cheapest round-trip total is the min price across both.
    offers = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    prices = [o["price"] for o in offers if o.get("price") is not None]
    if not prices:
        return None, "no priced offers returned"
    return min(prices), f"{len(prices)} priced offers, cheapest {min(prices)} {CURRENCY}"


def main():
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("Set SERPAPI_KEY (serpapi.com, free tier = 250 searches/month).")

    depart = date.today() + timedelta(days=ADVANCE_DAYS)
    ret = depart + timedelta(days=RETURN_GAP_DAYS)
    print(f"Query convention: round-trip, depart {depart}, return {ret}\n")

    ok = True
    for origin, dest in TEST_ROUTES:
        fare, detail = cheapest_fare(api_key, origin, dest, depart, ret)
        print(f"  {origin}-{dest}: {detail}")
        if fare is None:
            ok = False

    if ok:
        print(
            "\n✅ Round-trip totals returned in a single call per route. "
            "Ready to build the ingestion function against this convention."
        )
    else:
        print("\n⚠️  Some routes returned no price — inspect before building ingestion.")


if __name__ == "__main__":
    main()
