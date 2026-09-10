"""A team, its record, and how it has actually gone against anybody.

Ethan, 2026-09-09: *"we need to add a feature where you can look up an
actual team and show the past stats versus another team. Example, I
should be able to search for the Los Angeles Rams, and look at how
they've played against any team in the past. And it should also show any
other data and shit for teams that would be useful like offense rank and
defense rank and past wins and loss and shit like that."*

Every number here comes out of the `games` table — the finals this repo
has already ingested — and nothing else. No feed is called, no model is
consulted, and the only judgement in the file is which questions to ask
of a scoreline.

WHY NOT THE STANDINGS FEED. `web/data/standings_*.json` carries offence
and defence ranks and would have been a shorter path. It is built from
the CURRENT season, which on the day this was written held zero games —
the NFL opener is tonight. A team page that says "no rankings" the day
somebody looks up the Rams is a team page nobody opens twice. The finals
go back to 2021 for the NFL and 2022 for college, so this reads them
directly and STAMPS THE SEASON on every row: a rank is meaningless
without the year it is a rank within.

THE SPREAD SIGN, stated because it is the one thing here that is easy to
get backwards and impossible to see. `games.spread` is the HOME team's
number. Seattle home at -2.5 means Seattle laid two and a half; Carolina
home at +10 means Carolina took ten. So the home side covers when
``home_margin + spread > 0``, and exactly zero is a push, not a win.
Every ATS record in this file runs through `_ats` for that reason.

Read-only, and everything is handed a connection. No network, no clock.
"""

from __future__ import annotations

import re


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ats(home_margin: float, spread) -> str | None:
    """"home", "away" or "push" — who covered. ``None`` with no line.

    `spread` is the HOME number: negative means the home side is laying
    it. Adding it to the home margin therefore asks the only question
    that matters, "did the home team beat its own number", and zero is a
    push rather than a cover.
    """
    s = _num(spread)
    if s is None:
        return None
    edge = home_margin + s
    if abs(edge) < 1e-9:
        return "push"
    return "home" if edge > 0 else "away"


def _ou(points: float, total) -> str | None:
    t = _num(total)
    if t is None:
        return None
    if abs(points - t) < 1e-9:
        return "push"
    return "over" if points > t else "under"


def _finals(conn, sport: str, where: str = "", args=()) -> list[dict]:
    """Every PLAYED game for a sport, newest first.

    A row without both scores is not a final — it is tonight's fixture,
    or a game we hold a line for and no result — and counting one as a
    loss is the first thing a page like this gets wrong.

    THE FILTER IS HERE AND NOT IN THE SQL, deliberately. `NOT NULL` would
    catch the missing scores and not the malformed ones, and SQLite will
    hold a string in a REAL column quite happily; `_num` catches both. One
    filter that covers every way a score can fail to be a score beats a
    fast one that covers most of them and a second guard at each caller
    to cover the rest.
    """
    q = ("SELECT season, period, date, home, away, home_score, away_score, "
         "spread, total FROM games WHERE sport=?"
         + (" AND " + where if where else "")
         + " ORDER BY season DESC, period DESC")
    try:
        rows = conn.execute(q, (sport,) + tuple(args)).fetchall()
    except Exception:                                         # noqa: BLE001
        return []
    out = []
    for r in rows:
        g = dict(r)
        if _num(g.get("home_score")) is None or _num(g.get("away_score")) is None:
            continue
        out.append(g)
    return out


def teams(conn, sport: str) -> list[str]:
    """Every team with a final in this sport, sorted."""
    seen = set()
    for g in _finals(conn, sport):
        seen.add(g["home"])
        seen.add(g["away"])
    return sorted(x for x in seen if x)


# --------------------------------------------------------------- naming

def name_map(sport: str) -> dict:
    """``{full name: abbreviation}`` for a sport, from what already exists.

    NOT A NEW TABLE. The book-facing maps in `engine.sources.oddsapi`
    already turn "Los Angeles Rams" into "LA" because that is how every
    price is keyed, and college's map is harvested by the builds
    themselves (`engine.cfbteams`) rather than hand-written, because 134
    schools in reshuffling conferences is the table that rots. A second
    copy here would be a second thing to keep right.

    Empty is a fine answer: the caller still resolves a bare abbreviation,
    which is what a college id like ``espn:61`` will only ever be.
    """
    try:
        from .sources import oddsapi
    except Exception:                                         # noqa: BLE001
        return {}
    if sport == "nfl":
        return dict(getattr(oddsapi, "TEAM_ABBR", {}) or {})
    if sport == "mlb":
        return dict(getattr(oddsapi, "MLB_TEAM_ABBR", {}) or {})
    if sport == "nba":
        return dict(getattr(oddsapi, "NBA_TEAM_ABBR", {}) or {})
    if sport == "wnba":
        return dict(getattr(oddsapi, "WNBA_TEAM_ABBR", {}) or {})
    if sport == "cfb":
        try:
            from . import cfbteams
            return dict(cfbteams.load() or {})
        except Exception:                                     # noqa: BLE001
            return {}
    return {}


def _norm(s) -> str:
    return " ".join(str(s or "").lower().replace(".", " ")
                    .replace("-", " ").split())


def resolve(query: str, sport: str, known=None) -> list[str]:
    """Abbreviations a typed name could mean, best match first.

    Ordered rather than single, because "LA" is a real answer and so is
    "Los Angeles" — one of which is two teams. Handing the page the list
    lets it ASK instead of picking, which is the difference between a
    lookup and a guess.

    Matching is: the abbreviation itself, then a whole full name, then a
    full name that starts with what was typed, then one that contains it.
    A one-character query matches nothing on the last two rules — "a"
    would otherwise return half the league.
    """
    q = _norm(query)
    if not q:
        return []
    names = name_map(sport)
    pool = list(known) if known is not None else sorted(set(names.values()))
    out: list[str] = []

    def add(abbr):
        if abbr and abbr in pool and abbr not in out:
            out.append(abbr)

    for abbr in pool:
        if _norm(abbr) == q:
            add(abbr)
    for full, abbr in sorted(names.items()):
        if _norm(full) == q:
            add(abbr)
    if len(q) >= 2:
        for full, abbr in sorted(names.items()):
            if _norm(full).startswith(q):
                add(abbr)
        for full, abbr in sorted(names.items()):
            # Word-boundary containment: "rams" must find the Rams and
            # "ram" must not, or every query is a substring of something.
            if q in _norm(full).split() or (" " + q + " ") in (
                    " " + _norm(full) + " "):
                add(abbr)
    return out


def label(abbr: str, sport: str) -> str:
    """The longest full name that maps to this abbreviation, or the abbr.

    Longest because "Los Angeles Rams" and "Rams" can both be stored and
    the page wants the one that identifies the team without context.
    """
    best = ""
    for full, a in name_map(sport).items():
        if a == abbr and len(full) > len(best):
            best = full
    return best or abbr


# --------------------------------------------------------------- record

def _blank() -> dict:
    return {"games": 0, "wins": 0, "losses": 0, "ties": 0,
            "points_for": 0.0, "points_against": 0.0,
            "ats_w": 0, "ats_l": 0, "ats_p": 0,
            "over": 0, "under": 0, "ou_p": 0}


def _add(acc: dict, mine: float, theirs: float, at_home: bool, g: dict):
    acc["games"] += 1
    acc["points_for"] += mine
    acc["points_against"] += theirs
    if mine > theirs:
        acc["wins"] += 1
    elif mine < theirs:
        acc["losses"] += 1
    else:
        acc["ties"] += 1
    cover = _ats(_num(g["home_score"]) - _num(g["away_score"]), g["spread"])
    if cover == "push":
        acc["ats_p"] += 1
    elif cover is not None:
        mine_covered = (cover == "home") == at_home
        acc["ats_w" if mine_covered else "ats_l"] += 1
    ou = _ou(_num(g["home_score"]) + _num(g["away_score"]), g["total"])
    if ou == "over":
        acc["over"] += 1
    elif ou == "under":
        acc["under"] += 1
    elif ou == "push":
        acc["ou_p"] += 1


def _finish(acc: dict) -> dict:
    n = acc["games"] or 1
    acc["pf_per_game"] = round(acc["points_for"] / n, 1)
    acc["pa_per_game"] = round(acc["points_against"] / n, 1)
    acc["point_diff"] = round(acc["pf_per_game"] - acc["pa_per_game"], 1)
    acc["record"] = (f"{acc['wins']}-{acc['losses']}"
                     + (f"-{acc['ties']}" if acc["ties"] else ""))
    return acc


def season_table(conn, sport: str, season: int) -> dict:
    """``{team: record}`` for one season — the basis of every rank."""
    out: dict = {}
    for g in _finals(conn, sport, "season=?", (season,)):
        h, a = _num(g["home_score"]), _num(g["away_score"])
        for team, mine, theirs, at_home in ((g["home"], h, a, True),
                                            (g["away"], a, h, False)):
            if not team:
                continue
            _add(out.setdefault(team, _blank()), mine, theirs, at_home, g)
    return {t: _finish(v) for t, v in out.items()}


def _ranked(table: dict, key: str, ascending: bool) -> dict:
    """``{team: rank}``, ties sharing the better rank.

    Shared rather than broken alphabetically: two teams allowing 20.4 a
    game are the same defence, and inventing an order between them puts
    a number on the page that means nothing.
    """
    order = sorted(table, key=lambda t: (table[t][key] if ascending
                                         else -table[t][key], t))
    out, last, rank = {}, None, 0
    for i, t in enumerate(order, 1):
        v = table[t][key]
        if last is None or abs(v - last) > 1e-9:
            rank, last = i, v
        out[t] = rank
    return out


def profile(conn, sport: str, team: str) -> dict:
    """Season by season, with the league rank of each unit that season.

    A rank is only ever reported ALONGSIDE the field it was taken from —
    "7th of 32" — because 7th means one thing in the NFL and another in
    a 137-team college season, and the reader cannot tell which he is
    looking at from the number.
    """
    rows = []
    for season in sorted({g["season"] for g in
                          _finals(conn, sport, "(home=? OR away=?)",
                                  (team, team))}, reverse=True):
        table = season_table(conn, sport, season)
        if team not in table:
            continue
        off = _ranked(table, "pf_per_game", False)
        dfn = _ranked(table, "pa_per_game", True)
        rows.append({**table[team], "season": season,
                     "offense_rank": off.get(team),
                     "defense_rank": dfn.get(team),
                     "teams_ranked": len(table)})
    career = _blank()
    for g in _finals(conn, sport, "(home=? OR away=?)", (team, team)):
        h, a = _num(g["home_score"]), _num(g["away_score"])
        at_home = g["home"] == team
        _add(career, h if at_home else a, a if at_home else h, at_home, g)
    return {"sport": sport, "team": team, "name": label(team, sport),
            "seasons": rows, "career": _finish(career)}


def opponents(conn, sport: str, team: str) -> list[dict]:
    """Everyone this team has a final against, most-played first.

    The picker's own list. Offering all 32 clubs when we hold games
    against nineteen of them would advertise seventeen empty pages.
    """
    counts: dict = {}
    for g in _finals(conn, sport, "(home=? OR away=?)", (team, team)):
        other = g["away"] if g["home"] == team else g["home"]
        if other and other != team:
            counts[other] = counts.get(other, 0) + 1
    return [{"team": t, "name": label(t, sport), "games": n}
            for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def head_to_head(conn, sport: str, team: str, opp: str) -> dict:
    """Every meeting, newest first, and what each one settled at."""
    games, acc = [], _blank()
    for g in _finals(conn, sport,
                     "((home=? AND away=?) OR (home=? AND away=?))",
                     (team, opp, opp, team)):
        h, a = _num(g["home_score"]), _num(g["away_score"])
        at_home = g["home"] == team
        mine, theirs = (h, a) if at_home else (a, h)
        _add(acc, mine, theirs, at_home, g)
        cover = _ats(h - a, g["spread"])
        ou = _ou(h + a, g["total"])
        games.append({
            "season": g["season"], "period": g["period"], "date": g["date"],
            "home": g["home"], "away": g["away"],
            "home_score": h, "away_score": a,
            "at_home": at_home, "points_for": mine, "points_against": theirs,
            "margin": round(mine - theirs, 1),
            "result": "W" if mine > theirs else "L" if mine < theirs else "T",
            "spread": _num(g["spread"]), "total": _num(g["total"]),
            # SIGNED FOR THE TEAM BEING LOOKED UP, not for the home side.
            # A page that shows the Rams and prints Seattle's number is
            # correct arithmetic answering somebody else's question.
            "line": (None if _num(g["spread"]) is None
                     else (_num(g["spread"]) if at_home
                           else -_num(g["spread"]))),
            "covered": (None if cover is None else "push" if cover == "push"
                        else ((cover == "home") == at_home)),
            "ou": ou,
        })
    return {"sport": sport, "team": team, "opponent": opp,
            "name": label(team, sport), "opponent_name": label(opp, sport),
            "games": games, "summary": _finish(acc)}


#: WHICH LINE LEADS A POSITION. A quarterback's row is about passing
#: yards and a receiver's is about catches, and a squad list that sorted
#: every position on the same market would rank the whole offence by
#: whichever stat the quarterback happens to dominate. Falls back to the
#: player's own biggest total when a position is not here — a college
#: roster carries positions this table has never seen, and guessing at
#: them is worse than reading the numbers.
LEAD_MARKET = {
    "QB": "pass_yds", "RB": "rush_yds", "FB": "rush_yds",
    "WR": "rec_yds", "TE": "rec_yds",
    "C": "hits", "1B": "hits", "2B": "hits", "3B": "hits", "SS": "hits",
    "LF": "hits", "CF": "hits", "RF": "hits", "DH": "hits", "OF": "hits",
    "G": "pts", "F": "pts", "PG": "pts", "SG": "pts", "SF": "pts",
    "PF": "pts",
}

#: How many players a position lists before the rest are folded away.
#: A 90-man NFL roster is not a page.
SQUAD_PER_POSITION = 6

#: Markets whose value is a RATE, not a count, so summing them is
#: meaningless. Ethan's Rams page, 2026-09-10, showed "Nick Vannett —
#: Snap Pct 0/g · 0.3 total": seven games at a four-percent snap share
#: added up to 0.3 of nothing, and the per-game number rounded to zero.
#: A rate's honest summary is its mean, printed as a percentage.
#:
#: `snap_pct` is the only one this table holds today (`ingest.
#: snap_count_rows` writes it 0-1). Kept as a set rather than a name
#: check so the next one is a one-line change and not a new bug.
RATE_MARKETS = {"snap_pct"}


def _latest_season(conn, sport: str, team: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(season) FROM player_game_logs WHERE sport=? AND team=?",
        (sport, team)).fetchone()
    return row[0] if row and row[0] is not None else None


_ABBREV = re.compile(r"^[A-Za-z]\.")


def _is_abbreviated(name: str) -> bool:
    """"K.Williams" — a first initial, a dot, and no first name.

    The one shape `sources.nflpbp` writes and the one shape that cannot
    identify a person on its own. A full name never matches it.
    """
    return bool(_ABBREV.match(str(name or "").strip()))


def _absorb(who: dict, r) -> None:
    """Fold one (player, market) group row into a squad entry."""
    name = str(r["player"])
    who["games"] = max(who["games"], int(r["games"] or 0))
    # A position can differ between a player's rows (a feed changing its
    # mind mid-season); the first non-empty one wins rather than the
    # last, so the list does not reshuffle on a re-ingest.
    if not who["position"] and r["position"]:
        who["position"] = str(r["position"])
    # …and a full name always beats an abbreviation for the row's label.
    if _is_abbreviated(who["player"]) and not _is_abbreviated(name):
        who["player"] = name
    market = str(r["market"])
    games = int(r["games"] or 0)
    total = float(r["total"] or 0.0)
    rate = market in RATE_MARKETS
    who["stats"][market] = {
        "market": market,
        # A RATE HAS NO TOTAL. See RATE_MARKETS: seven games of snap
        # share do not add up to anything, and printing "0.3 total"
        # beside a number that means 4% of snaps is worse than printing
        # nothing at all.
        "total": None if rate else round(total, 1),
        "rate": rate,
        "per_game": round(total / max(1, games), 3 if rate else 1),
        "games": games}


def squad(conn, sport: str, team: str, season: int | None = None,
          per_position: int = SQUAD_PER_POSITION) -> dict:
    """Who plays for this team, by position, and what they have done.

    Ethan, 2026-09-10, looking at the Rams page: "We should be showing
    more info too when you look up a team on the search page. We should
    show a depth chart and player stats and all that shit."

    THIS IS A DEPTH CHART MEASURED RATHER THAN PUBLISHED, and the
    difference is worth stating because it cuts both ways. nflverse
    publishes a real one — `engine/sources/depthcharts` reads it — and it
    is what a coach filed, which is the right answer to "who is listed
    first" and is NFL-only. This orders each position by what the players
    actually did: games first, then the position's leading market. It
    covers every league this repo ingests, it cannot go stale against a
    depth chart nobody refiled, and it answers the question a bettor is
    really asking — who gets the ball. What it cannot do is call a Week 1
    starter who has not played yet, and the row count says so.

    Everything comes out of `player_game_logs`, the same table the props
    grade against, so a name here is a name the rest of the site can
    price. No feed is called and no roster file is read: a player who has
    not taken a snap for this team is not on this list, which is honest
    rather than complete.
    """
    from .fantasy import _fold, _short_key
    season = season if season is not None else _latest_season(conn, sport, team)
    if season is None:
        return {"season": None, "positions": [], "players": 0}
    rows = conn.execute(
        "SELECT player, position, market, COUNT(*) n, SUM(value) total, "
        "COUNT(DISTINCT game_id) games FROM player_game_logs "
        "WHERE sport=? AND team=? AND season=? AND player<>'' "
        "GROUP BY player, position, market", (sport, team, season)).fetchall()
    # ONE PLAYER, ONE ROW. `player_game_logs` holds two NFL feeds under
    # one schema and they do not spell a name the same way: the weekly
    # box score writes "Kyren Williams" with a position,
    # `sources.nflpbp.xfp_player_rows` writes "K.Williams" with an EMPTY
    # one and says so in its own docstring. Grouped on the raw string,
    # every skill player came out twice — once under his position and
    # once in a nameless bucket at the bottom of the page. Ethan's Rams
    # screenshot, 2026-09-10: a "— 14 listed" group holding K.Williams,
    # B.Corum, P.Nacua, D.Adams, C.Parkinson and D.Allen, every one of
    # them already listed above under RB, WR or TE.
    #
    # THE FOLD RUNS ONE WAY ONLY, and that is the whole care in it. An
    # abbreviated row cannot name a person — "D.Moore" is Devin or
    # Dennis and the row does not know — so it JOINS a full name rather
    # than merging with one. Two full names that differ stay two people
    # however alike their initials are; `fantasy._short_key` is
    # deliberately loose (2025 logged two ('d','moore') and two
    # ('m','evans')) and loose is right for a lookup and wrong for an
    # identity.
    #
    # An abbreviation that matches no full name, or matches two, is left
    # as its own row rather than guessed at — the same refusal
    # `sources.livescores.ingest_finals` makes about an ambiguous
    # fixture. Nothing is dropped, which is what a college feed with no
    # roster position needs.
    by_player: dict = {}
    short_rows: list = []
    for r in rows:
        name = str(r["player"])
        if _is_abbreviated(name):
            short_rows.append(r)
            continue
        key = (_short_key(name, team), _fold(name))
        who = by_player.setdefault(
            key, {"player": name, "position": str(r["position"] or ""),
                  "games": 0, "stats": {}})
        _absorb(who, r)
    # …then the abbreviations, each onto its one full name or onto
    # nobody. Built after the full names so the answer cannot depend on
    # ingest order.
    full_by_key: dict = {}
    for (short, _full), who in by_player.items():
        full_by_key.setdefault(short, []).append(who)
    for r in short_rows:
        name = str(r["player"])
        hits = full_by_key.get(_short_key(name, team)) or []
        who = hits[0] if len(hits) == 1 else by_player.setdefault(
            (_short_key(name, team), _fold(name)),
            {"player": name, "position": str(r["position"] or ""),
             "games": 0, "stats": {}})
        _absorb(who, r)

    groups: dict = {}
    for who in by_player.values():
        lead = LEAD_MARKET.get(who["position"])
        stats = who["stats"]
        if lead not in stats:
            # The player's own biggest number, which is what a reader
            # reads him by when the table has never seen his position.
            # COUNTS ONLY: a rate has no size to be biggest, and a snap
            # share is not what anyone reads a tight end by. A man who
            # has nothing else still leads on it — that is all he has.
            counts = [m for m in stats if not stats[m]["rate"]]
            lead = (max(counts, key=lambda m: stats[m]["total"]) if counts
                    else (max(stats) if stats else ""))
        who["lead_market"] = lead
        who["stats"] = sorted(stats.values(),
                              key=lambda st: (st["market"] != lead,
                                              st["rate"], -(st["total"] or 0.0)))
        groups.setdefault(who["position"], []).append(who)
    out = []
    for pos, players in groups.items():
        players.sort(key=lambda w: (-w["games"],
                                    -((w["stats"][0]["total"] or 0.0)
                                      if w["stats"] else 0.0),
                                    w["player"]))
        out.append({"position": pos or "—",
                    "players": players[:max(1, per_position)],
                    "listed": len(players)})
    out.sort(key=lambda g: (_POSITION_ORDER.get(g["position"], 99),
                            g["position"]))
    return {"season": season, "positions": out, "players": len(by_player)}


def _position_order() -> dict:
    """The roster page's own ordering, borrowed rather than restated.

    `engine/rosters` already decides that a quarterback comes before a
    linebacker and a starting pitcher before a catcher; two tables would
    drift and the drift would show as two pages listing one squad in two
    orders. Imported through a function so a change there cannot break
    an import here.
    """
    try:
        from .rosters import MLB_POSITION_ORDER, POSITION_ORDER
    except Exception:                                       # noqa: BLE001
        return {}
    out = dict(POSITION_ORDER)
    for pos, at in MLB_POSITION_ORDER.items():
        out.setdefault(pos, 100 + at)
    return out


_POSITION_ORDER = _position_order()
