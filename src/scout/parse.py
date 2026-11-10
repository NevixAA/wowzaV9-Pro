"""Pure parsers for API-Football payloads. No I/O, so every rule here is unit-tested."""
from __future__ import annotations

import statistics

#: The quotes worth keeping per book. Everything else in the payload is dropped at parse time.
KEEP_BOOKS = {"Pinnacle": "pinnacle", "Bet365": "bet365"}
MARKETS = {  # (API bet name, API value) -> (market, selection)
    ("Goals Over/Under", "Over 1.5"): ("ou15", "over"), ("Goals Over/Under", "Under 1.5"): ("ou15", "under"),
    ("Goals Over/Under", "Over 2.5"): ("ou25", "over"), ("Goals Over/Under", "Under 2.5"): ("ou25", "under"),
    ("Goals Over/Under", "Over 3.5"): ("ou35", "over"), ("Goals Over/Under", "Under 3.5"): ("ou35", "under"),
    ("Both Teams Score", "Yes"): ("btts", "yes"), ("Both Teams Score", "No"): ("btts", "no"),
}
FINISHED = {"FT", "AET", "PEN"}
#: Finished after extra time / on penalties. For these API-Football's `goals` holds the 120-minute
#: score and `score.fulltime` the 90-minute one (v9 src/api_football_ou.py, 2026-11). Settlement is on
#: 90 minutes (owner rule), so these rows take score.fulltime; without it the goals stay MISSING.
EXTRA_TIME = {"AET", "PEN"}
#: Provider statuses that explain why a fixture past its kickoff has no result (Data Truth R3).
#: AWD / WO are awarded, not played: never a result, always a recorded reason.
UNFINISHED_REASON = {"PST", "CANC", "ABD", "AWD", "WO", "SUSP", "INT", "TBD"}


def odds_rows(resp: list, snapshot_ts: str, now_epoch: int) -> list[dict]:
    """One row per (fixture, market, selection, book) for Pinnacle and Bet365, plus a
    `median` row carrying the cross-book median and the number of books quoting it.

    Fixtures that have already kicked off are dropped: an in-play quote is not a pre-match price,
    and storing one would let it pass for a closing line later.
    """
    # ONE FIXTURE, ONE ENTRY PER ANSWER (Data Truth R5). A paged /odds?league answer has returned the
    # same fixture twice; each copy used to get its own median, so one snapshot stored two prices.
    # Copies are merged per (fixture, book, market, selection): an identical quote counts once, and
    # a book quoting two DIFFERENT prices for one selection in one answer is ambiguous, so that quote
    # is dropped (missing stays missing) rather than picked.
    quotes: dict[int, dict] = {}
    meta: dict[int, tuple] = {}
    for fx in resp:
        f = fx.get("fixture") or {}
        ko = f.get("timestamp")
        if not ko or int(ko) <= now_epoch or f.get("id") is None:
            continue
        fid = int(f["id"])
        meta.setdefault(fid, (f, (fx.get("league") or {}).get("id"), ko))
        q = quotes.setdefault(fid, {})
        for bk in fx.get("bookmakers") or []:
            name = bk.get("name")
            book = bk.get("id") if bk.get("id") is not None else name
            for bet in bk.get("bets") or []:
                for v in bet.get("values") or []:
                    key = MARKETS.get((bet.get("name"), str(v.get("value"))))
                    if not key:
                        continue
                    try:
                        o = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if o <= 1.0:
                        continue
                    q.setdefault((book, name, key), set()).add(o)
    rows = []
    for fid, q in quotes.items():
        f, lg, ko = meta[fid]
        per_sel: dict[tuple, list[float]] = {}
        for (book, name, key), prices in q.items():
            if len(prices) != 1:
                continue                                  # ambiguous within one answer: not stored
            o = next(iter(prices))
            per_sel.setdefault(key, []).append(o)
            if name in KEEP_BOOKS:
                rows.append(_row(f, lg, key, KEEP_BOOKS[name], o, None, snapshot_ts, ko, now_epoch))
        for key, qs in per_sel.items():
            rows.append(_row(f, lg, key, "median", round(statistics.median(qs), 3), len(qs),
                             snapshot_ts, ko, now_epoch))
    return rows


ODDS_KEY = ("fixture_id", "market", "selection", "bookmaker", "snapshot_ts")


def unique_odds(rows: list[dict]) -> list[dict]:
    """One row per (fixture, market, selection, book, snapshot) before an append (Data Truth R5).
    Identical repeats collapse to one; a key carrying two different prices is dropped whole."""
    seen: dict[tuple, set] = {}
    first: dict[tuple, dict] = {}
    for r in rows:
        k = tuple(r[c] for c in ODDS_KEY)
        seen.setdefault(k, set()).add(r["odds"])
        first.setdefault(k, r)
    return [first[k] for k in first if len(seen[k]) == 1]


def _row(f, lg, key, book, odds, n_books, snapshot_ts, ko, now_epoch):
    return {"fixture_id": int(f["id"]), "league_id": int(lg) if lg else None,
            "kickoff_ts": int(ko), "market": key[0], "selection": key[1], "bookmaker": book,
            "odds": float(odds), "n_books": n_books, "snapshot_ts": snapshot_ts,
            "minutes_to_kickoff": round((int(ko) - now_epoch) / 60.0, 1),
            # src/quality.py vocabulary: a thin median is a real number but not a consensus.
            "quality_flags": "INSUFFICIENT_BOOKS" if book == "median" and (n_books or 0) < 3 else ""}


def fixture_rows(resp: list) -> list[dict]:
    """Fixture metadata and, when finished, the score. Used for both upcoming and results."""
    out = []
    for fx in resp:
        f, lg, t, g = fx.get("fixture") or {}, fx.get("league") or {}, fx.get("teams") or {}, fx.get("goals") or {}
        sc = fx.get("score") or {}
        ht, ft, et, pen = (sc.get(k) or {} for k in ("halftime", "fulltime", "extratime", "penalty"))
        st = ((f.get("status") or {}).get("short") or "")
        fin = st in FINISHED
        # 90-minute settlement: AET / PEN take score.fulltime; `goals` (120 minutes) is kept beside it.
        src = ft if st in EXTRA_TIME else g
        hg, ag = (src.get("home"), src.get("away")) if fin else (None, None)
        basis = None
        if fin:
            basis = (("fulltime_90" if st in EXTRA_TIME else "goals")
                     if hg is not None and ag is not None else "missing_90")
            if basis == "missing_90":
                hg = ag = None
        out.append({
            "fixture_id": int(f["id"]), "league_id": int(lg.get("id")), "season": str(lg.get("season")),
            "round": lg.get("round"),
            # a missing kickoff stays missing (Data Truth R10); it used to become epoch 0
            "kickoff_ts": int(f["timestamp"]) if f.get("timestamp") else None,
            "match_date": str(f.get("date", ""))[:10],
            "home_id": (t.get("home") or {}).get("id"), "home_team": _name((t.get("home") or {}).get("name")),
            "away_id": (t.get("away") or {}).get("id"), "away_team": _name((t.get("away") or {}).get("name")),
            "status": st, "status_long": (f.get("status") or {}).get("long"),
            "home_goals": hg, "away_goals": ag, "goals_basis": basis,
            "goals_home_api": g.get("home") if fin else None, "goals_away_api": g.get("away") if fin else None,
            "et_home": et.get("home") if fin else None, "et_away": et.get("away") if fin else None,
            "pen_home": pen.get("home") if fin else None, "pen_away": pen.get("away") if fin else None,
            "ht_home": ht.get("home") if fin else None,
            "ht_away": ht.get("away") if fin else None,
            "quality_flags": "" if f.get("timestamp") else "MISSING_KICKOFF",
        })
    return out


def _name(x):
    """Provider club name, trimmed (Data Truth R14: leading spaces and tabs were stored)."""
    return x.strip() if isinstance(x, str) else x


def changed(rows: list[dict], last: dict, full_inside_min: float = 180.0) -> list[dict]:
    """Change-log filter. Keep a row when its price differs from the last stored one for the
    same (fixture, market, selection, book) — or always inside the final `full_inside_min`
    minutes, so the closing price is OBSERVED with a timestamp rather than inferred from an
    old row. READERS MUST CARRY FORWARD per key before aggregating (CLAUDE.md trap 2)."""
    out = []
    for r in rows:
        k = (r["fixture_id"], r["market"], r["selection"], r["bookmaker"])
        if r["minutes_to_kickoff"] <= full_inside_min or last.get(k) != r["odds"]:
            out.append(r)
    return out
