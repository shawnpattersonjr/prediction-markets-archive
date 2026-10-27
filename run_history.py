"""Entry point for the history backfill: daily prices since open for every market in the latest snapshot.

Runs for at most HISTORY_MINUTES (default 150) and resumes next run; see elections/history.py.
"""
import os

from elections.history import backfill

counts = backfill(float(os.environ.get("HISTORY_MINUTES", "150")))
print("fetched events:", counts)
