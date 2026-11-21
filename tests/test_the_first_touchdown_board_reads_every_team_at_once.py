"""The first-touchdown board reads every team's usage in one pass
(engine/firsttd.teams_usage), not one walk of the game logs per team.

No index on player_game_logs leads with the team, so each team's read
walked the sport's rows for the five stats it needs across every stored
season, and the board asked twice a game: the first-touchdown board took
28 of the NFL build's 221 seconds at 08:25 on 8 November, and a college
Saturday asks for a hundred teams and more. What these hold:

  * every team's usage from the one read is exactly its own read — the
    same players, in the same order, to the last digit — this season and
    last, before a given week, a college box score's catches;
  * the answer does not depend on the order the rows were stored in (a
    catches-only game's volume is a fraction, so a sum's order could move
    a last digit, and two men sharing a short name are matched in it);
  * the board reads the logs once a season, not once a team, and prices
    exactly what it priced off the per-team reads;
  * a team with no rows reads empty, and an empty name is never asked for.

Run directly: `python3 tests/test_the_first_touchdown_board_reads_every_team_at_once.py`
"""
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, firsttd as F                                 # noqa: E402

TEAMS = ("DET", "MIN", "GB", "CHI")


def _hist():
    c = sqlite3.connect(":memory:")
    c.executescript(db.SCHEMA)
    return c


def _rows(sport="nfl"):
    """Two seasons of four teams: backs, receivers with targets, a receiver
    whose games carry catches and no targets (a fraction of volume), a man
    who changed teams, and two men on one team sharing a short name."""
    out = []
    rnd = random.Random(7)
    for season, weeks in ((2025, range(1, 18)), (2026, range(1, 10))):
        for wk in weeks:
            period = f"{wk:03d}"
            for t in TEAMS:
                game = f"{season}-{period}-{t}"
                cast = [(f"{t} Back", {"carries": rnd.randint(8, 22), "targets": rnd.randint(0, 5),
                                       "rush_td": rnd.randint(0, 2), "rec_td": 0}),
                        (f"{t} Wideout", {"targets": rnd.randint(4, 12), "receptions": rnd.randint(2, 4),
                                          "rec_td": rnd.randint(0, 1)}),
                        (f"{t} Slot", {"receptions": rnd.randint(1, 7), "rec_td": rnd.randint(0, 1)}),
                        ("J. Williams" if t == "DET" else f"{t} Tight End",
                         {"targets": rnd.randint(1, 6), "receptions": rnd.randint(1, 6), "rec_td": 0}),
                        ("Jameson Williams" if t == "DET" else f"{t} Fullback",
                         {"carries": rnd.randint(0, 3), "targets": rnd.randint(0, 9), "rush_td": 0,
                          "rec_td": rnd.randint(0, 1)})]
                if season == 2025 and t == "MIN":
                    cast.append(("Mover", {"carries": 20, "targets": 3, "rush_td": 2}))
                if season == 2026 and t == "GB":
                    cast.append(("Mover", {"carries": 11, "targets": 2, "rush_td": 1}))
                for player, stats in cast:
                    for m, v in stats.items():
                        out.append((sport, season, period, game, player, t, "OPP", "WR", 1, m, float(v)))
                    out.append((sport, season, period, game, player, t, "OPP", "WR", 1, "rec_yds", 40.0))
    return out


def _stored(rows):
    c = _hist()
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return c


def _one_team(c, sport, season, team, before_period=None):
    """The read as it was: one team's rows asked for by itself."""
    q = ("SELECT season, period, player, market, value FROM player_game_logs "
         "WHERE sport=? AND team=? AND season IN (?, ?) AND market IN (?,?,?,?,?)")
    rows = list(c.execute(q, [sport, team, season, season - 1, *F.TOUCH_MARKETS, *F.TD_MARKETS, F.REC_MARKET]))
    return F._usage_from(rows, sport, season, before_period)


def _exact(a, b):
    return list(a) == list(b) and all(
        list(a[p]) == list(b[p]) and all(a[p][k] == b[p][k] for k in a[p]) for p in a)


def test_one_read_gives_every_team_its_own_read_exactly():
    for sport in ("nfl", "cfb"):
        c = _stored(_rows(sport))
        for before in (None, "005"):
            every = F.teams_usage(c, sport, 2026, TEAMS, before_period=before)
            assert list(every) == sorted(TEAMS)
            for t in TEAMS:
                own = _one_team(c, sport, 2026, t, before)
                assert own and _exact(every[t], own), (sport, before, t)
                assert _exact(F.team_usage(c, sport, 2026, t, before_period=before), own)
        # His rows for this team only: the man who moved brings GB none of
        # his Minnesota volume.
        gb = F.teams_usage(c, sport, 2026, ["GB"])["GB"]
        assert gb["Mover"]["touch"] == 9 * 13, gb["Mover"]


def test_the_answer_does_not_depend_on_the_order_the_rows_were_stored():
    rows = _rows("cfb")
    shuffled = list(rows)
    random.Random(11).shuffle(shuffled)
    a = F.teams_usage(_stored(rows), "cfb", 2026, TEAMS)
    b = F.teams_usage(_stored(shuffled), "cfb", 2026, TEAMS)
    b_rev = F.teams_usage(_stored(list(reversed(rows))), "cfb", 2026, TEAMS)
    for t in TEAMS:
        assert _exact(a[t], b[t]) and _exact(a[t], b_rev[t]), t
    slot = a["DET"]["DET Slot"]["touch"]
    assert slot != int(slot), "a catches-only receiver's volume is a fraction — the case order moves"
    assert list(a["DET"]).index("J. Williams") < list(a["DET"]).index("Jameson Williams"), \
        "two men sharing a short name are listed in name order, whatever the file's order"


def _games():
    return [{"home": "DET", "away": "MIN", "spread": -3.5, "date": "2026-11-08", "kickoff": "13:00"},
            {"home": "GB", "away": "CHI", "spread": 2.5, "date": "2026-11-08", "kickoff": "16:25"}]


def _quotes():
    return {"det back": {"player": "DET Back", "home": "DET", "away": "MIN",
                         "quotes": [{"book": "FanDuel", "yes_odds": 450}]},
            "min wideout": {"player": "MIN Wideout", "home": "DET", "away": "MIN",
                            "quotes": [{"book": "DraftKings", "yes_odds": 900}]},
            "j williams": {"player": "J. Williams", "home": "DET", "away": "MIN",
                           "quotes": [{"book": "DraftKings", "yes_odds": 1400}]}}


def test_the_board_reads_the_logs_once_a_season_not_once_a_team():
    c = _stored(_rows("nfl"))
    reads = []
    c.set_trace_callback(lambda sql: reads.append(sql) if "FROM player_game_logs" in sql else None)
    b = F.board(_quotes(), _games(), sport="nfl", conn=c)
    c.set_trace_callback(None)
    assert len(reads) == 1, f"one read for four teams, not {len(reads)}"
    assert b["games"] == 1 and b["ours_games"] == 1 and b["quoted"] == 3, b
    # A slate across a season's turn reads each season once.
    reads.clear()
    c.set_trace_callback(lambda sql: reads.append(sql) if "FROM player_game_logs" in sql else None)
    F.board({}, _games() + [{"home": "DET", "away": "GB", "spread": 0, "date": "2027-01-03",
                              "kickoff": "13:00"}], sport="nfl", conn=c)
    c.set_trace_callback(None)
    assert len(reads) == 1, "January is still last season's"
    reads.clear()
    c.set_trace_callback(lambda sql: reads.append(sql) if "FROM player_game_logs" in sql else None)
    F.board({}, _games() + [{"home": "DET", "away": "GB", "spread": 0, "date": "2027-09-12",
                              "kickoff": "13:00"}], sport="nfl", conn=c)
    c.set_trace_callback(None)
    assert len(reads) == 2, "two seasons on one slate: one read each"


def test_the_board_prices_exactly_what_it_priced_off_the_per_team_reads():
    for sport in ("nfl", "cfb"):
        c = _stored(_rows(sport))
        now = F.board(_quotes(), _games(), sport=sport, conn=c)
        keep = F.teams_usage
        F.teams_usage = lambda conn, sp, season, teams, before_period=None: {
            t: _one_team(conn, sp, season, t, before_period) for t in sorted({t for t in teams if t})}
        try:
            was = F.board(_quotes(), _games(), sport=sport, conn=c)
        finally:
            F.teams_usage = keep
        assert now == was, sport
        assert now["rows"] and now["ours"], "both halves of the board were exercised"
        jw = next(r for r in now["rows"] if r["player"] == "J. Williams")
        assert jw["team"] == "DET"


def test_a_team_with_no_rows_reads_empty_and_an_empty_name_is_never_asked():
    c = _stored(_rows("nfl"))
    got = F.teams_usage(c, "nfl", 2026, ["DET", "NOBODY", None, ""])
    assert list(got) == ["DET", "NOBODY"] and got["NOBODY"] == {}
    assert F.teams_usage(c, "nfl", 2026, []) == {} and F.teams_usage(c, "nfl", 2026, [None]) == {}
    assert F.team_usage(c, "nfl", 2026, "NOBODY") == {} and F.team_usage(c, "nfl", 2026, None) == {}


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
