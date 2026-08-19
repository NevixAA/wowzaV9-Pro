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
        elif age > max_h:
            a.add("wiring", path, sev,
                  f"last written {age:.1f}h ago per {src} (limit {max_h}h) — exists but is NOT "
                  f"advancing{fwd}", round(age, 1), why)
        else:
            a.add("wiring", path, PASS,
                  f"{len(df):,} rows, written {age:.1f}h ago per {src}{fwd}",
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


def run(days: int = 7, json_path: str | None = None, strict: bool = False) -> int:
    now = pd.Timestamp.now(tz="UTC")
    a = Audit()
    try:
        sha = v9.v9_head_sha()
    except Exception:
        sha = "unknown"
    print(f"[audit] {now:%Y-%m-%d %H:%M UTC}  window={days}d  v9={sha}")
    print(f"[audit] V9_LOCAL={cfg.V9_LOCAL}  exists={cfg.V9_LOCAL.exists()}\n")
    for fn in (audit_wiring, audit_odds_curve, audit_tips, audit_collection):
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
