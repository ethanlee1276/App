"""A plain-English explainer for one pick, written by a language model
from the numbers already on the card — behind a tap, cached per build.

Ethan, 2026-09-05: "a plain English explainer per pick" — from a list
he asked for in full.

WHAT IT MAY SAY. Only what the row says. The prompt hands the model the
card's own facts — the pick, the price, the projection and its range,
the hit probability against the book's, the edge, the grade and stake,
the model's reasons and warnings, the game script, the recent form —
and tells it to restate those in plain words and add nothing: no
injury it was not given, no statistic that is not in the row, no
number that is not on the card. A reader who taps "Explain" gets the
card read back to them by someone patient, not a second opinion.

WHAT IT COSTS AND WHEN. One call per pick per build: the answer is
cached on disk under the board's build stamp, so the second reader of
a pick, and every reader after, is served from the file. A new build
is a new stamp and a fresh answer. The call runs through the official
`anthropic` Python package, which is the one dependency this project
installs (docs/DEPLOY.md); the model and key come from the service's
environment (QB_EXPLAIN_MODEL, ANTHROPIC_API_KEY — /etc/qellys/env on
the box) and nowhere else. Missing either, `configured()` is False and
the page says so instead of pretending.

WHAT IT REFUSES. A `stop_reason` of "refusal" — the model's own
safety classifiers declining — is returned as a sentence saying the
explainer declined, never as an empty box. A network or API error
raises `Unavailable` and the endpoint answers 503; nothing here is a
claim about the pick.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the answers live between readers. One JSON object keyed by
#: board name, pick id and build stamp.
CACHE_PATH = Path(os.environ.get("QB_EXPLAIN_CACHE", "").strip()
                  or (ROOT / "data" / "explain_cache.json"))

#: How many answers the cache keeps before the oldest go.
CACHE_MAX = 4000

#: The ceiling on the answer, in words, said to the model and enforced
#: nowhere else — a cap on max_tokens is not a cap on words.
WORDS = 120

#: Tokens: generous against the words asked for, because the model's
#: own thinking counts against this ceiling too.
MAX_TOKENS = 4000

#: The row fields the model is shown — and the only ones. Verified
#: against engine/pipeline.py and engine/mlb/pipeline.py row dicts.
FACT_KEYS = (
    "player", "team", "opponent", "position", "market", "market_label", "side",
    "line", "odds", "book", "projection", "proj_low", "proj_high", "hit_prob",
    "fair_prob", "edge", "grade", "stake_units", "confidence", "quality", "tier",
    "volatility", "trend", "trend_delta", "recommended", "has_market",
    "headline", "summary", "reasons", "warnings", "game_date", "game_kickoff",
)

SYSTEM = (
    "You explain one sports-betting pick to a reader in plain English.\n"
    "Use ONLY the facts in the JSON you are given. Do not add statistics, "
    "injuries, news, matchups or numbers that are not in it. If a field is "
    "missing, do not guess it. If the row says the pick is not recommended "
    "or carries no stake, say so plainly and why, from its own warnings.\n"
    f"At most {WORDS} words, one or two short paragraphs, no headings, no "
    "bullet points, no preamble. Name the player, the bet, the price, what "
    "the model projects against the line, how likely it thinks the bet is "
    "against what the book's price implies, and the one or two reasons "
    "that matter most. Plain words a first-time bettor understands; "
    "explain 'edge' and the odds in a clause if you use them. Never tell "
    "the reader to bet or how much; the card's stake is the model's, not "
    "advice."
)


class NotConfigured(RuntimeError):
    """No model name or no key in the environment, or no SDK installed."""


class Unavailable(RuntimeError):
    """The call could not be made or did not come back."""


def facts_for(row: dict) -> dict:
    """The card's facts, and nothing else, in a stable order."""
    out: dict = {}
    for k in FACT_KEYS:
        v = row.get(k)
        if v is None or v == "" or v == []:
            continue
        if k in ("reasons", "warnings") and isinstance(v, list):
            v = [str(x) for x in v[:8]]
        out[k] = v
    gs = row.get("game_script") or {}
    if isinstance(gs, dict) and gs.get("summary"):
        out["game_script"] = str(gs["summary"])
    form = row.get("form") or {}
    if isinstance(form, dict):
        f = {k: form[k] for k in ("last3", "last5", "last10", "season") if form.get(k) is not None}
        if f:
            out["form_averages"] = f
    rv = row.get("recent_values")
    if isinstance(rv, list) and rv:
        out["recent_games_values"] = rv[:10]
    return out


def pick_id(row: dict) -> str:
    """The page's `propId` (web/js/app.js): player|market|side|line."""
    line = row.get("line")
    return "|".join([str(row.get("player") or ""), str(row.get("market") or ""),
                     str(row.get("side") or ""), "" if line is None else f"{line:g}"
                     if isinstance(line, (int, float)) else str(line)])


def same_pick(row: dict, wanted: str) -> bool:
    """Match by parts, tolerant of how each side spells the line."""
    parts = (wanted or "").split("|")
    if len(parts) != 4:
        return False
    if (str(row.get("player") or ""), str(row.get("market") or ""),
            str(row.get("side") or "")) != tuple(parts[:3]):
        return False
    line = row.get("line")
    if parts[3] == "":
        return line is None
    try:
        return line is not None and abs(float(line) - float(parts[3])) < 1e-9
    except (TypeError, ValueError):
        return str(line) == parts[3]


def find_row(board: dict, wanted: str) -> dict | None:
    for lst in ("recommendations", "game_bets", "long_shots", "most_likely"):
        for r in board.get(lst) or []:
            if isinstance(r, dict) and same_pick(r, wanted):
                return r
    return None


def board_stamp(board: dict) -> str:
    """The build this answer belongs to."""
    return str(board.get("built_at") or board.get("generated_at") or board.get("date") or "")


def cache_key(board_name: str, wanted: str, stamp: str) -> str:
    return f"{board_name}\t{wanted}\t{stamp}"


# ---- the cache -------------------------------------------------------------
_LOCK = threading.Lock()
_MEM: dict | None = None


def _load() -> dict:
    global _MEM
    if _MEM is None:
        try:
            _MEM = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if not isinstance(_MEM, dict):
                _MEM = {}
        except (OSError, ValueError):
            _MEM = {}
    return _MEM


def _save(mem: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(mem), encoding="utf-8")
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass                                       # the answer was still served


def cached(key: str) -> dict | None:
    with _LOCK:
        hit = _load().get(key)
    return dict(hit) if isinstance(hit, dict) else None


def remember(key: str, entry: dict) -> None:
    with _LOCK:
        mem = _load()
        mem[key] = entry
        if len(mem) > CACHE_MAX:
            for k in sorted(mem, key=lambda k: mem[k].get("at", 0))[: len(mem) - CACHE_MAX]:
                mem.pop(k, None)
        _save(mem)


def forget_all() -> None:
    """Tests only."""
    global _MEM
    with _LOCK:
        _MEM = {}


#: One call per pick per build even when two readers tap at once: the
#: second waits on the first's lock and then reads the cache.
_INFLIGHT: dict = {}


def _key_lock(key: str) -> threading.Lock:
    with _LOCK:
        return _INFLIGHT.setdefault(key, threading.Lock())


# ---- the call --------------------------------------------------------------
def model_name() -> str:
    from engine import secrets as _s
    _s.load_local_secrets()
    return os.environ.get("QB_EXPLAIN_MODEL", "").strip()


def configured() -> bool:
    """A model name and a key in the environment, and the SDK importable."""
    if not model_name() or not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False
    try:
        import anthropic                                   # noqa: F401
    except ImportError:
        return False
    return True


def _client():
    try:
        import anthropic
    except ImportError as exc:
        raise NotConfigured("the anthropic package is not installed") from exc
    return anthropic.Anthropic()


def ask(facts: dict, client=None) -> dict:
    """One call. ``{"text", "model", "refused"}``. Raises Unavailable."""
    model = model_name()
    if not model:
        raise NotConfigured("QB_EXPLAIN_MODEL is not set")
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise NotConfigured("ANTHROPIC_API_KEY is not set")
        client = _client()
    try:
        import anthropic
        errors = (anthropic.APIStatusError, anthropic.APIConnectionError)
    except ImportError:
        errors = ()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Explain this pick from these facts only:\n" + json.dumps(facts, indent=1)}],
        )
    except errors as exc:                               # typed, most specific first
        raise Unavailable(f"{type(exc).__name__}: {getattr(exc, 'message', exc)}") from exc
    except Exception as exc:                            # noqa: BLE001 — a client without the SDK's types
        raise Unavailable(f"{type(exc).__name__}: {exc}") from exc
    if getattr(response, "stop_reason", "") == "refusal":
        return {"text": "The explainer declined to write about this pick.", "model": model,
                "refused": True}
    text = "".join(getattr(b, "text", "") for b in getattr(response, "content", None) or []
                   if getattr(b, "type", "") == "text").strip()
    if not text:
        raise Unavailable("the answer had no text")
    return {"text": text, "model": model, "refused": False}


def explain(board_name: str, board: dict, wanted: str, client=None) -> dict:
    """The cached answer for a pick on a board, or a fresh one.

    ``{"text", "cached", "pick", "stamp"}``; KeyError when the pick is
    not on the board; NotConfigured / Unavailable as above.
    """
    row = find_row(board, wanted)
    if row is None:
        raise KeyError(wanted)
    stamp = board_stamp(board)
    key = cache_key(board_name, wanted, stamp)
    with _key_lock(key):
        hit = cached(key)
        if hit and hit.get("text"):
            return {"text": hit["text"], "cached": True, "pick": wanted, "stamp": stamp,
                    "refused": bool(hit.get("refused"))}
        got = ask(facts_for(row), client=client)
        remember(key, {"text": got["text"], "at": time.time(), "refused": got["refused"]})
    return {"text": got["text"], "cached": False, "pick": wanted, "stamp": stamp,
            "refused": got["refused"]}
