"""The preseason schedule, which nflverse does not have.

    from engine.sources.nflpreseason import preseason_games
    games = preseason_games(2026)

WHY A SECOND SCHEDULE SOURCE
----------------------------
The whole NFL board reads `nfldata/games.csv`, and that file contains no
preseason at all. Measured on the cached copy: 7,548 games whose
`game_type` values are REG, WC, DIV, CON and SB, and nothing else. So
`build_games(2026, 1)` cannot show an August fixture however it is asked.

ESPN's public scoreboard does carry it, under `seasontype=1`, and this repo
already parses that payload shape for live scores. This module reuses the
same reading and the same abbreviation map, so a team is spelled one way
across the site.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH
---------------------------------------------------
site.api.espn.com is refused by the environment's network policy (the
gateway answers 403 to CONNECT), so the parser below was written from the
payload shape `livescores.parse_espn_scoreboard` already handles rather
than from a response anyone here has seen.

Two consequences are designed in rather than hoped away:

* **The raw payload is cached before it is parsed.** If the parse is
  wrong, the data is already on disk and the fix costs no second fetch.
* **A shape it does not recognise raises rather than returning nothing.**
  An empty list would read as "no preseason scheduled", which is a
  perfectly ordinary thing for August to mean, and would hide a broken
  parser until someone wondered where the games went.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
It does not price anything. Preseason is the one part of the calendar
where this engine's central premise fails: projections are volume times
efficiency measured over prior games, and in August starters play a series
and a half behind a line that will not start together again. A prop priced
off last season's usage is not a slightly worse number, it is a number
about a different event.

Schedules, scores and results are useful; props are not, and the two are
separated here so that showing the first never quietly enables the second.
"""

from __future__ import annotations

import datetime as _dt
import json

from .fetch import CACHE_DIR, DEFAULT_AGENT, DataUnavailable, fetch_text
from .livescores import ESPN_NFL, _abbr

#: ESPN's season types. 1 is preseason, 2 regular, 3 postseason.
PRESEASON, REGULAR, POSTSEASON = 1, 2, 3

#: How long a cached scoreboard stays fresh. Schedules barely move, and a
#: preseason fixture list is settled weeks ahead; scores are what change,
#: and `livescores` owns those on its own 30-second clock.
SCHEDULE_TTL = 6 * 3600


def _url(season: int, seasontype: int, week: int | None) -> str:
    """No `limit` parameter, and that is the whole bug the first run hit.

    Probed from Ethan's machine 2026-08-08, the difference between a query
    that answers and one that does not was exactly that:

        ?dates=2026&seasontype=1&week=1              1 game
        ?dates=2026&seasontype=1&week=1&limit=400    nothing

    ESPN's scoreboard does not take `limit`, and rather than ignoring it,
    supplying it empties the answer. It was added here on the assumption
    that a season's worth of fixtures would paginate — a guess about an API
    nobody had called, doing damage in the one way a guess like that can.

    THE WEEK IS NOT OPTIONAL EITHER. Dropping it does not widen the query,
    it breaks the season-type filter: `?dates=2026&seasontype=1` returned
    100 games starting 2026-01-03, which is a REGULAR season fixture from
    the 2025 season. Anything that looks like a chance to do one call
    instead of four is that.
    """
    q = f"?dates={season}&seasontype={seasontype}"
    if week is not None:
        q += f"&week={week}"
    return ESPN_NFL + q


def fetch_scoreboard(season: int, seasontype: int = PRESEASON,
                     week: int | None = None) -> dict:
    """The raw ESPN payload, cached to disk before anything reads it."""
    name = f"espn_nfl_{season}_t{seasontype}" + (f"_w{week}" if week else "") + ".json"
    text = fetch_text(_url(season, seasontype, week), name,
                      ttl=SCHEDULE_TTL, user_agent=DEFAULT_AGENT)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise DataUnavailable(
            f"ESPN returned something that is not JSON for {season} "
            f"seasontype {seasontype}; the raw body is cached at "
            f"{CACHE_DIR / name}") from exc


def parse_games(data: dict, season: int) -> list[dict]:
    """Scoreboard payload → one dict per game.

    Raises rather than returning [] on a payload it cannot read: an empty
    list is a legitimate answer for a date with no fixtures, so using it
    for "I did not understand this" would make a broken parser look like a
    quiet August.
    """
    if "events" not in data:
        raise DataUnavailable(
            "ESPN payload has no `events` key — the scoreboard shape has "
            "changed, or this is an error body. Nothing was parsed.")

    out: list[dict] = []
    for ev in data.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        home = away = None
        hs = as_ = None
        for c in comp.get("competitors", []):
            ab = _abbr((c.get("team") or {}).get("abbreviation", ""))
            score = c.get("score")
            score = int(score) if str(score).lstrip("-").isdigit() else None
            if c.get("homeAway") == "home":
                home, hs = ab, score
            else:
                away, as_ = ab, score
        if not home or not away:
            continue
        status = (comp.get("status") or ev.get("status") or {})
        stype = status.get("type") or {}
        venue = comp.get("venue") or {}
        # ESPN sends `score: "0"` for a game nobody has played, not an
        # absent field. Taken at face value that reads as a real 0-0, and
        # since `completed` is also false the only honest label left is
        # "live" — which is how 48 scheduled preseason fixtures came out
        # tagged as in progress on the first real run.
        #
        # `state` is the discriminator: pre / in / post. A genuine 0-0 in
        # the first quarter has state "in", so gating on "pre" costs
        # nothing and stops a placeholder becoming a scoreline.
        state = stype.get("state", "pre")
        if state == "pre":
            hs = as_ = None
        out.append({
            "season": season,
            "season_type": "PRE",
            "week": ((ev.get("week") or {}).get("number")),
            "game_id": str(ev.get("id") or ""),
            "kickoff": ev.get("date", ""),
            "date": (ev.get("date", "") or "")[:10],
            "home": home,
            "away": away,
            "home_score": hs,
            "away_score": as_,
            "completed": bool(stype.get("completed")),
            "state": state,
            "venue": venue.get("fullName", ""),
            "indoor": bool(venue.get("indoor")),
        })
    return out


def _range_url(season: int) -> str:
    """August, as an explicit date range.

    A FALLBACK, not the primary, and the distinction is the point. This is
    a calendar guess: it asks for every NFL game in a window and trusts
    that only preseason falls there. True for 2026 — the regular season
    opens Sep 9 — and false for any year the window is drawn wrongly. The
    week loop asks for preseason BY NAME, which is a filter rather than a
    coincidence, so it stays first.

    Probed 2026-08-08: this returns 49 games, the same total the week loop
    reaches, which is what makes it a usable cross-check.
    """
    return f"{ESPN_NFL}?dates={season}0701-{season}0908"


def _by_date_range(season: int) -> list[dict]:
    name = f"espn_nfl_{season}_range.json"
    text = fetch_text(_range_url(season), name, ttl=SCHEDULE_TTL,
                      user_agent=DEFAULT_AGENT)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise DataUnavailable(f"range query returned non-JSON; see "
                              f"{CACHE_DIR / name}") from exc
    # The range carries whatever is in the window, so anything already
    # played as a REGULAR fixture has to be dropped rather than relabelled.
    return [g for g in parse_games(data, season)
            if (g.get("week") or 0) <= 4]


def preseason_games(season: int, weeks: tuple[int, ...] | None = None) -> list[dict]:
    """Every preseason game ESPN lists for a season, earliest first.

    One call per week, because the season-type filter does not work
    without one — see `_url`. Measured on 2026: week 1 is the Hall of Fame
    game alone, weeks 2-4 are sixteen apiece, and the total of 49 matches
    what an explicit August date range returns. Weeks with no fixtures
    contribute nothing and are not an error.
    """
    seen: dict[str, dict] = {}
    failed: list[str] = []
    empty: list[int] = []
    for wk in (weeks if weeks is not None else (1, 2, 3, 4)):
        try:
            data = fetch_scoreboard(season, PRESEASON, wk)
        except DataUnavailable as exc:
            failed.append(f"week {wk}: {exc}")
            continue
        got = parse_games(data, season)
        if not got:
            empty.append(wk)
        for g in got:
            if g["game_id"]:
                seen[g["game_id"]] = g
    if seen:
        return sorted(seen.values(), key=lambda g: (g["kickoff"], g["home"]))

    # The week loop found nothing. Before blaming the calendar, try the
    # other shape that is known to work — if ESPN changes what `week`
    # means for preseason, this is what keeps the board alive.
    try:
        got = _by_date_range(season)
    except DataUnavailable as exc:
        failed.append(f"date range: {exc}")
    else:
        if got:
            return sorted(got, key=lambda g: (g["kickoff"], g["home"]))
        empty.append(0)

    # Nothing came back — and WHY matters, because the two causes need
    # opposite responses. The first cut of this reported one message for
    # both, which is the same misdirection as a "run the ingest" prompt
    # for a season that has not been played: it sends the reader to wait
    # for a schedule when the calls never landed, or to debug a network
    # that is working fine.
    if failed and not empty:
        raise DataUnavailable(
            f"Every ESPN call for {season} preseason FAILED — no payload was "
            f"received, so nothing can be said about whether a schedule "
            f"exists. This is a fetch problem, not a calendar one.\n  "
            + "\n  ".join(failed))
    raise DataUnavailable(
        f"ESPN answered for preseason week(s) {empty or '?'} of {season} and "
        f"listed no games. The calls worked; the schedule is not in this "
        f"response. Either it is not published yet, or the query shape is "
        f"wrong — the cached payloads under {CACHE_DIR} hold the actual "
        f"answers, and `python3 nflpre.py --raw` says where."
        + (f"\n  {len(failed)} week(s) also failed outright:\n  "
           + "\n  ".join(failed) if failed else ""))


def board_payload(games: list[dict], season: int,
                  today: _dt.date | None = None) -> dict:
    """The fixture list as the website reads it. Facts only — no price.

    Grouped by week because that is how a preseason is talked about, and
    because the weeks are not equal: week 1 is the Hall of Fame game alone
    and the rest are sixteen apiece, so a flat list of 49 reads as noise.

    `show_until` is the last fixture's date, and it is the whole retirement
    mechanism. This board is live for about five weeks a year; a permanent
    home for it would mean a nav tab that says nothing for eleven months,
    or a block someone has to remember to take down. The page compares
    today against this date and stops drawing itself.

    NOTHING HERE IS A PRICE, and that is structural rather than an
    oversight. Preseason is where this engine's premise fails — a
    projection is volume times efficiency over prior games, and in August a
    starter plays a series and a half behind a line that will not start
    together again. Scores and schedules are worth showing; a number
    claiming what a player will do is not, and keeping the two apart is
    what stops the first quietly becoming the second.
    """
    today = today or _dt.date.today()
    span = window(games)
    by_week: dict = {}
    for g in games:
        by_week.setdefault(g.get("week"), []).append(g)
    weeks = []
    for wk in sorted(by_week, key=lambda w: (w is None, w)):
        rows = sorted(by_week[wk], key=lambda g: (g["kickoff"], g["home"]))
        weeks.append({"week": wk, "games": rows})
    done = sum(1 for g in games if g.get("completed"))
    return {
        "season": season,
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "first": span[0] if span else None,
        "last": span[1] if span else None,
        "show_until": span[1] if span else None,
        "days_until": days_until(games, today),
        "total": len(games),
        "complete": done,
        "weeks": weeks,
    }


def window(games: list[dict]) -> tuple[str, str] | None:
    """(first date, last date) across a fixture list, or None if empty."""
    days = sorted(g["date"] for g in games if g.get("date"))
    return (days[0], days[-1]) if days else None


def days_until(games: list[dict], today: _dt.date | None = None) -> int | None:
    """Days to the first fixture; negative once it has started."""
    w = window(games)
    if not w:
        return None
    try:
        first = _dt.date.fromisoformat(w[0])
    except ValueError:
        return None
    return (first - (today or _dt.date.today())).days
