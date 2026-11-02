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

## clean_clv_pct (src/market/clv_schema.py)

`clean_clv_pct` is now non-NULL only where `clv_quality = OK`. Rows of the committed
`output/clv_enriched.csv` (220,317) that lose their clean value: 54,246 CLOSE_EQUALS_ENTRY (all
at 0.0) and 39,643 CLOSE_NOT_PROVEN_PRE_KICKOFF (closes recovered by player and market name only).
`clv_pct` (raw) is unchanged on every row.

| | rows with clean_clv_pct | mean |
|---|---|---|
| before | 184,416 | +0.0061% |
| after | 90,527 | -0.6387% |

The weekly audit now FAILS when any non-OK row carries a clean value. Its coverage line moves
from 83.7% (PASS) to 41.1% (WARN).

v9's first-half-contaminated list (`output/corrections/clv_first_half_contaminated.csv`) currently
exists only on the v9 branch `fix4/sharp_clv`. It lists bets_ledger O/U rows, while Pro's `clv`
table holds player props, so 0 Pro clv rows match it. Imported settlements rows that match it get
the `CLV_FIRST_HALF_CONTAMINATED` quality flag.

## Snapshot observation time (src/data/observation_time.py)

`observed_at` was the time Pro ingested the row on every stored row: 401,270 market_snapshots and
381,972 book_odds_snapshots. Stored rows are not rewritten. New imports carry the provider stamp
(v9 `snapshot_ts`, or the board's `generated_at`) as `observed_at`, plus `observed_at_source`.
Date-only stamps (T00:00:00) are never used as times. `scheduler._near_kickoff` now places rows by
provider time only. It reads `snapshot_ts` / `captured_at` on old rows and reports the
ingest-only rows apart.

| kicked-off fixtures: 1,930 | T-6h | T-3h | T-1h | T-30m | T-10m |
|---|---|---|---|---|---|
| market_snapshots, before (ingest time) | 93.4% | 70.4% | 29.1% | 14.9% | 6.2% |
| market_snapshots, after (provider time; 268,972 ingest-only rows excluded) | 86.2% | 72.0% | 38.4% | 23.3% | 10.0% |
| book_odds_snapshots, before | 60.1% | 42.2% | 15.6% | 8.4% | 3.4% |
| book_odds_snapshots, after | 90.0% | 78.4% | 36.3% | 23.7% | 11.0% |

## Consensus de-vig gate (src/market/devig.fair_prob)

The study consensus panels (`studies/common.book_panel`, btts_contradiction, monthly_learning)
used the ungated power de-vig. Placeholder exchange pairs (1.01/1.01) and margins above 25% now
return no probability. Of 44,143 last-pre-kickoff two-sided book pairs in book_odds_snapshots,
12 are rejected (all Matchbook). Ten fixture-market consensus values move, by at most 1.59pp
(BTTS). v11's momentum restatement belongs to v11.

## valuable_all_fixture_close_audit_2026-11-02.csv

`experiments/valuable_2026_10/all_fixture_settled.parquet` (committed) labels 19 rows
VALID_PRE_KICKOFF_CLOSE whose close was taken after that row's kickoff. Five more fail when a
close is compared with the earliest kickoff any snapshot recorded for the fixture. The sidecar
lists all 24 with `corrected_close_status = CLOSE_NOT_PROVEN_PRE_KICKOFF`. The parquet is unchanged.
VALID closes go from 2,847 (mean CLV +0.1456%) to 2,823 (+0.1478%).
`edge_reassessment.all_fixture` and `valuable.snapshots` now apply the earliest-kickoff rule.
`snapshots` also drops snapshots with no kickoff and writes the tracked
`prematch_snapshots_manifest.json`: the parquet's SHA-256, row count and every v9 commit read.

## Round 5 (2026-11-02): read-time corrections, no stored row rewritten

**v9 first-half-contaminated CLV list in every CLV reader.** v9's
`output/corrections/clv_first_half_contaminated.csv` (170 rows, on v9 data-truth-100) is now applied
through `v9_corrections.quarantine_first_half_clv` in every Pro reader of bets_ledger `clv_pct`
(bankroll.data, analytics.core, pipelines.monthly_eval, studies.evidence, studies.monthly_learning,
studies.valuable.deep_dive, and through it edge_reassessment) and in the settlements CLV readers
(validation.threshold_curves, pipelines.shadow). Listed rows get `clv_pct` and `closing_odds` = NaN
plus `clv_quarantine = CLV_FIRST_HALF_CONTAMINATED`; v9's ledger and Pro's stored settlements are
unchanged. At v9 origin/data-truth-100: 170 of 1,833 bets_ledger rows match (all live; a plain merge
gives the same 170). Raw ledger CLV: 1,475 rows, mean +5.6516% becomes 1,305 rows, mean +0.1149%
(median 0.00% both). monthly_eval's |clv| <= 25 view does not move (1,294 rows, +0.0309%), because
every listed row has |clv_pct| >= 50.85.

**Bet Builder rescheduled matches.** When the fixture_key finds no scoreline, settle now searches
the same canonical league and resolved clubs on the match date, then +-1..3 days. After that the
48h rule applies to kickoff times. Offline re-settle of the 10,298 UNKNOWN rows in
bet_builder_settled.csv against the local store found 3 moved fixtures (21-25h later): Columbus v New
England, Valerenga v Molde, Viking v Aalesund. They hold 108 combos (49 WON, 59 LOST), which are now
`OK:RESOLVER_DAY+1`. Vicenza v Catanzaro (12 combos) was found a day later, but its combos carry no
kickoff, so they stay UNKNOWN as `RESCHEDULE_KICKOFF_UNKNOWN`. The record changes only on the next
CI settle pass.

**Empty Bet Builder build.** A generate run that builds nothing now writes a header-only
`bet_builder_candidates.csv` and `bet_builder_candidates_meta.json` (generated_at, rows). The
current file (917 rows, generated 2026-11-01T16:01:55Z) is replaced on the next generate run.
