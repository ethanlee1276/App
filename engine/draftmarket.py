"""The players the market drafts that our board cannot see.

THE PROBLEM, stated plainly. `fantasy_draft.build_draft_kit` projects
last season's usage forward, so a player with no usage rows is not on the
board at all — and the board's own notes have said so from the start:
"knows nothing about rookies (they are not on it)". That was an honest
disclosure while the board was a reading aid. It stopped being merely a
disclosure when the mock draft simulator started drafting FROM the board:
`app.js` builds its pool from `kit.board`, so no rookie can be taken in a
simulated draft, by any team, ever. A twelve-team mock in August 2026 in
which no rookie goes in the first four rounds is not a rehearsal of the
draft anyone is about to do — it is a rehearsal of a different draft.

This is not only about rookies. Anyone the market drafts and our board
cannot see has the same shape: a back who missed all of last season, a
returning suspension, a veteran on a new team after a lost year.

WHAT WE MAY HONESTLY SAY ABOUT SUCH A PLAYER, which is less than a
projection and more than nothing. We have no usage for him, so we cannot
project him, and inventing a number would be the one thing this codebase
does not do. What we DO have is Sleeper's `search_rank` — the order their
own draft board shows by default, which millions of drafts are run off —
and our own projections for the players ranked around him.

So the placement is an interpolation over OUR OWN NUMBERS, indexed by the
market's opinion:

    the market drafts this rookie where it drafts our RB18 and RB19
    our board projects those two at 11.4 and 11.1 PPG
    therefore he is placed at ~11.2

Every number in that sentence except the ranking is ours. The ranking is
the market's, and the row says so: `basis="market"`, `source="market"`,
`games=0`. It is a deferral, recorded as one, not a forecast wearing a
model's clothes.

TWO CONSEQUENCES WORTH STATING BECAUSE THEY ARE FEATURES, NOT BUGS.

*A market-placed player can never be a sleeper or a value pick.* He sits
exactly where the market put him, so our board and the market agree on
him by construction and the disagreement column reads zero. That is the
correct answer: we have no independent opinion on a player we have never
seen play. `fantasy_ranks` already understood this from the other side —
"rookies are absent from our board BY CONSTRUCTION" — and scored their
absence as None rather than as rank 999.

*Replacement level moves, and should.* VORP is measured against the best
freely available body at the position. If eight rookie running backs are
drafted before the tenth round in every real league, then the tenth-round
RB our board called "replacement" was never actually available, and every
RB's VORP was computed against a fiction. Placing them corrects that for
everyone else on the board, not just for them.

Interpolation only — never extrapolation. A player the market ranks below
everyone we can see is clamped to our lowest visible projection at his
position rather than extended past it, because the curve's shape beyond
our data is not something we know.

Standard library only. No fetches: the players blob is handed in, and
`None` (Sleeper unreachable) yields an empty list, so the board builds
exactly as it did before.
"""

from __future__ import annotations

from .fantasy_ranks import from_sleeper, normalize

#: Positions the draft board carries. Same tuple as fantasy_draft's, kept
#: local so importing this module cannot create a cycle.
POSITIONS = ("QB", "RB", "WR", "TE")

#: How deep into the market's order to look. Sleeper ranks thousands of
#: players; only the top of that list is drafted in a 12-team league (16
#: rounds x 12 teams = 192 picks), and past it we would be placing
#: practice-squad names onto a draft board. Generous rather than tight —
#: the point is to stop before the list becomes noise, not to guess at a
#: league size.
MARKET_DEPTH = 260

#: A position needs this many of our own players carrying a market rank
#: before we will interpolate within it. Two points define a line; below
#: that we would be projecting a rookie off a single comparison, which is
#: not an interpolation, it is a coin toss with extra steps.
MIN_ANCHORS = 4


def _anchors(board: list[dict], ranks: dict, position: str,
             field: str = "proj") -> list:
    """Our own players at one position, as (market rank, our value).

    Sorted by the market's order, which is the axis we interpolate along.
    `field` is the number being read off the curve — the projection for
    placing a player, and `rec_pg` for scoring him in a format that pays
    receptions (see the note on RECEPTIONS in place_missing).
    """
    out = []
    for r in board:
        if (r.get("position") or "").upper() != position:
            continue
        rank = ranks.get(normalize(r.get("player")))
        val = r.get(field)
        if rank is None or not isinstance(val, (int, float)):
            continue
        out.append((float(rank), float(val)))
    out.sort()
    return out


def _interpolate(anchors: list, rank: float) -> float | None:
    """Our projection curve for a position, read at the market's rank.

    Clamped at both ends. Above our best-ranked player the answer is that
    player's projection, not something larger — a rookie the market likes
    more than anyone we can see is placed level with our best, because we
    have no evidence for "better than the best we have measured".
    """
    if len(anchors) < MIN_ANCHORS:
        return None
    if rank <= anchors[0][0]:
        return anchors[0][1]
    if rank >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(1, len(anchors)):
        r1, p1 = anchors[i - 1]
        r0, p0 = anchors[i]
        if rank <= r0:
            if r0 == r1:
                return p0
            f = (rank - r1) / (r0 - r1)
            return p1 + f * (p0 - p1)
    return anchors[-1][1]


#: Join coverage from the last place_missing() call, read by summary().
#: Module-level because the two are always called as a pair by the one
#: caller that exists; a return-tuple would ripple through every test.
_coverage: dict = {}


def _name(p: dict) -> str:
    return " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)


def place_missing(board: list[dict], players: dict | None,
                  depth: int = MARKET_DEPTH) -> list[dict]:
    """Rows for market-ranked players our board has never seen.

    `board` is `_players()` output — pre-VORP, pre-tier, because the
    caller merges these in and then ranks everybody together. Returns []
    for a missing or unusable blob, which is what makes this safe to call
    unconditionally.
    """
    _coverage.clear()
    if not players or not board:
        return []
    ranks = from_sleeper(players, positions=POSITIONS)
    if not ranks:
        return []
    have = {normalize(r.get("player")) for r in board}
    anchors = {pos: _anchors(board, ranks, pos) for pos in POSITIONS}
    # RECEPTIONS, on the same curve as the projection and for one reason:
    # they are the only field a SCORING FORMAT needs that the projection
    # does not already contain. `_mockScoreBoard` computes a TE-premium or
    # full-PPR bonus as `bonus x rec_pg`, and reads a missing value as
    # zero — so a market-placed tight end would have been scored as though
    # he catches nothing, in precisely the format where catching is the
    # whole point. Interpolating it keeps one rule: every number about a
    # placed player is one of OUR numbers, read at the market's rank.
    #
    # Only this field. targets_pg, carries_pg and pass_att_pg stay None,
    # because those are shown to a reader as measured usage and an
    # interpolated number in a usage column would be an invented
    # observation rather than a stated deferral. rec_pg is read in exactly
    # one place in the whole codebase, and it is not a display.
    rec_anchors = {pos: _anchors(board, ranks, pos, "rec_pg")
                   for pos in POSITIONS}

    out = []
    for p in players.values():
        if not isinstance(p, dict):
            continue
        pos = (p.get("position") or "").upper()
        if pos not in POSITIONS:
            continue
        name = _name(p)
        key = normalize(name)
        if not key or key in have:
            continue
        rank = ranks.get(key)
        if rank is None or rank > depth:
            continue
        proj = _interpolate(anchors.get(pos) or [], float(rank))
        if proj is None:
            continue
        exp = p.get("years_exp")
        out.append({
            "player": name,
            "team": (p.get("team") or "").upper(),
            "position": pos,
            # ZERO GAMES, said out loud rather than left to be inferred
            # from a missing key. Every consumer that reasons about
            # sample size reads this field.
            "games": 0,
            # NOT 0.0. He did not average zero points, he did not play,
            # and the two render differently everywhere it matters: the
            # calendar card prints "· {ppg} FPPG last season" whenever
            # ppg is non-null, so a zero would have claimed a rookie
            # scored nothing per game all last year. The dossier's stat()
            # drops a null row and prints a zero one. Nothing computes
            # with these on a market row — the sleepers filter excludes
            # basis "market" before it ever subtracts them.
            "ppg": None, "xppg": None,
            "proj": round(proj, 1),
            "basis": "market",
            "source": "market",
            "market_rank": int(rank),
            "rookie": exp == 0 if isinstance(exp, int) else False,
            # No usage means no usage RATES either. Zeroes here would read
            # as "measured zero carries"; None reads as "not measured",
            # and the page prints an em dash for it. rec_pg is the one
            # exception and the comment above says why.
            "targets_pg": None, "carries_pg": None, "pass_att_pg": None,
            # Rounded to match _players()'s own rec_pg, which is 2dp. An
            # unrounded float here serialises as 5.733333333333333 into a
            # payload where every sibling is short, and lands in the JSON
            # the phone downloads.
            "rec_pg": (lambda v: None if v is None else round(v, 2))(
                _interpolate(rec_anchors.get(pos) or [], float(rank))),
            "small_sample": True,
        })
    out.sort(key=lambda r: r["market_rank"])
    # THE NUMBER THAT SAYS WHETHER ANY OF THIS WORKED. Every placement is
    # an interpolation between OUR players at THEIR market ranks, so it
    # depends entirely on our names joining Sleeper's. A join that quietly
    # degrades — a normaliser that stops handling suffixes, a feed that
    # starts shipping "A.J." as "AJ" — would not raise and would not empty
    # the board; it would leave a handful of anchors per position and
    # place rookies off a line drawn through almost nothing. So the
    # coverage rides out with the rows and the caller can print it.
    _coverage["anchored"] = sum(1 for r in board
                                if normalize(r.get("player")) in ranks)
    _coverage["board"] = len(board)
    return out


def summary(rows: list[dict]) -> dict:
    """What was placed, for the page's own note and the terminal line."""
    by_pos: dict[str, int] = {}
    for r in rows:
        by_pos[r["position"]] = by_pos.get(r["position"], 0) + 1
    n, tot = _coverage.get("anchored", 0), _coverage.get("board", 0)
    return {
        "placed": len(rows),
        "rookies": sum(1 for r in rows if r.get("rookie")),
        "by_position": by_pos,
        "deepest": max((r["market_rank"] for r in rows), default=0),
        "anchored": n,
        "board_seen": tot,
        "anchor_pct": round(100.0 * n / tot, 1) if tot else 0.0,
    }
