"""The game page in the clubs' colours (GP1).

Ethan, 2026-11-01, four screenshots of Apple Sports on Vikings @ Lions, live in
the fourth quarter: "Look at this live play by play and live box score and stat
page, I want ours too look just like this. I love how they use the team color
for the background". Drawn our way, with nothing of Apple's own. What these
hold:

  - every sport's game file carries the period line and the building where
    ESPN's summary has them (livescore_build.pbp_doc); the scorer's table
    stays basketball's;
  - the wash: each club's own colour, deepened until white type reads on it,
    black giving way to the club's next colour, the away side taking another
    of its own when the two would look alike, grey for a club with none;
  - the line score: the file's own, else read off the plays (each period's
    last score less the one before, the newest period catching up with the
    scoreboard, no line at all when a period has no play), regulation's
    columns always, overtime after, the total last;
  - the field: home's end zone on the left and away's on the right, as the
    drive card, the drive chart and the ground's picture draw it, each named;
    the line of scrimmage, the line to gain (the goal line on "& Goal"), the
    drive's band from where it started; nothing at a hold, a final or without
    a spot;
  - the tabs: Stats, Play-By-Play, Standings, Our picks; a live game opens on
    Play-By-Play, any other on Stats;
  - Stats: the odds as a book prints them (live, pregame, the open), the team
    stats with a bar a side (a rate compared as a rate, a clock as seconds),
    each side's box score, the facts; a final leads with its scoring plays;
  - Play-By-Play: drive by drive, newest first, under its quarter, the drive
    on now open, and what a reader opens stays open through the poll;
  - Standings: the two clubs' divisions, the two lit, ties only where any;
  - the compact bar: inert while hidden, drawn shown on a redraw when the
    reader is down the page;
  - the page is dark on the wash in either theme, its cards a glass with no
    blur, and the wash leaves with the view;
  - and in a browser (QB_BROWSER_TESTS=1), at a phone's width: the wash fills
    the screen behind the page, nothing scrolls sideways, the field and the
    line score are drawn, the four tabs fit, and scrolling past the score
    brings the compact bar down.

    python3 tests/test_the_game_page_wears_the_team_colours.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
GP = DETAIL[DETAIL.rindex("/*", 0, DETAIL.index("   THE GAME PAGE IN THE CLUBS' COLOURS")):]
GP_CSS = CSS[CSS.rindex("/*", 0, CSS.index("   THE GAME PAGE IN THE CLUBS' COLOURS")):]
COLOUR_MATH = DETAIL[DETAIL.index("const PBP_READS"):DETAIL.index("function pbpSideColours(")]


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


STUBS = r"""
const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const escapeAttr = escapeHtml;
const icon = (n) => `<i data-icon="${n}"></i>`;
const teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
const TABLES = { nfl: {
  MIN: { name: "Minnesota Vikings", nick: "Vikings", primary: "#4f2683", secondary: "#ffc62f" },
  DET: { name: "Detroit Lions", nick: "Lions", primary: "#0076b6", secondary: "#b0b7bc" },
  CIN: { name: "Cincinnati Bengals", nick: "Bengals", primary: "#000000", secondary: "#fb4f14" },
  PIT: { name: "Pittsburgh Steelers", nick: "Steelers", primary: "#ffb612", secondary: "#101820" },
  NYG: { name: "New York Giants", nick: "Giants", primary: "#0b2265", secondary: "#a71930" },
  BUF: { name: "Buffalo Bills", nick: "Bills", primary: "#00338d", secondary: "#c60c30" },
  GB: { name: "Green Bay Packers", nick: "Packers", primary: "#203731", secondary: "#ffb612" },
} };
const teamsIn = (lg) => TABLES[lg] || {};
const teamNameIn = (lg, a) => (teamsIn(lg)[a] || {}).nick || a;
const PBP_FOOTBALL = new Set(["nfl", "cfb"]);
const liveHoldWord = (lv) => ((lv || {}).hold ? String(lv.hold) : "");
const pbpTime = (iso) => (iso ? "1:00 PM" : "");
const pbpOrd = (n) => n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
const MINUS = "−";
const american = (o) => (o > 0 ? `+${o}` : `${MINUS}${Math.abs(o)}`);
let LIVE = null;
const liveLineOf = () => LIVE;
const lineTrackHTML = () => "<div class=\"track\"></div>";
const driveResultWord = (dr) => String((dr || {}).result || "");
const footballWords = (p) => ({ snap: !/timeout|end/i.test(p.event || ""), title: `${p.event} words` });
const playsHTML = (g) => `<ol class="plays">${(g.plays || []).map((p) => `<li>${p.event}</li>`).join("")}</ol>`;
const pbpRoom = () => "";
const panelEmpty = (t) => `<p class="empty">${t}</p>`;
const tzTime = () => "Sun, Nov 1, 1:00 PM";
const pbpBack = () => ({ view: "live", label: "← Back to Live" });
const pbpTvHTML = () => "<div class=\"pbp-tv\"></div>";
const pbpSpoilHTML = () => "";
const lockGameHTML = () => "";
const pbpWinChartHTML = () => "<div class=\"winchart\"></div>";
const pbpModelWinProbHTML = () => "";
const pbpPressureHTML = () => "";
const pbpCrewHTML = () => "";
const pbpInjuriesHTML = () => "<p class=\"rail-quiet\">No designations listed for either club on the injury board.</p>";
const pbpTotalsHTML = () => "";
const pbpCallItHTML = () => "<div class=\"callit\"></div>";
const pbpParkHeadHTML = () => "";
const pbpParkHTML = () => "<div class=\"park\"></div>";
const pbpSituationHTML = () => "";
const pbpPropsHTML = () => "<div class=\"picks\"></div>";
const gameId = (g) => `${g.away}@${g.home}`;
const _standingsCache = {};
const loadStandings = () => Promise.resolve({});
const state = { view: "pbp" };
let _pbpTab = "stats";
const renderPbpPage = () => {};
"""


def _node(body):
    if not shutil.which("node"):
        return None
    js = f"{STUBS}\n{COLOUR_MATH}\n{GP}\nconsole.log(JSON.stringify((() => {{ {body} }})()));"
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def _plays(rows):
    """[(period, away, home, event)] -> football rows."""
    return [{"kind": "football", "period": p, "away_score": a, "home_score": h, "event": e, "clock": "5:00"}
            for p, a, h, e in rows]


# --- the file ---------------------------------------------------------------------
def test_every_sports_file_carries_its_period_line_and_its_building():
    import livescore_build as B
    payload = {"drives": {"previous": [], "current": None},
               "header": {"competitions": [{"competitors": [
                   {"homeAway": "home", "team": {"id": "8", "abbreviation": "DET"},
                    "linescores": [{"displayValue": "3"}, {"displayValue": "3"}, {"displayValue": "6"}]},
                   {"homeAway": "away", "team": {"id": "16", "abbreviation": "MIN"},
                    "linescores": [{"displayValue": "0"}, {"displayValue": "7"}, {"displayValue": "0"}]}]}]},
               "gameInfo": {"venue": {"fullName": "Ford Field", "address": {"city": "Detroit", "state": "MI"}}}}
    doc = B.pbp_doc("nfl", {"event_id": "401873030", "home": "DET", "away": "MIN", "live": {"state": "live"}}, payload)
    assert doc["linescores"] == {"DET": [3, 3, 6], "MIN": [0, 7, 0]}
    assert doc["venue"] == {"name": "Ford Field", "city": "Detroit", "state": "MI"}
    assert "situation" not in doc, "the scorer's table is basketball's"


# --- the wash ---------------------------------------------------------------------
def test_each_club_washes_in_its_own_colour_deep_enough_for_white_type():
    got = _node("""
      const L = (h) => pbpOklab(pbpHexRgb(h))[0];
      const a = gpWashColours("nfl", { away: "MIN", home: "DET" });
      const black = gpWashColours("nfl", { away: "CIN", home: "DET" });
      const gold = gpWashColours("nfl", { away: "PIT", home: "DET" });
      const close = gpWashColours("nfl", { away: "NYG", home: "BUF" });
      const none = gpWashColours("nfl", { away: "ZZZ", home: "DET" });
      return { a, black, gold, close, none, ls: [a.away, a.home, black.away, gold.away].map(L), GP_DEEP_L };
    """)
    if got is None:
        print("      (skipped: no node)")
        return
    assert got["a"] == {"away": "#4f2683", "home": "#0076b6"}, "already deep: the clubs' own colours"
    assert got["black"]["away"] != "#000000" and got["black"]["away"].startswith("#"), "black gives way to the orange"
    assert all(v <= got["GP_DEEP_L"] + 0.005 for v in got["ls"]), "white type reads on every wash colour"
    assert got["gold"]["away"] != "#ffb612", "a gold is deepened, not printed under white"
    assert got["close"]["away"] != "#0b2265", "two navies: the away side takes its red"
    assert got["none"]["away"] == "#3d3a36", "no colours: grey, never the site's gold"


def test_the_wash_is_the_views_and_leaves_with_it():
    page = _fn(DETAIL, "renderPbpPage")
    assert "if (d) gpWashOn(league, d); else gpWashOff();" in page
    assert page.count("gpWashOff();") >= 3, "no game, a veiled game and no file each draw without it"
    on = _fn(GP, "gpWashOn")
    assert 'view.insertAdjacentHTML("afterbegin", `<div class="gp-wash" aria-hidden="true"></div>`)' in on
    assert 'document.body.style.setProperty("--wa", away);' in on and 'view.classList.add("gp-on");' in on
    assert 'if (name !== "pbp" && typeof gpWashOff === "function") gpWashOff();' in APP, "leaving the view takes it off"
    assert "#view-pbp.gp-on > .gp-wash {" in GP_CSS and "position: fixed; inset: 0; z-index: -1;" in GP_CSS


def test_the_page_is_dark_on_the_wash_in_either_theme_and_its_glass_never_blurs():
    import re as _re
    styles = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    i = styles.index(':root[data-theme="light"] {\n')
    light = styles[i:styles.index("\n}\n", i)]
    scoped = GP_CSS[GP_CSS.index("#view-pbp.gp-on, body.gp-on .topbar, body.gp-on .sportbar {"):]
    scoped = scoped[:scoped.index("\n}\n")]
    for tok in set(_re.findall(r"^\s+(--[a-z0-9-]+):", light, _re.M)):
        assert f"  {tok}: " in scoped, f"{tok}: the light theme's value would reach the page on the wash"
    assert "backdrop-filter" not in _re.sub(r"/\*.*?\*/", "", GP_CSS, flags=_re.S), "no blur: it crashed his phone"
    assert "#view-pbp.gp-on .card { background-color: var(--gp-glass); background-image: none; box-shadow: none; }" in GP_CSS
    assert "#view-pbp.gp-on > .gp-wash, body.gp-on .topbar, #view-pbp.gp-on .gp-compact," in GP_CSS, \
        "the bar over the page wears its top: the wash's own picture (tests/test_the_top_of_the_game_page_is_one_picture.py)"


# --- the line score ---------------------------------------------------------------
def test_the_line_score_is_read_off_the_plays_when_the_file_has_none():
    plays = _plays([(1, 0, 0, "Kickoff"), (1, 0, 3, "Field Goal Good"), (2, 7, 6, "Passing Touchdown"),
                    (3, 7, 12, "Rushing Touchdown"), (4, 7, 12, "Pass Reception")])
    got = _node(f"""
      const plays = {json.dumps(plays)};
      const live = {{ state: "live", period: "Q4", away_score: 7, home_score: 15 }};
      const L = gpLinesFromPlays({{ plays }}, live);
      const gap = gpLinesFromPlays({{ plays: plays.filter((p) => p.period !== 2) }}, live);
      const own = gpLines({{ away: "MIN", home: "DET", plays, linescores: {{ MIN: [0, 7], DET: [3, 3] }} }}, "nfl", live);
      const html = gpLineHTML({{ away: "MIN", home: "DET", plays }}, "nfl", live);
      return {{ L, gap, own, html }};
    """)
    if got is None:
        return
    assert got["L"] == {"away": [0, 7, 0, 0], "home": [3, 3, 6, 3]}, "the fourth catches up with the scoreboard's 15"
    assert got["gap"] is None, "a period with no play on file: no line rather than a wrong one"
    assert got["own"] == {"away": [0, 7], "home": [3, 3]}, "the summary's own line comes first"
    html = got["html"]
    assert [m for m in re.findall(r'<th scope="col"[^>]*>([^<]*)</th>', html)][-5:] == ["1", "2", "3", "4", "T"]
    assert '<td class="now">0</td>' in html and '<td class="t">15</td>' in html


def test_overtime_gets_its_column_and_a_final_dims_the_side_that_lost():
    got = _node("""
      const d = { away: "MIN", home: "DET", linescores: { MIN: [0, 7, 14, 0, 3], DET: [14, 7, 0, 0, 0] } };
      return gpLineHTML(d, "nfl", { state: "final", period: "Final/OT", away_score: 24, home_score: 21 });
    """)
    if got is None:
        return
    assert ">OT</th>" in got and '<td class="t">24</td>' in got
    assert '<tr class="lost">' in got and got.index('<tr class="lost">') > got.index("MIN</span>"), "the home side lost"
    assert '<tr class="">' in got
    board = _fn(DETAIL, "pbpBoardHTML")
    assert 'const lost = lv.state === "final" && score != null && other != null && Number(score) < Number(other);' in board


# --- the field --------------------------------------------------------------------
def test_the_field_reads_as_the_pages_other_fields_and_draws_the_two_lines():
    got = _node("""
      const d = { away: "MIN", home: "DET", drive: { team: "MIN", plays: 10, yards: 49, elapsed: "4:52", start_yard_line: 74 } };
      const lv = { state: "live", yard_line: 25, possession: "MIN", detail: "4th & 5 at DET 25" };
      const m = gpFieldModel(d, "nfl", lv);
      const goal = gpFieldModel(d, "nfl", { ...lv, yard_line: 4, detail: "1st & Goal at DET 4" });
      const homeBall = gpFieldModel({ ...d, drive: null }, "nfl", { ...lv, possession: "DET", yard_line: 30, detail: "2nd & 7 at DET 30" });
      const none = [gpFieldModel(d, "nfl", { ...lv, hold: "Halftime" }), gpFieldModel(d, "nfl", { ...lv, state: "final" }),
                    gpFieldModel(d, "nfl", { ...lv, yard_line: null }), gpFieldModel(d, "nba", lv)];
      return { m, goal, homeBall, none, html: gpFieldHTML(d, "nfl", lv),
               x: [gpFieldX(100), gpFieldX(0), gpFieldX(50)], ez: GP_FD_EZ, w: GP_FD_W,
               homeFirst: gpFieldHTML(d, "nfl", lv).indexOf('gp-fd-ez home') < gpFieldHTML(d, "nfl", lv).indexOf('gp-fd-ez away') };
    """)
    if got is None:
        return
    m = got["m"]
    assert (m["los"], m["dir"], m["gain"], m["start"], m["words"]) == (25, -1, 20, 74, "4th & 5 · DET 25")
    assert got["goal"]["gain"] == 0 and got["goal"]["goal"], "& Goal: the line to gain is the goal line"
    assert got["homeBall"]["dir"] == 1 and got["homeBall"]["gain"] == 37 and got["homeBall"]["start"] is None
    assert got["none"] == [None, None, None, None]
    ez, w = got["ez"], got["w"]
    assert abs(got["x"][1] - ez) < 1e-6 and abs(got["x"][0] - (w - ez)) < 1e-6 and abs(got["x"][2] - w / 2) < 1e-6, \
        "home's goal line on the left, away's on the right, as the drive card and the picture draw it"
    html = got["html"]
    assert '<div class="gp-fd-words">4th &amp; 5 · DET 25</div>' in html
    for part in ('class="gp-fd-ez away"', 'class="gp-fd-ez home"', 'class="gp-fd-los"', 'class="gp-fd-gain"',
                 'class="gp-fd-drive"', 'class="gp-fd-ball"', ">MIN</text>", ">DET</text>"):
        assert part in html, part
    assert "Vikings drive · 10 plays, 49 yards, 4:52" in html
    assert got["homeFirst"], "home's end zone drawn first, at the left"
    assert "--off:var(--wa)" in html, "the drive in the offence's colour"


# --- the tabs and the panels ------------------------------------------------------
def test_four_tabs_and_a_live_game_opens_on_the_plays():
    assert 'const GP_FB_TABS = [["stats", "Stats"], ["plays", "Play-By-Play"], ["standings", "Standings"], ["props", "Our picks"]];' in GP
    page = _fn(DETAIL, "renderPbpPage")
    assert ': tabs === GP_FB_TABS && lv.state === "live" ? "plays" : tabs[0][0];' in page
    assert "host.innerHTML = fb ? gpFootballHTML({" in page and "if (fb) gpWire(host);" in page
    fb = _fn(GP, "gpFootballHTML")
    order = ["${gpCompactHTML(", "${pbpBoardHTML(d, league, lv, {", "${field}", "${gpLineHTML(d, league, lv)}",
             '<div class="gch-entry-slot"></div>', "${pbpMineSlotsHTML()}", "${pbpTabsHTML(tab, null, tabs)}", "${back}"]
    at = [fb.index(x) for x in order]
    assert at == sorted(at), "the score, the field, the line, the room's card, your action, the tabs"


def test_the_odds_card_reads_the_live_quote_the_pregame_line_and_the_open():
    got = _node("""
      const d = { away: "MIN", home: "DET" };
      const g = { away: "MIN", home: "DET", spread: 3, favorite: "DET", total: 45.5, home_ml: -162, away_ml: 163,
                  line_open: { spread_home: -3, total: 45.5, home_ml: -162, away_ml: 163 } };
      LIVE = { books: 14, spread: -3.5, total: 32.5, home_ml: -233, away_ml: 228 };
      const live = gpOddsHTML({ ...d, live: { state: "live" } }, "nfl", g);
      LIVE = null;
      const pre = gpOddsHTML({ ...d, live: { state: "pre" } }, "nfl", g);
      const fin = gpOddsHTML({ ...d, live: { state: "final" } }, "nfl", g);
      return { live, pre, fin, none: gpOddsHTML(d, "nfl", null) };
    """)
    if got is None:
        return
    live = got["live"]
    assert "Live · 14 books" in live and "+3.5" in live and "−3.5" in live and "O 32.5" in live and "U 32.5" in live
    assert "+228" in live and "−233" in live and "Opened DET −3.0 · total 45.5" in live
    assert "Pregame" in got["pre"] and "−3.0" in got["pre"], "the favourite lays the points"
    assert "Opening line" in got["fin"] and "Opened" not in got["fin"].split("</table>")[1]
    assert got["none"] == ""


def test_team_stats_compare_a_rate_as_a_rate_and_a_clock_as_seconds():
    got = _node("""
      const r = (name, v) => ({ name, label: name, value: v });
      const d = { away: "MIN", home: "DET", team_stats: {
        MIN: [r("totalYards", "177"), r("thirdDownEff", "3-9"), r("possessionTime", "18:20"), r("totalPenaltiesYards", "5-40"), r("yardsPerPlay", "4.5")],
        DET: [r("totalYards", "273"), r("thirdDownEff", "4-11"), r("possessionTime", "26:52"), r("totalPenaltiesYards", "6-72"), r("yardsPerPlay", "5.1")] } };
      return { nums: [gpStatNum("thirdDownEff", "3-9"), gpStatNum("possessionTime", "18:20"), gpStatNum("totalPenaltiesYards", "5-40"),
                      gpStatNum("totalYards", "177"), gpStatNum("completionAttempts", "12/22"), gpStatNum("totalYards", "—")],
               html: gpTeamStatsHTML(d, "nfl") };
    """)
    if got is None:
        return
    assert got["nums"][:4] == [1 / 3, 1100, 5, 177] and abs(got["nums"][4] - 12 / 22) < 1e-9 and got["nums"][5] is None
    html = got["html"]
    assert html.count('class="gp-ts-bars"') == 5
    yards = html[html.index(">totalYards<"):]
    assert 'class="h lead"><i style="width:100%">' in yards[:400] and 'style="width:65%"' in yards[:400]
    assert "More team stats" in html, "the rest folds under More"


def test_each_side_gets_a_box_score_card_in_the_order_a_box_is_read():
    got = _node("""
      const g = (name, labels, rows) => ({ name, labels, rows });
      const d = { away: "MIN", home: "DET", box: [{ team: "MIN", groups: [
        g("defensive", ["TOT", "SOLO", "SACKS"], Array.from({ length: 11 }, (_, i) => ({ name: `Def Ender${i}`, stats: [String(11 - i), "1", "0"] }))),
        g("passing", ["C/ATT", "YDS"], [{ name: "Kyler Murray", stats: ["12/22", "136"] }]),
        g("rushing", ["CAR", "YDS"], [{ name: "Aaron Jones Sr.", stats: ["4", "19"] }, { name: "Nobody", stats: ["--", "--"] }]) ] }] };
      return { away: gpBoxHTML(d, "nfl", {}, "away"), home: gpBoxHTML(d, "nfl", {}, "home") };
    """)
    if got is None:
        return
    html = got["away"]
    assert html.index(">Passing<") < html.index(">Rushing<") < html.index(">Defense<")
    assert "K. Murray" in html and "A. Jones Sr." in html and 'title="Kyler Murray"' in html
    assert ">TCKL<" in html and ">SACK<" in html, "the defence's columns in words a box score uses"
    assert "Nobody" not in html, "a row with nothing logged is not drawn"
    assert "<summary>All 11</summary>" in html, "a long group shows eight and folds the rest"
    assert got["home"] == ""


def test_play_by_play_is_drive_by_drive_newest_first_and_the_drive_on_now_is_open():
    got = _node("""
      const p = (period, event, a, h, extra) => ({ kind: "football", period, event, away_score: a, home_score: h, ...(extra || {}) });
      const d = { away: "MIN", home: "DET", live: { state: "live" }, drives: [
        { id: "1", team: "MIN", period: 1, result: "Touchdown", scoring: true, offensive_plays: 7, yards: 74, elapsed: "2:53",
          plays: [p(1, "Rush", 0, 0), p(1, "Passing Touchdown", 6, 0, { scoring: true }), p(1, "Extra Point Good", 7, 0)] },
        { id: "2", team: "DET", period: 2, result: "Interception", offensive_plays: 4, yards: 37, elapsed: "1:23", plays: [p(2, "Pass Interception", 7, 0, { turnover: true })] },
        { id: "3", team: "MIN", period: 4, offensive_plays: 10, yards: 49, elapsed: "4:52", plays: [p(4, "Pass Reception", 7, 12)] } ] };
      const first = gpDrivesHTML(d, "nfl");
      _gpOpen.set("dr-3", false); _gpOpen.set("dr-1", true);
      return { first, kept: gpDrivesHTML(d, "nfl") };
    """)
    if got is None:
        return
    html = got["first"]
    assert html.index("4th quarter") < html.index("2nd quarter") < html.index("1st quarter"), "newest first"
    assert 'data-gp-key="dr-3" open>' in html and "Drive in progress" in html
    assert 'class="card gp-dr score" data-gp-key="dr-1">' in html and "Passing Touchdown words" in html, \
        "a scoring drive names the play that scored, in our words"
    assert 'class="card gp-dr bad"' in html, "a turnover reads as one"
    kept = got["kept"]
    assert 'data-gp-key="dr-3">' in kept and 'data-gp-key="dr-1" open>' in kept, "the reader's own open and close"
    wire = _fn(GP, "gpWire")
    assert 'host.addEventListener("toggle", (e) => {' in wire and "_gpOpen.set(k, e.target.open);" in wire


def test_standings_are_the_two_divisions_with_the_two_clubs_lit():
    got = _node("""
      const t = (team, w, l, ties, rank, pf, pa, streak) => ({ team, wins: w, losses: l, ties, rank, points_for: pf, points_against: pa, streak });
      _standingsCache.nfl = { season: 2026, groups: [
        { label: "NFC North", teams: [t("MIN", 6, 0, 0, 1, 125, 74, 6), t("DET", 4, 2, 0, 3, 184, 165, 2), t("GB", 5, 3, 0, 2, 171, 164, -1)] },
        { label: "AFC East", teams: [t("BUF", 5, 1, 0, 1, 197, 171, 2)] } ] };
      _standingsCache.nhl = { groups: [{ label: "Metro", teams: [t("NYG", 9, 3, 2, 1, 48, 42, 5)] }] };
      return { nfl: gpStandingsHTML({ away: "MIN", home: "DET" }, "nfl"),
               nhl: gpStandingsHTML({ away: "NYG", home: "ZZZ" }, "nhl"),
               loading: gpStandingsHTML({ away: "A", home: "B" }, "cfb") };
    """)
    if got is None:
        return
    html = got["nfl"]
    assert "NFC North" in html and "AFC East" not in html, "only the divisions in the game"
    assert html.index(">Vikings<") < html.index(">Packers<") < html.index(">Lions<"), "by rank"
    assert html.count('<tr class="on">') == 2 and ">T<" not in html, "no ties, no T column"
    assert "1.000" in html and ".667" in html and "W6" in html and "L1" in html
    assert ">OTL<" in got["nhl"] and ">PTS<" in got["nhl"] and "<td>20</td>" in got["nhl"], "hockey counts points"
    assert "Loading the standings" in got["loading"]


def test_the_compact_bar_is_inert_until_shown_and_stays_shown_on_a_redraw():
    got = _node("""
      const d = { away: "MIN", home: "DET", live: { state: "live", period: "Q4", clock: "14:48", away_score: 7, home_score: 12 } };
      const hidden = gpCompactHTML(d, "nfl", d.live, GP_FB_TABS, "stats");
      _gpStuck = true;
      const shown = gpCompactHTML(d, "nfl", d.live, GP_FB_TABS, "stats");
      return { hidden, shown, words: [gpClockWord("nfl", d.live), gpClockWord("nfl", { state: "final", period: "Final/OT" }),
               gpClockWord("nfl", { state: "live", hold: "Halftime — 2nd quarter" })] };
    """)
    if got is None:
        return
    assert '<div class="gp-compact" inert>' in got["hidden"] and '<div class="gp-compact on">' in got["shown"]
    assert got["hidden"].count("data-gp-jump") == 4, "the four tabs, each opening at its top"
    assert got["words"] == ["Q4 14:48", "Final/OT", "Halftime"]
    assert ".gp-stick { position: sticky; top: var(--topbar-h); height: 0; z-index: 45; }" in GP_CSS
    assert "if (_gpFor !== `${league}:${event}`) { _gpFor = `${league}:${event}`; _gpStuck = false; _gpTabsStuck = false; _gpOpen.clear(); }" in GP
    assert ".gp-compact.tabs-on .gp-c-tabs { display: flex; }" in GP_CSS, "its tabs join it once the page's own have gone under"
    assert 'bar.classList.toggle("tabs-on", _gpTabsStuck);' in _fn(GP, "gpWire")
    assert "if (open && !open.contains(e.target)) open.open = false;" in _fn(GP, "gpWire"), "the ⋯ menu closes on a tap elsewhere"


def test_basketball_and_hockey_draw_the_line_under_their_score_too():
    for f, league in (("hoopscast.js", "league"), ("rinkcast.js", '"nhl"')):
        src = (ROOT / "web" / "js" / f).read_text(encoding="utf-8")
        assert f'${{typeof gpLineHTML === "function" ? gpLineHTML(d, {league}, d.live || {{}}) : ""}}' in src, f
    assert "#view-pbp.gp-on .hc-score, #view-pbp.gp-on .rc-score { background: none;" in GP_CSS


def test_a_yes_or_no_prop_reads_as_words():
    fn = _fn(APP, "trackerBetText")
    got = None
    if shutil.which("node"):
        js = (f"const escapeHtml = (s) => String(s); const teamName = (a) => a;\n{fn}\n"
              "console.log(JSON.stringify([trackerBetText({ player: 'Jahmyr Gibbs', side: 'yes', line: null, market_label: 'Anytime TD' }),"
              "trackerBetText({ player: 'Jahmyr Gibbs', side: 'no', line: null, market_label: 'Anytime TD' }),"
              "trackerBetText({ player: 'Jahmyr Gibbs', side: 'UNDER', line: 75.5, market_label: 'Rushing Yards' })]));")
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        got = json.loads(r.stdout)
    if got is None:
        return
    assert got == ["Jahmyr Gibbs Anytime TD", "Jahmyr Gibbs not Anytime TD", "Jahmyr Gibbs UNDER 75.5 Rushing Yards"]


# --- in a browser (opt-in) --------------------------------------------------------
def _doc():
    plays = []
    for k, (a, h) in enumerate([(0, 3), (7, 6), (7, 12), (7, 12)], start=1):
        plays += [{"kind": "football", "id": f"{k}a", "period": k, "clock": "15:00", "team": "MIN", "event": "Rush",
                   "down": 1, "distance": 10, "yard_line": 60, "yards": 4, "away_score": a if k > 1 else 0,
                   "home_score": h if k > 1 else 0, "spot": 60.0},
                  {"kind": "football", "id": f"{k}b", "period": k, "clock": "0:00", "team": "DET", "event": "End Period",
                   "yard_line": 40, "yards": 0, "away_score": a, "home_score": h, "spot": 40.0}]
    drives = [{"id": f"d{k}", "team": "MIN" if k % 2 else "DET", "offensive_plays": 2, "yards": 4, "elapsed": "1:00",
               "start_yard_line": 64, "period": k, "scoring": False, "result": "Punt" if k < 4 else "",
               "plays": plays[2 * (k - 1):2 * k]} for k in range(1, 5)]
    row = lambda name, v: {"name": name, "label": name, "value": v}  # noqa: E731
    return {"league": "nfl", "event_id": "401873030", "generated_at": "2026-11-01T20:25:00Z",
            "home": "DET", "away": "MIN", "home_name": "Detroit Lions", "away_name": "Minnesota Vikings",
            "live": {"state": "live", "home_score": 12, "away_score": 7, "period": "Q4", "clock": "14:48",
                     "detail": "4th & 5 at DET 25", "start_time": "2026-11-01T18:00Z", "yard_line": 25.0, "possession": "MIN"},
            "drive": {"team": "MIN", "plays": 10, "yards": 49, "elapsed": "4:52", "start_yard_line": 74, "period": 3},
            "drives": drives, "plays": plays, "records": {"DET": "4-2", "MIN": "6-0"}, "tv": ["Fox"],
            "team_stats": {"MIN": [row("totalYards", "177"), row("thirdDownEff", "3-9")],
                           "DET": [row("totalYards", "273"), row("thirdDownEff", "4-11")]},
            "box": [{"team": t, "groups": [{"name": "passing", "labels": ["C/ATT", "YDS"],
                                             "rows": [{"name": n, "stats": ["12/22", "136"]}]}]}
                    for t, n in (("MIN", "Kyler Murray"), ("DET", "Jared Goff"))]}


GEOM = """() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
    return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
  const wash = document.querySelector('#view-pbp > .gp-wash');
  const tabs = [...document.querySelectorAll('.gp .pbp-tabs .pbp-tab')].map((b) => [b.scrollWidth, b.clientWidth]);
  return { view: document.getElementById('view-pbp').classList.contains('gp-on'), body: document.body.classList.contains('gp-on'),
           wash: r('#view-pbp > .gp-wash'), washPos: wash ? getComputedStyle(wash).position : '',
           washBg: wash ? getComputedStyle(wash).backgroundImage : '', page: document.scrollingElement.scrollWidth,
           field: r('.gp-field svg.gp-fd'), line: document.querySelectorAll('.gp-line .gp-ls tbody tr').length,
           tabs, text: getComputedStyle(document.querySelector('.gp .pbp-sb-nick')).color,
           hero: r('.gp .pbp-hero'), compact: r('.gp-compact'),
           compactOn: document.querySelector('.gp-compact').classList.contains('on'),
           tabsOn: document.querySelector('.gp-compact').classList.contains('tabs-on'),
           tabRow: r('.gp .pbp-tabs'), sy: Math.round(scrollY), h: document.documentElement.scrollHeight };
}"""


def _until(page, ok, seconds=10, between=None):
    """The page's geometry once `ok` holds, or its last reading after
    `seconds` (the assertions then say what was not there). `between`,
    when given, is shown each reading that falls short before the next
    look: a reader's next move."""
    import time
    end = time.time() + seconds
    while True:
        g = page.evaluate(GEOM)
        if ok(g) or time.time() > end:
            return g
        if between:
            between(g)
        page.wait_for_timeout(150)


SCREEN_H = 667


def test_the_page_in_a_browser_at_a_phones_width():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    doc = _doc()
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for theme in ("dark", "light"):
                    # A short phone's screen (an iPhone SE's 667 points): the
                    # page's own tabs start below it however the page above
                    # them has filled in, which the compact bar's check needs.
                    ctx = browser.new_context(viewport={"width": 390, "height": SCREEN_H}, is_mobile=True, has_touch=True,
                                              service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    body = json.dumps(doc)
                    page.route("**/data/pbp/nfl_401873030.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.route("**/data/live_nfl.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
                        {"games": [{"event_id": "401873030", "home": "DET", "away": "MIN", "live": doc["live"]}]})))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/401873030", wait_until="load")
                    if theme == "light":
                        page.evaluate("document.documentElement.dataset.theme = 'light'")
                    page.wait_for_selector(".gp .pbp-hero", timeout=20000)
                    # Polled, not slept: under a loaded machine (the gate runs
                    # eight files at once) a fixed wait is a coin toss.
                    # The tab row's place too: gate #23 (5 November) read it at
                    # 645px, above the screen's foot, while the cards over it
                    # were still coming in; alone, and on the gate before, it
                    # sits below it.
                    g = _until(page, lambda g: g["field"] and g["line"] == 2 and g["view"] and g["body"]
                               and g["tabRow"] and g["tabRow"]["t"] > SCREEN_H)
                    g = page.evaluate(GEOM)
                    at = f"{theme}:"
                    assert g["view"] and g["body"], f"{at} the wash is on"
                    assert g["washPos"] == "fixed" and g["wash"]["w"] >= 389 and g["wash"]["h"] >= SCREEN_H - 1, f"{at} it fills the screen: {g['wash']}"
                    assert "linear-gradient" in g["washBg"], g["washBg"]
                    assert g["page"] <= 390, f"{at} the page scrolls sideways ({g['page']}px)"
                    assert g["field"] and g["field"]["w"] > 300, f"{at} the field is drawn across the page: {g['field']}"
                    assert g["line"] == 2, f"{at} the line score's two rows"
                    assert all(sw <= cw + 1 for sw, cw in g["tabs"]) and len(g["tabs"]) == 4, f"{at} the four tabs fit: {g['tabs']}"
                    rgb = [int(x) for x in re.findall(r"\d+", g["text"])[:3]]
                    assert min(rgb) >= 200, f"{at} white type on the wash, not the theme's ink: {g['text']}"
                    assert not g["compactOn"], f"{at} the bar waits for the score to leave"
                    # The page's own tabs start below the screen, so the jump
                    # below goes from under the screen to over it without
                    # crossing it: the case the gate caught on 1 November,
                    # when the bar's tabs never came (an observer of the
                    # screen alone sees nothing change).
                    assert g["tabRow"]["t"] > SCREEN_H, f"{at} the tabs start below the screen: {g['tabRow']}"
                    # Down past the page's own tabs, and again if anything above
                    # them (the chat's card, filled when chat.js lands) pushed
                    # them back into view: as a reader would keep scrolling.
                    under = "window.scrollTo({ top: document.querySelector('.gp .pbp-tabs').getBoundingClientRect().bottom + scrollY + 40, behavior: 'instant' })"
                    page.evaluate(under)

                    def still_showing(g):
                        if g["tabRow"] and g["tabRow"]["b"] > 0:
                            page.evaluate(under)

                    g2 = _until(page, lambda g: g["compactOn"] and g["tabsOn"] and abs(g["compact"]["t"]) < 2,
                                between=still_showing)
                    assert g2["compactOn"] and abs(g2["compact"]["t"]) < 2, f"{at} the compact bar is down at the top: {g2['compact']}"
                    assert g2["tabsOn"], (f"{at} its tabs are in it once the page's own are under it: "
                                          f"row {g2['tabRow']}, scrolled {g2['sy']} of {g2['h']}")
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
