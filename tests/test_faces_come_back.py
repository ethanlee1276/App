"""A headshot that misses once comes back; one that loaded never flickers.

Ethan, 2026-11-02, the "Who could shine" list drawn in helmets where the
faces had been: "after being on the site for a while, the headshots will
disappear". Every face is an <img> over a drawn mark (visuals.js
playerAvatar, the pick page's tile, the live pages' faces), and two things
took faces away for good:

  * a miss was final — the small face failed, the whole one failed, the
    photo removed itself, and nothing put it back until its card happened
    to be redrawn. A connection dropping as the phone wakes or changes
    networks takes every face it touches at once;
  * every redraw (the board's 30-second poll) put a fresh lazy image in
    every frame, the mark showing until it loaded, and iOS's lazy loader can
    leave such an image never asked for (WebKit bug 237703).

These hold (visuals.js FACES COME BACK):

  * a face that has loaded this visit is drawn already up on a redraw — its
    frame wears art-on and the image is eager — at the URL that worked;
  * a face that misses waits hidden with the mark showing, and is asked for
    again when the connection comes back; after FACE_TRIES_MAX misses it
    rests: no more asks on a timer, one each time the page comes back to
    the screen, and the connection coming back wipes its misses and asks
    again;
    any image that is not a face keeps its old rule;
  * the sweep nudges a lazy face on screen that never finished, parks one
    on screen that finished broken, and leaves one far below the screen
    alone;
  * every place that draws a face goes through faceImg.

Run directly: `python3 tests/test_faces_come_back.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
VIS = READ("web", "js", "visuals.js")
FACE = "https://static.www.nfl.com/image/upload/f_auto,q_auto/league/"


def _node(body: str):
    """Run `body` against visuals.js in a bare context (no page, no timers),
    returning what it prints as JSON; None without node."""
    node = shutil.which("node")
    if not node:
        return None
    prog = ("const vm = require('vm'); const fs = require('fs');\n"
            f"const src = fs.readFileSync({json.dumps(str(ROOT / 'web' / 'js' / 'visuals.js'))}, 'utf8');\n"
            "const ctx = { console, Math, String, Number, JSON, Map, Set, Object, Array, RegExp,\n"
            "  window: {}, document: { addEventListener() {}, querySelectorAll() { return []; } } };\n"
            "vm.createContext(ctx);\n"
            "vm.runInContext(src + '\\n;globalThis.T = { playerAvatar, faceImg, faceUp, facePark, IMG_ERR, FACE_UP, FACE_USE, FACE_MISS, FACE_TRIES_MAX, faceOnline };', ctx);\n"
            "const T = ctx.T;\n" + body)
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_face_loaded_this_visit_is_drawn_up_and_eager():
    got = _node(f"""
      const full = {json.dumps(FACE + 'abc')};
      const cold = T.playerAvatar("Jaxon Smith-Njigba", "SEA", {{ size: 36, headshot: full }});
      const small = (cold.match(/data-face="([^"]+)"/) || [])[1];
      T.FACE_UP.add(small);
      const warm = T.playerAvatar("Jaxon Smith-Njigba", "SEA", {{ size: 36, headshot: full }});
      // The small one missed this visit and the whole one loaded: redraws use the whole one.
      T.FACE_UP.clear();
      T.faceUp({{ getAttribute: () => full, dataset: {{ face: small }}, hidden: true }});
      const whole = T.faceImg(small, full);
      process.stdout.write(JSON.stringify({{ cold, warm, small, whole }}));
    """)
    if got is None:
        return
    cold, warm = got["cold"], got["warm"]
    assert got["small"] and "w_72" in got["small"], got["small"]
    assert '<span class="avatar-stack" ' in cold and 'loading="lazy"' in cold and "data-full=" in cold, cold
    assert 'data-onload="art-on"' in cold and 'data-onerr="swapFull"' in cold
    assert '<span class="avatar-stack art-on" ' in warm, "up at once: no helmet between redraws"
    assert 'loading="lazy"' not in warm, "eager: the browser has it"
    assert got["whole"]["up"] and f'src="{FACE}abc"' in got["whole"]["attrs"] and "data-full" not in got["whole"]["attrs"]


def test_a_face_that_misses_waits_and_anything_else_goes():
    got = _node("""
      const mk = (face) => {
        const el = { removed: false, hidden: false, attrs: { src: "https://x.test/a.png" }, dataset: {},
                     parentNode: { classList: { removed: [], remove(c) { this.removed.push(c); } } },
                     getAttribute(k) { return this.attrs[k]; }, remove() { this.removed = true; },
                     removeAttribute(k) { delete this.dataset[k.replace(/^data-/, "")]; } };
        if (face) el.dataset.face = "https://x.test/a.png";
        return el;
      };
      const logo = mk(false); T.IMG_ERR.remove(logo);
      const face = mk(true); T.IMG_ERR.remove(face);
      const out = { logo: logo.removed, face: [face.removed, face.hidden, face.dataset.parked, face.parentNode.classList.removed] };
      // Past the tries: resting, the mark showing, no longer waiting on a timer.
      const last = mk(true);
      for (let i = 1; i < T.FACE_TRIES_MAX; i++) T.facePark(last);
      out.last = [last.removed, last.hidden, last.dataset.rested, last.dataset.parked === undefined,
                  T.FACE_MISS.get("https://x.test/a.png")];
      // The connection back: the misses while it was gone do not count.
      T.faceOnline();
      out.online = T.FACE_MISS.size;
      // A whole photo to fall back on first, then the wait.
      const two = mk(true); two.dataset.full = "https://x.test/whole.png";
      T.IMG_ERR.swapFull(two);
      out.two = [two.src, two.dataset.full === undefined, two.hidden];
      process.stdout.write(JSON.stringify(out));
    """)
    if got is None:
        return
    assert got["logo"] is True, "a logo that misses goes, as before"
    assert got["face"] == [False, True, "https://x.test/a.png", ["art-on"]], got["face"]
    assert got["last"][:4] == [False, True, "https://x.test/a.png", True] and got["last"][4] >= 4, got["last"]
    assert got["online"] == 0, "the connection back wipes the slate"
    assert got["two"] == ["https://x.test/whole.png", True, False], got["two"]


def test_every_place_that_draws_a_face_goes_through_faceImg():
    assert "const f = faceImg(small, opts.headshot);" in VIS, "the avatar"
    app = READ("web", "js", "app.js")
    tile = app[app.index("function playerTileHTML("):]
    tile = tile[:tile.index("\n}\n")]
    assert "faceImg(s, h, { lazy: false })" in tile and 'class="ptile${f && f.up ? " art-on" : ""}"' in tile
    for name, needle in (("gamecast.js", "faceImg(small, src).attrs"), ("hoopscast.js", "faceImg(small, src).attrs"),
                         ("rinkcast.js", "faceImg(src, src).attrs")):
        assert needle in READ("web", "js", name), name
    assert 'addEventListener("online", faceOnline);' in VIS
    assert 'if (document.visibilityState === "visible") { faceRetry(true); faceSweep(); }' in VIS
    assert 'addEventListener("pageshow", () => { faceRetry(true); faceSweep(); });' in VIS
    assert "if (el && el.dataset && el.dataset.face !== undefined) faceUp(el);" in VIS


PAGE = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="{base}/css/styles.css"><body style="margin:0">
<div id="a"></div><div id="b"></div><div id="c"></div><div id="d"></div><div id="e"></div>
<div style="height:4000px"></div><div id="far"></div>
<script src="{base}/js/visuals.js"></script></body>"""
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082")


def test_in_a_browser_a_face_that_missed_comes_back():
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
    base = f"http://127.0.0.1:{port}"
    host = {"up": True, "hang": False}
    got, errors, hung = {}, [], []

    asked = []

    def face(route):
        asked.append(route.request.url)
        if host["hang"]:
            hung.append(route)                       # never answered: in flight for good
            return
        if host["up"]:
            route.fulfill(status=200, content_type="image/png", body=PNG)
        else:
            route.abort()

    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            page = None
            try:
                page = browser.new_page(viewport={"width": 390, "height": 800})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("https://static.www.nfl.com/**", face)
                # A blank page (no content policy of ours to refuse the
                # test's own evaluations) with the real visuals.js.
                page.set_content(PAGE.format(base=base), wait_until="load")
                draw = """([id, url]) => { document.getElementById(id).innerHTML =
                  playerAvatar("A Player", "SEA", { size: 36, headshot: url }); }"""
                state = """(id) => { const f = document.querySelector('#' + id + ' .avatar-stack');
                  const i = f && f.querySelector('img'); return { up: !!f && f.classList.contains('art-on'),
                  img: !!i, hidden: !!i && i.hidden, parked: !!i && i.hasAttribute('data-parked'),
                  rested: !!i && i.hasAttribute('data-rested'),
                  lazy: !!i && i.getAttribute('loading') === 'lazy',
                  mark: !!f && getComputedStyle(f.querySelector('svg.avatar')).display !== 'none' }; }"""
                # 1. A face loads; a redraw draws it up at once, eager.
                page.evaluate(draw, ["a", FACE + "one"])
                page.wait_for_function("document.querySelector('#a .avatar-stack.art-on')", timeout=10000)
                page.evaluate(draw, ["a", FACE + "one"])
                got["redrawn"] = page.evaluate(state, "a")
                # 2. The host drops: a new face misses twice (small, whole) and waits, the mark showing.
                host["up"] = False
                page.evaluate(draw, ["b", FACE + "two"])
                page.wait_for_function("document.querySelector('#b img[data-parked]')", timeout=10000)
                got["missed"] = page.evaluate(state, "b")
                # 3. The connection comes back: it is asked for again and comes up.
                host["up"] = True
                page.evaluate("dispatchEvent(new Event('online'))")
                page.wait_for_function("document.querySelector('#b .avatar-stack.art-on img:not([hidden])')", timeout=10000)
                got["back"] = page.evaluate(state, "b")
                # 4. A face that never comes: after FACE_TRIES_MAX misses it rests, the mark
                #    showing; a timed ask leaves it alone; the connection back asks again.
                host["up"] = False
                page.evaluate(draw, ["c", FACE + "three"])
                for _ in range(8):
                    page.wait_for_function("document.querySelector('#c img[data-parked], #c img[data-rested]')",
                                           timeout=10000)
                    if page.evaluate("!!document.querySelector('#c img[data-rested]')"):
                        break
                    page.evaluate("faceRetry()")
                got["rested"] = page.evaluate(state, "c")
                asks = len(asked)
                page.evaluate("faceRetry()")
                page.wait_for_timeout(300)
                got["rest_asks"] = len(asked) - asks
                # The page back on screen asks it once, and it rests again at once.
                page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow'))")
                page.wait_for_function("document.querySelector('#c img[data-rested]')", timeout=10000)
                page.wait_for_timeout(300)
                got["shown_asks"] = len(asked) - asks
                got["rested_again"] = page.evaluate(state, "c")
                host["up"] = True
                page.evaluate("dispatchEvent(new Event('online'))")
                page.wait_for_function("document.querySelector('#c .avatar-stack.art-on img:not([hidden])')", timeout=10000)
                got["woke"] = page.evaluate(state, "c")
                # 5. A lazy face on screen still in flight is nudged; one far below is not
                #    (neither nudged nor taken for broken).
                host["up"], host["hang"] = True, True
                page.evaluate(draw, ["d", FACE + "four"])
                page.evaluate(draw, ["far", FACE + "five"])
                page.evaluate("faceSweep()")
                got["sweep"] = page.evaluate("""() => [document.querySelector('#d img').loading,
                                                       document.querySelector('#far img').loading,
                                                       document.querySelector('#far img').hidden]""")
                # 6. A face on screen that ended broken with no error reaching the page
                #    (here: no handler on it) waits like any miss.
                host["up"], host["hang"] = False, False
                page.evaluate("""(url) => { document.getElementById('e').innerHTML =
                  '<span class="avatar-stack"><img class="avatar-photo" data-face="' + url + '" src="' + url
                  + '" alt="" style="width:36px;height:36px"></span>'; }""", FACE + "six")
                page.wait_for_function("document.querySelector('#e img').complete", timeout=10000)
                page.evaluate("faceSweep()")
                got["broken"] = page.evaluate("""() => { const i = document.querySelector('#e img');
                                                  return [i.hidden, i.dataset.parked || '']; }""")
            finally:
                # Answer everything before closing: the hung face, and the
                # whole photo it falls back to when let go.
                host.update(up=False, hang=False)
                for r in hung:
                    try:
                        r.abort()
                    except Exception:
                        pass
                if page is not None:
                    try:
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
    assert got["redrawn"]["up"] and not got["redrawn"]["lazy"] and not got["redrawn"]["mark"], got["redrawn"]
    assert got["missed"]["hidden"] and got["missed"]["parked"] and not got["missed"]["up"] and got["missed"]["mark"], \
        ("a miss waits out of sight, the helmet showing", got["missed"])
    assert got["back"]["up"] and not got["back"]["hidden"] and not got["back"]["parked"] and not got["back"]["mark"], \
        ("back with the connection, without a redraw", got["back"])
    r = got["rested"]
    assert r["img"] and r["hidden"] and r["rested"] and not r["parked"] and r["mark"], \
        ("resting after its tries, the helmet showing", r)
    assert got["rest_asks"] == 0, "a timed ask leaves a resting face alone"
    assert got["shown_asks"] == 1 and got["rested_again"]["rested"] and not got["rested_again"]["parked"], \
        ("the page back on screen asks a resting face once", got["shown_asks"], got["rested_again"])
    w = got["woke"]
    assert w["up"] and not w["hidden"] and not w["rested"] and not w["mark"], ("the connection back wakes it", w)
    assert got["sweep"] == ["eager", "lazy", False], got["sweep"]
    assert got["broken"] == [True, FACE + "six"], got["broken"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
