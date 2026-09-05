"""Live per-player stat lines from an in-progress boxscore.

The MLB Stats API boxscore we already fetch for lineups carries each
player's batting and pitching line as the game runs. This module turns it
into ``{normalized name: {market: current value}}`` for the markets the
journal actually bets — so a pre-game pick can show "2 total bases, needs
one more" while its game is live, instead of going dark until settlement.

Pure parsing; fixture-tested.
"""

from __future__ import annotations

from ..sources.oddsapi import normalize_name


def parse_situation(linescore: dict) -> dict:
    """The live game situation from a linescore payload: who's at the plate
    (and on deck), who's pitching, outs, count, and which bases are
    occupied — the sportsbook-style "Top 6 · 2 out · runners on the corners"
    strip. Pure parsing; fixture-tested."""
    off = linescore.get("offense") or {}
    de = linescore.get("defense") or {}

    def _name(d, key):
        return ((d.get(key) or {}).get("fullName")) or ""

    return {
        "batter": _name(off, "batter"),
        "on_deck": _name(off, "onDeck"),
        "pitcher": _name(de, "pitcher"),
        "outs": int(linescore.get("outs") or 0),
        "balls": int(linescore.get("balls") or 0),
        "strikes": int(linescore.get("strikes") or 0),
        # Occupied bases carry the runner's name; empty bases are "".
        "bases": {b: _name(off, b) for b in ("first", "second", "third")},
        "half": (linescore.get("inningHalf") or ""),
        "inning": int(linescore.get("currentInning") or 0),
    }


def parse_live_stats(boxscore: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for side in ("home", "away"):
        players = ((boxscore.get("teams") or {}).get(side) or {}).get("players") or {}
        for p in players.values():
            name = ((p.get("person") or {}).get("fullName")) or ""
            if not name:
                continue
            stats = p.get("stats") or {}
            bat = stats.get("batting") or {}
            pit = stats.get("pitching") or {}
            row: dict = {}
            if bat:
                h = int(bat.get("hits") or 0)
                d2 = int(bat.get("doubles") or 0)
                t3 = int(bat.get("triples") or 0)
                hr = int(bat.get("homeRuns") or 0)
                # Total bases = singles + 2·2B + 3·3B + 4·HR
                #             = hits + doubles + 2·triples + 3·HR.
                row.update(hits=float(h), home_runs=float(hr),
                           total_bases=float(h + d2 + 2 * t3 + 3 * hr))
            if pit.get("strikeOuts") is not None or pit.get("inningsPitched"):
                row["strikeouts"] = float(pit.get("strikeOuts") or 0)
            # WHERE HE BATS AND HOW OFTEN HE HAS BATTED. Neither is a
            # market, so neither belongs in the bar-vs-line display — they
            # are what `liveprops` needs to work out how many more cracks
            # at it he has left, which is the whole difference between "he
            # needs one more base" and "he needs one more base and is not
            # coming up again".
            #
            # `battingOrder` is a three-digit string: "300" is the number
            # three hitter, "301" the first player to replace him there.
            # Only the slot matters here, so the last two digits go.
            order = str(p.get("battingOrder") or "")
            if order.isdigit():
                row["spot"] = int(order) // 100
            if bat.get("plateAppearances") is not None:
                row["pa"] = float(bat.get("plateAppearances") or 0)
            if pit.get("battersFaced") is not None:
                row["bf"] = float(pit.get("battersFaced") or 0)
            if row:
                out[normalize_name(name)] = row
    return out


def current_pitchers(boxscore: dict) -> set:
    """Whoever is on the mound for each side, normalized.

    The API lists each team's ``pitchers`` in the order they appeared, so
    the last id is the one currently throwing. A starter who is NOT in
    this set has finished: his strikeout prop cannot move again, which
    turns a live probability into a settled one.
    """
    out = set()
    for side in ("home", "away"):
        team = ((boxscore.get("teams") or {}).get(side) or {})
        ids = team.get("pitchers") or []
        if not ids:
            continue
        p = (team.get("players") or {}).get(f"ID{ids[-1]}") or {}
        name = ((p.get("person") or {}).get("fullName")) or ""
        if name:
            out.add(normalize_name(name))
    return out
