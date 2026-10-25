"""The arenas come alive: the basketball and hockey boards lit with the game,
their big moments, the final horn everywhere, and a banner for a phone.

2026-10-25, Ethan, after the ballpark's scoreboard and the football field's
board: "yeah do the nba and nhl next and cfb and Just make sure all
additions and features and changes we have added and done has been done to
all sports."

What holds it (detail.js; js/hoopscast.js and js/rinkcast.js hand their game
over):

  - THE ARENAS ARE LIT WHERE THEIR PAGES SHOW THEM, measured off the
    photographs in the renders' 1672 x 941. Basketball: the board's ring
    band (the one part of the board a wide screen's window holds) and the
    scorer's table carry "LAL 10 · Q2 5:10 · BOS 8"; the shot clocks, painted
    5:24 and 18, carry the game clock over the quarter (the shot clock is in
    no feed, so it is not drawn). Hockey: the ring band carries the score,
    its halo the period, the clock and the power play or an empty net (all
    below the last-play card's reach), the centre panel of the far boards
    the score again (the one piece every phone window holds); a goal says
    GOAL on the main screen and lights the lamp behind the net it went in.
  - THE MOMENTS: BUZZER BEATER, 3-POINTER, DUNK, LEAD CHANGE, TIMEOUT; GOAL,
    POWER PLAY, EMPTY NET; and for every sport the FINAL horn, seen live.
    Fireworks for a buzzer-beater, a goal and the final horn.
  - ON A PHONE a moment gets a banner over the picture (the boards there are
    a few pixels high): the ballpark's sky, under the field's board, an
    arena's corner. A wide screen reads the boards.
  - COLLEGE'S TABLE names its second colour `alt`, and a board reads it.

Run directly: `python3 tests/test_the_arenas_come_alive.py`
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
JS = lambda f: open(os.path.join(ROOT, "web", "js", f), encoding="utf-8").read()
DETAIL, HOOPS, RINK = JS("detail.js"), JS("hoopscast.js"), JS("rinkcast.js")
DETAIL_CSS = open(os.path.join(ROOT, "web", "css", "detail.css"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
NOW = 1_800_000_000_000


def _board_src():
    i = DETAIL.index("const PBP_BOARD = ")
    return DETAIL[i:DETAIL.index("async function renderPbpPage()", i)]


def _node(body):
    """The boards' own code in node with every league's team table, the
    page's helpers stubbed, the clock held at NOW (`clock(ms)` moves it)."""
    tables = "".join(JS(f) + "\n" for f in ("teams.js", "teams_mlb.js", "teams_nba.js", "teams_wnba.js", "teams_nhl.js"))
    js = (tables + "globalThis.teamsForSport = (l) => ({ mlb: MLB_TEAMS, nba: NBA_TEAMS, wnba: WNBA_TEAMS, nhl: NHL_TEAMS,"
          " cfb: { MICH: { primary: '#00274c', alt: '#ffcb05' } } })[l] || TEAMS;\n"
          + "globalThis.escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => `&#${c.charCodeAt(0)};`);\n"
          + "globalThis.liveHoldWord = (lv) => (lv || {}).hold ? String(lv.hold) : '';\n"
          + "globalThis.tzTime = () => '7:30 PM';\n"
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
    return [html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
            for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)]


def _arena(league, live, plays=None, rink=None, opt=None, away=None, home=None):
    hockey = league == "nhl"
    d = {"away": away or ("NYR" if hockey else "LAL"), "home": home or ("BOS"), "live": live}
    if hockey:
        d["rink"] = rink or {"events": [{"id": 1, "kind": "faceoff", "team": "NYR", "sc": "1551"}]}
    else:
        d["plays"] = plays or [{"kind": "hoops", "id": "1", "event": "Jump Shot"}]
    return f"pbpArenaSVG({json.dumps(d)}, {json.dumps(league)}, {json.dumps(opt or {})})"


HOOPS_LIVE = {"state": "live", "period": "Q2", "clock": "5:10", "away_score": 10, "home_score": 8}
RINK_LIVE = {"state": "live", "period": "P3", "clock": "16:00", "away_score": 0, "home_score": 1}


# --- where the boards are --------------------------------------------------------------
def _arena_table():
    hoops = re.search(r"hoops: \{\s*ring: (\[.*?\]),\s*table: (\[.*?\]),", DETAIL, re.S)
    hockey = re.search(r"hockey: \{\s*ring: (\[.*?\]),\s*halo: (\[.*?\]),.*?boards: (\[.*?\]),", DETAIL, re.S)
    return [json.loads(g) for g in hoops.groups()], [json.loads(g) for g in hockey.groups()]


def test_each_board_is_where_its_page_shows_the_picture():
    (ring, table), (hring, halo, boards) = _arena_table()
    # Basketball's wide window starts at y 230 (css/hoopscast.css --crop-y);
    # a phone's is 440-880. The ring band is the board's part in the first,
    # the scorer's table in both.
    assert ring[1] >= 230 and ring[3] < 440, ring
    assert table[1] >= 440 and table[3] <= 880, table
    # Measured off the 1280 x 720 file: the band 530-752 x 211-237, the
    # table 505-779 x 425-447 (x 1.30625, y 1.30694 into the render's units).
    for (x0, y0, x1, y1), (mx0, my0, mx1, my1) in ((ring, (530, 211, 752, 237)), (table, (505, 425, 779, 447))):
        assert abs(x0 - mx0 * 1.30625) < 3 and abs(x1 - mx1 * 1.30625) < 3, (x0, x1)
        assert abs(y0 - my0 * 1.30694) < 3 and abs(y1 - my1 * 1.30694) < 3, (y0, y1)
    # Hockey: the last-play card reaches y 256 over the board's left half on
    # a wide screen; the ring and the halo sit below it.
    assert hring[1] > 256 and halo[1] - halo[3] > 256, (hring, halo)
    # Both of a phone's half windows (x 752-1612 and 60-920) hold the far
    # boards' centre panel.
    assert boards[0] >= 752 and boards[2] <= 922, boards
    nets = re.search(r"nets: \{ away: (\[.*?\]), home: (\[.*?\]) \}", DETAIL)
    away, home = (json.loads(g) for g in nets.groups())
    assert away[:2] == [294, 682] and home[:2] == [1391, 682], "rinkcast's own goal lines (its CP map)"
    assert "[[-89, 0], [294.2, 681.7]]" in RINK and "[[89, 0], [1391.0, 681.7]]" in RINK


def test_the_two_arena_pages_hand_their_game_over():
    assert 'const lit = typeof pbpArenaSVG === "function" ? pbpArenaSVG(d, league) : "";' in HOOPS
    assert 'preserveAspectRatio="none" aria-hidden="true">${lit}${svg}</svg></div>\n        ${shout}${where}' in HOOPS
    assert 'pbpArenaSVG(d, "nhl", { pp: k.pp ? k.pp.side : "", ppLeft: k.pp && k.pp.left > 0 ? k.pp.left : null })' in RINK
    assert 'preserveAspectRatio="none" aria-hidden="true">${lit}${marks}</svg></div>\n        ${shout}${where}${pp}' in RINK
    for page in (HOOPS, RINK):
        assert 'typeof pbpMomentBannerHTML === "function" ? pbpMomentBannerHTML(d, ' in page
    assert "function pbpArenaSVG(" not in HOOPS + RINK, "the boards are the live page's own (detail.js)"


# --- basketball -------------------------------------------------------------------------
def test_basketball_lights_the_ring_the_table_and_both_shot_clocks():
    got = _node("return [" + ", ".join([
        _arena("nba", HOOPS_LIVE),
        _arena("nba", dict(HOOPS_LIVE, period="Q5", clock="3:12")),
        _arena("wnba", dict(HOOPS_LIVE, period="Q6", clock="45.2"), away="LVA", home="NYL"),
        _arena("nba", {"state": "final", "period": "Final/OT", "away_score": 110, "home_score": 112}),
        _arena("nba", {"state": "scheduled", "start_time": "2099-01-01T00:30:00Z"}),
    ]) + "];")
    if got is None:
        return
    live, ot, two_ot, final, pre = (_texts(s) for s in got)
    line = "LAL 10 · Q2 5:10 · BOS 8"
    assert live.count(line) == 2, ("the ring and the table", live)
    assert live.count("5:10") == 2 and live.count("Q2") == 2, "both shot clocks: the game clock over the quarter"
    assert got[0].count('fill="#120707"') == 2, "each clock's painted 5:24 and 18 under its own face"
    assert "LAL 10 · OT 3:12 · BOS 8" in ot and ot.count("OT") == 2
    assert "LVA 10 · 2OT 45.2 · NYL 8" in two_ot and "45.2" in two_ot
    assert "LAL 110 · FINAL/OT · BOS 112" in final and final.count("FINAL") == 2 and final.count("0.0") == 2
    assert "LAL · TIP-OFF 7:30 PM · BOS" in pre
    assert not any(w in ("Q2", "0.0") for w in pre), "before the tip the clocks are dark"
    assert "5:24" not in "".join(live) and "18" not in live, "nothing painted is invented back"


def test_a_three_a_dunk_a_buzzer_beater_a_lead_change_and_a_timeout():
    shot = lambda i, pts, clock="4:50", ev="Jump Shot", team="BOS": {
        "kind": "hoops", "id": str(i), "period": 2, "clock": clock, "team": team, "event": ev,
        "scoring": True, "shot": True, "points": pts}
    base = [{"kind": "hoops", "id": "1", "event": "Jump Shot"}]
    steps = [
        (dict(HOOPS_LIVE, home_score=11), base + [shot(2, 3)]),                      # a three, BOS still behind
        (dict(HOOPS_LIVE, home_score=13), base + [shot(2, 3), shot(3, 2, ev="Dunk")]),  # a dunk takes the lead
        (dict(HOOPS_LIVE, home_score=13, away_score=14), base + [shot(2, 3), shot(3, 2, ev="Dunk"),
                                                                 shot(4, 1, ev="Free Throw - 1 of 1", team="LAL")]),
        (dict(HOOPS_LIVE, home_score=13, away_score=14), base + [shot(2, 3), shot(3, 2, ev="Dunk"),
                                                                 shot(4, 1, ev="Free Throw - 1 of 1", team="LAL"),
                                                                 {"kind": "hoops", "id": "5", "event": "Timeout", "team": "BOS"}]),
        (dict(HOOPS_LIVE, home_score=16, away_score=14, clock="0.0"), base + [shot(2, 3), shot(3, 2, ev="Dunk"),
                                                                 shot(4, 1, ev="Free Throw - 1 of 1", team="LAL"),
                                                                 {"kind": "hoops", "id": "5", "event": "Timeout", "team": "BOS"},
                                                                 shot(6, 3, clock="0.0")]),
    ]
    body = [_arena("nba", HOOPS_LIVE, base) + ";"]
    for live, plays in steps:
        body.append(f"clock(12000); out.push({_arena('nba', live, plays)});")
    got = _node("const out = []; " + " ".join(body) + " return out;")
    if got is None:
        return
    shouts = [next((t for t in _texts(s) if "·" in t and not t.startswith("LAL")), "") for s in got]
    assert shouts == ["3-POINTER · BOS", "DUNK · BOS", "LEAD CHANGE · LAL", "TIMEOUT · BOS", "BUZZER BEATER · BOS"], shouts
    booms = [s.count('class="pbp-boom-b"') for s in got]
    assert booms == [0, 0, 0, 0, 5], ("fireworks for the horn alone", booms)
    assert 'stroke="#007a33"' in got[-1], "one burst in the Celtics' green"


# --- hockey -----------------------------------------------------------------------------
def test_hockey_lights_the_ring_the_halo_and_the_far_boards():
    got = _node("return [" + ", ".join([
        _arena("nhl", RINK_LIVE, opt={"pp": "home", "ppLeft": 100}),
        _arena("nhl", dict(RINK_LIVE, period="P4", clock="3:20")),
        _arena("nhl", dict(RINK_LIVE, period="P5", clock="0:00")),
        _arena("nhl", dict(RINK_LIVE, period="P5", clock="12:00"), rink={"game_type": 3, "events": []}),
        _arena("nhl", dict(RINK_LIVE, hold="End of 2nd Period")),
        _arena("nhl", RINK_LIVE, rink={"events": [{"id": 9, "kind": "faceoff", "team": "NYR", "sc": "0651"}]}),
        _arena("nhl", {"state": "scheduled", "start_time": "2099-01-01T00:30:00Z"}),
    ]) + "];")
    if got is None:
        return
    pp, ot, so, two_ot, inter, empty, pre = (_texts(s) for s in got)
    assert pp.count("NYR 0 – 1 BOS") == 2, ("the ring and the far boards", pp)
    assert "3RD 16:00" in pp and "BOS POWER PLAY 1:40" in pp, pp
    assert "OT 3:20" in ot and "SO 0:00" in so, "a regular season's fifth period is the shootout"
    assert "2OT 12:00" in two_ot, "a playoff game's is the second overtime"
    assert "END OF 2ND" in inter
    assert "NYR EMPTY NET" in empty, "the away goalie pulled (situation code 0651)"
    assert "NYR · BOS" in pre and "PUCK DROP 7:30 PM" in pre


def test_a_goal_lights_its_lamp_says_goal_and_sets_off_the_fireworks():
    face = {"id": 1, "kind": "faceoff", "team": "NYR", "sc": "1551"}
    goal = lambda team: {"id": 2, "kind": "goal", "team": team, "sc": "1551"}
    got = _node(f"""
      {_arena("nhl", RINK_LIVE, rink={"events": [face]})};
      clock(12000); const home = {_arena("nhl", dict(RINK_LIVE, home_score=2), rink={"events": [face, goal("BOS")]})};
      return home;""")
    away = _node(f"""
      {_arena("nhl", RINK_LIVE, rink={"events": [face]})};
      clock(12000); return {_arena("nhl", dict(RINK_LIVE, away_score=1), rink={"events": [face, goal("NYR")]})};""")
    if got is None:
        return
    assert "GOAL · BOS" in _texts(got) and "GOAL" in _texts(got), "the ring and the main screen"
    assert got.count('class="pbp-boom-b"') == 5
    lamp = re.search(r'<g class="pbp-lamp"[^>]*><ellipse cx="(\d+)"', got)
    assert lamp and lamp.group(1) == "1391", "the home side shoots at the right net"
    lamp = re.search(r'<g class="pbp-lamp"[^>]*><ellipse cx="(\d+)"', away)
    assert lamp and lamp.group(1) == "294", "the away side at the left"
    assert 'stroke="#fdb927"' in got, "a burst in the Bruins' gold"


def test_a_power_play_and_an_empty_net_go_up_when_they_start():
    ev = lambda i, sc: {"id": i, "kind": "faceoff", "team": "NYR", "sc": sc}
    got = _node(f"""
      {_arena("nhl", RINK_LIVE, rink={"events": [ev(1, "1551")]}, opt={"pp": ""})};
      clock(12000); const pp = {_arena("nhl", RINK_LIVE, rink={"events": [ev(1, "1551"), ev(2, "1451")]}, opt={"pp": "home"})};
      clock(12000); const still = {_arena("nhl", RINK_LIVE, rink={"events": [ev(1, "1551"), ev(2, "1451"), ev(3, "1451")]}, opt={"pp": "home"})};
      clock(12000); const pulled = {_arena("nhl", RINK_LIVE, rink={"events": [ev(1, "1551"), ev(2, "1451"), ev(3, "1451"), ev(4, "0651")]}, opt={"pp": ""})};
      return [pp, still, pulled];""")
    if got is None:
        return
    pp, still, pulled = got
    assert "POWER PLAY · BOS" in _texts(pp)
    assert not any("·" in t and "POWER PLAY" in t for t in _texts(still)), "once, when it starts"
    assert "EMPTY NET · NYR" in _texts(pulled)
    assert "pbp-boom" not in pp + pulled


def test_the_strength_reads_the_situation_code_as_the_parser_does():
    from engine.sources import nhlrink
    codes = ["1551", "1451", "1541", "0651", "1560", "1460", "0641", "1331", ""]
    got = _node(f"""return {json.dumps(codes)}.map((sc) =>
      pbpRinkSit({{ home: "BOS", away: "NYR", rink: {{ events: sc ? [{{ id: 1, sc }}] : [] }} }}));""")
    if got is None:
        return
    want = [nhlrink.situation(c) or {"pp": "", "en": ""} for c in codes]
    assert [(s["pp"], s["en"]) for s in got] == [(w["pp"], w["en"]) for w in want], (got, want)
    assert (got[1]["pp"], got[3]["en"]) == ("home", "away"), "a minor on the away side; the away goalie pulled"


# --- every sport ------------------------------------------------------------------------
def test_the_final_horn_seen_live_is_every_sports_last_moment():
    fb = lambda live: json.dumps({"away": "TB", "home": "DAL", "live": live, "plays": [{"kind": "football", "id": "p1", "event": "Rush"}]})
    mlb = lambda live: json.dumps({"away": "TBR", "home": "MIL", "live": live, "events": []})
    live_fb = {"state": "live", "away_score": 20, "home_score": 27, "period": "Q4", "clock": "0:04"}
    live_mlb = {"state": "live", "away_score": 3, "home_score": 2, "period": "Bottom 9th", "outs": 2}
    got = _node(f"""
      pbpBoardSVG({fb(live_fb)}, "nfl"); clock(12000);
      const f = pbpBoardSVG({fb(dict(live_fb, state="final", period="Final"))}, "nfl");
      pbpBoardSVG({mlb(live_mlb)}, "mlb"); clock(12000);
      const m = pbpBoardSVG({mlb(dict(live_mlb, state="final", period="Final"))}, "mlb");
      {_arena("nba", HOOPS_LIVE)}; clock(12000);
      const h = {_arena("nba", dict(HOOPS_LIVE, state="final", period="Final"))};
      pbpBoardSVG({fb(dict(live_fb, state="final", period="Final"))}, "cfb");
      const cold = pbpBoardSVG({fb(dict(live_fb, state="final", period="Final"))}, "cfb");
      return [f, m, h, cold];""")
    if got is None:
        return
    f, m, h, cold = got
    for svg, winner in ((f, "DAL"), (m, "TBR"), (h, "LAL")):
        assert svg.count('class="pbp-boom-b"') == 5, "the horn's fireworks"
        assert "pbp-sb-moment" in svg and ("FINAL" in _texts(svg) or f"FINAL · {winner}" in _texts(svg)), _texts(svg)
        assert f"<span>{winner}</span>" in svg or winner in "".join(_texts(svg)), "the winner named"
    assert "pbp-boom" not in cold, "a game already over when the page opened celebrates nothing"


def test_a_phone_gets_the_moment_as_a_banner_in_its_pictures_room():
    td = {"kind": "football", "id": "p2", "event": "Passing Touchdown", "scoring": True}
    fb = lambda live, plays: json.dumps({"away": "TB", "home": "DAL", "live": live, "plays": plays})
    live = {"state": "live", "away_score": 10, "home_score": 17, "period": "Q3", "clock": "4:12"}
    got = _node(f"""
      const rush = {{ kind: "football", id: "p1", event: "Rush" }};
      const quiet = pbpBoardSVG({fb(live, [{"kind": "football", "id": "p1", "event": "Rush"}])}, "nfl");
      clock(12000);
      const loud = pbpBoardSVG({fb(dict(live, home_score=23), [{"kind": "football", "id": "p1", "event": "Rush"}, td])}, "nfl");
      {_arena("nhl", RINK_LIVE)}; clock(12000);
      {_arena("nhl", dict(RINK_LIVE, home_score=2), rink={"events": [{"id": 1, "kind": "faceoff", "team": "NYR", "sc": "1551"},
                                                                     {"id": 2, "kind": "goal", "team": "BOS", "sc": "1551"}]})};
      const rink = pbpMomentBannerHTML({{ away: "NYR", home: "BOS" }}, "nhl");
      const other = pbpMomentBannerHTML({{ away: "PHI", home: "NJD" }}, "nhl");
      return [quiet, loud, rink, other];""")
    if got is None:
        return
    quiet, loud, rink, other = got
    assert "pbp-moment-banner" not in quiet
    assert re.search(r'<div class="pbp-moment-banner pbp-mb-below" style="--t:0ms" aria-hidden="true"><b>TOUCHDOWN</b><span>DAL</span></div>', loud)
    assert '<div class="pbp-moment-banner pbp-mb-left"' in rink and "<b>GOAL</b><span>BOS</span>" in rink
    assert other == "", "another game's moment is not this one's"
    assert "@media (max-width: 720px) { .pbp-moment-banner { display: flex; } }" in DETAIL_CSS, \
        "a phone's (the arenas' own crop turns at 720)"
    assert "@media (max-width: 720px) {" in open(os.path.join(ROOT, "web", "css", "hoopscast.css"), encoding="utf-8").read()
    assert "@media (prefers-reduced-motion: reduce) { .pbp-moment-banner { animation: none; } }" in DETAIL_CSS, \
        "reduced motion holds it, lit, until the next pass"
    for k in ("@keyframes pbp-banner", "@keyframes pbp-lamp"):
        assert k in CSS and k not in DETAIL_CSS, "steps in the main sheet"
    for tok in ("var(--night-3)", "var(--night-gold)", "var(--night-text)"):
        assert tok in DETAIL_CSS, "night tokens: it sits on a photograph in either theme"


def test_college_reads_its_alt_colour():
    got = _node("return [pbpBoardColor('MICH', 'cfb')];")
    if got is None:
        return
    assert got == ["#ffcb05"], "Michigan's navy would vanish; its maize (the table's `alt`) shows"


def test_a_room_replaces_only_its_own_entry_points():
    # A room's file loads after app.js, so a function it declares under an
    # app.js name REPLACES that one everywhere: the arenas' first draft had a
    # game-clock reader called pbpClockSecs, app.js's name for a drive's
    # length, and the box score's time of possession read the wrong one.
    # The rooms' render* entry points are the deliberate exception (app.js
    # holds a stub that loads the room, and the room's own takes over).
    names = lambda s: set(re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", s, flags=re.M))
    app = names(JS("app.js"))
    for room in ("detail.js", "record.js", "account.js", "more.js", "fantasy.js", "memes.js"):
        shared = sorted(n for n in names(JS(room)) & app if not n.startswith("render"))
        assert not shared, (room, shared)


# --- in a browser -----------------------------------------------------------------------
def test_in_a_browser_the_arenas_light_and_a_moment_reaches_a_phone():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import copy
    import rendercheck
    import test_the_nba_live_page as TB
    import test_the_nhl_live_page as TH
    cases = []
    nba = TB._deep()
    three = copy.deepcopy(nba)
    three["plays"].append({"kind": "hoops", "id": "999", "period": 2, "clock": "4:50", "team": "BOS", "player": "Jayson Tatum",
                           "event": "Jump Shot", "scoring": True, "shot": True, "points": 3, "points_attempted": 3,
                           "away_score": nba["live"]["away_score"], "home_score": nba["live"]["home_score"] + 3, "x": 3.0, "y": 4.0})
    three["live"].update({"home_score": nba["live"]["home_score"] + 3, "clock": "4:50"})
    cases.append(("nba", "401810010", ".hc-stage", nba, three, "3-POINTER"))
    nhl = TH._deep()
    goal = copy.deepcopy(nhl)
    goal["rink"]["events"].append({"id": 9999, "period": 3, "clock": "15:20", "elapsed": 2680, "kind": "goal", "team": "BOS",
                                   "x": 80.0, "y": 3.0, "player": "David Pastrnak", "score": [0, 2], "sc": "1551"})
    goal["live"].update({"home_score": 2, "clock": "15:20"})
    cases.append(("nhl", "401802123", ".rc-stage", nhl, goal, "GOAL"))
    srv, port = rendercheck._serve()
    got = []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for league, ev, stage, before, after, word in cases:
                    for width in (390, 1280):
                        box = {"doc": before}
                        strip = lambda: {"games": [{"event_id": ev, "home": before["home"], "away": before["away"], "live": box["doc"]["live"]}]}
                        ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                                  has_touch=width < 600, service_workers="block")
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        page.route(f"**/data/pbp/{league}_{ev}.json*",
                                   lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(box["doc"])))
                        page.route(f"**/data/live_{league}.json*",
                                   lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(strip())))
                        page.goto(f"http://127.0.0.1:{port}/index.html#pbp/{league}/{ev}", wait_until="load")
                        page.wait_for_selector(f"{stage} .pbp-arena", state="attached", timeout=15000)
                        page.wait_for_timeout(600)
                        g = {"league": league, "width": width, "lit": page.evaluate(
                            "[...document.querySelectorAll('.pbp-arena text')].map((t) => t.textContent.trim())")}
                        box["doc"] = after
                        page.evaluate("renderPbpPage()")
                        page.wait_for_selector(f"{stage} .pbp-moment-banner", state="attached", timeout=5000)
                        g.update(page.evaluate("""() => { const b = document.querySelector('.pbp-moment-banner'), r = b.getBoundingClientRect();
                          const art = b.parentElement.getBoundingClientRect();
                          return { banner: b.textContent.trim(), shown: getComputedStyle(b).display,
                                   inside: r.left >= art.left && r.right <= art.right && r.top >= art.top,
                                   boom: document.querySelectorAll('.pbp-arena ~ .pbp-boom .pbp-boom-b').length,
                                   lamp: document.querySelectorAll('.pbp-lamp').length,
                                   wide: document.scrollingElement.scrollWidth - innerWidth }; }"""))
                        g["word"], g["errors"] = word, errors
                        got.append(g)
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for g in got:
        lit = " | ".join(g["lit"])
        if g["league"] == "nba":
            assert "LAL 10 · Q2 5:10 · BOS 8" in lit and g["lit"].count("5:10") == 2, (g["width"], lit)
        else:
            assert "NYR 0 – 1 BOS" in lit and "3RD 16:00" in lit, (g["width"], lit)
        assert g["banner"].startswith(g["word"]), g
        assert g["shown"] == ("flex" if g["width"] < 720 else "none"), ("a phone's banner; a wide screen reads the boards", g)
        assert g["inside"] or g["shown"] == "none", ("the banner stays inside its picture", g)
        if g["league"] == "nhl":
            assert g["boom"] == 5 and g["lamp"] == 1, g
        assert g["wide"] <= 0 and not g["errors"], g


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
