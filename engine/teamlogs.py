"""What a team has actually done lately — the game bets' equivalent of a
player's game log.

Ethan, 2026-08-13, circling a run line on the dashboard: "i should be able
to click on this prop and it shows more info for the prop and it will show
the bar graph too."

The pick he circled was MIL +1.5 — a GAME bet, not a player prop, and the
prop page could not open it for a straightforward reason: a run line has
no player and therefore no player game log, so there was nothing to draw.
That is a gap in the DATA the page was offered, not a reason the page
cannot exist. A run line's history is the team's last few RESULTS, and we
have been ingesting those all along to grade our own game bets with.

WHAT EACH MARKET'S BAR ACTUALLY IS, because they are not the same number
and charting the wrong one would be worse than charting nothing:

    moneyline    the team's margin, read against 0
    spread       the team's margin, read against the handicap
    team total   the runs/points that team SCORED
    game total   the combined score of the game

All four come out of one row of the `games` table, so this returns the raw
per-game facts and lets the caller pick the quantity its market needs.
Nothing is derived, averaged or projected here.

Read-only, standard library, one query per sport.
"""

from __future__ import annotations

DEFAULT_N = 10


def recent_games(conn, sport: str, teams=None, before: str | None = None,
                 n: int = DEFAULT_N, seasons=None) -> dict:
    """``{team: [game, …]}`` newest first, each game a plain dict.

    ``before`` excludes the day being priced. That exclusion is the whole
    reason this takes a date at all: tonight's own result is not evidence
    about tonight's bet, and a chart that quietly included it would be
    reporting the answer as if it were the reasoning. Same rule
    `team_form` documents, for the same reason.

    ``seasons`` defaults to the season ``before`` falls in. Without it a
    backfilled history would hand a team its 2023 form as "recent", and
    the last five games would run straight through an offseason.
    """
    if seasons is None and before:
        try:
            from .seasons import season_of
            seasons = [season_of(sport, before)]
        except Exception:                                     # noqa: BLE001
            seasons = None
    q = ("SELECT season, period, home, away, home_score, away_score "
         "FROM games WHERE sport=? AND home_score IS NOT NULL "
         "AND away_score IS NOT NULL AND period IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    try:
        rows = conn.execute(q + " ORDER BY season, period", args).fetchall()
    except Exception:                                         # noqa: BLE001
        return {}         # no games table is no history, not a broken page

    want = {t for t in (teams or []) if t}
    out: dict[str, list] = {}
    for r in rows:
        period = str(r["period"])
        # A period we cannot compare to a date is one we make no claim
        # about — the NFL stores week numbers here, and "018" < "2026-08-13"
        # is a comparison that always succeeds and never means anything.
        if before and len(period) == 10 and period >= before:
            continue
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        for team, opp, mine, theirs, home in (
                (r["home"], r["away"], hs, as_, True),
                (r["away"], r["home"], as_, hs, False)):
            if want and team not in want:
                continue
            out.setdefault(team, []).append({
                "when": period,
                "opponent": opp,
                "home": home,
                "scored": mine,
                "allowed": theirs,
                "margin": mine - theirs,
                "total": hs + as_,
                "won": bool(mine > theirs),
            })
    # Newest first, trimmed. Sorted rather than reversed: the query orders
    # by (season, period) across every team at once, so one team's rows
    # arrive in order but the list has to be cut from the END.
    for team in out:
        out[team] = out[team][-n:][::-1]
    return out
