"""The month's odds plan: every league in season budgeted, the NFL first.

Ethan, 2026-10-21: "we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority". And 2026-10-28: "all of that needs its own budget
... NFL comes first, then college football, then NBA, then baseball ...
once baseball is over, we can take baseball out of the credit pool".

What this file holds the plan (engine/oddsplan) to:

* THE NFL FIRST, THEN EVERY SPORT ITS FLOOR. A month that cannot fund
  everyone funds the NFL's target in full before anyone else's; then every
  other league in season gets half its target together, so a short month
  thins a sport and never switches it off; then the rest in Ethan's order —
  college, the NBA, baseball, then hockey, UFC and the WNBA at one fill.
  Nobody gets headroom while any league's target is cut.
* A SEASON THAT IS OVER IS OUT OF THE POOL, the morning its own board says
  so (`launch._seasons_over`), and what it would have held goes to the
  leagues still playing.
* NEVER MORE THAN THE POOL. Targets, headroom and the unplanned remainder
  add up to the spendable pool; a month spent at every league's ceiling
  every day still ends above the reserve.
* THE PACER READS IT. `launch._budget_share` hands the pacer each league's
  ceiling for today as a share of the day's allowance, so the pacer's own
  arithmetic (`allowance × share`) lands on the plan's number — and falls
  back to the old weights when there is no measured balance to plan from.
* THE RENEWAL DAY. The month runs to the plan's renewal, not to the end of
  the calendar month: a plan that renews on the 14th spread to October 31
  would spend thirteen days of credits in one.
* THE TWO PACER FIXES THAT CAME WITH IT: basketball and hockey keep their
  own two windows and do not burst a three-pull day; a cheap lane on a day
  with no game near is off-peak, not "time-blind".

Offline; every file the plan reads is a temporary one.

Run directly: `python3 tests/test_the_odds_plan.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_ODDS_RESET_DAY", None)
os.environ.pop("QB_ODDS_WINDOWS", None)

from engine import oddsbudget as ob                          # noqa: E402
from engine import oddsplan as P                             # noqa: E402

NOV1 = dt.date(2026, 11, 1)      # a Sunday: the NFL, college, NBA, NHL in season
TUE = dt.date(2026, 11, 10)
OCT21 = dt.date(2026, 10, 21)
TONIGHT = {"nba": 11, "nhl": 9, "mlb": 0, "nfl": 14, "cfb": 3, "ufc": 13}
ET = ZoneInfo("America/New_York")


def _tmp(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(), name)


def _state(remaining: int = 60_000, used: int = 40_000, seen: str | None = None,
           keys: dict | None = None, **stamps) -> str:
    """A budget state file, measured (a quota reading on `seen`)."""
    st = ob.BudgetState(remaining=remaining, used=used,
                        last_seen_iso=seen or dt.datetime.now().isoformat(timespec="seconds"))
    st.sport_last_refresh = dict(stamps)
    if keys is not None:
        st.keys = keys
    path = _tmp("odds_budget.json")
    ob.save(st, path)
    return path


def _ledger(rows: list) -> str:
    path = _tmp("odds_spend.jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    ob._TODAY_CACHE.clear()
    return path


class _Swap:
    """Point the budget's files at temporary ones for the length of a block."""

    def __init__(self, state: str, ledger: str):
        self.state, self.ledger = state, ledger

    def __enter__(self):
        self.saved = (ob.STATE_PATH, ob.SPEND_LOG)
        ob.STATE_PATH, ob.SPEND_LOG = Path(self.state), Path(self.ledger)
        ob._TODAY_CACHE.clear()
        P._CACHE.clear()
        P._RESET.clear()
        return self

    def __exit__(self, *exc):
        ob.STATE_PATH, ob.SPEND_LOG = self.saved
        ob._TODAY_CACHE.clear()
        P._CACHE.clear()
        P._RESET.clear()
        return False


# --- the order things are funded in --------------------------------------------
def test_after_tonights_games_the_nfl_is_funded_first_when_the_month_is_short():
    """Ethan, 2026-10-30: "tonight's games come first". On a Tuesday the NFL
    plays nobody; the leagues that play tonight are funded for tonight, and
    every credit after that goes to the NFL's month before anyone's next."""
    plan = P.build(TUE, 20_000)
    nfl = plan.get("nfl")
    tonight = sum(lp.first for lp in plan.leagues.values())
    assert nfl.today_need == nfl.first == 0, "no NFL game on a Tuesday"
    assert 0 < tonight < plan.spendable < tonight + nfl.need, \
        "the fixture is meant to be short of the NFL alone, after tonight"
    assert nfl.target == plan.spendable - tonight, (nfl.target, plan.spendable, tonight)
    for lg in P.PRIORITY[1:]:
        lp = plan.get(lg)
        assert lp.alloc == lp.first == lp.today_need, f"{lg} got past tonight before the NFL's target"


def test_tonights_games_come_before_any_day_to_come():
    """However short the month, a league that plays tonight is funded for
    tonight before the NFL's Sunday or anybody's next game night — and its
    ceiling today is never cut below what tonight was funded."""
    thursday = dt.date(2026, 11, 12)
    for pool in range(600, 30_000, 400):
        plan = P.build(thursday, pool, {"nfl": 1, "nba": 9, "nhl": 6, "cfb": 2, "ufc": 0})
        tonight = sum(lp.today_need for lp in plan.leagues.values())
        if plan.spendable >= tonight:
            for lp in plan.leagues.values():
                assert lp.first == lp.today_need, (pool, lp.league)
        else:
            assert all(lp.target == lp.first for lp in plan.leagues.values()), \
                (pool, "a day to come was funded before tonight")
        for lp in plan.leagues.values():
            assert lp.envelope >= lp.first, (pool, lp.league)
    # The NFL's one Thursday game first, then every floor, then the tiers.
    thin = P.build(thursday, 9_500, {"nfl": 1, "nba": 9, "nhl": 6, "cfb": 2, "ufc": 0})
    nfl, later = thin.get("nfl"), [thin.get(lg) for lg in ("cfb", "nba", "nhl")]
    assert nfl.today_need < thin.spendable < sum(lp.today_need for lp in thin.leagues.values())
    assert nfl.first == nfl.today_need > 0
    assert all(0 < lp.first <= lp.today_need * P.FLOOR_SHARE + 1 for lp in later), \
        [(lp.league, lp.first, lp.today_need) for lp in later]


def _floor(lp) -> int:
    return int(lp.need * P.FLOOR_SHARE)


def test_the_order_is_ethans():
    """"NFL comes first, then college football, then NBA, then baseball";
    hockey, UFC and the WNBA, which he did not place, after them at one fill."""
    assert P.TIERS == (("nfl",), ("cfb",), ("nba",), ("mlb",), ("nhl", "ufc", "wnba"))
    assert P.PRIORITY == ("nfl", "cfb", "nba", "mlb", "nhl", "ufc", "wnba")
    assert P.tiers(NOV1) == P.TIERS
    assert 0 < P.FLOOR_SHARE < 1


def _pools(day, lo=1_000, hi=200_000, step=250, **kw):
    for pool in range(lo, hi, step):
        yield pool, P.build(day, pool, **kw)


def test_every_sport_playing_gets_its_floor_before_any_but_the_nfl_gets_more():
    """THE OCTOBER BUG: the NFL and college funded in full and basketball
    and hockey left nothing (DK: 0 NBA props priced). Past tonight's games
    and the NFL's target, while anyone is short of half their target,
    nobody is past half theirs (or tonight's, where tonight costs more) —
    the floors fill together, at one fill."""
    for day in (NOV1, TUE, dt.date(2026, 10, 28)):
        thin = 0
        for pool, plan in _pools(day):
            later = [plan.get(lg) for t in P.tiers(day)[1:] for lg in t if plan.get(lg).need > 0]
            if any(lp.target < max(_floor(lp), lp.first) - 1 for lp in later):
                thin += 1
                assert all(lp.target <= max(_floor(lp), lp.first) + 1 for lp in later), \
                    (day, pool, {lp.league: (lp.target, _floor(lp), lp.first) for lp in later})
                fills = [(lp.target - lp.first) / (_floor(lp) - lp.first) for lp in later
                         if _floor(lp) - lp.first > 50]
                if fills:
                    assert max(fills) - min(fills) < 0.02, (day, pool, fills)
                if plan.get("nfl").fill < 1:
                    assert all(lp.target == lp.first for lp in later), \
                        "after tonight, the NFL's target comes before every floor"
        assert thin, f"{day}: no pool short of the floors"


def test_past_the_floors_each_tier_waits_for_the_one_above():
    """College, then the NBA, then baseball, then the rest: a tier past its
    floor means every tier above it has its whole target."""
    for day in (NOV1, TUE):
        order = P.tiers(day)
        seen = set()
        for pool, plan in _pools(day):
            for i, tier in enumerate(order[1:], 1):
                if any(plan.get(lg).target > _floor(plan.get(lg)) + 1 for lg in tier):
                    seen.add(i)
                    for above in order[:i]:
                        for lg in above:
                            lp = plan.get(lg)
                            assert lp.need - lp.target <= 2, \
                                f"{day} {pool}: {tier} past its floor before {lg}'s target"
        assert {1, 2, 4} <= seen, (day, seen)


def test_the_last_tier_shares_one_fill():
    for pool, plan in _pools(NOV1, 60_000, 120_000, 500):
        nhl, ufc = plan.get("nhl"), plan.get("ufc")
        if 0.55 < nhl.fill < 0.95:
            assert abs(nhl.fill - ufc.fill) < 0.01, (pool, nhl.fill, ufc.fill)
            return
    raise AssertionError("no pool funds the last tier in part")


def test_november_at_100k_funds_every_sport_and_most_of_the_headroom():
    """The page's numbers (docs/ODDS_PLAN.md): the whole plan on the 1st.
    With every league buying on its game nights only — tonight's games, not
    the week's — every target is met with room left: the NFL's half again,
    a quarter for college, the NBA and baseball, and hockey and UFC share
    the rest at one fill."""
    plan = P.build(NOV1, 100_000, end=dt.date(2026, 12, 1), reset="measured", start=NOV1)
    assert all(lp.target == lp.need for lp in plan.leagues.values())
    nfl = plan.get("nfl")
    assert nfl.extra == int(nfl.need * P.NFL_HEADROOM), "the NFL's headroom first"
    for lg in ("cfb", "nba", "mlb"):
        assert plan.get(lg).extra == int(plan.get(lg).need * P.HEADROOM), lg
    nhl, ufc = plan.get("nhl"), plan.get("ufc")
    assert 1.0 < nhl.fill < 1.0 + P.HEADROOM and abs(nhl.fill - ufc.fill) < 0.01, (nhl.fill, ufc.fill)
    assert plan.get("wnba").need == 0 and plan.unplanned <= 2
    gone = P.build(NOV1, 100_000, end=dt.date(2026, 12, 1), reset="measured", start=NOV1,
                   over={"mlb"})
    assert gone.get("nhl").fill > plan.get("nhl").fill, "baseball's share went to the leagues still playing"


def test_a_season_that_is_over_leaves_the_pool():
    plan = P.build(NOV1, 100_000, TONIGHT, over={"mlb"})
    mlb = plan.get("mlb")
    assert mlb.over and mlb.need == mlb.today_need == mlb.alloc == mlb.envelope == 0
    assert P.build(NOV1, 100_000, TONIGHT).get("mlb").need > 0, "the table alone still holds November 1-4"
    text = P.report(plan, {"mlb": 1_240})
    assert "MLB   season over — out of the pool (spent 1,240 this month)" in text
    assert "WNBA  out of season" in text


def test_until_the_renewal_the_nba_is_funded_right_after_the_nfl():
    """Ethan, 2026-10-28: "we still don't have edge bets or most likely bets
    for nba. We need that now" — October's credits had run out after the
    NFL and college, and he chose the NBA before college until Nov 1."""
    oct28, end = dt.date(2026, 10, 28), dt.date(2026, 11, 1)
    assert P.tiers(oct28) == (("nfl",), ("nba",), ("cfb",), ("mlb",), ("nhl", "ufc", "wnba"))
    assert sorted(lg for t in P.tiers(oct28) for lg in t) == sorted(P.PRIORITY), "nobody dropped"
    assert P.tiers(P.NBA_FIRST_UNTIL) == P.TIERS and P.tiers(NOV1) == P.TIERS, "from the renewal, as before"
    seen = 0
    for pool in range(2_000, 30_000, 250):
        plan = P.build(oct28, pool, end=end, reset="measured", start=dt.date(2026, 10, 1))
        nfl, nba, cfb = plan.get("nfl"), plan.get("nba"), plan.get("cfb")
        assert nba.priority == 2 and cfb.priority == 3
        # A share is cut to whole credits, so one can trickle past a tier.
        # Tonight's games come before everything (`first`).
        if nba.target > nba.first + 1:
            assert nfl.need - nfl.target <= 1, "after tonight, the NFL's target still comes first"
        if cfb.target > max(_floor(cfb), cfb.first) + 1:
            assert nba.need - nba.target <= 1, f"college past its floor at {pool} before the NBA's target was met"
            seen += 1
    assert seen, "some pool funds both"


def test_nobody_gets_headroom_while_a_target_is_cut():
    short = 0
    for pool, plan in _pools(NOV1, 20_000, 120_000, 1_000):
        if any(lp.target < lp.need for lp in plan.leagues.values()):
            short += 1
            assert all(lp.extra == 0 for lp in plan.leagues.values()), \
                (pool, {lg: lp.extra for lg, lp in plan.leagues.items()})
    assert short, "no pool short of a target"


def test_headroom_goes_to_the_nfl_first_once_every_target_is_met():
    rich = P.build(NOV1, 400_000)
    assert all(lp.target == lp.need for lp in rich.leagues.values())
    assert rich.get("nfl").extra == int(rich.get("nfl").need * P.NFL_HEADROOM)
    for lg in ("cfb", "nba", "nhl"):
        assert rich.get(lg).extra == int(rich.get(lg).need * P.HEADROOM), lg
    assert rich.unplanned > 0
    # …and a pool that covers every target and part of the NFL's headroom
    # gives the rest none of theirs.
    need = sum(lp.need for lp in rich.leagues.values())
    for pool in range(40_000, 400_000, 500):
        plan = P.build(NOV1, pool)
        if plan.spendable > need + 1000 and plan.get("nfl").extra < int(plan.get("nfl").need * P.NFL_HEADROOM):
            assert all(plan.get(lg).extra == 0 for lg in P.PRIORITY[1:]), \
                "a later tier's headroom came before the NFL's"
            break
    else:
        raise AssertionError("no pool lands inside the NFL's headroom")


def test_the_plan_never_plans_more_than_the_pool_holds():
    for day in (OCT21, NOV1, TUE, dt.date(2026, 12, 31), dt.date(2027, 3, 1)):
        for pool in (0, 499, 5_000, 20_000, 60_000, 100_000, 250_000):
            plan = P.build(day, pool, TONIGHT if day == OCT21 else None)
            planned = sum(lp.alloc for lp in plan.leagues.values())
            assert planned + plan.unplanned == plan.spendable, (day, pool)
            assert plan.unplanned >= 0 and all(lp.alloc >= 0 for lp in plan.leagues.values())
            assert plan.spendable <= max(0, pool - plan.reserve - plan.harvest - plan.buffer)
            for lp in plan.leagues.values():
                assert lp.envelope == max(lp.first, int(lp.today_need * lp.fill)), \
                    (day, pool, lp.league)


def test_a_month_spent_at_every_ceiling_never_overspends():
    """Every league spending its whole ceiling every day, and the harvest
    its whole cap: the month still ends above the reserve, the NFL is
    funded in full every day it is owed anything, and little is left to
    expire at the reset past what the plan itself left unplanned — with
    every league buying on its game nights only, the tables and their
    headroom no longer take the whole month (`unplanned`, said in the
    report)."""
    for first in (dt.date(2026, 10, 1), NOV1, dt.date(2026, 12, 1)):
        pool, day, end = 100_000, first, P.period(first)[1]
        unplanned = P.build(day, pool).unplanned
        while day < end:
            plan = P.build(day, pool)
            nfl = plan.get("nfl")
            assert nfl.need == 0 or nfl.fill >= 1.0, f"{day}: the NFL is short ({nfl.fill:.2f})"
            pool -= sum(lp.envelope for lp in plan.leagues.values()) + P.HARVEST_DAY
            day += dt.timedelta(days=1)
        assert pool >= ob.RESERVE, f"{first:%B}: the month overspent — {pool} left"
        assert pool < unplanned + 100_000 * 0.06, \
            f"{first:%B}: {pool} credits left to expire ({unplanned} unplanned on the 1st)"


# --- what a league is owed -----------------------------------------------------
def test_a_league_out_of_season_is_owed_nothing():
    assert P.build(NOV1, 100_000).get("wnba").need == 0
    assert P.day_need("mlb", dt.date(2026, 12, 10)) == 0
    assert P.day_need("nfl", dt.date(2027, 3, 10)) == 0
    assert P.day_need("cfb", dt.date(2027, 3, 10)) == 0


def test_todays_slate_replaces_the_table_for_today():
    busy = P.build(TUE, 100_000, {"nba": 12})
    dark = P.build(TUE, 100_000, {"nba": 0})
    assert dark.get("nba").today_need == 0, "an NBA night with no games is owed nothing"
    assert busy.get("nba").today_need == P.day_need("nba", TUE, 12) > 0
    assert busy.get("nba").need - dark.get("nba").need == busy.get("nba").today_need, \
        "today's slate moved the rest of the month too"


def test_the_nfl_is_owed_nothing_on_a_night_it_does_not_play():
    """Ethan, 2026-10-30: "if just NFL has a game that night, we just need to
    pull NFL and so forth" — and the other way round. Its Sunday, Monday and
    Thursday come off the table; a game night the table does not hold
    (Thanksgiving's Friday, December's Saturdays) is priced by the game; a
    board whose times could not be read (None) leaves the table to answer."""
    sun, mon, thu = NOV1, dt.date(2026, 11, 2), dt.date(2026, 11, 5)
    sat, fri = dt.date(2026, 12, 19), dt.date(2026, 11, 27)
    for day in (TUE, fri, sat):
        assert P.day_need("nfl", day, 0) == 0, day
        assert P.NFL_REGULAR[day.weekday()] == 0, day
    assert P.day_need("nfl", sun, 13) == P.NFL_REGULAR[6] > 0
    assert P.day_need("nfl", sun, None) == P.NFL_REGULAR[6]
    assert P.day_need("nfl", thu, 1) == P.NFL_REGULAR[3] > 0
    assert P.day_need("nfl", mon, 0) == 0, "a Monday with no Monday game"
    game = P.NFL_FLOOR_PULLS * 3 * P.price("nfl") + P.NFL_LINES_PULLS * P.LINES_CREDITS
    assert P.day_need("nfl", sat, 2) == game, "a December Saturday's two games, by the game"
    assert P.day_need("nfl", fri, 1) > 0, "Black Friday's game"
    assert P.day_need("nfl", dt.date(2027, 3, 10), 0) == 0


def test_college_buys_on_its_game_nights_only():
    """Its lines lane ran every day of the season — the board holds the week
    — until the tonight rule: a Sunday with no college game buys nothing,
    and the week's table counts each night's own games (twelve a pull at
    most on Saturday), not the ones inside the 36-hour player window."""
    sunday, saturday = dt.date(2026, 11, 8), dt.date(2026, 11, 7)
    assert P.day_need("cfb", sunday, 0) == 0
    assert P.day_need("cfb", sunday) == 0, "the table's Sunday has no game"
    assert P.GAMES_BY_WEEKDAY["cfb"][6] == P.GAMES_BY_WEEKDAY["cfb"][0] == 0
    assert P.day_need("cfb", saturday, 50) == P.day_need("cfb", saturday, 12), "a pull prices twelve"
    assert P.day_need("cfb", saturday, 12) > P.LINES_BY_WEEKDAY["cfb"][5] * P.LINES_CREDITS
    assert P.GAMES_BY_WEEKDAY["ufc"] == (0, 0, 0, 0, 0, 13, 0), "UFC buys on fight night"
    assert not hasattr(P, "LINES_EVERY_DAY")
    assert P.day_need("cfb", dt.date(2027, 3, 7), 0) == 0


def test_a_healthy_month_does_not_starve_basketball():
    """THE BUG THE PLAN REPLACES: under the weights the NBA drew ~2% of a
    weekday — one sparse pull. On a healthy pool its ceiling tonight covers
    three pulls of an eleven-game slate, its lines and its live line."""
    plan = P.build(OCT21, 45_000, TONIGHT)
    pull = (TONIGHT["nba"] + 1) * ob.credits_per_event("nba")
    assert plan.get("nba").envelope >= 3 * pull, (plan.get("nba").envelope, pull)
    assert plan.get("nhl").envelope >= 3 * (TONIGHT["nhl"] + 1) * ob.credits_per_event("nhl")


def test_the_plans_prices_are_the_pacers_and_the_builds():
    import cfb_build
    from engine import maintenance
    assert ob.credits_per_event("ufc") == 1 == P.price("ufc"), \
        "UFC asks one market a fight and was metered at the generic eight"
    for lg in ("nfl", "nba", "nhl", "mlb", "wnba"):
        assert P.price(lg) == ob.EVENT_CREDITS[lg], lg
    assert P.CFB_PRICE == cfb_build.CREDITS_PER_EVENT == P.price("cfb")
    assert P.PULL_CAP["cfb"] == cfb_build.PLAYER_EVENT_CAP
    assert P.HARVEST_DAY == maintenance.HARVEST_DAY_BUDGET


# --- the plan on the box ---------------------------------------------------------
def test_the_pool_is_taken_at_the_start_of_the_day():
    now = time.time()
    today = dt.datetime.now().isoformat(timespec="seconds")
    with _Swap(_state(remaining=50_000), _ledger([
            {"iso": today, "kind": "live_event", "sport": "nba", "credits": 2_000}])):
        plan = P.current(TONIGHT, now=now)
        assert plan.pool == 52_000, plan.pool


def test_no_measured_balance_is_no_plan():
    st = ob.BudgetState(remaining=500)                # never read from the API
    path = _tmp("odds_budget.json")
    ob.save(st, path)
    with _Swap(path, _ledger([])):
        try:
            P.current(TONIGHT)
        except P.PlanUnavailable:
            return
    raise AssertionError("an unmeasured balance produced a plan")


def test_the_launcher_hands_the_pacer_the_plans_ceiling():
    import launch
    saved = launch._games_today, launch._seasons_over
    launch._games_today = lambda: dict(TONIGHT)
    launch._seasons_over = lambda day=None: frozenset()
    try:
        with _Swap(_state(remaining=60_000), _ledger([])):
            allowance = ob.daily_allowance(ob.load())
            for lg in ("nfl", "cfb", "nba", "nhl", "ufc"):
                env = P.envelope(lg, games_today=TONIGHT)
                got = int(allowance * launch._budget_share(lg))
                assert got == env, f"{lg}: the pacer's ceiling is {got}, the plan's {env}"
            # A lines lane spends its league's money, so it reads its league's ceiling.
            assert launch._budget_share("nba_board_lines") == launch._budget_share("nba")
            assert launch._budget_share("wnba") == 0.0, "an out-of-season league has no ceiling"
            # …and a season its board calls over has none either, its share the others'.
            launch._seasons_over = lambda day=None: frozenset({"nba"})
            P._CACHE.clear()
            assert launch._budget_share("nba") == 0.0
            env = P.envelope("nhl", games_today=TONIGHT, over={"nba"})
            assert int(allowance * launch._budget_share("nhl")) == env
    finally:
        launch._games_today, launch._seasons_over = saved


def test_the_launcher_falls_back_to_the_weights_without_a_plan():
    import launch
    saved = launch._live_sports
    launch._live_sports = lambda: ["nfl", "cfb", "nba"]
    try:
        path = _tmp("odds_budget.json")
        ob.save(ob.BudgetState(remaining=500), path)          # unmeasured
        with _Swap(path, _ledger([])):
            for lg in ("nfl", "cfb", "nba"):
                assert launch._budget_share(lg) == launch._weighted_share(lg), lg
            assert launch._budget_share() == launch._weighted_share(None) == 1 / 3
    finally:
        launch._live_sports = saved


def test_todays_games_come_off_the_built_boards():
    """Tonight's games, league by league (Ethan, 2026-10-30: "recognizing
    what sport has what games live that night"). The daily boards hold
    tonight's slate; the NFL's and college's hold the week and count only
    tonight's — a game past midnight is still tonight's, the boards' own
    5 AM roll — and UFC counts the card's bouts on fight night. An empty
    board is 0; a weekly board whose times cannot be read says nothing,
    and the plan's table answers for it."""
    import launch
    d = tempfile.mkdtemp()
    thu = dt.datetime(2026, 11, 5, 10, tzinfo=ET).timestamp()        # a Thursday morning
    sat = dt.datetime(2026, 11, 7, 9, tzinfo=ET).timestamp()

    def board(name, games):
        path = os.path.join(d, name)
        with open(path, "w") as fh:
            json.dump({"games": games}, fh)
        return path

    def iso(*when):
        return dt.datetime(*when, tzinfo=ET).astimezone(dt.timezone.utc).isoformat()

    saved = {k: getattr(launch, k) for k in
             ("MLB_OUT", "NBA_OUT", "WNBA_OUT", "NHL_OUT", "NFL_OUT", "UFC_OUT", "CFB_OUT",
              "_ufc_card")}
    launch.NBA_OUT = board("nba.json", [{}] * 7)            # no times: a daily board is tonight's
    launch.NHL_OUT = board("nhl.json", [{"kickoff": iso(2026, 11, 5, 19)}] * 4)
    launch.MLB_OUT = board("mlb.json", [])
    launch.WNBA_OUT = os.path.join(d, "missing.json")
    launch.NFL_OUT = board("nfl.json", [{"date": "2026-11-05", "kickoff": "20:15"}]
                           + [{"date": "2026-11-08", "kickoff": "13:00"}] * 13)
    launch.CFB_OUT = board("cfb.json", [
        {"kickoff": iso(2026, 11, 5, 19, 30)}, {"kickoff": iso(2026, 11, 6, 0, 30)},
        {"kickoff": iso(2026, 11, 6, 19)}, {"kickoff": iso(2026, 11, 7, 12)}])
    card = [{"commence_time": iso(2026, 11, 7, 18)}] * 12
    launch._ufc_card = lambda cache_only=False: card
    launch._GAMES_TODAY[:] = [0.0, {}]
    try:
        got = launch._games_tonight(thu)
        assert got == {"mlb": 0, "nba": 7, "wnba": 0, "nhl": 4, "nfl": 1, "cfb": 2,
                       "ufc": 0}, got
        got = launch._games_tonight(sat)
        assert (got["nfl"], got["cfb"], got["ufc"]) == (0, 1, 12), got
        launch.NFL_OUT = board("nfl_x.json", [{"date": "2026-W10", "kickoff": "TBD"}] * 14)
        assert "nfl" not in launch._games_tonight(thu), "times unread: the table answers"
        assert launch._games_today()["nba"] == 7
        launch.NBA_OUT = board("nba2.json", [{}] * 9)
        assert launch._games_today()["nba"] == 7, "read again inside the minute"
        launch._GAMES_TODAY[0] -= launch.GAMES_TODAY_TTL_S + 1
        assert launch._games_today()["nba"] == 9, "a minute on, the boards are read again"
    finally:
        for k, v in saved.items():
            setattr(launch, k, v)
        launch._GAMES_TODAY[:] = [0.0, {}]


def test_a_board_says_when_its_season_is_over():
    """Ethan, 2026-10-28: "once baseball is over, we can take baseball out of
    the credit pool". The table runs baseball's postseason to November 4;
    the board knows the morning after the last game: empty, and its five-day
    look ahead found no next slate. A hoops or college board says it outright
    (`status: offseason`). Only in a league's postseason, and a board that
    cannot be read says nothing."""
    import launch
    d = tempfile.mkdtemp()

    def board(name, body):
        path = os.path.join(d, name)
        with open(path, "w") as fh:
            json.dump(body, fh)
        return path

    names = ("MLB_OUT", "NBA_OUT", "WNBA_OUT", "NHL_OUT", "CFB_OUT")
    saved = {k: getattr(launch, k) for k in names}
    nov1, june, july = NOV1, dt.date(2027, 6, 18), dt.date(2027, 7, 15)
    try:
        for k in names:
            setattr(launch, k, os.path.join(d, "missing.json"))
        assert launch._seasons_over(nov1) == frozenset(), "a missing board says nothing"
        launch.MLB_OUT = board("mlb.json", {"games": []})
        assert launch._seasons_over(nov1) == {"mlb"}, "the World Series is over"
        assert launch._seasons_over(july) == frozenset(), "a blank July board is the All-Star break, not the end"
        launch.MLB_OUT = board("mlb2.json", {"games": [{}], "upcoming": {"date": "2026-11-02", "days_ahead": 1}})
        assert launch._seasons_over(nov1) == frozenset(), "a travel day, game six tomorrow"
        launch.MLB_OUT = board("mlb3.json", {"games": [], "upcoming": {"date": "2026-11-03"}})
        assert launch._seasons_over(nov1) == frozenset()
        launch.NBA_OUT = board("nba.json", {"games": [], "status": "offseason"})
        assert launch._seasons_over(june) == {"nba"}, "the Finals are over"
        assert launch._seasons_over(nov1) == frozenset(), "never in the regular season"
        launch.NBA_OUT = board("nba2.json", {"games": [], "status": "no games today"})
        assert launch._seasons_over(june) == frozenset(), "a quiet date between two Finals games"
        launch.MLB_OUT = board("mlb4.json", ["not", "a", "board"])
        assert launch._seasons_over(nov1) == frozenset()
    finally:
        for k, v in saved.items():
            setattr(launch, k, v)
        launch._SEASONS_OVER[:] = [0.0, frozenset()]


# --- the renewal day -------------------------------------------------------------
def test_the_billing_month_runs_renewal_to_renewal():
    assert P.period(OCT21) == (dt.date(2026, 10, 1), dt.date(2026, 11, 1))
    assert P.period(OCT21, 14) == (dt.date(2026, 10, 14), dt.date(2026, 11, 14))
    assert P.period(dt.date(2026, 10, 10), 14) == (dt.date(2026, 9, 14), dt.date(2026, 10, 14))
    assert P.period(dt.date(2026, 12, 20), 14) == (dt.date(2026, 12, 14), dt.date(2027, 1, 14))
    assert P.period(dt.date(2027, 2, 28), 31) == (dt.date(2027, 2, 28), dt.date(2027, 3, 31))
    assert len(P.days_left(OCT21)) == 11
    assert len(P.days_left(OCT21, dt.date(2026, 11, 14))) == 24


def test_the_renewal_day_is_measured_off_the_ledger():
    rows = [{"iso": (OCT21 - dt.timedelta(days=b)).isoformat() + "T12:00:00", "credits": 3_000}
            for b in range(40)]
    assert P.measured_start(8 * 3_000, rows, OCT21) == dt.date(2026, 10, 14)
    assert P.measured_start(50, rows, OCT21) is None, "too young a month to measure"
    assert P.measured_start(200_000, rows, OCT21) is None, "a ledger that never adds up"
    seen = dt.datetime(2026, 10, 21, 9, 0).isoformat()
    st = ob.load(_state(used=8 * 3_000, seen=seen))
    assert P.reset_day(st, rows, OCT21) == (14, "measured")
    # A reading days old is not today's count.
    stale = ob.load(_state(used=8 * 3_000, seen="2026-10-12T09:00:00"))
    assert P.reset_day(stale, rows, OCT21) == (1, "assumed")
    # Two keys with credits: one ledger, two renewal dates — not measured.
    two = ob.load(_state(used=8 * 3_000, seen=seen, keys={
        "aaaa1111": {"remaining": 30_000, "used": 24_000},
        "bbbb2222": {"remaining": 30_000, "used": 9_000}}))
    assert P.reset_day(two, rows, OCT21) == (1, "assumed")
    os.environ[P.RESET_DAY_ENV] = "9"
    try:
        assert P.reset_day(st, rows, OCT21) == (9, "set"), "the setting wins"
    finally:
        os.environ.pop(P.RESET_DAY_ENV, None)


def test_a_plan_that_renews_mid_month_spreads_to_the_renewal():
    """THE FAILURE THIS GUARDS: the calendar month would end October 31 for
    a plan that renews November 14, and spend thirteen days in one."""
    calendar = P.build(OCT21, 45_000, TONIGHT)
    renewal = P.build(OCT21, 45_000, TONIGHT, end=dt.date(2026, 11, 14), reset="measured")
    assert renewal.days_left == 24 and calendar.days_left == 11
    assert renewal.harvest == 24 * P.HARVEST_DAY
    assert renewal.get("nba").envelope <= calendar.get("nba").envelope
    assert renewal.get("nfl").envelope <= calendar.get("nfl").envelope


def test_an_unknown_renewal_day_holds_the_headroom():
    """Until the renewal day is known, the box pays every league's target
    and nothing on top: headroom spent against the wrong month's end is
    spent out of the next month's days."""
    held = P.build(NOV1, 400_000, headroom=False)
    assert all(lp.extra == 0 and lp.target == lp.need for lp in held.leagues.values())
    assert "no headroom until it is known" in P.report(held)
    with _Swap(_state(remaining=400_000, used=10), _ledger([])):   # too young to measure
        plan = P.current(TONIGHT)
        assert plan.reset == "assumed" and not plan.headroom
        assert all(lp.extra == 0 for lp in plan.leagues.values())


def test_the_box_plan_follows_the_measured_renewal():
    today = dt.date.today()
    rows = [{"iso": (today - dt.timedelta(days=b)).isoformat() + "T12:00:00",
             "kind": "live_event", "sport": "nfl", "credits": 2_000} for b in range(40)]
    with _Swap(_state(remaining=60_000, used=5 * 2_000), _ledger(rows)):
        plan = P.current(TONIGHT)
        start = today - dt.timedelta(days=4)
        assert plan.reset == "measured" and plan.starts == P.period(today, start.day)[0]
        assert plan.ends == P.period(today, start.day)[1]
        assert plan.headroom, "a measured renewal day plans the headroom"


# --- the report --------------------------------------------------------------
def test_the_report_says_where_the_month_stands():
    plan = P.build(NOV1, 100_000, end=dt.date(2026, 11, 14), reset="measured",
                   start=dt.date(2026, 10, 14))
    text = P.report(plan, {"nfl": 30_000, "harvest": 4_000}, {"nfl": 1_200},
                    pool_now=98_800, recent={"nfl": 2_400, "nba": 600})
    assert "renews Nov 14" in text and "measured" in text
    for lg in P.PRIORITY:
        assert P.LABEL[lg] in text, lg
    assert "WNBA  out of season" in text
    assert "spent this month: NFL 30,000 · harvest 4,000" in text
    assert "last 7 days, a day: NFL 2,400 · NBA 600" in text
    assert "ASSUMED" in P.report(P.build(NOV1, 100_000)), \
        "an assumed renewal day is said out loud"


def test_the_report_gives_each_sport_its_month():
    """Ethan: "all of that needs its own budget". Each sport's line is its
    month: what it spent since the renewal plus what the plan holds for it
    from now, the order and the floor said above them."""
    plan = P.build(TUE, 70_000, {"nba": 9, "nhl": 6}, end=dt.date(2026, 12, 1), reset="measured",
                   start=NOV1)
    nba = plan.get("nba")
    text = P.report(plan, {"nfl": 30_000, "nba": 6_200, "harvest": 3_600}, {"nba": 400},
                    pool_now=69_000)
    assert "order: NFL > CFB > NBA > MLB > NHL · UFC · WNBA" in text
    assert ("tonight's games are funded first, in that order; then the month: the NFL, "
            "then every sport playing held 50% of its need before any gets more") in text
    assert "  tonight: NBA 9 · NHL 6 — funded first" in text, text
    assert "each sport's month: budget = spent + left (fill)" in text
    left = nba.alloc - 400
    assert f"NBA   {6_200 + left:>7,} = {6_200:>6,} + {left:>6,} ({nba.fill * 100:>3.0f}%)" in text, text
    assert "MLB   out of season" in text, "baseball's table ends November 4"
    early = P.report(P.build(dt.date(2026, 10, 28), 9_000), {})
    assert "order: NFL > NBA > CFB > MLB > NHL · UFC · WNBA" in early, "Ethan's October call, said"


def test_the_report_run_by_hand_says_it_cannot_see_the_services_renewal_day():
    """Ethan, 2026-10-30: he set QB_ODDS_RESET_DAY with setenv, restarted,
    ran the plan by hand — and its line still read ASSUMED. The service
    reads /etc/qellys/env; `sudo -u qellys python3 -m engine.oddsplan` does
    not, and the report now says so under that line, with the command that
    shows the service's value."""
    import inspect
    plan = P.build(NOV1, 100_000)
    note = P.shell_note(plan, env={})
    assert note.startswith("  (run by hand, this shell can't see the service's settings")
    assert "sudo grep QB_ODDS_RESET_DAY /etc/qellys/env" in note
    assert P.shell_note(plan, env={P.RESET_DAY_ENV: "1"}) == "", "a shell that was told"
    told = P.build(NOV1, 100_000, end=dt.date(2026, 12, 1), reset="set", start=NOV1)
    assert P.shell_note(told, env={}) == ""
    src = inspect.getsource(P.main)
    assert "lines.insert(2, note)" in src and "shell_note(plan)" in src


def test_the_pace_line_says_whether_the_pool_lasts():
    """Ethan: "make sure we're not running through credits like crazy" —
    every lane's spend a day, and the day the pool runs dry at it."""
    plan = P.build(TUE, 60_000, end=dt.date(2026, 12, 1), reset="measured", start=NOV1)
    calm = P.pace_line(plan, {"nfl": 1_200, "nba": 500, "harvest": 300}, 60_000)
    assert calm == "  pace: 2,000 a day — the pool outlasts the renewal (Dec 1) ✓", calm
    hot = P.pace_line(plan, {"nfl": 4_000, "nba": 1_000}, 60_000)
    assert hot.startswith("  pace: 5,000 a day — at that pace the pool runs dry Nov 21, 10 day(s) "
                          "before the renewal"), hot
    assert P.pace_line(plan, {}, 60_000) == "" and P.pace_line(plan, None) == ""
    text = P.report(plan, {}, {}, pool_now=60_000, recent={"nfl": 4_000, "nba": 1_000}, recent_days=3)
    assert "last 3 days, a day: NFL 4,000 · NBA 1,000" in text and "runs dry Nov 21" in text


def test_month_spend_and_the_last_seven_days():
    rows = [
        {"iso": "2026-10-13T10:00:00", "kind": "live_event", "sport": "nfl", "credits": 999},
        {"iso": "2026-10-14T10:00:00", "kind": "live_event", "sport": "nfl", "credits": 400},
        {"iso": "2026-10-15T10:00:00", "kind": "live_board", "sport": "nba_lines", "credits": 3},
        {"iso": "2026-10-16T10:00:00", "kind": "hist_event", "sport": "mlb", "credits": 190},
        {"iso": "2026-10-17T10:00:00", "kind": "slip_event", "sport": "nfl", "credits": 25},
        {"iso": "2026-10-21T10:00:00", "kind": "live_event", "sport": "nhl", "credits": 700},
    ]
    got = P.month_spend(rows, dt.date(2026, 10, 14))
    assert got == {"nfl": 400, "nba": 3, "harvest": 190, "slips": 25, "nhl": 700}, got
    week = P.recent_daily(rows, OCT21)
    assert week == {"nfl": 57, "nba": 0, "harvest": 27, "slips": 4}, \
        f"seven FULL days, today left out: {week}"


# --- the pacer fixes that came with the plan ------------------------------------------
def test_basketball_and_hockey_keep_their_own_two_windows():
    assert ob._touchpoints("nba") == ob._touchpoints("nhl") == ob._touchpoints("wnba") == (12, 18)
    assert ob._touchpoints("nfl") == ob._touchpoints() == ob.TOUCHPOINTS
    assert ob._touchpoints("nba_board_lines") == ob.TOUCHPOINTS, \
        "a three-credit lane keeps the four windows"
    os.environ["QB_ODDS_WINDOWS"] = "6,9"
    try:
        assert ob._touchpoints("nba") == ob._touchpoints("nfl") == (6, 9)
    finally:
        os.environ.pop("QB_ODDS_WINDOWS", None)


def _ten_am() -> float:
    return dt.datetime(2026, 11, 10, 10, 0, tzinfo=ET).timestamp()


def test_basketball_does_not_burst_its_three_pull_day():
    """Inside the pre-game window baseball's share is tripled (PRIME_BURST)
    and basketball's is not: the burst would spend a three-pull day before
    the 6pm window, the one after the injury reports. 10am Eastern, so no
    window is owed to either."""
    now = _ten_am()
    kicks = [now + 2 * 3600]
    path = _state(remaining=60_000, nba=now - 2 * 3600, mlb=now - 2 * 3600)
    allowance = ob.daily_allowance(ob.load(path), dt.date.fromtimestamp(now))
    share = 300 / allowance              # 300 credits: two 150-credit pulls a day
    with _Swap(path, _ledger([])):
        nba, why = ob.should_refresh(0, now=now, path=path, kickoffs=kicks, sport="nba",
                                     share=share, credits=150)
        mlb, _ = ob.should_refresh(0, now=now, path=path, kickoffs=kicks, sport="mlb",
                                   share=share, credits=150)
    assert mlb, "the burst no longer reaches the leagues it is for"
    assert not nba and "next odds refresh" in why, why


def test_a_day_with_no_game_near_is_off_peak_for_the_cheap_lanes():
    now = _ten_am()
    assert ob.slate_is_far([now + 50 * 3600, now + 60 * 3600], now)
    assert ob.slate_is_far([now - 20 * 3600], now), "a week of finals is not a live slate"
    assert not ob.slate_is_far([now + 50 * 3600, now + 30 * 3600], now)
    assert not ob.slate_is_far([], now) and not ob.slate_is_far(None, now)
    assert not ob.slate_is_far(["13:00", None], now), "no numeric time is no time at all"
    path = _state(remaining=60_000, nfl_lines=now - 20 * 60)
    allowance = ob.daily_allowance(ob.load(path), dt.date.fromtimestamp(now))
    with _Swap(path, _ledger([])):
        blind, _ = ob.should_refresh(0, now=now, path=path, kickoffs=None,
                                     sport="nfl_lines", share=600 / allowance, credits=3)
        far, why = ob.should_refresh(0, now=now, path=path, kickoffs=[now + 50 * 3600],
                                     sport="nfl_lines", share=600 / allowance, credits=3)
    assert blind, "a board with no times keeps the old fifteen-minute cadence"
    assert not far and "off-peak" in why, why


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
