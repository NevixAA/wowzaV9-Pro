"""Pro writers of the prediction ledger (src/prediction_ledger.py, shared verbatim with v9) - LEARNING ONLY.
==========================================================================================================

    python -m src.prediction_ledger_pro settle     # settled view + registry (pro_bet_builder.yml)
    python -m src.prediction_ledger_pro validate   # the same contract v9 gates as Data truth 12

OWNER RULE (2026-11-17): every model predicts every match of the tracked leagues, for every market it
serves, and the prediction is stored - the Pro research models included: 1X2, extreme goals (0 / 0-1 /
5+ / 6+ / 7+, side 4+), the full correct-score distribution and the bet-builder combos.

WHERE THE NUMBERS COME FROM. src/pipelines/bet_builder.py `generate()` fits, for EVERY upcoming board
fixture, a Dixon-Coles score grid to v9's four goal marginals (src/combo/score_model.fit). This module
reads that grid (model_id `pro_bb_dc`) and the builder's candidate combos BEFORE the v9-direction gate
(model_id `pro_bb_combo`). It never changes a grid, a candidate, a gate, a notification or a file the
builder writes; it writes only under output/prediction_ledger/ and output/prediction_ledger_settled/.
No price is stored and no API call is made. OFF unless PREDICTION_LEDGER_ENABLED == 'true'; nothing here
can raise into the builder.

THE JOIN WITH v9. Pro's board is v9's output/predictions.csv. Each Pro row's fixture_ref is the same
'oa:<OddsAPI event id>' v9's team rows carry, mapped through v9's board (checked out read-only at
$PREDICTION_LEDGER_V9_DIR, default $V9_LOCAL) on Pro's own fixture_key; a fixture the board no longer
lists falls back to v9's natural key 'nk:<league>|<date>|<home>|<away>' (the board's own names).
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import prediction_ledger as PL  # noqa: E402

REPO = "pro"
GRID_MODEL, COMBO_MODEL = "pro_bb_dc", "pro_bb_combo"
CS_MAX = 6                                     # correct score 0-0 .. 6-6, everything else 'other'
NO_RESULT_AFTER_H = 72


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.is_file() else ""


def _v9_dir() -> Path | None:
    for c in (os.getenv("PREDICTION_LEDGER_V9_DIR", ""), os.getenv("V9_LOCAL", "")):
        if c and (Path(c) / "config" / "leagues.json").is_file():
            return Path(c)
    return None


def _hash_values(vals) -> str:
    h = hashlib.sha1()
    for v in vals:
        h.update(f"{float(v):.10g}|".encode() if v is not None and v == v else b"nan|")
    return h.hexdigest()[:12]


def grid_markets(m: np.ndarray) -> dict:
    """{market: {selection: probability}} read off one score grid m[home_goals, away_goals]."""
    n = m.shape[0]
    H, A = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    T = H + A
    cs = {f"{h}-{a}": float(m[h, a]) for h in range(CS_MAX + 1) for a in range(CS_MAX + 1)}
    cs["other"] = float(max(0.0, 1.0 - sum(cs.values())))
    return {
        "1x2": {"H": float(m[H > A].sum()), "D": float(m[H == A].sum()), "A": float(m[H < A].sum())},
        "correct_score": cs,
        "goals_exact_0": {"YES": float(m[T == 0].sum())},
        "goals_le1": {"YES": float(m[T <= 1].sum())},
        "goals_ge5": {"YES": float(m[T >= 5].sum())},
        "goals_ge6": {"YES": float(m[T >= 6].sum())},
        "goals_ge7": {"YES": float(m[T >= 7].sum())},
        "team_ge4": {"HOME": float(m[H >= 4].sum()), "AWAY": float(m[A >= 4].sum())},
    }


class Recorder:
    """One builder run: grids, unscored board fixtures and combo candidates -> ledger rows."""

    def __init__(self, now: datetime | None = None):
        self.now = now
        v9 = _v9_dir()
        self.slugs = PL.LeagueSlugs(PL.load_leagues(v9 / "config" / "leagues.json" if v9 else None))
        self.markets = PL.load_markets()
        self.ents = {(e["model_id"], e["market"]): e for e in PL.entries(self.markets, repo=REPO, status="active")}
        self.grid_rows: list = []
        self.gridded: set = set()
        self.oa = self._oa_map(v9)
        self.grid_ver = self._version("score_model.py", GRID_MODEL)
        self.combo_ver = self._version("match_picture.py", COMBO_MODEL)

    @staticmethod
    def _version(fname: str, model_id: str) -> tuple:
        sha = _sha(ROOT / "src" / "combo" / fname)
        try:
            from src.combo import score_model as sm
            calc = str(getattr(sm, "CALC_VERSION", ""))
        except Exception:                                              # noqa: BLE001
            calc = ""
        return (f"{model_id}_{calc}_{sha[:8]}" if sha else "", sha, calc)

    @staticmethod
    def _oa_map(v9: Path | None) -> dict:
        """Pro fixture_key -> v9 `_oa_event_id`, from v9's current board (no API call)."""
        if v9 is None or not (v9 / "output" / "predictions.csv").is_file():
            return {}
        try:
            from src.data import entities as ent
            b = pd.read_csv(v9 / "output" / "predictions.csv", dtype=str, low_memory=False,
                            usecols=lambda c: c in ("league", "date", "home_team", "away_team", "_oa_event_id"))
            b = b.rename(columns={"date": "match_date"})
            b["match_date"] = b["match_date"].astype(str).str[:10]
            b = ent.add_fixture_key(b)
            return {k: v for k, v in zip(b["fixture_key"], b["_oa_event_id"]) if isinstance(v, str) and v}
        except Exception as e:                                         # noqa: BLE001
            print(f"[prediction_ledger] v9 board unreadable for the oa join ({type(e).__name__}: {e})")
            return {}

    def _identity(self, f, key: str) -> dict:
        ko = pd.Timestamp(f["_ko"]) if f.get("_ko") is not None else PL.utc_ts(f.get("kickoff_utc"))
        lentry = self.slugs.entry(f.get("league"))
        date = PL._s(f.get("match_date"))[:10]
        ref = PL.fixture_ref(None, self.oa.get(key),
                             (lentry["id"] if lentry else "", date, f.get("home_team"), f.get("away_team")))
        return {"ko": ko, "lentry": lentry, "ref": ref, "oa": self.oa.get(key, ""),
                "league": self.slugs.canonical(f.get("league")) or PL._s(f.get("league"))}

    def _rows(self, model_id, market, sel_probs: dict, idn: dict, f, *, ver, sha, payload, fhash,
              line=None, reason=""):
        now = self.now or _now()
        if idn["ko"] is None:
            return []
        mtk = (idn["ko"] - pd.Timestamp(now)).total_seconds() / 60.0
        out = []
        for snap in PL.snapshots_due(mtk):
            for sel, p in sel_probs.items():
                out.append(PL.make_row(
                    repo=REPO, model_id=model_id, model_version=ver, model_sha=sha, payload_version=payload,
                    feature_hash=fhash, track="board", market=market, line=line, selection=sel,
                    fixture_ref=idn["ref"], fixture_id="", oddsapi_event_id=idn["oa"], league=idn["league"],
                    season=PL.season_of(idn["lentry"], idn["ko"]), kickoff_utc=PL.iso(idn["ko"]),
                    home_team=f.get("home_team"), away_team=f.get("away_team"),
                    probability=None if p is None else float(min(max(p, 0.0), 1.0)), snapshot=snap,
                    predicted_at=PL.iso(pd.Timestamp(now)), minutes_to_kickoff=round(mtk, 1),
                    not_scored_reason=reason, git_sha=(os.getenv("GITHUB_SHA") or "")[:12],
                    run_id=os.getenv("GITHUB_RUN_ID", "")))
        return out

    # -- hooks called from bet_builder.generate() --------------------------------------------------

    def grid(self, f, key: str, fit: dict, targets: dict) -> None:
        try:
            idn = self._identity(f, key)
            ver, sha, calc = self.grid_ver
            fh = _hash_values([targets.get(k) for k in ("O15", "O25", "O35", "BTTS")])
            for market, sels in grid_markets(np.asarray(fit["matrix"], dtype=float)).items():
                e = self.ents.get((GRID_MODEL, market))
                if e is None:
                    continue
                self.grid_rows += self._rows(GRID_MODEL, market, sels, idn, f, ver=ver, sha=sha, payload=calc,
                                             fhash=fh, line=e.get("line"))
            self.gridded.add(key)
        except Exception as ex:                                        # noqa: BLE001
            print(f"[prediction_ledger] grid not recorded for {key} ({type(ex).__name__}: {ex})")

    def board_done(self, fx: pd.DataFrame, probs: pd.DataFrame) -> dict:
        """Every board fixture the builder looked at and could NOT grid -> unscored rows with the reason.
        Then append everything. Never raises."""
        try:
            from src.combo import score_model as sm
            ver, sha, calc = self.grid_ver
            for _, f in fx.iterrows():
                k = f["fixture_key"]
                if k in self.gridded:
                    continue
                row = probs.loc[k] if (probs is not None and k in probs.index) else None
                t = {}
                if row is not None:
                    for src_m, dst_m in (("OU15", "O15"), ("OU25", "O25"), ("OU35", "O35"), ("BTTS", "BTTS"),
                                         ("O15", "O15"), ("O25", "O25"), ("O35", "O35")):
                        if src_m in row.index and pd.notna(row.get(src_m)):
                            t[dst_m] = float(row[src_m])
                if len(t) < 2:
                    why = "no grid: fewer than 2 of v9's O1.5/O2.5/O3.5/BTTS probabilities in the warehouse"
                elif sm.monotonicity_violation(t):
                    why = "no grid: v9's goal probabilities are not monotone (O2.5 > O1.5 or similar)"
                else:
                    why = "no grid: the Dixon-Coles fit to v9's marginals failed"
                idn = self._identity(f, k)
                for (mid, market), e in self.ents.items():
                    if mid != GRID_MODEL:
                        continue
                    self.grid_rows += self._rows(GRID_MODEL, market, {s: None for s in e["selections"]}, idn, f,
                                                 ver=ver, sha=sha, payload=calc, fhash="", line=e.get("line"),
                                                 reason=why)
            st = PL.append(self.grid_rows, repo=REPO, writer="bet_builder_grid",
                           run_id=os.getenv("GITHUB_RUN_ID", ""), now=self.now,
                           slugs=self.slugs)
            self.grid_rows = []
            print(f"[prediction_ledger] grids: {st}")
            return st
        except Exception as ex:                                        # noqa: BLE001
            print(f"[prediction_ledger] grids not recorded ({type(ex).__name__}: {ex})")
            return {"error": str(ex)}

    def combos(self, d: pd.DataFrame, fx: pd.DataFrame) -> dict:
        """Every candidate combo the builder produced, BEFORE the v9-direction gate."""
        try:
            if d is None or d.empty:
                return {"offered": 0}
            ver, sha, _ = self.combo_ver
            fx_by = {r["fixture_key"]: r for r in fx.to_dict("records")}
            legcols = sorted(c for c in d.columns if c.startswith("leg") and c.endswith("_market"))
            labcols = [c[:-len("_market")] + "_label" for c in legcols]
            rows = []
            for r in d.to_dict("records"):
                f = fx_by.get(r["fixture_key"])
                if f is None:
                    continue
                legs = sorted(f"{r.get(m) or ''}:{r.get(lab) or ''}" for m, lab in zip(legcols, labcols)
                              if r.get(m) and r.get(m) == r.get(m))
                p = pd.to_numeric(pd.Series([r.get("joint_probability")]), errors="coerce").iloc[0]
                rows += self._rows(COMBO_MODEL, "combo", {"|".join(legs): None if pd.isna(p) else float(p)},
                                   self._identity(f, r["fixture_key"]), f, ver=ver, sha=sha,
                                   payload=str(r.get("calc_version") or ""), fhash="",
                                   reason="" if pd.notna(p) else "candidate carries no joint_probability")
            st = PL.append(rows, repo=REPO, writer="bet_builder_combo", run_id=os.getenv("GITHUB_RUN_ID", ""), slugs=self.slugs,
                           now=self.now)
            print(f"[prediction_ledger] combos: {st}")
            return st
        except Exception as ex:                                        # noqa: BLE001
            print(f"[prediction_ledger] combos not recorded ({type(ex).__name__}: {ex})")
            return {"error": str(ex)}


_REC: Recorder | None = None


def recorder(now: datetime | None = None) -> Recorder | None:
    """The run's recorder, or None when the flag is off / it cannot load (never raises)."""
    global _REC
    if not PL.enabled():
        return None
    if _REC is None:
        try:
            _REC = Recorder(now=now)
        except Exception as ex:                                        # noqa: BLE001
            print(f"[prediction_ledger] recorder unavailable ({type(ex).__name__}: {ex})")
            return None
    return _REC


# ── SETTLE ───────────────────────────────────────────────────────────────────────────────────────

def _scorelines() -> pd.DataFrame:
    from src.pipelines.bet_builder import _read
    need = {"home_team", "away_team", "home_goals", "away_goals", "match_date", "league"}
    parts = [t for t in (_read("team_match_stats"), _read("settlements_backfill")) if not t.empty and need <= set(t.columns)]
    if not parts:
        return pd.DataFrame(columns=sorted(need) + ["fixture_key"])
    res = pd.concat(parts, ignore_index=True)
    # Go-live merge 2026-11-17 (data-truth-100 round 3 rule): a full-time score stored before its own kickoff
    # is a provider error and never settles anything - the same guard as bet_builder's scorelines.
    from src.data import result_guard as rg
    res = rg.drop_unplayed(res, "prediction_ledger scorelines")
    if "fixture_key" not in res.columns:
        from src.data import entities as ent
        res = ent.add_fixture_key(res)
    return res.dropna(subset=["home_goals", "away_goals"]).drop_duplicates("fixture_key", keep="last")


def outcome_fn(*, now: datetime | None = None, scores: pd.DataFrame | None = None,
               combos: pd.DataFrame | None = None, markets: dict | None = None):
    from src.data import entities as ent
    idx = PL.entry_index(markets)
    now_ts = pd.Timestamp(now or _now())
    stamp = PL.iso(now_ts)
    by_key = {} if scores is None else {k: r for k, r in zip(scores["fixture_key"], scores.to_dict("records"))}
    combo_res = {}
    if combos is not None and len(combos) and {"combo_id", "combo_result"} <= set(combos.columns):
        combo_res = dict(zip(combos["combo_id"].astype(str), combos["combo_result"].astype(str)))

    def missing(ko, why):
        if ko is not None and (now_ts - ko).total_seconds() / 3600 >= NO_RESULT_AFTER_H:
            return {"outcome_status": "NO_RESULT", "outcome_value": why}
        return {"outcome_status": "PENDING"}

    def outcome_of(r: dict) -> dict:
        e = idx.get((r["repo"], r["model_id"], r["market"]))
        ko = PL.utc_ts(r.get("kickoff_utc"))
        if e is None:
            return {"outcome_status": "UNREGISTERED"}
        if ko is None or ko > now_ts:
            return {"outcome_status": "PENDING"}
        m = None
        for off in (0, -1, 1):                     # board date vs UTC kickoff date
            k = ent.fixture_key(r["league"], (ko + pd.Timedelta(days=off)).strftime("%Y-%m-%d"),
                                r["home_team"], r["away_team"])
            if k in by_key:
                m, fkey = by_key[k], k
                break
        if m is None:
            return missing(ko, "no Pro scoreline (team_match_stats / settlements_backfill)")
        if e["settle"].get("rule") == "combo_all_legs":
            legs = sorted(x for x in str(r["selection"]).split("|") if x)
            cid = f"{fkey}|" + hashlib.sha1("|".join(legs).encode("utf-8")).hexdigest()[:12]
            res = combo_res.get(cid)
            if res in ("WON", "LOST"):
                return {"outcome_status": "SETTLED", "y": int(res == "WON"), "outcome_value": res,
                        "home_goals": int(m["home_goals"]), "away_goals": int(m["away_goals"]),
                        "result_source": "bet_builder_settled", "settled_at": stamp}
            return missing(ko, f"combo not graded by Pro ({res or 'not in bet_builder_settled'})")
        y, val = PL.match_outcome(e["settle"], r["selection"], r.get("line"), m["home_goals"], m["away_goals"])
        if y is None:
            return {"outcome_status": "NO_RESULT", "outcome_value": val}
        return {"outcome_status": "SETTLED", "y": y, "home_goals": int(m["home_goals"]),
                "away_goals": int(m["away_goals"]), "outcome_value": val, "result_source": "pro_scorelines",
                "settled_at": stamp}
    return outcome_of


def settle(*, root: Path | None = None, settled_root: Path | None = None, now: datetime | None = None,
           force: bool = False) -> dict:
    if not (force or PL.enabled()):
        return {"skipped": f"{PL.FLAG_ENV} is not 'true'"}
    from src.pipelines.bet_builder import SETTLED_FILE
    combos = pd.read_csv(SETTLED_FILE, low_memory=False, dtype=str) if SETTLED_FILE.exists() else None
    fn = outcome_fn(now=now, scores=_scorelines(), combos=combos)
    return PL.write_settled(fn, repo=REPO, root=root, settled_root=settled_root)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Pro prediction ledger (learning only)")
    ap.add_argument("cmd", choices=["settle", "registry", "validate"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else None
    v9 = _v9_dir()
    slugs = PL.LeagueSlugs(PL.load_leagues(v9 / "config" / "leagues.json" if v9 else None))
    if a.cmd == "validate":
        issues = PL.validate(root, slugs=slugs)
        for i in issues:
            print(f"PREDICTION LEDGER VIOLATION: {i}")
        print(f"prediction ledger: {len(PL.partitions(root))} partition(s), {len(issues)} violation(s)")
        return 1 if issues else 0
    if not (a.force or PL.enabled()):
        print(f"[prediction_ledger] {PL.FLAG_ENV} is not 'true' - nothing written")
        return 0
    if a.cmd == "settle":
        print(f"[prediction_ledger] settle: {settle(root=root, force=True)}")
    else:
        reg = PL.write_registry(root=root, slugs=slugs, repos=(REPO,))
        print(f"[prediction_ledger] registry: {len(reg['models'])} model x market entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
