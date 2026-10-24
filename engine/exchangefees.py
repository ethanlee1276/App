"""What an exchange charges to take a price — one schedule, one place.

Audit 2026-09-30, B7-1 (roadmap #22). Nothing in the codebase subtracted a
fee. The Kalshi desks recommended on the gross gap between our probability
and the mid and journaled the contract at the bare price, and the Pick of
the Day's exchange rung claimed edge against prices that cannot be taken
net of what the venue keeps. An edge that exists only before the fee is
not an edge anyone can buy.

THE SCHEDULE, per $1-payout contract bought at price P (0 < P < 1):

  kalshi       0.07 x P x (1 - P)   the general taker fee in Kalshi's
                                    published schedule: 1.75 cents at 50
                                    cents, 1.12 at 20 or 80. Kalshi rounds
                                    each ORDER up to the next cent; per
                                    contract this is the unrounded rate, so
                                    a one-contract ticket pays slightly more
                                    than this says, never less than it.
  polymarket   0                    no trading fee on its sports markets.
  novig        0                    commission-free; its margin is in the
  prophetx     0                    spread, which the price already carries.

The zeros are stated rather than omitted so a venue that starts charging
is one line to change, and `fee_bps` goes on every row so a later schedule
change is visible against the rows priced under the old one.

Everything here is in PROBABILITY units (contract price), because that is
what an exchange quotes. A sportsbook is not an exchange and pays nothing.
"""

from __future__ import annotations

#: Taker fee coefficient per venue: fee = rate x P x (1 - P) per contract.
FEE_RATE = {"kalshi": 0.07, "polymarket": 0.0, "novig": 0.0, "prophetx": 0.0}


def _venue(book) -> str:
    return str(book or "").strip().lower().replace(" ", "")


def is_exchange(book) -> bool:
    return _venue(book) in FEE_RATE


def fee_per_contract(venue, price: float) -> float:
    """Dollars of fee on one $1-payout contract bought at `price`."""
    rate = FEE_RATE.get(_venue(venue), 0.0)
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0.0
    if not 0.0 < p < 1.0 or not rate:
        return 0.0
    return rate * p * (1.0 - p)


def fee_bps(venue, price: float) -> int:
    """The fee as basis points of what the contract costs — the unit the
    journal stores, so a row says how much of its stake the venue kept."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0
    if not 0.0 < p < 1.0:
        return 0
    return int(round(fee_per_contract(venue, p) / p * 10000))


def paid(venue, price: float) -> float:
    """What one contract actually costs: the price plus the fee."""
    return float(price) + fee_per_contract(venue, price)


def net_expected_value(fair: float, price: float, venue) -> float:
    """EV of one unit staked on a contract at `price`, after the fee.

    A unit buys 1 / (price + fee) contracts, each paying $1 with
    probability `fair`: EV = fair / (price + fee) - 1.
    """
    return float(fair) / paid(venue, price) - 1.0


def net_edge_pts(fair: float, price: float, venue) -> float:
    """The desk's unit — probability points — after the fee: fair minus
    what the contract really costs, x 100."""
    return (float(fair) - paid(venue, price)) * 100.0
