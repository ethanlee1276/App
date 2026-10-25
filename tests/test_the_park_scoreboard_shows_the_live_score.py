"""The scoreboard on the MLB park photograph shows the live score.

2026-10-25, Ethan, with the blank board circled on a live game: "for the
mlb live view, we should display the live score where I circled on the
screen. We could make it look good and blend it and make it look like it's
a real mlb score board."

What holds it (detail.js pbpBoardSVG):

  - THE SCREEN IS THE PHOTOGRAPH'S OWN, measured inside the board's white
    frame in the 240x150 box the wall marks and the bags use, and the board
    is drawn in its perspective: every piece rides the screen's projective
    map, so the lettering leans with the board instead of sitting flat on
    it.
  - IT SHOWS WHAT THE LIVE FEED HOLDS: both teams and their runs, the
    inning and its half, the runners on base (Ethan, the same day: "next to
    the score we added on the board, should also show the batters on
    base"), balls, strikes and outs, a lamp at the team batting; FINAL at
    the end, the first pitch before it, the delay in one.
    Hits and errors are not in the live state, so they are not drawn.
  - A RUN THAT HAS JUST SCORED FLASHES ONCE, and only that team's number.
  - NOTHING SPILLS: a two-digit score steps down a size so it keeps clear of
    a three-letter team, and every word on the right is sized to its column.

Run directly: `python3 tests/test_the_park_scoreboard_shows_the_live_score.py`
(the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
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
TEAMS = open(os.path.join(ROOT, "web", "js", "teams_mlb.js"), encoding="utf-8").read()
MEASURED = [[20.3, 24.1], [52.9, 24.7], [52.9, 39.8], [21.0, 40.7]]


def _board_src():
    i = DETAIL.index("const PBP_BOARD = ")
    return DETAIL[i:DETAIL.index("async function renderPbpPage()", i)]


def _node(body):
    """Runs the board's own code in node, with the page's helpers stubbed."""
    js = (TEAMS + "\nglobalThis.MLB_TEAMS = MLB_TEAMS;\n"
          + "globalThis.escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => `&#${c.charCodeAt(0)};`);\n"
          + "globalThis.liveHoldWord = (lv) => (lv || {}).hold ? String(lv.hold) : '';\n"
          + "globalThis.tzTime = () => '7:10 PM';\n"
          + _board_src().replace("\nconst ", "\nvar ").replace("\nlet ", "\nvar ")
          + f"\nconst __out = (() => {{ {body} }})();\nprocess.stdout.write(JSON.stringify(__out));")
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        print("      (skipped: no node)")
        return None
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def _svg(live, away="TB", home="MIL"):
    return f"pbpBoardSVG({{ away: {json.dumps(away)}, home: {json.dumps(home)}, live: {json.dumps(live)} }})"


def _texts(svg):
    return [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S)]


# --- where it is -------------------------------------------------------------------
def test_the_screen_is_the_one_measured_off_the_photograph():
    m = re.search(r"const PBP_BOARD = (\[\[.*?\]\]);", DETAIL)
    assert m and json.loads(m.group(1)) == MEASURED, "the corners changed without re-measuring the photograph"
    got = _node("const m = pbpBoardMap(); return [m(0,0), m(1,0), m(1,1), m(0,1)].map((p) => [p.X, p.Y]);")
    if got is None:
        return
    for (x, y), (ex, ey) in zip(got, MEASURED):
        assert abs(x - ex) < 1e-9 and abs(y - ey) < 1e-9, (got, MEASURED)
    # In perspective, as the photograph is: the left edge stands taller.
    assert MEASURED[3][1] - MEASURED[0][1] > MEASURED[2][1] - MEASURED[1][1]


def test_only_baseball_gets_it_and_it_rides_the_park():
    park = APP[APP.index("function pbpParkHTML("):]
    park = park[:park.index("\n}\n")]
    assert 'const board = league === "mlb" && typeof pbpBoardSVG === "function" ? pbpBoardSVG(d) : "";' in park
    assert '<div class="pbp-park">${art}${board}${runners}${arc}${chip}</div>' in park
    assert "function pbpBoardSVG(" not in APP, "the board is the live page's own (detail.js), not the boot file's"


# --- what it says -------------------------------------------------------------------
def test_live_it_shows_both_teams_the_runs_the_inning_and_the_count():
    svg = _node("return " + _svg({"state": "live", "away_score": 3, "home_score": 2, "period": "Top 6th",
                                  "balls": 2, "strikes": 1, "outs": 1}) + ";")
    if svg is None:
        return
    words = _texts(svg)
    for w in ("TB", "MIL", "3", "2", "6", "B", "S", "O"):
        assert w in words, (w, words)
    lit = lambda color: svg.count(f'<circle r="2.2" fill="{color}"/>')
    assert lit("#3DDC84") == 2, "two balls lit"
    assert lit("#FF5A4E") == 2, "a strike and an out lit"
    assert lit("#262B36") == 3, "the rest dark: one ball, one strike, one out"
    assert svg.count('d="M-1.4 -2.2 L1.8 0 L-1.4 2.2 Z"') == 1, "one lamp, at the team batting"
    assert 'd="M-3 2.2 L0 -2.6 L3 2.2 Z"' in svg, "the top half's arrow points up"
    assert 'aria-hidden="true"' in svg, "the score above the photograph says it in words"
    for invented in (">H<", ">E<", ">R<"):
        assert invented not in svg, f"{invented}: hits and errors are not in the live state"


def test_the_bottom_half_bats_the_home_team():
    svg = _node("return " + _svg({"state": "live", "away_score": 1, "home_score": 1, "period": "Bottom 9th",
                                  "balls": 3, "strikes": 2, "outs": 2}) + ";")
    if svg is None:
        return
    assert 'd="M-3 -2.2 L0 2.6 L3 -2.2 Z"' in svg, "the arrow points down"
    caret = svg.index('d="M-1.4 -2.2 L1.8 0 L-1.4 2.2 Z"')
    assert svg.index(">TB<") < caret < svg.index(">MIL<"), "the lamp sits on the home row"


def test_final_pregame_middle_and_a_delay_each_say_so():
    got = _node("return [" + ", ".join([
        _svg({"state": "final", "away_score": 4, "home_score": 11, "period": "Final"}, "NYY", "BOS"),
        _svg({"state": "scheduled", "start_time": "2026-10-25T23:10:00Z"}),
        _svg({"state": "live", "away_score": 3, "home_score": 2, "period": "Middle 3rd", "outs": 3}),
        _svg({"state": "live", "away_score": 1, "home_score": 7, "period": "Top 4th", "hold": "Delayed — Rain"}, "CWS", "DET"),
    ]) + "];")
    if got is None:
        return
    final, pre, mid, delay = (_texts(s) for s in got)
    assert "FINAL" in final and "4" in final and "11" in final, final
    assert ["FIRST", "PITCH", "7:10", "PM"] == [w for w in pre if w in ("FIRST", "PITCH", "7:10", "PM")], pre
    assert not any(w.isdigit() for w in pre), "no score before the first pitch"
    assert "MID" in mid and "3" in mid, mid
    assert "DELAYED" in delay and "RAIN" in delay and "B" not in delay, "a delay, not a count"


def test_a_run_that_just_scored_flashes_once_on_its_own_number():
    got = _node("const a = " + _svg({"state": "live", "away_score": 0, "home_score": 0, "period": "Top 2nd"})
                + "; const b = " + _svg({"state": "live", "away_score": 1, "home_score": 0, "period": "Top 2nd"})
                + "; const c = " + _svg({"state": "live", "away_score": 1, "home_score": 0, "period": "Top 2nd"})
                + "; const other = " + _svg({"state": "live", "away_score": 5, "home_score": 0, "period": "Top 2nd"}, "SD", "LAD")
                + "; return [a, b, c, other];")
    if got is None:
        return
    first, scored, again, other = got
    assert "pbp-sb-new" not in first, "nothing flashes on the first draw"
    assert scored.count("pbp-sb-new") == 1 and re.search(r'pbp-sb-new"[^>]*>1<', scored), "the away 1 flashes"
    assert "pbp-sb-new" not in again, "once"
    assert "pbp-sb-new" not in other, "another game's score is not a run that scored"
    assert ".pbp-sb-new { animation: pbp-sb-flash 1.4s linear 1; }" in DETAIL_CSS
    assert "@keyframes pbp-sb-flash" in CSS


def test_nothing_spills_off_the_board():
    got = _node("return [" + _svg({"state": "live", "away_score": 12, "home_score": 10, "period": "Top 11th"}, "ARI", "MIL")
                + ", " + _svg({"state": "live", "away_score": 1, "home_score": 2, "period": "Top 3rd",
                               "hold": "Suspended — Weather"}) + "];")
    if got is None:
        return
    extra, suspended = got
    assert len(re.findall(r'font-size="15"\s+text-anchor="end"', extra)) == 2, "two-digit scores step down a size"
    assert re.search(r'font-size="10" text-anchor="middle"[^>]*>11<', extra), "so does the 11th"
    word = _board_src()
    assert "const size = Math.min(max, room / (Math.max(1, txt.length) * 0.62));" in word, "a word fits its room"
    assert "const word = (txt, y, max, fill, mono, cx = 82, room = 30) => {" in word
    sizes = [float(s) for s in re.findall(r'font-size="([0-9.]+)" text-anchor="middle"\s*fill="#FFC94A">SUSPENDED', suspended)]
    assert sizes and sizes[0] * 0.62 * len("SUSPENDED") <= 30.1, sizes   # printed to two places


def test_the_runners_light_their_bags_second_at_the_top():
    lit_rect = lambda svg: len(re.findall(r'<rect x="-2.2" y="-2.2" width="4.4" height="4.4"\s+transform="rotate\(45\)" fill="#FFC94A"', svg))
    dark_rect = lambda svg: len(re.findall(r'<rect x="-2.2" y="-2.2" width="4.4" height="4.4"\s+transform="rotate\(45\)" fill="#262B36"', svg))
    cases = [[], [1], [2], [1, 3], [1, 2, 3]]
    got = _node("return [" + ", ".join(_svg({"state": "live", "away_score": 0, "home_score": 0, "period": "Top 3rd",
                                              "bases": b}) for b in cases)
                + ", " + _svg({"state": "final", "away_score": 1, "home_score": 0})
                + ", " + _svg({"state": "live", "period": "Top 3rd", "bases": [1], "hold": "Delayed — Rain"}) + "];")
    if got is None:
        return
    for bases, svg in zip(cases, got):
        assert (lit_rect(svg), dark_rect(svg)) == (len(bases), 3 - len(bases)), (bases, lit_rect(svg), dark_rect(svg))
    final, delay = got[-2:]
    assert lit_rect(final) + dark_rect(final) == 0, "no bags on a finished game"
    assert lit_rect(delay) + dark_rect(delay) == 0, "a delay says so instead"
    bags = {b: (x, y) for b, x, y in json.loads(re.search(r"const PBP_BOARD_BASES = (\[\[.*?\]\]);", DETAIL).group(1))}
    assert bags[2][1] < bags[1][1] == bags[3][1], "second at the top, first and third level"
    assert bags[3][0] < bags[2][0] < bags[1][0], "third on the left, first on the right"
    assert 82 < bags[3][0] - 3.12 and bags[1][0] + 3.12 < 100, "inside the column, clear of the inning"
    assert "const on = new Set(lv.bases || []);" in _board_src(), "the photograph's own base numbers (pbpBasesSVG)"


def test_a_teams_colour_shows_on_a_black_board():
    got = _node("return ['MIL', 'TB', 'BOS', 'NYY', 'XXX'].map(pbpBoardColor);")
    if got is None:
        return
    assert got[0].lower() == "#ffc52f", "the Brewers' navy would vanish; their gold shows"
    assert got[2].lower() == "#bd3039", "the Red Sox red shows as it is"
    assert got[4] == "#8C95A8", "a team the table does not know gets the board's grey"


def test_the_boards_faces_are_the_sites():
    assert ".pbp-board text { font-family: var(--font-display); font-weight: 800; }" in DETAIL_CSS
    assert ".pbp-board .pbp-sb-num { font-family: var(--font-mono); font-weight: 700; }" in DETAIL_CSS


# --- in a browser -------------------------------------------------------------------
def test_in_a_browser_the_board_sits_on_the_photographs_screen():
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
    gen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    live = {"state": "live", "home_score": 2, "away_score": 3, "period": "Top 6th", "outs": 1, "balls": 2, "strikes": 1,
            "bases": [1]}
    doc = T._mlb_doc()
    doc.update({"generated_at": gen, "home_name": "Detroit Tigers", "away_name": "New York Yankees", "plays": [], "live": live})
    strip = {"generated_at": gen, "games": [{"game_pk": 777001, "home": "DET", "away": "NYY", "live": live}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
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
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block", reduced_motion="reduce")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/mlb_777001.json*", serve(doc))
                    page.route("**/data/live_mlb.json*", serve(strip))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/mlb/777001", wait_until="load")
                    page.wait_for_selector(".pbp-park .pbp-board", timeout=15000)
                    got[width] = page.evaluate("""() => {
                      const park = document.querySelector('.pbp-park').getBoundingClientRect();
                      const photo = document.querySelector('.pbp-park .pbp-photo').getBoundingClientRect();
                      const poly = document.querySelector('.pbp-board polygon').getBoundingClientRect();
                      const words = [...document.querySelectorAll('.pbp-board text')].map((t) => t.textContent.trim());
                      const font = getComputedStyle(document.querySelector('.pbp-board text')).fontFamily;
                      const bags = [...document.querySelectorAll('.pbp-board rect[transform="rotate(45)"]')].map((r) => r.getAttribute('fill'));
                      return { photo: [photo.x, photo.y, photo.width, photo.height], park: [park.x, park.y, park.width, park.height],
                               poly: [poly.x, poly.y, poly.width, poly.height], words, font, bags,
                               wide: document.scrollingElement.scrollWidth - innerWidth };
                    }""")
                    got[width]["errors"] = errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for width, g in got.items():
        px, py, pw_, ph = g["photo"]
        # Where the measured screen is, in this photograph's pixels.
        xs = [px + x / 240 * pw_ for x, _ in MEASURED]
        ys = [py + y / 150 * ph for _, y in MEASURED]
        want = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
        assert all(abs(a - b) <= 1.5 for a, b in zip(g["poly"], want)), (width, g["poly"], want)
        for w in ("NYY", "DET", "3", "2", "6"):
            assert w in g["words"], (width, w, g["words"])
        assert "Archivo Narrow" in g["font"], g["font"]
        assert sorted(g["bags"]) == ["#262B36", "#262B36", "#FFC94A"], ("a runner on first, the other bags dark", g["bags"])
        assert g["wide"] <= 0 and not g["errors"], (width, g)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
