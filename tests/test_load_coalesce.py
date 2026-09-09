"""Twenty pulls on the refresh must not become twenty board downloads.

Ethan, 2026-09-09: *"think like a degenerate that gambles all the time
and will be constantly checking the app"*. So the app was measured under
one.

MOST OF IT WAS ALREADY RIGHT, and that is worth writing down so nobody
re-fixes it: fifty tab switches leak nothing (six intervals before, six
after; the node count flat after the first lap), and an idle tab costs
six requests a minute against a per-IP ceiling of three hundred.

Pull-to-refresh was the exception. Twenty refreshes fired twenty full
board fetches, because nothing asked whether one was already on the wire.
On a phone on a bad connection that is the same board pulled five times
over, five renders of it, and five times the work on the box, for one
person who wanted to know whether the line moved.

WHY THIS RUNS THE REAL FUNCTION rather than grepping for a semaphore.
The interesting behaviour is not "is there a guard" — it is what the
guard does to three cases that pull in opposite directions: a burst must
collapse to one, a load for DIFFERENT filter values must not be swallowed
by one already running, and a hung load must not wedge refreshing for
ever. A grep can see none of that. app.js is evaluated in Node against
the same stub DOM `test_app_loads.py` uses, `fetch` is replaced with a
counter, and `load()` is called for real.

    python3 tests/test_load_coalesce.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NODE = shutil.which("node")

#: The stub DOM and globals come from the file that already owns them —
#: two copies of a browser stub would drift, and this one only needs to
#: get as far as calling a function.
def _boot_harness():
    """The stub DOM and globals, from the file that already owns them.

    Imported INSIDE the function on purpose: tests/test_doctor.py refuses
    module-scope imports beyond the stdlib in tests/, so that collecting
    this file can never fail on somebody else's import. Two copies of a
    browser stub would drift, and this one only needs to get as far as
    calling a function.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_app_loads import HARNESS
    return HARNESS

_PROBE = r"""
// --- the probe -------------------------------------------------------
// Runs after app.js has evaluated. Counts board fetches, never resolves
// them (a board that landed would drag the whole render in), and reports.
//
// ASYNC, AND THAT IS NOT A DETAIL. `load()` reaches its fetch after an
// await, so a probe that read the counter on the same tick saw zero and
// would have passed no matter what the guard did. Every phase waits for
// the microtask queue to drain before it reads.
const probe = {};   // `out` belongs to the boot harness
let n = 0;
const seen = [];
globalThis.fetch = (u) => {
  const s = String(u || "");
  seen.push(s);
  if (/recommendations|\/api\/board/.test(s)) n++;
  return new Promise(() => {});          // in flight for ever, on purpose
};
const settle = () => new Promise((r) => setTimeout(r, 25));

(async () => {
  state.sport = "nfl";
  // BOOT ALREADY STARTED A LOAD, and it is still on the wire because
  // nothing here resolves. Twenty more calls would correctly JOIN it and
  // the burst would measure zero — a true number for the wrong question.
  // Winding the clock past the join window strands that one so each
  // phase below starts from a known state.
  const realNow = Date.now;
  Date.now = () => realNow() + 10 * 60 * 1000;

  // 1. A BURST COLLAPSES. Twenty callers, one board on the wire.
  n = 0;
  for (let i = 0; i < 20; i++) load(true);
  await settle();
  probe.burst = n;

  // 2. DIFFERENT NUMBERS ARE A DIFFERENT LOAD. Moving a slider while one
  //    is running must not be answered with the load for the old values.
  n = 0;
  state.minEdge = (state.minEdge || 0) + 5;
  load(true);
  await settle();
  probe.after_slider = n;

  // 3. A HUNG LOAD DOES NOT WEDGE REFRESHING FOR EVER. Every fetch above
  //    is still pending — the phone-in-a-lift case. Inside the window the
  //    next caller still joins; past it, it must start a fresh one.
  n = 0;
  load(true);
  await settle();
  probe.while_hung = n;

  Date.now = () => realNow() + 20 * 60 * 1000;
  n = 0;
  load(true);
  await settle();
  Date.now = realNow;
  probe.after_window = n;

  probe.seen = seen.slice(0, 8);
  console.log("PROBE" + JSON.stringify(probe));
  process.exit(0);
})();
"""


def _run(src_path=None):
    harness = _boot_harness().replace("console.log(JSON.stringify(out));", "").replace(
        "process.exit(0);", "") + _PROBE
    with tempfile.TemporaryDirectory() as tmp:
        h = os.path.join(tmp, "h.js")
        with open(h, "w", encoding="utf-8") as fh:
            fh.write(harness)
        proc = subprocess.run(
            [NODE, h, src_path or os.path.join(ROOT, "web", "js", "app.js"),
             "[]", "[]", "", "[]"],
            capture_output=True, text=True, timeout=120)
    line = [l for l in proc.stdout.splitlines() if l.startswith("PROBE")]
    if not line:
        raise AssertionError(
            "the probe did not report:\nSTDOUT:\n" + proc.stdout[-1500:]
            + "\nSTDERR:\n" + proc.stderr[-1500:])
    return json.loads(line[-1][len("PROBE"):])


def test_a_burst_of_refreshes_is_one_board_download():
    got = _run()
    assert got["burst"] == 1, (
        f"{got['burst']} board fetches for twenty refreshes — a phone on a "
        "bad connection pulls the same board that many times")


def test_moving_a_slider_is_not_answered_with_the_old_numbers():
    """The guard must key on what was ASKED for. Joining here would show
    somebody the board for the filter they just moved away from, which is
    a worse bug than the one the guard exists to fix."""
    got = _run()
    assert got["after_slider"] == 1, got


def test_a_hung_load_cannot_wedge_refreshing_for_ever():
    """`fetch` has no timeout. Without a bound, one connection that never
    answers — a phone walking into a lift — would hold the slot and the
    board would never refresh again in that tab. Worse than the problem
    being solved, and invisible until somebody complained the numbers
    were frozen."""
    got = _run()
    assert got["while_hung"] == 0, "the join window is not being used at all"
    assert got["after_window"] == 1, (
        "a load that never answered is still holding the slot minutes "
        "later — refreshing is wedged")


def test_the_window_is_short_enough_to_be_invisible():
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    m = re.search(r"const LOAD_JOIN_MS = (\d+);", src)
    assert m, "LOAD_JOIN_MS is gone"
    ms = int(m.group(1))
    assert 2000 <= ms <= 30000, (
        f"{ms}ms: too short and the burst is not caught, too long and a "
        "dead connection freezes the board for that whole time")


def test_the_slot_is_freed_when_a_load_throws():
    """`finally`, not `then`. One failed refresh must not wedge every
    later one for the length of the window."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = src.index("async function load(quiet = false) {")
    body = src[i:src.index("async function _loadNow", i)]
    assert "p.finally(" in body, "a rejected load never frees the slot"
    assert "_loadInFlight === p" in body, \
        "a late finally would clear a NEWER load's slot"


if __name__ == "__main__":
    if not NODE:
        print("node not found — skipping"); raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
