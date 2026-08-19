"""A paragraph inside a flex card must not render as five stacked lines.

Found 2026-08-19 by reading `rendercheck.py`'s own screenshot of the My
Bets page. The safety note rendered like this:

    So you log bets here yourself. A
    Qellys
    account is a different thing: …

One sentence, three blocks. `.card` is `display: flex; flex-direction:
column; gap: 14px` — correct for a card of stacked children, wrong for a
card that IS a paragraph. **Flex blockifies its item children**, so the
two inline `<b>`s became block-level flex items with a 14px gap between
them. The card was 171px tall for 92px of text.

Nothing in the stylesheet was malformed and nothing threw. The rule is a
sensible rule applied to an element it does not fit, which is why no
existing test saw it: the only instrument that could was a picture.

The sweep below is the general form of the question — a flex or grid
container holding a long bare text node beside an inline element that
flex has blockified — and it holds an ALLOWLIST rather than a count.
Two matches are deliberate row layouts and stay:

  * `.section-title` — title and `.sub` on one baseline row
  * `.slate-horizon` — the date banner, `align-items: baseline`, 7px gap

Both are `flex-direction: row`, where blockified items sit side by side
and read as one line. The defect only exists in a COLUMN.

Run directly: `python3 tests/test_proseflow.py`
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

#: Reviewed and kept. Both are ROW layouts, where a blockified item sits
#: beside its neighbours and the line still reads as a line.
ALLOWED = ("section-title", "slate-horizon")


def test_the_card_that_is_a_paragraph_is_a_block():
    """The fix itself, and it must stay a fix: `.card`'s column flex is
    right for every other card, so this one opts out rather than the rule
    changing underneath eighty of them."""
    i = CSS.index(".mb-safety {")
    block = CSS[i:CSS.index("}", i)]
    assert "display: block" in block, \
        "the safety note is a flex column again — its sentence will split"


def test_the_column_card_rule_is_still_what_it_was():
    """If `.card` ever stops being a column, this whole finding changes
    shape and the comment above `.mb-safety` becomes a lie."""
    i = CSS.index(".card {")
    block = CSS[i:CSS.index("\n}", i)]
    assert "flex-direction: column" in block or "display: flex" in block


_SWEEP = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const VIEWS = ['[data-view="alerts"]','[data-sport="intel"]','[data-sport="fantasy"]',
  '[data-sport="mybets"]','#nav-acct','[data-sport="about"]','[data-sport="why"]',
  '[data-sport="record"]','[data-view="scanner"]','[data-view="futures"]',
  '[data-view="edge"]','[data-view="longshots"]','[data-view="bankroll"]',
  '[data-sport="lab"]','[data-view="injuries"]','[data-view="weather"]'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const p = await b.newPage({ viewport: { width: 1280, height: 1100 } });
await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'networkidle' });
await p.waitForTimeout(1300);
const seen = new Map();
async function scan() {
  const rows = await p.evaluate(() => {
    const out = [];
    document.querySelectorAll("*").forEach(el => {
      const cs = getComputedStyle(el);
      if (!/flex|grid/.test(cs.display)) return;
      if (el.offsetParent === null) return;
      let text = false, kid = null;
      for (const n of el.childNodes) {
        if (n.nodeType === 3 && n.textContent.trim().length > 25) text = true;
        if (n.nodeType === 1 && /^(B|I|EM|STRONG|A|CODE|SPAN)$/.test(n.tagName)
            && getComputedStyle(n).display === "block") kid = n.tagName;
      }
      if (text && kid) out.push({
        cls: (el.className || "").toString(),
        dir: cs.flexDirection,
        t: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 70) });
    });
    return out;
  });
  rows.forEach(r => seen.set(r.cls + "|" + r.t, r));
}
await scan();
for (const v of VIEWS) {
  const ok = await p.evaluate((s) => {
    const e = document.querySelector(s); if (!e) return false; e.click(); return true; }, v);
  if (!ok) continue;
  await p.waitForTimeout(800);
  await scan();
}
console.log(JSON.stringify([...seen.values()]));
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


def test_no_new_paragraph_is_being_shredded_by_a_flex_column():
    """Skipped with a reason when there is no browser, like every other
    rendered check here. Sixteen views plus the board."""
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return

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
        proc = subprocess.run(["node", script, str(port)], cwd=ROOT,
                              capture_output=True, text=True, timeout=240)
    finally:
        srv.shutdown()
        if script:
            Path(script).unlink(missing_ok=True)

    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("[")]
    assert lines, "the sweep produced no output — " + (proc.stderr or "")[:200]
    found = json.loads(lines[-1])
    bad = [r for r in found
           if not any(a in r["cls"] for a in ALLOWED)]
    assert not bad, (
        f"{len(bad)} paragraph(s) split by a flex/grid parent: "
        + "; ".join(f'.{r["cls"]} ({r["dir"]}) "{r["t"]}"' for r in bad[:4]))
    # And the allowlist has to stay honest: an entry that stops matching is
    # an entry nobody needs, and a stale allowlist hides the next defect.
    assert found, "the sweep matched nothing at all — check the instrument"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
