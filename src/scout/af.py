"""Minimal API-Football client for the scout: retries, rate limits and a quota floor.

The quota floor matters more than anything else here. v9's 5-minute predict loop and odds
capture use the SAME key; the scout is a batch job and must stop long before it could starve them.
"""
from __future__ import annotations

import os
import time

from config import pro_config as cfg

_BASE = "https://v3.football.api-sports.io"
#: Stop calling when the day's remaining requests fall below this.
MIN_QUOTA = int(os.getenv("SCOUT_MIN_QUOTA", "20000"))


class QuotaFloor(RuntimeError):
    """Raised when the remaining daily quota reaches MIN_QUOTA."""


def _key() -> str:
    key = os.getenv("APIFOOTBALL_KEY", "")
    if not key:
        for name in (".env", "secrets.env"):
            p = cfg.BASE_DIR / name
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("APIFOOTBALL_KEY"):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    if not key:
        raise RuntimeError("APIFOOTBALL_KEY not available (env or .env)")
    return key


class Client:
    def __init__(self, sleep_s: float = 0.15):
        import requests
        self.s = requests.Session()
        self.h = {"x-apisports-key": _key()}
        self.sleep_s = sleep_s
        self.calls = 0
        self.remaining: int | None = None

    def get(self, endpoint: str, params: dict) -> dict | None:
        """Parsed body, or None on a permanent failure. Raises QuotaFloor at the floor.

        A 200 carrying `errors` is not data. Rate limits arrive that way (errors.rateLimit), not
        as HTTP 429, and are retried; any other `errors` payload is a permanent answer.
        """
        if self.remaining is not None and self.remaining < MIN_QUOTA:
            raise QuotaFloor(f"remaining quota {self.remaining} < floor {MIN_QUOTA}")
        last = None
        for attempt in range(5):
            try:
                r = self.s.get(f"{_BASE}{endpoint}", headers=self.h, params=params, timeout=30)
            except Exception as e:                                        # noqa: BLE001
                last = f"{type(e).__name__}"
                time.sleep(min(30, 2 ** attempt))
                continue
            self.calls += 1
            rem = r.headers.get("x-ratelimit-requests-remaining")
            if rem is not None and str(rem).isdigit():
                self.remaining = int(rem)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            if r.status_code != 200:
                print(f"[scout] {endpoint} HTTP {r.status_code} (not retried)")
                return None
            try:
                body = r.json()
            except Exception:                                             # noqa: BLE001
                last = "unparseable body"
                time.sleep(min(30, 2 ** attempt))
                continue
            errs = body.get("errors")
            if errs:
                if isinstance(errs, dict) and "rateLimit" in errs:
                    time.sleep(min(70, 20 * (attempt + 1)))
                    last = "rateLimit"
                    continue
                print(f"[scout] {endpoint} {params} errors={errs} (permanent)")
                return None
            time.sleep(self.sleep_s)
            return body
        print(f"[scout] {endpoint} {params} failed after 5 attempts ({last})")
        return None

    def get_all_pages(self, endpoint: str, params: dict, max_pages: int = 20) -> list:
        """Concatenate `response` across pages. /odds pages at 10 fixtures."""
        out, page = [], 1
        while page <= max_pages:
            body = self.get(endpoint, {**params, "page": page} if page > 1 else params)
            if not body:
                break
            out.extend(body.get("response") or [])
            total = (body.get("paging") or {}).get("total") or 1
            if page >= int(total):
                break
            page += 1
        return out
