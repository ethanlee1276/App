"""The hypothesis lab: the LLM proposes, the arithmetic disposes.

The recorded WON'T stands — a language model never sets a probability,
because it cannot be re-run, swept, or audited. What it CAN do safely is
the one thing the rest of the ladder cannot: creative hypothesis
generation. The blind-spot miner tests every single dimension of the
record (side, price band, stated-probability band, horizon, book) but
never their INTERSECTIONS — "unders on heavy favorites", "70%+ claims at
short prices on DraftKings" — because testing every combination would
explode the false-discovery family. A model that has read the record's
summary can propose the handful of intersections worth testing.

Authority never moves. Every proposal is:

  * **Constrained to the menu.** A hypothesis is a slice built ONLY from
    the miner's own dimensions and band values. The model cannot invent a
    dimension, reference data we don't journal, or write a number into
    the pricing path. Anything off-menu is discarded as invalid.
  * **Tried by the same tribunal.** The calibration z-test and
    Benjamini–Hochberg control from engine/losspatterns.py, applied over
    the hypothesis family. Below the sample floor is "collecting", a
    survivor is "confirmed", the rest are "rejected" — and rejected is a
    published result.
  * **Enforced only through the existing gate.** A confirmed hypothesis
    that ran hot past the closure bar, on a specific market, closes its
    slice — and losspatterns.veto() (already consulted by every sport's
    engine) blocks matching picks. A hypothesis can never act except by
    becoming ordinary, tested arithmetic.

One honest caveat, stated rather than hidden: the model saw a summary of
the record before proposing, so its hypotheses are not independent of the
data they are first tested on. That is why confirmation is re-earned
EVERY night — retest() runs on each settle pass against the growing
journal, and a hypothesis that was luck decays back to rejected as new
bets settle. The API call happens only when a human runs the CLI; the
nightly tribunal is pure arithmetic and free.

The call itself is raw HTTP against POST /v1/messages by project
doctrine (stdlib only, like every other source adapter here), following
the current API contract: claude-opus-5, thinking on by default,
structured outputs via output_config.format so the reply is guaranteed
to match the schema, no sampling parameters.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PATH = Path("data/models/hypotheses.json")

#: Every paid token, on the books. Lives beside the journal rather than in
#: data/cache — the cache is prunable by design, and a spend ledger that a
#: cleanup can silently erase is not a ledger.
SPEND_PATH = Path("data/llm_spend.json")
#: claude-opus-5, $ per million tokens — the source of every cost figure
#: printed or stored anywhere in the app.
PRICE_IN, PRICE_OUT = 5.00, 25.00

#: The skill-current default. Override with QELLYS_LLM_MODEL in
#: secrets.local; pricing note in the CLI assumes this model.
DEFAULT_MODEL = "claude-opus-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# A ceiling, not a spend — billing is on tokens actually produced, and the
# model's thinking counts against this. The first real run used 2,706 of
# 4,096; the triage bench proved a too-low ceiling returns billed garbage.
MAX_TOKENS = 8192
#: Cap on the evidence pack, so a season of journal can never turn one
#: nightly idea run into a five-dollar prompt.
MAX_PACK_CHARS = 12000
MAX_HYPOTHESES = 8

#: The tribunal's bars are the miner's bars — one discipline, two doors.
from .losspatterns import (ALPHA, CLOSE_GAP_PTS, MIN_N,  # noqa: E402
                           _bh, _slice_test)

# "lead" is capture_lag — minutes from bet log to the game's start,
# banded. The triage bench drafted it, the miner journals and slices it
# for every sport, and listing it here lets the lab propose on it too.
DIMS = ("side", "odds", "prob", "horizon", "book", "lead")


class HypothesisUnavailable(RuntimeError):
    """The API call could not produce hypotheses (no key, network, HTTP)."""


# --- the evidence pack -------------------------------------------------------
def evidence_pack(lconn, lp_store: dict | None = None) -> dict:
    """What the model is shown: per-market calibration summaries, the
    miner's findings AND near-misses, and the exact menu of testable
    values. Deterministic for a given journal, banded rather than raw —
    the model reasons over the same vocabulary the tribunal tests."""
    from . import losspatterns as lp

    records = lp.records_from_ledger(lconn)
    by_mkt: dict = {}
    values: dict = {d: set() for d in DIMS}
    for r in records:
        k = (r["sport"], r["market"])
        s = by_mkt.setdefault(k, {"n": 0, "won": 0, "said": 0.0})
        s["n"] += 1
        s["won"] += r["won"]
        s["said"] += r["prob"]
        for d, v in r["feats"].items():
            values[d].add(v)

    markets = [{"sport": s, "market": m, "n": v["n"],
                "said": round(v["said"] / v["n"], 3),
                "hit": round(v["won"] / v["n"], 3),
                "gap_pts": round((v["said"] - v["won"]) / v["n"] * 100, 1)}
               for (s, m), v in sorted(by_mkt.items())]

    mined = lp_store if lp_store is not None else lp.load()
    findings = [{k: f.get(k) for k in ("sport", "market", "dim", "value",
                                       "n", "said", "hit", "gap_pts",
                                       "action")}
                for f in (mined.get("findings") or [])][:12]

    pack = {
        "as_of": _dt.date.today().isoformat(),
        "n_records": len(records),
        "markets": markets,
        "miner_findings": findings,
        "menu": {d: sorted(values[d]) for d in DIMS},
        "sports": sorted({s for (s, _m) in by_mkt}),
    }
    # Trim the widest sections first if the pack runs long; the menu and
    # sports lists are load-bearing and never trimmed.
    while len(json.dumps(pack)) > MAX_PACK_CHARS and pack["markets"]:
        pack["markets"] = pack["markets"][:-1]
    return pack


# --- the ask -----------------------------------------------------------------
SYSTEM = """You are the hypothesis generator inside a sports-betting \
model's self-tuning loop. The model journals every bet and already runs: \
a nightly temperature refit per market, a recency-dial fit, per-player \
memory, and a blind-spot miner that tests every SINGLE dimension of the \
record under false-discovery control.

Your one job: propose slice INTERSECTIONS worth testing — combinations \
of the tested dimensions where the model's stated probabilities may \
systematically miss (e.g. a side crossed with a price band). You may \
only use dimension values copied EXACTLY from the menu provided. You \
never state probabilities, corrections, or picks; every proposal is \
tested by the same statistics that govern everything else, and only \
proposals that survive are acted on.

Propose at most {max_h} hypotheses. Prefer intersections the summary \
genuinely motivates over exhaustive coverage; an empty list is a valid \
answer when nothing is motivated. Ideas that CANNOT be expressed in the \
menu's dimensions belong in the watchlist as one-line prose instead."""

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "rationale": {"type": "string"},
                    "sport": {"type": "string"},
                    "market": {"type": ["string", "null"]},
                    "side": {"type": ["string", "null"]},
                    "odds": {"type": ["string", "null"]},
                    "prob": {"type": ["string", "null"]},
                    "horizon": {"type": ["string", "null"]},
                    "book": {"type": ["string", "null"]},
                    "lead": {"type": ["string", "null"]},
                },
                "required": ["claim", "rationale", "sport", "market",
                             "side", "odds", "prob", "horizon", "book",
                             "lead"],
                "additionalProperties": False,
            },
        },
        "watchlist": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hypotheses", "watchlist"],
    "additionalProperties": False,
}


def build_prompt(pack: dict) -> str:
    return ("Here is the record's current state as JSON. Propose slice "
            "intersections worth testing, using ONLY values from `menu` "
            "(and sports/markets that appear in `markets`).\n\n"
            + json.dumps(pack, indent=1))


# --- the call (raw HTTP, stdlib, per project doctrine) -----------------------
def _api_key() -> str | None:
    from . import secrets
    secrets.load_local_secrets()
    return os.environ.get("ANTHROPIC_API_KEY")


def _model() -> str:
    from . import secrets
    secrets.load_local_secrets()
    return os.environ.get("QELLYS_LLM_MODEL") or DEFAULT_MODEL


def cost_usd(usage: dict) -> float:
    """Dollars for one call's token usage, at this model's list price."""
    return (usage.get("input_tokens", 0) * PRICE_IN
            + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000


def log_llm_spend(usage: dict, model: str, kind: str = "propose",
                  path: Path | str | None = None) -> dict:
    """Append one paid call to the spend ledger. Returns the entry.

    Logged from the point the API RESPONDS, before any parsing — a refusal
    or an unparseable reply is billed exactly like a good one, and a spend
    log that only counts the successes understates the bill.
    """
    p = Path(path if path is not None else SPEND_PATH)
    entry = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
             "model": model, "kind": kind,
             "input_tokens": int(usage.get("input_tokens") or 0),
             "output_tokens": int(usage.get("output_tokens") or 0),
             "cost_usd": round(cost_usd(usage), 6)}
    try:
        rows = json.loads(p.read_text()) if p.is_file() else []
        if not isinstance(rows, list):
            rows = []
    except (ValueError, OSError):
        rows = []
    rows.append(entry)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=1))
    return entry


def llm_spend_report(path: Path | str | None = None) -> dict:
    """Totals off the spend ledger: all-time and this calendar month."""
    p = Path(path if path is not None else SPEND_PATH)
    try:
        rows = json.loads(p.read_text()) if p.is_file() else []
        if not isinstance(rows, list):
            rows = []
    except (ValueError, OSError):
        rows = []
    month = _dt.date.today().isoformat()[:7]
    m = [r for r in rows if str(r.get("ts", "")).startswith(month)]
    return {
        "runs": len(rows),
        "total_usd": round(sum(float(r.get("cost_usd") or 0)
                               for r in rows), 4),
        "month_runs": len(m),
        "month_usd": round(sum(float(r.get("cost_usd") or 0)
                               for r in m), 4),
        "last": rows[-1] if rows else None,
    }


def call_claude(prompt: str, api_key: str, model: str | None = None,
                timeout: float = 180.0) -> tuple[dict, dict]:
    """One structured-output request. Returns (parsed_json, usage).

    Raises HypothesisUnavailable with the API's own message on any
    failure — the lab degrades like every other source adapter here."""
    body = {
        "model": model or _model(),
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM.format(max_h=MAX_HYPOTHESES),
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema",
                                     "schema": SCHEMA}},
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"x-api-key": api_key,
                 "anthropic-version": API_VERSION,
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
        raise HypothesisUnavailable(f"API error {e.code}: {msg}") from e
    except Exception as e:                         # noqa: BLE001
        raise HypothesisUnavailable(f"network: {e}") from e
    # On the books BEFORE parsing: these tokens are billed whether or not
    # the reply survives the parser. Its own guard — a full disk must not
    # turn a successful API call into a reported failure.
    try:
        log_llm_spend(payload.get("usage") or {}, body["model"])
    except Exception:                              # noqa: BLE001
        pass
    return _parse_response(payload)


def _parse_response(payload: dict) -> tuple[dict, dict]:
    """Pure and offline-testable: API response dict → (proposals, usage)."""
    stop = payload.get("stop_reason")
    if stop == "refusal":
        raise HypothesisUnavailable("the model declined the request")
    # Truncation BEFORE parsing: a reply cut off at the ceiling is broken
    # JSON, and "unparseable" sends the reader debugging the schema when
    # the fix is the ceiling.
    if stop == "max_tokens":
        raise HypothesisUnavailable(
            "reply truncated at max_tokens — the ceiling is too low for "
            "this prompt")
    text = next((b.get("text") for b in payload.get("content") or []
                 if b.get("type") == "text"), None)
    if not text:
        raise HypothesisUnavailable(f"no text in response (stop={stop})")
    try:
        out = json.loads(text)
    except ValueError as e:
        raise HypothesisUnavailable(f"unparseable reply: {e}") from e
    return out, payload.get("usage") or {}


# --- validation: the menu is the law -----------------------------------------
def validate(raw: dict, pack: dict) -> tuple[list[dict], list[str]]:
    """Keep only proposals whose every value exists in the menu. The model
    cannot smuggle in a dimension value the tribunal has never banded."""
    menu = pack.get("menu") or {}
    sports = set(pack.get("sports") or [])
    mkts = {(m["sport"], m["market"]) for m in pack.get("markets") or []}
    keep = []
    for h in (raw.get("hypotheses") or [])[:MAX_HYPOTHESES]:
        if not isinstance(h, dict) or h.get("sport") not in sports:
            continue
        if h.get("market") is not None and \
                (h["sport"], h["market"]) not in mkts:
            continue
        dims = {d: h.get(d) for d in DIMS if h.get(d) is not None}
        if not dims:
            continue                       # a slice of everything is nothing
        if any(v not in (menu.get(d) or []) for d, v in dims.items()):
            continue
        keep.append({"claim": str(h.get("claim", ""))[:200],
                     "rationale": str(h.get("rationale", ""))[:400],
                     "sport": h["sport"], "market": h.get("market"),
                     "dims": dims})
    watch = [str(w)[:200] for w in (raw.get("watchlist") or [])[:5]]
    return keep, watch


# --- the tribunal ------------------------------------------------------------
def _match(r: dict, h: dict) -> bool:
    if r["sport"] != h["sport"]:
        return False
    if h.get("market") is not None and r["market"] != h["market"]:
        return False
    return all(r["feats"].get(d) == v for d, v in h["dims"].items())


def tribunal(hyps: list[dict], records: list[dict]) -> list[dict]:
    """The same discipline the miner lives under, over the hypothesis
    family. Statuses: collecting (under the floor), confirmed (survives
    BH), rejected. Only a confirmed, hot, MARKET-SPECIFIC slice closes —
    the same pooled-slices-point-specific-slices-convict rule."""
    tested = []
    for h in hyps:
        rows = [r for r in records if _match(r, h)]
        h = dict(h)
        h["n"] = len(rows)
        if len(rows) < MIN_N:
            h["status"], h["test"] = "collecting", None
            tested.append(h)
            continue
        t = _slice_test(rows)
        if t is None:
            h["status"], h["test"] = "collecting", None
        else:
            h["status"], h["test"] = "tested", t
        tested.append(h)
    family = [h["test"] for h in tested if h.get("test")]
    _bh(family, ALPHA)
    for h in tested:
        t = h.get("test")
        if not t:
            h.setdefault("action", None)
            continue
        survives = t.pop("survives", False)
        h["status"] = "confirmed" if survives else "rejected"
        hot = t["gap_pts"] >= CLOSE_GAP_PTS
        h["action"] = ("close" if survives and hot
                       and h.get("market") is not None else
                       "watch" if survives else None)
        h["reading"] = (
            f"said {t['said']:.0%}, hit {t['hit']:.0%} over {t['n']} bets"
            + (" — confirmed and closed; picks in this slice are vetoed"
               if h["action"] == "close"
               else " — confirmed, watching" if survives
               else " — did not survive false-discovery control"))
        h["last_tested"] = _dt.date.today().isoformat()
    return tested


# --- persistence, retest, and the veto hook ----------------------------------
_cache: dict = {}


def load(path=None) -> dict:
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if key in _cache:
        return _cache[key]
    try:
        raw = json.loads(p.read_text())
        out = raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        out = {}
    _cache.clear()
    _cache[key] = out
    return out


def save(store: dict, path=None) -> Path:
    p = Path(path if path is not None else DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=1))
    return p


def _key(h: dict) -> tuple:
    return (h["sport"], h.get("market"),
            tuple(sorted(h.get("dims", {}).items())))


def merge(store: dict, new_hyps: list[dict], watch: list[str],
          meta: dict) -> dict:
    """New proposals join the store; a re-proposed slice keeps its
    original first_proposed date. Watchlist replaces (it is prose)."""
    today = _dt.date.today().isoformat()
    existing = {_key(h): h for h in store.get("hypotheses") or []}
    for h in new_hyps:
        h.setdefault("first_proposed", today)
        old = existing.get(_key(h))
        if old:
            h["first_proposed"] = old.get("first_proposed", today)
        existing[_key(h)] = h
    return {**store, **meta, "generated": today,
            "hypotheses": list(existing.values()),
            "watchlist": watch if watch else store.get("watchlist") or []}


def retest(lconn, path=None) -> dict:
    """The free nightly step: every stored hypothesis re-earns its status
    against the grown journal. This is what keeps the double-dip honest —
    a lucky confirmation decays as independent new bets settle."""
    from . import losspatterns as lp
    store = load(path)
    hyps = store.get("hypotheses") or []
    if not hyps:
        return store
    records = lp.records_from_ledger(lconn)
    kept = [{k: h[k] for k in ("claim", "rationale", "sport", "market",
                               "dims", "first_proposed") if k in h}
            for h in hyps]
    store = dict(store)
    store["hypotheses"] = tribunal(kept, records)
    store["retested"] = _dt.date.today().isoformat()
    save(store, path)
    return store


def blocked(sport: str, market: str, feats: dict, path=None) -> str | None:
    """Consulted by losspatterns.veto — the single enforcement gate every
    sport already goes through. Multi-dim: EVERY dim must match."""
    for h in load(path).get("hypotheses") or []:
        if h.get("action") != "close" or h.get("sport") != sport:
            continue
        if h.get("market") != market:
            continue
        dims = h.get("dims") or {}
        if dims and all(feats.get(d) == v for d, v in dims.items()):
            return ("The record confirmed a proposed blind spot here: "
                    f"{h.get('claim', 'this slice')} — "
                    f"{h.get('reading', 'ran hot under test')}")
    return None


# --- the paid step, CLI-invoked ----------------------------------------------
def propose(lconn, api_key: str | None = None, model: str | None = None,
            path=None) -> dict:
    """Evidence pack → one API call → validate → tribunal → store.

    The only function in the ladder that spends money, which is why it
    runs from the CLI on demand and never from the nightly loop."""
    key = api_key or _api_key()
    if not key:
        raise HypothesisUnavailable(
            "no ANTHROPIC_API_KEY — add it to secrets.local to enable "
            "the hypothesis lab; everything else runs without it")
    from . import losspatterns as lp
    pack = evidence_pack(lconn)
    if not pack["markets"]:
        raise HypothesisUnavailable("journal has no graded bets to reason over")
    raw, usage = call_claude(build_prompt(pack), key, model=model)
    hyps, watch = validate(raw, pack)
    tested = tribunal(hyps, lp.records_from_ledger(lconn))
    store = merge(load(path), tested, watch,
                  {"model": model or _model(), "usage": usage,
                   # Stamped so the automatic weekly cadence (prose.weekly_lab)
                   # can hold its interval without a second bookkeeping file.
                   "last_proposed": _dt.date.today().isoformat()})
    save(store, path)
    return store
