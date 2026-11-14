"""The newest render of the home deck wins (web/js/app.js renderHomeDeck).

Found 2026-10-27 while shooting the "No hard lines" comparisons: the same
build, the same board and the same wait drew the desktop dashboard's Live
now card on one run and hid it on the next. renderHomeDeck awaits the live
scoreboard (and, on a full render, the record) before it fills the deck,
and two renders can be in flight at once: a visit's board lands twice, or a
league is switched mid-fetch. Whichever render's awaits came back LAST
filled the deck, so an older board's Live now could land over a newer
one's, or the last league's over this one's. What these hold:

  * a full render takes a new number, and one that comes back to find a
    newer number fills nothing (no Live now, no record, no Zeno, and no
    re-arming of the clock: the newer render does all of that);
  * a clock redraw (still) keeps the number it found: it refreshes the same
    board, and it must not cancel a full render that still has the record
    and Zeno to fill, or those zones would stay empty;
  * a clock redraw overtaken by a full render fills nothing.

The races run in node against the real function with its neighbours
stubbed (skipped without node).
Run directly: `python3 tests/test_the_newest_deck_wins.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


DECK = _fn("renderHomeDeck")


def test_a_full_render_takes_a_number_and_a_redraw_keeps_it():
    assert "let _deckGen = 0;" in APP
    i = DECK.index("const gen = still ? _deckGen : ++_deckGen;")
    assert i < DECK.index("await "), "numbered before anything is awaited"
    assert DECK.index('if (!host) return;') < i, "no number spent on a page without a deck"


def test_nothing_is_filled_after_an_await_without_checking_the_number():
    after = DECK[DECK.index("if (still) {"):]
    for branch in after.split("} else {")[:2]:
        j = branch.index("await ")
        k = branch.index("if (gen !== _deckGen) return;")
        assert j < k < branch.index('deckFill(host, "live", live);'), branch[:200]
    assert DECK.count("if (gen !== _deckGen) return;") == 2, "one check after each await"
    fill = DECK[:DECK.index('host.querySelectorAll(".hd-game")')]
    assert fill.count("await ") == 2, "a new await before the fills needs its own check"


# --- the races, in node ----------------------------------------------------------------------
_STUBS = """
let _deckGen = 0, _deckTimer = null, _deckStamp = "", _deckFast = { at: 0, games: [] };
const LIVE_FEEDS = {};
const state = { data: { live_picks: [], live_potd: [] }, quiet: false, sport: "nfl" };
const fills = [], armed = [];
const host = { classList: { toggle() {}, add() {}, contains() { return false; } }, dataset: {}, hidden: true,
               querySelectorAll: () => [] };
const document = { getElementById: (id) => (id === "home-deck" ? host : null), body: { classList: { add() {} } } };
const deckSkeleton = () => {}, deckAdopt = () => {}, placeSlip = () => {};
const liveTrackerRows = (x) => x, deckRidingRows = () => [], deckRidingHTML = () => "", renderRidingTray = () => {};
const deckFill = (h, sec, html) => { if (sec !== "riding") fills.push(`${sec}:${html}`); };
const fastLiveStamp = () => "", sweepRings = () => {}, switchView = () => {};
const armDeckLive = () => armed.push(1);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Each call's delay and answer come from the plan the race sets.
let liveCalls = 0, recordCalls = 0;
const plan = { live: [], record: [] };
const deckLiveHTML = async () => { const p = plan.live[liveCalls++]; await sleep(p[0]); return p[1]; };
const deckRecordHTML = async () => { const p = plan.record[recordCalls++]; await sleep(p[0]); return { record: p[1], zeno: p[1] + "-zeno" }; };
"""


def _race(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""{_STUBS}
{DECK}
(async () => {{ {js}
  await sleep(250);
  console.log(JSON.stringify({{ fills, armed: armed.length }}));
}})();
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_board_that_lands_twice_keeps_the_second():
    """The first render's scoreboard is the slow one: it comes back last
    and, before the guard, its Live now and record were the ones left up."""
    got = _race("""
      plan.live = [[80, "old-live"], [5, "new-live"]];
      plan.record = [[80, "old-rec"], [5, "new-rec"]];
      renderHomeDeck(); renderHomeDeck();""")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got["fills"] == ["live:new-live", "record:new-rec", "zeno:new-rec-zeno"], got
    assert got["armed"] == 1, "the clock re-armed once, by the render that drew"


def test_a_league_switched_mid_fetch_never_shows_the_last_league():
    got = _race("""
      plan.live = [[60, "nfl-live"], [10, "cfb-live"]];
      plan.record = [[60, "nfl-rec"], [10, "cfb-rec"]];
      renderHomeDeck(); await sleep(20); state.sport = "cfb"; renderHomeDeck();""")
    if got is None:
        return
    assert not [f for f in got["fills"] if f.startswith(("live:nfl", "record:nfl", "zeno:nfl"))], got
    assert got["fills"][-3:] == ["live:cfb-live", "record:cfb-rec", "zeno:cfb-rec-zeno"], got


def test_a_clock_redraw_never_cancels_a_full_render():
    """A full render still waiting on the record when the live clock ticks:
    the record and Zeno must still be filled, or those zones stay empty."""
    got = _race("""
      plan.live = [[60, "full-live"], [5, "tick-live"]];
      plan.record = [[60, "rec"]];
      renderHomeDeck(); await sleep(10); renderHomeDeck({ still: true });""")
    if got is None:
        return
    assert "record:rec" in got["fills"] and "zeno:rec-zeno" in got["fills"], got
    assert "live:tick-live" in got["fills"], "the redraw is the same board: its newer clock may show"


def test_a_clock_redraw_overtaken_by_a_full_render_fills_nothing():
    got = _race("""
      plan.live = [[80, "tick-live"], [5, "full-live"]];
      plan.record = [[5, "rec"]];
      renderHomeDeck({ still: true }); await sleep(10); renderHomeDeck();""")
    if got is None:
        return
    assert got["fills"] == ["live:full-live", "record:rec", "zeno:rec-zeno"], got
    assert got["armed"] == 1


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
