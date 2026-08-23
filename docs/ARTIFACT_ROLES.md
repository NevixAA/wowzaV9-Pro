# The four monitoring artifacts, and why each exists separately

Pro writes four JSON artifacts that all look like "health output". They are **not**
interchangeable, and the reason they are separate is that each answers a question the others
cannot. Collapsing any two would lose a real distinction — every one of these was created after a
failure that the existing artifacts could not have caught.

| artifact | question | grain | cadence | severity |
|---|---|---|---|---|
| `system_registry.json` | *What data do we have?* | one entry per canonical table | every collect | none — it states, it does not judge |
| `weekly_audit.json` | *Is the chain wired and PERSISTING?* | one row per check | weekly | PASS / INFO / WARN / FAIL |
| `snapshot_coverage.json` | *Are we capturing the CLOSE?* | one entry per snapshot source | with the audit | feeds the audit |
| `data_quality` (canonical table) | *Which stored rows are trustworthy?* | one row per (table, flag) finding | on demand | PASS / WARN / FAIL, append-only |

---

## `system_registry.json` — what we have

The single machine-readable answer to "how much data is there". Regenerated from the canonical
store on every successful collect; **counts are always measured, never carried forward**.

It makes no judgements. A table with zero rows is stated as zero rows, not flagged. That is
deliberate: the moment a registry starts deciding what is acceptable it becomes a monitor with an
opinion, and two artifacts then disagree about the same table with no way to tell which is stale.

**Why it cannot be merged into the audit.** The audit runs weekly; the registry must be current
after every collect, because it is what a human or a script reads to answer "is the data there".
It froze for four days once and understated the store by 49% (`market_snapshots` −31%,
`model_snapshots` −64%, `settlements` −45%) while every number in it looked plausible.

## `weekly_audit.json` — is it moving

Checks whether each artifact has **MOVED**, not whether it exists. Every incident in this
project's history had the same shape: green workflows, no data. Not one was a crash.

Severity follows **recoverability**, which is the load-bearing idea:

- a missing odds snapshot is **FAIL** — `/odds` is pre-match only, so the loss is permanent
- a thin tip week is **INFO** — no tips is a legitimate model opinion

**Why it cannot be merged into the registry.** "The table has 74,740 rows" and "that table
stopped advancing 30 hours ago" are different facts, and only the second is actionable. A count
cannot express the second without a previous count to compare against, which is precisely what
the registry deliberately does not keep.

## `snapshot_coverage.json` — are we capturing the close

Density per fixture-market and coverage of T-6h / T-3h / T-1h / T-30m / T-10m.

A file can advance every hour and still never hold a price inside the final ten minutes. Since
CLV is measured against the close and the close cannot be backfilled, that gap is invisible to
every freshness check yet fatal to the only measurement that decides whether any of this is real.
Current standing finding: the main market reaches T-1h on 71.4% of fixture-markets while side
markets reach T-10m on **0.8%**.

Measured **only over fixtures whose kickoff has passed.** For an upcoming match the T-10m bucket
has not *arrived*, so counting it as uncovered measures the calendar rather than our collection —
a confound that once produced a confident and entirely false "99% of fixtures are never sampled
inside T-1h".

**Why it cannot be merged into the audit.** The audit reduces to a status; this needs the full
per-bucket distribution to be useful, and burying a 7-row table inside a check's `detail` string
makes it unreadable.

## `data_quality` — which rows to trust

The only one of the four that is a **canonical table** rather than a JSON file, and the only one
that is **append-only**.

One row per (table, flag) finding, carrying counts, the affected date span, and sample keys so a
finding is investigable rather than merely a number. The grain is the finding, not the flagged
row — the latter would make it larger than the tables it describes (33,447 flagged movement
observations alone).

**Why append-only, and why not a JSON.** A single scan says what is wrong now; the *series* says
whether it is getting worse. A quality metric whose history is overwritten cannot show a slow
decline, which is the failure mode every incident here has had. It held **0 rows from the day the
store was created** until 2026-08-23, because nothing wrote to it — and a row count alone could
never distinguish "nothing writes here" from "nothing is wrong", which is why the audit now names
that distinction explicitly.

---

## Reading them together

```
system_registry.json     how much
weekly_audit.json        still moving?
snapshot_coverage.json   will CLV be measurable?
data_quality             which rows survive which level
```

Quality levels are defined once, in `src/quality.py`: **RAW** (everything, the only level that
can measure contamination), **CLEAN** (excludes rows whose value is wrong), **STRICT_CLEAN**
(also excludes rows whose quality could not be verified). `at_level` requires the level as an
argument rather than defaulting, because "we checked and it was fine" and "we could not check"
are different statements and neither is a safe default.

## The contract they all depend on

`src/contract.py` declares what Pro and v11 require from frozen v9: path, consumers, required
columns, freshness, **grain**, and the caveat a new consumer would otherwise learn by being
wrong. Verified by `audit_contract`. It caught two of my own mis-declarations on its first run —
a `match` column that does not exist on `predictions.csv`, and a `player_props_predictions.csv`
that is really `player_tips.csv`.
