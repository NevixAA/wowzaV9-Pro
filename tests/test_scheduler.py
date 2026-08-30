"""
Prompt 01 section 17 — scheduler interval calculation.

    python -m tests.test_scheduler

The measurement these tests protect is the one the module exists for: a CONFIGURED interval is
not an OBSERVED interval. Every incident in this project looked like a healthy cron and an empty
table, so the arithmetic that turns stored timestamps into "missed windows" has to be right, and
in particular has to survive the two things that make it silently lie — thousands of rows sharing
one run's timestamp, and a tail that hides behind a good median.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.monitoring import scheduler as sch  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def _ts(*minutes: int) -> pd.Series:
    base = pd.Timestamp("2026-08-30T09:00:00Z")
    return pd.Series([(base + pd.Timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
                      for m in minutes])


def test_spacing() -> None:
    print("observed spacing")
    perfect = sch.spacing(_ts(0, 10, 20, 30, 40), 10)
    check("a perfect 10-minute cadence has a 10-minute median",
          perfect["median_gap_min"] == 10.0, str(perfect["median_gap_min"]))
    check("a perfect cadence misses no windows", perfect["missed_windows"] == 0,
          str(perfect["missed_windows"]))

    # 47 minutes against a 10-minute target: floor(47/10) - 1 = 3 windows that should have
    # existed and do not. Counting this as "one gap" is what makes an outage look like a blip.
    gap = sch.spacing(_ts(0, 47), 10)
    check("a 47-min gap on a 10-min target is 3 missed windows",
          gap["missed_windows"] == 3, str(gap["missed_windows"]))

    # ONE RUN WRITES THOUSANDS OF ROWS SHARING A TIMESTAMP. Left in, every duplicate becomes a
    # zero-minute gap and the schedule reports as flawless no matter what actually happened.
    dup = pd.concat([_ts(0, 10, 20)] * 500, ignore_index=True)
    check("duplicate timestamps from one run are collapsed",
          sch.spacing(dup, 10)["n_observations"] == 3,
          str(sch.spacing(dup, 10)["n_observations"]))
    check("duplicates do not manufacture a zero-minute median",
          sch.spacing(dup, 10)["median_gap_min"] == 10.0)

    # A median can look perfect while the tail is where the closing prices were lost.
    tail = sch.spacing(_ts(0, 10, 20, 30, 40, 50, 60, 70, 80, 400), 10)
    check("a good median does not hide a bad tail",
          tail["median_gap_min"] == 10.0 and tail["max_gap_min"] == 320.0,
          f"median={tail['median_gap_min']} max={tail['max_gap_min']}")
    check("the tail is counted as missed windows", tail["missed_windows"] == 31,
          str(tail["missed_windows"]))


def test_degenerate() -> None:
    print("degenerate input")
    empty = sch.spacing(pd.Series(dtype=object), 10)
    check("no observations does not raise", empty["n_observations"] == 0)
    check("no observations reports None, not 0, for the median",
          empty["median_gap_min"] is None,
          "a 0 would read as 'measured a perfect cadence'")
    one = sch.spacing(_ts(0), 10)
    check("a single observation has no cadence to report", one["median_gap_min"] is None)
    check("missed windows are None when unmeasurable, not 0", one["missed_windows"] is None)


def test_targets() -> None:
    print("mode targets")
    check("live matches get the tightest target",
          sch.TARGET_MINUTES["LIVE_MATCH"] <= sch.TARGET_MINUTES["HIGH_ACTIVITY"])
    check("heavy days are tighter than normal days",
          sch.TARGET_MINUTES["HIGH_ACTIVITY"] < sch.TARGET_MINUTES["NORMAL"])
    check("section 7's ~10 minute heavy-day target is what we score against",
          sch.TARGET_MINUTES["HIGH_ACTIVITY"] == 10)
    check("horizons run wide to tight", [h[0] for h in sch.HORIZONS] ==
          sorted([h[0] for h in sch.HORIZONS], reverse=True))


def main() -> int:
    for fn in (test_spacing, test_degenerate, test_targets):
        fn()
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("all scheduler tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
