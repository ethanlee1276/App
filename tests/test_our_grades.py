"""Our grades: a man's season against his position's, from free numbers, said as a reading and never PFF's.

Ethan, 2026-10-24: "yes build all of D" — PFF grades among them. PFF's
terms limit its data to personal, non-commercial use, so a paid page cannot
show it; engine/grades scores each player 0-100 against the men at his
position from the tracking and charting files the site already reads.

What these hold: a grade is the mean of his percentiles, a lower-is-better
part counted the right way up, against his own position only and only the
men with the volume; a man with one part is not graded; the parts are read
before the board's week, in the season, and NGS's "LAR" joins PFR's "LA";
the report puts the grade on his card with its parts and ranks, gives a
corner his coverage grade, and says once that it is ours, not PFF's, and
moves no number; and nothing fetches from PFF.

Run directly: `python3 tests/test_our_grades.py`
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamereport as R                                  # noqa: E402
from engine import grades as G                                      # noqa: E402


def _rec(name, team, pos, week, targets, yards, sep, yac, season=2026):
    return {"season": str(season), "season_type": "REG", "week": str(week), "player_display_name": name,
            "player_position": pos, "team_abbr": team, "targets": str(targets), "yards": str(yards),
            "receptions": "0", "avg_separation": str(sep), "avg_yac_above_expectation": str(yac)}


def _drop(name, team, week, drops, season=2026):
    return {"season": str(season), "game_type": "REG", "week": str(week), "team": team,
            "pfr_player_name": name, "receiving_drop": str(drops)}


def _values():
    ngs = {"receiving": [_rec("Top Wr", "LAR", "WR", 1, 10, 120, 3.5, 2.0), _rec("Top Wr", "LAR", "WR", 2, 10, 110, 3.3, 1.8),
                         _rec("Mid Wr", "CHI", "WR", 1, 20, 160, 2.8, 0.5),
                         _rec("Low Wr", "NE", "WR", 1, 20, 100, 2.2, -0.8),
                         _rec("Thin Wr", "NE", "WR", 1, 5, 90, 4.0, 3.0),
                         _rec("Late Wr", "KC", "WR", 7, 30, 400, 5.0, 5.0),
                         _rec("Old Wr", "KC", "WR", 3, 30, 400, 5.0, 5.0, season=2025),
                         _rec("Only Te", "DET", "TE", 1, 20, 150, 2.0, 1.0)]}
    pfr = {"rec": [_drop("Top Wr", "LA", 1, 0), _drop("Mid Wr", "CHI", 1, 1), _drop("Low Wr", "NE", 1, 3)]}
    return G._values(ngs, pfr, 2026, 7)


def test_the_parts_are_read_in_the_window_and_the_teams_join():
    v = _values()["receiving"]
    top = v[("LA", "top wr")]
    assert top["volume"] == 20 and abs(top["yds_per_tgt"] - 11.5) < 1e-9
    assert abs(top["avg_separation"] - 3.4) < 1e-9, "volume-weighted over his weeks"
    assert top["drop_rate"] == 0.0, "NGS's LAR is PFR's LA"
    assert v[("NE", "low wr")]["drop_rate"] == 3 / 20
    assert ("KC", "late wr") not in v, "week 7 is the board's week, not before it"
    assert ("KC", "old wr") not in v, "another season"


def test_a_grade_is_his_percentiles_against_his_own_position_with_the_volume():
    got = G.grade(_values())["receiving"]
    top, mid, low = got[("LA", "top wr")], got[("CHI", "mid wr")], got[("NE", "low wr")]
    assert (top["grade"], mid["grade"], low["grade"]) == (100, 50, 0), (top, mid, low)
    assert top["n"] == 3 and top["pos"] == "WR"
    drops = next(p for p in low["parts"] if p["part"] == "drop_rate")
    assert (drops["rank"], drops["of"]) == (3, 3), "the most drops ranks last: lower is better"
    assert ("NE", "thin wr") not in got, "five targets is not the volume to rank"
    assert ("DET", "only te") not in got, "a tight end is ranked against tight ends, and one is not a field"


def test_a_man_with_one_part_is_not_graded():
    vals = {"receiving": {("A", "x"): {"pos": "WR", "volume": 30, "yds_per_tgt": 9.0},
                          ("B", "y"): {"pos": "WR", "volume": 30, "yds_per_tgt": 7.0}},
            "rushing": {}, "passing": {}, "coverage": {}}
    assert G.grade(vals)["receiving"] == {}


def test_the_words_carry_the_grade_the_field_and_each_part():
    g = G.grade(_values())["receiving"][("LA", "top wr")]
    text = G.words(g)
    assert text.startswith("100 of 100, against 3 wide receivers with the volume to rank: ")
    assert "11.5 yards a target (1st)" in text and "0.0% drops a target (1st)" in text
    assert "+1.9 yards after the catch over expected (1st)" in text
    assert G.words(None) == ""
    assert "not PFF's" in G.NOTE and "not part of any number" in G.NOTE


def _board():
    game = {"away": "LA", "home": "CHI", "date": "2026-10-25", "kickoff": "13:00",
            "scan": {"units": {}, "method": {"teams": 32},
                     "coverage": {"LA": {"corners": [{"name": "Top Corner", "spot": "LCB", "targets": 20,
                                                      "rating": 70.0, "yds_per_tgt": 5.5}]}}}}
    reads = [{"player": "Top Wr", "team": "LA", "pos": "WR", "read": "good", "label": "Good matchup",
              "usage": {"tgt_share": 0.28, "targets_pg": 9.0}, "pro": ["A soft corner"]},
             {"player": "Mid Wr", "team": "CHI", "pos": "WR", "read": "good", "label": "Good matchup",
              "usage": {"tgt_share": 0.25, "targets_pg": 8.0}, "pro": ["Volume"]}]
    return {"date": "2026-W7", "games": [game], "scan_reads": {"LA@CHI": {"players": reads}}}


def test_the_report_puts_it_on_his_card_the_corners_and_says_whose_it_is():
    grades = G.grade(_values())
    grades["coverage"] = {("LA", "top corner"): {"grade": 81, "n": 140, "pos": "coverage", "parts": []}}
    board = _board()
    c = R.Ctx(board["games"][0], board, names={}, form={"Top Wr": {"games": []}}, grades=grades)
    lines = dict((k, v) for k, v in R.form_lines(c, board["scan_reads"]["LA@CHI"]["players"][0]))
    assert lines["Our grade"][0].startswith("100 of 100, against 3 wide receivers"), lines
    assert "our coverage grade 81 of 100 (140 defenders ranked)" in R._corner_line(
        board["games"][0]["scan"]["coverage"]["LA"]["corners"][0], grades["coverage"][("LA", "top corner")])
    rep = R.build(board["games"][0], board, names={}, form={"Top Wr": {"games": []}, "Mid Wr": {"games": []}},
                  grades=grades)
    text = json.dumps(next(s for s in rep["sections"] if s["key"] == "matchups"), ensure_ascii=False)
    assert G.NOTE in text and "our coverage grade 81" in text
    bare = R.build(board["games"][0], board, names={}, form={"Top Wr": {"games": []}})
    assert G.NOTE not in json.dumps(bare, ensure_ascii=False), "no grades, no note"
    assert R._week_of({"date": "2026-W07"}) == 7 and R._week_of({"date": "2026-10-24"}) is None


def test_nothing_fetches_from_pff():
    for base, _dirs, files in os.walk(os.path.join(ROOT, "engine")):
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(base, f), encoding="utf-8").read()
                assert "https://www.pff.com" not in src and "premium.pff.com" not in src, f


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
