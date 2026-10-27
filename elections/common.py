"""Shared HTTP and CSV helpers."""

import csv
import gzip
import json
import time
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Penn APPC research; election market archive)", "Accept": "application/json"}


class NotFound(Exception):
    pass


def get_json(url: str, params: dict | None = None, attempts: int = 5):
    """GET with retries on network errors, 429 (rate limit) and 5xx. Other 4xx fail at once (404 -> NotFound)."""
    for i in range(1, attempts + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 404:
                raise NotFound(r.url)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {r.url}", response=r)
            if r.status_code >= 400:
                raise ValueError(f"{r.status_code} for {r.url}: {r.text[:200]}")
            return r.json()
        except requests.RequestException:
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
