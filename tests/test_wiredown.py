"""A verdict the model never reached is the worst thing this site can print.

Measured 2026-08-20 by aborting every board payload and reading what each
page then said:

    Tonight's bets   "Nothing clears the bar right now"
    Edge board       "Nothing clears the bar right now"
    Record           "No graded picks yet"
    Fantasy          "No NFL usage data yet"

Every one of those is a claim about the MODEL. The truth was that the
fetch failed. Twenty call sites each did `try { fetch } catch { null }`,
which collapses "the wire refused us" into the same value as "the payload
was empty", and nothing downstream can tell them apart afterwards.

This is the distinction the engine already draws everywhere else and the
front end did not: `cfb_build._has_board` ("games are the test, not file
existence"), rendercheck's no-data verdict, `DataUnavailable.status`. The
one place a reader actually looks was the place without it.

A 404 IS NOT A WIRE FAILURE, and that split is the whole reason this
does not cry wolf. A board that has never been built has no file, and
"no data yet" is the honest thing to say about it. Only a THROWN fetch —
offline, abort, DNS, TLS — means we could not ask. A later success for
the same URL clears the flag, so the signal is self-correcting and needs
no reset.

Verified both ways: with 29 payloads aborted the banner reads "We could
not reach the data for this page"; healthy, it falls through to the
staleness message it always had.

Run directly: `python3 tests/test_wiredown.py`
"""

import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_every_board_payload_goes_through_the_wrapper():
    """A bare `fetch("data/…")` is a fetch whose failure nobody counts."""
    bare = re.findall(r'await fetch\((["`]data/[^)]*)', APP)
    assert not bare, \
        f"these board fetches bypass boardFetch, so their failures are invisible: {bare}"
    # A canary against a wholesale rip-out, not a census. It moved from 20
    # to 18 on 2026-08-20 when the injury watch box and the injuries page
    # both stopped fetching data/injuries.json for themselves and went
    # through loadInjuryBoard() — two call sites fewer because one file is
    # now read once instead of three times, which is the opposite of
    # losing coverage. Lower it only for a reason you can write down like
    # this one.
    assert len(re.findall(r"await boardFetch\(", APP)) >= 18, \
        "the wrapper lost call sites — did a refactor drop them?"


def test_a_404_is_not_counted_as_the_wire_refusing_us():
    """THE HALF THAT STOPS THIS CRYING WOLF. A board that was never built
    has no file. Counting that as unreachable would put a scary banner
    over every feature the user has simply not enabled yet."""
    i = APP.index("async function boardFetch(")
    fn = APP[i:APP.index("\n}", i)]
    assert "_wire.set(key, true)" in fn, "a response no longer clears the flag"
    # the success path must run for ANY response, not only res.ok
    assert not re.search(r"if\s*\(\s*res\.ok\s*\)\s*_wire\.set\(key, true\)", fn), \
        "only 2xx clears the flag now — a 404 would read as an outage"


def test_a_later_success_clears_an_earlier_failure():
    i = APP.index("function wireDown(")
    fn = APP[i:APP.index("\n}", i)]
    assert "filter" in fn and "!ok" in fn, \
        "wireDown no longer reads the latest outcome per URL"


def test_unreachable_outranks_stale():
    """Old numbers are a fact about the build. A refused fetch means the
    empty states below are not verdicts at all — the more urgent
    sentence, so it is checked first."""
    i = APP.index("function renderStaleBar(")
    fn = APP[i:APP.index("\n}\n", i)]
    down_at = fn.index("wireDown()")
    stale_at = fn.index("STALE_LOUD_MS")
    assert down_at < stale_at, \
        "the staleness branch now runs before the unreachable one"
    assert "could not reach the data" in fn


def test_the_banner_says_it_is_about_the_connection_not_the_model():
    """The whole point. Without this sentence the banner is just another
    warning and the reader still believes "nothing qualifies"."""
    i = APP.index("could not reach the data")
    block = APP[i:i + 420]
    assert "not the model" in block, \
        "the banner no longer tells the reader the empty states below are not verdicts"


def test_a_lazy_view_failing_late_still_raises_the_banner():
    """Most boards are fetched when their view is opened, long after the
    load cycle drew the bar. Without an out-of-band redraw the banner
    would only ever appear if the very FIRST pull failed."""
    i = APP.index("async function boardFetch(")
    fn = APP[i:APP.index("\n}", i)]
    assert "refreshStaleBar()" in fn, \
        "a late failure no longer redraws the bar"
    assert "first" in fn, \
        "the redraw is no longer limited to the first failure — a flapping feed will spin it"


_PROBE = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2], MODE = process.argv[3];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const p = await b.newPage({ viewport: { width: 1280, height: 1000 } });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 120)));
let aborted = 0;
if (MODE === 'fail') {
  // The query string matters: the app appends ?t= to bust caches, so a
  // `**/data/*.json` glob matches nothing and the "wire down" run
  // silently becomes a second copy of the healthy one. It did.
  await p.route(u => /\/data\//.test(u.pathname) || /\/api\//.test(u.pathname),
                r => { aborted++; return r.abort('failed'); });
}
await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2600);
const out = await p.evaluate(() => {
  const bar = document.getElementById('stalebar');
  const main = document.querySelector('main');
  const txt = (main ? main.innerText : '');
  return { shown: bar ? !bar.hidden : false,
           says: bar && !bar.hidden ? (bar.innerText || '').replace(/\s+/g, ' ') : '',
           undef: (txt.match(/\bundefined\b|\bNaN\b|\[object Object\]/g) || []).length };
});
console.log(JSON.stringify({ ...out, aborted, errs }));
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


def _run(mode):
    import rendercheck
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=ROOT) as fh:
            fh.write(_PROBE)
            script = fh.name
        proc = subprocess.run(["node", script, str(port), mode], cwd=ROOT,
                              capture_output=True, text=True, timeout=300)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1200:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_banner_appears_when_the_wire_is_cut():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    down = _run("fail")
    assert down["aborted"] > 5, \
        (f"only {down['aborted']} requests were aborted — the route did not "
         "match, so this proves nothing (it matched nothing the first time)")
    assert down["shown"], "every payload was refused and the page said nothing"
    assert "could not reach" in down["says"], \
        f"the banner did not name the real cause: {down['says'][:120]}"
    assert not down["undef"], "placeholder values leaked into the page"
    assert not down["errs"], f"page errors with the wire down: {down['errs']}"

    ok = _run("ok")
    assert "could not reach" not in ok["says"], \
        f"the healthy page claims the wire is down: {ok['says'][:120]}"
    assert not ok["errs"], f"page errors on a healthy load: {ok['errs']}"


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
