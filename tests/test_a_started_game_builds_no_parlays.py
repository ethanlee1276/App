"""A game under way builds no parlay, in every league (GPWIN2, 2026-11-18).

Tuesday's 7 pm hockey games (17 November) have two-leg tickets on the
record, and the board only began making two-leg tickets at 8:17 pm Eastern,
after the puck dropped. Hockey's prop rows carried no kickoff and no live or
started flag (the basketball rows carry all three, engine/pipeline), and the
game parlays drop a leg by the kickoff on its row (engine/twoleg `_started`),
so a started game's tickets were built again from its pre-game legs and
journaled as versions. The singles journal was safe: it reads the board's
own games list (engine/ledger._kickoff_map).

Now the hockey rows are told (nhl_build.stamp_started), and the parlay
builder reads the board's own games list whatever a row says
(engine/gameparlays.still_to_play).
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP                                 # noqa: E402
import nhl_build                                                      # noqa: E402

#: 8:30 pm Eastern on 17 November, as the clock reads it (naive UTC).
NOW = dt.datetime(2026, 11, 18, 1, 30)
GAMES = [
    # Under way by its live block.
    {"home": "TBL", "away": "WSH", "date": "2026-11-17", "kickoff": "2026-11-18T00:00:00Z", "live": {"state": "live"}},
    # Still to play.
    {"home": "STL", "away": "ANA", "date": "2026-11-17", "kickoff": "2026-11-18T02:00:00Z", "live": None},
    # Under way by its own clock, the live block not yet read.
    {"home": "UTA", "away": "VAN", "date": "2026-11-17", "kickoff": "2026-11-18T01:00:00Z", "live": None},
    # Over.
    {"home": "PHI", "away": "BUF", "date": "2026-11-17", "kickoff": "2026-11-17T17:00:00Z", "live": {"state": "final"}},
]


def _row(player, team, opp, home, away, market="anytime_goal", p=0.40, odds=150):
    return {"player": player, "team": team, "opponent": opp, "home": home, "away": away, "market": market,
            "side": "Over", "line": 0.5, "odds": odds, "model_prob": p, "book": "fanduel", "game_date": "2026-11-17"}


def test_the_board_s_own_games_say_which_have_started():
    assert GP.game_started(GAMES[0], now=NOW) and GP.game_started(GAMES[3], now=NOW)
    assert not GP.game_started(GAMES[1], now=NOW), "a game still to play"
    assert GP.game_started(GAMES[2], now=NOW), "its own kickoff by the clock, before the live block is read"
    assert GP.game_started({"final": True}) and GP.game_started({"live": True}) and not GP.game_started({})


def test_a_leg_of_a_started_game_is_no_leg_whatever_its_row_says():
    legs = [{"player": "A", "team": "WSH", "opponent": "TBL"}, {"player": "B", "team": "STL", "opponent": "ANA"},
            {"player": "C", "home": "UTA", "away": "VAN"}, {"player": "D", "team": "BUF", "opponent": "PHI"},
            {"player": "E", "team": "XXX", "opponent": "YYY"}]
    got = GP.still_to_play(legs, {"games": GAMES}, now=NOW)
    assert [l["player"] for l in got] == ["B", "E"], "a leg the board's games list does not name stays to its row"
    assert GP.still_to_play(legs, {}, now=NOW) == legs, "a board with no games list leaves every leg to its row"


def test_a_doubleheader_s_second_game_keeps_its_legs_while_the_first_is_played():
    games = [{"home": "NYY", "away": "BOS", "date": "2026-07-04", "kickoff": "2026-07-04T17:05:00Z",
              "live": {"state": "live"}},
             {"home": "NYY", "away": "BOS", "date": "2026-07-04", "kickoff": "2026-07-04T23:05:00Z", "live": None}]
    leg = {"player": "Aaron Judge", "team": "NYY", "opponent": "BOS"}
    at = dt.datetime(2026, 7, 4, 18, 0)
    assert GP.still_to_play([leg], {"games": games}, now=at) == [leg], "game two is still to play"
    assert GP.still_to_play([leg], {"games": [dict(g, live={"state": "final"}) for g in games]}, now=at) == []


def test_hockey_s_scorer_legs_of_a_started_game_are_dropped():
    # The rows as hockey's board carried them: no kickoff, no live, no started.
    board = {"date": "2026-11-17", "games": GAMES, "recommendations": [
        _row("Alex Ovechkin", "WSH", "TBL", "TBL", "WSH"), _row("Jordan Kyrou", "STL", "ANA", "STL", "ANA"),
        _row("Clayton Keller", "UTA", "VAN", "UTA", "VAN")]}
    got = GP.scorer_legs(board, "nhl", now=NOW)
    assert [l["player"] for l in got] == ["Jordan Kyrou"], got
    assert "return still_to_play(list(got.values()), board, now)" in (ROOT / "engine" / "gameparlays.py").read_text(
        encoding="utf-8"), "every priced leg passes the same check"


def test_hockey_rows_are_told_when_their_game_starts_and_whether_it_has():
    recs = [{"player": "Alex Ovechkin", "team": "WSH", "recommended": True, "grade": "A", "stake_units": 1.0,
             "edge_hunter": {"play": True, "passes": []}},
            {"player": "Jordan Kyrou", "team": "STL", "recommended": True, "grade": "A", "stake_units": 1.0},
            {"player": "Clayton Keller", "team": "UTA", "recommended": True, "grade": "B", "stake_units": 0.5}]
    n = nhl_build.stamp_started(recs, GAMES, "2026-11-17", now=NOW)
    ovi, kyrou, keller = recs
    assert n == 2
    assert ovi["kickoff"] == "2026-11-18T00:00:00Z" and ovi["live"] and ovi["started"]
    assert not ovi["recommended"] and ovi["grade"] == "Pass" and ovi["stake_units"] == 0.0
    assert ovi["edge_hunter"]["passes"] == [nhl_build.STARTED_PASS], "off the Edge board, saying why"
    assert kyrou["kickoff"] == "2026-11-18T02:00:00Z" and not kyrou["live"] and not kyrou["started"]
    assert kyrou["recommended"] and kyrou["grade"] == "A", "a game still to play keeps its pick"
    assert keller["started"] and not keller["live"], "started by its own clock"
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert "    stamp_started(recs, out[\"games\"], date)\n" in src, "the build tells every row, after the injuries"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
