"""What the game report reads beyond the board: player form and the meetings.

Ethan, 2026-10-20, on the game report (engine/gamereport): "I want you
too do all of it besides D". Two of the asks need the stored history
rather than tonight's board:

  form       Every key player's season so far and his last three games,
             with his red-zone work — from the game logs the nightly
             ingest keeps (engine/db player_game_logs). The red-zone
             counts come off play-by-play under its short names
             ("J.Gibbs"), joined the way engine/fantasy joins them.
  meetings   The two teams' last meetings, regular season and playoffs,
             with the closing spread and total each was played at — from
             nflverse's schedule file, the one engine/spots reads.

Numbers only, no words: engine/gamereport writes the sentences. Every
reader returns {} on a missing table, file or column, so a report on a
box without them is a report without those lines.

Standard library only. Never raises.
"""
from __future__ import annotations

import csv
from pathlib import Path

#: The weekly-stat markets a form line reads (engine/db player_game_logs).
FORM_MARKETS = ("pass_cmp", "pass_att", "pass_yds", "pass_td", "pass_int",
                "rush_att", "rush_yds", "rush_td",
                "targets", "receptions", "rec_yds", "rec_td")

#: Red-zone work off play-by-play: carries inside the 20 and the 5,
#: targets inside the 20 and the 10 (engine/sources/nflpbp).
RZ_MARKETS = ("rz_car", "i5_car", "rz_tgt", "i10_tgt")

#: How many of his latest games the form line lists.
LAST_N = 3

#: How many meetings, and how far back.
MEETINGS_N = 5
MEETINGS_YEARS = 6


def _chunks(seq, n: int = 400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def player_form(conn, season: int, players: dict, sport: str = "nfl", schedule=None) -> dict:
    """``players``: {name: team} for everyone the report names.

    → {name: {"games": [newest first, up to LAST_N: {"season", "week",
    "team", "opp", "where" ("home", "away", "neutral" or "" — off the
    schedule file ``schedule``, nflverse's cached one by default),
    "s": {market: value}}],
    "season": {"games": n, "s": {market: total}} (this season, when he
    has played in it), "last_season": the same for the season before
    (only when he has not played in this one), "rz": {"rz_car", "i5_car",
    "rz_tgt", "i10_tgt", "team_rz_car", "team_rz_tgt", "team"}}}.

    A name two players share is told apart by the team on the board: in
    a week both played, the row for the board's team is kept."""
    if conn is None or not players:
        return {}
    try:
        season = int(season)
    except (TypeError, ValueError):
        return {}
    marks = ",".join("?" * len(FORM_MARKETS))
    games: dict = {}
    try:
        for chunk in _chunks(sorted(players)):
            q = (f"SELECT player, team, opponent, home, season, period, game_id, market, value "
                 f"FROM player_game_logs WHERE sport=? AND season IN (?, ?) AND market IN ({marks}) "
                 f"AND player IN ({','.join('?' * len(chunk))})")
            for r in conn.execute(q, (sport, season, season - 1, *FORM_MARKETS, *chunk)):
                name, team, opp, _home, yr, period, gid, mk, val = tuple(r)
                try:
                    wk = int(period)
                except (TypeError, ValueError):
                    continue
                g = games.setdefault(name, {}).setdefault((int(yr), wk), {})
                one = g.setdefault(str(gid), {"season": int(yr), "week": wk, "team": team, "opp": opp,
                                               "s": {}})
                if val is not None:
                    one["s"][mk] = float(val)
    except Exception:                                        # noqa: BLE001
        return {}
    out: dict = {}
    for name, by_week in games.items():
        mine = players.get(name)
        rows = []
        for key in sorted(by_week, reverse=True):
            cands = list(by_week[key].values())
            # Two men of one name the same week: the board's team's.
            pick = next((c for c in cands if c["team"] == mine), cands[0])
            rows.append(pick)
        cur = [g for g in rows if g["season"] == season]
        prior = [g for g in rows if g["season"] == season - 1]
        for g in rows[:LAST_N]:
            g["where"] = venue(g["season"], g["week"], g["team"], schedule)
        rec = {"games": rows[:LAST_N]}
        if cur:
            rec["season"] = _totals(cur)
        elif prior:
            rec["last_season"] = _totals(prior)
        rec["teams"] = sorted({g["team"] for g in cur if g.get("team")})
        out[name] = rec
    _red_zone(conn, season, players, out, sport)
    return out


def _totals(rows) -> dict:
    s: dict = {}
    for g in rows:
        for k, v in g["s"].items():
            s[k] = s.get(k, 0.0) + v
    return {"games": len(rows), "s": s}


def _red_zone(conn, season: int, players: dict, out: dict, sport: str) -> None:
    """His red-zone counts this season and his team's, into ``out``."""
    try:
        from .fantasy import _short_key
    except Exception:                                        # noqa: BLE001
        return
    marks = ",".join("?" * len(RZ_MARKETS))
    mine: dict = {}
    team_tot: dict = {}
    try:
        for r in conn.execute(f"SELECT player, team, market, SUM(value) FROM player_game_logs "
                              f"WHERE sport=? AND season=? AND market IN ({marks}) "
                              f"GROUP BY player, team, market", (sport, season, *RZ_MARKETS)):
            name, team, mk, tot = tuple(r)
            if tot is None:
                continue
            mine.setdefault(_short_key(name, team), {})[mk] = float(tot)
            tt = team_tot.setdefault(team, {})
            tt[mk] = tt.get(mk, 0.0) + float(tot)
    except Exception:                                        # noqa: BLE001
        return
    for name, team in players.items():
        rec = out.get(name)
        if rec is None or not team:
            continue
        got = mine.get(_short_key(name, team))
        if not got:
            continue
        tt = team_tot.get(team) or {}
        rec["rz"] = {**{k: got.get(k, 0.0) for k in RZ_MARKETS}, "team": team,
                     "team_rz_car": tt.get("rz_car", 0.0), "team_rz_tgt": tt.get("rz_tgt", 0.0)}


# --- the meetings ---------------------------------------------------------------------
_SCHED: dict = {}


def _schedule_rows(path=None) -> list:
    """Every game in nflverse's schedule file with a final score, read
    once per change of the file: [{"season", "week", "type", "day",
    "home", "away", "hs", "as", "spread", "total"}]. ``spread`` is the
    closing line from the home side (nflverse's ``spread_line``: positive
    when the home team is favored)."""
    try:
        from .sources.fetch import CACHE_DIR
        p = Path(path) if path else Path(CACHE_DIR) / "games.csv"
        stamp = (str(p), p.stat().st_mtime)
    except Exception:                                        # noqa: BLE001
        return []
    if _SCHED.get("stamp") == stamp:
        return _SCHED["rows"]
    rows = []
    try:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    hs, as_ = float(r["home_score"]), float(r["away_score"])
                    season, week = int(r["season"]), int(r["week"])
                except (KeyError, TypeError, ValueError):
                    continue
                rows.append({"season": season, "week": week,
                             "type": str(r.get("game_type") or "REG").upper(),
                             "day": str(r.get("gameday") or "")[:10],
                             "home": str(r.get("home_team") or "").upper(),
                             "away": str(r.get("away_team") or "").upper(),
                             "hs": hs, "as": as_,
                             "neutral": str(r.get("location") or "").lower() == "neutral",
                             "spread": _num(r.get("spread_line")), "total": _num(r.get("total_line"))})
    except (OSError, ValueError):
        rows = []
    _SCHED["stamp"], _SCHED["rows"] = stamp, rows
    return rows


def venue(season: int, week: int, team: str, path=None) -> str:
    """"home", "away" or "neutral" for a team's finished game that week,
    off the schedule — the game logs' own home flag is not kept (every
    NFL row reads 1). "" when the schedule does not have it."""
    rows = _schedule_rows(path)
    idx = _SCHED.get("venue")
    if idx is None or _SCHED.get("venue_of") is not rows:
        idx = {}
        for r in rows:
            for t, side in ((r["home"], "home"), (r["away"], "away")):
                idx[(r["season"], r["week"], t)] = "neutral" if r["neutral"] else side
        _SCHED["venue"], _SCHED["venue_of"] = idx, rows
    try:
        return idx.get((int(season), int(week), str(team or "").upper()), "")
    except (TypeError, ValueError):
        return ""


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


#: nflverse's names for the playoff rounds.
ROUNDS = {"WC": "wild-card round", "DIV": "divisional round", "CON": "conference title game",
          "SB": "Super Bowl"}


def meetings(home: str, away: str, before: str, path=None, n: int = MEETINGS_N,
             years: int = MEETINGS_YEARS) -> list:
    """The two teams' last ``n`` finished meetings before ``before`` (an
    ISO date), newest first, within ``years`` seasons. Each: {"season",
    "week", "round" (a playoff round's name, else ""), "day", "home",
    "away", "hs", "as", "winner" (None on a tie), "spread_home" (the
    home side's number, negative when it was favored), "total", "covered"
    (the team that covered, "push", or None without a line), "ou"
    ("over"/"under"/"push", or None)}."""
    home, away = str(home or "").upper(), str(away or "").upper()
    if not home or not away:
        return []
    rows = _schedule_rows(path)
    if not rows:
        return []
    try:
        floor = int(str(before)[:4]) - years
    except ValueError:
        floor = 0
    hit = [r for r in rows if {r["home"], r["away"]} == {home, away}
           and r["day"] and r["day"] < str(before)[:10] and r["season"] >= floor]
    hit.sort(key=lambda r: r["day"], reverse=True)
    out = []
    for r in hit[:n]:
        margin = r["hs"] - r["as"]
        winner = r["home"] if margin > 0 else r["away"] if margin < 0 else None
        sp = r["spread"]
        covered = None
        if sp is not None:
            # spread_line favors the home side when positive: the home team
            # covers when it wins by more than that.
            covered = "push" if margin == sp else r["home"] if margin > sp else r["away"]
        ou = None
        if r["total"] is not None:
            pts = r["hs"] + r["as"]
            ou = "push" if pts == r["total"] else "over" if pts > r["total"] else "under"
        out.append({"season": r["season"], "week": r["week"],
                    "round": ROUNDS.get(r["type"], ""), "day": r["day"],
                    "home": r["home"], "away": r["away"], "hs": r["hs"], "as": r["as"],
                    "neutral": r["neutral"], "winner": winner,
                    "spread_home": -sp if sp is not None else None, "total": r["total"],
                    "covered": covered, "ou": ou})
    return out
