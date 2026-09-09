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
