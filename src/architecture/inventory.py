"""Discover and profile every data store across the three repos, and trace who touches it.

    python -m src.architecture.inventory --write

WHAT COUNTS AS ONE STORE. A partitioned directory of 2,615 parquet files is ONE logical table,
not 2,615 data stores, and a cache directory of 45,753 provider responses is one cache. Listing
them file by file would bury the twelve tables that actually matter under forty thousand rows of
noise. So partitions and caches are collapsed to a single entry with a file count.

FRESHNESS COMES FROM GIT, NEVER FROM mtime. `git checkout` resets mtime on every CI run, so
anything mtime-based reads as ~0 hours old and never refreshes. That trap has produced three
separate bugs in this estate (provenance._model_sha, fpl_api._cached_fetch, and the player-history
cooldown that froze collection for 35 days). Last-updated here is the author date of the last
commit that touched the path, which is a recorded timestamp and cannot be reset by a checkout.

PRODUCERS AND CONSUMERS ARE TRACED BY READING THE CODE, not by guessing from filenames. A file
whose name looks like a duplicate of another may be the only thing a production workflow reads,
and a file with an important-sounding name may have no readers at all -- which is exactly what
`backtest_all_leagues.csv` turned out to be: 44,207 rows, 24,629 fixtures found nowhere else,
and not one line of code that opens it.

The write/read distinction is deliberately conservative. A path appearing next to `to_parquet`,
`to_csv`, `write_text` or a workflow's `git add` counts as WRITTEN; next to `read_parquet`,
`read_csv`, `open` or `load` counts as READ. A mention that is neither is recorded as a
reference, because a path in a comment or a docstring is not a dependency and should not be
counted as one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

REPOS = {"v9": "v9", "pro": "v10", "v11": "wowza-v11"}
DATA_EXT = (".csv", ".parquet", ".json", ".xlsx")
SKIP_DIR = ("/.venv/", "/site-packages/", "/__pycache__/", "/node_modules/", "/_archive/",
            "/_legacy/", "/_presync", "/.git/", "/archive/", "/_quarantine")

# Layer taxonomy from the brief (section 27). Every store lands in exactly one.
LAYERS = ("RAW", "CANONICAL", "DERIVED", "CACHE", "REPORT", "UNKNOWN")

WRITE_HINTS = ("to_parquet", "to_csv", "write_text", "write_bytes", "to_json", "savefig",
               "open(", "git add", "np.save", "dump(")
READ_HINTS = ("read_parquet", "read_csv", "read_json", "load(", "loads(", "open(", "glob(")


def _root() -> Path:
    return cfg.BASE_DIR.parent


def _sh(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                              timeout=60).stdout.strip()
    except Exception:
        return ""


_GITLOG_CACHE: dict[str, dict[str, tuple[str, str]]] = {}


def _git_history(repo_dir: Path, *, depth: int = 4000) -> dict[str, tuple[str, str]]:
    """path -> (last commit iso date, subject), from ONE batched `git log` per repo.

    One `git log -1 -- <path>` per file is the obvious implementation and it is unusable here:
    git on this working tree is slow (OneDrive plus multi-hundred-megabyte caches) and there are
    ~100 tracked data files per repo, so the per-file version ran for twenty minutes without
    finishing. A single `--name-only` walk of the last few thousand commits gives the same answer
    in one call, because commits arrive newest-first and the FIRST time a path appears is by
    definition its most recent change.
    """
    key = str(repo_dir)
    if key in _GITLOG_CACHE:
        return _GITLOG_CACHE[key]
    out = _sh(["git", "log", f"-n{depth}", "--name-only", "--format=@@|%aI|%s"], repo_dir)
    hist: dict[str, tuple[str, str]] = {}
    cur = ("", "")
    for line in out.splitlines():
        line = line.rstrip()
        if line.startswith("@@|"):
            parts = line.split("|", 2)
            cur = (parts[1][:19] if len(parts) > 1 else "",
                   parts[2][:90] if len(parts) > 2 else "")
        elif line and cur[0]:
            hist.setdefault(line.replace("\\", "/"), cur)
    _GITLOG_CACHE[key] = hist
    return hist


def _git_last_commit(repo_dir: Path, rel: str) -> tuple[str, str]:
    """(iso date, subject) of the last commit touching this path. Empty if untracked."""
    h = _git_history(repo_dir)
    if rel in h:
        return h[rel]
    # A partitioned table is a directory: take the newest commit among its files.
    pref = rel.rstrip("/") + "/"
    best = ("", "")
    for p, v in h.items():
        if p.startswith(pref) and v[0] > best[0]:
            best = v
    return best


def _tracked(repo_dir: Path) -> set[str]:
    out = _sh(["git", "ls-files"], repo_dir)
    return {l.strip().replace("\\", "/") for l in out.splitlines() if l.strip()}


def _profile(path: Path) -> dict:
    """Rows, columns, date span and a primary-key guess. Cheap: reads at most 200k rows."""
    info: dict = {"rows": None, "cols": None, "first": "", "last": "", "key_guess": "",
                  "read_error": ""}
    try:
        if path.suffix == ".parquet":
            d = pd.read_parquet(path)
        elif path.suffix == ".csv":
            d = pd.read_csv(path, low_memory=False, nrows=200_000)
        elif path.suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                d = pd.DataFrame(raw)
            elif isinstance(raw, dict):
                info["rows"] = len(raw)
                info["cols"] = len(next(iter(raw.values()))) if raw and isinstance(
                    next(iter(raw.values())), dict) else 0
                info["key_guess"] = "json object"
                return info
            else:
                return info
        else:
            return info
        info["rows"], info["cols"] = int(len(d)), int(len(d.columns))
        dc = next((c for c in ("date", "Date", "match_date", "snapshot_date", "observed_at",
                               "snapshot_ts", "kickoff_utc", "generated_at", "checked_at")
                   if c in d.columns), None)
        if dc is not None:
            s = pd.to_datetime(d[dc], errors="coerce", format="mixed")
            if s.notna().any():
                info["first"], info["last"] = str(s.min())[:19], str(s.max())[:19]
        for cand in (("fixture_key",), ("fixture_id",), ("date", "home_team", "away_team"),
                     ("fixture_id", "player_id"), ("date", "league", "match", "market")):
            if all(c in d.columns for c in cand):
                info["key_guess"] = "+".join(cand)
                break
    except Exception as e:                                           # noqa: BLE001
        info["read_error"] = f"{type(e).__name__}: {e}"[:110]
    return info


def _classify(repo: str, rel: str) -> str:
    r = rel.lower()
    if "_cache" in r or r.startswith("cache"):
        return "CACHE"
    if repo == "pro" and r.startswith("data/season_"):
        return "CANONICAL"
    if "history" in r or r.endswith("_history.csv") or "snapshots" in r:
        return "RAW" if ("odds" in r or "book" in r or "snapshot" in r) else "CANONICAL"
    if any(k in r for k in ("backtest", "ledger", "training", "model_", "predictions",
                            "tips", "bets", "signals")):
        return "DERIVED"
    if any(k in r for k in ("health", "audit", "coverage", "manifest", "report", "summary",
                            "verdict", "registry", "log.json", "_log")):
        return "REPORT"
    return "UNKNOWN"


def discover() -> pd.DataFrame:
    root = _root()
    rows = []
    for repo, folder in REPOS.items():
        rd = root / folder
        if not rd.exists():
            continue
        tracked = _tracked(rd)
        partitions: dict[str, list[Path]] = defaultdict(list)
        caches: dict[str, list[Path]] = defaultdict(list)
        singles: list[Path] = []

        # PRUNE WHOLE DIRECTORIES, do not walk into them. v9 holds ~90,000 cache files and
        # rglob("*") visits every one before anything can be filtered -- on OneDrive that alone
        # ran for twenty minutes. Caches are counted by a cheap per-directory scan below.
        cache_dirs = [d for d in rd.iterdir()
                      if d.is_dir() and (d.name.endswith("_cache") or d.name == "cache")]
        for d in cache_dirs:
            fs = [x for x in d.rglob("*") if x.is_file() and x.suffix in DATA_EXT]
            if fs:
                caches[d.name] = fs

        for p in rd.rglob("*"):
            if not p.is_file() or p.suffix not in DATA_EXT:
                continue
            rel = str(p.relative_to(rd)).replace("\\", "/")
            if any(s in f"/{rel}/" for s in SKIP_DIR):
                continue
            if rel.split("/")[0] in caches:
                continue
            if "_cache/" in rel or rel.split("/")[0].endswith("_cache"):
                caches[rel.split("/")[0]].append(p)
            elif re.search(r"/dt=\d{4}-\d{2}-\d{2}/", rel):
                # data/season_X/table/dt=.../run=... -> one logical table
                partitions["/".join(rel.split("/")[:3])].append(p)
            else:
                singles.append(p)

        for p in singles:
            rel = str(p.relative_to(rd)).replace("\\", "/")
            prof = _profile(p)
            d, subj = _git_last_commit(rd, rel)
            rows.append({"repo": repo, "path": rel, "kind": "file",
                         "format": p.suffix.lstrip("."), "files": 1,
                         "bytes": p.stat().st_size, "tracked": rel in tracked,
                         "layer": _classify(repo, rel), "last_commit": d,
                         "last_commit_subject": subj, **prof})
        for name, ps in partitions.items():
            tot = sum(x.stat().st_size for x in ps)
            d, subj = _git_last_commit(rd, name)
            dts = sorted(re.search(r"dt=(\d{4}-\d{2}-\d{2})", str(x)).group(1) for x in ps
                         if re.search(r"dt=(\d{4}-\d{2}-\d{2})", str(x)))
            rows.append({"repo": repo, "path": name, "kind": "partitioned_table",
                         "format": "parquet", "files": len(ps), "bytes": tot,
                         "tracked": any(str(x.relative_to(rd)).replace("\\", "/") in tracked
                                        for x in ps[:50]),
                         "layer": _classify(repo, name), "last_commit": d,
                         "last_commit_subject": subj, "rows": None, "cols": None,
                         "first": dts[0] if dts else "", "last": dts[-1] if dts else "",
                         "key_guess": "", "read_error": ""})
        for name, ps in caches.items():
            tot = sum(x.stat().st_size for x in ps)
            rows.append({"repo": repo, "path": name, "kind": "cache_dir", "format": "json",
                         "files": len(ps), "bytes": tot, "tracked": False, "layer": "CACHE",
                         "last_commit": "", "last_commit_subject": "", "rows": None,
                         "cols": None, "first": "", "last": "", "key_guess": "",
                         "read_error": ""})
    return pd.DataFrame(rows)


def trace_code(inv: pd.DataFrame) -> pd.DataFrame:
    """Who writes each store, who reads it, and which workflow stages it."""
    root = _root()
    names = {}
    for _, r in inv.iterrows():
        base = r["path"].split("/")[-1] if r["kind"] != "cache_dir" else r["path"]
        names.setdefault(base, []).append((r["repo"], r["path"]))

    prod = defaultdict(set)
    cons = defaultdict(set)
    refs = defaultdict(set)
    wf = defaultdict(set)

    for repo, folder in REPOS.items():
        rd = root / folder
        if not rd.exists():
            continue
        for p in list(rd.rglob("*.py")) + list(rd.rglob("*.yml")) + list(rd.rglob("*.yaml")):
            rel = str(p.relative_to(rd)).replace("\\", "/")
            if any(s in f"/{rel}/" for s in SKIP_DIR):
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = txt.splitlines()
            for base in names:
                if base not in txt:
                    continue
                tag = f"{repo}:{rel}"
                is_wf = rel.startswith(".github/workflows/")
                hit_w = hit_r = False

                # FOLLOW THE VARIABLE, not just the literal. The first version of this looked
                # only at a +/-3 line window around the filename and produced false orphans on
                # every file opened through a module-level constant -- the dominant idiom here:
                #
                #     OUT = PROJ / "output" / "standard_sidemarket_odds_history.csv"   (line 32)
                #     ...
                #     df = pd.read_csv(OUT)                                            (line 180)
                #
                # It reported 34 stores as "written but never read", and spot-checking the first
                # four showed all four were read. An audit that invents dead files is worse than
                # no audit, so the literal is now traced to the names it is bound to and those
                # names are searched across the whole file.
                aliases: set[str] = set()
                for i, line in enumerate(lines):
                    if base not in line:
                        continue
                    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=", line)
                    if m:
                        aliases.add(m.group(1))
                    ctx = " ".join(lines[max(0, i - 3):i + 4])
                    if any(h in ctx for h in WRITE_HINTS):
                        hit_w = True
                    if any(h in ctx for h in READ_HINTS):
                        hit_r = True
                for al in aliases:
                    if re.search(rf"(read_csv|read_parquet|read_json|open|load)\s*\(\s*{al}\b",
                                 txt):
                        hit_r = True
                    if re.search(rf"\b{al}\s*\.\s*(write_text|write_bytes)|"
                                 rf"(to_csv|to_parquet|to_json)\s*\(\s*{al}\b", txt):
                        hit_w = True
                if is_wf:
                    wf[base].add(tag)
                    if "git add" in txt:
                        hit_w = True
                if hit_w:
                    prod[base].add(tag)
                if hit_r:
                    cons[base].add(tag)
                if not hit_w and not hit_r:
                    refs[base].add(tag)

    out = inv.copy()
    key = out.apply(lambda r: r["path"].split("/")[-1] if r["kind"] != "cache_dir"
                    else r["path"], axis=1)
    out["producers"] = key.map(lambda b: "; ".join(sorted(prod.get(b, ()))[:6]))
    out["n_producers"] = key.map(lambda b: len(prod.get(b, ())))
    out["consumers"] = key.map(lambda b: "; ".join(sorted(cons.get(b, ()))[:8]))
    out["n_consumers"] = key.map(lambda b: len(cons.get(b, ())))
    out["workflows"] = key.map(lambda b: "; ".join(sorted(wf.get(b, ()))[:6]))
    out["n_workflows"] = key.map(lambda b: len(wf.get(b, ())))
    out["mention_only"] = key.map(lambda b: len(refs.get(b, ())))
    # THE FLAG THAT MATTERS: produced, never consumed. That is data we are paying to create and
    # then not using -- which is how 24,629 fixtures ended up invisible.
    out["orphan_written_never_read"] = (out.n_consumers == 0) & (out.n_producers > 0)
    out["dead_no_code_touches_it"] = (out.n_consumers == 0) & (out.n_producers == 0)
    return out


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    inv = discover()
    print(f"[inventory] {len(inv)} logical data stores across {inv.repo.nunique()} repos")
    full = trace_code(inv)

    print("\nBY REPO x LAYER")
    print(full.pivot_table(index="repo", columns="layer", values="path",
                           aggfunc="count", fill_value=0).to_string())

    big = full[(full.kind == "file") & (full.rows.notna())].sort_values("rows", ascending=False)
    print(f"\nLARGEST TABLES BY ROWS")
    print(big.head(16)[["repo", "path", "layer", "rows", "cols", "first", "last",
                        "n_producers", "n_consumers"]].to_string(index=False))

    orph = full[full.orphan_written_never_read & (full.rows.fillna(0) > 500)]
    print(f"\nWRITTEN BUT NEVER READ  ({len(orph)} stores with >500 rows) "
          f"-- data we create and do not use:")
    if len(orph):
        print(orph[["repo", "path", "layer", "rows", "first", "last",
                    "producers"]].to_string(index=False))

    if a.write:
        full.to_csv(out_dir() / "data_lineage.csv", index=False)
        print(f"\n[inventory] wrote {out_dir() / 'data_lineage.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
