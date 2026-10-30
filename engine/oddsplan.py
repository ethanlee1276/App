"""The month's odds plan — every sport in season its own budget, NFL first.

Ethan, 2026-10-21: *"we have 100k credit per month for figure out how too
budget in all the sports that are currently active while keeping NFL at
number one priority"*. And 2026-10-28, after October's credits ran out for
every league after football: *"NHL, NBA, WNBA, NFL, college football, MLB,
all of that needs its own budget and needs to be able to budget every
single sport every month with that 100K credit ... NFL comes first, then
college football, then NBA, then baseball since it's about to be over. So
once baseball is over, we can take baseball out of the credit pool, and
whatever other sport is not being played needs to be taken out of the
credit pool ... and make sure we're not running through credits like
crazy."*

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
2. TONIGHT FIRST. Ethan, 2026-10-30, with October's credits nearly gone:
   *"tonight's games come first. We need to make up a system of just
   recognizing what sport has what games live that night and pulling
   credits just for those sports"*. Every league playing tonight is owed
   what tonight's slate costs at its cadence (`day_need` on the real
   count, `games_today`), and that is funded before any day to come, in
   the order below: the NFL's tonight in full, then every other league's
   `FLOOR_SHARE` of its tonight together, then the rest tier by tier. A
   league with no game tonight is owed nothing today — the pacer lets it
   buy nothing (`launch._odds_affordable`) — and its next game night is
   funded with the month. The report's "tonight" line says who plays.
3. TARGETS, IN ETHAN'S ORDER (`TIERS`). Every league in season is owed what
   its target cadence costs for the rest of the month (`day_need`); a
   league out of season, or whose own board says its season is over
   (`over`: baseball the morning after the World Series), is owed nothing
   and is out of the pool. The NFL's target is funded first and in full.
   Then EVERY OTHER LEAGUE IN SEASON gets `FLOOR_SHARE` of its target
   together — its own budget, which no league below the NFL can take: a
   short month can thin a sport, never switch it off, which is what
   October did to basketball and hockey. Then the rest of each target,
   tier by tier: college, the NBA, baseball, then hockey, UFC and the WNBA
   at one fill (proportional within a tier).
4. HEADROOM, IN THE SAME ORDER: the NFL up to `NFL_HEADROOM` more, then
   each later tier up to `HEADROOM` more — extra pulls on a busy news day
   rather than credits that expire at the reset. A tier whose target was
   cut gets none.
5. Whatever is left is UNPLANNED, and the report says how much.

EACH SPORT'S BUDGET FOR THE MONTH is what it has spent since the renewal
plus what the plan holds for it from today: the report prints it that way
("budget = spent + left"), beside the pace the pool is going at and the day
that pace would empty it.

HOW A DAY IS METERED. A league's ceiling today is its need today times the
share of its month the plan could fund (its FILL), and never less than what
step 2 funded for tonight: `envelope`. The launcher
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
next plan cuts from the last tier's share past its floor, never from the
NFL's target and never below anyone's floor until the NFL's own target
needs it; credits a lane did not spend (the harvest's unused cap, a quiet
day, a season that ended early) come back as fill for the days after.

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
#: Ethan, 2026-10-28: "NFL comes first, then college football, then NBA,
#: then baseball since it's about to be over". Hockey, UFC and the WNBA,
#: which he did not place, come after baseball together, at one fill
#: (proportional within the tier), so none of them is the one cut first.
#: Every one of them past the NFL is owed its floor before any of them is
#: owed more (`FLOOR_SHARE`).
TIERS = (("nfl",), ("cfb",), ("nba",), ("mlb",), ("nhl", "ufc", "wnba"))
#: Every league, in the order the report lists them.
PRIORITY = tuple(lg for tier in TIERS for lg in tier)

#: EVERY SPORT ITS OWN BUDGET (Ethan, 2026-10-28: "all of that needs its own
#: budget"). After the NFL's target, every other league in season is funded
#: this share of its own target before any of them gets more — together, in
#: proportion, when the month cannot cover even that. October funded the
#: NFL and college in full and left basketball and hockey nothing (DK: 0
#: NBA props priced); half a target is a prop pull or two on every game
#: night, which is Edge and Most Likely on the board.
FLOOR_SHARE = 0.5

#: ETHAN'S CALL, 2026-10-28: "we still don't have edge bets or most likely
#: bets for nba. We need that now". October's credits had run out for every
#: league after the NFL and college (DK: 0 NBA props priced), and of the
#: ways to pay for the month's last days he chose the NBA before college
#: until the plan renews. Before this day the NBA is funded right after the
#: NFL; from it, TIERS stands again by itself.
NBA_FIRST_UNTIL = _dt.date(2026, 11, 1)


def tiers(day: _dt.date) -> tuple:
    """The order the plan funds the leagues in on ``day`` (TIERS, but for
    NBA_FIRST_UNTIL)."""
    if day < NBA_FIRST_UNTIL:
        return (("nfl",), ("nba",), ("cfb",)) + TIERS[3:]
    return TIERS

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
#: two Monday), in the pacer's days (the service's date, Eastern). It buys
#: on game nights only (`oddsbudget.tonight_games`), and only tonight's
#: games (`launch._tonight_args`: the rest of the week's board is read from
#: the cache), at 25 credits a game (`oddsbudget.EVENT_CREDITS`).
#:
#:   Sunday   the ceiling the day runs up to: the four windows (7am, 12, 3pm,
#:            6pm ET), a readiness and an inactives pull for each wave (1pm,
#:            4pm, the night game), the slate shrinking through the day, and
#:            the game-lines lane every fifteen minutes in the window (~210).
#:   Thursday the priority floor (`oddsbudget.PRIORITY_PULLS`: six pulls on a
#:            day with a kickoff inside 24h) of the one game, and its lines.
#:            Until 2026-10-30 every pull priced the week's board — 2,000.
#:   Monday   the floor on the Monday game(s); lines in its window.
#:   other    nothing — no game tonight. A game night the table does not
#:            hold (Thanksgiving's Friday, December's Saturdays, Christmas)
#:            is priced by the game (`NFL_FLOOR_PULLS`).
NFL_REGULAR = (600, 0, 0, 400, 0, 0, 3500)
#: The playoffs: wild-card weekend's Saturday, Sunday and Monday, two games
#: each weekend day of the next two rounds, one on Super Bowl Sunday.
NFL_PLAYOFFS = (400, 0, 0, 0, 0, 1600, 1600)
#: A game night by the game, when the table holds less: the priority floor's
#: six pulls of tonight's games and the lines lane's ~30 three-credit pulls.
NFL_FLOOR_PULLS = 6
NFL_LINES_PULLS = 30

#: Average games a day, Monday to Sunday, in a regular season — the games
#: a pull buys that day, which under the tonight rule are that night's
#: games: college's weeknight games and Saturday's (a pull prices twelve at
#: most, `PULL_CAP`), and UFC's card on fight night.
GAMES_BY_WEEKDAY = {
    "nba": (7, 6, 10, 4, 9, 7, 7),
    "nhl": (4, 10, 5, 11, 5, 13, 4),
    "mlb": (15, 15, 15, 15, 15, 15, 15),
    "wnba": (4, 4, 4, 4, 4, 4, 4),
    "cfb": (0, 1, 1, 2, 3, 12, 0),
    "ufc": (0, 0, 0, 0, 0, 13, 0),
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
#: fifteen minutes (~43). College's (`launch.CFB_LINES_CLOCK`) runs on its
#: game nights — it ran every day of the season until the tonight rule —
#: and through the games, so it is college's live line too: ~40 on a
#: weeknight with one, ~58 on Thursday and Friday, ~78 across Saturday's
#: eighteen-hour window. The NFL's lane is inside its day table above.
#: Hockey and baseball have no pre-game tier: their prop pull carries the
#: game lines.
LINES_BY_WEEKDAY = {"nba": (43,) * 7, "wnba": (43,) * 7,
                    "cfb": (24, 40, 40, 58, 58, 78, 24)}
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

    ``games`` is tonight's real slate (`launch._games_today`) and replaces
    the table: a 12-game NBA night is priced as twelve games, a night with
    none as nothing — the NFL's too, which buys nothing on a night it does
    not play (`oddsbudget.tonight_games`). None (a board whose times could
    not be read) leaves the table to answer.
    """
    wd = day.weekday()
    if league == "nfl":
        if games is not None and games <= 0:
            return 0
        phase = season_phase("nfl", day)
        table = (NFL_PLAYOFFS if phase == "playoffs" else
                 NFL_REGULAR if phase == "regular" else (0,) * 7)[wd]
        if games is None:
            return table
        return max(table, NFL_FLOOR_PULLS * (int(games) + 1) * price("nfl")
                   + NFL_LINES_PULLS * LINES_CREDITS)
    g = expected_games(league, day) if games is None else float(games)
    if g <= 0 or league not in PULLS:
        return 0
    lines = LINES_BY_WEEKDAY.get(league, (0,) * 7)[wd] * LINES_CREDITS
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
    envelope: int = 0         # today's ceiling: today_need × fill, at least `first`
    over: bool = False        # its own board says its season is over (`build`)
    tonight: float | None = None   # games tonight (None: not counted)
    first: int = 0            # what step 2 funded for tonight's games

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
          start: _dt.date | None = None, headroom: bool = True,
          over=()) -> Plan:
    """The month's plan from ``pool``, the credits at the start of ``day``,
    to ``end`` (the renewal; the calendar month's end when not given).

    ``headroom`` False pays every target and nothing on top — the box's
    plan while the renewal day is only assumed (`current`). Headroom is
    what lets a league spend past its cadence, and a month planned to the
    wrong end would spend it on days that belong to the next one; the
    targets alone are what the leagues need, whichever month it is.

    ``over`` names the leagues whose own board says the season has ended
    (`launch._seasons_over`): owed nothing today or after, whatever the
    season table says, so what the table would have held for them goes to
    the leagues still playing.

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
    order = tiers(day)
    for i, tier in enumerate(order, 1):
        for lg in tier:
            done = lg in over
            today = 0 if done else day_need(lg, day, games_today.get(lg))
            rest = 0 if done else sum(day_need(lg, d) for d in days[1:])
            plan.leagues[lg] = LeaguePlan(league=lg, priority=i, over=done,
                                          need=today + rest, today_need=today,
                                          tonight=games_today.get(lg))

    def share_out(tier, owed, money):
        """Hand ``money`` across ``tier`` in proportion to what each is
        ``owed``; every league in the tier gets the same fraction."""
        total = sum(owed.values())
        if money >= total:
            return {lg: owed[lg] for lg in tier}
        if len(tier) == 1:                   # a tier of one takes every credit
            return {lg: int(money) for lg in tier}
        frac = money / total if total > 0 else 0.0
        return {lg: int(owed[lg] * frac) for lg in tier}

    def fund(tier, owed):
        """Add to the targets in ``tier`` out of what is ``left``."""
        nonlocal left
        for lg, n in share_out(tier, owed, left).items():
            plan.leagues[lg].target += n
            left -= n

    def rest_of(lg, owed):
        return max(0, owed - plan.leagues[lg].target)

    left = spendable
    first, later = order[0], [lg for tier in order[1:] for lg in tier]
    # 2. TONIGHT FIRST, in the month's order: the NFL's, every floor after
    # it, then the rest of tonight tier by tier.
    fund(first, {lg: plan.leagues[lg].today_need for lg in first})
    fund(later, {lg: int(plan.leagues[lg].today_need * FLOOR_SHARE) for lg in later})
    for tier in order[1:]:
        fund(tier, {lg: rest_of(lg, plan.leagues[lg].today_need) for lg in tier})
    for lp in plan.leagues.values():
        lp.first = lp.target
    # 3. The month: the NFL's target, every floor after it, then the rest.
    fund(first, {lg: rest_of(lg, plan.leagues[lg].need) for lg in first})
    fund(later, {lg: rest_of(lg, int(plan.leagues[lg].need * FLOOR_SHARE))
                 for lg in later})
    for tier in order[1:]:
        fund(tier, {lg: rest_of(lg, plan.leagues[lg].need) for lg in tier})
    short = (not headroom
             or any(lp.target < lp.need for lp in plan.leagues.values()))
    for i, tier in enumerate(order):                     # 4. headroom, same order
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
        lp.envelope = max(lp.first, int(lp.today_need * lp.fill))
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
            path=None, over=()) -> Plan:
    """Today's plan from the real budget state.

    The pool is taken AT THE START OF THE DAY — what is left now plus what
    the ledger says today already spent — so a pull made this morning does
    not shrink this afternoon's plan a second time on top of counting
    against today's ceiling. The day is the pacer's own (the box's local
    date, the one `oddsbudget.spent_today` keys on). ``over``: the leagues
    whose own board says the season has ended (`build`).
    """
    from . import oddsbudget as ob
    now = time.time() if now is None else now
    state = ob.load(path) if path else ob.load()
    if not ob.is_measured(state):
        raise PlanUnavailable("the odds quota has not been read from the API yet")
    day = _dt.date.fromtimestamp(now)
    pool = int(state.remaining) + int(ob.spent_today(now) or 0)
    start, end, how = renewal(day, state)
    over = frozenset(over or ())
    key = (day, pool, end, tuple(sorted((games_today or {}).items())), over)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    plan = build(day, pool, games_today, end=end, reset=how, start=start,
                 headroom=how != "assumed", over=over)
    _CACHE.clear()                                       # one day's plan at a time
    _CACHE[key] = plan
    return plan


def envelope(league: str, games_today: dict | None = None,
             now: float | None = None, path=None, over=()) -> int:
    """This league's ceiling for today, in credits."""
    from .oddsbudget import budget_sport
    lp = current(games_today, now, path, over).get(budget_sport(league))
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
           recent: dict | None = None, recent_days: int = 7) -> str:
    """The plan in words a phone screen holds.

    Each sport's line is its MONTH: what it has spent since the renewal
    plus what the plan holds for it from now — its own budget — with the
    share of its need that covers, then today's ceiling. ``recent`` is a
    day's spend by lane over the last ``recent_days`` full days
    (`recent_daily`), and the pace line says how long the pool lasts at it.
    """
    spent_month = spent_month or {}
    spent_today = spent_today or {}
    d = plan.day
    ends = plan.ends or period(d)[1]
    order = tiers(d)
    lines = [f"ODDS PLAN · {d.strftime('%a %b')} {d.day} · {plan.days_left} day(s) "
             f"left · renews {ends.strftime('%b')} {ends.day}",
             f"  renewal day {RESET_WORDS.get(plan.reset, plan.reset)}"
             + ("" if plan.headroom else " · no headroom until it is known"),
             f"  pool {plan.pool:,} at the start of today"
             + (f" ({pool_now:,} now)" if pool_now is not None else ""),
             f"  held back: reserve {plan.reserve:,} · closing lines "
             f"{plan.harvest:,} ({HARVEST_DAY} a day) · buffer {plan.buffer:,} "
             f"({int(BUFFER_SHARE * 100)}%)",
             f"  planned for the sports: {plan.spendable - plan.unplanned:,}"
             f" · unplanned {plan.unplanned:,}",
             "  order: " + " > ".join(" · ".join(LABEL[lg] for lg in t) for t in order)]
    tonight = tonight_line(plan)
    if tonight:
        lines.append(tonight)
    lines += [f"  tonight's games are funded first, in that order; then the month: "
              f"the NFL, then every sport playing held {int(FLOOR_SHARE * 100)}% "
              f"of its need before any gets more",
              "",
             "  each sport's month: budget = spent + left (fill) | today: need -> ceiling, spent"]
    for lg in (lg for t in order for lg in t):
        lp = plan.leagues[lg]
        spent = int(spent_month.get(lg, 0))
        if lp.need <= 0:
            word = ("season over — out of the pool" if lp.over else
                    "no game before the renewal — buys nothing"
                    if season_phase(lg, d) is not None else "out of season")
            lines.append(f"  {LABEL[lg]:<5} {word}"
                         + (f" (spent {spent:,} this month)" if spent else ""))
            continue
        today = int(spent_today.get(lg, 0))
        left = max(0, lp.alloc - today)
        lines.append(f"  {LABEL[lg]:<5} {spent + left:>7,} = {spent:>6,} + {left:>6,} "
                     f"({lp.fill * 100:>3.0f}%) | {lp.today_need:>5,} -> "
                     f"{lp.envelope:>5,}, {today:,}"
                     + (" · no game tonight" if lp.tonight == 0 else ""))
    month = [f"{LABEL.get(k, k)} {v:,}" for k, v in
             sorted(spent_month.items(), key=lambda t: -t[1])]
    if month:
        lines += ["", "  spent this month: " + " · ".join(month)]
    week = [f"{LABEL.get(k, k)} {v:,}" for k, v in
            sorted((recent or {}).items(), key=lambda t: -t[1]) if v]
    if week:
        lines += [f"  last {recent_days} day{'s' if recent_days != 1 else ''}, a day: "
                  + " · ".join(week)]
    pace = pace_line(plan, recent, pool_now)
    if pace:
        lines.append(pace)
    return "\n".join(lines)


def tonight_line(plan: Plan) -> str:
    """Who plays tonight — the leagues the pacer lets buy, funded first —
    and who is in season with no game ("" when tonight was not counted)."""
    order = [lg for t in tiers(plan.day) for lg in t]
    counted = [lg for lg in order if plan.leagues[lg].tonight is not None]
    if not counted:
        return ""
    playing = [f"{LABEL[lg]} {int(plan.leagues[lg].tonight)}" for lg in counted
               if plan.leagues[lg].tonight > 0]
    idle = [LABEL[lg] for lg in counted
            if plan.leagues[lg].tonight <= 0 and not plan.leagues[lg].over
            and (plan.leagues[lg].need > 0 or season_phase(lg, plan.day) is not None)]
    head = ("  tonight: " + " · ".join(playing) + " — funded first" if playing
            else "  tonight: no games — nothing is bought today")
    return head + (f"; no game: {', '.join(idle)} (they buy nothing today)"
                   if idle else "")


def shell_note(plan: Plan, env=None) -> str:
    """A line for the report run by hand. `sudo -u qellys` gives this shell
    none of the service's settings, so a renewal day set in /etc/qellys/env
    is the service's and not this report's: Ethan, 2026-10-30, set it,
    and the report's line still read ASSUMED. "" when the shell was told."""
    import os
    env = os.environ if env is None else env
    if plan.reset == "set" or RESET_DAY_ENV in env:
        return ""
    return (f"  (run by hand, this shell can't see the service's settings; a "
            f"{RESET_DAY_ENV} set there shows with: sudo grep {RESET_DAY_ENV} "
            f"/etc/qellys/env)")


def pace_line(plan: Plan, recent: dict | None, pool_now: int | None = None) -> str:
    """How long the pool lasts at the recent pace, every lane counted —
    Ethan's "make sure we're not running through credits like crazy" as a
    line to read. The plan slows every sport to fit whatever this says;
    a pace that would empty the pool before the renewal is the sign the
    tables are short of what the box really spends."""
    from .oddsbudget import RESERVE
    per_day = sum(int(v) for v in (recent or {}).values() if v)
    if per_day <= 0:
        return ""
    ends = plan.ends or period(plan.day)[1]
    have = max(0, (plan.pool if pool_now is None else pool_now) - RESERVE)
    dry = plan.day + _dt.timedelta(days=have // per_day)
    if dry >= ends:
        return (f"  pace: {per_day:,} a day — the pool outlasts the renewal "
                f"({ends.strftime('%b')} {ends.day}) ✓")
    return (f"  pace: {per_day:,} a day — at that pace the pool runs dry "
            f"{dry.strftime('%b')} {dry.day}, {(ends - dry).days} day(s) before the "
            f"renewal; the plan slows every sport to fit ⚠️")


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
        games, over = launch._games_today(), launch._seasons_over()
    except Exception:                                        # noqa: BLE001
        games, over = None, ()
    try:
        plan = current(games, over=over)
    except PlanUnavailable as exc:
        print(f"No plan yet: {exc}.")
        return 1
    rows = ob.read_spend()
    start = plan.starts or period(plan.day)[0]
    # The pace is this billing month's: the last days of the one before
    # it were spent to another month's plan.
    n = min(7, (plan.day - start).days)
    text = report(plan, month_spend(rows, start), month_spend(rows, plan.day),
                  pool_now=int(ob.load().remaining),
                  recent=recent_daily(rows, plan.day, n) if n else None,
                  recent_days=n or 7)
    note = shell_note(plan)
    if note:                              # under the renewal day's line
        lines = text.splitlines()
        lines.insert(2, note)
        text = "\n".join(lines)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
