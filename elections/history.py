"""Daily price history for every market in the latest snapshot, from the day it opened.

Reads the newest data/<date>/{kalshi,polymarket}.csv.gz for the list of markets and writes one file per
event (race), with one row per market per day:

  history/kalshi/<series_ticker>/<event_ticker>.csv.gz
      event_ticker, ticker, date, price_close, price_mean, yes_bid_close, yes_ask_close, volume, open_interest
      (Kalshi daily candlesticks; prices in dollars 0-1; price_* is empty on days with no trades)
  history/polymarket/<event_id>.csv.gz
      event_id, market_id, outcome, date, price
      (Polymarket CLOB daily price of the market's first outcome, i.e. "Yes" for binary markets)

Progress is kept in history/<source>/manifest.json. An event whose markets have all resolved is fetched once
more after it closes and then never again; an open event is refreshed every REFRESH_DAYS (the daily snapshot
covers the days in between). Events never fetched go first, biggest volume first. Each run stops after a time
budget and the next run picks up where it left off, so the first full backfill spreads over several runs.
"""

import csv
import gzip
import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import kalshi as k
from .common import NotFound, get_json, write_csv_gz

ROOT = Path(__file__).resolve().parent.parent
REFRESH_DAYS = 7
DAY = 86400

KALSHI_FIELDS = ["event_ticker", "ticker", "date", "price_close", "price_mean", "yes_bid_close", "yes_ask_close",
                 "volume", "open_interest"]
POLY_FIELDS = ["event_id", "market_id", "outcome", "date", "price"]
CLOB = "https://clob.polymarket.com"


def latest_snapshot(source: str) -> list[dict]:
    files = sorted((ROOT / "data").glob(f"*/{source}.csv.gz"))
    if not files:
        return []
    with gzip.open(files[-1], "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ts(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def ymd(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).date().isoformat()


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --- Kalshi -------------------------------------------------------------------------------------------------

def kalshi_candles(series: str, ticker: str, start: int, end: int) -> list[dict]:
    """Daily candles. Kalshi moves long-settled markets to a separate historical endpoint, so fall back to it."""
    params = {"start_ts": start, "end_ts": end, "period_interval": 1440}
    for path in (f"/series/{series}/markets/{ticker}/candlesticks", f"/historical/markets/{ticker}/candlesticks"):
        try:
            candles = get_json(f"{k.API}{path}", params).get("candlesticks") or []
        except NotFound:
            candles = []
        if candles:
            return candles
        time.sleep(k.PAUSE)
    return []


def kalshi_event(markets: list[dict], now: int) -> list[dict]:
    rows = []
    for m in markets:
        start = ts(m["open_time"]) or now - 5 * 365 * DAY
        end = min(ts(m["close_time"]) or now, now) + DAY
        for c in kalshi_candles(m["series_ticker"], m["ticker"], start, end):
            price, bid, ask = c.get("price") or {}, c.get("yes_bid") or {}, c.get("yes_ask") or {}
            rows.append({
                "event_ticker": m["event_ticker"], "ticker": m["ticker"], "date": ymd(c["end_period_ts"] - 1),
                "price_close": k.dollars(price, "close"), "price_mean": k.dollars(price, "mean"),
                "yes_bid_close": k.dollars(bid, "close"), "yes_ask_close": k.dollars(ask, "close"),
                "volume": k.count(c, "volume"), "open_interest": k.count(c, "open_interest"),
            })
        time.sleep(k.PAUSE)
    return rows


# --- Polymarket ---------------------------------------------------------------------------------------------

def poly_prices(token: str, start: int | None, end: int) -> list[dict]:
    """Daily prices. Very long ranges can come back empty, so fall back to interval=max, then to yearly chunks."""
    if start:
        hist = get_json(f"{CLOB}/prices-history", {"market": token, "startTs": start, "endTs": end,
                                                    "fidelity": 1440}).get("history") or []
        if hist:
            return hist
    hist = get_json(f"{CLOB}/prices-history", {"market": token, "interval": "max", "fidelity": 1440}).get("history")
    if hist or not start:
        return hist or []
    out = []
    for s in range(start, end, 365 * DAY):
        out += get_json(f"{CLOB}/prices-history", {"market": token, "startTs": s, "endTs": min(s + 365 * DAY, end),
                                                   "fidelity": 1440}).get("history") or []
        time.sleep(0.2)
    return out


def poly_event(markets: list[dict], now: int) -> list[dict]:
    rows = []
    for m in markets:
        tokens, outcomes = json.loads(m["clob_token_ids"] or "[]"), json.loads(m["outcomes"] or "[]")
        if not tokens:
            continue
        raw = json.loads(m["raw"] or "{}")
        start = ts(m["start_date"]) or ts(raw.get("createdAt", ""))
        end = min(ts(m["closed_time"]) or ts(m["end_date"]) or now, now) + DAY
        by_day = {}
        for p in poly_prices(tokens[0], start, end):
            by_day[ymd(int(p["t"]))] = p["p"]   # keep the last price of each day
        for d, p in sorted(by_day.items()):
            rows.append({"event_id": m["event_id"], "market_id": m["market_id"],
                         "outcome": outcomes[0] if outcomes else "", "date": d, "price": p})
        time.sleep(0.2)
    return rows


# --- Driver -------------------------------------------------------------------------------------------------

SOURCES = {
    # source: (event key, output path for an event's markets, is-resolved test, fetcher, fields)
    "kalshi": ("event_ticker", lambda ms: Path(ms[0]["series_ticker"]) / f"{ms[0]['event_ticker']}.csv.gz",
               lambda m: bool(m["result"]), kalshi_event, KALSHI_FIELDS),
    "polymarket": ("event_id", lambda ms: Path(f"{ms[0]['event_id']}.csv.gz"),
                   lambda m: m["closed"] == "True", poly_event, POLY_FIELDS),
}


def backfill(minutes: float) -> dict[str, int]:
    start = time.monotonic()
    today, now = date.today().isoformat(), int(time.time())
    stale = (date.today() - timedelta(days=REFRESH_DAYS)).isoformat()
    done = {}
    for source, (key, rel, resolved, fetch, fields) in SOURCES.items():
        # Kalshi may use 2/3 of the budget, so Polymarket still gets a turn while Kalshi's backlog is long.
        deadline = start + minutes * 60 * (2 / 3 if source == "kalshi" else 1)
        out_dir = ROOT / "history" / source
        manifest_path = out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        events = defaultdict(list)
        for m in latest_snapshot(source):
            events[m[key]].append(m)
        todo = [e for e, ms in events.items()
                if not manifest.get(e, {}).get("final") and manifest.get(e, {}).get("fetched", "") <= stale]
        todo.sort(key=lambda e: (e in manifest, -sum(num(m["volume"]) for m in events[e])))
        print(f"{source}: {len(events)} events, {len(todo)} to fetch")
        done[source] = 0
        for e in todo:
            if time.monotonic() > deadline:
                print(f"{source}: time budget reached, {len(todo) - done[source]} events left for the next run")
                break
            ms = events[e]
            try:
                rows = fetch(ms, now)
            except Exception as ex:
                print(f"  {source} {e}: failed ({ex})")
                continue
            if rows:
                write_csv_gz(out_dir / rel(ms), fields, rows)
            manifest[e] = {"fetched": today, "final": bool(rows) and all(resolved(m) for m in ms), "rows": len(rows)}
            done[source] += 1
            if done[source] % 50 == 0:
                manifest_path.write_text(json.dumps(manifest, indent=0, sort_keys=True))
                print(f"  {source}: {done[source]}/{len(todo)} events")
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=0, sort_keys=True))
    return done
