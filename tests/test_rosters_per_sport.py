"""A roster belongs to a league.

Rosters used to be one page in the tools menu, next to Polymarket, and it
only ever meant the NFL. Two things wrong with that: "who is on this team"
is a question you ask *while* looking at a league's board, and every other
sport on the site had no answer at all.

Only the NFL has a published players file. For MLB, the NBA and the WNBA
the honest source is the one we already own — our own ingested game logs.
Who actually appeared, how often, how recently. That is a record of who
played rather than a copy of somebody's roster page, and the page must
never let those two read as the same claim.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect, upsert_player_logs
from engine import rosters as R


def _log(player, team, period, market="pa", season=2026, pos="OF"):
    return {"sport": "mlb", "season": season, "period": period,
            "game_id": f"{player}-{period}", "player": player, "team": team,
            "opponent": "XXX", "position": pos, "home": 1,
            "market": market, "value": 4.0}


def _seed():
    conn = connect(":memory:")
    rows = []
    for d in range(1, 21):
        rows.append(_log("Everyday Guy", "NYY", f"2026-07-{d:02d}"))
    for d in range(1, 6):
        rows.append(_log("Bench Guy", "NYY", f"2026-07-{d:02d}"))
    # Traded mid-season: BOS through June, NYY in July.
    for d in range(1, 11):
        rows.append(_log("Traded Guy", "BOS", f"2026-06-{d:02d}"))
    for d in range(15, 21):
        rows.append(_log("Traded Guy", "NYY", f"2026-07-{d:02d}"))
    upsert_player_logs(conn, rows)
    return conn


def test_players_are_listed_by_measured_playing_time():
    """With no published depth chart, playing time IS the depth chart —
    and it is measured rather than claimed."""
    out = R.from_game_logs(_seed(), "mlb", seasons=[2026], today="2026-07-21")
    nyy = out["teams"]["NYY"]["players"]
    assert [p["player"] for p in nyy][:2] == ["Everyday Guy", "Traded Guy"]
    assert nyy[0]["games"] == 20


def test_a_traded_player_appears_only_on_his_current_club():
    """He has rows under both teams. Listing him on both would show a
    roster the league does not have."""
    out = R.from_game_logs(_seed(), "mlb", seasons=[2026], today="2026-07-21")
    everyone = [p["player"] for t in out["teams"].values() for p in t["players"]]
    assert everyone.count("Traded Guy") == 1
    assert "Traded Guy" in [p["player"] for p in out["teams"]["NYY"]["players"]]
    assert "Traded Guy" not in [p["player"]
                                for p in out["teams"].get("BOS", {}).get("players", [])]


def test_somebody_who_stopped_appearing_is_shown_as_cold_not_deleted():
    """A roster with the missing players quietly removed reads as a
    healthy team."""
    out = R.from_game_logs(_seed(), "mlb", seasons=[2026], today="2026-08-15")
    nyy = out["teams"]["NYY"]
    assert nyy["unavailable"] == nyy["count"], "nobody has played in weeks"
    assert all(p["status"].startswith("not in a game since")
               for p in nyy["players"])


def test_a_week_number_period_makes_no_staleness_claim():
    """The NFL stores week numbers here, not dates. Comparing "018" to a
    date cutoff always succeeds and always means nothing — it would stamp
    a whole league "not in a game since 018"."""
    conn = connect(":memory:")
    upsert_player_logs(conn, [
        {"sport": "nba", "season": 2026, "period": "018", "game_id": "g1",
         "player": "Week Guy", "team": "BOS", "opponent": "MIA",
         "position": "G", "home": 1, "market": "min", "value": 30.0}])
    out = R.from_game_logs(conn, "nba", seasons=[2026], today="2026-08-01")
    p = out["teams"]["BOS"]["players"][0]
    assert p["unavailable"] is False and p["status"] == ""


def test_a_sport_with_no_appearance_market_returns_nothing_rather_than_guessing():
    assert R.from_game_logs(_seed(), "cfb")["player_count"] == 0


# --- the page ---------------------------------------------------------------
def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_rosters_is_a_sport_tab_not_a_tool_page():
    html = _read("web", "index.html")
    js = _read("web", "js", "app.js")
    assert 'data-sport="rosters"' not in html, "still a standalone tool page"
    assert 'data-view="rosters"' in html, "no per-sport tab"
    modes = re.search(r"const STANDALONE_MODES = \[([^\]]*)\]", js).group(1)
    assert '"rosters"' not in modes


def test_each_sport_loads_its_own_payload():
    js = _read("web", "js", "app.js")
    assert "rosters_${key}.json" in js or "rosters_${sport}.json" in js, \
        "the page still loads one shared roster file"


def test_switching_leagues_redraws_the_roster_tab():
    """Rosters live outside the slate, so nothing in renderAll touched
    them — switching leagues left the old league's teams on screen under
    the new league's header."""
    js = _read("web", "js", "app.js")
    fn = js[js.index("function renderAll("):js.index("function renderEmptySlate(")]
    assert 'state.view === "rosters"' in fn


def test_a_sport_with_no_roster_source_hides_the_tab():
    js = _read("web", "js", "app.js")
    hidden = js[js.index("const HIDDEN_VIEWS"):]
    hidden = hidden[:hidden.index("};")]
    assert '"rosters"' in hidden, "CFB has no player feed and must hide it"


def test_the_page_says_which_kind_of_roster_it_is_showing():
    """A published depth chart and a list of who happened to play are not
    the same claim, and the page must not present them as one."""
    js = _read("web", "js", "app.js")
    copy = js[js.index("const ROSTER_COPY"):js.index("function rosterPlayerHTML")]
    assert "depth chart" in copy, "the NFL's source is not described"
    for sport in ("mlb:", "nba:", "wnba:"):
        assert sport in copy, f"{sport} has no description of its source"
    assert "actually appeared" in copy


def test_the_search_box_speaks_the_sport_it_is_sitting_on():
    """It shipped asking for "49ers, SF, Purdy" on every league, which on
    the MLB page is an example of nothing you can type."""
    js = _read("web", "js", "app.js")
    block = js[js.index("const ROSTER_PLACEHOLDER"):js.index("const ROSTER_COPY")]
    for sport, hint in (("nfl", "Purdy"), ("mlb", "Judge"),
                        ("nba", "Tatum"), ("wnba", "Stewart")):
        assert f"{sport}:" in block and hint in block, f"{sport} has no examples"
    assert "search.placeholder = ROSTER_PLACEHOLDER" in js, \
        "the placeholder is defined but never applied"


def test_the_builder_covers_every_sport_the_site_shows():
    src = _read("rosters_build.py")
    for sport in ("mlb", "nba", "wnba"):
        assert f'"{sport}"' in src
    # And the ones with no source must be explained, not left blank.
    assert "cfb" in src and "ufc" in src
    assert "no free player-level roster feed" in src


def test_the_launcher_builds_them():
    src = _read("launch.py")
    assert "refresh_sport_rosters" in src
    fn = src[src.index("def refresh_all("):src.index("def _run_maintenance(")]
    assert "refresh_sport_rosters(" in fn, "never called from the refresh loop"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
