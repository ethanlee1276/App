"""A player back with a club he played for, read against his own games there (step ACK, 22 November 2026).

Ethan, 22 November: "we need to be implementing past player data, as in the example of Kirk Cousins was just traded
back to the Vikings ... So we need to implement a feature or data that uses that data as well when they realize a
QB or another player is back with the team they used to be on." The quarterback is engine/qblean.reunion (his
starts, off the play-by-play); this is every other player, off the box's game logs (player_game_logs):

  * his games are read club by club, season by season, in one pass a build (`stints`);
  * a player whose club now is one he played for before playing for another (`returning`: MIN_GAMES games there
    or more) has those games added up, market by market (`line`);
  * the game's report says it, one line a man (`words`): "[he] is back with the Vikings: in his [N] games for them
    ([first season]–[last]) he caught [n] passes for [y] yards a game". Words only: whether a man's old games with
    a club say more about his new ones than his recent games do is not measured, so nothing prices them.

Never raises: a history that cannot be read says nothing.
"""

from __future__ import annotations

#: His games there before he is said to be back.
MIN_GAMES = 4
#: The markets a line reads (`words` says the catches, then the carries).
MARKETS = ("receptions", "rec_yds", "rush_att", "rush_yds")
#: Positions a line is for (the quarterback's is engine/qblean's).
POSITIONS = ("WR", "TE", "RB", "FB")
_STINTS: dict = {}


def stints(conn, sport: str = "nfl") -> dict:
    """{player: {season: {club: (games, position)}}} for every player in the logs, one pass, kept for the life of the
    process by the logs' newest season and row count (a new week's rows read it again). {} when it cannot be read."""
    try:
        key = conn.execute("SELECT MAX(season), COUNT(*) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()
        key = (sport, tuple(key) if key else None)
        if key in _STINTS:
            return _STINTS[key]
        out: dict = {}
        for player, team, season, games, pos in conn.execute(
                "SELECT player, team, season, COUNT(DISTINCT game_id), MAX(position) FROM player_game_logs "
                "WHERE sport=? AND team IS NOT NULL AND team != '' GROUP BY player, team, season", (sport,)):
            out.setdefault(player, {}).setdefault(int(season), {})[team] = (int(games), str(pos or ""))
        _STINTS.clear()
        _STINTS[key] = out
        return out
    except Exception:                                        # noqa: BLE001 — a history that cannot be read says nothing
        return {}


def returning(st: dict, player: str, team: str, season: int) -> dict | None:
    """{"team", "seasons", "games", "position"}: the seasons he played for ``team`` before the last season (up to
    ``season``) he played for another club, when they hold MIN_GAMES games or more and he plays for ``team`` now.
    None otherwise."""
    mine = (st or {}).get(player) or {}
    now = mine.get(int(season)) or {}
    if team not in now:
        return None
    away = [yr for yr, clubs in mine.items() if yr <= int(season) and any(c != team for c in clubs)]
    if not away:
        return None
    last_away = max(away)
    then = sorted(yr for yr, clubs in mine.items() if team in clubs and yr < last_away)
    games = sum(mine[yr][team][0] for yr in then)
    if not then or games < MIN_GAMES:
        return None
    pos = next((mine[yr][team][1] for yr in reversed(then) if mine[yr][team][1]), "")
    return {"team": team, "seasons": then, "games": games, "position": pos}


def line(conn, player: str, back: dict, sport: str = "nfl") -> dict:
    """{market: per-game average} over his games with the club then (MARKETS), off the logs."""
    try:
        marks = ",".join("?" * len(back["seasons"]))
        rows = conn.execute(
            f"SELECT market, SUM(value) FROM player_game_logs WHERE sport=? AND player=? AND team=? "
            f"AND season IN ({marks}) AND market IN ({','.join('?' * len(MARKETS))}) GROUP BY market",
            (sport, player, back["team"], *back["seasons"], *MARKETS)).fetchall()
    except Exception:                                        # noqa: BLE001
        return {}
    n = max(int(back.get("games") or 0), 1)
    return {m: float(v or 0) / n for m, v in rows}


def words(player: str, back: dict, per_game: dict, club: str) -> str:
    """The line in a sentence (catches where he caught half a pass a game or more, carries where he ran twice or
    more). "" when the logs say nothing of what he did there."""
    yrs = back["seasons"]
    span = f"{yrs[0]}" if yrs[0] == yrs[-1] else f"{yrs[0]}–{yrs[-1]}"
    bits = []
    catch = per_game.get("receptions", 0) >= 0.5
    run = per_game.get("rush_att", 0) >= 2
    if catch:
        bits.append(f"caught {per_game['receptions']:.1f} passes for {per_game.get('rec_yds', 0):.0f} yards")
    if run:
        bits.append(f"ran {per_game['rush_att']:.1f} times for {per_game.get('rush_yds', 0):.0f} yards")
    if not bits:
        return ""
    return (f"{player} is back with {club}: in his {back['games']} games for them ({span}) he "
            + " and ".join(bits) + " a game")


def lines_for(conn, players: list, season: int, club_words, sport: str = "nfl", most: int = 3) -> list:
    """The report's lines for a game: each of ``players`` ([(name, club)]) back with a club he played for, the
    most games there first, at most ``most``. ``club_words``: club code -> "the Vikings"."""
    st = stints(conn, sport) if conn is not None else {}
    found = []
    for name, team in players:
        back = returning(st, name, team, season)
        if not back or str(back.get("position") or "").upper() not in POSITIONS:
            continue
        found.append((back["games"], name, team, back))
    out = []
    for _g, name, team, back in sorted(found, key=lambda x: (-x[0], x[1]))[:most]:
        w = words(name, back, line(conn, name, back, sport), club_words(team))
        if w:
            out.append(w)
    return out
