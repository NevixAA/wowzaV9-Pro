"""Forward progress of the frozen H-EDGE2 v1 family (market_edge_v2, registered 2026-10-25).

    python -m src.studies.edge2_forward [--v9 PATH]   # -> output/edge_reassessment/edge2_forward_progress.json

Reads registry/edge2_hypotheses_v1.json (FROZEN - never edited here; its content hash is pinned below)
and v9's first-sight shadow output/edge_engine_shadow.csv (local v9 checkout first - `--v9`, then
cfg.V9_LOCAL - else raw HTTP). Read-only towards v9.

What it reports per hypothesis:
    counts           logged first-sight rows in the forward window, two-sided rows, settled rows,
                     gameweeks, decision-state counts, selections (QUALIFIED/STRONG)
    status           REGISTERED / ACCRUING / ELIGIBLE_FOR_REVIEW / BLOCKED_CONFIG_CHANGED
    metrics          ONLY once ELIGIBLE_FOR_REVIEW (interim policy: no effect size before eligibility),
                     then the pre-registered primary test, BH across the eligible family members, and
                     which promotion / rejection criteria are met. The owner decides.

CONFIRMED is never assigned here. Nothing in production changes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

REG = cfg.BASE_DIR / "registry" / "edge2_hypotheses_v1.json"
OUT = cfg.BASE_DIR / "output" / "edge_reassessment" / "edge2_forward_progress.json"
SHADOW_REL = "output/edge_engine_shadow.csv"
#: content_sha256 (CRLF -> LF) of registry/edge2_hypotheses_v1.json at registration. A mismatch is a
#: mutated registration: the evaluator refuses to grade against it.
REGISTRATION_SHA256 = "17238eb560906be283c5776f01be3a0e12266a11433ba867ae787fc4ed548517"
TWO_SIDED = ("MEDIAN_TWO_SIDED_BOOKS", "SINGLE_TWO_SIDED_BOOK")
SIDE_A = {"OU25": "OVER", "OU15": "OVER", "OU35": "OVER", "BTTS": "YES"}
LINE = {"OU25": 2.5, "OU15": 1.5, "OU35": 3.5}
N_BOOT = 10_000
SEED = 20261026


def sha256_lf(b: bytes) -> str:
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


# ───────────────────────────── inputs ─────────────────────────────
def _v9_root(v9: str | None) -> Path | None:
    for p in ([Path(v9)] if v9 else []) + [cfg.V9_LOCAL]:
        if p and Path(p).exists():
            return Path(p)
    return None


def _read_v9_bytes(rel: str, v9: str | None) -> bytes | None:
    root = _v9_root(v9)
    if root is not None and (root / rel).exists():
        return (root / rel).read_bytes()
    try:
        import requests
        r = requests.get(f"{cfg.V9_RAW_BASE}/{rel}", timeout=60)
        return r.content if r.status_code == 200 else None
    except Exception:                                                  # noqa: BLE001
        return None


def load_shadow(v9: str | None = None) -> pd.DataFrame:
    b = _read_v9_bytes(SHADOW_REL, v9)
    if not b:
        return pd.DataFrame()
    import io
    return pd.read_csv(io.BytesIO(b), low_memory=False)


def engine_hashes(v9: str | None, reg: dict) -> dict:
    e = reg["engine"]
    out = {}
    for k, rel in (("config_sha256_lf", e["config_path"]), ("code_sha256_lf", e["code_path"])):
        b = _read_v9_bytes(rel, v9)
        out[k] = sha256_lf(b) if b else None
    return out


def results_and_resolver(v9: str | None):
    """(results frame, resolve fn) or (None, None) when either is unavailable (then nothing settles)."""
    root = _v9_root(v9)
    tn = root / "src" / "team_names.py" if root else None
    if tn is None or not tn.exists():
        return None, None
    spec = importlib.util.spec_from_file_location("v9_team_names_edge2", tn)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:                                                  # noqa: BLE001
        return None, None
    fn = getattr(mod, "resolve_result", None) or mod.resolve
    fs = sorted((cfg.BASE_DIR / "data" / "season_2026_27" / "team_match_stats").rglob("*.parquet"))
    if not fs:
        return None, fn
    r = pd.concat([pd.read_parquet(f, columns=["league", "match_date", "home_team", "away_team", "home_goals",
                                               "away_goals"]) for f in fs], ignore_index=True)
    r = r.dropna(subset=["home_goals", "away_goals"]).drop_duplicates(
        ["league", "match_date", "home_team", "away_team"], keep="last")
    r["md"] = pd.to_datetime(r["match_date"], errors="coerce").dt.normalize()
    return r, fn


def settle(rows: pd.DataFrame, results: pd.DataFrame | None, resolve) -> pd.Series:
    """y_a (side A happened) per row; NaN when not uniquely settled."""
    y = pd.Series(np.nan, index=rows.index, dtype=float)
    if results is None or resolve is None or rows.empty:
        return y
    by = {lg: g for lg, g in results.groupby("league")}
    names: dict = {}
    for i, r in rows.iterrows():
        g = by.get(str(r["league"]))
        if g is None:
            continue
        if r["league"] not in names:
            names[r["league"]] = sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str)))
        h, a = resolve(str(r["home_team"]), names[r["league"]]), resolve(str(r["away_team"]), names[r["league"]])
        if not h or not a:
            continue
        md = pd.Timestamp(str(r["match_date"])[:10])
        m = g[(g["home_team"] == h) & (g["away_team"] == a) & ((g["md"] - md).abs() <= pd.Timedelta(days=1))]
        m = m.drop_duplicates(["home_goals", "away_goals"])
        if len(m) != 1:
            continue
        hg, ag = float(m["home_goals"].iloc[0]), float(m["away_goals"].iloc[0])
        fam = str(r["market"])
        y[i] = float(hg > 0 and ag > 0) if fam == "BTTS" else float(hg + ag > LINE.get(fam, 99))
    return y


# ───────────────────────────── metrics ─────────────────────────────
def _boot(v: np.ndarray, days: np.ndarray, n: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u = np.unique(days)
    idx = [np.where(days == k)[0] for k in u]
    return np.array([v[np.concatenate([idx[k] for k in rng.integers(0, len(u), len(u))])].mean() for _ in range(n)])


def _bh(p: list) -> list:
    v = np.array([np.nan if x is None else x for x in p], float)
    ok = np.isfinite(v)
    q = np.full(len(v), np.nan)
    if ok.sum():
        w = v[ok]
        o = np.argsort(w)
        qq = w[o] * len(w) / (np.arange(len(w)) + 1)
        qq = np.minimum.accumulate(qq[::-1])[::-1]
        r = np.empty(len(w))
        r[o] = np.minimum(qq, 1)
        q[ok] = r
    return [None if not np.isfinite(x) else round(float(x), 4) for x in q]


def _ll(y, p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _slope(y, p) -> float | None:
    x = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    if len(y) < 20 or y.min() == y.max():
        return None
    a, b = 0.0, 1.0
    for _ in range(50):
        mu = 1 / (1 + np.exp(-(a + b * x)))
        w = mu * (1 - mu)
        g = np.array([np.sum(y - mu), np.sum((y - mu) * x)])
        h = np.array([[w.sum(), (w * x).sum()], [(w * x).sum(), (w * x * x).sum()]])
        try:
            s = np.linalg.solve(h, g)
        except np.linalg.LinAlgError:
            return None
        a, b = a + s[0], b + s[1]
        if np.abs(s).max() < 1e-9:
            break
    return round(float(b), 3)


def side_a(rows: pd.DataFrame, col: str) -> pd.Series:
    p = pd.to_numeric(rows[col], errors="coerce")
    is_a = rows["side"].astype(str).str.upper() == rows["market"].map(SIDE_A)
    return p.where(is_a, 1 - p)


def primary(s: pd.DataFrame) -> dict:
    y = s["y_a"].to_numpy(float)
    d = _ll(y, s["p_dec_a"].to_numpy(float)) - _ll(y, s["p_mkt_a"].to_numpy(float))
    days = pd.to_datetime(s["kickoff_utc"], utc=True).dt.tz_convert(None).dt.normalize().to_numpy()
    bs = _boot(d, days)
    db = (y - s["p_dec_a"].to_numpy(float)) ** 2 - (y - s["p_mkt_a"].to_numpy(float)) ** 2
    return {"ll_diff_mean": round(float(d.mean()), 6),
            "ll_diff_ci95": [round(float(np.percentile(bs, 2.5)), 6), round(float(np.percentile(bs, 97.5)), 6)],
            "p_one_sided": round(float((bs >= 0).mean()), 5),
            "brier_diff_mean": round(float(db.mean()), 6),
            "calibration_slope_decision": _slope(y, s["p_dec_a"].to_numpy(float)),
            "calibration_slope_market": _slope(y, s["p_mkt_a"].to_numpy(float))}


# ───────────────────────────── evaluation ─────────────────────────────
def prepare(shadow: pd.DataFrame, engine_version: str) -> pd.DataFrame:
    if shadow is None or shadow.empty:
        return pd.DataFrame()
    s = shadow[shadow["selection_engine_version"].astype(str) == engine_version].copy()
    s["_pts"] = pd.to_datetime(s["prediction_ts"], errors="coerce", utc=True)
    s["_ko"] = pd.to_datetime(s["kickoff_utc"], errors="coerce", utc=True)
    s = s[s["_pts"].notna() & s["_ko"].notna() & (s["_pts"] < s["_ko"])]
    # first sight, defensively (the writer already keeps the earliest row per key)
    s = s.sort_values("_pts", kind="mergesort").drop_duplicates(
        ["selection_engine_version", "fixture_id", "market"], keep="first")
    s["two_sided"] = s["market_source"].isin(TWO_SIDED)
    s["p_dec_a"] = side_a(s, "p_decision")
    s["p_mkt_a"] = side_a(s, "p_market_fair")
    return s


def evaluate(reg: dict, shadow: pd.DataFrame, results=None, resolve=None, hashes: dict | None = None,
             now: pd.Timestamp | None = None) -> list[dict]:
    now = now or pd.Timestamp.now(tz="UTC")
    eng = reg["engine"]
    start = pd.Timestamp(reg["forward_start"])
    drift = hashes is not None and (hashes.get("config_sha256_lf") != eng["config_sha256_lf"]
                                    or hashes.get("code_sha256_lf") != eng["code_sha256_lf"])
    s = prepare(shadow, eng["engine_version"])
    if len(s):
        s["y_a"] = settle(s, results, resolve)
    rows = []
    for h in reg["hypotheses"]:
        g = s[(s["model_type"] == h["track"]) & (s["market"] == h["market"])] if len(s) else s
        pre = g[g["_pts"] < start] if len(g) else g
        fwd = g[g["_pts"] >= start] if len(g) else g
        two = fwd[fwd["two_sided"]] if len(fwd) else fwd
        st = two[two["y_a"].notna()] if len(two) else two
        gw = int(st["_ko"].dt.isocalendar().apply(lambda r: (r["year"], r["week"]), axis=1).nunique()) if len(st) else 0
        sel = fwd[fwd["decision_state"].isin(["QUALIFIED", "STRONG"])] if len(fwd) else fwd
        r = {"id": h["id"], "track": h["track"], "market": h["market"],
             "min_n_settled_two_sided": h["min_n_settled_two_sided"], "min_gameweeks": h["min_gameweeks"],
             "PRE_REGISTRATION_NOT_COUNTED": int(len(pre)),
             "forward": {"logged": int(len(fwd)), "two_sided": int(len(two)), "settled_two_sided": int(len(st)),
                         "gameweeks": gw, "selections_QUALIFIED_STRONG": int(len(sel)),
                         "states": {k: int(v) for k, v in fwd["decision_state"].value_counts().items()} if len(fwd) else {}},
             "progress_pct": round(min(100.0, 100 * len(st) / h["min_n_settled_two_sided"]), 1),
             "metrics": None}
        if drift:
            r["status"] = "BLOCKED_CONFIG_CHANGED"
        elif now < start or len(fwd) == 0:
            r["status"] = "REGISTERED"
        elif len(st) >= h["min_n_settled_two_sided"] and gw >= h["min_gameweeks"]:
            r["status"] = "ELIGIBLE_FOR_REVIEW"
            r["metrics"] = primary(st)
            r["_n"] = len(st)
        else:
            r["status"] = "ACCRUING"
        rows.append(r)
    elig = [r for r in rows if r["status"] == "ELIGIBLE_FOR_REVIEW"]
    for r, q in zip(elig, _bh([r["metrics"]["p_one_sided"] for r in elig])):
        m = r["metrics"]
        m["bh_q_family"] = q
        sl = m["calibration_slope_decision"]
        hi, lo = m["ll_diff_ci95"][1], m["ll_diff_ci95"][0]
        n_min = r["min_n_settled_two_sided"]
        r["criteria_met"] = {
            "PROBABILITY_LAYER_SUPPORTED": bool(hi < 0 and q is not None and q <= 0.05 and sl is not None and 0.8 <= sl <= 1.2),
            "REJECT": bool(lo > 0),
            "FUTILITY": bool(r.pop("_n") >= 2 * n_min and m["ll_diff_mean"] >= 0),
            "note": "criteria report only - the decision is the owner's; never CONFIRMED"}
    for r in rows:
        r.pop("_n", None)
    return rows


def run(v9: str | None = None) -> dict:
    raw = REG.read_bytes()
    reg = json.loads(raw.decode("utf-8"))
    mutated = sha256_lf(raw) != REGISTRATION_SHA256
    shadow = load_shadow(v9)
    hashes = engine_hashes(v9, reg)
    results, resolve = results_and_resolver(v9)
    rows = evaluate(reg, shadow, results, resolve, hashes) if not mutated else []
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
           "registry": "registry/edge2_hypotheses_v1.json", "registration_sha256_lf": sha256_lf(raw),
           "registration_intact": not mutated, "forward_start": reg["forward_start"],
           "engine_version": reg["engine"]["engine_version"], "v9_engine_hashes_now": hashes,
           "engine_hashes_match_registration": (hashes.get("config_sha256_lf") == reg["engine"]["config_sha256_lf"]
                                                and hashes.get("code_sha256_lf") == reg["engine"]["code_sha256_lf"]),
           "shadow_rows_read": int(len(shadow)), "settlement_source_available": results is not None,
           "confirmed_assignable_here": False, "production_changed": "NO",
           "status_counts": pd.Series([r["status"] for r in rows]).value_counts().to_dict() if rows else {},
           "hypotheses": rows}
    if mutated:
        res["error"] = "REGISTRATION_MUTATED: registry content hash differs from the pinned value; nothing graded"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", default=None, help="local wowza-betting checkout (else cfg.V9_LOCAL, else raw HTTP)")
    a = ap.parse_args()
    r = run(a.v9)
    print({k: r[k] for k in ("registration_intact", "engine_hashes_match_registration", "shadow_rows_read",
                             "settlement_source_available", "status_counts")})
    for h in r["hypotheses"]:
        f = h["forward"]
        print(f"{h['id']:22s} logged {f['logged']:4d} two-sided {f['two_sided']:4d} settled {f['settled_two_sided']:4d}"
              f"/{h['min_n_settled_two_sided']} gw {f['gameweeks']}/{h['min_gameweeks']} {h['status']}")
