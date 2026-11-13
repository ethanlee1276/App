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
    # Men's college basketball (2026-11-13): every conference's table, which
    # the page groups by the conference the board's scoreboard carried.
    "cbb": "basketball/mens-college-basketball",
}

#: ESPN NAMES A WINTER SEASON BY THE YEAR IT ENDS; this site names it by the
#: year it starts (`engine.seasons`). The NBA's 2026-27 is ``season=2027``
#: at ESPN, and asking for 2026 handed back 2025-26's FINAL table: the
#: Standings page on 13 November 2026 read Boston 56-26 and Detroit 60-22
#: under "2026", a fortnight into a season nobody had played eighty-two
#: games of. The football leagues and the WNBA play inside one calendar
#: year (football's January is still its start year's season at ESPN too),
#: so only the two basketball winters move. Hockey reads its own league.
ESPN_SEASON_SHIFT = {"nba": 1, "cbb": 1}

#: Leagues whose grouping is the feed's own: college basketball's
#: conferences (`parse_espn` ``groups``). Everyone else is grouped by
#: `engine.divisions`, which the docstring above says why.
GROUPED_BY_FEED = frozenset({"cbb"})

#: Hockey: the league's own feed (the host every NHL score and box score
#: here already comes from), keyed by the same abbreviations our games use.
NHL_URL = "https://api-web.nhle.com/v1/standings/{date}"

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


def _espn_entries(node, out, group: str = ""):
    """Every standings entry anywhere in ESPN's tree.

    The envelope nests conferences inside the league and divisions inside
    conferences, and which levels exist differs by sport and by season.
    Walking for `standings.entries` reads them all without encoding a
    depth that changes. Each entry is paired with the name of the nearest
    group above it that has one (its conference, for college basketball:
    `parse_espn` ``groups=True``)."""
    if isinstance(node, dict):
        here = str(node.get("abbreviation") or node.get("shortName")
                   or node.get("name") or "").strip() or group
        st = node.get("standings")
        if isinstance(st, dict):
            for e in (st.get("entries") or []):
                if isinstance(e, dict):
                    out.append((e, here))
        for key in ("children", "groups"):
            for child in (node.get(key) or []):
                _espn_entries(child, out, here)
    elif isinstance(node, list):
        for child in node:
            _espn_entries(child, out, group)
    return out


def parse_espn(payload, groups: bool = False) -> list[dict]:
    """ESPN v2 standings envelope -> flat rows, one per team.

    ``groups`` adds each row's ``group``: the name of the table ESPN filed
    it under — its conference, which is how college basketball's 365
    schools are grouped (no division table in this repo holds them)."""
    rows = []
    for e, group in _espn_entries(payload, []):
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
        if groups and group:
            rows[-1]["group"] = group
    return rows


def fetch(sport: str, season: int) -> list[dict]:
    """Live standings rows for one sport, or raise DataUnavailable."""
    if sport == "mlb":
        url = MLB_URL.format(season=season)
        return parse_mlb(fetch_json(url, f"standings_mlb_{season}.json",
                                    ttl=STANDINGS_TTL,
                                    user_agent=DEFAULT_AGENT))
    if sport == "nhl":
        # "now" FIRST. The box, 2026-10-03, four days before opening night:
        # the dated table answered with no teams and the page fell back to
        # counting our own (empty) season. "now" is the league's current
        # table — last season's final until a puck drops, which parse_nhl
        # turns into this season's 0-0-0 — and the dated one is the backup.
        #
        # THE SAME USER AGENT AS EVERY OTHER NHL CALL (engine/sources/
        # nhldata: scores, box scores, rosters, all answered on the box).
        # This call alone sent DEFAULT_AGENT — no header, so urllib's
        # "Python-urllib" — and came back with nothing while `curl` on the
        # same box got the whole table. And a failure is RAISED with its
        # reason, never swallowed into an empty list: the build line then
        # says what went wrong instead of "answered with no teams".
        import datetime as _dt
        day = _dt.date.today().isoformat()
        rows: list = []
        errors: list = []
        for when in ("now", day):
            try:
                rows = parse_nhl(fetch_json(NHL_URL.format(date=when), f"standings_nhl_{when}.json",
                                            ttl=STANDINGS_TTL), season)
            except DataUnavailable as exc:
                errors.append(str(exc))
                rows = []
            if rows:
                break
        if not rows and errors:
            raise DataUnavailable("; ".join(errors))
        return rows
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
    # ESPN's label for the season, not ours (`ESPN_SEASON_SHIFT`), and the
    # cache named by it: a file kept under the old name holds the wrong
    # season's table.
    espn_season = season + ESPN_SEASON_SHIFT.get(sport, 0)
    url = (f"https://site.api.espn.com/apis/v2/sports/{path}/standings"
           f"?season={espn_season}&seasontype=2")
    return parse_espn(fetch_json(url, f"standings_{sport}_espn{espn_season}_t2.json",
                                 ttl=STANDINGS_TTL,
                                 user_agent=DEFAULT_AGENT),
                      groups=sport in GROUPED_BY_FEED)


def parse_nhl(payload, season: int | None = None) -> list[dict]:
    """The NHL's standings envelope -> flat rows, one per club.

    Overtime and shootout losses ride in ``ties`` (see
    `engine.standings.OTL_SPORTS`). BEFORE OPENING NIGHT the league answers
    with last season's final table; a row from another season is shown as
    0-0-0 rather than as this year's record, because that is what this
    season's standings are until a puck drops.
    """
    want = f"{season}{season + 1}" if season else ""
    rows = []
    for e in (payload or {}).get("standings") or []:
        if not isinstance(e, dict):
            continue
        abbr = e.get("teamAbbrev")
        abbr = abbr.get("default") if isinstance(abbr, dict) else abbr
        if not abbr:
            continue
        fresh = not want or str(e.get("seasonId") or want) == want
        n = (lambda k: int(_num(e.get(k), 0) or 0)) if fresh else (lambda k: 0)
        code, count = str(e.get("streakCode") or ""), n("streakCount")
        rows.append({
            "team": str(abbr), "wins": n("wins"), "losses": n("losses"), "ties": n("otLosses"),
            "points_for": float(n("goalFor")), "points_against": float(n("goalAgainst")),
            "streak": count if code == "W" else -count if code in ("L", "OT") else 0,
            "home_wins": n("homeWins"), "home_losses": n("homeLosses") + n("homeOtLosses"),
            "away_wins": n("roadWins"), "away_losses": n("roadLosses") + n("roadOtLosses"),
            "last10": (f"{n('l10Wins')}-{n('l10Losses')}-{n('l10OtLosses')}" if fresh else ""),
        })
    return rows
