"""One league picker per screen (audit V-16, roadmap #46).

The audit counted four sport selectors: the league strip, the Live tab's
"ALL 2 / NFL 1" row, Tonight's "NFL / ALL SPORTS", the Record's chips,
and a league <select> in the games strip that mirrored the strip. On a
phone the page's row sat under the strip, two selectors stacked, both
saying NFL and meaning different things.

Pinned here:
  * one builder (`leagueChipsHTML`) draws the Live, Tonight and Record rows;
  * Tonight's row is a full league picker, and a league button switches
    the board through the strip's own button;
  * Live lists every live-feed league, at 0 too;
  * on those three pages the strip steps aside under 1280px;
  * the games strip's league select is gone.

Run directly: `python3 tests/test_one_league_picker.py`
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i)]


def test_one_builder_draws_every_page_level_league_row():
    assert "leagueChipsHTML(items, { group: \"lb-chips tn-chips\"" in _fn("tonightChipsHTML")
    assert "leagueChipsHTML(chips.map(" in _fn("renderLiveBoard")
    assert "leagueChipsHTML(parts, { group: \"rec-scopes\"" in _fn("recordScopeHTML")
    b = _fn("leagueChipsHTML")
    assert 'role="group"' in b and 'aria-pressed="${on}"' in b


def test_tonight_s_row_switches_the_league_through_the_strip():
    t = _fn("tonightChipsHTML")
    assert "tonightLeagueOrder([...SPORT_CODES" in t and '{ key: "all", label: "All sports" }' in t
    bind = _fn("bindTonightChips")
    assert '.sportbar-in .sport-btn[data-sport="${want}"]' in bind and "btn.click()" in bind


def test_live_lists_every_live_league():
    live = _fn("renderLiveBoard")
    assert 'const chips = ["all", ...Object.keys(LIVE_FEEDS)];' in live
    assert "(bySport[s] || 0)" in live


def test_the_strip_steps_aside_where_the_page_has_its_own_row():
    i = CSS.index("/* ONE LEAGUE PICKER")
    block = CSS[i:i + 900]
    assert "@media (max-width: 1279px)" in block
    assert "body:has(#view-live.active, #view-tonight.active, #view-record.active) .sportbar { display: none; }" in block


def test_the_games_strip_has_no_league_select():
    assert 'id="games-sport"' not in HTML and "games-sport" not in APP and "games-sport" not in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
