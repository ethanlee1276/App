"""His role, game by game, in every league: the role chart (kind "role").

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list he
said yes to had a role trend chart for every sport on it: how much a
player is used, game by game, which is what every prop he is priced on
rides on.

NOTHING NEW TO FETCH. The box scores the boards already read
(`player_game_logs`) carry most of a role: an NFL player's snap share,
targets, carries, attempts, red-zone looks and air yards; a college
player's carries, catches, attempts and red-zone touches; a basketball
player's minutes and whether he started; a hitter's plate appearances and
a pitcher's outs; a skater's ice time and shots on goal, a goalie's starts
and shots faced. Where the play-by-play the other charts already store
adds what a box score lacks, it is read as well: a hitter's spot in the
order and the pitches he saw, a pitcher's pitch count, batters faced,
starts and rest (mlb_pa, mlb_pitches); an NBA player's shots, threes and
free throws tried (nba_shots); a skater's every attempt and his power-play
attempts (nhl_shots).

A SHARE IS OF HIS OWN TEAM THAT GAME: his targets over every target his
club's logged players drew in it, so a player traded mid-season takes his
denominator with him.

A NUMBER NOT ON FILE IS NOT A ZERO. A game with no snap count stored has
no snap share (None, a gap on the chart), never 0%; a hitter who came off
the bench has no spot in the order, and the game says he did not start.
"""

from __future__ import annotations

import datetime as _dt
import re

#: key -> (name, short name, unit): "pct" a share (0-1), "n" a count,
#: "min" minutes, "spot" a place in the batting order (1 leads off).
METRICS = {
    "snap": ("Snap share", "Snaps", "pct"),
    "att": ("Pass attempts", "Attempts", "n"),
    "tgt": ("Targets", "Targets", "n"),
    "tgt_sh": ("Target share", "Target share", "pct"),
    "car": ("Carries", "Carries", "n"),
    "car_sh": ("Carry share", "Carry share", "pct"),
    "rec": ("Catches", "Catches", "n"),
    "rec_sh": ("Share of the catches", "Catch share", "pct"),
    "rz": ("Red-zone looks", "Red zone", "n"),
    "air": ("Air yards", "Air yards", "n"),
    "min": ("Minutes", "Minutes", "min"),
    "fga": ("Shots from the floor", "FGA", "n"),
    "fg3a": ("Threes tried", "3PA", "n"),
    "fta": ("Free throws tried", "FTA", "n"),
    "pa": ("Plate appearances", "PA", "n"),
    "spot": ("Spot in the order", "Spot", "spot"),
    "seen": ("Pitches seen", "Seen", "n"),
    "pitches": ("Pitches thrown", "Pitches", "n"),
    "bf": ("Batters faced", "Batters", "n"),
    "outs": ("Outs recorded", "Outs", "n"),
    "rest": ("Days of rest", "Rest", "n"),
    "toi": ("Ice time", "Ice time", "min"),
    "sog": ("Shots on goal", "SOG", "n"),
    "sat": ("Shot attempts", "Attempts", "n"),
    "pp": ("Power-play attempts", "PP attempts", "n"),
    "sa": ("Shots faced", "Shots faced", "n"),
}
#: The same key meaning something else in a league: a college red-zone
#: touch is a carry or a catch inside the 20 (no college target is named).
NAMED = {("cfb", "rz"): ("Red-zone touches", "Red zone", "n")}

#: What each league's box score carries: (key, the stored markets summed
#: into it).
LOGGED = {
    "nfl": (("snap", ("snap_pct",)), ("att", ("pass_att",)), ("tgt", ("targets",)),
            ("car", ("carries",)), ("air", ("air_yards",))),
    "cfb": (("att", ("pass_att",)), ("car", ("carries",)), ("rec", ("receptions",)),
            ("rz", ("rz_car", "rz_rec"))),
    "nba": (("min", ("min",)),),
    "wnba": (("min", ("min",)),),
    "mlb": (("pa", ("pa",)), ("outs", ("outs",))),
    "nhl": (("toi", ("toi",)), ("sog", ("sog",)), ("sa", ("shots_against",))),
}
#: A market that says whether he started rather than how much he did.
STARTED = {"nhl": "started"}
#: A share of his own team's that game: (key, the count's key, its market).
SHARES = {"nfl": (("tgt_sh", "tgt", "targets"), ("car_sh", "car", "carries")),
          "cfb": (("car_sh", "car", "carries"), ("rec_sh", "rec", "receptions"))}
#: The order a league lists its numbers in (the ones he has).
ORDER = {
    "nfl": ("snap", "att", "tgt", "tgt_sh", "car", "car_sh", "rz", "air"),
    "cfb": ("att", "car", "car_sh", "rec", "rec_sh", "rz"),
    "nba": ("min", "fga", "fg3a", "fta"),
    "wnba": ("min",),
    "mlb": ("pa", "spot", "seen", "pitches", "bf", "outs", "rest"),
    "nhl": ("toi", "sog", "sat", "pp", "sa"),
}
#: A count is listed when he averages this many a game; his lead always is.
SHOW_AT = 0.5
#: A quarterback, read off the numbers: this many attempts a game.
PASSER_AT = 10.0
#: The stretches the chart sets beside his season.
STRETCHES = (3, 5)


def season_label(sport: str, season: int) -> str:
    if sport in ("nba", "nhl"):
        return f"{int(season)}-{(int(season) + 1) % 100:02d}"
    return str(int(season))


def metric(sport: str, key: str) -> dict:
    name, short, unit = NAMED.get((sport, key)) or METRICS[key]
    return {"key": key, "name": name, "short": short, "unit": unit}


def resolve(conn, sport: str, player: str) -> str:
    """The stored spelling of a player's name in the logs, or ""."""
    from .carries import _fold
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT player FROM player_game_logs WHERE sport=? AND player=? LIMIT 1",
                       (sport, q)).fetchone()
    if row:
        return row[0]
    want = _fold(q)
    if not want:
        return ""
    # Spelled out with or without its apostrophe or hyphen: "Ja'Marr" is
    # "jamarr" to anyone typing it.
    tight = want.replace(" ", "")
    hits = {p for (p,) in conn.execute("SELECT DISTINCT player FROM player_game_logs WHERE sport=?", (sport,))
            if _fold(p).replace(" ", "") == tight}
    return next(iter(hits)) if len(hits) == 1 else ""


def _marks(xs) -> str:
    return ",".join("?" * len(xs))


def _logged(conn, sport: str, name: str, season: int) -> list:
    """His games from the box scores, oldest first, one per game."""
    spec = LOGGED[sport]
    markets = sorted({m for _k, ms in spec for m in ms} | ({STARTED[sport]} if sport in STARTED else set()))
    rows = conn.execute(
        f"SELECT period, game_id, team, opponent, position, home, market, value FROM player_game_logs "
        f"WHERE sport=? AND player=? AND season=? AND market IN ({_marks(markets)}) ORDER BY period, game_id",
        (sport, name, season, *markets)).fetchall()
    games: dict = {}
    for period, gid, team, opp, pos, home, market, value in rows:
        leg = 1
        if sport == "mlb":
            m = re.search(r"-G(\d+)$", str(gid or ""))
            leg = int(m.group(1)) if m else 1
        g = games.setdefault((str(period), leg), {"period": str(period), "leg": leg, "team": team or "",
                                                  "opp": opp or "", "pos": pos or "",
                                                  "home": bool(home), "raw": {}})
        # Two feeds can file one game (a box score and the play file):
        # the first number kept stands.
        g["raw"].setdefault(market, None if value is None else float(value))
    out = []
    for (period, leg), g in sorted(games.items()):
        v = {}
        for key, ms in spec:
            got = [g["raw"][m] for m in ms if g["raw"].get(m) is not None]
            if got:
                v[key] = round(sum(got), 4)
        start = None
        if sport in ("nba", "wnba"):
            start = {"S": True, "B": False}.get(g["pos"].upper())
        elif sport in STARTED and g["raw"].get(STARTED[sport]) is not None:
            start = bool(g["raw"][STARTED[sport]])
        out.append({"id": period + (f"-G{leg}" if leg > 1 else ""), "period": period, "leg": leg,
                    "date": period if sport != "nfl" else "", "team": g["team"], "opp": g["opp"],
                    "home": g["home"], "start": start, "pos": g["pos"], "v": v})
    return out


def _shares(conn, sport: str, season: int, games: list) -> None:
    """His share of his team's targets, carries or catches that game."""
    want = SHARES[sport]
    teams = sorted({g["team"] for g in games if g["team"]})
    periods = sorted({g["period"] for g in games})
    if not teams or not periods:
        return
    markets = [m for _sh, _k, m in want]
    tot = {(p, t, m): v for p, t, m, v in conn.execute(
        f"SELECT period, team, market, SUM(value) FROM player_game_logs WHERE sport=? AND season=? "
        f"AND market IN ({_marks(markets)}) AND period IN ({_marks(periods)}) AND team IN ({_marks(teams)}) "
        "GROUP BY period, team, market", (sport, season, *markets, *periods, *teams))}
    for g in games:
        for sh, key, market in want:
            mine, all_ = g["v"].get(key), tot.get((g["period"], g["team"], market))
            if mine is not None and all_:
                g["v"][sh] = round(mine / all_, 4)


def _nfl_games(conn, season: int, games: list) -> None:
    """An NFL row is keyed by its week: the schedule says home or away and
    the date (the log's own home flag is not kept for the NFL)."""
    teams = sorted({g["team"] for g in games if g["team"]})
    at: dict = {}
    if teams:
        for period, home, away, date in conn.execute(
                f"SELECT period, home, away, date FROM games WHERE sport='nfl' AND season=? "
                f"AND (home IN ({_marks(teams)}) OR away IN ({_marks(teams)}))", (season, *teams, *teams)):
            at[(str(period), home)] = (True, date or "")
            at[(str(period), away)] = (False, date or "")
    for g in games:
        hit = at.get((g["period"], g["team"]))
        g["home"] = hit[0] if hit else None
        g["date"] = hit[1] if hit else ""
        try:
            g["week"] = int(g["period"])
        except ValueError:
            g["week"] = None


def _nfl_red_zone(conn, name: str, season: int, games: list) -> None:
    """His targets and carries inside the 20. The play-by-play files them
    under its own short names ("J.Chase"), so they are joined the way the
    touchdown model joins them: first initial, surname and team
    (fantasy._short_key), which keeps A.J. Brown and Amon-Ra St. Brown
    apart."""
    from .fantasy import _short_key
    teams = sorted({g["team"] for g in games if g["team"]})
    periods = sorted({g["period"] for g in games})
    if not teams or not periods:
        return
    want = {_short_key(name, t) for t in teams}
    per: dict = {}
    for player, team, period, value in conn.execute(
            f"SELECT player, team, period, value FROM player_game_logs WHERE sport='nfl' AND season=? "
            f"AND market IN ('rz_tgt', 'rz_car') AND period IN ({_marks(periods)}) AND team IN ({_marks(teams)})",
            (season, *periods, *teams)):
        if _short_key(player, team) in want:
            per[(str(period), team)] = per.get((str(period), team), 0.0) + float(value or 0)
    for g in games:
        got = per.get((g["period"], g["team"]))
        if got is not None:
            g["v"]["rz"] = got


def _by_leg(per_pk: dict) -> dict:
    """{game_pk: row} → {(date, leg): row}: a doubleheader's games in the
    order the league numbered them."""
    days: dict = {}
    for pk, row in per_pk.items():
        days.setdefault(row["date"], []).append(pk)
    return {(d, i + 1): per_pk[pk] for d, pks in days.items() for i, pk in enumerate(sorted(pks))}


def _mlb(conn, name: str, season: int, games: list) -> None:
    """What the play-by-play adds: a hitter's spot in the order (the first
    nine of his side to bat, in the order they came up) and the pitches he
    saw; a pitcher's pitch count, batters faced, whether he started (he
    faced his opponents' first batter) and his rest."""
    from .mlb import charts as M
    try:
        bid, _b = M._resolve(conn, name, "batter")
        pid, _p = M._resolve(conn, name, "pitcher")
    except Exception:                                              # noqa: BLE001 — no play file, no extras
        return
    day = {(g["period"], g["leg"]): g for g in games}
    if bid is not None:
        mine: dict = {}
        for pk, date, team, n in conn.execute(
                "SELECT game_pk, date, team, pitches FROM mlb_pa WHERE batter_id=? AND season=? "
                "ORDER BY game_pk, at_bat", (bid, season)):
            m = mine.setdefault(pk, {"pk": pk, "date": date, "team": team, "seen": 0})
            m["seen"] += int(n or 0)
        if mine:
            nine: dict = {}
            for pk, b, team in conn.execute(
                    f"SELECT game_pk, batter_id, team FROM mlb_pa WHERE game_pk IN ({_marks(mine)}) "
                    "ORDER BY game_pk, at_bat", list(mine)):
                if team != mine[pk]["team"]:
                    continue
                lst = nine.setdefault(pk, [])
                if b not in lst and len(lst) < 9:
                    lst.append(b)
            for (date, leg), m in _by_leg(mine).items():
                g = day.get((date, leg))
                if g is None or "pa" not in g["v"]:
                    continue
                lst = nine.get(m["pk"], [])
                g["v"]["seen"] = float(m["seen"])
                g["start"] = bid in lst
                if bid in lst:
                    g["v"]["spot"] = float(lst.index(bid) + 1)
    if pid is not None:
        mine = {}
        for pk, date, ab in conn.execute(
                "SELECT game_pk, date, at_bat FROM mlb_pa WHERE pitcher_id=? AND season=?", (pid, season)):
            m = mine.setdefault(pk, {"pk": pk, "date": date, "bf": 0, "first": ab})
            m["bf"] += 1
            m["first"] = min(m["first"], ab)
        if mine:
            count = {pk: n for pk, n in conn.execute(
                "SELECT game_pk, COUNT(*) FROM mlb_pitches WHERE pitcher_id=? AND season=? GROUP BY game_pk",
                (pid, season))}
            # The first batter his opponents sent up, game by game: the
            # man who faced him started.
            lead = {}
            for pk, ab in conn.execute(
                    f"SELECT p.game_pk, MIN(p.at_bat) FROM mlb_pa p WHERE p.game_pk IN ({_marks(mine)}) "
                    "AND p.team IN (SELECT q.team FROM mlb_pa q WHERE q.game_pk=p.game_pk AND q.pitcher_id=?) "
                    "GROUP BY p.game_pk", (*mine, pid)):
                lead[pk] = ab
            # His rest counts every game he pitched in the play file, logged
            # or not: the day before is the day before.
            prev = None
            for (date, leg), m in sorted(_by_leg(mine).items()):
                g = day.get((date, leg))
                rest = None
                if prev:
                    try:
                        rest = (_dt.date.fromisoformat(date) - _dt.date.fromisoformat(prev)).days - 1
                    except ValueError:
                        rest = None
                prev = date
                if g is None:
                    continue
                g["v"]["bf"] = float(m["bf"])
                if count.get(m["pk"]):
                    g["v"]["pitches"] = float(count[m["pk"]])
                g["start"] = lead.get(m["pk"]) == m["first"]
                if rest is not None:
                    # Twice in a day (a doubleheader) is no rest at all.
                    g["v"]["rest"] = float(max(0, rest))


def _nba(conn, name: str, season: int, games: list) -> None:
    """His shots from the floor, threes and free throws tried, off the
    play-by-play the shot chart stores (the NBA only: no WNBA play file)."""
    from .nba import shots as N
    try:
        pid, _n = N.resolve(conn, name)
    except Exception:                                              # noqa: BLE001
        return
    if pid is None:
        return
    per: dict = {}
    for date, kind, n in conn.execute(
            "SELECT date, kind, COUNT(*) FROM nba_shots WHERE person_id=? AND season=? GROUP BY date, kind",
            (pid, season)):
        d = per.setdefault(date, {"fga": 0.0, "fg3a": 0.0, "fta": 0.0})
        if kind == "ft":
            d["fta"] += n
        else:
            d["fga"] += n
            if kind == "3pt":
                d["fg3a"] += n
    for g in games:
        if g["period"] in per and g["v"].get("min"):
            g["v"].update(per[g["period"]])


def _nhl(conn, name: str, season: int, games: list) -> None:
    """A skater's every shot attempt and those on the power play, off the
    shots the expected-goals model stores."""
    per: dict = {}
    try:
        for date, n, pp in conn.execute(
                "SELECT date, COUNT(*), SUM(CASE WHEN strength='PP' THEN 1 ELSE 0 END) FROM nhl_shots "
                "WHERE shooter=? AND season=? GROUP BY date", (name, season)):
            per[date] = (float(n), float(pp or 0))
    except Exception:                                              # noqa: BLE001
        return
    for g in games:
        if g["period"] in per and "sog" in g["v"]:
            g["v"]["sat"], g["v"]["pp"] = per[g["period"]]


def _mean(xs: list):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _lead(sport: str, games: list, avg: dict) -> str:
    """The number his role is read by: the one the trend is drawn for."""
    n = len(games)
    have = lambda k: sum(1 for g in games if g["v"].get(k) is not None)  # noqa: E731
    if sport == "nfl":
        if (avg.get("att") or 0) >= PASSER_AT:
            return "att"
        if have("snap") * 2 >= n:
            return "snap"
        return "tgt" if (avg.get("tgt") or 0) >= (avg.get("car") or 0) else "car"
    if sport == "cfb":
        if (avg.get("att") or 0) >= PASSER_AT:
            return "att"
        return "car" if (avg.get("car") or 0) >= (avg.get("rec") or 0) else "rec"
    if sport == "mlb":
        if have("pa") * 2 >= n:
            return "pa"
        return "pitches" if have("pitches") * 2 >= max(1, have("outs")) else "outs"
    if sport == "nhl":
        return "sa" if have("sa") > have("sog") else "toi"
    return "min"


def _split(games: list, keys: list, test) -> dict | None:
    xs = [g for g in games if test(g)]
    if not xs:
        return None
    return {"n": len(xs), "avg": {k: _mean([g["v"].get(k) for g in xs]) for k in keys}}


def chart(conn, sport: str, player: str, season: int | None = None) -> dict:
    """Everything the role chart draws for one player-season:
    ``{player, sport, seasons, season, season_label, team, position, lead,
    metrics: [{key, name, short, unit}], games: [{id, period, week?, date,
    team, opp, home, start, v: {key: value}}], season_line, splits}``,
    games newest first; ``season_line.n`` is his games."""
    if sport not in LOGGED:
        return {}
    name = resolve(conn, sport, player)
    if not name:
        return {}
    markets = sorted({m for _k, ms in LOGGED[sport] for m in ms})
    seasons = [int(s) for (s,) in conn.execute(
        f"SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND player=? "
        f"AND market IN ({_marks(markets)}) AND season IS NOT NULL ORDER BY season DESC",
        (sport, name, *markets))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    games = [g for g in _logged(conn, sport, name, pick) if g["v"]]
    if not games:
        return {}
    if sport in SHARES:
        _shares(conn, sport, pick, games)
    if sport == "nfl":
        _nfl_games(conn, pick, games)
        _nfl_red_zone(conn, name, pick, games)
    extra = {"mlb": _mlb, "nba": _nba, "nhl": _nhl}.get(sport)
    if extra:
        extra(conn, name, pick, games)
    keys = [k for k in ORDER[sport] if any(g["v"].get(k) is not None for g in games)]
    avg = {k: _mean([g["v"].get(k) for g in games]) for k in keys}
    lead = _lead(sport, games, avg)
    counts = {k for k in keys if (NAMED.get((sport, k)) or METRICS[k])[2] == "n"}
    shown = []
    for k in keys:
        base = next((c for sh, c, _m in SHARES.get(sport, ()) if sh == k), None)
        if base is not None:
            keep = base in shown
        elif k in counts and k not in ("rest", "bf", "pitches", "seen"):
            keep = k == lead or (avg.get(k) or 0) >= SHOW_AT
        else:
            keep = True
        if keep:
            shown.append(k)
    # His lead number first: the strip drawn tallest, the first tile.
    shown = [lead] + [k for k in shown if k != lead]
    # A pitcher's own numbers stay with a pitcher, a hitter's with a hitter.
    if sport == "mlb":
        side = ("pa", "spot", "seen") if lead == "pa" else ("pitches", "bf", "outs", "rest")
        shown = [k for k in shown if k in side]
    newest = games[::-1]
    position = "" if sport in ("nba", "wnba") else newest[0]["pos"]
    for g in games:
        g["v"] = {k: g["v"][k] for k in shown if g["v"].get(k) is not None}
        g.pop("leg", None)
        g.pop("pos", None)
    line = {"n": len(games), "games": len(games),
            "avg": {k: avg.get(k) for k in shown},
            "high": {k: max((g["v"][k] for g in games if k in g["v"]), default=None) for k in shown},
            "low": {k: min((g["v"][k] for g in games if k in g["v"]), default=None) for k in shown}}
    for n in STRETCHES:
        line[f"last{n}"] = {k: _mean([g["v"].get(k) for g in newest[:n]]) for k in shown}
    flags = [g["start"] for g in games if g["start"] is not None]
    line["starts"] = sum(flags) if flags else None
    line["start_known"] = len(flags)
    splits = {}
    if any(g["home"] is not None for g in games):
        splits["place"] = [x for x in (
            dict(_split(games, shown, lambda g: g["home"] is True) or {}, key="home", name="Home"),
            dict(_split(games, shown, lambda g: g["home"] is False) or {}, key="away", name="Away")) if x.get("n")]
    if flags and 0 < sum(flags) < len(flags):
        on, off = {"mlb": ("Started", "Off the bench") if lead == "pa" else ("Started", "In relief"),
                   "nhl": ("Started", "In relief")}.get(sport, ("Started", "Off the bench"))
        splits["start"] = [x for x in (
            dict(_split(games, shown, lambda g: g["start"] is True) or {}, key="start", name=on),
            dict(_split(games, shown, lambda g: g["start"] is False) or {}, key="bench", name=off)) if x.get("n")]
    latest = newest[0]
    return {"player": name, "sport": sport, "seasons": seasons, "season": pick,
            "season_label": season_label(sport, pick), "team": latest["team"],
            "position": position,
            "lead": lead, "metrics": [metric(sport, k) for k in shown],
            "games": newest, "season_line": line, "splits": splits}
