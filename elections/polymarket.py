"""Polymarket election markets via the public Gamma API (no key needed).

Polymarket groups markets into events, e.g. event "Presidential Election Winner 2028" -> one Yes/No market
per candidate. We pull every event tagged with an election tag, both open and closed, so each snapshot
holds current prices for live markets and the resolution for closed ones (a resolved market's winning
outcome is priced 1).

One row per market. `outcomes` and `outcome_prices` are JSON lists in matching order; `yes_price` is the
first outcome's price (the "Yes" side of binary markets). `raw` keeps the API's full market object as JSON.
"""

import json
import time

from .common import dumps, get_json

API = "https://gamma-api.polymarket.com"
TAG_SLUGS = ["elections"]   # Polymarket's elections tag; add e.g. "politics" for broader coverage
PAGE = 100
PAUSE = 0.25

FIELDS = ["date", "tag", "event_id", "event_slug", "event_title", "market_id", "condition_id", "market_slug",
          "question", "group_item_title", "outcomes", "outcome_prices", "yes_price", "winner",
          "best_bid", "best_ask", "last_trade_price", "volume", "volume_24hr", "liquidity",
          "active", "closed", "uma_resolution_status", "start_date", "end_date", "closed_time",
          "clob_token_ids", "raw"]
# What changes day to day; the daily file keeps only these (see run_snapshot.py).
ID = "market_id"
PRICE_FIELDS = ["date", "event_id", "market_id", "closed", "winner", "outcome_prices", "yes_price", "best_bid",
                "best_ask", "last_trade_price", "volume", "volume_24hr", "liquidity"]


def resolved(row: dict) -> bool:
    return str(row["closed"]) == "True"


def as_list(v) -> list:
    """Gamma returns outcomes/prices/token ids as JSON-encoded strings."""
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if v else []
    except ValueError:
        return []


def events(tag: str) -> list[dict]:
    out = {}
    for closed in ("false", "true"):
        offset = 0
        while True:
            page = get_json(f"{API}/events", {"tag_slug": tag, "closed": closed, "limit": PAGE,
                                              "offset": offset, "order": "id", "ascending": "true"})
            new = [e for e in page if str(e.get("id")) not in out]
            if not new:   # empty page, or the server stopped advancing
                break
            out.update((str(e["id"]), e) for e in new)
            offset += len(page)
            time.sleep(PAUSE)
    return list(out.values())


def winner(m: dict, outcomes: list, prices: list) -> str:
    if not m.get("closed"):
        return ""
    for o, p in zip(outcomes, prices):
        try:
            if float(p) == 1:
                return o
        except (TypeError, ValueError):
            pass
    return ""


def fetch(day: str) -> list[dict]:
    rows, seen = [], set()
    for tag in TAG_SLUGS:
        evs = events(tag)
        print(f"  polymarket: {len(evs)} events tagged {tag!r}")
        for ev in evs:
            for m in ev.get("markets") or []:
                if m.get("id") in seen:
                    continue
                seen.add(m.get("id"))
                outcomes, prices = as_list(m.get("outcomes")), as_list(m.get("outcomePrices"))
                rows.append({
                    "date": day, "tag": tag, "event_id": ev.get("id", ""), "event_slug": ev.get("slug", ""),
                    "event_title": ev.get("title", ""), "market_id": m.get("id", ""),
                    "condition_id": m.get("conditionId", ""), "market_slug": m.get("slug", ""),
                    "question": m.get("question", ""), "group_item_title": m.get("groupItemTitle", ""),
                    "outcomes": dumps(outcomes), "outcome_prices": dumps(prices),
                    "yes_price": prices[0] if prices else "", "winner": winner(m, outcomes, prices),
                    "best_bid": m.get("bestBid", ""), "best_ask": m.get("bestAsk", ""),
                    "last_trade_price": m.get("lastTradePrice", ""),
                    "volume": m.get("volumeNum", m.get("volume", "")), "volume_24hr": m.get("volume24hr", ""),
                    "liquidity": m.get("liquidityNum", m.get("liquidity", "")),
                    "active": m.get("active", ""), "closed": m.get("closed", ""),
                    "uma_resolution_status": m.get("umaResolutionStatus", ""),
                    "start_date": m.get("startDate", ""), "end_date": m.get("endDate", ""),
                    "closed_time": m.get("closedTime", ""), "clob_token_ids": dumps(as_list(m.get("clobTokenIds"))),
                    "raw": dumps(m),
                })
    return rows
