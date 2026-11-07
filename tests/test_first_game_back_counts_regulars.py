"""History's "first game back" counts a regular's return, never a backup's.

Ethan, 2026-10-10, on college's first saved history: quarterback
pass-attempt overs in a player's first game back proved at -35% and pass
yards at -28% — far too big for a starter back from an injury. The flag
means his team played its last game without him, which in the stored logs
is also every backup who simply did not get in; a backup's "return" is
mop-up work after a line built on spot starts. "yes make that fix."

These check, one rule each: a return is scored only for a player who was a
regular in the five games his line is built from (the top passer; a top-two
back by carries; a top-three player by catches) IN THE RETURN'S SEASON AND
FOR ITS TEAM — decided from those games, never from the return game (the
first version also counted last season's starts, and college's QB number
grew to -40%: last November's starter, a backup now, "returning" in mop-up); a part-timer's return is left out of the replay
altogether; a quarterback's rushing and a back's catches are judged on
their own jobs; ties at the cut all count; the dry run says how many of
each it scored.

Run directly: `python3 tests/test_first_game_back_counts_regulars.py`
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import scouthist as H                                   # noqa: E402

DAYS = ["2025-09-06", "2025-09-13", "2025-09-20", "2025-09-27", "2025-10-04", "2025-10-11", "2025-10-18",
        "2025-10-25"]


def _hist():
    """College as the box stores it: the date in ``period``, games keyed
    "AWAY@HOME", logs keyed by a numeric id. UGA's starter QB1 misses the
    sixth game and comes back with a bad one; the backup QB2, who only
    mopped up before, misses it too and comes back with a big one."""
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, logs = [], []

    def log(i, player, att, yds):
        logs.append(("cfb", 2025, DAYS[i], f"40100{i}", player, "UGA", f"OPP{i}", "QB", 1, "pass_att", att))
        logs.append(("cfb", 2025, DAYS[i], f"40100{i}", player, "UGA", f"OPP{i}", "QB", 1, "pass_yds", yds))

    for i, day in enumerate(DAYS):
        games.append(("cfb", 2025, day, f"OPP{i}@UGA", "UGA", f"OPP{i}", 35, 14, -14.5, 55.5, None))
        if i < 5:
            log(i, "UGA QB1", 30, 240)
            log(i, "UGA QB2", 3, 20)
        elif i == 5:
            log(i, "UGA QB3", 30, 230)          # both missed this one
        elif i == 6:
            log(i, "UGA QB1", 2, 10)            # the starter's return: a bad game
            log(i, "UGA QB2", 40, 300)          # the backup's: a big one
        else:
            log(i, "UGA QB1", 30, 240)
            log(i, "UGA QB2", 3, 20)
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    c.row_factory = sqlite3.Row
    return c


def test_a_starters_return_counts_and_a_backups_does_not_whatever_the_game():
    h = H.replay(_hist(), sport="cfb")
    # QB1's pass attempts and yards (2 rows) are scored; QB2's (2) are left
    # out — and neither decision read the return game, where the starter
    # threw twice and the backup forty times.
    assert h["first_game_back"] == {"kept": 2, "skipped": 2}, h["first_game_back"]


def test_last_seasons_starter_is_not_this_seasons_regular():
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    last = ["2024-10-26", "2024-11-02", "2024-11-09", "2024-11-16", "2024-11-23"]
    games, logs = [], []
    for i, day in enumerate(last):         # he started every game last November
        games.append(("cfb", 2024, day, f"L{i}@UGA", "UGA", f"L{i}", 30, 20, -7.5, 52.5, None))
        logs.append(("cfb", 2024, day, f"50100{i}", "UGA QB9", "UGA", f"L{i}", "QB", 1, "pass_att", 32))
    this = ["2025-09-06", "2025-09-13", "2025-09-20"]
    for i, day in enumerate(this):         # a backup now: did not play the first two, mops up the third
        games.append(("cfb", 2025, day, f"N{i}@UGA", "UGA", f"N{i}", 45, 10, -24.5, 58.5, None))
        logs.append(("cfb", 2025, day, f"60100{i}", "UGA QB1", "UGA", f"N{i}", "QB", 1, "pass_att", 30))
    logs.append(("cfb", 2025, this[2], "601002", "UGA QB9", "UGA", "N2", "QB", 1, "pass_att", 4))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    c.row_factory = sqlite3.Row
    h = H.replay(c, sport="cfb")
    assert h["first_game_back"] == {"kept": 0, "skipped": 1}, h["first_game_back"]


def test_each_market_is_judged_on_the_job_it_belongs_to():
    assert H.role_group("pass_att", "QB") == "pass"
    assert H.role_group("rush_yds", "QB") == "pass", "a quarterback's rushing is his starting job"
    assert H.role_group("rush_yds", "RB") == "rush"
    assert H.role_group("receptions", "RB") == "rush", "a back's catches come with his backfield job"
    assert H.role_group("rec_yds", "TE") == "catch"
    assert H.role_group("anytime_td", "WR") == "catch"
    assert H.role_group("anytime_td", "") is None, "no position: any of the three jobs"


def _row(team, gid, value):
    return ("2025-09-06", value, team, "WR", {"game_id": gid}, 2025)


def test_ties_at_the_cut_all_count_and_three_of_five_makes_a_regular():
    series = {("A", "receptions"): [_row("UGA", "g1", 6)], ("B", "receptions"): [_row("UGA", "g1", 5)],
              ("C", "receptions"): [_row("UGA", "g1", 4)], ("D", "receptions"): [_row("UGA", "g1", 4)],
              ("E", "receptions"): [_row("UGA", "g1", 1)]}
    top = H.team_leaders(series)
    assert top[("UGA", "g1", "catch")] == {"A", "B", "C", "D"}, "a tie for third keeps both"
    window = [_row("UGA", f"g{k}", 0) for k in range(1, 6)]
    assert not H.is_regular("D", window, "catch", {k: {"D"} for k in (("UGA", "g1", "catch"),
                                                                       ("UGA", "g2", "catch"),
                                                                       ("UGA", "g3", "catch"))},
                            season=2026), "last season's games do not make this season's regular"
    leaders = {("UGA", "g1", "catch"): {"D"}, ("UGA", "g2", "catch"): {"D"}, ("UGA", "g3", "catch"): {"D"}}
    assert H.is_regular("D", window, "catch", leaders)
    leaders.pop(("UGA", "g3", "catch"))
    assert not H.is_regular("D", window, "catch", leaders), "two of five is a part-timer"
    assert H.is_regular("D", window, None, {**leaders, ("UGA", "g4", "rush"): {"D"}}), \
        "no position: any job counts"


def test_the_dry_run_says_how_many_of_each_it_scored():
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    assert "returns by regulars scored" in src and "by part-timers left out" in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
