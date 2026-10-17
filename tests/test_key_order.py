"""Which key gets spent next.

Ethan, 2026-08-14, holding two Odds API keys — one with 5,284 credits left
and one freshly upgraded to 100,000: "use up the small key first."

It was already happening, and that is exactly the problem this file
exists for. `get_api_key` walked the ring in ENVIRONMENT-VARIABLE order
(`ODDS_API_KEY`, then `_2`, `_3`) and returned the first key with credits
left; the small key happened to be the primary. Swap the two values in
`secrets.local` — a thing a person does without thinking, while rotating
a key or pasting a new one in — and the behaviour silently inverts,
draining the 100k plan while a nearly-empty one sits untouched.

Nothing would have caught that. The balances still add up, the pulls still
work, and the only symptom is the big plan emptying months early.

WHY SMALLEST-FIRST IS THE POLICY, not just Ethan's preference: plans refill
on their own monthly cycles, so a part-used small plan is the perishable
one — credits left on it at the reset are simply gone. Draining it first
turns the ring into "the big plan, plus whatever the small ones still
had". Draining the big one first throws the small balances away.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as ob                          # noqa: E402
from engine.sources import oddsapi                           # noqa: E402

SMALL, BIG, FRESH = "key-small", "key-big", "key-fresh"


def _state(path, balances):
    """Write a budget state with the given per-key remaining balances."""
    st = ob.BudgetState()
    for key, rem in balances.items():
        entry = {} if rem is None else {"remaining": rem}
        if rem == 0:
            entry["spent_ts"] = 1.0
        st.keys[ob.fingerprint(key)] = entry
    ob.save(st, path)


def _pick(ring, balances):
    """`get_api_key` against a temp state file and a stubbed ring."""
    path = os.path.join(tempfile.mkdtemp(), "budget.json")
    _state(path, balances)
    saved_ring, saved_path = oddsapi.api_keys, ob.STATE_PATH
    ob.STATE_PATH = path
    oddsapi.api_keys = lambda explicit=None: ([explicit] if explicit else list(ring))
    try:
        return oddsapi.get_api_key()
    finally:
        oddsapi.api_keys, ob.STATE_PATH = saved_ring, saved_path


def test_the_small_key_goes_first():
    assert _pick([SMALL, BIG], {SMALL: 5284, BIG: 100000}) == SMALL


def test_ring_order_does_not_decide_it():
    """THE WHOLE POINT. Same two keys, opposite environment order, same
    answer. Before this rule the second case drained the 100k plan."""
    assert _pick([SMALL, BIG], {SMALL: 5284, BIG: 100000}) == SMALL
    assert _pick([BIG, SMALL], {SMALL: 5284, BIG: 100000}) == SMALL


def test_a_spent_key_is_skipped_however_small():
    """Zero is the smallest balance of all, and picking it would wedge the
    ring on a key the API will refuse."""
    assert _pick([SMALL, BIG], {SMALL: 0, BIG: 100000}) == BIG


def test_the_next_smallest_takes_over_when_the_small_one_empties():
    assert _pick([SMALL, BIG, "mid"],
                 {SMALL: 0, BIG: 100000, "mid": 400}) == "mid"


def test_an_unmeasured_key_is_not_assumed_to_be_small():
    """Unknown is not zero and it is not tiny either. A never-called key
    sorts behind every measured one, so a fresh 100k spare does not get
    drained ahead of a small plan we can actually see."""
    assert _pick([FRESH, SMALL], {SMALL: 5284, FRESH: None}) == SMALL


def test_an_unmeasured_key_is_still_reachable():
    """It must not starve — otherwise it never gets called, never gets
    measured, and stays unknown forever. Once the measured keys are spent
    it is the one that answers, and `record_quota` gives it a balance on
    that first use."""
    assert _pick([FRESH, SMALL], {SMALL: 0, FRESH: None}) == FRESH


def test_a_fresh_ring_falls_back_to_environment_order():
    """Nothing measured yet: every key ties at infinity and ring position
    breaks it, which is the old behaviour and the right one — there is no
    balance to prefer."""
    assert _pick([BIG, SMALL], {}) == BIG
    assert _pick([SMALL, BIG], {}) == SMALL


def test_an_exhausted_ring_still_answers():
    """Every key known empty. Returning the first lets the API give its own
    "out of credits" reply instead of us guessing from a state file that
    may be a month stale."""
    assert _pick([SMALL, BIG], {SMALL: 0, BIG: 0}) == SMALL


def test_an_explicit_key_wins_outright():
    """A caller naming a key means it."""
    saved = oddsapi.api_keys
    try:
        assert oddsapi.get_api_key("named-key") == "named-key"
    finally:
        oddsapi.api_keys = saved


def test_no_keys_is_an_error_not_a_silent_empty_string():
    saved = oddsapi.api_keys
    oddsapi.api_keys = lambda explicit=None: []
    try:
        oddsapi.get_api_key()
    except oddsapi.OddsAPIError as exc:
        assert "the-odds-api.com" in str(exc)
    else:
        raise AssertionError("an empty ring returned a key")
    finally:
        oddsapi.api_keys = saved


def test_budgeting_never_blocks_a_fetch():
    """If the state file is unreadable the ring still answers. A pull that
    cannot happen because the BOOKKEEPING broke is the worst trade in the
    module."""
    saved_ring, saved_state = oddsapi.api_keys, ob.key_state
    oddsapi.api_keys = lambda explicit=None: [SMALL, BIG]
    ob.key_state = lambda *a, **k: (_ for _ in ()).throw(OSError("no disk"))
    try:
        assert oddsapi.get_api_key() in (SMALL, BIG)
    finally:
        oddsapi.api_keys, ob.key_state = saved_ring, saved_state


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
