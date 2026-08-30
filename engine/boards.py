"""What each board is, in one place, so the page cannot misdescribe it.

Ethan, 2026-08-30: "it might be confusing for people using the site that
wants to know what good bets are that will win. we need to be more clear
on what bets are what and what bets to use and trust and whats being
recorded and not."

He is right, and the confusion was earned. The site shows three boards
that select on different things, carry very different amounts of
evidence, and are journaled to three different places — and a reader had
no way to tell any of that apart. Worse, the strongest-looking board is
the one with the weakest evidence behind it.

THE NUMBERS COME FROM THE MEASUREMENTS, NOT FROM PROSE. The likelihood
blurb in app.js used to carry "0.72 AUC" and "0.69-0.77" as typed text.
Those are `likely.RANK_AUC`, measured over 22,099 NFL player-weeks, and a
copy of a number in a template is a number that rots the first time the
model is refitted. Everything quotable here is derived.

WHAT IS RECORDED IS ASSERTED AGAINST WHAT ACTUALLY RECORDS IT.
`tests/test_board_guide.py` checks each entry's `journal` against the
function that does the journaling, because "we record this" is exactly
the kind of claim this codebase has repeatedly made in prose and
enforced nowhere.

Standard library only.
"""

from __future__ import annotations

from .likely import RANK_AUC

#: What the edge claim measures at. From `engine/likely`'s own header:
#: the model sorts who scores and who clears a line well, and its claim
#: about where the MARKET is wrong tests as a coin flip.
EDGE_AUC = 0.468


def _auc_range() -> str:
    """The measured ranking range, phrased from the fitted values."""
    lo, hi = min(RANK_AUC.values()), max(RANK_AUC.values())
    return f"{lo:.2f}-{hi:.2f}"


#: One entry per board a reader can land on. `key` matches the payload
#: key the page renders from, so a board that exists without an entry —
#: or an entry with no board — is a test failure rather than a surprise.
def guide() -> list[dict]:
    """The boards, ordered by how much evidence stands behind them."""
    td = RANK_AUC.get("anytime_td", 0.0)
    return [
        {
            "key": "most_likely",
            "title": "Most Likely",
            "selects_on": "how likely we think it is to happen",
            "measured": (
                f"Ranked at {td:.2f} AUC on who scores and "
                f"{_auc_range()} on who clears a line, over five seasons "
                f"and 22,099 player-weeks."),
            "journal": "likely",
            "money": False,
            "trust": (
                "The strongest evidence on the site. This is the model "
                "doing the thing it measurably does well — sorting who "
                "hits. It is now recorded so the ledger, not a backtest, "
                "can settle it."),
        },
        {
            "key": "long_shots",
            "title": "Long Shots",
            "selects_on": "plus-money prices we think are too long",
            "measured": (
                f"Built on the same {td:.2f} AUC ranking, then filtered on "
                f"price — so it inherits a strong signal and adds a weak "
                f"one."),
            "journal": "longshot",
            "money": False,
            "trust": (
                "Sized like lottery tickets and recorded like them: a flat "
                "small stake, no dollar exposure, kept out of the headline "
                "record."),
        },
        {
            "key": "recommendations",
            "title": "Tonight's bets",
            "selects_on": "where we think the price is wrong",
            "measured": (
                f"The edge claim itself tests at {EDGE_AUC:.3f} AUC — "
                f"indistinguishable from a coin flip. No NFL bet has "
                f"settled yet, so the live record cannot referee it "
                f"either."),
            "journal": "main",
            "money": True,
            "trust": (
                "The only board that stakes real money, and the one with "
                "the least evidence behind it. Treat it as unproven until "
                "the Record page has settled rows, not as the headline it "
                "looks like."),
        },
    ]


def by_key() -> dict:
    return {b["key"]: b for b in guide()}


def summary_line(board: dict) -> str:
    """One sentence: what it picks on, and where it is recorded."""
    where = ("staked and graded on the Record page" if board["money"]
             else f"recorded to the '{board['journal']}' book at no dollar "
                  f"risk — measured, not staked")
    return f"Picked on {board['selects_on']} · {where}."
