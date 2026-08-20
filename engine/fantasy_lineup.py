"""The best legal lineup under YOUR league's scoring, week by week.

Ethan, 2026-08-15: "since league after draft to optimize line ups each
week."

WHY THIS IS NOT JUST "START YOUR BEST PLAYERS".

Two things make a lineup call league-specific, and a generic ranking gets
both wrong:

  * SCORING. Half-PPR, full PPR and TE-premium do not agree about who to
    start. A twelve-catch, eighty-yard tight end beats a two-catch,
    ninety-yard receiver in one of those leagues and loses in another.
    Six-point passing touchdowns move every quarterback up a tier.
  * SLOTS. A FLEX changes the question from "who is my best receiver" to
    "which of my remaining backs, receivers and tight ends fits the last
    hole best", and a SUPERFLEX makes a second quarterback a starter.

So both come from the league itself — Sleeper hands us `scoring_settings`
and `roster_positions` — and neither is assumed.

HOW A PROJECTION BECOMES *THIS* LEAGUE'S POINTS.

The base is `fp_ppr`, which is nflverse's own PPR total: exactly right for
a PPR league, and already containing the things we cannot rebuild from
parts (passing touchdowns before the 2026-08-15 ingest change, fumbles,
two-point conversions, return yards). Then the DIFFERENCE between this
league's rules and PPR is applied for every component we actually store:

    points = fp_ppr + Σ (league_rate - ppr_rate) × per_game_component

Adding a delta is safe where a component is missing — the term is simply
absent — but it is not HONEST unless the gap is reported, because an
absent term looks exactly like a rule that matches PPR. Every row carries
`exact` and `missing`, and the board says so rather than implying a
precision it does not have.

THE ASSIGNMENT IS SOLVED, NOT GREEDILY FILLED. Filling dedicated slots
first and flexing the leftovers is optimal only when slot eligibility
nests, and it stops being optimal the moment a SUPERFLEX exists: the
right answer can be to put your QB2 in the superflex and your QB1 in the
QB slot, or to bench a running back you would have flexed. This uses a
real maximum-weight assignment, and the tests check it against brute
force on small boards.

Read-only. Every input is handed in.
"""

from __future__ import annotations

#: What nflverse's `fp_ppr` already charges for each component. Deltas are
#: measured against these, so a league that matches PPR gets no adjustment
#: at all and the baseline passes through untouched.
PPR_BASELINE = {
    "rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "pass_yd": 0.04,
    "pass_td": 4.0, "pass_int": -2.0,
    # The two touchdown rates, added 2026-08-15. Every adapter already
    # produced these keys and nothing read them, so a league scoring a
    # rushing touchdown at 4 was scored at PPR's 6 in silence. Listing
    # them here is what makes the difference get applied — or, when the
    # component has not been ingested, REPORTED as missing instead of
    # passing as "agrees with PPR".
    "rush_td": 6.0, "rec_td": 6.0,
}
#: Sleeper's scoring key → the per-game market that scales it.
SCORING_MARKET = {
    "rec": "receptions", "rec_yd": "rec_yds", "rush_yd": "rush_yds",
    "pass_yd": "pass_yds", "pass_td": "pass_td", "pass_int": "pass_int",
    "rush_td": "rush_td", "rec_td": "rec_td",
}
#: Components only a quarterback produces. The ingest stores these for
#: quarterbacks alone, so for anyone else an absent value means zero —
#: which is a fact, not a gap. Rushing and receiving touchdowns are NOT
#: here: quarterbacks rush for plenty of them.
QB_ONLY_COMPONENTS = {"pass_yd", "pass_td", "pass_int"}
#: Slot name → the positions allowed in it. Anything not listed is a
#: bench seat and is never started.
SLOT_ELIGIBILITY = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "K": {"K"}, "DEF": {"DEF"}, "DST": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "SUPERFLEX": {"QB", "RB", "WR", "TE"},
    "IDP_FLEX": set(),
}
BENCH_SLOTS = {"BN", "IR", "TAXI"}
#: A per-game mean under this many games is mostly noise.
MIN_GAMES = 3


# --- what a player is worth in this league ----------------------------------
def per_game(conn, season: int, markets=None) -> dict:
    """``{player: {market: per-game mean, "_games": n, "position": pos}}``.

    Averaged over games the player actually appeared in, which is the
    right denominator for a start/sit call — dividing a season by 17 when
    he missed six weeks answers a question nobody asked.
    """
    markets = tuple(markets or (["fp_ppr"] + list(SCORING_MARKET.values())))
    q = ("SELECT player, position, market, COUNT(*) n, AVG(value) a "
         "FROM player_game_logs WHERE sport='nfl' AND season=? AND market IN "
         "(%s) GROUP BY player, position, market" % ",".join("?" * len(markets)))
    out: dict = {}
    try:
        rows = conn.execute(q, [int(season)] + list(markets)).fetchall()
    except Exception:                                         # noqa: BLE001
        return {}
    for r in rows:
        who = out.setdefault(r["player"], {"position": (r["position"] or "").upper(),
                                           "_games": 0})
        who[r["market"]] = float(r["a"] or 0.0)
        if r["market"] == "fp_ppr":
            who["_games"] = int(r["n"] or 0)
    return out


def with_board(means: dict, board: list[dict] | None) -> dict:
    """`means` plus a projected fallback for anyone it has never seen.

    THE BUG THIS CLOSES, measured 2026-08-20 on a fixture roster. `per_game`
    reads `player_game_logs`; a player with no rows there is absent from
    `means`, and `league_points` starts from `float(means.get("fp_ppr") or
    0.0)` — so he is worth EXACTLY ZERO POINTS. Consequences, all of them
    live before this:

      * the lineup optimiser benched a first-round rookie running back
        behind a 4.0-point receiver, and reported the lineup as optimal;
      * `fantasy_trade` proposed no deal involving him in either
        direction — giving him away costs nothing by this arithmetic, so
        the rival's side never clears MIN_GAIN and every such trade is
        filtered out before anyone sees it.

    It is the same mistake as a zero in a usage column: an ABSENT
    measurement scored as a measured zero. The difference is that this one
    was not disclosed anywhere, because a benched player looks like a
    judgement rather than a gap.

    The fix is only possible now. The draft board carries a projection for
    precisely these people — rookies and anyone who missed the season are
    placed at the market's own draft rank (engine/draftmarket.py) — and
    `proj` is in the same unit as `fp_ppr`, PPR points per game. So the
    board answers where the logs cannot.

    Two rules that keep this honest:

      * A MEASUREMENT IS NEVER OVERRIDDEN. Only players absent from
        `means` are filled. A projection must not quietly replace a season
        of real games.
      * THE ROW SAYS SO. `_from_board` rides along, `_games` stays 0, and
        `lineup()` lists every player valued this way, so a starting
        eleven built partly on projections cannot be mistaken for one
        built on results.

    Receptions come across too, because the PPR-to-league conversion needs
    them — without it a half-PPR or TE-premium league would adjust a
    board-valued player as though he catches nothing, which is the defect
    already fixed once in the mock draft's scoring.

    Returns a NEW dict; the input is not mutated.
    """
    if not board:
        return means or {}
    out = dict(means or {})
    for r in board or []:
        name = r.get("player")
        if not name or name in out:
            continue
        proj = r.get("proj")
        if not isinstance(proj, (int, float)):
            continue
        row = {"position": (r.get("position") or "").upper(),
               "fp_ppr": float(proj), "_games": 0, "_from_board": True}
        rec = r.get("rec_pg")
        if isinstance(rec, (int, float)):
            row["receptions"] = float(rec)
        out[name] = row
    return out


def league_points(means: dict, scoring: dict) -> dict:
    """One player's per-game points under this league. ``{points, exact, missing}``.

    Starts from the PPR total and adds only the DIFFERENCES this league
    makes. A missing component cannot be adjusted for, and that is
    reported rather than silently treated as "matches PPR".
    """
    base = float((means or {}).get("fp_ppr") or 0.0)
    pos = (means or {}).get("position") or ""
    pts = base
    missing = []
    for key, ppr_rate in PPR_BASELINE.items():
        want = (scoring or {}).get(key)
        if want is None or abs(float(want) - ppr_rate) < 1e-9:
            continue                       # this league agrees with PPR here
        market = SCORING_MARKET[key]
        have = (means or {}).get(market)
        if have is None:
            # A RECEIVER'S PASSING TOUCHDOWNS ARE ZERO, NOT UNKNOWN. The
            # ingest stores the passing markets for quarterbacks only
            # (`NFL_QB_ONLY`), so without this every wide receiver, back
            # and tight end carried `exact: false` and a permanent
            # "could not adjust for: pass_int, pass_td" — seen on CeeDee
            # Lamb the first time a Yahoo league rendered. A warning that
            # fires on every row of the table is one nobody reads, and it
            # would have buried a real gap the day one appeared.
            if key in QB_ONLY_COMPONENTS and pos and pos != "QB":
                continue
            missing.append(key)
            continue
        pts += (float(want) - ppr_rate) * float(have)
    # TE premium is a bonus PER RECEPTION on top of the reception rate,
    # and it is the single most common reason a generic ranking starts the
    # wrong tight end.
    bonus = (scoring or {}).get("bonus_rec_te")
    if bonus and pos == "TE":
        rec = (means or {}).get("receptions")
        if rec is None:
            missing.append("bonus_rec_te")
        else:
            pts += float(bonus) * float(rec)
    return {"points": round(pts, 2), "exact": not missing,
            "missing": sorted(set(missing)), "base_ppr": round(base, 2)}


# --- the assignment ---------------------------------------------------------
def starting_slots(roster_positions) -> list[str]:
    """The startable slots, in league order. Bench and IR are dropped."""
    return [str(s).upper() for s in (roster_positions or [])
            if str(s).upper() not in BENCH_SLOTS]


def _eligible(slot: str, position: str) -> bool:
    return position in SLOT_ELIGIBILITY.get(slot, set())


def assign(players: list[dict], slots: list[str]) -> dict:
    """Maximum-weight assignment of players to slots. ``{slot index: player}``.

    Kuhn's algorithm run in descending value order, which for a bipartite
    graph gives the maximum-weight matching: taking players best-first and
    augmenting when a seat is contested can only ever improve the total,
    and a player who cannot be seated even by rearranging was worth less
    than everyone already in.

    Not a greedy fill. Filling dedicated slots and flexing the leftovers
    is optimal only while eligibility nests, and a SUPERFLEX breaks that —
    `tests/test_fantasy_lineup.py` checks this against brute force.
    """
    order = sorted(range(len(players)),
                   key=lambda i: -float(players[i].get("points") or 0.0))
    seat: dict = {}                        # slot index -> player index

    def try_seat(pi, seen):
        for si, slot in enumerate(slots):
            if si in seen or not _eligible(slot, players[pi].get("position") or ""):
                continue
            seen.add(si)
            if si not in seat or try_seat(seat[si], seen):
                seat[si] = pi
                return True
        return False

    for pi in order:
        try_seat(pi, set())
    return {si: players[pi] for si, pi in seat.items()}


def lineup(roster: list[dict], roster_positions, scoring: dict,
           means: dict, min_games: int = MIN_GAMES) -> dict:
    """The whole answer: starters, bench, and what each swap is worth.

    ``roster`` is ``[{player, position}]``. Players with too few games are
    kept but flagged — a rookie with two games is not a reason to leave a
    slot empty, and a board that silently drops him looks like it lost
    him.
    """
    slots = starting_slots(roster_positions)
    rows = []
    for r in roster or []:
        name = r.get("player")
        m = (means or {}).get(name) or {}
        pos = (r.get("position") or m.get("position") or "").upper()
        scored = league_points({**m, "position": pos}, scoring)
        rows.append({
            "player": name, "position": pos,
            "points": scored["points"], "exact": scored["exact"],
            "missing": scored["missing"], "base_ppr": scored["base_ppr"],
            "games": int(m.get("_games") or 0),
            "thin": int(m.get("_games") or 0) < min_games,
            # Valued from the draft board rather than from games he
            # played. Distinct from `exact`, which is about whether this
            # LEAGUE's scoring could be applied — a different question.
            "projected": bool(m.get("_from_board")),
        })
    seated = assign(rows, slots)
    starters = []
    for si, slot in enumerate(slots):
        p = seated.get(si)
        starters.append({"slot": slot, **(p or {"player": None, "points": 0.0})})
    started = {p["player"] for p in seated.values()}
    bench = sorted((r for r in rows if r["player"] not in started),
                   key=lambda r: -r["points"])

    # WHAT EACH DECISION IS WORTH. A lineup with no deltas is an
    # instruction; with them it is an argument you can disagree with.
    swaps = []
    for s in starters:
        if not s.get("player"):
            continue
        best = None
        for b in bench:
            if not _eligible(s["slot"], b["position"]):
                continue
            if best is None or b["points"] > best["points"]:
                best = b
        if best and best["points"] > s["points"] + 1e-9:
            swaps.append({"slot": s["slot"], "out": s["player"],
                          "in": best["player"],
                          "gain": round(best["points"] - s["points"], 2)})
    return {
        "slots": slots,
        "starters": starters,
        "bench": bench,
        "total": round(sum(s["points"] for s in starters), 2),
        "swaps": sorted(swaps, key=lambda s: -s["gain"]),
        "exact": all(r["exact"] for r in rows) if rows else True,
        # Named, not just counted: "three of your starters are projected"
        # is a caveat a manager can act on, a bare flag is not.
        "projected": sorted(r["player"] for r in rows if r.get("projected")),
        "missing": sorted({k for r in rows for k in r["missing"]}),
        "note": ("Scored under your league's own settings, starting from "
                 "nflverse's PPR total and applying only the differences. "
                 "A component we do not store cannot be adjusted for, and "
                 "any that apply are named rather than assumed to match."),
    }
