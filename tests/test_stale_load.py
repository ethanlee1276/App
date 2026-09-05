"""A load that lands after the league changed is abandoned, not drawn.

Ethan, 2026-09-05: "MLB live tab is showing nfl edge and most likely
bets and CFB live bets are showing mlb."

Every board's open-bet tracker is filtered by sport in SQL, the server
maps each sport to its own file and cache key, and every assignment to
`state.data` in `load()` is identity-guarded (tests/test_board_identity
.py). So an MLB tab drawing NFL rows means an NFL load that finished
AFTER the button moved to MLB: the auto-refresh had one in flight, the
league switch started another, and whichever answered last won. The
8 MB MLB board is the slow one, which is why the CFB tab wore baseball.

Two guards, pinned here. `load()` captures the league it was asked for
and abandons its result at every await if another league is in force
when it lands. `renderAll()` refuses to draw a slate whose recorded
board is not the current league's, so no other writer can put one
league's picks under another's name either.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_load_remembers_which_league_asked():
    body = _fn("load")
    assert "const asked = state.sport;" in body
    assert "const overtaken = () => state.sport !== asked;" in body
    # Captured BEFORE the first await, or it would read the new league.
    assert body.index("const asked = state.sport;") < body.index("await fetch(")


def test_every_await_in_the_load_is_followed_by_the_check():
    """Six awaits stand between asking and drawing — the API fetch, its
    body, the fallback fetch, its body — plus the two catch paths and the
    final render. Each is a place the league can have moved."""
    body = _fn("load")
    assert body.count("if (overtaken()) return;") >= 6, body.count("if (overtaken()) return;")
    # The check sits between the fetch and any assignment to the slate.
    for m in re.finditer(r"await fetch\(", body):
        after = body[m.end():m.end() + 400]
        assert "if (overtaken()) return;" in after, after[:120]
    # And no assignment to state.data happens before a check.
    first_assign = body.index("state.data = ")
    assert body.index("if (overtaken()) return;") < first_assign


def test_the_render_is_the_last_thing_gated():
    body = _fn("load")
    i = body.index("renderAll();")
    assert "if (overtaken()) return;" in body[i - 60:i], \
        "an abandoned load must not render the league it was asked for"


def test_render_all_refuses_a_board_that_is_not_this_leagues():
    body = _fn("renderAll")
    assert "const _meta = SPORT_META[state.sport];" in body
    assert "if (_meta && _boardFor && _boardFor !== _meta.api) return;" in body
    # Before the first section is drawn.
    assert body.index("_boardFor !== _meta.api") < body.index("renderLivePicks();")


def test_the_identity_guards_are_still_there():
    """This sits ON TOP of the 2026-08-25 fix, not instead of it."""
    body = _fn("load")
    assert "const holding = state.data && _boardFor === meta.api;" in body
    assert body.count("_boardFor = meta.api;") >= 3


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
