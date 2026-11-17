"""A shooter's percentages and a skater's +/- and penalty minutes are on
their pages (2026-11-17).

Ethan, with Cameron Dicker's empty page: "Also the player page is missing a
bunch of data". Past football (test_a_kicker_and_a_defender_have_their_numbers),
the box scores already in hand held more than the pages drew:

* BASKETBALL (NBA, WNBA, college) stored a player's three-point and free-throw
  makes and tries and drew them as made-tried only; the 3P% and FT% a box
  score prints beside them are now columns (engine/gamelog HOOPS), off the
  same rows.
* HOCKEY's box score carries each skater's plus-minus and penalty minutes,
  which the live page read and the stored rows dropped. They are stored now
  (engine/sources/nhldata SKATER_MARKETS, LATER_MARKETS), drawn as +/- and
  PIM (engine/gamelog HOCKEY), and the season's finals stored before are
  filled once from their cached box scores (nhldata.backfill_lines, run at
  start by launch._fill_missing_lines).

Run directly: `python3 tests/test_a_shooters_percentages_and_a_skaters_plus_minus_are_on_the_page.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, gamelog as GL                                    # noqa: E402
from engine.sources import nhldata as N                                         # noqa: E402


def _history(games=(), rows=(), assets=()):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date, "
                     "extra) VALUES (?,?,?,?,?,?,?,?,?,?)", list(games))
    if rows:
        _db.upsert_player_logs(conn, list(rows))
    if assets:
        _db.upsert_player_assets(conn, list(assets))
    conn.commit()
    return path, conn


def _log(sport, period, gid, player, team, opp, stats, season=2026):
    return [{"sport": sport, "season": season, "period": period, "game_id": gid, "player": player, "team": team,
             "opponent": opp, "position": "G", "home": 1, "market": m, "value": v} for m, v in stats.items()]


# --- basketball --------------------------------------------------------------------------------
def test_a_shooters_page_prints_the_three_point_and_free_throw_percentages():
    rows = (_log("nba", "2026-11-10", "g1", "Jalen Brunson", "NYK", "BOS",
                 {"min": 36, "pts": 30, "fgm": 11, "fga": 20, "fg3m": 3, "fg3a": 7, "ftm": 5, "fta": 6})
            + _log("nba", "2026-11-12", "g2", "Jalen Brunson", "NYK", "PHI",
                   {"min": 34, "pts": 24, "fgm": 9, "fga": 19, "fg3m": 2, "fg3a": 5, "ftm": 4, "fta": 4}))
    path, conn = _history(rows=rows)
    conn.close()
    log = GL.season_log("nba", "Jalen Brunson", db_path=path)
    cols = [c["key"] for c in log["groups"][0]["cols"]]
    assert cols[cols.index("fg3") + 1] == "fg3p" and cols[cols.index("ft") + 1] == "ftp", \
        "each percentage beside its makes, as a box score prints them"
    t = log["totals"]
    assert (t["box.fg3"], t["box.fg3p"], t["box.ft"], t["box.ftp"]) == ("5-12", 41.7, "9-10", 90.0), t
    first = next(g for g in log["games"] if g["date"] == "2026-11-12")
    assert first["values"]["box.fg3p"] == 40.0 and first["values"]["box.ftp"] == 100.0
    labels = {c["key"]: c["label"] for c in log["groups"][0]["cols"]}
    assert (labels["fg3p"], labels["ftp"]) == ("3P%", "FT%")


def test_a_percentage_without_its_tries_is_left_out_not_zero():
    path, conn = _history(rows=_log("cbb", "2026-11-14", "c1", "Walk On", "DUKE", "UNC",
                                    {"min": 3, "pts": 0, "fgm": 0, "fga": 1}))
    conn.close()
    log = GL.season_log("cbb", "Walk On", db_path=path)
    cols = [c["key"] for c in log["groups"][0]["cols"]]
    assert "fg3p" not in cols and "ftp" not in cols, "no tries, no percentage column"


# --- hockey ------------------------------------------------------------------------------------
def _skater(pid, short, pos, **kw):
    return {"playerId": pid, "name": {"default": short}, "position": pos, "goals": kw.get("g", 0),
            "assists": kw.get("a", 0), "points": kw.get("g", 0) + kw.get("a", 0), "sog": kw.get("sog", 0),
            "toi": "18:00", **({"plusMinus": kw["pm"]} if "pm" in kw else {}),
            **({"pim": kw["pim"]} if "pim" in kw else {})}


BOX = {"homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "CGY"}, "playerByGameStats": {
    "homeTeam": {"forwards": [_skater(8478402, "C. McDavid", "C", g=1, a=2, sog=5, pm=2, pim=2)],
                 "defense": [_skater(8480803, "E. Bouchard", "D", a=1, pm=-1)],
                 "goalies": [{"playerId": 8479973, "name": {"default": "S. Skinner"}, "saveShotsAgainst": "23/25",
                              "goalsAgainst": 2, "toi": "60:00", "starter": True}]},
    "awayTeam": {"forwards": [_skater(8477496, "N. Kadri", "C", g=1, sog=4, pm=-2, pim=4)], "defense": [],
                 "goalies": []}}}
NAMES = {"8478402": "Connor McDavid", "8480803": "Evan Bouchard", "8479973": "Stuart Skinner",
         "8477496": "Nazem Kadri"}


def test_the_box_score_keeps_a_skaters_plus_minus_and_penalty_minutes():
    players = {p["short"]: p for p in N.parse_boxscore(BOX)}
    assert (players["C. McDavid"]["plus_minus"], players["C. McDavid"]["pim"]) == (2.0, 2.0)
    assert (players["N. Kadri"]["plus_minus"], players["N. Kadri"]["pim"]) == (-2.0, 4.0)
    assert players["E. Bouchard"]["pim"] == 0.0, "a skater with none has none, not a gap"
    assert set(N.LATER_MARKETS) <= set(N.SKATER_MARKETS)
    rows = N.log_rows(list(players.values()), {pid: (name, "") for pid, name in NAMES.items()}, "2026-11-10")
    by = {(r["player"], r["market"]): r["value"] for r in rows}
    assert by[("Nazem Kadri", "plus_minus")] == -2.0 and by[("Connor McDavid", "pim")] == 2.0
    assert ("Stuart Skinner", "pim") not in by, "a goalie's line is a goalie's"


def _nhl_world(with_pim=False):
    """A season whose first final was stored before the rows kept +/- and
    PIM: its lines as the day ingest wrote them then."""
    games = [("nhl", 2026, "2026-11-10", "CGY@EDM", "EDM", "CGY", 4, 2, "2026-11-10",
              json.dumps({"nhl_id": 2026020101})),
             ("nhl", 2026, "2026-11-12", "EDM@VAN", "VAN", "EDM", 1, 3, "2026-11-12",
              json.dumps({"nhl_id": 2026020120})),
             ("nhl", 2026, "2026-11-13", "SEA@LA", "LA", "SEA", 2, 1, "2026-11-13", "{}")]
    names = {pid: (name, "") for pid, name in NAMES.items()}
    rows = [r for r in N.log_rows(N.parse_boxscore(BOX), names, "2026-11-10") if r["market"] not in N.LATER_MARKETS]
    if with_pim:
        rows += [{"sport": "nhl", "season": 2026, "period": "2026-11-12", "game_id": "Connor McDavid-2026-11-12",
                  "player": "Connor McDavid", "team": "EDM", "opponent": "VAN", "position": "C", "home": 0,
                  "market": "pim", "value": 0.0}]
    assets = [{"sport": "nhl", "player": n, "espn_id": pid, "headshot": "", "seen": "2026-11-10"}
              for pid, n in NAMES.items()]
    return _history(games, rows, assets)


def test_the_seasons_finals_get_their_plus_minus_once_from_the_kept_box_scores():
    path, conn = _nhl_world(with_pim=True)
    before = conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='nhl' AND market NOT IN "
                          "('plus_minus', 'pim')").fetchone()[0]
    asked = []

    def box(game_id, ttl=None):
        asked.append((game_id, ttl))
        return BOX

    def person(pid, ttl=None):
        raise AssertionError("every name is already on file")
    try:
        got = N.backfill_lines(conn, 2026, fetch_box=box, fetch_person=person)
        assert asked == [(2026020101, N.FINAL_BOX_TTL)], \
            "the game whose day has penalty minutes is filled already; a game with no id is not asked for"
        assert got["games"] == 1 and got["rows"] == 6 and not got["skipped"], got
        stored = {(r[0], r[1]): r[2] for r in conn.execute(
            "SELECT player, market, value FROM player_game_logs WHERE sport='nhl' AND period='2026-11-10' "
            "AND market IN ('plus_minus', 'pim')")}
        assert stored[("Nazem Kadri", "plus_minus")] == -2.0 and stored[("Connor McDavid", "pim")] == 2.0
        assert not any(p == "Stuart Skinner" for p, _m in stored), "only the skaters' columns"
        assert conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='nhl' AND market NOT IN "
                            "('plus_minus', 'pim')").fetchone()[0] == before, \
            "the rest of the line is the day ingest's, left as it was"
        asked.clear()
        assert N.backfill_lines(conn, 2026, fetch_box=box, fetch_person=person)["games"] == 0 and asked == [], \
            "a game filled once is not read again"
    finally:
        conn.close()


def test_a_box_score_that_will_not_load_costs_that_game_only():
    path, conn = _nhl_world()

    def box(game_id, ttl=None):
        if game_id == 2026020101:
            raise N.DataUnavailable("the league's host is down")
        return {**BOX, "homeTeam": {"abbrev": "VAN"}, "awayTeam": {"abbrev": "EDM"}}
    try:
        got = N.backfill_lines(conn, 2026, fetch_box=box, fetch_person=lambda pid, ttl=None: {})
        assert got["skipped"] == ["nhl box 2026020101: the league's host is down"], got
        assert got["games"] == 1, "the next game is still filled"
    finally:
        conn.close()


def test_a_skater_without_a_goal_yet_still_has_a_page():
    """The group a page draws is read off every one of its marks: read off
    the first one stored, a skater with no goal had no skater group, so
    the page and the game log were empty all season."""
    rows = []
    for day, gid, a, sog in (("2026-11-10", "n1", 1, 2), ("2026-11-12", "n2", 0, 1)):
        rows += _log("nhl", day, f"Evan Bouchard-{day}", "Evan Bouchard", "EDM", "CGY",
                     {"goals": 0, "assists": a, "points": a, "sog": sog, "toi": 22.5})
    path, conn = _history(rows=rows)
    conn.close()
    log = GL.season_log("nhl", "Evan Bouchard", db_path=path)
    assert [g["key"] for g in log["groups"]] == ["skater"], log
    assert log["totals"]["skater.a"] == 1 and log["totals"]["skater.g"] == 0
    assert GL.shows([{"stats": {"goals": 0.0, "hits": 3.0}}], ("goals", "hits"))
    assert not GL.shows([{"stats": {"carries": 0.0, "rush_yds": 0.0}}], ("carries", "rush_yds")), \
        "a receiver's carries of 0 every week are still no rushing line"


def test_the_skaters_page_draws_plus_minus_and_penalty_minutes():
    path, conn = _nhl_world()

    def box(game_id, ttl=None):
        if game_id != 2026020101:
            raise N.DataUnavailable("not in this test")
        return BOX
    try:
        N.backfill_lines(conn, 2026, fetch_box=box, fetch_person=lambda pid, ttl=None: {})
    finally:
        conn.close()
    log = GL.season_log("nhl", "Nazem Kadri", db_path=path)
    cols = [c["key"] for c in log["groups"][0]["cols"]]
    assert cols[:5] == ["g", "a", "pts", "pm", "pim"], "after the points, as a hockey box score has them"
    assert log["totals"]["skater.pm"] == -2.0 and log["totals"]["skater.pim"] == 4.0, log["totals"]
    labels = {c["key"]: c["label"] for c in log["groups"][0]["cols"]}
    assert (labels["pm"], labels["pim"]) == ("+/-", "PIM")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
