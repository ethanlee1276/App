"""The month's odds plan — who gets the plan's credits, NFL first.

Ethan, 2026-10-21: *"we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority"*.

WHAT THIS REPLACES. A league's slice of the day used to be a weight
(`launch.SPORT_WEIGHT`, times 7 over the days a week it plays),
normalised over every league with games on its board. Two things in that
rule starved the leagues it was never asked to starve:

* the NFL and college boards hold the WEEK's games, so they claimed their
  game-day weights on Tuesday too — and with basketball and hockey at 0.15
  the NBA and the NHL drew about 2% of a weekday: ~77 credits against a
  ~156-credit NBA pull, one "sparse" pull a day. That is the opening-night
  board with no lines on it;
* `daily_allowance` plans on half of what is left (LIVE_SHARE), divided by
  the days left, so a month's allowance ramps from ~1,650 a day on the 1st
  to several thousand at the end — thin when the month is young, and about
  a tenth of the plan left over at the reset, where it expires.

HOW THE MONTH IS PLANNED. From the pool at the start of the day, to the
plan's RENEWAL — the day the API's month turns over, which need not be the
1st (`reset_day`: set, measured off the ledger, or assumed and said so):

1. HELD BACK: `oddsbudget.RESERVE`; the closing-line harvest's day cap
   (`maintenance.HARVEST_DAY_BUDGET`) for every day left, because it
   spends on its own meter; and `BUFFER_SHARE` of the pool, never planned.
2. TARGETS, TIER BY TIER (`TIERS`). Every league in season is owed what its
   target cadence costs for the rest of the month (`day_need`). The NFL's
   is funded first and in full; then college's; then every other league in
   season shares what is left IN PROPORTION TO ITS NEED — one fill for the
   tier, so a short month thins every one of them a little rather than
   switching the last on the list off.
3. HEADROOM, IN THE SAME ORDER: the NFL up to `NFL_HEADROOM` more, then
   each later tier up to `HEADROOM` more — extra pulls on a busy news day
   rather than credits that expire at the reset. A tier whose target was
   cut gets none.
4. Whatever is left is UNPLANNED, and the report says how much.

HOW A DAY IS METERED. A league's ceiling today is its need today times the
share of its month the plan could fund (its FILL): `envelope`. The launcher
hands that to the pacer as the league's share of the day
(`launch._budget_share`), so the cadence, the day's ceiling, the
starvation rule and the wide-or-narrow pull all read the plan's number.
The reserve, the fifteen-minute floor, the NFL's priority floor and its
readiness, inactives and closing pulls all stand. Two pacer changes came
with the plan: basketball and hockey pull at noon and 6pm and do not burst
(`oddsbudget.SPORT_TOUCHPOINTS`), and a board whose next game is past the
window's horizon paces off-peak (`oddsbudget.slate_is_far`).

IT IS RECOMPUTED FROM THE REAL BALANCE every cycle (`current`), so it
corrects itself: a league that ran over leaves less in the pool, and the
next plan cuts from the last tier, never from the NFL's target; credits a
lane did not spend (the harvest's unused cap, a quiet day) come back as
fill for the days after.

THE NUMBERS BELOW ARE A MODEL, NOT A MEASUREMENT: a typical week of each
league at the cadence its machinery spends at full strength — the prop
pulls, and the three-credit lines and live lanes that run all day out of
the same ceiling — priced at what each league's event call really costs.
They share the month across days and leagues; today's real slate replaces
the table for today (`games_today`). `python3 -m engine.oddsplan` prints the
plan on the box beside what each league has actually spent this month and
a day over the last seven, which is what the tables are checked against.
docs/ODDS_PLAN.md has the plan in a page.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field

#: WHO IS FUNDED FIRST when the month cannot fund everyone, tier by tier.
#: Ethan, 2026-10-21: "keeping NFL at number one priority" — and "budget in
#: all the sports that are currently active". The NFL alone first; college
#: second, because football has led every budget call he has made
#: (2026-09-07: "prioritize NFL and CFB over anything"); then every other
#: league together, at one fill, so none of them is the one switched off.
TIERS = (("nfl",), ("cfb",), ("mlb", "nba", "nhl", "ufc", "wnba"))
#: Every league, in the order the report lists them.
PRIORITY = tuple(lg for tier in TIERS for lg in tier)

#: Headroom on top of the target, funded only after every tier's target:
#: the NFL's first, up to half again; then each later tier's, a quarter.
NFL_HEADROOM = 0.50
HEADROOM = 0.25

#: Share of the pool never planned. It shrinks with the pool, so the month
#: ends with little held back — credits left at the reset expire.
BUFFER_SHARE = 0.05

#: The closing-line harvest's day cap — `engine.maintenance.
#: HARVEST_DAY_BUDGET`, restated here so this module imports nothing heavy
#: (pinned equal by test). It spends on its own meter every night.
HARVEST_DAY = 400

#: What one game costs on each league's event call, where the pacer's own
#: table (`oddsbudget.EVENT_CREDITS`) does not say: college states its price
#: in its build (`cfb_build.CREDITS_PER_EVENT`, pinned equal by test).
CFB_PRICE = 13

#: A three-credit pull — the board endpoint, three markets, the whole slate:
#: the pre-game lines tier and the live line alike.
LINES_CREDITS = 3
LIVE_CREDITS = 3
#: A league's live pulls an hour. The live clock is SHARED (`livelines.
#: last_pull_ts`) and polls every ten minutes at most (`livelines.
#: LIVE_GAP_FLOOR_S`), six an hour across every league with a game on —
#: two leagues live at once on most nights, so three a league.
LIVE_PULLS_PER_HOUR = 3

#: THE NFL'S DAY, in credits, Monday to Sunday — what its machinery spends
#: at full strength on a normal week (one Thursday game, ~13 Sunday, one or
#: two Monday), in the PACER'S days: the box's date, which is UTC, so a day
#: turns at 8pm Eastern and "Thursday" runs from Wednesday 8pm to Thursday
#: 8pm ET. A full pull prices every game still to play on the week's board
#: at 25 credits (`oddsbudget.EVENT_CREDITS`); a narrow one only the games
#: inside six hours (`oddsbudget.wide_pull_affordable`).
#:
#:   Sunday   the ceiling the day runs up to: the four windows (7am, 12, 3pm,
#:            6pm ET), a readiness and an inactives pull for each wave (1pm,
#:            4pm, the night game), the slate shrinking through the day, and
#:            the game-lines lane every fifteen minutes in the window (~210).
#:   Thursday the priority floor (`oddsbudget.PRIORITY_PULLS`: six pulls on a
#:            day with a kickoff inside 24h) — the week's board until the
#:            Thursday game is six hours out, then narrow pulls of that game;
#:            lines every fifteen minutes in its window.
#:   Saturday the floor from 1pm, when Sunday's first kickoff is inside 24h:
#:            the windows on the week's board.
#:   Monday   the floor on the Monday game(s), narrow; lines in its window.
#:   other    one pull of the week's board (props move all week with the
#:            injury reports) and the hourly lines lane.
NFL_REGULAR = (600, 500, 500, 2000, 600, 1780, 3500)
#: The playoffs: three games a day on wild-card weekend, two in the next two
#: rounds, one on Super Bowl Sunday; a maintenance pull between.
NFL_PLAYOFFS = (400, 200, 200, 200, 200, 1600, 1600)

#: Average games a day, Monday to Sunday, in a regular season. College
#: counts the games inside its 36-hour player window (`cfb_build.
#: PLAYER_WINDOW_HOURS`), so Friday's pulls price Saturday's games; UFC
#: counts the week's card, priced through the week.
GAMES_BY_WEEKDAY = {
    "nba": (7, 6, 10, 4, 9, 7, 7),
    "nhl": (4, 10, 5, 11, 5, 13, 4),
    "mlb": (15, 15, 15, 15, 15, 15, 15),
    "wnba": (4, 4, 4, 4, 4, 4, 4),
    "cfb": (2, 3, 3, 6, 12, 12, 0),
    "ufc": (13, 13, 13, 13, 13, 13, 0),
}
#: Average games a day outside the regular season (playoffs, bowls; one
#: World Series game every day or two).
POSTSEASON_GAMES = {"nba": 3, "nhl": 3, "mlb": 1, "wnba": 1.5, "cfb": 3}

#: Prop pulls a game day gets at the target cadence, with the days that
#: differ. Basketball and hockey: noon, the pre-game run and 6pm ET
#: (`oddsbudget.SPORT_TOUCHPOINTS`). College: eight on Saturday — the
#: windows and a readiness pull for each wave — two on Thursday and
#: Friday, four on the weekday nights. UFC: one a day, four on fight day.
PULLS = {"nba": 3, "nhl": 3, "mlb": 4, "wnba": 3, "cfb": 4, "ufc": 1}
PULLS_ON = {("cfb", 3): 2, ("cfb", 4): 2, ("cfb", 5): 8, ("ufc", 5): 4}
#: The most games one pull prices (college's `PLAYER_EVENT_CAP`).
PULL_CAP = {"cfb": 12}

#: THE THREE-CREDIT LANES, at the pacer's own cadence for a three-credit
#: pull: the fifteen-minute floor (`oddsbudget.MIN_REFRESH_GAP`) inside the
#: pre-game window, four times that off-peak (`OFFPEAK_STRETCH`). Cheap a
#: pull and dear a month — they run all day, and every credit of them
#: comes out of the same league's ceiling as its props.
#:
#: Pre-game lines pulls a day. Basketball's lane (`launch.NBA_BOARD_CLOCK`)
#: runs on a game day until the last tip: hourly to the window, then every
#: fifteen minutes (~43). College's (`launch.CFB_LINES_CLOCK`) runs every
#: day of the season — the board holds the week — and through the games, so
#: it is college's live line too: hourly on a day with no game near, ~58 on
#: a weeknight with one, ~78 across Saturday's eighteen-hour window. The
#: NFL's lane is inside its day table above. Hockey and baseball have no
#: pre-game tier: their prop pull carries the game lines.
LINES_BY_WEEKDAY = {"nba": (43,) * 7, "wnba": (43,) * 7,
                    "cfb": (24, 40, 40, 58, 58, 78, 24)}
#: Leagues whose lines lane runs every day of the season, games or none.
LINES_EVERY_DAY = ("cfb",)
#: Hours a game day has a game in progress, for the live-line lane
#: (`launch.MLB_LINES_CLOCK` and its kin). The football leagues' live line
#: is their lines lane, counted above.
LIVE_HOURS = {"nba": 6, "nhl": 6, "mlb": 4, "wnba": 4}

#: WHEN EACH LEAGUE PLAYS, as (phase, first (month, day), last (month, day)).
#: Approximate and year-agnostic: they only share the month across days.
#: Today's real slate always overrides them.
SEASONS = {
    "nfl": (("regular", (9, 3), (1, 11)), ("playoffs", (1, 12), (2, 15))),
    "cfb": (("regular", (8, 22), (12, 13)), ("bowls", (12, 14), (1, 20))),
    "nba": (("regular", (10, 20), (4, 12)), ("playoffs", (4, 13), (6, 22))),
    "nhl": (("regular", (10, 6), (4, 16)), ("playoffs", (4, 17), (6, 22))),
    "mlb": (("regular", (3, 25), (9, 28)), ("postseason", (9, 29), (11, 4))),
    "wnba": (("regular", (5, 14), (9, 14)), ("playoffs", (9, 15), (10, 20))),
    "ufc": (("regular", (1, 1), (12, 31)),),
}

LABEL = {"nfl": "NFL", "cfb": "CFB", "nba": "NBA", "nhl": "NHL",
         "mlb": "MLB", "ufc": "UFC", "wnba": "WNBA"}


class PlanUnavailable(Exception):
    """The plan cannot be built (no measured balance yet); callers fall back."""


def _in_window(day: _dt.date, first: tuple, last: tuple) -> bool:
    md = (day.month, day.day)
    if first <= last:
        return first <= md <= last
    return md >= first or md <= last                 # a season over New Year


def season_phase(league: str, day: _dt.date) -> str | None:
    """"regular", a postseason phase, or None out of season."""
    for phase, first, last in SEASONS.get(league, ()):
        if _in_window(day, first, last):
            return phase
    return None


def price(league: str) -> int:
    """Credits one game costs on this league's event call."""
    if league == "cfb":
        return CFB_PRICE
    from .oddsbudget import credits_per_event
    return credits_per_event(league)


def expected_games(league: str, day: _dt.date) -> float:
    """The table's games for this league on this day (0 out of season)."""
    phase = season_phase(league, day)
    if phase is None:
        return 0.0
    if phase == "regular":
        return float(GAMES_BY_WEEKDAY.get(league, (0,) * 7)[day.weekday()])
    return float(POSTSEASON_GAMES.get(league, 0))


def day_need(league: str, day: _dt.date, games: float | None = None) -> int:
    """Credits this league's target cadence costs on this day.

    ``games`` is today's real slate (from the built board) and replaces the
    table: a 12-game NBA night is priced as twelve games, an empty one as
    nothing. The NFL reads its weekday table whatever its board says while
    it is in season — a board that failed to build must not zero the
    league that is funded first.
    """
    wd = day.weekday()
    if league == "nfl":
        phase = season_phase("nfl", day)
        if phase == "playoffs":
            return NFL_PLAYOFFS[wd]
        if phase == "regular" or (games or 0) > 0:
            return NFL_REGULAR[wd]
        return 0
    g = expected_games(league, day) if games is None else float(games)
    lines_daily = (league in LINES_EVERY_DAY
                   and (season_phase(league, day) is not None or g > 0))
    if (g <= 0 and not lines_daily) or league not in PULLS:
        return 0
    lines = LINES_BY_WEEKDAY.get(league, (0,) * 7)[wd] * LINES_CREDITS
    if g <= 0:
        return lines
    priced = min(g, PULL_CAP.get(league, g))
    pulls = PULLS_ON.get((league, wd), PULLS[league])
    props = pulls * (priced + 1) * price(league)
    live = LIVE_HOURS.get(league, 0) * LIVE_PULLS_PER_HOUR * LIVE_CREDITS
    return int(round(props + lines + live))


#: THE DAY OF THE MONTH THE ODDS API PLAN RENEWS, when it must be said
#: outright. The plan spends to the end of the BILLING month, and the
#: pacer has always taken that to be the calendar month. A plan that
#: renews on the 14th would then read October 31 as the last day of a
#: month that runs to November 13, and spend thirteen days of credits in
#: one — so the renewal day is measured when it is not set
#: (`measured_start`), and the calendar month is only the last resort.
RESET_DAY_ENV = "QB_ODDS_RESET_DAY"


def _on_day(year: int, month: int, dom: int) -> _dt.date:
    """``dom`` in that month, clamped to its length (a 31st in April is the 30th)."""
    nxt = _dt.date(year + (month == 12), month % 12 + 1, 1)
    return _dt.date(year, month, min(dom, (nxt - _dt.timedelta(days=1)).day))


def period(day: _dt.date, reset_day: int = 1) -> tuple[_dt.date, _dt.date]:
    """(first day, first day of the next) of the billing month ``day`` is in."""
    start = _on_day(day.year, day.month, reset_day)
    if start > day:
        prev = day.replace(day=1) - _dt.timedelta(days=1)
        start = _on_day(prev.year, prev.month, reset_day)
    after = start.replace(day=1) + _dt.timedelta(days=32)
    return start, _on_day(after.year, after.month, reset_day)


def measured_start(used: int, rows: list, today: _dt.date) -> _dt.date | None:
    """The day this billing month began, read off the ledger: walking back
    from today, the day the ledger's credits reach what the API says the
    key has ``used`` since its reset (its own `x-requests-used`).

    None when it cannot be told — too little used to say (`MIN_USED`), or
    a ledger that runs out (or passes a month) before it adds up. Errs
    late: a ledger that over-counts finds a later start, which plans a
    longer month and spends slower; the five per cent of slack is for the
    estimate, not for that.
    """
    if not used or used < MIN_USED:
        return None
    by_day: dict = {}
    for r in rows or []:
        d = str(r.get("iso", ""))[:10]
        try:
            by_day[d] = by_day.get(d, 0) + int(r.get("credits", 0) or 0)
        except (TypeError, ValueError):
            continue
    total = 0
    for back in range(0, 32):
        d = today - _dt.timedelta(days=back)
        total += by_day.get(d.isoformat(), 0)
        if total >= used * 0.95:
            return d
    return None


#: Below this many credits used, a billing month is too young to measure:
#: any stray ledger row would match it.
MIN_USED = 100
#: A quota reading older than this is not today's (`last_seen_iso`).
READING_MAX_AGE_DAYS = 3


def reset_day(state=None, rows=None, today: _dt.date | None = None) -> tuple[int, str]:
    """(the day of the month the plan renews, how that is known): "set"
    (`RESET_DAY_ENV`), "measured" (`measured_start`, one key on the ring —
    two keys' spend is one ledger and their resets are two dates), or
    "assumed" (the 1st, the calendar month the pacer always used)."""
    import os
    raw = os.environ.get(RESET_DAY_ENV, "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 31:
        return int(raw), "set"
    today = today or _dt.date.today()
    try:
        # `used` is the API's count AT ITS LAST READING, so the ledger is
        # walked back from that day — and a reading days old is not used.
        seen = _dt.date.fromisoformat(str(state.last_seen_iso)[:10])
        keys = [v for v in _ring(state) if int(v.get("remaining") or 0) > 0]
        if len(keys) <= 1 and 0 <= (today - seen).days <= READING_MAX_AGE_DAYS:
            used = int(keys[0].get("used", 0) or 0) if keys else int(state.used or 0)
            start = measured_start(used, rows, seen)
            if start is not None:
                return start.day, "measured"
    except Exception:                                        # noqa: BLE001
        pass
    return 1, "assumed"


def _ring(state) -> list:
    """The key ring's entries the pool counts — the keys in the environment
    now (`oddsbudget._pool_remaining`'s rule: a rotated key's last reading
    stays in the state file, and is not a key)."""
    entries = dict(getattr(state, "keys", None) or {})
    try:
        from .oddsbudget import fingerprint
        from .sources.oddsapi import api_keys
        active = {fingerprint(k) for k in api_keys()}
    except Exception:                                        # noqa: BLE001
        active = set()
    if active:
        entries = {fp: v for fp, v in entries.items() if fp in active}
    return list(entries.values())


def days_left(day: _dt.date, end: _dt.date | None = None) -> list[_dt.date]:
    """Today and every day after it in the billing month — up to ``end``
    (the renewal; the calendar month's end when not given)."""
    if end is None:
        end = period(day)[1]
    return [day + _dt.timedelta(days=i) for i in range(max(1, (end - day).days))]


@dataclass
class LeaguePlan:
    league: str
    priority: int
    need: int = 0             # the rest of the month at the target cadence
    target: int = 0           # the part of the need the month could fund
    extra: int = 0            # headroom on top
    today_need: int = 0
    envelope: int = 0         # today's ceiling: today_need × fill

    @property
    def alloc(self) -> int:
        return self.target + self.extra

    @property
    def fill(self) -> float:
        return self.alloc / self.need if self.need > 0 else 0.0


@dataclass
class Plan:
    day: _dt.date
    days_left: int
    pool: int                 # credits at the start of the day
    reserve: int
    harvest: int
    buffer: int
    spendable: int
    unplanned: int
    leagues: dict = field(default_factory=dict)
    ends: _dt.date | None = None    # the renewal: the first day of the next month
    reset: str = "assumed"          # how the renewal day is known (`reset_day`)
    starts: _dt.date | None = None  # this billing month's first day
    headroom: bool = True           # False: targets only (`build`)

    def get(self, league: str) -> LeaguePlan | None:
        return self.leagues.get(league)


def build(day: _dt.date, pool: int, games_today: dict | None = None,
          end: _dt.date | None = None, reset: str = "assumed",
          start: _dt.date | None = None, headroom: bool = True) -> Plan:
    """The month's plan from ``pool``, the credits at the start of ``day``,
    to ``end`` (the renewal; the calendar month's end when not given).

    ``headroom`` False pays every target and nothing on top — the box's
    plan while the renewal day is only assumed (`current`). Headroom is
    what lets a league spend past its cadence, and a month planned to the
    wrong end would spend it on days that belong to the next one; the
    targets alone are what the leagues need, whichever month it is.

    Pure arithmetic: no file, no clock. See the module docstring for the
    order things are funded in.
    """
    from .oddsbudget import RESERVE
    games_today = games_today or {}
    if end is None:
        start, end = period(day)
    days = days_left(day, end)
    pool = max(0, int(pool))
    harvest = HARVEST_DAY * len(days)
    buffer = int(pool * BUFFER_SHARE)
    spendable = max(0, pool - RESERVE - harvest - buffer)
    plan = Plan(day=day, days_left=len(days), pool=pool, reserve=RESERVE,
                harvest=harvest, buffer=buffer, spendable=spendable, unplanned=0,
                ends=end, reset=reset, starts=start, headroom=headroom)
    for i, tier in enumerate(TIERS, 1):
        for lg in tier:
            today = day_need(lg, day, games_today.get(lg))
            rest = sum(day_need(lg, d) for d in days[1:])
            plan.leagues[lg] = LeaguePlan(league=lg, priority=i,
                                          need=today + rest, today_need=today)

    def share_out(tier, owed, left):
        """Hand ``left`` across ``tier`` in proportion to what each is
        ``owed``; every league in the tier gets the same fraction."""
        total = sum(owed.values())
        frac = min(1.0, left / total) if total > 0 else 0.0
        return {lg: int(owed[lg] * frac) for lg in tier}

    left = spendable
    for tier in TIERS:                                   # 2. targets, NFL first
        got = share_out(tier, {lg: plan.leagues[lg].need for lg in tier}, left)
        for lg, n in got.items():
            plan.leagues[lg].target = n
            left -= n
    short = (not headroom
             or any(lp.target < lp.need for lp in plan.leagues.values()))
    for i, tier in enumerate(TIERS):                     # 3. headroom, same order
        if short:
            break                    # nobody's extra before everybody's target
        rate = NFL_HEADROOM if i == 0 else HEADROOM
        got = share_out(tier, {lg: int(plan.leagues[lg].need * rate)
                               for lg in tier}, left)
        for lg, n in got.items():
            plan.leagues[lg].extra = n
            left -= n
    plan.unplanned = left
    for lp in plan.leagues.values():
        lp.envelope = int(lp.today_need * lp.fill)
    return plan


# --- the plan on the box -------------------------------------------------------
_CACHE: dict = {}
#: The renewal day, worked out once a day — it reads the whole ledger.
_RESET: dict = {}


def renewal(day: _dt.date, state=None) -> tuple[_dt.date, _dt.date, str]:
    """(this billing month's first day, the next renewal, how the renewal
    day is known) for ``day``."""
    hit = _RESET.get(day)
    if hit is None:
        from . import oddsbudget as ob
        try:
            rows = ob.read_spend()
        except Exception:                                    # noqa: BLE001
            rows = []
        hit = reset_day(state if state is not None else ob.load(), rows, day)
        _RESET.clear()
        _RESET[day] = hit
    dom, how = hit
    start, end = period(day, dom)
    return start, end, how


def current(games_today: dict | None = None, now: float | None = None,
            path=None) -> Plan:
    """Today's plan from the real budget state.

    The pool is taken AT THE START OF THE DAY — what is left now plus what
    the ledger says today already spent — so a pull made this morning does
    not shrink this afternoon's plan a second time on top of counting
    against today's ceiling. The day is the pacer's own (the box's local
    date, the one `oddsbudget.spent_today` keys on).
    """
    from . import oddsbudget as ob
    now = time.time() if now is None else now
    state = ob.load(path) if path else ob.load()
    if not ob.is_measured(state):
        raise PlanUnavailable("the odds quota has not been read from the API yet")
    day = _dt.date.fromtimestamp(now)
    pool = int(state.remaining) + int(ob.spent_today(now) or 0)
    start, end, how = renewal(day, state)
    key = (day, pool, end, tuple(sorted((games_today or {}).items())))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    plan = build(day, pool, games_today, end=end, reset=how, start=start,
                 headroom=how != "assumed")
    _CACHE.clear()                                       # one day's plan at a time
    _CACHE[key] = plan
    return plan


def envelope(league: str, games_today: dict | None = None,
             now: float | None = None, path=None) -> int:
    """This league's ceiling for today, in credits."""
    from .oddsbudget import budget_sport
    lp = current(games_today, now, path).get(budget_sport(league))
    return lp.envelope if lp else 0


# --- the report ---------------------------------------------------------------
def month_spend(rows: list, start: _dt.date, end: _dt.date | None = None) -> dict:
    """Credits by league from ``start`` (the billing month's first day) to
    ``end`` (excluded; open when not given), the harvest and the slip lane
    apart. Rows are the spend ledger's.
    """
    from .oddsbudget import HARVEST_KINDS, SLIP_KINDS, budget_sport
    first, stop = start.isoformat(), end.isoformat() if end else "9999"
    out: dict = {}
    for r in rows:
        if not first <= str(r.get("iso", ""))[:10] < stop:
            continue
        kind = str(r.get("kind", "") or "")
        key = ("harvest" if kind in HARVEST_KINDS else
               "slips" if kind in SLIP_KINDS else
               budget_sport(str(r.get("sport", "") or "")) or "other")
        try:
            out[key] = out.get(key, 0) + int(r.get("credits", 0) or 0)
        except (TypeError, ValueError):
            continue
    return out


#: What the report says about the renewal day, by how it is known.
RESET_WORDS = {
    "set": f"set by {RESET_DAY_ENV}",
    "measured": "measured: the ledger's spend since then matches what the "
                "API says this month has used",
    "assumed": f"ASSUMED — the 1st; if your plan renews another day, set "
               f"{RESET_DAY_ENV}",
}


def report(plan: Plan, spent_month: dict | None = None,
           spent_today: dict | None = None, pool_now: int | None = None,
           recent: dict | None = None) -> str:
    """The plan in words a phone screen holds."""
    spent_month = spent_month or {}
    spent_today = spent_today or {}
    d = plan.day
    ends = plan.ends or period(d)[1]
    lines = [f"ODDS PLAN · {d.strftime('%a %b')} {d.day} · {plan.days_left} day(s) "
             f"left · renews {ends.strftime('%b')} {ends.day}",
             f"  renewal day {RESET_WORDS.get(plan.reset, plan.reset)}"
             + ("" if plan.headroom else " · no headroom until it is known"),
             f"  pool {plan.pool:,} at the start of today"
             + (f" ({pool_now:,} now)" if pool_now is not None else ""),
             f"  held back: reserve {plan.reserve:,} · closing lines "
             f"{plan.harvest:,} ({HARVEST_DAY} a day) · buffer {plan.buffer:,} "
             f"({int(BUFFER_SHARE * 100)}%)",
             f"  planned for the leagues: {plan.spendable - plan.unplanned:,}"
             f" · unplanned {plan.unplanned:,}",
             "",
             "  rest of month: need -> planned (fill) | today: need -> ceiling, spent"]
    for lg in PRIORITY:
        lp = plan.leagues[lg]
        if lp.need <= 0 and not spent_month.get(lg):
            lines.append(f"  {LABEL[lg]:<5} out of season")
            continue
        lines.append(f"  {LABEL[lg]:<5} {lp.need:>7,} -> {lp.alloc:>7,} "
                     f"({lp.fill * 100:>3.0f}%) | {lp.today_need:>5,} -> "
                     f"{lp.envelope:>5,}, {int(spent_today.get(lg, 0)):,}")
    month = [f"{LABEL.get(k, k)} {v:,}" for k, v in
             sorted(spent_month.items(), key=lambda t: -t[1])]
    if month:
        lines += ["", "  spent this month: " + " · ".join(month)]
    week = [f"{LABEL.get(k, k)} {v:,}" for k, v in
            sorted((recent or {}).items(), key=lambda t: -t[1]) if v]
    if week:
        lines += ["  last 7 days, a day: " + " · ".join(week)]
    return "\n".join(lines)


def recent_daily(rows: list, today: _dt.date, days: int = 7) -> dict:
    """Credits a day by league over the last ``days`` FULL days (today
    left out) — what the model's tables are checked against."""
    got = month_spend(rows, today - _dt.timedelta(days=days), today)
    return {k: int(round(v / days)) for k, v in got.items()}


def main() -> int:
    """`python3 -m engine.oddsplan` — today's plan beside the real spend."""
    from . import oddsbudget as ob
    try:
        import launch
        games = launch._games_today()
    except Exception:                                        # noqa: BLE001
        games = None
    try:
        plan = current(games)
    except PlanUnavailable as exc:
        print(f"No plan yet: {exc}.")
        return 1
    rows = ob.read_spend()
    today = {lg: ob.spent_today(sport=lg, exclude=ob.HARVEST_KINDS | ob.SLIP_KINDS)
             for lg in PRIORITY}
    start = plan.starts or period(plan.day)[0]
    print(report(plan, month_spend(rows, start), today,
                 pool_now=int(ob.load().remaining),
                 recent=recent_daily(rows, plan.day)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
