"""What the page prints when a field is missing.

Written during the pre-launch pass, from a probe that fed every display
helper the values a real payload actually produces when a build does not
fill a key: null, undefined, NaN, Infinity, 0.

THREE OF THEM LEAKED, and two were reachable from live call sites:

  * `escapeHtml(undefined)` printed the word **"undefined"**. It is
    `String(s)` at heart and it is the last step before hundreds of
    optional payload fields reach the page — a board row with no
    `opponent`, a bet with no `book`, any key a build did not write. The
    JavaScript word for absence, in the sentence, on a live page.
  * `money(NaN)` printed **"$NaN"**. `stakeDollars(r.stake_units)` is the
    common caller and it MULTIPLIES, so a row whose `stake_units` never
    got filled makes NaN and this rendered it as a price.
  * `money(null)` and `money(undefined)` **THREW**, because
    `.toLocaleString` does. A throw inside a render loses the whole block
    and nothing says a word — this repo has already lost the team-form
    panel for thirteen days to exactly that shape of failure.

WHERE THE LINE IS, because "make everything safe" is how a test suite
starts hiding bugs. These helpers now absorb ABSENCE — null and undefined
mean "there is nothing here", and a blank or a dash is the honest way to
draw nothing. They do NOT absorb malformed values: `escapeHtml({})` still
renders "[object Object]" and `escapeHtml(NaN)` still renders "NaN",
because those are mistakes at the call site and hiding them makes the
real bug harder to find. Zero and false are printed exactly as given —
swallowing those would turn a real "0" into a blank, which is a
different lie.

Run directly: `python3 tests/test_display_safety.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")

# The same stub the load test uses, borrowed rather than copied so the two
# cannot drift — a second hand-maintained browser stub is a second thing
# to keep true.
#
# Imported INSIDE the helper, not at module scope: tests/ must import
# cleanly on a box with nothing installed, and tests/test_doctor.py walks
# every file here to enforce it. `tests` is not on sys.path when this file
# is run from the repo root either way.
def _harness():
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_app_loads as loads
    return loads.HARNESS


#: (call, expected). Written as source so the probe reads like the code
#: it is checking rather than like a table of encodings.
CASES = [
    # Absence renders as nothing, not as the word for nothing.
    ('escapeHtml(undefined)', ''),
    ('escapeHtml(null)', ''),
    # …and a real value still renders, including the falsy ones.
    ('escapeHtml(0)', '0'),
    ('escapeHtml(false)', 'false'),
    ('escapeHtml("")', ''),
    ('escapeHtml("a<b")', 'a&lt;b'),
    # A malformed value is still shown, on purpose. See the docstring.
    ('escapeHtml(NaN)', 'NaN'),
    # Money never prints a machine word and never throws.
    ('money(NaN)', '—'),
    ('money(null)', '—'),
    ('money(undefined)', '—'),
    ('money(Infinity)', '—'),
    ('money("")', '—'),
    # …and a REAL zero still prints as money. `Number(null)` and
    # `Number("")` are both 0, so a finiteness check alone would have
    # rendered a field that was never filled as "$0.00" — a stake of zero
    # is a thing this site prints on purpose and a missing one is not.
    ('money(0)', '$0.00'),
    ('money(12.5)', '$12.50'),
    ('mbMoney(Infinity)', '$0.00'),
    ('mbMoney(NaN)', '$0.00'),
    ('mbMoney(0)', '$0.00'),
    ('mbMoney(-3.5, true)', '−$3.50'),
]

# `vm` is already required by the harness this replaces the tail of;
# declaring it again is a redeclaration error in the same scope.
# Every name here is prefixed: this REPLACES the harness's last line and
# runs in the same scope, where `vm` and `out` are already declared.
PROBE = r"""
const _pr = [];
for (const _src of JSON.parse(process.argv[3])) {
  try { _pr.push({ src: _src, got: String(vm.runInThisContext(_src)) }); }
  catch (e) { _pr.push({ src: _src, threw: String((e && e.message) || e) }); }
}
console.log("PROBE" + JSON.stringify(_pr));
process.exit(0);
"""


def _probe(calls):
    if not NODE:
        return None
    harness = _harness().replace(
        'console.log(JSON.stringify(out));', PROBE)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "probe.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(harness)
        # THE CALLS GO IN argv[3], which is where PROBE reads them. The
        # first cut passed them in argv[4] — the slot the load harness
        # uses for its constants list — so the probe parsed `[]`, ran
        # nothing, and the test compared an empty list to an empty list
        # and passed against code with all three leaks still in it. A
        # green test that cannot fail is worse than no test, which is why
        # the count is checked below.
        proc = subprocess.run(
            [NODE, path, os.path.join(ROOT, "web", "js", "app.js"),
             json.dumps(calls), json.dumps([])],
            capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (proc.stderr or "")[:1200]
    line = [l for l in proc.stdout.splitlines() if l.startswith("PROBE")]
    assert line, "the probe printed nothing:\n" + proc.stdout[:800]
    got = json.loads(line[-1][5:])
    assert len(got) == len(calls), (
        f"the probe ran {len(got)} of {len(calls)} calls — it is not "
        "checking what this file says it checks")
    return got


def test_no_display_helper_prints_a_machine_word_for_a_missing_field():
    got = _probe([c for c, _ in CASES])
    if got is None:
        print("      (skipped: no Node)")
        return
    want = dict(CASES)
    wrong = []
    for r in got:
        if "threw" in r:
            wrong.append(f"{r['src']} THREW {r['threw']}")
        elif r["got"] != want[r["src"]]:
            wrong.append(f"{r['src']} -> {r['got']!r}, wanted {want[r['src']]!r}")
    assert not wrong, "\n  ".join([""] + wrong)


def test_the_guards_are_in_the_source_and_not_only_in_the_behaviour():
    """A behaviour test passes for the wrong reason if somebody replaces
    the guard with a coincidence. These name the two mechanisms."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function escapeHtml(")
    assert "if (s == null) return \"\";" in app[i:app.index("\n}", i)], (
        "escapeHtml no longer absorbs null and undefined")
    i = app.index("function money(")
    body = app[i:app.index("\nfunction ", i + 1)]
    assert "Number.isFinite" in body, (
        "money is back to calling .toLocaleString on whatever it is given, "
        "which throws on null")


def test_zero_is_not_treated_as_missing():
    """The failure mode of a careless fix. `if (!x) return "—"` reads
    fine and turns a real $0.00 stake into a dash — and a stake of zero
    is a thing this site prints on purpose, because parlays are graded
    at a zero stake."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function money(")
    body = app[i:app.index("\nfunction ", i + 1)]
    assert "!x" not in body and "!Number(x)" not in body, (
        "a truthiness check would swallow a legitimate zero")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
