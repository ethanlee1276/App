"""The research reports, our board and the price are scored on the games.

Ethan, 2026-10-04, six research reports on two games: whose method is
better is settled by results, not argument. engine/scancard grades every
written-down pick against the box score. Checks: an over, an under and a
push grade the right way; our chance is the same bet at the same line and
never the stale-price sampler's consensus; a source is compared with ours
only on the picks both priced; the claims file is well formed.

Run directly: `python3 tests/test_the_research_is_scored_on_what_happened.py`
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import scancard as S                                    # noqa: E402


def _dbs():
    hist = sqlite3.connect(":memory:")
    hist.execute("CREATE TABLE player_game_logs (sport, season, period, player, team, market, value)")
    hist.executemany("INSERT INTO player_game_logs VALUES ('nfl', 2026, '004', ?, ?, ?, ?)", [
        ("Bhayshul Tuten", "JAX", "rush_yds", 71), ("Trevor Lawrence", "JAX", "pass_yds", 240),
        ("Tee Higgins", "CIN", "receptions", 4), ("Chase Brown", "CIN", "anytime_td", 1),
        ("Bhayshul Tuten", "JAX", "carries", 15)])
    led = sqlite3.connect(":memory:")
    led.execute("CREATE TABLE bets (sport, date, player, market, side, line, category, hit_prob)")
    led.executemany("INSERT INTO bets VALUES ('nfl', '2026-W04', ?, ?, ?, ?, ?, ?)", [
        ("Bhayshul Tuten", "rush_yds", "OVER", 55.5, "board", 0.61),
        ("Bhayshul Tuten", "rush_yds", "OVER", 44.5, "board", 0.75),        # another line: not ours
        ("Chase Brown", "anytime_td", "OVER", 0.5, "stale", 0.70),           # the field's, not ours
        ("Chase Brown", "anytime_td", "OVER", 0.5, "matchup_td", 0.538)])
    return hist, led


CLAIMS = [
    {"source": "A", "team": "JAX", "player": "Bhayshul Tuten", "market": "rush_yds", "side": "OVER", "line": 55.5, "prob": 0.72, "price": -110},
    {"source": "A", "team": "JAX", "player": "Trevor Lawrence", "market": "pass_yds", "side": "UNDER", "line": 260.5, "prob": 0.69, "price": -111},
    {"source": "B", "team": "CIN", "player": "Tee Higgins", "market": "receptions", "side": "OVER", "line": 4.0, "prob": 0.6, "price": None},
    {"source": "B", "team": "CIN", "player": "Chase Brown", "market": "anytime_td", "side": "OVER", "line": 0.5, "prob": 0.61, "price": -145},
    {"source": "B", "team": "JAX", "player": "Bhayshul Tuten", "market": "rush_att", "side": "OVER", "line": 12.5, "prob": 0.64, "price": -132},
]


def test_overs_unders_and_pushes_grade_the_right_way():
    hist, led = _dbs()
    rows = {(r["player"], r["market"]): r for r in S.grade(CLAIMS, 2026, 4, hist, led)}
    assert rows[("Bhayshul Tuten", "rush_yds")]["hit"] == 1
    assert rows[("Trevor Lawrence", "pass_yds")]["hit"] == 1, "240 is under 260.5"
    assert rows[("Tee Higgins", "receptions")]["hit"] is None, "4 on a line of 4 is a push"
    assert rows[("Chase Brown", "anytime_td")]["hit"] == 1
    assert rows[("Bhayshul Tuten", "rush_att")]["actual"] == 15, "rush attempts read the carries row"


def test_our_chance_is_the_same_bet_and_never_the_consensus():
    hist, led = _dbs()
    rows = {(r["player"], r["market"]): r for r in S.grade(CLAIMS, 2026, 4, hist, led)}
    assert rows[("Bhayshul Tuten", "rush_yds")]["ours"] == 0.61, "the 55.5 line, not the 44.5"
    assert rows[("Chase Brown", "anytime_td")]["ours"] == 0.538, "the board's, not the stale sampler's 70%"
    assert rows[("Trevor Lawrence", "pass_yds")]["ours"] is None


def test_a_source_meets_ours_only_on_shared_picks():
    hist, led = _dbs()
    board = {s["source"]: s for s in S.scoreboard(S.grade(CLAIMS, 2026, 4, hist, led))}
    a = board["A"]
    assert a["graded"] == 2 and a["paired"] == 1
    assert a["brier_them_paired"] == round((0.72 - 1) ** 2, 4)
    assert a["brier_ours_paired"] == round((0.61 - 1) ** 2, 4)
    assert board["B"]["graded"] == 2, "the push is not graded"
    text = S.report(S.grade(CLAIMS, 2026, 4, hist, led))
    assert "SCOREBOARD" in text and "push" in text


def test_the_claims_file_is_well_formed():
    spec = json.load(open(S.DEFAULT, encoding="utf-8"))
    assert spec["season"] == 2026 and spec["week"] == 4 and len(spec["claims"]) >= 30
    for c in spec["claims"]:
        assert set(c) >= {"source", "team", "player", "market", "side", "line", "prob", "price"}, c
        assert 0 < c["prob"] < 1 and c["side"] in ("OVER", "UNDER"), c


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
