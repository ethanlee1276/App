"""When our number is far above the books': a data error, or a real find?

Ethan, 2026-09-27, on Most Likely picks refused for being more than ten
points more confident than the market (Sadiq 67% vs 51%, Hampton 71% vs
57%): "maybe we figure out if thats data error or if thats genuinely
something our model found and that could happen based on the
circumstances." engine/boldcheck asks each such row whether its inputs
look wrong (another team's history, a changed role against our side, the
books moving away, a stale price) and, if not, whether a measured step
or his own games account for the gap. Real finds go on Most Likely as
"Bolder than the books"; the rest stay off with the reason.

The fixture is the real rows from the week-3 build priced at the other
AI's Chargers @ Bills and Jets @ Lions lines.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import boldcheck as B                                    # noqa: E402
from engine import likely as L                                       # noqa: E402

ROWS = json.load(open(os.path.join(ROOT, "tests", "fixtures", "bold_gap_rows_2026_w3.json"), encoding="utf-8"))


def _check(key):
    r = ROWS[key]
    return B.check(r, r["side"], r["line"], r["hit_prob"], r["fair_prob"], r["raw_prob"])


def test_a_measured_step_up_is_a_real_find():
    v = _check("Kenyon Sadiq|rec_yds")
    assert v["verdict"] == B.FOUND and v["label"] == "Bolder than the books"
    assert "Mason Taylor just ruled out ahead of him at TE" in v["why"][0]
    assert "from his own form (34% on this number) to 67%" in v["why"][0]


def test_his_own_games_backing_it_is_a_real_find():
    v = _check("Omarion Hampton|receptions")
    assert v["verdict"] == B.FOUND
    assert v["why"] == ["His own games back it: over 1.5 catches in 7 of his last 11 (64%) — the books say 57%."]
    v = _check("Ladd McConkey|receptions")
    assert v["verdict"] == B.FOUND and v["gap"] > B.BIG_GAP, "past 25 points only his own games can carry it"
    assert "under 4.5 catches in 9 of his last 12 (75%)" in v["why"][0]


def test_another_teams_history_is_a_data_problem():
    v = _check("DJ Moore|receptions")
    assert v["verdict"] == B.SUSPECT and v["label"] == "Likely a data problem"
    assert "joined BUF from CHI" in v["why"][0]


def test_nothing_behind_it_is_unexplained_and_stays_off():
    v = _check("Garrett Wilson|rec_yds")
    assert v["verdict"] == B.UNEXPLAINED
    assert "His own games clear it 44% of the time over 9" in v["why"][0]


def test_inside_the_bar_there_is_nothing_to_check():
    r = ROWS["Omarion Hampton|receptions"]
    assert B.check(r, "OVER", 1.5, 0.60, 0.57, 0.62) is None


def test_the_role_and_the_tape_flags():
    r = dict(ROWS["Omarion Hampton|receptions"])
    r["carried"] = {"weight": 0.8}
    r["logs"] = [{"week": 2, "value": 1, "snaps": 0.30}, {"week": 1, "value": 1, "snaps": 0.32},
                 {"week": 17, "value": 4, "snaps": 0.80}, {"week": 16, "value": 3, "snaps": 0.78},
                 {"week": 15, "value": 5, "snaps": 0.82}]
    assert any("His role has shrunk — 31% of the snaps" in f for f in B.flags(r, "over"))
    assert not any("role" in f for f in B.flags(r, "under")), "a shrunken role backs an under"
    r = dict(ROWS["Omarion Hampton|receptions"], line_move={"verdict": "against", "delta": -1.0, "open": 2.5, "current": 1.5})
    assert any("moved the line away from our side" in f for f in B.flags(r, "over"))
    r = dict(ROWS["Omarion Hampton|receptions"], price_age_s=8 * 3600)
    assert any("8 hours old" in f for f in B.flags(r, "over"))


def test_a_real_find_reaches_most_likely_and_a_data_problem_does_not():
    base = {"has_market": True, "all_lines": [], "alt_lines": []}
    hampton = dict(ROWS["Omarion Hampton|receptions"], **base)
    got = L.from_prop(hampton, lambda m: True, fits={})
    assert got and got["bold"] and got["side"] == "OVER" and got["bold_why"], got
    assert L.admissible(got) == "", "a real find stands past both credibility bars"
    moore = dict(ROWS["DJ Moore|receptions"], **base)
    row = L.from_prop(moore, lambda m: True, fits={})
    assert row is None or not row["bold"]
    if row is not None:
        assert L.admissible(row) != ""


def test_bold_rows_are_journaled_apart_and_never_staked():
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert 'if category == "likely" and r.get("bold"):' in src
    nfl = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'category="bold", grade_label="Bold"' in nfl
    assert nfl.index("_carry_early.decorate(") < nfl.index("result = run_slate("), \
        "the team change is on the rows before the board reads them"
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert '"Bolder than the books", "up"' in app


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
