"""The NBA's minutes are read against their own games (Ethan, 2026-10-29:
"almost ever nba most likely bet is an under bet so that seems wrong and we
need to work on that and calibrate that more").

The minutes model laid tonight's blowout and rest haircuts on a base that
is an average of his recent games, which had already taken theirs. Every
blowout step is 1.00 or less and every rest step but one, so every starter
read light: about 2% on an even club, about 7% on one favoured most nights.
The Most Likely board ranks by our chance at a number near −250, where a
few percent of mean is several points of chance, so the under won the seat
nearly every time. What these hold:

  * each haircut is divided by what his own games carried
    (engine/nba/minutes.context_norms), so it keeps its shape (a bigger
    spread than his usual still costs minutes, a rested night still adds)
    and averages one over his schedule;
  * the build reads each history game's margin and rest off the finals it
    holds (nba_build.history_context), found by date and opponent;
  * a history without that context (the replay, an old database) prices
    exactly as before, so the replay the board is calibrated on is unmoved;
  * the scoring environment is read against the league's own recent
    average total, not a fixed 225;
  * nbalean.py reads the board's lean, the model's level against the
    market's own number, and the record by side.

Run directly: `python3 tests/test_the_nba_minutes_are_read_against_their_own_games.py`
"""
import json
import math
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.hoops import NBA                    # noqa: E402
from engine.nba import minutes as M             # noqa: E402
from engine.nba import pipeline as P            # noqa: E402
from engine.nba.context import env_factor       # noqa: E402

BUILD = (ROOT / "nba_build.py").read_text(encoding="utf-8")


def _schedule(margin_mean: float, n: int, seed: int = 7):
    """``n`` games of spreads ~ Normal(margin_mean, SPREAD_SD)."""
    rnd = random.Random(seed)
    return [rnd.gauss(margin_mean, M.SPREAD_SD) for _ in range(n)]


def test_a_favoured_clubs_starter_no_longer_reads_light():
    base = 34.0
    for mean, light in ((10.0, 0.06), (0.0, 0.012), (-10.0, 0.03)):
        spreads = _schedule(mean, 4000)
        norm = M.expected_blowout(mean, True)
        old = sum(M.project_minutes(base, s, True, s > 0) for s in spreads) / len(spreads)
        new = sum(M.project_minutes(base, s, True, s > 0, blowout_norm=norm) for s in spreads) / len(spreads)
        assert old < base * (1 - light), (mean, old)          # the bias that seated the under
        assert abs(new / base - 1) < 0.006, (mean, new)        # averages his base now
    # Its shape is kept: a bigger spread than his usual still costs minutes.
    norm = M.expected_blowout(3.0, True)
    assert M.project_minutes(base, 14.0, True, True, blowout_norm=norm) < base \
        < M.project_minutes(base, 1.0, True, True, blowout_norm=norm)


def test_rest_is_read_against_his_own_schedule():
    rests = ["1day", "b2b_home", "1day", "1day", "b2b_home", "1day", "2plus", "1day", "b2b_home", "1day"]
    kept = list(range(len(rests)))
    b_norm, r_norm = M.context_norms([3.0] * 10, rests, kept, True)
    assert r_norm < 1.0 and 0.9 < b_norm < 1.0
    assert M.project_minutes(32.0, 0.0, True, False, "1day", rest_norm=r_norm) > 32.0, \
        "a normal night is above a base that held three back-to-backs"
    assert M.project_minutes(32.0, 0.0, True, False, "b2b_home", rest_norm=r_norm) < 32.0


def test_without_context_it_prices_as_before():
    assert M.context_norms(None, None, [0, 1, 2], True) == (1.0, 1.0)
    assert M.context_norms([5.0, None], ["1day"], [0, 1], True) == (1.0, 1.0), "under three games, no norm"
    prop = {"player": "A Starter", "market": "pts", "minutes": [34, 35, 33, 36, 34, 32, 35, 34],
            "values": [26, 28, 24, 30, 25, 23, 27, 26], "is_starter": True, "spread": -8.5,
            "is_favorite": True, "rest": "1day", "player_mult": 1.0}
    old = P.project(prop, NBA)
    assert old["minutes_norms"] == {"blowout": 1.0, "rest": 1.0}
    lifted = P.project(dict(prop, margins=[12.0] * 8, rests=["1day"] * 8), NBA)
    assert lifted["projection"] > old["projection"] * 1.04, (old["projection"], lifted["projection"])
    assert lifted["minutes_norms"]["blowout"] < 0.95


def test_the_build_reads_margins_and_rest_off_its_finals():
    import importlib
    sys.path.insert(0, str(ROOT))
    nb = importlib.import_module("nba_build")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, home TEXT, "
                 "away TEXT, home_score REAL, away_score REAL)")
    rows = [("2026-10-20", "BOS", "NYK", 110, 100), ("2026-10-22", "MIA", "BOS", 99, 120),
            ("2026-10-23", "BOS", "PHI", 101, 104), ("2026-10-27", "TOR", "BOS", 95, 97)]
    for d, h, a, hs, as_ in rows:
        conn.execute("INSERT INTO games VALUES ('nba', 2026, ?, ?, ?, ?, ?, ?)", (d, d + h, h, a, hs, as_))
    hist = {"J Tatum": {"team": "BOS", "dates": ["2026-10-27", "2026-10-23", "2026-10-22", "2026-10-20"],
                        "opps": ["TOR", "PHI", "MIA", "NYK"], "homes": [0, 1, 0, 1]}}
    nb.history_context(conn, "nba", hist)
    h = hist["J Tatum"]
    assert h["margins"] == [2.0, -3.0, 21.0, 10.0], h["margins"]
    assert h["rests"] == ["1day", "3in4", "1day", "2plus"], h["rests"]   # 10-20, 10-22, 10-23: three in four
    assert "history_context(conn, args.league, hist)" in BUILD
    assert '"margins": h.get("margins"), "rests": h.get("rests"),' in BUILD
    assert '"total_norm": norm_total,' in BUILD


def test_the_scoring_norm_is_the_leagues_own():
    assert env_factor(232.0, "nba") == env_factor(232.0, "nba", None), "no norm: the fixed one, as before"
    fast, _ = env_factor(232.0, "nba")
    level, note = env_factor(232.0, "nba", 232.0)
    assert fast > 1.0 and level == 1.0 and note is None, "a normal night for this league is not a fast one"
    import importlib
    nb = importlib.import_module("nba_build")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, period TEXT, home_score REAL, away_score REAL)")
    for i in range(60):
        conn.execute("INSERT INTO games VALUES ('nba', ?, 115, 117)", (f"2026-10-{1 + i % 27:02d}",))
    assert nb.total_norm(conn, "nba", "2026-10-29") == 232.0
    assert nb.total_norm(conn, "nba", "2026-10-02") is None, "too few finals before the date"


def test_the_lean_report_reads_the_level_on_one_scale():
    import nbalean
    from engine.nba.prob import p_over
    for stat, mean, line in (("pts", 24.0, 22.5), ("reb", 8.4, 7.5), ("fg3m", 2.6, 2.5)):
        q = p_over(stat, mean, line)
        back = nbalean.implied_mean(stat, line, q)
        assert back and abs(back - mean) / mean < 0.01, (stat, mean, back)
    doc = {"most_likely": [{"kind": "prop", "market": "pts", "side": "under"},
                           {"kind": "prop", "market": "pts", "side": "under"},
                           {"kind": "prop", "market": "reb", "side": "over"}],
           "recommendations": [{"market": "pts", "projection": 24.0, "line": 22.5, "side": "OVER",
                                "fair_prob": p_over("pts", 24.0, 22.5)}] * 10}
    sides = nbalean.board_sides(doc)
    assert sides["pts"]["under"] == 2 and sides["reb"]["over"] == 1
    ratios = nbalean.levels(doc)["pts"]
    assert len(ratios) == 10 and all(abs(r - 1.0) < 0.01 for r in ratios)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nba.json"
        path.write_text(json.dumps(doc))
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert nbalean.main(["--board", str(path)]) == 0
        text = out.getvalue()
        assert "3 picks — 1 over, 2 under (67% under)" in text, text
        assert "median 1.000" in text, text


def test_the_report_reads_the_minutes_base_at_the_seasons_start():
    """A lottery club's April (24 minutes) under a starter's 34 this season:
    the twenty-game window runs light, this season's games alone do not."""
    import nbalean
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, player TEXT, "
                 "market TEXT, value REAL)")
    for k in range(30):
        name = f"Starter {k}"
        for i in range(15):
            conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2025, ?, ?, 'min', 24)",
                         (f"2026-03-{10 + i:02d}", name))
        for i in range(6):
            conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2026, ?, ?, 'min', 34)",
                         (f"2026-10-{21 + i:02d}", name))
    got = nbalean.minutes_check(conn, 2026)
    assert got["n"] == 90, got                                  # games 4-6 of each of thirty men
    assert got["window"] > 1.10 and abs(got["season_only"] - 1.0) < 0.01, got


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
