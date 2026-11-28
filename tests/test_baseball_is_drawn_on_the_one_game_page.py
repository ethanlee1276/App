"""Baseball's live game page is the one game page (step AAK, 21 November).

Ethan, 21 November: "go work on the nba and CFB and all other sports live
page to try to match nfl ... that should be automatic when we do any visual
changes". Basketball and hockey moved that morning (step AAI); baseball kept
four rooms of its own (Game info, Our picks, Injuries, Player stats) under a
ballpark card. It is drawn by gpPageHTML now, and brings only its own parts
(detail.js gpBaseballKit): the ballpark as its stage, the newest at-bat on
the shared card, the at-bats by inning in sentences, team stats and the
batting and pitching boxes from the box score, the line score by inning.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    j = src.index("\n}\n", i)
    return src[i:j + 3]


def test_one_layout_and_baseball_brings_its_parts():
    page = DETAIL[DETAIL.index("async function renderPbpPage("):DETAIL.index("THE GAME PAGE IN THE CLUBS' COLOURS")]
    assert "const tabs = GP_TABS;" in page and "PBP_TABS" not in DETAIL and "pbpTabsFor" not in DETAIL
    assert "host.innerHTML = gpPageHTML({ d, league, lv, tab, tabs, GC, boardGame, faces, stripHTML, back, event, kit });" in page
    assert DETAIL.count('<div class="pbp-layout') == 1, "one layout in the whole file"
    kit = _fn(DETAIL, "gpKit")
    assert 'if (league === "mlb") {\n    try { return gpBaseballKit(o); }' in kit
    parts = _fn(DETAIL, "gpBaseballKit")
    for part in ("stage", "now", "rows: rows.length ? rows : null", "say:", "teamStats", "boxes", 'ballIcon: "baseball"', "down:"):
        assert part in parts, part
    # Built only from the page's own boxes (no layout of its own): the stage card, the box cards, the stat rows.
    for builder in ('gpStageHTML("pbp-parkcard", ""', "gpBoxCardHTML(league, d[ha], [", "gpTsRowHTML(label", "gpTsCardHTML(d, league,",
                    "GC.playNow(d, league, faces,"):
        assert builder in parts, builder
    # The line score reads the at-bats, the period cards are innings, an extra inning is its number.
    assert 'if (league === "mlb") return gpBaseballLines(d, lv);' in DETAIL
    assert 'if (league === "mlb") return `${pbpOrd(k)} inning`;' in DETAIL
    assert '${league === "mlb" ? "R" : "T"}' in DETAIL
    # The shared rows say an at-bat in the page's sentence when it hands one in.
    rows = APP[APP.index("function playsHTML("):]
    assert "const said = typeof g.say === \"function\" ? g.say(p) : null;" in rows[rows.index("const row = (p) => {"):]


def _node(js):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no node)")
        return None
    pieces = []
    # The at-bat's words are app.js's (the Live tab's baseball cards say them too); the lines are the page's.
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    for name in ("const GP_BB_VERB", "const GP_BB_OUT", "const GP_BB_OFF"):
        i = app.index(name)
        pieces.append(app[i:app.index(";\n", i) + 2])
    pieces.append(_fn(app, "gpAtBatWords"))
    for name in ("gpBaseballLine", "gpBaseballLines"):
        pieces.append(_fn(DETAIL, name))
    prog = ("const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/'/g, '&#39;');\n"
            + "\n".join(pieces) + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_an_at_bat_is_said_as_a_sentence():
    got = _node("""return [
      gpAtBatWords({ batter: "Eli Stroud", pitcher: "Reid Calloway", event: "Home Run", event_type: "home_run", rbi: 3, distance: 448 }),
      gpAtBatWords({ batter: "Teo Varga", pitcher: "Felix Durand", event: "Single", event_type: "single", rbi: 0, distance: 267 }),
      gpAtBatWords({ batter: "Kip Farrow", pitcher: "Owen Tarrant", event: "Strikeout", event_type: "strikeout" }),
      gpAtBatWords({ batter: "Gus Malloy", pitcher: "Owen Tarrant", event: "Walk", event_type: "walk", rbi: 1 }),
      gpAtBatWords({ batter: "Aaron Vale", pitcher: "Jace Morrow", event: "Groundout", event_type: "field_out", distance: 74 }),
      gpAtBatWords({ batter: "Nico Brandao", pitcher: "Jace Morrow", event: "Catcher Interference", event_type: "weird_new_kind" })];""")
    if got is None:
        return
    texts = [x["text"] for x in got]
    assert texts == ["Eli Stroud homers off Reid Calloway, 448 ft, 3 runs in.",
                     "Teo Varga singles off Felix Durand, 267 ft.",
                     "Kip Farrow strikes out off Owen Tarrant.",
                     "Gus Malloy walks off Owen Tarrant, a run in.",
                     "Aaron Vale grounds out, 74 ft.",
                     "Nico Brandao: Catcher Interference"], texts
    assert got[0]["html"] == "<b>Eli Stroud</b> homers off <b>Reid Calloway</b>, 448 ft, 3 runs in."


def test_the_line_score_is_inning_by_inning_and_a_half_not_batted_is_empty():
    got = _node("""const p = (inning, half, a, h) => ({ inning, half, event: "x", away_score: a, home_score: h });
      const d = { plays: [p(1, "T", 0, 0), p(1, "B", 0, 2), p(2, "T", 1, 2), p(2, "B", 1, 2),
                          p(3, "T", 1, 2), p(3, "B", 1, 3), p(9, "T", 1, 3)] };
      // (Innings four to eight left out: a gap is read as no runs, from the score before it.)
      return [gpBaseballLines(d, { state: "final" }), gpBaseballLines({ plays: [] }, {}),
              gpBaseballLine({ line: { batting: { ab: 4, h: 2, rbi: 3, bb: 0, k: 1, hr: 1 } } }),
              gpBaseballLine({ line: { pitching: { ip: "5.2", k: 7, er: 2, bb: 1, p: 91 } } }), gpBaseballLine({})];""")
    if got is None:
        return
    lines, empty, bat, pit, none = got
    assert lines["away"][:3] == [0, 1, 0] and lines["home"][:3] == [2, 0, 1], lines
    assert lines["away"][8] == 0 and lines["home"][8] is None, "the home side did not bat in the ninth: an empty cell"
    assert empty is None
    assert bat == "2-4, 1 HR, 3 RBI" and pit == "5.2 IP, 7 K, 2 ER" and none == ""


# --- in a browser (opt-in) -------------------------------------------------------------
def _doc(state):
    import live_build as lvb
    from engine.mlb.sources.pbp import recent_plays

    def ab(i, inning, half, batter, pitcher, event, et, a, h, rbi=0):
        return {"about": {"atBatIndex": i, "inning": inning, "halfInning": half, "isScoringPlay": rbi > 0},
                "matchup": {"batter": {"fullName": batter}, "pitcher": {"fullName": pitcher}},
                "result": {"event": event, "eventType": et, "rbi": rbi, "awayScore": a, "homeScore": h},
                "count": {"outs": 1}, "playEvents": [{"isPitch": True, "pitchNumber": 1, "details": {"call": {"code": "X"}},
                                                     "pitchData": {"startSpeed": 94.0}, "count": {"balls": 0, "strikes": 0}}]}
    plays = [ab(0, 1, "top", "Dale Rourke", "Owen Tarrant", "Groundout", "field_out", 0, 0),
             ab(1, 1, "bottom", "Aaron Vale", "Reid Calloway", "Home Run", "home_run", 0, 1, 1),
             ab(2, 2, "top", "Teo Varga", "Owen Tarrant", "Double", "double", 0, 1)]
    lv = ({"state": "live", "away_score": 0, "home_score": 1, "period": "Top 2nd", "outs": 1, "bases": [2], "balls": 1, "strikes": 2}
          if state == "live" else {"state": "final", "away_score": 0, "home_score": 1, "period": "Final"})
    g = {"game_pk": 776655, "home": "NYY", "away": "BOS", "live": lv, "players": []}
    pay = {"allPlays": plays}
    return lvb.mlb_doc(g, pay, recent_plays(pay, 0), chances={})


def test_in_a_browser_baseball_is_the_one_page_live_and_final():
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
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium) and os.path.isfile(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for state in ("live", "final"):
                    doc = _doc(state)
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    body = lambda x: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(x)))  # noqa: E731
                    page.route("**/data/pbp/mlb_776655.json*", body(doc))
                    page.route("**/data/live_mlb.json*", body({"games": [{"game_pk": 776655, "home": "NYY", "away": "BOS",
                                                                          "live": doc["live"]}]}))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/mlb/776655", wait_until="load")
                    # The shared cards (js/gamecast.js) load after the page's first draw, and the page draws
                    # again when they land: a live game waits for its last-play card too.
                    ready = ("!!document.querySelector('.gp .pbp-hero') && !!document.querySelector('.gp-line')"
                             + (" && !!document.querySelector('.gc-dv')" if state == "live" else " && !!window.QBGamecast"))
                    for _ in range(300):
                        if page.evaluate(ready):
                            break
                        page.wait_for_timeout(100)
                    got = page.evaluate("""() => { const q = (s) => document.querySelector(s);
                      return { layouts: document.querySelectorAll('.pbp-layout').length, gp: !!q('.pbp-layout.gp'),
                               tabs: [...document.querySelectorAll('.gp .pbp-tabs .pbp-tab')].map((b) => b.textContent.trim()),
                               stage: !!q('.gp-stage.pbp-parkcard'), now: q('.gc-dv') ? q('.gc-dv').textContent : '',
                               r: [...document.querySelectorAll('.gp-ls thead th')].map((t) => t.textContent.trim()).pop(),
                               wide: document.documentElement.scrollWidth, more: !!q('.gp-more'), compact: !!q('.gp-compact') }; }""")
                    assert got["layouts"] == 1 and got["gp"], (state, got)
                    assert got["tabs"] == ["Stats", "Play-By-Play", "Standings", "Our picks"], (state, got)
                    assert got["r"] == "R" and got["more"] and got["compact"] and got["wide"] <= 390, (state, got)
                    if state == "live":
                        assert got["stage"], "the ballpark is the stage while the game is on"
                        assert "Teo Varga doubles off Owen Tarrant." in got["now"], got["now"]
                        page.click('.gp .pbp-tabs [data-pbp-tab="plays"]')
                        for _ in range(100):
                            if page.evaluate("!!document.querySelector('details.gp-dr[open] .lb-what')"):
                                break
                            page.wait_for_timeout(100)
                        cards = page.evaluate("[...document.querySelectorAll('details.gp-dr .gp-dr-t > b')].map((b) => b.textContent)")
                        assert cards[:2] == ["2nd inning", "1st inning"], cards
                        said = page.evaluate("document.querySelector('details.gp-dr[open] .lb-what').textContent")
                        assert "Teo Varga doubles off Owen Tarrant" in said, said
                    else:
                        assert not got["stage"] and not got["now"], "a final is its record: no picture, no last play"
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
