"""Entry point for the daily GitHub Actions run: snapshot election markets into ./data/<UTC date>/<source>.csv.gz.

A source already saved today is skipped, so a retry only re-fetches what failed. Exits 1 if any source failed.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from elections import kalshi, polymarket
from elections.common import write_csv_gz

SOURCES = {"kalshi": kalshi, "polymarket": polymarket}

day = datetime.now(timezone.utc).date().isoformat()
out_dir = Path(__file__).resolve().parent / "data" / day
failed = []
for name, mod in SOURCES.items():
    path = out_dir / f"{name}.csv.gz"
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
    write_csv_gz(path, mod.FIELDS, rows)
    print(f"{name}: saved {len(rows)} markets to {path.relative_to(path.parents[2])}")

sys.exit(1 if failed else 0)
