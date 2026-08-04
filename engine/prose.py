"""The prose lanes: the LLM narrates, the arithmetic decides.

Third sanctioned use of a language model, after proposing (the hypothesis
lab) and nothing else. The recorded WON'T stands untouched — no model
output here is ever a probability, a stake, or a gate. These lanes write
PROSE about numbers the arithmetic already produced:

  * **The nightly postmortem** — one call after the settle pass reads the
    night's graded picks across every sport and writes the bettor's-diary
    column templates can't: what happened, in plain English.
  * **The weekly brief** — one call a week digests what the learning
    ladder actually did (dials moved, markets self-closed, patterns found,
    each sport's week) into an analyst's note.
  * **The triage bench** (CLI only) — reads the hypothesis lab's watchlist
    and drafts an implementable spec for the next miner dimension.

Every sport is covered STRUCTURALLY, not hopefully: the packs list the
sports with activity, and validation back-fills a deterministic line from
the pack's own numbers for any sport the model skipped — so MLB, NBA,
WNBA, NFL, CFB and UFC each always have their paragraph, model mood
notwithstanding.

The cap: the automatic lanes check the spend ledger first and stand down
for the rest of the month once it passes QELLYS_LLM_CAP_USD (default
$5.00). The worst case is bounded by arithmetic, not discipline. Manual
CLI runs are a human decision and only warn.

Same plumbing as the lab: raw HTTP against /v1/messages (stdlib-only
doctrine), structured outputs so the reply always parses, every call on
the spend ledger from the moment the API responds.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from . import hypotheses as hyp

POSTMORTEM_PATH = Path("data/models/postmortems.json")
BRIEF_PATH = Path("data/models/briefs.json")
KEEP_POSTMORTEMS = 30
KEEP_BRIEFS = 12
BRIEF_EVERY_DAYS = 7
DEFAULT_CAP_USD = 5.00
# A ceiling, not a spend: billing is on tokens actually produced. 2048 was
# a real-world truncation — the model THINKS before it writes, thinking
# counts against max_tokens, and the triage bench's three specs came back
# as JSON cut off mid-string. Headroom costs nothing; truncation costs a
# billed call that returns garbage.
MAX_TOKENS = 8192
MAX_PACK_CHARS = 12000
#: The diary narrates OUR bets. The measurement buckets (stale-line
#: sampler, form sampler) are experiments, not picks, and narrating them
#: as wagers would misstate what the operation actually risked.
DIARY_CATEGORIES = ("main", "longshot", "parlay")


class ProseUnavailable(RuntimeError):
    """The lane can't run — no key, no data, or the API said no."""


# --- the cap -----------------------------------------------------------------
def cap_usd() -> float:
    try:
        return float(os.environ.get("QELLYS_LLM_CAP_USD") or DEFAULT_CAP_USD)
    except (TypeError, ValueError):
        return DEFAULT_CAP_USD


def month_spent() -> float:
    return float(hyp.llm_spend_report()["month_usd"])


def under_cap() -> bool:
    return month_spent() < cap_usd()


def _model() -> str:
    from . import secrets
    secrets.load_local_secrets()
    return (os.environ.get("QELLYS_PROSE_MODEL")
            or os.environ.get("QELLYS_LLM_MODEL") or hyp.DEFAULT_MODEL)


# --- the call ----------------------------------------------------------------
def _call(system: str, prompt: str, schema: dict, kind: str,
          timeout: float = 180.0) -> dict:
    """One structured-output request, on the spend ledger before parsing."""
    key = hyp._api_key()
    if not key:
        raise ProseUnavailable(
            "no ANTHROPIC_API_KEY — add it to secrets.local")
    body = {
        "model": _model(),
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema",
                                     "schema": schema}},
    }
    req = urllib.request.Request(
        hyp.API_URL, data=json.dumps(body).encode(),
        headers={"x-api-key": key,
                 "anthropic-version": hyp.API_VERSION,
                 "content-type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode())["error"]["message"]
        except Exception:                          # noqa: BLE001
            msg = str(e)
        raise ProseUnavailable(f"API error {e.code}: {msg}") from e
    except Exception as e:                         # noqa: BLE001
        raise ProseUnavailable(f"network: {e}") from e
    # Billed whether or not the reply parses — meter first.
    try:
        hyp.log_llm_spend(payload.get("usage") or {}, body["model"], kind=kind)
    except Exception:                              # noqa: BLE001
        pass
    stop = payload.get("stop_reason")
    if stop == "refusal":
        raise ProseUnavailable("the model declined the request")
    # Truncation BEFORE parsing: a reply cut off at the ceiling is broken
    # JSON, and reporting it as "unparseable" sends the reader debugging
    # the schema when the fix is the ceiling. (Learned from a real run.)
    if stop == "max_tokens":
        raise ProseUnavailable(
            "reply truncated at max_tokens — the ceiling is too low for "
            "this prompt")
    text = next((b.get("text") for b in payload.get("content") or []
                 if b.get("type") == "text"), None)
    if not text:
        raise ProseUnavailable(f"no text in response (stop={stop})")
    try:
        return json.loads(text)
    except ValueError as e:
        raise ProseUnavailable(f"unparseable reply: {e}") from e


# --- shared shape: headline / overall / one note per sport -------------------
SCHEMA_PROSE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "overall", "by_sport"],
    "properties": {
        "headline": {"type": "string"},
        "overall": {"type": "string"},
        "by_sport": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "required": ["sport", "note"],
                      "properties": {"sport": {"type": "string"},
                                     "note": {"type": "string"}}}},
    },
}

SYSTEM_NIGHT = """You write the nightly postmortem column for a sports \
betting analytics site's public track-record page. You are handed the \
night's graded picks as JSON — results the site's own arithmetic already \
produced. Your job is narrative, nothing else.

Rules, all hard:
- Use ONLY numbers present in the JSON. Never invent a stat, a score, a \
price, or a reason the data does not carry.
- Honest diary voice: losses are losses. No hype, no hedging, no advice, \
no predictions, no "lock" talk. Note when a loss looks like variance on a \
fine price and when the model's stated probability just missed.
- Write one short note per sport that appears in the pack (its key in \
by_sport), plus a 2-4 sentence overall paragraph and a headline under \
80 characters.
- Plain English a casual reader follows; a sharp reader should find \
nothing to object to."""

SYSTEM_WEEK = """You write the weekly model brief for a sports betting \
analytics site — the analyst's note explaining what the site's \
self-learning system actually did this week. You are handed JSON \
containing each sport's week and season record and the learning ladder's \
current state (calibration temperatures, recency dials, player-memory \
adoptions, loss patterns, hypothesis verdicts) — all computed by the \
site's own arithmetic.

Rules, all hard:
- Use ONLY facts in the JSON. Never invent a number or a cause.
- The learning is per sport; write one short note per sport listed in \
the pack, plus a 3-5 sentence overall paragraph and a headline under 80 \
characters. A sport where nothing changed gets one honest sentence.
- Explain plainly what a change MEANS for the board (a self-closed \
market hard-passes; an adopted dial reweights recent form) without \
promising results. No advice, no predictions."""


def _ensure_coverage(out: dict, pack_sports: list[str],
                     fallback) -> dict[str, str]:
    """Every sport in the pack gets a note — the model's mood is not
    allowed to decide coverage. Off-pack sports the model added are
    dropped; missing ones are back-filled from the pack's own numbers."""
    got = {}
    for row in (out.get("by_sport") or []):
        if isinstance(row, dict) and row.get("sport") in pack_sports:
            got[row["sport"]] = str(row.get("note") or "")[:600]
    return {sp: (got.get(sp) or str(fallback(sp))[:600])
            for sp in pack_sports}


def _load_list(path: Path) -> list:
    try:
        rows = json.loads(path.read_text()) if path.is_file() else []
        return rows if isinstance(rows, list) else []
    except (ValueError, OSError):
        return []


def _save_list(rows: list, path: Path, keep: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows[-keep:], indent=1))


# --- lane one: the nightly postmortem ----------------------------------------
def diary_date(lconn) -> str | None:
    """The most recent ISO date with graded diary picks.

    `MAX(date)` alone would be a trap: NFL journals under week labels
    ("2026-W1"), and "W" string-sorts above every digit — the postmortem
    would chase a label that is not a night. Weekly football belongs to
    the weekly brief; the diary narrates nights.
    """
    r = lconn.execute(
        "SELECT MAX(date) FROM bets WHERE status IN "
        "('won','lost','push','void') AND category IN (?,?,?) "
        "AND date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'",
        DIARY_CATEGORIES).fetchone()
    return r[0] if r and r[0] else None


def postmortem_pack(lconn, date: str) -> dict:
    rows = [dict(r) for r in lconn.execute(
        "SELECT sport, player, market, side, line, odds, status, "
        "stake_units, pnl_units, hit_prob, category FROM bets "
        "WHERE date=? AND status IN ('won','lost','push','void') "
        "AND category IN (?,?,?)", (date, *DIARY_CATEGORIES))]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["sport"], []).append(r)
    summary = {}
    for sp, v in sorted(by.items()):
        picks = sorted(v, key=lambda b: -abs(b.get("pnl_units") or 0))[:12]
        summary[sp] = {
            "graded": len(v),
            "won": sum(1 for b in v if b["status"] == "won"),
            "lost": sum(1 for b in v if b["status"] == "lost"),
            "pushed": sum(1 for b in v if b["status"] == "push"),
            "voided": sum(1 for b in v if b["status"] == "void"),
            "net_units": round(sum(b.get("pnl_units") or 0 for b in v), 2),
            "picks": [{k: b.get(k) for k in
                       ("player", "market", "side", "line", "odds", "status",
                        "stake_units", "pnl_units", "hit_prob", "category")}
                      for b in picks],
        }
    pack = {"date": date, "sports": sorted(by), "by_sport": summary}
    # Trim the biggest sport's pick lists until the pack fits the cap.
    while len(json.dumps(pack)) > MAX_PACK_CHARS:
        big = max(summary, key=lambda s: len(summary[s]["picks"]))
        if not summary[big]["picks"]:
            break
        summary[big]["picks"].pop()
    return pack


def _night_fallback(pack: dict):
    def fb(sport: str) -> str:
        s = pack["by_sport"].get(sport) or {}
        return (f"{s.get('won', 0)}-{s.get('lost', 0)} on the night, "
                f"{s.get('net_units', 0):+.2f}u across {s.get('graded', 0)} "
                f"graded pick(s).")
    return fb


def write_postmortem(lconn, date: str | None = None,
                     path: Path | str | None = None) -> dict:
    """The paid step: one call, one dated diary entry. Idempotence and the
    cap live in nightly(); this writes when asked."""
    p = Path(path if path is not None else POSTMORTEM_PATH)
    date = date or diary_date(lconn)
    if not date:
        raise ProseUnavailable("no graded picks on any night yet")
    pack = postmortem_pack(lconn, date)
    if not pack["sports"]:
        raise ProseUnavailable(f"nothing graded on {date}")
    out = _call(SYSTEM_NIGHT, json.dumps(pack), SCHEMA_PROSE, "postmortem")
    entry = {
        "date": date,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "model": _model(),
        "headline": str(out.get("headline") or "")[:120],
        "overall": str(out.get("overall") or "")[:1500],
        "by_sport": _ensure_coverage(out, pack["sports"],
                                     _night_fallback(pack)),
    }
    rows = [r for r in _load_list(p) if r.get("date") != date]
    rows.append(entry)
    rows.sort(key=lambda r: r.get("date") or "")
    _save_list(rows, p, KEEP_POSTMORTEMS)
    return entry


def nightly(lconn, log=print, path: Path | str | None = None) -> str:
    """The automatic lane: guarded, idempotent, capped. Returns a status
    word rather than raising — the settle pass must never fail on prose."""
    p = Path(path if path is not None else POSTMORTEM_PATH)
    if not hyp._api_key():
        return "no-key"
    date = diary_date(lconn)
    if not date:
        return "nothing-graded"
    if any(r.get("date") == date for r in _load_list(p)):
        return "already"
    if not under_cap():
        log(f"  prose: paused — ${month_spent():.2f} of the "
            f"${cap_usd():.2f} monthly LLM cap is spent")
        return "capped"
    try:
        e = write_postmortem(lconn, date, p)
        log(f"  prose: nightly postmortem written for {e['date']} "
            f"({', '.join(sorted(e['by_sport']))})")
        return f"done:{e['date']}"
    except ProseUnavailable as exc:
        log(f"  ⚠️  postmortem skipped: {exc}")
        return "failed"


# --- lane two: the weekly model brief ----------------------------------------
def brief_pack(lconn) -> dict:
    from . import ledger
    from . import losspatterns as lp
    week_ago = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
    per = {}
    for sp in ledger.TRACKED_SPORTS:
        rows = [dict(r) for r in lconn.execute(
            "SELECT date, status, pnl_units FROM bets WHERE sport=? AND "
            "status IN ('won','lost','push') AND category IN (?,?,?)",
            (sp, *DIARY_CATEGORIES))]
        wk = [r for r in rows if str(r.get("date") or "") >= week_ago]
        per[sp] = {
            "season": {"graded": len(rows),
                       "won": sum(1 for r in rows if r["status"] == "won"),
                       "lost": sum(1 for r in rows if r["status"] == "lost"),
                       "net_units": round(sum(r.get("pnl_units") or 0
                                              for r in rows), 2)},
            "this_week": {"graded": len(wk),
                          "won": sum(1 for r in wk if r["status"] == "won"),
                          "lost": sum(1 for r in wk if r["status"] == "lost"),
                          "net_units": round(sum(r.get("pnl_units") or 0
                                                 for r in wk), 2)},
        }
    from .ledger import _self_tuning_block
    st = _self_tuning_block()
    hl_store = hyp.load()
    ladder = {
        "calibration": (st.get("markets") or [])[:20],
        "self_closed": st.get("closed") or [],
        "recency_dials": (st.get("weights") or [])[:20],
        "player_memory": (st.get("players") or [])[:20],
        "loss_patterns": [
            {k: f.get(k) for k in ("sport", "market", "dim", "value",
                                   "status", "reading")}
            for f in (lp.load().get("findings") or [])[:12]],
        "hypotheses": [
            {k: h.get(k) for k in ("sport", "market", "claim", "status",
                                   "action", "reading")}
            for h in (hl_store.get("hypotheses") or [])[:12]],
    }
    pack = {"week_of": _dt.date.today().isoformat(),
            "sports": list(ledger.TRACKED_SPORTS),
            "by_sport": per, "ladder": ladder}
    for key in ("player_memory", "recency_dials", "calibration",
                "loss_patterns", "hypotheses"):
        while len(json.dumps(pack)) > MAX_PACK_CHARS and ladder[key]:
            ladder[key].pop()
    return pack


def _week_fallback(pack: dict):
    def fb(sport: str) -> str:
        s = (pack["by_sport"].get(sport) or {})
        wk, se = s.get("this_week") or {}, s.get("season") or {}
        if not (se.get("graded") or 0):
            return "Nothing journaled yet — its learning switches on with " \
                   "its first graded picks."
        return (f"{wk.get('won', 0)}-{wk.get('lost', 0)} this week "
                f"({wk.get('net_units', 0):+.2f}u); "
                f"{se.get('won', 0)}-{se.get('lost', 0)} on the season.")
    return fb


def write_brief(lconn, path: Path | str | None = None) -> dict:
    p = Path(path if path is not None else BRIEF_PATH)
    pack = brief_pack(lconn)
    out = _call(SYSTEM_WEEK, json.dumps(pack), SCHEMA_PROSE, "brief")
    entry = {
        "week_of": pack["week_of"],
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "model": _model(),
        "headline": str(out.get("headline") or "")[:120],
        "overall": str(out.get("overall") or "")[:1800],
        "by_sport": _ensure_coverage(out, pack["sports"],
                                     _week_fallback(pack)),
    }
    rows = _load_list(p)
    rows.append(entry)
    _save_list(rows, p, KEEP_BRIEFS)
    return entry


def weekly(lconn, log=print, path: Path | str | None = None) -> str:
    """Automatic cadence: one brief per BRIEF_EVERY_DAYS. Same guard order
    as nightly() — and the same promise to never raise into the settle."""
    p = Path(path if path is not None else BRIEF_PATH)
    if not hyp._api_key():
        return "no-key"
    graded = lconn.execute(
        "SELECT COUNT(*) FROM bets WHERE status IN ('won','lost','push')"
    ).fetchone()[0]
    if not graded:
        return "nothing-graded"
    rows = _load_list(p)
    if rows:
        try:
            last = _dt.date.fromisoformat(rows[-1].get("week_of") or "")
            if (_dt.date.today() - last).days < BRIEF_EVERY_DAYS:
                return "already"
        except ValueError:
            pass
    if not under_cap():
        log(f"  prose: paused — ${month_spent():.2f} of the "
            f"${cap_usd():.2f} monthly LLM cap is spent")
        return "capped"
    try:
        e = write_brief(lconn, p)
        log(f"  prose: weekly model brief written ({e['week_of']})")
        return f"done:{e['week_of']}"
    except ProseUnavailable as exc:
        log(f"  ⚠️  weekly brief skipped: {exc}")
        return "failed"


# --- the lab's weekly propose, automated under the same guards ---------------
LAB_EVERY_DAYS = 7


def weekly_lab(lconn, log=print) -> str:
    """One paid propose per week, self-run: without it the lab only
    re-tests old hypotheses and never gets new ones — a recurring manual
    chore, which is exactly the thing this operation does not keep. Same
    guard order and the same promise as the other automatic lanes: key,
    fresh-enough store, cap, and never a raise into the settle pass."""
    if not hyp._api_key():
        return "no-key"
    graded = lconn.execute(
        "SELECT COUNT(*) FROM bets WHERE status IN ('won','lost','push')"
    ).fetchone()[0]
    if not graded:
        return "nothing-graded"
    store = hyp.load()
    try:
        last = _dt.date.fromisoformat(store.get("last_proposed") or "")
        if (_dt.date.today() - last).days < LAB_EVERY_DAYS:
            return "already"
    except ValueError:
        pass
    if not under_cap():
        log(f"  prose: lab propose paused — ${month_spent():.2f} of the "
            f"${cap_usd():.2f} monthly LLM cap is spent")
        return "capped"
    try:
        out = hyp.propose(lconn)
        n = len(out.get("hypotheses") or [])
        log(f"  hypothesis lab: weekly propose ran — {n} hypothesis(es) "
            f"in the store, tribunal applied")
        return "done"
    except hyp.HypothesisUnavailable as exc:
        log(f"  ⚠️  weekly propose skipped: {exc}")
        return "failed"


# --- lane three: the triage bench (CLI only, never automatic) ----------------
SCHEMA_TRIAGE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {"proposals": {
        "type": "array",
        "items": {"type": "object", "additionalProperties": False,
                  "required": ["dimension", "bands", "data_needed",
                               "source", "rationale"],
                  "properties": {"dimension": {"type": "string"},
                                 "bands": {"type": "string"},
                                 "data_needed": {"type": "string"},
                                 "source": {"type": "string"},
                                 "rationale": {"type": "string"}}}}},
}

SYSTEM_TRIAGE = """You are drafting engineering specs for a sports betting \
analytics engine's blind-spot miner. The miner slices a graded-bet journal \
by fixed dimensions (currently: side, odds band, stated-probability band, \
horizon, book) under false-discovery control. The hypothesis lab's \
watchlist (in the JSON) names ideas that CANNOT be tested yet because no \
journaled dimension carries them.

Draft at most 3 concrete specs, each turning one watchlist idea into a \
new miner dimension: a short dimension name, the discrete bands it would \
take, exactly what must be recorded on each bet at pick time, where that \
data would come from given the site's existing feeds (listed in the \
JSON), and why the slice could plausibly separate wins from losses. \
Favor data the site already touches. You are proposing measurements, \
never probabilities."""


def triage_pack(lconn) -> dict:
    from . import ledger
    from . import losspatterns as lp
    watch = hyp.load().get("watchlist") or []
    markets = [dict(r) for r in lconn.execute(
        "SELECT sport, market, COUNT(*) n FROM bets WHERE status IN "
        "('won','lost') GROUP BY sport, market ORDER BY n DESC")][:20]
    return {
        "watchlist": watch,
        "current_dimensions": list(lp.DIMS) if hasattr(lp, "DIMS")
        else ["side", "odds", "prob", "horizon", "book"],
        "journaled_markets": markets,
        "sports": list(ledger.TRACKED_SPORTS),
        "existing_feeds": [
            "The Odds API (prices, books, line history)",
            "MLB Stats API (boxscores, lineups, parks, weather via "
            "Open-Meteo)", "nflverse (NFL players, depth charts)",
            "ESPN scoreboards (NBA/WNBA/CFB)", "own ingested game logs "
            "and odds snapshots"],
    }


def triage(lconn) -> dict:
    pack = triage_pack(lconn)
    if not pack["watchlist"]:
        raise ProseUnavailable(
            "the hypothesis lab has no watchlist yet — run "
            "`python3 hypotheses.py` first")
    return _call(SYSTEM_TRIAGE, json.dumps(pack), SCHEMA_TRIAGE, "triage")


# --- what the website reads (store-only, never a call) -----------------------
def site_block() -> dict:
    """The record.json block. Reads stores and the spend ledger; the export
    path must never be able to spend a token."""
    pms = _load_list(POSTMORTEM_PATH)
    briefs = _load_list(BRIEF_PATH)
    return {
        "postmortem": pms[-1] if pms else None,
        "brief": briefs[-1] if briefs else None,
        "cap_usd": cap_usd(),
        "month_usd": round(month_spent(), 2),
        "capped": not under_cap(),
    }
