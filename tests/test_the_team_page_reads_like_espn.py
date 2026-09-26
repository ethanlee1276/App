"""The team page in ESPN's shape, and the doors onto it.

Ethan, 2026-09-24, with ESPN's Packers page beside ours: "I like all the
data we included but I want it too be layed out like the espn and include
all this information and have tabs for each page". And, the same message,
"Yes start all 3": team names open the team page everywhere, the game
page opens it on tonight's matchup, and a pick with one or two games
still draws its chart.

The header is ESPN's (crest, city over nickname, record and standing);
the tabs are ESPN's order — Home, Stats, Schedule, Roster, Depth Chart,
Injuries — then Versus and History, the two that were already ours.
Schedule and Depth Chart are new data: `teamdex.season_schedule` (the
games table holds the fixtures as well as the finals) and the published
NFL depth chart, written by the NFL build where it already loads it.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as DB, teamdex as T                          # noqa: E402
from engine.sources import depthcharts as D                        # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
VIS = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(DB.SCHEMA)
    c.executemany(
        "INSERT INTO games (sport,season,period,game_id,home,away,home_score,away_score,"
        "spread,total,date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [("nfl", 2026, "1", "a", "GB", "DET", 27, 20, -2.5, 47.5, "2026-09-13"),
         ("nfl", 2026, "2", "b", "CHI", "GB", 10, 24, 3.0, 44.0, "2026-09-20"),
         ("nfl", 2026, "10", "c", "GB", "MIN", None, None, -3.0, 45.5, "2026-11-15"),
         ("nfl", 2026, "3", "d", "GB", "DAL", None, None, None, None, "2026-09-27"),
         ("nfl", 2025, "1", "e", "GB", "SEA", 1, 2, None, None, "2025-09-10")])
    return c


# --- the new data -------------------------------------------------------------
def test_the_schedule_is_this_season_played_and_to_come_in_order():
    s = T.season_schedule(_conn(), "nfl", "GB")
    assert s["season"] == 2026, "the newest season with any game, fixtures included"
    assert [g["period"] for g in s["games"]] == ["1", "2", "3", "10"], "week 10 after week 3"
    won, away_win, nxt = s["games"][0], s["games"][1], s["games"][2]
    assert won["final"] and won["result"] == "W" and won["opponent"] == "DET" and won["line"] == -2.5
    assert away_win["line"] == -3.0, "the line is the Packers' own when they are the away side"
    assert nxt["final"] is False and nxt["opponent"] == "DAL" and "result" not in nxt
    assert T.season_schedule(_conn(), "nfl", "NOPE") == {"season": None, "games": []}


def test_the_published_depth_chart_reads_in_depth_order_from_the_newest_snapshot():
    rows = [{"dt": "2026-09-22", "club_code": "GB", "full_name": "Jordan Love", "depth_position": "QB", "depth_team": "1"},
            {"dt": "2026-09-22", "club_code": "GB", "full_name": "Malik Willis", "depth_position": "QB", "depth_team": "2"},
            {"dt": "2026-09-22", "club_code": "GB", "full_name": "Xavier McKinney", "depth_position": "FS", "depth_team": "1"},
            {"dt": "2026-09-22", "club_code": "GB", "full_name": "Josh Jacobs", "depth_position": "RB", "depth_team": "1"},
            {"dt": "2026-09-15", "club_code": "GB", "full_name": "Old Starter", "depth_position": "QB", "depth_team": "1"}]
    got = D.team_charts(rows, 3)
    assert got["as_of"] == "2026-09-22"
    assert got["teams"]["GB"] == [{"position": "QB", "players": ["Jordan Love", "Malik Willis"]},
                                  {"position": "RB", "players": ["Josh Jacobs"]},
                                  {"position": "FS", "players": ["Xavier McKinney"]}]
    assert D.CHART_FILE.startswith("data/built/"), "an ignored directory: build output is never committed"


def test_the_build_writes_it_and_the_server_serves_it():
    src = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert "write_team_charts(rows, args.week)" in src
    import server
    root = Path(tempfile.mkdtemp())
    (root / "data" / "built").mkdir(parents=True)
    (root / D.CHART_FILE).write_text(json.dumps({"as_of": "2026-09-22", "teams": {"GB": [{"position": "QB", "players": ["Jordan Love"]}]}}))
    was = server.ROOT
    server.ROOT = root
    try:
        assert server._depth_chart("nfl", "GB") == {"as_of": "2026-09-22", "positions": [{"position": "QB", "players": ["Jordan Love"]}]}
        assert server._depth_chart("nfl", "DET") is None and server._depth_chart("mlb", "GB") is None
    finally:
        server.ROOT = was
    body = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"schedule": _schedule_or_empty(teamdex, conn, sport, team),' in body
    assert '"depth": _depth_chart(sport, team)}' in body


# --- the page -----------------------------------------------------------------
def test_the_tabs_are_espns_then_ours():
    i = APP.index("const TEAM_TABS = ")
    tabs = re.findall(r'\["(\w+)", "([^"]+)"\]', APP[i:APP.index(";", i)])
    assert [t[1] for t in tabs] == ["Home", "Stats", "Schedule", "Roster", "Depth Chart",
                                    "Injuries", "Versus", "History"]
    page = _fn("renderTeamPage")
    for k, fn in (("home", "teamHomeHTML"), ("schedule", "teamScheduleHTML"), ("depth", "teamDepthHTML"),
                  ("injuries", "teamInjuriesHTML")):
        assert f"{k}: () => {fn}(" in page, k
    assert "${teamHeaderHTML(d, p)}" in page and 'role="tablist"' in page
    assert 'data-team-tab="${k}"' in page


def test_the_header_is_crest_city_nickname_and_standing():
    head = _fn("teamHeaderHTML")
    assert "teamMarkIn(d.sport, p.team, 64)" in head
    assert 'class="tm-city"' in head and 'class="tm-nick"' in head
    assert "in ${std.group}" in head, "“2nd in NFC North”, off the league's own standings"


def test_a_tab_is_kept_through_a_chip_and_reset_by_a_new_team():
    fn = APP[APP.index("async function openTeam(sport, team, vs, tab) {"):]
    assert 'tab: tab || (same ? _teamState.tab : (vs ? "vs" : "home")),' in fn[:3000]
    listener = APP[APP.index('const tabBtn = e.target.closest && e.target.closest("[data-team-tab]");'):][:500]
    assert "_teamState.tab = tabBtn.dataset.teamTab;" in listener and "renderTeamPage();" in listener


def test_the_tab_strip_scrolls_away_with_the_page():
    i = CSS.index(".tm-tabs {")
    rule = CSS[i:CSS.index("}", i)]
    # Ethan, 2026-09-24, twice: "fix how this bar follows when I scroll
    # down", then "you didn't fix how this bar follows me when I scroll
    # down the page". It does not follow.
    assert "position: sticky" not in rule and "position: fixed" not in rule
    assert "hdr-shift" not in CSS and "headerShiftVar" not in APP, "the header offset had only the strip to tell"
    tab = CSS[CSS.index(".tm-tab {"):]
    assert "min-height: 44px" in tab[:tab.index("}")]
    on = CSS[CSS.index(".tm-tab.on {"):]
    assert "border-bottom-color: var(--brand)" in on[:on.index("}")]


def test_the_depth_chart_says_which_it_is():
    fn = _fn("teamDepthHTML")
    assert "as the team filed it" in fn and "ordered by who has actually played" in fn
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = "\n".join([
        "const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml;",
        "const slugify = (s) => String(s).toLowerCase().replace(/ /g, '-');",
        "const teamEmptyTab = (m) => 'EMPTY:' + m;", "const teamInjMark = (n) => n === 'C D' ? ' <abbr>Q</abbr>' : '';", "const teamInjKeyHTML = () => '<KEY>';",
        _fn("ordinal"), _fn("teamDepthHTML"),
        "const measured = teamDepthHTML({ squad: { positions: [{ position: 'QB', players: [{ player: 'A B' }, { player: 'C D' }] }] } });",
        "const filed = teamDepthHTML({ depth: { as_of: '2026-09-22', positions: [{ position: 'QB', players: ['Jordan Love'] }] }, squad: { positions: [] } });",
        "process.stdout.write(JSON.stringify([measured, filed, teamDepthHTML({})]));"])
    out = json.loads(subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60, check=True).stdout)
    assert "ordered by who has actually played" in out[0] and ">A B</button>" in out[0] and "<th>2nd</th>" in out[0]
    assert ">C D</button> <abbr>Q</abbr></td>" in out[0], "the letter sits beside the name"
    assert out[0].rstrip().endswith("<KEY>") and out[1].rstrip().endswith("<KEY>"), "the key closes the chart"
    assert "as the team filed it, 2026-09-22" in out[1] and 'data-player-page="jordan-love"' in out[1]
    assert out[2].startswith("EMPTY:")


def test_the_injury_tab_finds_the_team_under_espns_full_name():
    fn = _fn("teamInjuryRows")
    assert "ffNorm(r.team || \"\") === want" in fn and "!isReturnRow(r)" in fn


def test_the_record_footer_sits_only_under_what_the_finals_built():
    page = _fn("renderTeamPage")
    assert '["home", "schedule", "vs", "history"].includes(tab)' in page



def test_an_injured_player_carries_espns_red_letter():
    """Ethan, 2026-09-24, on the depth chart: "make sure we indicate if that
    player is out or questionable or on ir … Put a Q or O or IR next too
    the names in red." Off the same injury board as the Injuries tab."""
    assert "${teamInjMark(r.names[i])}" in _fn("teamDepthHTML")
    assert "${teamInjMark(w.player)}" in _fn("teamSquadHTML")
    assert "_teamInj = teamInjuryMap(d, p);" in _fn("renderTeamPage")
    assert '["home", "injuries", "depth", "roster"].includes(tab)' in _fn("renderTeamPage")
    rule = CSS[CSS.index(".tm-inj {"):]
    assert "color: var(--bad)" in rule[:rule.index("}")]
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    i = APP.index("const TEAM_INJ_MARKS = ")
    prog = APP[i:APP.index(";\n", i) + 2] + _fn("teamInjMarkOf") + (
        "process.stdout.write(JSON.stringify(['Questionable', 'Out', 'Injured Reserve', 'Doubtful', "
        "'Suspension', 'Physically Unable to Perform', '10-Day-IL', 'Day-To-Day', 'Active', '']"
        ".map(teamInjMarkOf)));")
    got = json.loads(subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60, check=True).stdout)
    assert got == ["Q", "O", "IR", "D", "SUSP", "PUP", "IL", "DTD", "", ""], got


def test_a_key_says_what_the_letters_mean():
    """Ethan, 2026-09-24: "create like a key section … so people will know
    what the letters mean". Under the depth chart and the roster; the
    league's own letters; every letter the mark can draw is in a key."""
    assert "${teamInjKeyHTML(d.sport)}" in _fn("teamDepthHTML")
    assert "rosterTab + teamInjKeyHTML(d.sport)" in _fn("renderTeamPage")
    key = _fn("teamInjKeyHTML")
    assert 'sport === "nfl" || sport === "cfb" ? "football" : "other"' in key
    i = APP.index("const TEAM_INJ_KEY = ")
    block = APP[i:APP.index("};", i)]
    keyed = set(re.findall(r'\["([A-Z]+)", "', block))
    j = APP.index("const TEAM_INJ_MARKS = ")
    drawn = set(re.findall(r'"([A-Z]+)"\]', APP[j:APP.index(";\n", j)]))
    assert drawn <= keyed, f"a letter with no key: {drawn - keyed}"
    assert '"Questionable"' in block and '"Injured reserve"' in block and '"Out"' in block

# --- the doors ------------------------------------------------------------------
def test_the_game_page_opens_the_team_on_tonights_matchup():
    assert "${gpTeamDoor(g.away, g.home)}" in APP and "${gpTeamDoor(g.home, g.away)}" in APP
    assert 'data-team-against="${escapeAttr(opp)}"' in _fn("gpTeamDoor")
    assert 'pick.dataset.teamAgainst || "",' in APP
    home = _fn("teamHomeHTML")
    assert 'data-team-tab="vs"' in home and "Against the ${" in home


def test_team_names_in_page_headers_are_doors():
    link = _fn("teamLinkHTML")
    assert '<button type="button" class="team-link"' in link and "data-team-open=" in link
    assert "teamLinkHTML(state.sport, b.away, b.away)" in _fn("renderGameBetPage")
    prop = _fn("renderPropPage")
    assert "teamLinkHTML(state.sport, r.team)" in prop and "vs ${teamLinkHTML(state.sport, r.opponent)}" in prop
    assert "vs ${teamLinkHTML(lg, r.opponent)}" in APP, "the player page's header"
    assert "teamLinkHTML(state.sport, t.team, meta.name || meta.nick || t.team)" in _fn("standingsRowHTML")
    # A header that is a door itself lets an inner button win.
    assert 'if (e.target.closest("a, button, input, label, select, .chip")) return;' in APP


def test_a_pick_with_one_or_two_games_still_draws_its_chart():
    fn = _fn("propAnalysis", VIS)
    assert "if (vals.length < (opts.min || 3)) return \"\";" in fn, "lists keep three"
    assert "ONLY ${n} GAME${n === 1 ? \"\" : \"S\"} SO FAR vs PROP LINE" in fn
    prop = _fn("renderPropPage")
    assert "tier: tier && tier.word, min: 1 })" in prop and "propAnalysis(r, { min: 1 })" in prop


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
