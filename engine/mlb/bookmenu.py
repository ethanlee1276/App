"""Props from the book's own menu — the roster source that never waits.

Sportsbooks post player props hours before official lineups: their menu IS
the market's statement of who is expected to play. When the odds feed prices
a player who isn't on the slate (lineup not posted, and no recent order to
project him from), this module builds his prop directly:

  * **lines** — the books' real posted prices, exactly as pulled;
  * **logs** — the player's own ingested season from the history DB;
  * **team/opponent** — resolved from his latest log against the event's
    matchup.

Nothing is invented. The player's batting spot is unknown (0), which keeps
plate appearances estimated, adds the "lineup unconfirmed" caveat on the HR
board, and makes the rules engine hold any recommendation until the official
card posts.
"""

from __future__ import annotations

from .models import MLBProp, MLBGameLog, HITTER_MARKETS

MIN_LOGS = 3


def logs_by_player(conn, market: str,
                   seasons: list[int] | None = None) -> dict[str, dict]:
    """``{normalized_player: {"player", "team", "position", "logs"}}`` from
    the ingested history — logs newest-first, like a live game log."""
    from ..sources.oddsapi import normalize_name

    # SEASON-SCOPED, and that is not an optimisation. `compute_form` blends
    # a "season" window at 20% for MLB, and this query used to return every
    # row we had. With one season ingested that was correct by accident;
    # with six it silently turned the season average into a six-year career
    # average and diluted current form with a player who no longer exists.
    # More history made the live model worse — the backtest wants all of
    # it, the projection wants this year.
    q = ("SELECT player, team, opponent, position, period, value, home "
         "FROM player_game_logs WHERE sport='mlb' AND market=?")
    args: list = [market]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    rows = conn.execute(q + " ORDER BY period", args).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        rec = out.setdefault(normalize_name(r["player"]),
                             {"player": r["player"], "rows": []})
        rec["rows"].append(r)
    for rec in out.values():
        rows = rec["rows"]
        last = rows[-1]
        rec["team"] = last["team"]
        rec["position"] = last["position"] or ""
        n = len(rows)
        rec["logs"] = [MLBGameLog(game=n - i, opponent=r["opponent"],
                                  value=float(r["value"]), home=bool(r["home"]),
                                  date=str(r["period"]))
                       for i, r in enumerate(rows)][::-1]
        del rec["rows"]
    return out


def add_book_listed_props(slate, book_only: list[dict], conn,
                          seasons: list[int] | None = None) -> int:
    """Build hitter props for book-priced players missing from the slate.

    Returns how many props were added. Pitcher markets are skipped (probable
    starters already exist independent of lineups), as is anyone without
    enough ingested history to project honestly.

    ``seasons`` bounds the form history. Callers on the LIVE path pass the
    current season; leaving it open means the projection's "season" window
    quietly becomes a career average once more than one season is
    ingested.
    """
    existing = set()
    from ..sources.oddsapi import normalize_name
    for p in slate.props:
        existing.add((normalize_name(p.player), p.market))

    history: dict[str, dict[str, dict]] = {}
    added = 0
    for entry in book_only:
        market = entry.get("market", "")
        if market not in HITTER_MARKETS:
            continue
        lines = entry.get("lines") or []
        if not lines:
            continue
        norm = normalize_name(entry.get("player", ""))
        if not norm or (norm, market) in existing:
            continue
        if market not in history:
            history[market] = logs_by_player(conn, market, seasons)
        rec = history[market].get(norm)
        if not rec or len(rec["logs"]) < MIN_LOGS:
            continue                     # nobody to model — needs history
        home, away = entry.get("home", ""), entry.get("away", "")
        team = rec["team"]
        if team == home:
            opponent = away
        elif team == away:
            opponent = home
        else:
            continue                     # traded / stale team — don't guess
        logs = rec["logs"]
        slate.props.append(MLBProp(
            player=rec["player"], team=team, opponent=opponent,
            position=rec["position"], market=market, logs=logs,
            career_avg=round(sum(g.value for g in logs) / len(logs), 3),
            vs_pitcher_avg=None, lines=list(lines),
            bats="R", lineup_spot=0,
        ))
        existing.add((norm, market))
        added += 1
    return added
