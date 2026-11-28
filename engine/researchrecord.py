"""What our hand-researched picks hit, kind by kind (2026-11-15).

Ethan, 2026-11-15: "you should be learning from all those reports and
everything ... the catches over picks hit 83%, all picks hit 67%. That's
pretty good numbers ... the point of our app is to not have me go do the
research because it's already done for me on the app."

Every leg the final card of an NFL research chat named, from 9 September to
12 November 2026 (the "NFL Bet checking" project and the chats beside it),
graded against nflverse's box scores and final scores: 166 legs, 112 won. A
leg two chats both named counts once for each, as each card stood on its own.
The spring's MLB and NBA chats are not graded here (their box scores were
not to hand), so this table is the NFL's alone.

What the table is for: each pick on a game's card (engine/gamereport,
sec_card) says how its kind has done twice — on our board, from the board's
own record (likelyboard.record_seen), and in these hand-researched picks —
so a reader sees which kinds of pick have earned the trust and which have
not, side by side. Where the two disagree is itself the finding: the
research's catch overs (83%) and quarterback volume (12 of 13) were floor
numbers on featured roles; the board's rushing yards and touchdowns did
better than the research's.

It is a fixed table, not a learner: these picks were made once, by hand, and
graded once. The board's own record is the one that keeps learning.
"""
from __future__ import annotations

#: (market, side) -> (won, graded). Sides are the board's: OVER, UNDER.
NFL = {
    ("receptions", "OVER"): (25, 30),
    ("rec_yds", "OVER"): (11, 15),
    ("rush_yds", "OVER"): (4, 9),
    ("rush_yds", "UNDER"): (2, 2),
    ("rush_att", "OVER"): (3, 6),
    ("pass_att", "OVER"): (4, 5),
    ("pass_att", "UNDER"): (1, 1),
    ("pass_cmp", "OVER"): (5, 5),
    ("pass_cmp", "UNDER"): (2, 2),
    ("pass_td", "OVER"): (7, 8),
    ("pass_yds", "OVER"): (2, 2),
    ("pass_yds", "UNDER"): (0, 1),
    ("anytime_td", "OVER"): (39, 71),
    ("moneyline", ""): (2, 4),
}
#: Every graded leg, all kinds: (won, graded).
NFL_ALL = (112, 166)
#: Under this many graded legs a kind says nothing on a card.
MIN_N = 5

TABLES = {"nfl": NFL}


def side_of(side) -> str:
    """The board's side words, as the table keys them: "Yes" is an over."""
    s = str(side or "").strip().upper()
    if s in ("OVER", "YES"):
        return "OVER"
    if s in ("UNDER", "NO"):
        return "UNDER"
    return ""


def record(sport: str, market: str, side) -> tuple | None:
    """(won, graded) for the kind, or None under MIN_N or with no table."""
    table = TABLES.get(str(sport or "").lower()) or {}
    key = (str(market or ""), side_of(side) if market != "moneyline" else "")
    got = table.get(key)
    return got if got and got[1] >= MIN_N else None


def line(sport: str, market: str, side) -> str:
    """"25 of 30 in our hand-researched picks", or "" when the table is
    silent on the kind."""
    got = record(sport, market, side)
    return f"{got[0]} of {got[1]} in our hand-researched picks" if got else ""
