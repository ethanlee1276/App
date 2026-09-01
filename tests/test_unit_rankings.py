"""Football team rankings — scoring offense and defense, from the table.

Ethan, 2026-09-02: "For nfl and cfb on the rankings page, we should
have a section ranking the current ranking for teams defense and
offense." Built from the standings table's OWN rows, so the rankings
can never disagree with the records beside them, and labeled "scoring"
honestly — we hold league-wide points, not yardage.

Run directly: `python3 tests/test_unit_rankings.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.standings import unit_rankings


def _table(sport="nfl", teams=None):
    rows = []
    for i, (abbr, pf, pa) in enumerate(teams or [
            ("KC", 28.4, 19.2), ("BUF", 26.0, 21.0),
            ("NYJ", 15.5, 24.8), ("NE", 17.0, 14.9)]):
        rows.append({"team": abbr, "games": 4, "record": "2-2",
                     "pf_per_game": pf, "pa_per_game": pa,
                     "rank": i + 1})
    return {"sport": sport, "groups": [{"label": "A", "teams": rows[:2]},
                                       {"label": "B", "teams": rows[2:]}]}


def test_offense_ranks_high_scoring_first_and_defense_low_allowed():
    got = unit_rankings(_table())
    assert got["measure"] == "points per game"
    assert [r["team"] for r in got["offense"]] == ["KC", "BUF", "NE", "NYJ"]
    assert [r["team"] for r in got["defense"]] == ["NE", "KC", "BUF", "NYJ"]
    assert got["offense"][0]["rank"] == 1
    assert got["offense"][0]["value"] == 28.4
    assert got["defense"][0]["value"] == 14.9
    assert got["offense"][0]["record"] == "2-2"


def test_only_football_and_only_played_seasons_get_rankings():
    assert unit_rankings(_table(sport="mlb")) is None
    assert unit_rankings({"sport": "nfl", "groups": []}) is None
    waiting = _table()
    for g in waiting["groups"]:
        for t in g["teams"]:
            t["games"] = 0
    assert unit_rankings(waiting) is None, \
        "an unplayed season has no rankings to claim"
    thin = {"sport": "nfl",
            "groups": [{"teams": _table()["groups"][0]["teams"][:1]}]}
    assert unit_rankings(thin) is None


def test_cfb_rides_the_same_rails():
    got = unit_rankings(_table(sport="cfb"))
    assert got and len(got["offense"]) == 4


def test_the_build_attaches_it_and_the_page_draws_it():
    with open(os.path.join(ROOT, "standings_build.py"),
              encoding="utf-8") as f:
        assert 'table["unit_rankings"] = ur' in f.read()
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    assert "function unitRankingsHTML(ur)" in js
    assert "unitRankingsHTML(d.unit_rankings)" in js
    at = js.index("function unitRankingsHTML")
    body = js[at:js.index("\nasync function renderStandings", at)]
    assert "scoring offense and defense" in body, \
        "the section says WHICH measure it ranks"
    assert "teamMarkIn(state.sport" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
