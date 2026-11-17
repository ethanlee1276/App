"""A goal flashes on the live hockey score (2026-11-17).

Football's touchdown flash (detail.js gpTouchdownSeen; Ethan, 16 November:
"Yes"), on the hockey page (js/rinkcast.js goalSeen, run once a draw by the
scoreboard). When one side's score rises between two draws while the game is
live and the page is on screen, that side's score pulses gold with GOAL over
it for GOAL_MS, announced to a screen reader. Never on opening a game or
coming back to it, never for a draw while the tab was hidden, never a
shootout's deciding goal. A redraw mid-flash carries the animation on from
where it was (--td-t). With reduced motion it is a tint and a fade.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

RC = (ROOT / "web" / "js" / "rinkcast.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "rinkcast.css").read_text(encoding="utf-8")


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


NHL = _Harness("test_the_nhl_live_page")

#: One game's draws: `seen(...)` is one draw of the page.
GAME = r"""
  const doc = (a, h, state, period, ev) => ({ event_id: ev || "2026020123", home: "BOS", away: "NYR",
    live: { state: state || "live", away_score: a, home_score: h, period: period || "P2", clock: "11:02" } });
  const seen = (d, t) => { const f = Q.goalSeen(d, t); return f ? { side: f.side, start: f.start } : null; };
"""


def _run(body):
    return NHL._node(GAME + body)


def test_a_goal_seen_happen_flashes_the_scoring_side():
    got = _run("""
      const out = [];
      out.push(seen(doc(0, 1), 1000));                                // the page opens: never a flash
      out.push(seen(doc(1, 1), 13000));                               // the Rangers score, seen happen
      const d = doc(1, 1);
      out.push(Q.goalFor(d, "away", 14000), Q.goalFor(d, "home", 14000), Q.goalFor(d, "away", 13000 + Q.GOAL_MS + 1));
      return out;
    """)
    if got is None:
        return
    first, flash, away_ms, home_ms, after = got
    assert first is None, "opening a game never flashes"
    assert flash == {"side": "away", "start": 13000}, flash
    assert away_ms == 1000 and home_ms is None, (away_ms, home_ms)
    assert after is None, "gone after GOAL_MS"


def test_a_return_a_shootout_and_a_new_game_do_not_flash():
    got = _run("""
      const out = [];
      seen(doc(0, 0), 0);
      out.push(seen(doc(0, 1), 300000));                               // five minutes on: a return, not a moment
      seen(doc(2, 2, "live", "OT"), 700000);                           // another return, into overtime
      out.push(seen(doc(2, 3, "final", "SO"), 710000));                // the shootout settles it: no goal flash
      seen(doc(0, 0, "live", "P1", "B"), 800000);                       // another game opens
      out.push(seen(doc(0, 1, "live", "P1", "B"), 812000));            // and its own goal does flash
      return out;
    """)
    if got is None:
        return
    ret, so, other = got
    assert ret is None and so is None, (ret, so)
    assert other == {"side": "home", "start": 812000}, other


def test_an_overtime_winner_flashes_as_the_game_ends():
    """Sudden death: the goal and the final arrive together, and that goal is a goal."""
    got = _run("""
      seen(doc(2, 2, "live", "OT"), 0);
      return seen(doc(3, 2, "final", "OT"), 9000);
    """)
    if got is None:
        return
    assert got == {"side": "away", "start": 9000}, got


def test_the_score_wears_it_and_says_it():
    assert "goalSeen(d);" in RC and 'class="gp-td-word" role="status"' in RC
    assert 'aria-label="${esc(`Goal, ${nick}`)}">Goal</span>' in RC
    assert '" rc-goal" : ""}"${goal != null ? ` style="--td-t:-${Math.round(goal)}ms"` : ""}' in RC
    assert ".rc-goal .rc-pts { animation: gp-td-pulse 1.5s ease-out 3 both;" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS[CSS.index(".rc-goal .rc-team"):]


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
