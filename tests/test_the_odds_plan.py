"""The month's odds plan: every league in season budgeted, the NFL first.

Ethan, 2026-10-21: "we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority".

What this file holds the plan (engine/oddsplan) to:

* THE NFL FIRST. A month that cannot fund everyone funds the NFL's target
  in full before anyone else's, then college's; the other leagues share
  what is left at one fill, so a short month thins them all a little
  rather than switching the last one off. Nobody gets headroom while any
  league's target is cut.
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
def test_the_nfl_is_funded_first_when_the_month_is_short():
    plan = P.build(TUE, 20_000)
    nfl = plan.get("nfl")
    assert plan.spendable < nfl.need, "the fixture is meant to be short of the NFL alone"
    assert nfl.target == plan.spendable, (nfl.target, plan.spendable)
    for lg in P.PRIORITY[1:]:
        assert plan.get(lg).alloc == 0, f"{lg} was funded before the NFL's target"


def _short_plan():
    """A November pool that funds the NFL and college in full and the rest
    in part — found, not hand-computed, so it survives the tables moving."""
    for pool in range(40_000, 200_000, 500):
        plan = P.build(NOV1, pool)
        rest = [plan.get(lg) for lg in P.TIERS[2] if plan.get(lg).need > 0]
        if plan.get("nfl").fill == 1 and plan.get("cfb").fill == 1 \
                and all(0.3 < lp.fill < 0.9 for lp in rest):
            return plan
    raise AssertionError("no pool funds football in full and the rest in part")


def test_college_comes_second_and_the_rest_share_one_fill():
    plan = _short_plan()
    fills = [plan.get(lg).fill for lg in P.TIERS[2] if plan.get(lg).need > 0]
    assert len(fills) >= 3, fills
    assert max(fills) - min(fills) < 0.01, \
        f"the third tier is not at one fill: {fills} — someone was cut before the rest"


def test_nobody_gets_headroom_while_a_target_is_cut():
    plan = _short_plan()
    assert all(lp.extra == 0 for lp in plan.leagues.values()), \
        {lg: lp.extra for lg, lp in plan.leagues.items()}


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
                assert lp.envelope == int(lp.today_need * lp.fill), (day, pool, lp.league)


def test_a_month_spent_at_every_ceiling_never_overspends():
    """Every league spending its whole ceiling every day, and the harvest
    its whole cap: the month still ends above the reserve, the NFL is
    funded in full every day, and little is left to expire at the reset."""
    for first in (dt.date(2026, 10, 1), NOV1, dt.date(2026, 12, 1)):
        pool, day, end = 100_000, first, P.period(first)[1]
        while day < end:
            plan = P.build(day, pool)
            assert plan.get("nfl").fill >= 1.0, f"{day}: the NFL is short ({plan.get('nfl').fill:.2f})"
            pool -= sum(lp.envelope for lp in plan.leagues.values()) + P.HARVEST_DAY
            day += dt.timedelta(days=1)
        assert pool >= ob.RESERVE, f"{first:%B}: the month overspent — {pool} left"
        assert pool < 100_000 * 0.05, f"{first:%B}: {pool} credits left to expire"


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


def test_the_nfl_keeps_its_day_whatever_its_board_says():
    """The league funded first is not zeroed by a board that failed to build."""
    assert P.day_need("nfl", TUE, 0) == P.NFL_REGULAR[TUE.weekday()] > 0
    assert P.day_need("nfl", NOV1, None) == P.NFL_REGULAR[6]


def test_college_buys_its_lines_every_day_of_its_season():
    sunday = dt.date(2026, 11, 8)
    assert P.day_need("cfb", sunday, 0) == P.LINES_BY_WEEKDAY["cfb"][6] * P.LINES_CREDITS > 0
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
    saved = launch._games_today
    launch._games_today = lambda: dict(TONIGHT)
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
    finally:
        launch._games_today = saved


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
    import launch
    d = tempfile.mkdtemp()
    now = time.time()

    def board(name, games):
        path = os.path.join(d, name)
        with open(path, "w") as fh:
            json.dump({"games": games}, fh)
        return path

    iso = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()
    saved = {k: getattr(launch, k) for k in
             ("MLB_OUT", "NBA_OUT", "WNBA_OUT", "NHL_OUT", "NFL_OUT", "UFC_OUT", "CFB_OUT")}
    launch.NBA_OUT = board("nba.json", [{}] * 7)
    launch.NHL_OUT = board("nhl.json", [{}] * 4)
    launch.MLB_OUT = board("mlb.json", [])
    launch.WNBA_OUT = os.path.join(d, "missing.json")
    launch.NFL_OUT = board("nfl.json", [{}] * 14)
    launch.UFC_OUT = board("ufc.json", [{}] * 12)
    launch.CFB_OUT = board("cfb.json", [
        {"kickoff": iso(now + 3 * 3600)}, {"kickoff": iso(now + 30 * 3600)},
        {"kickoff": iso(now + 60 * 3600)}, {"kickoff": iso(now - 3600)}])
    launch._GAMES_TODAY[:] = [0.0, {}]
    try:
        got = launch._games_today()
        assert got == {"mlb": 0, "nba": 7, "wnba": 0, "nhl": 4, "nfl": 14, "ufc": 12,
                       "cfb": 2}, got
        launch.NBA_OUT = board("nba2.json", [{}] * 9)
        assert launch._games_today()["nba"] == 7, "read again inside the minute"
        launch._GAMES_TODAY[0] -= launch.GAMES_TODAY_TTL_S + 1
        assert launch._games_today()["nba"] == 9, "a minute on, the boards are read again"
    finally:
        for k, v in saved.items():
            setattr(launch, k, v)
        launch._GAMES_TODAY[:] = [0.0, {}]


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
