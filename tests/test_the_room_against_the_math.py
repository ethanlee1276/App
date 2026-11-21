"""The room against the math: the game chat's who-wins vote drawn through
the game against the live win chance (docs/IDEAS.md, the live game list's
fourth; built 2026-10-28, runbook FS).

"The room had CIN at 30% when the math had them at 70%." What these hold:

  * the vote's split is marked at most once a minute (engine/gamechat
    chat_vote_marks): a later vote inside the minute rewrites that minute's
    mark, so a busy room is a line, not a row for every tap; the marks are
    aggregates only, no user ids; they are pruned with the rest of the room;
  * a room hands back its marks (`vote_path`, oldest first, capped);
  * the game page's win-chance chart carries each play's time and the
    room's line, key and sentence as places to fill (js/detail.js
    pbpWinChartHTML), and only when every play has its time;
  * js/detail.js pbpRoomLine lays the marks along the plays by time, only
    marks with ten votes behind them, and says the widest gap of fifteen
    points or more, of the side the math favoured; the chat hands over its
    marks (js/chat.js chatVotePath) and asks for a redraw when they move;
  * and in a browser, a game page with a room behind it draws the dashed
    line and the sentence.

Run directly: `python3 tests/test_the_room_against_the_math.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import gamechat as G  # noqa: E402

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, created_at REAL)")
    G.ensure_tables(c)
    return c


def _open_game(monkey):
    real = G.game_of
    G.game_of = lambda room, data_dir=None: {"state": "in"}
    try:
        return monkey()
    finally:
        G.game_of = real


def test_the_split_is_marked_once_a_minute_and_carries_no_one():
    c = _db()

    def run():
        t = 1000.0
        for i, side in enumerate(("home", "home", "away")):
            G.vote(c, i + 1, "nfl_401", side, now=t + i * 20)     # one minute: one mark, rewritten
        G.vote(c, 4, "nfl_401", "home", now=t + 60)               # the next minute: a new mark
        G.vote(c, 5, "nfl_401", "away", now=t + 130)
        G.vote(c, 1, "nfl_401", "away", now=t + 140)              # a changed mind moves the same mark
        return G.vote_path(c, "nfl_401")
    assert _open_game(run) == [[1000.0, 2, 1], [1060.0, 3, 1], [1130.0, 2, 3]]
    cols = [r[1] for r in c.execute("PRAGMA table_info(chat_vote_marks)")]
    assert cols == ["room", "at", "home", "away"], "aggregates only: no user ids"


def test_a_room_hands_back_its_path_capped_and_pruned():
    c = _db()

    def run():
        for i in range(G.VOTE_PATH_MAX + 5):
            G.vote(c, i + 1, "nba_7", "home" if i % 3 else "away", now=1000.0 + i * G.VOTE_MARK_EVERY_S)
    _open_game(run)
    path = G.vote_path(c, "nba_7")
    assert len(path) == G.VOTE_PATH_MAX and path[0][0] < path[-1][0], "the newest marks, oldest first"
    src = Path(G.__file__).read_text(encoding="utf-8")
    view = src[src.index("def room_view("):]
    assert '"vote_path": vote_path(conn, room),' in view[:view.index("\ndef ")]
    prune = src[src.index("def _prune("):]
    assert 'conn.execute("DELETE FROM chat_vote_marks WHERE at<?", (old,))' in prune[:prune.index("\ndef ")]


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_chart_carries_the_times_and_the_places_to_fill():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    chart = _fn(DETAIL, "pbpWinChartHTML")
    prog = f"""
      const escapeHtml = (s) => String(s); const escapeAttr = (s) => String(s);
      const WP_W = 320, WP_H = 110;
      {chart}
      const plays = (timed) => [0, 1, 2, 3, 4].map((i) => ({{ wp: 40 + i * 5, wpa: 0,
        at: timed ? new Date(Date.UTC(2026, 9, 25, 17, i)).toISOString() : "" }}));
      console.log(JSON.stringify([pbpWinChartHTML({{ home: "ATL", away: "SF", plays: plays(true) }}, "nfl"),
                                  pbpWinChartHTML({{ home: "ATL", away: "SF", plays: plays(false) }}, "nfl")]));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    timed, untimed = json.loads(out.stdout)
    assert 'data-ats="1792947600,1792947660,1792947720,1792947780,1792947840"' in timed
    assert 'data-wps="40,45,50,55,60"' in timed and 'data-home="ATL" data-away="SF"' in timed
    assert '<polyline class="pbp-wp-room" fill="none" points=""/>' in timed
    assert '<span class="pbp-wp-roomkey" hidden>' in timed and '<p class="mini pbp-wp-says" hidden></p>' in timed
    for part in ("data-ats", "pbp-wp-room", "pbp-wp-says"):
        assert part not in untimed, part


def test_the_line_and_the_sentence_and_who_hands_them_over():
    line = _fn(DETAIL, "pbpRoomLine")
    assert "const ROOM_LINE_MIN_VOTES = 10, ROOM_LINE_GAP = 15;" in DETAIL
    assert '.filter((m) => m[1] + m[2] >= ROOM_LINE_MIN_VOTES);' in line, "ten votes behind a mark"
    assert "const path = (before ? [[ats[0], before[1], before[2]]] : []).concat(marks.filter((m) => m[0] >= ats[0]));" in line
    assert "if (best.gap < ROOM_LINE_GAP) { says.hidden = true; return; }" in line
    assert "const home = best.math >= 50;" in line, "said of the side the math favoured"
    assert "`The room had ${home ? svg.dataset.home : svg.dataset.away} at ${pct(best.room)}% `" in line
    assert "pbpRoomLine();" in DETAIL[DETAIL.index("const wire = () => {"):], "drawn with the page"
    assert "CH.votePath = v.vote_path || CH.votePath || [];" in CHAT
    assert 'if (typeof pbpRoomLine === "function") pbpRoomLine();' in CHAT, "redrawn when the vote moves"
    assert "function chatVotePath() {\n  return CH.votePath || [];\n}" in CHAT
    for cls in ("pbp-wp-room", "pbp-wp-roomkey", "pbp-wp-says"):
        assert cls not in CHAT, f"{cls} is the game page's to draw (css/detail.css is its room's)"


# --- in a browser (opt-in) -------------------------------------------------------------------
def test_in_a_browser_the_room_is_dashed_on_the_chart_and_said():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import time
    import rendercheck
    t0 = 1792947600  # 2026-10-25 17:00 UTC
    plays = []
    for i in range(12):
        wp = 70 - i * 2      # the math has ATL about 70% early, drifting down
        plays.append({"kind": "football", "id": f"p{i}", "period": 1, "clock": f"{14 - i}:00", "team": "SF",
                      "event": "Rush", "yards": 4, "away_score": 0, "home_score": 0, "wp": wp, "wpa": 0,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0 + i * 120))})
    pbp = {"league": "nfl", "event_id": "401", "home": "ATL", "away": "SF", "generated_at": "2026-10-25T17:30:00Z",
           "live": {"state": "live", "period": "Q1", "clock": "3:00", "away_score": 0, "home_score": 0},
           "plays": plays, "drives": [{"team": "SF", "plays": plays, "yards": 48}]}
    # The room: 30% ATL at kickoff, the same through the first half hour, 12 then 20 votes.
    marks = [[t0 - 300, 4, 8], [t0 + 300, 6, 14], [t0 + 900, 9, 11]]
    room = {"room": "nfl_401", "t": time.time(), "older": False, "reacts": {}, "plays": {}, "threads": {},
            "mine_plays": {}, "votes": {"home": 9, "away": 11, "mine": "", "open": True}, "here": 4,
            "me": {"signed_in": False}, "messages": [], "vote_path": marks}
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            b = pw.chromium.launch(**kw)
            try:
                p = b.new_context(viewport={"width": 1280, "height": 900}, service_workers="block").new_page()
                errs = []
                p.on("pageerror", lambda e: errs.append(str(e)))
                p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                p.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                mk = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
                p.route("**/data/pbp/nfl_401.json*", mk(pbp))
                p.route("**/api/chat/room*", mk(room))
                p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
                p.wait_for_selector(".pbp-wpcard .pbp-wp-room", state="attached", timeout=20000)
                # A function, not an expression: the site's CSP refuses a string Playwright would eval.
                p.wait_for_function("() => { const l = document.querySelector('.pbp-wp-room');"
                                    " return !!l && (l.getAttribute('points') || '').length > 0; }", timeout=20000)
                got = p.evaluate("""() => ({
                  pts: document.querySelector('.pbp-wp-room').getAttribute('points').trim().split(' ').length,
                  key: !document.querySelector('.pbp-wp-roomkey').hidden,
                  says: document.querySelector('.pbp-wp-says').hidden ? '' : document.querySelector('.pbp-wp-says').textContent })""")
                assert got["pts"] == 3 and got["key"], got
                # At kickoff the room had ATL at 33% (4 of 12) when the math had them at 70%.
                assert got["says"] == "The room had ATL at 33% when the math had them at 70%.", got
                assert not errs, errs
            finally:
                b.close()
    finally:
        srv.shutdown()


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
