"""What each sport's model actually has behind it, checked rather than claimed.

Every sport here has a written spec, and every spec has an implementation
map in ``docs/``. Those maps are prose, and prose rots: a feed stops
resolving, a season's results never get ingested, a key expires, and the
document still says ✅ because nobody edited it.

This module answers the same question by looking. Each layer names the
thing a model needs, why it needs it, and a check that reads the real
database, the real cache and the real config. The output is deliberately
actionable — a missing layer prints the command that fixes it, because
"MLB umpires: missing" is only useful next to the thing you'd run.

Three states and they mean different things:

* **ok** — present and current enough to price with.
* **partial** — there but thin; the model runs and is weaker than it looks.
* **missing** — the model is running without it right now, and the line
  says what that costs.
* **parked** — no free source exists. Listed every time rather than
  quietly dropped, because a permanent gap you've stopped seeing is how a
  model's blind spot becomes its identity.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

OK, PARTIAL, MISSING, PARKED = "ok", "partial", "missing", "parked"
_ICON = {OK: "✅", PARTIAL: "🟡", MISSING: "❌", PARKED: "📋"}

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"


@dataclass
class Layer:
    name: str
    why: str
    state: str
    detail: str = ""
    fix: str = ""


@dataclass
class SportCoverage:
    sport: str
    label: str
    layers: list = field(default_factory=list)

    def __post_init__(self):
        # A layer builder may answer None for "this question does not
        # apply to this sport" — `_prop_closes_layer` does, for a board
        # with no props. Dropping them HERE means no per-sport builder
        # has to remember to, and none of them can forget.
        self.layers = [l for l in self.layers if l is not None]

    @property
    def score(self) -> tuple[int, int]:
        """(layers present, layers that could be present) — parked items are
        excluded from the denominator, because counting a gap with no
        source against the model would make the number meaningless."""
        live = [l for l in self.layers if l.state != PARKED]
        return sum(1 for l in live if l.state == OK), len(live)


# --- primitive checks -------------------------------------------------------
def _count(conn, sql: str, args: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    except Exception:
        return 0


def _games(conn, sport: str) -> tuple[int, int]:
    total = _count(conn, "SELECT COUNT(*) FROM games WHERE sport=?", (sport,))
    scored = _count(conn, "SELECT COUNT(*) FROM games WHERE sport=? AND "
                          "home_score IS NOT NULL", (sport,))
    return total, scored


def _logs(conn, sport: str) -> int:
    return _count(conn, "SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                  (sport,))


def _cache_age_h(pattern: str) -> float | None:
    """Age of the NEWEST cache file matching a glob, in hours.

    A glob, not a filename, and that is a bug fix rather than a flourish:
    the injury feed caches as ``injuries_2026.csv`` and Statcast as
    ``savant_barrels_batter_2026.csv``, so checking for a fixed name
    reported two working feeds as never fetched. A scan that cries wolf is
    worse than no scan — you stop reading it, and then the real gap goes
    past you too.
    """
    try:
        hits = [p for p in CACHE.glob(pattern) if p.is_file()]
    except OSError:
        return None
    if not hits:
        return None
    newest = max(p.stat().st_mtime for p in hits)
    return round((time.time() - newest) / 3600, 1)


def _has_key(env: str) -> bool:
    try:
        from .secrets import load_local_secrets
        load_local_secrets()
    except Exception:
        pass
    return bool(os.environ.get(env))


def _journal(sport: str) -> tuple[int, int]:
    """(open, settled) bets for this sport."""
    try:
        from . import ledger
        conn = ledger.connect()
        o = _count(conn, "SELECT COUNT(*) FROM bets WHERE sport=? AND "
                         "status='open'", (sport,))
        s = _count(conn, "SELECT COUNT(*) FROM bets WHERE sport=? AND "
                         "status IN ('won','lost','push')", (sport,))
        conn.close()
        return o, s
    except Exception:
        return 0, 0


def _results_layer(conn, sport: str, need: int, fix: str) -> Layer:
    total, scored = _games(conn, sport)
    state = OK if scored >= need else PARTIAL if scored else MISSING
    return Layer(
        "Results history", "team ratings, spreads, totals and settlement all "
        "read finished games", state,
        f"{scored} finished game(s) of {total} scheduled (need ~{need})", fix)


def _logs_layer(conn, sport: str, need: int, fix: str) -> Layer:
    n = _logs(conn, sport)
    state = OK if n >= need else PARTIAL if n else MISSING
    return Layer("Player game logs", "every player prop is projected from "
                 "these; without them the board has no props at all", state,
                 f"{n} log row(s) (need ~{need})", fix)


#: Bets you can grade before the number means anything. Below this the ROI
#: is a coin flip with a decimal point, which is worse than no number.
GRADEABLE_BETS = 100


def _game_lines_layer(conn, sport: str) -> Layer:
    """Are there stored CLOSES for the spread/total model to be graded on?

    Every other layer here asks whether the board can be built. This one
    asks whether it can be checked — the game-bet model priced spreads and
    totals for months against numbers nobody wrote down, which is how it
    shipped with no market shrink and no credibility ceiling and nobody
    could tell.
    """
    n = _count(conn, "SELECT COUNT(DISTINCT event_id) FROM odds_history "
                     "WHERE sport=? AND market IN ('total','spread')", (sport,))
    fix = f"python3 game_backtest.py {sport}"
    if n >= GRADEABLE_BETS:
        return Layer("Stored game-line closes", "the spread/total model can "
                     "only be graded against numbers we wrote down", OK,
                     f"{n} game(s) with a stored close — enough to backtest",
                     fix)
    if n:
        return Layer("Stored game-line closes", "the spread/total model can "
                     "only be graded against numbers we wrote down", PARTIAL,
                     f"{n} game(s) stored (want ~{GRADEABLE_BETS} before the "
                     f"ROI means anything) — every build adds more, free", fix)
    return Layer("Stored game-line closes", "the spread/total model can only "
                 "be graded against numbers we wrote down", MISSING,
                 "none yet — the board prices spreads and totals it cannot "
                 "check", "they accumulate on every build from now on; for "
                 "past dates: python3 harvest_odds.py")


def _prop_markets(sport: str) -> set:
    """The player-prop markets this sport's board actually quotes.

    Three sources, because no one of them is honest alone. The harvest
    CONFIG says what can be bought — but CFB's is empty while its
    touchdown board publishes picks every Saturday, so the config alone
    would report that college has no props to price. `HOLD_MARKETS` names
    the Yes-only boards each sport quotes — but only those. The JOURNAL
    says what was actually bet — but a market added before its first pick
    is invisible there, and so is a whole board in its own offseason. The
    union is what this sport is on the hook for.

    Game markets are excluded through `ledger.GAME_MARKETS` rather than a
    second list here, for the reason that constant's own comment gives.
    `GRADED_ELSEWHERE` buckets are dropped too: a Kalshi ticker in the
    `player` column is not a prop this harvest could ever buy.
    """
    from .ledger import GAME_MARKETS, GRADED_ELSEWHERE
    from .maintenance import HOLD_MARKETS
    from .sources.oddsapi import SPORT_CONFIG
    out = set((SPORT_CONFIG.get(sport) or {}).get("markets", {}).values())
    # The Yes-only boards, from the registry that already knows which
    # sport quotes which — `anytime_td` for both football codes and
    # `home_runs` for baseball. Without this CFB reports no props at all
    # in the week before its first pick is journaled, which is the one
    # week the answer would have been worth acting on.
    out.update(m for s, m in HOLD_MARKETS if s == sport)
    try:
        from . import ledger
        conn = ledger.connect()
        holes = ",".join("?" * len(GRADED_ELSEWHERE))
        for row in conn.execute(
                f"SELECT DISTINCT market FROM bets WHERE sport=? AND "
                f"COALESCE(category,'main') NOT IN ({holes})",
                (sport, *GRADED_ELSEWHERE)):
            out.add(str(row[0] or ""))
        conn.close()
    except Exception:                                      # noqa: BLE001
        pass
    return {m for m in out if m and m not in GAME_MARKETS}


def _stored_prop_markets(conn, sport: str) -> dict:
    """``{market: harvested price rows}`` for this sport, game lines aside."""
    from .ledger import GAME_MARKETS
    out: dict = {}
    try:
        rows = conn.execute("SELECT market, COUNT(*) FROM odds_history "
                            "WHERE sport=? GROUP BY market", (sport,))
    except Exception:                                      # noqa: BLE001
        return out
    for row in rows:
        market = str(row[0] or "")
        if market and market not in GAME_MARKETS:
            out[market] = int(row[1] or 0)
    return out


def _settled_props_with_close(sport: str) -> tuple[int, int]:
    """(settled prop bets, how many carry a closing price) for this sport."""
    try:
        from . import ledger
        from .ledger import GAME_MARKETS, GRADED_ELSEWHERE
        conn = ledger.connect()
        marks = ",".join("?" * len(GAME_MARKETS))
        holes = ",".join("?" * len(GRADED_ELSEWHERE))
        row = conn.execute(
            f"SELECT COUNT(*), COUNT(closing_odds) FROM bets WHERE sport=? "
            f"AND status IN ('won','lost','push') "
            f"AND market NOT IN ({marks}) "
            f"AND COALESCE(category,'main') NOT IN ({holes})",
            (sport, *GAME_MARKETS, *GRADED_ELSEWHERE)).fetchone()
        conn.close()
        return int(row[0] or 0), int(row[1] or 0)
    except Exception:                                      # noqa: BLE001
        return 0, 0


def _harvest_fix(sport: str, markets: list) -> str:
    """The command that would buy these markets — or why it cannot.

    Runs the request through the same `unreadable_markets` gate the
    harvester itself uses, so this never prints a command that would spend
    credits on a key the parser drops on the floor.
    """
    from .sources import oddshistory as oh
    if not markets:
        return ""
    try:
        keys = oh.resolve_market_keys(sport, list(markets))
        blocked = set(oh.unreadable_markets(sport, keys))
    except Exception:                                      # noqa: BLE001
        return "python3 harvest_odds.py " + sport
    buyable = [m for m, k in zip(markets, keys) if k not in blocked]
    if not buyable:
        return (f"nothing to run yet — engine.sources.oddsapi.SPORT_CONFIG"
                f"['{sport}']['markets'] names no market the parser can read "
                f"back, so a harvest would spend credits and store nothing")
    return (f"python3 harvest_odds.py {sport} --from YYYY-MM-DD "
            f"--to YYYY-MM-DD --markets {','.join(sorted(buyable))}")


def _prop_closes_layer(conn, sport: str) -> Layer | None:
    """Are there stored CLOSES for the PLAYER-PROP model to be graded on?

    `_game_lines_layer` above asks exactly this for spreads and totals,
    and its docstring records what the absence cost: the game model
    "priced spreads and totals for months against numbers nobody wrote
    down". Nobody ever asked the same question about props.

    The answer, when it was finally asked on 2026-08-27: `odds_history`
    held 157k MLB moneylines, 132k NFL moneylines, 66k NFL spreads, 66k
    NFL totals, 48k MLB total-bases and 16k MLB hits — and not one row
    for any NFL or college player prop. NFL has four configured prop
    markets, an anytime-touchdown board and a grade ladder pooled over
    four seasons, and every bet behind all of it was replayed against a
    synthetic -110 at a trailing average.

    That is not a worthless number — it grades the PROJECTION, and the
    ladder's claimed-vs-landed reading stands on it. It is simply not the
    number anyone thinks they are reading. "The A band lands 49.6%" is a
    statement about the model. "The A band beats the book" has never been
    measured, in any football market, and could not have been.

    Returns None for a sport with no prop board, because a layer that
    appears everywhere is furniture, not information.
    """
    boarded = _prop_markets(sport)
    if not boarded:
        return None
    stored = _stored_prop_markets(conn, sport)
    priced = sorted(m for m in boarded if stored.get(m))
    unpriced = sorted(m for m in boarded if not stored.get(m))
    why = ("a prop replayed against a line we never wrote down measures the "
           "projection, not the market — it cannot say we beat a book")
    fix = _harvest_fix(sport, unpriced) if unpriced else ""

    settled, with_close = _settled_props_with_close(sport)
    clv = ""
    if settled:
        clv = (f"; {with_close} of {settled} settled prop bet(s) carry a "
               f"closing price")

    if not priced:
        return Layer(
            "Stored prop closes", why, MISSING,
            f"no harvested price for any of {_names(unpriced)} — every prop "
            f"number this sport has ever published was graded against a "
            f"synthetic -110{clv}", fix)
    if unpriced:
        rows = sum(stored.get(m, 0) for m in priced)
        return Layer(
            "Stored prop closes", why, PARTIAL,
            f"{rows:,} price row(s) across {_names(priced)}; nothing for "
            f"{_names(unpriced)}{clv}", fix)
    rows = sum(stored.get(m, 0) for m in priced)
    return Layer("Stored prop closes", why, OK,
                 f"{rows:,} price row(s) across {_names(priced)}{clv}", fix)


def _names(markets: list, limit: int = 4) -> str:
    """A readable market list that does not run off the line."""
    markets = list(markets)
    if len(markets) <= limit:
        return ", ".join(markets) or "none"
    return ", ".join(markets[:limit]) + f" (+{len(markets) - limit} more)"


def _odds_layer() -> Layer:
    if _has_key("ODDS_API_KEY"):
        return Layer("Sportsbook prices", "nothing is recommended against a "
                     "line we didn't fetch", OK, "ODDS_API_KEY is set")
    return Layer("Sportsbook prices", "nothing is recommended against a line "
                 "we didn't fetch", MISSING, "ODDS_API_KEY not set",
                 "free key at the-odds-api.com → secrets.local")


BOARD_FILE = {"nfl": "recommendations.json", "mlb": "mlb_recommendations.json",
              "nba": "nba.json", "wnba": "wnba.json", "cfb": "cfb.json",
              "ufc": "ufc.json"}


def _board_status(sport: str) -> str:
    """What the last build of this sport's board said about itself."""
    import json
    p = ROOT / "web" / "data" / BOARD_FILE.get(sport, "")
    try:
        return str(json.loads(p.read_text()).get("status") or "")
    except (OSError, ValueError):
        return ""


def _journal_layer(sport: str) -> Layer:
    o, s = _journal(sport)
    # An empty journal in the offseason is not a gap — there were no games
    # to bet. Reporting it as ❌ next to a real gap is how a scan trains
    # you to skim past the rows that matter.
    dormant = _board_status(sport) in ("offseason", "no_card")
    if not (o or s) and dormant:
        return Layer("Graded record", "CLV and the audit loop are what decide "
                     "whether this model is allowed to keep betting", PARTIAL,
                     "nothing journaled yet — this board is out of season, so "
                     "there has been nothing to bet",
                     "it fills itself once the season starts")
    state = OK if s >= 25 else PARTIAL if (o or s) else MISSING
    return Layer("Graded record", "CLV and the audit loop are what decide "
                 "whether this model is allowed to keep betting", state,
                 f"{s} settled · {o} open",
                 "" if s else "the board journals automatically once it runs")


# --- per-sport inventories --------------------------------------------------
def nfl(conn) -> SportCoverage:
    weeks = _count(conn, "SELECT COUNT(*) FROM team_weeks WHERE sport='nfl'")
    return SportCoverage("nfl", "NFL", [
        _results_layer(conn, "nfl", 250, "python3 ingest.py nfl"),
        _logs_layer(conn, "nfl", 5000, "python3 ingest.py nfl"),
        _odds_layer(),
        _game_lines_layer(conn, "nfl"),
        _prop_closes_layer(conn, "nfl"),
        Layer("EPA / PROE / pace", "§5's volume-first projection — the inputs "
              "that separate a real usage read from a box-score average",
              OK if weeks >= 200 else PARTIAL if weeks else MISSING,
              f"{weeks} team-week row(s)", "python3 ingest.py nfl"),
        Layer("Injury report", "§7's ripple model holds clouded players and "
              "boosts the beneficiaries",
              OK if _cache_age_h("injuries_*.csv") is not None else MISSING,
              _fresh("injuries_*.csv"), "refreshes with the launcher"),
        Layer("Weather", "§7's wind bands block deep passing above 25mph",
              OK, "Open-Meteo, keyless"),
        Layer("Rosters / depth charts", "a traded player projected on his old "
              "team is a silently wrong number",
              OK if _cache_age_h("sleeper_players_nfl*.json") is not None else MISSING,
              _fresh("sleeper_players_nfl*.json"),
              "python3 launch.py --refresh-rosters"),
        Layer("Referee crews", "§7 crew foul tendencies feed the margins",
              PARKED, "no free assignment or tendency feed"),
        Layer("Coordinator tendencies", "§6 scheme profiles", PARKED,
              "no free tendency feed"),
        _journal_layer("nfl"),
    ])


def mlb(conn) -> SportCoverage:
    umps = _count(conn, "SELECT COUNT(*) FROM game_umpires")
    starters = _count(conn, "SELECT COUNT(*) FROM game_starters")
    return SportCoverage("mlb", "MLB", [
        _results_layer(conn, "mlb", 600, "python3 ingest.py mlb --seasons 2021-2026"),
        _logs_layer(conn, "mlb", 20000, "python3 ingest.py mlb --seasons 2021-2026"),
        _odds_layer(),
        _game_lines_layer(conn, "mlb"),
        _prop_closes_layer(conn, "mlb"),
        Layer("Statcast", "exit velocity and barrel rate are the difference "
              "between a hitter's luck and his contact quality",
              OK if _cache_age_h("savant_*.csv") is not None else PARTIAL,
              _fresh("savant_*.csv"), "refreshes with the launcher"),
        Layer("Confirmed lineups", "a projected lineup that never took the "
              "field is a void, and betting it is a guess",
              OK if starters else MISSING, f"{starters} recorded lineup row(s)",
              "refreshes with the launcher"),
        Layer("Umpires", "plate-umpire zone size moves strikeout props more "
              "than most matchups do",
              OK if umps >= 100 else PARTIAL if umps else MISSING,
              f"{umps} game(s) with an umpire recorded", "refreshes with the launcher"),
        Layer("Park factors", "the same fly ball is a home run in one park "
              "and an out in another", OK, "built in, per park and per hand"),
        Layer("Catcher framing", "a framing catcher is worth real strikeouts",
              PARKED, "no free per-game framing feed"),
        _journal_layer("mlb"),
    ])


def nba(conn) -> SportCoverage:
    return SportCoverage("nba", "NBA", [
        _results_layer(conn, "nba", 400,
                       "python3 ingest.py nba --seasons 2021-2026 --scores-only"),
        # NOT --scores-only. That flag is precisely what SKIPS the logs, so
        # offering it as the fix for "0 player game logs" hands over a
        # command that cannot work — and worse, one that exits looking
        # successful because every day is already stored.
        _logs_layer(conn, "nba", 8000,
                    "python3 ingest.py nba --seasons 2024-2026"),
        _odds_layer(),
        _prop_closes_layer(conn, "nba"),
        Layer("Schedule feed", "the free NBA CDN answers 'is there a slate "
              "tonight' before a single credit is spent", OK,
              "cdn.nba.com, keyless"),
        Layer("Availability / injury report", "§2 says a prop is conditional "
              "until the player's status is confirmed; without a feed every "
              "projection assumes she plays", MISSING,
              "no feed wired — minutes come from recent games only",
              "the same gap the WNBA board has; a source would lift both"),
        Layer("Per-possession team defence", "pace pollutes points-allowed, "
              "which is the matchup input the grade reads", PARTIAL,
              "points allowed per GAME, labelled as directional"),
        Layer("Line movement per prop", "§4's first-mover read — who moved "
              "and whether we agree", PARKED,
              "no per-prop movement history is stored yet"),
        _journal_layer("nba"),
    ])


def wnba(conn) -> SportCoverage:
    from .hoops import WNBA
    return SportCoverage("wnba", "WNBA", [
        _results_layer(conn, "wnba", 200, "python3 ingest.py wnba --seasons 2021-2026"),
        _logs_layer(conn, "wnba", 3000, "python3 ingest.py wnba --seasons 2021-2026"),
        _odds_layer(),
        _prop_closes_layer(conn, "wnba"),
        Layer("Schedule feed", "the day's slate and its finals",
              OK, "ESPN basketball/wnba, keyless"),
        Layer("Fitted tuning", "margin SD, blowout curves and stat spreads "
              "are the NBA's until this league has graded results of its own",
              PARTIAL if WNBA.probation else OK,
              "on probation — journaled and graded, not staked "
              "(enforced: engine/probation zeroes every size)",
              # This said "the bar lifts itself", which was not true —
              # `calibrated` was a literal only a source edit could flip.
              # It is now a recorded promotion (engine/promotion), so the
              # bar can be reached; what it deliberately is NOT is
              # automatic, because the worst case of a wrong promotion is
              # money at risk that was not at risk before.
              "the record decides when it is available; promoting is an "
              "explicit, logged act — engine/promotion"),
        Layer("Availability / injury report", "§2.3 — the single highest-edge "
              "information category in this league, and the one that decides "
              "whether a prop is a bet or a conditional", MISSING,
              "no feed wired; freshness is capped and with it the grade, so "
              "half-Kelly stays out of reach",
              "the biggest single upgrade available to this board"),
        Layer("On/off + lineup data", "§5 — when X sits, whose usage jumps. "
              "In a 12-player league this is knowable and rarely priced",
              PARKED, "no free on/off feed; the injury ripple is modelled "
              "from minutes redistribution only"),
        Layer("International windows", "§6 — players arriving late or "
              "carrying an overseas season's fatigue", PARKED,
              "no structured source; a manual note would be guesswork"),
        _journal_layer("wnba"),
    ])


def cfb(conn) -> SportCoverage:
    from .cfb import ratings as R
    from . import teamrates
    # REAL ratings, not {}. The variance is the spread of residuals around
    # what the ratings projected, so an empty map skips every row, leaves
    # nothing to measure, and hands back the PRIOR — which this scan then
    # reported as "Fitted on 4,005 CFB games". A prior wearing a fitted
    # label is the one number on the board nobody would think to check.
    import datetime as _dt
    season = _dt.date.today().year
    # EVERY SEASON, like the build's own variance fit. A current-season
    # map is two teams in August and cannot produce a single residual, so
    # this scan reported the sport's measured variance as MISSING while
    # its own detail line said "Fitted on 3,133 CFB games". The `if not
    # rates` guard below was written for an EMPTY map and a two-team map
    # is just as useless, which is how it survived.
    rates = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0)
    if not rates:
        rates = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0,
                                               seasons=[season])
    fit = R.fit_from_history(conn, rates)
    talent_key = _has_key("CFBD_API_KEY")
    qb = ROOT / "data" / "cfb_qb_status.json"
    return SportCoverage("cfb", "College football", [
        _results_layer(conn, "cfb", R.MIN_GAMES,
                       "python3 ingest.py cfbhist --seasons 2022-2025"),
        # THE LAYER THAT WAS NOT ON THIS SCAN, AND THE ONE THE TOUCHDOWN
        # BOARD IS ENTIRELY MADE OF. `engine.cfb.tds` will not quote a
        # player it has no ingested usage for, and on 2026-08-27 this
        # database held ten CFB player rows against 3,132 games — a board
        # that would have published empty, with nothing on the coverage
        # page saying why.
        _logs_layer(conn, "cfb", 20_000,
                    "python3 ingest.py cfbhist --seasons 2022-2025"),
        Layer("Schedule / conferences / rankings", "attention tier is the "
              "whole model, and it reads all three", OK,
              "ESPN college-football feed, keyless"),
        _odds_layer(),
        _game_lines_layer(conn, "cfb"),
        _prop_closes_layer(conn, "cfb"),
        Layer("Fitted variance", "how far games land from the projection "
              "decides every probability on the board",
              OK if fit.fitted else MISSING,
              fit.note.split(".")[0],
              "python3 ingest.py cfb --seasons 2021-2026"),
        Layer("Recruiting / talent prior", "§5-§6 — in September a team's own "
              "results are two games against unmeasured opponents; the "
              "high-school layer is what carries the number until then",
              OK if talent_key else MISSING,
              "CFBD_API_KEY is set" if talent_key else
              "no key — the board runs with no preseason prior",
              "" if talent_key else
              "free key at collegefootballdata.com/key → secrets.local"),
        Layer("Quarterback status", "§2.3 — a gate, not an adjustment; "
              "unconfirmed games publish conditionals",
              OK if qb.exists() else PARTIAL,
              "confirmations recorded" if qb.exists() else
              "none recorded yet — every game publishes as a conditional",
              'python3 launch.py --confirm-qb "TEAM"'),
        # BUILT, MEASURED, AND NOT ADOPTED — which is why this is PARKED
        # rather than MISSING. §5 asks for success rate and drive stats,
        # and the assumption behind the ask was that opponent-adjusted
        # play efficiency would beat a points-for/points-against rating
        # against the closing line. It was built off the ingested plays
        # and graded on 1,273 held-out games (2024-25, ratings fitted on
        # 2022-23). Its side beat the close on:
        #
        #     success rate            48.4%      yards per play   47.5%
        #     both + the points model 49.8%      pace (totals)    50.1%
        #     yards per play (totals) 50.0%      points model     49.3%
        #
        # Nothing reaches the 52.4% a -110 line needs, in the average or
        # in the tail where the board actually bets. The closing college
        # number already contains this. Parked means "asked and
        # answered", not "not got to yet".
        Layer("Play-by-play efficiency", "§5's success rate and drive stats",
              PARKED,
              "play-level rows are ingested (engine/sources/cfbstats) and "
              "opponent-adjusted efficiency was measured against the close: "
              "no edge over it, so the game model is not built on it"),
        _journal_layer("cfb"),
    ])


def ufc(conn) -> SportCoverage:
    doss = ROOT / "data" / "ufc_dossiers.json"
    n = 0
    if doss.exists():
        try:
            import json
            n = len(json.loads(doss.read_text()))
        except Exception:
            n = 0
    weigh = ROOT / "data" / "ufc_weighins.json"
    cards = ROOT / "data" / "ufc_cards.json"
    return SportCoverage("ufc", "UFC", [
        Layer("Fighter dossiers", "the engine refuses to bet a fighter it has "
              "no measured record for", OK if n >= 20 else PARTIAL if n else MISSING,
              f"{n} dossier(s)", "python3 ufc_dossiers.py"),
        _odds_layer(),
        Layer("Weigh-ins", "'missed weight → automatic void' was a rule with "
              "nothing behind it until this existed",
              OK if weigh.exists() else PARTIAL,
              "recorded" if weigh.exists() else "none recorded this card",
              'python3 launch.py --weigh-in "Fighter" 155.5'),
        Layer("Card venue", "§8 — a 25-foot cage raises finishes and altitude "
              "pushes them later; both reshape every method and distance "
              "price and neither rides in the odds feed",
              OK if cards.exists() else MISSING,
              "recorded" if cards.exists() else "not set — cage size and "
              "altitude unchecked, scored neutral",
              'python3 launch.py --card-venue "UFC Apex" "Las Vegas"'),
        Layer("Method / distance prop prices", "§3.8 — books derive method "
              "props off the moneyline, so the props are the numbers they "
              "did NOT think about. Without prices we can only publish our "
              "fair number for you to shop", PARTIAL,
              "our feed carries moneylines reliably and method markets "
              "rarely; unpriced markets publish a fair number instead",
              "shop the fair numbers on each pick card"),
        Layer("Line movement open → close", "§4 — MMA lines move further from "
              "open to close than almost any market, and the path is the "
              "signal", PARKED,
              "no per-fight movement history is stored yet"),
        Layer("Referee & judge assignments", "§8 — a quick-stoppage referee "
              "raises TKO probability; assigned judges shift every decision "
              "path", PARKED, "no structured assignment feed"),
        _journal_layer("ufc"),
    ])


def _fresh(cache_name: str) -> str:
    age = _cache_age_h(cache_name)
    return "never fetched" if age is None else f"cached {age}h ago"


BUILDERS = {"nfl": nfl, "mlb": mlb, "nba": nba, "wnba": wnba, "cfb": cfb,
            "ufc": ufc}


def scan(sports: list[str] | None = None) -> list[SportCoverage]:
    from .db import connect
    conn = connect()
    try:
        return [BUILDERS[s](conn) for s in (sports or list(BUILDERS))
                if s in BUILDERS]
    finally:
        conn.close()


def report(sports: list[str] | None = None) -> str:
    lines = ["Data & model coverage — measured, not claimed", ""]
    for cov in scan(sports):
        have, total = cov.score
        lines.append(f"{cov.label}  ({have}/{total} live layers present)")
        for l in cov.layers:
            lines.append(f"  {_ICON[l.state]} {l.name}: {l.detail}")
            lines.append(f"       why it matters — {l.why}")
            if l.fix and l.state in (MISSING, PARTIAL):
                lines.append(f"       → {l.fix}")
        lines.append("")
    lines.append("📋 = no free source exists. Listed every time on purpose: a "
                 "permanent gap you've stopped seeing is how a blind spot "
                 "becomes an identity.")
    return "\n".join(lines)
