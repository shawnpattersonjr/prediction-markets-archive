"""Minute-by-minute prices for the 2026 midterms: election night, then the races still being counted.

For each UTC day from Nov 3, 2026 to yesterday, writes up to three files:

  intraday-<day>-kalshi.csv.gz         Kalshi 1-minute candles
      event_ticker, ticker, time, price_open, price_high, price_low, price_close, price_mean,
      yes_bid_close, yes_ask_close, volume, open_interest   (time = end of the minute, UTC; prices 0-1)
  intraday-<day>-kalshi-trades.csv.gz  every Kalshi trade in the headline markets (chamber control, Senate and
                                       governor winners)
      event_ticker, ticker, time, yes_price, no_price, count, taker_side, trade_id
  intraday-<day>-polymarket.csv.gz     Polymarket CLOB price of each market's first outcome, about once a minute
      event_id, market_id, outcome, time, price

Which markets: on Nov 3-4, every 2026 election market that has resolved, plus the winner/control markets still
open; from Nov 5 on, only winner/control markets (the races still being called), each until it closes. Only
races that could have been settled on Nov 3 count: runoffs, swearing-in dates, margin and turnout counts that
wait for certification, and foreign elections are left out.
The files are too big for git, so run_intraday.py uploads them to a GitHub release instead of committing them.
"""

import csv
import gzip
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import kalshi as k
from .common import get_json, load_markets
from .history import CLOB, kalshi_candles, ts

ROOT = Path(__file__).resolve().parent.parent
FIRST_DAY = date(2026, 11, 3)
NIGHT = {date(2026, 11, 3), date(2026, 11, 4)}
YEAR_26 = re.compile(r"-(26|2026)\b")
WINNER = re.compile(r"winner|who will win|control|which party will win", re.I)
# Markets that could not settle on election night: runoffs, swearing-in dates, and foreign elections that the
# 2026-ticker rule below lets in.
NOT_NOV3 = re.compile(r"runoff|sworn in|Gambia|Leban", re.I)
# Headline Kalshi races for the trade-level file; "State Senate/House" (legislatures) are left out.
HEADLINE = re.compile(r"^Who will control the (House|Senate)\?|^(?!.*\bState\b).*\b(Senate|Governor) winner\?", re.I)

KALSHI_FIELDS = ["event_ticker", "ticker", "time", "price_open", "price_high", "price_low", "price_close",
                 "price_mean", "yes_bid_close", "yes_ask_close", "volume", "open_interest"]
TRADE_FIELDS = ["event_ticker", "ticker", "time", "yes_price", "no_price", "count", "taker_side", "trade_id"]
POLY_FIELDS = ["event_id", "market_id", "outcome", "time", "price"]


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Which markets --------------------------------------------------------------------------------------------

def kalshi_markets() -> list[dict]:
    """2026 election markets still trading on Nov 3. Kalshi dates them inconsistently (House control "occurs"
    when called, Texas Senate when the winner is sworn in), so take any of: occurrence on Nov 3, expected
    settlement Nov 3-4, or a 2026 event ticker (CONTROLH-2026, SENATETX-26)."""
    out = []
    for m in load_markets(ROOT / "data", "kalshi", k.ID).values():
        raw = json.loads(m["raw"] or "{}")
        if not ((raw.get("occurrence_datetime") or "")[:10] == "2026-11-03"
                or (raw.get("expected_expiration_time") or "")[:10] in ("2026-11-03", "2026-11-04")
                or YEAR_26.search(m["event_ticker"])):
            continue
        m["resolved"] = bool(m["result"]) or m["status"] in ("closed", "determined", "finalized", "settled")
        if m["resolved"] and (m["close_time"] or "9999") < "2026-11-03":
            continue   # settled before election day (primaries and the like)
        out.append(m)
    return out


def poly_markets() -> list[dict]:
    """2026 election-day markets: events Polymarket set to end Nov 3-4, 2026."""
    out = []
    for m in load_markets(ROOT / "data", "polymarket", "market_id").values():
        if m["end_date"][:10] in ("2026-11-03", "2026-11-04"):
            m["resolved"] = m["closed"] == "True"
            out.append(m)
    return out


def trading_on(m: dict, day: date, title: str, closed_at: str) -> bool:
    """Should this market be in the file for `day`? Only races that could have been called on election night."""
    if NOT_NOV3.search(title + " " + (m.get("title") or m.get("question") or "")):
        return False
    if day not in NIGHT and not WINNER.search(title):
        return False
    if day in NIGHT and not m["resolved"] and not WINNER.search(title):
        return False   # open margin/turnout markets: thousands of them, left out
    end = ts(closed_at) if m["resolved"] else None
    start_of_day = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    return end is None or end >= start_of_day


# --- Fetchers -------------------------------------------------------------------------------------------------

def kalshi_minutes(m: dict, start: int, end: int) -> list[dict]:
    rows = []
    for c in kalshi_candles(m["series_ticker"], m["ticker"], start, end, period=1):
        price, bid, ask = c.get("price") or {}, c.get("yes_bid") or {}, c.get("yes_ask") or {}
        rows.append({
            "event_ticker": m["event_ticker"], "ticker": m["ticker"], "time": iso(c["end_period_ts"]),
            "price_open": k.dollars(price, "open"), "price_high": k.dollars(price, "high"),
            "price_low": k.dollars(price, "low"), "price_close": k.dollars(price, "close"),
            "price_mean": k.dollars(price, "mean"),
            "yes_bid_close": k.dollars(bid, "close"), "yes_ask_close": k.dollars(ask, "close"),
            "volume": k.count(c, "volume"), "open_interest": k.count(c, "open_interest"),
        })
    return rows


def kalshi_trades(m: dict, start: int, end: int) -> list[dict]:
    return [{"event_ticker": m["event_ticker"], "ticker": m["ticker"], "time": t.get("created_time", ""),
             "yes_price": k.dollars(t, "yes_price"), "no_price": k.dollars(t, "no_price"),
             "count": k.count(t, "count"), "taker_side": t.get("taker_side", ""), "trade_id": t.get("trade_id", "")}
            for t in k.paged("/markets/trades", "trades",
                             {"ticker": m["ticker"], "min_ts": start, "max_ts": end, "limit": 1000})]


def poly_minutes(m: dict, start: int, end: int) -> list[dict]:
    tokens, outcomes = json.loads(m["clob_token_ids"] or "[]"), json.loads(m["outcomes"] or "[]")
    if not tokens:
        return []
    hist = get_json(f"{CLOB}/prices-history", {"market": tokens[0], "startTs": start, "endTs": end, "fidelity": 1})
    return [{"event_id": m["event_id"], "market_id": m["market_id"], "outcome": outcomes[0] if outcomes else "",
             "time": iso(int(p["t"])), "price": p["p"]}
            for p in hist.get("history") or [] if start <= int(p["t"]) < end]


def collect(day: date, deadline: float, out_dir: Path) -> list[Path] | None:
    """Write the day's files into out_dir as rows arrive (a night's Kalshi candles run to millions of rows).
    Returns their paths, Polymarket last, or None if the time budget ran out first (partial files removed)."""
    start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    end = start + 86400
    jobs = []
    for m in kalshi_markets():
        if trading_on(m, day, m["event_title"], m["close_time"]):
            jobs.append(("kalshi", m, kalshi_minutes, k.PAUSE))
            if HEADLINE.search(m["event_title"].strip()):
                jobs.append(("kalshi-trades", m, kalshi_trades, k.PAUSE))
    for m in poly_markets():
        if trading_on(m, day, m["event_title"], m["closed_time"]):
            jobs.append(("polymarket", m, poly_minutes, 0.1))
    names = {"kalshi": KALSHI_FIELDS, "kalshi-trades": TRADE_FIELDS, "polymarket": POLY_FIELDS}
    print(f"{day}: markets", {n: sum(j[0] == n for j in jobs) for n in names}, flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {n: out_dir / f"intraday-{day}-{n}.csv.gz" for n in names}
    files = {n: gzip.open(p.with_suffix(".gz.tmp"), "wt", newline="", encoding="utf-8") for n, p in paths.items()}
    writers = {n: csv.DictWriter(files[n], fieldnames=f, extrasaction="ignore") for n, f in names.items()}
    for w in writers.values():
        w.writeheader()
    rows = dict.fromkeys(names, 0)
    finished = True
    for i, (name, m, fetch, pause) in enumerate(jobs, 1):
        if time.monotonic() > deadline:
            finished = False
            break
        try:
            got = fetch(m, start, end)
        except Exception as e:
            print(f"  {name} {m.get('ticker') or m.get('market_id')}: failed ({e})")
            got = []
        writers[name].writerows(got)
        rows[name] += len(got)
        time.sleep(pause)
        if i % 500 == 0:
            print(f"  {i}/{len(jobs)}", flush=True)
    for f in files.values():
        f.close()
    for n, p in paths.items():
        tmp = p.with_suffix(".gz.tmp")
        if finished:
            tmp.replace(p)
            print(f"{day} {n}: {rows[n]:,} rows, {p.stat().st_size / 1e6:.1f} MB", flush=True)
        else:
            tmp.unlink()
    return list(paths.values()) if finished else None


def days_to_do(done: set[str]) -> list[date]:
    """Complete UTC days from FIRST_DAY to yesterday whose files are not uploaded yet."""
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    days, d = [], FIRST_DAY
    while d <= yesterday:
        if f"intraday-{d}-polymarket.csv.gz" not in done:   # written last, so it marks a finished day
            days.append(d)
        d += timedelta(days=1)
    return days
