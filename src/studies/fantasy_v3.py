"""Does Player V3 make better FANTASY (FPL) projections than v9's Fantasy model?

    python -m src.studies.fantasy_v3          # -> output/studies/fantasy_v3.json + FANTASY_V3.md

WHY (owner, 2026-10-14). V3's gains were accuracy without a betting edge. Fantasy has no bookmaker:
better accuracy is the whole product. So the question is asked on FPL points, not on prop outcomes.

POPULATION. Premier League SQUAD panel (src/player_v3/minutes.build_panel): every club fixture for
every player inside his club tenure, INCLUDING the matches he missed (0 points). Ranking only players
who appeared would hide the biggest Fantasy error - picking someone who does not play. Test period =
V3's untouched holdout (fixtures from 2025-07-01); models are fitted on V3's train/validation split.

WHAT IS SCORED, both sides identically: FPL points from APPEARANCE (2 if 60+, 1 if 1-59) + GOALS
(position points) + ASSISTS (3). Clean sheets, conceded, saves, cards, bonus and defensive
contribution are left out of the projection AND the actuals: V3 does not change them, and keeping
them would add the same noise to every variant.

VARIANTS (each projection uses only the player's LAST appearance before the fixture - the same
as-of view v9's Fantasy uses, `tail(1)` of his history):
  V9        v9's Fantasy formula: p_start = 0.6 starter_rate + 0.4 season_start_rate,
            appearance = 2 if minutes_pg >= 60 else 1, P(goal)/P(assist) from BASE_V9 features with
            v9's Platt-on-probability; points = p_start x (appearance + attack)
  V9_CAL    same, Platt on log-odds
  V9_MIN    v9 probabilities + V3's expected-minutes model: 2 P(60+) + 1 (P(start) - P(60+)) +
            P(start) x attack
  V3_FULL   V3 features (BASE_V9 + FORM_SHRUNK + TEAM_ENV + MINUTES_V3), log-odds Platt, V3 minutes

METRICS per variant, differences vs V9 with a 90% CI by bootstrap over whole weeks:
  MAE of projected vs actual points; mean within-week Spearman rank correlation; CAPTAIN = actual
  points of the week's top projected player; TOP-11 = actual points of the week's 11 highest projected.
Decision (fixed here, before results): a variant is BETTER only if its MAE CI and its captain or
top-11 CI both favour it; otherwise NOT_SHOWN. A switch in v9 Fantasy remains an owner-approved PR.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.player_v3 import HOLDOUT_FROM, TRAIN_END, VALID_END
from src.player_v3 import data as D
from src.player_v3.sot_lab import CACHE, expected_minutes, fit_binary, load_features

LEAGUE = "Premier League"
GOAL_PTS = {"F": 4, "M": 5, "D": 6, "G": 6}
OUT = cfg.OUTPUT_DIR / "studies"
RNG = np.random.default_rng(20261014)


def _attack_probs(X: pd.DataFrame, fam: dict) -> pd.DataFrame:
    """P(goal), P(assist) for every appearance row, three ways. HGB raw fitted once per feature set;
    the two calibration forms reuse it."""
    tr, va, _ = (m.to_numpy() for m in D.chrono_split(X["date"], TRAIN_END, VALID_END, HOLDOUT_FROM))
    base = fam["BASE_V9"]
    v3 = base + [c for k in ("FORM_SHRUNK", "TEAM_ENV", "MINUTES_V3") for c in fam[k]]
    out = X[["player_id", "fixture_id", "date"]].copy()
    for name, y in (("goal", (X["goals"].fillna(0) > 0).astype(int).to_numpy()),
                    ("assist", (X["assists"].fillna(0) > 0).astype(int).to_numpy())):
        out[f"p_{name}_v9"], _ = fit_binary(X[base], y, tr, va, calib="v9")
        out[f"p_{name}_cal"], _ = fit_binary(X[base], y, tr, va, calib="logit")
        out[f"p_{name}_v3"], _ = fit_binary(X[v3], y, tr, va, calib="logit")
        print(f"  fitted {name}")
    for c in ("starter_rate", "season_start_rate", "minutes_pg", "position"):
        out[c] = X[c].to_numpy()
    return out


def _panel_pl() -> pd.DataFrame:
    from src.player_v3 import minutes as M
    p = M.build_panel()
    p = p[(p["league"] == LEAGUE) & (p["date"] >= pd.Timestamp(HOLDOUT_FROM))].copy()
    return p


def _carry_last(panel: pd.DataFrame, probs: pd.DataFrame) -> pd.DataFrame:
    """Each panel row gets the player's LAST appearance row strictly before the fixture date.
    merge_asof resets the index, so the result is used as its own frame (never assigned back)."""
    a = panel.sort_values("date", kind="mergesort").reset_index(drop=True)
    b = probs.sort_values("date", kind="mergesort").rename(columns={"date": "last_app_date",
                                                                    "fixture_id": "last_fixture"})
    a["date"] = a["date"].astype("datetime64[ns]")
    b["last_app_date"] = b["last_app_date"].astype("datetime64[ns]")
    a["player_id"] = a["player_id"].astype("float64")
    b["player_id"] = b["player_id"].astype("float64")
    m = pd.merge_asof(a, b, left_on="date", right_on="last_app_date", by="player_id",
                      allow_exact_matches=False, direction="backward")
    return m[m["last_app_date"].notna()].reset_index(drop=True)


def _actual(m: pd.DataFrame) -> np.ndarray:
    gp = m["pos"].map(GOAL_PTS).fillna(5).to_numpy()
    mins = m["minutes"].fillna(0).to_numpy()
    app = np.where(mins >= 60, 2.0, np.where(mins >= 1, 1.0, 0.0))
    return app + m["act_goals"].fillna(0).to_numpy() * gp + m["act_assists"].fillna(0).to_numpy() * 3.0


def project(m: pd.DataFrame) -> dict[str, np.ndarray]:
    gp = m["pos"].map(GOAL_PTS).fillna(5).to_numpy()
    sr = pd.to_numeric(m["starter_rate"], errors="coerce")
    ssr = pd.to_numeric(m["season_start_rate"], errors="coerce")
    p_start_v9 = (0.6 * sr.fillna(ssr) + 0.4 * ssr.fillna(sr)).clip(0, 1).fillna(0.6).to_numpy()
    app_v9 = np.where(pd.to_numeric(m["minutes_pg"], errors="coerce").fillna(60).to_numpy() >= 60, 2.0, 1.0)
    xs = m["xm_start"].fillna(pd.Series(p_start_v9)).clip(0, 1).to_numpy()
    x60 = np.minimum(m["xm_m60"].fillna(pd.Series(p_start_v9 * 0.8)).clip(0, 1).to_numpy(), xs)
    app_v3 = 2.0 * x60 + 1.0 * (xs - x60)

    def att(k):
        return m[f"p_goal_{k}"].to_numpy() * gp + m[f"p_assist_{k}"].to_numpy() * 3.0

    return {"V9": p_start_v9 * (app_v9 + att("v9")),
            "V9_CAL": p_start_v9 * (app_v9 + att("cal")),
            "V9_MIN": app_v3 + xs * att("v9"),
            "V3_FULL": app_v3 + xs * att("v3")}


def _week_boot(per_week: pd.DataFrame, col_a: str, col_b: str, n=4000) -> list:
    d = (per_week[col_b] - per_week[col_a]).to_numpy()
    if len(d) < 5:
        return [None, None]
    idx = RNG.integers(0, len(d), size=(n, len(d)))
    s = d[idx].mean(1)
    return [round(float(np.quantile(s, 0.05)), 4), round(float(np.quantile(s, 0.95)), 4)]


def evaluate(m: pd.DataFrame, proj: dict, y: np.ndarray) -> dict:
    from scipy.stats import spearmanr
    wk = m["date"].dt.strftime("%G-W%V").to_numpy()
    rows = []
    for w in np.unique(wk):
        k = wk == w
        if k.sum() < 40:
            continue
        r = {"week": w, "n": int(k.sum())}
        for v, p in proj.items():
            pv, yv = p[k], y[k]
            r[f"mae_{v}"] = float(np.abs(pv - yv).mean())
            r[f"rho_{v}"] = float(spearmanr(pv, yv).statistic)
            order = np.argsort(-pv)
            r[f"capt_{v}"] = float(yv[order[0]])
            r[f"top11_{v}"] = float(yv[order[:11]].sum())
        rows.append(r)
    W = pd.DataFrame(rows)
    res = {"weeks": int(len(W)), "rows": int(len(y)), "variants": {}}
    for v in proj:
        e = {"mae": round(float(W[f"mae_{v}"].mean()), 4), "spearman": round(float(W[f"rho_{v}"].mean()), 4),
             "captain_pts": round(float(W[f"capt_{v}"].mean()), 3), "top11_pts": round(float(W[f"top11_{v}"].mean()), 2)}
        if v != "V9":
            e["mae_diff_ci90"] = _week_boot(W, "mae_V9", f"mae_{v}")            # negative = better
            e["spearman_diff_ci90"] = _week_boot(W, "rho_V9", f"rho_{v}")       # positive = better
            e["captain_diff_ci90"] = _week_boot(W, "capt_V9", f"capt_{v}")
            e["top11_diff_ci90"] = _week_boot(W, "top11_V9", f"top11_{v}")
            mae_ok = e["mae_diff_ci90"][1] is not None and e["mae_diff_ci90"][1] < 0
            pick_ok = any(e[k][0] is not None and e[k][0] > 0 for k in ("captain_diff_ci90", "top11_diff_ci90"))
            e["verdict"] = "BETTER" if mae_ok and pick_ok else (
                "MORE_ACCURATE_PICKS_NOT_SHOWN" if mae_ok else "NOT_SHOWN")
        res["variants"][v] = e
    return res


def build() -> dict:
    X = load_features()
    fam = json.loads((CACHE / "families.json").read_text())
    xm = expected_minutes(X)
    X = X.merge(xm, on=["player_id", "fixture_id"], how="left")
    fam["MINUTES_V3"] = ["xm_start", "xm_minutes", "xm_m60", "xm_m75", "xm_m90"]
    probs = _attack_probs(X, fam)
    panel = _panel_pl().drop(columns=["position"], errors="ignore")
    panel = panel.merge(xm, on=["player_id", "fixture_id"], how="left")
    acts = X[["player_id", "fixture_id", "goals", "assists"]].rename(columns={"goals": "act_goals", "assists": "act_assists"})
    panel = panel.merge(acts.drop_duplicates(["player_id", "fixture_id"]), on=["player_id", "fixture_id"], how="left")
    # FAIR SLICE (added 2026-10-14 after the first run, before any decision): live v9 Fantasy also uses
    # FPL's injury / availability flags, which have no history. So the headline flatters any minutes
    # model by letting it catch long absences the live system partly catches already. The slice keeps
    # only players who played their club's PREVIOUS match; the recommendation rests on it.
    from src.player_v3 import minutes as M
    full = M.build_panel()
    club = (full[full["league"] == LEAGUE][["team", "fixture_id", "date"]]
            .drop_duplicates(["team", "fixture_id"]).sort_values("date", kind="mergesort"))
    club["prev_club_date"] = club.groupby("team")["date"].shift(1)
    panel = panel.merge(club[["team", "fixture_id", "prev_club_date"]], on=["team", "fixture_id"], how="left")
    m = _carry_last(panel, probs)
    m["pos"] = m["position"].astype(str).str[:1].str.upper()
    y = _actual(m)
    r = evaluate(m, project(m), y)
    k = (m["last_app_date"] == m["prev_club_date"]).to_numpy()
    mf = m[k].reset_index(drop=True)
    r["fair_slice"] = {"rule": "player appeared in his club's previous match", **evaluate(mf, project(mf), _actual(mf))}
    r.update({"population": f"{LEAGUE} squad panel from {HOLDOUT_FROM} (missed fixtures = 0 points)",
              "scored": "appearance + goals + assists (CS, saves, cards, bonus, DC excluded both sides)",
              "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")})
    return r


def to_md(r: dict) -> str:
    L = [f"# Fantasy (FPL) — v9 projections vs Player V3 ({r['generated_at']})", "",
         f"Population: {r['population']}. Scored: {r['scored']}. {r['weeks']} weeks, {r['rows']:,} player-fixtures.", "",
         "| Variant | MAE | Spearman (per week) | Captain pts | Top-11 pts | MAE Δ 90% CI | Captain Δ CI | Top-11 Δ CI | Verdict |",
         "|---|---|---|---|---|---|---|---|---|"]
    for v, e in r["variants"].items():
        L.append(f"| {v} | {e['mae']} | {e['spearman']} | {e['captain_pts']} | {e['top11_pts']} | "
                 f"{e.get('mae_diff_ci90', '—')} | {e.get('captain_diff_ci90', '—')} | {e.get('top11_diff_ci90', '—')} | "
                 f"{e.get('verdict', 'baseline')} |")
    f = r.get("fair_slice")
    if f:
        L += ["", f"## Fair slice — {f['rule']} ({f['rows']:,} player-fixtures, {f['weeks']} weeks)", "",
              "Live v9 Fantasy also uses FPL injury flags, which have no history; this slice removes the long "
              "absences those flags partly catch. **The recommendation rests on this table.**", "",
              "| Variant | MAE | Spearman | Captain pts | Top-11 pts | MAE Δ CI | Captain Δ CI | Top-11 Δ CI | Verdict |",
              "|---|---|---|---|---|---|---|---|---|"]
        for v, e in f["variants"].items():
            L.append(f"| {v} | {e['mae']} | {e['spearman']} | {e['captain_pts']} | {e['top11_pts']} | "
                     f"{e.get('mae_diff_ci90', '—')} | {e.get('captain_diff_ci90', '—')} | {e.get('top11_diff_ci90', '—')} | "
                     f"{e.get('verdict', 'baseline')} |")
    L += ["", "MAE Δ negative = more accurate; captain / top-11 Δ positive = better picks (actual points, "
              "captain not doubled). Rule in the module docstring, fixed before results."]
    return "\n".join(L) + "\n"


def main() -> int:
    r = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fantasy_v3.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "FANTASY_V3.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
