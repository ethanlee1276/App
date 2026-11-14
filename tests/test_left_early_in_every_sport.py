"""A game a player left early is handled as measured in every sport.

Ethan, 2026-09-23: "make sure that Wilson 0 yard game issue doesn't affect
any other players or picks or sports and that all gets sorted out so it's
no an issue." The NFL answer (keep it, name it) is
tests/test_a_game_he_left_early_is_named_not_hidden.py. Hoops had a
docstring promising "early-exit/blowout games excluded" that nothing
honoured; measured on 2022-2025 WNBA and NBA box scores (engine/exitfit.py),
the rule is narrower than the promise: a recent early exit stays, older
ones go when the last five are clean. MLB is measured on the box's own
history (`python3 exitfit.py mlb`) before any rule.
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import exitfit as X                                     # noqa: E402
from engine.nba import minutes as M                                  # noqa: E402


def test_what_counts_as_leaving_early():
    usage = [31, 30, 33, 8, 32, 29, 34]            # newest first; 8 is under half of 31
    assert X.exits(usage, 15.0) == [3]
    assert X.exits([10, 4, 11, 12], 15.0) == [], "a bench player's usual is no role to leave"
    assert X.exits([30, 5], 15.0) == [], "too few games to say what usual is"


def test_the_hoops_rule_keeps_a_recent_exit_and_drops_an_old_one():
    recent = [31, 9, 30, 33, 32, 30, 29]
    assert X.keep_rule(recent, 15.0, "old") == list(range(7)), "still limited: keep it"
    old = [31, 30, 33, 32, 29, 7, 34, 30]
    assert X.keep_rule(old, 15.0, "old") == [0, 1, 2, 3, 4, 6, 7]
    both = [31, 9, 33, 32, 29, 7, 34]
    assert X.keep_rule(both, 15.0, "old") == list(range(7)), "a recent exit keeps the older ones too"
    role, dropped = M.role_minutes(old)
    assert dropped == [5] and role == [31, 30, 33, 32, 29, 34, 30]


def test_the_board_reads_his_role_minutes_and_says_so():
    from engine.hoops import WNBA
    from engine.nba.pipeline import evaluate_prop
    mins = [31.0, 30.0, 33.0, 32.0, 29.0, 6.0, 34.0, 30.0, 31.0, 32.0]
    base = {"player": "Guard", "team": "NYL", "market": "pts", "line": 17.5, "over_odds": -110,
            "under_odds": -110, "book": "DK", "values": [16.0] * 10, "is_starter": True,
            "spread": -2.0, "is_favorite": True}
    card = evaluate_prop(dict(base, minutes=mins), WNBA)
    assert card.get("base_minutes") == M.base_minutes([m for i, m in enumerate(mins) if i != 5], WNBA)
    assert card["early_exits"] == {"kept": [], "left_out": [6.0]}
    assert any("left out of his minutes" in n for n in card["context"]), card["context"]
    fresh = evaluate_prop(dict(base, line=16.5, minutes=[31.0, 6.0] + mins[2:5] + [33.0] + mins[6:]), WNBA)
    assert fresh["early_exits"] == {"kept": [6.0], "left_out": []}
    assert "Left early 2 games ago (6 min) — kept: a recent early exit predicts a quieter game (measured)" \
        in fresh["context"], fresh["context"]
    src = open(os.path.join(ROOT, "engine", "nba", "minutes.py"), encoding="utf-8").read()
    assert "early-exit/blowout games excluded" not in src, "the promise nothing kept is gone"


def test_the_measurement_centres_on_what_it_is_given():
    series = {"p": [(2025, f"2025-06-{d:02d}", 30.0 if d != 3 else 5.0, 30.0 if d != 3 else 5.0)
                    for d in range(1, 13)]}
    got = X.measure(series, X.minutes_projection(__import__("engine.hoops", fromlist=["NBA"]).NBA), 15.0)
    old_all, old_rule = got[("old", "all")], got[("old", "old")]
    assert old_all["bias"] > 0 and abs(old_rule["bias"]) < 1e-9, "the old exit only dragged it down"
    assert "recent" in {k[0] for k in got}


def test_the_mlb_command_reads_the_box_read_only():
    import exitfit
    from engine import db
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INT, market TEXT, value REAL)")
    rows = []
    for d in range(1, 12):
        outs = 3.0 if d == 4 else 18.0
        for market, value in (("outs", outs), ("strikeouts", 1.0 if d == 4 else 6.0)):
            rows.append(("mlb", 2026, f"2026-05-{d:02d}", f"Ace-2026-05-{d:02d}", "Ace", "NYY", "BOS",
                         "SP", 1, market, value))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    saved = db.DEFAULT_DB
    db.DEFAULT_DB = path
    import io
    import contextlib
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            assert exitfit.main(["mlb"]) == 0
    finally:
        db.DEFAULT_DB = saved
    text = out.getvalue()
    assert "mlb starter strikeouts by outs — 1 players" in text and "old    old" in text, text


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
