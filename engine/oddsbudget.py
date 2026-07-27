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
import time
from dataclasses import dataclass, asdict
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
    remaining: int = ASSUMED_MONTHLY
    used: int = 0
    last_refresh_ts: float = 0.0
    last_seen_iso: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def load(path: Path | str = STATE_PATH) -> BudgetState:
    path = Path(path)
    if not path.is_file():
        return BudgetState()
    try:
        raw = json.loads(path.read_text())
        return BudgetState(
            remaining=int(raw.get("remaining", ASSUMED_MONTHLY)),
            used=int(raw.get("used", 0)),
            last_refresh_ts=float(raw.get("last_refresh_ts", 0.0)),
            last_seen_iso=str(raw.get("last_seen_iso", "")),
        )
    except (ValueError, OSError, TypeError):
        return BudgetState()


def save(state: BudgetState, path: Path | str = STATE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2))


def record_quota(remaining, used=None, path: Path | str = STATE_PATH) -> BudgetState:
    """Store the quota the API just reported. Non-numeric values are ignored."""
    state = load(path)
    try:
        state.remaining = int(remaining)
    except (TypeError, ValueError):
        return state
    try:
        state.used = int(used)
    except (TypeError, ValueError):
        pass
    state.last_seen_iso = _dt.datetime.now().isoformat(timespec="seconds")
    save(state, path)
    return state


def mark_refreshed(ts: float | None = None, path: Path | str = STATE_PATH) -> None:
    state = load(path)
    state.last_refresh_ts = ts if ts is not None else time.time()
    save(state, path)


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
                        active_hours: float = 14.0) -> float:
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
    allowance = daily_allowance(state, today)
    if allowance < per_refresh:
        return float("inf")
    refreshes_today = allowance / per_refresh
    return max(MIN_REFRESH_GAP, (active_hours * 3600.0) / refreshes_today)


# When the budget believes it's exhausted, still allow one probe this often.
# A monthly reset or a replacement key both restore the quota silently, and
# without a probe the budgeter would refuse to call and so never find out.
PROBE_INTERVAL = 6 * 3600

# --- Time-aware pacing -------------------------------------------------
# A credit is not worth the same all day. Books post MLB props close to
# first pitch, lineups confirm in the same stretch, and stale-line windows
# open as books re-price at different speeds — so a pull at 5:45pm buys a
# real board while a pull at noon buys proxy lines and silence. When the
# slate's kickoff times are known, off-peak spending is stretched and the
# low-quota sparse pull is HELD for the window instead of firing on a
# 12-hour timer that knows nothing about baseball.
PRIME_BEFORE_S = 2.5 * 3600      # window opens this long before first pitch
PRIME_AFTER_LAST_S = 4 * 3600    # and covers the last game into play
OFFPEAK_STRETCH = 4              # off-peak refresh gaps widen by this factor


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


def should_refresh(requests_per_refresh: int, now: float | None = None,
                   path: Path | str = STATE_PATH,
                   kickoffs=None, **kw) -> tuple[bool, str]:
    """Is an odds refresh affordable right now? Returns ``(ok, reason)``."""
    now = now if now is not None else time.time()
    state = load(path)
    window = prime_window(kickoffs, now)
    if state.remaining <= RESERVE:
        if now - state.last_refresh_ts >= PROBE_INTERVAL:
            return True, ("odds quota looked exhausted — probing once in case the "
                          "plan reset or the key changed")
        return False, (f"odds quota nearly exhausted ({state.remaining} left) — "
                       f"holding a reserve; scores still update free")
    gap = min_seconds_between(requests_per_refresh, state, **kw)
    waited = now - state.last_refresh_ts
    if gap == float("inf"):
        # Starvation mode: the daily allowance can't cover even one refresh,
        # but the month's spendable balance can. Allow a sparse pull so the
        # cache still gets seeded with today's real prices — cached re-reads
        # carry the board the rest of the day for free.
        per_refresh = max(1, int(requests_per_refresh)) * CREDITS_PER_EVENT
        if state.remaining - RESERVE >= per_refresh and waited >= SPARSE_INTERVAL:
            if window is False:
                # The day's one affordable pull is too precious to fire at
                # noon: real prices post near first pitch, so wait for them.
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


def summary(path: Path | str = STATE_PATH) -> str:
    state = load(path)
    if not is_measured(state):
        return (f"Odds quota: not yet measured — assuming a free plan "
                f"({ASSUMED_MONTHLY}/month, ~{daily_allowance(state)} today). "
                f"The real figure is read from the API on the next odds call.")
    return (f"Odds quota: {state.remaining} left, {state.used} used "
            f"(as of {state.last_seen_iso}) "
            f"· ~{daily_allowance(state)} affordable today")
