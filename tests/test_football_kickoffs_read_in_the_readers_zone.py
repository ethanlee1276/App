"""Football's kickoffs read in the reader's own zone (Ethan's answer to decision 13, 21 November: "yes").

The NFL board carries a kickoff as the game's Eastern day ("2026-11-22") and an Eastern clock ("13:00"),
so every NFL time on the site read "1:00 PM ET" while every other league's start read in the reader's
zone. The day and the clock together are one instant (app.js etInstant: Eastern is five hours behind UTC
in winter, four in summer, and New York's own clock says which); the game cards, the game page, the
empty board, the Live tab's quiet line, a player's upcoming game, the inactives note and the slip grader
all say it in the reader's zone now. A clock with no day is no instant and keeps its "ET".

Exercised for real in node (skipped without node), under a system zone that is neither the chosen one
nor Eastern.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
SLIP = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def _slip_kick():
    i = SLIP.index("  const kick = (s) => {")
    return SLIP[i:SLIP.index("\n  };\n", i) + 5]


def _node(js, tz="America/Los_Angeles", helpers=True):
    node = shutil.which("node")
    if not node:
        return None
    names = ("tzOpts", "tzTime", "formatGameDate", "formatKickoff", "etInstant", "kickInstant", "kickClock",
             "whenLabel", "firstKickOf")
    src = "\n".join(_fn(n) for n in names) if helpers else ""
    prog = f"""
      const settings = () => ({{ tz: {json.dumps(tz)} }});
      const escapeHtml = (s) => String(s);
      {src}
      {_fn("inactivesNote", DETAIL)}
      {_slip_kick()}
      let state = {{ sport: "nfl" }};
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    env = dict(os.environ, TZ="Asia/Tokyo", LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30, env=env)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_an_eastern_day_and_clock_are_one_instant_in_winter_and_summer():
    got = _node("""return [etInstant("2026-11-22", "13:00"), etInstant("2026-09-05", "15:30"),
                           etInstant("2026-11-01", "13:00"), etInstant("2026-03-08", "13:00"),
                           etInstant("2026-11-22", ""), etInstant("", "13:00"), etInstant("2026-11-22", "24:00"),
                           etInstant("2026-11-22", "2026-11-22T18:00Z")].map((t) => Number.isFinite(t)
                             ? new Date(t).toISOString() : null);""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got[:4] == ["2026-11-22T18:00:00.000Z", "2026-09-05T19:30:00.000Z",
                       "2026-11-01T18:00:00.000Z", "2026-03-08T17:00:00.000Z"], \
        "five hours in winter, four in summer, and each change-over Sunday's afternoon on its own side"
    assert got[4:] == [None, None, None, None], "no day, no clock, no real clock, or an ISO stamp: no Eastern reading"


def test_the_game_card_the_board_and_a_players_next_game_say_the_readers_clock():
    got = _node("""
      const games = [{ date: "2026-11-22", kickoff: "13:00" }, { date: "2026-11-19", kickoff: "20:15" },
                     { kickoff: "2026-11-21T17:00Z" }];
      return { card: whenLabel("2026-11-23", "20:15"), first: firstKickOf(games),
               firstUndated: firstKickOf([{ kickoff: "16:25" }, { kickoff: "13:00" }]), none: firstKickOf([]),
               clock: kickClock("2026-11-22", "16:25"), clockNoDay: kickClock("", "16:25"),
               mlb: kickClock("2026-09-23", "2026-09-23T23:10:00Z") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["card"] == "Mon, Nov 23 · 5:15 PM", "Monday night's 8:15 PM Eastern, read in Los Angeles"
    assert got["first"] == "5:15 PM", "Thursday's game is the first start, not the smallest clock text"
    assert got["firstUndated"] == "1:00 PM ET" and got["none"] == "", "with no day the old reading stands"
    assert got["clock"] == "1:25 PM" and got["clockNoDay"] == "4:25 PM ET"
    assert got["mlb"] == "4:10 PM", "an ISO start is read as it always was"


def test_the_inactives_note_and_the_slip_grader_read_it_too():
    got = _node("""
      const g = { date: "2026-11-22", kickoff: "13:00", live: { state: "scheduled" } };
      return { inactives: inactivesNote(g), started: inactivesNote({ ...g, live: { state: "live" } }),
               slip: kick("2026-11-23 20:15"), college: kick("2026-11-21 2026-11-21T17:00Z"), junk: kick("soon") };""",
                tz="Europe/London")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["inactives"] == ' · <span class="gp-inactives">inactives 4:30 PM</span>', got["inactives"]
    assert got["started"] == "", "a game under way has no inactives ahead"
    assert got["slip"] == "Tue 1:15 AM", "past midnight in London: the day moves with the clock"
    assert got["college"] == "Sat 5:00 PM", "college football's ISO start, which the slip read as nothing"
    assert got["junk"] == ""
    # Without the page's helpers (each script is tried alone) the Eastern reading stands, as it was.
    old = _node("""return [inactivesNote({ date: "2026-11-22", kickoff: "13:00" }), kick("2026-11-23 20:15")];""",
                helpers=False)
    assert old == [' · <span class="gp-inactives">inactives 11:30 AM ET</span>', "Mon 8:15 PM ET"], old


def test_every_place_that_printed_et_on_a_dated_kickoff_now_asks_the_instant():
    assert "kickClock" in APP and "${escapeHtml(whenLabel(up.date, up.kickoff) || up.date || \"\")}" in APP, \
        "a player's upcoming game"
    assert " ET` : \"\"}" not in APP, "no dated kickoff glues on its own ET"
    assert "if (!first) first = firstKickOf((state.data || {}).games);" in APP, "the deck's quiet card"
    assert "return firstKickOf(((state.data || {}).games || []).filter(notStarted));" in APP
    assert "typeof etInstant === \"function\" ? etInstant(g.date, g.kickoff) : NaN" in DETAIL
    assert "Ethan's answer to decision 13" in APP


if __name__ == "__main__":
    import sys
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
