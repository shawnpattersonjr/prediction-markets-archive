"""One-off API diagnostics, run from GitHub Actions (the dev sandbox can't reach these APIs)."""
import json
import sys
sys.path.insert(0, ".")
import requests
from pathlib import Path
from elections.common import HEADERS, load_markets

def show(label, url, params=None):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        body = r.text
        try:
            j = r.json()
            summary = {k: (len(v) if isinstance(v, list) else v) for k, v in j.items()} if isinstance(j, dict) else f"list[{len(j)}]"
            first = next((v[:1] for v in (j.values() if isinstance(j, dict) else [j]) if isinstance(v, list) and v), None)
        except ValueError:
            summary, first = body[:200], None
        print(f"[{r.status_code}] {label}: {json.dumps(summary, default=str)[:400]}")
        if first:
            print("      first:", json.dumps(first, default=str)[:600])
    except Exception as e:
        print(f"[ERR] {label}: {e}")

pm = load_markets(Path("data"), "polymarket", "market_id")
pres = [m for m in pm.values() if m["event_title"] == "Presidential Election Winner 2024"]
trump = max(pres, key=lambda m: float(m["volume"] or 0))
tok = json.loads(trump["clob_token_ids"])[0]
print("POLY 2024 market:", trump["question"], trump["start_date"], trump["end_date"], trump["closed_time"])
C = "https://clob.polymarket.com/prices-history"
show("startTs..endTs fid1440", C, {"market": tok, "startTs": 1704067200, "endTs": 1731000000, "fidelity": 1440})
show("interval=max fid1440", C, {"market": tok, "interval": "max", "fidelity": 1440})
show("interval=max fid720", C, {"market": tok, "interval": "max", "fidelity": 720})
show("interval=max", C, {"market": tok, "interval": "max"})
show("30-day window fid1440", C, {"market": tok, "startTs": 1727740800, "endTs": 1730332800, "fidelity": 1440})
show("30-day window fid60", C, {"market": tok, "startTs": 1727740800, "endTs": 1730332800, "fidelity": 60})
open_m = next(m for m in pm.values() if m["event_title"].startswith("PA-07 House Election Winner"))
otok = json.loads(open_m["clob_token_ids"])[0]
print("POLY open market:", open_m["question"], open_m["start_date"])
show("open interval=max fid1440", C, {"market": otok, "interval": "max", "fidelity": 1440})
show("open startTs fid1440", C, {"market": otok, "startTs": 1735689600, "endTs": 1761600000, "fidelity": 1440})

K = "https://api.elections.kalshi.com/trade-api/v2"
show("kalshi /series/PRES", f"{K}/series/PRES")
show("kalshi /events PRES", f"{K}/events", {"series_ticker": "PRES", "with_nested_markets": "true"})
show("kalshi /markets PRES", f"{K}/markets", {"series_ticker": "PRES"})
show("kalshi /historical/cutoff", f"{K}/historical/cutoff")
show("kalshi /historical/markets PRES", f"{K}/historical/markets", {"series_ticker": "PRES", "limit": 5})
show("kalshi /historical/markets event PRES-2024", f"{K}/historical/markets", {"event_ticker": "PRES-2024", "limit": 5})
show("kalshi /historical/events", f"{K}/historical/events", {"series_ticker": "PRES", "limit": 5})
show("kalshi /historical/markets/PRES-2024-DJT", f"{K}/historical/markets/PRES-2024-DJT")
for path in ("/series/PRES/markets/PRES-2024-DJT/candlesticks", "/historical/markets/PRES-2024-DJT/candlesticks"):
    show(f"kalshi candles {path}", f"{K}{path}", {"start_ts": 1704067200, "end_ts": 1731000000, "period_interval": 1440})
show("kalshi /historical/markets (any)", f"{K}/historical/markets", {"limit": 3})
show("kalshi /series Elections count", f"{K}/series", {"category": "Elections"})
