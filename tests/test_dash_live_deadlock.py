"""A game that kicked off ninety minutes ago, drawn as upcoming.

Ethan, 2026-09-10, 9:55pm ET, looking at the Home page an hour and a
half after an 8:20 kickoff: "the patriots game is still not showing it's
live." The card read "Wed, Sep 9 · 8:20 PM ET" with no score and no LIVE
mark, while `web/data/live_nfl.json` on the droplet said, at that
moment, sixteen games, ONE LIVE, one deep play-by-play file, two seconds
old.

THE DASHBOARD WAS IN A DEADLOCK WITH ITSELF. `renderGames` merges the
fast scoreboard into the board's cards, but it merges whatever
`pbpStripGames` last left in `_pbpStrip` — it does not fetch. The two
things that fetched were both guarded the same way:

    if (games.some(live) && LIVE_FAST[sport]) pbpStripGames(sport)
    armDashLive: if (!state.data.games.some(live)) return;

Both ask "is a game live?" of the MODEL BOARD, which is rebuilt on the
45-minute cycle. So the fast file was only fetched once a game was
already known to be live, and the only source that could know that was
the fast file. Until the slow board caught up, nothing asked.

This is the same shape as the Live tab bug fixed hours earlier the same
night — the fast path gated behind the slow one — in a different
function, which is why that fix did not reach this screen.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10)
            for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n/*:")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _render_games():
    """`renderGames` whole — anchored on its own last statement, never a
    byte count. Three fixed windows in this neighbourhood broke on a
    comment earlier tonight; not adding a fourth."""
    i = APP.index("function renderGames(")
    return APP[i:APP.index("armDashLive(fastLiveStamp(games));", i) + 60]


def _code(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"//[^\n]*", "", js)


def test_the_board_no_longer_decides_whether_we_ask_the_scoreboard():
    """THE DEADLOCK ITSELF. The fetch must not be conditional on a live
    game, because the fetch is how a live game is discovered."""
    body = _code(_render_games())
    assert "pbpStripGames(state.sport)" in body, "the fast file is never fetched"
    fetch = body.index("pbpStripGames(state.sport)")
    guard = body.rindex("if (", 0, fetch)
    condition = body[guard:fetch]
    assert "some(" not in condition, \
        f"the fetch is still gated on a game already being live: {condition.strip()!r}"
    assert "LIVE_FAST[state.sport]" in condition, condition


def test_the_fast_clock_arms_on_the_merged_state_not_the_board():
    """Fixing the fetch and leaving this would draw the score once and
    then freeze it: the 16-second clock still would not start."""
    body = _code(_fn("armDashLive"))
    assert "dashLiveGames()" in body, body
    assert "(state.data || {}).games" not in body, \
        "the clock still asks the model board whether anything is live"


def test_one_merged_view_serves_every_reader():
    """Three readers need the same answer — the cards, the redraw check
    and the clock — and a fourth copy of the merge is how they drift."""
    assert "function dashLiveGames()" in APP
    body = _code(_fn("dashLiveGames"))
    assert "mergeFastLive(" in body and "_pbpStrip.games" in body, body
    # renderGames reads it rather than open-coding the merge again.
    rg = _code(_render_games())
    assert "const games = dashLiveGames();" in rg, rg[:400]
    assert rg.count("mergeFastLive(") == 0, "renderGames merges a second time"


def test_the_redraw_cannot_loop():
    """`renderGames` re-entering itself needs a fixed point. The second
    pass hits `pbpStripGames`' 15-second cache, computes the same stamp
    and stops — so the comparison must be against a stamp taken BEFORE
    the fetch, and the redraw must be conditional on it changing."""
    body = _code(_render_games())
    i = body.index("pbpStripGames(state.sport)")
    before = body[:i]
    after = body[i:]
    assert "const seen = fastLiveStamp(games);" in before, before[-300:]
    # The unchanged case leaves without redrawing — that is the fixed
    # point. (Spelled as an early return since the redraw grew a second
    # statement; the contract is the comparison, not its punctuation.)
    assert "=== seen) return;" in after, after[:500]
    # Unconditional re-entry would spin forever.
    assert not re.search(r"then\(\(\)\s*=>\s*\{?\s*renderGames\(\);", after), after[:400]


def test_the_rail_draws_the_same_live_games_as_the_cards():
    """Ethan, 2026-09-10, one screenshot: the stadium card reads LIVE Q3
    8:11, 10-0, "4th & 5 at NE 11", and the LIVE NOW panel six inches to
    its right reads "No games in progress right now."

    `renderRail` read `state.data.games` — the raw model board — while
    the strip beside it read the merged view. Its own docstring claimed
    both came from "the same live states the stadium strip draws"."""
    body = _code(_fn("renderRail"))
    assert "dashLiveGames()" in body, "the rail still reads the raw board"
    assert 'const games = (d.games || []).filter' not in body, body[:600]


def test_the_redraw_is_bounded_at_one_not_merely_convergent():
    """A re-render that can re-arm itself is one bad input away from
    spinning the tab, and a spinning tab reads as "the site won't
    load". The stamp check makes it converge; the flag makes it
    impossible."""
    body = _code(_render_games())
    assert "!_dashRedrawing" in body, "the warm can re-enter itself"
    assert "_dashRedrawing = true;" in body, body[-700:]
    assert "finally { _dashRedrawing = false; }" in body, \
        "an early return would leave the warm switched off for good"
    # Cleared on rejection too, or one failed fetch kills it for the session.
    assert "() => { _dashRedrawing = false; }" in body, body[-700:]
    assert "let _dashRedrawing = false;" in APP


def test_no_reader_asks_the_45_MINUTE_BOARD_whether_a_game_is_live():
    """THE SWEEP, because finding these one at a time did not work.

    Five separate readers asked `state.data.games` — the model board on
    its 45-minute cycle — whether anything was in progress, and each was
    found only when a symptom reached Ethan: the cards (the game drawn
    as upcoming ninety minutes after kickoff), the fast clock (the score
    would have frozen), the rail ("No games in progress" beside a LIVE
    card), `findGame` (the play-by-play door opening the game page
    instead), and the auto-refresh (the poll that would have noticed
    never started). Same bug, five addresses, three separate pushes.

    So this is enumerated rather than remembered: any expression that
    decides a game is live may not source it from the board."""
    live = [(n, ln) for n, ln in enumerate(APP.splitlines(), 1)
            if 'state === "live"' in ln]
    assert len(live) > 10, f"only {len(live)} live checks found — did the spelling change?"
    for n, ln in live:
        assert "state.data" not in ln, f"app.js:{n} asks the raw board: {ln.strip()!r}"
        assert "d.games" not in ln, f"app.js:{n} asks the raw board: {ln.strip()!r}"


def test_the_door_and_the_poll_read_the_merged_view():
    """The two that reach the board through one indirection, which is
    how they survived the sweep above."""
    door = _code(_fn("openGameOrPlays"))
    assert "findGame(gid)" in door, door
    i = APP.index("const findGame = ")
    assert "dashLiveGames()" in APP[i:APP.index(";", i)], APP[i:i + 200]
    poll = _code(_fn("manageAutoRefresh"))
    assert "dashLiveGames().some(" in poll, poll[:400]


def test_the_merge_still_lets_board_only_fields_survive():
    """The fast file carries no odds grid and no win-probability track.
    Wholesale replacement unplugged both in August; this is the guard
    that the fix above did not quietly reintroduce."""
    body = _code(_fn("mergeFastLive"))
    assert "...bg" in body and "...(bg.live || {})" in body, body
    assert "return bg;" in body, "a game the fast file does not know must survive as it was"


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
