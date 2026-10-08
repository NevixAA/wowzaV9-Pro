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


def odds_rows(resp: list, snapshot_ts: str, now_epoch: int) -> list[dict]:
    """One row per (fixture, market, selection, book) for Pinnacle and Bet365, plus a
    `median` row carrying the cross-book median and the number of books quoting it.

    Fixtures that have already kicked off are dropped: an in-play quote is not a pre-match price,
    and storing one would let it pass for a closing line later.
    """
    rows = []
    for fx in resp:
        f = fx.get("fixture") or {}
        ko = f.get("timestamp")
        if not ko or int(ko) <= now_epoch:
            continue
        lg = (fx.get("league") or {}).get("id")
        per_sel: dict[tuple, list[float]] = {}
        for bk in fx.get("bookmakers") or []:
            name = bk.get("name")
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
                    per_sel.setdefault(key, []).append(o)
                    if name in KEEP_BOOKS:
                        rows.append(_row(f, lg, key, KEEP_BOOKS[name], o, None, snapshot_ts, ko, now_epoch))
        for key, quotes in per_sel.items():
            rows.append(_row(f, lg, key, "median", round(statistics.median(quotes), 3), len(quotes),
                             snapshot_ts, ko, now_epoch))
    return rows


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
        ht = (fx.get("score") or {}).get("halftime") or {}
        st = ((f.get("status") or {}).get("short") or "")
        out.append({
            "fixture_id": int(f["id"]), "league_id": int(lg.get("id")), "season": str(lg.get("season")),
            "round": lg.get("round"), "kickoff_ts": int(f.get("timestamp") or 0),
            "match_date": str(f.get("date", ""))[:10],
            "home_id": (t.get("home") or {}).get("id"), "home_team": (t.get("home") or {}).get("name"),
            "away_id": (t.get("away") or {}).get("id"), "away_team": (t.get("away") or {}).get("name"),
            "status": st,
            "home_goals": g.get("home") if st in FINISHED else None,
            "away_goals": g.get("away") if st in FINISHED else None,
            "ht_home": ht.get("home") if st in FINISHED else None,
            "ht_away": ht.get("away") if st in FINISHED else None,
            "quality_flags": "" if f.get("timestamp") else "MISSING_KICKOFF",
        })
    return out


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
