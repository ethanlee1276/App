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
    games. From week 9 on it makes the read of how often a team throws closer in every season 2022–2025, and in
    three of the five older seasons. Before week 9 it fails the rule (three older seasons disagree).
  * A TEAM'S PASS RATE OVER EXPECTED (the play-by-play's own: how much more it throws than the down, distance and
    score call for) is its tendency with the game script taken out; its overall rate carries the script (a team
    that trails throws more). Added to its rate, the line and the lean, it made the read closer again from week 9
    (step AIS, 28 November 2026), and from week 4 the rate, the line and it alone pass the rule where the lean did
    not: the read now starts at week 4 (FROM_WEEK). Against the team's own rate and the line alone, the read's
    squared error is 4.5%, 8.9%, 7.4% and 6.1% lower in weeks 4 to 8 of 2022–2025, and 4.9%, 3.9%, 5.8% and 2.0%
    lower from week 9 (two older seasons disagree in each), the pass rate over expected taken against the
    league's so far. A team's pass rate on early downs in a close game
    (downs 1 and 2, quarters 1 to 3, a win chance of 20% to 80%) does the same work: either passes, and neither
    adds on top of the other, so the read takes the one the box already keeps (team_weeks.proe).
  * A DEFENSE'S STYLE (its blitz rate, how often it puts 8 or more in the box against the run, or 6 or fewer)
    added nothing beyond the lean, and nor did its quality split (the EPA it allows a dropback against a run).
  * A TEAM'S OWN SPLIT AGAINST A STYLE (throwing more against blitzing defenses than against the rest, in its
    earlier games) did not carry to its next game, in any of the three styles tested. Nor did its red-zone pass
    rate beyond its overall rate, nor its share of touchdowns thrown; the defense's lean shows in the red zone too.
  * THE PLAYERS' NUMBERS. The lean alone, on top of a player's form and what each defense allows the position,
    passed the rule in none of eleven markets. The full read (the team's rate coming back toward the league's,
    its pass rate over expected, the lean and the line, as a change from the team's own rate) does, on top of the
    player's form, what the defense allows the position and the line: completions, wide receivers', tight ends'
    and backs' targets, and wide receivers' catches; not yards, not carries, and passing attempts by a hair (one
    season of four a shade worse). No single
    part passes on its own. A team-tendency layer priced against the league made the live model worse
    (engine/teamcontext: the player's own games already carry the team's level), so this one is priced as a change
    and waits switched off (engine/teamcontext "read" mode) until the box's backtest over real props says it helps.

Standard library only; `tables` returns {} on what it cannot read and never raises.
"""
from __future__ import annotations

#: THE READ (step AIS), fit on 2022–2025, each rate measured against the league's rate so far that season (so a
#: league that throws less this year moves every read with it):
#:     read = league + C0 + OWN × (own − league) + PROE × pass rate over expected [+ LEAN × the defense's lean]
#:            + MARGIN × the line's margin
#: EARLY is weeks 4 to 8 (no lean: it failed the rule there), LATE week 9 on. Early, the season's few games make the
#: overall rate mostly game script, and the pass rate over expected carries the tendency (OWN comes out near zero).
#: The pass rate over expected enters against the league's so far, as the rates do: the league's own swung from
#: -2.7% (2024) to +0.4% (2018) by week 12, and measured that way the read was closer again.
EARLY = {"c0": -0.0048, "own": -0.1863, "proe": 0.7610, "margin": -0.0033}
LATE = {"c0": -0.0073, "own": 0.2286, "lean": 0.3217, "proe": 0.5165, "margin": -0.0021}
#: The step AIQ read (no pass rate over expected), weeks 9 on, for a team whose pass rate over expected the box has
#: not filed.
C0, OWN, LEAN, MARGIN = -0.0073, 0.6212, 0.4133, -0.0007
#: The read is said from this week on (weeks 1 to 3 have too few games for a rate).
FROM_WEEK = 4
#: The defense's lean joins from this week (before it, it failed the rule).
LEAN_FROM = 9
#: A team's rate, and a defense's lean, need this many games.
MIN_GAMES = 3
#: A read this far from the team's own rate is said as more (or less) than usual, and graded on that side.
#: Nearer, it is "about its usual" and a finished game only says what happened.
SAID_GAP = 0.02
#: How the read did, held out one season at a time (the measurement above).
MEASURED = {
    "seasons": "2022–2025",
    "older_agree": (3, 5),
    # Reads 2 points or more off the team's own rate, and how often the game landed on that side (held out,
    # 2022–2025): weeks 4 to 8, and week 9 on.
    "side_early": (0.59, 0.79),
    "side_late": (0.62, 0.68),
    # How much closer than the team's own rate and the line (squared error, held out, 2022–2025).
    "gain_early": (4.5, 8.9, 7.4, 6.1),
    "gain_late": (4.9, 3.9, 5.8, 2.0),
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
            "proe",                                             its pass rate over expected (team_weeks)
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

    # PASS RATE OVER EXPECTED (step AIS): team_weeks' proe, pooled by each week's plays, as season_numbers pools it.
    proe: dict = {}
    try:
        acc: dict = {}
        for team, plays, oe in conn.execute(
                "SELECT team, plays, proe FROM team_weeks WHERE sport='nfl' AND season=? AND proe IS NOT NULL "
                "AND CAST(period AS INTEGER) < ?", (int(season), int(before_week))):
            n = _f(plays) or 0.0
            if team and n > 0 and _f(oe) is not None:
                a = acc.setdefault(team, [0.0, 0.0, 0])
                a[0] += _f(oe) * n
                a[1] += n
                a[2] += 1
        proe = {t: a[0] / a[1] for t, a in acc.items() if a[1] and a[2] >= MIN_GAMES}
        lg_n = sum(a[1] for a in acc.values())
        league_proe = sum(a[0] for a in acc.values()) / lg_n if lg_n else None
    except Exception:                                        # noqa: BLE001
        proe, league_proe = {}, None

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
                  "proe": None if proe.get(t) is None else round(proe[t], 4),
                  "lean": None if lean.get(t) is None else round(lean[t], 4), "lean_games": len(faced.get(t) or []),
                  "lean_rank": lean_rank.get(t), "lean_of": len(lean_rank),
                  "weeks": [{"week": wk, "opp": o, "rate": round(db / (db + ru), 4),
                             **({"for": scores[(t, wk)][0], "against": scores[(t, wk)][1]}
                                if (t, wk) in scores else {})}
                            for wk, (o, db, ru) in sorted(wks.items())]}
    return {"league": None if league is None else round(league, 4), "week": int(before_week), "teams": out,
            "league_proe": None if league_proe is None else round(league_proe, 4)}


def read(tab: dict, team: str, opp: str, margin=None) -> dict | None:
    """Our read of how often ``team`` throws against ``opp``: {"expect", "own", "lean", "proe", "said", "model"},
    ``said`` being "more", "less" or "usual" (SAID_GAP) and ``model`` "early" (weeks 4 to 8: the team's rate, its
    pass rate over expected and the line), "late" (week 9 on: and the defense's lean) or "lean" (week 9 on, for a
    team the box has no pass rate over expected for: the step AIQ read). None before FROM_WEEK, or without what
    its model needs. ``margin`` is the points the lines expect the team to win by (negative: to lose by)."""
    teams = (tab or {}).get("teams") or {}
    league, week = _f((tab or {}).get("league")), int(_f((tab or {}).get("week")) or 0)
    me, them = teams.get(team) or {}, teams.get(opp) or {}
    own, lean, proe = _f(me.get("rate")), _f(them.get("lean")), _f(me.get("proe"))
    lg_proe = _f((tab or {}).get("league_proe"))
    if week < FROM_WEEK or league is None or own is None:
        return None
    m = _f(margin) or 0.0
    rel = None if proe is None or lg_proe is None else proe - lg_proe
    if week >= LEAN_FROM and lean is not None and rel is not None:
        k, model = LATE, "late"
        expect = league + k["c0"] + k["own"] * (own - league) + k["proe"] * rel + k["lean"] * lean + k["margin"] * m
    elif week < LEAN_FROM and rel is not None:
        k, model = EARLY, "early"
        expect = league + k["c0"] + k["own"] * (own - league) + k["proe"] * rel + k["margin"] * m
    elif week >= LEAN_FROM and lean is not None:
        model = "lean"
        expect = league + C0 + OWN * (own - league) + LEAN * lean + MARGIN * m
    else:
        return None
    expect = min(0.95, max(0.05, expect))
    gap = expect - own
    said = "more" if gap >= SAID_GAP else "less" if gap <= -SAID_GAP else "usual"
    return {"expect": round(expect, 4), "own": round(own, 4),
            "lean": None if lean is None or model == "early" else round(lean, 4),
            "proe": None if proe is None or model == "lean" else round(proe, 4),
            "proe_rel": None if rel is None or model == "lean" else round(rel, 4), "said": said, "model": model}


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
