"""No sentence on the site is allowed to have a hole in it.

Ethan, 2026-08-26, was reading the schedule-only NFL board — the one the
site publishes every day between the schedule appearing and Week 1 being
played — and the parlay panel on it said:

    Screened undefined candidate tickets built from undefined eligible
    legs on tonight's board.

Nothing was broken enough to raise a page error, no test knew, and the
number of readers who would have reported it is one. It was found by
walking every page in every sport in a browser and looking for the word.

FOUR MARKS, because a render bug leaves one of four traces in the text
and all of them are cheap to look for:

    a HOLE          undefined / NaN / Infinity reached the glass
    a TEMPLATE      ${...} or }} that never interpolated
    an UNROUNDED    5.733333333333333 — a float nobody formatted
    a REPEAT        "SPREAD Spread" — a label printed beside itself

The last one is not hypothetical either: the game-bet chart's strip read
"SPREAD Spread" for a week, and it was caught by eye rather than by
anything that could catch it twice.

WHY A BROWSER AND NOT A GREP. Every one of these is produced by
INTERPOLATION — the template in the source is correct and the value
handed to it is not — so the string that goes wrong exists only after
the page has run. Static analysis cannot see any of it.

TWO LEVELS, NOT JUST LEAVES. "SPREAD Spread" was two sibling spans, and
a leaves-only scan sees two innocent words. So elements whose children
are all leaves are read as one string too.

ONE EXEMPTION, WITH A REASON: the memecoin board prints a symbol beside
a coin name — two fields that usually differ and sometimes coincide — so
the duplicate-word mark is off on that view alone. The other three marks
still apply there, and all four apply everywhere else.

COVERAGE IS PART OF THE RESULT, the lesson rendercheck.py paid for: this
container has almost no board data, so most views draw their empty state
and there is little text to be wrong. A green run is evidence about the
text that EXISTED, and the run says how much that was — 38,763 strings
across 138 views here, and the assertion floor catches "the sweep broke"
rather than "the board is quiet".

THE PROP-PAGE HALF NEEDS A BOARD WITH CARDS ON IT, and this harness
serves the REDACTED copy of the board (game bets and picks are paid
keys), so it reports zero doors here. That number is printed rather than
assumed: on the droplet, where the board is whole, the same run opens
every door and reads the chart strip behind it — which is where the
"SPREAD Spread" repeat lived.

Opt in with QB_BROWSER_TESTS=1, for the reason test_proseflow.py records.

    QB_BROWSER_TESTS=1 python3 tests/test_textholes.py

Run directly: `python3 tests/test_textholes.py`
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

// The same ground test_deadcontrols.py covers, plus the sports: the one
// finding this sweep has produced was on a board that only one league
// publishes, so a single-sport walk would have missed it.
const SPORTS = ['nfl', 'cfb', 'mlb', 'nba', 'wnba', 'ufc'];
const VIEWS = [['board', null], ['scanner', '[data-view="scanner"]'],
  ['longshots', '[data-view="longshots"]'], ['futures', '[data-view="futures"]'],
  ['edge', '[data-view="edge"]'], ['injuries', '[data-view="injuries"]'],
  ['weather', '[data-view="weather"]'], ['players', '[data-view="players"]'],
  ['live', '[data-view="live"]'], ['trending', '[data-view="trending"]'],
  ['rosters', '[data-view="rosters"]'], ['standings', '[data-view="standings"]'],
  ['bankroll', '[data-view="bankroll"]'], ['alerts', '[data-view="alerts"]'],
  ['tonight', '[data-view="tonight"]'], ['record', '[data-sport="record"]'],
  ['intel', '[data-sport="intel"]'], ['fantasy', '[data-sport="fantasy"]'],
  ['memes', '[data-sport="memes"]'], ['mybets', '[data-sport="mybets"]'],
  ['lab', '[data-sport="lab"]'], ['about', '[data-sport="about"]'],
  ['why', '[data-sport="why"]']];

const SCAN = ({ where, dupOff }) => {
  const out = [];
  const seen = new Set();
  const DUP = /\b([A-Za-z][A-Za-z'’-]{2,})\s+\1\b/i;
  const LONGDEC = /\d+\.\d{6,}/;
  const TEMPLATE = /\$\{|\}\}|\[object /;
  const HOLE = /\bundefined\b|\bNaN\b|\bInfinity\b/;
  // THE ONE EXEMPTION, and it earns its place. The memecoin board's
  // whole idiom is "SYMBOL Name" — two different fields that usually say
  // different things ("MEW rocket" / "Cat in a Dogs World") and
  // sometimes coincide ("SLERF" / "Slerf"). That is the component
  // working, and it prints in four places on that page: the pick row,
  // the card head, and two gated tables. Chasing selectors would be a
  // list somebody has to maintain, so the exemption is the VIEW and it
  // is only the duplicate mark — holes, templates and unrounded floats
  // are still read there, and every other view is still read for all
  // four.
  let scanned = 0;
  document.querySelectorAll('.view').forEach(v => {
    if (getComputedStyle(v).display === 'none') return;
    v.querySelectorAll('*').forEach(el => {
      const kids = [...el.children];
      if (kids.length && (kids.length > 4 || !kids.every(k => !k.children.length))) return;
      const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length > 200) return;
      scanned++;
      let why = null;
      if (HOLE.test(t)) why = 'a hole';
      else if (TEMPLATE.test(t)) why = 'an uninterpolated template';
      else if (LONGDEC.test(t)) why = 'an unrounded float';
      else if (!dupOff && DUP.test(t)) why = 'a word printed twice';
      if (!why) return;
      const key = why + '|' + el.className + '|' + t;
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ where, why, cls: String(el.className).slice(0, 40),
                 text: t.slice(0, 130) });
    });
  });
  return { out, scanned };
};

const found = [], missing = [];
let scanned = 0, reached = 0, doors = 0;
for (const sport of SPORTS) {
  const p = await b.newPage({ viewport: { width: 1280, height: 1100 } });
  await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1800);
  const ok = await p.evaluate(s => { const e = document.querySelector(`[data-sport="${s}"]`);
                                     if (!e) return false; e.click(); return true; }, sport);
  if (!ok) { missing.push(sport); await p.close(); continue; }
  await p.waitForTimeout(2200);
  for (const [view, sel] of VIEWS) {
    if (sel) {
      const got = await p.evaluate(s => { const e = document.querySelector(s);
                                          if (!e) return false; e.click(); return true; }, sel);
      if (!got) continue;
      await p.waitForTimeout(700);
    }
    reached++;
    const r = await p.evaluate(SCAN, { where: `${sport}/${view}`,
                                      dupOff: view === 'memes' });
    scanned += r.scanned;
    found.push(...r.out.slice(0, 4));
  }
  // EVERY DOOR, OPENED. A prop page is where the chart strip lives, and
  // the strip is where "SPREAD Spread" was. Collected AFTER the view
  // walk rather than on the board alone: the first draft went back to
  // the board, found no cards there on a quiet slate, and reported zero
  // prop pages while claiming a green run — a sweep that covers nothing
  // and says nothing about it is the cry-wolf failure inverted.
  const ids = await p.evaluate(() =>
    [...new Set([...document.querySelectorAll('[data-prop]')].map(e => e.dataset.prop))]);
  for (const id of ids.slice(0, 25)) {
    const opened = await p.evaluate(pid => {
      if (typeof openProp !== 'function') return false;
      openProp(pid); return true;
    }, id);
    if (!opened) break;                       // openProp is not global
    await p.waitForTimeout(240);
    doors++;
    const r = await p.evaluate(SCAN, { where: `${sport}/prop ${id}`,
                                      dupOff: false });
    scanned += r.scanned;
    found.push(...r.out.slice(0, 2));
  }
  await p.close();
}
console.log(JSON.stringify({ found, missing, scanned, reached, doors }));
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


def test_no_sentence_on_the_site_has_a_hole_in_it():
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

    print(f"      ({out['scanned']:,} strings across {out['reached']} views "
          f"and {out['doors']} prop pages)")
    assert not out["missing"], \
        f"these leagues could not be reached at all: {out['missing']}"
    # The floor catches "the sweep broke", not "the board is quiet".
    assert out["scanned"] >= 400, \
        (f"only {out['scanned']} strings were read — the sweep is not "
         "covering the app any more, so a green result means nothing")
    assert not out["found"], (
        "these rendered strings carry the mark of a render bug:\n  "
        + "\n  ".join(f"{f['where']}: {f['why']} — \"{f['text']}\""
                      for f in out["found"][:10]))


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
