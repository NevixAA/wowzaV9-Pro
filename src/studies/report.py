"""Combine the October 2026 studies into output/studies/REPORT.md.

    python -m src.studies.argentina_btts && python -m src.studies.ou_studies \
        && python -m src.studies.evidence && python -m src.studies.report
"""
from __future__ import annotations

import json

from config import pro_config as cfg

D = cfg.OUTPUT_DIR / "studies"


def _j(name):
    return json.loads((D / f"{name}.json").read_text(encoding="utf-8"))


def _pct(x, d=0):
    return "–" if x is None else f"{x * 100:+.{d}f}%"


def _ci(c):
    return "–" if not c or c[0] is None else f"[{c[0] * 100:+.0f}%, {c[1] * 100:+.0f}%]"


def _cs(cs):
    return "–" if cs.get("lcb") is None else f"[{cs['lcb']:+.1f}, {cs['ucb']:+.1f}]"


def main() -> int:
    a, o, e = _j("argentina_btts"), _j("ou_studies"), _j("evidence")
    ch = _j("ou_challenger") if (D / "ou_challenger.json").exists() else None
    t, rg = a["tip_period"], a["regime_by_period"].get("2026 since Aug 10 (tip period)", {})
    mv = a.get("model_vs_market", {})
    L = ["# Upgrade studies — October 2026", "",
         "Research only. Nothing here changes v9, a threshold or a stake.", "",
         "## 1. Argentina BTTS: model, league, bookmaker, or luck?", "",
         f"- BTTS rate, all Argentina matches: 2025 **{a['btts_rate_all_matches']['2025']['rate']:.0%}**, "
         f"2026 {a['btts_rate_all_matches']['2026']['rate']:.0%}, since 10 Aug "
         f"**{a['btts_rate_all_matches']['2026 since Aug 10']['rate']:.0%}**.",
         f"- Tip period, {rg.get('n')} matches with a clean Bet365 price: BTTS happened "
         f"{rg.get('btts_rate', 0):.0%} while the de-vigged price implied {rg.get('bet365_fair_yes_close', 0):.0%} "
         f"(gap {rg.get('gap_pp')} points).",
         f"- **B, blind YES on every match: {_pct(t['B_blind_yes_all'].get('roi'))}** "
         f"{_ci(t['B_blind_yes_all'].get('roi_ci90'))}, n {t['B_blind_yes_all'].get('n')}.",
         f"- A, matches Wowza picked: {_pct(t['A_wowza_selected'].get('roi'))}; matches it did not pick: "
         f"{_pct(t['not_selected'].get('roi'))}. Difference {_pct(t.get('A_minus_not_selected_roi'))} "
         f"{_ci(t.get('A_minus_not_selected_ci90'))} — **not distinguishable from zero**.",
         f"- Model vs market on the same matches: Brier {mv.get('brier_model')} vs {mv.get('brier_market')}; "
         f"residual z {mv.get('residual_z')} (no fixture-level signal beyond the level).",
         f"- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus "
         f"({a['C_market_relative']['n_fixtures']} fixtures). The whole market is behind, not one book.",
         f"- {a['dropped_first_half_contaminated_prices']} Bet365 price pairs were the FIRST-HALF BTTS market and "
         "were dropped (YES 8.00 / NO 1.08 passes a margin check).", "",
         "**Reading.** The profit is a league scoring regime the market has priced slowly, not model "
         "selection. Wowza's contribution is being more bullish on YES than the market. If the league "
         "reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.", "",
         "## 2. The UNDER problem", ""]
    u = o["under"]
    L += [f"- {u['n']} O/U 2.5 fixtures, every priced one (not only tips).",
          "- The model's P(over) barely moves: it sits around 52% in every band while the market ranges "
          "41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.",
          "", "| Model leans | n | Realised over | Model | Market | Model error | Market error |",
          "|---|---|---|---|---|---|---|"]
    for k, v in u["by_model_lean"].items():
        L.append(f"| {k} | {v['n']} | {v['realised_over']:.0%} | {v['model_p_over']:.0%} | {v['market_p_over']:.0%} | "
                 f"{v['model_error_pp']:+.1f} | {v['market_error_pp']:+.1f} |")
    L += ["", f"- Share of the model's lean that showed up in results: leaning UNDER "
          f"{u.get('leans_under_share_of_lean_realised')}, leaning OVER {u.get('leans_over_share_of_lean_realised')} "
          "(1 = all of it, 0 = none; negative = the result moved the other way).",
          "", "**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays "
          "near 52%. The market is right. The fix is in the probability: anchor on the market and add the "
          "model only as a small, fitted residual — whose fitted weight is currently about zero.", "",
          "## 3. Does the model add anything once the price is known?", "",
          "| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |",
          "|---|---|---|---|---|---|---|---|"]
    for m, by in o["residual"].items():
        for tr, x in by.items():
            if x.get("n_oos"):
                ci = x["oos_delta_logloss_ci90"]
                L.append(f"| {m} | {tr} | {x['n']} | {x['brier_market_raw']} | {x['brier_model_raw']} | "
                         f"{x['oos_delta_logloss']:+.5f} | [{ci[0]:+.4f}, {ci[1]:+.4f}] | {x['verdict']} |")
    L += ["", "Negative Δ = adding the model improved the forecast. No market × track shows an improvement; "
          "several are made worse. O/U stays PAPER regardless of short ROI windows.", "",
          "## 4. Evidence per cell (staked tips since 10 Aug)", "",
          f"{e['n_cells_searched']} cells tested (of {e['n_cells_total']}; the rest are too small). Pooled prior "
          f"{_pct(e['pool']['prior_mean'], 1)}, between-cell sd {e['pool']['tau']:.2f}. "
          f"Reality-check p for the best cell: **{e['reality_check_p_best_cell']}**.", "",
          "| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in e["cells"]:
        if not c["testable"]:
            continue
        cs = c["clv_cs"]
        L.append(f"| {c['league']} | {c['market']} | {c['n']} | {_pct(c['roi'])} | {_pct(c['posterior_mean'])} | "
                 f"{c['p_edge_gt_0']:.2f} | {c['q_bh']:.2f} | "
                 f"{_cs(cs)} | "
                 f"{c['recommendation']} |")
    if ch and ch.get("probabilistic_oos"):
        po, tv, tc, w = ch["probabilistic_oos"], ch["tips_at_5pct_edge"]["v9"], ch["tips_at_5pct_edge"]["challenger"], ch["current_weights"]
        L += ["", "## 5. Market-anchored O/U 2.5 challenger", "",
              f"`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only "
              f"(never the close). {ch['oos_fixtures']} out-of-sample fixtures.", "",
              "| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |",
              "|---|---|---|---|---|---|---|---|",
              f"| Market | {po['market']['logloss']} | {po['market']['brier']} | – | – | – | – | – |",
              f"| v9 | {po['v9']['logloss']} | {po['v9']['brier']} | {tv.get('n')} | {tv.get('under_share', '–')} | "
              f"{tv.get('units', '–')} | {_pct(tv.get('roi'))} | {tv.get('mean_clv_pp', '–')} |",
              f"| Challenger | {po['challenger']['logloss']} | {po['challenger']['brier']} | {tc.get('n')} | "
              f"{tc.get('under_share', '–')} | {tc.get('units', '–')} | {_pct(tc.get('roi'))} | {tc.get('mean_clv_pp', '–')} |",
              "", f"Current weights: c (model) = {w['c_model']} — unconstrained fit {w['c_model_unconstrained']}, i.e. "
              "given the market, v9's lean points the WRONG way, so it gets no say. Forward record: "
              "`output/studies/ou_challenger_forward.csv` (first sight, never revised)."]
    L += ["", "Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration "
          "alarm. Recommendations only; the execution policy changes by a human-approved commit."]
    (D / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
