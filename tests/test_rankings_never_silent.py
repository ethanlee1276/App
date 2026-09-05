"""The football rankings section is never silently absent.

Ethan, 2026-09-05, word for word the request of 09-02: "For nfl and cfb
on the rankings page, we should have a section ranking the current
ranking for teams defense and offense." It shipped on 09-02 —
`engine.standings.unit_rankings`, drawn by `unitRankingsHTML` — and
returned "" whenever the build had no rankings. For the NFL that is
every day until Week 1 has finals (kickoff is the 10th), so the
section was invisible exactly when he looked for it.

The rankings are unchanged. The EMPTY case is what changes: on a
football page it renders the section with the build's own reason, and
on the NFL it fills the wait with the model's measured profile — points
scored and points allowed per game, ranked on the latest season with
enough finals — under the caveat the game page already prints.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_a_football_page_with_no_rankings_still_gets_the_section():
    body = _fn("unitRankingsHTML")
    assert 'const isFootball = state.sport === "nfl" || state.sport === "cfb";' in body
    assert "if (!isFootball) return \"\";" in body
    assert "return unitRankingsWaitHTML(d || {});" in body
    # The wait branch is the EMPTY branch, not a replacement for the
    # real rankings when they exist.
    assert body.index("return unitRankingsWaitHTML") < body.index("const CAP = 25;")


def test_the_reason_comes_from_the_builds_own_fields():
    body = _fn("unitRankingsWaitHTML")
    for field in ("d.season_wait", "d.first_games", "d.feed_error", "d.season"):
        assert field in body, field
    assert "hasn’t kicked off" in body
    assert "Scoring rankings start with the first finals." in body
    assert "fewer than four teams" in body


def test_the_nfl_wait_shows_the_models_profile_ranked_on_last_season():
    body = _fn("unitRankingsWaitHTML")
    assert "(state.data || {}).team_shapes || {}" in body
    assert "(state.data || {}).team_shapes_season" in body
    # Offense descending (points scored), defense ascending (points
    # allowed) — the same directions the scoring rankings use.
    assert '"offense", false)' in body and '"defense", true)' in body
    assert "ascending ? va - vb : vb - va" in body
    assert "shapes[t].raw[key]" in body
    assert "Last season’s" in body and "roster is not this season’s" in body


def test_fewer_than_four_shaped_teams_is_no_fallback_not_a_two_row_table():
    body = _fn("unitRankingsWaitHTML")
    assert "if (teams.length >= 4) {" in body


def test_the_scoring_rankings_render_exactly_as_before_when_present():
    body = _fn("unitRankingsHTML")
    assert "scoring offense and defense, in ${escapeHtml(" in body
    assert 'col("Offense", "most points scored", ur.offense)' in body
    assert 'col("Defense", "fewest points allowed", ur.defense)' in body


def test_the_page_hands_the_table_over():
    assert "${unitRankingsHTML(d.unit_rankings, d)}" in APP


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
