"""The Ask page with the keyboard up: the chat sits above the keys.

Ethan, 2026-09-23, a screenshot from his phone with the keyboard open —
the message box shoved up under the clock, a screen of nothing below it
and the tab bar floating over the keys: "Fix how every time I click on
the keyboard it makes the screen do this."

An iPhone does not shrink the page for its keyboard. It scrolls the page
to reach the focused box, and a fixed bar rides up with what is left of
the view; the room's old sizing then measured itself from where that
scroll had left it and grew taller still. What is pinned here:

  * while the box has focus and the visual viewport is short of the
    window by more than a keyboard's worth, body.ask-typing is on and the
    room is a FIXED layer set to the visual viewport's top and height —
    the conversation above, the box resting on the keys, the tab bar and
    riding tray out of the way;
  * it follows the visual viewport's resize AND scroll (iOS pans it), a
    redraw mid-typing re-applies it, and the moment the keyboard goes the
    room returns to the page and is measured the ordinary way;
  * leaving Ask can never strand the class on another page.

BROWSER HALF IS OPT-IN (`QB_BROWSER_TESTS=1`), as tests/test_phone_drawer.py
explains: it drives Chromium with a stand-in visual viewport shaped like an
iPhone's with the keyboard up, since no desktop browser raises a keyboard.

    QB_BROWSER_TESTS=1 python3 tests/test_ask_keyboard.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_room_takes_the_space_the_keyboard_leaves():
    kb = _fn("askKeyboard")
    assert "document.activeElement === input" in kb and "window.innerHeight - vv.height > 120" in kb, \
        "typing means the box has focus AND the view is a keyboard short"
    assert 'document.body.classList.toggle("ask-typing", up);' in kb
    assert "room.style.top = `${Math.round(vv.offsetTop)}px`;" in kb, "it follows iOS panning the view"
    assert "room.style.height = `${Math.floor(vv.height)}px`;" in kb, "exactly the part the keys leave"
    assert 'room.style.top = "";' in kb and "askRoomSize();" in kb[kb.index("} else if (was)"):], \
        "and goes back into the page when the keyboard does"
    rule = re.search(r"body\.ask-typing \.ask-room \{([^}]*)\}", CSS)
    assert rule and "position: fixed;" in rule.group(1) and "z-index: 62;" in rule.group(1)
    assert "env(safe-area-inset-top)" in rule.group(1), "clear of the clock on a home-screen app"
    assert "body.ask-typing .tabbar, body.ask-typing .riding-tray { display: none; }" in CSS


def test_it_listens_where_an_iphone_speaks():
    assert 'window.visualViewport.addEventListener("resize", () => { if (state.view === "ask") askKeyboard(); });' in APP
    assert 'window.visualViewport.addEventListener("scroll", () => { if (state.view === "ask") askKeyboard(); });' in APP
    r = _fn("renderAsk")
    assert 'input.addEventListener("focus", () => { askKeyboard(); setTimeout(askKeyboard, 350); });' in r
    assert 'input.addEventListener("blur", () => setTimeout(askKeyboard, 120));' in r
    assert r.index("askKeyboard();") < r.index("askRoomSize();"), "a redraw mid-typing keeps its place first"
    size = _fn("askRoomSize")
    assert 'document.body.classList.contains("ask-typing")) return;' in size, \
        "the ordinary sizing never fights the keyboard's"
    assert "vv.height" not in size, "and no longer measures itself against the keyboard at all"
    sw = _fn("_switchViewNow")
    assert 'if (name !== "ask") document.body.classList.remove("ask-typing");' in sw


_PROBE = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const p = await (await b.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })).newPage();
const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
await p.addInitScript(() => {
  try { localStorage.setItem('qb.tour', 'done'); } catch (e) {}
  const fake = new EventTarget();
  Object.assign(fake, { height: window.innerHeight, width: window.innerWidth, offsetTop: 0, offsetLeft: 0, scale: 1 });
  Object.defineProperty(window, 'visualViewport', { get: () => fake, configurable: true });
  window.__kb = (h, off) => { fake.height = h; fake.offsetTop = off;
    fake.dispatchEvent(new Event('resize')); fake.dispatchEvent(new Event('scroll')); };
});
await p.goto(`http://127.0.0.1:${PORT}/#ask`, { waitUntil: 'domcontentloaded' });
await p.waitForSelector('#ask-input', { timeout: 20000 });
await p.waitForTimeout(800);
const probe = () => p.evaluate(() => {
  const r = document.getElementById('ask-room').getBoundingClientRect();
  const f = document.getElementById('ask-form').getBoundingClientRect();
  return { typing: document.body.classList.contains('ask-typing'), top: Math.round(r.top), bottom: Math.round(r.bottom),
    page: Math.round(document.documentElement.getBoundingClientRect().height), screen: window.innerHeight,
    scroll: document.scrollingElement.scrollHeight - window.innerHeight,
    form: Math.round(f.bottom), tab: getComputedStyle(document.querySelector('.tabbar')).display,
    pos: getComputedStyle(document.getElementById('ask-room')).position };
});
const out = { before: await probe() };
await p.tap('#ask-input');
await p.evaluate(() => window.__kb(508, 0)); await p.waitForTimeout(400);
out.up = await probe();
await p.evaluate(() => window.__kb(508, 180)); await p.waitForTimeout(200);
out.panned = await probe();
await p.evaluate(() => { window.__kb(508, 0); document.getElementById('ask-input').blur(); window.__kb(844, 0); });
await p.waitForTimeout(400);
out.down = await probe();
out.errors = errs;
console.log(JSON.stringify(out));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
                           capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def test_with_an_iphones_keyboard_up_the_box_rests_on_the_keys():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    import rendercheck
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, dir=ROOT) as fh:
            fh.write(_PROBE)
            script = fh.name
        proc = subprocess.run(["node", script, str(port)], cwd=ROOT, capture_output=True, text=True, timeout=180)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    before = out["before"]
    assert before["pos"] == "static" and not before["typing"]
    assert before["page"] >= before["screen"] and before["scroll"] == 0, \
        f"the page must be a screen tall and not scroll — shorter, and his iPhone lifts the tab bar: {before}"
    up = out["up"]
    assert up["typing"] and up["pos"] == "fixed" and up["tab"] == "none", up
    assert (up["top"], up["bottom"]) == (0, 508), f"the room is not the part the keys leave: {up}"
    assert 490 <= up["form"] <= 508, f"the box is not resting on the keys: {up}"
    assert (out["panned"]["top"], out["panned"]["bottom"]) == (180, 688), "it did not follow the view"
    down = out["down"]
    assert not down["typing"] and down["pos"] == "static" and down["tab"] != "none", down
    assert not out["errors"], out["errors"]


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
