#!/usr/bin/env python3
"""CLI client for the seats.aero Partner API.

Requires an API key in the SEATS_AERO_API_KEY environment variable
(or pass --api-key explicitly). Get a key from your seats.aero Pro
account settings -> API tab.

Subcommands:
  search       Cached search: award availability for an origin/destination
               over a date range (fast, covers many dates at once).
  availability Bulk availability: raw availability rows for one mileage
               program (source), optionally filtered by region/date.
  trip         Trip detail for a specific AvailabilityID: full segments,
               routing, and (when present) direct booking links.
  routes       List routes seats.aero tracks for a given mileage program.

Examples:
  seats_aero.py search --origin JFK --dest NRT --cabin J,F --start 2026-09-01 --end 2026-09-30
  seats_aero.py trip --id 5f8e...  # id comes from a search result's "ID" field
  seats_aero.py routes --source united
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://seats.aero/partnerapi"


def _request(path, params, api_key):
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Partner-Authorization": api_key})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 401:
            raise SystemExit(
                "seats.aero rejected the API key (401). Check SEATS_AERO_API_KEY."
            )
        if e.code == 429:
            raise SystemExit(
                "seats.aero rate limit hit (429). Pro API is capped at 1000 calls/day."
            )
        raise SystemExit(f"seats.aero API error {e.code}: {body}")


def cmd_search(args, api_key):
    params = {
        "origin_airport": args.origin,
        "destination_airport": args.dest,
        "cabin": args.cabin,
        "start_date": args.start,
        "end_date": args.end,
        "take": args.take,
    }
    if args.source:
        params["source"] = args.source
    if args.only_direct:
        params["only_direct_flights"] = "true"

    all_rows = []
    cursor = 0
    while True:
        if cursor:
            params["skip"] = cursor
        page = _request("/search", params, api_key)
        rows = page.get("data", [])
        all_rows.extend(rows)
        if not page.get("hasMore") and not page.get("HasMore"):
            break
        cursor = page.get("cursor") or page.get("Cursor")
        if cursor is None or args.max_pages and len(all_rows) >= args.max_pages * args.take:
            break
        time.sleep(0.2)  # be polite against the daily call cap
    return all_rows


def cmd_availability(args, api_key):
    params = {"source": args.source}
    if args.origin_region:
        params["origin_region"] = args.origin_region
    if args.dest_region:
        params["destination_region"] = args.dest_region
    if args.start:
        params["start_date"] = args.start
    if args.end:
        params["end_date"] = args.end
    if args.cabin:
        params["cabin"] = args.cabin
    return _request("/availability", params, api_key)


def cmd_trip(args, api_key):
    return _request(f"/trips/{args.id}", {}, api_key)


def cmd_routes(args, api_key):
    return _request("/routes", {"source": args.source}, api_key)


def main():
    parser = argparse.ArgumentParser(description="seats.aero Partner API client")
    parser.add_argument("--api-key", default=os.environ.get("SEATS_AERO_API_KEY"))
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="cached search across a date range")
    p_search.add_argument("--origin", required=True, help="e.g. JFK or JFK,EWR")
    p_search.add_argument("--dest", required=True, help="e.g. NRT or NRT,HND")
    p_search.add_argument("--cabin", default="Y,W,J,F", help="comma list of Y,W,J,F")
    p_search.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_search.add_argument("--end", required=True, help="YYYY-MM-DD")
    p_search.add_argument("--source", default=None, help="restrict to one mileage program")
    p_search.add_argument("--only-direct", action="store_true")
    p_search.add_argument("--take", type=int, default=500)
    p_search.add_argument("--max-pages", type=int, default=4)

    p_avail = sub.add_parser("availability", help="bulk availability for one program")
    p_avail.add_argument("--source", required=True, help="e.g. united, aeroplan, virginatlantic")
    p_avail.add_argument("--origin-region", default=None)
    p_avail.add_argument("--dest-region", default=None)
    p_avail.add_argument("--start", default=None)
    p_avail.add_argument("--end", default=None)
    p_avail.add_argument("--cabin", default=None)

    p_trip = sub.add_parser("trip", help="full trip detail for an AvailabilityID")
    p_trip.add_argument("--id", required=True)

    p_routes = sub.add_parser("routes", help="routes tracked for a mileage program")
    p_routes.add_argument("--source", required=True)

    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit(
            "No API key. Set SEATS_AERO_API_KEY or pass --api-key."
        )

    handlers = {
        "search": cmd_search,
        "availability": cmd_availability,
        "trip": cmd_trip,
        "routes": cmd_routes,
    }
    result = handlers[args.command](args, args.api_key)
    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent))


if __name__ == "__main__":
    main()
