"""College football gets the NFL's scout: the same flags, in college numbers.

Ethan, 2026-10-09: "look at every single tool and every single data point
... we've added for NFL and add it for college football." The NFL's Most
Likely board has carried the scout's football read since 2026-10-03 —
seventeen flags a football person would raise, a correction the graded
record earns out of sample, and a five-season history replay. College had
none of it (likelyctx.SPORTS was the NFL alone).

College totals run about ten points above the NFL's and its spreads about
twice as wide, so the NFL's thresholds would call most college games a
shootout or a blowout — and a flag on more than half the record is never
judged. These check, one rule each: college reads its own numbers and the
NFL keeps its own; the sentences say the league's number; the board reads
the scout for college; the record and history joins read college's rows
only; the history store is per league and the NFL's file keeps its name.

Run directly: `python3 tests/test_the_college_scout.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyctx as C                                  # noqa: E402
from engine import scout as SC                                     # noqa: E402
from engine import scouthist as H                                  # noqa: E402


def _flags(league, **kw):
    base = dict(market="rush_yds", side="OVER", line=60.5, position="RB", values=[60] * 6)
    base.update(kw)
    return SC.flags(SC.situation(league=league, **base))


def test_college_reads_college_numbers_and_the_nfl_keeps_its_own():
    # A 56 total is an ordinary college game and a high NFL one.
    assert "shootout_under" in _flags("nfl", side="UNDER", total=56.0, game_spread=-3.0, home=True)
    assert "shootout_under" not in _flags("cfb", side="UNDER", total=56.0, game_spread=-3.0, home=True)
    assert "shootout_under" in _flags("cfb", side="UNDER", total=66.0, game_spread=-3.0, home=True)
    # A 10-point underdog trails all day in the NFL; in college it is a
    # Saturday like any other. A 21-point one trails in both.
    assert "dog_run_over" in _flags("nfl", game_spread=10.0, home=True, total=45.0)
    assert "dog_run_over" not in _flags("cfb", game_spread=10.0, home=True, total=55.0)
    assert "dog_run_over" in _flags("cfb", game_spread=21.0, home=True, total=55.0)
    # A 14-point favourite is a blowout in the NFL, not in college.
    assert "blowout_over" in _flags("nfl", game_spread=-14.0, home=True, total=45.0)
    assert "blowout_over" not in _flags("cfb", game_spread=-14.0, home=True, total=55.0)
    # The player flags are the same in both leagues.
    for lg in ("nfl", "cfb"):
        assert "back_from_absence" in _flags(lg, missed_last=True)
        assert "thin_sample" in _flags(lg, games_season=2)
    # Every college number is its own, and the NFL's are untouched.
    assert SC.threshold("SHOOTOUT_TOTAL", "nfl") == SC.SHOOTOUT_TOTAL == 49.0
    assert SC.threshold("SHOOTOUT_TOTAL", "cfb") > SC.SHOOTOUT_TOTAL
    assert SC.threshold("WIND", "cfb") == SC.WIND, "wind is wind in either league"


def test_the_sentence_says_the_leagues_number():
    nfl = SC.notes(["low_implied_td"], "nfl")[0]
    cfb = SC.notes(["low_implied_td"], "cfb")[0]
    assert "under 18" in nfl and "under 20" in cfb
    assert SC.note("back_from_absence", "cfb") == SC.FLAGS["back_from_absence"]
    # And the threshold behind it is the one the sentence names.
    assert SC.threshold("LOW_IMPLIED", "cfb") == 20.0


def test_the_board_reads_the_scout_for_college():
    assert "cfb" in C.SPORTS and "nfl" in C.SPORTS
    src = open(os.path.join(ROOT, "engine", "likelyboard.py"), encoding="utf-8").read()
    assert "_ctx.annotate(_rows, result, sport)" in src, "the board must tell the scout its league"
    games = [{"home": "UGA", "away": "VAN", "spread": -24.5, "total": 58.5, "kickoff": "2026-10-10T19:30:00Z",
              "weather": {"dome": False, "wind_mph": 6}}]
    recs = [{"player": "Back Dawg", "team": "VAN", "logs": [{"week": 4}, {"week": 5}]},
            {"player": "Other", "team": "VAN", "logs": [{"week": 6}]}]
    rows = [{"player": "Back Dawg", "team": "VAN", "opponent": "UGA", "market": "rush_yds", "side": "OVER",
             "line": 45.5, "odds": -125, "model_prob": 0.64, "recent_values": [48, 50, 46, 47, 49, 52]}]
    C.annotate(rows, {"games": games, "recommendations": recs}, "cfb")
    flags = rows[0]["scout_flags"]
    assert "dog_run_over" in flags, flags            # a 24.5-point college dog trails all day
    assert "back_from_absence" in flags, flags       # his team played week 6, he last played week 5
    assert "blowout_over" not in flags, "a 24.5 spread is not a college blowout (28)"
    assert rows[0]["model_prob"] == 0.64, "the read moves no number"


def _hist(path):
    from engine import db
    c = db.connect(path)
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                      ("cfb", 2026, "5", "VAN@UGA", "UGA", "VAN", 41, 10, -24.5, 58.5, "2026-10-04"),
                      ("cfb", 2026, "4", "UGA@ALA", "ALA", "UGA", 24, 28, -3.0, 52.5, "2026-09-27"),
                      ("nfl", 2026, "5", "LV@KC", "KC", "LV", 30, 17, -9.5, 51.0, "2026-10-05")])
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                      ("cfb", 2026, "4", "UGA@ALA", "Dawg Back", "UGA", "ALA", "RB", 0, "rush_yds", 88),
                      ("nfl", 2026, "5", "LV@KC", "Dawg Back", "LV", "KC", "RB", 0, "rush_yds", 40)])
    c.commit()
    return c


def test_the_history_join_reads_only_its_own_league():
    d = tempfile.mkdtemp()
    c = _hist(os.path.join(d, "h.db"))
    c.row_factory = sqlite3.Row
    games, by_team, logs = C.history_index(c, {"Dawg Back"}, "cfb")
    assert {g["raw_id"] for g in games.values()} == {"VAN@UGA", "UGA@ALA"}
    assert [r["value"] for r in logs["Dawg Back"]] == [88], "an NFL log must never feed a college pick"
    games, _, logs = C.history_index(c, {"Dawg Back"}, "nfl")
    assert {g["raw_id"] for g in games.values()} == {"LV@KC"} and [r["value"] for r in logs["Dawg Back"]] == [40]


def test_a_settled_college_pick_finds_its_game_with_college_numbers():
    d = tempfile.mkdtemp()
    c = _hist(os.path.join(d, "h.db"))
    c.row_factory = sqlite3.Row
    games, by_team, logs = C.history_index(c, {"Dawg Back"}, "cfb")
    pick = {"player": "Dawg Back", "team": "UGA", "market": "rush_yds", "side": "UNDER", "line": 80.5,
            "day": "2026-10-04"}
    s = C.context(pick, games, by_team, logs, "cfb")
    assert s and s["league"] == "cfb" and s["spread"] == -24.5 and s["total"] == 58.5
    assert "fav_run_under" in SC.flags(s), "a 24.5-point college favourite runs the clock out (17+)"


def test_the_history_store_is_per_league_and_the_nfls_keeps_its_name():
    assert H._store("nfl").name == "scout_history.json", "the box's NFL file is read as it is"
    assert H._store("cfb").name == "cfb_scout_history.json"
    d = Path(tempfile.mkdtemp())
    H.save({"back_from_absence": {"rush_yds OVER": {"shift": -0.05, "n": 300, "gaps": [-0.05, -0.06]}}},
           [2024, 2025], path=d / "x.json", sport="cfb")
    assert H.load(d / "x.json", sport="cfb")["flags"]["back_from_absence"]
    src = open(os.path.join(ROOT, "engine", "likelyctx.py"), encoding="utf-8").read()
    assert "scouthist.load(sport=sport)" in src, "the board must read its own league's history"


def test_the_replay_and_its_share_check_run_on_college():
    d = tempfile.mkdtemp()
    c = _hist(os.path.join(d, "h.db"))
    c.row_factory = sqlite3.Row
    h = H.replay(c, sport="cfb")
    assert isinstance(h.get("flags"), dict)
    shares = H.threshold_shares(c, "cfb")
    total_check = next(v for k, v in shares.items() if k.startswith("total >="))
    assert total_check == (0.0, 2), "neither stored college total reaches 63"
    nfl_check = next(v for k, v in H.threshold_shares(c, "nfl").items() if k.startswith("total >="))
    assert nfl_check == (1.0, 1), "the NFL's 51 is a shootout at 49"



def _box_shaped_hist(path):
    """College as the box stores it (2026-10-09): the kickoff date in
    ``period``, ``date`` empty, games keyed "AWAY@HOME", the player logs
    keyed by the play-by-play's numeric id. The first runs on the box
    joined none of it: the replay found no seasons and 0 of 689 picks met
    their game."""
    from engine import db
    c = db.connect(path)
    games, logs = [], []
    days = ["2025-09-06", "2025-09-13", "2025-09-20", "2025-09-27", "2025-10-04", "2025-10-11", "2025-10-18"]
    for i, day in enumerate(days):
        games.append(("cfb", 2025, day, f"OPP{i}@UGA", "UGA", f"OPP{i}", 35, 14, -14.5, 55.5, None))
        logs.append(("cfb", 2025, day, f"40100{i}", "Dawg Back", "UGA", f"OPP{i}", "RB", 1, "rush_yds",
                     80.0 + i))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    c.row_factory = sqlite3.Row
    return c


def test_college_games_are_found_by_the_date_in_their_period():
    c = _box_shaped_hist(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, by_team, logs = C.history_index(c, {"Dawg Back"}, "cfb")
    assert len(games) == 7, "a college game with its date in period was dropped"
    assert len(logs["Dawg Back"]) == 7, "the logs' numeric ids must meet the games on season, day and team"
    pick = {"player": "Dawg Back", "team": "UGA", "market": "rush_yds", "side": "OVER", "line": 85.5,
            "day": "2025-10-18"}
    s = C.context(pick, games, by_team, logs, "cfb")
    assert s is not None and s["spread"] == -14.5 and s["games_season"] == 6, s
    h = H.replay(c, sport="cfb")
    assert h["seasons"] == [2025], "the replay must score college's stored season"

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
