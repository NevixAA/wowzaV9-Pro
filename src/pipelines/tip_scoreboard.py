"""Are the tips we SEND hitting? Scoreboard for the 1X2 and Bet Builder tips Pro sends to Telegram.

    python -m src.pipelines.tip_scoreboard            # write output/tip_scoreboard.json + .md
    python -m src.pipelines.tip_scoreboard --notify   # also send the daily recap (once per day)

WHY THIS EXISTS. Both products settle their records (paper_1x2.csv, bet_builder_settled.csv), but
nothing reported on the tips that actually went out. paper_1x2's scoreboard grades every LOGGED
pick (165) together, of which only 26 were sent; Bet Builder's settled file holds 16,474 generated
combos of which 276 were sent. "How are the tips we send doing" had no answer anywhere.

WHAT IS MEASURED, AND WHAT IS NOT

1X2       Sent tips carry the price shown in the message, so this is a real betting record:
          hit rate, break-even (mean 1/odds), flat-stake units, ROI with a matchday-bootstrap CI.
Bet Builder
          No bookmaker builder price is collected anywhere (combo_price_snapshots is
          SOURCE_REQUIRED), so ROI cannot be measured honestly and is NOT reported. What can be
          measured is whether combos win as often as the model said: actual wins vs the sum of
          claimed joint probabilities, with a z-score. That is a calibration record, not P/L.

Paper leagues (USA MLS) are excluded from every headline, consistent with v9, and shown on their
own line so nothing is hidden.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

OUT_JSON = cfg.OUTPUT_DIR / "tip_scoreboard.json"
OUT_MD = cfg.OUTPUT_DIR / "TIP_SCOREBOARD.md"
SENT_STATE = cfg.OUTPUT_DIR / "tip_scoreboard_sent.json"
PICK_INDEX = {"HOME": 0, "DRAW": 1, "AWAY": 2}
RNG = np.random.default_rng(7)


def _ci(units: pd.Series, days: pd.Series, n_boot: int = 4000) -> list:
    g = pd.DataFrame({"u": units.to_numpy(), "d": days.to_numpy()}).groupby("d")["u"].agg(["sum", "count"])
    if len(g) < 3:
        return [None, None]
    idx = RNG.integers(0, len(g), size=(n_boot, len(g)))
    roi = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
    return [round(float(np.quantile(roi, 0.05)), 4), round(float(np.quantile(roi, 0.95)), 4)]


# ── 1X2 ───────────────────────────────────────────────────────────────────────────────────────
def one_x_two(d: pd.DataFrame | None = None) -> dict:
    if d is None:
        f = cfg.OUTPUT_DIR / "paper_1x2.csv"
        d = pd.read_csv(f, low_memory=False) if f.exists() else pd.DataFrame()
    if d.empty or "notified_at" not in d.columns:
        return {"sent": 0}
    s = d[d["notified_at"].notna()].copy()
    s["paper_league"] = s["league"].astype(str).str.strip().isin(cfg.PAPER_LEAGUES)
    s["res"] = pd.to_numeric(s["result"], errors="coerce")
    s["pick_i"] = s["notified_pick"].map(PICK_INDEX)
    s["odds"] = pd.to_numeric(s["notified_odds"], errors="coerce")
    st = s[s["res"].notna() & s["pick_i"].notna() & (s["odds"] > 1)].copy()
    st["won"] = (st["res"] == st["pick_i"]).astype(int)
    st["units"] = np.where(st["won"] == 1, st["odds"] - 1, -1.0)
    p_cols = ["p_home", "p_draw", "p_away"]
    st["claimed"] = [float(r[p_cols[int(r.pick_i)]]) for _, r in st.iterrows()] if len(st) else []

    def block(x: pd.DataFrame) -> dict:
        if x.empty:
            return {"settled": 0}
        return {"settled": int(len(x)), "won": int(x["won"].sum()),
                "hit_rate": round(float(x["won"].mean()), 4),
                "break_even": round(float((1 / x["odds"]).mean()), 4),
                "model_claimed": round(float(x["claimed"].mean()), 4),
                "avg_odds": round(float(x["odds"].mean()), 2),
                "units": round(float(x["units"].sum()), 2),
                "roi": round(float(x["units"].mean()), 4),
                "roi_ci90": _ci(x["units"], x["match_date"]),
                "negative_ev_when_sent": int((pd.to_numeric(x["notified_ev"], errors="coerce") < 0).sum())}

    head = st[~st["paper_league"]]
    recent = st.sort_values("match_date").tail(10)
    return {
        "sent": int(len(s)), "sent_excl_paper": int((~s["paper_league"]).sum()),
        "pending": int(s["res"].isna().sum()),
        "headline": block(head),
        "paper_leagues": block(st[st["paper_league"]]),
        "by_pick": {k: block(head[head["notified_pick"] == k]) for k in ("HOME", "DRAW", "AWAY")},
        "last_10": [{"date": r.match_date, "match": f"{r.home_team} v {r.away_team}",
                     "pick": r.notified_pick, "odds": r.odds, "won": bool(r.won)}
                    for r in recent.itertuples()],
    }


# ── Bet Builder ───────────────────────────────────────────────────────────────────────────────
def bet_builder(settled: pd.DataFrame | None = None, notified: dict | None = None) -> dict:
    if settled is None:
        f = cfg.OUTPUT_DIR / "bet_builder_settled.csv"
        settled = pd.read_csv(f, low_memory=False) if f.exists() else pd.DataFrame()
    if notified is None:
        f = cfg.OUTPUT_DIR / "combo_notified.json"
        notified = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if not notified:
        return {"sent": 0}
    sent_ids = set(notified)
    s = settled[settled["combo_id"].astype(str).isin(sent_ids)].drop_duplicates("combo_id", keep="last").copy()
    s["paper_league"] = s["league"].astype(str).str.strip().isin(cfg.PAPER_LEAGUES)
    s["p"] = pd.to_numeric(s["joint_probability"], errors="coerce")
    dec = s[s["combo_result"].isin(["WON", "LOST"])].copy()
    dec["won"] = (dec["combo_result"] == "WON").astype(int)
    # VOIDED LEGS. A combo whose player leg was voided is settled on the remaining legs, so it can
    # be WON while the claimed joint probability still covers every leg. Measured 2026-10-08: 43
    # of the 48 sent "wins" had a voided leg; with those removed, 5 of 81 won against 6.4
    # expected (z -0.57) — calibrated, not a 29% hit rate. The headline uses fully graded combos
    # only; the void-leg ones are reported beside it and never mixed in.
    dec["n_void"] = dec["leg_results"].astype(str).str.count("=VOID")
    full = dec[dec["n_void"] == 0]

    def block(x: pd.DataFrame) -> dict:
        if x.empty:
            return {"settled": 0}
        exp = float(x["p"].sum())
        var = float((x["p"] * (1 - x["p"])).sum())
        return {"settled": int(len(x)), "won": int(x["won"].sum()),
                "hit_rate": round(float(x["won"].mean()), 4),
                "model_claimed": round(float(x["p"].mean()), 4),
                "expected_wins": round(exp, 1),
                "z_actual_vs_claimed": round((x["won"].sum() - exp) / np.sqrt(var), 2) if var > 0 else None}

    head = full[~full["paper_league"]]
    voided = dec[(dec["n_void"] > 0) & ~dec["paper_league"]]
    bands = pd.cut(head["p"], [0, 0.1, 0.25, 0.4, 0.6, 1.0],
                   labels=["<10%", "10-25%", "25-40%", "40-60%", ">60%"])
    return {
        "sent": len(sent_ids), "found_in_settled": int(len(s)),
        "not_found": len(sent_ids) - int(len(s)),
        "ungraded": int((~s["combo_result"].isin(["WON", "LOST"])).sum()),
        "ungraded_reasons": s.loc[~s["combo_result"].isin(["WON", "LOST"]), "settle_note"]
                             .fillna("?").value_counts().to_dict(),
        "headline": block(head),
        "with_voided_legs": {"settled": int(len(voided)), "won": int(voided["won"].sum()),
                             "note": "settled on the remaining legs after a leg was voided; not "
                                     "comparable with the claimed probability, which covers every leg"},
        "paper_leagues": block(dec[dec["paper_league"]]),
        "by_claimed_probability": {str(k): block(head[bands == k]) for k in bands.cat.categories},
        "by_legs": {str(k): block(head[head["n_legs"] == k]) for k in sorted(head["n_legs"].dropna().unique())},
        "roi": "NOT MEASURED — no bookmaker builder price is collected (combo_price_snapshots is "
               "SOURCE_REQUIRED). Hit rate vs claimed probability is the honest measure.",
    }


# ── output ────────────────────────────────────────────────────────────────────────────────────
def build() -> dict:
    return {"generated_at": cfg.utc_now_iso(), "one_x_two": one_x_two(), "bet_builder": bet_builder()}


def _pct(x):
    return "–" if x is None else f"{x:.0%}"


def to_md(r: dict) -> str:
    a, b = r["one_x_two"], r["bet_builder"]
    h, bh = a.get("headline", {}), b.get("headline", {})
    L = [f"# Tip scoreboard — {r['generated_at'][:16]} UTC", "", "## 1X2 tips sent", ""]
    if h.get("settled"):
        ci = h["roi_ci90"]
        L += [f"- Sent {a['sent_excl_paper']} (excl. paper leagues), settled {h['settled']}, "
              f"pending {a['pending']}",
              f"- Won {h['won']}/{h['settled']} = **{_pct(h['hit_rate'])}** vs break-even "
              f"{_pct(h['break_even'])} (model claimed {_pct(h['model_claimed'])})",
              f"- Flat stakes: **{h['units']:+.2f}u**, ROI {h['roi']:+.1%}"
              + (f", 90% CI [{ci[0]:+.0%}, {ci[1]:+.0%}]" if ci[0] is not None else ""),
              f"- Sent with negative EV: {h['negative_ev_when_sent']}"]
    else:
        L.append("- No settled sent tips yet.")
    L += ["", "## Bet Builder combos sent", ""]
    if bh.get("settled"):
        v = b["with_voided_legs"]
        L += [f"- Sent {b['sent']}, fully graded {bh['settled']}, with a voided leg {v['settled']} "
              f"({v['won']} of those 'won' on the remaining legs), ungraded {b['ungraded']}",
              f"- Won {bh['won']}/{bh['settled']} = **{_pct(bh['hit_rate'])}**; the model claimed "
              f"{_pct(bh['model_claimed'])} on average, i.e. {bh['expected_wins']} expected wins "
              f"(z = {bh['z_actual_vs_claimed']})",
              f"- ROI: {b['roi']}"]
    else:
        L.append("- No graded sent combos yet.")
    return "\n".join(L)


def telegram_text(r: dict) -> str:
    a, b = r["one_x_two"], r["bet_builder"]
    h, bh = a.get("headline", {}), b.get("headline", {})
    lines = ["📋 *Tip scoreboard* — tips sent so far", ""]
    if h.get("settled"):
        lines += ["*1X2*",
                  f"Won {h['won']}/{h['settled']} ({_pct(h['hit_rate'])}) · needs {_pct(h['break_even'])} to break even",
                  f"Flat stakes {h['units']:+.2f}u · ROI {h['roi']:+.0%}", ""]
    if bh.get("settled"):
        lines += ["*Bet Builder*",
                  f"Won {bh['won']}/{bh['settled']} ({_pct(bh['hit_rate'])}) · model expected {bh['expected_wins']:.0f} wins",
                  f"_Combos with a voided leg ({b['with_voided_legs']['settled']}) counted separately._",
                  "_No bookmaker builder price is recorded, so no P/L._", ""]
    if len(lines) == 2:
        lines.append("Nothing settled yet.")
    lines.append("_Paper leagues excluded._")
    return "\n".join(lines)


def maybe_notify(r: dict, now: dt.datetime | None = None) -> str:
    """Once per UTC day, first run inside 05:00-11:00 UTC. Safe to over-schedule (CLAUDE.md:
    make a time-sensitive job idempotent first, then over-schedule it)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not (5 <= now.hour < 11):
        return "outside window"
    key = f"SCOREBOARD|{now:%Y-%m-%d}"
    state = json.loads(SENT_STATE.read_text(encoding="utf-8")) if SENT_STATE.exists() else {}
    if key in state:
        return "already sent today"
    if not getattr(cfg, "PRO_MAY_NOTIFY", False):
        return "PRO_MAY_NOTIFY off"
    from src.combo import notify as cn
    ok, detail = cn.send(telegram_text(r))
    if not ok:
        return f"send failed: {detail}"
    state[key] = now.isoformat()
    SENT_STATE.write_text(json.dumps(state, indent=0), encoding="utf-8")
    return "sent"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()
    r = build()
    cfg.OUTPUT_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    OUT_MD.write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    if a.notify:
        print(f"[scoreboard] telegram: {maybe_notify(r)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
