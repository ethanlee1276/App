"""A new version of the app replaces the old copy on the phone — it never lives on.

2026-10-26, Ethan, a screenshot of the Live tab: "clicking any sport button
on this live page throws an error" — "mbLoad().some is not a function", the
My Bets clash fixed hours before. The box was serving the fix; his
installed app was still running the copy it kept. register-sw.js reloaded a
replaced page only "when hidden", and a phone freezes a page it puts away,
so that reload often never ran. What these hold (web/js/register-sw.js, and
app.js crashNote):

  - a new version that arrives before the reader's first touch (a launch,
    in practice) reloads the page at once;
  - after a touch, a pill says a new version is ready (a tap reloads), and
    the page still reloads when it is put away;
  - coming back to a replaced page reloads it; coming back is also a fresh
    start, so a version that lands before the next touch reloads at once;
  - the first worker ever is an install, not an update: no reload;
  - a render fault on a replaced page reloads instead of apologising, once,
    and the apology itself now has a Reload button.

    python3 tests/test_a_new_version_takes_over.py
"""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "web", "js", "register-sw.js")
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const steps = JSON.parse(process.argv[2]);
const on = { win: {}, doc: {}, sw: {} };
const add = (box) => (t, f) => { (box[t] = box[t] || []).push(f); };
const fire = (box, t) => (box[t] || []).forEach((f) => f({}));
const out = { reloads: 0, updates: 0, pill: null };
const made = [];
const ctx = {
  console, Date, Promise, setTimeout,
  location: { reload: () => { out.reloads++; } },
  matchMedia: () => ({ matches: false }),
  navigator: { standalone: false, serviceWorker: {
    controller: steps.controller ? {} : null,
    addEventListener: add(on.sw),
    register: () => Promise.resolve({ update: () => { out.updates++; } }),
    ready: Promise.resolve({ active: null }) } },
  document: {
    visibilityState: "visible",
    addEventListener: add(on.doc),
    getElementById: (id) => made.find((e) => e.id === id) || null,
    createElement: () => ({ listeners: {}, addEventListener(t, f) { this.listeners[t] = f; } }),
    body: { appendChild: (el) => { made.push(el); out.pill = el.textContent; } } },
};
ctx.window = ctx;
ctx.addEventListener = add(on.win);
vm.createContext(ctx);
vm.runInContext(src, ctx);
(async () => {
  fire(on.win, "load");
  await new Promise((r) => setTimeout(r, 0));
  for (const s of steps.do) {
    if (s === "touch") fire(on.win, "pointerdown");
    else if (s === "newversion") fire(on.sw, "controllerchange");
    else if (s === "hide") { ctx.document.visibilityState = "hidden"; fire(on.doc, "visibilitychange"); }
    else if (s === "show") { ctx.document.visibilityState = "visible"; fire(on.doc, "visibilitychange"); }
    else if (s === "tap") made[0].listeners.click();
    out[s + "_" + out.reloads] = true;
  }
  out.stale = !!ctx.QB_STALE;
  console.log(JSON.stringify(out));
})();
"""


def _run(do, controller=True):
    r = subprocess.run(["node", "-e", HARNESS, REG, json.dumps({"controller": controller, "do": do})],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_version_that_lands_before_the_first_touch_reloads_at_once():
    out = _run(["newversion"])
    assert out["reloads"] == 1 and out["stale"] and out["pill"] is None


def test_after_a_touch_a_pill_and_a_reload_when_put_away():
    out = _run(["touch", "newversion"])
    assert out["reloads"] == 0 and out["pill"] == "A new version is ready — tap to refresh"
    assert _run(["touch", "newversion", "hide"])["reloads"] == 1
    assert _run(["touch", "newversion", "tap"])["reloads"] == 1, "the pill reloads"


def test_coming_back_to_a_replaced_page_reloads_it():
    # A frozen page never ran its reload "when hidden": the return does it.
    out = _run(["touch", "newversion", "show"])
    assert out["reloads"] == 1


def test_coming_back_is_a_fresh_start():
    out = _run(["touch", "hide", "show", "newversion"])
    assert out["reloads"] == 1, "the version landed before the next touch"
    assert _run(["touch", "hide", "show", "touch", "newversion"])["reloads"] == 0


def test_the_first_worker_is_an_install_not_an_update():
    out = _run(["newversion"], controller=False)
    assert out["reloads"] == 0 and not out["stale"]


def test_one_reload_never_a_loop():
    out = _run(["newversion", "show", "hide", "show"])
    assert out["reloads"] == 1


def test_a_fault_on_a_replaced_page_reloads_and_the_apology_has_a_button():
    i = APP.index("function crashNote(what) {")
    body = APP[i:APP.index("\n}\n", i)]
    assert body.index("if (window.QB_STALE && !window._qbSkewReload)") < body.index("if (_crashSaid")
    assert '<button type="button" class="cn-reload">Reload</button>' in body
    assert 'el.querySelector(".cn-reload").addEventListener("click", () => location.reload());' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
