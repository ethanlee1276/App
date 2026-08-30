"""Is the NFL board ready, market by market, with the evidence?

"It is not ready" and "it is ready" are both claims nobody can check.
This turns the question into a table: for every market the NFL board can
publish, what is its calibration, is the engine allowed to bet it, has it
ever been measured against a real book, and what did it settle at.

WHY A REPORT RATHER THAN A FIX. Six gates stand between a modelled prop
and a published pick — credible, tier edge, net price, quality,
calibration, loss-pattern veto — and each closes a market for a different
reason with a different remedy. A market shut by a boundary calibration
needs a refit; one shut by having no measured edge needs a better model
or a permanent retirement; one shut by an empty prop menu needs nothing
at all but a later kickoff. Guessing which is which is how the wrong one
gets worked on.

WHAT THE COLUMNS MEAN

    calib     the stored temperature and bias, or "none" — an unfitted
              market is not broken, it is unmeasured, and those are
              different states with different work behind them
    reliable  `calibrate.is_reliable`: False when the fit ran to the edge
              of its search range (a cap, not an optimum) or when the
              correction is one-sided. Either way the engine hard-passes
    one-sided a correction that cannot reach both sides of 0.5 has
              stopped being a calibration and become a constant side
    tier      the §3 minimum edge this market must clear post-haircut
    settled   won/lost rows in the ledger and their flat-stake ROI — the
              only column that is an outcome rather than a setting

Standard library only.

    python3 -m engine.nflready [sport]
"""

from __future__ import annotations

import sys

#: Every market the NFL board can publish a player prop in. Kept explicit
#: rather than discovered from the calibration store, because a market
#: that has NEVER been fitted is exactly the case this report exists to
#: surface — discovering the list from the store would hide it.
PLAYER_MARKETS = ("anytime_td", "receptions", "rec_yds", "rush_yds",
                  "pass_yds")

#: The game-level markets, which price through `engine.gamebets` rather
#: than the prop chain and so answer to different gates — no tier
#: minimum, and a `MAX_CREDIBLE_EDGE` credibility test instead. Named
#: from what the ledger actually journals, not from what the module
#: could in principle emit.
GAME_MARKETS = ("moneyline", "spread", "total", "team_total")

#: WHAT A REPLAY HAS ACTUALLY SAID ABOUT EACH MARKET, 2026-08-30, over
#: 1,424 completed NFL games (1,184 with a stored close and team history)
#: through `engine.gamebacktest` against nflverse's closing consensus:
#:
#:     moneyline   Brier 0.2336, mean P(home) 55% against 55% actual —
#:                 mild real skill, since always-guessing-the-base-rate
#:                 scores 0.2475 — and NOT ONE bet graded above Pass
#:     total       projection off the close by 3.18 points, 449 games
#:                 refused for exceeding the credibility ceiling, NOT ONE
#:                 bet graded above Pass
#:     spread      off by 4.05 points, 578 refused, NOT ONE bet graded
#:     team_total  NO BACKTEST EXISTS
#:
#: The three that can be measured have never produced a gradeable bet in
#: four seasons. That is the gates working, not failing: the model does
#: not beat the closing number and correctly declines to bet it. Dropping
#: `min_team_games` from 15 to 0 changes nothing, so it is not a
#: thin-history effect either.
#:
#: WHICH MAKES THE LIVE BOARD THE THING TO EXPLAIN. It carries open game
#: bets in all four markets, and `ledger.journal_skip_reason` only
#: journals a row that was RECOMMENDED with a positive stake. A model
#: that qualifies nothing in replay and publishes live is describing two
#: different models, and the difference has to be found before either is
#: trusted.
BACKTESTED = {
    "moneyline": "1,184 games, Brier 0.2336, no bet graded above Pass",
    "spread": "1,184 games, off the close by 4.05 pts, none graded",
    "total": "1,184 games, off the close by 3.18 pts, none graded",
    "team_total": None,
}

#: Settled rows before a record means anything. Below this the ROI is a
#: number about four games.
MIN_SETTLED = 25


def calib_state(sport: str, market: str) -> dict:
    """Everything the calibration layer knows about one market."""
    from . import calibrate as C
    key = f"{sport}:{market}"
    store = C.load(C.DEFAULT_PATH)
    raw = store.get(key)
    entry = {"fitted": raw is not None}
    if raw is not None:
        temp, bias = raw if isinstance(raw, tuple) else (raw, 0.0)
        entry["temperature"] = temp
        entry["bias"] = bias
        entry["boundary"] = temp in (C.GRID_MIN, C.GRID_MAX)
    entry["one_sided"] = C.one_sided(sport, market)
    entry["reliable"] = C.is_reliable(sport, market)
    return entry


def settled_record(conn, sport: str, market: str) -> dict:
    """Won/lost rows and flat-stake ROI, straight from the ledger."""
    row = conn.execute(
        "SELECT COUNT(*) n, "
        "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) w, "
        "SUM(COALESCE(pnl_units, 0)) pnl, "
        "SUM(COALESCE(stake_units, 0)) staked "
        "FROM bets WHERE sport=? AND market=? AND status IN ('won','lost')",
        (sport, market)).fetchone()
    n = int((row[0] if row else 0) or 0)
    # OPEN ROWS COUNT AS EVIDENCE OF LIFE, not of performance. "0
    # settled" on a market that has never produced a pick and "0 settled"
    # on one holding thirteen open tickets are opposite states, and the
    # first cut of this report printed both as a bare zero.
    still_open = int(conn.execute(
        "SELECT COUNT(*) FROM bets WHERE sport=? AND market=? "
        "AND status NOT IN ('won','lost')", (sport, market)).fetchone()[0] or 0)
    if not n:
        return {"n": 0, "open": still_open}
    # ROI PER UNIT STAKED, not per bet: the board sizes its stakes, so
    # dividing by the count would rate a losing 3-unit bet the same as a
    # losing 0.5-unit one.
    staked = float(row[3] or 0.0)
    return {"n": n, "wins": int(row[1] or 0), "staked": staked,
            "open": still_open,
            "roi": (float(row[2] or 0.0) / staked) if staked else None}


def market_row(sport: str, market: str, conn=None) -> dict:
    from .quality import tier_min_edge, market_tier
    game = market in GAME_MARKETS
    got = {"market": market, "game": game,
           "tier": None if game else market_tier(market),
           # Game bets do not go through the §3 tier bars at all — they
           # answer to `gamebets.MAX_CREDIBLE_EDGE` instead. Printing the
           # default tier here would invent a rule this market has never
           # been subject to.
           "min_edge": None if game else tier_min_edge(market)}
    got.update(calib_state(sport, market))
    got["backtest"] = BACKTESTED.get(market, "") if game else ""
    got["settled"] = settled_record(conn, sport, market) if conn else {"n": 0}
    return got


def verdict_for(row: dict) -> tuple[str, str]:
    """``(state, what to do about it)`` for one market.

    The states are deliberately about CAUSE, not severity. "Shut" and
    "unmeasured" both produce an empty board and need opposite work.
    """
    if row.get("one_sided"):
        return ("SHUT: one-sided",
                "the correction cannot name both sides — refit, or retire "
                "the market. See calibrate.one_sided")
    if row.get("fitted") and row.get("boundary"):
        return ("SHUT: boundary fit",
                "the data wanted a bigger correction than the search "
                "allowed, so the stored temperature is a cap. Refit, or "
                "accept the model is wrong here")
    if row.get("game") and row.get("backtest") is None:
        return ("NO BACKTEST",
                "no replay exists for this market at all — it is publishing "
                "picks nothing has ever graded, which is worse than "
                "unmeasured because it looks measured")
    if not row.get("fitted"):
        why = ("never fitted: not broken, unmeasured. Needs settled rows "
               "or a harvest to fit against")
        if row.get("backtest"):
            # A market CAN be unfitted and still have been replayed, and
            # that replay is the more useful sentence of the two.
            why += f". Replay says: {row['backtest']}"
        return ("UNMEASURED", why)
    s = row.get("settled") or {}
    if s.get("n", 0) < MIN_SETTLED:
        opened = s.get("open") or 0
        if not s.get("n") and not opened:
            return ("LIVE, SILENT",
                    "calibrated and bettable and it has never published a "
                    "pick — either the gates never pass or nothing upstream "
                    "reaches this market. Check the board's gate census")
        return ("LIVE, UNPROVEN",
                f"calibrated and bettable; {s.get('n', 0)} settled"
                + (f" and {opened} still open" if opened else "")
                + " — the record cannot say whether it works yet")
    roi = s.get("roi")
    if roi is not None and roi < 0:
        return ("LIVE, LOSING",
                f"{s['n']} settled at {roi:+.1%} — the gates let it through "
                f"and it has not paid")
    return ("LIVE", f"{s['n']} settled"
            + (f" at {roi:+.1%}" if roi is not None else ""))


def report(sport: str = "nfl", conn=None) -> list:
    close_it = conn is None
    if conn is None:
        try:
            from . import ledger as L
            conn = L.connect()
        except Exception:                                  # noqa: BLE001
            conn = None
            close_it = False
    try:
        out = [f"=== {sport.upper()} readiness, market by market"]
        out.append(f"  {'market':<13}{'calib':>14}{'reliable':>10}"
                   f"{'min edge':>10}{'settled':>9}  state")
        rows = []
        for label, markets in (("player props", PLAYER_MARKETS),
                               ("game bets", GAME_MARKETS)):
            out.append(f"  -- {label}")
            for market in markets:
                r = market_row(sport, market, conn)
                rows.append(r)
                state, _why = verdict_for(r)
                calib = ("none" if not r.get("fitted")
                         else f"T={r['temperature']} b={r['bias']:+.2f}")
                s = r["settled"]
                bar = ("n/a" if r["min_edge"] is None
                       else f"{r['min_edge']:.1%}")
                seen = (f"{s.get('n', 0)}"
                        + (f"+{s['open']}o" if s.get("open") else ""))
                out.append(
                    f"  {market:<13}{calib:>14}"
                    f"{('yes' if r['reliable'] else 'NO'):>10}"
                    f"{bar:>10}{seen:>9}  {state}")
        out.append("")
        for r in rows:
            state, why = verdict_for(r)
            if state.startswith("LIVE") and "UNPROVEN" not in state \
                    and "LOSING" not in state:
                continue
            out.append(f"  {r['market']}: {why}")
        if not conn:
            out.append("  (no ledger on this box — the settled column is "
                       "empty here and real on the one that takes bets)")
        return out
    finally:
        if close_it and conn is not None:
            conn.close()


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    for line in report(args[0] if args else "nfl"):
        print(line)
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
