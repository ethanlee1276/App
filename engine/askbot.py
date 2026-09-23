"""Ask Qellys — a question about tonight's board, answered from our data.

Ethan, 2026-09-23, on Rithmm's "Ask Scout": "I like the Ask Scout AI
agent." Then, the same day: "make the ask feature better and make it
cost less credits. We have so much data backed up on the site ... we
can use that too. Also turn the model down."

WHAT IT MAY SAY. Only what our own data says. Each question is sent
with the facts it needs and nothing it does not, picked here in code
rather than by the model, so a question costs one call:

  * the board rows the question names (a player, a pick, a matchup; a
    team code typed in capitals), each with its recent games and form;
  * the pick it was asked from, when Ask was opened from a prop page;
  * the games those rows are in — spread, total, prices, weather, the
    stadium note, each team's rest — and, for a weather question, every
    game's conditions;
  * our record from web/data/record.json when the question is about how
    we have done — the pooled headline, the last 30 days, this sport,
    the Most Likely board with its calibration, best and worst markets;
  * the injury board (web/data/injuries.json) when it asks about health;
  * the long-shot shelf when it asks about long shots.

A short summary of the night rides in the system prompt behind a cache
breakpoint. The model is told to answer from those facts alone, to say
when they do not cover the question, and never to tell anyone to bet.

WHAT IT COSTS, and the levers pulled on it:

  * THE MODEL: QB_ASK_MODEL, else Claude Sonnet 5 (claude-sonnet-5) —
    no longer the explainer's model. Grounded restatement is not work
    that needs the largest model, and Sonnet 5's prompt cache starts at
    1,024 tokens where Haiku 4.5's needs 4,096 — so with the summary
    cached, Sonnet costs about what Haiku would uncached and reasons
    better across several rows. Effort is set to low on the models
    that take it.
  * THE SAME QUESTION IS NEVER PAID FOR TWICE on one build: an opening
    question (no conversation carried) is cached by board, build stamp,
    attached pick and its normalised words (data/ask_cache.json). The
    page's suggested questions are exactly the ones asked most.
  * SHORT: at most WORDS words, the last MAX_TURNS turns carried, each
    trimmed; every section above is capped.
  * MEASURED: every call's tokens, and every cache hit, go into
    data/ask_usage.json by day with an estimated dollar figure —
    `python3 -m engine.askbot usage` prints the last week.

REFUSALS AND FAILURES. A `refusal` stop reason is a sentence, never an
empty box. On Claude Opus 5 / Claude Fable 5.1 the call carries the
server-side refusal fallback. An installed SDK too old for a parameter
(`fallbacks`, `output_config`) is retried once without it. Network or
API errors raise `explainer.Unavailable` and the endpoint answers 503.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import threading
import time
from pathlib import Path

from engine import explainer as _ex

ROOT = Path(__file__).resolve().parent.parent

#: Used when QB_ASK_MODEL is not set.
DEFAULT_MODEL = "claude-sonnet-5"

#: Models that take `output_config.effort`; Ask runs them at low.
LOW_EFFORT_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-opus-5-5", "claude-opus-4-8",
                     "claude-opus-4-7", "claude-fable-5", "claude-fable-5-1")

#: Models the server-side refusal fallback is sent for, and where to.
FALLBACK_FOR = ("claude-opus-5", "claude-fable-5-1")
FALLBACK_BETA = "server-side-fallback-2026-06-01"
FALLBACK_TO = "claude-opus-4-8"

#: $ per million tokens (input, output), for the usage log's estimate.
#: Cache reads bill at 0.1x input, 5-minute cache writes at 1.25x.
PRICES = {"claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0),
          "claude-opus-5": (5.0, 25.0), "claude-opus-5-5": (4.0, 20.0),
          "claude-opus-4-8": (5.0, 25.0), "claude-fable-5-1": (10.0, 50.0)}

#: Ceilings.
MAX_QUESTION = 400
MAX_TURNS = 4
MAX_TURN_CHARS = 800
WORDS = 120
MAX_TOKENS = 4000
MAX_MATCHED = 10
#: Rows matched only by a team code, at most (sent without their game logs).
MAX_WEAK = 5
SUMMARY_EACH = 6
RECENT_GAMES = 8
MAX_GAMES = 3
MAX_INJURIES = 15

CACHE_PATH = Path(os.environ.get("QB_ASK_CACHE", "").strip() or (ROOT / "data" / "ask_cache.json"))
USAGE_PATH = Path(os.environ.get("QB_ASK_USAGE", "").strip() or (ROOT / "data" / "ask_usage.json"))
CACHE_MAX = 3000
USAGE_DAYS = 60

#: The fields a row is shown with — the card's own facts, not its payload.
ROW_KEYS = ("player", "team", "opponent", "matchup", "market", "market_label", "bet_type",
            "side", "pick_label", "line", "odds", "book", "projection", "proj_low", "proj_high",
            "hit_prob", "model_prob", "win_prob", "fair_prob", "implied_prob", "edge", "grade",
            "stake_units", "recommended", "has_market", "injury_status", "usage_role", "trend",
            "game_date", "kickoff", "game_kickoff", "headline", "reasons", "warnings")

#: What a question is about, read from its words.
INTENTS = {
    "record": r"\b(record|track|win ?rate|winning|hit ?rate|roi|profit\w*|accura\w*|trust|results?|"
              r"how (?:have|has|are|is|did) (?:you|we|it|the model|qellys)|units?|calibrat\w*)\b",
    "injury": r"\b(injur\w*|hurt|questionable|doubtful|inactive|ruled out|is out|be out|health\w*|"
              r"playing|active|status)\b",
    "weather": r"\b(weather|wind\w*|rain\w*|snow\w*|cold|temperature|dome|roof)\b",
    "longshot": r"\b(long ?shots?|plus[- ]money|underdogs?|lottery|big (?:odds|payout))\b",
}

SYSTEM = (
    "You are Ask Qellys, the assistant inside Qellys Book, a sports-betting analytics "
    "site. Answer the reader's question about tonight's board.\n"
    "Use ONLY the facts you are given: the board summary below and the facts sent with "
    "the question (board rows with their recent games and form, the games with their "
    "lines, weather and rest, our record, the injury board). Do not add statistics, "
    "injuries, news, odds or any number that is not in them. If the facts do not cover "
    "the question, say plainly that our data has nothing on it and name the closest "
    "thing it does have, if anything.\n"
    "hit_prob, model_prob and win_prob are our model's chance the bet wins; fair_prob "
    "and implied_prob are what the price implies; edge is the gap. A row with "
    "recommended false or no stake is not one of our bets: say so. Our record is real "
    "and includes losses; quote it straight.\n"
    f"Lead with the direct answer in one sentence, then the one or two facts behind it. "
    f"At most {WORDS} words, plain words a first-time bettor understands, no headings. "
    "Never tell the reader to bet or how much; a stake on a row is our model's, not "
    "advice. You cannot see the internet or live scores, and you say so if asked."
)


# ---- configuration ------------------------------------------------------------
def model_name() -> str:
    from engine import secrets as _s
    _s.load_local_secrets()
    return os.environ.get("QB_ASK_MODEL", "").strip() or DEFAULT_MODEL


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


# ---- reading the question ------------------------------------------------------
def _norm(text) -> str:
    """Lowercase words and nothing else, space-padded, for whole-word finds."""
    t = str(text or "").lower().replace("\u2019", "'").replace("\u2018", "'")   # what’s = what's
    return " " + " ".join(re.sub(r"[^a-z0-9.']+", " ", t).split()) + " "


def intents(question: str) -> set[str]:
    q = str(question or "").lower()
    return {k for k, rx in INTENTS.items() if re.search(rx, q)}


def cache_words(question: str) -> str:
    """The question as a cache key: its words, in order, nothing else."""
    return _norm(question).strip()


# ---- the board -----------------------------------------------------------------
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


def detailed(row: dict) -> dict:
    """A row with what we know about the player behind it: recent games,
    form and the game script's read."""
    out = compact(row)
    logs = [g for g in (row.get("logs") or []) if isinstance(g, dict) and g.get("value") is not None]
    if logs:
        out["recent_games"] = [{"vs": g.get("opponent"), "value": g.get("value")}
                               for g in logs[:RECENT_GAMES]]
    elif isinstance(row.get("recent_values"), list) and row["recent_values"]:
        out["recent_games"] = [{"value": v} for v in row["recent_values"][:RECENT_GAMES]]
    form = row.get("form") or {}
    if isinstance(form, dict):
        f = {k: form[k] for k in ("last3", "last5", "last10", "season", "vs_opponent")
             if form.get(k) is not None}
        if f:
            out["form"] = f
    gs = row.get("game_script") or {}
    if isinstance(gs, dict) and (gs.get("read") or gs.get("archetype")):
        out["game_script"] = str(gs.get("read") or gs.get("archetype"))[:300]
    return out


def _rows(board: dict):
    for lst in ("recommendations", "game_bets", "most_likely", "long_shots"):
        for r in (board or {}).get(lst) or []:
            if isinstance(r, dict):
                yield lst, r


def _names(row: dict) -> list[str]:
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
    """Team codes ("KC"), matched only as typed in capitals — lowercase
    "no" is a word before it is New Orleans."""
    return {str(row.get(k) or "").strip() for k in ("team", "opponent", "home", "away")
            if 2 <= len(str(row.get(k) or "").strip()) <= 4}


def _caps(question: str) -> set[str]:
    return set(re.findall(r"\b[A-Z]{2,4}\b", str(question or "")))


def _hits(board: dict, question: str) -> list[tuple]:
    q = _norm(question)
    caps = _caps(question)
    hits = []
    for lst, r in _rows(board):
        best = max([len(n) for n in _names(r) if f" {n} " in q] or [0])
        if not best and caps & _codes(r):
            best = 1                                # a team code: the weakest match
        if best:
            hits.append((best, lst, r))
    hits.sort(key=lambda h: -h[0])
    seen, out, weak = set(), [], 0
    for h in hits:
        r = h[2]
        key = (h[1], r.get("player"), r.get("market"), r.get("side"), r.get("line"), r.get("pick_label"))
        if key in seen:
            continue
        seen.add(key)
        if h[0] == 1:                               # named only by a team code
            weak += 1
            if weak > MAX_WEAK:
                continue
        out.append(h)
    return out[:MAX_MATCHED]


def _shown(hit: tuple) -> dict:
    """A named row in full; a row a team code merely touches, as its card
    alone — its game logs are the priciest part of a question, and they
    earn their place only when the player or pick was asked about."""
    score, lst, r = hit
    return {"board": lst, **(detailed(r) if score > 1 else compact(r))}


def matched_rows(board: dict, question: str) -> list[dict]:
    """The rows the question names, most specific first, capped."""
    return [_shown(h) for h in _hits(board, question)]


def _game_label(g: dict) -> str:
    return str(g.get("matchup") or f"{g.get('away', '')} @ {g.get('home', '')}")


def game_facts(board: dict, g: dict) -> dict:
    """One game as the model needs it: lines, weather, the stadium, rest."""
    out = {"game": _game_label(g)}
    for k in ("date", "kickoff", "spread", "favorite", "total", "home_ml", "away_ml", "roof"):
        if g.get(k) not in (None, ""):
            out[k] = g[k]
    w = g.get("weather") or {}
    if isinstance(w, dict) and w:
        out["weather"] = {k: w[k] for k in ("dome", "temp_f", "wind_mph", "rain", "snow")
                          if w.get(k) is not None}
    plays = ((g.get("stadium") or {}) if isinstance(g.get("stadium"), dict) else {}).get("plays")
    if plays:
        out["stadium_note"] = str(plays)[:240]
    teams = ((board or {}).get("fatigue") or {}).get("teams") or {}
    rest = {}
    for side in ("home", "away"):
        t = teams.get(g.get(side)) if isinstance(teams, dict) else None
        if isinstance(t, dict):
            r = {k: t[k] for k in ("rest_days", "rest_band") if t.get(k) is not None}
            notes = [str(x) for x in (t.get("notes") or []) + (t.get("warnings") or [])][:2]
            if notes:
                r["notes"] = notes
            if r:
                rest[str(g.get(side))] = r
    if rest:
        out["rest"] = rest
    return out


def named_games(board: dict, question: str, rows: list[dict]) -> list[dict]:
    """The games the question or its rows are about."""
    want = _caps(question)
    for r in rows:
        want |= _codes(r)
    q = _norm(question)
    out = []
    for g in (board or {}).get("games") or []:
        if not isinstance(g, dict):
            continue
        codes = {str(g.get("home") or ""), str(g.get("away") or "")}
        if (codes & want) or f" {_norm(_game_label(g)).strip()} " in q:
            out.append(g)
    return out[:MAX_GAMES]


def board_summary(board: dict) -> dict:
    """Tonight in brief: our bets, the likeliest rows, the games."""
    b = board or {}
    recs = [r for r in b.get("recommendations") or [] if isinstance(r, dict) and r.get("recommended")]
    likely = [r for r in b.get("most_likely") or [] if isinstance(r, dict)]
    likely.sort(key=lambda r: -(r.get("model_prob") or 0))
    return {
        "sport": b.get("sport") or "",
        "date": b.get("date") or "",
        "our_bets": [compact(r) for r in recs[:SUMMARY_EACH]],
        "our_bets_total": len(recs),
        "most_likely": [compact(r) for r in likely[:SUMMARY_EACH]],
        "games": [_game_label(g) for g in (b.get("games") or [])[:20] if isinstance(g, dict)],
    }


# ---- the rest of the site's data ----------------------------------------------
def _load_json(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _wl(o: dict) -> dict:
    o = o or {}
    out = {k: o.get(k) for k in ("settled", "wins", "losses", "pushes", "roi", "net_units")
           if o.get(k) is not None}
    if isinstance(out.get("roi"), float):
        out["roi"] = round(out["roi"], 4)
    if isinstance(out.get("net_units"), float):
        out["net_units"] = round(out["net_units"], 2)
    return out


def record_facts(record: dict, sport: str = "") -> dict:
    """Our public record, the numbers the Record page leads with."""
    if not record:
        return {}
    pooled = record.get("pooled") or {}
    head = pooled.get("overall") or record.get("overall") or {}
    out = {"since": record.get("record_epoch"), "all_bets": _wl(head)}
    curve = pooled.get("curve") or record.get("curve") or []
    if curve and all(isinstance(p, dict) and p.get("w") is not None for p in curve):
        start = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
        last = [p for p in curve if str(p.get("date") or "") >= start]
        if last:
            net = sum(float(p.get("day_u") or 0) for p in last)
            out["last_30_days"] = {"wins": sum(p["w"] for p in last), "losses": sum(p["l"] for p in last),
                                   "net_units": round(net, 2)}
    sp = ((record.get("by_sport") or {}).get(sport) or {}) if sport else {}
    if sp:
        out[f"{sport}_bets"] = _wl((sp.get("pooled") or {}).get("overall") or sp.get("overall"))
    lk = record.get("likely") or {}
    if lk:
        out["most_likely_board"] = _wl(lk)
        bands = [{"model_said": f"{int(b['lo'] * 100)}-{int(min(b['hi'], 1) * 100)}%",
                  "hit": b.get("actual"), "bets": b.get("n")}
                 for b in (lk.get("bands") or []) if isinstance(b, dict) and b.get("n")]
        if bands:
            out["most_likely_calibration"] = bands
    bm = head.get("by_market") or {}
    graded = [(m, v) for m, v in bm.items() if isinstance(v, dict)
              and (v.get("w") or 0) + (v.get("l") or 0) >= 10]
    if graded:
        graded.sort(key=lambda mv: -(mv[1].get("net_u") or 0))
        row = lambda mv: {"market": mv[0], "wins": mv[1].get("w"), "losses": mv[1].get("l"),  # noqa: E731
                          "net_units": round(float(mv[1].get("net_u") or 0), 2)}
        out["best_markets"] = [row(mv) for mv in graded[:3]]
        out["worst_markets"] = [row(mv) for mv in graded[-3:][::-1]]
    return out


def injury_facts(injuries: dict, sport: str, teams: set[str], players: set[str]) -> list[dict]:
    rows = ((injuries or {}).get("sports") or {}).get(sport) or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if (str(r.get("team") or "") in teams) or (_norm(r.get("player")).strip() in players):
            out.append({k: r[k] for k in ("player", "team", "status", "injury", "detail", "position")
                        if r.get(k) not in (None, "")})
        if len(out) >= MAX_INJURIES:
            break
    return out


# ---- the request ---------------------------------------------------------------
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


def build_request(board: dict, question: str, history=None, pick: str = "",
                  data_dir: Path | None = None) -> dict:
    """Everything one call sends, apart from the model and the client."""
    question = str(question or "").strip()[:MAX_QUESTION]
    data_dir = Path(data_dir) if data_dir else ROOT / "web" / "data"
    sport = str((board or {}).get("sport") or "")
    want = intents(question)
    hits = _hits(board, question)
    rows = [_shown(h) for h in hits]
    focus = _ex.find_row(board, pick) if pick else None
    facts: dict = {"rows_matching_the_question": rows}
    sources: list[dict] = []
    if focus is not None:
        f = detailed(focus)
        f.update(_ex.facts_for(focus))
        facts["the_pick_this_was_asked_from"] = f
    for lst, r in [(None, focus)] * (focus is not None) + [(h[1], h[2]) for h in hits]:
        label = (r.get("pick_label") or " ".join(str(x) for x in (r.get("player"), r.get("side"),
                 r.get("line"), r.get("market_label") or r.get("market")) if x not in (None, ""))).strip()
        prop = _ex.pick_id(r) if r.get("player") and r.get("line") is not None and lst != "game_bets" else ""
        if label and all(s["label"] != label for s in sources):
            sources.append({"label": label, "prop": prop})
    games = named_games(board, question, rows + ([compact(focus)] if focus is not None else []))
    if "weather" in want and not games:
        games = [g for g in (board or {}).get("games") or [] if isinstance(g, dict)][:12]
    if games:
        facts["games"] = [game_facts(board, g) for g in games]
        sources += [{"label": _game_label(g), "prop": ""} for g in games]
    if "record" in want:
        rec = record_facts(_load_json(data_dir / "record.json"), sport)
        if rec:
            facts["our_record"] = rec
            sources.append({"label": "Our record", "prop": ""})
    if "injury" in want:
        teams = set()
        for r in rows + ([compact(focus)] if focus is not None else []):
            teams |= _codes(r)
        teams |= _caps(question)
        for g in games:
            teams |= {str(g.get("home") or ""), str(g.get("away") or "")}
        players = {_norm(r.get("player")).strip() for r in rows if r.get("player")}
        inj = injury_facts(_load_json(data_dir / "injuries.json"), sport, teams, players)
        facts["injury_board"] = inj or "nothing listed for these teams"
        sources.append({"label": "Injury board", "prop": ""})
    if "longshot" in want:
        shots = [compact(r) for r in (board or {}).get("long_shots") or [] if isinstance(r, dict)][:6]
        if shots:
            facts["long_shots"] = shots
    system = [
        {"type": "text", "text": SYSTEM},
        {"type": "text", "text": "Tonight's board summary:\n"
         + json.dumps(board_summary(board), sort_keys=True, separators=(",", ":")),
         "cache_control": {"type": "ephemeral"}},
    ]
    messages = clean_history(history) + [{"role": "user", "content":
        f"{question}\n\nFacts for this question:\n" + json.dumps(facts, sort_keys=True, separators=(",", ":"))}]
    return {"system": system, "messages": messages, "matched": len(rows),
            "focused": focus is not None, "sources": sources[:8], "sections": sorted(facts)}


# ---- the answer cache and the usage log -----------------------------------------
_LOCK = threading.Lock()


def _read(path: Path) -> dict:
    return _load_json(path)


def _write(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass                                       # the answer was still served


def answer_key(board_name: str, board: dict, pick: str, question: str) -> str:
    return "\t".join((board_name, _ex.board_stamp(board), pick or "", cache_words(question)))


def cached_answer(key: str) -> dict | None:
    with _LOCK:
        hit = _read(CACHE_PATH).get(key)
    return dict(hit) if isinstance(hit, dict) and hit.get("text") else None


def remember_answer(key: str, entry: dict) -> None:
    with _LOCK:
        mem = _read(CACHE_PATH)
        mem[key] = {**entry, "at": time.time()}
        if len(mem) > CACHE_MAX:
            for k in sorted(mem, key=lambda k: (mem[k] or {}).get("at", 0))[: len(mem) - CACHE_MAX]:
                mem.pop(k, None)
        _write(CACHE_PATH, mem)


def estimate_usd(model: str, usage: dict) -> float | None:
    p = PRICES.get(model)
    if not p:
        return None
    i, o = p
    return round((usage.get("in", 0) * i + usage.get("out", 0) * o
                  + usage.get("cache_read", 0) * i * 0.1
                  + usage.get("cache_write", 0) * i * 1.25) / 1e6, 6)


def log_usage(model: str, response=None, cached: bool = False, today: str | None = None) -> None:
    """Add one question to today's line in the usage log."""
    u = getattr(response, "usage", None)
    got = {"in": int(getattr(u, "input_tokens", 0) or 0),
           "out": int(getattr(u, "output_tokens", 0) or 0),
           "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0),
           "cache_write": int(getattr(u, "cache_creation_input_tokens", 0) or 0)}
    day = today or _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    with _LOCK:
        log = _read(USAGE_PATH)
        days = log.setdefault("days", {})
        d = days.setdefault(day, {"calls": 0, "cached": 0, "in": 0, "out": 0,
                                  "cache_read": 0, "cache_write": 0, "usd": 0.0})
        if cached:
            d["cached"] += 1
        else:
            d["calls"] += 1
            for k, v in got.items():
                d[k] += v
            usd = estimate_usd(model, got)
            if usd is not None:
                d["usd"] = round(d["usd"] + usd, 6)
        for k in sorted(days)[:-USAGE_DAYS]:
            days.pop(k, None)
        _write(USAGE_PATH, log)


# ---- the call ------------------------------------------------------------------
def _client():
    try:
        import anthropic
    except ImportError as exc:
        raise _ex.NotConfigured("the anthropic package is not installed") from exc
    return anthropic.Anthropic()


def _call(client, model: str, req: dict):
    kw = dict(model=model, max_tokens=MAX_TOKENS, system=req["system"], messages=req["messages"])
    extra = {"output_config": {"effort": "low"}} if model in LOW_EFFORT_MODELS else {}
    if model in FALLBACK_FOR and hasattr(getattr(client, "beta", None), "messages"):
        try:
            return client.beta.messages.create(betas=[FALLBACK_BETA],
                                               fallbacks=[{"model": FALLBACK_TO}], **kw, **extra)
        except TypeError:
            pass                                   # an SDK too old for `fallbacks`
    if extra:
        try:
            return client.messages.create(**kw, **extra)
        except TypeError:
            pass                                   # an SDK too old for `output_config`
    return client.messages.create(**kw)


def ask(board: dict, question: str, history=None, pick: str = "", client=None,
        board_name: str = "", data_dir: Path | None = None) -> dict:
    """One answer: ``{"text", "model", "refused", "matched", "focused",
    "sources", "cached"}``. Raises ValueError for an empty question,
    NotConfigured, Unavailable.
    """
    if not str(question or "").strip():
        raise ValueError("empty question")
    model = model_name()
    req = build_request(board, question, history, pick, data_dir)
    base = {"model": model, "matched": req["matched"], "focused": req["focused"],
            "sources": req["sources"]}
    fresh = not clean_history(history)
    key = answer_key(board_name, board, pick, question) if fresh and board_name else ""
    if key:
        hit = cached_answer(key)
        if hit:
            log_usage(model, cached=True)
            return {**base, "text": hit["text"], "refused": bool(hit.get("refused")), "cached": True}
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise _ex.NotConfigured("ANTHROPIC_API_KEY is not set")
        client = _client()
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
    log_usage(model, response)
    if getattr(response, "stop_reason", "") == "refusal":
        return {**base, "text": "Ask declined to answer that one.", "refused": True, "cached": False}
    text = "".join(getattr(b, "text", "") for b in getattr(response, "content", None) or []
                   if getattr(b, "type", "") == "text").strip()
    if not text:
        raise _ex.Unavailable("the answer had no text")
    if key:
        remember_answer(key, {"text": text, "refused": False})
    return {**base, "text": text, "refused": False, "cached": False}


def usage_report(days: int = 7) -> str:
    log = _read(USAGE_PATH).get("days") or {}
    lines = ["day         calls  cached  in_tok   out_tok  cache_rd  ~usd"]
    total = 0.0
    for day in sorted(log)[-days:]:
        d = log[day]
        total += d.get("usd") or 0
        lines.append(f"{day}  {d.get('calls', 0):5}  {d.get('cached', 0):6}  {d.get('in', 0):7}  "
                     f"{d.get('out', 0):7}  {d.get('cache_read', 0):8}  {d.get('usd', 0):.4f}")
    lines.append(f"total ~${total:.4f} over {min(days, len(log))} day(s); model {model_name()}")
    return "\n".join(lines)


if __name__ == "__main__":                              # python3 -m engine.askbot usage
    import sys
    if sys.argv[1:2] == ["usage"]:
        print(usage_report(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
    else:
        print("usage: python3 -m engine.askbot usage [days]")
