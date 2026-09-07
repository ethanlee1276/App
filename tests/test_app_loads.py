"""Does app.js actually run? Not "does it parse" — does it RUN.

WHY THIS IS SEPARATE FROM `node --check`. On 2026-08-21 a new top-level
`const REFUND_DAYS` was added below the `FAQ` array that reads it. That is
perfectly valid syntax; `node --check` passes; every other test in this
suite passes, because they all read app.js as TEXT. In a browser it throws
`ReferenceError: Cannot access 'REFUND_DAYS' before initialization` at
module-evaluation time, which aborts the whole script — so `state`,
`load()`, the router and every render function never come into existence
and the site is a blank page.

Caught by opening it in a real browser, which is the only reason it was
caught at all. A blank page is the loudest possible failure and the
quietest possible test result.

WHAT THIS DOES. It evaluates app.js in Node with a stub `window` and
`document`, which is enough to get past the top-level declarations and the
one `(function(){...})()` at the bottom. It does NOT try to be a browser
and does not check any rendering. It answers one question: **does the file
survive being evaluated, and do the functions the site depends on exist
afterwards?**

The temporal dead zone is not the only thing it catches. A duplicate
`const`, a top-level throw, a typo'd identifier at module scope — all of
them are load-time aborts, and all of them look exactly like a syntax
error in the browser and exactly like nothing in this suite.

    python3 tests/test_app_loads.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")

#: Everything the site cannot start without. Each of these is reachable
#: only if evaluation got all the way to the bottom of the file.
REQUIRED = [
    "paywallHTML", "checkoutHTML", "renderPaywall", "renderCheckout",
    "paywallCheck", "paidReturnWait", "codeBoxHTML", "billPlansHTML",
    "extLink", "brandMarkHTML", "iconMark", "escapeHtml", "barLink",
]

#: Top-level constants the pages read. A missing one is a page that
#: renders `undefined` where a price should be.
#: REFUND_DAYS was here for one commit and is gone — Ethan withdrew the
#: money-back guarantee on 2026-08-21, and this test caught the removal,
#: which is what it is for. DISCORD_INVITE is deliberately NOT here: the
#: invite is served by the API to entitled callers only, so a constant by
#: that name in the bundle would be the bug rather than the feature.
REQUIRED_VALUES = ["PLANS", "PLAN_FEATURES", "PLAN_EXTRAS", "FAQ",
                   "PW_CARDS", "PW_SPORTS", "VIEW_ORDER",
                   "ICON_PATHS", "EXTERNAL_MARKET_LINKS"]

HARNESS = r"""
// The smallest stub that lets a browser script finish evaluating. Not a
// DOM: anything that actually needs one is called from an event, and
// events do not fire here.
const noop = () => {};
// A proxy so any property access answers with SOMETHING. The named keys
// below are the ones whose TYPE matters: code does
// `.querySelectorAll(x).forEach(...)`, and a bare `noop` there is a
// function where an array is expected — a TypeError that looks like a
// real defect and is only the stub being too thin.
const el = new Proxy({}, {
  get(t, k) {
    switch (k) {
      case "classList": return { add: noop, remove: noop, toggle: noop,
                                 contains: () => false };
      case "style": return {};
      case "dataset": return {};
      case "children": return [];
      case "childNodes": return [];
      case "options": return [];
      case "files": return [];
      case "textContent": case "innerHTML": case "innerText":
      case "value": case "id": case "className": return "";
      case "checked": case "disabled": case "hidden": return false;
      case "offsetWidth": case "offsetHeight":
      case "scrollTop": case "scrollHeight": return 0;
      case "querySelectorAll": return () => [];
      case "querySelector": case "closest": case "appendChild":
      case "cloneNode": case "insertBefore": return () => el;
      case "contains": return () => false;
      case "getBoundingClientRect":
        return () => ({ top: 0, left: 0, right: 0, bottom: 0,
                        width: 0, height: 0, x: 0, y: 0 });
      case "getAttribute": return () => null;
      case "parentNode": case "parentElement":
      case "firstChild": case "nextElementSibling": return null;
      default:
        if (typeof k === "symbol") return undefined;
        return noop;
    }
  },
  set() { return true; },
});
globalThis.document = {
  // AN ELEMENT, NOT null. The boot block does
  // `getElementById(x).addEventListener(...)` in several places, which is
  // correct in a browser where the element is in index.html and a
  // TypeError here. Returning the stub lets evaluation finish, which is
  // the only thing this file measures — it is not pretending to render.
  getElementById: () => el, querySelector: () => el,
  querySelectorAll: () => [], createElement: () => el,
  createElementNS: () => el, createTextNode: () => el,
  addEventListener: noop, removeEventListener: noop,
  documentElement: el, body: el, head: el, cookie: "",
  readyState: "complete", visibilityState: "visible",
  startViewTransition: undefined,
};
// THE HASH IS AN ARGUMENT. With no hash the boot block's router returns
// before it switches a view, and the view switch is exactly the code
// that runs during boot and nowhere else in this file — so a `const`
// declared below it and read by it (2026-09-06, NO_TOUR_VIEWS: every
// load of the live site failed with "before initialization") passed
// this file's empty-hash boot and took the site down for anyone landing
// on a tab. A landing on a tab is the common case, not the edge.
globalThis.location = { search: "", hash: process.argv[5] || "", href: "http://localhost/",
                        pathname: "/", origin: "http://localhost",
                        reload: noop, replace: noop, assign: noop };
globalThis.history = { replaceState: noop, pushState: noop };
globalThis.localStorage = { getItem: () => null, setItem: noop,
                            removeItem: noop };
globalThis.sessionStorage = globalThis.localStorage;
globalThis.navigator = { userAgent: "node", language: "en-US",
                         serviceWorker: undefined, onLine: true };
globalThis.matchMedia = () => ({ matches: false, addEventListener: noop,
                                 addListener: noop });
globalThis.addEventListener = noop;
globalThis.removeEventListener = noop;
globalThis.requestAnimationFrame = noop;
globalThis.fetch = () => new Promise(() => {});      // never resolves
globalThis.scrollTo = noop;
globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });
globalThis.IntersectionObserver = class { observe(){} disconnect(){} };
globalThis.ResizeObserver = globalThis.IntersectionObserver;
globalThis.window = globalThis;

const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const out = { ok: false, error: null, missing: [], missingValues: [] };
// WHAT THE PAGE LOADS FIRST. index.html puts visuals.js ahead of app.js
// and app.js calls into it (escapeAttr, the venue art) — from the
// checkout view's render, among others, which a `#checkout` landing runs
// during boot. Loaded here in the same context so a tab boot fails for
// a fault on the site and not for a helper the page had all along.
for (const pre of JSON.parse(process.argv[6] || "[]")) {
  vm.runInThisContext(fs.readFileSync(pre, "utf8"), { filename: pre });
}
try {
  // Same context, so top-level `const` really is top-level — running it
  // inside a function would hoist differently and hide the exact bug
  // this file exists for.
  vm.runInThisContext(src, { filename: "app.js" });
  out.ok = true;
} catch (e) {
  // MESSAGE FIRST, then the stack. V8 puts the offending SOURCE LINE at
  // the top of a stack and the actual message four lines down, so a
  // naive head-of-stack loses the one word that says what went wrong.
  const msg = String((e && e.message) || e);
  const stack = String((e && e.stack) || "").split("\n").slice(0, 3).join(" | ");
  out.error = msg + "  [" + stack + "]";
}
if (out.ok) {
  for (const name of JSON.parse(process.argv[3])) {
    if (typeof globalThis[name] !== "function") out.missing.push(name);
  }
  // A TOP-LEVEL `const` IS NOT A PROPERTY OF globalThis. That is correct
  // ES semantics — only `var` and function declarations go there — so
  // reading globalThis.PLANS reports every constant in the file as
  // missing. They have to be looked up by evaluating an expression in
  // the SAME context the script ran in.
  for (const name of JSON.parse(process.argv[4])) {
    let seen;
    try { seen = vm.runInThisContext(`typeof ${name}`); }
    catch (e) { seen = "undefined"; }
    if (seen === "undefined") out.missingValues.push(name);
  }
}
console.log(JSON.stringify(out));
// EXIT, do not fall off the end. The app's boot block starts intervals
// (the live loop, the clock), and a pending timer keeps Node's event loop
// alive for ever — the check would pass and then hang, which reads as a
// broken test rather than a working one.
process.exit(0);
"""


#: Scripts index.html loads before app.js that app.js calls into.
PRELUDE = [os.path.join(ROOT, "web", "js", "visuals.js")]


def _run(hash_="", path=None):
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, "harness.js")
        with open(harness, "w", encoding="utf-8") as fh:
            fh.write(HARNESS)
        proc = subprocess.run(
            [NODE, harness, path or os.path.join(ROOT, "web", "js", "app.js"),
             json.dumps(REQUIRED), json.dumps(REQUIRED_VALUES), hash_,
             json.dumps([p for p in PRELUDE if os.path.isfile(p)])],
            capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(
            "the harness itself failed:\n" + (proc.stderr or "")[:1500])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_app_js_evaluates_without_throwing():
    """THE ONE THAT MATTERS. A throw here is a blank site."""
    got = _run()
    assert got["ok"], (
        "app.js throws while being evaluated, which in a browser means "
        "NOTHING on the site runs — not a broken feature, a blank page:\n  "
        + str(got["error"]))


def test_every_function_the_pages_need_exists_afterwards():
    """Evaluation reaching the end is necessary and not sufficient — a
    function defined inside a block that never executed is still
    missing."""
    got = _run()
    assert got["ok"], got["error"]
    assert not got["missing"], \
        f"these are referenced by the pages and do not exist: {got['missing']}"


def test_every_top_level_constant_the_pages_read_exists():
    got = _run()
    assert got["ok"], got["error"]
    assert not got["missingValues"], \
        f"missing top-level constants: {got['missingValues']}"


def test_a_constant_used_before_its_declaration_is_caught():
    """The negative check, because a green test that cannot fail is worse
    than no test. Injects the exact shape of the 2026-08-21 bug — a
    top-level array reading a `const` declared below it — and requires
    the harness to reject it.
    """
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
        src = fh.read()
    broken = "const _tdzProbe = [_tdzValue];\nconst _tdzValue = 1;\n" + src
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, "harness.js")
        target = os.path.join(tmp, "app.js")
        with open(harness, "w", encoding="utf-8") as fh:
            fh.write(HARNESS)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(broken)
        proc = subprocess.run([NODE, harness, target, "[]", "[]"],
                              capture_output=True, text=True, timeout=120)
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not got["ok"], \
        "the harness accepted a temporal-dead-zone error, so it would " \
        "have accepted the real one"
    assert "before initialization" in str(got["error"]), got["error"]


def _view_order():
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("const VIEW_ORDER = [")
    body = src[i:src.index("];", i)]
    return re.findall(r'"([a-z_]+)"', body)


def test_a_landing_on_every_tab_boots():
    """The 2026-09-06 outage, generalised. `#live` in the address bar —
    the app's own bottom bar puts it there — makes the boot block's
    router call the view switch before the file has finished
    evaluating, so everything the switch reads must already exist. Boots
    once per view in VIEW_ORDER, eight at a time."""
    from concurrent.futures import ThreadPoolExecutor
    views = _view_order()
    assert len(views) >= 10, views
    with ThreadPoolExecutor(max_workers=8) as pool:
        got = dict(zip(views, pool.map(lambda v: _run("#" + v), views)))
    bad = {v: r["error"] for v, r in got.items() if not r["ok"]}
    assert not bad, "a landing on these tabs throws during boot — a blank site for " \
        "anyone whose address bar carries the tab:\n  " + "\n  ".join(f"#{v}: {e}" for v, e in bad.items())


def test_a_constant_the_view_switch_reads_late_is_caught():
    """The negative for the tab landing: a `const` declared at the bottom
    of the file and read inside the view switch — the exact shape of
    NO_TOUR_VIEWS — must fail the `#live` boot and, because the empty
    hash never reaches the switch, pass the plain one. Both halves, or
    the new test is not measuring what the outage was."""
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as fh:
        src = fh.read()
    hook = "  state.view = name;\n"
    assert src.count(hook) == 1, "the view switch moved; re-anchor this probe"
    broken = src.replace(hook, "  state.view = name; void _tdzLateView;\n") \
        + "\nconst _tdzLateView = 1;\n"
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "app.js")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(broken)
        live = _run("#live", target)
        plain = _run("", target)
    assert not live["ok"] and "before initialization" in str(live["error"]), live
    assert plain["ok"], "the plain boot was supposed to miss this — that is the point of the tab boot"


def test_visuals_js_evaluates_too():
    """app.js is not the only script the page loads, and the same class
    of error in visuals.js is the same blank page."""
    path = os.path.join(ROOT, "web", "js", "visuals.js")
    if not os.path.isfile(path):
        return
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, "harness.js")
        with open(harness, "w", encoding="utf-8") as fh:
            fh.write(HARNESS)
        proc = subprocess.run([NODE, harness, path, "[]", "[]"],
                              capture_output=True, text=True, timeout=120)
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["ok"], "visuals.js throws on load: " + str(got["error"])


if __name__ == "__main__":
    if not NODE:
        # The runner reads this line and does not score the file zero.
        print("SKIP no node on this machine, so app.js cannot be evaluated")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
