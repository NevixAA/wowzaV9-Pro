"""
Daily board digest — what is LIVE right now, at every tier.
===========================================================
    python -m src.pipelines.board_digest [--days 4] [--out output/board_digest.md]

THE PROBLEM IT SOLVES. v9 notifies a tip ONCE, when it is first detected — typically 3-5 days
before kickoff. So on a match day you can see nothing at all while a full board sits waiting. That
happened on 2026-08-21: three standard VALUABLE tips (Oviedo v Leganes, SD Eibar v Real Valladolid,
Sudtirol v Virtus Entella) were all live for the weekend and all already in notified.json, sent
earlier in the week. Nothing was broken and nothing was below threshold — the notifications had
simply already happened.

Lowering the tier thresholds would NOT have produced a single extra message that weekend, because
dedup, not the bar, is what kept the board quiet. A digest is the actual fix: it shows the standing
board every morning rather than only the moment a tip appears.

WHY IT LIVES IN PRO AND SENDS NOTHING. v9 is frozen, and `PRO_MAY_NOTIFY = False` — Pro must never
notify. So this writes a markdown file and publishes to the GitHub Actions job summary, which is
visible without any Telegram message. Read-only against v9 throughout.

WHAT IT DELIBERATELY SEPARATES. Staked and recorded are different things, and conflating them is
how "26 tips" becomes a P&L expectation when only 3 carry money:

    STAKED    SNIPER + MARKSMAN only
    RECORDED  VALUABLE and below — tracked for measurement, never bet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import v9_source as v9

STAKED = ("SNIPER", "MARKSMAN")


def _read(name: str) -> pd.DataFrame:
    try:
        return v9.fetch_csv(name, required=False)
    except Exception:
        return pd.DataFrame()


def _upcoming(df: pd.DataFrame, days: int, now) -> pd.DataFrame:
    """Fixtures that have NOT kicked off yet, within the window.

    Prefers kickoff_utc and falls back to the date column. The fallback is a DAY-level filter and
    cannot exclude a fixture that kicked off earlier today — reported rather than hidden, because a
    digest that silently lists a started match is worse than one that says it cannot tell.
    """
    if df.empty:
        return df, "empty"
    for c in ("kickoff_utc", "kickoff_ts"):
        if c in df.columns:
            t = pd.to_datetime(df[c], errors="coerce", utc=True)
            if t.notna().any():
                m = (t > now) & (t <= now + pd.Timedelta(days=days))
                return df[m].assign(_ko=t[m]), "kickoff"
    for c in ("date", "match_date"):
        if c in df.columns:
            t = pd.to_datetime(df[c], errors="coerce", utc=True)
            if t.notna().any():
                m = (t >= now.normalize()) & (t <= now + pd.Timedelta(days=days))
                return df[m].assign(_ko=t[m]), "date-only"
    return df.iloc[0:0], "no-timestamp"


def build(days: int = 4) -> str:
    now = pd.Timestamp.now(tz="UTC")
    L: list[str] = []
    L.append(f"# Board digest — {now:%Y-%m-%d %H:%M UTC}")
    L.append("")
    L.append(f"Next **{days} days**. Read-only from v9. "
             f"**STAKED = SNIPER/MARKSMAN only**; everything else is recorded, not bet.")
    L.append("")

    # ── main O/U board ───────────────────────────────────────────────────────
    bets = _read("output/bets.csv")
    up, how = _upcoming(bets, days, now)
    tier = next((c for c in ("signal_tier", "tier") if c in up.columns), None)
    L.append("## Main O/U 2.5")
    if up.empty:
        L.append(f"_No upcoming fixtures on the board ({how})._")
    else:
        counts = up[tier].fillna("-").value_counts().to_dict() if tier else {}
        staked = up[up[tier].isin(STAKED)] if tier else up.iloc[0:0]
        L.append(f"{len(up)} fixture(s) · tiers `{counts}` · filter `{how}`")
        L.append("")
        L.append(f"### STAKED — {len(staked)}")
        if staked.empty:
            L.append("_None. Nothing cleared SNIPER or MARKSMAN._")
        else:
            L.append("| kickoff | league | fixture | side | odds | edge | tier | drift |")
            L.append("|---|---|---|---|---|---|---|---|")
            for _, r in staked.sort_values("_ko").iterrows():
                side = str(r.get("bet") or r.get("best_side") or "")
                # the price of the side ACTUALLY BET — printing the other one is how a 2.92
                # UNDER got reported as 1.39 on 2026-08-19
                odds = r.get("odds_under25") if side.upper() == "UNDER" else r.get("odds_over25")
                edge = pd.to_numeric(pd.Series([r.get("best_edge")]), errors="coerce").iloc[0]
                L.append(f"| {r['_ko']:%m-%d %H:%M} | {r.get('league','')} | "
                         f"{r.get('home_team','')} v {r.get('away_team','')} | {side} | "
                         f"{odds} | {'' if pd.isna(edge) else f'{100*edge:.1f}%'} | "
                         f"{r.get(tier,'')} | {r.get('drift_signal','')} |")
        rec = up[~up[tier].isin(STAKED)] if tier else up
        L.append("")
        L.append(f"### Recorded, not staked — {len(rec)}")
        if not rec.empty and "best_edge" in rec.columns:
            e = pd.to_numeric(rec["best_edge"], errors="coerce")
            L.append(f"top edge {100 * e.max():.1f}% · median {100 * e.median():.1f}%")
            top = rec.assign(_e=e).nlargest(6, "_e")
            L.append("")
            L.append("| kickoff | league | fixture | side | edge | tier | note |")
            L.append("|---|---|---|---|---|---|---|")
            for _, r in top.iterrows():
                note = "no form data" if bool(r.get("no_form_data")) else ""
                L.append(f"| {r['_ko']:%m-%d %H:%M} | {r.get('league','')} | "
                         f"{r.get('home_team','')} v {r.get('away_team','')} | "
                         f"{r.get('best_side','')} | {100*r['_e']:.1f}% | {r.get(tier,'')} | "
                         f"{note} |")
    L.append("")

    # ── side markets ─────────────────────────────────────────────────────────
    side_led = _read("output/side_bets_ledger.csv")
    sup, show = _upcoming(side_led, days, now)
    L.append("## Side markets (BTTS / O1.5 / O3.5)")
    st = next((c for c in ("signal_tier", "tier") if c in sup.columns), None)
    if sup.empty:
        L.append(f"_Nothing upcoming ({show})._")
    else:
        staked = sup[sup[st].isin(STAKED)] if st else sup.iloc[0:0]
        L.append(f"{len(sup)} row(s) · tiers `{sup[st].value_counts().to_dict() if st else {}}` "
                 f"· markets `{sup['market'].value_counts().to_dict() if 'market' in sup else {}}` "
                 f"· filter `{show}`")
        L.append("")
        L.append(f"### STAKED — {len(staked)}")
        if staked.empty:
            L.append("_None._")
        else:
            L.append("| date | league | fixture | market | odds | edge | tier |")
            L.append("|---|---|---|---|---|---|---|")
            for _, r in staked.sort_values("_ko").iterrows():
                L.append(f"| {r['_ko']:%m-%d} | {r.get('league','')} | "
                         f"{r.get('home_team','')} v {r.get('away_team','')} | "
                         f"{r.get('market','')} | {r.get('odds','')} | "
                         f"{r.get('edge_pct','')}% | {r.get(st,'')} |")
        # concentration is worth surfacing: correlated bets lose together
        if len(staked) and "league" in staked.columns:
            vc = staked["league"].value_counts()
            if len(vc) and vc.iloc[0] >= 3:
                L.append("")
                L.append(f"> **Concentration:** {vc.iloc[0]} of {len(staked)} staked side tips are "
                         f"in **{vc.index[0]}**. Same league, same market means they are not "
                         f"independent — a systematic bias loses them together.")
    L.append("")

    # ── player props: paper only, permanently ────────────────────────────────
    props = _read("output/player_tips.csv")
    pup, pshow = _upcoming(props, days, now)
    L.append("## Player props — PAPER ONLY (invariant 2, never staked)")
    if pup.empty:
        L.append(f"_Nothing upcoming ({pshow})._")
    else:
        pt = "tier" if "tier" in pup.columns else None
        mo = pd.to_numeric(pup.get("market_odds"), errors="coerce")
        priced = pup[mo.notna() & (mo > 1)]
        L.append(f"{len(pup)} row(s) · **priced by the market: {len(priced)}** · "
                 f"unpriced: {len(pup) - len(priced)}")
        L.append("")
        L.append("> An unpriced row is `AVOID` **by construction**, not a model rejection "
                 "(invariant 13) — no price means no edge was ever computed.")
        if pt and len(priced):
            sig = priced[priced[pt].isin(["PAPER", "VALUABLE", "SNIPER", "MARKSMAN"])]
            L.append("")
            L.append(f"### Priced signals — {len(sig)}")
            if sig.empty:
                L.append("_None among priced rows._")
            else:
                L.append("| player | team | league | market | mkt odds | fair | tier |")
                L.append("|---|---|---|---|---|---|---|")
                for _, r in sig.iterrows():
                    L.append(f"| {r.get('player_name','')} | {r.get('team','')} | "
                             f"{r.get('league','')} | {r.get('market','')} | "
                             f"{r.get('market_odds','')} | {r.get('fair_odds','')} | "
                             f"{r.get(pt,'')} |")
    L.append("")
    L.append("---")
    L.append(f"_Generated by Pro from v9's committed output. Pro sends no notifications "
             f"(`PRO_MAY_NOTIFY={cfg.PRO_MAY_NOTIFY}`)._")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=4)
    ap.add_argument("--out", default=str(cfg.OUTPUT_DIR / "board_digest.md"))
    a = ap.parse_args()
    md = build(days=a.days)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[digest] written -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
