"""Ask Qellys — a question about tonight's board, answered from the board.

Ethan, 2026-09-23, on Rithmm's "Ask Scout": "I like the Ask Scout AI
agent." Scout answers questions about any game, player or bet from that
app's own models. This is ours, built the way the explainer is
(engine/explainer.py) and bound by the same rule:

WHAT IT MAY SAY. Only what our board says. Each question is sent with
the board's own rows — the ones it names (a player, a team, a matchup),
the pick it was asked from if any, and a short summary of tonight's
board — and the model is told to answer from those facts alone: no
injury, statistic, news or number that is not in them. When the board
has nothing on what was asked, it says so instead of guessing. It never
tells anyone to bet or how much; our stake is the model's, not advice.

WHAT IT COSTS. One call per question. Subscribers only, behind a per-IP
rate limit (server.RATE_ASK_PER_MIN), with the question and the carried
conversation capped in length. The board summary sits in the system
prompt with a cache breakpoint, so a second question on the same build
reads it from the prompt cache instead of paying for it again.

WHERE THE MODEL COMES FROM. The service's environment and nowhere else:
QB_ASK_MODEL, else the explainer's QB_EXPLAIN_MODEL, else claude-opus-5;
the key is ANTHROPIC_API_KEY (/etc/qellys/env). No key, or no SDK, and
`configured()` is False — the page says Ask is not switched on rather
than pretending.

REFUSALS AND FAILURES. A `refusal` stop reason comes back as a sentence
saying Ask declined, never an empty box. On Claude Opus 5 and Claude
Fable 5.1 the request carries the API's server-side refusal fallback
(to Claude Opus 4.8); an installed SDK too old to know that parameter
is retried once without it. A network or API error raises
`explainer.Unavailable` and the endpoint answers 503.
"""

from __future__ import annotations

import json
import os
import re

from engine import explainer as _ex

#: The fallback when neither QB_ASK_MODEL nor QB_EXPLAIN_MODEL is set.
DEFAULT_MODEL = "claude-opus-5"

#: Models the server-side refusal fallback is sent for, and where to.
FALLBACK_FOR = ("claude-opus-5", "claude-fable-5-1")
FALLBACK_BETA = "server-side-fallback-2026-06-01"
FALLBACK_TO = "claude-opus-4-8"

#: Ceilings. A question is a sentence or two; the carried conversation
#: is the last few turns, each trimmed.
MAX_QUESTION = 400
MAX_TURNS = 6
MAX_TURN_CHARS = 1200
WORDS = 150
MAX_TOKENS = 16000

#: Rows named by the question, and rows in the board summary, at most.
MAX_MATCHED = 12
SUMMARY_EACH = 8

#: The fields a row is shown to the model with — the card's own facts.
ROW_KEYS = ("player", "team", "opponent", "matchup", "market", "market_label", "bet_type",
            "side", "pick_label", "line", "odds", "book", "projection", "hit_prob",
            "model_prob", "win_prob", "fair_prob", "implied_prob", "edge", "grade",
            "stake_units", "recommended", "has_market", "game_date", "kickoff",
            "game_kickoff", "headline", "summary", "reasons", "warnings")

SYSTEM = (
    "You are Ask Qellys, the assistant inside Qellys Book, a sports-betting "
    "analytics site. You answer the reader's question about tonight's board.\n"
    "Use ONLY the facts in the JSON you are given: the board summary below and "
    "the rows sent with the question. Do not add statistics, injuries, news, "
    "matchups, odds or any number that is not in them. If the facts do not "
    "cover the question, say plainly that tonight's board has nothing on it, "
    "and say what it does have that is closest, if anything.\n"
    "hit_prob, model_prob and win_prob are our model's chance the bet wins; "
    "fair_prob and implied_prob are what the price implies; edge is the gap. "
    "A row with recommended false or no stake is not one of our bets: say so.\n"
    f"At most {WORDS} words. Plain words a first-time bettor understands. "
    "No headings. Never tell the reader to bet or how much to bet; a stake on a "
    "row is our model's, not advice. You cannot see the internet, live scores "
    "or anything outside these facts, and you say so if asked."
)


def model_name() -> str:
    from engine import secrets as _s
    _s.load_local_secrets()
    return (os.environ.get("QB_ASK_MODEL", "").strip()
            or os.environ.get("QB_EXPLAIN_MODEL", "").strip()
            or DEFAULT_MODEL)


def configured() -> bool:
    """A key in the environment and the SDK importable."""
    model_name()                                   # loads the env file
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False
    try:
        import anthropic                                   # noqa: F401
    except ImportError:
        return False
    return True


# ---- what the model is shown ------------------------------------------------
def compact(row: dict) -> dict:
    out = {}
    for k in ROW_KEYS:
        v = row.get(k)
        if v is None or v == "" or v == []:
            continue
        if k in ("reasons", "warnings") and isinstance(v, list):
            v = [str(x) for x in v[:4]]
        out[k] = v
    return out


def _rows(board: dict):
    for lst in ("recommendations", "game_bets", "most_likely", "long_shots"):
        for r in (board or {}).get(lst) or []:
            if isinstance(r, dict):
                yield lst, r


def _norm(text) -> str:
    """Lowercase words and nothing else, space-padded, for whole-word finds."""
    return " " + " ".join(re.sub(r"[^a-z0-9.']+", " ", str(text or "").lower()).split()) + " "


def _names(row: dict) -> list[str]:
    """What a reader might call this row, normalised like the question."""
    out = []
    for k in ("player", "matchup", "pick_label", "home", "away"):
        v = _norm(row.get(k)).strip()
        if len(v) >= 3:
            out.append(v)
    p = _norm(row.get("player")).split()
    if len(p) >= 2 and len(p[-1]) >= 4:
        out.append(p[-1])                           # "kelce"
    return out


def _codes(row: dict) -> set[str]:
    """The row's team codes ("KC"), matched only as typed in capitals —
    lowercase "no" is a word before it is New Orleans."""
    return {str(row.get(k) or "").strip() for k in ("team", "opponent", "home", "away")
            if 2 <= len(str(row.get(k) or "").strip()) <= 4}


def matched_rows(board: dict, question: str) -> list[dict]:
    """The rows the question names, most specific first, capped."""
    q = _norm(question)
    caps = set(re.findall(r"\b[A-Z]{2,4}\b", str(question or "")))
    hits = []
    for lst, r in _rows(board):
        best = max([len(n) for n in _names(r) if f" {n} " in q] or [0])
        if not best and caps & _codes(r):
            best = 1                                # a team code: the weakest match
        if best:
            hits.append((best, lst, r))
    hits.sort(key=lambda h: -h[0])
    seen, out = set(), []
    for _, lst, r in hits:
        key = (lst, r.get("player"), r.get("market"), r.get("side"), r.get("line"), r.get("pick_label"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"board": lst, **compact(r)})
        if len(out) >= MAX_MATCHED:
            break
    return out


def board_summary(board: dict) -> dict:
    """Tonight in brief: our bets, the likeliest rows, the games."""
    b = board or {}
    recs = [r for r in b.get("recommendations") or [] if isinstance(r, dict) and r.get("recommended")]
    likely = [r for r in b.get("most_likely") or [] if isinstance(r, dict)]
    likely.sort(key=lambda r: -(r.get("model_prob") or 0))
    games = b.get("games") or []
    return {
        "sport": b.get("sport") or "",
        "date": b.get("date") or "",
        "our_bets": [compact(r) for r in recs[:SUMMARY_EACH]],
        "our_bets_total": len(recs),
        "most_likely": [compact(r) for r in likely[:SUMMARY_EACH]],
        "games": [g.get("matchup") or f"{g.get('away', '')} @ {g.get('home', '')}"
                  for g in games[:20] if isinstance(g, dict)],
    }


def clean_history(history) -> list[dict]:
    """The last few turns the page sent back, reduced to plain text."""
    out = []
    for t in (history or [])[-MAX_TURNS:]:
        if not isinstance(t, dict):
            continue
        role = t.get("role")
        text = str(t.get("text") or "").strip()[:MAX_TURN_CHARS]
        if role in ("user", "assistant") and text:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":             # the API opens on the reader
        out.pop(0)
    return out


def build_request(board: dict, question: str, history=None, pick: str = "") -> dict:
    """Everything one call sends, apart from the model and the client."""
    question = str(question or "").strip()[:MAX_QUESTION]
    focus = _ex.find_row(board, pick) if pick else None
    facts = {"rows_matching_the_question": matched_rows(board, question)}
    if focus is not None:
        facts["the_pick_this_was_asked_from"] = _ex.facts_for(focus)
    system = [
        {"type": "text", "text": SYSTEM},
        {"type": "text", "text": "Tonight's board summary:\n"
         + json.dumps(board_summary(board), sort_keys=True, separators=(",", ":")),
         "cache_control": {"type": "ephemeral"}},
    ]
    messages = clean_history(history) + [{"role": "user", "content":
        f"{question}\n\nFacts for this question:\n" + json.dumps(facts, sort_keys=True)}]
    return {"system": system, "messages": messages, "matched": len(facts["rows_matching_the_question"]),
            "focused": focus is not None}


def _client():
    try:
        import anthropic
    except ImportError as exc:
        raise _ex.NotConfigured("the anthropic package is not installed") from exc
    return anthropic.Anthropic()


def _call(client, model: str, req: dict):
    kw = dict(model=model, max_tokens=MAX_TOKENS, system=req["system"], messages=req["messages"])
    if model in FALLBACK_FOR and hasattr(getattr(client, "beta", None), "messages"):
        try:
            return client.beta.messages.create(betas=[FALLBACK_BETA],
                                               fallbacks=[{"model": FALLBACK_TO}], **kw)
        except TypeError:
            pass                                   # an SDK too old for `fallbacks`
    return client.messages.create(**kw)


def ask(board: dict, question: str, history=None, pick: str = "", client=None) -> dict:
    """One answer. ``{"text", "model", "refused", "matched", "focused"}``.

    Raises ValueError for an empty question, NotConfigured, Unavailable.
    """
    if not str(question or "").strip():
        raise ValueError("empty question")
    model = model_name()
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise _ex.NotConfigured("ANTHROPIC_API_KEY is not set")
        client = _client()
    req = build_request(board, question, history, pick)
    try:
        import anthropic
        errors = (anthropic.APIStatusError, anthropic.APIConnectionError)
    except ImportError:
        errors = ()
    try:
        response = _call(client, model, req)
    except errors as exc:                               # typed, most specific first
        raise _ex.Unavailable(f"{type(exc).__name__}: {getattr(exc, 'message', exc)}") from exc
    except Exception as exc:                            # noqa: BLE001 — a client without the SDK's types
        raise _ex.Unavailable(f"{type(exc).__name__}: {exc}") from exc
    base = {"model": getattr(response, "model", None) or model,
            "matched": req["matched"], "focused": req["focused"]}
    if getattr(response, "stop_reason", "") == "refusal":
        return {**base, "text": "Ask declined to answer that one.", "refused": True}
    text = "".join(getattr(b, "text", "") for b in getattr(response, "content", None) or []
                   if getattr(b, "type", "") == "text").strip()
    if not text:
        raise _ex.Unavailable("the answer had no text")
    return {**base, "text": text, "refused": False}
