"""Pass or run: how often each NFL team throws, how much more or less often offenses throw against each defense,
and our read of how often each team throws in a game (step AIQ, 27 November 2026). The game report says it and a
finished game checks it.

Ethan, 27 November: "with most likely picks and game report picks ... we need to make sure we are judging and
recording and playing off the % of times teams pass vs run bc that plays a factor in picks also go deeper on that
on who they run and pass More against and what style of defense".

THE RATE is the report's own (engine/sources/nflunits, the team_units table). Dropbacks (passes, sacks and
scrambles) are divided by dropbacks plus designed runs, so a team's pass rate here and its run rate in "How each
team plays" add to 100.

WHAT WAS MEASURED (nflverse play-by-play 2017–2025 and FTN's charting 2022–2025). Each test walks forward inside
a season and holds out one season at a time. Every switch here meets the adoption rule: better in every season
2022–2025, and not contradicted in three or more of 2017–2021.

  * A DEFENSE'S LEAN is how much more (or less) often its opponents threw against it than they did in their other
    games. It makes the read of how often a team throws closer from week 9 on, in every season 2022–2025: the
    squared error is 3.3%, 2.8%, 2.6% and 2.2% lower than the team's own rate and the line alone. It is also
    closer in three of the five older seasons. About 0.41 of a defense's lean carried into its next game (LEAN).
    Weeks 4 to 8 fail the rule, because three older seasons disagree, so the read starts at week 9 (FROM_WEEK).
  * A DEFENSE'S STYLE (its blitz rate, how often it puts 8 or more in the box against the run, or 6 or fewer)
    added nothing beyond the lean. It was better in two of the four seasons and worse in the others.
  * A TEAM'S OWN SPLIT AGAINST A STYLE (throwing more against blitzing defenses than against the rest, in its
    earlier games) did not carry to its next game, in any of the three styles tested.
  * NOT IN THE PLAYERS' NUMBERS. A player's volume and yards already read what each defense allows to the
    position (engine/defensevs). The lean, added on top of that, passed the rule in none of eleven markets
    (passing attempts and yards, completions, carries, rushing yards, and targets, catches and receiving yards by
    position): receivers' targets and catches came out a little better in 2022–2025 and worse in four or five of
    the older seasons, and the rest were mixed or worse. So nothing here moves a pick's number: the read is said,
    and graded, on its own.

Standard library only; `tables` returns {} on what it cannot read and never raises.
"""
from __future__ import annotations

#: The read, fit on 2022–2025, weeks 9 to 18, with each rate measured against the league's rate so far that
#: season (so a league that throws less this year moves every read with it):
#:     read = league + C0 + OWN × (own − league) + LEAN × the defense's lean + MARGIN × the line's margin
#: C0 is the late season's drift: games after week 8 run a little more than the weeks before them said.
C0, OWN, LEAN, MARGIN = -0.0073, 0.6212, 0.4133, -0.0007
#: The read is said from this week on (weeks 4 to 8 failed the rule).
FROM_WEEK = 9
#: A team's rate, and a defense's lean, need this many games.
MIN_GAMES = 3
#: A read this far from the team's own rate is said as more (or less) than usual, and graded on that side.
#: Nearer, it is "about its usual" and a finished game only says what happened.
SAID_GAP = 0.02
#: How the read did, held out one season at a time, from week 9 on (engine/passrun's measurement).
MEASURED = {
    "seasons": "2022–2025",
    "lean_gain": (3.3, 2.8, 2.6, 2.2),
    "older_agree": (3, 5),
    # Reads 2 points or more off the team's own rate, and how often the game landed on that side (held out).
    "side_share": (0.58, 0.66),
    "side_pooled": (589, 1196, 0.63),
    # The average miss, in points of pass rate: the read and the team's own rate alone (2022–2025, week 9 on).
    "miss": (7.9, 8.2),
}


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _rank(values: dict) -> dict:
    """{team: rank} with 1 the highest value; a tie shares its rank."""
    have = sorted(((t, v) for t, v in values.items() if v is not None), key=lambda tv: -tv[1])
    out, rank, prev = {}, 0, None
    for i, (t, v) in enumerate(have):
        if prev is None or round(v, 6) != prev:
            rank, prev = i + 1, round(v, 6)
        out[t] = rank
    return out


def tables(conn, season: int, before_week: int) -> dict:
    """This season's pass and run before ``before_week``, off team_units' offense rows:

        {"league": rate, "week": before_week, "teams": {team: {
            "rate", "games", "rank", "of",                     its own pass rate, ranked (1 = throws the most)
            "lean", "lean_games", "lean_rank", "lean_of",       its DEFENSE's lean (1 = most toward the pass)
            "weeks": [{"week", "opp", "rate", "for", "against"}, ...] }}}

    {} when there is no connection, no table or nothing played."""
    if conn is None or not season or not before_week:
        return {}
    try:
        rows = conn.execute("SELECT period, team, opp, dropbacks, rushes FROM team_units WHERE sport='nfl' "
                            "AND season=? AND side='off' AND CAST(period AS INTEGER) < ?",
                            (int(season), int(before_week))).fetchall()
    except Exception:                                        # noqa: BLE001
        return {}
    games: dict = {}
    for period, team, opp, db, ru in rows:
        try:
            wk = int(period)
        except (TypeError, ValueError):
            continue
        db, ru = int(_f(db) or 0), int(_f(ru) or 0)
        if not team or not opp or db + ru <= 0:
            continue
        games.setdefault(team, {})[wk] = (str(opp), db, ru)
    if not games:
        return {}
    scores: dict = {}
    try:
        for period, home, away, hs, as_ in conn.execute(
                "SELECT period, home, away, home_score, away_score FROM games WHERE sport='nfl' AND season=? "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL AND CAST(period AS INTEGER) < ?",
                (int(season), int(before_week))):
            try:
                wk = int(period)
            except (TypeError, ValueError):
                continue
            scores[(home, wk)] = (hs, as_)
            scores[(away, wk)] = (as_, hs)
    except Exception:                                        # noqa: BLE001
        scores = {}

    def own(team: str, skip: int | None = None):
        mine = [(db, db + ru) for wk, (_o, db, ru) in (games.get(team) or {}).items() if wk != skip]
        if len(mine) < MIN_GAMES:
            return None
        plays = sum(p for _d, p in mine)
        return sum(d for d, _p in mine) / plays if plays else None

    league_db = sum(db for wks in games.values() for (_o, db, _r) in wks.values())
    league_plays = sum(db + ru for wks in games.values() for (_o, db, ru) in wks.values())
    league = league_db / league_plays if league_plays else None
    # Each defense's lean: the offenses it faced, each game's rate against that offense's own in its other games.
    faced: dict = {}
    for off, wks in games.items():
        for wk, (dfn, db, ru) in wks.items():
            base = own(off, skip=wk)
            if base is not None:
                faced.setdefault(dfn, []).append(db / (db + ru) - base)
    rate = {t: own(t) for t in games}
    lean = {t: (sum(v) / len(v) if len(v) >= MIN_GAMES else None) for t, v in faced.items()}
    rate_rank, lean_rank = _rank(rate), _rank(lean)
    out = {}
    for t in sorted(set(games) | set(faced)):
        wks = games.get(t) or {}
        out[t] = {"rate": None if rate.get(t) is None else round(rate[t], 4), "games": len(wks),
                  "rank": rate_rank.get(t), "of": len(rate_rank),
                  "lean": None if lean.get(t) is None else round(lean[t], 4), "lean_games": len(faced.get(t) or []),
                  "lean_rank": lean_rank.get(t), "lean_of": len(lean_rank),
                  "weeks": [{"week": wk, "opp": o, "rate": round(db / (db + ru), 4),
                             **({"for": scores[(t, wk)][0], "against": scores[(t, wk)][1]}
                                if (t, wk) in scores else {})}
                            for wk, (o, db, ru) in sorted(wks.items())]}
    return {"league": None if league is None else round(league, 4), "week": int(before_week), "teams": out}


def read(tab: dict, team: str, opp: str, margin=None) -> dict | None:
    """Our read of how often ``team`` throws against ``opp``: {"expect", "own", "lean", "said"}, ``said`` being
    "more", "less" or "usual" (SAID_GAP). None before FROM_WEEK, or without the team's rate, the opponent's lean
    or the league's rate. ``margin`` is the points the lines expect the team to win by (negative: to lose by)."""
    teams = (tab or {}).get("teams") or {}
    league, week = _f((tab or {}).get("league")), int(_f((tab or {}).get("week")) or 0)
    me, them = teams.get(team) or {}, teams.get(opp) or {}
    own, lean = _f(me.get("rate")), _f(them.get("lean"))
    if week < FROM_WEEK or league is None or own is None or lean is None:
        return None
    m = _f(margin) or 0.0
    expect = league + C0 + OWN * (own - league) + LEAN * lean + MARGIN * m
    expect = min(0.95, max(0.05, expect))
    gap = expect - own
    said = "more" if gap >= SAID_GAP else "less" if gap <= -SAID_GAP else "usual"
    return {"expect": round(expect, 4), "own": round(own, 4), "lean": round(lean, 4), "said": said}


def claim(season, week, team: str, r: dict) -> dict | None:
    """What a finished game grades the read by (engine/reportfacts.passrun_check)."""
    if not r or not team:
        return None
    return {"kind": "passrun", "season": int(season), "week": int(week), "team": team,
            "expect": r["expect"], "own": r["own"], "said": r["said"]}


def actual(conn, season, week, team: str):
    """(dropbacks, plays) the team ran in that week's game, off team_units; None until the play-by-play is in."""
    if conn is None:
        return None
    try:
        # The week as a number: team_units files it zero-padded ("012", engine/sources/nflunits).
        row = conn.execute("SELECT dropbacks, rushes FROM team_units WHERE sport='nfl' AND season=? "
                           "AND CAST(period AS INTEGER)=? AND team=? AND side='off'",
                           (int(season), int(week), team)).fetchone()
    except Exception:                                        # noqa: BLE001
        return None
    if not row:
        return None
    db, ru = int(_f(row[0]) or 0), int(_f(row[1]) or 0)
    return (db, db + ru) if db + ru > 0 else None
