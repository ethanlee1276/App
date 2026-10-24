"""recordcheck.py: the Record page's numbers, checked read-only on the box.

Ethan, 2026-09-28: the Most Likely section's Spread row read 2/2 while Pick
of the Day listed a CAR spread lost — "make sure all the numbers are
correct". The check re-derives every grade on an in-memory copy (the
settler's own repair pass), finds a bet carrying two results in two
sections, lists every game-line bet by section, and recounts each
section. Fixture ledger and history in a temp directory — never the box's.

Run directly: `python3 tests/test_the_record_check_finds_a_wrong_grade_and_a_split_result.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import recordcheck as RC                                        # noqa: E402
from engine import db, ledger                                   # noqa: E402


def _fixtures():
    tmp = Path(tempfile.mkdtemp())
    lpath, hpath = tmp / "ledger.db", tmp / "history.db"
    conn = ledger.connect(lpath)
    rows = [
        # Pick of the Day: CAR +2.5 (stored negated), CAR lost by 7 — graded lost, right.
        ("potd", "2026-W03", "2026-09-20", "CAR", "spread", "OVER", -2.5, -102, "lost", -7.0, 1.0),
        # Most Likely: BUF -4.5 won by 10 — right.
        ("likely", "2026-W02", "2026-09-14", "BUF", "spread", "OVER", 4.5, -104, "won", 10.0, 0.1),
        # Most Likely: HOU moneyline graded WON though HOU lost — the wrong grade to find.
        ("likely", "2026-W02", "2026-09-14", "HOU", "moneyline", "OVER", 0.5, -136, "won", 1.0, 0.1),
        # The same BUF spread in Pick of the Day, graded LOST — a split result.
        ("potd", "2026-W02", "2026-09-14", "BUF", "spread", "OVER", 4.5, -104, "lost", 10.0, 1.0),
    ]
    for cat, date, day, player, market, side, line, odds, status, actual, stake in rows:
        pnl = stake * (100 / abs(odds)) if status == "won" else -stake
        conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, "
                     "stake_units, stake_dollars, status, actual, pnl_units, category) VALUES "
                     "('t','nfl',?,?,?,?,?,?,?,0.6,?,0,?,?,?,?)",
                     (date, day, player, market, side, line, odds, stake, status, actual, pnl, cat))
    conn.commit()
    conn.close()
    h = db.connect(hpath)
    h.executemany("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?, ?)",
                  [("003", "CAR@TB", "2026-09-20", "TB", "CAR", 24, 17),
                   ("002", "BUF@MIA", "2026-09-14", "MIA", "BUF", 17, 27),
                   ("002", "HOU@JAX", "2026-09-14", "JAX", "HOU", 20, 13)])
    h.commit()
    h.close()
    return lpath, hpath


def test_the_ledger_is_never_written():
    lpath, hpath = _fixtures()
    before = lpath.read_bytes()
    RC.main(["--db", str(lpath), "--history", str(hpath)])
    assert lpath.read_bytes() == before, "the real ledger is untouched; the repair pass ran on a copy"


def test_the_wrong_grade_the_split_and_the_game_lines_are_found():
    lpath, hpath = _fixtures()
    mem = RC.copy_to_memory(lpath)
    fixes = RC.regrade(mem, RC._ro(hpath))
    hou = [f for f in fixes if f.get("player") == "HOU"]
    assert hou and hou[0]["was"] == "won" and hou[0]["now"] == "lost", fixes
    assert not [f for f in fixes if f.get("player") == "CAR"], "a right grade is left alone"
    split = RC.split_grades(RC.copy_to_memory(lpath), "nfl")
    assert len(split) == 1 and split[0][0][1] == "BUF"
    assert sorted(split[0][1]) == [("likely", "won"), ("potd", "lost")]
    lines = RC.game_lines(RC.copy_to_memory(lpath), "nfl")
    assert {(r["category"], r["player"]) for r in lines} == {("potd", "CAR"), ("likely", "BUF"),
                                                             ("likely", "HOU"), ("potd", "BUF")}


def test_a_result_that_contradicts_its_own_number_is_found():
    """The repair pass audits a grade against NEW numbers; a row graded
    against its own stored number wrongly (BUF won by 10 on −4.5, recorded
    lost) is invisible to it, so the check reads the row against itself."""
    lpath, _ = _fixtures()
    bad = RC.self_contradictions(RC.copy_to_memory(lpath), "nfl")
    assert [(r["category"], r["player"], r["status"], r["want"]) for r in bad] == [("potd", "BUF", "lost", "won")]
    assert RC.expected_status("OVER", -2.5, -7.0) == "lost", "CAR +2.5 lost by 7"
    assert RC.expected_status("OVER", 3.0, 3.0) == "push"
    assert RC.expected_status("UNDER", 45.5, 41.0) == "won"
    assert RC.expected_status("YES", 0.5, 1.0) == "won"
    assert RC.expected_status("OVER", None, 3) is None


def test_the_sections_recount_clean_on_a_consistent_ledger():
    lpath, _ = _fixtures()
    assert RC.recount(RC.copy_to_memory(lpath), "nfl") == [], "the report functions agree with a plain count"


def _board_ledger():
    """Ethan, 2026-10-02: "No way we have hit 12/13 TD picks bc I've seen
    more then that loose." A ledger with the board, its twin in the staked
    Most Likely book, a matchup scorer, a dateless row and a stuck one."""
    conn = ledger.connect(":memory:")
    ins = ("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, grade, "
           "stake_units, stake_dollars, status, category, pnl_units, actual) "
           "VALUES ('t','nfl',?,?,?,?,?,?,?,0.6,?,?,0,?,?,?,?)")
    for r in [("2026-W04", "2026-09-28", "Twin", "rec_yds", "OVER", 40.5, -110, "", 0.25, "won", "likely_live", 0.227, 55),
              ("2026-W04", "2026-09-28", "Twin", "rec_yds", "OVER", 40.5, -110, "Top pick", 0.1, "won", "board", 0.091, 55),
              ("2026-W04", "2026-09-28", "Scorer", "anytime_td", "OVER", 0.5, 150, "Strong", 0.1, "lost", "board", -0.1, 0),
              ("2026-W04", "2026-09-28", "Scorer", "anytime_td", "OVER", 0.5, 150, "Matchup", 0.1, "lost", "matchup_td", -0.1, 0),
              ("2026-W04", "2026-09-28", "NoTD Guy", "anytime_td", "UNDER", 0.5, -170, "", 0.25, "won", "likely_live", 0.147, 0),
              ("2026-W04", "", "Nodate", "rec_yds", "OVER", 30.5, -110, "Worth a look", 0.1, "lost", "board", -0.1, 20),
              ("2026-W02", "2026-09-14", "Edge A", "pass_yds", "OVER", 245.5, -110, "A", 1.0, "won", "main", 0.909, 260),
              ("2026-W03", "2026-09-21", "Stuck", "rec_yds", "OVER", 40.5, -110, "", 0.25, "open", "likely_live", 0, None)]:
        conn.execute(ins, r)
    conn.commit()
    return conn


def test_every_td_pick_is_listed_with_its_side_in_every_section():
    rows = RC.td_rows(_board_ledger(), "nfl")
    assert len(rows) == 3
    summ = RC.td_summary(rows)
    assert summ[("Most Likely", "no TD")] == [1, 0, 0], "a no-TD pick is never read as a touchdown"
    assert summ[("Most Likely by tier", "scores")] == [0, 1, 0]
    assert summ[("Matchup TD picks", "scores")] == [0, 1, 0]


def test_the_boards_picks_are_traced_to_where_they_came_from():
    src = RC.board_sources(_board_ledger(), "nfl")
    assert (src["the Most Likely list"]["w"], src["the Most Likely list"]["l"]) == (1, 0)
    assert (src["the matchup picks"]["w"], src["the matchup picks"]["l"]) == (0, 1)
    assert src["the board only"]["tiers"] == {"Worth a look": [0, 1]}


def test_stuck_bets_and_dateless_rows_are_found():
    import datetime as dt
    conn = _board_ledger()
    assert RC.stuck_open(conn, "nfl", today=dt.date(2026, 10, 2)) == [("likely_live", 1, "2026-09-21")]
    assert RC.stuck_open(conn, "nfl", today=dt.date(2026, 9, 22)) == [], "a game two days old is still settling"
    assert RC.no_day(conn, "nfl") == [("board", 1, 0)]


def test_the_headline_recounted_by_hand_matches_the_page():
    conn = _board_ledger()
    hand = RC.by_hand(conn, "nfl")
    rep = ledger.pooled_report(conn, "nfl")
    for k in ("edge", "likely", "overall"):
        assert (hand[k]["wins"], hand[k]["losses"]) == (rep[k]["wins"], rep[k]["losses"]), k
        assert abs(hand[k]["net_units"] - rep[k]["net_units"]) < 0.011, k
    assert (hand["likely"]["wins"], hand["likely"]["losses"]) == (2, 2), "the board's twin is counted once"


def test_a_published_board_pick_with_no_journal_row_is_named():
    import json
    conn = _board_ledger()
    d = Path(tempfile.mkdtemp())
    (d / "recommendations.json").write_text(json.dumps({"date": "2026-W04", "likely_board": {"rows": [
        {"player": "Twin", "market": "rec_yds", "side": "OVER", "line": 40.5, "odds": -110, "model_prob": 0.6},
        {"player": "Ghost", "market": "receptions", "side": "OVER", "line": 3.5, "odds": -120, "model_prob": 0.6},
        {"player": "Reserve", "market": "receptions", "side": "OVER", "line": 2.5, "odds": -150,
         "model_prob": 0.5, "reserve": True}]}}))
    n, missing = RC.board_vs_journal(conn, "nfl", d)
    assert n == 3
    assert [(r["player"], why) for r, why in missing] == [("Ghost", "not journaled"),
                                                         ("Reserve", "a reserve row (below the bar)")]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
