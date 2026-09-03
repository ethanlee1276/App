"""College bought nothing because its cheap half was priced with its dear half.

Ethan, 2026-09-03: *"we still do not show any cfb props or best bets or
anything and there is games today."*

TWO PULLS SHARED ONE PERMISSION. `cfb_build` makes two paid calls and they
are not remotely the same size:

    attach_odds           full-game markets for the ENTIRE board in ONE
                          request — 3 credits, however many games
    attach_player_quotes  one call per game, five markets each — up to 60

`CFB_ODDS_COST` is the SUM (3 + 12*5 = 63) and both halves ran only when
that sum was authorised. So on a budget that could not carry the player
pull, college bought no game lines either: no moneyline, no spread, no
total, and therefore no game bets, nothing on the Most Likely game shelf
and nothing on Best Bets. An empty college page on a day with games.

AND THE SUM WAS ITSELF METERED EIGHT TIMES OVER. `should_refresh`'s first
parameter is an EVENT COUNT that it multiplies by CREDITS_PER_EVENT, and
launch passed 63 credits through it — authorising college against 504. It
erred toward under-spending, so nothing was lost but the board.

MEASURED, on the budget Ethan was actually on that morning (5,000 credits
left, three slates live, so 26 credits to college for the day):

    full pull   63 credits   starves — 0 a day
    lines only   3 credits   every 1.6h — 8 a day

`test_the_cheap_half_fits_on_the_day_the_dear_half_starves` below is that
measurement. What it does NOT do is get college its player props: those
cost 63 credits and a 26-credit day cannot buy them. That is a plan-size
fact, not a bug, and the board says which markets it priced.

Run directly: `python3 tests/test_cfb_lines_tier.py`
"""

import datetime as _date
import json as _json
import os
import sys
import tempfile as _tmp
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ODDS_API_KEY", "test-key-not-a-real-one")

BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def _refresh_cfb_src():
    i = LAUNCH.index("def refresh_cfb(")
    return LAUNCH[i:LAUNCH.index("\ndef ", i + 40)]


# --- the economics ----------------------------------------------------------
def test_the_cheap_half_fits_on_the_day_the_dear_half_starves():
    """THE MEASUREMENT. Reconstructed from the state Ethan's plan was in on
    2026-09-03: 5,000 credits left, three slates live, so college's slice
    of the day is 26 credits. The full pull needs 63 and starves. The game
    lines need 3.

    If this ever inverts, the middle tier has stopped being reachable and
    the college board is back to publishing nothing."""
    from engine import oddsbudget as ob
    import launch

    now = _time.time()
    day = _date.date(2026, 9, 3)
    st = ob.BudgetState(remaining=5000, used=15000, last_refresh_ts=now - 1800)
    st.sport_last_refresh = {"cfb": now - 3 * 3600,
                             "cfb_lines": now - 3 * 3600}
    path = os.path.join(_tmp.mkdtemp(), "b.json")
    with open(path, "w") as fh:
        _json.dump(st.to_dict(), fh)
    state = ob.load(path)

    share = 1 / 3                       # MLB + NFL + CFB all live in September
    allowance = int(ob.daily_allowance(state, day) * share)
    full = ob.refresh_credits(0, launch.CFB_ODDS_COST)
    lines = ob.refresh_credits(0, launch.CFB_LINES_COST)

    assert full > allowance, (
        f"the premise is gone: the full college pull ({full}) now fits in "
        f"the day's {allowance} credits, so there is nothing to fall back "
        f"from")
    assert lines <= allowance, (
        f"the cheap half ({lines}) does not fit in {allowance} either")
    assert allowance // lines >= 5, (
        f"only {allowance // lines} game-line refresh(es) a day for college")

    full_gap = ob.min_seconds_between(0, state, today=day, share=share,
                                      credits=launch.CFB_ODDS_COST)
    lines_gap = ob.min_seconds_between(0, state, today=day, share=share,
                                       credits=launch.CFB_LINES_COST)
    assert full_gap == float("inf"), "the full pull is no longer the starved one"
    assert lines_gap != float("inf"), "the cheap half starves too"
    assert lines_gap <= 3 * 3600, f"college lines only every {lines_gap/3600:.1f}h"


def test_the_two_halves_add_up_to_the_whole():
    """CFB_LINES_COST is the board request inside CFB_ODDS_COST, not a new
    number. If the sum and its part ever stop agreeing, one of them is
    lying about what the meter will bill."""
    import launch
    assert launch.CFB_LINES_COST == 3
    assert launch.CFB_ODDS_COST == launch.CFB_LINES_COST + 12 * 5, (
        "the full cost is no longer the lines pull plus the player calls")


def test_college_is_priced_in_credits_now():
    """63 through the event-count parameter authorised college against 504
    — eight times its real price. `credits` says the number outright."""
    seg = _refresh_cfb_src()
    assert "credits=CFB_ODDS_COST" in seg, \
        "the full pull is still metered as an event count"
    assert "cost=CFB_ODDS_COST" not in seg, \
        "63 credits is being multiplied by CREDITS_PER_EVENT again"
    assert "credits=CFB_LINES_COST" in seg


def test_the_cheap_pull_has_its_own_clock():
    """Sharing "cfb" would have a three-credit pull reset the clock the
    sixty-three-credit one waits on — the same trap LINES_CLOCK avoids for
    the NFL."""
    import launch
    assert launch.CFB_LINES_CLOCK != "cfb"
    assert launch.CFB_LINES_CLOCK != launch.LINES_CLOCK, \
        "college and the NFL share a lines clock, so they starve each other"
    assert "sport=CFB_LINES_CLOCK" in _refresh_cfb_src()


# --- the branch -------------------------------------------------------------
def test_the_middle_tier_is_only_reached_when_the_full_pull_was_declined():
    """It is a FALLBACK. A cycle that already bought the whole thing —
    game lines included — must not pay three credits for numbers it just
    bought."""
    seg = _refresh_cfb_src()
    lines = seg.splitlines()

    def _at(needle):
        for n, ln in enumerate(lines):
            if needle in ln:
                return n, len(ln) - len(ln.lstrip())
        raise AssertionError(f"{needle} is gone from refresh_cfb")

    full, _ = _at('args.append("--odds")')
    elif_n, elif_col = _at("elif _with_odds():")
    mid, mid_col = _at('args.append("--lines-odds")')
    assert full < elif_n < mid, "the branch order changed"
    assert mid_col > elif_col, "--lines-odds is not inside the declined branch"
    body = lines[elif_n + 1:mid]
    assert any("_odds_affordable(" in ln for ln in body), \
        "--lines-odds is appended without asking whether it is affordable"
    for ln in body:
        if ln.strip() and not ln.lstrip().startswith("#"):
            assert len(ln) - len(ln.lstrip()) > elif_col, \
                f"the branch closed before --lines-odds: {ln.strip()[:60]}"


def test_a_lines_pull_that_never_landed_does_not_burn_its_clock():
    seg = _refresh_cfb_src()
    assert "_finish_paid_pull(lines_spend" in seg
    assert "lines_before = _paid_pull_baseline()" in seg


def test_a_raise_in_the_prop_block_reaches_the_board():
    """THE SILENT FAILURE. The block fills `prop_census` and THEN prices,
    in that order, so a raise inside `price_props` leaves a census
    reporting hundreds of markets and `recommendations` still holding the
    empty list it was initialised with.

    From outside that is indistinguishable from an honest "no edge
    anywhere tonight" — and those are not the same fact. Measured on the
    droplet 2026-09-03: 612 markets built, 70 carrying a real book line,
    and a Best Bets page with nothing on it. Ethan: "there isnt even any
    best bets, we should have best bets for cfb."

    The reason has to travel with the BOARD, because the board is what
    anyone looks at. A log line is what nobody is tailing."""
    i = BUILD.index("player props unavailable")
    seg = BUILD[max(0, i - 1600):i + 300]
    assert 'prop_census["error"]' in seg, \
        "a raise in the prop block still leaves no trace on the board"
    assert "extract_tb" in seg, \
        "the message travels without the line that raised it"


def test_the_census_error_is_not_written_on_a_good_build():
    """A census carrying an error and a census carrying zero picks are
    different states, and this field is the only thing separating them."""
    i = BUILD.index('out["recommendations"] = _price_props')
    j = BUILD.index("except Exception as _pexc", i)
    assert 'prop_census["error"]' not in BUILD[i:j], \
        "the error field is set on a successful build too"


# --- the build --------------------------------------------------------------
def test_the_build_takes_the_flag():
    assert '"--lines-odds"' in BUILD, "the flag is gone"


def test_the_flag_buys_the_game_lines():
    """`attach_odds` is the three-credit half. Under --lines-odds it must
    go to the network, not to the cache — that IS the tier."""
    i = BUILD.index("priced, odds_note = attach_odds(")
    seg = BUILD[i:i + 400]
    assert "args.odds or args.lines_odds" in seg, \
        "--lines-odds reads the game lines from cache, so it buys nothing"


def test_the_flag_does_not_buy_a_single_player_call():
    """The whole argument for the tier is that it skips the sixty credits.
    A --lines-odds run that reached the per-event endpoint would cost more
    than the full pull it is standing in for."""
    i = BUILD.index("td_quotes, prop_lines, quotes_note = attach_player_quotes(")
    seg = BUILD[i:i + 300]
    assert "cache_only=not args.odds" in seg, \
        "the player pull is no longer gated on --odds alone"
    assert "lines_odds" not in seg, \
        "--lines-odds reaches the per-event player endpoint"


def test_the_cached_player_quotes_still_reach_the_long_shot_board():
    """--lines-odds buys no scorer quotes, but the last paid pull's are on
    disk. A board that has them and does not draw them is the same silence
    this tier exists to break."""
    i = BUILD.index("from engine.cfb import tds as _tds")
    guard = BUILD.rindex("if args.odds", 0, i)
    assert "args.lines_odds" in BUILD[guard:i], \
        "the long-shot board is skipped on a lines-only cycle"


def test_every_odds_gate_in_the_build_admits_the_new_tier():
    """Three blocks in cfb_build are fenced by "did this cycle have odds".
    A tier that half the fences do not know about produces a board with
    prices on it and boards that read empty — which is the bug, again, one
    level down."""
    import re
    gates = re.findall(r"^    if args\.odds or args\.cached_odds.*$",
                       BUILD, flags=re.M)
    assert gates, "the odds gates moved; re-check this rule"
    for g in gates:
        assert "args.lines_odds" in g, f"gate does not admit the tier: {g.strip()}"


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
