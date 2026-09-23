# CANONICAL ARCHITECTURE DESIGN

One recommendation, not five options (section 48). Nothing here is deployed; the canonical view exists in parallel and no production path reads it.

## Ownership

| repo | owns |
|---|---|
| **v9** | production. Collects, predicts, tips, settles. Serves the approved model. Keeps writing its raw captures exactly as it does today. |
| **Pro** | memory. Canonicalises v9's raw output, builds training datasets, validates challengers, holds the promotion gate. |
| **v11** | experiments. Market hypotheses only. Never a source of production truth, never a direct route into v9. |

## Layers

```text
RAW        provider data, unchanged, never merged           v9 (+ Pro's own captures)
  |        fd_history, af_history, odds captures, caches
  v
CANONICAL  normalised, club identity resolved, deduped      Pro
  |        canonical_match_history / _player / _market
  v
DERIVED    features, training views, model outputs          Pro
  |        match_training.parquet, player_training.parquet
  v
REPORT     CSV/JSON/Markdown for humans                     all three
```

Raw is never merged or deleted. The consolidation happens at the canonical layer, which is a REBUILD rather than a migration: a script reads every raw source and produces the canonical table deterministically. If the canonical table is wrong, fix the builder and rebuild. If raw had been archived first, there would be no way back — and this estate has twice in two days needed exactly that route (a cache-skip bug that froze four seasons of columns, and an odds enrichment that was a silent no-op).

## Why Pro and not v9

v9 is frozen and live. Pro already holds the validation machinery — chronological splits, FDR control, calibration, the prediction lab — and already reads v9's committed output without writing back. The canonical layer needs exactly that position.

## What changes for live collection

Nothing, and deliberately. Live collect keeps appending to its own raw files; the canonical rebuild folds them in. Having live collect write ONLY into a combined file would mean one bad run corrupts the only copy with no source to rebuild from.

## Sequencing

| phase | what | reversible |
|---|---|---|
| A | audit, quantify stranded data | n/a — read only |
| B | canonical view in parallel, nothing reads it | yes — delete one file |
| C | prove equivalence: same backtest, same numbers on the shared subset | yes |
| D | challenger trained on canonical, chronological OOS vs champion | yes |
| E | decision on production training input — **requires explicit approval** | — |

A through D are done or in progress. **E is not recommended today**, and the reason is evidence rather than caution: the canonical dataset is statistically indistinguishable from the current one on every target. There is no prediction gain to bank, so there is no case for taking the risk of switching production's training input.

## What IS worth doing now

1. **Read `backtest_all_leagues.csv` into the canonical layer.** 22,522 fixtures we already own and no code opens. Cost: nothing. It does not improve prediction, but it makes the history complete and reproducible.
2. **Fix the COVID filter, or delete it.** It has been inert; right now it is a comment that looks like a control.
3. **De-duplicate the training frame.** 2,889 rows are double-weighted.
4. **Close the player loop.** ~709 fixtures of collected player data never reach `player_history.parquet`.
5. **Keep the coverage report and the canary.** The four-season column gap survived because nothing failed and nobody looked.

Canonical view as built: **80,868 fixtures**, 2019-02-15..2026-09-22, 3 quarantined.
