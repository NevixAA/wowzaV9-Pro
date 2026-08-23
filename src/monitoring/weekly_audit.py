"""
Weekly data audit — is the whole chain actually wired, and is it PERSISTING?
===========================================================================
    python -m src.monitoring.weekly_audit [--days 7] [--json path] [--strict]

Runs from Pro and reads v9 READ-ONLY, so it can audit live production without touching a frozen
repo.

WHY THIS EXISTS. Every incident in this project's history had the same shape: **green workflows,
no data.** Not one was a crash.

  * `git add -f a b missing` aborts and stages NOTHING -> player_props silent for three days
  * `git pull --rebase -X ours` discards the pushing run's OWN rows -> predict captured 3,480
    quotes from 17 bookmakers and threw them away, exit code 0
  * `odds_history_v9.json` gitignored -> `drift_signal` was "New" on 100% of rows FOREVER, so the
    tier upgrade/downgrade never fired once
  * `COLLECT_SEASONS` frozen at "2025" -> six weeks uncollected while the daily job reported
    success every day
  * `*.csv text eol=lf` -> every push failed on a renormalisation diff, models all fine

So this audit deliberately does NOT check "does the file exist" or "did the job succeed". It
checks whether each artifact has MOVED, because a stale file and a working pipeline look
identical from the outside.

THE ASYMMETRY THAT SETS THE SEVERITIES. Odds snapshots cannot be recovered. API-Football's
`/odds` endpoint is pre-match only — verified 2026-08-19 across every season 2019-2025, both
Bet365 and unfiltered: zero rows for finished fixtures. A day of closing prices not captured is
gone permanently, and CLV is the measurement that decides whether any of this is real. Missing
odds capture is therefore FAIL, while a thin tip week is only INFO — no tips is a legitimate
model opinion, no odds is data loss.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import v9_source as v9

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
_RANK = {PASS: 0, INFO: 0, WARN: 1, FAIL: 2}


@dataclass
class Check:
    area: str
    name: str
    status: str
    detail: str
    value: object = None
    why: str = ""


@dataclass
class Audit:
    checks: list[Check] = field(default_factory=list)

    def add(self, area, name, status, detail, value=None, why=""):
        self.checks.append(Check(area, name, status, detail, value, why))

    @property
    def worst(self) -> str:
        return max((c.status for c in self.checks), key=lambda s: _RANK[s], default=PASS)

    def counts(self) -> dict[str, int]:
        out = {PASS: 0, INFO: 0, WARN: 0, FAIL: 0}
        for c in self.checks:
            out[c.status] += 1
        return out


def _read(path: str) -> pd.DataFrame:
    try:
        return v9.fetch_csv(path, required=False)
    except Exception:
        return pd.DataFrame()


def _dt(s, utc=True):
    return pd.to_datetime(s, errors="coerce", utc=utc)


def _newest(df: pd.DataFrame, cols: list[str]):
    """Newest parseable timestamp across the first column that exists."""
    for c in cols:
        if c in df.columns:
            t = _dt(df[c])
            if t.notna().any():
                return t.max()
    return None


def _age_h(ts, now) -> float | None:
    if ts is None or pd.isna(ts):
        return None
    return (now - ts).total_seconds() / 3600.0


# Columns that record when a row was WRITTEN, as opposed to when the match is played. Only these
# can prove an artifact is advancing.
#
# The distinction is not pedantic — it was a bug in the first version of this file. Using
# kickoff_utc, bets.csv reported "newest -105.8h old": the newest row was in the FUTURE, so the
# `age > limit` test could never fire and the check passed unconditionally. A board written a month
# ago and listing fixtures two months out would have looked perfectly fresh. Fixture dates say what
# the file is ABOUT; write timestamps say when it last changed.
_WRITE_COLS = ("generated_at", "snapshot_ts", "added_at", "signal_date", "captured_at",
               "ingested_at", "observed_at")


def _write_age_h(df: pd.DataFrame, path: str, now) -> tuple[float | None, str]:
    """Hours since this artifact was last written, and how we know."""
    for c in _WRITE_COLS:
        if c in df.columns:
            t = _dt(df[c])
            if t.notna().any():
                return _age_h(t.max(), now), c
    # No write column: fall back to filesystem mtime, which is real evidence for a local checkout
    # and simply unavailable over HTTP.
    p = cfg.V9_LOCAL / path
    if p.exists():
        ts = pd.Timestamp(p.stat().st_mtime, unit="s", tz="UTC")
        return _age_h(ts, now), "file mtime"
    return None, "none"


# Artifacts whose producer only runs during part of the day. Without this the check cries wolf
# every morning: predict's cron is `1-59/5 8-23`, so NOTHING is scheduled between 00:00 and 07:59
# UTC and predictions.csv is legitimately ~8h old at 07:50. A fixed 6h limit FAILED on that, which
# is a false alarm on a healthy pipeline — and a check that fails predictably every day is a check
# people learn to ignore.
#
# (path -> first active UTC hour, last active UTC hour inclusive)
_ACTIVE_HOURS = {
    "output/predictions.csv": (8, 23),
}


def _idle_hours_in_span(age_h: float, now, start: int, end: int) -> float:
    """Hours inside the last `age_h` that were OUTSIDE the producer's active window.

    Sampled in 10-minute steps rather than solved arithmetically: the closed form has to special-
    case spans shorter than an hour, spans crossing midnight, and spans covering several whole
    days, and each of those is a place to get it silently wrong. 144 cheap comparisons per day of
    age is not worth optimising.
    """
    steps = max(1, int(age_h * 6))
    idle = sum(1 for i in range(steps)
               if not (start <= (now - pd.Timedelta(minutes=10 * (i + 1))).hour <= end))
    return idle / 6.0


def _allowed_age_h(path: str, base_limit: float, now, age_h: float | None = None) -> tuple[float, str]:
    """Freshness limit, widened by the idle time actually CONTAINED IN THE GAP.

    The first version keyed off the hour it happened to be called at: inside the window it
    returned the base limit, outside it added the hours since the window closed. That is wrong at
    the boundary and it FAILED at 08:01 UTC on a completely healthy pipeline — predict's window
    had been open for one minute, its last legitimate commit was 00:00 (the previous window's
    close), so the measured age was 8.0h against a limit that had just snapped back to 6h. The
    check then self-healed a few minutes later when the 08:01 run committed, which is the worst
    possible behaviour: a daily red flash that always clears by the time anyone looks.

    Counting the idle hours WITHIN the gap has no boundary case. Only active time counts against
    the limit, so an overnight gap is free whenever it is measured, and a real stall inside the
    window still accumulates active hours and still fails.
    """
    win = _ACTIVE_HOURS.get(path)
    if not win or age_h is None:
        return base_limit, ""
    start, end = win
    idle = _idle_hours_in_span(age_h, now, start, end)
    if idle < 0.2:
        return base_limit, f"active window {start:02d}-{end:02d}h, no idle time in gap"
    return base_limit + idle, (f"active window {start:02d}-{end:02d}h; {idle:.1f}h of the "
                               f"{age_h:.1f}h gap was outside it")


# ── A. wiring: has each artifact MOVED recently ──────────────────────────────
def audit_wiring(a: Audit, now, days: int) -> None:
    # (path, max write age in hours, severity when stale, why it matters)
    specs = [
        ("output/predictions.csv", 6, FAIL,
         "predict is the entry point; stale means no board is being produced"),
        ("output/bets.csv", 24 * 4, WARN,
         "the staked board. thin weeks are legitimate, so only WARN"),
        ("output/player_tips.csv", 24 * 3, WARN,
         "props are paper-only, so staleness is not money — but it is a broken collector"),
        ("output/side_bets_ledger.csv", 24 * 7, WARN,
         "side markets carry most staked tips right now"),
        ("output/bets_ledger.csv", 24 * 7, WARN,
         "the durable tip record; grading and CLV hang off it"),
    ]
    for path, max_h, sev, why in specs:
        df = _read(path)
        if df.empty:
            a.add("wiring", path, FAIL, "missing or empty", 0, why)
            continue
        age, src = _write_age_h(df, path, now)
        max_h_eff, sched = _allowed_age_h(path, max_h, now, age)
        # Does the board still look forward? Reported alongside, never as proof of freshness.
        fwd = ""
        for c in ("kickoff_utc", "match_date", "date"):
            if c in df.columns:
                t = _dt(df[c])
                if t.notna().any():
                    n_future = int((t > now).sum())
                    fwd = f"; {n_future} future-dated row(s)"
                    break
        if age is None:
            a.add("wiring", path, WARN,
                  f"{len(df):,} rows but nothing proves when it was written "
                  f"(no {list(_WRITE_COLS)[:3]}..., no local file){fwd}", len(df), why)
        elif age > max_h_eff:
            a.add("wiring", path, sev,
                  f"last written {age:.1f}h ago per {src} (limit {max_h_eff:.0f}h"
                  + (f", {sched}" if sched else "") + f") — exists but is NOT advancing{fwd}",
                  round(age, 1), why)
        else:
            a.add("wiring", path, PASS,
                  f"{len(df):,} rows, written {age:.1f}h ago per {src}"
                  + (f" [{sched}]" if sched else "") + fwd,
                  round(age, 1), why)


# ── B. moving -> closing: the data that cannot be recovered ──────────────────
def audit_odds_curve(a: Audit, now, days: int) -> None:
    cutoff = now - pd.Timedelta(days=days)
    specs = [
        ("output/standard_sidemarket_odds_history.csv", "snapshot_ts",
         ["match_date", "match", "market"]),
        ("output/newformat_odds_history.csv", "snapshot_ts", ["match_date", "match", "market"]),
        ("output/book_odds_snapshots.csv", "snapshot_ts", ["match", "market", "bookmaker"]),
    ]
    for path, tcol, keys in specs:
        df = _read(path)
        if df.empty:
            a.add("odds_curve", path, FAIL, "missing or empty — closing prices are being LOST "
                  "and cannot be backfilled", 0,
                  "API-Football /odds is pre-match only; unrecoverable")
            continue
        if tcol not in df.columns:
            a.add("odds_curve", path, FAIL, f"no {tcol} column", 0, "schema drift")
            continue
        t = _dt(df[tcol])
        recent = df[t >= cutoff]
        n_snap = t[t >= cutoff].dt.floor("min").nunique()
        if recent.empty:
            age = _age_h(t.max(), now)
            a.add("odds_curve", path, FAIL,
                  f"NOTHING captured in {days}d (newest {age:.0f}h old). Unrecoverable loss.",
                  0, "closing curve gap")
            continue
        have = [k for k in keys if k in recent.columns]
        per = recent.groupby(have).size() if have else pd.Series(dtype=int)
        mean_pts = float(per.mean()) if len(per) else 0.0
        # >1 point per fixture-market is the difference between a curve and an entry price
        st = PASS if mean_pts > 1.5 else (WARN if mean_pts > 1.0 else FAIL)
        a.add("odds_curve", path, st,
              f"{len(recent):,} rows / {n_snap} distinct snapshot minutes in {days}d; "
              f"{mean_pts:.2f} points per fixture-market",
              round(mean_pts, 2),
              "1.0 means an ENTRY PRICE, not a curve — CLV needs several points per fixture")

    # near-kickoff coverage: where the closing line actually forms
    df = _read("output/standard_sidemarket_odds_history.csv")
    if not df.empty and {"snapshot_ts", "match_date"} <= set(df.columns):
        t = _dt(df["snapshot_ts"])
        md = _dt(df["match_date"], utc=True)
        lead_h = (md - t).dt.total_seconds() / 3600
        recent = lead_h[(t >= now - pd.Timedelta(days=days)) & lead_h.notna()]
        if len(recent):
            near = int((recent.between(-2, 6)).sum())
            st = PASS if near > 0 else WARN
            a.add("odds_curve", "near-kickoff snapshots", st,
                  f"{near} snapshot(s) within 6h of kickoff in {days}d",
                  near, "T-1h/T-30m is where the closing line forms")

    # the drift bug: odds_history_v9.json gitignored made drift_signal 'New' on 100% of rows
    preds = _read("output/predictions.csv")
    if not preds.empty and "drift_signal" in preds.columns:
        vc = preds["drift_signal"].fillna("(blank)").value_counts()
        share_new = vc.get("New", 0) / max(1, len(preds))
        st = FAIL if share_new >= 0.999 else (WARN if share_new > 0.9 else PASS)
        a.add("odds_curve", "drift_signal populated", st,
              f"{share_new:.1%} of rows are 'New' ({vc.to_dict()})", round(share_new, 4),
              "100% 'New' means odds history is not persisting, so tier drift never fires")


# ── C. tips saved AND graded ─────────────────────────────────────────────────
def audit_tips(a: Audit, now, days: int) -> None:
    cutoff = now - pd.Timedelta(days=days)
    led = _read("output/bets_ledger.csv")
    if led.empty:
        a.add("tips", "bets_ledger", FAIL, "missing or empty", 0, "no durable tip record")
        return
    tcol = next((c for c in ("date", "match_date") if c in led.columns), None)
    t = _dt(led[tcol], utc=True) if tcol else None
    week = led[t >= cutoff] if t is not None else led

    tier = next((c for c in ("signal_tier", "tier") if c in led.columns), None)
    if tier:
        staked = week[week[tier].isin(["SNIPER", "MARKSMAN"])]
        # No tips is a legitimate model opinion, never a failure.
        a.add("tips", "staked tips recorded", INFO if staked.empty else PASS,
              f"{len(staked)} SNIPER/MARKSMAN in {days}d "
              f"(all tiers: {week[tier].value_counts().to_dict()})", len(staked),
              "VALUABLE is recorded but NOT staked")

    # grading: settled fixtures must acquire a result, else CLV can never be computed
    res = next((c for c in ("result", "outcome", "status") if c in led.columns), None)
    if res is not None and t is not None:
        past = led[(t < now - pd.Timedelta(hours=6)) & (t >= now - pd.Timedelta(days=days * 3))]
        if len(past):
            filled = past[res].astype(str).str.upper().isin(["WIN", "LOSS", "VOID", "PUSH"]).sum()
            share = filled / len(past)
            st = PASS if share > 0.8 else (WARN if share > 0.4 else FAIL)
            a.add("tips", "settled tips graded", st,
                  f"{filled}/{len(past)} ({share:.0%}) of kicked-off tips have a result",
                  round(share, 3),
                  "ungraded tips cannot produce P&L or CLV")

    clv = next((c for c in led.columns if "clv" in c.lower()), None)
    if clv and t is not None:
        past = led[t < now - pd.Timedelta(hours=6)]
        if len(past):
            have = pd.to_numeric(past[clv], errors="coerce").notna().sum()
            share = have / len(past)
            st = PASS if share > 0.5 else (WARN if share > 0 else FAIL)
            a.add("tips", "CLV recorded", st,
                  f"{have}/{len(past)} ({share:.0%}) settled tips carry {clv}",
                  round(share, 3),
                  "CLV is the gate that certifies a BET; without it everything stays PAPER")


# ── D. collection: training data still advancing ─────────────────────────────
def audit_collection(a: Audit, now, days: int) -> None:
    # The frozen-season class of bug: a collector that runs daily, succeeds, and collects nothing.
    # player_history.parquet lives at the REPO ROOT, not under output/ — the first version of this
    # check looked in output/ and reported "not present", which would have masked exactly the
    # stalled-collector bug it exists to catch.
    for rel, col, max_d in (("player_history.parquet", "date", 10),
                            ("output/af_history.parquet", "date", 14)):
        p = cfg.V9_LOCAL / rel
        if not p.exists():
            a.add("collection", rel, INFO, "not present in this checkout (parquet is not "
                  "fetched over HTTP)", None, "run with V9_LOCAL for this check")
            continue
        try:
            df = pd.read_parquet(p, columns=[col])
        except Exception as e:
            a.add("collection", rel, WARN, f"unreadable: {str(e)[:60]}", None, "")
            continue
        t = _dt(df[col], utc=True)
        age_d = (now - t.max()).total_seconds() / 86400 if t.notna().any() else None
        if age_d is None:
            a.add("collection", rel, WARN, "no parseable dates", None, "")
        else:
            st = PASS if age_d <= max_d else FAIL
            a.add("collection", rel, st,
                  f"newest row {age_d:.1f}d old (limit {max_d}d)", round(age_d, 1),
                  "a season-keyed table that stops advancing while the job reports success "
                  "is the COLLECT_SEASONS failure")

    # Pro's own store should be growing too.
    try:
        from src.data import season_store as store
        s = store.stats()
        empty = [k for k, v in s.items() if v["rows"] == 0]
        a.add("collection", "pro season store", PASS if len(empty) < len(s) else FAIL,
              f"{sum(v['rows'] for v in s.values()):,} rows across "
              f"{len(s) - len(empty)}/{len(s)} tables; empty: {empty}",
              sum(v["rows"] for v in s.values()), "Pro must keep its own record")
    except Exception as e:
        a.add("collection", "pro season store", WARN, f"unreadable: {str(e)[:60]}", None, "")


# ── E. registry: is the machine-readable statement of "what we have" TRUE? ───
def audit_registry(a: Audit, now, days: int) -> None:
    """output/system_registry.json is what any consumer reads to answer "how much data".

    Both checks exist because of the same 2026-08-23 finding: the registry was written only by
    the tail of shadow.py, so it aged four days and understated the store by 49% (market
    snapshots -31%, model snapshots -64%, settlements -45%). Nothing reported it, because every
    number in it was internally consistent and its own `generated_at` was honest. So freshness
    and truthfulness are tested SEPARATELY:

      * FRESHNESS catches "the refresh stopped running" — the file can be perfectly accurate for
        the day it was written and still be useless.
      * RECONCILIATION catches "the refresh ran but wrote the wrong thing", which freshness
        alone cannot see. It re-measures the canonical store and diffs table by table, so the
        assertion does not depend on the registry's own arithmetic.

    Limit is 30h, not 24h: pro_collect runs 2-hourly, so 30h means roughly 15 consecutive
    refreshes were missed and it cannot fire on one skipped run or a slow day.
    """
    try:
        from src.pipelines import registry as reg
    except Exception as e:
        a.add("registry", "module import", WARN, f"unimportable: {str(e)[:60]}", None,
              "cannot audit the registry without it")
        return

    p = cfg.OUTPUT_DIR / "system_registry.json"
    if not p.exists():
        a.add("registry", "system_registry.json", FAIL, "absent", None,
              "consumers asking 'how much data do we have' have no answer at all")
        return

    age = reg.age_hours(p)
    LIMIT = 30.0
    if age is None:
        a.add("registry", "freshness", FAIL, "no parseable generated_at", None,
              "an undateable registry cannot be told from a stale one")
    else:
        st = PASS if age <= LIMIT else FAIL
        a.add("registry", "freshness", st, f"generated {age:.1f}h ago (limit {LIMIT:.0f}h)",
              round(age, 1),
              "pro_collect refreshes it 2-hourly; 30h means the refresh step itself stopped, "
              "which is how the counts drifted 49% unnoticed")

    r = reg.reconcile(p)
    if r.get("error"):
        a.add("registry", "reconciliation", WARN, r["error"], None,
              "cannot verify the registry against the store")
        return
    n = len(r["mismatches"])
    if r["ok"]:
        a.add("registry", "reconciliation", PASS,
              f"all {r['n_tables']} tables match canonical ({r['canonical_total']:,} rows)",
              r["canonical_total"], "")
    else:
        worst = max(r["mismatches"],
                    key=lambda m: abs((m["canonical"] or 0) - (m["registry"] or 0)))
        drift = r["canonical_total"] - r["registry_total"]
        a.add("registry", "reconciliation", FAIL,
              f"{n}/{r['n_tables']} tables disagree; registry {r['registry_total']:,} vs "
              f"canonical {r['canonical_total']:,} ({drift:+,} rows). Worst: "
              f"{worst['table']} {worst['registry']} vs {worst['canonical']:,}",
              drift,
              "a registry that states counts it did not measure is worse than no registry: the "
              "numbers look plausible so a reader has no way to notice they are wrong. Fix with "
              "`python -m src.pipelines.registry`, then find out why the collect step skipped it")

    # A table that has NEVER received a row is a wiring gap, not a volume problem — it is how
    # `data_quality` sat empty without anyone noticing it had no writer at all.
    stated = (reg._read_previous(p).get("season_store") or {})
    empty = sorted(k for k, v in stated.items()
                   if int((v.get("rows") if isinstance(v, dict) else v) or 0) == 0)
    a.add("registry", "populated tables", PASS if not empty else WARN,
          f"{len(stated) - len(empty)}/{len(stated)} tables hold rows"
          + (f"; EMPTY: {', '.join(empty)}" if empty else ""),
          len(empty),
          "an always-empty canonical table usually means nothing writes to it, which no row "
          "count can distinguish from 'nothing happened yet'")


# ── F. config reachability: can each bet league actually be fetched? ─────────
def audit_config(a: Audit, now, days: int) -> None:
    """Every league v9 is willing to BET must have a valid, reachable odds key.

    WHY: on 2026-08-21 three of v9's 29 OddsAPI sport keys were invalid, and one of them was
    `Ligue 2` — an ENABLED league with a per-league SNIPER threshold and a recorded backtest ROI of
    +45.2%. `soccer_france_ligue_2` returns HTTP 404 while the real key is
    `soccer_france_ligue_two`. It had been wrong since the repo's first commit, so Ligue 2 had never
    produced a live tip in three months.

    The reason it hid so long is the failure mode: a wrong key 404s inside a try/except, so the
    league simply reports no fixtures. "This competition is quiet today" and "this competition is
    unreachable forever" look identical from the outside — exactly the green-workflow-no-data shape
    everything else in this audit is built to catch.

    Two checks, and the first needs no API key at all:
      1. every ENABLED league has a sport key  (catches Romanian Superliga, enabled with none)
      2. every configured key exists in OddsAPI's catalogue  (catches the 404 typos)
    """
    v9 = cfg.V9_LOCAL
    cfgpy = v9 / "config.py"
    if not cfgpy.exists():
        a.add("config", "v9 config", INFO, "v9 checkout not available", None, "")
        return
    # IMPORT v9's config rather than regexing it. A text parse over-matched on the first
    # attempt — it reported 27 ENABLED_LEAGUES where the module defines 20, because a
    # non-greedy block match can run past the closing bracket. It still found the right
    # answer, but a check that miscounts its own denominator cannot be trusted to be
    # complete, and an over-match could just as easily invent a missing key.
    keys: dict = {}
    enabled: list = []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_v9cfg", cfgpy)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(v9))          # config imports siblings
        spec.loader.exec_module(mod)
        keys = dict(getattr(mod, "ODDS_API_SPORT_KEYS", {}) or {})
        enabled = list(getattr(mod, "ENABLED_LEAGUES", []) or [])
        how = "imported v9 config"
    except Exception as e:
        # Fall back to a TIGHT regex, and say so — silently degrading to a weaker method is how
        # a check starts passing for the wrong reason.
        import re
        src = cfgpy.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^ODDS_API_SPORT_KEYS\s*:?\s*dict?\s*=\s*\{(.*?)^\}",
                      src, re.S | re.M)
        keys = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1))) if m else {}
        m2 = re.search(r"^ENABLED_LEAGUES\s*:?\s*\w*\s*=\s*[\[\{](.*?)^[\]\}]",
                       src, re.S | re.M)
        enabled = re.findall(r'"([^"]+)"', m2.group(1)) if m2 else []
        how = f"regex fallback ({type(e).__name__})"

    if not keys or not enabled:
        a.add("config", "parse v9 config", WARN,
              f"could not parse (keys={len(keys)}, enabled={len(enabled)})", None,
              "a silent parse failure would make these checks vacuously pass")
        return

    # An enabled league with no sport key is TWO different things needing opposite responses:
    #
    #   CONFIG_BROKEN         we mapped it wrong or forgot. A BUG -> FAIL.
    #   PROVIDER_UNSUPPORTED  the provider does not sell this competition -> INFO, nothing to fix.
    #
    # Both look identical from outside: the league returns zero fixtures forever. That is exactly
    # how Ligue 2 stayed dark for three months on an invalid key. Conflating them means either
    # crying wolf every week or staying silent on a real bug, so v9 now DECLARES the unsupported
    # set (config.PROVIDER_UNSUPPORTED) with the evidence, and anything missing but NOT declared is
    # a genuine config break.
    declared: dict = {}
    try:
        declared = dict(getattr(mod, "PROVIDER_UNSUPPORTED", {}) or {})
    except Exception:
        declared = {}
    def _reason(l: str) -> str:
        v = declared.get(l)
        return str(v.get("reason", "?")) if isinstance(v, dict) else str(v or "?")

    def _verified(l: str) -> str:
        v = declared.get(l)
        return str(v.get("verified", "?")) if isinstance(v, dict) else "?"

    missing = [l for l in enabled if l not in keys]
    unsupported = [l for l in missing if l in declared]
    broken = [l for l in missing if l not in declared]
    unsup_txt = ", ".join(f"{l}={_reason(l)}" for l in unsupported) or "none"
    a.add("config", "enabled leagues: sport-key coverage",
          PASS if not broken else FAIL,
          f"{len(enabled)} enabled, {len(keys)} keys ({how}); "
          f"CONFIG_BROKEN: {broken or 'none'}; PROVIDER_UNSUPPORTED: {unsup_txt}",
          len(broken),
          "CONFIG_BROKEN means a league we intend to bet can never reach the board. "
          "PROVIDER_UNSUPPORTED is declared and expected, not a defect")
    if unsupported:
        detail = "; ".join(f"{l} -> {_reason(l)} (verified {_verified(l)})" for l in unsupported)
        a.add("config", "provider-unsupported leagues (declared)", INFO,
              f"{len(unsupported)} league(s) the provider does not carry: {detail}",
              len(unsupported),
              "recorded so an unsupported league never looks like a healthy league with zero "
              "fixtures")

    import os
    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        a.add("config", "sport keys valid against OddsAPI", INFO,
              f"skipped — no ODDS_API_KEY in this environment ({len(keys)} keys unverified)",
              None, "set ODDS_API_KEY to enable; /sports is free and does not consume quota")
        return
    try:
        import requests
        r = requests.get("https://api.the-odds-api.com/v4/sports",
                         params={"apiKey": api_key, "all": "true"}, timeout=30)
        if r.status_code != 200:
            a.add("config", "sport keys valid against OddsAPI", WARN,
                  f"catalogue fetch returned HTTP {r.status_code}", None, "")
            return
        have = {s["key"] for s in r.json()}
    except Exception as e:
        a.add("config", "sport keys valid against OddsAPI", WARN,
              f"catalogue unreachable: {str(e)[:60]}", None, "")
        return
    bad = {l: k for l, k in keys.items() if k not in have}
    bad_enabled = {l: k for l, k in bad.items() if l in enabled}
    a.add("config", "sport keys valid against OddsAPI",
          FAIL if bad_enabled else (WARN if bad else PASS),
          f"{len(keys)} keys checked; invalid: {bad or 'none'}"
          + (f"; OF THOSE ENABLED FOR BETTING: {bad_enabled}" if bad_enabled else ""),
          len(bad),
          "an invalid key 404s inside a try/except, so the league reports no fixtures and looks "
          "quiet rather than broken — this is how Ligue 2 stayed dark for three months")


def run(days: int = 7, json_path: str | None = None, strict: bool = False) -> int:
    now = pd.Timestamp.now(tz="UTC")
    a = Audit()
    try:
        sha = v9.v9_head_sha()
    except Exception:
        sha = "unknown"
    print(f"[audit] {now:%Y-%m-%d %H:%M UTC}  window={days}d  v9={sha}")
    print(f"[audit] V9_LOCAL={cfg.V9_LOCAL}  exists={cfg.V9_LOCAL.exists()}\n")
    for fn in (audit_wiring, audit_odds_curve, audit_tips, audit_collection,
               audit_registry, audit_config):
        try:
            fn(a, now, days)
        except Exception as e:
            a.add(fn.__name__, "audit itself failed", WARN, f"{type(e).__name__}: {e}", None,
                  "a broken check must not look like a passing one")

    area = None
    for c in a.checks:
        if c.area != area:
            area = c.area
            print(f"\n== {area} ==")
        print(f"  [{c.status:4}] {c.name}")
        print(f"         {c.detail}")
        if c.status in (WARN, FAIL) and c.why:
            print(f"         WHY: {c.why}")

    counts = a.counts()
    print(f"\n[audit] {counts}  -> worst={a.worst}")
    if a.worst == FAIL:
        print("[audit] FAIL means an artifact is not advancing. For odds snapshots that is "
              "PERMANENT loss — /odds cannot be backfilled.")

    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_days": days,
           "v9_sha": sha, "worst": a.worst, "counts": counts,
           "checks": [c.__dict__ for c in a.checks]}
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[audit] written -> {json_path}")
    # Default is to report, not to break CI. --strict makes FAIL exit non-zero.
    return 1 if (strict and a.worst == FAIL) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", default=str(cfg.OUTPUT_DIR / "weekly_audit.json"))
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when any check FAILs")
    args = ap.parse_args()
    return run(days=args.days, json_path=args.json, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
