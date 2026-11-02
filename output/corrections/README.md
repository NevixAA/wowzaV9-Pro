# Corrections beside the record (Data Truth round 3, 2026-11-02)

Owner rule: a committed record is never rewritten. A correction is a new column or a sidecar file,
with an audit note, and the original values stay where they are.

## bet_builder_record_audit_2026-11-02.csv

Rows of `output/bet_builder_settled.csv` (27,942 at origin/data-truth-100 4410959d) that the
headline must not count. `combo_result` and `joint_probability` are unchanged in the record; from
the next settle pass the record itself carries the same columns (`src/combo/record_audit.py`).

| flag | rows | why |
|---|---|---|
| `model_validity = INVALID_MODEL` | 8,370 (1,480 WON, 2,665 LOST, 4,225 UNKNOWN) | a HOME / AWAY / 1X / X2 / HOME_O05 / AWAY_O05 / HOME_O15 / AWAY_O15 leg read off `score_model.fit`, whose four targets are symmetric in the home and away rates. The split was the optimiser seed, not data. |
| `scoreboard_result = EXCLUDED_VOID_LEG` | 5,144 decided (2,659 of them WON) | a player leg voided and the combo was settled on the remaining legs; its claimed joint covers every leg. Same rule as `tip_scoreboard`. |
| `frechet_violation = True` | 116 | the recorded joint is above the smaller leg (or below p_a + p_b - 1), which is impossible. |

`performance()` on the record:

| | settled | won | hit rate | P/L at fair odds |
|---|---|---|---|---|
| before (counted every WON/LOST) | 17,644 | 5,057 | 28.66% | +46,659.97u |
| after (`scoreboard_result`) | 8,279 | 883 | 10.67% | +99.54u |

The P/L is at Pro's own fair price (no bookmaker builder price exists), so it is not a betting result.

Sent combos (`tip_scoreboard`): 12 of the 324 sent combos found in the record are INVALID_MODEL.
The headline moves from 125 settled / 6 won / z = -0.97 to 120 settled / 6 won / z = -0.73.
The 5 removed decided combos all lost. After the fixture_key v2 re-key, `tip_scoreboard`
matched 0 of 342 sent ids. It now also matches `old_combo_id`.
