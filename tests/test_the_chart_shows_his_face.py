"""The carry and route chart shows the player's face — his photo, or his initials.

Ethan, 2026-10-13, about the charts: "Make sure we are showing headshots
in this new page." The chart's header drew an EMPTY ring whenever it had
no photo or the photo did not load, and two things left it without one:

  * the chart names a player the way its play file does and the face was
    looked up by that name alone. In this checkout's chart tables 48 of 685
    NFL chart players had no face that way — players on last season's
    roster and not this one, and spellings like "Kenny Gainwell" against
    the roster file's "Kenneth Gainwell" — while every row carries the
    league's own id;
  * a college face is ESPN's by-id path, built for every athlete whether
    ESPN has a photo of him or not, so some of them fail to load.

Pinned here:

  * the daily face pass gives a chart player with no face one JOINED ON
    THE ID — this season's NFL roster file first, then his last season's
    and the one before; in college the id is the path — only where his
    name has none, and never for a name two ids share;
  * the chart reads the row stored under its own spelling before the
    six-hour face map, so a face filled this morning shows this morning;
  * the page draws his initials under every photo; a photo that loads
    hides them, one that fails tries the next (the small copy, the full
    one, then the face the player's page was showing, which the door hands
    over), and with none left the initials stay; a redraw remembers both;
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): the real module in
    Chromium — a small copy that fails falls back to the full photo, which
    loads and hides the initials; a player with no photo that loads shows
    his initials and no broken image.

    QB_BROWSER_TESTS=1 python3 tests/test_the_chart_shows_his_face.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
import struct
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import facesfill                                        # noqa: E402
from engine import db as D, rosters, statlogs           # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
GAINWELL = "https://static.www.nfl.com/image/upload/f_auto,q_auto/league/gainwell"


def _carry(conn, player, pid, season, play, sport="nfl", table="carries", yards=4.0):
    cols = {"sport": sport, "season": season, "period": "005", "game_id": f"g{season}",
            "play_id": str(play), "date": f"{season}-10-05", "player": player, "player_id": pid,
            "team": "PIT", "opponent": "CLE", "home": 1, "position": "RB", "jersey": "14",
            "qtr": 1, "clock": "10:00", "down": 1, "distance": 10, "yardline_100": 60,
            "yards": yards, "td": 0, "first_down": 0}
    if table == "carries":
        cols.update(hole="LG", scramble=0, fumble=0, fumble_lost=0)
    else:
        cols.update(air_yards=8.0, side="left", complete=1, yac=2.0, interception=0)
    marks = ", ".join("?" * len(cols))
    conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})", list(cols.values()))


def _face(conn, sport, player, url, pid=""):
    D.upsert_player_assets(conn, [{"sport": sport, "player": player, "espn_id": pid,
                                   "headshot": url, "seen": "2026-10-13"}])


# --- the daily pass -----------------------------------------------------------
def test_a_chart_player_spelled_differently_gets_his_face_by_id():
    conn = D.connect(":memory:")
    _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 1)
    _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 2, table="targets")
    _carry(conn, "Sam LaPorta", "00-0039149", 2026, 3, table="targets")
    # The roster pass wrote him under the roster file's spelling.
    _face(conn, "nfl", "Kenneth Gainwell", "https://elsewhere/kenneth.png")
    _face(conn, "nfl", "Sam LaPorta", "https://static.www.nfl.com/laporta")
    asked = []

    def by_id(season):
        asked.append(season)
        return {2025: {"00-0036919": GAINWELL}}.get(season, {})
    rows = facesfill.chart_rows(conn, "nfl", by_id=by_id)
    assert [(r["player"], r["headshot"]) for r in rows] == [("Kenny Gainwell", GAINWELL)]
    # This season's file first — a photo is retaken — then his last season's.
    assert asked == [2026, 2025], asked


def test_only_a_name_with_no_face_is_touched():
    conn = D.connect(":memory:")
    _carry(conn, "Marvin Harrison Jr.", "00-0039849", 2026, 1, table="targets")
    _carry(conn, "Sam LaPorta", "00-0039149", 2026, 2, table="targets")
    _carry(conn, "D.J. Moore", "00-0034827", 2026, 3, table="targets")
    _face(conn, "nfl", "Marvin Harrison", "https://x/mhj.png")     # the suffix folds away
    _face(conn, "nfl", "Sam LaPorta", "https://x/laporta.png")
    # The shared name join reads "D.J." and "DJ" as two names, so his face
    # under the roster's "DJ Moore" never reached a chart that says "D.J."
    _face(conn, "nfl", "DJ Moore", "https://x/moore.png")
    ids = {"00-0039849": "https://y/h.png", "00-0039149": "https://y/l.png", "00-0034827": "https://y/m.png"}
    rows = facesfill.chart_rows(conn, "nfl", by_id=lambda s: ids)
    assert [(r["player"], r["headshot"]) for r in rows] == [("D.J. Moore", "https://y/m.png")], \
        "a name with a face keeps the one it has; the one the name join missed gets his by id"


def test_a_name_two_ids_share_gets_no_face():
    conn = D.connect(":memory:")
    _carry(conn, "Michael Carter", "00-0036000", 2025, 1)
    _carry(conn, "Michael Carter", "00-0037000", 2026, 2)
    rows = facesfill.chart_rows(conn, "nfl", by_id=lambda s: {"00-0036000": "https://y/a.png",
                                                              "00-0037000": "https://y/b.png"})
    assert rows == [], "initials beat somebody else's face"


def test_college_builds_espns_path_from_the_id_and_reads_no_file():
    conn = D.connect(":memory:")
    _carry(conn, "Jeremiah Smith", "4870906", 2026, 1, sport="cfb")
    _carry(conn, "Has One", "111", 2026, 2, sport="cfb")
    _face(conn, "cfb", "Has One", "https://a.espncdn.com/x/111.png", "111")

    def no_file(_season):
        raise AssertionError("college reads no roster file for a face")
    rows = facesfill.chart_rows(conn, "cfb", by_id=no_file)
    assert rows == [{"sport": "cfb", "player": "Jeremiah Smith", "espn_id": "4870906",
                     "headshot": "https://a.espncdn.com/i/headshots/college-football/players/full/4870906.png",
                     "seen": rows[0]["seen"]}]


def test_no_chart_tables_is_no_rows_not_a_crash():
    import sqlite3
    bare = sqlite3.connect(":memory:")
    assert facesfill.chart_rows(bare, "nfl", by_id=lambda s: {}) == []
    assert facesfill.chart_rows(D.connect(":memory:"), "mlb") == []


def test_fill_writes_the_roster_first_and_only_the_charts_gaps_after():
    with tempfile.TemporaryDirectory() as td:
        conn = D.connect(os.path.join(td, "h.db"))
        _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 1)
        _carry(conn, "Sam LaPorta", "00-0039149", 2026, 2, table="targets")
        conn.commit()
        roster = {"Sam LaPorta": "https://static.www.nfl.com/laporta", "Kenneth Gainwell": "https://k"}
        ids = {"00-0036919": GAINWELL, "00-0039149": "https://never-used"}
        with mock.patch("engine.sources.nflverse.headshot_map", return_value=roster), \
                mock.patch("engine.sources.nflverse.headshots_by_id", return_value=ids):
            n, _before, _after = facesfill.fill(conn, "nfl", dry_run=True)
            assert n == 3 and conn.execute("SELECT COUNT(*) FROM player_assets").fetchone()[0] == 0, \
                "a dry run counts the roster's two and the chart's one gap, and writes nothing"
            n, before, after = facesfill.fill(conn, "nfl")
        assert (n, before, after) == (3, 0, 3)
        got = dict(conn.execute("SELECT player, headshot FROM player_assets WHERE sport='nfl'"))
        assert got["Kenny Gainwell"] == GAINWELL
        assert got["Sam LaPorta"] == "https://static.www.nfl.com/laporta", "the roster's photo stands"


def test_the_daily_chores_and_the_command_line_ask_for_college():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("import facesfill")
    assert '("nfl", "mlb", "nba", "wnba", "cfb")' in src[i:i + 900]
    assert '"wnba", "cfb"]' in (ROOT / "facesfill.py").read_text(encoding="utf-8")


def test_the_check_counts_the_charts_players_the_way_the_chart_reads_them():
    memo = dict(rosters._FACE_MEMO)
    rosters._FACE_MEMO.clear()             # this file's faces, not an earlier test's
    try:
        _check_counts()
    finally:
        rosters._FACE_MEMO.clear()
        rosters._FACE_MEMO.update(memo)


def _check_counts():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.db")
        conn = D.connect(path)
        _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 1)
        _carry(conn, "Sam LaPorta", "00-0039149", 2026, 2, table="targets")
        _carry(conn, "Jeremiah Smith", "4870906", 2026, 3, sport="cfb")
        _face(conn, "nfl", "Sam LaPorta", "https://x/laporta.png")
        conn.commit()
        assert facesfill.chart_coverage(conn, "nfl") == (1, 2, ["Kenny Gainwell"])
        assert facesfill.chart_coverage(conn, "cfb") == (0, 1, ["Jeremiah Smith"])
        assert facesfill.chart_coverage(conn, "mlb") == (0, 0, [])
        before = conn.execute("SELECT COUNT(*) FROM player_assets").fetchone()[0]
        conn.close()
        out = subprocess.run([sys.executable, str(ROOT / "facesfill.py"), "--check", "--db", path],
                             capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        assert out.returncode == 0, out.stderr
        assert "NFL   1 of 2 chart players have a face; none for: Kenny Gainwell" in out.stdout
        assert "CFB   0 of 1 chart players have a face; none for: Jeremiah Smith" in out.stdout
        conn = D.connect(path)
        assert conn.execute("SELECT COUNT(*) FROM player_assets").fetchone()[0] == before, "read-only"
    assert "python3 facesfill.py --check" in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")


# --- what the chart serves ------------------------------------------------------
def test_the_chart_reads_the_row_under_its_own_spelling_before_the_face_map():
    conn = D.connect(":memory:")
    _face(conn, "nfl", "Kenny Gainwell", GAINWELL)
    keep = dict(rosters._FACE_MEMO)
    try:
        # The six-hour map, taken before this morning's pass wrote him.
        rosters._FACE_MEMO["nfl"] = (time.time(), {"someone else": "https://x/else.png"})
        assert statlogs._face_of(conn, "nfl", "Kenny Gainwell") == ""
        assert statlogs.face(conn, "nfl", "Kenny Gainwell") == GAINWELL
        assert statlogs.face(conn, "nfl", "Someone Else") == "https://x/else.png", "then the map"
        assert statlogs.face(None, "nfl", "Nobody") == "", "never raises"
    finally:
        rosters._FACE_MEMO.clear()
        rosters._FACE_MEMO.update(keep)


def test_both_chart_endpoints_serve_that_face():
    import server
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    for fn in ("def _players_carries(", "def _players_routes("):
        i = src.index(fn)
        body = src[i:src.index("\n    def ", i + 10)]
        assert 'out["face"] = statlogs.face(conn, ' in body, fn
    tmp = tempfile.mkdtemp()
    keep, memo = D.DEFAULT_DB, dict(rosters._FACE_MEMO)
    try:
        path = Path(tmp) / "history.db"
        conn = D.connect(str(path))
        _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 1)
        _carry(conn, "Kenny Gainwell", "00-0036919", 2025, 2, table="targets")
        _face(conn, "nfl", "Kenny Gainwell", GAINWELL)
        conn.commit()
        conn.close()
        D.DEFAULT_DB = path
        rosters._FACE_MEMO["nfl"] = (time.time(), {"someone else": "https://x/else.png"})
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_carries({"sport": ["nfl"], "player": ["Kenny Gainwell"]})
        h._players_routes({"sport": ["nfl"], "player": ["Kenny Gainwell"]})
    finally:
        D.DEFAULT_DB = keep
        rosters._FACE_MEMO.clear()
        rosters._FACE_MEMO.update(memo)
        shutil.rmtree(tmp, ignore_errors=True)
    assert [b.get("face") for _c, b in sent] == [GAINWELL, GAINWELL], sent


# --- the page -------------------------------------------------------------------
def _node(js, extra=""):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
      const teamNameIn = (lg, a) => a;
      const lockScroll = () => {};
      const window = {};
    """ + extra
    prog = f"{stubs}\n{CC_JS}\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_his_initials_are_drawn_under_every_photo_and_alone_without_one():
    got = _node("""
      const st = { hint: "" }, st2 = { hint: "https://x/page.png" }, st3 = { hint: "" };
      return {
        both: T.faceHTML({ player: "Marvin Harrison Jr.", face: "https://x/a.png", sport: "nfl" }, st),
        list: st.faces,
        none: T.faceHTML({ player: "Sam LaPorta", face: "", sport: "nfl" }, st3),
        hint: T.faceHTML({ player: "Sam LaPorta", face: "", sport: "nfl" }, st2),
        names: ["A.J. Brown", "Amon-Ra St. Brown", "Kenneth Walker III", "Travis Kelce", "", "Pelé"].map(T.inits),
      };""")
    if got is None:
        assert "function inits(" in CC_JS and 'class="cc-init" aria-hidden="true"' in CC_JS
        return
    assert '<span class="cc-face"><span class="cc-init" aria-hidden="true">MH</span><img src="https://x/a.png"' in got["both"]
    assert got["list"] == ["https://x/a.png"]
    assert "<img" not in got["none"] and ">SL</span></span>" in got["none"], got["none"]
    assert '<img src="https://x/page.png"' in got["hint"], "the page's own face when the chart has none"
    assert got["names"] == ["AB", "AB", "KW", "TK", "?", "P"]


def test_the_small_copy_then_the_full_one_then_the_pages_and_a_redraw_remembers():
    extra = "const facePreview = (u, px) => u + '?w=' + px * 2;"
    got = _node("""
      const st = { hint: "https://x/page.png" };
      const d = { player: "Sam LaPorta", face: "https://x/srv.png", sport: "nfl" };
      T.faceHTML(d, st);
      const order = [st.faces[st.fi]];
      let removed = false;
      const parent = { classes: [], classList: { add(c) { parent.classes.push(c); } } };
      const img = { tagName: "IMG", src: st.faces[0], closest: (s) => s === ".cc-face", parentNode: parent,
                    remove() { removed = true; } };
      for (let i = 0; i < 3; i++) { T.faceStep("error", img, st); order.push(img.src); }
      T.faceStep("load", img, st);
      const loaded = { classes: parent.classes.slice(), ok: st.faceOk, redraw: T.faceHTML(d, st) };
      T.faceStep("error", img, st);
      const gone = { removed, redraw: T.faceHTML(d, st) };
      const stray = { tagName: "IMG", closest: () => null };
      T.faceStep("error", stray, st);
      return { order, list: st.faces, loaded, gone, fi: st.fi };""", extra)
    if got is None:
        return
    assert got["list"] == ["https://x/srv.png?w=116", "https://x/srv.png",
                           "https://x/page.png?w=116", "https://x/page.png"]
    assert got["order"] == got["list"], got["order"]
    assert got["loaded"]["classes"] == ["on"] and got["loaded"]["ok"] is True
    assert '<span class="cc-face on">' in got["loaded"]["redraw"], "a redraw keeps the initials hidden"
    # The last one failing too: no photo left, the initials alone, no new request.
    assert got["gone"]["removed"] is True
    assert "<img" not in got["gone"]["redraw"] and '<span class="cc-face">' in got["gone"]["redraw"]
    assert got["fi"] == 4, "a stray image outside the face moves nothing"


def test_the_initials_wear_his_teams_colour_when_the_page_knows_it():
    extra = """
      const teamsForSport = (lg) => lg === "nfl" ? { DET: { primary: "#0076B6" } } : {};
      const idealText = () => "#ffffff";
    """
    got = _node("""
      return [T.faceHTML({ player: "Sam LaPorta", sport: "nfl", team: "DET" }, { hint: "" }),
              T.faceHTML({ player: "Sam LaPorta", sport: "cfb", team: "DET" }, { hint: "" })];""", extra)
    if got is None:
        return
    assert 'style="background:#0076B6;color:#ffffff">SL<' in got[0]
    assert "style=" not in got[1], "an unknown team leaves the neutral disc"


def test_the_css_hides_the_initials_once_a_photo_is_in():
    css = re.sub(r"/\*.*?\*/", "", CC_CSS, flags=re.S)
    assert ".cc-face.on .cc-init { visibility: hidden; }" in css
    i = css.index(".cc-init {")
    rule = css[i:css.index("}", i)]
    assert "position: absolute" in rule and "inset: 0" in rule and "place-items: center" in rule


def test_the_door_hands_over_the_face_and_no_handler_is_inline():
    assert "chartDoor(player, lg, priced.get(mkt) || r0)" in APP_JS
    assert 'ccDoor(player, lg, "auto", "His charts", r.headshot, r)' in APP_JS, "the face the page shows"
    assert '${face ? ` data-face="${escapeAttr(face)}"` : ""}' in APP_JS
    assert "m.open(d.carry, d.lg, d.kind, d.face, d.mkt, d.pos, d.opp)" in APP_JS
    assert "function open(player, sport, kind, face, mkt, pos, opp)" in CC_JS and 'hint: face || ""' in CC_JS
    assert 'ov.addEventListener("load", faceEvent, true);' in CC_JS
    assert 'ov.addEventListener("error", faceEvent, true);' in CC_JS
    assert not re.search(r"\bon(error|load)\s*=", CC_JS), "the page's CSP allows no inline handler"
    assert "${faceHTML(d, S)}" in CC_JS


# --- the browser, opt-in --------------------------------------------------------
def _png():
    """A 2x2 opaque PNG, written with the standard library."""
    raw = b"".join(b"\x00" + b"\x40\x80\xc0" * 2 for _ in range(2))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  const facePreview = (u, px) => u + "?w=" + px * 2;
  window.fetch = async (q) => ({{ ok: true, json: async () => window.CHART }});
</script>
<script>{js}</script></body></html>"""


def _chart(face):
    game = {"id": "g", "period": "005", "week": 5, "date": "2026-10-05", "opp": "CLE", "home": True,
            "team": "PIT", "line": {"n": 1, "yds": 4, "ypc": 4, "td": 0, "long": 4, "first": 0,
                                    "success": 0, "stuffed": 0, "explosive": 0, "fum": 0},
            "carries": [{"q": 1, "clk": "10:00", "dn": 1, "ds": 10, "yl": 60, "y": 4, "h": "LG",
                         "sc": False, "td": False, "fl": False, "fd": False, "band": "short"}]}
    return {"player": "Kenny Gainwell", "sport": "nfl", "holes": True, "seasons": [2025], "season": 2025,
            "team": "PIT", "position": "RB", "jersey": "14", "games": [game],
            "season_line": game["line"], "bands": {"loss": 0, "short": 1, "gain": 0},
            "by_hole": [], "by_zone": [], "by_down": [], "kinds": {}, "ngs": {}, "face": face}


def test_in_a_browser_a_failed_photo_falls_back_and_a_missing_one_shows_initials():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    html = PAGE.format(css=CC_CSS, js=CC_JS)
    png = _png()
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            asked = []

            def photo(route):
                asked.append(route.request.url)
                if "?w=" in route.request.url or "nobody" in route.request.url:
                    return route.fulfill(status=404, body="")
                return route.fulfill(status=200, content_type="image/png", body=png)
            page.route("https://faces.test/**", photo)
            page.set_content(html)
            page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Kenny Gainwell', 'nfl', 'carries'); }",
                          _chart("https://faces.test/gainwell.png"))
            page.wait_for_selector(".cc-head .cc-face.on img", timeout=5000)
            # His card (2026-10-14) asks for its own size of the same photo
            # beside the header's, and steps to the whole one the same way.
            page.wait_for_selector(".mb-hero-face .cc-act.cut.on img", timeout=5000)
            assert set(asked[:2]) == {"https://faces.test/gainwell.png?w=116",
                                      "https://faces.test/gainwell.png?w=320"}, asked
            assert set(asked[2:]) == {"https://faces.test/gainwell.png"}, asked
            assert page.evaluate("getComputedStyle(document.querySelector('.cc-head .cc-init')).visibility") == "hidden"
            page.evaluate("window.QBCarry.close()")

            page.evaluate("(c) => { window.CHART = c; window.QBCarry.open('Kenny Gainwell', 'nfl', 'carries'); }",
                          _chart("https://faces.test/nobody.png"))
            page.wait_for_selector(".cc-head", timeout=5000)
            page.wait_for_function("() => !document.querySelector('.cc-face img') && !document.querySelector('.cc-act')",
                                   timeout=5000)
            init = page.locator(".cc-head .cc-init")
            assert init.inner_text() == "KG" and init.is_visible()
            assert page.evaluate("getComputedStyle(document.querySelector('.cc-head .cc-init')).visibility") == "visible"
            card = page.locator(".mb-hero-face .cc-init")
            assert card.inner_text() == "KG" and card.is_visible()
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
