"""Live picks — journaled PRE-GAME picks whose games are now in progress.

The pre-game model never recommends an in-play bet (its projections assume
a full game of opportunity), so once first pitch passes, a recommended
pick vanishes from the board — even though it was placed and is live right
now. This module brings those picks back as a TRACKER: the open journal
rows for today's slate, matched to their (live) games, with the player's
current stat line where the boxscore provides one.

Nothing here creates a bet. It answers "how are the bets we already made
doing?" — the question every bettor asks the moment the game starts.

Pure assembly; the callers supply journal rows, the slate's games and
recommendations, and (optionally) live per-player stats.
"""

from __future__ import annotations

from .sources.oddsapi import normalize_name

TEAM_MARKETS = {"moneyline", "spread", "team_total"}


def assemble_live_picks(open_bets: list[dict], recommendations: list[dict],
                        games: list[dict],
                        progress: dict | None = None) -> list[dict]:
    """One row per open journaled pick whose game is LIVE right now.

    ``progress``: {normalized player name: {market: current value}} from
    engine.mlb.livestats — optional; rows render without it.
    """
    progress = progress or {}
    rec_idx = {(normalize_name(r.get("player", "")), r.get("market", "")): r
               for r in recommendations}

    def _game_for(team, opp=None, gn=0):
        matches = []
        for g in games:
            pair = {g.get("home"), g.get("away")}
            if team not in pair or (opp is not None and opp not in pair):
                continue
            if gn and g.get("game_number") and gn != g.get("game_number"):
                continue
            matches.append(g)
        # Doubleheader without an explicit leg (team-level bets): the LIVE
        # leg is the one being tracked; a final/scheduled sibling isn't.
        live = [g for g in matches
                if ((g.get("live") or {}).get("state")) == "live"]
        return (live or matches or [None])[0]

    out = []
    for b in open_bets:
        market = b.get("market", "")
        rec = None
        if market in TEAM_MARKETS:
            g = _game_for(b.get("player"))
        elif market == "total":
            key = b.get("player", "")           # journaled as AWAY@HOME
            g = next((x for x in games
                      if f"{x.get('away', '')}@{x.get('home', '')}" == key), None)
        else:
            rec = rec_idx.get((normalize_name(b.get("player", "")), market))
            if rec is None:
                continue
            g = _game_for(rec.get("team"), rec.get("opponent"),
                          rec.get("game_number") or 0)
        live = (g or {}).get("live") or {}
        if not g or live.get("state") != "live":
            continue

        current = None
        if market not in TEAM_MARKETS and market != "total":
            current = (progress.get(normalize_name(b.get("player", ""))) or {}) \
                .get(market)
        side = (b.get("side") or "OVER").upper()
        line = float(b.get("line") or 0)
        status = "tracking"
        if current is not None:
            if side == "OVER" and current > line:
                status = "cleared"              # an over can lock in early…
            elif side == "UNDER" and current > line:
                status = "busted"               # …and an under can die early
        out.append({
            "player": b.get("player"), "market": market,
            "market_label": (rec or {}).get("market_label")
                or {"moneyline": "Moneyline", "total": "Game Total",
                    "spread": "Run Line", "team_total": "Team Total"}
                    .get(market, market),
            "side": side, "line": line,
            "odds": b.get("odds"), "stake_units": b.get("stake_units") or 0,
            "current": current, "status": status,
            "team": (rec or {}).get("team", b.get("player", "")),
            "game": {"home": g.get("home"), "away": g.get("away"),
                     "game_number": g.get("game_number", 1),
                     "doubleheader": g.get("doubleheader", False),
                     "state": live.get("state"),
                     "period": live.get("period", ""),
                     "home_score": live.get("home_score"),
                     "away_score": live.get("away_score")},
        })
    # Cleared first (good news leads), then by stake.
    order = {"cleared": 0, "tracking": 1, "busted": 2}
    out.sort(key=lambda r: (order.get(r["status"], 1), -(r["stake_units"] or 0)))
    return out
