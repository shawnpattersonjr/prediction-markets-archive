"""Kalshi election markets via the public Trade API (no key needed for market data).

Kalshi groups markets as series -> events -> markets, e.g. series PRES (presidential winner) -> event
PRES-2028 -> markets PRES-2028-DEM, PRES-2028-REP. We list every series in the election categories, then
pull all of each series' events with their markets, in every status (open, closed, settled), so each
snapshot holds current prices for live markets and the result for resolved ones.

One row per market. Prices are in dollars (0-1, = implied probability); `raw` keeps the API's full market
object as JSON so fields we don't break out are still archived.
"""

import time

from .common import dumps, get_json

API = "https://api.elections.kalshi.com/trade-api/v2"
CATEGORIES = ["Elections"]   # Kalshi's category for races; add "Politics" for policy/approval markets
PAUSE = 0.15                 # basic tier allows ~20 reads/s

FIELDS = ["date", "category", "series_ticker", "series_title", "event_ticker", "event_title", "event_subtitle",
          "ticker", "title", "subtitle", "yes_sub_title", "status", "result", "settlement_value",
          "yes_bid", "yes_ask", "no_bid", "no_ask", "last_price", "previous_price",
          "volume", "volume_24h", "open_interest",
          "open_time", "close_time", "expiration_time", "settlement_ts", "rules_primary", "raw"]
# What changes day to day; the daily file keeps only these (see run_snapshot.py).
ID = "ticker"
PRICE_FIELDS = ["date", "event_ticker", "ticker", "status", "result", "settlement_value", "yes_bid", "yes_ask",
                "no_bid", "no_ask", "last_price", "volume", "volume_24h", "open_interest"]


def resolved(row: dict) -> bool:
    return bool(row["result"])


def paged(path: str, key: str, params: dict):
    """Yield every item of a cursor-paginated list endpoint."""
    params = dict(params)
    while True:
        data = get_json(f"{API}{path}", params)
        yield from data.get(key) or []
        cursor = data.get("cursor")
        if not cursor:
            return
        params["cursor"] = cursor
        time.sleep(PAUSE)


def dollars(m: dict, name: str):
    """Kalshi moved from integer cents (`yes_bid`) to dollar strings (`yes_bid_dollars`); accept either."""
    if m.get(f"{name}_dollars") not in (None, ""):
        return m[f"{name}_dollars"]
    if m.get(name) not in (None, ""):
        return round(m[name] / 100, 4)
    return ""


def count(m: dict, name: str):
    """Contract counts, which Kalshi also offers as fixed-point strings (`volume_fp`)."""
    for k in (name, f"{name}_fp"):
        if m.get(k) not in (None, ""):
            return m[k]
    return ""


def series() -> list[dict]:
    out = {}
    for cat in CATEGORIES:
        for s in paged("/series", "series", {"category": cat}):
            if (s.get("category") or cat) == cat:   # in case the server ignores the filter
                out[s["ticker"]] = s
        time.sleep(PAUSE)
    return list(out.values())


def fetch(day: str) -> list[dict]:
    rows = []
    all_series = series()
    print(f"  kalshi: {len(all_series)} series in {CATEGORIES}")
    for n, s in enumerate(all_series, 1):
        try:
            events = list(paged("/events", "events",
                                {"series_ticker": s["ticker"], "with_nested_markets": "true", "limit": 200}))
        except Exception as e:
            print(f"  kalshi {s['ticker']}: failed ({e})")
            continue
        for ev in events:
            for m in ev.get("markets") or []:
                rows.append({
                    "date": day, "category": s.get("category", ""), "series_ticker": s["ticker"],
                    "series_title": s.get("title", ""), "event_ticker": ev.get("event_ticker", ""),
                    "event_title": ev.get("title", ""), "event_subtitle": ev.get("sub_title", ""),
                    "ticker": m.get("ticker", ""), "title": m.get("title", ""), "subtitle": m.get("subtitle", ""),
                    "yes_sub_title": m.get("yes_sub_title", ""), "status": m.get("status", ""),
                    "result": m.get("result", ""), "settlement_value": dollars(m, "settlement_value"),
                    **{p: dollars(m, p) for p in ["yes_bid", "yes_ask", "no_bid", "no_ask",
                                                  "last_price", "previous_price"]},
                    **{c: count(m, c) for c in ["volume", "volume_24h", "open_interest"]},
                    **{t: m.get(t, "") for t in ["open_time", "close_time", "expiration_time",
                                                 "settlement_ts", "rules_primary"]},
                    "raw": dumps(m),
                })
        if n % 100 == 0:
            print(f"  kalshi: {n}/{len(all_series)} series, {len(rows)} markets")
        time.sleep(PAUSE)
    return rows
