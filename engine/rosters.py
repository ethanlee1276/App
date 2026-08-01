"""Active NFL rosters, per team, from the roster feed already on disk.

The Fantasy page uses this feed to answer "who moved" and "who's a
rookie". The same blob answers a plainer question the site couldn't:
*who is on this team right now*. No new source, no new request — the
players file is already fetched and cached for the fantasy layer, so this
is a second reading of it.

Two decisions worth stating, because they're what makes the page honest:

* **Depth-chart order is the coaching staff's opinion, not ours.** Rows
  are grouped by position and sorted by the slot the team lists, so QB1
  is above QB2 because Sleeper says so. Where a team publishes no order,
  the player still appears — just unranked, rather than silently dropped
  or invented into a slot.
* **Inactive is shown, not hidden.** A roster with the IR players quietly
  removed reads as a healthy team. They're listed with their status, at
  the bottom of their position group.
"""

from __future__ import annotations

# The fantasy skill positions plus the rest of an actual roster. A page
# called "active roster" that only lists four positions is not one.
OFFENCE = ("QB", "RB", "FB", "WR", "TE", "OL", "OT", "OG", "C")
DEFENCE = ("DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "S", "FS", "SS", "DB")
SPECIAL = ("K", "P", "LS")
GROUPS = (("Offense", OFFENCE), ("Defense", DEFENCE), ("Special teams", SPECIAL))
POSITION_ORDER = {p: i for i, p in enumerate(OFFENCE + DEFENCE + SPECIAL)}

# Statuses that mean "on the roster but not available this week". Anything
# else Sleeper reports is passed through verbatim rather than guessed at.
UNAVAILABLE = {"injured reserve", "ir", "pup", "non football injury",
               "suspended", "physically unable to perform"}


def _is_unavailable(status: str) -> bool:
    return (status or "").strip().lower() in UNAVAILABLE


def _player_row(p: dict) -> dict | None:
    """One roster row, or None when the entry isn't a real rostered player."""
    from .offseason import _canon_team
    if not isinstance(p, dict):
        return None
    team = _canon_team(p.get("team"))
    if not team:
        return None                       # free agent — no roster to be on
    name = (p.get("full_name")
            or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
    if not name:
        return None
    pos = (p.get("position") or "").upper()
    order = p.get("depth_chart_order")
    exp = p.get("years_exp")
    return {
        "player": name,
        "team": team,
        "position": pos,
        # The slot the STAFF lists him at, which is not always his listed
        # position (a slot receiver shows SWR, a nickel corner NB).
        "depth_pos": (p.get("depth_chart_position") or pos).upper(),
        "depth_order": order if isinstance(order, int) else None,
        "status": (p.get("status") or "").strip(),
        "unavailable": _is_unavailable(p.get("status") or ""),
        "rookie": exp in (0, "0"),
        "years_exp": exp if isinstance(exp, int) else None,
        "number": p.get("number") if isinstance(p.get("number"), int) else None,
        "age": p.get("age") if isinstance(p.get("age"), int) else None,
    }


def _sort_key(r: dict) -> tuple:
    """Position group, then the staff's depth order, then name.

    Unranked players sort AFTER ranked ones inside their position rather
    than to the top — an unlisted depth slot is missing information, not
    a claim that he's the starter."""
    return (POSITION_ORDER.get(r["position"], 99),
            r["unavailable"],
            r["depth_order"] if r["depth_order"] is not None else 99,
            r["player"])


def build_rosters(blob: dict | None) -> dict:
    """``{teams: {ABBR: {...}}, counts, generated_from}`` from the feed.

    Pure: give it the players blob and it returns the payload the page
    renders. An empty or missing blob yields an empty payload rather than
    a partial one — "no roster feed" must never render as "empty rosters".
    """
    teams: dict[str, list] = {}
    for p in (blob or {}).values():
        row = _player_row(p)
        # Inactive-and-teamless entries (practice squad churn, retired
        # players Sleeper keeps) carry no team and drop out above.
        if row is None or not row["position"]:
            continue
        teams.setdefault(row["team"], []).append(row)

    out: dict[str, dict] = {}
    for team, rows in teams.items():
        rows.sort(key=_sort_key)
        out[team] = {
            "players": rows,
            "count": len(rows),
            "unavailable": sum(1 for r in rows if r["unavailable"]),
            "rookies": sum(1 for r in rows if r["rookie"]),
        }
    return {"teams": out, "team_count": len(out),
            "player_count": sum(t["count"] for t in out.values())}


def group_of(position: str) -> str:
    """Which section of the page a position belongs in."""
    for label, members in GROUPS:
        if position in members:
            return label
    return "Other"


# --- Rosters for the sports with no roster feed -----------------------------
#
# Only the NFL has a published players file here. For MLB, the NBA and the
# WNBA the honest source is the one we already own: our own ingested game
# logs. Who has actually appeared for a team this season, how often, and
# how recently is not a copy of somebody's roster page — it is a record of
# who played, which is the question a bettor is really asking. It also
# cannot go stale in the way a scraped roster can, because it is refreshed
# by the same nightly ingest that feeds the models.
#
# What it is NOT: a transactions feed. A player who was traded last week
# appears under BOTH teams with the dates that say so, and the page shows
# his most recent club first rather than pretending to know the move
# happened. That is the truthful version of what game logs can tell you.

# How many days without an appearance before somebody is listed as
# inactive rather than active. Long enough to survive a rest day or a
# short IL stint, short enough that a released player stops looking like a
# starter.
STALE_DAYS = {"mlb": 14, "nba": 21, "wnba": 21}

# The market we count appearances from, per sport. One row per game
# played, so counting these counts games — using every market would count
# a hitter once per stat line.
APPEARANCE_MARKET = {"mlb": "pa", "nba": "min", "wnba": "min"}


def from_game_logs(conn, sport: str, seasons: list[int] | None = None,
                   today: str | None = None) -> dict:
    """Rosters for one sport, built from who actually appeared.

    Returns the same payload shape as :func:`build_rosters` so the page
    renders one way for every sport.
    """
    import datetime as _dt

    market = APPEARANCE_MARKET.get(sport)
    if not market:
        return {"teams": {}, "team_count": 0, "player_count": 0}
    q = ("SELECT player, team, position, MAX(period) AS last_seen, "
         "COUNT(*) AS games FROM player_game_logs "
         "WHERE sport=? AND market=? AND team IS NOT NULL AND team != ''")
    args: list = [sport, market]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    q += " GROUP BY player, team"
    rows = conn.execute(q, args).fetchall()

    day = _dt.date.fromisoformat(today) if today else _dt.date.today()
    cutoff = (day - _dt.timedelta(days=STALE_DAYS.get(sport, 21))).isoformat()

    def _dated(period: str) -> bool:
        """Is this period an ISO date we can measure staleness against?

        The NFL stores week numbers here, not dates. Comparing "018" to a
        cutoff string is a comparison that always succeeds and always
        means nothing — it would stamp an entire league "not in a game
        since 018". A period we cannot read is one we make no claim about.
        """
        try:
            _dt.date.fromisoformat(str(period))
            return True
        except ValueError:
            return False

    # A player who changed teams has a row per team. His CURRENT club is
    # the one he appeared for most recently; the others are history and
    # are not listed as if he were still there.
    latest: dict[str, str] = {}
    for r in rows:
        seen = latest.get(r["player"])
        if seen is None or str(r["last_seen"]) > seen:
            latest[r["player"]] = str(r["last_seen"])

    teams: dict[str, list] = {}
    for r in rows:
        last = str(r["last_seen"])
        if last != latest[r["player"]]:
            continue                      # an old club, not this one
        cold = _dated(last) and last < cutoff
        teams.setdefault(r["team"], []).append({
            "player": r["player"],
            "team": r["team"],
            "position": (r["position"] or "").upper(),
            "depth_pos": (r["position"] or "").upper(),
            "depth_order": None,
            "status": f"not in a game since {last}" if cold else "",
            "unavailable": cold,
            "rookie": False,
            "years_exp": None, "number": None, "age": None,
            "games": int(r["games"]), "last_seen": last,
        })

    out: dict[str, dict] = {}
    for team, players in teams.items():
        # Most games played first: on a roster with no published depth
        # chart, playing time IS the depth chart, and it is measured
        # rather than claimed.
        players.sort(key=lambda p: (p["unavailable"], -p["games"], p["player"]))
        out[team] = {
            "players": players,
            "count": len(players),
            "unavailable": sum(1 for p in players if p["unavailable"]),
            "rookies": 0,
        }
    return {"teams": out, "team_count": len(out),
            "player_count": sum(t["count"] for t in out.values())}


# --- Transactions: who changed teams, found by diffing our own history ------
#
# There is no transactions API here and none is needed. The roster feed
# already says which team every player is on; store that each day and a
# trade is simply the day the answer changed. No news source to go stale,
# nobody to tell the site a trade happened, and it works for every player
# rather than the ones somebody remembered to mention.
#
# The file is NOT prefixed with anything in maintenance.PRUNABLE_CACHE_PREFIXES,
# so the cache pruner leaves it alone by construction — this is accumulated
# history, and losing it means losing the ability to see a move at all.
SNAPSHOT_FILE = "roster_snapshots.json"
KEEP_DAYS = 45


def team_snapshot(blob: dict | None) -> dict[str, str]:
    """``{player: team}`` for everyone on a roster today.

    Deliberately broader than the camp watch's depth-chart snapshot, which
    only covers fantasy positions with a numeric slot: a trade is a trade
    whether or not the player is on somebody's fantasy board.
    """
    out: dict[str, str] = {}
    for p in (blob or {}).values():
        row = _player_row(p)
        if row and row["position"]:
            out[row["player"]] = row["team"]
    return out


def _path(path=None):
    from pathlib import Path
    from .sources.fetch import CACHE_DIR
    return Path(path) if path else Path(CACHE_DIR) / SNAPSHOT_FILE


def record_teams(blob: dict | None, today: str, path=None) -> dict:
    """Store today's team map, prune old days, return the whole store."""
    import datetime as _dt
    import json
    p = _path(path)
    try:
        store = json.loads(p.read_text())
    except (OSError, ValueError):
        store = {}
    snap = team_snapshot(blob)
    if snap:                      # an unreachable feed must not erase history
        store[today] = snap
    try:
        floor = (_dt.date.fromisoformat(today)
                 - _dt.timedelta(days=KEEP_DAYS)).isoformat()
        store = {d: s for d, s in store.items() if d >= floor}
    except ValueError:
        pass
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store))
    except OSError:
        pass                      # a read-only disk loses history, not the build
    return store


def transactions(store: dict, days: int = 14) -> dict:
    """Team changes across the stored snapshots, newest first.

    Compares each stored day against the one before it, so a player who
    moved twice shows both moves rather than only the net result. A player
    who appears for the first time is NOT a transaction — he could be a
    signing, but he could equally be the feed adding a player it didn't
    carry yesterday, and we can't tell the two apart.
    """
    dates = sorted(store)
    if len(dates) < 2:
        return {"moves": [], "days": len(dates),
                "from": dates[0] if dates else None,
                "to": dates[-1] if dates else None}
    window = dates[-(days + 1):]
    moves = []
    for older, newer in zip(window, window[1:]):
        before, after = store[older] or {}, store[newer] or {}
        for player, team in after.items():
            was = before.get(player)
            if was and was != team:
                moves.append({"player": player, "from": was, "to": team,
                              "date": newer})
    moves.sort(key=lambda m: (m["date"], m["player"]), reverse=True)
    return {"moves": moves, "days": len(window),
            "from": window[0], "to": window[-1]}
