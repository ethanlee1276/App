"""The open bets vanished off a page nobody touched. Executed, not read.

Ethan, 2026-09-03: *"ill be staring at the live page at the open bets and
ill scroll and shit then the open bets will just dissapear."*

`live_picks` is a PAID key. So the static board Caddy serves off disk —
`SPORT_META[sport].fallback` — is the REDACTED copy: open bets stripped,
recommendations stripped, the likelihood board stripped, and a
`locked_reason` stamped on to say so. That file is the honest answer for
a signed-out reader and for a static host with no API behind it.

`load()` reached for it on EVERY failure of the real endpoint, and
installed whatever came back over a board the subscriber already had:

    one dropped poll   a phone changing cell, a deploy, the seal that
                       runs at server startup
    a non-ok status    a 502 from the proxy mid-deploy, a 503 while the
                       box is busy — thrown as "api" into the same catch
    both copies gone   offline entirely, which replaced the board with
                       `status: "not built"` — a claim about the MODEL,
                       which is the substitution tests/test_wiredown.py
                       was written about

Every one of them heals on the next successful poll thirty seconds later,
which is why it reads as a flicker rather than a fault, and why it is
hard to catch in the act.

WHY THIS FILE RUNS load() INSTEAD OF READING IT. The bug is not a missing
string, it is which of five paths assigns `state.data`. A source pin
saying "the guard is present" would have passed against a guard that
never fires, and the guard has to fire on exactly one of the cases below
and stay out of the way on the other four. So `load()` is sliced out with
its real `normalizeSlate`, given a scripted `fetch`, and run.

THE CASE THAT MUST STILL SWAP, and the reason the guard is not simply
"never replace a board": after a league switch the slate in hand is the
one being LEFT. Leaving it up under the new league's name is the bug
tests/test_board_identity.py exists for, so the guard is keyed on
`_boardFor === meta.api` exactly as the revalidation guard is.

Run directly: `python3 tests/test_open_bets_vanish.py`
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

if not shutil.which("node"):
    print("SKIP node is not installed; this file EXECUTES load() rather "
          "than reading it. `apt install -y nodejs`")
    print("\n0 tests passed.")
    raise SystemExit(0)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name, kind="function"):
    i = APP.index(f"{kind} {name}(")
    depth = 0
    for k in range(APP.index("{", i), len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"{name} has unbalanced braces")


#: Everything `load()` reaches for that is not the thing under test. Each
#: one is inert on purpose: this file is about WHICH payload survives the
#: call, not about what gets drawn from it.
_STUBS = """
const SPORT_META = {
  nfl: { api: "/api/recommendations", fallback: "data/recommendations.json" },
  mlb: { api: "/api/mlb/recommendations", fallback: "data/mlb_recommendations.json" },
};
const _boardTags = {};
let _boardFor = null;
const state = { sport: "nfl", minConf: 0, minEdge: 0, maxJuice: 0,
                data: null, builtAt: null, static: false };
function showSkeleton() {}
function loadHeartbeat() {}
function captureFreshBaseline() {}
function renderAll() {}
function applyFreshPulses() {}
function manageAutoRefresh() {}
function updateAgo() {}
const document = { getElementById: () => null };

/* The light copy (2026-09-05) is ABSENT on this wire: that is the shape
   of every board built before it shipped, and every case in this file
   is about which FULL payload survives the call. tests/test_light_board.py
   overrides this to hand the light copy in. */
async function paidFetch(name) {
  return { ok: false, status: 404, headers: { get: () => null }, json: async () => ({}) };
}

/* The scripted wire. `PLAN` is consumed one entry per fetch, in order,
   so a test says exactly what the endpoint and then the static file do.
   "throw" is a network failure (offline, abort, DNS); the others are
   real responses. */
let PLAN = [];
async function fetch(url) {
  const step = PLAN.shift();
  if (!step) throw new Error("fetch beyond the plan: " + url);
  if (step.throw) throw new Error("wire");
  return {
    ok: step.ok !== false,
    status: step.status || 200,
    headers: { get: (h) => (step.headers || {})[h] || null },
    json: async () => step.body,
  };
}
"""

#: A subscriber's board: the paid keys are populated.
FULL = {"date": "2026-09-03", "live_picks": [{"player": "A"}, {"player": "B"}],
        "recommendations": [{"pick": "x"}], "games": [{"id": "g1"}]}

#: The same board as the public path serves it. This is `gate.redact`'s
#: real output shape — paid keys emptied rather than dropped, plus the
#: two fields that say why.
REDACTED = {"date": "2026-09-03", "live_picks": [], "recommendations": [],
            "games": [{"id": "g1"}],
            "locked": {"live_picks": 2, "recommendations": 1},
            "locked_reason": "subscription"}


def _run(setup, plan):
    """Run load() once and report what the page is left holding."""
    src = (_STUBS
           + _fn("normalizeSlate") + "\n"
           + _fn("locksAwayWhatWeHold") + "\n"
           + _fn("lightNameFor") + "\n"
           + _fn("load", kind="async function") + "\n"
           + setup + "\n"
           + f"PLAN = {json.dumps(plan)};\n"
           + """
load(true).then(() => {
  console.log(JSON.stringify({
    live: (state.data || {}).live_picks || [],
    locked: !!(state.data || {}).locked_reason,
    status: (state.data || {}).status || "",
    boardFor: _boardFor,
    builtAt: state.builtAt,
  }));
}).catch((e) => { console.error(e); process.exit(3); });
""")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


#: Holding this sport's real board, which is the state Ethan was in.
HOLDING = ('state.data = ' + json.dumps(FULL) + ';\n'
           '_boardFor = SPORT_META.nfl.api;\n'
           'state.builtAt = 1000;')


# --- the report ------------------------------------------------------------
def test_a_dropped_poll_does_not_take_the_open_bets_away():
    """THE BUG. The endpoint fails, the static file answers with the
    stripped copy, and the two open bets on screen must still be there."""
    got = _run(HOLDING, [{"throw": True}, {"body": REDACTED}])
    assert len(got["live"]) == 2, \
        f"the open bets were replaced by the redacted board: {got}"
    assert not got["locked"], "the paywalled stub was installed over a real board"


def test_the_stale_stamp_is_not_moved_by_a_board_we_refused():
    """A board we declined to install must not date the one we kept, or
    the freshness chip would restart its clock on every failed poll and
    an ageing board would read as fresh."""
    got = _run(HOLDING, [{"throw": True},
                         {"body": REDACTED,
                          "headers": {"Last-Modified": "Thu, 03 Sep 2026 12:00:00 GMT"}}])
    assert got["builtAt"] == 1000, \
        f"the refused board stamped its own build time: {got}"


def test_a_bad_gateway_mid_deploy_does_not_empty_the_board():
    """The second route in: a non-ok status rather than a thrown fetch.
    A 502 from the proxy while the box restarts is the same failure to a
    reader and took the same path."""
    got = _run(HOLDING, [{"ok": False, "status": 502}, {"body": REDACTED}])
    assert len(got["live"]) == 2, f"a 502 emptied the board: {got}"


def test_the_unasked_304_route_had_nothing_to_take_away():
    """WRITTEN DOWN BECAUSE THE FIRST DRAFT OF THIS FILE GOT IT WRONG.

    `load()` throws "unasked 304" and lands in the same catch, so it read
    like a third way for the bets to vanish. It is not: that branch is
    the `else` of `res.status === 304 && holding`, so it only fires when
    we are NOT holding this board — nothing is on screen to lose, and
    installing the static copy is the right thing.

    The first cut of this test claimed to cover it and never reached it:
    with no stored tag, `holding` was true and the FIRST 304 branch ran.
    A test named for a branch it cannot enter is the defect this session
    already fixed once in tests/test_touchtargets.py, so it is kept here
    pointing at what actually happens."""
    # Holding nothing: no tag is sent, and a 304 from a proxy is unasked.
    got = _run("", [{"status": 304, "ok": False}, {"body": REDACTED}])
    assert got["locked"], \
        f"the fallback did not install for a board we do not hold: {got}"
    assert got["boardFor"] == "/api/recommendations"


def test_going_offline_keeps_the_board_rather_than_blaming_the_model():
    """Both copies unreachable. "not built" is a claim about the model;
    the truth is that we could not ask."""
    got = _run(HOLDING, [{"throw": True}, {"throw": True}])
    assert len(got["live"]) == 2, f"offline emptied the board: {got}"
    assert got["status"] != "not built", \
        "a wire failure was reported as a board that was never built"


# --- the four cases the guard must stay out of the way of -------------------
def test_switching_league_still_replaces_the_board_it_is_leaving():
    """THE REASON THE GUARD IS BOARD-AWARE. Holding NFL, asking for MLB,
    both fetches failing: the NFL slate must NOT be left on screen under
    MLB's name — that is tests/test_board_identity.py's bug."""
    got = _run(HOLDING + '\nstate.sport = "mlb";',
               [{"throw": True}, {"throw": True}])
    assert got["live"] == [], \
        f"the previous league's open bets survived a switch: {got}"
    assert got["status"] == "not built"
    assert got["boardFor"] == "/api/mlb/recommendations"


def test_a_signed_out_reader_still_gets_refreshed():
    """Locked over locked is an ordinary refresh, not a downgrade — this
    is every poll a reader without a subscription makes, all day."""
    got = _run('state.data = ' + json.dumps(REDACTED)
               + ';\n_boardFor = SPORT_META.nfl.api;',
               [{"throw": True},
                {"body": dict(REDACTED, date="2026-09-04")}])
    assert got["locked"], got
    assert json.loads(json.dumps(got))["live"] == []


def test_the_first_load_of_a_static_host_still_lands():
    """Nothing held, no API: the static file is the honest board and has
    to install, or a host with no back end shows nothing at all."""
    got = _run("", [{"throw": True}, {"body": REDACTED}])
    assert got["locked"], f"the fallback did not install on a cold page: {got}"
    assert got["boardFor"] == "/api/recommendations"


def test_the_endpoint_may_still_lock_the_board_itself():
    """A LAPSED SUBSCRIPTION IS NOT A WIRE FAILURE. When /api answers
    with the stripped board, that is the truth about this reader and it
    renders — the guard covers the path that reached for the static file
    because the API would not answer, not the API's own verdict."""
    got = _run(HOLDING, [{"body": REDACTED}])
    assert got["locked"], \
        "the guard swallowed the endpoint's own answer and kept a stale board"
    assert got["live"] == []


# --- the shape the fix depends on ------------------------------------------
def test_the_guard_reads_the_field_the_engine_actually_stamps():
    """`locked_reason` is written by engine/gate.redact on every stripped
    board. Pinned across the two files so a rename cannot quietly turn
    the guard off — it would fail open, which is invisible."""
    gate = open(os.path.join(ROOT, "engine", "gate.py"), encoding="utf-8").read()
    assert 'out["locked_reason"] = "subscription"' in gate, \
        "gate.redact no longer stamps locked_reason; the page guard is now blind"
    assert "next.locked_reason" in _fn("locksAwayWhatWeHold")


def test_every_assignment_to_the_slate_still_records_its_board():
    """Held from tests/test_board_identity.py, because this change adds a
    path that assigns nothing and it must not disturb the ones that do."""
    body = _fn("load", kind="async function")
    for at in [m.start() for m in re.finditer(r"state\.data\s*=", body)]:
        assert "_boardFor = meta.api" in body[at:at + 400], \
            " ".join(body[at:at + 90].split())


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
