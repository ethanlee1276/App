"""The play-by-play page's other rooms.

Ethan, 2026-09-05: "the play by plays other rooms". The render's
sub-tabs, built where the data is real: Game info (the park facts),
Live props (the reader's open bets on this game, from the tracker),
Injuries (both clubs' designations from the injury board), Player
stats (the box score the fast loop writes into the deep file, through
the parsers the tracker already trusts). Team stats and Splits are not
built, on purpose: the summary's team block has not been probed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build                                              # noqa: E402
from engine.mlb import livestats                                    # noqa: E402
from engine.sources import nflpreseason, cfbdata                    # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
LIVE_BUILD = (ROOT / "live_build.py").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n//")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the engine ------------------------------------------------------------------
def test_football_rows_fold_one_market_per_line_into_one_row_per_player(monkeypatch=None):
    fake = [{"player": "Josh Allen", "team": "BUF", "opponent": "NYJ", "market": "pass_yds", "value": 212},
            {"player": "Josh Allen", "team": "BUF", "opponent": "NYJ", "market": "rush_yds", "value": 31},
            {"player": "Breece Hall", "team": "NYJ", "opponent": "BUF", "market": "rush_yds", "value": "88"},
            {"player": "Bad Row", "team": "NYJ", "opponent": "BUF", "market": "rec_yds", "value": "n/a"}]
    orig = nflpreseason.parse_boxscore
    nflpreseason.parse_boxscore = lambda payload, game: fake
    try:
        got = livescore_build.pbp_players("nfl", {}, {"home": "BUF", "away": "NYJ"})
    finally:
        nflpreseason.parse_boxscore = orig
    by = {r["player"]: r for r in got}
    assert by["Josh Allen"]["stats"] == {"pass_yds": 212.0, "rush_yds": 31.0} and by["Josh Allen"]["team"] == "BUF"
    assert by["Breece Hall"]["stats"] == {"rush_yds": 88.0}
    assert by["Bad Row"]["stats"] == {}, "a value the parser could not read is left out, not zeroed"


def test_college_and_hoops_rows_keep_the_parsers_own_contract():
    fake = [{"player": "Jeremiah Smith", "team": "OSU", "position": "WR", "stats": {"rec_yds": "104", "receptions": 6, "x": "?"}}]
    orig = cfbdata.parse_summary
    cfbdata.parse_summary = lambda payload: fake
    try:
        got = livescore_build.pbp_players("cfb", {}, {"home": "OSU", "away": "TEX"})
    finally:
        cfbdata.parse_summary = orig
    assert got == [{"player": "Jeremiah Smith", "team": "OSU", "position": "WR", "stats": {"rec_yds": 104.0, "receptions": 6.0}}]


def test_the_deep_file_carries_the_box_and_survives_a_parser_that_raises():
    orig = nflpreseason.parse_boxscore
    nflpreseason.parse_boxscore = lambda payload, game: (_ for _ in ()).throw(ValueError("shape"))
    try:
        doc = livescore_build.pbp_doc("nfl", {"event_id": "1", "home": "BUF", "away": "NYJ", "live": {}}, {"drives": []})
    finally:
        nflpreseason.parse_boxscore = orig
    assert "players" not in doc and "plays" in doc, "the tab is lost, the page is not"
    nflpreseason.parse_boxscore = lambda payload, game: [{"player": "A", "team": "BUF", "market": "rec_yds", "value": 1}]
    try:
        doc = livescore_build.pbp_doc("nfl", {"event_id": "1", "home": "BUF", "away": "NYJ", "live": {}}, {"drives": []})
    finally:
        nflpreseason.parse_boxscore = orig
    assert doc["players"] == [{"player": "A", "team": "BUF", "position": "", "stats": {"rec_yds": 1.0}}]


def test_the_mlb_box_reads_the_trackers_own_fields_and_names_the_sides():
    box = {"teams": {
        "home": {"players": {"ID1": {"person": {"fullName": "Aaron Judge"}, "position": {"abbreviation": "RF"},
                                     "stats": {"batting": {"hits": 2, "doubles": 1, "triples": 0, "homeRuns": 1, "plateAppearances": 4}}},
                             "ID2": {"person": {"fullName": "Gerrit Cole"}, "position": {"abbreviation": "P"},
                                     "stats": {"pitching": {"strikeOuts": 7, "inningsPitched": "6.1", "battersFaced": 24}}},
                             "ID3": {"person": {"fullName": "Bench Guy"}, "stats": {}},
                             "ID4": {"person": {}, "stats": {"batting": {"hits": 1}}}}},
        "away": {"players": {"ID5": {"person": {"fullName": "Rafael Devers"}, "stats": {"batting": {"hits": 0, "doubles": 0, "triples": 0, "homeRuns": 0}}}}},
    }}
    got = livestats.box_rows(box, home="NYY", away="BOS")
    by = {r["player"]: r for r in got}
    assert by["Aaron Judge"] == {"player": "Aaron Judge", "team": "NYY", "position": "RF",
                                 "stats": {"hits": 2.0, "home_runs": 1.0, "total_bases": 6.0, "pa": 4.0}}
    assert by["Gerrit Cole"]["stats"] == {"strikeouts": 7.0, "ip": "6.1", "bf": 24.0}
    assert by["Rafael Devers"]["team"] == "BOS" and by["Rafael Devers"]["stats"]["total_bases"] == 0.0
    assert "Bench Guy" not in by and len(got) == 3, "no line, no row; no name, no row"
    assert livestats.parse_live_stats(box)["aaron judge"]["total_bases"] == 6.0, "the same arithmetic the tracker uses"


def test_the_fast_loop_writes_the_box_on_the_five_minute_cache():
    i = LIVE_BUILD.index("def write_pbp(")
    body = LIVE_BUILD[i:LIVE_BUILD.index("\ndef main(", i)]
    assert 'doc["players"] = box_rows(fetch_boxscore(int(g["game_pk"])),' in body
    assert 'home=g.get("home") or "home", away=g.get("away") or "away")' in body
    assert "except Exception:" in body[body.index('doc["players"]'):], "a fetch that fails costs the tab and nothing else"
    assert 'f"mlb_box_{game_pk}.json", ttl=300' in (ROOT / "engine" / "mlb" / "sources" / "statslogs.py").read_text()


# --- the page --------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const teamsForSport = (lg) => ({{ BUF: {{ name: "Buffalo Bills" }}, NYJ: {{ name: "New York Jets" }} }});
      const isReturnRow = (r) => r.status === "Active";
      {_fn("pbpPropRows")}
      {_fn("pbpInjuryRows")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_props_and_injuries_rooms_pick_this_games_rows_only():
    got = _node("""
      const d = { home: "BUF", away: "NYJ" };
      const picks = [{ player: "A", game: { home: "BUF", away: "NYJ" } }, { player: "B", game: { home: "NYJ", away: "BUF" } },
                     { player: "C", game: { home: "KC", away: "LV" } }, { player: "D" }];
      const inj = [{ player: "X", team: "Buffalo Bills", status: "Out" }, { player: "Y", team: "New York Jets", status: "Questionable" },
                   { player: "Z", team: "Buffalo Bills", status: "Active" }, { player: "W", team: "Kansas City Chiefs", status: "Out" },
                   { player: "V", team: "buffalo bills", status: "Doubtful" }];
      return { props: pbpPropRows(picks, d).map((r) => r.player), none: pbpPropRows(null, d),
               inj: pbpInjuryRows(inj, "nfl", d).map((r) => r.player), injNone: pbpInjuryRows(undefined, "nfl", d) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["props"] == ["A"], "home and away in the tracker's own orientation; another game is another game"
    assert got["inj"] == ["X", "Y", "V"], "both clubs by the feed's club name, case aside; a return filing is not a designation"
    assert got["none"] == [] and got["injNone"] == []


def test_the_page_has_four_real_tabs_and_says_what_is_not_built():
    i = APP.index("const PBP_TABS = ")
    assert 'const PBP_TABS = [["info", "Game info"], ["props", "Live props"], ["injuries", "Injuries"], ["players", "Player stats"]];' in APP[i:i + 200]
    assert "Team stats and Splits are not built" in APP[i - 900:i]
    page = _fn("renderPbpPage")
    assert 'const tab = PBP_TABS.some(([k]) => k === _pbpTab) ? _pbpTab : "info";' in page
    assert 'tab === "props" ? pbpPropsHTML(d, league)' in page and 'tab === "players" ? pbpPlayersHTML(d, league)' in page
    assert '_pbpTab = b.dataset.pbpTab; renderPbpPage();' in page
    props = _fn("pbpPropsHTML")
    assert "if (state.sport !== league) {" in props and "No open bets on this game." in props
    players = _fn("pbpPlayersHTML")
    assert "No box score on file yet" in players and "the fields the open-bet tracker reads, nothing more" in players
    assert "marketWord(k)" in players, "the market words the record uses"
    for sel in (".pbp-tab.active", ".pbp-prop-row", ".pbp-box-row"):
        assert sel in CSS, sel
    assert "min-height: 44px" in CSS[CSS.index(".pbp-tab {"):CSS.index(".pbp-tab.active")], "a thumb-sized tab"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
