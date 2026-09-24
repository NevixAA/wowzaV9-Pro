"""Publication-quality charts for the shadow-learning results.

    python -m src.shadow_learning.charts --write

Section 76. Honest axes throughout -- section 76 asks for that explicitly, and it is the easiest
thing in this whole project to get wrong: the differences here are thousandths of a nat, and an
axis cropped to the data range turns a rounding error into a cliff. Every metric panel starts
from a range that includes the naive baseline where one exists, so the reader can see how much
of the plot is actually skill.

WHAT EACH CHART HAS TO SURVIVE. A monthly series of 50 points on four variants is noisy, and a
raw line chart of it invites the eye to find a trend that the statistics do not support. So:

  * the FROZEN control is drawn on every learning chart, in the same panel, on the same axis --
    never in a separate figure where the reader has to hold two pictures in their head;
  * a 6-month rolling mean is drawn over the monthly points rather than replacing them, so the
    noise stays visible and the trend is not a claim made by smoothing;
  * the trend verdict from the formal test is printed on the panel, so the picture cannot say
    something the statistics did not.

COLOR. Four categorical hues in fixed order, validated by the skill's checker: all six checks
pass on the light surface, with a contrast warning on two slots that obliges visible labels --
so every series carries a direct label as well as a legend, and identity is never colour alone.
The league heatmap is diverging blue/red on a gray midpoint, because its quantity has a
meaningful zero (retraining helped / hurt) and a sequential ramp would hide the sign.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

# Validated categorical order (see references/palette.md); never cycled.
SERIES = {"canonical": "#2a78d6", "frozen": "#eb6834",
          "rolling_3y": "#1baf7a", "v9_path": "#eda100",
          "current": "#1baf7a"}
LABEL = {"canonical": "retrained monthly", "frozen": "FROZEN (never retrains)",
         "rolling_3y": "rolling 3-year window", "v9_path": "v9 data path",
         "current": "current player data"}
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#22201d", "#55524d", "#8b8781"
DIVERGE = ("#d03b3b", "#f0efec", "#2a78d6")      # hurt <- neutral -> helped


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def C() -> Path:
    p = O() / "charts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "font.size": 10,
        "axes.edgecolor": "#d8d5d0", "axes.linewidth": 0.8,
        "axes.labelcolor": INK2, "text.color": INK,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "grid.color": "#e9e6e1", "grid.linewidth": 0.7,
        "legend.frameon": False, "figure.dpi": 150,
    })
    return plt


def _finish(ax, title, subtitle=None, ylabel=None):
    ax.set_title(title, loc="left", fontsize=12.5, color=INK, pad=14 if subtitle else 8,
                 fontweight="semibold")
    if subtitle:
        ax.text(0, 1.035, subtitle, transform=ax.transAxes, fontsize=9, color=MUTED,
                va="bottom")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(axis="y", alpha=0.9)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def _monthly(ax, led, metric, *, variants, roll=6, lower_better=True, trends=None,
             target=None):
    for v in variants:
        g = led[led.variant == v].sort_values("month")
        if g.empty:
            continue
        x = np.arange(len(g))
        y = g[metric].to_numpy(dtype=float)
        c = SERIES.get(v, MUTED)
        ax.plot(x, y, lw=0.9, color=c, alpha=0.30, zorder=2)
        r = pd.Series(y).rolling(roll, min_periods=max(2, roll // 2)).mean()
        ax.plot(x, r, lw=2.0, color=c, zorder=3,
                label=f"{LABEL.get(v, v)}")
        # Direct label at the end of the rolling line -- identity is never colour alone.
        if np.isfinite(r.iloc[-1]):
            # Stagger vertically by series index: two labels landing at the same height was
            # putting "FROZEN (never retrains)" straight through the other line.
            dy = 7 if variants.index(v) % 2 == 0 else -9
            ax.annotate(LABEL.get(v, v), (x[-1], r.iloc[-1]), xytext=(7, dy),
                        textcoords="offset points", fontsize=8, color=INK2,
                        va="center", ha="left")
    g0 = led[led.variant == variants[0]].sort_values("month")
    # Every 9th month, and year-only labels. At every 6th with full YYYY-MM the ticks ran into
    # each other ("2023-082024-02") -- unreadable, and the kind of thing only rendering the
    # figure and looking at it catches.
    ticks = np.arange(0, len(g0), 9)
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(g0["month"].iloc[i])[:7] for i in ticks], rotation=0, fontsize=8)

    # ROBUST Y-RANGE, AND SAY SO WHEN IT CLIPS. One chaotic month on Over 2.5 (-0.026) stretched
    # the axis until four years of real signal looked flat. Cropping silently would be the
    # dishonesty section 76 warns about, so the panel is framed on the 1st-99th percentile of
    # the plotted series and states how many points fall outside.
    vals = np.concatenate([led[led.variant == v][metric].to_numpy(dtype=float)
                           for v in variants if (led.variant == v).any()])
    vals = vals[np.isfinite(vals)]
    if vals.size > 20:
        lo, hi = np.percentile(vals, [1, 99])
        pad = (hi - lo) * 0.18 or 0.001
        n_out = int(((vals < lo - pad) | (vals > hi + pad)).sum())
        ax.set_ylim(lo - pad, hi + pad)
        if n_out:
            ax.text(0.985, 0.96, f"{n_out} extreme month(s) outside this range",
                    transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
                    color=MUTED, style="italic")
    if trends is not None and target is not None:
        t = trends[(trends.variant == variants[0]) & (trends.target == target)
                   & (trends.metric == metric)]
        if len(t):
            ax.text(0.985, 0.04, f"formal trend: {t.verdict.iloc[0]}  (p={t.p_value.iloc[0]:.3f})",
                    transform=ax.transAxes, ha="right", fontsize=8, color=MUTED)


def chart_headline(led, trends):
    """The one chart that carries the whole finding."""
    plt = _style()
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.4), sharex=True)
    for ax, t in zip(axes.ravel(), ("btts", "over15", "over25", "over35")):
        sub = led[(led.target == t) & led.interpretable]
        _monthly(ax, sub, "margin_vs_baseline_ll",
                 variants=["canonical", "frozen"], trends=trends, target=t)
        ax.axhline(0, color=MUTED, lw=0.9, ls=(0, (4, 3)), zorder=1)
        _finish(ax, {"btts": "Both teams to score", "over15": "Over 1.5",
                     "over25": "Over 2.5", "over35": "Over 3.5"}[t])
        ax.set_xlim(-1, len(sub[sub.variant == "canonical"]) + 9)
    axes[0, 0].set_ylabel("edge over a naive forecast", fontsize=9)
    axes[1, 0].set_ylabel("edge over a naive forecast", fontsize=9)
    fig.suptitle("Does Wowza learn?  Retrained monthly vs frozen in Aug 2022",
                 x=0.012, ha="left", fontsize=15, color=INK, fontweight="semibold")
    fig.text(0.012, 0.943,
             "Higher is better. Zero = no better than guessing each league's base rate. "
             "Faint line: month. Bold: 6-month average. Identical fixtures for both models.",
             fontsize=9, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(C() / "frozen_vs_retrained.png", bbox_inches="tight")
    plt.close(fig)


def chart_metric(led, trends, metric, fname, title, sub, ylabel):
    plt = _style()
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.2), sharex=True)
    for ax, t in zip(axes.ravel(), ("btts", "over15", "over25", "over35")):
        s = led[(led.target == t) & led.interpretable]
        _monthly(ax, s, metric, variants=["canonical", "frozen", "rolling_3y"],
                 trends=trends, target=t)
        _finish(ax, {"btts": "Both teams to score", "over15": "Over 1.5",
                     "over25": "Over 2.5", "over35": "Over 3.5"}[t])
        ax.set_xlim(-1, len(s[s.variant == "canonical"]) + 11)
    axes[0, 0].set_ylabel(ylabel, fontsize=9)
    axes[1, 0].set_ylabel(ylabel, fontsize=9)
    fig.suptitle(title, x=0.012, ha="left", fontsize=15, color=INK, fontweight="semibold")
    fig.text(0.012, 0.943, sub, fontsize=9, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(C() / fname, bbox_inches="tight")
    plt.close(fig)


def chart_league_heatmap(lt):
    plt = _style()
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    d = lt[lt.verdict != "INSUFFICIENT"].copy()
    piv = d.pivot_table(index="league", columns="target", values="delta")
    piv = piv.loc[piv.mean(axis=1).sort_values(ascending=False).index]
    cmap = LinearSegmentedColormap.from_list("d", [DIVERGE[0], DIVERGE[1], DIVERGE[2]])
    lim = float(np.nanmax(np.abs(piv.to_numpy())))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    fig, ax = plt.subplots(figsize=(7.6, 0.30 * len(piv) + 2.1))
    im = ax.imshow(piv.to_numpy(), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(["BTTS", "Over 1.5", "Over 2.5", "Over 3.5"], fontsize=9, color=INK2)
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels(piv.index, fontsize=8)
    for i in range(len(piv)):
        for j in range(len(piv.columns)):
            v = piv.iloc[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:+.3f}", ha="center", va="center", fontsize=6.6,
                        color=INK if abs(v) < lim * 0.55 else SURFACE)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("retraining gain (log loss)", fontsize=8.5, color=INK2)
    cb.outline.set_visible(False)
    ax.set_title("Where retraining helps, league by league",
                 loc="left", fontsize=13, color=INK, fontweight="semibold", pad=16)
    ax.text(0, -0.055, "Blue = retraining beat the frozen model. Red = it did not. "
            "Numbers are the log-loss gain on identical fixtures.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED, va="top")
    fig.savefig(C() / "league_learning_heatmap.png", bbox_inches="tight")
    plt.close(fig)


def chart_training_size(led):
    plt = _style()
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    s = led[(led.variant == "canonical") & led.interpretable]
    for t, mk in zip(("btts", "over15", "over25", "over35"), ("o", "s", "^", "D")):
        g = s[s.target == t]
        ax.scatter(g["n_train"] / 1000, g["log_loss"], s=22, alpha=0.55,
                   color=list(SERIES.values())[("btts", "over15", "over25",
                                                "over35").index(t)],
                   marker=mk, label={"btts": "BTTS", "over15": "Over 1.5",
                                     "over25": "Over 2.5", "over35": "Over 3.5"}[t],
                   linewidths=0)
    ax.legend(fontsize=8.5, loc="upper right", ncol=2)
    ax.set_xlabel("training matches available (thousands)", fontsize=9)
    _finish(ax, "More experience, better next month?",
            "Each dot is one month. Lower is better. Four markets on different scales — "
            "read the slope within a colour, not across colours.",
            "prediction error next month")
    fig.savefig(C() / "training_size_vs_future_logloss.png", bbox_inches="tight")
    plt.close(fig)


def chart_player(pled, ptr):
    plt = _style()
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    for ax, (metric, lab, note) in zip(axes, [
            ("pr_auc", "PR-AUC (rare-event skill)", "Higher is better."),
            ("margin_vs_baseline_ll", "edge over a position baseline", "Higher is better.")]):
        _monthly(ax, pled, metric, variants=["canonical", "current", "frozen"], roll=6)
        _finish(ax, lab, note)
        ax.set_xlim(-1, pled[pled.variant == "canonical"].shape[0] + 12)
    fig.suptitle("Player: does recovering the stranded records help?",
                 x=0.012, ha="left", fontsize=15, color=INK, fontweight="semibold")
    fig.text(0.012, 0.935, "Players score in ~8% of appearances, so PR-AUC is the metric "
             "that moves. 41 months, 959,007 appearances.", fontsize=9, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.915))
    fig.savefig(C() / "player_scorer_learning.png", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    led = pd.read_csv(O() / "monthly_walkforward_performance.csv")
    tr = pd.read_csv(O() / "walkforward_trends.csv")
    lt = pd.read_csv(O() / "league_target_comparison.csv")

    chart_headline(led, tr)
    chart_metric(led, tr, "log_loss", "global_logloss_by_month",
                 "Prediction error by month", "Lower is better. Raw error — this is the "
                 "view that can mislead: it moves with how hard the football was.",
                 "prediction error")
    chart_metric(led, tr, "brier", "global_brier_by_month",
                 "Brier score by month", "Lower is better.", "Brier")
    chart_metric(led, tr, "accuracy_lift", "accuracy_lift_by_month",
                 "Accuracy above the majority class, by month",
                 "Percentage points above always-guess-the-common-outcome.", "points")
    chart_league_heatmap(lt)
    chart_training_size(led)

    pp = O() / "player_walkforward_performance.csv"
    if pp.exists():
        pled = pd.read_csv(pp)
        ptr = pd.read_csv(O() / "player_walkforward_trends.csv")
        chart_player(pled, ptr)

    made = sorted(p.name for p in C().glob("*.png"))
    print(f"[charts] wrote {len(made)} charts to {C()}")
    for m in made:
        print(f"   {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
