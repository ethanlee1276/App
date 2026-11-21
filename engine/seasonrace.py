"""The NBA's and the NHL's playoff races, off the season simulation.

Ethan, 2026-11-17, yes to "NHL and NBA playoff race pages? The season
simulation already computes every team's playoff chances, so they can get
brackets like the NFL's: seeds free, chances for members."

ONE SIMULATION, TWO PAGES. The chances here are the Futures page's own run
(`futuresdata.project` → `futures.simulate`), not a second one, so the race
and the Futures page cannot disagree about a club and the race costs the
build nothing. That run plays each league's own format: the NBA's play-in
and its fixed 1 v 8 / 4 v 5 bracket, the NHL's division bracket with two
wild cards a conference (`futures.SHAPES`).

THE FIELD IF IT ENDED TODAY is a fact off the results we have counted
(`standings.compute`, the same table the simulation banks), ordered by the
league's first tiebreakers and then our rating, and the page says so:

  * the NBA: win percentage, then head-to-head among the tied clubs,
    conference record and point differential;
  * the NHL: points, then points percentage, regulation wins, wins and goal
    differential.

Free, as every race's "if it ended today" is. The chances are the model's
and members' (gate.PAID_KEYS_BY_FILE).

PURE BELOW `publish`: a standings table, its games and the simulation's
rows in, a payload out (tests/test_the_nba_and_nhl_playoff_races.py).
"""

from __future__ import annotations

import datetime as _dt

from .divisions import group_of

SPORTS = ("nba", "nhl")
FILES = {"nba": "nba_race.json", "nhl": "nhl_race.json"}
#: Clubs named just outside the field, each with how far back it is.
HUNT_SHOWN = 3
#: The NBA's seeds: straight in, then the play-in, then out.
NBA_DIRECT, NBA_PLAYIN_LAST = 6, 10
#: The NHL's places: three a division, then two wild cards a conference.
NHL_DIVISION_PLACES, NHL_WILD_CARDS = 3, 2

TIEBREAKERS = {
    "nba": ("win percentage, then head-to-head among the tied clubs, conference record and point "
            "differential, then our rating — the league's first steps, not all of them"),
    "nhl": ("points, then points percentage, regulation wins, wins and goal differential, then our "
            "rating — the league's first steps, not all of them"),
}


def _conference_of(sport: str, team: str) -> str:
    return group_of(sport, team)[0]


def _pct(w: int, n: int) -> float:
    return w / n if n else 0.0


def _nba_order(rows: list[dict], games: list[dict], rating: dict) -> list[dict]:
    """One conference's clubs in seed order (see TIEBREAKERS["nba"])."""
    conf: dict[str, list[int]] = {}
    for g in games:
        h, a = g["home"], g["away"]
        if _conference_of("nba", h) != _conference_of("nba", a):
            continue
        hw = g["home_score"] > g["away_score"]
        for team, won in ((h, hw), (a, not hw)):
            rec = conf.setdefault(team, [0, 0])
            rec[0 if won else 1] += 1

    def conf_pct(t):
        w, l = conf.get(t, (0, 0))
        return _pct(w, w + l)

    by_pct: dict[float, list[dict]] = {}
    for r in rows:
        by_pct.setdefault(round(float(r.get("pct") or 0.0), 6), []).append(r)
    out: list[dict] = []
    for pct in sorted(by_pct, reverse=True):
        tied = by_pct[pct]
        if len(tied) > 1:
            names = {r["team"] for r in tied}
            h2h = {t: [0, 0] for t in names}
            for g in games:
                if g["home"] in names and g["away"] in names:
                    w, l = ((g["home"], g["away"]) if g["home_score"] > g["away_score"]
                            else (g["away"], g["home"]))
                    h2h[w][0] += 1
                    h2h[l][1] += 1

            def h2h_pct(t):                 # no meeting yet: level, not behind
                w, l = h2h[t]
                return _pct(w, w + l) if w + l else 0.5
            tied = sorted(tied, key=lambda r: (
                -h2h_pct(r["team"]), -conf_pct(r["team"]), -float(r.get("diff") or 0.0),
                -float(rating.get(r["team"], 0.0)), r["team"]))
        out += tied
    return out


def _nhl_key(rating: dict):
    def key(r):
        gp = int(r.get("games") or 0)
        pts = int(r.get("points") or 0)
        return (-pts, -_pct(pts, 2 * gp), -int(r.get("reg_wins") or 0), -int(r.get("wins") or 0),
                -float(r.get("diff") or 0.0), -float(rating.get(r["team"], 0.0)), r["team"])
    return key


def _side(r: dict, sport: str, why: str, seed=None) -> dict:
    out = {"team": r["team"], "record": r.get("record") or "", "why": why}
    if seed is not None:
        out["seed"] = seed
    if sport == "nhl":
        out["points"] = int(r.get("points") or 0)
        out["games"] = int(r.get("games") or 0)
    return out


def nba_today(rows: list[dict], games: list[dict], rating: dict) -> dict:
    """{conference: seeds 1-10 with why each is in, the play-in's games, the
    first round, and the clubs just outside with games back of the 10th}."""
    out = {}
    for conf in sorted({_conference_of("nba", r["team"]) for r in rows}):
        order = _nba_order([r for r in rows if _conference_of("nba", r["team"]) == conf], games, rating)
        seeds = [_side(r, "nba", "In" if i <= NBA_DIRECT else "Play-in", i)
                 for i, r in enumerate(order[:NBA_PLAYIN_LAST], 1)]
        tenth = order[NBA_PLAYIN_LAST - 1] if len(order) >= NBA_PLAYIN_LAST else None

        def back(r):
            if tenth is None:
                return None
            return round(((int(tenth.get("wins") or 0) - int(r.get("wins") or 0))
                          + (int(r.get("losses") or 0) - int(tenth.get("losses") or 0))) / 2.0, 1)
        out[conf] = {
            "seeds": seeds,
            "hunt": [{"team": r["team"], "record": r.get("record") or "", "back": back(r)}
                     for r in order[NBA_PLAYIN_LAST:NBA_PLAYIN_LAST + HUNT_SHOWN]],
        }
    return out


def nhl_today(rows: list[dict], rating: dict) -> dict:
    """{conference: each division's top three, the two wild cards, the first
    round as the league draws it, and the clubs just outside with points
    back of the second wild card}."""
    key = _nhl_key(rating)
    out = {}
    for conf in sorted({_conference_of("nhl", r["team"]) for r in rows}):
        mine = [r for r in rows if _conference_of("nhl", r["team"]) == conf]
        divs: dict[str, list[dict]] = {}
        for r in mine:
            divs.setdefault(group_of("nhl", r["team"])[1], []).append(r)
        tops = {d: sorted(v, key=key)[:NHL_DIVISION_PLACES] for d, v in sorted(divs.items())}
        taken = {r["team"] for v in tops.values() for r in v}
        rest = sorted((r for r in mine if r["team"] not in taken), key=key)
        wild, outside = rest[:NHL_WILD_CARDS], rest[NHL_WILD_CARDS:]
        entry = {
            "divisions": {d: [_side(r, "nhl", f"{d} {i}", i) for i, r in enumerate(v, 1)]
                          for d, v in tops.items()},
            "wild_cards": [_side(r, "nhl", f"Wild card {i}", i) for i, r in enumerate(wild, 1)],
            "first_round": [],
            "hunt": [],
        }
        full = (len(tops) == 2 and all(len(v) == NHL_DIVISION_PLACES for v in tops.values())
                and len(wild) == NHL_WILD_CARDS)
        if full:
            # The division winner with the better record draws the lower
            # wild card; the other winner the first; 2 v 3 in each.
            (d1, a), (d2, b) = sorted(tops.items(), key=lambda kv: key(kv[1][0]))
            entry["first_round"] = [
                {"division": d1, "games": [[a[0]["team"], wild[1]["team"]], [a[1]["team"], a[2]["team"]]]},
                {"division": d2, "games": [[b[0]["team"], wild[0]["team"]], [b[1]["team"], b[2]["team"]]]},
            ]
        last = wild[-1] if len(wild) == NHL_WILD_CARDS else None
        entry["hunt"] = [{"team": r["team"], "record": r.get("record") or "",
                          "points": int(r.get("points") or 0),
                          "back": (int(last.get("points") or 0) - int(r.get("points") or 0)) if last else None,
                          "in_hand": (int(last.get("games") or 0) - int(r.get("games") or 0)) if last else None}
                         for r in outside[:HUNT_SHOWN]]
        out[conf] = entry
    return out


def _chances(sport: str, sim_rows: list[dict]) -> dict:
    """{team: the simulation's chances and its projected finish}."""
    out = {}
    for t in sim_rows:
        if not isinstance(t, dict) or not t.get("team"):
            continue
        row = {"playoffs": t.get("p_playoffs"), "division": t.get("p_division"),
               "conference": t.get("p_conference"), "title": t.get("p_title")}
        if sport == "nba":
            row["playin"] = t.get("p_playin")
            row["proj"] = [t.get("proj_wins_lo"), t.get("proj_wins_hi")]
            row["mean"] = t.get("proj_wins")
        else:
            row["proj"] = [t.get("proj_points_lo"), t.get("proj_points_hi")]
            row["mean"] = t.get("proj_points")
        out[t["team"]] = {k: v for k, v in row.items() if v is not None}
    return out


def build(sport: str, table: dict, games: list[dict], sim: dict, today: str) -> dict:
    """The race page's payload: the field if it ended today, the standings,
    and the simulation's chances."""
    from .standings import team_rows
    rows = [r for r in team_rows(table) if r.get("team")]
    sim_rows = [t for t in sim.get("teams") or [] if isinstance(t, dict)]
    rating = {t["team"]: float(t.get("rating") or 0.0) for t in sim_rows if t.get("team")}
    if sport == "nba":
        field = nba_today(rows, games, rating)
        fmt = {"direct": NBA_DIRECT, "play_in": [7, 10], "first_round": [[1, 8], [4, 5], [3, 6], [2, 7]]}
    else:
        field = nhl_today(rows, rating)
        fmt = {"division_places": NHL_DIVISION_PLACES, "wild_cards": NHL_WILD_CARDS}
    def slim(r):
        return {k: r.get(k) for k in ("team", "record", "games", "points", "pct", "diff",
                                      "reg_wins", "streak_label", "last10_label") if r.get(k) is not None}
    # THE TABLE THAT DECIDES THE SEEDS: the NBA's is the conference (its
    # divisions seed nothing), in seed order; the NHL's is the division.
    standings = {}
    if sport == "nba":
        for conf in sorted({_conference_of("nba", r["team"]) for r in rows}):
            order = _nba_order([r for r in rows if _conference_of("nba", r["team"]) == conf], games, rating)
            standings[conf] = [{**slim(r), "seed": i} for i, r in enumerate(order, 1)]
    else:
        for g in (table or {}).get("groups") or []:
            label = g.get("label") or f"{g.get('conference', '')} {g.get('division', '')}".strip()
            standings[label] = [slim(r) for r in sorted(g.get("teams") or [], key=_nhl_key(rating))]
    names = {r["team"]: r for r in rows}
    return {
        "sport": sport, "season": table.get("season") or sim.get("season"), "date": today,
        "sims": sim.get("trials"),
        "format": fmt,
        "today": field,
        "standings": standings,
        "teams": [{"team": t["team"], "conference": t.get("conference") or "",
                   "division": t.get("division") or "",
                   "record": (names.get(t["team"]) or {}).get("record") or ""}
                  for t in sim_rows],
        "games_played": sim.get("games_played"),
        "games_left": sim.get("fixtures_remaining"),
        "prior_share": sim.get("prior_share"),
        "tiebreakers": TIEBREAKERS[sport],
        "source": "counted from the games we have ingested",
        # THE MODEL'S HALF — members' (gate.PAID_KEYS_BY_FILE).
        "chances": _chances(sport, sim_rows),
    }


def publish(sport: str, sim: dict, conn, out_dir) -> str:
    """Build the race off this simulation and the table it banked, and
    write it through the gate. Returns the build-log line; a league with no
    game played yet is not built."""
    from pathlib import Path
    from . import gate, standings
    if sport not in SPORTS or not sim.get("teams"):
        return f"{sport.upper()} playoff race: no season simulation to read, not built"
    season = int(sim.get("season") or 0)
    table = standings.compute(conn, sport, season=season)
    games = standings.season_games(conn, sport, season)
    if not games:
        return f"{sport.upper()} playoff race: no games played yet, not built"
    out = build(sport, table, games, sim, _dt.date.today().isoformat())
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    path = Path(out_dir) / FILES[sport]
    gate.publish(out, path, path.name)
    return f"{sport.upper()} playoff race: {len(games)} games counted, {out['games_left'] or 0} left"
