"""Our own read on a leg the boards do not carry.

Ethan, 2026-10-13, on a graded slip's "Josh Allen Over 5.5 Carries — NOT ON
OUR BOARD": "for picks not on our board ... we need too use every single
too we have available and still scan and use data and our tools too figure
out if it's a good leg or not. We should be able too put it into the game
script and see if it fits or run our offense and defense stats against the
props ... Basically whatever we do too see if a most likely pick fits the
board, we would do too whatever pick is not on our board and see if it
fits or not ... We can't just not give the user information on a prop
since it's not on our board".

A board carries the props its build chose to price: the volume leaders at
each position, in the markets each position is built for, with a book's
price on them. A slip carries whatever a book sells — a quarterback's
carries, a backup's catches, a game the board has not built yet. For a
player prop no board carries, this runs THE MODEL THE BOARD WOULD HAVE RUN,
fed from the same history database the builds read:

  * football (NFL, college) — the generic engine end to end
    (`projection.build_projection` → `betting.evaluate_prop` →
    `rules.apply_rules` → `pipeline._rec_to_dict`): his own games this
    season with last season as the anchor from week four (engine/carry),
    a thin sample topped up from last season and said so, the defence's
    allowed-by-position ratings rebuilt from the same database the way the
    builds rate them (engine/defensevs: this season shrunk toward last;
    college through engine/cfb/defense), and the game card the board
    already holds — its spread, total and weather;
  * basketball (NBA, WNBA) — Scalpy's minutes × per-minute rate × the
    scoring environment × a long layoff × tonight's defence
    (engine/hoopsdvp), calibrated as the board calibrates
    (engine/nba/pipeline.evaluate_prop);
  * hockey — engine/nhl/model: his ice time × his rate per 60, shrunk to
    his position's league rate, against what the opponent allows;
  * baseball — engine/mlb/projection with the park, the game total and
    the opposing starter the board's game card names, priced by the
    board's own curve (engine/mlb/betting.prob_over_at).

Then the questions the Most Likely board asks of every pick it seats
(engine/likelyboard) are asked of this one: our chance against the bar,
the matchup (the scan's lean on him where it has one, else the model's own
matchup step where the board reads one), the market's price beside our
chance, and our journal's record on picks like it — and the tier those
four would have earned. The game script is read for this market off the
posted spread and total (engine/gamescript, engine/gameplan.script_sign):
a script that pushes this side, one that fights it, or one that says
nothing about it.

THE INJURY REPORT FIRST, as every board reads it: a player the board's own
lists name as out (the football scan's injury list, hockey's tale of the
tape, baseball's injured list) or whose props every book took down gets no
number for a game he is not playing; a questionable one keeps his and the
card says so.

WHO PLAYS AROUND HIM AND HOW MUCH HE IS USED (NFL, 2026-10-13): the read
runs the build's own lineup steps — a teammate at his position ruled out
(engine/teammates: the depth order off the database, the absences off the
board's injury lists), his quarterback out or benched (engine/qbchange,
off the card the board published) — and his measured volume role
(engine/nflusage), three inputs it priced without before. What it still
cannot see, said so nobody takes it for more: the role-based injury
effects the build reads off the weekly report (an elite corner out) and
the depth chart's starter-or-backup flag. The live board prices no team
tendency (pace, pass rate); that layer is the backtest's.

NOTHING HERE IS A PICK. A read is not journaled, posted, staked or put on
any board; it is our number for a ticket someone else built, with what it
rests on and why the board did not carry it. Where we keep no games for
him in that market, it says so and prices nothing.
"""
from __future__ import annotations

import math
import os
import sys
import threading
import time

#: The slip's market -> the stored markets it is read from, per sport
#: family: alternatives in order, each a tuple summed game by game (a
#: back's rushing + receiving yards where the combo was never stored).
FOOTBALL_LOGS = {
    "pass_yds": (("pass_yds",),), "pass_td": (("pass_td",),), "pass_att": (("pass_att",),),
    "pass_cmp": (("pass_cmp",),), "pass_int": (("pass_int",),), "rush_yds": (("rush_yds",),),
    "rush_att": (("rush_att",), ("carries",)), "rec_yds": (("rec_yds",),),
    "receptions": (("receptions",),),
    "rush_rec_yds": (("rush_rec_yds",), ("rush_yds", "rec_yds")),
    "pass_rush_yds": (("pass_rush_yds",), ("pass_yds", "rush_yds", "rec_yds")),
    "kick_pts": (("kick_pts",),), "fg_made": (("fg_made",),), "tackles_ast": (("tackles_ast",),),
    "anytime_td": (("anytime_td",), ("rush_td", "rec_td")),
}
HOOPS_LOGS = {"pts": (("pts",),), "reb": (("reb",),), "ast": (("ast",),), "fg3m": (("fg3m",),),
              "pra": (("pts", "reb", "ast"),), "pts_reb": (("pts", "reb"),),
              "pts_ast": (("pts", "ast"),), "reb_ast": (("reb", "ast"),),
              "stl": (("stl",),), "blk": (("blk",),), "tov": (("tov",),)}
HOCKEY_MARKETS = ("sog", "points", "goals", "assists", "blocks", "saves", "anytime_goal")
BASEBALL_LOGS = {"hits": (("hits",),), "total_bases": (("total_bases",),), "home_runs": (("home_runs",),),
                 "strikeouts": (("strikeouts",),), "outs": (("outs",),)}
FAMILY = {"nfl": "football", "cfb": "football", "nba": "hoops", "wnba": "hoops", "nhl": "hockey",
          "mlb": "baseball"}
#: Where a slip names no sport (or "other"), the leagues a market can be
#: read in, in the order tried. A name has to resolve in exactly one.
LEAGUES_FOR = {}
for _m in FOOTBALL_LOGS:
    LEAGUES_FOR[_m] = ("nfl", "cfb")
for _m in HOOPS_LOGS:
    LEAGUES_FOR[_m] = ("nba", "wnba")
for _m in HOCKEY_MARKETS:
    LEAGUES_FOR[_m] = ("nhl",)
for _m in BASEBALL_LOGS:
    LEAGUES_FOR[_m] = ("mlb",)
LEAGUES_FOR["assists"] = ("nhl",)
LEAGUES_FOR["points"] = ("nhl",)

#: Fewer of his games than this in the market and there is no read: three
#: is what every board asks before it builds a prop (nflverse.MIN_LOGS,
#: nba_build's three games, engine/nhl/model's three).
MIN_GAMES = 3
#: A thin current season is topped up from last season up to this many
#: games — the carry the football board makes, said on the card.
TOP_UP = 8
#: The football form window the projection reads (form.WINDOW_WEIGHTS
#: reaches back ten games; more adds nothing).
LOG_WINDOW = 16
#: How long a rebuilt table (a sport's defence ratings, hockey's league
#: rates) is kept before it is rebuilt — the builds refresh their own
#: tables on about this clock, and a slip graded twice in a minute should
#: not pay for the scan twice.
CACHE_S = 1800

#: Words for why the board did not carry the prop, keyed on what is true.
POSITION_MARKETS_NFL = {
    "QB": ("pass_yds", "pass_td", "pass_att", "pass_cmp", "pass_int", "rush_yds", "pass_rush_yds"),
    "RB": ("rush_yds", "rush_att", "receptions", "rec_yds", "rush_rec_yds"),
    "WR": ("rec_yds", "receptions"), "TE": ("receptions", "rec_yds"),
    "K": ("kick_pts", "fg_made"), "DEF": ("tackles_ast",),
}
POSITION_WORDS = {"QB": "quarterbacks", "RB": "running backs", "WR": "receivers", "TE": "tight ends",
                  "K": "kickers", "DEF": "defenders", "FB": "fullbacks"}

_lock = threading.Lock()
_cache: dict = {}


def _cached(key, build):
    """``build()`` kept for CACHE_S under ``key``. A failure is not kept."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_S:
            return hit[1]
    val = build()
    with _lock:
        _cache[key] = (now, val)
        if len(_cache) > 64:                       # never a slow leak
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:16]:
                _cache.pop(k, None)
    return val


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _history_path() -> str:
    from . import askbot as AB
    from . import db as _db
    return str(AB.HISTORY_DB or _db.DEFAULT_DB)


def _connect(path: str | None = None):
    """The history database, read-only in spirit, or None where there is none."""
    path = path or _history_path()
    if not os.path.exists(path):
        return None
    from . import db as _db
    return _db.connect(path)


def _stamp(conn) -> tuple:
    """What a cached table is keyed on: the database file and when it last
    changed, so a nightly ingest is read the next time, not 30 minutes on."""
    try:
        path = conn.execute("PRAGMA database_list").fetchone()[2] or ""
    except Exception:                                              # noqa: BLE001
        path = ""
    try:
        mtime = os.path.getmtime(path) if path else 0.0
    except OSError:
        mtime = 0.0
    return (path or id(conn), mtime)


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _fmt(x) -> str:
    f = _num(x)
    return "" if f is None else f"{f:.1f}".rstrip("0").rstrip(".")


def _key(name) -> str:
    from .teammates import _norm
    return _norm(name)


def _ord(n: int) -> str:
    n = int(n)
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _pkey(season, period) -> tuple:
    """A game's place in time, comparable across the ways a period is
    kept: a zero-padded week, a bare week number, an ISO date."""
    p = str(period or "")
    return (int(season or 0), (0, int(p)) if p.isdigit() else (1, p))


# ---- who he is -----------------------------------------------------------------
def _seasons(conn, sport: str, asof=None) -> list[int]:
    """The two newest seasons this sport has games stored for, newest
    first — as of ``asof``'s season when a replay asks (``asof`` is a
    (season, period) a read is made AS OF, engine/slipreadfit: his games
    before it, the defence rated on the weeks before it. None, the live
    case, is tonight)."""
    if asof:
        rows = conn.execute("SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND season<=? "
                            "ORDER BY season DESC LIMIT 2", (sport, int(asof[0]))).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT season FROM player_game_logs WHERE sport=? "
                            "ORDER BY season DESC LIMIT 2", (sport,)).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]


def resolve(conn, sport: str, leg: dict, markets) -> dict | None:
    """{"player", "team", "position"} as the database stores him, or None.

    The slip's own spelling first ("Josh Allen"); else — for "J. Allen" or
    "Allen" — the ONE player whose surname, initial and (when the slip
    names it) team match, among the players with games in this market
    these two seasons. Two candidates is a guess, and a guess is not
    graded: Josh Allen the quarterback and Josh Allen the edge rusher
    share a name, never a carries log."""
    seasons = _seasons(conn, sport)
    if not seasons:
        return None
    want = _key(leg.get("player"))
    if not want:
        return None
    marks = ",".join("?" * len(markets))
    q = (f"SELECT player, team, position, season, period FROM player_game_logs WHERE sport=? "
         f"AND market IN ({marks}) AND season >= ?")
    latest: dict = {}
    for r in conn.execute(q, (sport, *markets, min(seasons))):
        name = r[0]
        stamp = (int(r[3] or 0), str(r[4] or ""))
        if name not in latest or stamp > latest[name][0]:
            latest[name] = (stamp, str(r[1] or ""), str((r[2] or "")).upper())
    exact = [n for n in latest if _key(n) == want]
    team = str(leg.get("team") or "").upper()
    if len(exact) > 1 and team:
        exact = [n for n in exact if latest[n][1].upper() == team] or exact
    if len(exact) == 1:
        n = exact[0]
        return {"player": n, "team": latest[n][1], "position": latest[n][2]}
    if len(exact) > 1:
        return None
    words = want.split()
    if len(words) > 1 and len(words[0]) > 1:
        return None                          # a full first name that matched nobody is somebody else
    initial = words[0] if len(words) > 1 else ""
    hits = []
    for n in latest:
        got = _key(n).split()
        if len(got) > 1 and got[-1] == words[-1] and got[0].startswith(initial):
            hits.append(n)
    if len(hits) > 1 and team:
        hits = [n for n in hits if latest[n][1].upper() == team]
    if len(hits) != 1:
        return None
    n = hits[0]
    return {"player": n, "team": latest[n][1], "position": latest[n][2]}


def games(conn, sport: str, player: str, alternatives, seasons: list[int],
          before=None) -> tuple[list[dict], tuple]:
    """His games in the market, newest first: [{"season", "period", "team",
    "opponent", "home", "value"}], and the stored markets they were read
    from. The first alternative he has rows for wins; a sum adds what each
    game stored. ``before`` (a (season, period)) keeps only the games
    played before it — a replay's view of him."""
    cut = _pkey(*before) if before else None
    for alt in alternatives:
        marks = ",".join("?" * len(alt))
        sm = ",".join("?" * len(seasons))
        rows = conn.execute(
            f"SELECT season, period, game_id, team, opponent, home, market, value FROM player_game_logs "
            f"WHERE sport=? AND player=? AND market IN ({marks}) AND season IN ({sm}) "
            f"ORDER BY season DESC, period DESC", (sport, player, *alt, *seasons)).fetchall()
        if cut:
            rows = [r for r in rows if _pkey(r[0], r[1]) < cut]
        if not rows:
            continue
        by: dict = {}
        order = []
        for r in rows:
            k = (int(r[0] or 0), str(r[1] or ""), str(r[2] or ""))
            g = by.get(k)
            if g is None:
                g = by[k] = {"season": k[0], "period": k[1], "team": str(r[3] or ""),
                             "opponent": str(r[4] or ""), "home": bool(r[5]), "value": 0.0, "_m": set()}
                order.append(k)
            g["value"] += float(r[7] or 0.0)
            g["_m"].add(str(r[6]))
        out = []
        for k in sorted(order, reverse=True):
            g = by[k]
            g.pop("_m", None)
            g["value"] = round(g["value"], 2)
            out.append(g)
        return out, alt
    return [], ()


# ---- tonight's game ------------------------------------------------------------
def game_card(board: dict | None, team: str, leg: dict, league: str) -> dict | None:
    """The board's own card for his game tonight — the one with his team
    on it, else the one the slip's game text names. None when the board
    has not built it (a game days out, a slate not posted)."""
    cards = [g for g in (board or {}).get("games") or [] if isinstance(g, dict)]
    team = str(team or "").upper()
    for g in cards:
        if team and team in (str(g.get("home") or "").upper(), str(g.get("away") or "").upper()):
            return g
    try:
        from .slipgrade import _codes
        named = _codes(leg.get("game"), league) | _codes(leg.get("team"), league)
    except Exception:                                              # noqa: BLE001
        named = set()
    for g in cards:
        if named and {g.get("home"), g.get("away")} & named:
            return g
    return None


def game_lines(board: dict | None, card: dict | None) -> tuple | None:
    """(home spread, total) for a game: the card's own posted numbers, else
    the board's game bets on it (a basketball card carries no line; its
    spread and total rows do). None when neither has one."""
    if not card:
        return None
    if _posted(card) and card.get("spread") is not None:
        return (_num(card.get("spread")), _num(card.get("total")))
    home, away = card.get("home"), card.get("away")
    spread = total = None
    for r in (board or {}).get("game_bets") or []:
        if not isinstance(r, dict) or r.get("home") != home or r.get("away") != away:
            continue
        kind = str(r.get("market") or r.get("bet_type") or "")
        line = _num(r.get("line"))
        if line is None:
            continue
        if kind == "spread" and spread is None and r.get("team") in (home, away):
            spread = line if r.get("team") == home else -line
        elif kind == "total" and total is None:
            total = line
    return (spread, total) if (spread is not None or total is not None) else None


def _opponent(card: dict | None, team: str, leg: dict) -> str:
    if card:
        h, a = str(card.get("home") or ""), str(card.get("away") or "")
        if team == h:
            return a
        if team == a:
            return h
    return str(leg.get("opponent") or "")


def _posted(card: dict | None) -> bool:
    """Is the card's total a book's number, not the model's placeholder?
    MLB says so outright (`total_posted`); the football card carries a book
    moneyline beside it whenever a book posted the game."""
    if not card or _num(card.get("total")) in (None, 0.0):
        return False
    if "total_posted" in card:
        return bool(card.get("total_posted"))
    return bool(card.get("home_ml") or card.get("away_ml") or card.get("total_measured"))


def script_for(card: dict | None, team: str, market: str, side: str, position: str = "",
               lines: tuple | None = None) -> dict | None:
    """The game script from the posted number, seen from his sideline, and
    which way it pushes THIS side: +1 backs it, -1 fights it, 0 says
    nothing (engine/gameplan.script_sign on engine/gamescript's lean).
    ``lines`` = (home spread, total) where the card itself carries none
    (a basketball card: they ride on its game bets)."""
    spread, total = lines if lines else ((card or {}).get("spread"), (card or {}).get("total"))
    if spread is None or not total or (not lines and not _posted(card)):
        return None
    from .gamescript import for_team
    from .gameplan import script_sign
    d = for_team(spread, total, (card or {}).get("home"), (card or {}).get("away"), team)
    if not d:
        return None
    # The lean is about the BACKS' carries and the passing game; a
    # quarterback's own runs (designed or scrambles) were never measured
    # against it, so for him it is said and not counted either way.
    qb_runs = str(position or "").upper() == "QB" and market in ("rush_att", "rush_yds")
    sign = 0 if qb_runs else script_sign(d.get("lean"), market)
    over = str(side or "").lower() in ("over", "yes")
    fits = sign if over else -sign
    if sign == 0 and not over:
        fits = 0
    fav = d.get("favorite")
    line = f"{fav} by {abs(float(d['spread'])):g}" if fav else "pick'em"
    return {"archetype": d.get("archetype"), "role": d.get("role"), "lean": d.get("lean"),
            "team_implied": d.get("team_implied"), "opp_implied": d.get("opp_implied"),
            "line": f"{line} at {float(d['total']):g}", "fits": fits,
            "text": (f"{d['archetype']}. {team} {d['role']}"
                     + (f" by {abs(float(d['team_spread'])):g}" if d.get("role") != "pick'em" else "")
                     + f", implied {d['team_implied']:g} points — {d['lean']}"),
            "note": ("that lean is about the backs' carries and the passing game; nothing measured says it moves "
                     "a quarterback's own runs" if qb_runs else "")}


# ---- football --------------------------------------------------------------------
_COLUMN = {"pass_yds": "passing_yards", "pass_td": "passing_tds", "rush_yds": "rushing_yards",
           "rec_yds": "receiving_yards", "receptions": "receptions", "carries": "carries",
           "pass_att": "attempts", "pass_cmp": "completions", "pass_int": "passing_interceptions",
           "rush_td": "rushing_tds", "rec_td": "receiving_tds"}


def _nfl_wide(conn, season: int, before: int | None = None) -> list[dict]:
    """One row per player-game, NFL, in the shape engine/defensevs reads:
    what each stored market was, under nflverse's column, with his position
    and the defence he faced. Regular season only, as the builds rate;
    the weeks before ``before`` only when a replay asks."""
    marks = ",".join("?" * len(_COLUMN))
    rows: dict = {}
    for r in conn.execute(f"SELECT period, game_id, player, opponent, position, market, value "
                          f"FROM player_game_logs WHERE sport='nfl' AND season=? AND market IN ({marks})",
                          (int(season), *_COLUMN)):
        try:
            wk = int(str(r[0]))
        except ValueError:
            continue
        if wk <= 0 or wk > 18 or not r[3] or (before is not None and wk >= before):
            continue
        row = rows.setdefault((r[1], r[2]), {"week": wk, "opponent_team": str(r[3]),
                                             "position": str(r[4] or "").upper(), "season_type": "REG"})
        row[_COLUMN[r[5]]] = float(r[6] or 0.0)
    return list(rows.values())


def defence_ratings(conn, sport: str, season: int, date: str = "", asof=None) -> dict:
    """{defence: {stat: rating}} for tonight, rebuilt from the history
    database the way the builds rate: this season's games shrunk toward
    last season's whole (engine/defensevs; college through
    engine/cfb/defense, FBS against FBS). Cached per database version.
    As of a past week when a replay asks (``asof``; college cuts at the
    card's date already)."""
    week = None
    if asof and str(asof[1]).isdigit() and int(asof[0]) == int(season):
        week = int(asof[1])

    def build():
        from . import defensevs as D
        if sport == "cfb":
            from .cfb import defense as CD
            return CD.ratings(conn, int(season), before=(date or None))
        now = _nfl_wide(conn, season, before=week)
        last = _nfl_wide(conn, season - 1)
        prior = D.ratings(last, 99) if last else None
        if not now:
            return ({t: {s: dict(v, games=0, last_season=True) for s, v in r.items()}
                     for t, r in prior.items()} if prior else {})
        return D.ratings(now, 99, prior=prior, week_one_prior=True)
    try:
        return _cached(("def", sport, int(season), str(date)[:10] if sport == "cfb" else "", week, _stamp(conn)),
                       build)
    except Exception:                                              # noqa: BLE001
        return {}


def _football_game(card: dict | None, team: str, opponent: str):
    from .models import Game, Weather
    w = (card or {}).get("weather") or {}
    weather = Weather(dome=bool(w.get("dome")), temp_f=_num(w.get("temp_f"), 65.0),
                      wind_mph=_num(w.get("wind_mph"), 5.0), wind_dir=str(w.get("wind_dir") or ""),
                      precip_chance=_num(w.get("precip_chance"), 0.0), rain=bool(w.get("rain")),
                      snow=bool(w.get("snow")), measured=bool(w.get("measured")),
                      forecast=bool(w.get("forecast")))
    home = str((card or {}).get("home") or team)
    away = str((card or {}).get("away") or opponent)
    posted = _posted(card)
    return Game(home=home, away=away, weather=weather, date=str((card or {}).get("date") or ""),
                kickoff=str((card or {}).get("kickoff") or ""),
                spread=_num((card or {}).get("spread"), 0.0) if posted else 0.0,
                total=_num((card or {}).get("total"), 44.0) if posted else 44.0,
                total_measured=posted, spread_measured=posted,
                roof=str((card or {}).get("roof") or ""), surface=str((card or {}).get("surface") or "grass"),
                neutral_site=bool((card or {}).get("neutral_site")), venue=str((card or {}).get("venue") or ""))


def _position(sport: str, stored: str, market: str) -> str:
    from .defensevs import GROUP_OF
    p = str(stored or "").upper()
    if p in ("K", "DEF") or GROUP_OF.get(p):
        return GROUP_OF.get(p, p)
    if market in ("kick_pts", "fg_made"):
        return "K"
    if market == "tackles_ast":
        return "DEF"
    return {"pass_yds": "QB", "pass_td": "QB", "pass_att": "QB", "pass_cmp": "QB", "pass_int": "QB",
            "pass_rush_yds": "QB", "rush_yds": "RB", "rush_att": "RB", "rush_rec_yds": "RB"}.get(market, "WR")


def _qb_real_games(conn, sport: str, player: str, seasons: list[int], before=None) -> set:
    """The games he really played as a passer (QB_START_ATTEMPTS throws or
    more) — the quarterback games the football board reads his passing
    from (nflverse.quarterbacked)."""
    from .sources.nflverse import QB_START_ATTEMPTS
    sm = ",".join("?" * len(seasons))
    cut = _pkey(*before) if before else None
    return {(int(r[0] or 0), str(r[1] or "")) for r in conn.execute(
        f"SELECT season, period, value FROM player_game_logs WHERE sport=? AND player=? "
        f"AND market='pass_att' AND season IN ({sm})", (sport, player, *seasons))
        if float(r[2] or 0.0) >= QB_START_ATTEMPTS and (cut is None or _pkey(r[0], r[1]) < cut)}


# ---- who plays around him, and how much he is used (NFL) ---------------------------
def _nfl_week(conn, season: int, asof=None) -> int:
    """The week the read is made for: a replay's own, else the one after
    the last week stored — tonight's."""
    if asof and str(asof[1]).isdigit():
        return int(asof[1])
    row = conn.execute("SELECT MAX(CAST(period AS INTEGER)) FROM player_game_logs WHERE sport='nfl' AND season=?",
                       (int(season),)).fetchone()
    return int((row and row[0]) or 0) + 1


def _nfl_stat_rows(conn, season: int, teams) -> list[dict]:
    """This season's box-score rows for these teams in the shape
    engine/teammates.depth_table ranks a depth order on — nflverse's
    columns (week, recent_team, position, player_display_name, targets,
    carries) off the stored markets. No snap file here, so the order is
    on targets and carries, as it was first measured."""
    marks = ",".join("?" * len(teams))
    rows: dict = {}
    for r in conn.execute(
            f"SELECT period, player, team, position, market, value FROM player_game_logs "
            f"WHERE sport='nfl' AND season=? AND team IN ({marks}) AND market IN ('targets', 'carries', 'rush_att')",
            (int(season), *teams)):
        p = str(r[0] or "")
        if not p.isdigit():
            continue
        row = rows.setdefault((int(p), str(r[1])), {"week": int(p), "season_type": "REG",
                                                     "recent_team": str(r[2] or ""),
                                                     "position": str(r[3] or "").upper(),
                                                     "player_display_name": str(r[1])})
        row[str(r[4])] = float(r[5] or 0.0)
    out = []
    for row in rows.values():
        if "carries" not in row and "rush_att" in row:
            row["carries"] = row["rush_att"]
        out.append(row)
    return out


def _depth(conn, season: int, teams: tuple, week: int) -> dict:
    """engine/teammates.depth_table for these teams as of ``week`` — the
    order the teammate-out multipliers were measured on. Cached per
    database version."""
    from . import teammates as TM
    return _cached(("depth", "nfl", int(season), tuple(sorted(teams)), int(week), _stamp(conn)),
                   lambda: TM.depth_table(_nfl_stat_rows(conn, season, teams), set(teams), int(week)))


def _team_outs(board: dict | None, card: dict | None, team: str) -> tuple[set, set]:
    """(ruled out, questionable) on this team tonight, as the lineup step
    keys names: the card's injury list, the books' pulled list, the
    board's rows with a status."""
    from .injuries import RULED_OUT
    from .teammates import MAYBE, _norm
    out: set = set()
    maybe: set = set()

    def take(name, status):
        st = str(status or "").strip().upper()
        if not name:
            return
        if st in RULED_OUT or st == "PULLED":
            out.add(_norm(name))
        elif st in MAYBE:
            maybe.add(_norm(name))
    scan = (card or {}).get("scan") or {}
    for i in scan.get("injuries") or []:
        if isinstance(i, dict) and str(i.get("team") or team).upper() == str(team).upper():
            take(i.get("player"), i.get("status"))
    for name in scan.get("pulled") or []:
        take(name if isinstance(name, str) else (name or {}).get("player"), "PULLED")
    b = board or {}
    for r in list(b.get("recommendations") or []) + list((b.get("likely_board") or {}).get("rows") or []):
        if isinstance(r, dict) and str(r.get("team") or "").upper() == str(team).upper() and r.get("injury_status"):
            take(r.get("player"), r.get("injury_status"))
    return out, maybe


def _lineup(conn, board: dict | None, card: dict | None, season: int, team: str, opponent: str, asof=None) -> dict:
    """Each side's depth order and who is out tonight, as engine/teammates
    .stamp puts them on a game for the build: the order off the database,
    the absences off the board's injury lists. A replay (``asof``) sees the
    order as of its week and no report — none is kept for past games."""
    from .teammates import GROUPS
    teams = tuple(t for t in (team, opponent) if t)
    if not teams:
        return {}
    depth = _depth(conn, season, teams, _nfl_week(conn, season, asof))
    order = depth.get("order") or {}
    last = depth.get("last") or {}
    seen = depth.get("seen") or {}
    weeks = depth.get("weeks") or {}
    lu = {}
    for t in teams:
        out, maybe = _team_outs(board, card, t) if not asof else (set(), set())
        lu[t] = {"order": {pos: order.get(f"{t}|{pos}") or [] for pos in GROUPS},
                 "out": sorted(out), "maybe": sorted(maybe), "last": last.get(t, 0),
                 "basis": depth.get("basis") or "targets",
                 "seen": {pos: seen.get(f"{t}|{pos}") or [] for pos in GROUPS},
                 "weeks": weeks.get(t) or []}
    return lu


def _qb_changes(card: dict | None, team: str, opponent: str) -> dict:
    """{team: change} off the card's QB-change cards (engine/qbchange.card,
    published on every game whose starter is out or benched) — what
    qbchange.effect reads: the tier, the replacement, the starter."""
    out = {}
    for c in (card or {}).get("qb_cards") or []:
        if isinstance(c, dict) and c.get("team") in (team, opponent) and c.get("tier") and c.get("starter") \
                and c.get("status"):
            out[c["team"]] = dict(c)
    return out


def _usage_role(conn, season: int, player: str, team: str, market: str, asof=None) -> dict | None:
    """His measured volume role for this market (engine/nflusage
    .volume_roles), as nfl_build hands the pipeline — the maps built once
    per database version, as of a week for a replay. None where he has no
    role, and none when the maps cannot be built (said on the log)."""
    from .nflusage import build_usage_maps, from_maps, usage_keys
    week = int(asof[1]) if asof and str(asof[1]).isdigit() else None
    try:
        maps = _cached(("usage", "nfl", int(season), week, _stamp(conn)),
                       lambda: build_usage_maps(conn, int(season), week))
    except Exception as exc:                                       # noqa: BLE001
        print(f"slip read: usage maps not built ({type(exc).__name__}: {exc})", file=sys.stderr)
        return None
    role = from_maps(maps.get("volume") or {}, usage_keys(player, team, maps.get("team_of")))
    return (role or {}).get(market) if isinstance(role, dict) else None


def football(conn, board: dict | None, league: str, leg: dict, who: dict, asof=None) -> dict | None:
    """The generic engine on one prop the board did not build. ``asof``,
    a (season, period), makes it a replay's read: his games before it and
    the defence rated on the weeks before it (engine/slipreadfit)."""
    from .models import GameLog, Prop, SportsbookLine, Team, DefenseProfile
    from .projection import build_projection
    from .betting import evaluate_prop
    from .rules import apply_rules
    from . import defensevs as D
    market = leg["market"]
    seasons = _seasons(conn, league, asof)
    rows, used = games(conn, league, who["player"], FOOTBALL_LOGS[market], seasons, before=asof)
    if not rows:
        return None
    pos = _position(league, who.get("position"), market)
    if pos == "QB" and market in ("pass_yds", "pass_td", "pass_att", "pass_cmp", "pass_int", "pass_rush_yds"):
        real = _qb_real_games(conn, league, who["player"], seasons, before=asof)
        if real:
            rows = [g for g in rows if (g["season"], g["period"]) in real]
    season = seasons[0]
    now = [g for g in rows if g["season"] == season]
    before = [g for g in rows if g["season"] != season]
    carried = 0
    use = list(now)
    if len(use) < MIN_GAMES:
        extra = before[:max(0, TOP_UP - len(use))]
        carried = len(extra)
        use = use + extra
    if len(use) < MIN_GAMES:
        return None
    use = use[:LOG_WINDOW]

    def week(g, i):
        try:
            return int(str(g["period"])) if str(g["period"]).isdigit() else len(use) - i
        except ValueError:
            return len(use) - i
    logs = [GameLog(week=week(g, i), opponent=g["opponent"], value=float(g["value"]),
                    home=bool(g["home"]), prior=g["season"] != season) for i, g in enumerate(use)]
    vals_now = [float(g["value"]) for g in now] or [float(g["value"]) for g in use]
    career = sum(vals_now) / len(vals_now)
    # HIS OWN LAST SEASON FROM WEEK FOUR (engine/carry.SEASON_PRIOR_GAMES):
    # the form pulled toward last season's per-game number by n/(n+k),
    # only for a man this involved this season — the board's own rule.
    prior = prior_n = 0
    prior_games = 0.0
    kind = ""
    if not carried and before:
        from .carry import MIN_PRIOR_GAMES, SEASON_PRIOR_FLOOR, SEASON_PRIOR_GAMES
        from .form import compute_form
        k = SEASON_PRIOR_GAMES.get(market)
        last = [float(g["value"]) for g in before if g["season"] == season - 1]
        if k and len(last) >= MIN_PRIOR_GAMES and \
                compute_form(list(logs), career, None).mean >= SEASON_PRIOR_FLOOR.get(market, 0.0):
            prior, prior_n, prior_games, kind = sum(last) / len(last), len(last), float(k), "season"
    team = who.get("team") or str(leg.get("team") or "")
    card = game_card(board, team, leg, league)
    if card and team not in (card.get("home"), card.get("away")):
        # His stored team is last season's; the card the slip named is tonight's.
        named = {card.get("home"), card.get("away")}
        team = next((t for t in named if t and str(t).upper() == str(leg.get("team") or "").upper()), team)
    opponent = _opponent(card, team, leg)
    ratings = defence_ratings(conn, league, season, str((card or {}).get("date") or ""), asof=asof)
    opp_team = Team(abbr=opponent or "OPP", name=opponent or "OPP",
                    defense=DefenseProfile(team=opponent or "OPP", ratings=(ratings or {}).get(opponent) or {}))
    game = _football_game(card, team, opponent)
    usage = None
    if league == "nfl":
        # WHO PLAYS AROUND HIM AND HOW MUCH HE IS USED, as the board prices
        # them: the depth order with the board's injury lists on it
        # (engine/teammates), the card's QB change (engine/qbchange), his
        # measured volume role (engine/nflusage) — the same steps
        # build_projection runs for a board prop. A failure here leaves
        # the read as it was before these landed, and says so.
        try:
            game.lineup = _lineup(conn, board, card, season, team, opponent, asof)
            game.qb_changes = _qb_changes(card, team, opponent)
            usage = _usage_role(conn, season, who["player"], team, market, asof)
        except Exception as exc:                                   # noqa: BLE001
            print(f"slip read: lineup and usage skipped for {who['player']} "
                  f"({type(exc).__name__}: {exc})", file=sys.stderr)
    odds = int(leg.get("odds") or -110)
    side = str(leg.get("side") or "over").lower()
    line = float(leg["line"])
    # A PROXY LINE at the slip's number, as the board prices a prop before
    # books post: the engine projects and prices it and claims no market
    # (has_market False — no "the books say" fact is ever made of it). The
    # slip's own price is the market the checks read, from the leg.
    prop = Prop(player=who["player"], team=team, opponent=opponent or "OPP", position=pos, market=market,
                logs=logs, career_avg=career, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=line, over_odds=-110, under_odds=-110)],
                form_prior=(prior if kind else None), form_prior_n=prior_n,
                form_prior_games=prior_games, form_prior_kind=kind)
    if market == "pass_int":
        att, _ = games(conn, league, who["player"], (("pass_att",),), seasons, before=asof)
        by = {(g["season"], g["period"]): g for g in att}
        paired = [(lg, by.get((g["season"], g["period"]))) for lg, g in zip(logs, use)]
        paired = [(lg, a) for lg, a in paired if a]
        if len(paired) >= MIN_GAMES:
            prop.logs = [lg for lg, _ in paired]
            prop.aux = {"pass_att": [GameLog(week=lg.week, opponent=lg.opponent, value=float(a["value"]),
                                             prior=lg.prior) for lg, a in paired]}
    if market == "anytime_td":
        return _scorer(conn, board, league, leg, who, prop, game, opp_team, card, rows, used, season, pos,
                       ratings, opponent, team)
    proj = build_projection(prop, game, opp_team, sport=league, usage=usage)
    rec = evaluate_prop(prop, proj, allow_synthetic_line=True, game=game, sport=league)
    decision = apply_rules(rec, prop, game)
    from .pipeline import _rec_to_dict
    row = _rec_to_dict(rec, prop, decision, proj, league)
    # The published card's own detail (the replacement's sample, which only
    # the build measured) where the read's copy of the card has none.
    pub = (getattr(game, "qb_changes", None) or {}).get(team)
    if pub and isinstance(row.get("qb_card"), dict) and pub.get("detail"):
        row["qb_card"]["detail"] = pub["detail"]
    # THE SLIP'S BET, not the side the model would have taken: the row
    # speaks for what was bet; the model's own pick rides beside it.
    row["model_side"], row["model_line"] = row.get("side"), row.get("line")
    row.update(side=side, line=line, odds=odds, book="slip")
    # No market was read: the proxy's -110s are the engine's placeholder,
    # and nothing on the card may be made of them.
    row.update(has_market=False, fair_prob=None, edge=None, net_edge=None, fair_consensus=None,
               consensus_books=None, sharp_fair=None, sharp_anchored=False, sharp_quoted=False,
               all_lines=[], alt_lines=[], alt_sharp_lines=[], stake_units=0.0, recommended=False)
    from .gamescript import for_prop
    row["game_script"] = for_prop(game, team, market, pos) if _posted(card) else None
    row["script_fit"] = script_for(card, team, market, side, pos)
    # What the defence gives this position in a market the model has no
    # rating for (a quarterback's carries read his run defence against
    # quarterbacks), SHOWN and kept out of the number — defensevs' rule.
    if not row.get("matchup_card") and opponent and ratings.get(opponent):
        also = {"rush_att": "qb_rush_yds" if pos == "QB" else "rb_rush_att",
                "pass_rush_yds": "qb_rush_yds"}.get(market)
        stat = also or D.stat_for(pos, market)
        if stat:
            c = D.matchup_card(opponent, ratings[opponent], stat)
            if c:
                c["shown_only"] = True
                row["matchup_card"] = c
    row.update(_common(leg, who, team, opponent, card, rows, used, season))
    row["carried"] = carried
    row["position"] = pos
    row["why_off"] = why_off(board, league, leg, who, pos, card)
    return row


def _touch_share(conn, league: str, team: str, season: int, player: str) -> float | None:
    """His share of his team's carries and targets this season — the
    workload the touchdown model scales a scorer by (the board reads the
    same thing off its slate's volume markets)."""
    rows = conn.execute("SELECT player, value FROM player_game_logs WHERE sport=? AND team=? AND season=? "
                        "AND market IN ('carries', 'targets')", (league, team, int(season))).fetchall()
    tot = sum(float(r[1] or 0.0) for r in rows)
    mine = sum(float(r[1] or 0.0) for r in rows if r[0] == player)
    return (mine / tot) if tot > 0 else None


def _scorer(conn, board, league, leg, who, prop, game, opp_team, card, rows, used, season, pos, ratings,
            opponent, team) -> dict:
    """A touchdown scorer the board did not price, through the board's
    touchdown model (engine/touchdowns.td_probability): his team's points
    from the posted spread and total, his share of its touchdowns blended
    from his own scoring rate and his workload, red-zone use inferred from
    that workload, as the board infers it where nothing measured it."""
    from . import defensevs as D
    out = {"player": who["player"], "team": team, "opponent": opponent, "market": "anytime_td",
           "position": pos, "side": str(leg.get("side") or "yes").lower(), "line": 0.5,
           "odds": int(leg.get("odds") or 0) or None, "projection": None, "game_script": None}
    stat = D.stat_for(pos, "anytime_td")
    if stat and opponent and ratings.get(opponent):
        out["matchup_card"] = D.matchup_card(opponent, ratings[opponent], stat)
    out.update(_common(leg, who, team, opponent, card, rows, used, season))
    out["why_off"] = why_off(board, league, leg, who, pos, card)
    if not _posted(card):
        out["refused"] = "no posted spread and total for his game yet — the touchdown model starts from those"
        return out
    share = _touch_share(conn, league, team, season, who["player"])
    if share is None or pos not in ("RB", "WR", "TE", "QB"):
        out["refused"] = "no workload of his on record this season to scale a touchdown chance by"
        return out
    from .touchdowns import td_probability, team_implied_total
    p, why = td_probability(prop, game, opp_team, share)
    out.update(model_over=round(float(p), 4), model_under=round(1.0 - float(p), 4),
               implied_total=round(team_implied_total(game, team), 1), touch_share=round(share, 3),
               reasons=[str(t) for t in ((why or {}).get("reasons") or [])][:4] if isinstance(why, dict) else [])
    return out


# ---- basketball ---------------------------------------------------------------------
def hoops(conn, board: dict | None, league: str, leg: dict, who: dict) -> dict | None:
    """Scalpy's projection for one prop the board did not price."""
    from .nba.pipeline import project
    from .nba.prob import p_over, sd_for
    from .calibrate import calibrated
    market = leg["market"]
    seasons = _seasons(conn, league)
    rows, used = games(conn, league, who["player"], HOOPS_LOGS[market], seasons)
    mins, _ = games(conn, league, who["player"], (("min",),), seasons)
    by_min = {(g["season"], g["period"]): g["value"] for g in mins}
    rows = [dict(g, minutes=by_min.get((g["season"], g["period"]))) for g in rows]
    rows = [g for g in rows if g["minutes"] is not None][:20]
    if len(rows) < MIN_GAMES:
        return None
    team = who.get("team") or str(leg.get("team") or "")
    card = game_card(board, team, leg, league)
    opponent = _opponent(card, team, leg)
    tune = _tuning(conn, league)
    lines = game_lines(board, card)
    spread, fav = 0.0, False
    if lines and lines[0] is not None:
        spread = lines[0] if team == (card or {}).get("home") else -lines[0]
        fav = spread < 0
    date = str((card or {}).get("date") or "")
    dvp_m, dvp_note, dvp_card = 1.0, "", None
    try:
        from . import hoopsdvp as HD
        rating, last = _cached(("hdvp", league, date[:10], _stamp(conn)),
                               lambda: HD.board_ratings(conn, league, date[:10] or _today()))
        dvp_m, dvp_note = HD.projection_mult(league, rating, opponent, market) if market in HD.MARKETS else (1.0, "")
        dvp_card = HD.matchup_card(opponent, rating, market, last, league) if market in HD.MARKETS else None
    except Exception:                                              # noqa: BLE001
        pass
    days_off = None
    try:
        from .nba.context import layoff_days
        days_off = layoff_days([g["period"] for g in rows], date or _today())
    except Exception:                                              # noqa: BLE001
        pass
    side = str(leg.get("side") or "over").lower()
    odds = int(leg.get("odds") or -110)
    line = float(leg["line"])
    prop = {"player": who["player"], "team": team, "opponent": opponent, "market": market, "line": line,
            "over_odds": odds if side == "over" else -110, "under_odds": odds if side == "under" else -110,
            "book": "slip", "minutes": [float(g["minutes"]) for g in rows],
            "values": [float(g["value"]) for g in rows], "is_starter": _starter(conn, league, who["player"]),
            "spread": spread, "is_favorite": fav, "game_total": (lines or (None, None))[1],
            "days_off": days_off, "rest": "1day", "dvp_mult": dvp_m, "dvp_note": dvp_note}
    got = project(prop, tune)
    row = {"player": who["player"], "team": team, "opponent": opponent, "market": market,
           "position": who.get("position") or "", "side": side, "line": line, "odds": odds,
           "projection": None, "matchup_card": dvp_card, "game_script": None}
    if "skip" in got:
        # Scalpy refuses a role it cannot price (a thin sample, minutes
        # that swing): that refusal IS the read, said as the board says it.
        row.update(_common(leg, who, team, opponent, card, rows, used, seasons[0]))
        row.update(refused=str(got["skip"]), why_off=why_off(board, league, leg, who, "", card))
        return row
    proj = float(got["projection"])

    def over_at(x):
        return calibrated(tune.key, market, p_over(market, proj, x, tune))
    sd = float(sd_for(market, proj, tune))
    row.update(projection=round(proj, 2), proj_std=round(sd, 3),
               proj_low=round(max(0.0, proj - sd), 1), proj_high=round(proj + sd, 1),
               reasons=list(got.get("context") or []),
               minutes={"projected": got.get("proj_min"), "base": got.get("base"),
                        "grade": got.get("grade")})
    row.update(_sides(over_at, line, proj, sd))
    if dvp_m != 1.0:
        row["chain"] = {"steps": [{"key": "matchup", "mult": dvp_m, "why": dvp_note, "label": "Matchup"}]}
    row.update(_common(leg, who, team, opponent, card, rows, used, seasons[0]))
    row["why_off"] = why_off(board, league, leg, who, "", card)
    return row


def _starter(conn, league: str, player: str) -> bool:
    r = conn.execute("SELECT position FROM player_game_logs WHERE sport=? AND player=? AND market='min' "
                     "ORDER BY period DESC LIMIT 1", (league, player)).fetchone()
    return bool(r and str(r[0] or "") == "S")


def _tuning(conn, league: str):
    from .hoops import for_league

    def build():
        try:
            from .hoops_fit import fitted_tuning
            return fitted_tuning(conn, league)[0]
        except Exception:                                          # noqa: BLE001
            return for_league(league)
    return _cached(("tune", league, _stamp(conn)), build)


def _today() -> str:
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                              # noqa: BLE001
        return _dt.date.today().isoformat()


# ---- hockey ------------------------------------------------------------------------
def _nhl_tables(conn, seasons: list[int]):
    """(every player's games, the league's per-60 priors, team profiles) —
    engine/nhl/model's own three, for the seasons the board reads."""
    def build():
        from .nhl import model as M
        players = M.player_games(conn, seasons=seasons)
        return players, M.league_rates(players), M.team_profiles(conn, seasons=seasons)
    return _cached(("nhl", tuple(seasons), _stamp(conn)), build)


def hockey(conn, board: dict | None, league: str, leg: dict, who: dict) -> dict | None:
    from .nhl import model as M
    market = leg["market"]
    seasons = _seasons(conn, "nhl")
    if not seasons:
        return None
    players, league_r, teams = _nhl_tables(conn, seasons)
    p = players.get(who["player"])
    if not p:
        return None
    team = p.get("team") or who.get("team") or ""
    card = game_card(board, team, leg, "nhl")
    opponent = _opponent(card, team, leg)
    side = str(leg.get("side") or "over").lower()
    line = float(leg["line"]) if market != "anytime_goal" else 0.5
    if market in M.GOALIE_MARKETS:
        proj = M.goalie_projection(p, league_r, teams, team, opponent)
        if not proj:
            return None

        def over_at(x):
            return M.goalie_prob(proj, x, "OVER")
        sd = float(proj.get("sd") or 0.0)
        reasons = [f"{proj['shots']:.1f} shots expected against × {proj['sv']:.3f} save rate → "
                   f"{proj['mean']:.1f} saves"]
    else:
        proj = M.skater_projection(p, market, league_r, teams, opponent)
        if not proj:
            return None

        def over_at(x):
            return M.skater_prob(proj, market, x, "OVER")
        sd = math.sqrt(max(proj["mean"], 0.0) * float(proj.get("disp") or 1.0))
        label = M.MARKET_LABELS.get(market, market).lower()
        reasons = [f"{proj['toi']:.1f} min of ice time × {proj['rate60']:.2f} per 60 → {proj['mean']:.2f} {label}"]
        if opponent and abs(float(proj.get("opp") or 1.0) - 1.0) >= 0.02:
            reasons.append(f"{opponent} allows {abs(proj['opp'] - 1):.0%} "
                           f"{'more' if proj['opp'] > 1 else 'less'} than an average team")
    stat = {"anytime_goal": "goals"}.get(market, market)
    from .seasons import season_of
    rows = [{"season": season_of("nhl", str(g.get("date") or "")[:10]) if g.get("date") else seasons[0],
             "period": g.get("date"), "team": g.get("team"), "opponent": g.get("opponent"),
             "home": bool(g.get("home")), "value": float(g.get(stat, 0.0))}
            for g in p.get("games") or [] if (g.get("toi", 0) > 0 or market in M.GOALIE_MARKETS)]
    row = {"player": who["player"], "team": team, "opponent": opponent, "market": market,
           "position": p.get("position") or "", "side": side, "line": line, "odds": int(leg.get("odds") or -110),
           "projection": round(float(proj["mean"]), 3), "proj_std": round(sd, 3),
           "proj_low": round(max(0.0, proj["mean"] - sd), 1), "proj_high": round(proj["mean"] + sd, 1),
           "reasons": reasons, "matchup_card": None,
           "nhl": {k: proj.get(k) for k in ("toi", "rate60", "opp", "disp", "sv", "shots") if proj.get(k) is not None},
           "game_script": None}
    row.update(_sides(over_at, line, float(proj["mean"]), sd) if market != "anytime_goal"
               else {"model_over": round(over_at(0.5), 4), "model_under": round(1.0 - over_at(0.5), 4)})
    if market not in M.GOALIE_MARKETS and abs(float(proj.get("opp") or 1.0) - 1.0) >= 0.005:
        row["chain"] = {"steps": [{"key": "matchup", "mult": float(proj["opp"]), "label": "Matchup",
                                   "why": f"{opponent} allows {abs(proj['opp'] - 1):.0%} "
                                          f"{'more' if proj['opp'] > 1 else 'less'} than an average team"}]}
    row.update(_common(leg, who, team, opponent, card, rows, (stat,), seasons[0]))
    row["why_off"] = why_off(board, "nhl", leg, who, "", card)
    return row


# ---- baseball ------------------------------------------------------------------------
def baseball(conn, board: dict | None, league: str, leg: dict, who: dict) -> dict | None:
    from .mlb.models import MLBGame, MLBGameLog, MLBProp, Pitcher
    from .mlb.projection import build_mlb_projection
    from .mlb.betting import prob_over_at
    from .models import SportsbookLine
    market = leg["market"]
    seasons = _seasons(conn, "mlb")
    rows, used = games(conn, "mlb", who["player"], BASEBALL_LOGS[market], seasons)
    if not rows:
        return None
    season = seasons[0]
    now = [g for g in rows if g["season"] == season]
    use = (now if len(now) >= MIN_GAMES else rows)[:40]
    if len(use) < MIN_GAMES:
        return None
    team = who.get("team") or str(leg.get("team") or "")
    card = game_card(board, team, leg, "mlb")
    opponent = _opponent(card, team, leg)
    pos = "SP" if market in ("strikeouts", "outs") else (who.get("position") or "DH")
    logs = [MLBGameLog(game=i + 1, opponent=g["opponent"], value=float(g["value"]), home=bool(g["home"]),
                       date=str(g["period"])) for i, g in enumerate(use[:15])]
    season_vals = [float(g["value"]) for g in (now or use)]
    side = str(leg.get("side") or "over").lower()
    odds = int(leg.get("odds") or -110)
    line = float(leg["line"])
    prop = MLBProp(player=who["player"], team=team, opponent=opponent, position=pos, market=market,
                   logs=logs, career_avg=sum(season_vals) / len(season_vals), vs_pitcher_avg=None,
                   lines=[SportsbookLine(book="slip", line=line, over_odds=odds if side == "over" else -110,
                                         under_odds=odds if side == "under" else -110)],
                   career_games=len(season_vals))
    pitchers = {}
    for where in ("home", "away"):
        pc = ((card or {}).get("pitchers") or {}).get(where) or {}
        code = (card or {}).get(where)
        if pc.get("name") and code:
            pitchers[code] = Pitcher(name=str(pc["name"]), throws=str(pc.get("throws") or "R"),
                                     k_rate=_num(pc.get("k_rate"), 0.22), xera=_num(pc.get("xera"), 4.0))
    park = str(((card or {}).get("park") or {}).get("key") or "generic") if isinstance((card or {}).get("park"), dict) \
        else "generic"
    game = MLBGame(home=str((card or {}).get("home") or team), away=str((card or {}).get("away") or opponent),
                   park=park, date=str((card or {}).get("date") or ""),
                   total=_num((card or {}).get("total"), 8.5) if _posted(card) else 8.5, pitchers=pitchers)
    proj = build_mlb_projection(prop, game)
    row = {"player": who["player"], "team": team, "opponent": opponent, "market": market, "position": pos,
           "side": side, "line": line, "odds": odds, "projection": round(float(proj.mean), 3),
           "proj_std": round(float(proj.std), 3), "proj_low": round(max(0.0, proj.mean - proj.std), 1),
           "proj_high": round(proj.mean + proj.std, 1),
           "reasons": list(getattr(proj, "reasons", []) or [])[:4], "chain": getattr(proj, "chain", None) or None,
           "matchup_card": None, "game_script": None}
    row.update(_sides(lambda x: prob_over_at(prop, proj, x), line, float(proj.mean), float(proj.std)))
    starter = pitchers.get(opponent)
    if starter and pos != "SP":
        row["facing"] = {"name": starter.name, "throws": starter.throws, "k_rate": starter.k_rate,
                         "xera": starter.xera}
    row.update(_common(leg, who, team, opponent, card, rows, used, season))
    row["why_off"] = why_off(board, "mlb", leg, who, pos, card)
    return row


#: A listing that takes a player off the board — every sport's words for it
#: (engine/gamescan.OUT_STATUSES, nhl_build.OUT_STATUSES, the MLB injured
#: list) — and the books' own verdict: every book took his props down,
#: which the boards treat as out (2026-09-26).
OUT_WORDS = {"out", "ir", "doubtful", "pup", "suspended", "inactive", "injured reserve",
             "long term injured reserve", "ltir", "il", "injured list", "pulled"}


def status_of(board: dict | None, player: str, card: dict | None = None) -> str:
    """His listing on tonight's injury report, as the board already holds
    it: a row of his with a status, his game card's injury lists (the
    football scan's, hockey's tale of the tape), the books' pulled list,
    baseball's injured list. "" when nothing names him."""
    want = _key(player)
    if not want:
        return ""
    b = board or {}
    rows = list(b.get("recommendations") or []) + list((b.get("likely_board") or {}).get("rows") or []) \
        + list(b.get("most_likely") or [])
    for r in rows:
        if isinstance(r, dict) and _key(r.get("player")) == want and r.get("injury_status"):
            return str(r["injury_status"])
    cards = [card] if card else []
    cards += [g for g in b.get("games") or [] if isinstance(g, dict) and g is not card]
    for g in cards:
        scan = g.get("scan") or {}
        tape = g.get("nhl_tape") or {}
        lists = [scan.get("injuries") or []] + [(side or {}).get("injuries") or []
                                                 for side in (tape.get("sides") or {}).values()]
        for lst in lists:
            for i in lst:
                if isinstance(i, dict) and _key(i.get("player")) == want and i.get("status"):
                    return str(i["status"])
        for name in list(scan.get("pulled") or []) + list(tape.get("pulled") or []):
            if _key(name) == want:
                return "pulled"
    for name in b.get("injured_list") or []:
        if _key(name if isinstance(name, str) else (name or {}).get("player")) == want:
            return "injured list"
    return ""


def _ruled_out(status: str) -> bool:
    return str(status or "").strip().lower() in OUT_WORDS


def _sides(over_at, line: float, mean: float | None = None, sd: float | None = None) -> dict:
    """Our chance of each side at ``line`` off a model's P(over) curve. At
    a whole number the under is P(below it): the push is neither side's
    (the over at 2.5 is P(3+); the under at 3 is P(2 or fewer)). With the
    projection's mean and spread, the same curve at every half-number
    around it (``rung_probs``, the ladder likely._prob_at reads first), so
    another book's number is priced by this sport's curve, not a normal."""
    over = float(over_at(line))
    under = 1.0 - (float(over_at(line - 0.5)) if float(line).is_integer() else over)
    out = {"model_over": round(over, 4), "model_under": round(max(0.0, under), 4)}
    if mean is not None and sd:
        lo = max(0.5, math.floor((mean - 3.0 * sd) * 2.0) / 2.0)
        hi = mean + 3.0 * sd
        rungs, x = {}, (math.floor(lo) + 0.5 if lo % 1 != 0.5 else lo)
        while x <= hi and len(rungs) < 80:
            rungs[f"{x:g}"] = round(float(over_at(x)), 4)
            x += 1.0
        rungs[f"{float(line):g}"] = out["model_over"]
        out["rung_probs"] = rungs
    return out


# ---- what every read carries ---------------------------------------------------------------
def _common(leg: dict, who: dict, team: str, opponent: str, card: dict | None, rows: list,
            used, season: int) -> dict:
    """His games as the board's rows carry them (newest first), this
    season's average, and the game he plays tonight."""
    vals = [float(g["value"]) for g in rows]
    now = [float(g["value"]) for g in rows if g["season"] == season]
    out = {"recent_values": vals[:12],
           "logs": [{"week": g["period"], "opponent": g["opponent"], "value": g["value"], "home": g["home"],
                     **({"prior": True} if g["season"] != season else {})} for g in rows[:20]],
           "season_avg": round(sum(now) / len(now), 2) if now else None, "season_games": len(now),
           "season": season, "read_from": list(used or ()),
           "home": str((card or {}).get("home") or ""), "away": str((card or {}).get("away") or ""),
           "game_date": str((card or {}).get("date") or ""), "kickoff": str((card or {}).get("kickoff") or ""),
           "on_board_game": bool(card)}
    if not team:
        out["team"] = who.get("team") or ""
    return out


def why_off(board: dict | None, league: str, leg: dict, who: dict, pos: str, card: dict | None) -> str:
    """Why the board did not carry this prop, in the board's own terms."""
    if not card:
        return "his game is not on tonight's board yet, so nothing in it was priced"
    market = leg["market"]
    if league == "nfl" and pos in POSITION_MARKETS_NFL and market not in POSITION_MARKETS_NFL[pos]:
        return f"our board does not build that market for {POSITION_WORDS.get(pos, pos.lower())}"
    rows = [r for r in (board or {}).get("recommendations") or [] if isinstance(r, dict)]
    mine = [r for r in rows if _key(r.get("player")) == _key(who.get("player"))]
    if mine:
        return "we price other markets of his, not this one"
    return "he is not one of the players our board prices in that game"


# ---- the Most Likely board's four questions ------------------------------------------------------
def checks(row: dict, board: dict | None, league: str, prob: float | None) -> dict:
    """The board's own four checks on this read, its notes, and the tier it
    would earn (engine/likelyboard): model (our chance against the bar),
    matchup (the scan's lean on him for this market; else, where the board
    reads one, the model's own matchup step), market (the price's own
    chance against ours), record (our journal on picks like it)."""
    from . import likelyboard as LB
    if prob is None:
        return {}
    side = str(row.get("side") or "").lower()
    r = dict(row, model_prob=prob, side=side)
    bar = LB.SPORT_MODEL_BAR.get(league, LB.MODEL_BAR)["prop"]
    out: dict = {"checks": {}, "notes": {}}
    out["checks"]["model"] = prob >= bar
    out["notes"]["model"] = f"our chance {prob:.0%} (the bar here is {bar:.0%})"
    try:
        from .gamescan import leans_from_reads
        leans = leans_from_reads((board or {}).get("scan_reads") or {})
    except Exception:                                              # noqa: BLE001
        leans = {}
    source = LB.MATCHUP_SOURCE.get(league, "none")
    lean = leans.get((row.get("player") or "", row.get("team") or "", row.get("market")))
    if lean:
        c, n = LB.matchup_check(r, leans, {}, {}, "scan")
    elif source in ("scan+model", "model") or league in ("nba", "wnba", "nhl"):
        steps = {(row.get("player") or "", row.get("market")): (s["mult"], s.get("why") or "")
                 for s in ((row.get("chain") or {}).get("steps") or [])
                 if isinstance(s, dict) and s.get("key") == "matchup" and s.get("mult") is not None}
        c, n = LB._model_matchup(r, steps)
    else:
        c, n = None, "the matchup scan has no read on this market"
    out["checks"]["matchup"], out["notes"]["matchup"] = c, n
    out["checks"]["market"], out["notes"]["market"] = LB.market_check(r)
    table = _record(league)
    out["checks"]["record"], out["notes"]["record"] = (
        LB.record_check(table, row.get("market"), LB._side(r), prob) if table is not None
        else (None, "our record could not be read just now"))
    tier = LB.tier_of(out["checks"])
    out["tier"] = tier
    out["tier_label"] = LB.TIER_LABEL.get(tier, tier)
    out["makes_board"] = bool(prob >= _floor(league))
    return out


def _floor(league: str) -> float:
    from . import likely
    return float(getattr(likely, "SPORT_MIN_PROB", {}).get(league, likely.MIN_PROB))


def _record(league: str) -> dict | None:
    """The record table the board's record check reads (engine/likelyboard
    .record_table), off the journal, cached. Empty when there is none; None
    when the journal could not be read, said on the log and in the check's
    note, so a failed read never passes for a short record. A failure is
    not cached: the next leg asks the journal again."""
    def build():
        from . import ledger
        from . import likelyboard as LB
        conn = ledger.connect()
        try:
            return LB.record_table(conn, league)
        finally:
            conn.close()
    try:
        return _cached(("record", league), build)
    except Exception as exc:                                       # noqa: BLE001
        print(f"slip read: the {league} record could not be read "
              f"({type(exc).__name__}: {exc})", file=sys.stderr)
        return None


# ---- the door ------------------------------------------------------------------------------
READERS = {"football": football, "hoops": hoops, "hockey": hockey, "baseball": baseball}


def read(boards: dict, leg: dict, conn=None) -> dict | None:
    """Our read on one player prop the boards do not carry: a row in the
    board's shape (projection, range, his games, the defence card, the
    chain, the game script) with ``league`` beside it. None where we keep
    no games for him in that market — the card then says so."""
    market = leg.get("market")
    if market in ("moneyline", "spread", "total", "other") or not leg.get("player"):
        return None
    sport = str(leg.get("sport") or "").lower()
    leagues = [sport] if sport in FAMILY else list(LEAGUES_FOR.get(market) or ())
    own = conn is None
    if own:
        conn = _connect()
        if conn is None:
            return None
    try:
        found = []
        for league in leagues:
            fam = FAMILY.get(league)
            logs = {"football": FOOTBALL_LOGS, "hoops": HOOPS_LOGS, "baseball": BASEBALL_LOGS}.get(fam)
            if fam == "hockey":
                stored = ("saves",) if market == "saves" else ("toi", "sog")
            elif logs and market in logs:
                stored = tuple({m for alt in logs[market] for m in alt})
            else:
                continue
            who = resolve(conn, league, leg, stored)
            if who:
                found.append((league, who))
        if len(found) != 1:
            return None                      # nobody, or two leagues' namesakes: a guess
        league, who = found[0]
        board = (boards or {}).get(league)
        key = ("read", league, who["player"], market, str(leg.get("side") or "").lower(),
               _num(leg.get("line")), leg.get("odds"), str((board or {}).get("date") or ""),
               str((board or {}).get("generated_at") or ""), _stamp(conn))

        def build():
            try:
                row = READERS[FAMILY[league]](conn, board, league, leg, who)
            except Exception:                                      # noqa: BLE001
                return None
            if row is None:
                return None
            row["league"] = league
            # THE INJURY REPORT FIRST, as every board reads it: a man ruled
            # out — or one every book took down — has no number for a game
            # he is not playing; a listed one keeps his and the card says so.
            st = status_of(board, row.get("player") or who["player"],
                           game_card(board, row.get("team") or who.get("team") or "", leg, league))
            if st:
                row["injury_status"] = st.title() if st != "pulled" else "Pulled"
                if _ruled_out(st):
                    for k in ("projection", "model_over", "model_under", "proj_low", "proj_high",
                              "proj_std", "rung_probs", "hit_prob"):
                        row[k] = None
                    row["refused"] = ("every book took his props down — the board treats that as out"
                                      if st == "pulled" else
                                      f"he is listed {st.lower()} — the board takes a ruled-out player off")
            return row
        row = _cached(key, build)
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


# ---- the box check ------------------------------------------------------------------------
def main(argv=None) -> int:
    """``python3 -m engine.slipread nfl "Josh Allen" rush_att over 5.5 -130``:
    our read on one prop against the live boards and the history database
    on this machine — the number, what it rests on, the four checks and the
    tier — the way a graded slip would show it. Reads only; writes nothing."""
    import json
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 5:
        print(main.__doc__)
        return 2
    sport, player, market, side, line = args[:5]
    odds = int(args[5]) if len(args) > 5 else -110
    from . import askbot as AB
    from . import gate as G
    from . import slipgrade as SG
    boards = {}
    for league, name in AB.BOARD_FILES.items():
        path = G.full_board_file(name)
        got = AB.board_at(path) if path else None
        if got:
            boards[league] = got
    leg = {"sport": sport, "player": player, "team": "", "market": market, "side": side.lower(),
           "line": float(line), "odds": odds, "game": "", "text": ""}
    at = SG.price_leg(boards, leg)
    at["why"] = SG.why(boards, at)
    row = at.get("row") or {}
    print(json.dumps({"found": at.get("found"), "league": at.get("league"), "player": at.get("player"),
                      "prob": at.get("prob"), "needs": at.get("needs"), "verdict": at.get("verdict"),
                      "projection": row.get("projection"), "range": [row.get("proj_low"), row.get("proj_high")],
                      "opponent": row.get("opponent"), "read": at.get("read"),
                      "checks": (row.get("read_checks") or {}).get("checks"),
                      "why": [f"{f['k']}: {f['t']}" for f in at["why"]]}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
