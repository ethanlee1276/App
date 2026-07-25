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

# Never spend below this many requests — leaves room to price a slate manually.
RESERVE = 25
# Assume a free plan until the API tells us otherwise.
ASSUMED_MONTHLY = 500


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
    """How many requests we can afford to spend today."""
    state = state or load()
    spendable = max(0, state.remaining - RESERVE)
    return int(spendable / days_left_in_month(today))


def min_seconds_between(requests_per_refresh: int,
                        state: BudgetState | None = None,
                        today: _dt.date | None = None,
                        active_hours: float = 14.0) -> float:
    """Smallest safe gap between odds refreshes, in seconds.

    The daily allowance is spread over the hours a slate is actually live rather
    than the full 24, so the budget isn't wasted refreshing overnight.
    Returns ``float('inf')`` when there is nothing left to spend.
    """
    state = state or load()
    per_refresh = max(1, int(requests_per_refresh))
    allowance = daily_allowance(state, today)
    if allowance < per_refresh:
        return float("inf")
    refreshes_today = allowance / per_refresh
    return max(60.0, (active_hours * 3600.0) / refreshes_today)


def should_refresh(requests_per_refresh: int, now: float | None = None,
                   path: Path | str = STATE_PATH, **kw) -> tuple[bool, str]:
    """Is an odds refresh affordable right now? Returns ``(ok, reason)``."""
    now = now if now is not None else time.time()
    state = load(path)
    if state.remaining <= RESERVE:
        return False, (f"odds quota nearly exhausted ({state.remaining} left) — "
                       f"holding a reserve; scores still update free")
    gap = min_seconds_between(requests_per_refresh, state, **kw)
    if gap == float("inf"):
        return False, f"odds budget spent for today ({state.remaining} left this month)"
    waited = now - state.last_refresh_ts
    if waited < gap:
        return False, (f"next odds refresh in {int(gap - waited)}s "
                       f"(budgeting {state.remaining} requests to month end)")
    return True, f"refreshing odds ({state.remaining} requests left this month)"


def summary(path: Path | str = STATE_PATH) -> str:
    state = load(path)
    return (f"Odds quota: {state.remaining} left, {state.used} used"
            + (f" (as of {state.last_seen_iso})" if state.last_seen_iso else "")
            + f" · ~{daily_allowance(state)} affordable today")
