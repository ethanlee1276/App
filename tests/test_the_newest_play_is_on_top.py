"""The newest play is on top of every play list.

Ethan, 2026-11-15, on the play-by-play beside the live NE @ DET game: "I
feel like the live right here is moving the wrong way. The most recent play
should be at the top." The list put the drives newest first, but each
drive's plays read forwards. So the play just run sat at the bottom of the
top drive, and the NE drive under it began at its 15:00 kickoff and ended at
its field goal. Baseball, basketball and hockey already read newest first,
inside their groups too.

Now a football drive's plays are newest first too, in the rail (app.js
pbpGroups), on the Plays tab (detail.js gpDrivesHTML) and in the gamecast's
drive cards (gamecast.js drivesHTML). The Live tab card's last few plays
read the same way. Each drive's head still reads the drive in game order:
the key play is its first score or its last snap, and the score is the one
it left.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

APP = app_js()
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


LIVE = _Harness("test_the_live_trackers")


def _fn(name, src=None):
    src = src or APP
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _stamped():
    """The live NFL fixture (TB @ DAL, four drives, the fourth on now), every
    play given its own clock in game order, so the order on the page can be
    read off the clocks. A play's key is (period, seconds gone), increasing
    as the game goes."""
    fb = LIVE._fb_doc()
    fb["event_id"] = "e9"
    n = 0
    for dr in fb.get("drives") or []:
        for p in dr.get("plays") or []:
            left = 900 - 40 * (n % 20) - 5
            p["clock"] = f"{left // 60}:{left % 60:02d}"
            n += 1
    return fb


def _key(period, clock):
    m, s = str(clock).split(":")
    return (int(period), 900 - (int(m) * 60 + int(s)))


def _node(js):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no node)")
        return None
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_every_group_reads_newest_first_in_football_as_in_the_other_sports():
    fb = _stamped()
    hoops = {"league": "nba", "plays": [{"kind": "hoops", "id": str(i), "period": 1 + i // 3, "clock": f"{11 - i}:00",
                                         "event": "Jump Shot"} for i in range(6)]}
    got = _node("const DRIVE_RESULT = {}; const hockeyPeriod = (p) => `P${p}`, halfPeriod = (p) => `H${p}`;\n"
                + _fn("driveResultWord") + _fn("pbpGroups")
                + f"\nconst fb = {json.dumps(fb)}; fb.league = 'nfl';"
                + f"\nconst g = pbpGroups(fb), h = pbpGroups({json.dumps(hoops)});"
                + "\nprocess.stdout.write(JSON.stringify({ fb: g.map((x) => [x.head, x.tag, x.rows.map((p) => [p.period, p.clock])]),"
                + " hoops: h.map((x) => x.rows.map((p) => p.id)) }));")
    if got is None:
        return
    heads = [h for h, _, _ in got["fb"]]
    assert heads == ["DAL drive", "TB drive", "DAL drive", "TB drive"], ("the drives, newest first, as before", heads)
    assert got["fb"][0][1] == "IN PROGRESS", got["fb"][0]
    keys = [_key(*r) for _, _, rows in got["fb"] for r in rows]
    assert keys == sorted(keys, reverse=True), ("every play newest first, inside its drive too", keys)
    last = fb["drives"][-1]["plays"][-1]
    assert got["fb"][0][2][0] == [last["period"], last["clock"]], "the play just run is the first row"
    assert got["hoops"] == [["5", "4", "3"], ["2", "1", "0"]], ("basketball unchanged: newest first", got["hoops"])


def test_a_drives_head_still_reads_it_in_game_order():
    drives = _fn("gpDrivesHTML")
    # The key play (its first score, else its last snap) and the score it left.
    assert "const key = snaps.find((p) => p.scoring) || snaps[snaps.length - 1];" in drives
    assert "const last = rows.slice().reverse().find((p) => p.away_score != null && p.home_score != null) || {};" in drives
    assert "playsHTML({ plays: rows.slice().reverse(), home: d.home, away: d.away, league, room: pbpRoom(d, league) })" in drives
    # The gamecast's cards: the score after the drive's last play, the rows newest first.
    cards = GC[GC.index("function drivesHTML("):GC.index("function playsTabHTML(")]
    assert "const last = rows[rows.length - 1] || {};" in cards
    assert "playsHTML({ plays: rows.slice().reverse(), home: d.home, away: d.away," in cards
    # The Live tab card's last few plays, the newest on top of them.
    card = _fn("liveCardHTML")
    assert "${playsHTML({ ...g, plays: (g.plays || []).slice().reverse()," in card


def test_in_a_browser_the_rail_and_the_plays_tab_put_the_newest_play_on_top():
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
    fb = _stamped()
    strip = {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": fb["live"], "plays_state": "ok"}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
    want = sorted((_key(p["period"], p["clock"]) for dr in fb["drives"] for p in dr["plays"]), reverse=True)
    read = """(sel) => [...document.querySelectorAll(sel)].map((r) => {
        const m = /(?:Q(\\d)|OT)\\s+(\\d+:\\d\\d)/.exec(r.textContent); return m ? [m[1] || '5', m[2]] : null; })
      .filter(Boolean)"""
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/data/pbp/nfl_e9.json*", serve(fb))
                page.route("**/data/live_nfl.json*", serve(strip))
                page.goto(f"http://127.0.0.1:{port}/#pbp/nfl/e9", wait_until="load")
                page.wait_for_selector(".pbp-main .gc-dv", timeout=15000)
                page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                # The rail beside every tab but Plays.
                page.click('.pbp-tab[data-pbp-tab="stats"]')
                page.wait_for_selector(".pbp-rail .pbp-group .lb-play", state="attached", timeout=5000)
                rail = [_key(int(q), c) for q, c in page.evaluate(f"({read})('.pbp-rail .pbp-group .lb-play')")]
                assert rail and rail == sorted(rail, reverse=True), ("the rail, newest first", rail)
                assert rail[0] == want[0], ("its first row is the play just run", rail[:3], want[:3])
                # The Plays tab: the drive on now, open, its newest play first.
                page.click('.pbp-tab[data-pbp-tab="plays"]')
                page.wait_for_selector(".gp-dr .lb-play", state="attached", timeout=5000)
                tab = [_key(int(q), c) for q, c in page.evaluate(f"({read})('.gp-dr .lb-play')")]
                assert tab == sorted(tab, reverse=True), ("the Plays tab, newest first", tab)
                assert tab[0] == want[0], (tab[:3], want[:3])
                assert page.evaluate("document.querySelector('.gp-dr').open"), "the drive on now is the open one, on top"
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
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
