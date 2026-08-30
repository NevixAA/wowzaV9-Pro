"""
Bet Builder pipeline — generate combos, notify them, settle them.
=================================================================
    python -m src.pipelines.bet_builder --mode generate   # build today's candidates
    python -m src.pipelines.bet_builder --mode notify     # Telegram the ones worth sending
    python -m src.pipelines.bet_builder --mode settle     # grade the ones that finished
    python -m src.pipelines.bet_builder --mode all

THE GAP THIS CLOSES

The combo engine has been complete for a while -- `match_picture` builds the legs, `notify`
formats and dedups them, `settle` grades them -- and NONE of it was reachable. Pro had four
workflows and not one mentioned combos; nothing outside `src/combo/` imported the package except
the config flag. So `PRO_MAY_NOTIFY = True` was set, the notifier existed, and it was never
invoked by anything. The candidates in git came from a single local run done by hand.

An engine with no entrypoint is not a feature. This is the entrypoint.

WHY IT READS PRO'S OWN WAREHOUSE AND NOT v9 OVER HTTP

`board_digest` reads v9's committed CSVs because it reports on v9's board. This does not: it needs
the model probabilities for FOUR markets at once (O1.5/O2.5/O3.5/BTTS) to fit a score matrix, plus
player props for the same fixture, keyed so they can be joined. That is exactly the shape
`model_snapshots` and `player_props` already have in the season store, with a stable `fixture_key`
on both. Going back out to CSV would mean re-deriving a join that is already done.

It also keeps invariant 4 intact from the other direction: Pro reads Pro, and writes only Pro.

PRE-KICKOFF ONLY

The same rule as v9's predict (invariant 5). A builder on a match already in play would be priced
off a pre-match score matrix that no longer describes the game, and the tier it produced would be
an artefact of stale inputs rather than an edge. Started fixtures are skipped and counted.

SETTLEMENT ACCUMULATES, IT NEVER REWRITES

Each settle pass merges into the existing record on `combo_id` and keeps the older row where a
fixture has already been graded. A combo that once settled WON must not silently become UNKNOWN
because a later run could not find its scoreline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.combo import canonical as cc
from src.combo import match_picture as mp
from src.combo import notify as cn
from src.combo import player_dependency as pdep
from src.combo import score_model as sm
from src.combo import settle as cs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output"
CAND_FILE = OUT / "bet_builder_candidates.csv"
SETTLED_FILE = OUT / "bet_builder_settled.csv"

CALC_VERSION = "1.0.0"

# How far ahead to build. Prop markets are posted late and deepen toward kickoff, so a builder
# generated a week out is mostly goal legs; three days is where the player legs start existing.
DEFAULT_DAYS = 3

# How many combos to keep per (fixture, leg count). See the note at the build call.
CANDIDATES_PER_LEG_COUNT = 12


def _read(table: str) -> pd.DataFrame:
    from src.data import season_store as store
    try:
        return store.read(table)
    except Exception:                                          # noqa: BLE001
        return pd.DataFrame()


def _latest_model_probs(snaps: pd.DataFrame) -> pd.DataFrame:
    """Newest model probability per (fixture, market), wide."""
    if snaps.empty:
        return pd.DataFrame()
    s = snaps.copy()
    if "observed_at" in s.columns:
        s = s.sort_values("observed_at")
    s = s.drop_duplicates(subset=["fixture_key", "market"], keep="last")
    return s.pivot_table(index="fixture_key", columns="market", values="model_prob",
                         aggfunc="last")


def _dependency() -> dict:
    """Measured player x goal-market dependence, or {} if it has not been built yet.

    An empty dict is NOT a failure: `_joint` falls back to a ratio of 1.0, which is plain
    independence. It is worth knowing that happened, so the caller reports it.
    """
    f = OUT / "player_combo_dependency.csv"
    if not f.exists():
        return {}
    try:
        return pdep.joint_lookup(pd.read_csv(f))
    except Exception:                                          # noqa: BLE001
        return {}


def _card_rates() -> pd.DataFrame:
    """Per team-match card totals, for the team-card legs.

    Cards were MISSING ENTIRELY from the first live tips — `build()` takes a `cards=` argument
    and the pipeline never passed one, so "team over 2.5 cards" could not be produced at all,
    however the gates were tuned. It needs OUTCOMES (yellow/red per player-match), which Pro does
    not hold: `player_props` stores probabilities and prices, not what happened. v9's
    `player_history.parquet` does, it is committed, and reading it is the same read-only
    borrowing pro_weekly_audit already does. Pro still writes nothing to v9.
    """
    from src.combo import team_markets as tm
    import os
    roots = [os.getenv("V9_LOCAL", ""), str(ROOT.parent / "v9"), str(ROOT.parent / "_v9")]
    for r in roots:
        if not r:
            continue
        p = Path(r) / "player_history.parquet"
        if not p.exists():
            continue
        try:
            h = pd.read_parquet(p)
            rates = tm.team_card_rates(h)
            print(f"[builder] card rates from {p.name}: {len(rates):,} team-matches")
            return rates
        except Exception as e:                                 # noqa: BLE001
            print(f"[builder] could not read {p}: {type(e).__name__}: {e}")
    # Said out loud. Silently producing zero card legs is what happened the first time.
    print("[builder] NO player_history.parquet found — team-card legs will NOT be built. "
          "Check out v9 alongside Pro, or set V9_LOCAL.")
    return pd.DataFrame()


def generate(days: int = DEFAULT_DAYS, *, now: dt.datetime | None = None) -> pd.DataFrame:
    now = now or dt.datetime.now(dt.timezone.utc)
    fixtures, snaps, props = _read("fixtures"), _read("model_snapshots"), _read("player_props")
    if fixtures.empty or snaps.empty:
        print("[builder] no fixtures or model snapshots in the warehouse — nothing to build")
        return pd.DataFrame()

    fx = fixtures.copy()
    fx["_ko"] = pd.to_datetime(fx.get("kickoff_utc"), errors="coerce", utc=True)
    fx = fx.dropna(subset=["_ko"]).drop_duplicates(subset=["fixture_key"], keep="last")
    horizon = now + dt.timedelta(days=days)
    started = int((fx["_ko"] <= now).sum())
    fx = fx[(fx["_ko"] > now) & (fx["_ko"] <= horizon)]
    print(f"[builder] {len(fx)} upcoming fixture(s) within {days}d "
          f"({started} already kicked off, skipped — pre-match only)")
    if fx.empty:
        return pd.DataFrame()

    probs = _latest_model_probs(snaps)
    dep = _dependency()
    cards = _card_rates()
    if not dep:
        print("[builder] no measured player dependence available — player legs fall back to "
              "independence (ratio 1.0), which is recorded per row as a flag")

    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    out, no_probs, bad_mono, no_fit = [], 0, 0, 0

    for _, f in fx.iterrows():
        k = f["fixture_key"]
        if k not in probs.index:
            no_probs += 1
            continue
        row = probs.loc[k]
        targets = {m: float(row[m]) for m in ("O15", "O25", "O35", "BTTS")
                   if m in row.index and pd.notna(row.get(m))}
        # The warehouse names the over/under markets OU15/OU25/OU35; score_model speaks O15/...
        for src_m, dst_m in (("OU15", "O15"), ("OU25", "O25"), ("OU35", "O35")):
            if src_m in row.index and pd.notna(row.get(src_m)):
                targets[dst_m] = float(row[src_m])
        if "BTTS" in row.index and pd.notna(row.get("BTTS")):
            targets["BTTS"] = float(row["BTTS"])
        if len(targets) < 2:
            no_probs += 1
            continue
        # Section 3: never build legs from a logically inconsistent probability set. An O2.5 above
        # O1.5 is not a tight market, it is a broken input, and the matrix fitted to it would be
        # confidently wrong rather than uncertain.
        if sm.monotonicity_violation(targets):
            bad_mono += 1
            continue
        fit = sm.fit(targets)
        if not fit.get("ok"):
            no_fit += 1
            continue

        fp = props[props["fixture_key"] == k] if not props.empty else None
        # QUOTA PER LEG COUNT, kept deliberately tight. The module default of 40 gives 120 rows
        # a fixture and 19,080 across a board — a 7 MB CSV committed on every run, several times
        # a week, forever. Nothing consumes that depth: notify sends at most 6, the dashboard
        # shows 200. Twelve of each leg count keeps the interesting tail of every length while
        # the file stays a few hundred KB.
        cand = mp.build(fit["matrix"], props=fp if fp is not None and len(fp) else None,
                        cards=cards if len(cards) else None,
                        home=str(f.get("home_team", "")), away=str(f.get("away_team", "")),
                        dep=dep, top_n=CANDIDATES_PER_LEG_COUNT)
        if cand.empty:
            continue
        cand.insert(0, "generated_at", stamp)
        cand.insert(1, "fixture_key", k)
        cand.insert(2, "league", f.get("league"))
        cand.insert(3, "match_date", f.get("match_date"))
        cand.insert(4, "kickoff_utc", f["_ko"].strftime("%Y-%m-%dT%H:%M:%SZ"))
        cand.insert(5, "match", f'{f.get("home_team")} vs {f.get("away_team")}')
        cand["calc_version"] = CALC_VERSION
        out.append(cand)

    if not out:
        print(f"[builder] no candidates built "
              f"(no model probs {no_probs}, inconsistent {bad_mono}, unfittable {no_fit})")
        return pd.DataFrame()

    d = pd.concat(out, ignore_index=True)
    # A stable identity per (fixture, leg set) so notify can dedup and settle can merge.
    #
    # THE ID MUST CONTAIN THE SELECTION, NOT ONLY THE MARKET. The previous version hashed
    # `leg1_market + leg2_market + ...` alone, so every combo on the same fixture with the same
    # market TYPES shared one id. Measured on the 2026-08-29 build: 475 candidates carried only
    # 225 distinct ids, and one id — `0a1967b546c57994|BTTS+player_sot++` — covered
    # "BTTS + R. Karjalainen 1+ SOT" and "BTTS + Julius Körkkö 1+ SOT", two different bets.
    #
    # That was not cosmetic. `settle_finished()` deduplicates the merged record on this id with
    # keep="first", so each settle pass collapsed those 475 rows to 225 and discarded ~250
    # DISTINCT combos — permanently, and invisibly. The existing "must never drop a graded row"
    # guard could not see it: the discarded rows are almost all still UNKNOWN at that point, so
    # the count of decided rows never fell. The settled file looks collision-free today precisely
    # BECAUSE the collapse already happened upstream of it.
    #
    # The label carries the selection ("R. Karjalainen 1+ shot on target"), so market+label is
    # the identity. Legs are sorted before hashing so leg ORDER cannot produce two ids for one
    # bet, which is the other half of "stable".
    legcols = sorted(c for c in d.columns if c.startswith("leg") and c.endswith("_market"))
    labcols = [c[:-len("_market")] + "_label" for c in legcols]

    def _identity(row) -> str:
        legs_ = sorted(f"{row.get(m) or ''}:{row.get(lab) or ''}"
                       for m, lab in zip(legcols, labcols) if row.get(m))
        return hashlib.sha1("|".join(legs_).encode("utf-8")).hexdigest()[:12]

    # Retained so rows written before 2026-08-30 stay joinable to the record they are part of.
    # Never used as a dedup key again — it is the broken key, kept only for lineage.
    d["combo_id_legacy"] = (d["fixture_key"].astype(str) + "|"
                            + d[legcols].fillna("").astype(str).agg("+".join, axis=1))
    d["combo_id"] = d["fixture_key"].astype(str) + "|" + d.apply(_identity, axis=1)
    n_ids = d["combo_id"].nunique()
    if n_ids < len(d):
        # Should now be impossible: two rows sharing an id means two identical leg sets on one
        # fixture, which `build()` does not emit. Said out loud rather than assumed.
        print(f"[builder] WARNING {len(d) - n_ids} candidate row(s) share a combo_id after the "
              f"selection-aware fix — inspect before trusting the settled record")
    print(f"[builder] {len(d):,} candidate(s) over {d['fixture_key'].nunique()} fixture(s); "
          f"skipped — no model probs {no_probs}, inconsistent {bad_mono}, unfittable {no_fit}")
    return d


def _recover_fixture_keys(d: pd.DataFrame) -> pd.DataFrame:
    """Attach `fixture_key` to rows that predate it, so they can settle by key.

    Candidates written before the key existed can only be joined to a scoreline by club name,
    which is the join that fails across sources (invariant 11) and is why 1,956 combos were once
    reported UNKNOWN when they were merely unjoined. But those rows were BUILT from Pro's own
    fixtures table, so `date|home|away` matches it exactly -- no fuzzy matching, no resolver, and
    nothing invented: a row that does not match is left alone rather than guessed at.
    """
    if "fixture_key" in d.columns and d["fixture_key"].notna().all():
        return d
    fx = _read("fixtures")
    if fx.empty or not {"fixture_key", "match_date", "home_team", "away_team"} <= set(fx.columns):
        return d
    fx = fx.drop_duplicates("fixture_key")
    m = dict(zip(fx["match_date"].astype(str).str[:10] + "|"
                 + fx["home_team"].astype(str) + "|" + fx["away_team"].astype(str),
                 fx["fixture_key"]))
    out = d.copy()
    if "fixture_key" not in out.columns:
        out["fixture_key"] = pd.NA
    miss = out["fixture_key"].isna()
    if not miss.any():
        return out
    k = (out.loc[miss, "match_date"].astype(str).str[:10] + "|"
         + out.loc[miss, "match"].astype(str).str.replace(" vs ", "|", regex=False))
    out.loc[miss, "fixture_key"] = k.map(m)
    got = int(out.loc[miss, "fixture_key"].notna().sum())
    if got:
        print(f"[builder] recovered fixture_key for {got:,} of {int(miss.sum()):,} older row(s) "
              f"— they can now settle by key instead of by club name")
    return out


def settle_finished() -> pd.DataFrame:
    """Grade every candidate whose fixture has a final score, merging into the standing record."""
    cand = pd.read_csv(CAND_FILE, low_memory=False) if CAND_FILE.exists() else pd.DataFrame()

    # RETRY EVERYTHING STILL UNDECIDED, not just today's candidates. A combo goes UNKNOWN for
    # reasons that expire: the fixture had not kicked off, the scoreline had not been collected
    # yet (team_match_stats runs on a lag), or the row predated fixture_key and could only be
    # joined by club name. All three become decidable later, and a settler that only ever looks
    # at the current candidate file would leave them UNKNOWN permanently.
    if SETTLED_FILE.exists():
        prev = pd.read_csv(SETTLED_FILE, low_memory=False)
        retry = prev[prev.get("combo_result").eq("UNKNOWN")] if "combo_result" in prev else prev
        if len(retry):
            drop = [c for c in ("combo_result", "leg_results", "settle_note", "final_score",
                                "settle_version") if c in retry.columns]
            cand = pd.concat([cand, retry.drop(columns=drop)], ignore_index=True)
            print(f"[builder] retrying {len(retry):,} previously-undecided combo(s)")
    if cand.empty:
        print("[builder] no candidates to settle")
        return pd.DataFrame()
    cand = _recover_fixture_keys(cand)

    # `settlements` carries a `result`, not a SCORELINE, and a builder cannot be graded from a
    # result: "Over 3.5 + BTTS + home over 1.5" needs the actual goals on each side. The tables
    # that hold them are team_match_stats (23,604 rows) and settlements_backfill (778), and both
    # carry `fixture_key`, which is what lets the settler avoid the club-name join entirely.
    need = {"home_team", "away_team", "home_goals", "away_goals", "match_date"}
    parts = [t for t in (_read("team_match_stats"), _read("settlements_backfill"))
             if not t.empty and need.issubset(t.columns)]
    if not parts:
        print("[builder] cannot settle — no table carries a full scoreline. "
              "Reporting that rather than grading everything UNKNOWN.")
        return pd.DataFrame()
    res = pd.concat(parts, ignore_index=True)
    if "fixture_key" in res.columns:
        res = res.drop_duplicates(subset=["fixture_key"], keep="last")
    players = _read("player_props")

    fresh = cs.settle(cand, res, players if not players.empty else pd.DataFrame())
    if fresh.empty:
        return fresh

    if SETTLED_FILE.exists():
        old = pd.read_csv(SETTLED_FILE, low_memory=False)
        # THE MERGE MUST NEVER BE ABLE TO DROP A GRADED ROW. The first version only merged when
        # BOTH frames carried `combo_id` and otherwise let `fresh` through untouched -- so the
        # first real run overwrote a 2,532-row record (576 decided) with 19,080 fresh UNKNOWNs,
        # because the historical file predated combo_id. The record survived only because it was
        # already committed. Old rows are now concatenated unconditionally; the identity is used
        # to deduplicate, never to decide whether to keep history at all.
        # THE DEDUP KEY MUST NEVER CONTAIN NULLS. Choosing `combo_id` merely because the column
        # exists on both sides destroyed the record a second time: 2,532 historical rows predate
        # combo_id and carry NaN, and drop_duplicates treats every NaN as the SAME value, so all
        # 2,532 collapsed into one and 576 graded results became 1. The key is therefore resolved
        # PER ROW -- combo_id where it is actually populated, the composite everywhere else -- and
        # a row that can be identified no other way is never deduplicated at all.
        key = None
        have = set(old.columns) & set(fresh.columns)
        if {"match", "match_date", "legs"} <= have or "combo_id" in have:
            key = "_merge_key"
            for f in (old, fresh):
                cid = (f["combo_id"].astype("string") if "combo_id" in f.columns
                       else pd.Series(pd.NA, index=f.index, dtype="string"))
                comp = pd.Series(pd.NA, index=f.index, dtype="string")
                if {"match", "match_date", "legs"} <= set(f.columns):
                    comp = (f["match"].astype(str) + "|" + f["match_date"].astype(str)
                            + "|" + f["legs"].astype(str)).astype("string")
                # THE COMPOSITE COMES FIRST, and that ordering is the fix for the collapse
                # described at the combo_id construction in `generate()`. `legs` spells out every
                # selection, so `match|match_date|legs` distinguishes two combos that differ only
                # by which player is in them; the old market-only combo_id did not, and putting it
                # first meant ~250 distinct combos were deduplicated away on every settle pass.
                #
                # Measured on the committed record: 5,861 rows carrying a combo_id resolve to
                # 5,861 distinct composites AND 5,861 distinct ids, so on today's data the two
                # keys agree exactly and this reordering changes no existing row. It changes what
                # happens to rows built before the id fix, which is the point.
                #
                # combo_id remains the fallback for any row that has an id but no legs text.
                f[key] = comp.fillna(cid).fillna(
                    # Row index as the last resort: distinct for every row, so an unidentifiable
                    # row survives instead of colliding with every other unidentifiable row.
                    pd.Series([f"__row{i}" for i in range(len(f))], index=f.index, dtype="string"))
        merged = pd.concat([old, fresh], ignore_index=True)
        if key:
            # `old` comes first and keep="first", so a combo already graded WON never reverts to
            # UNKNOWN because a later pass could not find its scoreline.
            merged["_decided"] = merged["combo_result"].isin(["WON", "LOST", "VOID"])
            merged = (merged.sort_values("_decided", ascending=False, kind="stable")
                            .drop_duplicates(subset=[key], keep="first")
                            .drop(columns=["_decided"] + ([key] if key == "_merge_key" else [])))
        # A merge must never be able to LOSE a graded result. Cheap to assert, and it is exactly
        # the invariant that broke twice.
        # A DISTINCT COMBO MUST NEVER BE MERGED AWAY EITHER, decided or not. The graded-row guard
        # below could not see the combo_id collapse because the rows it discarded were still
        # UNKNOWN, and an UNKNOWN row is a combo awaiting its result — losing it loses the bet,
        # not just a grade. Counted on the identity that actually distinguishes combos.
        def _ncombos(f: pd.DataFrame) -> int:
            if not {"match", "match_date", "legs"} <= set(f.columns):
                return 0
            return int((f["match"].astype(str) + "|" + f["match_date"].astype(str)
                        + "|" + f["legs"].astype(str)).nunique())

        c_was, c_now = _ncombos(old), _ncombos(merged)
        if c_now < c_was:
            raise RuntimeError(
                f"merge would drop {c_was - c_now} distinct combo(s) ({c_was} -> {c_now}); "
                f"refusing to write. The dedup key is collapsing combos that are not the "
                f"same bet — see the combo_id note in generate().")

        was = int(old["combo_result"].isin(["WON", "LOST", "VOID"]).sum()) if \
            "combo_result" in old.columns else 0
        now_ = int(merged["combo_result"].isin(["WON", "LOST", "VOID"]).sum())
        if now_ < was:
            raise RuntimeError(
                f"merge would drop graded results ({was} -> {now_}); refusing to write. "
                f"This means the dedup key collided rows that are not the same combo.")
        fresh = merged
        print(f"[builder] merged with {len(old):,} existing row(s) "
              f"-> {len(fresh):,} (graded {was} -> {now_})")
    perf = cs.performance(fresh)
    print(f"[builder] settled record: {perf}")
    return fresh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("generate", "notify", "settle", "all"), default="all")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--dry-run", action="store_true",
                    help="build and format, send nothing")
    ap.add_argument("--allow-local-write", action="store_true",
                    help="permit canonical appends from a laptop (scratch seasons only)")
    args = ap.parse_args()

    import config.pro_config as cfg

    failed = False
    canon: dict[str, int] = {}

    if args.mode in ("generate", "all"):
        d = generate(args.days)
        if not d.empty:
            OUT.mkdir(exist_ok=True)
            d.to_csv(CAND_FILE, index=False, encoding="utf-8")
            print(f"[builder] wrote {CAND_FILE.name} ({len(d):,} rows)")
            # The CSV above is the current-state view and is overwritten every run; this is the
            # history beside it. Both, not either: the CSV is what notify and the dashboard read,
            # the canonical tables are what any question about WHEN an opinion was formed needs.
            head, legs = cc.candidates(d, run_id=cfg.run_id())
            canon.update(cc.write(head, legs, None, None,
                                  source="pro:bet_builder/generate",
                                  allow_local=args.allow_local_write))

    if args.mode in ("notify", "all"):
        cand = pd.read_csv(CAND_FILE, low_memory=False) if CAND_FILE.exists() else pd.DataFrame()
        # Two independent gates. `--dry-run` is the operator's; PRO_MAY_NOTIFY is the repo's, and
        # it exists so Pro cannot start messaging by accident just because a pipeline ran.
        allowed = bool(getattr(cfg, "PRO_MAY_NOTIFY", False))
        dry = args.dry_run or not allowed
        if not allowed:
            print("[builder] PRO_MAY_NOTIFY is off — formatting only, sending nothing")
        if cand.empty:
            print("[builder] nothing to notify")
        else:
            sent = cn.run(cand, dry_run=dry)
            print(f"[builder] notify: {sent}")
            # FAIL LOUDLY WHEN WE MEANT TO SEND AND COULD NOT. Telegram credentials are
            # repository secrets and they DO NOT CROSS REPOS — v9 has them, Pro is a different
            # repository and pro_collect.yml states plainly that none exists here. Without this
            # check the workflow builds combos, formats messages, fails every send, and exits
            # green, which is the "green workflow, no data" pattern every incident in this project
            # has taken. An unsendable notify run is a failed run.
            if not dry and sent.get("send_failed"):
                errs = sent.get("send_errors", {})
                print(f"::error title=Combo tips were NOT delivered::"
                      f"{sent['send_failed']} send(s) failed — {errs}. "
                      f"If this says the token/chat id is not set, add those secrets to THIS "
                      f"repository; secrets from v9 do not apply here.")
                # Flagged, not returned: settlement still has to run. Grading finished combos is
                # independent of whether today's tips were delivered, and skipping it would turn
                # one problem into two.
                failed = True

    if args.mode in ("settle", "all"):
        s = settle_finished()
        if not s.empty:
            s.to_csv(SETTLED_FILE, index=False, encoding="utf-8")
            print(f"[builder] wrote {SETTLED_FILE.name} ({len(s):,} rows)")
            # Dependency estimates ride along with the settle pass rather than generate: they are
            # re-estimated on the same cadence as results arrive, and versioning them next to the
            # settlements keeps "what did we assume when we graded this" in one place.
            deps = cc.dependencies(
                pd.read_csv(OUT / "combo_dependency_matrix.csv")
                if (OUT / "combo_dependency_matrix.csv").exists() else pd.DataFrame(),
                pd.read_csv(OUT / "player_combo_dependency.csv")
                if (OUT / "player_combo_dependency.csv").exists() else pd.DataFrame(),
                run_id=cfg.run_id())
            canon.update(cc.write(None, None, cc.settlements(s, run_id=cfg.run_id()), deps,
                                  source="pro:bet_builder/settle",
                                  allow_local=args.allow_local_write))

    if canon:
        # Printed as a line CI can be read against, and a -1 (append refused) is reported rather
        # than silently absent — the whole failure mode this repo keeps hitting is a green run
        # that persisted nothing.
        print(f"[builder] canonical: " +
              ", ".join(f"{k}={v:,}" if v >= 0 else f"{k}=FAILED" for k, v in sorted(canon.items())))
        if any(v < 0 for v in canon.values()):
            print("::warning title=Builder evidence not fully persisted::"
                  "one or more canonical combo tables refused the append; the CSVs were still "
                  "written, so today's tips are unaffected and the HISTORY is what was lost.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
