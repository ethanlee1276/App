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
import math
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
WORDS = 150
MAX_TOKENS = 4000
MAX_MATCHED = 10
#: Rows matched only by a team code, at most (sent without their game logs).
MAX_WEAK = 5
#: Tonight's rows shown under an answer, as doors to their pick pages.
MAX_PICK_CHIPS = 3
#: Everything else under an answer: the lookups, pages and sections it read.
MAX_READ_CHIPS = 6
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
#: A search the API paused mid-turn is resumed at most this many times.
MAX_CONTINUATIONS = 2

#: WEB SEARCH. Ethan, 2026-09-23, asked whether Ask should reach past our
#: own data for the news and moves we don't store: "Yeah add it". It runs on
#: Anthropic's side at $10 per 1,000 searches on top of the tokens, so it is
#: capped per call and per day (QB_ASK_WEB_DAILY; 0 turns it off), and the
#: prompt keeps every number a bettor acts on coming from our data.
WEB_SEARCH_USD = 0.01
WEB_MAX_USES = 3
WEB_DAILY_CAP = 300
#: The standing rule is that we never scrape the books; their pages stay out
#: of the search too, so their prices cannot pass for ours.
WEB_BLOCKED = ("fanduel.com", "draftkings.com")
#: Models new enough for the search version that filters results in code
#: before they reach the context (Claude 4.6 and later); others get the basic one.
WEB_DYNAMIC_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7",
                      "claude-opus-4-6", "claude-sonnet-4-6")
WEB_SOURCES = 4
#: Set when the organisation has search switched off in the Claude Console:
#: Ask then answers without it until the service restarts.
_WEB = {"off": False}
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

#: Where the lookups read what is not a board. None is the site's own:
#: the gate's private copies for paid files (the server has checked the
#: reader's subscription before any lookup runs), engine.ledger's database.
PAID_DIR = None
LEDGER_DB = None
#: A lookup whose answer is stale within minutes is never served from the
#: answer cache.
#: Lookups whose answer is stale in minutes: an answer that used one is never remembered.
NO_CACHE_TOOLS = {"live_scores", "market_moves", "news", "our_picks_live", "prediction_markets", "web_search"}
SLATE_GAMES = 16
PICK_KINDS = ("best_bets", "most_likely", "long_shots", "game_lines", "parlays", "pick_of_the_day",
              "top_pick_today")
RECORD_WINDOWS = {"today": 0, "yesterday": 1, "last_7_days": 7, "last_30_days": 30, "season": None}
LIVE_LEAGUES = ("nfl", "cfb", "nba", "wnba", "mlb")

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
    "their games with lines, weather and rest; our record; the injury board; data_as_of, "
    "when each board was built); and your tools, which read everything the site "
    "publishes, refreshed all day: our history database (every stored final score with "
    "its spread and total, every stored player game log, play-by-play efficiency, injury "
    "designations), every league's board tonight (the slate with starters, weather and "
    "parks, our picks and parlays, our open bets live, each book's price and how lines "
    "have moved), the live market feed, the live scoreboard, the league's own standings, "
    "rosters and depth charts, headlines, Kalshi and Polymarket prices, the sportsbook "
    "report card, the fantasy desk, our futures simulation and our public record. When the "
    "question is about the past, such as a team's record, two teams' meetings, or how "
    "a player has done lately or against a team, look it up with the tools before you "
    "answer. For a question about the whole league (the best or worst at something, "
    "standings, a ranking, who leads a stat) use league_table or player_leaders; never "
    "ask the reader to name teams for it. The league is the one the question or the "
    "conversation is about, else the one the reader has open. Call several tools at "
    "once when you need several things, and pass the sport when you know it.\n"
    "Fantasy football questions are welcome: who to start, start/sit between players, "
    "flex calls, projected points, waiver pickups, streamers, trade value, which "
    "defences to target. Use fantasy_points for projections and start/sit (PPR unless "
    "the reader says half-PPR or standard), defense_vs_position for matchups against a "
    "position, and the fantasy desk for usage, waivers, streamers, trending and ranks. "
    "A team starting someone other than its usual quarterback (starting_qb_out, a "
    "row's qb_change) changes everything around it: whenever a question touches that "
    "team, its players or its game, say who is out and who starts, and what our model "
    "did with it. The same for a row's teammate_out: say who is out ahead of him and "
    "how much the projection moved.\n"
    "For a start/sit you may say who you would start: lead with that, then each "
    "player's projected points on its own line, and mention a big weekly swing "
    "(boom-or-bust) or a tough matchup when it decides it. That is fantasy advice, "
    "not a bet.\n"
    "Use ONLY the facts you are given, the tools return and web_search finds. Do not add "
    "statistics, injuries, news, odds or any number that is not in them. Look in our "
    "data first; when it has nothing on the question (breaking news, a trade or signing, "
    "an injury update, a coaching change, a result or a league we do not store, "
    "background), search the web with web_search. Numbers a bettor acts on (odds, lines, "
    "prices, picks, probabilities, our record) come only from our data, never from a web "
    "page: when a site's odds differ from ours, give ours. Say when a fact came from the "
    "web, and never pass off a site's pick or prediction as ours. If after looking nothing "
    "covers the question, say plainly that our data has nothing on it, say which "
    "seasons we do hold when that is why, and name the closest thing we have. You may "
    "explain how betting works in general terms (odds, spreads, totals, moneylines, "
    "parlays, the vig, closing line value, units); any payout, implied chance, parlay "
    "price or hold comes from odds_calc, never from your own arithmetic.\n"
    "hit_prob, model_prob and win_prob are our model's chance the bet wins; fair_prob "
    "and implied_prob are what the price implies; edge is the gap. A row with "
    "recommended false or no stake is not one of our bets: say so. Our record is real "
    "and includes losses; quote it straight.\n"
    f"Lead with the direct answer in one sentence, on its own line, then the one or two "
    f"facts behind it. At most {WORDS} words, plain words a first-time bettor understands. "
    "It is read on a phone, so lay it out: a list (a slate, picks, a ranking, facts side "
    "by side) goes one item per line, each line starting \"1.\" when the order means "
    "something and \"- \" when it does not, at most 8, with a blank line before and after "
    "it; keep each item short, like \"1. **Bills**: 38.5 points a game\"; bold (**...**) "
    "only the name or number that answers the question; a blank line between parts; no "
    "headings and no tables. "
    "Never tell the reader to bet or how much; a stake on a row is our model's, not "
    "advice. News comes from the news lookup first, then web_search for the story; "
    "scores for games in our leagues come only from live_scores; for anything live you "
    "say how old it is."
)


def _tool(name: str, what: str, props: dict, required=()) -> dict:
    need = [required] if isinstance(required, str) else list(required)
    return {"name": name, "description": what,
            "input_schema": {"type": "object", "properties": props, "required": need}}


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


#: What team_efficiency ranks by: {stat: (words, which way is better)}. None
#: is a style, not a grade: rank 1 is the most of it.
EFFICIENCY = {
    "off_epa": ("offense EPA per play", "high"),
    "def_epa": ("EPA per play allowed on defense", "low"),
    "pass_epa": ("EPA per pass play", "high"),
    "rush_epa": ("EPA per run play", "high"),
    "proe": ("pass rate over expected", None),
    "pace": ("seconds per snap in neutral situations", "low"),
    "plays_per_game": ("plays per game", None),
}

FANTASY_VIEWS = ("usage", "buy_sell", "waivers", "streamers", "trending", "ranks", "moves")
#: Fantasy scoring, points per unit. Interceptions, fumbles, two-point
#: tries and return yards are not projected, and every answer says so.
FANTASY_SCORING = {
    "ppr": {"receptions": 1.0, "rec_yds": 0.1, "rush_yds": 0.1, "pass_yds": 0.04, "pass_td": 4.0, "td": 6.0},
    "half": {"receptions": 0.5, "rec_yds": 0.1, "rush_yds": 0.1, "pass_yds": 0.04, "pass_td": 4.0, "td": 6.0},
    "standard": {"receptions": 0.0, "rec_yds": 0.1, "rush_yds": 0.1, "pass_yds": 0.04, "pass_td": 4.0, "td": 6.0},
}
FANTASY_POSITIONS = ("QB", "RB", "WR", "TE")
#: Most players one start/sit lookup compares.
FANTASY_PLAYERS_MAX = 6
#: The stat markets a projection is built from, and what each player
#: position scores in: a receiver's passing yards are zero, not unknown.
FANTASY_PARTS = {"QB": ("pass_yds", "pass_td", "rush_yds"),
                 "RB": ("rush_yds", "rec_yds", "receptions"),
                 "WR": ("rec_yds", "receptions", "rush_yds"),
                 "TE": ("rec_yds", "receptions")}
#: Fewest games a defence must have played before its rank is shown alone;
#: under it the table reads last season too, and says so.
FPA_MIN_GAMES = 3

def _stat_menu() -> str:
    """Every stat player_leaders can rank, by league — read from the logs'
    own market list, so a stat added there is offered here."""
    from engine import statlogs as SL
    return "; ".join(f"{s.upper()}: " + ", ".join(label for _, label in m)
                     for s, m in SL.SPORT_MARKETS.items())


#: Sorted by name and never changed per request: the tools are the front of
#: the cached prefix, and a byte of difference there re-bills all of it.
_ANY_SPORT = {"type": "string", "enum": list(LEAGUES) + ["ufc", "all"],
              "description": "The league, or all of them."}
TOOLS = [
    _tool("book_report",
          "Which sportsbooks price sharpest, measured from our own line snapshots: each book's early-price "
          "error against the closing line and how often it moves first. For which book is sharpest, which "
          "is softest, who moves first.",
          {}),
    _tool("defense_vs_position",
          "NFL defences against one position, from our stored game logs: the fantasy points (PPR) and "
          "the yards, catches and touchdowns each defence has given up per game to QBs, RBs, WRs or TEs "
          "this season, ranked (1 = gives up the most). For the best and worst matchups, which defences "
          "to target or avoid in fantasy, or how one defence does against a position.",
          {"position": {"type": "string", "enum": list(FANTASY_POSITIONS)},
           "team": {"type": "string", "description": "Optional: one defence."}}, "position"),
    _tool("fantasy",
          "The NFL fantasy desk: usage (target and carry shares, recent change), buy_sell (buy-low and "
          "sell-high by expected points), waivers (risers and who inherits an injured player's work), "
          "streamers (the week's best spots by position), trending (most added and dropped), ranks, and "
          "moves (recent signings and trades). For projected points and start/sit use fantasy_points; for "
          "matchups against a position use defense_vs_position.",
          {"view": {"type": "string", "enum": list(FANTASY_VIEWS)},
           "player": {"type": "string", "description": "Optional: one player."},
           "position": {"type": "string", "description": "Optional: QB, RB, WR, TE."}}, "view"),
    _tool("fantasy_points",
          "This week's projected fantasy points for up to six NFL players, side by side, highest first: "
          "our board's own projection for each stat (matchup, weather and injuries already in it), his "
          "expected touchdowns, his season average and week-to-week swing, his opponent and that "
          "defence's matchup line. For who to start, start/sit between players, flex calls, or how many "
          "points a player should score. Scoring is PPR unless the reader says half-PPR or standard.",
          {"players": {"type": "array", "items": {"type": "string"}, "description": "One to six players."},
           "scoring": {"type": "string", "enum": list(FANTASY_SCORING)}}, "players"),
    _tool("futures",
          "Our season simulation for one league: each team's record, projected wins and range, and its "
          "chances of the playoffs, the division, the conference and the title. With no team: the likeliest "
          "title winners and the projected season-stat leaders. For who is favored to win it all, playoff "
          "odds, win totals.",
          {"sport": _SPORT_ARG, "team": {"type": "string", "description": "Optional: one team."},
           "limit": {"type": "integer"}}, "sport"),
    _tool("injuries",
          "The injury board: one team's list, one player's status, or a league's. For is he playing, who is "
          "out, injury news we hold.",
          {"team": {"type": "string"}, "player": {"type": "string"}, "sport": _SPORT_ARG}),
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
    _tool("line_shop",
          "Every book's price on one of tonight's picks, the best price on our side at our line, and how "
          "the line has moved since it opened (steam, and whether the move is with our side or against it).",
          {"query": {"type": "string", "description": "The player or pick."}, "sport": _SPORT_ARG}, "query"),
    _tool("live_scores",
          "Our live scoreboard: games in progress with the score, period and clock (and the home side's win "
          "chance where we read one), then finals, then later games; sport ufc gives tonight's bouts, round "
          "and clock, and winners. Say how old it is.",
          {"sport": {**_SPORT_ARG, "enum": list(LEAGUES) + ["ufc"]},
           "team": {"type": "string", "description": "Optional: one team."}}),
    _tool("market_moves",
          "The live market feed from the last day, newest first: edges appearing and dying on our board, "
          "prop lines and prices moving, props getting priced when lineups drop, and stale lines at one "
          "book. For what just moved, any new edges, steam.",
          {"sport": _ANY_SPORT, "player": {"type": "string", "description": "Optional: one player."},
           "kind": {"type": "string", "enum": ["edge_appeared", "edge_died", "line_move", "price_move",
                                               "released", "stale_line"]}}),
    _tool("news",
          "The latest headlines we carry for a league, newest first: the title, publisher and time, never the "
          "article. For what is the news, any update on a team or player.",
          {"sport": {**_ANY_SPORT, "enum": list(LEAGUES) + ["ufc", "all"]},
           "query": {"type": "string", "description": "Optional: a team or player the headline names."}}),
    _tool("odds_calc",
          "Arithmetic on American odds, done exactly: each price's decimal odds, implied chance, profit and "
          "payout on a stake; with two or more, the parlay; with exactly two, the hold and the fair chances "
          "as two sides of one market. Use it for any payout, implied chance, parlay price or vig.",
          {"odds": {"type": "array", "items": {"type": "string"}, "description": "American odds, like -110 or +150."},
           "stake": {"type": "number", "description": "Optional: the stake (default 100)."}}, "odds"),
    _tool("our_picks",
          "Our model's picks tonight, by kind: best_bets (staked edges), most_likely (likeliest to hit), "
          "long_shots, game_lines (spreads, totals, moneylines), parlays (our tickets), pick_of_the_day (each "
          "league's) or top_pick_today (the one best pick across every league, with the ones it beat) — on "
          "one league's board or all of them, best first.",
          {"kind": {"type": "string", "enum": list(PICK_KINDS)}, "sport": _ANY_SPORT,
           "limit": {"type": "integer"}}, "kind"),
    _tool("our_picks_live",
          "Our open bets right now, in every league: each one's stat so far, whether it is still alive, its "
          "live chance to win against its pregame chance, and our parlays' live chances. For how are our "
          "picks doing, are we winning tonight.",
          {"sport": _ANY_SPORT}),
    _tool("our_record",
          "Our public record: all bets, a league's, the Most Likely board with its calibration, the best and "
          "worst markets; a window (today, yesterday, last_7_days, last_30_days, season); and with bets the "
          "settled bets themselves, newest first, filterable by result and by props or game lines.",
          {"sport": {**_SPORT_ARG, "enum": list(LEAGUES) + ["ufc"]},
           "window": {"type": "string", "enum": list(RECORD_WINDOWS)},
           "bets": {"type": "boolean"}, "result": {"type": "string", "enum": ["won", "lost", "push"]},
           "kind": {"type": "string", "enum": ["props", "lines"]}}),
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
    _tool("prediction_markets",
          "Prediction-market prices we carry: Kalshi (the exchange's chance, the sportsbooks' de-vigged "
          "chance for the same outcome, and our model's) and Polymarket. For what Kalshi or Polymarket says, "
          "exchange odds on a game or a title.",
          {"query": {"type": "string", "description": "Optional: a team, game or market."},
           "sport": _ANY_SPORT}),
    _tool("prop_hit_rate",
          "How often a player has gone over (or under) a line in one stat: last 5, last 10, this season, "
          "every stored game, and against one team, with his average. With no line, tonight's line on our "
          "board.",
          {"player": {"type": "string"}, "stat": {"type": "string"}, "line": {"type": "number"},
           "side": {"type": "string", "enum": ["over", "under"]},
           "opponent": {"type": "string", "description": "Optional: one team."}, "sport": _SPORT_ARG},
          ("player", "stat")),
    _tool("roster",
          "A team's current roster in depth-chart order, with each player's number, position, status and "
          "injury, and its recent signings and trades; or, with only a player, the team he is on. For who "
          "starts, the backup, the depth chart, who they signed.",
          {"team": {"type": "string"}, "player": {"type": "string"},
           "position": {"type": "string", "description": "Optional: one position, like QB or CB."},
           "sport": _SPORT_ARG}),
    _tool("schedule",
          "When a team plays next: its game on tonight's board with the lines, then the fixtures we hold, "
          "and its last result.",
          {"team": {"type": "string"}, "sport": _SPORT_ARG}, "team"),
    _tool("slate",
          "Tonight's games on one league's board or every league's: the matchup, kickoff, spread, total, "
          "moneylines and weather, and the score of any that has started. sport ufc gives the fight card.",
          {"sport": _ANY_SPORT}),
    _tool("standings",
          "The league's current standings from the league's own feed: every team's record by division or "
          "conference, win percentage, points for and against per game, home and away records, streak and "
          "last 10, the projected playoff seeds, and for one team its record in close games (clutch, "
          "reliability as favorite, comebacks as underdog, chokes). For standings, who leads the division, "
          "playoff picture.",
          {"sport": _SPORT_ARG, "team": {"type": "string", "description": "Optional: one team."},
           "group": {"type": "string", "description": "Optional: a division or conference, like NFC North."}}),
    _tool("team_efficiency",
          "Football efficiency from play-by-play (NFL, and college where stored): EPA per play on offense, "
          "allowed on defense, per pass and per run, pass rate over expected and pace, with ranks and the "
          "league average. With team: that team's profile. Without: the league ranked by one stat. last_n "
          "limits it to each team's latest weeks.",
          {"sport": {"type": "string", "enum": ["nfl", "cfb"]}, "team": {"type": "string"},
           "sort": {"type": "string", "enum": list(EFFICIENCY)}, "order": {"type": "string", "enum": ["best", "worst"]},
           "season": {"type": "integer"}, "last_n": {"type": "integer"}, "limit": {"type": "integer"}}),
    _tool("team_history",
          "A team's final scores from our history database, in any league we cover, whether "
          "or not it plays tonight. With opponent: every stored meeting of the two, newest "
          "first, each with the score, the spread and total, and who covered, and the "
          "head-to-head totals. Without opponent: its record season by season with its "
          "offense and defense rank, and its latest results. Names can be nicknames, cities "
          "or abbreviations.",
          {"team": {"type": "string", "description": "The team, as the reader wrote it."},
           "opponent": _OPP_ARG, "sport": _SPORT_ARG}, "team"),
    _tool("team_trends",
          "A team's betting splits from our stored finals: straight up, against the spread and over/under — "
          "overall, home, away, as favorite and as underdog — this season, its last 10, and every stored game.",
          {"team": {"type": "string"}, "sport": _SPORT_ARG,
           "season": {"type": "integer", "description": "Optional: a season year."}}, "team"),
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
    qb = row.get("qb_card")
    if isinstance(qb, dict) and qb.get("headline"):
        out["qb_change"] = qb_line(qb)
    mate = row.get("mate_card")
    if isinstance(mate, dict) and mate.get("headline"):
        out["teammate_out"] = ". ".join(x for x in (mate.get("headline"), mate.get("note")) if x)
    return out


def qb_line(card: dict) -> str:
    """A starting quarterback out (engine/qbchange.card) as one sentence."""
    return ". ".join(x for x in (card.get("headline"), card.get("detail"), card.get("note")) if x)


def _qb_changes(board: dict, teams=None) -> list[str]:
    return [qb_line(c) for c in (board or {}).get("qb_changes") or []
            if isinstance(c, dict) and c.get("headline") and (teams is None or c.get("team") in teams)]


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


def asked_in_full(boards, question: str) -> set[str]:
    """The players a question names in full, on any of these boards."""
    q = _norm(question)
    out = set()
    for b in boards:
        for _lst, r in _rows(b):
            full = _norm(r.get("player")).strip()
            if len(full.split()) >= 2 and f" {full} " in q:
                out.add(full)
    return out


def _namesake(r: dict, matched: list[str], asked: set[str]) -> bool:
    """Reached only through a surname it shares with a player the question
    names in full: "Josh Allen" is not a question about Nick or Keenan Allen
    (Ethan, 2026-09-23, a Josh Allen answer carrying both as chips)."""
    full = _norm(r.get("player")).strip()
    if not full or full in asked or len(full.split()) < 2:
        return False
    last = full.split()[-1]
    return matched == [last] and any(a.split()[-1] == last for a in asked)


def _hits(board: dict, question: str, asked: set[str] | None = None) -> list[tuple]:
    q = _norm(question)
    caps = _caps(question)
    asked = asked_in_full([board], question) if asked is None else asked
    hits = []
    for lst, r in _rows(board):
        matched = [n for n in _names(r) if f" {n} " in q]
        if _namesake(r, matched, asked):
            continue
        best = max([len(n) for n in matched] or [0])
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


def chip_label(r: dict) -> str:
    """A row as a reader says it: "Josh Allen · Over 149.5 Passing Yards",
    "Josh Allen · Anytime TD" — not "Josh Allen yes Anytime TD"."""
    if r.get("pick_label"):
        return str(r["pick_label"]).strip()
    side = str(r.get("side") or "").strip()
    what = str(r.get("market_label") or r.get("market") or "").strip()
    line = r.get("line")
    if side.upper() in ("OVER", "UNDER"):
        bet = f"{side.title()} {_n(line) if line is not None else ''} {what}"
    elif side.upper() in ("YES", "NO"):
        bet = what if side.upper() == "YES" else f"No {what}"
    else:
        bet = " ".join(str(x) for x in (side, line, what) if x not in (None, ""))
    bet = " ".join(bet.split())
    return f"{r['player']} · {bet}" if r.get("player") and bet else str(r.get("player") or bet)


def shown_sources(sources: list[dict], answer: str, about: dict) -> list[dict]:
    """What goes under an answer: first what it read (lookups, web pages,
    games, sections), then at most MAX_PICK_CHIPS of tonight's rows — only
    ones the question named outright, for a player the answer talks about,
    or the pick the conversation was opened from. Every other row the
    question's words touched was a fact for the model, not a thing to show."""
    a = " " + re.sub(r"'s?(?= )", "", _norm(answer)) + " "          # "Kelce's" names Kelce
    read = [s for s in sources if s.get("kind") != "pick"][:MAX_READ_CHIPS]
    picks = []
    # A surname names a player only when no other chip's player shares it.
    for s in sources:
        if s.get("kind") != "pick":
            continue
        who, strong = about.get(s["label"], ("", False))
        if who is None:                                  # the pick this was asked from
            keep = True
        elif not strong:
            keep = False
        elif not who:                                    # a game line the question named
            keep = True
        else:
            last = who.split()[-1]
            keep = f" {who} " in a or (len(last) >= 4 and f" {last} " in a
                                       and len({w for w, _st in about.values() if w and w.split()[-1] == last}) == 1)
        if keep:
            picks.append(s)
    return read + picks[:MAX_PICK_CHIPS]


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
        out["weather"] = {k: w[k] for k in ("dome", "temp_f", "wind_mph", "wind_dir", "precip_chance", "rain", "snow")
                          if w.get(k) not in (None, "")}
    pitchers = g.get("pitchers") or {}
    if isinstance(pitchers, dict) and pitchers:
        out["probable_starters"] = {str(g.get(side) or side): _slim(p, ("name", "throws", "xera", "k_rate"))
                                    for side, p in pitchers.items() if isinstance(p, dict) and p.get("name")}
    if g.get("lineups_confirmed") is not None:
        out["lineups_confirmed"] = bool(g["lineups_confirmed"])
    if g.get("park_name"):
        out["park"] = g["park_name"]
    f = g.get("factors")
    if isinstance(f, dict) and f:
        out["park_factors"] = _slim(f, ("hr", "run", "k"))
    if g.get("plate_umpire"):
        out["plate_umpire"] = g["plate_umpire"]
        if g.get("ump_k_factor") is not None:
            out["umpire_strikeout_factor"] = g["ump_k_factor"]
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
    qbs = _qb_changes(board, {g.get("home"), g.get("away")})
    if qbs:
        out["starting_qb_out"] = qbs
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
    qbs = _qb_changes(b)
    if qbs:
        out["starting_qb_out"] = qbs
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
    asked = asked_in_full([boards[s] for s in order], question)
    hits = []
    for i, s in enumerate(order):
        hits += [(h[0], i, h[1], h[2], s) for h in _hits(boards[s], question, asked)]
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


# ---- the bettor's lookups ------------------------------------------------------------
# Ethan, 2026-09-23: "Think of other questions a user would want to ask about
# sports and shit and add it. It's a sport betting ai so it should be able to
# answer." What a bettor asks, and where our data already holds the answer:
#
#   what is on tonight, and at what line  -> slate           (every board, live state)
#   what do you like / best bets / parlay -> our_picks       (every board's own lists)
#   best price on it, has the line moved  -> line_shop       (each pick's books, line_move)
#   how often does he go over this line   -> prop_hit_rate   (player_game_logs)
#   how do they do ATS at home / as dogs  -> team_trends     (finals with their lines)
#   is he playing, who is out             -> injuries        (web/data/injuries.json)
#   when do they play next                -> schedule        (boards + stored fixtures)
#   what is the score                     -> live_scores     (web/data/live_*.json)
#   who wins the title, playoff odds      -> futures         (futures_*.json, paid)
#   how did you do yesterday / this week  -> our_record      (record.json + the ledger)
#   what does +150 pay, parlay odds, vig  -> odds_calc       (arithmetic, never guessed)



def _paid(name: str, data_dir) -> dict:
    """A paid file's private copy (the full board), else the public one."""
    if PAID_DIR:
        return _load_json(Path(PAID_DIR) / name)
    try:
        from engine import gate
        got = gate.full_board(name)
        if isinstance(got, dict) and got:
            return got
    except Exception:                                         # noqa: BLE001
        pass
    return _load_json(Path(data_dir or ROOT / "web" / "data") / name)


def _codes_for(name: str, sport: str) -> set[str]:
    """Every code a typed team could mean in one league, and itself."""
    from engine import teamdex as T
    if not name:
        return set()
    out = set(T.resolve(name, sport)[:2])
    for part in _split(name):
        out |= set(T.resolve(part, sport)[:1])
    raw = name.strip()
    if 2 <= len(raw) <= 4 and raw.upper() == raw:
        out.add(raw)
    return out


def _board_leagues(boards: dict, sport: str, prefer: str) -> list[str]:
    if sport and sport != "all":
        return [sport] if sport in boards else []
    return _order(boards, prefer)


# -- live scores -------------------------------------------------------------------
def _live_games(sport: str, data_dir) -> tuple[list[dict], str]:
    got = _load_json(Path(data_dir or ROOT / "web" / "data") / f"live_{sport}.json")
    rows = []
    for g in got.get("games") or []:
        lv = g.get("live") if isinstance(g, dict) else None
        if not isinstance(lv, dict):
            continue
        home, away = str(g.get("home") or ""), str(g.get("away") or "")
        row = {"game": f"{away} @ {home}", "state": lv.get("state") or ""}
        if lv.get("home_score") is not None and lv.get("away_score") is not None:
            row["score"] = f"{away} {_n(lv['away_score'])}, {home} {_n(lv['home_score'])}"
        for k in ("period", "clock", "detail", "outs", "start_time"):
            if lv.get(k) not in (None, ""):
                row[k] = lv[k]
        wp = lv.get("win_prob")
        if isinstance(wp, dict) and wp.get("home") is not None:
            row["home_win_prob"] = wp.get("home")
        row["_names"] = " ".join(str(g.get(k) or "") for k in ("home", "away", "home_name", "away_name"))
        row["_key"] = (away, home)
        rows.append(row)
    return rows, str(got.get("generated_at") or "")


def live_scores(sport: str = "", team: str = "", data_dir=None, prefer: str = "") -> dict:
    """The scoreboard now: live games first, then finals, then later games."""
    leagues = [sport] if sport in LIVE_LEAGUES else [s for s in [prefer, *LIVE_LEAGUES] if s in LIVE_LEAGUES]
    out = []
    for s in dict.fromkeys(leagues):
        games, stamp = _live_games(s, data_dir)
        if team:
            codes = _codes_for(team, s)
            games = [g for g in games if set(g["_key"]) & codes or _norm(team).strip() in _norm(g["_names"])]
        if not games:
            continue
        order = {"live": 0, "in": 0, "post": 1, "final": 1}
        games.sort(key=lambda g: order.get(g["state"], 2))
        out.append({"sport": s, "as_of": stamp,
                    "games": [{k: v for k, v in g.items() if not k.startswith("_")} for g in games[:SLATE_GAMES]]})
        if team:
            break
    if not out:
        return {"found": False, "note": "our live scoreboard has no game for that right now"
                + (f" ({team})" if team else "")}
    return {"scoreboards": out}


# -- tonight ------------------------------------------------------------------------
def slate(boards: dict, sport: str = "", data_dir=None, prefer: str = "") -> dict:
    """Tonight's games with their lines and conditions, and the score where one has started."""
    if sport == "ufc":
        card = _paid("ufc.json", data_dir)
        fights = [r.get("fight") for r in (card.get("picks") or []) + (card.get("pass_list") or [])
                  if isinstance(r, dict) and r.get("fight")]
        if not fights:
            return {"found": False, "note": "no UFC card on our board"}
        return {"sport": "ufc", "event": card.get("event_date") or card.get("event") or "", "fights": fights}
    leagues = _board_leagues(boards, sport, prefer)
    out = []
    for s in leagues:
        b = boards[s]
        live = {g["_key"]: g for g in _live_games(s, data_dir)[0]}
        games = []
        for g in [g for g in b.get("games") or [] if isinstance(g, dict)][:SLATE_GAMES]:
            row = game_facts(b, g)
            for k in ("stadium_note", "rest", "park_factors", "umpire_strikeout_factor"):
                row.pop(k, None)
            now = live.get((str(g.get("away") or ""), str(g.get("home") or "")))
            if now and now.get("state") not in ("pre", ""):
                row["now"] = {k: now[k] for k in ("state", "score", "period", "clock", "detail") if k in now}
            games.append(row)
        if games:
            out.append({"sport": s, "date": b.get("date") or "", "games": games})
    if not out:
        return {"found": False, "note": "no games on tonight's boards" + (f" for {sport.upper()}" if sport else ""),
                "leagues_with_a_board_tonight": sorted(boards)}
    return {"slates": out}


def _ticket(t: dict, league: str, pool: str) -> dict:
    legs = []
    for l in t.get("legs") or []:
        legs.append(" ".join(str(x) for x in (l.get("player") or l.get("team"), l.get("side"), l.get("line"),
                                               l.get("market_label") or l.get("market"),
                                               f"({l['odds']:+d})" if isinstance(l.get("odds"), int) else "")
                             if x not in (None, "")))
    out = {"league": league, "pool": pool, "grade": t.get("grade"), "legs": legs}
    for k, name in (("likely_case_american", "price"), ("modeled_joint", "model_chance")):
        if t.get(k) is not None:
            out[name] = t[k]
    return out


def our_picks(boards: dict, kind: str = "best_bets", sport: str = "", limit=None, data_dir=None,
              prefer: str = "") -> dict:
    """What our model has tonight, by kind, on one league's board or all of them."""
    if kind not in PICK_KINDS:
        return {"error": "kind is one of: " + ", ".join(PICK_KINDS)}
    if sport == "ufc":
        card = _paid("ufc.json", data_dir)
        keep = ("fight", "division", "pick", "side", "odds", "book", "model_prob", "win_prob", "fair_prob",
                "edge", "grade", "stake_units")
        rows = [{k: r[k] for k in keep if r.get(k) not in (None, "")} for r in card.get("picks") or []
                if isinstance(r, dict)]
        return {"sport": "ufc", "kind": "picks", "rows": rows[:_limit(limit)]} if rows else \
            {"found": False, "note": "no UFC picks on our board"}
    if kind == "top_pick_today":
        top = _paid("day_top_pick.json", data_dir)
        p = top.get("pick")
        if not isinstance(p, dict) or not p:
            return {"found": False, "note": top.get("note") or "no top pick across the leagues today"}
        out = {"kind": kind, "league": top.get("sport") or p.get("sport"), "pick": compact(p),
               "as_of": top.get("generated_at"), "leagues_compared": top.get("leagues_seen")}
        for k in ("verdict", "note"):
            if isinstance(top.get(k), str) and top[k]:
                out[k] = top[k]
        beat = [{"league": r.get("sport"), **compact(r)} for r in top.get("runners_up") or [] if isinstance(r, dict)]
        if beat:
            out["runners_up"] = beat
        return out
    rows = []
    for s in _board_leagues(boards, sport, prefer):
        b = boards[s]
        if kind == "parlays":
            for key, pool in (("parlays", "edge"), ("likely_parlays", "likely")):
                block = b.get(key) or {}
                for t in (block.get("tickets") if isinstance(block, dict) else None) or []:
                    if isinstance(t, dict):
                        rows.append((0, _ticket(t, s, pool)))
            continue
        if kind == "pick_of_the_day":
            p = b.get("pick_of_the_day")
            if isinstance(p, dict) and p:
                rows.append((0, {"league": s, **compact(p)}))
            continue
        src = {"best_bets": [r for r in b.get("recommendations") or [] if isinstance(r, dict) and r.get("recommended")],
               "most_likely": [r for r in b.get("most_likely") or [] if isinstance(r, dict)],
               "long_shots": [r for r in b.get("long_shots") or [] if isinstance(r, dict)],
               "game_lines": [r for r in b.get("game_bets") or [] if isinstance(r, dict)]}[kind]
        for r in src:
            key = {"best_bets": r.get("edge"), "most_likely": r.get("model_prob") or r.get("hit_prob"),
                   "long_shots": r.get("edge"), "game_lines": r.get("win_prob") or r.get("edge")}[kind]
            rows.append((-(float(key) if isinstance(key, (int, float)) else 0), {"league": s, **compact(r)}))
    rows.sort(key=lambda x: x[0])
    if not rows:
        return {"found": False, "note": f"no {kind.replace('_', ' ')} on tonight's boards"
                + (f" for {sport.upper()}" if sport and sport != "all" else "")}
    return {"kind": kind, "count": len(rows), "rows": [r for _, r in rows[:_limit(limit)]]}


def line_shop(boards: dict, query: str, sport: str = "", prefer: str = "") -> dict:
    """Every book's price on a pick tonight, the best one on our side, and how the line has moved."""
    if not query:
        return {"error": "name the player or the pick"}
    out = []
    for s in _board_leagues(boards, sport, prefer):
        for _score, _lst, r in _hits(boards[s], query):
            books = [x for x in r.get("all_lines") or [] if isinstance(x, dict)]
            if not books and not r.get("line_move"):
                continue
            side = str(r.get("side") or "").upper()
            key = "over_odds" if side == "OVER" else "under_odds" if side == "UNDER" else ""
            row = {"league": s, "pick": " ".join(str(x) for x in (r.get("player"), r.get("side"), r.get("line"),
                                                                    r.get("market_label") or r.get("market"))
                                                   if x not in (None, "")),
                   "our_price": r.get("odds"), "our_book": r.get("book"),
                   "books": [{k: x[k] for k in ("book", "line", "over_odds", "under_odds") if x.get(k) is not None}
                             for x in books[:12]]}
            same = [x for x in books if key and x.get(key) is not None and x.get("line") == r.get("line")]
            if same:
                best = max(same, key=lambda x: x[key])
                row["best_price_at_this_line"] = {"book": best.get("book"), "odds": best[key]}
            tape = _line_tape(r.get("line_series"))
            if len(tape) > 1:
                row["line_since_open"] = tape
            mv = r.get("line_move")
            if isinstance(mv, dict):
                row["line_move"] = {k: mv[k] for k in ("open", "current", "delta", "open_odds", "current_odds",
                                                        "direction", "steam", "verdict", "moved_ago_min")
                                    if mv.get(k) is not None}
            out.append(row)
            if len(out) >= 4:
                break
    if not out:
        return {"found": False, "note": f"no priced pick on tonight's boards for {query}"}
    return {"picks": out}


# -- history, for bettors -----------------------------------------------------------------
def _tally(vals: list[float], line: float, side: str) -> dict:
    over = sum(1 for v in vals if v > line)
    under = sum(1 for v in vals if v < line)
    push = len(vals) - over - under
    hit = over if side == "over" else under
    decided = len(vals) - push
    out = {"games": len(vals), "over": over, "under": under}
    if push:
        out["push"] = push
    if decided:
        out[f"{side}_hit_rate"] = round(hit / decided, 3)
    if vals:
        out["average"] = _n(round(sum(vals) / len(vals), 1))
    return out


def prop_hit_rate(boards: dict, player: str, stat: str, line=None, side: str = "over", opponent: str = "",
                  sport: str = "", prefer: str = "") -> dict:
    """How often a player has cleared a line: last 5, last 10, this season, every stored game, and against one team."""
    from engine import statlogs as SL
    from engine import teamdex as T
    side = "under" if str(side or "").lower().startswith("u") else "over"
    if not player:
        return {"error": "no player named"}
    hits = [h for h in _find_players(player, sport, prefer) if h.get("sport") in SL.SPORT_MARKETS]
    if not hits:
        return {"found": False, "note": f"no stored games for a player called {player}"}
    s, name = hits[0]["sport"], hits[0]["player"]
    m = _market(stat, SL.SPORT_MARKETS[s])
    if not m:
        return {"error": f"the {s.upper()} stats we hold are: " + ", ".join(l for _, l in SL.SPORT_MARKETS[s])}
    mid, label = m
    tonight = None
    for r in (boards.get(s) or {}).get("recommendations") or []:
        if isinstance(r, dict) and r.get("player") == name and r.get("market") == mid and r.get("line") is not None:
            tonight = r
            break
    try:
        ln = float(line) if line not in (None, "") else float(tonight["line"]) if tonight else None
    except (TypeError, ValueError):
        ln = None
    if ln is None:
        return {"error": f"give a line for {name}'s {label} (none on tonight's board)"}
    conn = _history()
    if conn is None:
        return {"error": "our history database is not available"}
    try:
        rows = conn.execute("SELECT season, opponent, value FROM player_game_logs WHERE sport=? AND player=? "
                            "AND market=? ORDER BY season DESC, period DESC", (s, name, mid)).fetchall()
    finally:
        conn.close()
    if not rows:
        return {"found": False, "note": f"no stored {label} games for {name}"}
    vals = [float(r["value"]) for r in rows]
    season = rows[0]["season"]
    out = {"player": name, "sport": s, "stat": label, "line": _n(ln), "side": side,
           "last_5": _tally(vals[:5], ln, side), "last_10": _tally(vals[:10], ln, side),
           f"season_{season}": _tally([float(r["value"]) for r in rows if r["season"] == season], ln, side),
           "every_stored_game": _tally(vals, ln, side)}
    if tonight is not None:
        out["tonight"] = compact(tonight)
    if opponent:
        codes = _codes_for(opponent, s) | {opponent}
        vs = [float(r["value"]) for r in rows if r["opponent"] in codes
              or _norm(opponent).strip() in _norm(T.label(r["opponent"], s))]
        out["against"] = {"opponent": opponent, **_tally(vs, ln, side)}
    return out


def _split_line(rows: list[dict]) -> dict:
    if not rows:
        return {"games": 0}
    w = sum(r["result"] == "W" for r in rows)
    l = sum(r["result"] == "L" for r in rows)
    t = len(rows) - w - l
    cw = sum(r.get("covered") is True for r in rows)
    cl = sum(r.get("covered") is False for r in rows)
    cp = sum(r.get("covered") == "push" for r in rows)
    ov = sum(r.get("ou") == "over" for r in rows)
    un = sum(r.get("ou") == "under" for r in rows)
    op = sum(r.get("ou") == "push" for r in rows)
    out = {"games": len(rows), "record": f"{w}-{l}" + (f"-{t}" if t else "")}
    if cw + cl + cp:
        out["ats"] = f"{cw}-{cl}" + (f"-{cp}" if cp else "")
    if ov + un + op:
        out["over_under"] = f"{ov} over, {un} under" + (f", {op} push" if op else "")
    return out


def _splits(rows: list[dict]) -> dict:
    return {"overall": _split_line(rows),
            "home": _split_line([r for r in rows if r["at_home"]]),
            "away": _split_line([r for r in rows if not r["at_home"]]),
            "as_favorite": _split_line([r for r in rows if (r.get("line") or 0) < 0]),
            "as_underdog": _split_line([r for r in rows if (r.get("line") or 0) > 0])}


def team_trends(team: str, sport: str = "", season=None, prefer: str = "") -> dict:
    """A team's betting splits: straight up, against the spread and over/under — home, away, as favorite, as underdog."""
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
            rows = T.results(conn, s, mine[0])
            seasons = sorted({r["season"] for r in rows}, reverse=True)
            year = _season_of(seasons, season)
            return {"sport": s, "team": T.label(mine[0], s), "season": year,
                    "this_season": _splits([r for r in rows if r["season"] == year]),
                    "last_10": _split_line(rows[:10]),
                    "every_stored_game": _splits(rows),
                    "seasons_we_hold": f"{min(seasons)}-{max(seasons)}" if len(seasons) > 1 else str(seasons[0])}
    finally:
        conn.close()
    return {"found": False, "note": f"no stored games for {team}"}


def injuries(team: str = "", player: str = "", sport: str = "", data_dir=None, prefer: str = "") -> dict:
    """The injury board: one team's list, one player's status, or a league's."""
    data = _load_json(Path(data_dir or ROOT / "web" / "data") / "injuries.json")
    by = data.get("sports") or {}
    leagues = [sport] if sport else [s for s in [prefer, *LEAGUES, *sorted(by)] if s in by]
    out = []
    for s in dict.fromkeys(leagues):
        codes = _codes_for(team, s) if team else set()
        for r in by.get(s) or []:
            if not isinstance(r, dict):
                continue
            if team and not (str(r.get("team") or "") in codes or _norm(team).strip() in _norm(r.get("team"))):
                continue
            if player and _norm(player).strip() not in _norm(r.get("player")):
                continue
            out.append({"league": s, **{k: r[k] for k in ("player", "team", "position", "status", "injury", "detail")
                                        if r.get(k) not in (None, "")}})
        if out and (team or player or not sport):
            break
    past = injury_history(player, sport) if player else []
    if not out and not past:
        return {"found": False, "note": "nothing on the injury board for that"
                + (f" ({team or player})" if team or player else ""), "as_of": data.get("generated_at")}
    res = {"as_of": data.get("generated_at"), "count": len(out), "rows": out[:30]}
    if not out:
        res["note"] = "not on the injury board now"
    if past:
        res["designations_we_have_seen"] = past
    return res


def schedule(boards: dict, team: str, sport: str = "", prefer: str = "") -> dict:
    """When a team plays next: tonight's board first, then the fixtures we hold."""
    from engine import teamdex as T
    if not team:
        return {"error": "no team named"}
    conn = _history()
    try:
        for s in _leagues(sport, prefer):
            codes = _codes_for(team, s)
            if not codes:
                continue
            b = boards.get(s) or {}
            upcoming = []
            for g in b.get("games") or []:
                if isinstance(g, dict) and {str(g.get("home") or ""), str(g.get("away") or "")} & codes:
                    upcoming.append({"on_tonights_board": True, **game_facts(b, g)})
            if conn is not None:
                marks = ",".join("?" * len(codes))
                for r in conn.execute(
                        f"SELECT season, period, date, home, away, spread, total FROM games WHERE sport=? "
                        f"AND (home IN ({marks}) OR away IN ({marks})) AND (home_score IS NULL OR away_score IS NULL) "
                        f"ORDER BY date, period LIMIT 5", (s, *codes, *codes)).fetchall():
                    g = {"game": f"{r['away']} @ {r['home']}", "when": _when(r["season"], r["period"], r["date"], s)}
                    if r["spread"] is not None:
                        g["home_spread"] = _n(r["spread"])
                    if r["total"] is not None:
                        g["total"] = _n(r["total"])
                    if all(g["game"] != u.get("game") for u in upcoming):
                        upcoming.append(g)
            last = T.results(conn, s, sorted(codes)[0], 1) if conn is not None else []
            if upcoming or last:
                out = {"sport": s, "team": T.label(sorted(codes)[0], s), "upcoming": upcoming[:6]}
                if last:
                    out["last_game"] = _final(last[0], s, lambda c: T.label(c, s))
                return out
    finally:
        if conn is not None:
            conn.close()
    return {"found": False, "note": f"no upcoming games we hold for {team}"}


def futures(sport: str = "", team: str = "", limit=None, data_dir=None, prefer: str = "") -> dict:
    """Our season simulation: each team's projected wins and its chances of the playoffs, the division, the title."""
    from engine import teamdex as T
    s = _league(sport, prefer)
    f = _paid(f"futures_{s}.json", data_dir)
    teams = [t for t in f.get("teams") or [] if isinstance(t, dict)]
    if not teams:
        return {"found": False, "note": f"no {s.upper()} futures on our board"}
    if team:
        codes = _codes_for(team, s)
        teams = [t for t in teams if t.get("team") in codes or _norm(team).strip() in _norm(T.label(t.get("team"), s))]
    rows = []
    for t in teams[:_limit(limit)]:
        row = {"team": T.label(t.get("team"), s), "record": f"{t.get('wins', 0)}-{t.get('losses', 0)}"}
        if t.get("proj_wins") is not None:
            row["projected_wins"] = round(float(t["proj_wins"]), 1)
            if t.get("proj_wins_lo") is not None and t.get("proj_wins_hi") is not None:
                row["projected_range"] = f"{_n(round(float(t['proj_wins_lo']), 1))}-{_n(round(float(t['proj_wins_hi']), 1))}"
        for k, name in (("p_playoffs", "playoffs"), ("p_division", "division"), ("p_conference", "conference"),
                        ("p_title", "title")):
            if t.get(k) is not None:
                row[f"{name}_chance"] = round(float(t[k]), 3)
        rows.append(row)
    out = {"sport": s, "season": f.get("season"), "rows": rows}
    if f.get("prior_weight") is not None:
        out["share_resting_on_preseason_ratings"] = f["prior_weight"]
    if not team:
        totals = []
        for mk in (f.get("season_totals") or [])[:4]:
            ps = [{k: (round(p[k], 1) if isinstance(p.get(k), float) else p[k])
                   for k in ("player", "team", "banked", "mean", "games_left") if p.get(k) is not None}
                  for p in (mk.get("players") or [])[:3] if isinstance(p, dict)]
            if ps:
                totals.append({"stat": mk.get("label") or mk.get("market"), "projected_leaders": ps})
        if totals:
            out["season_totals"] = totals
    return out


def our_record(sport: str = "", window: str = "", bets: bool = False, result: str = "", kind: str = "",
               data_dir=None) -> dict:
    """Our public record: the headline, a window of days, the markets, and the settled bets themselves."""
    rec = _load_json(Path(data_dir or ROOT / "web" / "data") / "record.json")
    if not rec:
        return {"error": "our record file is not available"}
    s = sport if sport in LEAGUES or sport == "ufc" else ""
    out = record_facts(rec, s)
    if window in RECORD_WINDOWS:
        src = ((rec.get("by_sport") or {}).get(s) or {}) if s else (rec.get("pooled") or rec)
        curve = [p for p in src.get("curve") or [] if isinstance(p, dict)]
        days = RECORD_WINDOWS[window]
        today = _dt.date.today()
        if days is None:
            pts = curve
        elif days == 1:
            pts = [p for p in curve if str(p.get("date")) == (today - _dt.timedelta(days=1)).isoformat()]
        elif days == 0:
            pts = [p for p in curve if str(p.get("date")) == today.isoformat()]
        else:
            pts = [p for p in curve if str(p.get("date") or "") >= (today - _dt.timedelta(days=days)).isoformat()]
        out[window] = ({"wins": sum(p.get("w") or 0 for p in pts), "losses": sum(p.get("l") or 0 for p in pts),
                        "net_units": round(sum(float(p.get("day_u") or 0) for p in pts), 2),
                        "days_with_bets": len(pts)} if pts else "no settled bets in that window")
    if bets or result or kind:
        try:
            from engine import ledger as L
            path = Path(LEDGER_DB or L.DEFAULT_DB)
            if path.exists():
                conn = L.connect(str(path))
                try:
                    since = None
                    if window in RECORD_WINDOWS and RECORD_WINDOWS[window]:
                        since = (_dt.date.today() - _dt.timedelta(days=RECORD_WINDOWS[window])).isoformat()
                    page = L.settled_page(conn, s or None, kind if kind in ("props", "lines") else None,
                                          result if result in ("won", "lost", "push") else None, since)
                finally:
                    conn.close()
                out["settled_bets"] = [{k: r[k] for k in ("day", "sport", "player", "market", "side", "line", "odds",
                                                          "status", "pnl_units", "closing_odds", "clv")
                                        if r.get(k) is not None} for r in page["rows"][:12]]
                out["settled_bets_matching"] = page["total"]
        except Exception as exc:                              # noqa: BLE001
            out["settled_bets_note"] = f"the bet list could not be read ({type(exc).__name__})"
    return out


def _american_to_decimal(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / abs(a))


def _decimal_to_american(d: float) -> int:
    return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))


def odds_calc(odds, stake=100) -> dict:
    """Payouts, implied chances and parlays from American odds — the arithmetic, done here, not guessed."""
    vals = []
    for o in (odds if isinstance(odds, list) else [odds])[:12]:
        try:
            a = float(str(o).replace("+", "").strip())
        except ValueError:
            return {"error": f"{o} is not American odds, like -110 or +150"}
        if abs(a) < 100:
            return {"error": f"{o} is not American odds: they are at least 100 either way"}
        vals.append(a)
    if not vals:
        return {"error": "give one or more American odds"}
    try:
        st = float(stake) if stake not in (None, "") else 100.0
    except (TypeError, ValueError):
        st = 100.0
    each = []
    for a in vals:
        d = _american_to_decimal(a)
        each.append({"odds": f"{a:+.0f}", "decimal": round(d, 3), "implied_chance": round(1 / d, 4),
                     "profit": round(st * (d - 1), 2), "payout": round(st * d, 2)})
    out = {"stake": _n(st), "each": each}
    if len(vals) > 1:
        dec = 1.0
        for a in vals:
            dec *= _american_to_decimal(a)
        out["parlay"] = {"legs": len(vals), "decimal": round(dec, 3), "odds": f"{_decimal_to_american(dec):+d}",
                         "implied_chance": round(1 / dec, 4), "profit": round(st * (dec - 1), 2),
                         "payout": round(st * dec, 2)}
    if len(vals) == 2:
        p1, p2 = 1 / _american_to_decimal(vals[0]), 1 / _american_to_decimal(vals[1])
        # Only a pair that COULD be one market's two sides: the chances must
        # add up to at least 1 (a book's margin), and not absurdly more.
        if 1 <= p1 + p2 < 1.3:
            out["as_two_sides_of_one_market"] = {"hold": round(p1 + p2 - 1, 4),
                                                 "fair_chances": [round(p1 / (p1 + p2), 4), round(p2 / (p1 + p2), 4)]}
    return out


# -- everything else the site publishes ---------------------------------------------
# Ethan, 2026-09-23: "make sure the AI chat is pulling live data and all
# that shit that we usually access and have keys for." Every feed below is
# one the refresher already pulls with the site's own keys and writes to
# disk; a question reads the newest write, and nothing here fetches.
#
#   standings, division, clutch record  -> standings          (standings_*.json, the league's own table)
#   who is on the team, depth, moves     -> roster             (rosters_*.json)
#   what is the news                     -> news               (news.json, headlines only)
#   which book is sharpest               -> book_report        (bookreport.json)
#   the Kalshi / Polymarket price        -> prediction_markets (kalshi.json, predmarkets.json)
#   what just moved, a new edge          -> market_moves       (feed.json, live)
#   how are our bets doing right now     -> our_picks_live     (every board's live_picks, sweat.json)
#   EPA, pace, pass rate over expected   -> team_efficiency    (team_weeks)
#   fantasy usage, waivers, buy low      -> fantasy            (fantasy.json, rosters_nfl.json)
FEED_ROWS = 12
TAPE_POINTS = 6


def _web(data_dir) -> Path:
    return Path(data_dir or ROOT / "web" / "data")


def _slim(row: dict, keep=None) -> dict:
    """A row's plain facts: scalars only, blanks dropped, in ``keep``'s order when given."""
    if not isinstance(row, dict):
        return {}
    keys = keep if keep is not None else list(row)
    return {k: _n(row[k]) for k in keys
            if isinstance(row.get(k), (str, int, float, bool)) and row.get(k) != "" and not str(k).startswith("_")}


def _says(query: str, *texts) -> bool:
    """Does any text name the query: the whole of it, or a word of it long enough to mean something."""
    q = _norm(query).strip()
    if not q:
        return True
    hay = " " + " ".join(_norm(t) for t in texts) + " "
    return f" {q} " in hay or any(f" {w} " in hay for w in q.split() if len(w) >= 4)


def _ago_min(ts, now: float | None = None) -> int | None:
    try:
        return max(0, round(((now or time.time()) - float(ts)) / 60))
    except (TypeError, ValueError):
        return None


def standings(sport: str = "", team: str = "", group: str = "", data_dir=None, prefer: str = "") -> dict:
    """The league's own standings: records by division, home and away, streaks; one team's clutch numbers."""
    from engine import teamdex as T
    s = _league(sport, prefer)
    t = _load_json(_web(data_dir) / f"standings_{s}.json")
    groups = [g for g in t.get("groups") or [] if isinstance(g, dict) and g.get("teams")]
    if not groups:
        out = {"found": False, "note": t.get("note") or f"no {s.upper()} standings on file"}
        if t.get("first_games"):
            out["first_games"] = t["first_games"]
        return out
    codes = _codes_for(team, s) if team else set()
    keep = ("rank", "record", "pct", "games", "pf_per_game", "pa_per_game", "diff", "home", "away",
            "streak_label", "last10_label")
    shown = []
    for g in groups:
        label = str(g.get("label") or " ".join(str(g.get(k) or "") for k in ("conference", "division"))).strip()
        rows = [r for r in g["teams"] if isinstance(r, dict)]
        if team:
            rows = [r for r in rows if r.get("team") in codes or _says(team, T.label(r.get("team"), s))]
        elif group and not _says(group, label):
            continue
        if rows:
            shown.append({"group": label, "teams": [{"team": T.label(r.get("team"), s), **_slim(r, keep)}
                                                    for r in rows]})
    if not shown:
        return {"found": False, "note": f"no {s.upper()} team or group matching {team or group}"}
    out = {"sport": s, "season": t.get("season"), "as_of": t.get("generated_at"),
           "source": "the league's own standings" if t.get("source") == "league" else "counted from our stored games",
           "groups": shown}
    if t.get("order_note"):
        out["order"] = t["order_note"]
    pressure = t.get("pressure") or {}
    for code in codes:
        p = (pressure.get("teams") or {}).get(code)
        if isinstance(p, dict):
            out["under_pressure"] = {"season": pressure.get("season_used"),
                                     **_slim(p, ("record", "clutch", "one_score_games", "reliability", "fav_games",
                                                 "comeback", "dog_games", "choke"))}
            break
    if not team and not group:
        seeds = []
        for c in t.get("projected_seeds") or []:
            if isinstance(c, dict):
                seeds.append({"conference": c.get("conference"),
                              "seeds": [f"{x.get('seed')}. {T.label(x.get('team'), s)} {x.get('record', '')}".strip()
                                        for x in c.get("seeds") or [] if isinstance(x, dict)]})
        if seeds:
            out["projected_playoff_seeds"] = seeds
    if (t.get("bracket") or {}).get("started"):
        out["playoffs_started"] = True
    return out


def roster(team: str = "", player: str = "", position: str = "", sport: str = "", data_dir=None,
           prefer: str = "") -> dict:
    """A team's roster in depth-chart order with each player's status, or the team a player is on."""
    from engine import teamdex as T
    if not team and not player:
        return {"error": "name a team or a player"}
    keep = ("position", "depth_pos", "depth_order", "number", "status", "injury", "age", "years_exp", "college")
    pos = str(position or "").strip().upper()
    for s in _leagues(sport, prefer):
        data = _load_json(_web(data_dir) / f"rosters_{s}.json")
        teams = {k: v for k, v in (data.get("teams") or {}).items() if isinstance(v, dict)}
        if not teams:
            continue
        if player and not team:
            found = [{"team": T.label(code, s), "player": p.get("player"), **_slim(p, keep)}
                     for code, tm in teams.items() for p in tm.get("players") or []
                     if isinstance(p, dict) and _norm(player).strip() in _norm(p.get("player"))]
            if found:
                return {"sport": s, "as_of": data.get("generated_at"), "players": found[:5]}
            continue
        codes = _codes_for(team, s)
        code = next((c for c in codes if c in teams), None)
        if code is None:
            code = next((c for c in teams if _says(team, T.label(c, s))), None)
        if code is None:
            continue
        players = [p for p in teams[code].get("players") or [] if isinstance(p, dict)]
        if player:
            players = [p for p in players if _norm(player).strip() in _norm(p.get("player"))]
        out = {"sport": s, "team": T.label(code, s), "as_of": data.get("generated_at"),
               "count": teams[code].get("count", len(players))}
        if pos:
            players = [p for p in players if pos in (str(p.get("position") or "").upper(),
                                                    str(p.get("depth_pos") or "").upper())]
        elif not player and len(players) > 30:
            # A whole football roster runs past what a lookup carries, so it
            # arrives as its depth chart: the top two at each position, and
            # everyone who is out, by name.
            top, seen = [], {}
            for p in players:
                k = str(p.get("depth_pos") or p.get("position") or "")
                seen[k] = seen.get(k, 0) + 1
                if seen[k] <= 2:
                    top.append(p)
            out["unavailable"] = [f"{p.get('player')} ({p.get('position')}, {p.get('status') or 'out'})"
                                  for p in players if p.get("unavailable")][:15]
            out["shown"] = "the top two at each position"
            players = top
        out["players"] = [{"player": p.get("player"), **_slim(p, keep)} for p in players]
        moves = [_slim(m) for m in ((data.get("transactions") or {}).get("moves") or [])
                 if isinstance(m, dict) and {m.get("from"), m.get("to")} & (codes | {code})]
        if moves:
            out["recent_moves"] = moves[:8]
        return out
    return {"found": False, "note": f"no roster on file for {team or player}"}


def news(sport: str = "", query: str = "", data_dir=None, prefer: str = "") -> dict:
    """The latest headlines we carry, newest first — titles and their publishers, never the article."""
    data = _load_json(_web(data_dir) / "news.json")
    by = data.get("sports") or {}
    leagues = [sport] if sport and sport != "all" else [s for s in [prefer, *LEAGUES, "ufc"] if s in by]
    rows = []
    for s in dict.fromkeys(leagues):
        for r in by.get(s) or []:
            if isinstance(r, dict) and _says(query, r.get("title")):
                rows.append({"league": s, **_slim(r, ("title", "source", "published"))})
    rows.sort(key=lambda r: str(r.get("published") or ""), reverse=True)
    if not rows:
        return {"found": False, "note": "no headline we carry mentions that" if query else "no headlines on file",
                "as_of": data.get("generated_at")}
    return {"as_of": data.get("generated_at"), "headlines_only": True, "rows": rows[:FEED_ROWS]}


def book_report(data_dir=None) -> dict:
    """Which sportsbooks price sharpest: early-price error against the close, and who moves first."""
    data = _load_json(_web(data_dir) / "bookreport.json")
    books = [b for b in data.get("books") or [] if isinstance(b, dict)]
    if not books:
        return {"found": False, "note": "no book report on file yet"}
    out = {"as_of": data.get("generated_at"),
           "books": [{"book": b.get("book"), "early_price_error_pts": b.get("mae_pts"),
                      "moves_first_rate": b.get("lead_rate"), "snapshots": b.get("n"),
                      "ranked": bool(b.get("ranked"))} for b in books[:15]],
           "how": str(data.get("note") or "")[:400]}
    vs = data.get("vs_list") or {}
    if isinstance(vs, dict):
        for k in ("measured_sharpest", "asserted_but_not", "sharp_but_unnamed"):
            if vs.get(k):
                out[k] = vs[k]
    return out


def prediction_markets(query: str = "", sport: str = "", data_dir=None) -> dict:
    """Kalshi and Polymarket prices: the exchange's chance, the books' de-vigged chance, our model's."""
    kal = _paid("kalshi.json", data_dir)
    rows, teams = [], {}
    for r in kal.get("rows") or []:
        if not isinstance(r, dict):
            continue
        lg = str(r.get("sport") or "")
        if sport and sport != "all" and lg != sport:
            continue
        if query and lg in LEAGUES and lg not in teams:
            teams[lg] = _codes_for(query, lg) | _caps(query)     # "Lions" is DET in a matchup
        if query and not (_says(query, r.get("title"), r.get("matchup"), r.get("subtitle"))
                          or teams.get(lg, _caps(query)) & set(str(r.get("matchup") or "").split("@"))):
            continue
        row = _slim(r, ("title", "subtitle", "sport", "matchup"))
        for k, name in (("prob", "kalshi_yes_price"), ("book_p", "books_chance"), ("book_gap_pts", "kalshi_minus_books_pts"),
                        ("model_p", "our_model_chance"), ("edge_pts", "our_edge_pts"), ("volume_24h", "volume_24h"),
                        ("spread_cents", "spread_cents")):
            if r.get(k) is not None:
                row[name] = r[k]
        if r.get("rec"):
            row["our_side"] = r.get("rec_side")
        rows.append(row)
    poly = []
    pm = _paid("predmarkets.json", data_dir)
    for m in pm.get("markets") or []:
        if isinstance(m, dict) and (not query or _says(query, m.get("question"))):
            poly.append({"question": m.get("question"), "polymarket_yes_price": m.get("yes"),
                         "volume_24h": m.get("vol24"), "ends": m.get("end_date")})
    if not rows and not poly:
        return {"found": False, "note": "no Kalshi or Polymarket market we carry matches that"}
    out = {"as_of": kal.get("generated_at") or pm.get("generated_at")}
    if rows:
        out["kalshi"] = rows[:FEED_ROWS]
    if poly:
        out["polymarket"] = poly[:8]
    return out


def market_moves(sport: str = "", player: str = "", kind: str = "", data_dir=None) -> dict:
    """The live feed, newest first: edges appearing and dying, line and price moves, props priced."""
    f = _paid("feed.json", data_dir)
    rows = []
    for e in f.get("events") or []:
        if not isinstance(e, dict):
            continue
        if sport and sport != "all" and e.get("sport") != sport:
            continue
        if kind and e.get("kind") != kind:
            continue
        if player and not _says(player, e.get("player"), " ".join(str(x) for x in e.get("players") or [])):
            continue
        row = {k: v for k, v in _slim(e).items() if k not in ("id", "headshot", "qid")}
        if isinstance(e.get("players"), list):
            row["players"] = [str(x) for x in e["players"][:4]]
        rows.append(row)
    if not rows:
        return {"found": False, "note": "nothing on the live feed for that in the last day",
                "as_of": f.get("generated_at")}
    return {"as_of": f.get("generated_at"), "rows": rows[:FEED_ROWS]}


def our_picks_live(boards: dict, sport: str = "", data_dir=None, prefer: str = "") -> dict:
    """Our open bets right now: each one's stat so far, whether it is still alive, its live chance."""
    keep = ("player", "market_label", "side", "line", "odds", "phase", "status", "current", "still_in",
            "live_prob", "pregame_prob", "opp_left", "opp_unit")
    out = []
    for s in _board_leagues(boards, sport, prefer):
        b = boards[s]
        for key, top in (("live_potd", True), ("live_picks", False)):
            for r in b.get(key) or []:
                if not isinstance(r, dict) or r.get("status") == "unmapped":
                    continue
                row = {"league": s, **_slim(r, keep)}
                g = r.get("game") or {}
                if isinstance(g, dict) and g.get("home"):
                    row["game"] = f"{g.get('away', '')} @ {g.get('home', '')}"
                    row["game_state"] = g.get("state")
                if top:
                    row["pick_of_the_day"] = True
                if all(row != o for o in out):
                    out.append(row)
    res: dict = {}
    if out:
        res["bets"] = out[:20]
    sw = _paid("sweat.json", data_dir)
    tickets = []
    for t in sw.get("parlays") or []:
        if isinstance(t, dict):
            tickets.append({**_slim(t, ("book", "n_legs", "stake_units", "pregame_joint", "live_joint")),
                            "legs": [_slim(x, ("player", "market", "side", "line", "status", "live_prob"))
                                     for x in t.get("legs") or [] if isinstance(x, dict)]})
    if tickets:
        res["parlays"] = tickets[:4]
        res["parlays_as_of"] = sw.get("generated_at")
    if not res:
        return {"found": False, "note": "none of our bets is open right now"
                + (f" in the {sport.upper()}" if sport and sport != "all" else "")}
    return res


def team_efficiency(sport: str = "", team: str = "", sort: str = "off_epa", order: str = "best", season=None,
                    last_n=None, limit=None, prefer: str = "") -> dict:
    """Play-by-play efficiency: EPA per play on offense and defense, pass and run, PROE, pace."""
    from engine import teamdex as T
    from engine import teamprofiles as TP
    if sort not in EFFICIENCY:
        return {"error": "sort is one of: " + ", ".join(EFFICIENCY)}
    s = sport if sport in ("nfl", "cfb") else "nfl"
    conn = _history()
    if conn is None:
        return {"error": "our history database is not available"}
    try:
        n = int(last_n) if last_n not in (None, "") else None
        profiles = TP.season_profiles(conn, int(season) if season not in (None, "") else None, n, sport=s,
                                      min_weeks=1 if n else TP.MIN_WEEKS)
        held = [r[0] for r in conn.execute("SELECT DISTINCT season FROM team_weeks WHERE sport=? ORDER BY season",
                                           (s,)).fetchall()]
    except (TypeError, ValueError):
        return {"error": "season and last_n are whole numbers"}
    finally:
        conn.close()
    if not profiles:
        return {"found": False, "note": f"no {s.upper()} play-by-play efficiency stored"
                + (f" for {season}" if season else ""), "seasons_we_hold": held}
    ranks: dict = {}
    for stat, (_words, better) in EFFICIENCY.items():
        pool = sorted((t for t, p in profiles.items() if p.get(stat) is not None),
                      key=lambda t: profiles[t][stat], reverse=better != "low")
        ranks[stat] = {t: i + 1 for i, t in enumerate(pool)}
    base = TP.league_baseline(profiles)
    yr = next(iter(profiles.values())).get("season")
    head = {"sport": s, "season": yr, "teams": len(profiles), "window": f"last {n} weeks" if n else "the season"}
    if team:
        codes = _codes_for(team, s)
        code = next((c for c in codes if c in profiles), None) or next(
            (c for c in profiles if _says(team, T.label(c, s))), None)
        if code is None:
            return {"found": False, "note": f"no efficiency stored for {team} in {yr}"}
        p = profiles[code]
        return {**head, "team": T.label(code, s), "weeks": p.get("weeks"),
                "stats": {stat: {"value": p.get(stat), "rank": ranks[stat].get(code), "league_average": base.get(stat),
                                 "means": words} for stat, (words, _b) in EFFICIENCY.items() if p.get(stat) is not None}}
    words, better = EFFICIENCY[sort]
    order_ = sorted(ranks[sort], key=ranks[sort].get)
    if order == "worst" and better:
        order_.reverse()
    return {**head, "ranked_by": words, "order": order if better else "most first",
            "league_average": base.get(sort),
            "rows": [{"rank": ranks[sort][t], "team": T.label(t, s), "value": profiles[t][sort],
                      "weeks": profiles[t].get("weeks")} for t in order_[:_limit(limit)]]}


def fantasy(view: str = "usage", player: str = "", position: str = "", data_dir=None) -> dict:
    """The NFL fantasy desk: usage shares, buy-low and sell-high, waiver risers, streamers, trending adds, ranks."""
    if view not in FANTASY_VIEWS:
        return {"error": "view is one of: " + ", ".join(FANTASY_VIEWS)}
    f = _paid("fantasy.json", data_dir)
    pos = str(position or "").strip().upper()

    def pick(rows) -> list[dict]:
        out = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            if player and not _says(player, r.get("player"), r.get("name"), r.get("hurt")):
                continue
            if pos and str(r.get("position") or r.get("pos") or "").upper() not in (pos, ""):
                continue
            out.append(_slim(r))
        return out[:FEED_ROWS]

    if view == "moves":
        data = _load_json(_web(data_dir) / "rosters_nfl.json")
        body = {"moves": pick((data.get("transactions") or {}).get("moves"))}
        stamp = data.get("generated_at")
    elif view == "usage":
        body, stamp = {"usage": pick(f.get("usage"))}, f.get("generated_at")
    elif view in ("buy_sell", "waivers", "trending"):
        block = f.get(view) or {}
        body = {k: pick(v) for k, v in block.items() if isinstance(v, list)} if isinstance(block, dict) else {}
        stamp = f.get("generated_at")
    elif view == "streamers":
        block = f.get("streamers") or {}
        body = {k: pick(v)[:5] for k, v in block.items() if isinstance(v, list) and (not pos or k.upper() == pos)} \
            if isinstance(block, dict) else {}
        stamp = f.get("generated_at")
    else:
        body = {"ranks": pick((f.get("ranks") or {}).get("rows"))}
        stamp = f.get("generated_at")
    body = {k: v for k, v in body.items() if v}
    if not body:
        return {"found": False, "note": f"nothing on the fantasy desk's {view.replace('_', ' ')} for that"}
    return {"view": view, "season": f.get("season"), "as_of": stamp, **body}


_FANTASY_LOG_MARKETS = ("rec_yds", "receptions", "rush_yds", "pass_yds", "pass_td", "rush_td", "rec_td", "fp_ppr")
_FANTASY_BOARD_LISTS = ("recommendations", "most_likely", "long_shots", "longshot_watch")


def _fantasy_rows(boards: dict):
    for lst in _FANTASY_BOARD_LISTS:
        for r in ((boards or {}).get("nfl") or {}).get(lst) or []:
            if isinstance(r, dict) and r.get("player"):
                yield r


def _fantasy_name(conn, boards: dict, name: str) -> tuple:
    """The one NFL player a typed name means: (name or None, other candidates).
    A surname two players share is not a guess — the model is handed both."""
    q = _norm(name).strip()
    pool = {_norm(r["player"]).strip(): r["player"] for r in _fantasy_rows(boards)}
    if conn is not None:
        for (p,) in conn.execute(
                "SELECT DISTINCT player FROM player_game_logs WHERE sport='nfl' AND market='fp_ppr' AND "
                "season >= (SELECT MAX(season) - 1 FROM player_game_logs WHERE sport='nfl')"):
            pool.setdefault(_norm(p).strip(), p)
    if q in pool:
        return pool[q], []
    words = q.replace("'s", "").split()
    hits = sorted({v for k, v in pool.items() if words and all(f" {w} " in f" {k} " for w in words)})
    return (hits[0], []) if len(hits) == 1 else (None, hits[:5])


def _fantasy_season(conn, player: str) -> dict:
    """His latest season's per-game means for every scoring part, and his PPR swing."""
    if conn is None:
        return {}
    got = conn.execute(
        "SELECT season, position, market, COUNT(*) n, AVG(value) a, AVG(value*value) aa FROM player_game_logs "
        "WHERE sport='nfl' AND player=? AND season=(SELECT MAX(season) FROM player_game_logs WHERE sport='nfl' "
        "AND player=?) AND market IN (%s) GROUP BY season, position, market" % ",".join("?" * len(_FANTASY_LOG_MARKETS)),
        (player, player, *_FANTASY_LOG_MARKETS)).fetchall()
    out: dict = {}
    for r in got:
        out["season"], out["position"] = r["season"], (r["position"] or "").upper()
        out[r["market"]] = float(r["a"] or 0.0)
        if r["market"] == "fp_ppr":
            out["games"] = int(r["n"] or 0)
            out["swing"] = max(0.0, float(r["aa"] or 0.0) - float(r["a"] or 0.0) ** 2) ** 0.5
    return out


def fantasy_points(boards: dict, players: list, scoring: str = "ppr") -> dict:
    """This week's projected fantasy points for up to six NFL players, side by side, highest first.

    Each stat is the board's own projection where the board carries the
    player in that market (matchup, weather and injuries already in it),
    else his season average from the game logs, and every part says which.
    Rushing and receiving touchdowns come from our touchdown model's chance
    to score where the board priced one (a Poisson count at that chance),
    else his season rate."""
    rates = FANTASY_SCORING.get(str(scoring or "ppr").lower().replace("-", "").replace("halfppr", "half"))
    if not rates:
        return {"error": "scoring is one of: " + ", ".join(FANTASY_SCORING)}
    names = [str(p).strip() for p in (players or []) if str(p or "").strip()][:FANTASY_PLAYERS_MAX]
    if not names:
        return {"error": "name at least one player"}
    conn = _history()
    try:
        out, unsure = [], {}
        for typed in names:
            name, others = _fantasy_name(conn, boards, typed)
            if not name:
                unsure[typed] = others or "no NFL player by that name in our data"
                continue
            rows = [r for r in _fantasy_rows(boards) if r.get("player") == name]
            season = _fantasy_season(conn, name)
            pos = next((str(r.get("position") or "").upper() for r in rows if r.get("position")), "") \
                or season.get("position", "")
            if pos not in FANTASY_PARTS:
                unsure[typed] = f"{name} is not a QB, RB, WR or TE in our data"
                continue
            parts, pts, fresh = {}, 0.0, 0
            for m in FANTASY_PARTS[pos]:
                row = next((r for r in rows if r.get("market") == m and isinstance(r.get("projection"), (int, float))), None)
                if row is not None:
                    v, src = float(row["projection"]), "this week"
                    fresh += 1
                elif m in season:
                    v, src = season[m], "season average"
                else:
                    continue
                parts[m] = {"value": round(v, 1 if m != "pass_td" else 2), "from": src}
                pts += v * rates["pass_td" if m == "pass_td" else m]
            td = next((r for r in rows if r.get("market") == "anytime_td"
                       and isinstance(r.get("model_prob") or r.get("hit_prob"), (int, float))), None)
            if td is not None:
                p = min(0.95, max(0.0, float(td.get("model_prob") or td.get("hit_prob"))))
                lam = -math.log(1.0 - p)
                tds = {"expected": round(lam, 2), "from": f"our touchdown model, {round(100 * p)}% to score"}
            else:
                lam = season.get("rush_td", 0.0) + season.get("rec_td", 0.0)
                tds = {"expected": round(lam, 2), "from": "his season rate"}
            pts += lam * rates["td"]
            main = next((r for r in rows if r.get("market") == FANTASY_PARTS[pos][0]), None) or (rows[0] if rows else {})
            entry = {"player": name, "team": main.get("team"), "position": pos, "opponent": main.get("opponent"),
                     "projected_points": round(pts, 1), "parts": parts, "touchdowns": tds}
            if season.get("games"):
                entry["season"] = {"season": season.get("season"), "games": season["games"],
                                   "ppr_per_game": round(season.get("fp_ppr", 0.0), 1),
                                   "weekly_swing_ppr": round(season.get("swing", 0.0), 1)}
            card = main.get("matchup_card")
            if isinstance(card, dict) and card.get("text"):
                entry["matchup"] = card["text"]
            if main.get("injury_status"):
                entry["injury"] = main.get("injury_status")
            if not fresh:
                entry["note"] = "not on this week's board: season averages only"
            out.append(entry)
    finally:
        if conn is not None:
            conn.close()
    if not out:
        return {"found": False, "unsure": unsure,
                "note": "no player matched; when a name fits several, ask which one"}
    out.sort(key=lambda e: -e["projected_points"])
    res = {"scoring": {"ppr": "PPR", "half": "half-PPR", "standard": "standard"}[
               next(k for k, v in FANTASY_SCORING.items() if v is rates)],
           "players": out,
           "how": "each stat × the scoring, plus expected touchdowns × 6 (passing touchdowns × 4); not "
                  "counted: interceptions, fumbles, two-point tries, return yards. weekly_swing_ppr is his "
                  "own week-to-week spread: a big one is a boom-or-bust start."}
    if unsure:
        res["unsure"] = unsure
    return res


def defense_vs_position(position: str, team: str = "") -> dict:
    """What every NFL defence gives up per game to one position, from the stored game logs, ranked."""
    pos = str(position or "").strip().upper()
    if pos not in FANTASY_POSITIONS:
        return {"error": "position is one of: " + ", ".join(FANTASY_POSITIONS)}
    conn = _history()
    if conn is None:
        return {"found": False, "note": "no history database on this server"}
    try:
        top = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport='nfl' AND market='fp_ppr'").fetchone()[0]
        if top is None:
            return {"found": False, "note": "no NFL game logs stored"}
        got = conn.execute(
            "SELECT season, period, opponent, market, SUM(value) v FROM player_game_logs WHERE sport='nfl' "
            "AND position=? AND season IN (?, ?) AND market IN (%s) GROUP BY season, period, opponent, market"
            % ",".join("?" * len(_FANTASY_LOG_MARKETS)), (pos, top, top - 1, *_FANTASY_LOG_MARKETS)).fetchall()
    finally:
        conn.close()
    games: dict = {}
    for r in got:
        if r["opponent"]:
            games.setdefault(r["season"], {}).setdefault(r["opponent"], {}).setdefault(r["period"], {})[r["market"]] = \
                float(r["v"] or 0.0)
    now = games.get(top) or {}
    counts = sorted(len(g) for g in now.values())
    seasons = [top] if counts and counts[len(counts) // 2] >= FPA_MIN_GAMES else [top - 1, top]
    per: dict = {}
    for se in seasons:
        for d, wk in (games.get(se) or {}).items():
            per.setdefault(d, []).extend(wk.values())
    if not per:
        return {"found": False, "note": f"no {pos} game logs stored for {top}"}
    shown = {"QB": ("pass_yds", "pass_td", "rush_yds"), "RB": ("rush_yds", "rec_yds", "receptions"),
             "WR": ("rec_yds", "receptions", "rec_td"), "TE": ("rec_yds", "receptions", "rec_td")}[pos]
    table = []
    for d, gl in per.items():
        n = len(gl)
        row = {"defense": d, "games": n, "ppr_allowed": round(sum(g.get("fp_ppr", 0.0) for g in gl) / n, 1)}
        for m in shown:
            row[m] = round(sum(g.get(m, 0.0) for g in gl) / n, 2 if m.endswith("_td") else 1)
        if pos == "RB":
            row["tds"] = round(sum(g.get("rush_td", 0.0) + g.get("rec_td", 0.0) for g in gl) / n, 2)
        table.append(row)
    table.sort(key=lambda r: -r["ppr_allowed"])
    for i, r in enumerate(table, 1):
        r["rank"] = i
    res = {"position": pos, "season": "-".join(str(x) for x in seasons), "of": len(table),
           "league_avg_ppr": round(sum(r["ppr_allowed"] for r in table) / len(table), 1),
           "ranked": "1 = gives up the most", "most_generous": table[:8], "stingiest": table[-5:][::-1]}
    if len(seasons) > 1:
        res["note"] = f"{top} is only a few weeks old, so {top - 1} is read with it"
    if team:
        codes = _codes_for(team, "nfl")
        mine = [r for r in table if r["defense"] in codes]
        res["team"] = mine[0] if mine else f"no {pos} games stored against {team}"
    return res


def _ufc_live(data_dir) -> dict:
    blob = _load_json(_web(data_dir) / "ufc_live.json")
    bouts = []
    for b in blob.get("bouts") or []:
        if not isinstance(b, dict):
            continue
        names = [str(x.get("name") or "") for x in b.get("fighters") or [] if isinstance(x, dict)]
        st = b.get("status") or {}
        row = {"bout": " vs ".join(names), "state": st.get("state"), "detail": st.get("detail")}
        if st.get("live"):
            row["round"], row["clock"] = st.get("round"), st.get("clock")
        won = [str(x.get("name")) for x in b.get("fighters") or [] if isinstance(x, dict) and x.get("winner")]
        if won:
            row["winner"] = won[0]
        bouts.append({k: v for k, v in row.items() if v not in (None, "")})
    if not bouts:
        return {"found": False, "note": blob.get("note") or "no UFC card on our live feed right now"}
    return {"scoreboards": [{"sport": "ufc", "event": blob.get("event"), "as_of": blob.get("generated_at"),
                             "bouts": bouts[:SLATE_GAMES]}]}


def _line_tape(series, now: float | None = None) -> list[dict]:
    """A pick's line since it opened, as a handful of points: the open, the now, and even steps between."""
    pts = [p for p in series or [] if isinstance(p, dict) and p.get("line") is not None]
    if len(pts) > TAPE_POINTS:
        step = (len(pts) - 1) / (TAPE_POINTS - 1)
        pts = [pts[i] for i in sorted({round(i * step) for i in range(TAPE_POINTS)})]
    return [{"minutes_ago": _ago_min(p.get("ts"), now), **_slim(p, ("line", "odds", "book", "books"))} for p in pts]


def injury_history(player: str, sport: str = "") -> list[dict]:
    """Every designation we have seen for one player, newest first: when it posted and when we first saw it."""
    if not str(player or "").strip():
        return []
    conn = _history()
    if conn is None:
        return []
    try:
        q = "SELECT sport, player, team, status, injury, posted_at, first_seen FROM injury_events WHERE player LIKE ?"
        args: list = [f"%{str(player).strip()}%"]
        if sport:
            q += " AND sport=?"
            args.append(sport)
        rows = conn.execute(q + " ORDER BY first_seen DESC LIMIT 8", args).fetchall()
    finally:
        conn.close()
    return [_slim(dict(r)) for r in rows]


def run_tool(name: str, args, boards: dict, prefer: str = "", data_dir=None) -> dict:
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
        if name == "slate":
            return slate(boards, sport, data_dir, prefer)
        if name == "our_picks":
            return our_picks(boards, arg("kind") or "best_bets", sport, a.get("limit"), data_dir, prefer)
        if name == "line_shop":
            return line_shop(boards, arg("query"), sport, prefer)
        if name == "prop_hit_rate":
            return prop_hit_rate(boards, arg("player"), arg("stat"), a.get("line"), arg("side") or "over",
                                 arg("opponent"), sport, prefer)
        if name == "team_trends":
            return team_trends(arg("team"), sport, a.get("season"), prefer)
        if name == "injuries":
            return injuries(arg("team"), arg("player"), sport, data_dir, prefer)
        if name == "schedule":
            return schedule(boards, arg("team"), sport, prefer)
        if name == "live_scores":
            return _ufc_live(data_dir) if sport == "ufc" else live_scores(sport, arg("team"), data_dir, prefer)
        if name == "futures":
            return futures(sport, arg("team"), a.get("limit"), data_dir, prefer)
        if name == "our_record":
            return our_record(sport, arg("window"), bool(a.get("bets")), arg("result"), arg("kind"), data_dir)
        if name == "odds_calc":
            return odds_calc(a.get("odds"), a.get("stake"))
        if name == "league_table":
            return league_table(sport, arg("sort") or "points_allowed", arg("order") or "best",
                                a.get("season"), a.get("limit"), prefer)
        if name == "player_leaders":
            return player_leaders(sport, arg("stat"), arg("by") or "total", a.get("season"),
                                  a.get("limit"), prefer)
        if name == "standings":
            return standings(sport, arg("team"), arg("group"), data_dir, prefer)
        if name == "roster":
            return roster(arg("team"), arg("player"), arg("position"), sport, data_dir, prefer)
        if name == "news":
            return news(sport, arg("query"), data_dir, prefer)
        if name == "book_report":
            return book_report(data_dir)
        if name == "prediction_markets":
            return prediction_markets(arg("query"), sport, data_dir)
        if name == "market_moves":
            return market_moves(sport, arg("player"), arg("kind"), data_dir)
        if name == "our_picks_live":
            return our_picks_live(boards, sport, data_dir, prefer)
        if name == "team_efficiency":
            return team_efficiency(sport, arg("team"), arg("sort") or "off_epa", arg("order") or "best",
                                   a.get("season"), a.get("last_n"), a.get("limit"), prefer)
        if name == "fantasy":
            return fantasy(arg("view") or "usage", arg("player"), arg("position"), data_dir)
        if name == "fantasy_points":
            names = a.get("players") if isinstance(a.get("players"), list) else [arg("players")]
            return fantasy_points(boards, [str(x)[:MAX_ARG] for x in names if str(x or "").strip()],
                                  arg("scoring") or "ppr")
        if name == "defense_vs_position":
            return defense_vs_position(arg("position"), arg("team"))
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
    elif name == "slate":
        label = "Tonight's slate" + (f", {' and '.join(x['sport'].upper() for x in result.get('slates') or [])}"
                                     if result.get("slates") else ", UFC card")
    elif name == "our_picks":
        label = f"Our {str(result.get('kind', 'picks')).replace('_', ' ')} tonight"
    elif name == "line_shop":
        label = "Book prices and line moves"
    elif name == "prop_hit_rate":
        label = f"{result.get('player')}, {result.get('stat')} {result.get('side')} {result.get('line')} hit rates"
    elif name == "team_trends":
        label = f"{result.get('team')}, betting splits"
    elif name == "injuries":
        label = "Injury board"
    elif name == "schedule":
        label = f"{result.get('team')}, schedule"
    elif name == "live_scores":
        label = "Live scoreboard"
    elif name == "futures":
        label = f"{str(result.get('sport', '')).upper()} futures"
    elif name == "our_record":
        label = "Our record"
    elif name == "player_leaders":
        label = f"{result['sport'].upper()} {result['season']} leaders, {result['stat']}"
    elif name == "standings":
        label = f"{result['sport'].upper()} standings"
    elif name == "roster":
        label = f"{result['team']}, roster" if result.get("team") else "Rosters"
    elif name == "news":
        label = "Headlines"
    elif name == "book_report":
        label = "Book report card"
    elif name == "prediction_markets":
        label = "Kalshi and Polymarket prices"
    elif name == "market_moves":
        label = "Live market feed"
    elif name == "our_picks_live":
        label = "Our bets, live"
    elif name == "team_efficiency":
        label = (f"{result['team']}, efficiency" if result.get("team")
                 else f"{result['sport'].upper()} {result['season']} efficiency, by {result['ranked_by']}")
    elif name == "fantasy":
        label = f"Fantasy desk, {str(result.get('view', '')).replace('_', ' ')}"
    elif name == "fantasy_points":
        label = "Fantasy projections, " + ", ".join(p["player"] for p in result.get("players") or [])[:80]
    elif name == "defense_vs_position":
        label = f"Defences vs {result.get('position')}s, {result.get('season')}"
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


def data_as_of(boards: dict, data_dir: Path) -> dict:
    """When each league's board was built and when the refresher last ran, so
    the model can say how fresh a number is instead of implying it is live."""
    out = {s: _ex.board_stamp(b) for s, b in sorted(boards.items())}
    beat = _load_json(Path(data_dir) / "heartbeat.json")
    if beat.get("at"):
        out["site_refreshed"] = str(beat["at"])
    out["asked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
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
    facts: dict = {"rows_matching_the_question": rows, "data_as_of": data_as_of(boards, data_dir)}
    sources: list[dict] = []
    if focus is not None:
        f = detailed(focus)
        f.update(_ex.facts_for(focus))
        facts["the_pick_this_was_asked_from"] = f
    about: dict = {}
    for lst, r, strong in ([(None, focus, True)] * (focus is not None)
                           + [(h[1], h[2], h[0] > 1) for h in hits]):
        label = chip_label(r)
        prop = _ex.pick_id(r) if r.get("player") and r.get("line") is not None and lst != "game_bets" else ""
        if label and all(s["label"] != label for s in sources):
            sources.append({"label": label, "prop": prop, "kind": "pick"})
            about[label] = (None if lst is None and focus is not None and r is focus
                            else _norm(r.get("player")).strip(), strong)
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
        sources += [{"label": f"{_game_label(g)}, lines and weather", "prop": ""} for _, g in games]
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
            "focused": focus is not None, "sources": sources[:8], "about": about, "sections": sorted(facts),
            "boards": boards, "league": sport, "data_dir": data_dir}


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
                  + usage.get("cache_write", 0) * i * 1.25) / 1e6
                 + usage.get("web_searches", 0) * WEB_SEARCH_USD, 6)


def log_usage(model: str, response=None, cached: bool = False, today: str | None = None) -> None:
    """Add one question to today's line in the usage log. ``response`` may be
    a list — a question that looked something up is one call per round."""
    rounds = list(response) if isinstance(response, (list, tuple)) else [response] * (response is not None)
    got = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "web_searches": 0}
    for r in rounds:
        u = getattr(r, "usage", None)
        got["web_searches"] += int(getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0)
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
                d[k] = d.get(k, 0) + v
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


def web_daily_cap() -> int:
    try:
        return int(os.environ.get("QB_ASK_WEB_DAILY", "").strip() or WEB_DAILY_CAP)
    except ValueError:
        return WEB_DAILY_CAP


def searches_today(today: str | None = None) -> int:
    day = today or _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    with _LOCK:
        d = (_read(USAGE_PATH).get("days") or {}).get(day) or {}
    return int(d.get("web_searches", 0) or 0)


def web_tool(model: str) -> dict | None:
    """The web search tool for this model, or None: switched off, or today's searches spent.
    Built once per question, so every round sends the same bytes and the cache holds."""
    cap = web_daily_cap()
    if _WEB["off"] or cap <= 0 or searches_today() >= cap:
        return None
    dynamic = str(model or "").startswith(WEB_DYNAMIC_MODELS)
    return {"type": "web_search_20260209" if dynamic else "web_search_20250305", "name": "web_search",
            "max_uses": WEB_MAX_USES, "blocked_domains": list(WEB_BLOCKED),
            "user_location": {"type": "approximate", "country": "US", "timezone": "America/New_York"}}


def _web_refused(exc) -> bool:
    """The 400 an organisation with search switched off in the Claude Console gets."""
    return getattr(exc, "status_code", None) == 400 and "web search" in str(exc).lower()


def _call(client, model: str, req: dict, last: bool = False):
    """One round. The tools ride on every round, the last one told it may
    not use them — tool_choice leaves the tools-and-system cache alone."""
    web = None if _WEB["off"] else req.get("web")
    kw = dict(model=model, max_tokens=MAX_TOKENS, system=req["system"], messages=req["messages"],
              tools=TOOLS + [web] if web else TOOLS)
    if last:
        kw["tool_choice"] = {"type": "none"}
    try:
        return _send(client, model, kw)
    except Exception as exc:                                            # noqa: BLE001 — re-raised below
        if not (web and _web_refused(exc)):
            raise
        _WEB["off"] = True
        print("  ask: web search is switched off for this organisation in the Claude Console; "
              "answering without it")
        return _send(client, model, {**kw, "tools": TOOLS})


def _send(client, model: str, kw: dict):
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
    made = paused = 0
    req.setdefault("used", set())
    for n in range(MAX_TOOL_ROUNDS + 1):
        response = _call(client, model, {**req, "messages": messages}, last=n == MAX_TOOL_ROUNDS)
        rounds.append(response)
        while getattr(response, "stop_reason", "") == "pause_turn" and paused < MAX_CONTINUATIONS:
            # A long search the API paused: hand the turn back as it came and it resumes.
            paused += 1
            _web_seen(response, req, sources)
            messages = messages + [{"role": "assistant", "content": list(response.content)}]
            response = _call(client, model, {**req, "messages": messages}, last=n == MAX_TOOL_ROUNDS)
            rounds.append(response)
        _web_seen(response, req, sources)
        uses = [b for b in getattr(response, "content", None) or [] if getattr(b, "type", "") == "tool_use"]
        if getattr(response, "stop_reason", "") != "tool_use" or not uses or n == MAX_TOOL_ROUNDS:
            return response, sources, made
        results = []
        for b in uses:
            made += 1
            if made > MAX_TOOL_CALLS:
                out = {"error": "that is all the lookups one question gets; answer with what you have"}
            else:
                out = run_tool(getattr(b, "name", ""), getattr(b, "input", None), req["boards"], req["league"],
                               req.get("data_dir"))
                req["used"].add(getattr(b, "name", ""))
                src = tool_source(getattr(b, "name", ""), getattr(b, "input", None), out)
                if src and src not in sources:
                    sources.append(src)
            results.append({"type": "tool_result", "tool_use_id": getattr(b, "id", ""), "content": fit(out),
                            **({"is_error": True} if out.get("error") else {})})
        messages = messages + [{"role": "assistant", "content": list(response.content)},
                               {"role": "user", "content": results}]
    return response, sources, made


def _web_seen(response, req: dict, sources: list) -> None:
    """Note a round that searched the web, and keep the pages its answer cites."""
    for b in getattr(response, "content", None) or []:
        kind = getattr(b, "type", "")
        if kind == "server_tool_use" and getattr(b, "name", "") == "web_search":
            req["used"].add("web_search")
        for c in (getattr(b, "citations", None) or []) if kind == "text" else []:
            url = str(getattr(c, "url", "") or "")
            if getattr(c, "type", "") != "web_search_result_location" or not re.match(r"https?://", url):
                continue
            host = re.sub(r"^www\.", "", url.split("/")[2]) if url.count("/") >= 2 else url
            chip = {"label": host, "url": url, "title": str(getattr(c, "title", "") or "")[:120], "prop": ""}
            if all(s.get("url") != url for s in sources) and sum(1 for s in sources if s.get("url")) < WEB_SOURCES:
                sources.append(chip)


def answer_text(response) -> str:
    """The answer: the text after the last search or lookup, not the "let me look that up" before it."""
    blocks = list(getattr(response, "content", None) or [])
    last = max((i for i, b in enumerate(blocks) if getattr(b, "type", "") != "text"), default=-1)
    after = "".join(getattr(b, "text", "") for b in blocks[last + 1:] if getattr(b, "type", "") == "text").strip()
    return after or "".join(getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text").strip()


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
    # The record file is in the key too: a record question asked again after
    # the night's grading is a new question.
    try:
        graded = str(int((req["data_dir"] / "record.json").stat().st_mtime))
    except OSError:
        graded = ""
    key = (answer_key(board_name, board, pick, question, req["boards"]) + "\t" + graded
           if fresh and board_name else "")
    if key:
        hit = cached_answer(key)
        if hit:
            log_usage(model, cached=True)
            return {**base, "text": hit["text"], "refused": bool(hit.get("refused")), "cached": True,
                    "sources": hit.get("sources") or shown_sources(base["sources"], hit["text"], req["about"])}
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
    req["web"] = web_tool(model)
    try:
        response, looked, made = converse(client, model, req, rounds)
    except errors as exc:                               # typed, most specific first
        raise _ex.Unavailable(f"{type(exc).__name__}: {getattr(exc, 'message', exc)}") from exc
    except Exception as exc:                            # noqa: BLE001 — a client without the SDK's types
        raise _ex.Unavailable(f"{type(exc).__name__}: {exc}") from exc
    finally:
        if rounds:
            log_usage(model, rounds)
    merged = ([s for s in looked if s.get("url")] + [s for s in looked if not s.get("url")]
              + [s for s in base["sources"] if s not in looked])
    base["lookups"] = made
    if getattr(response, "stop_reason", "") == "refusal":
        base["sources"] = shown_sources(merged, "", req["about"])
        return {**base, "text": "Ask declined to answer that one.", "refused": True, "cached": False}
    text = answer_text(response)
    base["sources"] = shown_sources(merged, text, req["about"])
    if not text:
        raise _ex.Unavailable("the answer had no text")
    if key and not (req.get("used", set()) & NO_CACHE_TOOLS):     # a live score is stale in minutes
        remember_answer(key, {"text": text, "refused": False, "sources": base["sources"]})
    return {**base, "text": text, "refused": False, "cached": False}


def usage_report(days: int = 7) -> str:
    log = _read(USAGE_PATH).get("days") or {}
    lines = ["day         calls  cached  lookups  searches  in_tok   out_tok  cache_rd  ~usd"]
    total = 0.0
    for day in sorted(log)[-days:]:
        d = log[day]
        total += d.get("usd") or 0
        lines.append(f"{day}  {d.get('calls', 0):5}  {d.get('cached', 0):6}  {d.get('lookup_rounds', 0):7}  "
                     f"{d.get('web_searches', 0):8}  {d.get('in', 0):7}  "
                     f"{d.get('out', 0):7}  {d.get('cache_read', 0):8}  {d.get('usd', 0):.4f}")
    lines.append(f"total ~${total:.4f} over {min(days, len(log))} day(s); model {model_name()}; "
                 f"web search {'off' if web_daily_cap() <= 0 else f'up to {web_daily_cap()} a day'}")
    return "\n".join(lines)


if __name__ == "__main__":                              # python3 -m engine.askbot usage
    import sys
    if sys.argv[1:2] == ["usage"]:
        print(usage_report(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
    else:
        print("usage: python3 -m engine.askbot usage [days]")
