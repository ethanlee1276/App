"""The address bar must not name a page nobody is on.

Ethan is sending links to customers and customers send links to each
other, so a URL that does not describe the page is not cosmetic — it is
the thing that arrives in somebody else's message.

WHAT WAS WRONG. Both routers end with a guard that returns when the hash
matches nothing they know. That is the right call about the VIEW: an
unknown hash should not move anybody. It was the wrong call about the
URL, which was left pointing at whatever was typed. Reproduced
2026-09-09 with `#rankings` — a hash that reads like a real page and is
not one, because the rankings live on the standings page. The injuries
page stayed on screen and the address bar said `#rankings`. Copy that,
send it, and the person who opens it gets a third thing.

It is the same lie the hashchange handler's own comment was written to
stop, and the branch directly above the fall-through — the one refusing a
tab the current sport does not have — already put the URL back. This gave
the fall-through the same manners.

HOW THIS IS CHECKED. app.js is evaluated in Node against the stub DOM
`test_app_loads.py` owns, with `history` swapped for a recorder, and the
boot router is driven by the hash the same way a cold load drives it.

    python3 tests/test_router_url.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

NODE = shutil.which("node")


def _boot_harness():
    """The stub DOM, from the file that already owns it.

    Imported inside the function: tests/test_doctor.py refuses
    module-scope imports beyond the stdlib in tests/, so collecting this
    file can never fail on somebody else's import.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_app_loads import HARNESS
    return HARNESS


#: Swaps the stub's inert history for one that remembers, so the test can
#: see WHICH call was made and with what — `pushState` here would trap the
#: Back button on the bad URL, so telling them apart is the point.
_RECORDER = """globalThis.history = {
  calls: [],
  replaceState: function (s, t, u) { this.calls.push(["replace", u]); },
  pushState: function (s, t, u) { this.calls.push(["push", u]); },
};"""

_PROBE = """
console.log("ROUTE" + JSON.stringify({
  calls: history.calls,
  view: state.view,
}));
process.exit(0);
"""


def _boot(hash_):
    harness = _boot_harness()
    old = "globalThis.history = { replaceState: noop, pushState: noop };"
    assert old in harness, "the harness's history stub moved; re-anchor this"
    harness = harness.replace(old, _RECORDER)
    harness = harness.replace("console.log(JSON.stringify(out));", "")
    harness = harness.replace("process.exit(0);", "") + _PROBE
    with tempfile.TemporaryDirectory() as tmp:
        h = os.path.join(tmp, "h.js")
        with open(h, "w", encoding="utf-8") as fh:
            fh.write(harness)
        proc = subprocess.run(
            [NODE, h, os.path.join(ROOT, "web", "js", "app.js"),
             "[]", "[]", hash_, "[]"],
            capture_output=True, text=True, timeout=120)
    line = [l for l in proc.stdout.splitlines() if l.startswith("ROUTE")]
    if not line:
        raise AssertionError("the probe did not report:\n" + proc.stdout[-800:]
                             + "\n" + proc.stderr[-800:])
    return json.loads(line[-1][len("ROUTE"):])


def test_a_hash_that_matches_nothing_puts_the_url_back():
    """`#rankings` is the real one: it reads like a page this site would
    have, and it is not. Nobody typing it should be moved, and nobody
    copying the result should get a URL describing somewhere else."""
    got = _boot("#rankings")
    fixes = [u for kind, u in got["calls"] if kind == "replace"]
    assert "#recommended" in fixes, (
        "the address bar was left naming a page nobody is on: " + str(got))


def test_the_correction_is_never_a_history_entry():
    """`pushState` would put the bad URL in the back stack: press Back and
    you land on it, the router corrects it again, and you are stuck one
    step from where you wanted to be."""
    got = _boot("#nothing-here")
    pushes = [u for kind, u in got["calls"] if kind == "push"]
    assert not pushes, f"the correction was pushed onto history: {pushes}"


def test_a_real_view_is_left_completely_alone():
    """The guard must not fire on a hash that DID route — correcting a
    working URL to the same value is noise at best, and at worst it is a
    fight with whatever set it."""
    got = _boot("#live")
    assert got["view"] == "live", got
    fixes = [u for kind, u in got["calls"] if kind == "replace"]
    assert "#recommended" not in fixes, (
        "a hash that routed correctly was overwritten anyway: " + str(got))


def test_an_entity_link_keeps_its_own_url():
    """The links people actually send. `#pbp/nfl/<id>` is handled long
    before the fall-through, and a correction here would rewrite a
    working shared link into the board on arrival — which is the bug this
    change exists to fix, pointing the other way."""
    for h in ("#pbp/nfl/401671800", "#game/ne-sea", "#player/nfl/josh-jacobs"):
        got = _boot(h)
        fixes = [u for kind, u in got["calls"] if kind == "replace"]
        assert "#recommended" not in fixes, (
            f"{h} was corrected away to the board: {got}")


def test_a_plain_visit_does_not_get_a_hash_bolted_on():
    """THE REGRESSION THIS FIX ALMOST SHIPPED WITH, caught in a browser.

    The boot router reaches the fall-through on a plain visit — no hash
    matches nothing, by definition — so the first version of the
    correction turned every arrival at qellysbook.com into
    qellysbook.com/#recommended. Nobody asked for that, it changes what
    people copy off the home page, and it buys nothing: an empty hash is
    not a URL that names the wrong page, it is the canonical address for
    the board."""
    for h in ("", "#"):
        got = _boot(h)
        assert not got["calls"], (
            f"a plain visit (hash {h!r}) rewrote the address bar: {got}")


def test_both_routers_call_it():
    """One is the cold load and one is every navigation after it, and a
    fix in only one of them is the bug on the other half of the time."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert src.count("urlBackToView()") >= 2, \
        "only one of the two routers puts the URL back"
    boot = src[src.index("function initialView() {"):]
    boot = boot[:boot.index("\n}")]
    assert "urlBackToView()" in boot, "the cold load does not put the URL back"
    i = src.index('window.addEventListener("hashchange"')
    warm = src[i:src.index("\n  });", i)]
    assert "urlBackToView()" in warm, \
        "an in-app navigation to an unknown hash still leaves the URL wrong"


if __name__ == "__main__":
    if not NODE:
        print("node not found — skipping"); raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
