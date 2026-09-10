# GitHub Actions scheduling reliability — measurement record

**Measured 2026-09-10.** This is the raw measurement, kept separately from any analysis of it,
because the numbers were produced in a cloud session whose transcript is not durable and several
of them overturn earlier assumptions in this estate.

Scope: `NevixAA/wowza-betting` (v9) and `NevixAA/wowzaV9-Pro` (Pro), via the GitHub REST API
(`list_workflow_runs`, `list_workflow_jobs`, job logs). Read-only throughout; nothing was
changed, committed, or dispatched to produce it.

Two independent passes went into this document:

* **Pass A** — 1,367 scheduled runs across seven workflows, covering roughly 2026-08-16 to
  2026-09-10. Delay, delivery rate, duration, minute drift, and NEAR/WIDE verification.
* **Pass B** — the once-daily workflows specifically, from commit timestamps plus each
  workflow's own `timeout-minutes`. This pass found something Pass A's aggregates had hidden.

> **A methodology bug was caught and corrected mid-measurement in Pass A.** Two parallel API
> calls had their results cross-routed: `std_odds_capture` page 2 came back carrying
> `nf_odds_capture` data and vice versa. Every row was rebuilt by trusting each run's own `path`
> field rather than the request believed to have fetched it. The tables below are from the
> rebuilt data. The uncorrected version would have attributed each capture workflow's behaviour
> to the other — worth remembering, because both went on being individually plausible.

---

## Pass A, Measure 1 — delay and duration, in minutes

`queue wait` = `started_at − created_at` (runner availability).
`schedule delay` = `created_at −` nearest prior cron slot (the dispatcher's own lateness).
Format is median / p90 / p95 / max.

| Workflow | n | queue wait | schedule delay | duration |
|---|---:|---|---|---|
| `predict` | 367 | 0 / 0 / 0 / 0 | 10.5 / 26.4 / 29.1 / 52.7 | 2.5 / 3.1 / 3.6 / 19.2 |
| `std_odds_capture` | 200 | 0 / 0 / 0 / 0 | 17.9 / 49.3 / 88.2 / 177.7 | 1.6 / 22.9 / 36.0 / 38.3 |
| `nf_odds_capture` | 300 | 0 / 0 / 0 / 0 | 16.5 / 89.1 / 156.6 / 224.2 | 21.0 / 23.0 / 36.0 / 41.2 |
| `live_scanner` | 100 | 0 / 0 / 0 / 0 | 41.2 / 92.3 / 111.7 / 371.5 | 0.9 / 1.1 / 1.3 / 3.5 |
| `player_props` | 100 | 0 / 0 / 0 / 0 | 90.2 / 273.6 / 310.0 / 326.5 | 11.6 / 15.6 / 23.6 / 120.3 |
| `update_results` | 100 | 0 / 0 / 0 / 0 | 40.5 / 113.9 / 118.0 / 308.0 | 2.0 / 2.5 / 2.6 / 3.3 |
| `pro_collect` | 200 | 0 / 0 / 0 / 0 | 29.9 / 90.4 / 110.5 / 118.9 | 0.6 / 0.9 / 1.0 / 3.4 |

**Queue wait is exactly zero at every percentile of every workflow, including max.** Runner
availability has never once been the constraint. Whenever a run is late, it is late because
GitHub *created the event* late — not because our job waited for a machine. Any future
explanation of a missed capture that appeals to runner contention is ruled out by this row.

This also retires an earlier hypothesis of mine that Pro's loop jobs were starving v9's runners.
Cutting the estate from 398 to 233 runs/day on that theory moved predict's delivery from 16% to
15%. The theory was wrong; the cut happened to be right for a different reason (below).

## Pass A, Measure 2 — delivery rate falls monotonically with requested frequency

Over the seven full days 2026-09-03 to 2026-09-09:

| requested runs/day | delivered | rate |
|---:|---:|---:|
| ~9 | ~7 | **74%** |
| ~26 | — | 38% |
| ~57 (`predict`, 400 slots) | 53 | **13.2%** |

Asking for more does not merely fail to help — it actively costs you. The estate's own history
confirms the direction: `live_scanner` went from 3.0 to 5.1 delivered runs/day and
`player_props` from 38% to 90% delivery when their *requested* cadence was reduced.

**GitHub drops slots; it does not queue them.** Zero queue wait plus 13% delivery cannot both be
true of a queue. The verdict recorded at the time was `GITHUB_DROPS_RATHER_THAN_DELAYS = MIXED`,
because the dispatcher does both: it drops most high-frequency slots *and* delays what it fires.

## Pass A, Measure 5 — cron minutes do not survive the dispatcher

`predict` is configured on minutes `[9, 24, 39, 54]`. Its observed start-minute distribution is
spread across essentially all 60 minutes of the hour, no minute exceeding ~2.7%.

**Consequence: aligning cron minutes to a target clock time is not a usable control.** This is
the direct reason the 2026-09-02 kickoff-clock realignment could not have worked — 86.5% of
fixtures kick off at :00 or :30, so the crons were moved to :23/:52 to sit just before those,
and coverage on fixtures kicking off after the change *fell* (T-10m 8.7% → 3.2%). The design
assumed a precision the dispatcher does not offer. Only an **in-run adaptive loop that
self-schedules against real kickoff time** can hit a near-kickoff target.

## Pass A, Measure 4 — the NEAR loop is running again

The NEAR branch of both capture workflows was unreachable from 2026-08-29 until the 2026-09-07
fix. Runs longer than 10 minutes are NEAR (WIDE is a single ~1.4-minute pass):

| window | `std_odds_capture` | `nf_odds_capture` |
|---|---|---|
| before 08-29 | 71 of 82 long, max 23.8 min | 163 of 181 long, max 28.0 min |
| 08-29 → 09-07 (bug) | **1 of 89** | **1 of 91** |
| after 09-07 fix | 17 of 29 long, max 38.3 min | 18 of 28 long, max 41.2 min |

`NEAR_LOOP_RUNNING_AFTER_FIX = YES`, confirmed two independent ways: the duration distribution
above, and literal job-log lines (`NEXT_KO_MIN`, kickoff-window extension, `completed 17 passes
over 40m`).

**This resolves an ambiguity that was left open.** The standard capture file showed *zero* rows
less than 10 minutes apart after the fix, which looked like the loop still wasn't running. The
job logs show why it isn't: consecutive NEAR passes log the *same* running total minutes apart,
because the capture script only writes consecutive **distinct** prices. Sparse near-kickoff rows
are the dedup working, not the loop failing. Row spacing is therefore not a valid test of whether
the loop ran, and should not be used as one again.

---

## Pass B — once-daily workflows are delivered, but ~5 hours late

Pass A's aggregates mixed cadences together and hid this. Measured from commit timestamps, with
each workflow's `timeout-minutes` used to bound when it must have *started*:

| workflow | scheduled | observed | timeout | implied delay |
|---|---|---|---:|---|
| `player_history_extend` | 03:40 | ~08:20 | — | +4h40 |
| `injury_refresh` | 04:00 | 07:56 | — | +3h56 |
| `af_history_extend` | 06:00 | ~11:00 | — | +5h00 |
| `fantasy_refresh` | 06:30 | ~11:40 | 20 min | **+5h10** |
| `daily_summary` | 07:00 | ~12:00 | 10 min | **+4h51** |

The last two rows are the load-bearing ones. `daily_summary` is capped at 10 minutes, so a commit
at 12:01 proves the job *started* no earlier than 11:51 against a 07:00 slot. The delay cannot be
job duration. It is the dispatcher.

Observed `daily_summary` send times, 2026-08-27 to 2026-09-10 (UTC): 18:02, 19:12, 05:51, 12:31,
14:43, 12:18, 11:55, 11:54, 11:57, 11:06, 11:29, 13:12, 11:57, 12:07, 12:01. The recent fortnight
is tightly clustered at 11:00–13:12.

**It is not top-of-hour contention.** `fantasy_refresh` sits on minute 30 and is delayed
identically to `daily_summary` on minute 0. Minute choice is not the mechanism.

### The trade-off this establishes

Delivery and punctuality move in opposite directions:

| cadence | delivery | punctuality |
|---|---|---|
| high frequency (~57/day) | **13%** of slots | good when it fires (median +10 min) |
| once daily | **~100%** of slots | **+4 to +5 hours** |

So "ask for less, deliver more" is only half the story, and taken alone it is misleading. A
once-daily workflow will run — just not when you asked. **Neither cadence alone can hit a
wall-clock target.** Anything that must happen inside a specific window needs either several
slots plus an in-run guard, or an in-run adaptive loop.

That is what `daily_summary` now does (v9 `1805d42d`): five early slots at 01/03/05/07/09 UTC
plus a guard that sends on the first fire landing in 05:00–11:00 UTC, with a past-12:00 fallback
so a badly delayed day still gets a digest. It is only safe because the send was already
idempotent per UTC date via `DIGEST|<date>` in `telegram_bot/notified.json`; the four losing
slots no-op. Simulated across the delay range, it lands at 08:00 Israel when GitHub is punctual
and 09:00 when it is 5 hours late.

---

## What this means for design, in order of consequence

1. **Never build anything that depends on a cron firing near its slot.** Not near-kickoff
   capture, not a timed notification, not a live signal. The dispatcher offers neither
   punctuality nor delivery — only one at a time, depending on cadence.
2. **In-run adaptive loops are the only real timing control.** A job that starts whenever and
   then samples against real kickoff time is robust to everything above. This is why the NEAR
   loop matters and why its cadence and sampling design are the levers, not its cron.
3. **Live in-play betting is structurally hard here, and this is the number that decides it.**
   `live_scanner` shows a median schedule delay of 41 minutes and a max of 371. An in-play
   signal delayed 41 minutes is worthless. This needs quantifying as signal-to-execution delay
   before any further live work is justified.
4. **Idempotency is what buys back scheduling reliability.** Because the digest was already
   idempotent per day, five slots could be added at zero risk of duplicate sends. Any future
   time-sensitive job should be made idempotent *first*; that is the precondition for
   over-scheduling it safely.
5. **A green workflow still proves nothing about data landing** — unchanged from before, and this
   measurement was only possible because outputs are committed and therefore auditable after the
   fact.

## Open, not answered here

* **Achievable near-kickoff coverage.** Given jitter of this size, what fraction of fixtures can
  actually receive a T-10m capture, at what credit cost, and would a small always-on worker
  change it? Deliberately left to the snapshot-infrastructure analysis rather than answered here.
* **Whether the ~5h once-daily delay is stable or drifting.** Fifteen days of `daily_summary`
  data suggests it is stable and has been for at least a fortnight, but this is one repo over
  two weeks and the mechanism is not ours to see. The `daily_summary` guard is deliberately
  built to tolerate the delay changing in either direction rather than to assume +5h.
* **Whether `pro_backfill_results` firing hourly is helping.** It has committed nothing since
  2026-08-19 and asks for 24 runs/day, which by Measure 2 is squarely in the penalised band.

## Provenance

Pass A: cloud routine `trig_01CHNeKN2VuTB3jj3rxBcGyf`, run
`cse_01Ks7FzxZapiRpAm1SJwAJBU`, 2026-09-10 09:20–09:31 UTC, 77 turns, read-only.
Verdicts recorded at the time: `GITHUB_DROPS_RATHER_THAN_DELAYS = MIXED`,
`HIGH_FREQUENCY_PENALTY_CONFIRMED = YES`, `NEAR_LOOP_RUNNING_AFTER_FIX = YES`.

Pass B: local, from v9 git history and workflow definitions, 2026-09-10 ~12:40 UTC. It is the
pass that produced the delivery-versus-punctuality trade-off, and it exists only because
`daily_summary`'s observed send times were checked against its own timeout while investigating
why a digest scheduled for the morning was arriving mid-afternoon.

Sample sizes are stated in every table. Where a number is a median of a wide distribution the
p90 and max are given alongside it, because in this data the tails are the operationally
important part.
