"""engine/likelycal: the Most Likely board's chances, made honest by its record.

Ethan, 2026-10-03: "I don't want to really get rid of any most likely bets
... make the picks better, make what we recommend better." The box's
record: the list's own picks hold up (said 65, hit 65); the matchup picks
went 18-43 and the bold ones 23-38 on the same kind of claim. So each pick's
chance is pulled toward its price by as much as picks from the same maker
on the same side have earned — fitted per group, saved only if it holds on
games it was not fitted on, and never removing a pick.

Run directly: `python3 tests/test_the_board_shows_the_number_its_record_earned.py`
"""
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, likelycal as LC, likelyboard as LB     # noqa: E402

_INS = ("INSERT INTO bets (ts, sport, date, game_day, team, player, market, side, line, odds, hit_prob, grade, "
        "stake_units, stake_dollars, status, category, pnl_units) VALUES ('t','nfl',?,?,?,?,?,?,?,?,?,?,0.1,0,?,?,0)")


def _journal(seed=7):
    conn = ledger.connect(":memory:")
    rng = random.Random(seed)
    teams = [f"T{i}" for i in range(24)]
    for d in range(6):
        day = f"2026-09-{10 + d:02d}"
        for t in teams:
            # The list: honest — claims 62% at -150, hits 62%.
            p = f"L-{day}-{t}"
            conn.execute(_INS, (day, day, t, p, "rec_yds", "OVER", 40.5, -150, 0.62, "Likely",
                                "won" if rng.random() < 0.62 else "lost", "likely"))
            # The matchup picks: claim 65% at -110, hit 35%.
            m = f"M-{day}-{t}"
            won = "won" if rng.random() < 0.35 else "lost"
            conn.execute(_INS, (day, day, t, m, "receptions", "OVER", 3.5, -110, 0.65, "Matchup",
                                won, "matchup_prop"))
            conn.execute(_INS, (day, day, t, m, "receptions", "OVER", 3.5, -110, 0.65, "Strong",
                                won, "board"))
    conn.commit()
    return conn


def test_each_maker_is_corrected_by_its_own_record():
    res = LC.fit(_journal(), "nfl")
    g = res["groups"]
    assert g["list|over"]["k"] == 1.0, g["list|over"]
    assert g["matchup|over"]["k"] <= 0.2, g["matchup|over"]
    assert res["passed"], res["held_out"]


def test_honest_picks_alone_save_nothing():
    conn = ledger.connect(":memory:")
    rng = random.Random(3)
    for d in range(6):
        day = f"2026-09-{10 + d:02d}"
        for i in range(40):
            conn.execute(_INS, (day, day, f"T{i}", f"P{d}-{i}", "rec_yds", "OVER", 40.5, -150, 0.6, "Likely",
                                "won" if rng.random() < 0.6 else "lost", "likely"))
    conn.commit()
    res = LC.fit(conn, "nfl")
    assert not res["passed"], res


def test_the_board_lowers_the_chance_and_keeps_every_pick():
    store = {"nfl": {"groups": {"matchup|over": {"k": 0.0, "n": 61, "hit": 0.3, "claimed": 0.65}}}}
    rows = [{"player": "A", "market": "receptions", "side": "over", "odds": -110, "model_prob": 0.65,
             "sources": ["matchup"]},
            {"player": "B", "market": "rec_yds", "side": "over", "odds": -150, "model_prob": 0.66,
             "sources": ["likely", "matchup"]}]
    assert LC.apply(rows, "nfl", store) == 1
    a, b = rows
    assert a["board_raw_prob"] == 0.65 and abs(a["model_prob"] - 0.5013) < 1e-4, a
    assert "matchup picks on the over have hit 30% of 61" in a["cal_note"]
    assert b["model_prob"] == 0.66 and "board_raw_prob" not in b, "the list's pick is its own group"


def test_a_correction_never_raises_a_chance():
    store = {"nfl": {"groups": {"list|under": {"k": 0.5, "n": 80, "hit": 0.5, "claimed": 0.6}}}}
    rows = [{"player": "C", "market": "rec_yds", "side": "under", "odds": -300, "model_prob": 0.55,
             "sources": ["likely"]}]
    LC.apply(rows, "nfl", store)
    assert rows[0]["model_prob"] == 0.55, "a price above our chance does not lift it"


def test_the_board_reads_it_before_the_checks():
    store = {"nfl": {"groups": {"matchup|over": {"k": 0.0, "n": 61, "hit": 0.3, "claimed": 0.65}}}}
    result = {"most_likely": [], "td_scenarios": [],
              "matchup_picks": [{"props": [{"player": "A", "team": "T0", "market": "receptions", "side": "over",
                                            "line": 3.5, "odds": -110, "model_prob": 0.65}]}]}
    board = LB.build(result, sport="nfl", calibration=store)
    (row,) = board["rows"]
    assert row["model_prob"] < 0.58 and row["checks"]["model"] is False, row["checks"]
    assert "our raw number was 65%" in row["check_notes"]["model"]
    assert len(board["rows"]) == 1, "nothing leaves the pool"


def test_the_journal_keeps_the_raw_chance():
    conn = ledger.connect(":memory:")
    result = {"sport": "nfl", "date": "2030-W04",
              "games": [{"home": "BUF", "away": "MIA", "date": "2030-09-29", "kickoff": "13:00"}],
              "most_likely": [{"player": "A", "team": "MIA", "market": "receptions", "side": "OVER",
                               "line": 3.5, "odds": -110, "model_prob": 0.48, "board_raw_prob": 0.65,
                               "book": "DraftKings"}]}
    assert ledger.log_most_likely(conn, result, depth=None, category="board", grade_label="Worth a look") == 1
    hp, raw = conn.execute("SELECT hit_prob, raw_prob FROM bets").fetchone()
    assert (hp, raw) == (0.48, 0.65)


def test_the_store_round_trips():
    p = Path(tempfile.mkdtemp()) / "cal.json"
    res = LC.fit(_journal(), "nfl")
    LC.save(res, p)
    got = LC.load(p)
    assert got["nfl"]["groups"]["matchup|over"]["k"] == res["groups"]["matchup|over"]["k"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
