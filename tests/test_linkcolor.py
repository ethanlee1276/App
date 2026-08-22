"""No link on this site renders in the browser's default blue.

Found 2026-08-19 by looking at `rendercheck.py`'s own screenshots — the
first thing the render harness caught, and it caught it by being looked
at rather than by measuring anything.

**28 links across the site rendered `rgb(0, 0, 238)`.** Not a wrong brand
colour: no colour at all. The stylesheet has no base `a` rule, so anything
a component did not style itself fell through to the user agent, and what
fell through was

  * the legal footer — on EVERY view, so it was on screen most of the time
  * both legal pages' "← Back to Qellys Books"
  * the 404 and maintenance pages' wordmark and quick links
  * the sign-in card's "Terms" and "Privacy Policy"

RENDER_SPEC.md's first translation rule is *"Colors and name: OURS — the
renders' blue accent maps to `--brand`."* A raw user-agent blue is that
rule failing in the most literal way available.

**Why not a base `a { color }`.** Several links are deliberately
text-coloured because they are not link-shaped: the masthead wordmark, the
four Quick Tools doors. They INHERIT rather than set, so a base rule would
repaint all of them violet — a bigger regression than the bug. The fix
names the places the default was actually reaching; this file sweeps for
the next one.

Measured: **28 → 0**, over five pages and ten in-app views.

BROWSER HALVES ARE OPT-IN. Set `QB_BROWSER_TESTS=1` to run them.

They are skipped by default and the reason is a measured one: three
Chromium-driving tests inside a 284-file suite crashed the browser
("Page crashed" mid-navigation) on a container already busy running
everything else. A flaky test is worse than no test — the first false
alarm is what teaches you to skip the real one — and these particular
assertions have a better home anyway:

    QB_BROWSER_TESTS=1 python3 tests/test_linkcolor.py
    python3 launch.py --renders

The halves that need no browser still run on every commit, and they are
the ones that catch the drift class this exists for.

Run directly: `python3 tests/test_linkcolor.py`
"""

import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

#: What a user agent paints an unstyled anchor. The third is :visited,
#: which is a different default and just as wrong.
DEFAULT_BLUE = ("rgb(0, 0, 238)", "rgb(0, 0, 255)", "rgb(85, 26, 139)")


# --- the fix is where the defect was ----------------------------------------
def test_the_homes_the_default_was_reaching_are_all_coloured():
    """`.pw-legal a` joined the list on 2026-08-22 and by the same route:
    looking at a screenshot. The paywall and CHECKOUT pages did not exist
    when this file was written, and the legal line they both draw carries
    the Terms and Privacy links — rendering at #0000EE under the button
    where somebody enters a card, which is the worst place on the site for
    the default to surface.

    That is the second time this class has appeared, and it is worth being
    clear about why the answer is still not a base `a` rule: the next test
    holds. Naming each home costs a line per surface; a base rule would
    silently repaint the ones that inherit on purpose."""
    for sel in (".footer a", ".legal-back a", ".acct-confirm a",
                ".stub-brand", ".pw-legal a"):
        assert sel in DECLS, f"{sel} lost its colour again"


def test_it_was_not_fixed_with_a_base_rule():
    """A bare `a { color: … }` would repaint the masthead wordmark and the
    Quick Tools doors, which are cards that happen to be anchors and
    inherit their colour on purpose."""
    bad = re.findall(r"(?:^|[},])\s*a\s*\{[^}]*\bcolor\s*:", DECLS)
    assert not bad, f"a base anchor colour rule would repaint card links: {bad}"


# --- the sweep, when there is a browser -------------------------------------
_SWEEP = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const BLUE = new Set(JSON.parse(process.argv[3]));
const PAGES = ["index.html","terms.html","privacy.html","404.html","maintenance.html"];
const VIEWS = ['[data-view="alerts"]','[data-sport="intel"]','[data-sport="fantasy"]',
               '[data-sport="mybets"]','#nav-acct','[data-sport="about"]',
               '[data-sport="why"]','[data-sport="record"]','[data-view="scanner"]',
               '[data-view="futures"]'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const hits = [];
async function scan(p, where) {
  const rows = await p.evaluate(() => [...document.querySelectorAll("a")]
    .filter(a => a.offsetParent !== null)
    .map(a => ({ t: (a.textContent || "").trim().slice(0, 40),
                 c: getComputedStyle(a).color })));
  for (const r of rows) if (BLUE.has(r.c)) hits.push(`${where}: ${r.t}`);
}
for (const page of PAGES) {
  const p = await b.newPage({ viewport: { width: 1280, height: 1100 } });
  await p.goto(`http://127.0.0.1:${PORT}/${page}`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(1100);
  await scan(p, page);
  if (page === "index.html") for (const v of VIEWS) {
    const ok = await p.evaluate((s) => {
      const e = document.querySelector(s); if (!e) return false; e.click(); return true; }, v);
    if (!ok) continue;
    await p.waitForTimeout(800);
    await scan(p, "index " + v);
  }
  await p.close();
}
console.log(JSON.stringify(hits));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(
            ["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
            capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def test_no_rendered_link_is_the_browser_default():
    """The measurement itself, over five pages and ten in-app views.

    Skipped with a reason rather than failed when Node or Playwright is
    absent — the contract `launch.py --check`'s sweep already uses. A test
    that fails on a machine without a browser is a test people delete."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1, or run "
              "`python3 launch.py --renders`)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return

    import json

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=os.path.join(ROOT, "web"), **kw)

        def log_message(self, *a, **kw):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=ROOT) as fh:
            fh.write(_SWEEP)
            script = fh.name
        proc = subprocess.run(
            ["node", script, str(port), json.dumps(list(DEFAULT_BLUE))],
            cwd=ROOT, capture_output=True, text=True, timeout=240)
    finally:
        srv.shutdown()
        if script:
            Path(script).unlink(missing_ok=True)

    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("[")]
    assert lines, ("the sweep produced no output — "
                   + (proc.stderr or "")[:200])
    hits = json.loads(lines[-1])
    assert not hits, f"{len(hits)} link(s) still browser-default: {hits[:6]}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
