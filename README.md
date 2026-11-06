# Prediction markets archive

Daily snapshots of every election market on Kalshi and Polymarket, collected by GitHub Actions.
Both sites publish current prices through free public APIs but keep only limited history, so we keep our own.

| Source | What's collected | API |
|---|---|---|
| **Kalshi** | Every market in the `Elections` category, plus election events in `Politics` (where older races such as the 2024 presidential live): open, closed and settled, plus markets moved to Kalshi's historical archive (checked on Sundays) | Trade API v2 (`api.elections.kalshi.com`), no key |
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
backfill spreads over several days, biggest races first. Each race is fetched when first seen, refetched
weekly while it is open (so its file stays current), and once more after it resolves, then never again.
A manual run can refetch open races sooner (`refresh_days`, 0 = all) or run one source only (`sources`).

## 2026 midterms, minute by minute

The GitHub release `intraday-2026-midterms` holds minute-level prices from election night (Nov 3, 2026) on,
one set of files per UTC day. They are too big for git, so they live in the release; delete the release to
clear them. `.github/workflows/intraday.yml` adds each finished day at 06:23 UTC (code: `elections/intraday.py`).

- `intraday-<day>-kalshi.csv.gz`: Kalshi 1-minute candles (open/high/low/close/mean price, closing bid and ask,
  volume, open interest).
- `intraday-<day>-kalshi-trades.csv.gz`: every Kalshi trade in the headline races (House and Senate control,
  Senate and governor winners), timestamped to the microsecond.
- `intraday-<day>-polymarket.csv.gz`: Polymarket's price of each market's first outcome, about once a minute.

Nov 3-4 cover every 2026 election market that resolved, plus the winner markets still open. From Nov 5 on, only
the winner/control markets still open are kept, each until it closes. Only races that could have been called
on Nov 3 count: runoffs, swearing-in dates, certified margins and turnout, and foreign elections are left out.
Disable the workflow once every 2026 race has closed.

## Coverage

To change coverage, edit `CATEGORIES` and `is_election()` in `elections/kalshi.py` or `TAG_SLUGS` in
`elections/polymarket.py`.

- Workflow: `.github/workflows/daily-snapshot.yml` (13:07 UTC daily; it can also be run manually from the Actions tab).
- A failed source doesn't block the other. It is retried once an hour later, and if it still fails the run is
  marked failed, which makes GitHub email a notice.
- Run locally: `pip install -r requirements.txt && python run_snapshot.py`.
- Note: GitHub turns off scheduled workflows after 60 days with no repository activity. The daily commits
  count as activity.
