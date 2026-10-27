"""Kalshi election markets via the public Trade API (no key needed for market data).

Kalshi groups markets as series -> events -> markets, e.g. series PRES (presidential winner) -> event
PRES-2024 -> markets PRES-2024-DJT, PRES-2024-KH. We list every series in the Elections category, plus the
election events of the Politics category (where some older races such as PRES live), then pull each
series' events with their markets in every status. Markets settled before Kalshi's historical cutoff
(GET /historical/cutoff) are no longer nested in /events, so once a week we also page /historical/markets
per series.

One row per market. Prices are in dollars (0-1, = implied probability); `raw` keeps the API's full market
object as JSON so fields we don't break out are still archived.
"""

import re
import time
from datetime import date

from .common import dumps, get_json

API = "https://api.elections.kalshi.com/trade-api/v2"
CATEGORIES = ["Elections", "Politics"]   # Politics is filtered to election events, see is_election()
ELECTION_WORDS = re.compile(r"elect|primar|runoff|caucus|referend", re.I)
PAUSE = 0.15                 # basic tier allows ~20 reads/s
ARCHIVE_WEEKDAY = 6          # Sunday: also page /historical/markets (settled long ago, so weekly is plenty)

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
    """Kalshi moved from integer cents (`yes_bid`) to dollar strings (`yes_bid_dollars`, or a bare "0.5000"
    in historical candles); accept any of them."""
    v = m.get(f"{name}_dollars")
    if v in (None, ""):
        v = m.get(name)
    if v in (None, ""):
        return ""
    return v if isinstance(v, str) else round(v / 100, 4)


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


def is_election(s: dict, ev: dict) -> bool:
    if s.get("category") == "Elections":
        return True
    meta = ev.get("product_metadata") or {}
    return meta.get("competition_scope") == "Election" or bool(
        ELECTION_WORDS.search(f"{s.get('title', '')} {ev.get('title', '')}"))


def fetch(day: str, archive: bool | None = None) -> list[dict]:
    """Archived markets are only listed on ARCHIVE_WEEKDAY (or when archive=True): they have settled, so
    the copy in an earlier snapshot is final, and listing them doubles the run time."""
    if archive is None:
        archive = date.fromisoformat(day).weekday() == ARCHIVE_WEEKDAY
    rows, seen = [], set()
    all_series = series()
    print(f"  kalshi: {len(all_series)} series in {CATEGORIES}{', with archive' if archive else ''}")
    for n, s in enumerate(all_series, 1):
        try:
            events = {ev["event_ticker"]: ev for ev in paged(
                "/events", "events", {"series_ticker": s["ticker"], "with_nested_markets": "true", "limit": 200})}
            markets = [(ev, m) for ev in events.values() for m in ev.get("markets") or []]
            if archive:
                time.sleep(PAUSE)
                for m in paged("/historical/markets", "markets", {"series_ticker": s["ticker"], "limit": 1000}):
                    ev = events.get(m.get("event_ticker")) or {"event_ticker": m.get("event_ticker", ""),
                                                               "title": m.get("title", "")}
                    markets.append((ev, m))
            markets = [(ev, m) for ev, m in markets if is_election(s, ev)]
        except Exception as e:
            print(f"  kalshi {s['ticker']}: failed ({e})")
            continue
        for ev, m in markets:
            if m.get("ticker") in seen:
                continue
            seen.add(m.get("ticker"))
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
