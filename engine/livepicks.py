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
                        progress: dict | None = None,
                        longshots: list[dict] | None = None,
                        identity: dict | None = None) -> list[dict]:
    """One row per open journaled pick whose game is LIVE right now.

    ``progress``: {normalized player name: {market: current value}} from
    engine.mlb.livestats — optional; rows render without it.

    ``longshots``: the Long Shots board. A player prop is placed on the
    field by looking its name up in the recommendations, and long shots are
    NOT in that list — they are a separate board with its own bucket in the
    journal. Without them here, every home-run bet the site recommends maps
    to nothing and reports itself as unmapped, which is how a full night of
    live long shots renders as an empty tracker.

    ``identity``: {player: {team, headshot}} from engine.rosters.identity_map
    — who a player IS, independent of tonight's prices. THIS IS THE ONE
    SOURCE HERE THAT SURVIVES FIRST PITCH, and the reason it had to exist
    is below.
    """
    progress = progress or {}
    rec_idx = {(normalize_name(r.get("player", "")), r.get("market", "")): r
               for r in recommendations}
    # The main board wins a collision: if the same player+market is on both,
    # the main row is the one carrying the staked bet's context.
    for r in (longshots or []):
        rec_idx.setdefault(
            (normalize_name(r.get("player", "")), r.get("market", "")), r)

    # THREE PLACES TO LOOK, IN DESCENDING ORDER OF WHAT THEY KNOW.
    #
    # Ethan, 2026-08-13, on a Live Now screenshot: "it says it couldnt map
    # the game AND its not showing the heashshots of the players." Both
    # symptoms, one cause — a row was placed on the field ONLY by an exact
    # (player, market) hit on tonight's board, and the face was taken from
    # that same row, so a miss cost the game AND the photo together.
    #
    # And the board is precisely the thing that does not survive first
    # pitch. A book pulls its pre-game pitcher markets when the game goes
    # live; that prop then has no row tonight, no matter how correctly it
    # was journaled two hours earlier. Every unmapped name in his
    # screenshot was a pitcher (strikeouts, outs) and every mapped one a
    # hitter on the home-run board, which is the fingerprint of market
    # availability rather than of name matching.
    #
    # The page's own footnote already promised the opposite behaviour — "a
    # bet stays here until it settles, even if the pick later drops off
    # Tonight's Picks because prices moved" — so this was the mapping
    # contradicting the design, not the design being unclear.
    #
    # 1. exact (player, market): the full context — team, opponent, leg,
    #    face, and the ONLY row allowed to name this bet's market.
    # 2. the same player on ANY market tonight: he is in a game and it is
    #    the same game whatever he is priced for.
    # 3. the identity map: the club he plays for, from the league's own
    #    roster feed. Needs no board at all.
    player_idx: dict[str, dict] = {}
    for r in list(recommendations) + list(longshots or []):
        player_idx.setdefault(normalize_name(r.get("player", "")), r)
    id_idx = {normalize_name(k): v for k, v in (identity or {}).items()}

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

    def _face(b):
        """This player's photo, from whichever source still has one.

        Deliberately independent of whether the bet could be placed on a
        game: not knowing which field a man is on is no reason to stop
        knowing what he looks like, and the unmapped rows losing their
        faces is half of what Ethan reported.

        Returns "" for anything that is not a player prop. `player` holds
        a team ABBREVIATION on a moneyline and "AWAY@HOME" on a game
        total, so a name lookup there is a lookup for a player who does
        not exist — and any hit would be a collision, not a face.
        """
        m = b.get("market", "")
        if m in TEAM_MARKETS or m == "total":
            return ""
        n = normalize_name(b.get("player", ""))
        for src in (rec_idx.get((n, b.get("market", ""))),
                    player_idx.get(n), id_idx.get(n)):
            face = (src or {}).get("headshot") or ""
            if face:
                return face
        return ""

    def _unmapped(b, face=""):
        """An open bet the current board can't place — NEVER drop it: the
        section's count must always match the Record's, and a bet we can't
        map is a fact worth showing, not hiding."""
        return {
            "player": b.get("player"), "market": b.get("market", ""),
            "market_label": b.get("market", ""),
            "side": (b.get("side") or "OVER").upper(),
            "line": float(b.get("line") or 0),
            "odds": b.get("odds"), "stake_units": b.get("stake_units") or 0,
            "current": None, "status": "unmapped", "phase": "upcoming",
            "team": "", "headshot": face, "game": {},
            "category": b.get("category", "main"),
        }

    out = []
    for b in open_bets:
        market = b.get("market", "")
        rec = where = None
        if market in TEAM_MARKETS:
            g = _game_for(b.get("player"))
        elif market == "total":
            key = b.get("player", "")           # journaled as AWAY@HOME
            g = next((x for x in games
                      if f"{x.get('away', '')}@{x.get('home', '')}" == key), None)
        else:
            n = normalize_name(b.get("player", ""))
            rec = rec_idx.get((n, market))
            # `rec` stays EXACT-MARKET ONLY below this line. It is the row
            # that gets to say "Home Runs 0.5+", and a cross-market match
            # would relabel a strikeouts bet with a home-run market label —
            # trading an honest "unmapped" for a confident wrong one.
            # Placement is a different question, so it gets its own answer.
            where = rec or player_idx.get(n) or id_idx.get(n)
            if where is None:
                out.append(_unmapped(b, _face(b)))
                continue
            g = _game_for(where.get("team"), where.get("opponent"),
                          where.get("game_number") or 0)
        if not g:
            out.append(_unmapped(b, _face(b)))
            continue
        live = g.get("live") or {}
        state = live.get("state") or "scheduled"
        phase = state if state in ("live", "final") else "upcoming"

        current = None
        if market not in TEAM_MARKETS and market != "total":
            current = (progress.get(normalize_name(b.get("player", ""))) or {}) \
                .get(market)
        side = (b.get("side") or "OVER").upper()
        line = float(b.get("line") or 0)
        hs, as_ = live.get("home_score"), live.get("away_score")

        # Every open bet gets a phase and, where the numbers exist, a
        # verdict-in-waiting. FINAL games grade provisionally on the spot
        # (official settle still happens overnight from ingested results).
        status = "upcoming"
        if phase == "live":
            status = "tracking"
            if current is None and hs is not None and as_ is not None:
                # Team markets track from the live score, same as the books
                # do. Moneyline has no stat to bar — the score line says it.
                pick_home = b.get("player") == g.get("home")
                if market == "total":
                    current = float(hs) + float(as_)
                elif market == "team_total":
                    current = float(hs if pick_home else as_)
                elif market == "spread":
                    current = float(hs - as_) if pick_home else float(as_ - hs)
            # Early verdicts only where the number can't come back down:
            # player stats and run totals only ever go UP, so an over can
            # lock in and an under can die mid-game. A spread margin swings
            # both ways, so it tracks without ever locking.
            if current is not None and market not in ("spread", "moneyline"):
                if side == "OVER" and current > line:
                    status = "cleared"          # an over can lock in early…
                elif side == "UNDER" and current > line:
                    status = "busted"           # …and an under can die early
        elif phase == "final":
            actual = current
            if actual is None and hs is not None and as_ is not None:
                # Team markets grade from the final score.
                pick_home = b.get("player") == g.get("home")
                if market == "moneyline":
                    actual = 1.0 if ((hs > as_) == pick_home) else 0.0
                    side, line = "OVER", 0.5
                elif market == "total":
                    actual = float(hs) + float(as_)
                elif market == "spread":
                    actual = float(hs - as_) if pick_home else float(as_ - hs)
                elif market == "team_total":
                    actual = float(hs if pick_home else as_)
            if actual is None:
                status = "final_pending"        # no stat line available yet
            elif actual == line:
                status = "push_pending"
            else:
                won = (actual > line) == (side == "OVER")
                status = "won_pending" if won else "lost_pending"
                current = actual
        out.append({
            "player": b.get("player"), "market": market,
            "market_label": (rec or {}).get("market_label")
                or {"moneyline": "Moneyline", "total": "Game Total",
                    "spread": "Run Line", "team_total": "Team Total"}
                    .get(market, market),
            "side": side, "line": line,
            "odds": b.get("odds"), "stake_units": b.get("stake_units") or 0,
            "current": current, "status": status, "phase": phase,
            # Which journal bucket this came from. The same player can hold a
            # bet in two buckets at once — a long shot and a stale-line flag
            # on the same homer — so name + market alone does not identify a
            # row, and anything reconciling this list against the journal
            # will silently mismatch without it.
            "category": b.get("category", "main"),
            "team": (where or {}).get("team", b.get("player", "")),
            # The face, for the tracker's identity column. Only a prop has
            # one — a team market's `player` field holds an ABBREVIATION,
            # and a game total's holds "AWAY@HOME" — which is why this asks
            # the sources rather than inventing a lookup for every row.
            "headshot": _face(b),
            "game": {"home": g.get("home"), "away": g.get("away"),
                     "game_number": g.get("game_number", 1),
                     "doubleheader": g.get("doubleheader", False),
                     "date": g.get("date", ""), "kickoff": g.get("kickoff", ""),
                     "state": state,
                     "period": live.get("period", ""),
                     "home_score": hs, "away_score": as_,
                     # At-bat / outs / runners strip, when the feed has it.
                     "situation": live.get("situation")},
        })
    # Live action first (good news leads), then finals awaiting the official
    # settle, then tonight's not-yet-started bets.
    order = {"cleared": 0, "tracking": 1, "busted": 2,
             "won_pending": 3, "push_pending": 4, "lost_pending": 5,
             "final_pending": 6, "upcoming": 7, "unmapped": 8}
    out.sort(key=lambda r: (order.get(r["status"], 7), -(r["stake_units"] or 0)))
    return out
