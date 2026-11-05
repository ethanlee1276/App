"""First basket's team half reads the opening tip by its two jumpers
(engine/firstbasket.tips / tip_read; engine/nba/shots.fold_espn_tip).

Measured on the lab's two full seasons (docs/NBA_LAB.md, "First basket, the
opening tip"): the club's own tip record with the box study's home lean read
WORSE than a coin on who takes the first shot (0.708 and 0.698 against
0.693); each jumper's record, the home lean and the tip's conversion fitted
on the other season, read 0.676 and 0.664, and who scores first 0.694 ->
0.687 and 0.688 -> 0.685.

Run directly: `python3 tests/test_first_basket_opening_tip.py`
"""
import datetime as dt
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import firstbasket as FB                          # noqa: E402
from engine.nba import shots as S                               # noqa: E402


# --- the feed's opening jump ----------------------------------------------------------
def _summary(parts, *, label="Jumpball", period=1, home="BOS", away="NY"):
    def block(tid, ab, men):
        return {"team": {"id": tid, "abbreviation": ab},
                "statistics": [{"athletes": [{"athlete": {"id": i, "displayName": n}} for i, n in men]}]}
    return {"header": {"id": "401800001", "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "2", "abbreviation": home}},
                {"homeAway": "away", "team": {"id": "18", "abbreviation": away}}]}]},
            "boxscore": {"players": [block("2", home, [("10", "Kristaps Porzingis"), ("11", "Jayson Tatum")]),
                                     block("18", away, [("20", "Karl-Anthony Towns"), ("21", "Jalen Brunson")])]},
            "plays": [{"period": {"number": period}, "type": {"text": label},
                       "participants": [{"athlete": {"id": a}} for a in parts]},
                      {"period": {"number": 1}, "type": {"text": "Jump Shot"}, "shootingPlay": True,
                       "participants": [{"athlete": {"id": "21"}}]}]}


def test_espns_opening_jump_is_the_two_jumpers_and_the_third_mans_club():
    row = S.fold_espn_tip(_summary(["10", "20", "21"]), "2026-11-04")
    assert row == {"game_id": "401800001", "season": 2026, "date": "2026-11-04", "home": "BOS", "away": "NYK",
                   "home_jumper": "Kristaps Porzingis", "away_jumper": "Karl-Anthony Towns", "third": "NYK"}, row
    assert S.fold_espn_tip(_summary(["20", "10"]), "2026-11-04")["third"] == "", "two named: no third"
    assert S.fold_espn_tip(_summary(["20", "10", "11"], label="Jump Ball"), "2026-11-04")["third"] == "BOS"
    assert S.fold_espn_tip(_summary(["10", "11", "20"]), "2026-11-04") is None, "both jumpers one club's"
    assert S.fold_espn_tip(_summary(["10", "20"], period=2), "2026-11-04") is None, "the opening jump only"
    assert S.fold_espn_tip({}, "2026-11-04") is None


def test_the_leagues_own_play_by_play_folds_the_same_way():
    box = {"game": {"gameId": "0022600001", "gameEt": "2026-11-04T19:30:00",
                    "homeTeam": {"teamTricode": "BOS", "players": [{"personId": 1, "name": "Kristaps Porzingis"}]},
                    "awayTeam": {"teamTricode": "NYK", "players": [{"personId": 2, "name": "Karl-Anthony Towns"}]}}}
    pbp = {"game": {"actions": [{"actionType": "jumpball", "period": 1, "jumpBallWonPersonId": 2,
                                 "jumpBallLostPersonId": 1, "teamTricode": "NYK"}]}}
    row = S.fold_tip(pbp, box)
    assert row["home_jumper"] == "Kristaps Porzingis" and row["away_jumper"] == "Karl-Anthony Towns"
    assert row["third"] == "NYK" and row["date"] == "2026-11-04"


# --- the store and the nightly read ------------------------------------------------------
def _db():
    from engine import db
    return db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))


def test_a_folded_final_keeps_its_tip_with_its_shots():
    conn = _db()
    summ = _summary(["10", "20", "21"])
    summ["plays"][1].update({"pointsAttempted": 2, "team": {"id": "18"}, "sequenceNumber": "2",
                             "clock": {"displayValue": "11:40"}, "scoringPlay": False})
    got = S.ingest_games(conn, [{"game_id": "401800001", "date": "2026-11-04"}], read=lambda _g: summ, espn=True)
    assert got["games"] == 1 and got.get("tips") == 1, got
    assert [tuple(r) for r in conn.execute("SELECT home_jumper, away_jumper, third FROM nba_tips")] == \
        [("Kristaps Porzingis", "Karl-Anthony Towns", "NYK")]


def test_the_backfill_reads_the_tips_of_finals_stored_before_and_never_asks_twice():
    conn = _db()
    for gid, day in (("401800001", "2026-11-03"), ("401800002", "2026-11-02")):
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score)"
                     " VALUES ('nba', 2026, ?, ?, 'BOS', 'NYK', 100, 99)", (day, gid))
        conn.execute("INSERT INTO nba_shots (game_id, action, season, date, player, team, period, clock, kind, made)"
                     " VALUES (?, 1, 2026, ?, 'Jalen Brunson', 'NYK', 1, '11:40', '2pt', 0)", (gid, day))
    asked = []

    def read(gid):
        asked.append(gid)
        return _summary(["10", "20", "21"]) if gid == "401800001" else _summary(["10", "11"])
    today = dt.date(2026, 11, 5)
    out = S.backfill_tips(conn, today, read=read)
    assert out == {"games": 2, "tips": 1, "failed": 0, "left": 0}, out
    assert sorted(asked) == ["401800001", "401800002"]
    assert S.backfill_tips(conn, today, read=read)["games"] == 0, "a game with no readable jump is not asked again"
    assert len(asked) == 2
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert "tipped = _nshots.backfill_tips(_sc, today)" in src, "the nightly runs it"


# --- the read ----------------------------------------------------------------------------
def _tip_history(n=40, third_right=True):
    """``n`` BOS-NYK finals. Porzingis jumps for BOS and wins three in four;
    Towns jumps for NYK. The side that gains the tip shoots first, so the
    third man's club agrees with the first shot (or, ``third_right`` False,
    names the wrong club half the time)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE nba_shots (game_id TEXT, action INTEGER, season INTEGER, date TEXT, player TEXT, "
                 "team TEXT, period INTEGER, clock TEXT, made INTEGER)")
    conn.execute("CREATE TABLE nba_tips (game_id TEXT PRIMARY KEY, season INTEGER, date TEXT, home TEXT, away TEXT, "
                 "home_jumper TEXT, away_jumper TEXT, third TEXT)")
    start = dt.date(2026, 10, 21)
    for i in range(n):
        gid, day = f"g{i}", (start + dt.timedelta(days=i)).isoformat()
        gained = "BOS" if i % 4 else "NYK"
        third = gained if third_right or i % 2 else ("NYK" if gained == "BOS" else "BOS")
        conn.execute("INSERT INTO nba_tips VALUES (?, 2026, ?, 'BOS', 'NYK', 'Kristaps Porzingis', "
                     "'Karl-Anthony Towns', ?)", (gid, day, third))
        shooter = "Jayson Tatum" if gained == "BOS" else "Jalen Brunson"
        conn.execute("INSERT INTO nba_shots VALUES (?, 1, 2026, ?, ?, ?, 1, '11:40', 1)", (gid, day, shooter, gained))
        other = "Jalen Brunson" if gained == "BOS" else "Jayson Tatum"
        conn.execute("INSERT INTO nba_shots VALUES (?, 2, 2026, ?, ?, ?, 1, '11:20', 0)",
                     (gid, day, other, "NYK" if gained == "BOS" else "BOS"))
    return conn


def test_each_jumper_carries_his_record_and_the_third_man_is_checked_first():
    data = FB.read(_tip_history(), 2026, before="2026-12-31")
    t = data["tip"]
    assert t["source"] == "tip" and t["agree"] == 1.0 and t["games"] == 40
    assert t["jumps"][FB._norm("Kristaps Porzingis")] == [30.0, 40.0]
    assert t["team_jumpers"]["BOS"][-1] == FB._norm("Kristaps Porzingis")
    wrong = FB.read(_tip_history(third_right=False), 2026, before="2026-12-31")["tip"]
    assert wrong["source"] == "first shot" and wrong["agree"] < FB.TIP_CHECK_AGREE, \
        "a third man who is not the tip is never read as one: the first shot instead"
    assert wrong["jumps"][FB._norm("Kristaps Porzingis")] == [30.0, 40.0], "the first shot gives the same record"
    few = FB.read(_tip_history(n=10), 2026, before="2026-12-31")["tip"]
    assert few["source"] == "first shot", f"fewer than {FB.TIP_CHECK_MIN} checked games: not yet trusted"


def test_the_better_jumper_wins_more_tips_and_a_sitting_one_is_passed_over():
    data = FB.read(_tip_history(), 2026, before="2026-12-31")
    q, who = FB.tip_read(data, "BOS", "NYK")
    rate_h = (30 + FB.JUMP_PRIOR / 2) / (40 + FB.JUMP_PRIOR)
    rate_a = (10 + FB.JUMP_PRIOR / 2) / (40 + FB.JUMP_PRIOR)
    p = 1 / (1 + 2.718281828459045 ** -(FB._logit(FB.HOME_TIP) + FB._logit(rate_h) - FB._logit(rate_a)))
    assert abs(q - (FB.TIP_SHOOTS * p + (1 - FB.TIP_SHOOTS) * (1 - p))) < 1e-9
    assert 0.6 < q < 0.8 and who["BOS"] == ("Kristaps Porzingis", 30.0, 40.0)
    q_out, who_out = FB.tip_read(data, "BOS", "NYK", out={"kristaps porzingis"})
    assert who_out["BOS"][0] == "" and abs(q_out - 0.5) < abs(q - 0.5), "no jumper of theirs: read as even"
    q_moved, _w = FB.tip_read(data, "BOS", "NYK", plays={"Karl-Anthony Towns": "MIN"})
    assert q_moved < q, "a jumper filed with another club tonight is not theirs"
    assert FB.tip_read(FB.read(_tip_history(n=0), 2026), "BOS", "NYK") is None, "nothing stored"


def test_the_board_prices_the_team_half_by_the_jumpers_and_says_so():
    conn = _tip_history()
    data = FB.read(conn, 2026, before="2026-12-31")
    rows = FB.game_probs(data, "BOS", "NYK")
    q, _who = FB.tip_read(data, "BOS", "NYK")
    bos = next(r for r in rows if r["team"] == "BOS")
    assert abs(bos["first_shot"] - round(q, 4)) < 1e-9 and bos["jumper"] == "Kristaps Porzingis"
    assert abs(sum(r["prob"] for r in rows) - 1.0) < 1e-9
    games = [{"home": "BOS", "away": "NYK", "date": "2026-12-31", "kickoff": "2026-12-31T23:30:00Z"}]
    quote = {"a": {"player": "Jayson Tatum", "home": "BOS", "away": "NYK",
                   "quotes": [{"book": "DraftKings", "yes_odds": 400, "no_odds": None, "player": "Jayson Tatum"}]}}
    b = FB.board(quote, games, conn=conn, date="2026-12-31")
    line = b["rows"][0]["reasons"][0]
    assert "by tonight's two jumpers (Kristaps Porzingis: his side gained 30 of 40" in line, line


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
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
