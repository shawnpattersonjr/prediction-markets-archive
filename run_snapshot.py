"""Entry point for the daily GitHub Actions run: snapshot election markets into ./data/<UTC date>/.

Per source, two files:
  <source>.csv.gz          prices and status of every open market, plus markets resolved since the last snapshot
  <source>_markets.csv.gz  full details (titles, rules, dates, raw API object) of markets that are new today or
                           resolved today; together these files hold every market ever seen and its outcome

A source whose daily file is already saved today is skipped, so a retry only re-fetches what failed.
Exits 1 if any source failed.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from elections import kalshi, polymarket
from elections.common import load_markets, write_csv_gz

SOURCES = {"kalshi": kalshi, "polymarket": polymarket}

day = datetime.now(timezone.utc).date().isoformat()
data_dir = Path(__file__).resolve().parent / "data"
failed = []
for name, mod in SOURCES.items():
    path = data_dir / day / f"{name}.csv.gz"
    if path.exists():
        print(f"{name}: already saved for {day}, skipping")
        continue
    print(f"{name}: fetching")
    try:
        rows = mod.fetch(day)
    except Exception as e:
        print(f"{name}: failed ({e})")
        failed.append(name)
        continue
    if not rows:
        print(f"{name}: no markets returned, not saving")
        failed.append(name)
        continue
    known = load_markets(data_dir, name, mod.ID, before=day)
    changed = [r for r in rows if r[mod.ID] not in known
               or (mod.resolved(r) and not mod.resolved(known[r[mod.ID]]))]
    changed_ids = {r[mod.ID] for r in changed}
    daily = [r for r in rows if not mod.resolved(r) or r[mod.ID] in changed_ids]
    # Details first: the daily file marks the source as done for today.
    write_csv_gz(data_dir / day / f"{name}_markets.csv.gz", mod.FIELDS, changed)
    write_csv_gz(path, mod.PRICE_FIELDS, daily)
    print(f"{name}: {len(rows)} markets; saved {len(daily)} open or newly resolved, {len(changed)} new or resolved details")

sys.exit(1 if failed else 0)
