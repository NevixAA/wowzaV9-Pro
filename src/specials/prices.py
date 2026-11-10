"""
REAL pre-match prices for the special markets (owner 2026-11-09): correct score, high totals and
0-0 / low totals, from API-Football /odds?fixture=.

    python -m src.specials.prices [--dry-run]

WHAT IS COLLECTED. For every upcoming Pro fixture (src/specials/tracker.HORIZON_DAYS) that can be linked
to an API-Football fixture by PROOF, one /odds call. From each bookmaker in the answer, these bets only,
matched by their EXACT full-time bet name (a substring match once let a first-half BTTS overwrite the
full-match one, src/quality.py):
    Goals Over/Under   Over/Under 0.5, 1.5, 4.5, 5.5, 6.5   (both sides, as offered)
    Exact Score        every score quoted
    Total - Home / Total - Away   Over/Under 3.5             (a side scoring 4+)
Each quote is stored with the bookmaker, our capture time and the provider's update time. A fixture
that has kicked off is skipped: an in-play quote is not a pre-match price.

PROVEN LINK. The API-Football fixture comes from /fixtures?league&season&from&to for the fixture's own
canonical league (v9's league-id map and season resolver). It is linked to the Pro fixture only when it
is the ONE provider fixture of that league on the same UTC date whose home AND away clubs v9's resolver
places on the Pro fixture's clubs. Anything else is UNMAPPED and counted - never guessed.

SOURCE ORDER (2026-11-10). v9's live odds captures keep these same bets, at ZERO extra calls, from the
/odds answers they already make (v9 src/specials_quotes.py -> v9 output/specials_quotes/, every covered
std / new-format league; open, change and near-kickoff heartbeat rows). A run first links Pro fixtures to
the sidecar's provider fixtures (the same PROVEN rule, no call) and copies their quotes with Pro's identity
(source "v9_sidecar:<capture>"). Under/Over 1.5, which the sidecar leaves to v9's book_quotes, is copied
from v9 output/book_quotes (source "v9_book_quotes"; that file stores no provider update time, so it stays
missing). Pro's own /fixtures + /odds calls are made ONLY for upcoming Pro fixtures the sidecar does not
cover (source "pro_odds_call"); when the sidecar covers every fixture the run makes no call at all, not
even /status.

BUDGET. The key is shared with v9's predict loop and odds capture. Before any call /status is read
(it does not count against the quota); a run never starts or continues below MIN_REMAINING (owner:
25,000), and it plans no more than min(remaining - MIN_REMAINING, MAX_CALLS_PER_RUN) calls. Every run's calls are recorded.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "output" / "specials"
PRICES_FILE = OUT_DIR / "special_prices.csv"
RUNS_FILE = OUT_DIR / "special_price_runs.csv"

MIN_REMAINING = 25_000            # owner rule: never draw the shared key below this
MAX_CALLS_PER_RUN = 250          # owner 2026-11-09: about 100-200 calls a day; one daily run
#: sidecar / book_quotes day files read per run: the tracker's look-ahead (tracker.HORIZON_DAYS, 3) plus
#: the days v9's WIDE capture prices ahead of it (up to ~a week), so a fixture's opening quote is seen
SIDECAR_LOOKBACK_DAYS = 10
OU_LINES = ("0.5", "1.5", "4.5", "5.5", "6.5")
TEAM_LINES = ("3.5",)
BET_OU, BET_CS, BET_HOME, BET_AWAY = "Goals Over/Under", "Exact Score", "Total - Home", "Total - Away"
PRICE_COLS = ["captured_at", "provider_update", "af_fixture_id", "fixture_key", "league", "kickoff_utc",
              "home_team", "away_team", "bookmaker_id", "bookmaker", "bet", "selection", "odds", "source"]
SOURCE_OWN = "pro_odds_call"
SOURCE_BOOK_QUOTES = "v9_book_quotes"
SIDECAR_DIR = Path("output") / "specials_quotes"          # under V9_LOCAL (v9 main's live sidecar)
BOOK_QUOTES_DIR = Path("output") / "book_quotes"
RUN_COLS = ["run_at", "calls_fixtures", "calls_odds", "remaining_before", "remaining_after", "leagues",
            "af_fixtures", "linked", "unproven", "no_pro_fixture", "no_league_id", "quoted_fixtures", "rows",
            "status", "sidecar_linked", "sidecar_rows", "book_quotes_rows", "own_call_fixtures"]


def _keep(bet: str, value: str) -> bool:
    if bet == BET_OU:
        side, _, line = value.partition(" ")
        return side in ("Over", "Under") and line in OU_LINES
    if bet in (BET_HOME, BET_AWAY):
        side, _, line = value.partition(" ")
        return side in ("Over", "Under") and line in TEAM_LINES
    return bet == BET_CS and ":" in value


def odds_rows(resp: list, link: dict, captured_at: str, now_epoch: int) -> list[dict]:
    """Rows for the kept bets of one /odds answer. `link` carries the Pro fixture's identity."""
    rows = []
    for fx in resp or []:
        f = fx.get("fixture") or {}
        ko = f.get("timestamp")
        if not ko or int(ko) <= now_epoch:
            continue
        for bk in fx.get("bookmakers") or []:
            for bet in bk.get("bets") or []:
                name = bet.get("name")
                for v in bet.get("values") or []:
                    val = str(v.get("value"))
                    if not _keep(name, val):
                        continue
                    try:
                        o = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if o <= 1.01:                   # not a price (exchange placeholders, suspended lines)
                        continue
                    rows.append({"captured_at": captured_at, "provider_update": fx.get("update"),
                                 "af_fixture_id": int(f["id"]), **link, "bookmaker_id": bk.get("id"),
                                 "bookmaker": bk.get("name"), "bet": name, "selection": val, "odds": o,
                                 "source": SOURCE_OWN})
    return rows


def link_fixtures(pro: pd.DataFrame, af: list[dict], tn) -> tuple[dict, dict]:
    """{af_fixture_id: Pro identity} for proven pairs, and counts. `af` = parse.fixture_rows output
    (already one league); `pro` = that league's upcoming Pro fixtures (columns fixture_key, home_team,
    away_team, kickoff_utc as UTC timestamps in `_ko`)."""
    links, counts = {}, {"af_fixtures": len(af), "linked": 0, "unproven": 0, "no_pro_fixture": 0}
    for a in af:
        day = pd.to_datetime(a["kickoff_ts"], unit="s", utc=True).strftime("%Y-%m-%d")
        same = pro[pro["_ko"].dt.strftime("%Y-%m-%d") == day]
        if same.empty:
            counts["no_pro_fixture"] += 1          # the provider lists it; Pro has no fixture that day
            continue
        h = tn.resolve(str(a["home_team"]), sorted(same["home_team"].astype(str).unique()))
        w = tn.resolve(str(a["away_team"]), sorted(same["away_team"].astype(str).unique()))
        hit = same[(same["home_team"].astype(str) == h) & (same["away_team"].astype(str) == w)] \
            if h and w else same.iloc[0:0]
        if len(hit) != 1:
            counts["unproven"] += 1
            continue
        r = hit.iloc[0]
        links[int(a["fixture_id"])] = {"fixture_key": r["fixture_key"], "league": r["_lg"],
                                       "kickoff_utc": r["_ko"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                                       "home_team": r["home_team"], "away_team": r["away_team"]}
        counts["linked"] += 1
    return links, counts


def load_sidecar(v9_root: Path | None, since: dt.datetime) -> pd.DataFrame:
    """v9's special-market sidecar rows from day files on or after `since` (UTC day). Empty when absent."""
    if v9_root is None:
        return pd.DataFrame()
    d = Path(v9_root) / SIDECAR_DIR
    day = since.strftime("%Y-%m-%d")
    files = sorted(f for f in d.glob("*/*.csv") if f.name[:10] >= day) if d.exists() else []
    frames = [pd.read_csv(f, low_memory=False) for f in files]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_book_quotes_ou15(v9_root: Path | None, since: dt.datetime, fixture_ids) -> pd.DataFrame:
    """v9 book_quotes full-match Under/Over 1.5 rows (every bookmaker) for `fixture_ids`, from day files on
    or after `since`. The sidecar leaves this line to book_quotes, which v9 keeps from the same answers."""
    cols = ["snapshot_ts", "fixture_id", "kickoff_utc", "bookmaker_id", "bookmaker", "market", "side",
            "line", "odds"]
    if v9_root is None or not fixture_ids:
        return pd.DataFrame(columns=cols)
    d = Path(v9_root) / BOOK_QUOTES_DIR
    day = since.strftime("%Y-%m-%d")
    files = sorted(f for f in d.glob("*.csv") if f.stem >= day) if d.exists() else []
    ids = {int(x) for x in fixture_ids}
    out = []
    for f in files:
        b = pd.read_csv(f, usecols=lambda c: c in cols, low_memory=False)
        b = b[(b["market"] == "ou") & (pd.to_numeric(b["line"], errors="coerce") == 1.5)
              & pd.to_numeric(b["fixture_id"], errors="coerce").isin(ids)]
        if len(b):
            out.append(b)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=cols)


def _sidecar_fixture_list(sc: pd.DataFrame, league: str, now: dt.datetime) -> list[dict]:
    """The sidecar's provider fixtures of one canonical league kicking off after `now`, shaped for
    link_fixtures."""
    g = sc[sc["league"] == league].drop_duplicates("af_fixture_id")
    if g.empty:
        return []
    ko = pd.to_datetime(g["kickoff_utc"], utc=True, errors="coerce")
    g = g.assign(ko_ts=ko)[ko > pd.Timestamp(now)]
    return [{"fixture_id": int(r.af_fixture_id), "kickoff_ts": int(r.ko_ts.timestamp()),
             "home_team": r.home_team, "away_team": r.away_team} for r in g.itertuples(index=False)]


def sidecar_rows(sc: pd.DataFrame, bq: pd.DataFrame, links: dict, now: dt.datetime) -> tuple[list, int, int]:
    """PRICE_COLS rows from the sidecar and from book_quotes O/U 1.5 for linked provider fixtures; only quotes
    captured at or before `now` and before kickoff. Returns (rows, sidecar rows, book_quotes rows)."""
    rows: list[dict] = []
    now_ts = pd.Timestamp(now)
    if links and len(sc):
        s = sc[sc["af_fixture_id"].astype("int64").isin(list(links))]
        cap = pd.to_datetime(s["captured_at"], utc=True, errors="coerce")
        ko = pd.to_datetime(s["kickoff_utc"], utc=True, errors="coerce")
        for r in s[(cap <= now_ts) & (cap < ko)].itertuples(index=False):
            upd = r.provider_update if isinstance(r.provider_update, str) and r.provider_update else None
            rows.append({"captured_at": r.captured_at, "provider_update": upd,
                         "af_fixture_id": int(r.af_fixture_id), **links[int(r.af_fixture_id)],
                         "bookmaker_id": int(r.bookmaker_id), "bookmaker": r.bookmaker, "bet": r.bet,
                         "selection": str(r.selection), "odds": float(r.odds),
                         "source": f"v9_sidecar:{r.capture}"})
    n_sc = len(rows)
    if links and len(bq):
        cap = pd.to_datetime(bq["snapshot_ts"], utc=True, errors="coerce")
        ko = pd.to_datetime(bq["kickoff_utc"], utc=True, errors="coerce")
        b = bq[(cap <= now_ts) & (cap < ko) & bq["side"].isin(["over", "under"])]
        for r in b.itertuples(index=False):
            rows.append({"captured_at": r.snapshot_ts, "provider_update": None,
                         "af_fixture_id": int(r.fixture_id), **links[int(r.fixture_id)],
                         "bookmaker_id": int(r.bookmaker_id), "bookmaker": r.bookmaker, "bet": BET_OU,
                         "selection": f"{str(r.side).title()} 1.5", "odds": float(r.odds),
                         "source": SOURCE_BOOK_QUOTES})
    return rows, n_sc, len(rows) - n_sc


def collect(now: dt.datetime, client, tn, canon, league_ids, api_season, fixtures: pd.DataFrame,
            log=print, v9_root: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """One collection pass. Returns (price rows, run record). v9's sidecar under `v9_root` first (no call);
    Pro's own calls only for the fixtures it does not cover."""
    from src.scout import parse as P
    run = {"run_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "calls_fixtures": 0, "calls_odds": 0,
           "remaining_before": None, "remaining_after": None, "leagues": 0, "af_fixtures": 0, "linked": 0,
           "unproven": 0, "no_pro_fixture": 0, "no_league_id": 0, "quoted_fixtures": 0, "rows": 0, "status": "OK",
           "sidecar_linked": 0, "sidecar_rows": 0, "book_quotes_rows": 0, "own_call_fixtures": 0}
    # 1) v9's sidecar: proven links and quotes, zero calls
    since = now - dt.timedelta(days=SIDECAR_LOOKBACK_DAYS)
    sc = load_sidecar(v9_root, since)
    sc_links: dict = {}
    if len(sc) and len(fixtures):
        f0 = fixtures.assign(_lg=fixtures["league"].map(canon)).dropna(subset=["_lg"])
        for lg, g in f0.groupby("_lg"):
            lk, _c = link_fixtures(g, _sidecar_fixture_list(sc, lg, now), tn)
            sc_links.update(lk)
    bq = load_book_quotes_ou15(v9_root, since, list(sc_links))
    sc_rows, run["sidecar_rows"], run["book_quotes_rows"] = sidecar_rows(sc, bq, sc_links, now)
    run["sidecar_linked"] = len(sc_links)
    run["quoted_fixtures"] = len({r["af_fixture_id"] for r in sc_rows})
    covered = {v["fixture_key"] for v in sc_links.values()}
    fixtures = fixtures[~fixtures["fixture_key"].isin(covered)] if len(fixtures) else fixtures
    run["own_call_fixtures"] = int(len(fixtures))
    run["rows"] = len(sc_rows)
    if fixtures.empty:
        log(f"[specials prices] {run}")
        return pd.DataFrame(sc_rows, columns=PRICE_COLS), run
    # 2) Pro's own calls, only for fixtures the sidecar does not cover
    status = client.get("/status", {})
    rem = (((status or {}).get("response") or {}).get("requests") or {})
    if rem.get("limit_day") is not None and rem.get("current") is not None:
        run["remaining_before"] = int(rem["limit_day"]) - int(rem["current"])
    if run["remaining_before"] is None:
        run["status"] = "STOPPED: quota unknown (/status gave no request counts)"
        return pd.DataFrame(sc_rows, columns=PRICE_COLS), run
    budget = min(run["remaining_before"] - MIN_REMAINING, MAX_CALLS_PER_RUN)
    if budget <= 0:
        run["status"] = f"STOPPED: remaining {run['remaining_before']} at or below the floor {MIN_REMAINING}"
        return pd.DataFrame(sc_rows, columns=PRICE_COLS), run
    fx = fixtures.copy()
    fx["_lg"] = fx["league"].map(canon)
    fx = fx.dropna(subset=["_lg"])
    rows, links = [], {}
    used = 0
    start, end = now.strftime("%Y-%m-%d"), fx["_ko"].max().strftime("%Y-%m-%d") if len(fx) else None
    for lg, g in fx.groupby("_lg"):
        lid = league_ids.get(lg)
        season = api_season(lg, start)
        if not lid or not season:
            run["no_league_id"] += len(g)
            continue
        if used >= budget:
            run["status"] = "STOPPED: budget reached"
            break
        body = client.get("/fixtures", {"league": lid, "season": season, "from": start, "to": end})
        used += 1
        run["calls_fixtures"] += 1
        run["leagues"] += 1
        af = P.fixture_rows((body or {}).get("response") or [])
        lk, c = link_fixtures(g, af, tn)
        links.update({k: v for k, v in lk.items() if k not in sc_links})
        run["af_fixtures"] += c["af_fixtures"]
        run["linked"] += c["linked"]
        run["unproven"] += c["unproven"]
        run["no_pro_fixture"] += c["no_pro_fixture"]
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_epoch = int(now.timestamp())
    for fid, link in links.items():
        if used >= budget:
            run["status"] = "STOPPED: budget reached"
            break
        body = client.get("/odds", {"fixture": fid})
        used += 1
        run["calls_odds"] += 1
        r = odds_rows((body or {}).get("response") or [], link, stamp, now_epoch)
        if r:
            run["quoted_fixtures"] += 1
        rows.extend(r)
    rows = sc_rows + rows
    run["rows"] = len(rows)
    run["remaining_after"] = client.remaining
    log(f"[specials prices] {run}")
    return pd.DataFrame(rows, columns=PRICE_COLS), run


def probe(now: dt.datetime, client, leagues: list[str], league_ids, api_season, days: int,
          max_fixtures: int, log=print) -> dict:
    """AVAILABILITY PROBE (dry run only, nothing stored): which special markets does API-Football quote
    for our leagues' next `days` days? No Pro link is needed because no row is written; it measures the
    share of probed fixtures quoting each kept (bet, selection) and how many bookmakers quote it."""
    from src.scout import parse as P
    start = now.strftime("%Y-%m-%d")
    end = (now + dt.timedelta(days=days)).strftime("%Y-%m-%d")
    status = client.get("/status", {})
    req = (((status or {}).get("response") or {}).get("requests") or {})
    remaining = (int(req["limit_day"]) - int(req["current"])) if req.get("limit_day") is not None else None
    if remaining is None or remaining - MIN_REMAINING <= 0:
        return {"status": f"STOPPED: remaining {remaining} vs floor {MIN_REMAINING}"}
    budget = min(remaining - MIN_REMAINING, MAX_CALLS_PER_RUN)
    fx, used = [], 0
    for lg in leagues:
        lid, season = league_ids.get(lg), api_season(lg, start)
        if not lid or not season or used >= budget:
            continue
        body = client.get("/fixtures", {"league": lid, "season": season, "from": start, "to": end})
        used += 1
        fx += [dict(r, league=lg) for r in P.fixture_rows((body or {}).get("response") or [])
               if r["status"] == "NS"]
    fx = sorted(fx, key=lambda r: r["kickoff_ts"])
    # spread over leagues: round-robin so one big league does not take the whole sample
    by_lg: dict = {}
    for r in fx:
        by_lg.setdefault(r["league"], []).append(r)
    sample = []
    while len(sample) < max_fixtures and any(by_lg.values()):
        for lg in list(by_lg):
            if by_lg[lg] and len(sample) < max_fixtures:
                sample.append(by_lg[lg].pop(0))
    rows, quoted = [], 0
    now_epoch = int(now.timestamp())
    for r in sample:
        if used >= budget:
            break
        body = client.get("/odds", {"fixture": r["fixture_id"]})
        used += 1
        got = odds_rows((body or {}).get("response") or [], {"league": r["league"]}, "probe", now_epoch)
        quoted += bool(got)
        rows += got
    d = pd.DataFrame(rows)
    out = {"status": "OK", "days": days, "provider_fixtures": len(fx), "probed": len(sample),
           "quoted_fixtures": quoted, "calls": used, "remaining_before": remaining,
           "remaining_after": client.remaining, "leagues_probed": sorted({r["league"] for r in sample})}
    if not d.empty:
        g = d.groupby(["bet", "selection"]).agg(fixtures=("af_fixture_id", "nunique"),
                                                 bookmakers=("bookmaker", "nunique"))
        g["share_of_probed"] = (g["fixtures"] / max(len(sample), 1)).round(3)
        keep = [("Goals Over/Under", s) for s in ("Over 4.5", "Under 4.5", "Over 5.5", "Under 5.5",
                                                     "Over 6.5", "Under 6.5", "Under 0.5", "Over 0.5",
                                                     "Under 1.5", "Over 1.5")]
        keep += [("Exact Score", s) for s in ("0:0", "4:3", "3:3", "5:2", "4:4")]
        keep += [("Total - Home", "Over 3.5"), ("Total - Away", "Over 3.5")]
        out["coverage"] = {f"{b} | {s}": g.loc[(b, s)].to_dict() if (b, s) in g.index else None
                           for b, s in keep}
        out["exact_scores_quoted"] = int(d[d["bet"] == "Exact Score"]["selection"].nunique())
        out["bookmakers"] = int(d["bookmaker"].nunique())
    log(f"[specials probe] {out}")
    return out


def append_prices(new: pd.DataFrame, path: Path = PRICES_FILE) -> int:
    """Append quotes not stored yet (same fixture, bookmaker, bet, selection, capture time, provider update,
    odds and source). Re-reading the sidecar every day therefore adds only its new rows."""
    if new.empty:
        return 0
    key = ["af_fixture_id", "bookmaker_id", "bet", "selection", "captured_at", "provider_update", "odds",
           "source"]
    new = new.reindex(columns=PRICE_COLS)
    if path.exists():
        _align_header(path, PRICE_COLS, {"source": SOURCE_OWN})
        old = pd.read_csv(path, usecols=key, low_memory=False)
        seen = set(map(tuple, old.astype(str).to_numpy()))
        new = new[[tuple(x) not in seen for x in new[key].astype(str).to_numpy()]]
    new = new.drop_duplicates(key)
    if new.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, mode="a" if path.exists() else "w", header=not path.exists(), index=False)
    return int(len(new))


def _align_header(path: Path, cols: list, known: dict | None = None) -> None:
    """Rewrite a file written before columns were added, so appends stay aligned. Old rows keep their values;
    a new column is filled only with what is KNOWN about the old rows (`known`: every special price stored
    before 2026-11-10 came from Pro's own /odds call), otherwise it stays missing."""
    head = list(pd.read_csv(path, nrows=0).columns)
    if head == list(cols):
        return
    old = pd.read_csv(path, low_memory=False)
    for c, v in (known or {}).items():
        if c not in old.columns:
            old[c] = v
    old.reindex(columns=list(cols) + [c for c in old.columns if c not in cols]).to_csv(path, index=False)


def append_run(run: dict, path: Path = RUNS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _align_header(path, RUN_COLS)
    pd.DataFrame([run]).reindex(columns=RUN_COLS).to_csv(path, mode="a" if path.exists() else "w",
                                                        header=not path.exists(), index=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Specials: real pre-match prices (API-Football /odds)")
    ap.add_argument("--dry-run", action="store_true", help="call the API and report, write nothing")
    ap.add_argument("--probe", type=int, metavar="N", help="availability probe (dry run, nothing stored): "
                                                          "up to N provider fixtures over --probe-days")
    ap.add_argument("--probe-days", type=int)
    a = ap.parse_args(argv)
    if a.probe:
        from src.data import v9_config
        from src.scout.af import Client
        if not a.probe_days:
            ap.error("--probe needs --probe-days")
        lgs = sorted(v9_config.enabled_leagues())
        probe(dt.datetime.now(dt.timezone.utc), Client(), lgs, v9_config.league_ids(),
              v9_config.api_season, a.probe_days, a.probe)
        return 0
    from src.data import v9_config
    from src.scout.af import Client
    from src.specials import tracker as TR
    now = dt.datetime.now(dt.timezone.utc)
    fixtures = TR.upcoming_fixtures(now)
    if fixtures.empty:
        print("[specials prices] no upcoming fixtures in the store")
        return 0
    from config import pro_config as cfg
    rows, run = collect(now, Client(), v9_config.team_names(), v9_config.canonical_league,
                        v9_config.league_ids(), v9_config.api_season, fixtures, v9_root=cfg.V9_LOCAL)
    if not rows.empty:
        print(rows.groupby(["source", "bet"]).size().to_string())
        print(f"[specials prices] bookmakers {rows['bookmaker'].nunique()}, fixtures {rows['af_fixture_id'].nunique()}")
    if not a.dry_run:
        print(f"[specials prices] stored {append_prices(rows)} new quote(s)")
        append_run(run)
    return 0 if run["status"].startswith(("OK", "STOPPED: budget")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
