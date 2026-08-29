"""
Live odds collection pipeline (brief sections 126-160).
=======================================================
    python -m src.pipelines.live_odds [--dry-run] [--loop-minutes N]

Runs `src.live.collector` and appends each sweep to the canonical `live_odds_snapshots` table.

WHY IT LOOPS INSTEAD OF BEING SCHEDULED EVERY FIVE MINUTES

GitHub's scheduler is not a clock. Measured on this account, predict asked for ~180 runs a day
and received 13-32, and on 2026-08-27 a workflow asking for 3 runs a day received 0 -- GitHub
documents that queued jobs are dropped under load and gives no delivery guarantee. Live odds are
the least forgiving thing to schedule that way: a price exists for seconds, so a dropped run is
not a delayed observation, it is a permanently missing one.

So one firing samples repeatedly for `LOOP_MINUTES` instead of asking for many firings. This is
the pattern `std_odds_capture.yml` already uses in v9 and it converts a fragile schedule into a
robust one -- roughly 12 scheduled events a day rather than 288, each covering an hour.

ADAPTIVE SPACING, DRIVEN BY WHAT IS ACTUALLY LIVE

Sampling every 5 minutes when nothing is in play spends quota on empty responses. The loop asks
the collector what it found and spaces the next sample accordingly:

    matches live      -> SAMPLE_LIVE_SECONDS      (fast; the market is moving)
    nothing live      -> SAMPLE_IDLE_SECONDS      (slow; there is nothing to see)

Section 121 asks for exactly this: reserve calls for moving markets, not for quiet ones. The
measured pre-match profile makes the same point -- 87% of all polls happen more than 24h from
kickoff where 94% of the time nothing moves at all.

EACH SWEEP IS INDEPENDENT (section 157)

A failed sweep logs and the loop continues. One provider hiccup must not end an hour of
collection for every other live match.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import pandas as pd

TABLE = "live_odds_snapshots"

# Spacing, in seconds. Live prices move fast enough that a minute is already coarse, but the
# provider is polled once per sweep for ALL live fixtures, so the cost does not scale with the
# number of matches -- which is what makes a short interval affordable on a busy Saturday.
SAMPLE_LIVE_SECONDS = 300      # ~5 min while matches are in play
SAMPLE_IDLE_SECONDS = 900      # ~15 min when nothing is live
DEFAULT_LOOP_MINUTES = 55      # just under an hourly firing, leaving room for checkout+commit


def _get_fn():
    """v9's API-Football client. Imported lazily and with Pro's path FIRST, because v9 also has
    a `src` package and prepending its path would shadow Pro's own modules."""
    sys.path.append(str(__import__("pathlib").Path(__file__).resolve().parents[2].parent / "v9"))
    from player_model.api_football import _get
    return _get


def sweep(get_fn, *, dry_run: bool) -> tuple[pd.DataFrame, dict]:
    from src.live import collector as lc

    d = lc.quality_flags(lc.fetch(get_fn))
    return d, lc.summarise(d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and report, write nothing")
    ap.add_argument("--loop-minutes", type=float, default=DEFAULT_LOOP_MINUTES)
    ap.add_argument("--once", action="store_true", help="single sweep, no loop")
    args = ap.parse_args()

    from src.data import season_store as store
    import config.pro_config as cfg

    get_fn = _get_fn()
    end = time.time() + args.loop_minutes * 60
    n_sweeps = written = 0
    dry = args.dry_run

    while True:
        started = time.time()
        try:
            d, s = sweep(get_fn, dry_run=dry)
        except Exception as e:                                    # noqa: BLE001
            # Section 157: one failure must not end the hour.
            print(f"[live_odds] sweep failed ({type(e).__name__}: {e}) — continuing")
            d, s = pd.DataFrame(), {"live_fixtures": 0, "rows": 0}
        n_sweeps += 1
        print(f"[live_odds] sweep {n_sweeps}: {s.get('live_fixtures', 0)} live fixture(s), "
              f"{s.get('rows', 0)} row(s), median odds age "
              f"{s.get('median_odds_age_s')}s, stale {s.get('stale_pct')}%")

        if len(d) and not dry:
            try:
                store.append(TABLE, d, source="api_football:odds/live",
                             rid=f"{cfg.run_id()}-live-{n_sweeps}")
                written += len(d)
            except store.LocalWriteRefused as e:
                # Expected off-CI. Say it once and keep sampling, so a local run still proves
                # the collector works without pretending it persisted anything.
                print(f"[live_odds] NOT written — {e}")
                dry = True
            except Exception as e:                                # noqa: BLE001
                print(f"[live_odds] append failed ({type(e).__name__}: {e})")

        if args.once or time.time() >= end:
            break
        gap = SAMPLE_LIVE_SECONDS if s.get("live_fixtures", 0) else SAMPLE_IDLE_SECONDS
        sleep_for = max(5.0, gap - (time.time() - started))
        if time.time() + sleep_for > end:
            break
        time.sleep(sleep_for)

    print(f"[live_odds] done: {n_sweeps} sweep(s), {written:,} row(s) written"
          f"{' (dry run)' if dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
