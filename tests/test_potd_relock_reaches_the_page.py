"""What `_repoint` did to the card has to reach the reader.

Ethan, 2026-09-16: "pick of the day for mlb isn't showing still but nfl
is showing And so is CFB."

MLB-ONLY RULES OUT most of what was suspected on the first pass — the
paywall, the renderer's error branch and the sign-in state would all hit
three leagues, not one. What IS MLB-shaped is the LOCK: `relock_potd`
only does work when that sport has journaled a Pick of the Day today, and
MLB is the league with the longest record and the one whose card the
whole mechanism was written for.

TWO REAL BUGS FOUND LOOKING FOR IT, and neither is proven to be what he
is seeing — that needs the droplet (docs/WHEN_YOU_ARE_HOME.md block
POTD-MLB). Both are defects on their own terms.

ONE. `potd._repoint` writes three states to say which pick is on screen:
`relocked` (the board moved on; this is the pick the sport locked
earlier today), `off_board` (the row is gone; this is the journal at the
price it was locked at) and `locked` (the board still agrees). THE PAGE
RENDERED NONE OF THEM — the string `relocked` appeared nowhere in
app.js. So a card re-pointed at a morning lock looked exactly like a
fresh recommendation, at a price that may since have run out of the
band, and the blanked case said "No pick today." when the truth was "a
pick was locked today and is no longer anywhere".

That function exists BECAUSE the MLB page spent 2026-09-15 showing one
pick while the record held another. Writing the explanation and not
drawing it leaves the same reader in the same place.

TWO WAS NOT A BUG, AND THE CORRECTION IS THE POINT. I read `cfb_build`'s
POTD block, saw it go straight from `attach` to `_write` where the other
two call `relock_potd`, and added the missing call. It was not missing:
college applies the lock INSIDE `_write`, immediately before
`gate.publish`. Grepping the call sites and not the writer produced a
duplicate, reverted.

What survives from it is the test below, which asks the property of all
three builds — every league re-points at its lock before the file that
IS the card gets written — rather than asking whether a particular line
appears at a particular place.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _render():
    i = JS.index("async function renderPickOfTheDay()")
    return JS[i:JS.index("\n}\n", i)]


# --- the engine still says it -------------------------------------------------
def test_a_lock_that_cannot_be_found_says_so_on_the_card():
    """The state that produced "No pick today." while a pick was on the
    record. `_repoint` has always written the true sentence."""
    card = potd.build([], "mlb", "2026-09-16")
    out = potd.relock(card, [], ("GONE", "moneyline", "OVER", 0.5))
    assert out["pick"] is None
    assert "locked a pick today" in out["relocked"], out.get("relocked")


def test_a_relocked_pick_carries_its_note_and_its_mark():
    row = {"kind": "game", "market": "moneyline", "player": "BBB",
           "team": "BBB", "side": "", "line": 0.0, "odds": -130,
           "book": "DraftKings", "sharp_anchored": True, "sharp_fair": 0.60,
           "home": "BBB", "away": "AAA", "bettable": True, "rank_auc": 0.71}
    from engine.ledger import potd_row_key
    key = potd_row_key(row)
    assert key is not None, "the fixture cannot be keyed"
    card = potd.build([], "mlb", "2026-09-16")
    out = potd.relock(card, [row], tuple(key))
    assert isinstance(out["pick"], dict)
    assert out["pick"]["locked"] is True
    assert "board moved on" in (out.get("relocked") or ""), out.get("relocked")


# --- …and the page draws it ---------------------------------------------------
def test_the_no_pick_card_prefers_the_relock_note_over_the_generic_one():
    """`note` still reads "No pick today: the board had no rows" on a
    blanked card — true of the SELECTION and false about the day. The
    relock sentence is the specific one and goes first."""
    body = _render()
    assert "got.relocked || got.note" in body, \
        "the no-pick card still shows the generic note over the relock reason"


def test_the_pick_card_says_when_it_is_showing_an_earlier_lock():
    """A reader is entitled to know they are looking at a claim made
    hours ago rather than a recommendation made now — the price may have
    run out of the band since."""
    body = _render()
    assert "relockNote" in body, "the card never mentions the lock"
    for state in ("got.relocked", "pick.off_board", "pick.locked"):
        assert state in body, f"the card ignores {state}"
    assert "journal at the price it was locked at" in body


def test_the_note_is_escaped_like_every_other_string_on_this_card():
    body = _render()
    i = body.index("relockNote")
    assert "escapeHtml(relockNote)" in body[i:i + 600], body[i:i + 300]


# --- every league asks the lock ----------------------------------------------
def test_all_three_football_and_baseball_builds_relock_before_publishing():
    """A rule applied on two of three paths is not a rule — this
    codebase's most repeated bug, and college was the path missing."""
    for name in ("nfl_build.py", "mlb_build.py", "cfb_build.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "relock_potd(" in src, f"{name} never re-points at its lock"


def test_the_relock_runs_before_the_board_is_written():
    """"IT RUNS BEFORE PUBLISH BECAUSE THE FILE IS THE CARD" — a swap
    made after the write never reaches the page.

    Asked against the PUBLISH that actually ships the card, which for
    college is `gate.publish` inside `_write`. Comparing against the
    first `_write(out, args.out)` in that file measures nothing: there
    are five, and four of them are progressive writes that run long
    before the Pick of the Day is chosen.
    """
    for name in ("nfl_build.py", "mlb_build.py", "cfb_build.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        at = src.index("relock_potd(")
        after = src[at:]
        assert "gate.publish(" in after, \
            f"{name} re-points at its lock and never publishes after it"


def test_the_lock_is_applied_in_exactly_one_place_per_build():
    """Two calls is two places for the rule to live and one of them to
    drift — which is what a first pass at this added to college, having
    read the call sites and not the writer."""
    for name in ("nfl_build.py", "mlb_build.py", "cfb_build.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        n = src.count("relock_potd(")
        assert n == 1, f"{name} calls relock_potd {n} times"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
