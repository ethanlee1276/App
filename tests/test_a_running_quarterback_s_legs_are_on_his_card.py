"""A quarterback who runs has his legs on his matchup card (engine/gamescan
.player_read, QB_RUNS_CARRIES; engine/gamereport._role_line, _why,
form_season, form_game).

Ethan, 12 November 2026, the Commanders at the Giants: "we should have QB
rushing yards in the matchup report as well." Jayden Daniels' card read
him only as a passer: his passing work, the Giants' pass defense, his
passing lines. What these hold:

  * a quarterback with three carries or fifteen rushing yards a game has
    them said, on his read and in his card's role line, beside his pass
    attempts;
  * what the defence gives up to quarterbacks on the ground is said under
    him at any rank (college, with no such rating, says its run defense);
  * it is said, never counted: in the NFL that rating measured nothing
    beyond his own form (engine/defensevs.MODEL_STAT), so his verdict stays
    the passing read and none of his rushing markets is leaned;
  * a pocket passer gets none of it;
  * his season and game lines give his carries with his rushing yards.

Run directly: `python3 tests/test_a_running_quarterback_s_legs_are_on_his_card.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamereport as R                                   # noqa: E402
from engine import gamescan as G                                     # noqa: E402

ALLOWED = {"qb_pass_yds": {"rank": 30, "of": 32, "pg": 189.0},
           "qb_rush_yds": {"rank": 4, "of": 32, "pg": 31.2}}


def _qb(name, usage, allowed=ALLOWED, ratings=None, team="WAS", opp="NYG"):
    return G.player_read(name, team, opp, "QB", usage=usage, ratings=ratings or {}, room={},
                         scheme={}, split={}, tackling={}, line_out=[], mates_out=[],
                         allowed=allowed, points=20.0 if allowed else None)


DANIELS = {"games": 7, "attempts_pg": 31.4, "carries_pg": 6.4, "rush_yds_pg": 41.3}


def test_a_running_quarterback_has_his_legs_said_and_never_counted():
    x = _qb("Jayden Daniels", DANIELS)
    assert x["role"] == ["Runs 6.4 times a game for 41 yards"], x["role"]
    ground = [n for n in x["notes"] if n.startswith("On the ground:")]
    assert ground == ["On the ground: NYG gives up 31 rushing yards a game to quarterbacks — "
                      "the 4th-most of 32"], ground
    # Never counted: the verdict is the passing read's, and no rushing
    # market is leaned (the rating measured nothing in the NFL).
    assert x["pro"] == [] and x["con"] == ["NYG gives up the 3rd-fewest passing yards (189 a game)"]
    assert x["read"] == "tough"
    assert not {"rush_yds", "rush_att"} & set(x["lean"]), x["lean"]
    stingy = dict(ALLOWED, qb_rush_yds={"rank": 31, "of": 32, "pg": 9.0})
    y = _qb("Jayden Daniels", DANIELS, allowed=stingy)
    assert "On the ground: NYG gives up 9 rushing yards a game to quarterbacks — the 2nd-fewest of 32" \
        in y["notes"]
    assert (y["read"], y["pro"], y["con"]) == (x["read"], x["pro"], x["con"])


def test_a_pocket_passer_gets_none_of_it():
    x = _qb("Jared Goff", {"games": 8, "attempts_pg": 33.0, "carries_pg": 1.6, "rush_yds_pg": 2.1},
            team="DET", opp="GB")
    assert x["role"] == [] and not any(n.startswith("On the ground:") for n in x["notes"])
    assert R._role_line(x) == "33 pass attempts a game"


def test_college_says_the_run_defense():
    x = _qb("Arch Manning", {"games": 8, "carries_pg": 7.0, "rush_yds_pg": 38.0}, allowed=None,
            ratings={"UGA": {"def": {"rushing": {"rank": 5}}}}, team="TEX", opp="UGA")
    assert x["role"] == ["Runs 7 times a game for 38 yards"]
    assert "On the ground: UGA's run defense ranks 5th" in x["notes"]
    assert x["pro"] == [] and x["con"] == [], "said, not counted"


def test_the_card_carries_his_legs():
    x = _qb("Jayden Daniels", DANIELS)
    assert x["usage"]["attempts_pg"] == 31.4
    assert R._role_line(x) == "31.4 pass attempts a game, 6.4 carries for 41 rushing yards a game"
    why = R._why(x)
    assert "On the ground: NYG gives up 31 rushing yards a game to quarterbacks — the 4th-most of 32" in why
    assert not any(w.startswith("Runs ") for w in why), "his own work is on the role line, once"


def test_his_lines_give_his_carries():
    season = {"games": 7, "s": {"pass_cmp": 140, "pass_att": 220, "pass_yds": 1450, "pass_td": 10,
                                "pass_int": 3, "rush_att": 45, "rush_yds": 290, "rush_td": 2}}
    assert R.form_season("qb", season) == ("7 games: 1,450 yds (207 a game), 64% completed, 10 TD, "
                                           "3 INT, 45 carries for 290 rushing yds (41 a game), "
                                           "2 rushing TD")
    game = {"s": {"pass_cmp": 20, "pass_att": 31, "pass_yds": 210, "pass_td": 1, "pass_int": 0,
                  "rush_att": 8, "rush_yds": 52, "rush_td": 1}}
    assert R.form_game("qb", game) == "20 of 31, 210 yds, 1 TD, 0 INT, 8 carries for 52 rush yds, 1 rush TD"
    # College logs its carries as "carries".
    college = {"s": {"pass_att": 28, "pass_yds": 240, "pass_td": 2, "carries": 11, "rush_yds": 61}}
    assert "11 carries for 61 rush yds" in R.form_game("qb", college)
    # A quiet day on his feet stays off the line, as before.
    quiet = {"s": {"pass_cmp": 22, "pass_att": 30, "pass_yds": 250, "pass_td": 2, "pass_int": 1,
                   "rush_att": 2, "rush_yds": 4}}
    assert "carr" not in R.form_game("qb", quiet)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
