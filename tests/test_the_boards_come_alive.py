"""The stadium photographs come alive: the football board, the big moments,
the wind over the park, the countdown to the start.

2026-10-25, Ethan, after the ballpark's scoreboard and its runners: "ok now
keep going with any more ideas like that or any other ideas in general to
keep adding life to the app and cool shit."

What holds it (detail.js):

  - THE FOOTBALL FIELD'S CENTRE-HUNG BOARD (pbpFieldBoardSVG) puts the away
    team on its left screen and the home team on its right, each with its
    colour, its score and a football under the side with the ball (not at
    the half); the line under the crown is the game: "Q3 4:12 · 3RD & 8",
    OT, HALFTIME, END OF 3RD, FINAL/OT, the kickoff. The screens are drawn
    over the four photographs' own, measured.
  - A TEAM'S COLOUR IS ONE THAT SHOWS on the board's black: 3:1 off it (the
    contrast a mark needs), else its brightest past 2:1, else grey.
  - BIG MOMENTS (pbpMoment): a play that lands while the page is open goes
    up on the board, TOUCHDOWN, FIELD GOAL, SAFETY, INTERCEPTION, FUMBLE,
    HOME RUN, GRAND SLAM, and a touchdown or a home run sets off fireworks.
    A first drawing, a page come back to, an old play: nothing. Once up it
    stays up through a redraw for its few seconds, the fireworks carried on
    from where they were.
  - THE WIND (pbpWindSVG) runs over the ballpark's outfield, out or in, as
    the feed holds it: not a crosswind (its side is not held), not under
    5 mph, not under a roof, never on football (a compass bearing).
  - THE LAST HOUR COUNTS DOWN on both boards, a second at a time, and the
    page asks for the game on its own from ten minutes out.

Run directly: `python3 tests/test_the_boards_come_alive.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import html
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
DETAIL = open(os.path.join(ROOT, "web", "js", "detail.js"), encoding="utf-8").read()
DETAIL_CSS = open(os.path.join(ROOT, "web", "css", "detail.css"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
MLB_TEAMS = open(os.path.join(ROOT, "web", "js", "teams_mlb.js"), encoding="utf-8").read()
NFL_TEAMS = open(os.path.join(ROOT, "web", "js", "teams.js"), encoding="utf-8").read()
NOW = 1_800_000_000_000            # the clock the board code reads, held still


def _board_src():
    i = DETAIL.index("const PBP_BOARD = ")
    return DETAIL[i:DETAIL.index("async function renderPbpPage()", i)]


def _node(body):
    """The boards' own code in node, the page's helpers stubbed and the clock
    held at NOW (move it with `clock(ms)`)."""
    js = (MLB_TEAMS + "\nglobalThis.MLB_TEAMS = MLB_TEAMS;\n" + NFL_TEAMS + "\nglobalThis.TEAMS = TEAMS;\n"
          + "globalThis.teamsForSport = (l) => l === 'mlb' ? MLB_TEAMS : l === 'nfl' ? TEAMS : {};\n"
          + "globalThis.escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => `&#${c.charCodeAt(0)};`);\n"
          + "globalThis.liveHoldWord = (lv) => (lv || {}).hold ? String(lv.hold) : '';\n"
          + "globalThis.tzTime = () => '4:25 PM';\n"
          + f"let __t = {NOW}; Date.now = () => __t; globalThis.clock = (ms) => {{ __t += ms; }};\n"
          + _board_src().replace("\nconst ", "\nvar ").replace("\nlet ", "\nvar ")
          + f"\nconst __out = (() => {{ {body} }})();\nprocess.stdout.write(JSON.stringify(__out));")
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        print("      (skipped: no node)")
        return None
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def _texts(svg):
    return [html.unescape(re.sub(r"<[^>]+>", "", t).strip())
            for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)]


def _fb(live, plays=None, away="TB", home="DAL", league="nfl"):
    d = {"away": away, "home": home, "live": live, "plays": plays or [{"kind": "football", "id": "p1", "event": "Rush"}]}
    return f"pbpBoardSVG({json.dumps(d)}, {json.dumps(league)})"


def _mlb(live, events=None, weather=None, away="TBR", home="MIL"):
    d = {"away": away, "home": home, "live": live, "events": events or []}
    g = {"weather": weather} if weather else None
    return f"pbpBoardSVG({json.dumps(d)}, 'mlb', {json.dumps(g)})"


LIVE = {"state": "live", "away_score": 10, "home_score": 17, "period": "Q3", "clock": "4:12",
        "detail": "3rd & 8 at TB 24", "possession": "DAL"}
RUSH = {"kind": "football", "id": "p1", "event": "Rush"}


# --- the football board ---------------------------------------------------------------
def test_the_football_board_rides_the_park_on_its_own_measured_screens():
    park = APP[APP.index("function pbpParkHTML("):]
    park = park[:park.index("\n}\n")]
    assert ('const board = (league === "mlb" || isFootball) && typeof pbpBoardSVG === "function" '
            '? pbpBoardSVG(d, league, boardGame) : "";') in park
    assert 'if (league === "nfl" || league === "cfb") return pbpFieldBoardSVG(d, league);' in DETAIL
    m = re.search(r"const PBP_FIELD_BOARD = \{\s*away: (\[.*?\]),.*?home: (\[.*?\]),.*?line: (\[.*?\]),", DETAIL, re.S)
    away, home, line = (json.loads(g) for g in m.groups())
    # Drawn a touch larger than the frames measured on all four photographs
    # (left 85.5-99.0 x 13.0-26.7, right 140.3-153.8 x 13.0-26.7), so no
    # frame's edge shows past them; the line covers the wordmark (106.5-132.5).
    assert away[0] < 85.5 and away[2] > 99.0 and away[1] < 13.0 and away[3] > 26.7, away
    assert home[0] < 140.3 and home[2] > 153.8 and home[1] < 13.0 and home[3] > 26.7, home
    assert line[0] < 106.5 and line[2] > 132.5 and line[1] < 21.3 and line[3] > 25.3, line
    assert line[3] < 27.6, "the board's lit ring under it stays the photograph's"


def test_live_the_screens_carry_the_teams_the_scores_and_the_ball_and_the_line_the_game():
    svg = _node("return " + _fb(LIVE) + ";")
    if svg is None:
        return
    words = _texts(svg)
    assert words[:4] == ["TB", "10", "DAL", "17"], words
    assert "Q3 4:12 · 3RD & 8" in words, words
    assert svg.count('class="pbp-sb-ball"') == 1 and svg.index(">DAL<") < svg.index("pbp-sb-ball"), \
        "the ball under the home side, which has it"
    assert 'aria-hidden="true"' in svg, "the score above the photograph says it in words"


def test_overtime_the_half_a_quarters_end_the_final_and_the_kickoff_each_say_so():
    got = _node("return [" + ", ".join([
        _fb(dict(LIVE, period="Q5", clock="9:51", detail="2nd & 10 at DAL 35")),
        _fb(dict(LIVE, period="Q6", clock="2:00", detail="")),
        _fb(dict(LIVE, period="Q2", clock="0:00", hold="Halftime")),
        _fb(dict(LIVE, hold="End of 3rd Quarter")),
        _fb(dict(LIVE, hold="Delayed — Weather")),
        _fb({"state": "final", "away_score": 30, "home_score": 27, "period": "Final/OT"}),
        _fb({"state": "scheduled", "start_time": "2099-10-25T20:25:00Z"}),
    ]) + "];")
    if got is None:
        return
    ot, two_ot, half, end3, delay, final, pre = got
    assert "OT 9:51 · 2ND & 10" in _texts(ot)
    assert "2OT 2:00" in _texts(two_ot)
    assert "HALFTIME" in _texts(half) and "pbp-sb-ball" not in half, "no one has the ball at the half"
    assert "END OF 3RD" in _texts(end3), _texts(end3)
    assert "DELAYED" in _texts(delay) and "pbp-sb-ball" not in delay
    assert "FINAL/OT" in _texts(final) and "30" in _texts(final)
    assert "KICKOFF 4:25 PM" in _texts(pre) and not any(w.isdigit() for w in _texts(pre)), "no score before it"


def test_a_score_that_just_changed_flashes_on_its_own_side():
    got = _node("const a = " + _fb(LIVE) + "; const b = " + _fb(dict(LIVE, home_score=20))
                + "; const c = " + _fb(dict(LIVE, home_score=20)) + "; return [a, b, c];")
    if got is None:
        return
    first, scored, again = got
    assert "pbp-sb-new" not in first
    assert scored.count("pbp-sb-new") == 1 and re.search(r'pbp-sb-new"[^>]*>20<', scored)
    assert "pbp-sb-new" not in again


def test_a_teams_colour_is_one_that_shows_on_the_black():
    got = _node("return [pbpBoardColor('TB', 'nfl'), pbpBoardColor('DAL', 'nfl'), pbpBoardColor('HOU', 'nfl'),"
                " pbpBoardColor('NYJ', 'nfl'), pbpBoardColor('CIN'), pbpBoardColor('MIL'), pbpBoardColor('XXX', 'nfl')];")
    if got is None:
        return
    tb, dal, hou, nyj, cin, mil, unknown = (c.lower() for c in got)
    assert tb == "#d50a0a", "the Bucs' red stands 3.7:1 off the black: it shows as it is"
    assert dal == "#b0b7bc", "the Cowboys' navy would vanish: their silver"
    assert hou == "#a71930", "no colour of the Texans' reaches 3:1; their red is the brightest past 2:1"
    assert nyj == unknown == "#8c95a8", "the table's two Jets greens are both too dark: the board's grey"
    assert cin == "#c6011f" and mil == "#ffc52f", "the Reds' red, the Brewers' gold"


# --- big moments ----------------------------------------------------------------------
def _moment(svg):
    """The words of the big moment on a board, or [] (it is the board's last
    piece: the football line's text, the ballpark column's group)."""
    i = svg.find("pbp-sb-moment")
    if i < 0:
        return []
    part = svg[svg.rfind("<", 0, i):svg.index("</svg>", i)]
    return " ".join(re.findall(r"<text[^>]*>(.*?)</text>", part, flags=re.S)).split()


def test_a_touchdown_goes_up_on_the_board_and_sets_off_the_fireworks():
    td = {"kind": "football", "id": "p2", "event": "Passing Touchdown", "scoring": True}
    pat = {"kind": "football", "id": "p3", "event": "Extra Point Good", "scoring": True}
    fg = {"kind": "football", "id": "p4", "event": "Field Goal Good", "scoring": True}
    pick = {"kind": "football", "id": "p5", "event": "Pass Interception Return", "turnover": True}
    got = _node(f"""
      const first = {_fb(LIVE, [RUSH])};
      clock(12000); const td = {_fb(dict(LIVE, home_score=24), [RUSH, td, pat])};
      clock(12000); const after = {_fb(dict(LIVE, home_score=24), [RUSH, td, pat])};
      clock(12000); const fg = {_fb(dict(LIVE, home_score=27), [RUSH, td, pat, fg])};
      clock(12000); const pick = {_fb(dict(LIVE, home_score=27), [RUSH, td, pat, fg, pick])};
      return [first, td, after, fg, pick];""")
    if got is None:
        return
    first, td_svg, after, fg_svg, pick_svg = got
    assert not _moment(first) and "pbp-boom" not in first, "a first drawing celebrates nothing"
    assert _moment(td_svg) == ["TOUCHDOWN"], "its extra point, in the same pass, does not hide it"
    assert td_svg.count('class="pbp-boom-b"') == 5, "five bursts"
    assert 'stroke="#b0b7bc"' in td_svg, "one in the scoring side's colour (the Cowboys' silver)"
    assert not _moment(after) and "pbp-boom" not in after, "the next pass draws the game again"
    assert _moment(fg_svg) == ["FIELD", "GOAL"] and "pbp-boom" not in fg_svg, "a field goal, no fireworks"
    assert _moment(pick_svg) == ["INTERCEPTION"] and "pbp-boom" not in pick_svg


def test_a_play_missed_while_away_is_not_celebrated():
    td = {"kind": "football", "id": "p2", "event": "Rushing Touchdown", "scoring": True}
    got = _node(f"""
      const first = {_fb(LIVE, [RUSH])};
      clock(5 * 60000); const back = {_fb(dict(LIVE, home_score=24), [RUSH, td])};
      return back;""")
    if got is None:
        return
    assert not _moment(got) and "pbp-boom" not in got, "five minutes on, that touchdown is old news"


def test_once_up_it_stays_up_through_a_redraw_and_the_fireworks_run_on():
    td = {"kind": "football", "id": "p2", "event": "Passing Touchdown", "scoring": True}
    got = _node(f"""
      {_fb(LIVE, [RUSH])};
      clock(12000); const td = {_fb(dict(LIVE, home_score=23), [RUSH, td])};
      clock(1500); const redraw = {_fb(dict(LIVE, home_score=23), [RUSH, td])};
      clock(6000); const late = {_fb(dict(LIVE, home_score=23), [RUSH, td])};
      clock(4000); const gone = {_fb(dict(LIVE, home_score=23), [RUSH, td])};
      return [td, redraw, late, gone];""")
    if got is None:
        return
    td_svg, redraw, late, gone = got
    assert 'style="--t:0ms"' in td_svg
    assert _moment(redraw) == ["TOUCHDOWN"] and 'class="pbp-boom" ' in redraw.replace("\n", " ") + " "
    assert 'style="--t:1500ms"' in redraw, "the fireworks carry on from a second and a half in"
    assert _moment(late) == ["TOUCHDOWN"] and "pbp-boom" not in late, "past five seconds the sky is done"
    assert not _moment(gone), "eleven seconds on, the board is the game again"


def test_a_home_run_and_a_grand_slam_on_the_ballpark_board():
    single = {"kind": "atbat", "at_bat": 40, "half": "B", "event": "Single", "event_type": "single", "rbi": 0}
    hr = {"kind": "atbat", "at_bat": 41, "half": "T", "event": "Home Run", "event_type": "home_run", "rbi": 2}
    slam = {"kind": "atbat", "at_bat": 42, "half": "B", "event": "Home Run", "event_type": "home_run", "rbi": 4}
    out = {"kind": "atbat", "at_bat": 43, "half": "B", "event": "Strikeout", "event_type": "strikeout", "rbi": 0}
    live = {"state": "live", "away_score": 3, "home_score": 2, "period": "Top 7th", "outs": 1}
    got = _node(f"""
      {_mlb(live, [single])};
      clock(12000); const hr = {_mlb(dict(live, away_score=5), [single, hr])};
      clock(12000); const slam = {_mlb(dict(live, home_score=6), [single, hr, slam])};
      clock(12000); const k = {_mlb(dict(live, home_score=6), [single, hr, slam, out])};
      return [hr, slam, k];""")
    if got is None:
        return
    hr_svg, slam_svg, k_svg = got
    assert _moment(hr_svg) == ["HOME", "RUN"] and hr_svg.count('class="pbp-boom-b"') == 5
    assert 'stroke="#8fbce6"' in hr_svg, "the top half's homer: the Rays' light blue in the sky"
    assert _moment(slam_svg) == ["GRAND", "SLAM"]
    assert 'stroke="#ffc52f"' in slam_svg, "the bottom half's: the Brewers' gold"
    assert not _moment(k_svg) and "pbp-boom" not in k_svg, "a strikeout is the count again"


def test_a_leadoff_home_run_is_news_too():
    hr = {"kind": "atbat", "at_bat": 0, "half": "T", "event": "Home Run", "event_type": "home_run", "rbi": 1}
    live = {"state": "live", "away_score": 0, "home_score": 0, "period": "Top 1st"}
    got = _node(f"""
      {_mlb(live, [])};
      clock(12000); return {_mlb(dict(live, away_score=1), [hr])};""")
    if got is None:
        return
    assert _moment(got) == ["HOME", "RUN"], "no at-bat before it, and it is still the game's first news"


def test_the_fireworks_and_the_blink_are_the_pages_and_reduced_motion_has_none():
    assert "@keyframes pbp-boom" in CSS and "@keyframes pbp-boom" not in DETAIL_CSS, "steps in the main sheet"
    assert ".pbp-sb-moment { animation: pbp-sb-flash 1.4s linear 3; animation-delay: calc(0s - var(--t, 0s)); }" in DETAIL_CSS
    assert "animation-delay: calc(var(--d, 0s) - var(--t, 0s));" in DETAIL_CSS, "a redraw runs them on"
    assert "@media (prefers-reduced-motion: reduce) { .pbp-boom { display: none; } }" in DETAIL_CSS
    spots = re.search(r"const PBP_BOOM_SPOTS = \{\s*mlb: (\[\[.*?\]\]),\s*football: (\[\[.*?\]\]),", DETAIL, re.S)
    mlb, football = (json.loads(s) for s in spots.groups())
    # Clear of the boards: the ballpark's screen (x 18.5-53.6, y 17.5-41)
    # and the field's centre-hung board (x 85-154, y 5-28).
    for x, y, r in mlb:
        assert x - r > 53.6 or y - r > 41 or x + r < 18.5, (x, y, r)
    for x, y, r in football:
        assert x + r < 85 or x - r > 154 or y - r > 28, (x, y, r)


# --- the wind -------------------------------------------------------------------------
def test_the_wind_runs_out_or_in_over_the_outfield_as_hard_as_it_blows():
    live = {"state": "live", "away_score": 0, "home_score": 0, "period": "Top 1st"}
    cases = [{"wind_mph": 16, "wind_dir": "out"}, {"wind_mph": 16, "wind_dir": "in"}, {"wind_mph": 7, "wind_dir": "Out"},
             {"wind_mph": 12, "wind_dir": "out"}, {"wind_mph": 4, "wind_dir": "out"}, {"wind_mph": 20, "wind_dir": "cross"},
             {"wind_mph": 20, "wind_dir": "out", "dome": True}]
    got = _node("return [" + ", ".join(_mlb(live, weather=w) for w in cases) + "];")
    if got is None:
        return
    gusts = lambda svg: re.findall(r'<svg class="pbp-wind pbp-wind-(\w+)".*?</svg>', svg, flags=re.S)
    paths = lambda svg: re.findall(r'<path d="([^"]+)"/>', svg.split('class="pbp-wind')[1]) if "pbp-wind" in svg else []
    out16, in16, light, mid, calm, cross, dome = got
    assert gusts(out16) == ["strong"] and len(paths(out16)) == 5
    assert paths(out16)[0] == "M119 94Q119.5 74 120 52", "centre field first, from the infield toward the wall"
    assert paths(in16)[0] == "M120 52Q119.5 74 119 94", "blowing in: the same streak, the other way"
    assert gusts(light) == ["light"] and len(paths(light)) == 3, "a light wind, three streaks"
    assert gusts(mid) == ["brisk"]
    for svg in (calm, cross, dome):
        assert "pbp-wind" not in svg, "under 5 mph, a crosswind's unheld side, a closed roof: none"
    fb = _node("return " + _fb(LIVE) + ";")
    assert "pbp-wind" not in fb, "football's wind is a compass bearing; the photograph has no north"
    assert "@keyframes windflow { from { stroke-dashoffset: 48; } to { stroke-dashoffset: 0; } }" in CSS
    assert "stroke-dasharray: 12 36;" in DETAIL_CSS, "one dash a period of the keyframes' 48"


# --- the countdown --------------------------------------------------------------------
def test_the_last_hour_counts_down_on_both_boards():
    soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW / 1000 + 23 * 60 + 41))
    later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW / 1000 + 3 * 3600))
    got = _node(f"""return [pbpCountdown(754000), pbpCountdown(3600000), pbpCountdown(999), pbpCountdown(-5),
      {_mlb({"state": "scheduled", "start_time": soon})}, {_mlb({"state": "scheduled", "start_time": later})},
      {_fb({"state": "scheduled", "start_time": soon})}, {_fb({"state": "scheduled", "start_time": later})},
      pbpStartsSoon({{state: "scheduled", start_time: "{soon}"}}), pbpStartsSoon({{state: "scheduled",
        start_time: new Date(Date.now() + 9 * 60000).toISOString()}}),
      pbpStartsSoon({{state: "scheduled", start_time: new Date(Date.now() - 61 * 60000).toISOString()}}),
      pbpStartsSoon({{state: "live", start_time: new Date(Date.now()).toISOString()}})];""")
    if got is None:
        return
    assert got[:4] == ["12:34", "1:00:00", "0:01", "0:00"], got[:4]
    mlb_soon, mlb_later, fb_soon, fb_later = got[4:8]
    assert ["FIRST", "PITCH IN", "23:41"] == [w for w in _texts(mlb_soon) if w in ("FIRST", "PITCH IN", "23:41")]
    start = int(NOW + (23 * 60 + 41) * 1000)
    assert f'data-pbp-count="{start}" data-pbp-done="NOW"' in mlb_soon
    assert "PITCH" in _texts(mlb_later) and "4:25" in _texts(mlb_later) and "data-pbp-count" not in mlb_later
    assert "KICKOFF IN 23:41" in _texts(fb_soon)
    assert f'data-pbp-count="{start}" data-pbp-pre="KICKOFF IN " data-pbp-done="KICKOFF"' in fb_soon
    assert "KICKOFF 4:25 PM" in _texts(fb_later) and "data-pbp-count" not in fb_later
    assert got[8:] == [False, True, False, False], "asked about from ten minutes out to an hour past, not live"


def test_the_page_ticks_the_count_and_asks_again_before_the_start():
    page = DETAIL[DETAIL.index("async function renderPbpPage()"):]
    page = page[:page.index("\n}\n")]
    # The strip's chips start the timer whichever way the page then draws
    # itself (no file yet, the basketball page, the whole page); the boards'
    # numbers, drawn with the whole page, start it at its end.
    assert '\n  if (stripHTML.includes("data-pbp-count")) pbpCountStart();\n' in page
    assert page.count('if (host.querySelector("[data-pbp-count]")) pbpCountStart();') == 1
    assert page.endswith('\n  if (lv.state === "live" || pbpStartsSoon(lv)) again();')
    strip = DETAIL[DETAIL.index("function pbpStripHTML("):]
    strip = strip[:strip.index("\n}\n")]
    assert ': left > 0 && left <= PBP_COUNT_MS ? `<span class="pbp-chip-time" data-pbp-count="${start}" data-pbp-pre="in "' in strip, \
        "a chip in the strip counts down its last hour"
    tick = DETAIL[DETAIL.index("function pbpCountStart() {"):]
    tick = tick[:tick.index("\n}\n")]
    assert 'if (!els.length || state.view !== "pbp") { clearInterval(_pbpCountTimer); _pbpCountTimer = null; return; }' in tick, \
        "one timer, gone with the page"
    assert "if (rang) renderPbpPage();" in tick, "at zero the page asks for the game"


# --- in a browser ---------------------------------------------------------------------
def test_in_a_browser_the_field_board_lights_and_a_touchdown_goes_up():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    import test_the_live_trackers as T
    fb = T._fb_doc()
    fb["event_id"] = "e9"
    fb["live"].update({"home_score": 17, "away_score": 10, "clock": "4:12"})
    box = {"doc": fb}
    # The next game on the slate starts in 23 minutes: its chip counts down.
    soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 23 * 60))
    strip = lambda: {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": box["doc"]["live"], "plays_state": "ok"},
        {"event_id": "e10", "home": "KC", "away": "BUF", "live": {"state": "scheduled", "start_time": soon}}]}
    body = lambda x: json.dumps(x() if callable(x) else x)
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    box["doc"] = fb
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_e9.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=body(box["doc"])))
                    page.route("**/data/live_nfl.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=body(strip)))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/e9", wait_until="load")
                    page.wait_for_selector(".pbp-park .pbp-board", timeout=15000)
                    page.wait_for_timeout(800)
                    chip = "document.querySelector('.pbp-chip-time[data-pbp-count]').textContent"
                    tick = [page.evaluate(chip)]
                    page.wait_for_timeout(1300)
                    tick.append(page.evaluate(chip))
                    g = page.evaluate("""() => {
                      const photo = document.querySelector('.pbp-park .pbp-photo').getBoundingClientRect();
                      const rects = [...document.querySelectorAll('.pbp-board > rect')].map((r) => {
                        const b = r.getBoundingClientRect(); return [b.x - photo.x, b.y - photo.y, b.width, b.height]; });
                      return { photo: [photo.width, photo.height], rects,
                               words: [...document.querySelectorAll('.pbp-board text')].map((t) => t.textContent.trim()),
                               wide: document.scrollingElement.scrollWidth - innerWidth };
                    }""")
                    # The touchdown: a new play, six more points, the page's next pass.
                    d = json.loads(json.dumps(fb))
                    last = [p for p in d["plays"] if p.get("kind") == "football"][-1]
                    d["plays"].append(dict(last, id="td-1", event="Passing Touchdown", scoring=True))
                    d["live"]["home_score"] += 6
                    box["doc"] = d
                    page.evaluate("renderPbpPage()")
                    page.wait_for_selector(".pbp-park .pbp-sb-moment", state="attached", timeout=5000)
                    g["moment"] = page.evaluate("document.querySelector('.pbp-park .pbp-sb-moment').textContent.trim()")
                    g["bursts"] = page.evaluate("document.querySelectorAll('.pbp-park .pbp-boom .pbp-boom-b').length")
                    g["anim"] = page.evaluate("getComputedStyle(document.querySelector('.pbp-boom-b')).animationName")
                    g["errors"] = errors
                    g["tick"] = tick
                    got[width] = g
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    m = re.search(r"const PBP_FIELD_BOARD = \{\s*away: (\[.*?\]),.*?home: (\[.*?\]),", DETAIL, re.S)
    away, home = (json.loads(s) for s in m.groups())
    for width, g in got.items():
        pw_, ph = g["photo"]
        # The board's own rectangles: each screen, its stripe; the line's cover.
        for (x0, y0, x1, y1), r in zip((away, home), (g["rects"][0], g["rects"][2])):
            want = [x0 / 240 * pw_, y0 / 150 * ph, (x1 - x0) / 240 * pw_, (y1 - y0) / 150 * ph]
            assert all(abs(a - b) <= 1.5 for a, b in zip(r, want)), (width, r, want)
        assert g["words"][:4] == ["TB", "10", "DAL", "17"], (width, g["words"])
        assert g["moment"] == "TOUCHDOWN" and g["bursts"] == 5 and g["anim"] == "pbp-boom", (width, g)
        a, b = g["tick"]
        assert re.fullmatch(r"in 2[23]:\d\d", a) and re.fullmatch(r"in 2[23]:\d\d", b) and a != b, ("it ticks", g["tick"])
        assert g["wide"] <= 0 and not g["errors"], (width, g)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
