"""A deploy restarts the service. That must not look like a crash.

Ethan, 2026-09-09, on NFL opening day: *"the site crashed. It won't load
anything and won't show logos."* Then, a minute later: *"it loads on my
phone but my buddy's won't."*

THE SECOND MESSAGE IS THE DIAGNOSIS. Two phones disagreeing is not a
crash — it is a WINDOW. `deploy/autoupdate.py` pulls every five minutes
and `systemctl restart`s the service on any change, which is a hard stop
and start; for the second or two it takes to come back, every connection
is refused. Anyone who opens the page inside that window gets the shell
from the service-worker cache — which is exactly why it looks like a
working site rather than a dead one — and a thrown fetch on all ten
boards, which is the banner he photographed.

I pushed eight times that afternoon. Eight windows, on the day the new
subscribers arrived, and every one of them was mine.

The deploy is not going to stop restarting the service and the answer is
not to ship less. One retry, a beat later, rides over it.

THE GATEWAY CASE IS WORSE THAN THE THROWN ONE, and it is the half that
would have been easy to miss. Caddy stays up while the app is down, so it
answers on the app's behalf with a 502 — `_wire` records "answered", the
banner stays silent, and the page draws an empty board as though the
model had nothing to say. That is the exact failure the `_wire` comment
upstairs was written against, arriving through a door it did not cover.

Run directly: `python3 tests/test_deploy_window.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    """The function's source, INCLUDING an `async` in front of it.

    Dropping that keyword lifts an async body into a plain one, and the
    first `await` inside is then a syntax error rather than a behaviour
    change — which is how this file failed to run at all the first time.
    """
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(name)


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";", i) + 1]


def _run(script):
    """`boardFetch` against a scripted sequence of fetch outcomes."""
    src = ("let refreshed = 0;\n"
           "function refreshStaleBar() { refreshed++; }\n"
           + _const("BOARD_RETRY_MS").replace("1200", "1")   # no real waiting
           + "\n" + _const("BOARD_RETRY_CODES") + "\n"
           + "const _wire = new Map();\n"
           + _fn("boardFetch") + "\n" + script)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


_HARNESS = """
// `plan` is one outcome per call: a number is a status, "throw" throws.
function stub(plan) {
  let n = 0;
  globalThis.fetch = async () => {
    const step = plan[Math.min(n++, plan.length - 1)];
    if (step === "throw") throw new TypeError("Load failed");
    return { status: step, ok: step >= 200 && step < 300 };
  };
  return () => n;
}
"""


# ------------------------------------------------- riding over the window

def test_a_refused_connection_is_retried_once_and_succeeds():
    """The restart window, exactly: the first attempt lands while the
    service is down, the second a beat later lands after it is back."""
    got = _run(_HARNESS + """
      const calls = stub(["throw", 200]);
      const res = await boardFetch("data/recommendations.json");
      console.log(JSON.stringify([res.status, calls(), refreshed,
                                  _wire.get("data/recommendations.json")]));
    """.replace("const res", "const res"))
    assert got == [200, 2, 0, True], got


def test_a_gateway_error_is_retried_too():
    """Caddy answering 502 on the app's behalf. Without this the retry
    covers only the case where the connection is refused outright, and a
    restart behind a proxy takes the other path every time."""
    got = _run(_HARNESS + """
      const calls = stub([502, 200]);
      const res = await boardFetch("data/feed.json");
      console.log(JSON.stringify([res.status, calls(), refreshed]));
    """)
    assert got == [200, 2, 0], got


def test_the_banner_never_appears_for_a_blip():
    """The whole point. One failed attempt followed by a good one must
    leave no trace — no wire-down record, no re-drawn stale bar, and
    nothing on screen telling a new subscriber the site is broken."""
    got = _run(_HARNESS + """
      const calls = stub(["throw", 200]);
      await boardFetch("data/cfb.json");
      console.log(JSON.stringify([refreshed, [..._wire.values()]]));
    """)
    assert got == [0, [True]], got


# ------------------------------------------- and still honest when it is not

def test_a_wire_that_is_really_down_still_says_so():
    """Two failures is not a blip. The banner exists because the worst
    thing this site can say is a verdict it did not reach, and a retry
    must not turn that into silence."""
    got = _run(_HARNESS + """
      stub(["throw", "throw"]);
      let threw = false;
      try { await boardFetch("data/record.json"); } catch (e) { threw = true; }
      console.log(JSON.stringify([threw, refreshed,
                                  _wire.get("data/record.json")]));
    """)
    assert got == [True, 1, False], got


def test_a_gateway_error_twice_is_a_wire_failure_not_an_answer():
    """502 on the last attempt must NOT be recorded as answered. Caddy
    replying for an app that never saw the request is the wire failing
    with better manners, and counting it as a response is how the page
    goes quiet instead of honest."""
    got = _run(_HARNESS + """
      stub([503, 503]);
      let threw = false;
      try { await boardFetch("data/streak.json"); } catch (e) { threw = true; }
      console.log(JSON.stringify([threw, _wire.get("data/streak.json")]));
    """)
    assert got == [True, False], got


def test_a_404_is_answered_on_the_first_try_and_never_retried():
    """A board that has never been built has no file, and "no data yet"
    is the honest thing to say about it. Retrying every 404 would double
    the request count for every unbuilt board on the site."""
    got = _run(_HARNESS + """
      const calls = stub([404, 200]);
      const res = await boardFetch("data/nope.json");
      console.log(JSON.stringify([res.status, calls(), refreshed,
                                  _wire.get("data/nope.json")]));
    """)
    assert got == [404, 1, 0, True], got


def test_a_paywalled_board_is_not_retried_either():
    """401 and 402 are the server deciding, not the wire failing."""
    for code in (401, 402, 429):
        got = _run(_HARNESS + f"""
          const calls = stub([{code}, 200]);
          const res = await boardFetch("data/paid.json");
          console.log(JSON.stringify([res.status, calls()]));
        """)
        assert got == [code, 1], (code, got)


# ------------------------------------------------------------ the deploy

def test_the_updater_really_does_restart_on_every_pull():
    """The premise. If this ever becomes a reload or a socket handoff the
    retry is still harmless, but the comment above `boardFetch` would be
    describing a world that no longer exists."""
    src = open(os.path.join(ROOT, "deploy", "autoupdate.py"),
               encoding="utf-8").read()
    assert '"systemctl", "restart"' in src.replace("'", '"'), \
        "the updater no longer restarts — re-read the boardFetch comment"
    timer = open(os.path.join(ROOT, "deploy", "qellys-update.timer"),
                 encoding="utf-8").read()
    assert "OnUnitActiveSec=5min" in timer


if __name__ == "__main__":
    if not shutil.which("node"):
        print("SKIP node is not installed; this file executes boardFetch. "
              "`apt install -y nodejs`")
        print("\n0 tests passed.")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
