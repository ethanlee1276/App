"""Watch: a live game names where it streams, and the page links there.

Ethan, 2026-10-07: "on the live page for the games … we should put a
'watch' button and then it will link you to whatever streaming service is
hosting that game whether it's YouTube tv, or prime video, or peacock or
whatever."

The feeds already name the carrier — ESPN's scoreboard (football,
basketball, hockey) and MLB's schedule — so the chain is: parser → live
state → the fast file and the deep file → the page's table of which
service streams which network. Fixtures only; no network.

Run directly: `python3 tests/test_watch_button.py`
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import LiveStatus, live_to_dict                   # noqa: E402
from engine.sources import livescores as ls                           # noqa: E402
from engine.mlb.sources import live as mlive                          # noqa: E402
import livescore_build as LB                                          # noqa: E402
import live_build as MB                                               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _espn(broadcasts=None, geo=None):
    comp = {
        "competitors": [
            {"homeAway": "home", "score": "10", "team": {"id": "7", "abbreviation": "DEN", "displayName": "Denver Broncos"}},
            {"homeAway": "away", "score": "7", "team": {"id": "12", "abbreviation": "KC", "displayName": "Kansas City Chiefs"}}],
        "situation": {"downDistanceText": "2nd & 7 at DEN 45", "possession": "7", "possessionText": "DEN 45"}}
    if broadcasts is not None:
        comp["broadcasts"] = broadcasts
    if geo is not None:
        comp["geoBroadcasts"] = geo
    return {"events": [{"id": "401", "date": "2026-10-11T20:15Z",
                        "status": {"type": {"state": "in", "name": "STATUS_IN_PROGRESS", "detail": "4:12 - 2nd Quarter",
                                            "shortDetail": "4:12 - 2nd"}, "period": 2, "displayClock": "4:12"},
                        "competitions": [comp]}]}


def test_espn_names_the_national_carriers_first_and_never_the_radio():
    geo = [{"type": {"shortName": "TV"}, "market": {"type": "National"}, "media": {"shortName": "NBC"}},
           {"type": {"shortName": "Streaming"}, "market": {"type": "National"}, "media": {"shortName": "Peacock"}},
           {"type": {"shortName": "Radio"}, "market": {"type": "National"}, "media": {"shortName": "Westwood One"}},
           {"type": {"shortName": "TV"}, "market": {"type": "Home"}, "media": {"shortName": "KUSA"}}]
    row = ls.parse_espn_rows(_espn([{"market": "national", "names": ["NBC"]}], geo), "nfl")[0]
    assert row["live"].tv == ["NBC", "Peacock"] and row["live"].tv_local == ["KUSA"]
    plain = ls.parse_espn_rows(_espn(), "nfl")[0]
    assert plain["live"].tv is None and plain["live"].tv_local is None, "no block, no claim"
    assert live_to_dict(row["live"])["tv"] == ["NBC", "Peacock"]


def test_the_fast_file_and_the_deep_file_carry_it_only_when_named():
    geo = [{"type": {"shortName": "TV"}, "market": {"type": "National"}, "media": {"shortName": "Prime Video"}}]
    named = ls.parse_espn_rows(_espn(geo=geo), "nfl")[0]
    plain = ls.parse_espn_rows(_espn(), "nfl")[0]
    a, b = LB._row(named, "nfl"), LB._row(plain, "nfl")
    assert a["tv"] == ["Prime Video"] and a["tv_local"] == [] and "tv" not in b
    assert "tv" not in a["live"], "about the game, beside the team ids — not a piece of its state"
    doc = LB.pbp_doc("nfl", a, {"drives": {"previous": []}}, sides={})
    assert doc["tv"] == ["Prime Video"]
    assert "tv" not in LB.pbp_doc("nfl", b, {"drives": {"previous": []}}, sides={})


def test_mlb_asks_its_schedule_for_the_broadcasts_and_keeps_the_television_ones():
    src = (ROOT / "engine" / "mlb" / "sources" / "live.py").read_text()
    assert "hydrate=linescore,broadcasts(all)" in src
    nat, loc = mlive.mlb_carriers([
        {"name": "FOX", "type": "TV", "isNational": True, "homeAway": "home"},
        {"name": "Bally Sports Detroit", "type": "TV", "isNational": False, "homeAway": "home"},
        {"name": "97.1 The Ticket", "type": "AM", "isNational": False, "homeAway": "home"},
        {"name": "FOX", "type": "TV", "isNational": True, "homeAway": "away"}])
    assert nat == ["FOX"] and loc == ["Bally Sports Detroit"]
    st = LiveStatus(state="live", tv=["FOX"], tv_local=[])
    assert MB._row(1, st)["tv"] == ["FOX"]
    assert "tv" not in MB._row(2, LiveStatus(state="live"))
    assert mlive.mlb_carriers(None) == ([], [])


def test_the_page_knows_where_every_carrier_the_feeds_name_streams():
    """Every network the parsers can hand over has a door, and every door
    is an https front page — no guessed per-game address."""
    table = APP[APP.index("const STREAM_HOME = {"):APP.index("function streamKey(")]
    urls = re.findall(r'"(https?://[^"]+)"', table)
    assert urls and all(u.startswith("https://") for u in urls)
    keys = set(re.findall(r"^  (\w+): \[", table, re.M))
    rules = re.findall(r'\[/[^\]]+/i, "(\w+)"\]', table)
    assert rules and set(rules) <= keys, set(rules) - keys
    for k in ("peacock", "paramount", "foxone", "espn", "espnplus", "prime", "netflix", "nflplus", "ytv", "hbomax",
              "apple", "mlbtv", "nbalp", "wnbalp"):
        assert k in keys, k
    assert 'LEAGUE_OUT_OF_MARKET = { mlb: "mlbtv", nba: "nbalp", wnba: "wnbalp", nhl: "espnplus" }' in APP
    # "ESPN+" must not fall into ESPN, nor "YouTube TV" into YouTube: the
    # specific rule sits above the general one.
    assert table.index('"espnplus"]') < table.index('"espn"]') and table.index('"ytv"]') < table.index('"youtube"]')


def test_the_button_shows_only_while_the_game_is_live():
    """Ethan, 2026-10-07: "We should not show the 'watch' button until the
    game is live." The live cards are live by definition; the game page and
    the play-by-play page check the state themselves."""
    card = APP[APP.index("function liveCardHTML("):APP.index("function liveCardHTML(") + 4000]
    assert 'watchHTML(g, sport, "lb-watch")' in card
    pbp = APP[APP.index("async function renderPbpPage()"):]
    assert 'lv.state === "live" ? watchHTML(d, league, "pbp-watch") : ""' in pbp
    game = APP[APP.index("function renderGamePage()"):APP.index("function renderGamePage()") + 40000]
    assert 'isLive ? watchHTML(liveRowFor(state.sport, g) || g, state.sport, "gp-watch") : ""' in game
    assert '(row.live || {}).state === "live" ? watchHTML(row, state.sport, "gp-watch") : ""' in game
    fn = APP[APP.index("function watchHTML("):APP.index("function liveCardHTML(")]
    assert 'href="${safeHref(first.url)}"' in fn and 'target="_blank"' in fn and 'rel="noopener noreferrer"' in fn
    # No stream door: the carrier is still NAMED ("On NBC"); no carrier at all, nothing.
    assert "if (!list.length) {" in fn and 'class="watch-on">On ${escapeHtml(named.join(" · "))}' in fn
    assert 'return named.length ?' in fn and fn.index(': "";') > fn.index("return named.length ?"), "no carrier named, no button"
    assert 'id="gp-watch-slot"' in APP and 'watchHTML(row, state.sport, "gp-watch")' in APP, "the game page, once live"
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    assert ".watch-main {" in css and ".pbp-watch {" in css


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            n += 1
    print(f"\n{n} tests passed.")
