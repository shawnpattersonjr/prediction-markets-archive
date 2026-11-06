"""Entry point for the minute-by-minute 2026 midterm collection; see elections/intraday.py.

Each complete UTC day since Nov 3 that is not yet in the GitHub release (INTRADAY_TAG) is collected and its files
uploaded there, oldest first, until INTRADAY_MINUTES (default 300) run out; the next run picks up the rest.
With --local, files are written to ./intraday/ and nothing is uploaded.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from elections.intraday import collect, days_to_do

TAG = os.environ.get("INTRADAY_TAG", "intraday-2026-midterms")
local = "--local" in sys.argv
out_dir = Path(__file__).resolve().parent / "intraday"
deadline = time.monotonic() + float(os.environ.get("INTRADAY_MINUTES", "300")) * 60


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


done = set()
if not local:
    try:
        done = {a["name"] for a in json.loads(gh("release", "view", TAG, "--json", "assets"))["assets"]}
    except subprocess.CalledProcessError:
        gh("release", "create", TAG, "--title", "2026 midterms: minute-by-minute prices",
           "--notes", "Kalshi 1-minute candles, Kalshi trades (headline races) and Polymarket ~1-minute prices "
                      "for the 2026 midterms, one set of files per UTC day. See elections/intraday.py.")

days = days_to_do(done)
print("days to collect:", [str(d) for d in days])
for day in days:
    paths = collect(day, deadline, out_dir)
    if paths is None:
        print(f"{day}: time budget reached; the next run starts this day again")
        break
    if not local:
        # Polymarket last, on its own: its file marks the day done.
        gh("release", "upload", TAG, *map(str, paths[:-1]), "--clobber")
        gh("release", "upload", TAG, str(paths[-1]), "--clobber")
        for p in paths:
            p.unlink()
