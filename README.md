# Prediction markets archive

Daily snapshots of every election market on Kalshi and Polymarket, collected by GitHub Actions.
Both sites publish current prices through free public APIs but keep only limited history, so we keep our own.

| Source | What's collected | API |
|---|---|---|
| **Kalshi** | Every market in every series in the `Elections` category: open, closed and settled | Trade API v2 (`api.elections.kalshi.com`), no key |
| **Polymarket** | Every market in every event tagged `elections`: open and closed | Gamma API (`gamma-api.polymarket.com`), no key |

Files (dates are UTC), per source:

- `data/<YYYY-MM-DD>/<source>.csv.gz`: that day's prices and status for every **open** market, plus markets
  that resolved since the previous snapshot (so each result appears once). Resolved markets are dropped after that.
- `data/<YYYY-MM-DD>/<source>_markets.csv.gz`: full details of markets that **first appeared or resolved** that day.
  Together these files hold every market ever seen; the latest row for a market has its outcome.
  `elections.common.load_markets()` combines them. The first snapshot (2026-10-27) holds all markets then listed.

Daily columns:
- **Kalshi:** `event_ticker, ticker, status, result` (`yes`/`no` once settled), `settlement_value`, yes/no
  bid and ask and `last_price` in dollars (0–1, which equals the implied probability), `volume, volume_24h, open_interest`.
- **Polymarket:** `event_id, market_id, closed, winner` (the outcome priced 1 after resolution), `outcome_prices`
  (JSON list), `yes_price`, bid/ask/last, `volume, volume_24hr, liquidity`.

Details columns add titles, the series/event they belong to, the resolution rules, open/close dates, outcome names,
`clob_token_ids` (Polymarket), and `raw`, the API's full market object as JSON.

## Price history

`history/` holds the daily odds for every market ever snapshotted, going back to the day it opened:

- `history/kalshi/<series>/<event>.csv.gz`: `event_ticker, ticker, date, price_close, price_mean, yes_bid_close,
  yes_ask_close, volume, open_interest`. These come from Kalshi's daily candlesticks. `price_*` is empty on
  days with no trades; the bid/ask still give the market's odds on those days.
- `history/polymarket/<event_id>.csv.gz`: `event_id, market_id, outcome, date, price`. This is the CLOB daily
  price of the market's first outcome ("Yes" on binary markets), joined to the snapshot by `market_id`.

Workflow: `.github/workflows/daily-history.yml` (14:37 UTC daily). Each run has a 150-minute budget (set
another from the Actions tab) and records progress in `history/<source>/manifest.json`, so the first full
backfill spreads over several days, biggest races first. After that, a resolved race is fetched once more and
then never again, and open races are refreshed weekly. The daily snapshots cover the days in between.

## Coverage

To widen coverage, edit `CATEGORIES` in `elections/kalshi.py` (for example, add `"Politics"`) or `TAG_SLUGS`
in `elections/polymarket.py`.

- Workflow: `.github/workflows/daily-snapshot.yml` (13:07 UTC daily; it can also be run manually from the Actions tab).
- A failed source doesn't block the other. It is retried once an hour later, and if it still fails the run is
  marked failed, which makes GitHub email a notice.
- Run locally: `pip install -r requirements.txt && python run_snapshot.py`.
- Note: GitHub turns off scheduled workflows after 60 days with no repository activity. The daily commits
  count as activity.
