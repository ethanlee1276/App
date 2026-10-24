"""Grade football props the night the game ends, off the box score
already on screen.

Ethan, Tuesday 2026-09-15: "I still see some edge bets not graded from
last nights nfl games." Monday's game had been final for hours.

WHY THEY WERE OPEN. A football prop grades from `player_game_logs`, and
the only writer of an NFL stat line was nflverse's weekly file — which
publishes overnight, the morning after — and for college the Monday
backfill (`ingest.ingest_cfb_player_history`). So every Sunday and
Monday prop sat open until the next morning at best, and Saturday's
college props until Monday, while the play-by-play page had every
player's final line twelve seconds after the whistle, off ESPN's game
summary, through parsers this project already trusts for the live
tracker (`livepicks._box_rows`).

WHAT THIS DOES. For every finished game a league still has an open prop
on, fetch that game's summary, run it through the same parsers, and
file the rows into `player_game_logs` under the keys the settler
already reads — the bet's season and week (NFL) or the schedule's
period (college) — so `ledger.settle_from_history` grades them on the
same pass. Nothing about the grading changes; only when the evidence
arrives.

PROVISIONAL, AND MARKED AS SUCH. The rows carry a ``-box`` suffix on
their game id. When the official file lands — nflverse's weekly stats,
the college backfill — the official rows for that game replace them:
this pass deletes the provisional rows the moment official ones exist
for the game and never fetches a game that has them. Two sources for
one game would hand the settler two rows per player, and its duplicate
rule voids a bet whose rows disagree — so there is never more than one
source per game on disk. A grade made off a box score that the official
file later corrects is re-graded by `ledger.resettle_mismatches`, the
pass built for exactly that.

GUARDS. Only games with a stored FINAL score (the finals ingest runs
first; a box score is never read for a game in play). Only games with
an open prop in that league. Only the last ten days. One feed failure
costs that game, not the pass.
"""

from __future__ import annotations

import datetime as _dt

#: The mark on a provisional row's game id.
BOX_SUFFIX = "-box"
#: How far back a finished game may be to be worth a summary fetch.
LOOKBACK_DAYS = 10
#: EVERY PROP OPENS THE PASS, not a list of six (2026-10-13). Ethan:
#: "bets are taking way too long to settle … It should not take a day."
#: This read `market IN (pass_yds, pass_td, rush_yds, rec_yds, receptions,
#: anytime_td)` — the board as it stood on 2026-09-15 — so a week whose
#: open props were attempts, completions, carries, interceptions or any of
#: the five markets of 2026-10-10 never fetched a box score at all, and
#: those bets waited for the official file the next morning. A game market
#: grades from the score and a desk ticket or a fight from elsewhere
#: (`ledger.GRADED_ELSEWHERE`); everything else on the bet is a prop.


def _open_periods(lconn, league: str) -> dict:
    """``{(season, period): n}`` of open props, keyed the way the
    settler keys them: NFL by the week label's season and week, college
    by the bet's own date."""
    from .ledger import _NFL_WEEK_DATE, GAME_MARKETS, GRADED_ELSEWHERE
    gm = ",".join("?" * len(GAME_MARKETS))
    ge = ",".join("?" * len(GRADED_ELSEWHERE))
    out: dict = {}
    for r in lconn.execute(
            f"SELECT date, game_day FROM bets WHERE status='open' AND sport=? "
            f"AND market NOT IN ({gm}) AND COALESCE(category, '') NOT IN ({ge})",
            (league, *GAME_MARKETS, *GRADED_ELSEWHERE)):
        m = _NFL_WEEK_DATE.match(r["date"] or "")
        if league == "nfl" and m:
            key = (int(m.group(1)), f"{int(m.group(2)):03d}")
        else:
            key = (None, str(r["date"] or ""))
        out[key] = out.get(key, 0) + 1
    return out


def finished_games_with_open_props(lconn, hconn, league: str,
                                   today: _dt.date | None = None) -> list:
    """Games rows with a final score whose (season, period) still has an
    open prop in this league, inside the lookback."""
    today = today or _dt.date.today()
    floor = (today - _dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    wanted = _open_periods(lconn, league)
    if not wanted:
        return []
    if league != "nfl":
        # A COLLEGE GAME'S PERIOD IS ITS UTC DATE, and the bet's date is
        # the Eastern game day, so a Saturday-night kickoff is filed one
        # day later than the prop on it (Hawaii-UNLV, 2026-09-05 ET, is
        # the games row dated 09-06). Match a day either side.
        wide: dict = {}
        for (_s, day), n in wanted.items():
            try:
                d = _dt.date.fromisoformat(day)
            except ValueError:
                wide[(None, day)] = n
                continue
            for off in (-1, 0, 1):
                wide[(None, (d + _dt.timedelta(days=off)).isoformat())] = n
        wanted = wide
    out = []
    for g in hconn.execute(
            "SELECT season, period, game_id, home, away, date, extra FROM games "
            "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
            "ORDER BY COALESCE(date, period)", (league,)):
        # THE LOOKBACK, JUDGED ON WHATEVER DATE THE ROW CARRIES. This
        # read `COALESCE(date, '') >= floor` in SQL, and `games.date` is
        # NULL on every row the finals writer and the older ingests
        # filed — the whole college table on the droplet, and any NFL
        # week the finals scored without a date. Every such game was
        # silently outside the lookback, so the box score was never
        # fetched, no provisional row was ever written, and Sunday's
        # props waited for the official file the same-night settle exists
        # to beat (Ethan, 2026-09-14: 16 Sunday rows still open at 9pm
        # Monday, zero `-box` rows on disk). A dated row is judged on its
        # date; a college row's period IS its date; an NFL row with
        # neither is admitted on its week being open, which `wanted`
        # already requires.
        when = g["date"] or (str(g["period"]) if league != "nfl" else None)
        if when and str(when) < floor:
            continue
        key = ((int(g["season"]), str(g["period"])) if league == "nfl"
               else (None, str(g["period"])))
        if key in wanted:
            out.append(dict(g))
    return out


def _official_ids(league: str, g: dict) -> list:
    period = str(g["period"])
    if league == "nfl":
        return [f"{g['home']}-{period}", f"{g['away']}-{period}"]
    return [str(g["game_id"])]


def has_official_rows(hconn, league: str, g: dict) -> bool:
    ids = _official_ids(league, g)
    marks = ",".join("?" * len(ids))
    q = (f"SELECT 1 FROM player_game_logs WHERE sport=? AND period=? "
         f"AND game_id IN ({marks})")
    args: list = [league, str(g["period"]), *ids]
    if league == "nfl":
        q += " AND season=?"
        args.append(int(g["season"]))
    return hconn.execute(q + " LIMIT 1", args).fetchone() is not None


def purge_provisional(hconn, league: str, g: dict) -> int:
    ids = [i + BOX_SUFFIX for i in _official_ids(league, g)]
    marks = ",".join("?" * len(ids))
    cur = hconn.execute(
        f"DELETE FROM player_game_logs WHERE sport=? AND period=? "
        f"AND game_id IN ({marks})", (league, str(g["period"]), *ids))
    return cur.rowcount or 0


#: THE MARKETS THE SHARED PARSER DOES NOT WRITE (2026-10-13). The box
#: parser (`nflpreseason.parse_boxscore`) was built for the offence and the
#: preseason scan: yards, catches, carries, touchdowns, the quarterback's
#: line. Seven board markets had no same-night row and waited for the
#: official file — rush attempts (stored as `carries`), the two yardage
#: sums of 2026-10-10, a kicker's points and field goals, a defender's
#: tackles, and a quarterback's anytime touchdown when he never carried or
#: caught the ball. They are derived here, in settlement only, so the
#: preseason table the shared parser feeds is untouched.
#:
#: THE RULE FOR A SUM: a player in any of the three offensive blocks
#: played, and a block he is missing from is a zero in it — ESPN lists a
#: rusher for every carry and a receiver for every catch, so absence from
#: the rushing block IS zero rushing yards. A player in none of them is not
#: written: he may have sat, and that is `ledger._absent_player_verdict`'s
#: question, answered off the official snap file.
OFFENCE_BLOCKS = ("pass_yds", "pass_td", "pass_att", "rush_yds", "carries",
                  "rec_yds", "receptions")
#: The yardage sums, exactly as `nflverse.STAT_SUMS` adds them up.
YARD_SUMS = {"pass_rush_yds": ("pass_yds", "rush_yds", "rec_yds"),
             "rush_rec_yds": ("rush_yds", "rec_yds")}


def _made(cell) -> float | None:
    """"2/3" → 2.0, the makes half of a made/attempted cell."""
    head = str(cell or "").split("/")[0].strip()
    try:
        return float(head)
    except ValueError:
        return None


def _num(cell) -> float | None:
    try:
        return float(str(cell).strip())
    except (TypeError, ValueError):
        return None


def special_rows(payload: dict) -> list:
    """``[{player, team, position, market, value}]`` for the kicking and
    defensive blocks: a kicker's field goals and points (3 a field goal, 1
    an extra point, the book's and nflverse's sum), a defender's tackles
    plus assists (ESPN's TOT, solo and assisted together). Columns are read
    by label, never by position; a block whose labels are missing gives
    nothing rather than a wrong number."""
    from .sources.nflpreseason import _abbr
    out = []
    for side in ((payload or {}).get("boxscore") or {}).get("players") or []:
        team = _abbr(((side.get("team") or {}).get("abbreviation") or ""))
        for block in side.get("statistics") or []:
            kind = str(block.get("name") or "").lower()
            if kind not in ("kicking", "defensive"):
                continue
            cols = {str(x).upper(): i for i, x in enumerate(block.get("labels") or [])}
            for ath in block.get("athletes") or []:
                who = ath.get("athlete") or {}
                name = who.get("displayName") or who.get("shortName") or ""
                stats = ath.get("stats") or []
                if not name:
                    continue
                cell = lambda lab: stats[cols[lab]] if lab in cols and cols[lab] < len(stats) else None  # noqa: E731
                if kind == "kicking":
                    fg, xp = _made(cell("FG")), _made(cell("XP"))
                    pts = _num(cell("PTS"))
                    if pts is None and fg is not None and xp is not None:
                        pts = 3 * fg + xp
                    if fg is not None:
                        out.append({"player": name, "team": team, "position": "K",
                                    "market": "fg_made", "value": fg})
                    if pts is not None:
                        out.append({"player": name, "team": team, "position": "K",
                                    "market": "kick_pts", "value": pts})
                else:
                    tot = _num(cell("TOT"))
                    if tot is not None:
                        out.append({"player": name, "team": team, "position": "DEF",
                                    "market": "tackles_ast", "value": tot})
    return out


def derived_rows(rows: list) -> list:
    """The board markets the shared parser leaves out, from its own rows:
    rush attempts, the yardage sums, and a zero anytime touchdown for a
    player who played and never carried or caught it. Never a second row
    for a market a player already has."""
    have = {(r["player"], r["market"]) for r in rows}
    by_player: dict = {}
    for r in rows:
        by_player.setdefault((r["player"], r["team"]), {})[r["market"]] = r
    out = []

    def add(seed, market, value):
        if (seed["player"], market) in have:
            return
        have.add((seed["player"], market))
        out.append({**seed, "market": market, "value": float(value)})

    for (_name, _team), mk in by_player.items():
        if not any(m in mk for m in OFFENCE_BLOCKS):
            continue
        seed = next(iter(mk.values()))
        if "carries" in mk:
            add(seed, "rush_att", mk["carries"]["value"])
        for market, parts in YARD_SUMS.items():
            add(seed, market, sum(mk[p]["value"] for p in parts if p in mk))
        add(seed, "anytime_td", 0.0)
    return out


def nfl_rows(payload: dict, g: dict) -> list:
    """The NFL summary → provisional log rows keyed like nflverse's."""
    from .sources.nflpreseason import parse_boxscore
    period = str(g["period"])
    try:
        week = int(period)
    except ValueError:
        week = None
    rows = parse_boxscore(payload, {"home": g["home"], "away": g["away"],
                                    "season": int(g["season"]), "week": week,
                                    "game_id": g["game_id"]})
    rows = rows + derived_rows(rows)
    for r in special_rows(payload):
        opp = g["away"] if r["team"] == g["home"] else g["home"]
        rows.append({**r, "opponent": opp, "home": 1 if r["team"] == g["home"] else 0})
    out = []
    for r in rows:
        if r["team"] not in (g["home"], g["away"]):
            continue
        out.append({"sport": "nfl", "season": int(g["season"]), "period": period,
                    "game_id": f"{r['team']}-{period}{BOX_SUFFIX}",
                    "player": r["player"], "team": r["team"],
                    "opponent": r["opponent"], "position": r.get("position", ""),
                    "home": r.get("home", 0), "market": r["market"],
                    "value": float(r["value"])})
    return out


def cfb_rows(payload: dict, g: dict) -> list:
    """The college summary → provisional rows keyed like the backfill's:
    the schedule's period and game id, team keys resolved the way the
    college board resolves them."""
    from .sources.cfbdata import parse_summary, _team_key
    keys: dict = {}
    for block in ((payload or {}).get("boxscore") or {}).get("players") or []:
        team = (block or {}).get("team") if isinstance(block, dict) else None
        if isinstance(team, dict):
            abbr = (team.get("abbreviation") or "").strip()
            if abbr:
                keys[abbr] = _team_key(team)
    sides = {g["home"], g["away"]}
    out = []
    for r in parse_summary(payload):
        team = keys.get(r["team"], r["team"])
        if team not in sides:
            continue
        opp = g["away"] if team == g["home"] else g["home"]
        for market, value in (r.get("stats") or {}).items():
            out.append({"sport": "cfb", "season": int(g["season"]),
                        "period": str(g["period"]),
                        "game_id": f"{g['game_id']}{BOX_SUFFIX}",
                        "player": r["player"], "team": team, "opponent": opp,
                        "position": r.get("position", ""),
                        "home": 1 if team == g["home"] else 0,
                        "market": market, "value": float(value)})
    return out


def _event_id(league: str, g: dict, ids: dict) -> str:
    """The ESPN event to fetch: the schedule's own id when it kept one,
    else the scoreboard's row for the pair."""
    import json as _json
    try:
        extra = _json.loads(g.get("extra") or "{}") or {}
    except (ValueError, TypeError):
        extra = {}
    eid = str(extra.get("espn_game_id") or "").strip()
    if not eid and league == "cfb" and str(g.get("game_id") or "").isdigit():
        eid = str(g["game_id"])
    return eid or str(ids.get((g["away"], g["home"])) or "")


def ingest_for_open(lconn, hconn, league: str, log=print,
                    fetch_rows=None, fetch_summary=None,
                    today: _dt.date | None = None) -> dict:
    """File provisional stat lines for every finished game this league
    has an open prop on. Returns ``{games, rows, purged, skipped}``."""
    from . import db as _db
    res: dict = {"games": 0, "rows": 0, "purged": 0, "skipped": []}
    games = finished_games_with_open_props(lconn, hconn, league, today=today)
    if not games:
        return res
    need_ids = []
    for g in games:
        if has_official_rows(hconn, league, g):
            n = purge_provisional(hconn, league, g)
            res["purged"] += n
            continue
        need_ids.append(g)
    if not need_ids:
        if res["purged"]:
            hconn.commit()
        return res
    ids: dict = {}
    if fetch_rows is None:
        from .sources.livescores import fetch_rows as _fr
        fetch_rows = lambda lg: _fr(lg, ttl=30)          # noqa: E731
    if fetch_summary is None:
        from .sources.espnplays import fetch_summary as _fs
        fetch_summary = _fs
    if any(not _event_id(league, g, {}) for g in need_ids):
        try:
            ids = {(r["away"], r["home"]): r["event_id"] for r in fetch_rows(league)}
        except Exception as exc:                          # noqa: BLE001
            res["skipped"].append(f"{league} scoreboard unreachable: {exc}")
    for g in need_ids:
        eid = _event_id(league, g, ids)
        if not eid:
            res["skipped"].append(f"{league} {g['away']}@{g['home']}: no event id")
            continue
        try:
            payload = fetch_summary(league, eid)
            rows = nfl_rows(payload, g) if league == "nfl" else cfb_rows(payload, g)
        except Exception as exc:                          # noqa: BLE001
            res["skipped"].append(f"{league} {g['away']}@{g['home']}: {exc}")
            continue
        if not rows:
            res["skipped"].append(f"{league} {g['away']}@{g['home']}: summary "
                                  "carried no stat lines")
            continue
        res["rows"] += _db.upsert_player_logs(hconn, rows)
        res["games"] += 1
    if res["rows"] or res["purged"]:
        hconn.commit()
    return res
