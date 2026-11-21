"""The NBA board's slow reads are kept between builds until what they read
changes (engine/firstbasket.read; engine/nba/shooting.longrun,
rates.longrun; engine/nba/teams.board_profiles; engine/logcache).

The NBA build's parts at 09:34 on 9 November: first basket 9.8 seconds,
the shooting read 4.4, the rates read 3.7 and the team profiles 4.3, every
build reading the same two seasons again. What these hold:

  * each comes back the same through the cache as off the table, and is
    served the second time;
  * first basket reads again when a shot, an opening tip or a box score is
    stored, and for another day;
  * the two long reads read again for another slate's names or a new box
    score, and the WNBA keeps its own;
  * the team profiles read again for another day or a new box score.

Run directly: `python3 tests/test_the_nba_boards_reads_are_kept.py`
"""
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, firstbasket as FB, logcache                  # noqa: E402
from engine.nba import rates as R, shooting as S, teams as T        # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own, with the
    cache switched on for that file (it is not the production one)."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.keep = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.dir, "feedstate")
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        self.enabled = logcache.enabled_for
        logcache.enabled_for = lambda conn: True
        return self

    def __exit__(self, *exc):
        logcache.enabled_for = self.enabled
        self.conn.close()
        if self.keep is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)


CLUBS = {"BOS": ["Jayson Tatum", "Jaylen Brown", "Derrick White", "Jrue Holiday", "Al Horford",
                 "Sam Hauser"],
         "NYK": ["Jalen Brunson", "Josh Hart", "Mikal Bridges", "OG Anunoby", "Karl-Anthony Towns",
                 "Miles McBride"]}
MARKETS = ("min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm",
           "fta", "oreb")


def _season(conn, sport="nba", games=8, seed=3):
    """Eight BOS-NYK nights: box scores for every man, the opening shots and
    the opening tip."""
    rnd = random.Random(seed)
    logs, shots, tips = [], [], []
    for i in range(games):
        gid, day = f"{sport}{i}", f"2026-10-{20 + i:02d}"
        for team, opp in (("BOS", "NYK"), ("NYK", "BOS")):
            for k, p in enumerate(CLUBS[team]):
                for m in MARKETS:
                    v = {"min": 34 - 4 * k, "fga": 14 - k, "fgm": 6 - k // 2, "fg3a": 6 - k // 2,
                         "fg3m": 2, "fta": 4, "ftm": 3}.get(m, rnd.randint(0, 9))
                    logs.append({"sport": sport, "season": 2026, "period": day, "game_id": gid,
                                 "player": p, "team": team, "opponent": opp,
                                 "position": "S" if k < 5 else "B", "home": int(team == "BOS"),
                                 "market": m, "value": float(max(0, v))})
        a = 1
        for team, opp in (("BOS", "NYK"), ("NYK", "BOS")):
            for who in CLUBS[team][:3]:
                shots.append({"game_id": gid, "action": a, "season": 2026, "date": day, "player": who,
                              "team": team, "opponent": opp, "home": int(team == "BOS"), "period": 1,
                              "clock": f"11:{50 - a:02d}", "kind": "2pt", "made": int(a % 3 == 0)})
                a += 1
        tips.append({"game_id": gid, "season": 2026, "date": day, "home": "BOS", "away": "NYK",
                     "home_jumper": "Al Horford", "away_jumper": "Karl-Anthony Towns",
                     "third": "BOS" if i % 2 else "NYK"})
    db.upsert_player_logs(conn, logs)
    if sport == "nba":
        db.upsert_nba_shots(conn, shots)
        db.upsert_nba_tips(conn, tips)
    conn.commit()


def _note(name, sport="nba"):
    return logcache.status().get(f"{name}.{sport}") or {}


def _box(conn, sport="nba", day="2026-10-31"):
    db.upsert_player_logs(conn, [{"sport": sport, "season": 2026, "period": day, "game_id": "late",
                                  "player": "Jayson Tatum", "team": "BOS", "opponent": "NYK",
                                  "position": "S", "home": 1, "market": "pts", "value": 41.0}])
    conn.commit()


def test_first_basket_is_kept_and_read_again_when_a_shot_a_tip_or_a_box_score_lands():
    with _Sandbox() as sb:
        _season(sb.conn)
        want = FB._read(sb.conn, 2026, "2026-11-01")
        assert want["usage"] and want["tip"], "the read has shots and tips to give"
        assert FB.read(sb.conn, 2026, "2026-11-01") == want
        assert FB.read(sb.conn, 2026, "2026-11-01") == want
        assert _note("firstbasket2026")["kept"] is True
        db.upsert_nba_shots(sb.conn, [{"game_id": "nba3", "action": 99, "season": 2026, "date": "2026-10-23",
                                       "player": "Jaylen Brown", "team": "BOS", "opponent": "NYK", "home": 1,
                                       "period": 1, "clock": "11:58", "kind": "3pt", "made": 1}])
        sb.conn.commit()
        assert FB.read(sb.conn, 2026, "2026-11-01") == FB._read(sb.conn, 2026, "2026-11-01")
        assert _note("firstbasket2026")["why"] == "inputs changed", "a new shot"
        db.upsert_nba_tips(sb.conn, [{"game_id": "nba3", "season": 2026, "date": "2026-10-23", "home": "BOS",
                                      "away": "NYK", "home_jumper": "Jayson Tatum",
                                      "away_jumper": "Karl-Anthony Towns", "third": "NYK"}])
        sb.conn.commit()
        assert FB.read(sb.conn, 2026, "2026-11-01") == FB._read(sb.conn, 2026, "2026-11-01")
        assert _note("firstbasket2026")["why"] == "inputs changed", "a tip stored again"
        _box(sb.conn)
        assert FB.read(sb.conn, 2026, "2026-11-01") == FB._read(sb.conn, 2026, "2026-11-01")
        assert _note("firstbasket2026")["why"] == "rows changed", "a box score (the lineups)"
        assert FB.read(sb.conn, 2026, "2026-10-25") == FB._read(sb.conn, 2026, "2026-10-25")
        assert _note("firstbasket2026")["why"] == "inputs changed", "another day"


def test_the_long_reads_are_kept_per_slate_and_per_league():
    with _Sandbox() as sb:
        _season(sb.conn)
        _season(sb.conn, sport="wnba", seed=4)
        names = CLUBS["BOS"] + CLUBS["NYK"][:2]
        other = CLUBS["NYK"]
        for mod, name in ((S, "nba_shooting_long60"), (R, "nba_rates_long60")):
            want = mod._longrun(sb.conn, "nba", names)
            assert want and mod.longrun(sb.conn, "nba", reversed(names)) == want, name
            assert mod.longrun(sb.conn, "nba", names) == want
            assert _note(name)["kept"] is True, "the same slate in any order"
            assert mod.longrun(sb.conn, "nba", other) == mod._longrun(sb.conn, "nba", other)
            assert _note(name)["why"] == "inputs changed", "another slate"
            assert mod.longrun(sb.conn, "nba", []) == {}
            wnba = mod.longrun(sb.conn, "wnba", names)
            assert wnba == mod._longrun(sb.conn, "wnba", names) and wnba != want, "each league its own"
        _box(sb.conn)
        for mod, name in ((S, "nba_shooting_long60"), (R, "nba_rates_long60")):
            assert mod.longrun(sb.conn, "nba", other) == mod._longrun(sb.conn, "nba", other)
            assert _note(name)["why"] == "rows changed"
            assert mod.longrun(sb.conn, "wnba", names) == mod._longrun(sb.conn, "wnba", names)
            assert _note(name, "wnba")["kept"] is True, "an NBA box score leaves the WNBA's alone"


def test_the_team_profiles_are_kept_for_the_day():
    with _Sandbox() as sb:
        _season(sb.conn)

        def plain(day):
            return T.build(T.load_rows(sb.conn, "nba", 2026), T.load_rows(sb.conn, "nba", 2025), "nba",
                           before=day)
        want = plain("2026-11-01")
        assert T.board_profiles(sb.conn, "nba", "2026-11-01") == want
        assert T.board_profiles(sb.conn, "nba", "2026-11-01") == want
        assert _note("nba_team_profiles")["kept"] is True
        assert T.board_profiles(sb.conn, "nba", "2026-11-02") == plain("2026-11-02")
        assert _note("nba_team_profiles")["why"] == "inputs changed", "another day"
        _box(sb.conn)
        assert T.board_profiles(sb.conn, "nba", "2026-11-02") == plain("2026-11-02")
        assert _note("nba_team_profiles")["why"] == "rows changed"


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
