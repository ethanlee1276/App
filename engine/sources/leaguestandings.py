"""The league's OWN standings, fetched — not counted from our results.

Ethan, 2026-08-12, with the MLB page open: "This is not live or real data
at all. We need too fix that so our standings pages displays the actual
standings of the current seasons LIVE DATA."

He was right, and the tell was in the table: MLB records read 70-69-1 and
66-68-4. Baseball has no ties. Those columns were unfinished or unscored
rows in our own games table being counted as played games, and the whole
order followed them — the White Sox sat top of the AL Central.

`engine.standings.compute` counts finished games we have ingested. That is
a genuinely good property for a site whose boards must agree with each
other, and it stays as the FALLBACK. But it answers "what do our rows
say", and a standings page is asked "what are the standings" — a question
only the league can answer, because a half-ingested season is a different
number, not a rounded one.

Two keyless feeds cover all five sports, both already trusted elsewhere in
this repo:

  * **MLB** — statsapi.mlb.com, the same host the scores, lineups and
    probables come from. Team identity resolves through the id map that
    module already keeps, so there is no second table to rot.
  * **NFL / CFB / NBA / WNBA** — ESPN's v2 standings endpoint, the same
    site API behind the injury board and the live scores.

Both parsers are PURE and read by key name, dropping rather than guessing:
a row with no team or no win/loss pair is not a row. Neither host is
reachable from the sandbox this was written in (403 at the proxy, like
every other feed here), so shape comes from fixtures and
`python3 launch.py --standings` is where it meets the real thing.

What we deliberately do NOT take from the feed is the GROUPING or the
ORDER. Divisions come from `engine.divisions` and the sort from
`engine.standings`, so the page cannot disagree with itself about which
division a team is in, and one feed changing its envelope cannot silently
reorganize the league.
"""

from __future__ import annotations

import re

from .fetch import DEFAULT_AGENT, DataUnavailable, fetch_json

#: Standings move when games end, not by the second.
STANDINGS_TTL = 900

ESPN_PATHS = {
    "nfl": "football/nfl",
    "cfb": "football/college-football",
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
}

MLB_URL = ("https://statsapi.mlb.com/api/v1/standings"
           "?leagueId=103,104&season={season}&standingsTypes=regularSeason")


def _num(v, default=None):
    """A number from whatever the envelope put there, or the default."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _streak_from_code(code: str) -> int:
    """``"W3"`` -> 3, ``"L2"`` -> -2, anything else -> 0."""
    m = re.match(r"\s*([WL])\s*(\d+)\s*$", str(code or ""), re.I)
    if not m:
        return 0
    n = int(m.group(2))
    return n if m.group(1).upper() == "W" else -n


def _wl(text) -> tuple[int, int]:
    """``"6-4"`` / ``"6-4-1"`` -> (6, 4). Blank or odd -> (0, 0)."""
    parts = re.findall(r"\d+", str(text or ""))
    if len(parts) < 2:
        return (0, 0)
    return (int(parts[0]), int(parts[1]))


def parse_mlb(payload) -> list[dict]:
    """statsapi standings envelope -> flat rows, one per club.

    Identity comes from the numeric team id through the map the MLB source
    already keeps; a club we cannot name is dropped rather than guessed
    into somebody else's division.
    """
    from ..mlb.sources.mlbstats import TEAM_ID_ABBR

    rows = []
    for rec in ((payload or {}).get("records") or []):
        if not isinstance(rec, dict):
            continue
        for tr in (rec.get("teamRecords") or []):
            if not isinstance(tr, dict):
                continue
            team = tr.get("team") or {}
            abbr = (TEAM_ID_ABBR.get(team.get("id"))
                    or team.get("abbreviation") or "")
            wins, losses = _num(tr.get("wins")), _num(tr.get("losses"))
            if not abbr or wins is None or losses is None:
                continue
            home_w, home_l = _wl((tr.get("records") or {}).get("homeRecord"))
            away_w, away_l = _wl((tr.get("records") or {}).get("awayRecord"))
            # Splits also arrive as a list of named records on some
            # responses; the flat keys above win when both are present.
            last10 = ""
            for split in (((tr.get("records") or {}).get("splitRecords")) or []):
                kind = (split.get("type") or "").lower()
                if kind == "home" and not (home_w or home_l):
                    home_w, home_l = int(_num(split.get("wins"), 0)), \
                        int(_num(split.get("losses"), 0))
                elif kind == "away" and not (away_w or away_l):
                    away_w, away_l = int(_num(split.get("wins"), 0)), \
                        int(_num(split.get("losses"), 0))
                elif kind in ("lastten", "last_ten"):
                    last10 = (f"{int(_num(split.get('wins'), 0))}-"
                              f"{int(_num(split.get('losses'), 0))}")
            rows.append({
                "team": abbr,
                "wins": int(wins), "losses": int(losses), "ties": 0,
                "points_for": _num(tr.get("runsScored"), 0.0),
                "points_against": _num(tr.get("runsAllowed"), 0.0),
                "streak": _streak_from_code(
                    (tr.get("streak") or {}).get("streakCode")),
                "home_wins": home_w, "home_losses": home_l,
                "away_wins": away_w, "away_losses": away_l,
                # Only when the league publishes it — never derived.
                "last10": last10,
            })
    return rows


def _espn_entries(node, out):
    """Every standings entry anywhere in ESPN's tree.

    The envelope nests conferences inside the league and divisions inside
    conferences, and which levels exist differs by sport and by season.
    Walking for `standings.entries` reads them all without encoding a
    depth that changes.
    """
    if isinstance(node, dict):
        st = node.get("standings")
        if isinstance(st, dict):
            for e in (st.get("entries") or []):
                if isinstance(e, dict):
                    out.append(e)
        for key in ("children", "groups"):
            for child in (node.get(key) or []):
                _espn_entries(child, out)
    elif isinstance(node, list):
        for child in node:
            _espn_entries(child, out)
    return out


def parse_espn(payload) -> list[dict]:
    """ESPN v2 standings envelope -> flat rows, one per team."""
    rows = []
    for e in _espn_entries(payload, []):
        team = e.get("team") or {}
        abbr = (team.get("abbreviation") or team.get("displayName")
                or team.get("name") or "")
        stats = {}
        for s in (e.get("stats") or []):
            if isinstance(s, dict) and s.get("name"):
                stats[s["name"]] = s
        val = lambda k, d=None: _num((stats.get(k) or {}).get("value"), d)  # noqa: E731
        disp = lambda k: (stats.get(k) or {}).get("displayValue")           # noqa: E731
        wins, losses = val("wins"), val("losses")
        if not abbr or wins is None or losses is None:
            continue
        home_w, home_l = _wl(disp("Home") or disp("home"))
        away_w, away_l = _wl(disp("Road") or disp("road") or disp("away"))
        rows.append({
            "team": abbr,
            "wins": int(wins), "losses": int(losses),
            "ties": int(val("ties", 0) or 0),
            "points_for": val("pointsFor", 0.0) or 0.0,
            "points_against": val("pointsAgainst", 0.0) or 0.0,
            # ESPN signs the streak already: negative is a losing run.
            "streak": int(val("streak", 0) or 0),
            "home_wins": home_w, "home_losses": home_l,
            "away_wins": away_w, "away_losses": away_l,
            "last10": (disp("Last Ten Games") or disp("lastTen")
                       or disp("vs. Last 10") or ""),
        })
    return rows


def fetch(sport: str, season: int) -> list[dict]:
    """Live standings rows for one sport, or raise DataUnavailable."""
    if sport == "mlb":
        url = MLB_URL.format(season=season)
        return parse_mlb(fetch_json(url, f"standings_mlb_{season}.json",
                                    ttl=STANDINGS_TTL,
                                    user_agent=DEFAULT_AGENT))
    path = ESPN_PATHS.get(sport)
    if not path:
        raise DataUnavailable(f"no standings feed wired for {sport}")
    # THE REGULAR SEASON, SAID OUT LOUD. Without a season type ESPN
    # answers with whatever is current, and five days before Week 1 that
    # was the PRESEASON table: 49 exhibition games counted, Buffalo
    # "ranked" first on offense at 29.3 a game from August (Ethan's box,
    # 2026-09-05). `seasontype=2` is the same parameter family
    # `nflpreseason` reads the preseason scoreboard with (type 1), and
    # the cache name carries it so a cached preseason table is never
    # served as the regular one.
    url = (f"https://site.api.espn.com/apis/v2/sports/{path}/standings"
           f"?season={season}&seasontype=2")
    return parse_espn(fetch_json(url, f"standings_{sport}_{season}_t2.json",
                                 ttl=STANDINGS_TTL,
                                 user_agent=DEFAULT_AGENT))
