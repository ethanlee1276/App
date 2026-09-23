"""Ask Qellys — any sports question, answered from our data.

Ethan, 2026-09-23, on Rithmm's "Ask Scout": "I like the Ask Scout AI
agent." Then, the same day: "make the ask feature better and make it
cost less credits. We have so much data backed up on the site ... we
can use that too. Also turn the model down." And then: "the ai bot is
only responding for [whatever] sport you have selected. It should work
for any question no matter what sport is selected. And it should also
be able [to] pull up any player data. The lions are playing the Jets
this week and I asked it about how the lions have done against the
packers and it wouldn't answer ... It should answer any question no
matter the team schedule or player schedule."

ANY LEAGUE, ANY TEAM, ANY SEASON WE HOLD. The league the reader has
open is where they are standing, not what they may ask about:

  * every league's board rides along (BOARD_FILES), and the rows a
    question names are found on whichever board they are on;
  * three TOOLS read the rest, and the model calls them when the
    question is about something tonight's facts do not hold:
    `team_history` (every stored final: a team's seasons with its
    offense and defense rank and its latest results, or every meeting
    of two teams with the line, the total and who covered),
    `player_history` (any player's latest games and season averages,
    or every game he has played against one team; a UFC fighter's
    record) and `tonight_board` (any league's board tonight, for a
    team named by nickname or city). Two more read the WHOLE LEAGUE —
    Ethan, 2026-09-23: "I can't even ask it who has the worst defense in
    the league": `league_table` (every team in a season ranked by points
    allowed, points scored, differential, win rate, cover rate or overs)
    and `player_leaders` (a season's leaders in any stat we log, by total
    or per game). They read engine/teamdex.py,
    engine/statlogs.py and engine/playersearch.py — the same lookups
    the Teams and Players pages make — so a name resolves the way the
    search box resolves it. At most MAX_TOOL_ROUNDS rounds of at most
    MAX_TOOL_CALLS lookups, each answer capped at MAX_TOOL_CHARS; the
    last round is told it may not look anything else up.

WHAT IT MAY SAY. Only what our own data says. Most of it is picked here
in code rather than by the model, so most questions cost one call:

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

A short summary of the open league's night, and a count of every other
league's, rides in the system prompt behind a cache breakpoint — after
the tool definitions, so both are read from the cache. The model is told to answer from those facts alone, to say
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
    trimmed; every section above is capped. A lookup costs one more
    round, and only a question that needs one makes it.
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

#: Every league's board, by the name the page asks for it with. A question
#: is read against all of them, whichever league the reader has open.
BOARD_FILES = {"nfl": "recommendations.json", "cfb": "cfb.json", "nba": "nba.json",
               "wnba": "wnba.json", "mlb": "mlb_recommendations.json"}
#: The order leagues are tried in when a name could be more than one team;
#: the reader's own league always goes first.
LEAGUES = ("nfl", "nba", "mlb", "wnba", "cfb")
#: A league named in the question, for the record's per-league line.
LEAGUE_WORDS = {"nfl": r"\bnfl\b", "cfb": r"\b(?:cfb|college football|ncaaf?)\b",
                "nba": r"\bnba\b", "wnba": r"\bwnba\b", "mlb": r"\b(?:mlb|baseball)\b"}

#: The lookups: rounds of tool calls one question may take, calls in all,
#: and how much each answer carries.
MAX_TOOL_ROUNDS = 3
MAX_TOOL_CALLS = 6
MAX_TOOL_CHARS = 6000
LEAGUE_ROWS = 10
LEAGUE_ROWS_MAX = 40
H2H_GAMES = 12
TEAM_SEASONS = 3
TEAM_RECENT = 8
PLAYER_GAMES = 10
MAX_ARG = 80

#: Where the lookups read. None is the site's own: engine.db.DEFAULT_DB,
#: the fighter dossiers, the rosters in web/data. Tests point them at
#: temp files — a test never reads the box.
HISTORY_DB = None
UFC_PATH = None
ROSTER_DIR = None

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
    "site covering the NFL, college football, the NBA, the WNBA, MLB and the UFC. Answer "
    "the reader's question about any league, team, player or game: tonight's, or any "
    "season we hold. The league the reader has open is only where they are standing. "
    "Never decline because a team or player is not playing tonight, plays someone else "
    "this week, or is in another sport.\n"
    "Your facts: the board summary below; the facts sent with the question (rows from "
    "every league's board tonight that match it, with their recent games and form; "
    "their games with lines, weather and rest; our record; the injury board); and your "
    "tools, which read our history database (every stored final score with its spread "
    "and total, every stored player game log) and any league's board tonight. When the "
    "question is about the past, such as a team's record, two teams' meetings, or how "
    "a player has done lately or against a team, look it up with the tools before you "
    "answer. For a question about the whole league (the best or worst at something, "
    "standings, a ranking, who leads a stat) use league_table or player_leaders; never "
    "ask the reader to name teams for it. The league is the one the question or the "
    "conversation is about, else the one the reader has open. Call several tools at "
    "once when you need several things, and pass the sport when you know it.\n"
    "Use ONLY the facts you are given and the tools return. Do not add statistics, "
    "injuries, news, odds or any number that is not in them. If after looking they do "
    "not cover the question, say plainly that our data has nothing on it, say which "
    "seasons we do hold when that is why, and name the closest thing we have.\n"
    "hit_prob, model_prob and win_prob are our model's chance the bet wins; fair_prob "
    "and implied_prob are what the price implies; edge is the gap. A row with "
    "recommended false or no stake is not one of our bets: say so. Our record is real "
    "and includes losses; quote it straight.\n"
    f"Lead with the direct answer in one sentence, then the one or two facts behind it. "
    f"At most {WORDS} words, plain words a first-time bettor understands, no headings. "
    "Never tell the reader to bet or how much; a stake on a row is our model's, not "
    "advice. You cannot see the internet or live scores, and you say so if asked."
)


def _tool(name: str, what: str, props: dict, required: str) -> dict:
    return {"name": name, "description": what,
            "input_schema": {"type": "object", "properties": props, "required": [required]}}


_SPORT_ARG = {"type": "string", "enum": list(LEAGUES),
              "description": "The league, when you know it."}
_OPP_ARG = {"type": "string",
            "description": "Optional: the other team, by name, nickname, city or abbreviation."}

#: What a league table ranks by: {sort: (row field, higher is better, words)}.
TABLE_SORTS = {
    "points_allowed": ("allowed_per_game", False, "points allowed per game"),
    "points_scored": ("points_per_game", True, "points scored per game"),
    "point_diff": ("point_diff", True, "point differential per game"),
    "win_pct": ("win_pct", True, "win percentage"),
    "ats_cover_pct": ("ats_cover_pct", True, "against-the-spread cover rate"),
    "over_pct": ("over_pct", True, "share of games that went over the total"),
}


def _stat_menu() -> str:
    """Every stat player_leaders can rank, by league — read from the logs'
    own market list, so a stat added there is offered here."""
    from engine import statlogs as SL
    return "; ".join(f"{s.upper()}: " + ", ".join(label for _, label in m)
                     for s, m in SL.SPORT_MARKETS.items())


#: Sorted by name and never changed per request: the tools are the front of
#: the cached prefix, and a byte of difference there re-bills all of it.
TOOLS = [
    _tool("league_table",
          "Every team in one league for one season, ranked, from our stored final scores: "
          "for any question about the whole league, such as the best or worst defense "
          "(points_allowed), the best offense (points_scored), standings (win_pct), who "
          "covers the spread most (ats_cover_pct) or whose games go over (over_pct). "
          "order best puts the best first (for points_allowed, the fewest allowed); order "
          "worst puts the worst first. The latest stored season unless you pass another; "
          "each row says how many games it rests on, and early in a season you say so.",
          {"sport": _SPORT_ARG,
           "sort": {"type": "string", "enum": list(TABLE_SORTS)},
           "order": {"type": "string", "enum": ["best", "worst"]},
           "season": {"type": "integer", "description": "Optional: a season year."},
           "limit": {"type": "integer", "description": "Optional: how many teams (default 10)."}},
          "sort"),
    _tool("player_history",
          "One player's games from our history database, in any league we cover and any "
          "stored season, whether or not he plays tonight; for a UFC fighter, his record and "
          "measured rates. Without opponent: his latest games with every stat, and his "
          "per-game averages this season. With opponent: every stored game he has played "
          "against that team, whichever club he was with, and his averages in them. A "
          "misspelled name resolves to the closest match, and the result says who it found.",
          {"player": {"type": "string", "description": "The name as the reader wrote it."},
           "opponent": _OPP_ARG,
           "sport": {**_SPORT_ARG, "enum": list(LEAGUES) + ["ufc"]}}, "player"),
    _tool("player_leaders",
          "A league's leaders in one stat for one season, from our stored player game logs: "
          "who has the most rushing yards, home runs, points and so on. by total ranks season "
          "totals; by per_game ranks averages among players with at least half the games of "
          "the busiest. The latest stored season unless you pass another. Stats we hold: "
          + _stat_menu() + ".",
          {"sport": _SPORT_ARG,
           "stat": {"type": "string", "description": "The stat, by its name above."},
           "by": {"type": "string", "enum": ["total", "per_game"]},
           "season": {"type": "integer", "description": "Optional: a season year."},
           "limit": {"type": "integer", "description": "Optional: how many players (default 10)."}},
          "stat"),
    _tool("team_history",
          "A team's final scores from our history database, in any league we cover, whether "
          "or not it plays tonight. With opponent: every stored meeting of the two, newest "
          "first, each with the score, the spread and total, and who covered, and the "
          "head-to-head totals. Without opponent: its record season by season with its "
          "offense and defense rank, and its latest results. Names can be nicknames, cities "
          "or abbreviations.",
          {"team": {"type": "string", "description": "The team, as the reader wrote it."},
           "opponent": _OPP_ARG, "sport": _SPORT_ARG}, "team"),
    _tool("tonight_board",
          "Tonight's rows on one league's board, or on every league's, for a team, player or "
          "game: our bets, props, the most-likely board, long shots, and the game's lines and "
          "conditions. For a league other than the one summarised, or a team named by "
          "nickname or city.",
          {"query": {"type": "string", "description": "A team, player or matchup."},
           "sport": _SPORT_ARG}, "query"),
]


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


def _our_bets(board: dict) -> list[dict]:
    return [r for r in (board or {}).get("recommendations") or []
            if isinstance(r, dict) and r.get("recommended")]


def board_summary(board: dict, boards: dict | None = None) -> dict:
    """Tonight in brief: our bets, the likeliest rows, the games — and how
    much every other league has on tonight, so the model knows to look."""
    b = board or {}
    recs = _our_bets(b)
    likely = [r for r in b.get("most_likely") or [] if isinstance(r, dict)]
    likely.sort(key=lambda r: -(r.get("model_prob") or 0))
    out = {
        "sport": b.get("sport") or "",
        "date": b.get("date") or "",
        "our_bets": [compact(r) for r in recs[:SUMMARY_EACH]],
        "our_bets_total": len(recs),
        "most_likely": [compact(r) for r in likely[:SUMMARY_EACH]],
        "games": [_game_label(g) for g in (b.get("games") or [])[:20] if isinstance(g, dict)],
    }
    if boards and len(boards) > 1:
        out["every_league_tonight"] = {
            s: {"games": len([g for g in x.get("games") or [] if isinstance(g, dict)]),
                "our_bets": len(_our_bets(x))} for s, x in sorted(boards.items())}
    return out


_BOARDS: dict = {}


def board_at(path) -> dict | None:
    """A board file, parsed once per write of it. Every question reads every
    league's board, and the builds write each a few times a day."""
    try:
        st = os.stat(path)
    except (OSError, TypeError):
        return None
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _BOARDS.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    data = _load_json(Path(path)) or None
    if data is not None:
        _BOARDS[str(path)] = (stamp, data)
    return data


def _all_boards(board: dict, boards: dict | None) -> dict:
    """{league: board}, the reader's own always in it."""
    out = {s: b for s, b in (boards or {}).items() if isinstance(b, dict) and b}
    if board and not any(b is board for b in out.values()):
        out[str(board.get("sport") or "nfl")] = board
    return out


def _league_of(board: dict, boards: dict) -> str:
    for s, b in boards.items():
        if b is board:
            return s
    return str((board or {}).get("sport") or "nfl")


def _order(have, prefer: str) -> list[str]:
    """The leagues in ``have``, the reader's first, then LEAGUES order."""
    have = list(have)
    return list(dict.fromkeys(s for s in [prefer, *LEAGUES, *sorted(have)] if s in have))


def _leagues(sport: str, prefer: str) -> list[str]:
    """One league when the model named it; every league otherwise."""
    return [sport] if sport in LEAGUES else _order(LEAGUES, prefer)


def _hits_all(boards: dict, question: str, prefer: str) -> list[tuple]:
    """(score, list, row, league) across every league's board, best first,
    the reader's own league first on a tie."""
    order = _order(boards, prefer)
    hits = []
    for i, s in enumerate(order):
        hits += [(h[0], i, h[1], h[2], s) for h in _hits(boards[s], question)]
    hits.sort(key=lambda h: (-h[0], h[1]))
    out, weak = [], 0
    for score, _, lst, r, s in hits:
        if score == 1:
            weak += 1
            if weak > MAX_WEAK:
                continue
        out.append((score, lst, r, s))
    return out[:MAX_MATCHED]


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


# ---- the lookups (the tools) -------------------------------------------------------
def _n(x):
    """14.0 → 14, so a score reads as a score."""
    return int(x) if isinstance(x, float) and x.is_integer() else x


def _history():
    """The history database, or None where there is none — never created here."""
    from engine import db as _db
    path = Path(HISTORY_DB or _db.DEFAULT_DB)
    return _db.connect(str(path)) if path.exists() else None


def _when(season, period, date, sport: str) -> str:
    p = str(period or "")
    if sport in ("nfl", "cfb") and p.isdigit():
        return f"{season} week {int(p)}"
    return str(date or p or season)


def _seasons_held(conn, sport: str) -> str:
    r = conn.execute("SELECT MIN(season), MAX(season) FROM games WHERE sport=? "
                     "AND home_score IS NOT NULL", (sport,)).fetchone()
    if not r or r[0] is None:
        return "none"
    return str(r[0]) if r[0] == r[1] else f"{r[0]}-{r[1]}"


def _team_line(acc: dict) -> dict:
    """A record as a reader says it."""
    a = acc or {}
    if not a.get("games"):
        return {"games": 0}
    out = {"games": a["games"], "record": a.get("record"),
           "points_per_game": a.get("pf_per_game"), "allowed_per_game": a.get("pa_per_game")}
    w, l, p = a.get("ats_w") or 0, a.get("ats_l") or 0, a.get("ats_p") or 0
    if w + l + p:
        out["against_the_spread"] = f"{w}-{l}" + (f"-{p}" if p else "")
    o, u, p = a.get("over") or 0, a.get("under") or 0, a.get("ou_p") or 0
    if o + u + p:
        out["over_under"] = f"{o} over, {u} under" + (f", {p} push" if p else "")
    return out


def _final(row: dict, sport: str, name=None) -> dict:
    """One final as the looked-up team saw it."""
    out = {"when": _when(row["season"], row["period"], row.get("date"), sport),
           "result": f"{row['result']} {_n(row['points_for'])}-{_n(row['points_against'])}",
           "where": "home" if row["at_home"] else "away"}
    if row.get("opponent"):
        out["vs"] = name(row["opponent"]) if name else row["opponent"]
    if row.get("line") is not None:
        out["line"] = _n(row["line"])
    if row.get("covered") is not None:
        out["covered"] = "push" if row["covered"] == "push" else ("yes" if row["covered"] else "no")
    if row.get("total") is not None:
        out["total"] = _n(row["total"])
        if row.get("ou"):
            out["went"] = row["ou"]
    return out


def _rank(r, n) -> str | None:
    return f"{r} of {n}" if r and n else None


def team_history(team: str, opponent: str = "", sport: str = "", prefer: str = "") -> dict:
    """Every stored meeting of two teams, or one team's seasons and latest
    results — in whichever league the names resolve in, the reader's first."""
    from engine import teamdex as T
    if not team:
        return {"error": "no team named"}
    conn = _history()
    if conn is None:
        return {"error": "our history database is not available"}
    try:
        for s in _leagues(sport, prefer):
            known = T.teams(conn, s)
            mine = T.resolve(team, s, known) if known else []
            if not mine:
                continue
            theirs = [x for x in T.resolve(opponent, s, known) if x != mine[0]] if opponent else []
            if opponent and not theirs:
                continue
            name = lambda c: T.label(c, s)                               # noqa: E731
            out = {"sport": s, "team": name(mine[0]), "seasons_we_hold": _seasons_held(conn, s)}
            also = [name(x) for x in mine[1:3]] + [name(x) for x in theirs[1:3]]
            if also:
                out["names_that_also_match"] = also
            if theirs:
                h = T.head_to_head(conn, s, mine[0], theirs[0])
                out.update({"opponent": name(theirs[0]), "meetings_stored": len(h["games"]),
                            "head_to_head": _team_line(h["summary"]),
                            "meetings": [_final(g, s) for g in h["games"][:H2H_GAMES]]})
                return out
            p = T.profile(conn, s, mine[0])
            out["all_stored_games"] = _team_line(p.get("career"))
            out["by_season"] = [{"season": r["season"], **_team_line(r),
                                 "offense_rank": _rank(r.get("offense_rank"), r.get("teams_ranked")),
                                 "defense_rank": _rank(r.get("defense_rank"), r.get("teams_ranked"))}
                                for r in (p.get("seasons") or [])[:TEAM_SEASONS]]
            out["latest_games"] = [_final(g, s, name) for g in T.results(conn, s, mine[0], TEAM_RECENT)]
            return out
    finally:
        conn.close()
    return {"found": False, "note": f"no stored games for {team}"
            + (f" against {opponent}" if opponent else "")
            + (f" in the {sport.upper()}" if sport else "")}


def _find_players(q: str, sport: str, prefer: str) -> list[dict]:
    """The Players page's own search: every league's logs and rosters, and
    the fighters — one sport's when the model named it."""
    from engine import playersearch as PS
    from engine import statlogs as SL
    from engine.ufc import fighters as F
    from engine import db as _db
    only = sport if sport in SL.SPORT_MARKETS or sport == "ufc" else ""
    logs = [only] if only in SL.SPORT_MARKETS else ([] if only else list(SL.SPORT_MARKETS))
    per = dict(SL.search_by_sport(q, 5, logs, str(HISTORY_DB or _db.DEFAULT_DB), ROSTER_DIR)) if logs else {}
    if only in ("", "ufc"):
        per["ufc"] = F.search(q, limit=5, path=UFC_PATH)
    lead = only or prefer
    return PS.merge(per, q, 5, PS.source_order(lead), prefer=lead)


def _stats(rows, labels: dict, limit: int, sport: str) -> list[dict]:
    """player_game_logs rows → one entry per game, newest first."""
    games, seen = [], {}
    for r in rows:
        key = (r["season"], r["period"], r["game_id"])
        g = seen.get(key)
        if g is None:
            if len(games) >= limit:
                continue
            g = {"when": _when(r["season"], r["period"], None, sport), "team": r["team"],
                 "vs": r["opponent"], "where": "home" if r["home"] else "away", "stats": {}}
            seen[key] = g
            games.append(g)
        g["stats"][labels[r["market"]]] = _n(round(float(r["value"]), 2))
    return games


def _averages(games: list[dict]) -> dict:
    sums: dict = {}
    for g in games:
        for k, v in (g.get("stats") or {}).items():
            if isinstance(v, (int, float)):
                sums.setdefault(k, []).append(float(v))
    return {k: _n(round(sum(v) / len(v), 1)) for k, v in sums.items()}


def player_history(player: str, opponent: str = "", sport: str = "", prefer: str = "") -> dict:
    """A player's latest games and season averages, or every stored game he
    has against one team; a fighter's record."""
    from engine import statlogs as SL
    from engine import teamdex as T
    if not player:
        return {"error": "no player named"}
    hits = _find_players(player, sport, prefer)
    if not hits:
        return {"found": False, "note": f"no player or fighter called {player} in our data"}
    top = hits[0]
    s, name = str(top.get("sport") or ""), str(top.get("player") or "")
    out = {"player": name, "sport": s}
    for k in ("team", "position"):
        if top.get(k):
            out[k] = top[k]
    if _norm(name) != _norm(player):
        out["matched"] = f"the closest name to \u201c{player}\u201d"
    others = [f"{h['player']} ({str(h.get('sport') or '').upper()})" for h in hits[1:4]
              if (h.get("player"), h.get("sport")) != (name, s)]
    if others:
        out["other_names_that_match"] = others
    if s == "ufc":
        out["fighter"] = top.get("fighter") or {}
        return out
    markets = SL.SPORT_MARKETS.get(s) or ()
    labels = dict(markets)
    conn = _history()
    if conn is None or not markets:
        out["note"] = "no stored games for him"
        return out
    try:
        ids = [m for m, _ in markets]
        marks = ",".join("?" * len(ids))
        cols = "SELECT season, period, game_id, team, opponent, home, market, value FROM player_game_logs "
        if opponent:
            keys = [k for k in T.resolve(opponent, s)[:2]] + [opponent]
            for key in keys:
                opp = SL._resolve_opponent(conn, s, name, key)
                if opp:
                    break
            rows = conn.execute(cols + f"WHERE sport=? AND player=? AND opponent=? AND market IN ({marks}) "
                                "ORDER BY season DESC, period DESC",
                                (s, name, opp, *ids)).fetchall() if opp else []
            games = _stats(rows, labels, PLAYER_GAMES, s)
            out["opponent"] = T.label(opp, s) if opp else opponent
            out["games_against"] = games
            if games:
                out["averages_against"] = _averages(games)
            else:
                out["note"] = f"no stored games of his against {opponent}"
            return out
        rows = conn.execute(cols + f"WHERE sport=? AND player=? AND market IN ({marks}) "
                            "ORDER BY season DESC, period DESC", (s, name, *ids)).fetchall()
        games = _stats(rows, labels, PLAYER_GAMES, s)
        out["latest_games"] = games
        if not games:
            out["note"] = "no stored games for him"
            return out
        season = rows[0]["season"]
        avg = conn.execute(f"SELECT market, AVG(value) AS v, COUNT(DISTINCT game_id) AS n "
                           f"FROM player_game_logs WHERE sport=? AND player=? AND season=? "
                           f"AND market IN ({marks}) GROUP BY market", (s, name, season, *ids)).fetchall()
        if avg:
            out["season_averages"] = {"season": season, "games": max(r["n"] for r in avg),
                                      "per_game": {labels[r["market"]]: _n(round(float(r["v"]), 1))
                                                   for r in avg}}
        return out
    finally:
        conn.close()


def _league(sport: str, prefer: str) -> str:
    return sport if sport in LEAGUES else (prefer if prefer in LEAGUES else LEAGUES[0])


def _limit(n) -> int:
    try:
        return max(1, min(int(n or LEAGUE_ROWS), LEAGUE_ROWS_MAX))
    except (TypeError, ValueError):
        return LEAGUE_ROWS


def _season_of(seasons: list, asked) -> int:
    try:
        return int(asked) if asked and int(asked) in seasons else seasons[0]
    except (TypeError, ValueError):
        return seasons[0]


def _ranks(rows: list[dict], key: str, higher: bool) -> list[dict]:
    """Rank 1 is the best at ``key``; equal values share a rank, and a row
    with no value (no lines to cover, say) goes last, unranked."""
    have = sorted([r for r in rows if r.get(key) is not None],
                  key=lambda r: (-r[key] if higher else r[key], r.get("team") or r.get("player") or ""))
    last, rank = None, 0
    for i, r in enumerate(have, 1):
        if last is None or abs(r[key] - last) > 1e-9:
            rank, last = i, r[key]
        r["rank"] = rank
    return have + [r for r in rows if r.get(key) is None]


def league_table(sport: str = "", sort: str = "points_allowed", order: str = "best", season=None,
                 limit=None, prefer: str = "") -> dict:
    """Every team in a league's season, ranked by one measure."""
    from engine import teamdex as T
    if sort not in TABLE_SORTS:
        return {"error": "sort by one of: " + ", ".join(TABLE_SORTS)}
    s = _league(sport, prefer)
    conn = _history()
    if conn is None:
        return {"error": "our history database is not available"}
    try:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM games WHERE sport=? AND home_score IS NOT NULL "
            "ORDER BY season DESC", (s,))]
        if not seasons:
            return {"found": False, "note": f"no stored {s.upper()} games"}
        year = _season_of(seasons, season)
        table = T.season_table(conn, s, year)
    finally:
        conn.close()
    rows = []
    for team, a in table.items():
        g = a.get("games") or 0
        if not g:
            continue
        ats, ou = a["ats_w"] + a["ats_l"], a["over"] + a["under"]
        rows.append({**_team_line(a), "team": T.label(team, s),
                     "win_pct": round((a["wins"] + a["ties"] / 2) / g, 3),
                     "point_diff": a.get("point_diff"),
                     "ats_cover_pct": round(a["ats_w"] / ats, 3) if ats else None,
                     "over_pct": round(a["over"] / ou, 3) if ou else None})
    field, higher, words = TABLE_SORTS[sort]
    ranked = _ranks(rows, field, higher)
    if order == "worst":
        ranked = [r for r in ranked if r.get("rank")][::-1] + [r for r in ranked if not r.get("rank")]
    keep = [{k: r[k] for k in ("rank", "team", "games", "record", "points_per_game", "allowed_per_game",
                                 "point_diff", "against_the_spread", "over_under") if r.get(k) is not None}
            for r in ranked[:_limit(limit)]]
    return {"sport": s, "season": year, "seasons_we_hold": f"{min(seasons)}-{max(seasons)}"
            if len(seasons) > 1 else str(seasons[0]),
            "ranked_by": words, "order": "worst first" if order == "worst" else "best first",
            "teams_ranked": len(rows), "most_games_played": max((r["games"] for r in rows), default=0),
            "rows": keep}


def _market(stat: str, markets) -> tuple | None:
    """A stat as typed ("rushing yards", "rush_yds", "HR") → its (id, label)."""
    want = _norm(stat).strip()
    if not want:
        return None
    alias = {"hr": "home runs", "hrs": "home runs", "tds": "anytime td", "touchdowns": "anytime td",
             "points": "pts", "rebounds": "reb", "assists": "ast", "threes": "fg3m", "3s": "fg3m",
             "k": "strikeouts", "ks": "strikeouts"}
    want = alias.get(want, want)
    for mid, label in markets:
        if want in (_norm(mid).strip(), _norm(label).strip(), _norm(mid.replace("_", " ")).strip()):
            return mid, label
    for mid, label in markets:
        words = _norm(label).split()
        if all(w in words or any(x.startswith(w) for x in words) for w in want.split()):
            return mid, label
    return None


def player_leaders(sport: str = "", stat: str = "", by: str = "total", season=None, limit=None,
                   prefer: str = "") -> dict:
    """A league's season leaders in one stat, by total or per game."""
    from engine import statlogs as SL
    s = _league(sport, prefer)
    markets = SL.SPORT_MARKETS.get(s) or ()
    m = _market(stat, markets)
    if not m:
        return {"error": f"the {s.upper()} stats we hold are: " + ", ".join(label for _, label in markets)}
    mid, label = m
    conn = _history()
    if conn is None:
        return {"error": "our history database is not available"}
    try:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND market=? ORDER BY season DESC",
            (s, mid))]
        if not seasons:
            return {"found": False, "note": f"no stored {s.upper()} {label} logs"}
        year = _season_of(seasons, season)
        rows = [dict(r) for r in conn.execute(
            "SELECT player, COUNT(DISTINCT game_id) AS games, SUM(value) AS total, AVG(value) AS avg "
            "FROM player_game_logs WHERE sport=? AND season=? AND market=? GROUP BY player",
            (s, year, mid))]
        most = max((r["games"] for r in rows), default=0)
        floor = max(1, -(-most // 2)) if by == "per_game" else 1
        pool = [r for r in rows if r["games"] >= floor]
        pool.sort(key=lambda r: (-(r["avg"] if by == "per_game" else r["total"]), r["player"]))
        top = pool[:_limit(limit)]
        for r in top:
            t = conn.execute("SELECT team FROM player_game_logs WHERE sport=? AND season=? AND player=? "
                             "ORDER BY period DESC LIMIT 1", (s, year, r["player"])).fetchone()
            r["team"] = t["team"] if t else ""
    finally:
        conn.close()
    return {"sport": s, "season": year, "stat": label,
            "ranked_by": ("per game, among players with at least %d games" % floor) if by == "per_game"
            else "season total",
            "players_ranked": len(pool), "most_games_played": most,
            "rows": [{"rank": i, "player": r["player"], "team": r["team"], "games": r["games"],
                      "total": _n(round(float(r["total"]), 1)), "per_game": _n(round(float(r["avg"]), 1))}
                     for i, r in enumerate(top, 1)]}


def _split(query: str) -> list[str]:
    """"Lions @ Jets" → ["Lions", "Jets"]."""
    parts = re.split(r"\s+(?:@|at|vs\.?|v\.?|versus|and|or)\s+|,|/", str(query or ""))
    return [p.strip() for p in parts if p.strip()]


def tonight_board(boards: dict, query: str, sport: str = "", prefer: str = "") -> dict:
    """Tonight's rows and games for a team, player or matchup, on one
    league's board or on the first two that have any."""
    from engine import teamdex as T
    if not query:
        return {"error": "nothing to look for"}
    found = []
    for s in ([sport] if sport in boards else _order(boards, prefer)):
        b = boards.get(s) or {}
        hits = _hits(b, query)
        codes = set(_caps(query))
        for part in _split(query):
            codes |= set(T.resolve(part, s)[:1])
        rows = [_shown(h) for h in hits]
        seen = {id(h[2]) for h in hits}
        for lst, r in _rows(b):
            if len(rows) >= MAX_MATCHED:
                break
            if id(r) not in seen and codes & _codes(r):
                seen.add(id(r))
                rows.append({"board": lst, **compact(r)})
        games = [game_facts(b, g) for g in b.get("games") or [] if isinstance(g, dict)
                 and {str(g.get("home") or ""), str(g.get("away") or "")} & codes][:MAX_GAMES]
        if rows or games:
            found.append({"sport": s, "date": b.get("date") or "", "rows": rows[:MAX_MATCHED],
                          "games": games})
            if len(found) >= 2:
                break
    if found:
        return {"boards": found}
    return {"found": False, "note": f"nothing on tonight's boards for {query}",
            "leagues_with_a_board_tonight": sorted(boards)}


def run_tool(name: str, args, boards: dict, prefer: str = "") -> dict:
    """One lookup, answered from our data. Never raises: a failed lookup is a
    sentence the model can pass on, not a failed question."""
    a = args if isinstance(args, dict) else {}
    arg = lambda k: str(a.get(k) or "").strip()[:MAX_ARG]              # noqa: E731
    sport = arg("sport").lower()
    try:
        if name == "team_history":
            return team_history(arg("team"), arg("opponent"), sport, prefer)
        if name == "player_history":
            return player_history(arg("player"), arg("opponent"), sport, prefer)
        if name == "tonight_board":
            return tonight_board(boards, arg("query"), sport, prefer)
        if name == "league_table":
            return league_table(sport, arg("sort") or "points_allowed", arg("order") or "best",
                                a.get("season"), a.get("limit"), prefer)
        if name == "player_leaders":
            return player_leaders(sport, arg("stat"), arg("by") or "total", a.get("season"),
                                  a.get("limit"), prefer)
    except Exception as exc:                                          # noqa: BLE001
        return {"error": f"the lookup failed ({type(exc).__name__})"}
    return {"error": f"there is no lookup called {name}"}


def fit(result: dict) -> str:
    """A lookup's answer as the model reads it, at most MAX_TOOL_CHARS: the
    longest list is halved until it fits, so what arrives is still JSON."""
    res = dict(result)
    text = json.dumps(res, separators=(",", ":"), default=str)
    while len(text) > MAX_TOOL_CHARS:
        lists = [k for k, v in res.items() if isinstance(v, list) and len(v) > 1]
        if not lists:
            return text[:MAX_TOOL_CHARS]
        k = max(lists, key=lambda k: len(json.dumps(res[k], default=str)))
        res[k] = res[k][: len(res[k]) // 2]
        text = json.dumps(res, separators=(",", ":"), default=str)
    return text


def tool_source(name: str, args, result: dict) -> dict | None:
    """The chip under an answer that says a lookup was made, and of what."""
    if not isinstance(result, dict) or result.get("error") or result.get("found") is False:
        return None
    if name == "team_history":
        label = (f"{result.get('team')} vs {result['opponent']}, past meetings" if result.get("opponent")
                 else f"{result.get('team')}, results")
    elif name == "player_history":
        label = f"{result.get('player')}, game logs" + (f" vs {result['opponent']}" if result.get("opponent") else "")
    elif name == "tonight_board":
        label = " and ".join(f"{b['sport'].upper()} board" for b in result.get("boards") or [])
    elif name == "league_table":
        label = f"{result['sport'].upper()} {result['season']} table, by {result['ranked_by']}"
    elif name == "player_leaders":
        label = f"{result['sport'].upper()} {result['season']} leaders, {result['stat']}"
    else:
        return None
    return {"label": label, "prop": ""} if label else None


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
                  data_dir: Path | None = None, boards: dict | None = None) -> dict:
    """Everything one call sends, apart from the model, the tools and the
    client. ``board`` is the league the reader has open; ``boards`` is every
    league's, and the rows a question names are found on any of them."""
    question = str(question or "").strip()[:MAX_QUESTION]
    data_dir = Path(data_dir) if data_dir else ROOT / "web" / "data"
    boards = _all_boards(board, boards)
    sport = _league_of(board, boards)
    want = intents(question)
    hits = _hits_all(boards, question, sport)
    rows = [{**_shown(h[:3]), "league": h[3]} for h in hits]
    focus, focus_league = None, sport
    for s in _order(boards, sport) if pick else ():
        focus = _ex.find_row(boards[s], pick)
        if focus is not None:
            focus_league = s
            break
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
    # The games: the open league's by any team code the question types, any
    # other league's only through the rows it matched there.
    games: list[tuple] = []
    for s in _order(boards, sport):
        mine = [r for r in rows if r["league"] == s]
        if focus is not None and focus_league == s:
            mine.append(compact(focus))
        if s != sport and not mine:
            continue
        games += [(s, g) for g in named_games(boards[s], question if s == sport else "", mine)]
    games = games[:MAX_GAMES]
    if "weather" in want and not games:
        games = [(sport, g) for g in boards[sport].get("games") or [] if isinstance(g, dict)][:12]
    if games:
        facts["games"] = [game_facts(boards[s], g) for s, g in games]
        sources += [{"label": _game_label(g), "prop": ""} for _, g in games]
    if "record" in want:
        named = [s for s, rx in LEAGUE_WORDS.items() if re.search(rx, question.lower())]
        rec = record_facts(_load_json(data_dir / "record.json"), (named or [sport])[0])
        if rec:
            facts["our_record"] = rec
            sources.append({"label": "Our record", "prop": ""})
    if "injury" in want:
        injuries = _load_json(data_dir / "injuries.json")
        inj: list[dict] = []
        for s in _order({sport, focus_league, *(r["league"] for r in rows)}, sport):
            teams = set()
            for r in [r for r in rows if r["league"] == s] + (
                    [compact(focus)] if focus is not None and focus_league == s else []):
                teams |= _codes(r)
            if s == sport:
                teams |= _caps(question)
            for gs, g in games:
                if gs == s:
                    teams |= {str(g.get("home") or ""), str(g.get("away") or "")}
            players = {_norm(r.get("player")).strip() for r in rows if r.get("player") and r["league"] == s}
            inj += injury_facts(injuries, s, teams, players)
        facts["injury_board"] = inj[:MAX_INJURIES] or "nothing listed for these teams"
        sources.append({"label": "Injury board", "prop": ""})
    if "longshot" in want:
        shots = [compact(r) for r in boards[sport].get("long_shots") or [] if isinstance(r, dict)][:6]
        if shots:
            facts["long_shots"] = shots
    system = [
        {"type": "text", "text": SYSTEM},
        {"type": "text", "text": "Tonight's board summary, for the league the reader has open:\n"
         + json.dumps(board_summary(board, boards), sort_keys=True, separators=(",", ":")),
         "cache_control": {"type": "ephemeral"}},
    ]
    messages = clean_history(history) + [{"role": "user", "content":
        f"{question}\n\nFacts for this question:\n" + json.dumps(facts, sort_keys=True, separators=(",", ":"))}]
    return {"system": system, "messages": messages, "matched": len(rows),
            "focused": focus is not None, "sources": sources[:8], "sections": sorted(facts),
            "boards": boards, "league": sport}


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


def answer_key(board_name: str, board: dict, pick: str, question: str,
               boards: dict | None = None) -> str:
    """Every league's build is in the key: an answer may come from any board."""
    stamp = ("|".join(f"{s}:{_ex.board_stamp(b)}" for s, b in sorted(boards.items()))
             if boards else _ex.board_stamp(board))
    return "\t".join((board_name, stamp, pick or "", cache_words(question)))


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
    """Add one question to today's line in the usage log. ``response`` may be
    a list — a question that looked something up is one call per round."""
    rounds = list(response) if isinstance(response, (list, tuple)) else [response] * (response is not None)
    got = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    for r in rounds:
        u = getattr(r, "usage", None)
        got["in"] += int(getattr(u, "input_tokens", 0) or 0)
        got["out"] += int(getattr(u, "output_tokens", 0) or 0)
        got["cache_read"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
        got["cache_write"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
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
            d["lookup_rounds"] = d.get("lookup_rounds", 0) + max(0, len(rounds) - 1)
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


def _call(client, model: str, req: dict, last: bool = False):
    """One round. The tools ride on every round, the last one told it may
    not use them — tool_choice leaves the tools-and-system cache alone."""
    kw = dict(model=model, max_tokens=MAX_TOKENS, system=req["system"], messages=req["messages"],
              tools=TOOLS)
    if last:
        kw["tool_choice"] = {"type": "none"}
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


def converse(client, model: str, req: dict, rounds: list) -> tuple:
    """Ask, run the lookups the model asks for, hand back what they found,
    and ask again — at most MAX_TOOL_ROUNDS times. ``rounds`` collects every
    response, so a question that fails half way still logs what it spent.
    Returns (last response, the lookups' source chips, lookups made)."""
    messages = list(req["messages"])
    sources: list[dict] = []
    made = 0
    for n in range(MAX_TOOL_ROUNDS + 1):
        response = _call(client, model, {**req, "messages": messages}, last=n == MAX_TOOL_ROUNDS)
        rounds.append(response)
        uses = [b for b in getattr(response, "content", None) or [] if getattr(b, "type", "") == "tool_use"]
        if getattr(response, "stop_reason", "") != "tool_use" or not uses or n == MAX_TOOL_ROUNDS:
            return response, sources, made
        results = []
        for b in uses:
            made += 1
            if made > MAX_TOOL_CALLS:
                out = {"error": "that is all the lookups one question gets; answer with what you have"}
            else:
                out = run_tool(getattr(b, "name", ""), getattr(b, "input", None), req["boards"], req["league"])
                src = tool_source(getattr(b, "name", ""), getattr(b, "input", None), out)
                if src and src not in sources:
                    sources.append(src)
            results.append({"type": "tool_result", "tool_use_id": getattr(b, "id", ""), "content": fit(out),
                            **({"is_error": True} if out.get("error") else {})})
        messages = messages + [{"role": "assistant", "content": list(response.content)},
                               {"role": "user", "content": results}]
    return response, sources, made


def ask(board: dict, question: str, history=None, pick: str = "", client=None,
        board_name: str = "", data_dir: Path | None = None, boards: dict | None = None) -> dict:
    """One answer: ``{"text", "model", "refused", "matched", "focused",
    "sources", "cached", "lookups"}``. ``board`` is the league the reader has
    open, ``boards`` every league's. Raises ValueError for an empty question,
    NotConfigured, Unavailable.
    """
    if not str(question or "").strip():
        raise ValueError("empty question")
    model = model_name()
    req = build_request(board, question, history, pick, data_dir, boards)
    base = {"model": model, "matched": req["matched"], "focused": req["focused"],
            "sources": req["sources"], "lookups": 0}
    fresh = not clean_history(history)
    key = answer_key(board_name, board, pick, question, req["boards"]) if fresh and board_name else ""
    if key:
        hit = cached_answer(key)
        if hit:
            log_usage(model, cached=True)
            return {**base, "text": hit["text"], "refused": bool(hit.get("refused")), "cached": True,
                    "sources": hit.get("sources") or base["sources"]}
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise _ex.NotConfigured("ANTHROPIC_API_KEY is not set")
        client = _client()
    try:
        import anthropic
        errors = (anthropic.APIStatusError, anthropic.APIConnectionError)
    except ImportError:
        errors = ()
    rounds: list = []
    try:
        response, looked, made = converse(client, model, req, rounds)
    except errors as exc:                               # typed, most specific first
        raise _ex.Unavailable(f"{type(exc).__name__}: {getattr(exc, 'message', exc)}") from exc
    except Exception as exc:                            # noqa: BLE001 — a client without the SDK's types
        raise _ex.Unavailable(f"{type(exc).__name__}: {exc}") from exc
    finally:
        if rounds:
            log_usage(model, rounds)
    base["sources"] = (looked + [s for s in base["sources"] if s not in looked])[:8]
    base["lookups"] = made
    if getattr(response, "stop_reason", "") == "refusal":
        return {**base, "text": "Ask declined to answer that one.", "refused": True, "cached": False}
    text = "".join(getattr(b, "text", "") for b in getattr(response, "content", None) or []
                   if getattr(b, "type", "") == "text").strip()
    if not text:
        raise _ex.Unavailable("the answer had no text")
    if key:
        remember_answer(key, {"text": text, "refused": False, "sources": base["sources"]})
    return {**base, "text": text, "refused": False, "cached": False}


def usage_report(days: int = 7) -> str:
    log = _read(USAGE_PATH).get("days") or {}
    lines = ["day         calls  cached  lookups  in_tok   out_tok  cache_rd  ~usd"]
    total = 0.0
    for day in sorted(log)[-days:]:
        d = log[day]
        total += d.get("usd") or 0
        lines.append(f"{day}  {d.get('calls', 0):5}  {d.get('cached', 0):6}  {d.get('lookup_rounds', 0):7}  "
                     f"{d.get('in', 0):7}  "
                     f"{d.get('out', 0):7}  {d.get('cache_read', 0):8}  {d.get('usd', 0):.4f}")
    lines.append(f"total ~${total:.4f} over {min(days, len(log))} day(s); model {model_name()}")
    return "\n".join(lines)


if __name__ == "__main__":                              # python3 -m engine.askbot usage
    import sys
    if sys.argv[1:2] == ["usage"]:
        print(usage_report(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
    else:
        print("usage: python3 -m engine.askbot usage [days]")
