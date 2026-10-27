"""Shared HTTP and CSV helpers."""

import csv
import gzip
import json
import time
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Penn APPC research; election market archive)", "Accept": "application/json"}


def get_json(url: str, params: dict | None = None, attempts: int = 5):
    """GET with retries; backs off longer on 429 (rate limit) and 5xx."""
    for i in range(1, attempts + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {r.url}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if i == attempts:
                raise
            time.sleep(5 * 2 ** (i - 1))


def dumps(v) -> str:
    """Compact JSON for nested values kept in a CSV cell."""
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def write_csv_gz(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Write atomically so a crashed run never leaves a half-written file that later runs would skip."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)
