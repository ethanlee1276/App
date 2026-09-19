"""A riding row says when the bet was placed and which day its game is.

Ethan, 2026-09-05, with a screenshot of twenty college bets "still
riding": "Can we check to see if these picks on the CFB page are old or
new." The row printed the placed price and the current one and nothing
about WHEN — and the tracker never read the journal's timestamp at all,
so the page could not have said. Now every tracker row carries
`placed_at` (the journal's UTC stamp) and `date` (the day it is filed
under), the riding row reads "placed Thu 5:12 PM · game Sat, Sep 5 ·
3:30 PM ET" in the reader's zone, and the Live tab's open-bet rows say
when beside the price they were placed at.

The clock is exercised for real in node under a deliberately different
system zone (skipped without node): the stamp must parse as UTC and
render in the chosen zone, weekday included.
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

from engine.livepicks import TRACKER_COLS, assemble_live_picks   # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
SWEAT = (ROOT / "engine" / "sweat.py").read_text()
MLB_BUILD = (ROOT / "mlb_build.py").read_text()

GAME = {"home": "PHI", "away": "CHC", "game_number": 1,
        "date": "2026-09-05", "kickoff": "2026-09-05T19:30:00Z",
        "live": {"state": "scheduled"}}
PICK = {"player": "Bryce Harper", "team": "PHI", "opponent": "CHC",
        "market": "home_runs", "market_label": "Home Runs"}
BET = {"player": "Bryce Harper", "market": "home_runs", "side": "OVER",
       "line": 0.5, "odds": 400, "stake_units": 0.19,
       "date": "2026-09-04", "ts": "2026-09-03T21:12:00"}


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the engine ------------------------------------------------------------------
def test_every_tracker_query_reads_the_placement_time():
    assert TRACKER_COLS.endswith("hit_prob, ts"), TRACKER_COLS
    # The two other copies of the same column list, for the fast clock
    # and the baseball board.
    assert '"category, hit_prob, ts")' in SWEAT, "the sweat clock's rows carry no placement time"
    assert '"category, hit_prob, ts")' in MLB_BUILD, "the MLB board's rows carry no placement time"


def test_a_mapped_row_and_an_unmapped_row_both_say_when():
    mapped = assemble_live_picks([BET], [], [GAME], {}, [PICK])
    assert len(mapped) == 1 and mapped[0]["status"] != "unmapped"
    assert mapped[0]["placed_at"] == "2026-09-03T21:12:00"
    assert mapped[0]["date"] == "2026-09-04", "the journal's filing date"
    assert mapped[0]["game"]["date"] == "2026-09-05", "the game's own date stays in `game`"
    unmapped = assemble_live_picks([BET], [], [], {})
    assert unmapped[0]["status"] == "unmapped"
    assert unmapped[0]["placed_at"] == "2026-09-03T21:12:00"
    assert unmapped[0]["date"] == "2026-09-04"
    old = dict(BET); del old["ts"]; del old["date"]
    row = assemble_live_picks([old], [], [], {})[0]
    assert row["placed_at"] == "" and row["date"] == "", "present and empty on an old row"


# --- the page --------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join(_fn(n) for n in ("escapeHtml", "tzOpts", "tzTime", "placedStamp",
                                     "formatGameDate", "formatKickoff", "whenLabel", "ridingWhen"))
    prog = f"""
      const settings = () => ({{ tz: "America/New_York" }});
      {src}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    env = dict(os.environ, TZ="America/Chicago", LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30, env=env)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_stamp_is_utc_read_in_the_chosen_zone_weekday_included():
    got = _node("""
      return {
        thu: placedStamp("2026-09-03T21:12:00"),
        thuZ: placedStamp("2026-09-03T21:12:00Z"),
        midnight: placedStamp("2026-09-04T04:30:00"),
        empty: placedStamp(""), none: placedStamp(null), junk: placedStamp("last tuesday"),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["thu"] == "Thu 5:12 PM", got
    assert got["thuZ"] == "Thu 5:12 PM", "a stamp that already says Z reads the same"
    # 04:30 UTC is 12:30 AM Friday in New York and 11:30 PM Thursday in
    # Chicago, the system zone here: the weekday has to follow the clock.
    assert got["midnight"] == "Fri 12:30 AM", got
    assert got["empty"] == "" and got["none"] == "" and got["junk"] == ""


def test_the_row_reads_placed_and_game_and_prefers_the_games_own_date():
    got = _node("""
      const strip = (h) => h.replace(/<[^>]+>/g, "");
      return {
        both: strip(ridingWhen({placed_at: "2026-09-03T21:12:00", date: "2026-09-04",
                                game: {date: "2026-09-05", kickoff: "15:30"}})),
        unmapped: strip(ridingWhen({placed_at: "2026-09-03T21:12:00", date: "2026-09-04", game: {}})),
        gameOnly: strip(ridingWhen({placed_at: "", game: {date: "2026-09-05", kickoff: ""}})),
        nothing: ridingWhen({}), none: ridingWhen(null),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["both"] == "placed Thu 5:12 PM · game Sat, Sep 5 · 3:30 PM ET", got["both"]
    assert got["unmapped"] == "placed Thu 5:12 PM · game Fri, Sep 4", "the filing date stands in"
    assert got["gameOnly"] == "game Sat, Sep 5"
    assert got["nothing"] == "" and got["none"] == ""


def test_the_riding_row_and_the_live_tab_rows_wear_it():
    i = APP.index("const ridingRow =")
    row = APP[i:APP.index("(ridingAttrs(b));", i)]
    assert "${ridingWhen(b)}" in row, "the riding row no longer says when"
    assert row.index("</strong>") < row.index("${ridingWhen(b)}") < row.index('<span class="pick-moved">'), \
        "the dates sit between the bet and the price note"
    j = APP.index("const rowHTML = (r) => ((door, placed) =>")
    live = APP[j:APP.index("(ridingAttrs(r), placedStamp(r.placed_at));", j)]
    assert "placed ? ` · ${escapeHtml(placed)}` : \"\"" in live, "the Live tab rows dropped the stamp"
    assert "placed ${american(r.odds)}" in live, "and still say the price"
    assert APP.count("toLocaleTimeString") == 1, "the stamp's clock must go through tzTime"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
