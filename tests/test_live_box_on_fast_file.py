"""Each live game's box rows ride on the fast scoreboard file.

Ethan, 2026-09-14, 11:01pm, fourth quarter of Broncos-Chiefs, every bet
on the Live tab reading "in play" and nothing else: "why are we not
showing the live lines for the live props here and not tracking the
live stats like how sports books do it."

The tracker's number (`live_picks[].current`) came from a box score
fetched when the BOARD was built — every forty-five minutes or so on
football — and the page only ever promoted a row's phase from the fast
scoreboard. Now `livescore_build.attach_plays` (football, hoops) and
`live_build.attach_plays` (baseball) put the box rows the deep file's
Player stats room already parses onto the card's own row, on the same
twelve-second pass, and `liveTrackerRows` on the page reads a bet's
number off them (tests/test_live_tracker_fast_phase.py).

Same fixtures as tests/test_pbp_files.py, restated rather than imported
(the doctor forbids a test importing a sibling at module scope).
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
import live_build as M                                       # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402
from engine import gate                                      # noqa: E402


def _nfl_payload(with_box=True):
    """A live NFL summary: an empty drives block (the plays are not what
    this file is about) and the box shape `nflpreseason.parse_boxscore`
    reads — labels, not positions."""
    box = {"players": [
        {"team": {"abbreviation": "KC"}, "statistics": [
            {"name": "passing",
             "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"],
             "athletes": [{"athlete": {"displayName": "Patrick Mahomes",
                                       "position": {"abbreviation": "QB"}},
                           "stats": ["18/27", "187", "6.9", "1", "0", "1-8", "62.1", "98.7"]}]},
            {"name": "receiving",
             "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Travis Kelce",
                                       "position": {"abbreviation": "TE"}},
                           "stats": ["5", "57", "11.4", "0", "21", "7"]}]}]},
    ]} if with_box else {"teams": []}
    return {"drives": {"previous": []}, "header": {"id": "401"}, "boxscore": box}


def _game(state="live", eid="e1"):
    return {"event_id": eid, "home": "KC", "away": "DEN",
            "home_name": "Kansas City Chiefs", "away_name": "Denver Broncos",
            "live": {"state": state, "home_score": 21, "away_score": 14,
                     "period": "Q4", "clock": "9:02", "start_time": ""}}


def _with_fetch(fn, games, league="nfl", pbp_dir=None):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, league, pbp_dir=pbp_dir)
    finally:
        E.fetch_summary = real


def test_a_live_football_game_carries_its_box_rows():
    games = [_game(), _game(state="scheduled", eid="s1")]
    note = _with_fetch(lambda lg, eid, ttl=30: _nfl_payload(), games)
    rows = games[0]["players"]
    by = {r["player"]: r["stats"] for r in rows}
    assert by["Patrick Mahomes"]["pass_yds"] == 187.0, by
    assert by["Travis Kelce"]["rec_yds"] == 57.0 and by["Travis Kelce"]["receptions"] == 5.0, by
    assert rows[0]["team"] == "KC", rows[0]
    assert "players" not in games[1], "a scheduled game has no box"
    assert "1 box score(s)" in note, note


def test_the_rows_are_the_deep_files_rows_and_parsed_once():
    """One parser, one parse: the deep file takes the card's rows rather
    than reading the payload a second time on the same pass."""
    d = Path(tempfile.mkdtemp())
    games = [_game()]
    _with_fetch(lambda lg, eid, ttl=30: _nfl_payload(), games, pbp_dir=d)
    doc = json.loads((d / "nfl_e1.json").read_text())
    assert doc["players"] == games[0]["players"]
    # A row somebody put on the game beforehand is what the deep file
    # carries — proof it was not re-parsed from the payload.
    games = [dict(_game(), players=[{"player": "Marker", "team": "KC",
                                     "position": "", "stats": {"rec_yds": 1.0}}])]
    real = E.fetch_summary
    E.fetch_summary = lambda lg, eid, ttl=30: _nfl_payload()
    try:
        B.write_pbp("nfl", games[0], _nfl_payload(), d)
    finally:
        E.fetch_summary = real
    doc = json.loads((d / "nfl_e1.json").read_text())
    assert doc["players"][0]["player"] == "Marker", doc["players"]


def test_a_box_the_parser_cannot_read_costs_the_row_its_box_and_nothing_else():
    games = [_game()]
    note = _with_fetch(lambda lg, eid, ttl=30: _nfl_payload(with_box=False), games)
    assert "players" not in games[0], "an unreadable box must be absent, not empty"
    assert games[0]["plays_state"] == "ok", games[0]["plays_state"]
    assert "box score" not in note, note


def test_a_game_past_the_cap_has_no_box():
    games = [_game(eid=f"e{i}") for i in range(B.PLAYS_MAX_GAMES + 1)]
    _with_fetch(lambda lg, eid, ttl=30: _nfl_payload(), games)
    assert all("players" in g for g in games[:B.PLAYS_MAX_GAMES])
    assert "players" not in games[-1] and games[-1]["plays_state"] == "capped"


def test_the_rows_carry_nothing_priced():
    """The fast file is published whole and free (engine/gate FREE_FILES):
    a stat line is a public fact, and it must stay one."""
    games = [_game()]
    _with_fetch(lambda lg, eid, ttl=30: _nfl_payload(), games)
    flat = json.dumps(games[0]["players"])
    for banned in ("odds", "edge", "ev_per_unit", "stake", "book", "grade", "line"):
        assert f'"{banned}"' not in flat, (banned, flat)
    assert set(games[0]["players"][0]) == {"player", "team", "position", "stats"}
    assert not (set(games[0]) & set(gate.PAID_KEYS)), set(games[0]) & set(gate.PAID_KEYS)


# --- MLB ----------------------------------------------------------------------
def _mlb_box():
    return {"teams": {
        "home": {"players": {"ID1": {"person": {"fullName": "Aaron Judge"},
                                     "position": {"abbreviation": "RF"},
                                     "battingOrder": "200",
                                     "stats": {"batting": {"hits": 2, "doubles": 1, "triples": 0,
                                                           "homeRuns": 1, "plateAppearances": 3}}}}},
        "away": {"players": {"ID2": {"person": {"fullName": "Garrett Crochet"},
                                     "position": {"abbreviation": "P"},
                                     "stats": {"pitching": {"strikeOuts": 7, "inningsPitched": "5.2",
                                                            "battersFaced": 22}}}}}}}


def _mlb_plays():
    return {"allPlays": [
        {"result": {"event": "Single", "eventType": "single", "rbi": 0,
                    "awayScore": 0, "homeScore": 0, "description": "PROSE"},
         "about": {"inning": 1, "halfInning": "top", "isScoringPlay": False},
         "matchup": {"batter": {"fullName": "A"}, "pitcher": {"fullName": "P"}}},
    ]}


def _with_mlb(fn):
    from engine.mlb.sources import pbp as P
    from engine.mlb.sources import statslogs as S
    real_p, real_b = P.fetch_live_playbyplay, S.fetch_boxscore
    P.fetch_live_playbyplay = lambda pk, ttl=30: _mlb_plays()
    S.fetch_boxscore = lambda pk: _mlb_box()
    try:
        return fn()
    finally:
        P.fetch_live_playbyplay, S.fetch_boxscore = real_p, real_b


def test_the_mlb_builder_carries_the_same_rows():
    d = Path(tempfile.mkdtemp())
    games = [{"game_pk": 777, "home": "NYY", "away": "BOS",
              "live": {"state": "live", "start_time": ""}}]
    note = _with_mlb(lambda: M.attach_plays(games, pbp_dir=d))
    by = {r["player"]: r for r in games[0]["players"]}
    # The market names the tracker's bets carry: hits, total_bases,
    # home_runs, strikeouts — `livestats.box_rows`, the same reader the
    # deep file's Player stats room uses.
    assert by["Aaron Judge"]["stats"]["hits"] == 2.0
    assert by["Aaron Judge"]["stats"]["total_bases"] == 6.0, by["Aaron Judge"]
    assert by["Aaron Judge"]["team"] == "NYY"
    assert by["Garrett Crochet"]["stats"]["strikeouts"] == 7.0
    assert by["Garrett Crochet"]["team"] == "BOS"
    assert "1 box score(s)" in note, note
    doc = json.loads((d / "mlb_777.json").read_text())
    assert doc["players"] == games[0]["players"], "the deep file takes the card's rows"


def test_an_mlb_box_that_fails_leaves_the_plays():
    from engine.mlb.sources import pbp as P
    from engine.mlb.sources import statslogs as S
    real_p, real_b = P.fetch_live_playbyplay, S.fetch_boxscore
    P.fetch_live_playbyplay = lambda pk, ttl=30: _mlb_plays()

    def boom(pk):
        raise RuntimeError("statsapi down")
    S.fetch_boxscore = boom
    games = [{"game_pk": 778, "home": "NYY", "away": "BOS",
              "live": {"state": "live", "start_time": ""}}]
    try:
        note = M.attach_plays(games)
    finally:
        P.fetch_live_playbyplay, S.fetch_boxscore = real_p, real_b
    assert games[0]["plays"] and games[0]["plays_state"] == "ok"
    assert "players" not in games[0]
    assert "box score" not in note, note


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
