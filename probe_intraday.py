"""Temporary probe: how fine-grained is election-night price data? (branch only, not for main)"""
import requests
from datetime import datetime, timezone

H = {"User-Agent": "Mozilla/5.0 (Penn APPC research; election market archive)", "Accept": "application/json"}
TOKEN = "83247781037352156539108067944461291821683755894607244160607042790356561625563"  # PM: Dems control House
START, END = int(datetime(2026, 11, 3, 22, tzinfo=timezone.utc).timestamp()), int(datetime(2026, 11, 4, 14, tzinfo=timezone.utc).timestamp())


def show(name, url, params, key):
    r = requests.get(url, params=params, headers=H, timeout=60)
    print(f"== {name}: {r.status_code}")
    try:
        body = r.json()
    except ValueError:
        print("  ", r.text[:300]); return
    items = body.get(key) if isinstance(body, dict) else body
    if not isinstance(items, list):
        print("  ", str(body)[:400]); return
    print("   n =", len(items))
    for it in items[:2] + items[-2:]:
        print("   ", str(it)[:300])
    if isinstance(body, dict):
        print("   other keys:", {k: str(v)[:80] for k, v in body.items() if k != key})


CLOB = "https://clob.polymarket.com/prices-history"
show("PM fidelity=1, 16h window", CLOB, {"market": TOKEN, "startTs": START, "endTs": END, "fidelity": 1}, "history")
show("PM fidelity=1, 3 day window", CLOB, {"market": TOKEN, "startTs": START - 2 * 86400, "endTs": END, "fidelity": 1}, "history")
show("PM interval=1d fidelity=1", CLOB, {"market": TOKEN, "interval": "1d", "fidelity": 1}, "history")
show("PM interval=max fidelity=1", CLOB, {"market": TOKEN, "interval": "max", "fidelity": 1}, "history")
show("PM data-api trades", "https://data-api.polymarket.com/trades", {"market": "0x", "limit": 5}, None)

K = "https://api.elections.kalshi.com/trade-api/v2"
for path in ("/series/CONTROLH/markets/CONTROLH-2026-R/candlesticks", "/historical/markets/CONTROLH-2026-R/candlesticks"):
    show(f"Kalshi 1-min candles {path.split('/')[1]}", K + path,
         {"start_ts": START, "end_ts": END, "period_interval": 1}, "candlesticks")
show("Kalshi 1-min, 3 day window", K + "/series/CONTROLH/markets/CONTROLH-2026-R/candlesticks",
     {"start_ts": START - 2 * 86400, "end_ts": END, "period_interval": 1}, "candlesticks")
show("Kalshi trades", K + "/markets/trades", {"ticker": "CONTROLH-2026-R", "min_ts": START, "max_ts": END, "limit": 1000}, "trades")
