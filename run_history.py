"""Entry point for the history backfill: daily prices since open for every market in the latest snapshot.

Runs for at most HISTORY_MINUTES (default 150) and resumes next run. Open races are refetched every
HISTORY_REFRESH_DAYS (default 7; 0 = anything not fetched today). HISTORY_SOURCES limits the run, e.g. "polymarket".
See elections/history.py.
"""
import os

from elections.history import backfill

counts = backfill(float(os.environ.get("HISTORY_MINUTES", "150")),
                  refresh_days=int(os.environ.get("HISTORY_REFRESH_DAYS") or 7),
                  sources=[s for s in os.environ.get("HISTORY_SOURCES", "").split(",") if s] or None)
print("fetched events:", counts)
