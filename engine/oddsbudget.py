"""Odds request budgeting — poll as fast as the plan safely allows.

Refreshing odds is the one expensive thing this app does. A full MLB slate costs
roughly one request per game per refresh, so naive "poll every 90 seconds"
spends ~640 requests an hour — and The Odds API's free tier is **500 per
month**. Left unchecked, an evening of live tracking silently burns the whole
allowance and the board goes stale with no explanation.

So instead of a fixed interval, this module answers a different question:
*given what's left and how long it has to last, how often can we afford to
refresh right now?* It

* records the ``x-requests-remaining`` header the API returns on every call,
  so the budget tracks the real account rather than a guess;
* spreads what remains over the days left in the billing month, holding back a
  reserve so the quota never hits zero mid-evening;
* spends the daily allowance only on games worth refreshing — in-play and
  starting soon — because a game tomorrow doesn't need a new price every minute.

Scores are deliberately *not* budgeted: the MLB and ESPN feeds are free and
unlimited, so live scores can refresh far more often than odds. Keeping the two
on separate cadences is what makes live tracking affordable.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / "data" / "cache" / "odds_budget.json"

# Never spend below this many CREDITS — leaves real room for manual pricing
# and the end of the month. (Was 25 back when a refresh cost a handful of
# credits; a full-slate pull bills ~60-120, so 25 was no reserve at all.)
RESERVE = 500
# Assume a free plan until the API tells us otherwise.
ASSUMED_MONTHLY = 500

# The API bills per MARKET per region, not per request: one event-odds call
# asking for ~7 markets costs ~7 credits, not 1. The pacer once counted
# "requests" while the meter counted credits — an invisible 4-8x overspend
# that burned 19k of a 20k plan in a day. Every affordability estimate now
# multiplies the event count by this.
CREDITS_PER_EVENT = 8
# Live pricing may plan to spend only this share of what's left this month;
# the rest stays for harvests, probes, and just-in-case.
LIVE_SHARE = 0.5
# Hard floor between paid refreshes no matter how much quota remains — with
# cached prices persisting on the board, more frequent re-pricing buys
# almost nothing.
MIN_REFRESH_GAP = 15 * 60
# Starvation mode: when the daily allowance can't cover a single refresh but
# the month's balance still can, allow one paid pull this often to seed the
# cache with the day's real prices.
SPARSE_INTERVAL = 12 * 3600


@dataclass
class BudgetState:
    # The POOL, not one plan. With more than one key attached this is the sum
    # of what every unspent key has left — the pacer is deciding whether the
    # operation can afford a pull, and the operation can afford it if any key
    # can pay for it.
    remaining: int = ASSUMED_MONTHLY
    used: int = 0
    last_refresh_ts: float = 0.0
    last_seen_iso: str = ""
    # Which touchpoint each sport has already been served today, as
    # "YYYY-MM-DD:HH" in the touchpoint zone. Per sport, because a slate
    # each is the point — MLB taking the noon window must not spend NFL's.
    sport_touchpoint: dict = field(default_factory=dict)
    # Set when an AUTHORIZED paid pull never got an API response (network
    # blip, host down): a short cooldown before retrying, instead of
    # counting a pull that spent nothing as the day's spend.
    retry_after_ts: float = 0.0
    # Per-sport refresh stamps. The single global clock starved NFL: the
    # launcher checks MLB first each cycle, MLB's pull reset the clock, and
    # NFL's "waited" never grew past a cycle — so once football starts, the
    # NFL board would never get a paid pull of its own. The credit BUDGET
    # stays shared (it's one API plan); only the pacing clock splits.
    sport_last_refresh: dict = field(default_factory=dict)
    # Per-key quota, keyed by a short fingerprint rather than the key itself —
    # this file is not a place to write a secret, even a gitignored one.
    # {fingerprint: {"remaining": int, "used": int, "spent_ts": float}}
    keys: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def sport_ts(self, sport: str | None) -> float:
        """The pacing stamp for one sport (global clock when sport unknown)."""
        if sport is None:
            return self.last_refresh_ts
        return float(self.sport_last_refresh.get(sport, 0.0))


def load(path: Path | str = STATE_PATH) -> BudgetState:
    path = Path(path)
    if not path.is_file():
        return BudgetState()
    try:
        raw = json.loads(path.read_text())
        per_sport = {}
        for k, v in (raw.get("sport_last_refresh") or {}).items():
            try:
                per_sport[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        touch = {}
        for k, v in (raw.get("sport_touchpoint") or {}).items():
            if isinstance(v, str):
                touch[str(k)] = v
        legacy = float(raw.get("last_refresh_ts", 0.0))
        if not per_sport and legacy > 0:
            # Upgrading a pre-split state file: every paid pull to date was
            # MLB's (NFL was the starved sport — that's why this exists), so
            # the legacy clock is MLB's clock. Without this seed MLB would
            # double-pull the moment the upgrade lands.
            per_sport = {"mlb": legacy}
        state = BudgetState(
            remaining=int(raw.get("remaining", ASSUMED_MONTHLY)),
            used=int(raw.get("used", 0)),
            last_refresh_ts=legacy,
            last_seen_iso=str(raw.get("last_seen_iso", "")),
            retry_after_ts=float(raw.get("retry_after_ts", 0.0)),
            sport_last_refresh=per_sport,
            sport_touchpoint=touch,
            keys={str(k): dict(v) for k, v in (raw.get("keys") or {}).items()
                  if isinstance(v, dict)},
        )
        # The headline is DERIVED, so re-derive it on every read. The
        # stored number is whatever the last paid pull summed; after a key
        # rotation it keeps a dead key's ghost in the pool until some pull
        # happens to rewrite it — and the pacer spends against this number.
        if state.keys:
            state.remaining = _pool_remaining(state)
        return state
    except (ValueError, OSError, TypeError):
        return BudgetState()


def save(state: BudgetState, path: Path | str = STATE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2))


# --- the spend ledger --------------------------------------------------------
# "What burned twenty thousand credits?" should be a question with an answer,
# not an archaeology exercise. Ethan's plan emptied and the only evidence was
# a cumulative counter and a directory of cache files with useful timestamps
# and no prices on them. Every paid call appends one line here instead.
SPEND_LOG = STATE_PATH.parent / "odds_spend.jsonl"

# What one call costs, by kind. The API bills per market per region, so a live
# event call asking for eight markets is eight credits. Historical calls are
# billed at a large multiple — harvest_odds.py's own note says a full-market
# historical call has MEASURED at 35-40, which is where the money went.
CREDIT_COST = {"live_event": 8, "live_board": 8, "live_events": 1,
               "hist_event": 38, "hist_events": 10}


def log_spend(kind: str, sport: str = "", credits: int | None = None,
              detail: str = "", path: Path | str | None = None) -> None:
    """Append one paid call to the ledger. Never raises — accounting must not
    be able to break a fetch."""
    try:
        f = Path(path or SPEND_LOG)
        f.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(),
               "iso": _dt.datetime.now().isoformat(timespec="seconds"),
               "kind": kind, "sport": sport,
               "credits": int(credits if credits is not None
                              else CREDIT_COST.get(kind, 1)),
               "detail": detail[:120]}
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


def read_spend(path: Path | str | None = None) -> list[dict]:
    rows = []
    f = Path(path or SPEND_LOG)
    if not f.is_file():
        return rows
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def spend_by_day(rows: list[dict] | None = None,
                 path: Path | str | None = None) -> dict:
    """{date: {kind: [calls, credits]}} — the answer to "what spent it"."""
    out: dict = {}
    for r in (rows if rows is not None else read_spend(path)):
        day = str(r.get("iso", ""))[:10] or "?"
        kind = r.get("kind", "?")
        cell = out.setdefault(day, {}).setdefault(kind, [0, 0])
        cell[0] += 1
        cell[1] += int(r.get("credits", 0))
    return out


# --- the key ring ------------------------------------------------------------
def fingerprint(key: str) -> str:
    """A short, stable, non-reversible id for a key.

    The state file lives in a gitignored cache directory, which is not the
    same as being a safe place to write a secret. A fingerprint is enough to
    tell two keys apart and useless to anyone who reads it.
    """
    import hashlib
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:8]


# These three resolve STATE_PATH at CALL time, not in the signature. A
# default argument binds once, when the function is defined, so
# `path=STATE_PATH` cannot be redirected by reassigning the module attribute
# — which is exactly how a test (and a caller wanting a different state file)
# would try to redirect it, and it would silently keep writing to the real
# one. The same trap cost a whole test file its meaning earlier in this
# project; it is not a hypothetical.
def key_state(key: str, path: Path | str | None = None) -> dict:
    return load(path or STATE_PATH).keys.get(fingerprint(key), {})


def key_is_spent(key: str, path: Path | str | None = None) -> bool:
    """True when this key has nothing left.

    A key that has never been used is NOT spent — unknown is not zero, and
    treating it as zero would refuse to try a key that might be full.
    """
    st = key_state(key, path or STATE_PATH)
    if st.get("spent_ts"):
        return True
    rem = st.get("remaining")
    return rem is not None and int(rem) <= 0


def mark_key_spent(key: str, path: Path | str | None = None) -> BudgetState:
    """Record that the API refused this key for want of credits."""
    path = path or STATE_PATH
    state = load(path)
    fp = fingerprint(key)
    entry = dict(state.keys.get(fp, {}))
    entry.update(remaining=0, spent_ts=time.time())
    state.keys[fp] = entry
    state.remaining = _pool_remaining(state)
    save(state, path)
    return state


def _pool_remaining(state: BudgetState) -> int:
    """What the whole ring has left.

    Keys we have never called contribute nothing to the sum — counting an
    unmeasured key as a full plan would let the pacer spend against credits
    that may not exist. The ring is still TRIED in full; only the arithmetic
    is conservative.

    And only keys in the CURRENT ring count at all. A rotated or re-typed
    key gets a new fingerprint, and the old fingerprint's last measurement
    sits in this state file forever — summing it counted a dead plan's
    ghost as live credits, which is how a drained 20k key plus a real ~19k
    balance read as "38,314 left". When the ring cannot be read (no keys in
    the environment), every stored key counts, because refusing to answer
    would zero the pacer for no reason.
    """
    try:
        from .sources.oddsapi import api_keys
        active = {fingerprint(k) for k in api_keys()}
    except Exception:                              # noqa: BLE001
        active = set()
    entries = state.keys
    if active:
        entries = {fp: v for fp, v in entries.items() if fp in active}
    known = [int(v.get("remaining", 0)) for v in entries.values()
             if v.get("remaining") is not None]
    return max(0, sum(known)) if known else state.remaining


def pool_remaining(path: Path | str | None = None) -> int:
    """The ring's live balance, recomputed at READ time.

    The stored headline is whatever the last paid pull computed — a reader
    consulting it after a key rotation repeats the stale sum until the next
    pull happens to rewrite it. Anything REPORTING a balance (the doctor,
    the audit) should ask this instead of ``state.remaining``.
    """
    return _pool_remaining(load(path or STATE_PATH))


def record_quota(remaining, used=None, path: Path | str = STATE_PATH,
                 key: str | None = None) -> BudgetState:
    """Store the quota the API just reported. Non-numeric values are ignored."""
    state = load(path)
    if key:
        fp = fingerprint(key)
        entry = dict(state.keys.get(fp, {}))
        try:
            entry["remaining"] = int(remaining)
            if int(remaining) > 0:
                entry.pop("spent_ts", None)
        except (TypeError, ValueError):
            pass
        try:
            entry["used"] = int(used)
        except (TypeError, ValueError):
            pass
        state.keys[fp] = entry
        save(state, path)
        state = load(path)
    try:
        state.remaining = int(remaining)
    except (TypeError, ValueError):
        return state
    try:
        state.used = int(used)
    except (TypeError, ValueError):
        pass
    # With a ring attached, the headline balance is the POOL. One key
    # reporting zero must not read as "the operation is out of credits" while
    # a second key sits untouched — that is the whole point of the ring, and
    # the pacer only ever looks at this number.
    if state.keys:
        state.remaining = _pool_remaining(state)
    state.last_seen_iso = _dt.datetime.now().isoformat(timespec="seconds")
    save(state, path)
    return state


def _claim_touchpoint(state: "BudgetState", sport: str | None,
                      ts: float) -> None:
    """Mark the touchpoint this pull sits in as served.

    Whatever authorised the pull claims the window — a pull the pre-game
    burst paid for still satisfies the 6pm touchpoint, because the point of
    a touchpoint is a fresh board at that hour, not a second purchase of
    prices the app already has.
    """
    stamp = touchpoint_due(state, sport, ts)
    if stamp:
        state.sport_touchpoint[sport or "_all"] = stamp
        # Keep the ledger from growing a row per sport per day forever.
        today = stamp.split(":")[0]
        for k in [k for k, v in state.sport_touchpoint.items()
                  if not str(v).startswith(today)]:
            state.sport_touchpoint.pop(k, None)


def mark_refreshed(ts: float | None = None, path: Path | str = STATE_PATH,
                   sport: str | None = None) -> None:
    state = load(path)
    t = ts if ts is not None else time.time()
    state.last_refresh_ts = t
    if sport:
        state.sport_last_refresh[sport] = t
    _claim_touchpoint(state, sport, t)
    save(state, path)


# How soon a paid pull that never reached the API may be retried. Short,
# because nothing was spent — but not every 60s cycle, so a dead host
# isn't hammered with 30s-timeout requests.
FAILED_PULL_RETRY_S = 5 * 60


def paid_pull_result(before_seen_iso: str, path: Path | str = STATE_PATH,
                     now: float | None = None,
                     sport: str | None = None) -> bool:
    """Called after a paid pull ATTEMPT; returns whether it actually landed.

    "Landed" means the API answered — the quota stamp advanced past what it
    was before the attempt. Only then does the refresh clock stamp: a pull
    that never reached the API spent nothing, and counting it (the old
    behaviour stamped at authorization time) burned the day's one sparse
    pull on a network blip and stranded the board on stale prices for
    12 hours. Measured live on 2026-07-27: the 4:29pm window pull was
    authorized and stamped, no credits moved, and the next attempt was
    scheduled for 4:29am. A failed attempt now sets a short retry cooldown
    instead.
    """
    now = now if now is not None else time.time()
    state = load(path)
    landed = bool(state.last_seen_iso) and state.last_seen_iso != before_seen_iso
    if landed:
        state.last_refresh_ts = now
        if sport:
            state.sport_last_refresh[sport] = now
        state.retry_after_ts = 0.0
        # The claim belongs HERE as much as in mark_refreshed: production
        # confirms its pulls through this function, so a touchpoint claimed
        # only there would never be claimed at all in the live app — and an
        # unclaimed window re-authorises every MIN_REFRESH_GAP for the whole
        # grace period, which is eight paid pulls where one was intended.
        _claim_touchpoint(state, sport, now)
    else:
        state.retry_after_ts = now + FAILED_PULL_RETRY_S
    save(state, path)
    return landed


def days_left_in_month(today: _dt.date | None = None) -> int:
    """Days remaining in the billing month, counting today (never below 1)."""
    today = today or _dt.date.today()
    if today.month == 12:
        first_next = _dt.date(today.year + 1, 1, 1)
    else:
        first_next = _dt.date(today.year, today.month + 1, 1)
    return max(1, (first_next - today).days)


def daily_allowance(state: BudgetState | None = None,
                    today: _dt.date | None = None) -> int:
    """How many CREDITS live pricing may spend today.

    Only ``LIVE_SHARE`` of what's left (after the reserve) is on the table —
    "consume everything by month-end" is how a fresh plan dies in a day."""
    state = state or load()
    spendable = max(0, state.remaining - RESERVE) * LIVE_SHARE
    return int(spendable / days_left_in_month(today))


def min_seconds_between(requests_per_refresh: int,
                        state: BudgetState | None = None,
                        today: _dt.date | None = None,
                        active_hours: float = 14.0,
                        share: float = 1.0) -> float:
    """Smallest safe gap between odds refreshes, in seconds.

    ``requests_per_refresh`` is an EVENT count (games + 1); the credit cost is
    that times ``CREDITS_PER_EVENT``, because the meter bills per market.
    The daily allowance is spread over the hours a slate is actually live
    rather than the full 24, and the gap never drops below
    ``MIN_REFRESH_GAP`` — cached prices carry the board between pulls.
    Returns ``float('inf')`` when there is nothing left to spend.
    """
    state = state or load()
    per_refresh = max(1, int(requests_per_refresh)) * CREDITS_PER_EVENT
    # ``share`` is this sport's slice of the day's allowance — 0.5 when two
    # slates are live at once (Sep/Oct), so the sports can't jointly spend
    # double what the month can afford.
    allowance = int(daily_allowance(state, today) * share)
    if allowance < per_refresh:
        return float("inf")
    refreshes_today = allowance / per_refresh
    return max(MIN_REFRESH_GAP, (active_hours * 3600.0) / refreshes_today)


# When the budget believes it's exhausted, still allow one probe this often.
# A monthly reset or a replacement key both restore the quota silently, and
# without a probe the budgeter would refuse to call and so never find out.
PROBE_INTERVAL = 6 * 3600

# --- Time-aware pacing -------------------------------------------------
# A credit is not worth the same all day — but NOT for the reason this
# comment used to give. It claimed books post MLB props close to first
# pitch and "a pull at noon buys proxy lines and silence". That is false,
# and Ethan caught it on 2026-08-26: "when I look at FanDuel at 6am,
# there is batter props already posted." A morning pull buys a real
# board.
#
# What is actually true: a LATE credit is worth more than an early one,
# because lineups confirm near first pitch (a hitter pick cannot be
# journaled before that), stale-line windows open as books re-price at
# different speeds, and picks settle against numbers close to the close.
# So off-peak spending is stretched — stretched, not stopped — and on a
# day too poor to afford even one ordinary refresh the single sparse
# pull is HELD for that window rather than fired on a 12-hour timer that
# knows nothing about baseball.
#
# THE COST OF THAT LAST RULE, stated plainly because it is the one place
# the pacing can still empty a morning board: in starvation mode there is
# no morning pull at all. On a funded day the ordinary cadence prices the
# morning (~1.1h between pulls at a healthy balance), which is what
# "player props all day" needs.
PRIME_BEFORE_S = 2.5 * 3600      # window opens this long before first pitch
PRIME_AFTER_LAST_S = 4 * 3600    # and covers the last game into play
OFFPEAK_STRETCH = 4              # off-peak refresh gaps widen by this factor
# A flat 1/31st-of-the-balance-per-day is the wrong shape for how this is
# used. Most days nobody bets, and those days' credits are not lost — they
# are still in `remaining`, which is what the daily figure is computed from.
# But the divisor cannot tell a day with fifteen games from a Tuesday in
# February, so a real slate got the same allowance as an empty one: ~314
# credits against a 128-credit refresh, i.e. two pulls, spread so thin the
# second landed after first pitch.
#
# Inside the pre-game window a slate may spend this multiple of the flat
# daily rate. It is a BURST, not a raise: the balance still has to cover it,
# the reserve is still untouchable, and off-peak hours keep the flat rate,
# so a quiet week accumulates the credits a busy Saturday spends.
PRIME_BURST = 3.0

# --- guaranteed touchpoints ---------------------------------------------------
# Ethan, 2026-08-22, with real traffic on the site for the first time:
# "Today's books prices are not being pulled enough … a window at 7am, a
# window at noon, and maybe a window at 3? Then one more at 6 or 7."
#
# The pacer above is built to spend a credit where a credit buys the most,
# and it is right that a 7am pull buys worse PRICES than a 5:45pm one —
# books have not posted, lineups are not confirmed. What it could not
# know, because until this week nobody was looking, is that a board
# showing yesterday's numbers at 8am costs something too. That cost is not
# measured in credits and it lands on somebody who has paid.
#
# So: a floor, not a replacement. At each touchpoint the day's first paid
# pull for a sport is allowed through even though off-peak pacing would
# have held it — provided the balance covers it and the reserve is
# untouched. Everything else is unchanged: the pre-game burst still fires,
# the reserve is still a floor, and a quiet day still banks its credits.
#
# LOCAL HOURS, AND LOCAL MEANS EASTERN. The droplet runs UTC — its backups
# stamp 13:09Z while the clock on the desk says 9:09am — so a naive "7"
# here would fire at 3am and nobody would notice until the morning board
# was stale anyway. The zone is explicit and configurable for that reason.
TOUCHPOINT_TZ = "America/New_York"
TOUCHPOINTS = (7, 12, 15, 18)
# How long after the hour a missed touchpoint stays claimable. The refresh
# loop ticks on a timer and a build can be mid-flight when the hour turns;
# without this, a touchpoint missed by ninety seconds is missed for good.
TOUCHPOINT_GRACE_S = 2 * 3600


def _touchpoints() -> tuple:
    raw = os.environ.get("QB_ODDS_WINDOWS", "").strip()
    if not raw:
        return TOUCHPOINTS
    out = []
    for part in raw.replace(",", " ").split():
        try:
            h = int(part)
        except ValueError:
            continue
        if 0 <= h <= 23:
            out.append(h)
    return tuple(sorted(set(out))) or TOUCHPOINTS


def _local(now: float):
    """`now` as a datetime in the touchpoint zone.

    Falls back to the machine's own clock if the zone database is missing
    — a wrong hour is better than a refresh loop that dies on an import.
    """
    zone = os.environ.get("QB_ODDS_TZ", "").strip() or TOUCHPOINT_TZ
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromtimestamp(now, ZoneInfo(zone))
    except Exception:                                        # noqa: BLE001
        return _dt.datetime.fromtimestamp(now)


def _hour_label(now: float) -> str:
    """"7am" / "12pm" — spelled out rather than strftime'd, because the
    "%-I" that produces it is a glibc extension and this string ends up in
    front of a paying customer."""
    h = _local(now).hour
    return f"{(h % 12) or 12}{'am' if h < 12 else 'pm'}"


def touchpoint_due(state: "BudgetState", sport: str | None, now: float):
    """The touchpoint this sport still owes, or None.

    A touchpoint is owed from its hour until TOUCHPOINT_GRACE_S after it,
    and only once — the stamp is the local date and hour, so a second pull
    in the same window goes back through ordinary pacing.
    """
    local = _local(now)
    hours = [h for h in _touchpoints() if h <= local.hour]
    if not hours:
        return None
    hour = max(hours)
    opened = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if (local - opened).total_seconds() > TOUCHPOINT_GRACE_S:
        return None                       # the window has closed for today
    stamp = f"{local.date().isoformat()}:{hour:02d}"
    if state.sport_touchpoint.get(sport or "_all") == stamp:
        return None                       # already served
    return stamp


# --- how much of the slate to price ------------------------------------------
# Background cycles pass --active-odds, which prices only games inside a
# six-hour window. That was written for a 500-credit free plan, where a
# full slate was most of a month.
#
# MEASURED 2026-08-22, on a 15-game Saturday with 68,663 credits in hand:
# the day's allowance was 3,408 credits, a full-slate pull costs 128, and
# the six-hour window cut that to 32. It was saving 96 credits — 2.8% of
# the day — and the price was a board showing 710 props and no book price
# on any of them at midday, because at 11am ET a six-hour window reaches
# the 1:35 games and nothing else. That is the "prices are not being
# pulled enough" Ethan opened with.
#
# Worse, the pacer was already CHARGING for the whole slate: the cost it
# hands should_refresh is games+1 for every game on the board. So the
# narrow window did not buy extra pulls — it under-spent an allowance
# already reserved and left the evening unpriced anyway.
#
# So the window is now a poverty measure rather than a default. It stays
# for the plan it was designed for.
WIDE_PULL_MARGIN = 8


def wide_pull_affordable(requests_per_refresh: int,
                         state: "BudgetState | None" = None,
                         today: _dt.date | None = None,
                         share: float = 1.0) -> bool:
    """Can today afford to price the WHOLE slate rather than a window?

    True when the day's allowance covers ``WIDE_PULL_MARGIN`` full-slate
    pulls. Below that the six-hour window earns its keep again, which is
    what a smaller plan or a nearly spent month looks like.
    """
    state = state or load()
    per_refresh = max(1, int(requests_per_refresh)) * CREDITS_PER_EVENT
    allowance = int(daily_allowance(state, today) * share)
    return allowance >= per_refresh * WIDE_PULL_MARGIN


def prime_window(kickoffs, now: float):
    """Where ``now`` sits relative to the slate's high-value window.

    Returns True inside the window, False outside it, None when kickoff
    times are unknown (callers then behave exactly as before)."""
    ks = [k for k in (kickoffs or [])
          if isinstance(k, (int, float)) and now - 12 * 3600 < k < now + 36 * 3600]
    if not ks:
        return None
    return min(ks) - PRIME_BEFORE_S <= now <= max(ks) + PRIME_AFTER_LAST_S


def _fmt_clock(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%H:%M")


def _window_hours_left(kickoffs, now: float) -> float:
    """Hours from now to the end of tonight's pre-game window.

    Shrinks as the evening goes on, which is the point: the same remaining
    allowance concentrates into the time that is left, so a slate does not
    finish the night with credits it saved for hours that no longer exist.
    """
    ks = [k for k in (kickoffs or [])
          if isinstance(k, (int, float)) and now - 12 * 3600 < k < now + 36 * 3600]
    if not ks:
        return 14.0
    return max(0.0, (max(ks) + PRIME_AFTER_LAST_S - now)) / 3600.0


def should_refresh(requests_per_refresh: int, now: float | None = None,
                   path: Path | str = STATE_PATH,
                   kickoffs=None, sport: str | None = None,
                   share: float = 1.0, **kw) -> tuple[bool, str]:
    """Is an odds refresh affordable right now? Returns ``(ok, reason)``.

    ``sport`` selects that sport's own pacing clock (each slate holds its
    pull for its own pre-game window); ``share`` is its slice of the daily
    allowance when several slates are live. Omitting both keeps the legacy
    single-clock behaviour."""
    now = now if now is not None else time.time()
    state = load(path)
    if state.retry_after_ts and now < state.retry_after_ts:
        return False, (f"last paid pull never reached the odds API — "
                       f"retrying ~{_fmt_clock(state.retry_after_ts)}")
    window = prime_window(kickoffs, now)
    if state.remaining <= RESERVE:
        if now - state.last_refresh_ts >= PROBE_INTERVAL:
            return True, ("odds quota looked exhausted — probing once in case the "
                          "plan reset or the key changed")
        return False, (f"odds quota nearly exhausted ({state.remaining} left) — "
                       f"holding a reserve; scores still update free")
    # The date matters (days-left divides the allowance), so it must come
    # from the SAME clock as ``now`` — mixing an injected ``now`` with the
    # real date.today() made the sparse/ordinary decision flip with the
    # wall calendar, which is untestable and once meant a test that passed
    # on the 28th failed on the 29th.
    kw.setdefault("today", _dt.date.fromtimestamp(now))
    # Spread the day's allowance over the hours that HAVE prices, not over
    # a nominal 14-hour day. This is the whole bug behind an empty 5pm
    # board: 15 games cost 128 credits a refresh, a fresh month divides the
    # balance by 31 days, and the resulting ~314/day buys 2.45 refreshes —
    # spread across 14 hours that is one every 5.7 HOURS. The pacer pulled
    # at 12:37, and the next slot landed after first pitch. Every credit was
    # spent, none of it where the prices were, and the board showed "629
    # props with no book price" an hour before the games.
    #
    # Inside the window the same 2.45 refreshes are spread over the window
    # instead, which is the only stretch where a pull buys a real board.
    if window is True:
        kw.setdefault("active_hours", max(1.0, _window_hours_left(kickoffs, now)))
        share = share * PRIME_BURST
    gap = min_seconds_between(requests_per_refresh, state, share=share, **kw)
    waited = now - state.sport_ts(sport)
    if gap == float("inf"):
        # Starvation mode: the daily allowance can't cover even one refresh,
        # but the month's spendable balance can. Allow a sparse pull so the
        # cache still gets seeded with today's real prices — cached re-reads
        # carry the board the rest of the day for free.
        per_refresh = max(1, int(requests_per_refresh)) * CREDITS_PER_EVENT
        if state.remaining - RESERVE >= per_refresh and waited >= SPARSE_INTERVAL:
            if window is False:
                # The day's one affordable pull is too precious to fire at
                # noon. NOT because prices don't exist yet — Ethan,
                # 2026-08-26: "when I look at FanDuel at 6am, there is
                # batter props already posted" — but because on a day that
                # can afford exactly one pull, the near-pitch numbers are
                # the ones picks are journaled and settled against, and a
                # 6am pull leaves the whole evening stale. Funded days
                # pull through the morning on the ordinary cadence.
                # Same numeric filter as prime_window: a stray non-numeric
                # kickoff must not crash the refresh cycle's thread.
                opens = min(k for k in kickoffs
                            if isinstance(k, (int, float))
                            and now - 12 * 3600 < k < now + 36 * 3600) - PRIME_BEFORE_S
                when = (f"opens ~{_fmt_clock(opens)}" if opens > now
                        else "closed for tonight — resumes with tomorrow's slate")
                return False, (f"quota very low ({state.remaining} credits) — "
                               f"holding today's one paid pull for the pre-game "
                               f"window ({when})")
            return True, (f"quota very low ({state.remaining} credits) — sparse "
                          f"mode: one paid pull per {SPARSE_INTERVAL // 3600}h, "
                          f"cached prices in between")
        return False, (f"odds budget spent for today ({state.remaining} credits "
                       f"left this month; cached prices keep the board filled)")
    if window is False:
        # Ordinary pacing, off-peak: stretch the gap so most of the day's
        # refreshes land where the prices are.
        gap = gap * OFFPEAK_STRETCH
    if waited < gap:
        # …unless a touchpoint is owed. This is the ONE override, and it
        # buys a board that is current when somebody opens the site in the
        # morning rather than one that is optimally priced at 6pm and
        # yesterday's at 8am. It is a floor under the schedule, not a
        # raise: the reserve stays untouchable, the 15-minute hard gap
        # still applies, the starvation branch above is reached first when
        # the day cannot afford a pull at all, and the window is claimed by
        # the pull that lands so it fires once.
        per_refresh = max(1, int(requests_per_refresh)) * CREDITS_PER_EVENT
        if (touchpoint_due(state, sport, now)
                and waited >= MIN_REFRESH_GAP
                and state.remaining - RESERVE >= per_refresh):
            return True, (f"{_hour_label(now)} refresh window "
                          f"({state.remaining} credits left this month)")
        why = ("off-peak — saving the odds budget for the pre-game window"
               if window is False else
               f"budgeting {state.remaining} credits to month end")
        return False, f"next odds refresh in {int(gap - waited)}s ({why})"
    return True, f"refreshing odds ({state.remaining} credits left this month)"


def reset(path: Path | str = STATE_PATH) -> BudgetState:
    """Forget the recorded quota — use after swapping in a new key.

    The stored balance belongs to whichever key produced it, so a replacement
    key starts from a clean slate and re-learns its real allowance on the next
    call rather than inheriting the old key's exhausted state.
    """
    state = BudgetState()
    save(state, path)
    return state


def is_measured(state: BudgetState | None = None) -> bool:
    """Have we ever seen a real quota figure from the API?

    Until an actual request comes back, the numbers here are an assumed free
    plan — worth saying out loud, because an assumed 500 looks identical to a
    confirmed 500 and would be trusted the same way.
    """
    state = state or load()
    return bool(state.last_seen_iso)


def key_report(path: Path | str = STATE_PATH) -> list[str]:
    """One line per key on the ring: what it has, and whether it counts.

    The pool is a SUM, so "19,999 left" is the same sentence whether that
    is one 20k plan or a 100k plan with 80k already gone — and after a
    top-up or a rotation the two are easy to confuse. Naming each key and
    saying out loud which ones the pool is actually counting turns "why
    does it think I'm poor" into a question with a visible answer.
    """
    state = load(path)
    try:
        from .sources.oddsapi import api_keys
        ring = [fingerprint(k) for k in api_keys()]
    except Exception:                                        # noqa: BLE001
        ring = []
    out = []
    for i, fp in enumerate(ring, 1):
        entry = state.keys.get(fp)
        if entry is None:
            out.append(f"key {i} ({fp}): attached, never used — its balance "
                       f"is unknown, so the pacer counts it as nothing until "
                       f"the first call reads the meter")
            continue
        rem = entry.get("remaining")
        used = entry.get("used")
        spent = " · REFUSED for want of credits" if entry.get("spent_ts") else ""
        out.append(f"key {i} ({fp}): {rem} left, {used} used{spent}")
    if not ring:
        # No readable ring means _pool_remaining falls back to counting
        # every stored key, so nothing here is "not counted" — the shell
        # simply cannot see which keys are current.
        for fp in sorted(state.keys):
            rem = state.keys[fp].get("remaining")
            out.append(f"key {fp}: {rem} left (last measured)")
        out.append("no ODDS_API_KEY in this shell, so the ring can't be "
                   "checked — run this on the server to see which keys are live")
        return out
    for fp in sorted(set(state.keys) - set(ring)):
        rem = state.keys[fp].get("remaining")
        out.append(f"key {fp}: {rem} left, but NOT on the ring — a rotated or "
                   f"retyped key. Not counted.")
    return out


def summary(path: Path | str = STATE_PATH) -> str:
    state = load(path)
    if not is_measured(state):
        return (f"Odds quota: not yet measured — assuming a free plan "
                f"({ASSUMED_MONTHLY}/month, ~{daily_allowance(state)} today). "
                f"The real figure is read from the API on the next odds call.")
    return (f"Odds quota: {_pool_remaining(state)} left, {state.used} used "
            f"(as of {state.last_seen_iso}) "
            f"· ~{daily_allowance(state)} affordable today")
