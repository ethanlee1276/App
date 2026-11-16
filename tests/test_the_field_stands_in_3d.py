"""The field under the score stands in 3D, its posts where the field puts them.

Ethan, 2026-11-16, with FanDuel's tracker beside ours: "I like fanduels render
and how it looks 3d. I want ours too look like that". The night before, on
the drawn field the Last play card had then: "the goal posts are off compared
too the field". That field leaned its yard lines to fake depth and stood its
posts upright on top of it, so nothing tied the two together.

The strip under the score is now a field seen by one camera (detail.js
gpField3dSVG). Every mark is a point on a real field in yards, X along it as
the spots run (0 is home's goal line), Y across it, Z up, and goes through
the same pinhole camera. So the far sideline is narrower than the near one,
the yard lines run to one vanishing point, the posts stand straight up, and
their bases sit two yards behind each end line with the crossbar over it.
The small copy in the bar at the top of the screen stays the flat strip.
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
sys.path.insert(0, str(ROOT / "tests"))

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
FIELD = DETAIL[DETAIL.index("const GP3_W = "):DETAIL.index("function gpDriveWords(")]
STUBS = r"""
const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const escapeAttr = escapeHtml;
const safeHref = (u) => (/^https?:\/\//.test(String(u)) ? escapeAttr(u) : "#");
const NICK = { DET: "Lions", MIN: "Vikings", ND: "Fighting Irish" };
const teamNameIn = (lg, a) => NICK[a] || a;
const logoUrl = (a, lg, n) => `https://logo.test/${lg}/${a}.png`;
"""
MIN_AT_DET = {"los": 25, "dir": -1, "off": "MIN", "gain": 20, "goal": False, "start": 74, "words": "4th & 5 · DET 25"}


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


LIVE = _Harness("test_the_live_trackers")


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no node)")
        return None
    js = f"{STUBS}\n{FIELD}\nprocess.stdout.write(JSON.stringify((() => {{ {body} }})()));"
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


def test_the_camera_sees_a_field_in_perspective_and_keeps_the_posts_upright():
    got = _node("""
      const W = GP3_W, ln = (a, b) => b[0] - a[0];
      const near = ln(gp3(-10, 0), gp3(110, 0)), far = ln(gp3(-10, W), gp3(110, W));
      // Where the goal lines, extended, meet: one vanishing point for every line along Y.
      const meet = (x) => { const a = gp3(x, 0), b = gp3(x, W); const t = (0 - a[0]) / (b[0] - a[0]); return a[1] + t * (b[1] - a[1]); };
      return { near, far, deep: gp3(50, W)[1] - gp3(50, 0)[1], vp: [meet(0), meet(100), meet(20)],
               upright: [gp3(-10, 20, 0)[0], gp3(-10, 20, 15)[0]], upright2: [gp3(110, 33, 0)[0], gp3(110, 33, 15)[0]],
               up: gp3(50, 0, 15)[1] < gp3(50, 0, 0)[1] };
    """)
    if got is None:
        return
    assert 0.55 < got["far"] / got["near"] < 0.7, ("the far sideline narrower than the near one", got["far"] / got["near"])
    assert got["deep"] < 0, "the far sideline higher on the screen than the near one"
    assert max(got["vp"]) - min(got["vp"]) < 1e-6, ("the yard lines run to one vanishing point", got["vp"])
    assert abs(got["upright"][0] - got["upright"][1]) < 1e-9 and abs(got["upright2"][0] - got["upright2"][1]) < 1e-9, \
        "a level camera: the posts stand straight up, wherever they are"
    assert got["up"], "up is up the screen"


def test_the_posts_stand_behind_the_end_lines_with_the_crossbar_over_them():
    got = _node(f"""
      const svg = gpField3dSVG({json.dumps(MIN_AT_DET)}, {{ home: "DET", away: "MIN" }}, "nfl");
      const P = (x, y, z) => gp3(x, y, z).map((v) => v.toFixed(1)).join(" ");
      const W = GP3_W, mid = W / 2, h = GP3_POST.half, bar = GP3_POST.bar, top = bar + GP3_POST.up;
      const posts = [...svg.matchAll(/<path class="gp3-post" d="([^"]+)"/g)].map((m) => m[1]);
      return {{ posts, post: GP3_POST,
        home: [P(-10 - GP3_POST.back, mid, 0), P(-10, mid, bar), P(-10, mid - h, top), P(-10, mid - h, bar), P(-10, mid + h, bar), P(-10, mid + h, top)],
        away: [P(110 + GP3_POST.back, mid, 0), P(110, mid, bar), P(110, mid - h, top), P(110, mid - h, bar), P(110, mid + h, bar), P(110, mid + h, top)] }};
    """)
    if got is None:
        return
    p = got["post"]
    assert abs(p["bar"] - 10 / 3) < 1e-9 and abs(p["half"] * 2 - 18.5 / 3) < 1e-9 and abs(p["up"] - 35 / 3) < 1e-9 and p["back"] == 2, \
        "the crossbar ten feet up, 18 1/2 feet wide, the uprights 35 feet above it, the base 2 yards back (NFL rule 1, section 2)"
    assert len(got["posts"]) == 2, "one at each end"
    for d, want in zip(got["posts"], (got["home"], got["away"])):
        base, neck, *frame = want
        assert d.startswith(f"M{base}L"), ("the post rises from its base behind the end line", d[:40], base)
        assert f"L{neck}M" in d, ("the gooseneck reaches the end line at the crossbar", neck)
        assert d.endswith(f"M{frame[0]}L{frame[1]}L{frame[2]}L{frame[3]}"), ("the uprights and the crossbar over the end line", d[-90:])


def test_the_paint_reads_the_way_a_fields_does():
    got = _node(f"""
      const svg = gpField3dSVG({json.dumps(MIN_AT_DET)}, {{ home: "DET", away: "MIN" }}, "nfl");
      const mats = (cls) => [...svg.matchAll(new RegExp(`<text class="${{cls}}" transform="matrix\\\\(([^)]+)\\\\)"[^>]*>([^<]*)</text>`, "g"))]
        .map((m) => [m[1].split(" ").map(Number), m[2]]);
      return {{ ez: mats("gp3-ezt"), near: mats("gp3-num"), far: mats("gp3-num far") }};
    """)
    if got is None:
        return
    letters = "".join(t for _, t in got["ez"])
    assert letters == "LIONSVIKINGS", letters
    # A letter's top is minus its matrix's second column: toward each zone's end line.
    for (a, b, c, d, e, f), t in got["ez"][:5]:
        assert c > 0.5 and abs(d) < 1e-6, ("home's letters' tops toward its end line, on the left", t, c, d)
    for (a, b, c, d, e, f), t in got["ez"][5:]:
        assert c < -0.5 and abs(d) < 1e-6, ("away's toward its end line, on the right", t, c, d)
    # Home's name reads up the field from the near sideline, away's down it.
    ys = [m[5] for m, _ in got["ez"]]
    assert ys[:5] == sorted(ys[:5], reverse=True) and ys[5:] == sorted(ys[5:]), ys
    assert len(got["near"]) == 18 and len(got["far"]) == 18, "10 to 50 to 10 along both sidelines, two digits each"
    assert all(m[3] > 0 for m, _ in got["near"]), "the near numbers stand upright to the camera"
    assert all(m[3] < 0 for m, _ in got["far"]), "the far ones read from the far sideline"
    assert [t for _, t in got["near"]][:4] == ["1", "0", "2", "0"] and [t for _, t in got["near"]][8:10] == ["5", "0"]


def test_the_lines_the_drive_and_the_ball_sit_on_their_spots():
    got = _node(f"""
      const P = (x, y) => gp3(x, y).map((v) => v.toFixed(1)).join(" ");
      const m = {json.dumps(MIN_AT_DET)}, svg = gpField3dSVG(m, {{ home: "DET", away: "MIN" }}, "nfl");
      const goal = gpField3dSVG({{ ...m, los: 4, gain: 0, goal: true, start: null }}, {{ home: "DET", away: "MIN" }}, "nfl");
      const d = (cls, s) => ((new RegExp(`<path class="${{cls}}"[^>]*d="([^"]+)"`)).exec(s) || [])[1] || "";
      const box = GP3_BOX, pts = [gp3(-14, -4, -2.5), gp3(114, -4, -2.5), gp3(-14, GP3_W + 4), gp3(114, GP3_W + 4),
        gp3(-12, GP3_W / 2 - GP3_POST.half, GP3_POST.bar + GP3_POST.up), gp3(112, GP3_W / 2 + GP3_POST.half, GP3_POST.bar + GP3_POST.up)];
      return {{ los: d("gp3-los", svg), gain: d("gp3-gain", svg), drive: d("gp3-drive", svg),
        want: {{ los: P(24.7, 0), gain: P(19.7, 0), drive: P(25, GP3_W / 2 - 2.6) }},
        goalGain: goal.includes('class="gp3-gain"'), goalDrive: goal.includes("gp3-drive"),
        inside: pts.every(([x, y]) => x >= box.x0 && x <= box.x0 + box.w && y >= box.y0 && y <= box.y0 + box.h),
        view: (/viewBox="([^"]+)"/.exec(svg) || [])[1], logo: /<image class="gp3-logo" href="https:\\/\\/logo.test\\/nfl\\/DET.png"/.test(svg),
        named: /aria-label="4th &amp; 5 · DET 25 — MIN has the ball, the line to gain in yellow"/.test(svg) }};
    """)
    if got is None:
        return
    assert got["los"].startswith(f"M{got['want']['los']}L"), ("the line of scrimmage on the 25", got["los"][:30])
    assert got["gain"].startswith(f"M{got['want']['gain']}L"), ("the line to gain on the 20", got["gain"][:30])
    assert got["drive"].startswith(f"M{got['want']['drive']}L"), ("the drive runs from the ball back to where it began", got["drive"][:30])
    assert not got["goalGain"], "goal to go: the goal line is the line to gain, no yellow line of its own"
    assert not got["goalDrive"], "no drive on file, no ribbon"
    assert got["inside"], "every corner of the slab and the tops of both posts inside the picture"
    assert got["logo"], "the home club's mark at midfield"
    assert got["named"], "the picture says it in words"


def test_the_page_draws_the_3d_field_and_keeps_the_flat_one_for_the_bar():
    page = DETAIL[DETAIL.index("function gpFieldHTML("):]
    page = page[:page.index("\n}\n")]
    assert "${gpField3dSVG(m, d, league)}${drive}" in page
    compact = DETAIL[DETAIL.index("function gpCompactHTML("):]
    assert "gpFieldSVG(m, d, true)" in compact[:compact.index("\n}\n")], "the bar at the top of the screen keeps the flat strip"
    for rule in (".gp3-ez.home { fill: var(--wh); }", ".gp3-ez.away { fill: var(--wa); }",
                 ".gp3-los { fill: var(--gp-los); }", ".gp3-gain { fill: var(--gp-gain); }",
                 ".gp3-fade { stop-color: color-mix(in oklab, var(--off), white 22%); }"):
        assert rule in CSS, rule


def test_in_a_browser_the_field_stands_under_the_score_at_390_and_1280():
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
    fb = LIVE._fb_doc()
    fb["event_id"] = "e9"
    strip = {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": fb["live"], "plays_state": "ok"}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_e9.json*", serve(fb))
                    page.route("**/data/live_nfl.json*", serve(strip))
                    page.goto(f"http://127.0.0.1:{port}/#pbp/nfl/e9", wait_until="load")
                    page.wait_for_selector(".gp-field svg.gp3", timeout=15000)
                    got = page.evaluate("""(() => {
                      const svg = document.querySelector('.gp-field svg.gp3'), r = svg.getBoundingClientRect();
                      const n = (s) => svg.querySelectorAll(s).length;
                      const fill = (s) => getComputedStyle(svg.querySelector(s)).fill;
                      return { w: r.width, h: r.height, vw: innerWidth, posts: n('.gp3-post'), pads: n('.gp3-pad'),
                               zones: n('.gp3-ez'), los: n('.gp3-los'), gain: n('.gp3-gain'), ball: n('.gp3-ball'),
                               home: fill('.gp3-ez.home'), away: fill('.gp3-ez.away'), mow: fill('.gp3-mow'),
                               words: (document.querySelector('.gp-fd-words') || {}).textContent || '',
                               mini: document.querySelectorAll('.gp-c-field svg.gp-fd.mini').length };
                    })()""")
                    assert got["posts"] == 2 and got["pads"] == 2 and got["zones"] == 2, got
                    assert got["los"] == 1 and got["gain"] == 1 and got["ball"] == 1, got
                    assert got["w"] <= got["vw"] and got["h"] > (70 if width < 600 else 120), ("on the page, big enough to read", got)
                    assert got["home"] != got["away"] and got["mow"].startswith("rgb(52"), ("the clubs' end zones, the mown turf", got)
                    assert got["words"].startswith("3rd & 8"), got["words"]
                    assert got["mini"] == 1, "the bar's flat strip"
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
