---
name: seats-aero-redemptions
description: Use when the user wants to search award/points flight availability via their seats.aero API key, or asks to find good mileage redemptions
---

# Seats.aero Redemptions

## Overview

seats.aero tracks cached award availability across ~20 mileage programs
(United, Delta, American, Air Canada Aeroplan, Alaska, Virgin Atlantic,
Emirates, Etihad, Qantas, ANA, Air France/KLM Flying Blue, Avianca
LifeMiles, Turkish Miles&Smiles, Velocity, EuroBonus, and more) and
exposes it through a Partner API. This skill wraps that API so Claude can
search availability and help the user judge which results are actually
good redemptions, not just available ones.

**Core principle:** availability alone isn't value. A result is only worth
surfacing if the mileage cost, taxes/fees, cabin, and routing add up to a
good deal for that user's miles.

## Setup

**Note:** this script needs outbound HTTPS to `seats.aero`. Sandboxed
environments with restrictive egress allowlists (including some Claude Code
remote sessions) may block that host entirely — if `search`/`trip`/etc. fail
with a proxy `403`/`CONNECT` error rather than a seats.aero error, that's a
network policy issue, not a bug in this script. Run it somewhere with normal
internet access if you hit that.

The script needs an API key in `SEATS_AERO_API_KEY`:

```bash
export SEATS_AERO_API_KEY="<the user's seats.aero Pro API key>"
```

Get the key from the user's seats.aero account: Settings -> API tab (requires
a Pro subscription). **Never commit the key to a file or repo** — it's a
personal credential, keep it in the shell environment only. Pro accounts get
up to 1,000 API calls/day; `search` paginates automatically, so keep date
ranges reasonably scoped (a few weeks to a couple months) rather than
querying a whole year at once.

## Running searches

```bash
python3 scripts/seats_aero.py search \
  --origin JFK --dest NRT --cabin J,F \
  --start 2026-09-01 --end 2026-09-30 --pretty
```

- `--origin` / `--dest`: comma-separated IATA airport codes (searching
  multiple origin or destination airports in one call is supported and
  cheaper than looping).
- `--cabin`: any of `Y` (economy), `W` (premium economy), `J` (business),
  `F` (first). Only ask for the cabins the user actually wants — narrower
  queries are faster and cheaper against the daily cap.
- `--source`: restrict to one program (e.g. `aeroplan`, `united`,
  `virginatlantic`) if the user only cares about miles they actually hold.
- `--only-direct`: nonstops only.

Each row in the response is a `CachedSearchData` object, one per date, with
per-cabin fields: `{X}Available`, `{X}MileageCost`, `{X}RemainingSeats`,
`{X}Airlines`, `{X}TotalTaxes` (in `TaxesCurrency`) for X in Y/W/J/F, plus
`Source` (the mileage program) and `Route`. Filter to `{cabin}Available ==
true` and sort by `{cabin}MileageCostRaw` ascending to find the cheapest
open dates.

For a specific promising row, look up full routing/segments/booking links
with:

```bash
python3 scripts/seats_aero.py trip --id <the row's ID field> --pretty
```

Trip detail returns `AvailabilityData` (stops, carriers, flight numbers,
departure/arrival times, duration) — use this before recommending a result,
since a cheap fare with 2 stops and a redeye may not be worth it.

`availability` (bulk, one program) and `routes` (routes a program covers)
are lower-level building blocks — use `search` for "find me a redemption"
requests; reach for these only when the user wants to browse everything a
specific program has, unfiltered by route.

## Judging whether a result is a *good* redemption

Don't just list availability — evaluate it. Weigh:

1. **Cents-per-point value.** Estimate what the cash fare would cost for
   the same flight (ask the user, or use general knowledge of typical
   fares for that route/cabin), then compute
   `(cash_fare - taxes) / miles_required * 100` in cents/point. Rough
   guide: economy redemptions are rarely worth it below ~1.2 cpp; business
   is solid at ~1.5-2.5 cpp and great above 3 cpp; first class needs ~3+
   cpp to beat cash given how expensive first fares run. Below ~1 cpp,
   say so plainly rather than presenting it as a win.
2. **Taxes and carrier surcharges.** Some programs/carriers route through
   partners with heavy fuel surcharges (e.g. booking Lufthansa/ANA/British
   Airways-operated flights via certain partner programs) — a "cheap"
   mileage cost can still cost $500+ in taxes. Flag high `TotalTaxes`
   explicitly.
   *Confirm current surcharge behavior before asserting specifics — carrier
   partnerships and surcharge policies change.*
3. **Routing quality.** Nonstop > 1-stop > 2-stop, reasonable connection
   times, no unnecessary backtracking. Pull trip detail before recommending.
4. **Seat count and booking window.** `RemainingSeats` of 1 means it can
   vanish before the user books — say so. Note how far out saver space
   typically opens for that program if relevant (many programs release in
   waves, e.g. 330-360 days out).
5. **Which miles the user actually holds.** A phenomenal Aeroplan business
   redemption is useless if the user only has United miles and no
   transferable points that route to Aeroplan. Ask which currencies/programs
   they have before assuming they can book everything returned.

Present results ranked by real value (cpp and routing quality), not just
by lowest mileage cost, and call out the tradeoffs rather than only the
best case.
