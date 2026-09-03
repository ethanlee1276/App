"""The odds budget serves the three leagues the product is about.

Ethan, 2026-09-03: *"Yeah keep going we need college football. I don't
care about ufc or nba or wnba, I want NFL, CFB, MLB as the main focus."*

Three separate things were taking college's money, and only one of them
was a policy question.

**THE FIRST SPORT TO PULL EACH DAY ATE EVERYONE'S CEILING.** The hard
daily cap compares the day's spend against `daily_allowance` times the
league's SHARE — one league's slice. But `spent_today` summed EVERY
league's spend. The launcher runs baseball first, baseball spends ~128
credits, and football and college were then metered at 128-against-26 and
declined for the rest of the day, every day. That is a bug, not a budget:
the numerator and the denominator were describing different things.

**A WEEKLY SPORT WAS PAID DAILY.** `daily_allowance` spreads the month
evenly over every remaining day, which is right for baseball and wrong for
football. College plays Saturday. A flat 1/28th on each of 28 days means
it accrues 26 days of budget it can never spend and starves on the one day
it has games. Scaling a game day by 7/days-per-week hands a league its
week on the days it plays, and the month's total is unchanged.

**AND EVERY LEAGUE COUNTED THE SAME.** A WNBA night took the same slice of
a thin plan as college football's Saturday. That one IS a policy question
and Ethan answered it, so the answer is written down in `SPORT_WEIGHT`
rather than applied by hand.

WHAT THIS FILE GUARDS MOST CAREFULLY is that the fix did not become an
overspend. The first cut of the concentration multiplied each share by
7/days-per-week and stopped, which summed to 2.2 on a Saturday — the
leagues jointly planning to spend the day twice over, which is the
arithmetic that emptied the plan in the first place.
`test_the_day_is_allocated_exactly_once` is the guard.

Run directly: `python3 tests/test_budget_focus.py`
"""

import datetime as _date
import json
import os
import sys
import tempfile
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ODDS_API_KEY", "test-key-not-a-real-one")

import launch                                                # noqa: E402
from engine import oddsbudget as ob                          # noqa: E402

FOCUS = ("nfl", "cfb", "mlb")
REST = ("nba", "wnba", "ufc")


def _live(*names):
    """Pretend exactly these leagues have a slate on the board."""
    launch._live_sports = lambda: list(names)


def _state(remaining=5000, **stamps):
    now = _time.time()
    st = ob.BudgetState(remaining=remaining, used=15000,
                        last_refresh_ts=now - 13 * 3600)
    st.sport_last_refresh = {k: now - v for k, v in stamps.items()}
    path = os.path.join(tempfile.mkdtemp(), "b.json")
    with open(path, "w") as fh:
        json.dump(st.to_dict(), fh)
    return path


def _ledger(*rows):
    """A spend log with (sport, credits) entries dated today."""
    path = os.path.join(tempfile.mkdtemp(), "spend.jsonl")
    with open(path, "w") as fh:
        for sport, credits in rows:
            fh.write(json.dumps({
                "iso": _date.datetime.now().isoformat(timespec="seconds"),
                "kind": "live_event", "sport": sport,
                "credits": credits}) + "\n")
    ob._TODAY_CACHE.clear()
    return path


# --- the cap counted the wrong money ----------------------------------------
def test_one_league_s_spend_is_not_charged_to_another_s_ceiling():
    """THE BUG. Baseball spends its morning pull; college is metered
    against baseball's spend and declined on a day it has games.

    Executed against the real `should_refresh`, both ways, so this cannot
    pass by describing the fix instead of exercising it."""
    now = _time.time()
    path = _state(mlb=3600, cfb=13 * 3600)
    spend = _ledger(("mlb", 128))
    kicks = [now + 2 * 3600, now + 5 * 3600]
    _live("mlb", "cfb")
    share = launch._budget_share("cfb")

    saved = ob.SPEND_LOG
    ob.SPEND_LOG = spend
    try:
        assert ob.spent_today(now, spend, sport="cfb") == 0, \
            "college is being charged for baseball's pull"
        assert ob.spent_today(now, spend) == 128, \
            "the unfiltered total stopped counting"
        ok, why = ob.should_refresh(0, now=now, path=path, kickoffs=kicks,
                                    sport="cfb", share=share,
                                    credits=launch.CFB_ODDS_COST)
        assert ok, f"college still declined after baseball spent: {why}"
    finally:
        ob.SPEND_LOG = saved
        ob._TODAY_CACHE.clear()


def test_college_s_own_spend_still_stops_it():
    """The cap has to keep capping. A league that has spent its day is
    declined — that is the whole point of the ceiling, and a per-sport
    filter must not turn it into no ceiling at all."""
    now = _time.time()
    path = _state(mlb=3600, cfb=3600)
    # Deliberately NOT in the pre-game window (no kickoffs) and inside
    # SPARSE_INTERVAL, so the starvation branch cannot rescue it.
    spend = _ledger(("cfb", 5000))
    _live("mlb", "cfb")
    saved = ob.SPEND_LOG
    ob.SPEND_LOG = spend
    try:
        ok, why = ob.should_refresh(0, now=now, path=path, sport="cfb",
                                    share=launch._budget_share("cfb"),
                                    credits=launch.CFB_ODDS_COST)
        assert not ok, "a league that has spent its whole day still pulls"
        assert "budget" in why.lower() or "spent" in why.lower(), why
    finally:
        ob.SPEND_LOG = saved
        ob._TODAY_CACHE.clear()


def test_a_lines_lane_spends_its_league_s_money():
    """"cfb_lines" is a pacing clock, not a league. The ledger records the
    pull under "cfb" because that is whose budget it is, so the cap has to
    look there — otherwise the cheap tier is metered against an empty
    account and is never capped at all."""
    assert ob.budget_sport("cfb_lines") == "cfb"
    assert ob.budget_sport("nfl_lines") == "nfl"
    assert ob.budget_sport("nfl") == "nfl"
    assert ob.budget_sport(None) == ""
    now = _time.time()
    spend = _ledger(("cfb", 60))
    assert ob.spent_today(now, spend, sport="cfb_lines") == 60, \
        "the lines lane cannot see its own league's spend"
    ob._TODAY_CACHE.clear()


def test_the_per_sport_cache_does_not_answer_for_the_wrong_league():
    """One cycle asks for several leagues in a row. A cache keyed by day
    alone would hand the second league the first one's number."""
    now = _time.time()
    spend = _ledger(("mlb", 128), ("cfb", 3))
    assert ob.spent_today(now, spend, sport="mlb") == 128
    assert ob.spent_today(now, spend, sport="cfb") == 3
    assert ob.spent_today(now, spend, sport="nfl") == 0
    assert ob.spent_today(now, spend) == 131
    ob._TODAY_CACHE.clear()


# --- the allocation ---------------------------------------------------------
def test_the_day_is_allocated_exactly_once():
    """THE OVERSPEND GUARD. The first cut of the game-day concentration
    summed to 2.2 on a Saturday — every league planning to spend the day's
    pot, twice. That is the failure `LIVE_SHARE` exists to prevent and the
    one that emptied Ethan's plan."""
    for names in (("mlb",), ("mlb", "cfb"), ("mlb", "nfl"),
                  ("mlb", "nfl", "cfb"), ("mlb", "nfl", "cfb", "wnba"),
                  ("mlb", "nfl", "cfb", "nba", "wnba")):
        _live(*names)
        total = sum(launch._budget_share(n) for n in names)
        assert abs(total - 1.0) < 1e-9, \
            f"{names} allocate {total:.2f} of the day, not 1.00"


def test_the_three_focus_leagues_outweigh_the_rest():
    """Ethan's instruction, in the table where the money is decided."""
    for s in FOCUS:
        assert launch.SPORT_WEIGHT[s] == 1.0, f"{s} is not a focus league"
    for s in REST:
        w = launch.SPORT_WEIGHT[s]
        assert 0 < w < 1.0, f"{s} weighs {w}"
        # NOT zero: that would stop those boards pricing at all, which is a
        # different decision from the one that was asked for.
        assert w > 0, f"{s} was switched off rather than deprioritised"


def test_a_weeknight_basketball_slate_cannot_outbid_a_saturday():
    _live("cfb", "wnba", "nba")
    assert launch._budget_share("cfb") > 0.7, launch._budget_share("cfb")
    assert launch._budget_share("wnba") < 0.15
    assert launch._budget_share("nba") < 0.15


def test_a_weekly_league_is_paid_on_the_days_it_plays():
    """College plays Saturday. Against baseball — which plays every day —
    it must take the larger slice of the days it is on, and that is the
    whole content of PLAY_DAYS_PER_WEEK."""
    _live("mlb", "cfb")
    cfb, mlb = launch._budget_share("cfb"), launch._budget_share("mlb")
    assert cfb > mlb * 3, (
        f"college takes {cfb:.2f} against baseball's {mlb:.2f} on a day "
        f"college plays and baseball plays every day")
    assert launch.PLAY_DAYS_PER_WEEK["mlb"] == 7.0
    assert launch.PLAY_DAYS_PER_WEEK["cfb"] < launch.PLAY_DAYS_PER_WEEK["nfl"]


def test_the_concentration_does_not_invent_credits_over_a_week():
    """The month's total is what it was; only the days it lands on moved.
    Two leagues, one daily and one twice-weekly: over seven days each must
    draw close to its flat weekly entitlement."""
    _live("mlb", "cfb")
    cfb_day, mlb_day = launch._budget_share("cfb"), launch._budget_share("mlb")
    # College claims its share on 2 days; baseball on all 7.
    cfb_week = cfb_day * launch.PLAY_DAYS_PER_WEEK["cfb"]
    mlb_week = mlb_day * launch.PLAY_DAYS_PER_WEEK["mlb"]
    assert abs(cfb_week - mlb_week) < 0.01, (
        f"over a week college draws {cfb_week:.2f} day-shares and baseball "
        f"{mlb_week:.2f} — equal weights should draw equally")
    assert cfb_week + mlb_week <= 7.0 + 1e-9, (
        f"the two leagues draw {cfb_week + mlb_week:.2f} day-shares from a "
        f"seven-day week")


def test_a_league_with_no_board_yet_still_gets_a_share():
    """The bootstrap cycle: the first build of a season runs cached, writes
    the games, and only then is the league 'live'. A share of zero on that
    cycle would divide by a set it is missing from."""
    _live("mlb")
    assert launch._budget_share("cfb") > 0.0
    assert launch._budget_share("nfl") > 0.0


def test_no_sport_still_answers_the_old_way():
    """Callers with no league in hand kept the flat behaviour."""
    _live("mlb", "nfl", "cfb")
    assert abs(launch._budget_share() - 1 / 3) < 1e-9


# --- the measurement --------------------------------------------------------
def test_on_ethans_budget_college_gets_its_saturday():
    """The point of all of it. 5,000 credits left, baseball and college
    live, a Saturday two hours from kickoff: college's full 63-credit pull
    — game lines AND player quotes — is authorised. Before this it was
    metered at 504 against 26 and declined every time."""
    now = _time.time()
    path = _state(remaining=5000, mlb=3600, cfb=13 * 3600)
    _live("mlb", "cfb")
    state = ob.load(path)
    day = _date.date(2026, 9, 5)                       # a Saturday
    pot = ob.daily_allowance(state, day)
    allowance = int(pot * launch._budget_share("cfb"))
    flat = int(pot / 2)                                # the old even split
    # The gain here is 1.5x, not the 3x college takes against baseball on
    # the same day: with only two leagues live the old split was already a
    # half, so a conserved allocation cannot do better than 2x and college
    # is at 0.74 of it. The number that matters is the next assertion.
    assert allowance > flat, (
        f"college's Saturday is {allowance} credits against {flat} under the "
        f"old flat split — the concentration is not reaching it")
    assert allowance >= launch.CFB_LINES_COST * 10, (
        f"{allowance} credits does not buy a day of game-line refreshes")

    spend = _ledger(("mlb", 128))
    saved = ob.SPEND_LOG
    ob.SPEND_LOG = spend
    try:
        ok, why = ob.should_refresh(
            0, now=now, path=path, kickoffs=[now + 2 * 3600, now + 6 * 3600],
            sport="cfb", share=launch._budget_share("cfb"),
            credits=launch.CFB_ODDS_COST)
        assert ok, f"college's Saturday pull is still declined: {why}"
    finally:
        ob.SPEND_LOG = saved
        ob._TODAY_CACHE.clear()


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
