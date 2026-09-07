"""The ballpark cards read the fast clock too.

Ethan, 2026-09-07, with two screenshots taken at the same moment: the
dashboard card showed one runner, the game centre showed two. "So
something is delayed."

It was. The board file behind the dashboard cards is rebuilt on the
minutes-long cycle — the header said "Updated 5m ago" — while the game
centre and the Live tab read the fast scoreboard. The bases, the outs
and the score on a ballpark card were therefore minutes behind the same
numbers one tap away. The fast rows were already fetched for the league
so the play-by-play door could open instantly; they were never merged
into the cards. Now they are, with the same merge the Live tab uses, and
the cards re-read the scoreboard while a game is on, redrawing only when
the live state actually moved.

Run directly: `python3 tests/test_dashboard_live_merge.py`
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
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n//")]
    return APP[i:min([e for e in ends if e != -1])]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([_fn("mergeFastLive"), _fn("fastLiveStamp")])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src + "\n" + js); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


BOARD = ('[{away:"WSH",home:"SD",line_track:[1,2,3],'
         'live:{state:"live",home_score:1,away_score:0,period:"Top 3rd",outs:1,bases:[1]}},'
         '{away:"STL",home:"SF",live:{state:"scheduled"}}]')
FAST = ('[{away:"WSH",home:"SD",game_pk:823254,'
        'live:{state:"live",home_score:1,away_score:0,period:"Top 3rd",outs:1,bases:[2,3],balls:1,strikes:1}}]')


def test_fast_fields_win_and_board_only_fields_survive():
    got = _node(f"const m = mergeFastLive({BOARD}, {FAST}); console.log(JSON.stringify(m));")
    if got is None:
        return
    sd, sf = got
    assert sd["live"]["bases"] == [2, 3], sd["live"]
    assert sd["live"]["balls"] == 1 and sd["live"]["outs"] == 1
    assert sd["line_track"] == [1, 2, 3], "the board's own field was dropped"
    assert "game_pk" not in sd, "the merge is of `live`, not of the whole row"
    assert sf == {"away": "STL", "home": "SF", "live": {"state": "scheduled"}}, sf


def test_no_fast_rows_leaves_the_board_exactly_as_it_was():
    got = _node(f"const b = {BOARD}; console.log(JSON.stringify(["
               f"mergeFastLive(b, []), mergeFastLive(b, null), mergeFastLive(b, [{{away:'SD',home:'WSH',live:{{bases:[3]}}}}])]));")
    if got is None:
        return
    for m in got:
        assert m[0]["live"]["bases"] == [1], m[0]["live"]
    # A pair the other way round is a different game, not this one.


def test_the_stamp_moves_on_a_runner_and_not_on_a_board_field():
    got = _node(f"""
      const b = {BOARD};
      const a = fastLiveStamp(b);
      // ONLY the bases move here — a fixture that also moved the count
      // would let a stamp that ignores runners pass on the count alone.
      const c = fastLiveStamp(mergeFastLive(b, [{{away:"WSH",home:"SD",live:{{bases:[2,3]}}}}]));
      const d = fastLiveStamp(b.map((g) => ({{...g, line_track: [9, 9]}})));
      const e = fastLiveStamp(mergeFastLive(b, [{{away:"WSH",home:"SD",live:{{outs:2}}}}]));
      console.log(JSON.stringify({{same_board_field: a === d, runner_moved: a !== c, out_moved: a !== e}}));""")
    if got is None:
        return
    assert got == {"same_board_field": True, "runner_moved": True, "out_moved": True}, got


def test_the_dashboard_merges_and_re_arms_only_on_a_change():
    src = _fn("renderGames")
    assert "mergeFastLive([...(state.data.games || [])]" in src
    assert "_pbpStrip.league === state.sport ? _pbpStrip.games : []" in src
    assert "armDashLive(fastLiveStamp(games))" in src
    arm = _fn("armDashLive")
    assert 'state.view !== "recommended"' in arm, "the clock must stop when the dashboard is left"
    assert "LIVE_FAST[state.sport]" in arm
    assert 'state === "live"' in arm, "no live game, no clock"
    assert "if (now !== seen && document.getElementById(\"games\")) renderGames();" in arm
    assert "else armDashLive(seen);" in arm, "a quiet tick must re-arm, not go silent"
    i = APP.index("const DASH_LIVE_EVERY_MS = ")
    every = int(APP[i:APP.index(";", i)].split("=")[1])
    assert every > 15000, "must clear pbpStripGames' 15-second cache or every tick reads the same rows"
    assert "clearTimeout(_dashLiveTimer)" in arm, "two timers would double the redraws"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
