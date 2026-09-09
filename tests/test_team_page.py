"""The team page: searched, routed, and drawn.

Ethan, 2026-09-09: *"I should be able to search for the Los Angeles Rams,
and look at how they've played against any team in the past."*

`engine/teamdex` does the arithmetic and `tests/test_teamdex.py` guards
it. This is the page — and three of the things it guards are bugs the
SOURCE could not have shown me. I found them by opening the page in a
browser, which is the only reason they are fixed:

  * THE ADDRESS BAR LIED. `openTeam` wrote the deep link and then called
    `switchView`, which runs through the View Transitions API — so its
    own `pushState("#team")` landed AFTER. The page showed the Rams
    against Arizona and the URL said `#team`, which means every link a
    reader copied opened somewhere else. The write belongs in
    `_switchViewNow`, where every other deep view does it.
  * THREE CHIPS FOR ONE TEAM. The colour dictionary carries a
    franchise's old keys too — the Rams answer to LA, LAR and STL — so
    "rams" offered three identical chips, two of which open a page with
    no games on it.
  * THIRTY-ONE OPPONENTS IS A WALL. Measured on a 430px phone: the full
    list pushed the head-to-head table, the thing he came for, to 1050px
    down the page. Twelve and a toggle puts it at 772.

Run directly: `python3 tests/test_team_page.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(name)


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";", i) + 1]


_STUBS = """
function escapeHtml(s) { return String(s == null ? "" : s); }
function escapeAttr(s) { return String(s == null ? "" : s); }
function icon(n) { return "[" + n + "]"; }
function teamMark(t) { return "<i>" + t + "</i>"; }
function nflMap() { return TEAMS; }
"""

#: The shape `web/js/teams.js` really has, including the historical keys
#: that made one franchise look like three.
_TEAMS = {
    "LA": {"name": "Los Angeles Rams", "nick": "Rams", "loc": "LA Rams"},
    "LAR": {"name": "Los Angeles Rams", "nick": "Rams", "loc": "LA Rams"},
    "STL": {"name": "Los Angeles Rams", "nick": "Rams", "loc": "LA Rams"},
    "LAC": {"name": "Los Angeles Chargers", "nick": "Chargers",
            "loc": "LA Chargers"},
    "NE": {"name": "New England Patriots", "nick": "Patriots",
           "loc": "New England"},
    "MIN": {"name": "Minnesota Vikings", "nick": "Vikings",
            "loc": "Minnesota"},
}


def _run(script, fns, consts=()):
    src = (_STUBS + f"const TEAMS = {json.dumps(_TEAMS)};\n"
           + f"const state = {{ sport: 'nfl', search: '' }};\n"
           + "\n".join(_const(c) for c in consts) + "\n"
           + "\n".join(_fn(n) for n in fns) + "\n" + script)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2500:]
    return json.loads(res.stdout)


# ---------------------------------------------------- the search matches

def _hits(q):
    return _run(f"console.log(JSON.stringify(teamSearchHits({json.dumps(q)})));",
                ["ffNorm", "teamSearchHits"])


def test_one_chip_per_franchise_not_one_per_key():
    """The Rams answer to LA, LAR and STL in the colour dictionary. Two
    of those three open a page with no games on it."""
    got = _hits("rams")
    assert [h["name"] for h in got] == ["Los Angeles Rams"], got


def test_a_city_that_is_two_teams_offers_two():
    got = [h["name"] for h in _hits("los angeles")]
    assert got == ["Los Angeles Chargers", "Los Angeles Rams"], got


def test_an_abbreviation_matches_only_exactly():
    """Two letters inside a colour key is a coincidence, not a search.
    Substring matching on the abbreviation pulls Minnesota out of "ne"."""
    assert [h["abbr"] for h in _hits("ne")] == ["NE"], _hits("ne")
    # "st" is the front of the abbreviation STL and the front of nothing
    # else — no name, nickname or location starts with it. If the
    # abbreviation matched by prefix, this would hand back the Rams.
    assert _hits("st") == [], "an abbreviation matched on a fragment"
    # …and a prefix of a real NAME still matches, which is the rule that
    # makes the box usable: "mi" is Minnesota.
    assert [h["abbr"] for h in _hits("mi")] == ["MIN"], _hits("mi")


def test_one_character_matches_nothing():
    assert _hits("l") == [] and _hits("") == []


def test_the_chip_hands_the_server_a_name_not_a_key():
    """One resolver, server-side, against the teams that actually have
    finals — otherwise the page has to know which of LA/LAR/STL the
    database uses, and the two can disagree."""
    body = _fn("renderTeamHits")
    assert 'data-team-open="${escapeAttr(t.name)}"' in body, body


# --------------------------------------------------------- the opponents

def _picker(n, picked=None):
    d = {"opponents": [{"team": f"T{i}", "name": f"Team {i}", "games": n - i}
                       for i in range(n)]}
    if picked:
        d["head_to_head"] = {"opponent": picked}
    return _run(
        "let _teamOppAll = false;\n"
        f"console.log(JSON.stringify(teamOppPickerHTML({json.dumps(d)})));",
        ["teamOppPickerHTML"], ["TEAM_OPP_SHOWN"])


def test_a_long_opponent_list_collapses_behind_a_count():
    out = _picker(31)
    assert out.count("data-team-vs=") == 12, out.count("data-team-vs=")
    assert "+19 more" in out


def test_a_short_list_gets_no_toggle_at_all():
    out = _picker(5)
    assert out.count("data-team-vs=") == 5
    assert "more" not in out


def test_the_opponent_you_are_looking_at_is_never_collapsed_away():
    """He picked one out of the tail, then the list collapsed. Hiding the
    chip that is currently ON would leave the table below it belonging to
    nothing on screen."""
    out = _picker(31, picked="T30")
    assert "T30" in out, out
    assert 'aria-pressed="true"' in out


# ------------------------------------------------------------ the drawing

def test_the_line_shown_is_the_teams_own_and_an_ungraded_game_is_blank():
    """The stored spread is the HOME team's. Printing it under the Rams
    when Seattle was home is correct arithmetic answering somebody
    else's question — `engine/teamdex` flips it, and this checks the page
    prints what it was handed rather than re-deriving it."""
    h = {"name": "Rams", "opponent_name": "Seahawks",
         "summary": {"games": 2, "record": "1-1", "pf_per_game": 24.0,
                     "pa_per_game": 24.0, "ats_w": 1, "ats_l": 0, "ats_p": 0,
                     "over": 0, "under": 1, "ou_p": 0},
         "games": [
             {"season": 2025, "period": "021", "at_home": False, "result": "L",
              "margin": -4, "points_for": 27, "points_against": 31,
              "line": 2.5, "covered": False, "total": 45.5, "ou": "over"},
             {"season": 2024, "period": "010", "at_home": True, "result": "W",
              "margin": 3, "points_for": 24, "points_against": 21,
              "line": None, "covered": None, "total": None, "ou": None},
         ]}
    out = _run("console.log(JSON.stringify(teamH2HHTML("
               + json.dumps(h) + ', "nfl")));',
               ["teamRecordLine", "_teamWeek", "teamH2HHTML"])
    assert "+2.5" in out, out
    assert "Conf. Champ" in out, "a week-21 NFL game read as Week 21"
    # Losing by four as a 2.5-point dog is NOT a cover, and the row says
    # so rather than leaving the column blank.
    assert ">no<" in out, out
    # The ungraded row keeps its result — a win is still a win — while
    # its line, ATS and total are struck rather than guessed. Three
    # cells, which is what makes this different from dropping the row.
    assert out.count("rank-none") == 3, out.count("rank-none")
    assert "W" in out and "L" in out
    assert "null" not in out and "undefined" not in out


def test_a_matchup_with_no_meetings_says_so_rather_than_drawing_an_empty_table():
    out = _run("console.log(JSON.stringify(teamH2HHTML({name:'A',"
               "opponent_name:'B',games:[],summary:{}}, 'nfl')));",
               ["teamRecordLine", "_teamWeek", "teamH2HHTML"])
    assert "No finals between" in out and "<table" not in out


def test_the_playoff_rounds_are_named_and_only_in_football():
    got = _run("console.log(JSON.stringify(["
               '_teamWeek("nfl","021"), _teamWeek("nfl","005"),'
               '_teamWeek("cfb","021"), _teamWeek("nfl","")]));',
               ["_teamWeek"])
    assert got == ["Conf. Champ", "Week 5", "Week 21", ""], got


# -------------------------------------------------------------- the wiring

def test_the_address_bar_is_written_where_every_other_deep_view_writes_it():
    """The bug a browser found. `openTeam` wrote the URL and then called
    `switchView`, whose own pushState lands after it — so the page showed
    one matchup and the address bar named another, and a copied link
    opened the wrong page."""
    body = _fn("openTeam")
    assert "replaceState" not in body, \
        "openTeam is writing the URL again; switchView will overwrite it"
    i = APP.index('if (name === "team") {')
    branch = APP[i:APP.index('if (name === "game") {', i)]
    assert "history.replaceState" in branch and "teamHref(" in branch
    assert "renderTeamPage()" in branch


def test_one_router_serves_the_cold_load_and_the_click():
    """This app has been caught once with a branch in one router and not
    the other — the #parlays migration, which worked from a link and not
    from a bookmark."""
    assert APP.count("function teamRoute(h)") == 1
    assert APP.count("if (teamRoute(h)) return;") == 2
    fn = _fn("teamRoute")
    assert 'h.slice(0, 5) !== "team/"' in fn
    assert "decodeURIComponent" in fn
    # Split, not regexed: a college key is `espn:61`.
    assert '.split("/")' in fn


def test_the_view_has_a_section_and_a_place_in_the_order():
    assert 'id="view-team"' in HTML and 'id="team-page"' in HTML
    assert 'id="team-hits"' in HTML
    i = APP.index("const VIEW_ORDER = [")
    assert '"team"' in APP[i:APP.index("];", i)], "a view missing from " \
        "VIEW_ORDER animates as though you had gone backwards to reach it"



# --------------------------------------------- the tap that had to work

def test_the_chip_names_the_league_it_was_drawn_for():
    """Ethan hit this within an hour of the page shipping: tapping "Los
    Angeles Rams" on the search page returned the server's own "unknown
    sport" and drew an empty page.

    The handler was taking `_teamState.sport`, which is `""` until a team
    page has been opened — so the FIRST tap anybody makes, from the
    search box, sent `sport=` and was rejected. Every test I had passed,
    because I had exercised the chip's markup and the team page's route
    and never the click between them.

    The chip carries the league now. That is the right source and not
    merely the working one: the ambiguity chooser is drawn on a page that
    may itself have been reached by a shared link into another league, so
    `state.sport` is not reliably the team's league either. Whoever drew
    the chip knew which league it was; it says so.
    """
    for fn in ("renderTeamHits", "renderTeamPage"):
        body = _fn(fn)
        assert "data-team-open=" in body, fn
        assert "data-team-sport=" in body, \
            f"{fn} draws a chip that cannot say which league it means"


def test_the_handler_reads_the_league_off_the_chip_before_anything_else():
    import re as _re
    i = APP.index('e.target.closest("[data-team-open]")')
    body = APP[i:i + 1400]
    # COMMENTS STRIPPED FIRST. The block carries a paragraph explaining
    # the bug, and that paragraph NAMES `_teamState.sport` — so the
    # ordering check below read the explanation as the code and failed on
    # a correct fix. Third time this trap has been sprung in this repo.
    code = _re.sub(r"/\*.*?\*/", "", body, flags=_re.S)
    code = _re.sub(r"(?<!:)//[^\n]*", "", code)
    assert "pick.dataset.teamSport ||" in code, code[:300]
    # The fallbacks are a belt, and they must not come FIRST — reading
    # `_teamState.sport` before the chip is exactly the bug.
    assert code.index("pick.dataset.teamSport") < code.index("_teamState.sport")


def test_a_cold_search_tap_sends_a_real_sport():
    """The failure, reproduced without a browser: `_teamState` at its
    initial value, a chip drawn by the search page, and the argument the
    handler would actually pass. `""` is what the server rejects."""
    got = _run("""
      let _teamState = { sport: "", team: "", vs: "", data: null };
      let sent = null;
      function openTeam(sport, team, vs) { sent = [sport, team, vs]; }
      const pick = { dataset: { teamSport: "nfl", teamOpen: "Los Angeles Rams" } };
      openTeam(pick.dataset.teamSport || _teamState.sport || state.sport,
               pick.dataset.teamOpen, "");
      console.log(JSON.stringify(sent));""", [])
    assert got == ["nfl", "Los Angeles Rams", ""], got
    assert got[0], "the endpoint rejects an empty sport with 400 unknown sport"

if __name__ == "__main__":
    if not shutil.which("node"):
        print("SKIP node is not installed; this file executes the renderer. "
              "`apt install -y nodejs`")
        print("\n0 tests passed.")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
