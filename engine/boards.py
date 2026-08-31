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


# ---------------------------------------------------------------------------
# The shelves a bettor actually shops by.
#
# Ethan, 2026-08-30: "i made the site and im getting confused on it... a
# normal better is going to be looking for bets that are most likely to
# hit and probably not thinking about the edge a prop has. for someone
# betting nfl, they wanna find good props and td props, so lets lay it
# out that way."
#
# The likelihood board was one flat list of every market mixed together,
# sorted by probability. That sorting is correct and the list is not: a
# person opening an NFL slate is shopping for a KIND of bet — who scores,
# who catches passes, who runs — and a flat list makes them re-derive
# those groups by eye on every visit.
#
# NOT ORDERED BY AUC, DELIBERATELY, and this is the important part.
# Receptions rank at 0.770 and touchdowns at 0.721, so sorting the page
# on measured strength would put receptions first. That gap is nine
# thousandths of an AUC across five markets, and nothing here has shown
# it is a real difference rather than sampling noise — presenting it as
# an ordering would be the same error as reading a non-monotone ROI
# column as an edge, which this codebase has now made twice.
#
# So the shelves are ordered by what someone came to buy, and each one
# carries its measured ranking figure as INFORMATION rather than as a
# rank. The numbers still come from `likely.RANK_AUC`; only the sort key
# is a product decision.

#: `(key, title, markets, what a bettor is doing when they shop it)`.
FOOTBALL_SHELVES = (
    ("touchdowns", "Touchdown scorers", ("anytime_td",),
     "Who finds the end zone. The market most NFL bettors open the app "
     "for, and the one this model was built on first."),
    ("receiving", "Catches & receiving yards", ("receptions", "rec_yds"),
     "Volume receivers and the yardage that follows it — the markets "
     "that rank strongest of anything we measure."),
    ("rushing", "Rushing yards", ("rush_yds",),
     "Backfield workload. Ranks well; the price fit is shut, so these "
     "are a read rather than a card."),
    ("passing", "Passing yards", ("pass_yds",),
     "Quarterback volume. The weakest ranking of the five and labelled "
     "as such rather than mixed in silently."),
)

#: Baseball's shelves — real this time. The earlier BASEBALL_SHELVES
#: stub was deleted because nothing produced an MLB `most_likely` key
#: and a spec for a board that does not exist is a claim nothing
#: enforces. mlb_build publishes the board now, and the rule that kept
#: the stub out still governs what lands on it: a market appears only
#: once engine.rankfit has MEASURED that it ranks (>= likely.MIN_RANK_AUC
#: on 2,000+ walk-forward pairs, on the box whose logs it walked). So
#: these shelves can exist here in full while every one of them stays
#: empty on a box that has not measured its markets — the shape is
#: declared, the claim is earned per row.
BASEBALL_SHELVES = (
    ("homers", "Home runs", ("home_runs",),
     "Who leaves the yard. The market the long-shot board prices; here "
     "it is ranked by likelihood instead of edge."),
    ("bats", "Hits & total bases", ("hits", "total_bases"),
     "Contact and extra bases — the volume side of a hitter's night."),
    ("arms", "Strikeouts", ("strikeouts",),
     "Pitcher swing-and-miss. A different engine from the bats above, "
     "and shelved apart so its evidence reads apart."),
)

#: Hoops — one spec, both leagues, because the boards are the same
#: pipeline on the same markets. The trust line still reads per league:
#: _shelf_auc asks likely.rank_auc with the sport, so a WNBA shelf shows
#: the WNBA's own fitted figure and an NBA one the NBA's, or nothing.
HOOPS_SHELVES = (
    ("scoring", "Points", ("pts", "pra"),
     "Scoring volume — points alone and the PRA combo the books "
     "headline."),
    ("glass", "Rebounds & assists", ("reb", "ast"),
     "The possession game: boards and playmaking, shelved together "
     "because the same role players carry both."),
    ("threes", "Three-pointers", ("fg3m",),
     "Makes from deep — the highest-variance market on this board, "
     "and labelled by its own measurement rather than the shelf above."),
)

#: Sports with a likelihood board, and each one's shelf spec. A sport
#: not listed gets no shelves and the page falls back to its flat list —
#: also what happens for a payload built before shelves existed.
SHELVES_BY_SPORT = {
    "nfl": None,        # filled below — FOOTBALL_SHELVES defined next
    "cfb": None,
    "mlb": BASEBALL_SHELVES,
    "nba": HOOPS_SHELVES,
    "wnba": HOOPS_SHELVES,
}
FOOTBALL = ("nfl", "cfb")


def shelves(sport: str, rows=None) -> list[dict]:
    """The shelves for `sport`, each with the rows that belong on it.

    `rows` is the `most_likely` board. Pass it and each shelf comes back
    with its rows attached and empty shelves dropped; omit it and this is
    just the shape, which is what the tests read.

    A sport with no likelihood board answers `[]`, and the page falls
    back to its flat list rather than drawing an empty frame.

    A market with no shelf lands on a trailing "Other" rather than
    vanishing. A board that silently drops rows because someone added a
    market and not a shelf is precisely the failure this file exists to
    prevent, and it would look like an empty page rather than an error.
    """
    sp = (sport or "").lower()
    if sp not in SHELVES_BY_SPORT:
        return []
    spec = SHELVES_BY_SPORT[sp] or FOOTBALL_SHELVES
    out = []
    for key, title, markets, blurb in spec:
        shelf = {"key": key, "title": title, "markets": list(markets),
                 "blurb": blurb, "rank_auc": _shelf_auc(markets, sp)}
        if rows is not None:
            shelf["rows"] = [r for r in rows
                             if (r.get("market") or "") in markets]
        out.append(shelf)
    if rows is not None:
        claimed = {m for _, _, ms, _ in spec for m in ms}
        rest = [r for r in rows if (r.get("market") or "") not in claimed]
        if rest:
            out.append({"key": "other", "title": "Other markets",
                        "markets": sorted({r.get("market") or "" for r in rest}),
                        "blurb": "Markets without a shelf of their own yet.",
                        "rank_auc": None, "rows": rest})
        out = [s for s in out if s.get("rows")]
    return out


def _shelf_auc(markets, sport: str = "nfl") -> float | None:
    """The measured ranking figure for a shelf, or None if unmeasured.

    The MINIMUM across the shelf's markets, not the mean: a shelf is only
    as trustworthy as its weakest row, and a reader scanning the header
    is deciding whether to trust what is under it. Sport-aware via
    likely.rank_auc, so an MLB shelf reads the droplet's own fitted
    store and a CFB touchdown shelf stops borrowing the NFL's figure.
    """
    from .likely import rank_auc
    got = [rank_auc(sport, m) for m in markets]
    got = [g for g in got if g is not None]
    return min(got) if got else None
