"""If it looks like a button, clicking it has to do something.

Ethan, 2026-08-20: "Do not leave fake buttons ... If something appears
interactive, it must behave like an interactive component."

STATIC ANALYSIS CANNOT ANSWER THIS QUESTION IN THIS CODEBASE, and the
first attempt proved it. A sweep for controls with no `onclick`, no
`href` and no `data-*` returned seven suspects — `nav-search`,
`nav-bell`, `nav-acct`, `theme-toggle`, `hcm-toggle`, `pz-toggle` and
`why-see-record`. Every one of them is wired, through
`addEventListener`, which no amount of reading attributes can see. A
100% false-positive rate is not a slow detector; it is the wrong
instrument.

So the test clicks. For each control it records the view's HTML length,
the hash, the title, the element's own aria state and class, arms a
MutationObserver over the whole document, clicks, waits, and asks whether
ANYTHING moved. A control that changes nothing observable is the fake
button the brief is about.

Measured 2026-08-20 over 23 views: **zero dead controls and zero page
errors**, from 80 controls actually clicked. That number is lower than it
looks and the reason matters — this container has no board data, so most
views draw their empty state and offer little to click. Coverage is
reported on every run for exactly that reason. One reported at first — `games-prev` —
and it was the probe's fault: `visibility: hidden` elements still have a
bounding box, so the sweep clicked an arrow the strip correctly hides at
its own left edge. The filter below checks computed visibility for
exactly that reason.

DESTRUCTIVE CONTROLS ARE SKIPPED BY NAME. Clicking every button on a page
includes clicking "delete". The skip list is deliberately broad — a
missed fake button is cheaper than a wiped ledger — and it is why this
cannot claim to have covered *every* control.

Opt in with QB_BROWSER_TESTS=1, for the reason test_proseflow.py records.

    QB_BROWSER_TESTS=1 python3 tests/test_deadcontrols.py

Run directly: `python3 tests/test_deadcontrols.py`
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PROBE = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;

const VIEWS = [['board',null],['scanner','[data-view="scanner"]'],['longshots','[data-view="longshots"]'],
  ['futures','[data-view="futures"]'],['edge','[data-view="edge"]'],['injuries','[data-view="injuries"]'],
  ['weather','[data-view="weather"]'],['players','[data-view="players"]'],['live','[data-view="live"]'],
  ['trending','[data-view="trending"]'],['rosters','[data-view="rosters"]'],['standings','[data-view="standings"]'],
  ['bankroll','[data-view="bankroll"]'],['alerts','[data-view="alerts"]'],['tonight','[data-view="tonight"]'],
  ['record','[data-sport="record"]'],['intel','[data-sport="intel"]'],['fantasy','[data-sport="fantasy"]'],
  ['memes','[data-sport="memes"]'],['mybets','[data-sport="mybets"]'],['lab','[data-sport="lab"]'],
  ['about','[data-sport="about"]'],['why','[data-sport="why"]']];
// A missed fake button is cheaper than a wiped ledger.
const SKIP = 'delete|remove|clear|sign out|log out|reset|cancel|unsubscribe|import|export|upload|save|submit|pay|upgrade';

const dead = [], errs = [], missing = [];
let clicked = 0;
for (const [view, sel] of VIEWS) {
  const p = await b.newPage({ viewport: { width: 1280, height: 1000 } });
  p.on('pageerror', e => errs.push({ view, msg: e.message.slice(0, 130) }));
  await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1800);
  if (sel) {
    const ok = await p.evaluate(s => { const e = document.querySelector(s);
                                       if (!e) return false; e.click(); return true; }, sel);
    if (!ok) { missing.push(view); await p.close(); continue; }
    await p.waitForTimeout(800);
  }
  const n = await p.evaluate((skipSrc) => {
    const SKIP = new RegExp(skipSrc, 'i');
    window.__ctl = [...document.querySelectorAll('main button, main [role=button]')]
      .filter(e => {
        const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
        // VISIBILITY, not just a box. A hidden strip arrow has a 36x36
        // rect and is not on screen — that false finding is why.
        return r.width > 3 && r.height > 3 && !e.disabled
               && cs.visibility !== 'hidden' && cs.display !== 'none'
               && parseFloat(cs.opacity) > 0.05
               && !SKIP.test((e.textContent || '') + ' ' + (e.id || ''));
      });
    return window.__ctl.length;
  }, SKIP);
  for (let i = 0; i < Math.min(n, 28); i++) {
    const res = await p.evaluate(async (idx) => {
      const el = window.__ctl[idx];
      if (!el || !el.isConnected) return null;
      const label = ((el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 34)
                     || el.id || el.className || 'BUTTON');
      const main = document.querySelector('main');
      const snap = (e) => ({ html: main ? main.innerHTML.length : 0, hash: location.hash,
                             title: document.title, cls: e.className,
                             aria: '' + e.getAttribute('aria-expanded') + e.getAttribute('aria-checked') });
      const before = snap(el);
      let mutated = 0;
      const obs = new MutationObserver(ms => { mutated += ms.length; });
      obs.observe(document.body, { subtree: true, childList: true,
                                   attributes: true, characterData: true });
      el.click();
      await new Promise(r => setTimeout(r, 380));
      obs.disconnect();
      const after = snap(el);
      const changed = mutated > 0 || JSON.stringify(before) !== JSON.stringify(after);
      return { label, changed };
    }, i);
    if (!res) continue;
    clicked++;
    if (!res.changed) dead.push({ view, label: res.label });
  }
  await p.close();
}
console.log(JSON.stringify({ dead, errs, missing, clicked }));
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


def test_no_control_on_any_view_is_a_fake_button():
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
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=ROOT) as fh:
            fh.write(_PROBE)
            script = fh.name
        proc = subprocess.run(["node", script, str(port)], cwd=ROOT,
                              capture_output=True, text=True, timeout=1500)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    # COVERAGE IS PART OF THE RESULT, the lesson rendercheck.py paid for.
    # This container has almost no data, so most boards draw their empty
    # state and there is little to click: 80 controls here against what a
    # fed droplet would offer. A green run is therefore evidence about
    # the controls that EXISTED, and the number says how much that is
    # worth. The floor below catches "the sweep broke", not "the board is
    # quiet".
    print(f"      ({out['clicked']} controls clicked across "
          f"{23 - len(out['missing'])} views)")
    assert out["clicked"] >= 40, \
        (f"only {out['clicked']} controls were reachable — the sweep is not "
         "covering the app any more, so a green result means nothing")
    assert not out["missing"], \
        f"these views could not be reached at all: {out['missing']}"
    assert not out["errs"], (
        "clicking raised page errors:\n  "
        + "\n  ".join(f"{e['view']}: {e['msg']}" for e in out["errs"][:8]))
    assert not out["dead"], (
        "these controls changed nothing observable when clicked — either "
        "they are fake, or they need a visibly disabled state so nobody "
        "taps them expecting a result:\n  "
        + "\n  ".join(f"{d['view']}: \"{d['label']}\"" for d in out["dead"]))


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
