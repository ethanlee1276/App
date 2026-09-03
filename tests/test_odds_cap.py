"""The odds pacer set a cadence and never a ceiling.

Ethan, 2026-09-03, from the droplet, after a board whose prices were 55
minutes old on an 8-minute-old build:

    live_event   136,943  (85%)      hist_event   19,175  (12%)
    TOTAL       160,695

Historical harvesting was the first suspicion and the ledger disproved
it: live per-event pricing is 85% of every credit spent. So live pricing
genuinely costs the money, and the question became why the pacer let it.

IT NEVER CAPPED ANYTHING. `daily_allowance` was only ever an input to
`min_seconds_between` — a CADENCE. `should_refresh` compared elapsed
time against that gap, and nothing anywhere compared the day's spend
against the day's budget. Three things shorten the gap and all three
therefore spent ON TOP of the allowance rather than within it:

    PRIME_BURST = 3.0        x3 the share inside the pre-game window
    active_hours compressed  14h -> hours-left-in-window, up to ~7x
    guaranteed touchpoints   bypass the gap outright ("the ONE override")

Measured, with his numbers: an authorised 1,280 credits/day against
6,859 actually spent, and 72,225 remaining projecting to exhaust on 13
September — Week 1 Sunday, the biggest slate of the year, failing into
hours-stale prices on the games people bet.

His call, same day: a hard daily cap.

TWO THINGS THE CAP IS DELIBERATELY NOT.

It is not metered against the BURSTED share. Inside the window `share`
has already been multiplied by PRIME_BURST, and budgeting the day
against that would reintroduce the same bug one level down — so the
ceiling is computed from `base_share`, captured before the multiply.
The burst still works; it redistributes the day's credits toward the
window instead of adding to them.

And it does not gate the STARVATION path. That branch is the single
affordable pull on a day too poor for the ordinary cadence, held for the
pre-game window. Capping it would remove the safety net that stops a
board going a whole day with no real price — the opposite of the point.

Run directly: `python3 tests/test_odds_cap.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import oddsbudget as B                            # noqa: E402

NOW = dt.datetime(2026, 9, 3, 18, 0).timestamp()
DAY = dt.date.fromtimestamp(NOW).isoformat()
KICKOFFS = [NOW + 2 * 3600]          # inside the pre-game window


def _ledger(credits: int) -> Path:
    f = Path(tempfile.mkdtemp()) / "spend.jsonl"
    f.write_text("" if not credits else json.dumps(
        {"iso": f"{DAY}T09:00:00", "kind": "live_event",
         "sport": "nfl", "credits": credits}) + "\n")
    B.SPEND_LOG = f
    B._TODAY_CACHE.clear()
    return f


def _state(remaining=72225, last=NOW - 6 * 3600):
    st = B.BudgetState()
    st.remaining = remaining
    st.sport_last_refresh = {"nfl": last}
    p = Path(tempfile.mkdtemp()) / "state.json"
    B.save(st, p)
    return st, p


def _budget(st, share=0.5):
    return int(B.daily_allowance(st, dt.date(2026, 9, 3)) * share)


def _ask(path, share=0.5, events=21, last=None):
    return B.should_refresh(events, now=NOW, path=path, kickoffs=KICKOFFS,
                            sport="nfl", share=share)


# --- the ledger read -------------------------------------------------------
def test_spent_today_counts_only_today():
    f = Path(tempfile.mkdtemp()) / "spend.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in (
        {"iso": f"{DAY}T09:00:00", "credits": 100},
        {"iso": f"{DAY}T11:00:00", "credits": 68},
        {"iso": "2026-09-02T23:00:00", "credits": 5000},   # yesterday
    )) + "\n")
    B._TODAY_CACHE.clear()
    assert B.spent_today(NOW, f) == 168


def test_no_ledger_is_nothing_spent_not_a_crash():
    B._TODAY_CACHE.clear()
    assert B.spent_today(NOW, Path(tempfile.mkdtemp()) / "absent.jsonl") == 0


# --- the cap ---------------------------------------------------------------
def test_a_pull_inside_the_days_budget_still_happens():
    st, p = _state()
    _ledger(0)
    ok, why = _ask(p)
    assert ok, why


def test_the_day_stops_when_its_budget_is_gone():
    """THE BUG. Before this the answer here was still PULL, because
    nothing compared the day's spend to the day's budget."""
    st, p = _state()
    _ledger(_budget(st))
    ok, why = _ask(p)
    assert not ok, "the pacer still spends past the day's budget"
    assert "today's odds budget is spent" in why, why
    assert "cached prices" in why, "it does not say what the board falls back on"


def test_the_cost_of_the_pull_is_counted_before_it_is_made():
    """A pull that would take the day past its budget is refused, not
    made and regretted — the ledger only learns after the API answers."""
    st, p = _state()
    per = 21 * B.CREDITS_PER_EVENT
    _ledger(_budget(st) - per + 1)             # one credit short of room
    ok, _ = _ask(p)
    assert not ok
    _ledger(_budget(st) - per)                 # exactly enough
    ok, _ = _ask(p)
    assert ok


def test_the_burst_redistributes_the_day_it_does_not_raise_it():
    """PRIME_BURST triples the share INSIDE the window. The ceiling is
    computed from the share before that multiply, so a bursted pull still
    answers to the same day's budget — otherwise the cap would carry the
    original bug one level down."""
    st, p = _state()
    _ledger(_budget(st, share=0.5))            # budget at the BASE share
    ok, why = _ask(p, share=0.5)               # asked inside the window
    assert not ok, "the burst is spending on top of the day's budget again"
    assert "today's odds budget is spent" in why


def test_the_touchpoint_override_cannot_walk_past_the_cap():
    """The guaranteed morning/noon/evening windows are the one override
    on the gap. They are gated by construction: the cap returns before
    the gap check the override lives inside."""
    src = open(os.path.join(ROOT, "engine", "oddsbudget.py"),
               encoding="utf-8").read()
    i = src.index("def should_refresh")
    body = src[i:src.index("\ndef ", i + 10)]
    cap = body.index("THE HARD DAILY CEILING")
    assert cap < body.index("if waited < gap:"), \
        "the cap no longer precedes the gap check"
    assert cap < body.index("touchpoint_due(state"), \
        "a touchpoint can reach a pull without passing the cap"


def test_the_ceiling_never_blocks_the_days_first_pull():
    """THE CORRECTION THE FIRST CUT NEEDED, and the case the burst exists
    for. On a thin month the flat allowance can be smaller than a single
    refresh — 5,000 credits over 31 days is 72, against a 15-game pull at
    128 — and metering against that refused the day's ONE pre-game pull
    and left the board on yesterday's numbers through first pitch. That
    is the failure tests/test_prime_window_pacing.py was written about,
    and it went red when this cap first landed.

    So the ceiling floors at one pull: it stops the second and the
    fortieth, never the first."""
    st, p = _state(remaining=5000)
    _ledger(0)
    ok, why = _ask(p, share=0.5, events=15)
    assert ok, f"the day's first pull was refused: {why}"
    # …and the second one is not free
    _ledger(15 * B.CREDITS_PER_EVENT)
    ok, why = _ask(p, share=0.5, events=15)
    assert not ok, "the floor became a loophole — every pull is now a first pull"
    assert "today's odds budget is spent" in why


def test_the_starvation_pull_is_left_alone():
    """A day too poor for the ordinary cadence still gets its one held
    pull. Capping this would take away the safety net that stops a board
    going a whole day without a real price."""
    st, p = _state(remaining=900, last=NOW - 24 * 3600)
    _ledger(9999)                              # far past any day's budget
    ok, why = B.should_refresh(3, now=NOW, path=p, kickoffs=KICKOFFS,
                               sport="nfl", share=1.0)
    assert ok, why
    assert "sparse" in why


def test_the_cap_sits_below_the_starvation_branch():
    src = open(os.path.join(ROOT, "engine", "oddsbudget.py"),
               encoding="utf-8").read()
    i = src.index("def should_refresh")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("Starvation mode:") < body.index("THE HARD DAILY CEILING"), \
        "the cap moved above the sparse pull and would now block it"


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
