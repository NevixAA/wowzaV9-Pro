"""
Team news with an OBSERVATION CLOCK — the only slow-information source we can build.
===================================================================================
    python -m src.pipelines.team_news [--max-hours 3] [--dry-run]

THE THESIS THIS EXISTS TO TEST. Pro's premise is that the market absorbs some information late,
and that getting to it first is where an edge could live. Nothing currently collected is a
candidate: every stored artifact is either the market itself (odds) or the outcome (results). A
model built only from prices and results cannot, even in principle, know something the price does
not.

Lineups are the obvious candidate. They publish roughly an hour before kickoff, they move prices,
and their content is genuinely predictive — a missing first-choice striker changes the goal
distribution, not just sentiment.

THE CONSTRAINT THAT SHAPES EVERYTHING HERE, established before writing any of this:
**neither /fixtures/lineups nor /injuries carries a publication timestamp.** Lineups return
formation, startXI, substitutes and coach; injuries return player, team, fixture and league.
Nothing says when the fact became known.

So the timing has to be MANUFACTURED BY POLLING. `first_seen_ts` is the first moment OUR poll
found the information — not when it was published. Two consequences, both load-bearing:

1. **The resolution is the poll interval, and no better.** Polling every 10 minutes supports a
   claim about 10-minute windows and nothing finer. It is not evidence that we knew before the
   market: the market may have had it earlier from a source we do not watch.

   What it CAN establish is the weaker, still useful claim: *was there price movement after the
   team news was publicly available?* If prices move well after first_seen, there is a window. If
   they have already moved by first_seen, there is not, and the thesis dies cheaply.

2. **It is forward-only and cannot be backfilled.** A historical lineup has no publication time,
   so the timing question is unanswerable for the past — exactly like closing odds. Every day not
   collected is permanently unavailable, which is the argument for starting now rather than after
   the design is perfect.

WHAT IS STORED, and why each field:

    first_seen_ts        our first observation. The clock the whole experiment depends on.
    minutes_to_kickoff   at first observation — the horizon, so lead time is comparable across
                         fixtures with different kickoff times.
    formation            attacking shape; already a v9 feature (home_attack_formation) that was
                         being computed from data nothing collected.
    n_forwards           forwards in the XI. The crude version of "did they pick to score".
    starters             the XI as a stable, comparable string, so a later run can detect a CHANGE
                         (a leaked XI that then changed is a different event from a stable one).
    injuries_n           reported absences for that fixture at first observation.
    poll_n               how many polls it took to see it — the honest resolution marker.

Nothing here is a feature for a live model yet. It is the measurement apparatus for one question,
and that question has a clean negative answer available, which is the main reason to build it.
"""
from __future__ import annotations

import argparse
import os
import time

import pandas as pd

from config import pro_config as cfg
from src.data import entities as ent
from src.data import season_store as store

TABLE = "team_news"
_BASE = "https://v3.football.api-sports.io"

# Lineups publish ~1h before kickoff, so a 3h window catches the appearance with margin while
# staying cheap. Widening it mostly buys empty polls.
DEFAULT_MAX_HOURS = 3.0


def _headers() -> dict:
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
    return {"x-apisports-key": key}


def _get(endpoint: str, params: dict, session):
    """GET with retry on transport failures and 429/5xx. NOT cached.

    Deliberately uncached, unlike the statistics collector: this endpoint's whole purpose is to
    detect the MOMENT information appears, and a cache would return a stale "not available yet"
    and destroy the only measurement being made.
    """
    last = None
    for attempt in range(4):
        try:
            r = session.get(f"{_BASE}{endpoint}", headers=_headers(), params=params, timeout=25)
        except Exception as e:                                    # noqa: BLE001
            last = f"{type(e).__name__}"
            time.sleep(min(20, 2 ** attempt))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(min(45, 5 * 2 ** attempt))
            continue
        if r.status_code != 200:
            return None
        body = r.json()
        errs = body.get("errors")
        if errs:
            # A RATE LIMIT ARRIVES AS HTTP 200 WITH AN `errors.rateLimit` PAYLOAD, not as 429.
            # Retrying only on 429 therefore treats a transient limit as permanent — which is
            # exactly how a malformed `league` parameter masqueraded as "no live games" and killed
            # the live scanner for 14 days. The distinction is: rate limit = wait and retry,
            # parameter/plan error = permanent, do not spend more calls on it.
            if isinstance(errs, dict) and "rateLimit" in errs:
                wait = min(70, 20 * (attempt + 1))
                print(f"[team_news] {endpoint} rate-limited; waiting {wait}s "
                      f"(attempt {attempt + 1})")
                time.sleep(wait)
                last = "rateLimit"
                continue
            print(f"[team_news] {endpoint} errors={errs} (permanent, not retried)")
            return None
        return body
    print(f"[team_news] {endpoint} failed after retries ({last})")
    return None


def _already_seen() -> set:
    """(fixture_id, team) pairs whose lineup we have already recorded.

    first_seen_ts must be the FIRST observation, so a fixture already recorded is never
    re-recorded — otherwise a later poll would overwrite the very timestamp the experiment needs.
    """
    try:
        prev = store.read(TABLE)
        if prev is not None and not prev.empty and {"fixture_id", "team"} <= set(prev.columns):
            return set(zip(prev["fixture_id"].astype(str), prev["team"].astype(str)))
    except Exception:
        pass
    return set()


def _league_ids() -> dict:
    """v9's league-id mapping, via the shared loader that stubs v9's optional imports.

    Loaded through src.data.v9_config rather than executing v9/config.py directly: that file does
    `from dotenv import load_dotenv`, which Pro's workflows do not install, so a direct exec works
    on a laptop and raises ModuleNotFoundError in CI. That is exactly how the Pro Team News
    workflow failed on its first run.
    """
    from src.data import v9_config
    return v9_config.league_ids()


_FWD = {"F", "A"}   # API-Football position codes: G/D/M/F


def collect(max_hours: float = DEFAULT_MAX_HOURS, dry_run: bool = False,
            loop_minutes: float = 0.0) -> pd.DataFrame:
    import requests
    now = pd.Timestamp.now(tz="UTC")
    session = requests.Session()
    league_ids = _league_ids()
    seen = _already_seen()

    # Injuries per league, fetched once and indexed by fixture. One call per league beats one per
    # fixture, and the payload is already fixture-keyed.
    inj_by_fixture: dict[str, int] = {}
    season = str(now.year if now.month >= 7 else now.year - 1)
    for league, lid in league_ids.items():
        body = _get("/injuries", {"league": lid, "season": season}, session)
        for row in ((body or {}).get("response") or []):
            fid = str(((row.get("fixture") or {}).get("id")) or "")
            if fid:
                inj_by_fixture[fid] = inj_by_fixture.get(fid, 0) + 1

    # FIXTURE LIST FETCHED ONCE, LINEUPS POLLED REPEATEDLY.
    #
    # The schedule does not change inside a 25-minute window, but a lineup APPEARS inside it —
    # that appearance is the only thing this collector measures. The first version re-fetched
    # /fixtures for all 24 leagues on every pass, so 24 of every ~30 calls bought a fact that had
    # not changed, and the per-minute rate limit was reached on repeat polls rather than on the
    # lineups that matter.
    candidates = []
    calls = 0
    for league, lid in sorted(league_ids.items()):
        body = _get("/fixtures", {"league": lid, "next": "20"}, session)
        calls += 1
        for fx in ((body or {}).get("response") or []):
            ko = pd.to_datetime(fx["fixture"]["date"], errors="coerce", utc=True)
            if pd.isna(ko):
                continue
            mins = (ko - now).total_seconds() / 60.0
            if 0 < mins <= max_hours * 60:
                candidates.append((league, fx))
    print(f"[team_news] {len(candidates)} fixture(s) inside {max_hours}h "
          f"({calls} schedule call(s))")

    rows, n_lineups = [], 0
    deadline = time.time() + loop_minutes * 60
    poll = 0
    while True:
        poll += 1
        now = pd.Timestamp.now(tz="UTC")
        pending = [(lg, fx) for lg, fx in candidates
                   if not ((str(fx["fixture"]["id"]), str(fx["teams"]["home"]["name"])) in seen
                           and (str(fx["fixture"]["id"]),
                                str(fx["teams"]["away"]["name"])) in seen)]
        if not pending:
            print("[team_news] every candidate already recorded; stopping early")
            break
        print(f"[team_news] --- poll {poll}: {len(pending)} fixture(s) awaiting a lineup ---")
        for league, fx in pending:
            fid = str(fx["fixture"]["id"])
            ko = pd.to_datetime(fx["fixture"]["date"], errors="coerce", utc=True)
            mins = (ko - now).total_seconds() / 60.0
            if mins <= 0:
                continue
            ln = _get("/fixtures/lineups", {"fixture": fid}, session)
            calls += 1
            blocks = (ln or {}).get("response") or []
            if not blocks:
                continue        # not published yet — the normal case, and not an error
            n_lineups += 1
            for blk in blocks:
                team = str((blk.get("team") or {}).get("name") or "")
                if not team or (fid, team) in seen:
                    continue
                xi = blk.get("startXI") or []
                names, fwd = [], 0
                for p in xi:
                    pl = p.get("player") or {}
                    names.append(str(pl.get("name") or ""))
                    if str(pl.get("pos") or "") in _FWD:
                        fwd += 1
                rows.append({
                    "fixture_id": fid,
                    "league": league,
                    "match_date": str(fx["fixture"]["date"])[:10],
                    "home_team": fx["teams"]["home"]["name"],
                    "away_team": fx["teams"]["away"]["name"],
                    "team": team,
                    "is_home": team == str(fx["teams"]["home"]["name"]),
                    "kickoff_utc": fx["fixture"]["date"],
                    "first_seen_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "minutes_to_kickoff": round(mins, 1),
                    "formation": blk.get("formation"),
                    "n_starters": len(xi),
                    "n_forwards": fwd,
                    "starters": "|".join(sorted(n for n in names if n)),
                    "coach": (blk.get("coach") or {}).get("name"),
                    "injuries_n": inj_by_fixture.get(fid),
                    "poll_n": poll,
                    "news_source": "api_football/fixtures/lineups",
                })
                seen.add((fid, team))

        # Tighter polling as kickoff nears, for the same reason the side-market capture
        # does it: the APPEARANCE moment is what is measured, and the gap IS the
        # resolution of first_seen_ts.
        nearest = None
        for _, fx in pending:
            k = pd.to_datetime(fx["fixture"]["date"], errors="coerce", utc=True)
            if pd.isna(k):
                continue
            m = (k - pd.Timestamp.now(tz="UTC")).total_seconds() / 60.0
            if m > 0 and (nearest is None or m < nearest):
                nearest = m
        gap = 300 if nearest is None else (120 if nearest <= 90 else
                                          (240 if nearest <= 180 else 300))
        if time.time() + gap >= deadline:
            break
        print(f"[team_news] next poll in {gap}s"
              + (f" (nearest kickoff {nearest:.0f}m)" if nearest else ""))
        time.sleep(gap)

    d = pd.DataFrame(rows)
    print(f"[team_news] {calls} call(s), {poll} poll(s); {n_lineups} lineup(s) seen; "
          f"{len(d)} new team-lineup row(s)")
    if d.empty:
        return d
    d = ent.add_fixture_key(d)
    lead = pd.to_numeric(d["minutes_to_kickoff"], errors="coerce")
    print(f"[team_news] lead time at first observation: median {lead.median():.0f} min, "
          f"range {lead.min():.0f}-{lead.max():.0f}")
    if dry_run:
        print("[team_news] dry run — nothing written")
        return d
    try:
        store.append(TABLE, d, source="api_football:fixtures/lineups",
                     rid=f"{cfg.run_id()}-news")
        print(f"[team_news] appended {len(d)} row(s)")
    except store.LocalWriteRefused as e:
        print(f"[team_news] collected but NOT written — {e}")
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect team news with an observation clock")
    ap.add_argument("--max-hours", type=float, default=DEFAULT_MAX_HOURS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--loop-minutes", type=float, default=0.0,
                    help="keep polling for N minutes to catch lineup publication")
    a = ap.parse_args()
    collect(max_hours=a.max_hours, dry_run=a.dry_run,
            loop_minutes=a.loop_minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
