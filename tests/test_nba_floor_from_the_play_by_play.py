"""Who was on the floor, every second: stints from the play-by-play
(engine/nba/stints).

The NBA lab (docs/NBA_LAB.md) rebuilt every game of 2024-25 and 2025-26
with this parser — 2,459 of 2,460 games clean, every team's floor time
exactly five players for the game's length, and the players' points summing
to every final score — and measured the board's new tools on them. These
hold the parser's rules on a game small enough to check by hand:

  * a quarter's five are whoever acts before being subbed in;
  * the between-quarter changes, logged at the start of the next quarter,
    are applied before it starts (subbed in there is on, subbed out is off);
  * every second goes to exactly five players a side;
  * each stint's counts belong to the floor that played it (the stint is
    closed BEFORE a substitution changes the floor);
  * the box score it derives adds up to the final score, and the officials
    who called fouls are kept.

Run directly: `python3 tests/test_nba_floor_from_the_play_by_play.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.nba import stints as S                          # noqa: E402

HOME, AWAY = "HOM", "AWY"


def _a(order, period, clock, typ, sub=None, pid=0, team="", **kw):
    row = {"orderNumber": order, "actionNumber": order, "period": period,
           "clock": f"PT{clock[0]:02d}M{clock[1]:02d}.00S", "actionType": typ,
           "subType": sub or "", "personId": pid, "teamTricode": team,
           "scoreHome": kw.pop("h", 0), "scoreAway": kw.pop("aw", 0)}
    row.update(kw)
    return row


def _game():
    return [
        _a(1, 1, (12, 0), "period", "start"),
        _a(2, 1, (11, 56), "jumpball", "recovered", 1, HOME,
           jumpBallWonPersonId=1, jumpBallLostPersonId=11),
        _a(3, 1, (11, 40), "2pt", "Layup", 2, HOME, h=2, shotResult="Made", assistPersonId=3),
        _a(4, 1, (11, 20), "3pt", "Jump Shot", 12, AWAY, h=2, shotResult="Missed"),
        _a(5, 1, (11, 18), "rebound", "defensive", 4, HOME, h=2),
        _a(6, 1, (11, 0), "foul", "personal", 13, AWAY, h=2, foulDrawnPersonId=5, officialId=900),
        _a(7, 1, (11, 0), "freethrow", "1 of 2", 5, HOME, h=3, shotResult="Made"),
        _a(8, 1, (11, 0), "freethrow", "2 of 2", 5, HOME, h=3, shotResult="Missed"),
        _a(9, 1, (10, 58), "rebound", "defensive", 14, AWAY, h=3),
        _a(10, 1, (10, 30), "2pt", "Jump Shot", 15, AWAY, h=3, aw=2, shotResult="Made"),
        _a(11, 1, (6, 0), "substitution", "out", 2, HOME, h=3, aw=2),
        _a(12, 1, (6, 0), "substitution", "in", 6, HOME, h=3, aw=2),
        _a(13, 1, (5, 0), "2pt", "Jump Shot", 6, HOME, h=5, aw=2, shotResult="Made"),
        _a(14, 1, (0, 0), "period", "end", h=5, aw=2),
        # between the quarters, logged in quarter 2 before its start
        _a(15, 2, (12, 0), "substitution", "out", 6, HOME, h=5, aw=2),
        _a(16, 2, (12, 0), "substitution", "in", 2, HOME, h=5, aw=2),
        _a(17, 2, (12, 0), "period", "start", h=5, aw=2),
        _a(18, 2, (11, 0), "3pt", "Jump Shot", 2, HOME, h=8, aw=2, shotResult="Made", assistPersonId=1),
        _a(19, 2, (0, 0), "period", "end", h=8, aw=2),
    ]


def test_the_quarters_five_are_read_and_the_between_quarter_changes_applied():
    g = S.rebuild(_game())
    assert (g["home"], g["away"]) == (HOME, AWAY)
    assert g["quality"]["ok"], g["quality"]
    first, second, third = g["stints"][:3]
    assert sorted(first["floor"][HOME]) == ["1", "2", "3", "4", "5"]
    assert sorted(first["floor"][AWAY]) == ["11", "12", "13", "14", "15"]
    assert sorted(second["floor"][HOME]) == ["1", "3", "4", "5", "6"], "6 in for 2 at 6:00"
    assert sorted(third["floor"][HOME]) == ["1", "2", "3", "4", "5"], "2 back for quarter 2, 6 off"
    assert (first["t0"], first["t1"], second["t1"], third["t1"]) == (0, 360, 720, 1440)


def test_every_second_goes_to_five_players_a_side():
    g = S.rebuild(_game())
    p = g["players"]
    assert p["2"]["sec"] == 1080 and p["6"]["sec"] == 360 and p["1"]["sec"] == 1440
    for team in (HOME, AWAY):
        assert sum(ln["sec"] for ln in p.values() if ln["team"] == team) == 5 * g["game_sec"]


def test_the_box_score_adds_up_to_the_final_and_each_stint_owns_its_counts():
    g = S.rebuild(_game())
    p = g["players"]
    assert sum(ln["pts"] for ln in p.values() if ln["team"] == HOME) == 8
    assert sum(ln["pts"] for ln in p.values() if ln["team"] == AWAY) == 2
    assert (p["2"]["pts"], p["5"]["pts"], p["6"]["pts"]) == (5, 1, 2)
    assert (p["3"]["ast"], p["1"]["ast"], p["4"]["dreb"], p["14"]["dreb"]) == (1, 1, 1, 1)
    first, second, third = g["stints"][:3]
    assert first["lines"]["2"]["pts"] == 2 and third["lines"]["2"]["pts"] == 3
    assert second["lines"]["6"]["pts"] == 2, "the floor that played the stint owns its counts"
    assert "2" not in second["lines"]


def test_the_floor_around_him_and_the_crew():
    g = S.rebuild(_game())
    one = g["players"]["1"]
    assert one["on_team_fgm"] == 3 and one["on_opp_miss"] == 1
    assert one["on_team_miss"] == 1, "a missed last free throw is a live rebound"
    assert g["officials"] == ["900"]
    assert all(ln["garbage_sec"] == 0 for ln in g["players"].values())
    assert S.possessions(one) > 0


def test_a_csv_row_reads_like_the_json_and_bad_rows_do_not_stop_it():
    rows = [{k: ("" if v is None else str(v)) for k, v in a.items()} for a in _game()]
    g = S.rebuild(rows)
    assert g["quality"]["ok"] and g["players"]["2"]["pts"] == 5
    assert S.clock_s("PT11M56.00S") == 716.0 and S.clock_s(None) == 0.0
    assert S.elapsed(5, 300) == 2880 and S.elapsed(1, 0) == 720
    assert S.rebuild([None, "x"])["players"] == {}


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
