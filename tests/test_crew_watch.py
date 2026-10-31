"""Crew watch: an NFL game's flags, live, against its referee's games, and a
baseball game's plate umpire, call by call
(docs/IDEAS.md, the live game list's tenth; built 2026-10-28, runbook FX).

What these hold:

  * the football page's rail carries the card, under the pressure card, and
    only for the NFL, only once the board names the referee
    (engine/nflrefs on the board's game), and only live or final;
  * the flags are every play the game's file marks a penalty on, counted
    once across the drives and the last plays;
  * the pace shows once a quarter is played and stops at the final; his
    games' average is beside the league's, a thin record says how thin, and
    the caveat the game report gives him rides with it.
  * baseball's half is the plate umpire's zone: every called pitch the
    tracking located, against the rulebook zone (the batter's own top and
    bottom, to the edge of the ball), the misses, and whom they went
    against; swings, the pitch clock's balls and unlocated pitches are not
    calls.

Run directly: `python3 tests/test_crew_watch.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_card_rides_the_football_rail():
    rail = DETAIL[DETAIL.index('<aside class="pbp-rail">'):]
    rail = rail[:rail.index("</aside>")]
    assert "${pbpPressureHTML(d, league, boardGame)}\n        ${pbpCrewHTML(d, league, boardGame)}" in rail
    fn = _fn(DETAIL, "pbpCrewHTML")
    assert 'if (league !== "nfl" || !o.referee || (lv.state !== "live" && lv.state !== "final")) return "";' in fn
    assert "escapeHtml(o.referee)" in fn and "escapeHtml(avg)" in fn


def _run(cases):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const UMP_R = 1.45 / 12, UMP_HALF = 17 / 24;
      {_fn(DETAIL, "pbpCrewHTML")}
      {_fn(DETAIL, "pbpUmpHTML")}
      const cases = {json.dumps(cases)};
      console.log(JSON.stringify(cases.map(([d, league, bg]) => pbpCrewHTML(d, league, bg))));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip() for h in json.loads(out.stdout)]


def _doc(period="Q3", clock="7:30", state="live"):
    drive = lambda ids, pens: {"plays": [{"id": i, "penalty": i in pens} for i in ids]}  # noqa: E731
    return {"live": {"state": state, "period": period, "clock": clock},
            "drives": [drive(["a1", "a2", "a3"], {"a2"}), drive(["b1", "b2"], {"b1", "b2"}),
                       drive(["c1", "c2"], {"c2"})],
            "plays": [{"id": "c1", "penalty": False}, {"id": "c2", "penalty": True}]}


BOARD = {"officials": {"referee": "Shawn Hochuli", "record": {"games": 40, "flags": 13.4},
                       "league": {"flags": 12.1}}}


def test_the_flags_the_pace_and_his_games():
    got = _run([
        [_doc(), "nfl", BOARD],                                   # 2.5 quarters: 4 flags, pace 6.4 -> 6
        [_doc(period="Q1", clock="10:00"), "nfl", BOARD],         # under a quarter: no pace yet
        [_doc(state="final", period="Final", clock=""), "nfl", BOARD],
        [_doc(), "nfl", {"officials": {"referee": "New Ref", "record": {"games": 3, "flags": 15.0},
                                       "league": {"flags": 12.1}}}],
        [_doc(), "nfl", {}],                                      # no referee named
        [_doc(), "cfb", BOARD],                                   # the NFL only
        [_doc(state="pre"), "nfl", BOARD],
    ])
    if got is None:
        print("      (skipped: no node)")
        return
    live, early, final, thin, none, college, pre = got
    assert live.startswith("Crew watch Shawn Hochuli’s crew 4 flags so far · on pace for 6"), live
    assert "His games average 13.4 penalties (league 12.1)." in live and "over 40 games" not in live
    assert "closing line" in live, "the report's caveat rides with it"
    assert "4 flags so far" in early and "on pace" not in early, early
    assert "4 flags in the game" in final and "on pace" not in final, final
    assert "His games average 15.0 penalties (league 12.1) over 3 games." in thin, thin
    assert none == college == pre == "", (none, college, pre)


def _pitch(code, px, pz, half="T", sz=(3.5, 1.6)):
    return {"kind": "pitch", "code": code, "px": px, "pz": pz, "half": half, "sz": list(sz)}


def test_the_plate_umpire_s_zone_called_pitch_by_pitch():
    """Baseball's half: the rulebook zone with the batter's own top and
    bottom, to the edge of the ball (1.45 in), and who each miss cost."""
    edge = 17 / 24 + 1.45 / 12
    events = [
        _pitch("C", 0.0, 2.5),                  # a strike, called one
        _pitch("B", 1.2, 2.5),                  # a ball, called one
        _pitch("C", edge + 0.05, 2.5),          # just off the edge, called a strike: costs the hitters (SF)
        _pitch("B", edge - 0.05, 2.5, "B"),     # just touching, called a ball: costs the pitchers (SF fields)
        _pitch("*B", 0.1, 1.55, "B"),           # in the dirt but its top edge in the zone: a miss too
        _pitch("C", 0.0, 3.5 + 0.1),            # over the top by less than the ball: right
        _pitch("B", 0.0, 2.0, "T"),             # down the middle, called a ball: costs the pitchers (ATL fields)
        _pitch("S", 2.0, 5.0),                  # swung at: not a call
        _pitch("V", 0.0, 2.5),                  # the pitch clock's ball: not a call
        {"kind": "pitch", "code": "C"},         # not located: not counted
        {"kind": "atbat", "event": "Strikeout"},
    ]
    doc = {"live": {"state": "live"}, "away": "SF", "home": "ATL", "events": events}
    got = _run([[doc, "mlb", {}], [{"live": {"state": "live"}, "away": "SF", "home": "ATL", "events": []}, "mlb", {}],
                [dict(doc, live={"state": "pre"}), "mlb", {}]])
    if got is None:
        return
    live, empty, pre = got
    assert live.startswith("Umpire watch the plate umpire’s zone 4 missed of 7 called pitches · 43% right"), live
    assert "Against SF 3, against ATL 1." in live, live
    assert "no season of an umpire’s calls" in live
    assert empty == pre == "", (empty, pre)


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
