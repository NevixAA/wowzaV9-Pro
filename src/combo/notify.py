"""
Combo tip notifications from Pro (brief sections 83-85).
========================================================

WHY THIS EXISTS IN PRO AND NOWHERE ELSE

v9 owns the only existing Telegram sender and is frozen. v11 is forbidden from notifying at all
by invariant 4 ("no Telegram, no dashboard, no stakes"). So Pro is the only repository that can
carry this, and `PRO_MAY_NOTIFY` was flipped deliberately, by an explicit owner decision, to let
combo research reach a human. Everything else about Pro's posture is unchanged: it still never
bets, and `DEFAULT_DEPLOYMENT_MODE` is still RESEARCH.

RUN FREQUENCY IS NOT NOTIFICATION FREQUENCY

Section 83 is the rule this module exists to enforce. The generator may run every ten minutes on
a busy Saturday; that must not produce the same combo every ten minutes. A tip is sent only when
something MEANINGFUL changed, judged against a stored fingerprint of what was last sent.

WHAT COUNTS AS MEANINGFUL, AND WHY THESE NUMBERS

Every threshold below is a judgement, so each is named and justified rather than buried:

* `MIN_PROB_CHANGE_PP` = 2.0. The measured median absolute price move per poll is 0.05pp and the
  90th percentile beyond 24h is 0.00pp, so anything under ~2pp is inside the noise the collector
  sees constantly. Re-alerting on it would be alerting on nothing.
* `MIN_ODDS_IMPROVE_PCT` = 5.0. Below a 5% price improvement the change is smaller than the
  spread between books, so it is not reliably capturable.
* `RENOTIFY_AFTER_HOURS` = 12. A combo still valid a long time later is worth one reminder, not
  silence forever -- but not more than twice a day.
* A combo that DISAPPEARS is not announced. It would double the message volume to say nothing
  actionable, and the reader cannot act on a tip that no longer exists.

NO EXECUTABLE PRICE ON SAME-MATCH BUILDERS, AND THE MESSAGE SAYS SO

No bookmaker same-game-builder prices are collected anywhere, so a same-match combo carries a
FAIR price and no market price. Sending it without saying that would invite betting into an
unknown margin, which is exactly the error section 9 warns against. Cross-match multiples are
different: their legs are individually executable, so their combined odds are real.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pandas as pd

CALC_VERSION = "1.0.0"

STATE_FILE = Path(__file__).resolve().parents[2] / "output" / "combo_notified.json"

# Meaningful-change thresholds (section 85). Documented above; tune here, not inline.
MIN_PROB_CHANGE_PP = 2.0
MIN_ODDS_IMPROVE_PCT = 5.0
RENOTIFY_AFTER_HOURS = 12.0

# Never send a combo below this. A builder under it is a lottery ticket (section 30).
MIN_JOINT_PROB = 0.15
# Per leg count. Four likely legs multiply below any flat floor, so a single number silently
# banned every builder longer than a pair — the exact product this system exists to find.
# These are the joint probabilities of a plausible 4-leg builder (~4%) up through a pair (~15%).
MIN_JOINT_PROB_BY_LEGS = {2: 0.15, 3: 0.07, 4: 0.035, 5: 0.02}
# A leg above this is filler: it barely moves the joint probability or the price, but it is a
# real extra way to lose. Deliberately applied at NOTIFY time, not in the builder, so the
# candidate file keeps them for research.
MAX_LEG_PROB_FOR_TIP = 0.85
# ...and never above this either. The first version ranked purely by joint probability and its
# top pick was Over 1.5 + a 79% shots-on-target leg: 64% joint at 1.56 fair odds. Technically
# the most likely combo on the board and useless as a tip -- near-certainties at short prices
# are what you get when "most probable" is mistaken for "best".
MAX_JOINT_PROB = 0.55
MIN_FAIR_ODDS = 2.0

# THE RANKING. Section 28 warns against inventing a magical score, so this is one visible
# quantity with a stated rationale rather than a weighted blend of six.
#
# What this whole system is for is combos the market may misprice by multiplying marginals. The
# size of that error IS the opportunity, so rank by it directly:
#
#     independence_edge = fair_odds_if_independent / fair_odds_true - 1
#
# A book pricing O3.5+BTTS by multiplication asks 11.49 where the honest price is 5.97, so the
# edge is +92% and it tops the list. A pair that is genuinely near-independent scores ~0 and is
# never sent, however probable it is -- correctly, because we would be offering no insight.
MIN_INDEPENDENCE_EDGE = 0.15

MAX_PER_RUN = 6              # a burst of messages is itself a form of spam
# Give up after this many failed sends. Sending is all-or-nothing in practice — a missing token,
# a bad chat id or a Telegram outage fails every message identically — so retrying thousands of
# times only risks rate-limiting us for a problem no retry can fix.
MAX_SEND_FAILURES = 3


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)          # atomic, so a killed run cannot truncate the ledger


def fingerprint(row: pd.Series) -> str:
    """Stable identity for a combo (section 84). `combo_id` is already a hash of
    (fixture, legs), so it IS the fingerprint -- deliberately not re-derived here, or the two
    could drift apart and the same combo would notify twice under different identities."""
    return str(row.get("combo_id") or "")


def _first_num(row: pd.Series, *names: str) -> float | None:
    """First of `names` present on the row as a real number.

    Deliberately NOT `row.get(a) or row.get(b)`: that chain treats a legitimate 0.0 as missing,
    and it returns NaN rather than falling through when the first name exists but is null --
    which is how a column-name mismatch turns into a silent universal rejection instead of an
    error anyone would see.
    """
    for n in names:
        if n in row.index:
            v = pd.to_numeric(pd.Series([row.get(n)]), errors="coerce").iloc[0]
            if pd.notna(v):
                return float(v)
    return None


def independence_edge(row: pd.Series) -> float | None:
    """How badly a book pricing this by multiplying marginals would be wrong.

    Positive means independence pricing is too GENEROUS relative to the true joint -- the case
    worth a message. Returns None for cross-match multiples, where independence is the correct
    model and there is no correction to exploit.
    """
    pj = row.get("joint_probability")
    pi = row.get("independence_probability")
    if pj is None or pi is None or pd.isna(pj) or pd.isna(pi) or float(pj) <= 0 or float(pi) <= 0:
        return None
    return float(pj) / float(pi) - 1.0


def should_notify(row: pd.Series, state: dict, now: float) -> tuple[bool, str]:
    """(send?, reason). The whole anti-spam decision lives here so it is testable in isolation."""
    fid = fingerprint(row)
    if not fid:
        return False, "NO_FINGERPRINT"
    p = row.get("joint_probability")
    if p is None or pd.isna(p):
        return False, "BELOW_MIN_PROB"

    legs = [str(row.get(f"leg{i}_market") or "") for i in (1, 2, 3, 4, 5)]
    legs = [m for m in legs if m and m != "nan"]

    # A BUILDER IS NOT TWO WAYS OF SAYING THE SAME THING. "Over 2.5 goals + Both teams to score"
    # and "Over 3.5 + Away over 1.5" are restatements of one opinion about goals, and the huge
    # correlation adjustment they show is the tell, not the edge — it says the legs move together,
    # which is what makes them a single bet wearing two labels. The first live tips were all of
    # this shape and that is not what a builder is for.
    #
    # So a notifiable combo needs at least one leg from OUTSIDE the goal family: a player prop or
    # a team-card line. That is the whole point of a same-game builder — combining things a book
    # prices separately and correlates badly.
    # AT MOST ONE GOAL-FAMILY LEG. Over/under, BTTS, team goals and 1X2 are all read off the SAME
    # fitted score matrix, so two of them are not two opinions — they are one model's output
    # combined with itself, and the large correlation adjustment they produce is the symptom.
    # Requiring merely "one non-goal leg" was not enough: it still passed
    # "Over 3.5 + BTTS + Away over 1.5 + a card leg", which is the same objection with a
    # decoration. One scoreline view, then things the book prices separately.
    n_goal = sum(1 for m in legs
                 if not (m.startswith("player_") or m.startswith("teamcard")))
    if n_goal > 1:
        return False, "MULTIPLE_GOAL_LEGS_SAME_OPINION"
    if n_goal == len(legs):
        return False, "ALL_GOAL_LEGS_SAME_OPINION"

    # NO NEAR-CERTAIN FILLER. An 86% leg adds almost no probability and almost no price; it pads
    # the leg count and makes a combo look richer than it is, while adding a real way to lose.
    probs = [_first_num(row, f"leg{i}_p", f"leg{i}_model_p") for i in (1, 2, 3, 4, 5)]
    if any(v is not None and v > MAX_LEG_PROB_FOR_TIP for v in probs):
        return False, "LEG_TOO_CERTAIN_TO_ADD_ANYTHING"

    # THE FLOOR HAS TO SCALE WITH LEG COUNT. A flat 15% is right for two legs and impossible for
    # four: four genuinely likely legs multiply to well under it, so the requested product — a
    # handful of probable things whose COMBINED odds are worth taking — was being rejected as a
    # lottery ticket. Measured: combos containing a player leg averaged 6.8% joint against a 15%
    # floor, so 140 of 144 were refused and 4 survived.
    n = len(legs) or int(row.get("n_legs") or 2)
    floor = MIN_JOINT_PROB_BY_LEGS.get(n, MIN_JOINT_PROB_BY_LEGS[max(MIN_JOINT_PROB_BY_LEGS)])
    if float(p) < floor:
        return False, "BELOW_MIN_PROB"

    if float(p) > MAX_JOINT_PROB:
        return False, "TOO_PROBABLE_TO_BE_A_TIP"
    # THE TWO BUILDERS SPEAK DIFFERENT VOCABULARIES and this gate silently arbitrated between
    # them. `builder.same_match` writes `fair_combo_odds`; `match_picture.build` -- the N-leg
    # builder that produces everything the pipeline actually generates -- writes `fair_odds`.
    # Reading only the first name meant every match_picture row resolved to NaN and was rejected
    # as ODDS_TOO_SHORT: 6,318 of 6,360 candidates suppressed for having no price, while their
    # fair odds ranged 1.8-4.51. Nothing errored and the summary read like a strict filter doing
    # its job. Accept every name a builder emits, exactly as the odds layer normalises sources.
    fair = _first_num(row, "fair_combo_odds", "fair_odds", "combined_odds")
    if fair is None or pd.isna(fair) or float(fair) < MIN_FAIR_ODDS:
        return False, "ODDS_TOO_SHORT"
    edge = independence_edge(row)
    if edge is not None and edge < MIN_INDEPENDENCE_EDGE:
        return False, "NO_INDEPENDENCE_EDGE"

    prev = state.get(fid)
    if prev is None:
        return True, "NEW"

    # Tier upgrades and price improvements are the events worth interrupting someone for.
    prev_p = prev.get("joint_probability")
    if prev_p is not None:
        dpp = 100.0 * (float(p) - float(prev_p))
        if dpp >= MIN_PROB_CHANGE_PP:
            return True, f"PROB_UP_{dpp:+.1f}pp"
        if dpp <= -MIN_PROB_CHANGE_PP:
            # A materially WORSE combo is worth one message: it invalidates the earlier tip.
            return True, f"PROB_DOWN_{dpp:+.1f}pp"

    odds = _first_num(row, "builder_odds", "fair_combo_odds", "fair_odds", "combined_odds")
    prev_odds = prev.get("odds")
    if odds and prev_odds:
        imp = 100.0 * (float(odds) / float(prev_odds) - 1.0)
        if imp >= MIN_ODDS_IMPROVE_PCT:
            return True, f"ODDS_UP_{imp:+.1f}%"

    # `is not None`, NOT truthiness: a timestamp of 0 is falsy, so `if last` silently disabled
    # the reminder for any epoch-zero state. Real timestamps are large so production would have
    # worked, which is exactly why it would never have been noticed.
    last = prev.get("last_notified_ts")
    if last is not None and (now - float(last)) / 3600.0 >= RENOTIFY_AFTER_HOURS:
        return True, "REMINDER"
    return False, "UNCHANGED"


def format_combo(row: pd.Series) -> str:
    """One Telegram message. Plain text with light Markdown; no credentials, ever."""
    same_match = bool(row.get("match"))
    head = "🎯 *Bet Builder* (same match)" if same_match else "🔗 *Multi* (different matches)"
    lines = [head, ""]
    if same_match:
        lines.append(f"*{row.get('match')}*")
        lines.append(f"_{row.get('league')} · {row.get('match_date')}_")
        lines.append("")
        # EVERY leg, not the first two. This was hardcoded to legs 1 and 2 because the original
        # builder only ever made pairs; `match_picture` builds up to five, so a four-leg builder
        # displayed its first two legs beside the four-leg joint probability -- a message that
        # misrepresents which bet it is describing. The count comes from the data, not a constant.
        #
        # `leg{i}_p` is match_picture's name and `leg{i}_model_p` is same_match's. Reading only
        # the latter is why every leg printed `0%`: .get returned the default 0 for a name that
        # was never there, so a real 47% leg rendered as 0% and nothing raised.
        for i in (1, 2, 3, 4, 5):
            label = row.get(f"leg{i}_label")
            if label is None or (isinstance(label, float) and pd.isna(label)):
                continue
            lp = _first_num(row, f"leg{i}_p", f"leg{i}_model_p")
            pct = f"{lp:.0%}" if lp is not None else "—"
            lines.append(f"{i}️⃣ {label}   `{pct}`")
    else:
        for i in (1, 2, 3):
            if row.get(f"fixture_{i}"):
                lines.append(f"{i}️⃣ {row.get(f'fixture_{i}')}")
                lines.append(f"    {row.get(f'market_{i}')}  @ `{row.get(f'odds_{i}')}`")
    lines.append("")
    p = row.get("joint_probability") or row.get("conservative_joint_probability")
    lines.append(f"Joint probability: *{float(p):.1%}*")
    dr = row.get("dependency_ratio")
    if dr and float(dr) == float(dr):
        # The reason this system exists: independence would have priced it differently.
        lines.append(f"Correlation adj: ×{float(dr):.2f} vs independence")
    ie = independence_edge(row)
    if ie is not None and row.get("independence_fair_odds"):
        lines.append(f"Naive (independent) pricing would ask "
                     f"*{row.get('independence_fair_odds')}* — {ie:+.0%} too generous")

    if row.get("combined_odds"):
        lines.append(f"Combined odds: *{row.get('combined_odds')}*")
        ev = row.get("conservative_ev")
        if ev is not None and ev == ev:
            lines.append(f"Conservative EV: `{float(ev):+.1%}`")
        lines.append("")
        lines.append("_Legs are individually executable._")
    else:
        fair = _first_num(row, "fair_combo_odds", "fair_odds")
        lines.append(f"Fair odds: *{fair:.2f}*" if fair is not None else "Fair odds: _unavailable_")
        lines.append("")
        # Stated every time. A fair price is not a price you can bet.
        lines.append("⚠️ _No bookmaker builder price is collected, so this is a FAIR estimate, "
                     "not an executable one. The book adds its own correlation margin._")
    lines.append("")
    lines.append("_PAPER · research only · Pro sends no stakes_")
    return "\n".join(lines)


def send(text: str, *, timeout: int = 20) -> tuple[bool, str]:
    """Post to Telegram. Credentials come from the environment and are never logged."""
    import requests

    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        # Names only -- never the values.
        return False, "TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text,
                                "parse_mode": "Markdown",
                                "disable_web_page_preview": True},
                          timeout=timeout)
        if r.status_code != 200:
            # Response bodies can echo the request, so the body is never reported -- but the
            # STATUS CODE alone is diagnostic here and was being wasted. Telegram distinguishes
            # the two failures precisely, and knowing which one you have is the whole fix:
            #   404 -> the TOKEN is not recognised (wrong or truncated). A real token is
            #          "<digits>:<secret>"; pasting only the part after the colon gives exactly
            #          this, which is what happened on the first live run.
            #   400 -> token fine, the CHAT_ID is wrong ("chat not found").
            #   403 -> token and chat fine, but the bot was blocked or removed from the chat.
            #   429 -> rate limited; the circuit breaker above is what keeps this from escalating.
            hint = {404: "TELEGRAM_TOKEN not recognised — check it is the FULL token "
                         "(digits, colon, secret) with no angle brackets",
                    400: "either TELEGRAM_CHAT_ID is wrong (chat not found / minus sign "
                         "dropped) or the message failed to parse — see the description",
                    403: "bot is blocked or not a member of that chat",
                    429: "rate limited by Telegram"}.get(r.status_code)
            # TELEGRAM'S OWN `description` IS THE DIAGNOSIS AND SUPPRESSING IT COST TWO ROUND
            # TRIPS. "HTTP 400" alone cannot distinguish "chat not found" from "can't parse
            # entities" — opposite fixes — so the run said only that something was wrong. The
            # token is in the URL PATH, never in the response body, so echoing the description is
            # safe; it is still length-capped and passed through a redactor in case a future
            # error quotes the request back at us.
            desc = ""
            try:
                desc = str((r.json() or {}).get("description", ""))[:160]
                desc = re.sub(r"\d{6,}:[A-Za-z0-9_-]{20,}", "<redacted>", desc)
            except Exception:                                    # noqa: BLE001
                pass
            return False, (f"HTTP {r.status_code}" + (f" — {hint}" if hint else "")
                           + (f" | Telegram says: {desc}" if desc else ""))
        return True, "sent"
    except Exception as e:                                   # noqa: BLE001
        return False, f"{type(e).__name__}"


def run(candidates: pd.DataFrame, *, dry_run: bool = True,
        max_per_run: int = MAX_PER_RUN) -> dict:
    """Evaluate every candidate, send only what changed meaningfully, record what was sent.

    `dry_run=True` is the DEFAULT on purpose: a notifier whose safe mode must be opted into is
    one message away from spamming a channel during development.
    """
    import config.pro_config as cfg

    state = _load_state()
    now = time.time()
    out = {"evaluated": 0, "eligible": 0, "sent": 0, "suppressed": 0,
           "dry_run": dry_run, "reasons": {}, "may_notify": bool(cfg.PRO_MAY_NOTIFY)}
    if candidates is None or candidates.empty:
        return out

    d = candidates.copy()
    pcol = "joint_probability" if "joint_probability" in d.columns else "conservative_joint_probability"
    d = d[pd.to_numeric(d[pcol], errors="coerce").notna()]
    # Ranked by the mispricing we can point at, not by how likely the combo is.
    d["_edge"] = d.apply(independence_edge, axis=1)
    d = d.sort_values(["_edge", pcol], ascending=[False, False])
    sent_fixtures: set[str] = set()

    for _, row in d.iterrows():
        out["evaluated"] += 1
        ok, why = should_notify(row, state, now)
        out["reasons"][why] = out["reasons"].get(why, 0) + 1
        if not ok:
            out["suppressed"] += 1
            continue
        out["eligible"] += 1
        if out["sent"] >= max_per_run:
            continue
        # ONE TIP PER FIXTURE PER RUN. MAX_PER_RUN capped the total but nothing capped the
        # spread, and ranking by correlation edge concentrates on whichever fixture has the most
        # legs available — so a single Bundesliga 2 match with four priced players took all six
        # slots and the board went out as six variations of one game. Six near-identical tips are
        # not six tips; they are one opinion with the reader left to pick. The best combo per
        # fixture goes; the rest wait for the next run, and `d` is already sorted so the first one
        # seen for a fixture IS its best.
        fx = str(row.get("fixture_key") or row.get("match") or "")
        if fx and fx in sent_fixtures:
            out["suppressed"] += 1
            out["reasons"]["ANOTHER_TIP_ALREADY_SENT_FOR_THIS_MATCH"] = \
                out["reasons"].get("ANOTHER_TIP_ALREADY_SENT_FOR_THIS_MATCH", 0) + 1
            continue
        if dry_run or not cfg.PRO_MAY_NOTIFY:
            continue
        good, detail = send(format_combo(row))
        if not good:
            # A SWALLOWED SEND FAILURE IS THE WORST OUTCOME AVAILABLE. This was a bare `continue`,
            # so a run with 2,986 eligible combos and no Telegram credentials reported
            # `sent: 0` with no reason and exited green — indistinguishable from "nothing met the
            # bar". Record the count AND the reason so the caller can fail loudly.
            out["send_failed"] = out.get("send_failed", 0) + 1
            out.setdefault("send_errors", {})
            out["send_errors"][detail] = out["send_errors"].get(detail, 0) + 1
            # CIRCUIT BREAKER. `sent` only increments on success, so MAX_PER_RUN never engages
            # when sending is broken: a run with 2,986 eligible combos attempted 2,986 sends.
            # Harmless with no credentials (send returns before any HTTP call) but with a BAD
            # token that is 2,986 requests at Telegram, which is how an outage becomes a ban.
            # Whatever is wrong with the first few is wrong with all of them.
            if out["send_failed"] >= MAX_SEND_FAILURES:
                out["aborted"] = f"stopped after {MAX_SEND_FAILURES} consecutive send failures"
                break
            continue
        out["sent"] += 1
        if fx:
            sent_fixtures.add(fx)
        fid = fingerprint(row)
        prev = state.get(fid, {})
        state[fid] = {
            "first_seen_ts": prev.get("first_seen_ts", now),
            "last_seen_ts": now,
            "last_notified_ts": now,
            "notify_count": int(prev.get("notify_count", 0)) + 1,
            "joint_probability": float(row.get(pcol)),
            "odds": row.get("builder_odds") or row.get("combined_odds"),
            "reason": why,
        }
    if not dry_run and cfg.PRO_MAY_NOTIFY:
        _save_state(state)
    return out
