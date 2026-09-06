"""College football results from the sportsdataverse mirror.

    https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/
        main/schedules/csv/cfb_schedules_<season>.csv

WHY THIS EXISTS ALONGSIDE `cfbdata`. `engine.sources.cfbdata` reads
ESPN's live scoreboard, which is the right feed for a board being built
tonight and the wrong one for history: it answers "what is on today",
one day at a time, and a standard egress policy blocks it outright.
Everything the CFB model's own calibration needs is a season of finished
scores, and that arrives here in one file over the same
raw.githubusercontent.com path the NFL schedules already use.

THE GAP THIS CLOSES, measured 2026-08-27. `engine.cfb.ratings` fits
college football's scoring baseline, home field and margin/total spread
from finished games, and falls back to a prior when there are fewer than
`MIN_GAMES`. The database held ONE completed CFB game. So the entire CFB
board was running on the prior — which the module is honest about, and
which puts every college game on probation: journaled and graded, never
staked. Four seasons on this feed are 3,132 FBS-vs-FBS games.

FBS PLAYS FBS, AND NOTHING ELSE. The file carries all four divisions,
about 3,800 rows a season, and the board prices FBS only. Including the
cupcake games — an FBS side hosting an FCS opponent, 121 of them in
2024 — would drag the scoring baseline up and the margin spread wide
with games nobody can bet, and those are exactly the two constants the
stake depends on. So both sides must be FBS.

TEAMS ARE KEYED BY ESPN'S NUMERIC ID, NOT BY NAME. The file's
``home_id``/``away_id`` are ESPN team ids (Georgia is 61, Ohio State
194), the same ids `cfbdata.parse_teams` returns beside each
abbreviation. A numeric join needs no name-matching table, survives a
school rebranding, and does not rot — which is the standing objection to
writing 134 schools into this repo. Pass `id_to_abbr` from a build that
has the teams feed and the rows land keyed the way the board keys them;
without one they land under ``espn:<id>``, a form no real abbreviation
can collide with, so the two namings stay visibly distinct instead of
silently splitting a team in half.

Every constant the fit produces is invariant to that choice — a
scoring baseline, a home-field edge and a residual spread do not depend
on what the teams are called, only on each team mapping to exactly one
key. The naming matters for the per-team ratings the live board draws,
and for nothing else.

Standard library only.
"""

from __future__ import annotations

from .fetch import fetch_csv, load_local_csv, DataUnavailable

SCHEDULE_URL = ("https://raw.githubusercontent.com/sportsdataverse/"
                "cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv")

#: The division string the feed uses for Division I-A.
FBS = "fbs"

#: The values this feed uses for "no value". ``NA`` is R's, and it
#: arrives as the literal two characters — read as a number it would be
#: a crash, read as a name it would be a team called NA.
BLANK = ("", "NA", "NULL", "None", "nan")


def _blank(value) -> bool:
    return str(value).strip() in BLANK


def _num(value):
    """A float, or None when the feed left the cell empty."""
    if _blank(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _flag(value) -> bool:
    return str(value).strip().upper() in ("TRUE", "T", "1", "YES")


def _date(start_date: str) -> str:
    """``YYYY-MM-DD`` from the feed's ISO instant.

    Deliberately a plain slice of the UTC stamp rather than a conversion.
    A Saturday night kickoff is Sunday in UTC, so this puts a handful of
    games on the following day — which is wrong for a board and
    irrelevant here: nothing in the calibration reads the date except to
    order the season and key the row. `engine.sources.cfbdata` does the
    Eastern conversion properly, because there it decides whether a game
    is a marquee night window or a weeknight, and getting it wrong would
    hand the most-watched game of the week a low-attention haircut.
    """
    return str(start_date or "").strip()[:10]


def team_key(espn_id, id_to_abbr: dict | None) -> str | None:
    """The games-table key for one team, or None if it must be skipped."""
    ident = str(espn_id or "").strip()
    if _blank(ident):
        return None
    if id_to_abbr:
        abbr = id_to_abbr.get(ident)
        return str(abbr).strip() or None if abbr else None
    return f"espn:{ident}"


def parse_schedule(rows: list[dict], season: int,
                   id_to_abbr: dict | None = None) -> dict:
    """Finished FBS-vs-FBS games as ``engine.db.upsert_games`` rows.

    Returns ``{"games": [...], "skipped": {reason: n}}``. The skip counts
    are returned rather than logged because "the backfill ingested 640 of
    798" is a finding, and a number that only ever appeared on a terminal
    somebody had already closed is how the last dead loop on this site
    stayed dead.
    """
    games: list[dict] = []
    skipped: dict[str, int] = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for r in rows or []:
        # ONE FBS SIDE IS ENOUGH TO STORE THE RESULT. Both sides were
        # required until 2026-09-06, which is right for the FIT and wrong
        # for the LEDGER: the board prices every game an FBS team plays,
        # including the September buy games, and a bet on one of those had
        # no result row to grade against — ever. Ethan's --why-open that
        # day was full of them (UAPB@MIZ, BCU@UCF, EIU@MINN, MASS@RUTG).
        #
        # The fit is protected by the KEY, not by this filter: an FCS side
        # has no FBS abbreviation and lands as `espn:<id>`, which is
        # exactly the marker `teamrates.compute_team_ratings` already
        # excludes on (its docstring names the 70-0 buy game that was an
        # FBS team's whole rating for a fortnight) and which
        # `cfb.ratings.fit_from_history` now excludes on too. A game
        # neither side of which is FBS is still nothing we price.
        divisions = [(r.get(f"{s_}_division") or "").strip().lower()
                     for s_ in ("home", "away")]
        if FBS not in divisions:
            skip("no FBS side")
            continue
        hs, as_ = _num(r.get("home_points")), _num(r.get("away_points"))
        if hs is None or as_ is None:
            # Not played, or played and not yet scored. Either way it is
            # not evidence.
            skip("no final score")
            continue
        # An id the FBS map does not carry keys as `espn:<id>` rather
        # than dropping the game — that is the fallback `team_key`
        # already uses with no map at all, and the form every fit
        # excludes. It is how an FCS opponent gets stored at all, and it
        # also stops one unmapped FBS school taking a real game with it.
        home = team_key(r.get("home_id"), id_to_abbr) or team_key(r.get("home_id"), None)
        away = team_key(r.get("away_id"), id_to_abbr) or team_key(r.get("away_id"), None)
        if not home or not away:
            skip("no team id")
            continue
        if home == away:
            skip("both sides resolved to one team")
            continue
        date = _date(r.get("start_date"))
        if len(date) != 10:
            skip("no usable date")
            continue
        if _blank(str(r.get("game_id") or "")):
            skip("no game id")
            continue
        # THE KEY EVERY OTHER SPORT USES, and the reason a college total
        # could never settle. This wrote the mirror's own numeric id
        # ("401405059") while the NFL and MLB ingests both write
        # `f"{away}@{home}"` — and a total bet stores that matchup key in
        # its `player` column, which is what `ledger._game_bet_evidence`
        # looks the game up by. Three thousand college rows, not one of
        # them joinable: every college total sat open for ever, in a
        # bucket the doctor reported as "no stat line" (2026-09-06).
        # `ingest.remap_cfb_game_ids` rewrites the rows already stored.
        game_id = f"{away}@{home}"
        games.append({
            "sport": "cfb",
            "season": int(season),
            "period": date,
            "game_id": game_id,
            "home": home,
            "away": away,
            "home_score": hs,
            "away_score": as_,
            # NO SPREAD AND NO TOTAL, AND THAT IS THE POINT. This feed
            # carries scores and Elo, not betting lines — so unlike the
            # NFL backfill there is no closing number here to grade the
            # model against, and `engine.gamecal` will keep holding CFB
            # rather than fitting a market haircut it cannot measure.
            # Writing a 0.0 spread would be a fake number that reads as
            # a pick'em on 3,132 games.
            "spread": None,
            "total": None,
            "roof": None,
            "surface": None,
            "temp": None,
            "wind": None,
            "extra": _extra(r),
        })
    return {"games": games, "skipped": skipped}


def _extra(r: dict) -> str | None:
    """Neutral site and the school names, as JSON — or None.

    `engine.cfb.ratings` reads ``neutral`` out of this to hold the
    home-field fit out of bowl games and neutral-site openers, which
    have no home team to measure an edge for. The names ride along so a
    later pass can resolve an ``espn:`` key to an abbreviation without
    re-fetching the season.
    """
    import json as _json
    out = {}
    if _flag(r.get("neutral_site")):
        out["neutral"] = True
    for side in ("home", "away"):
        name = str(r.get(f"{side}_team") or "").strip()
        if name and not _blank(name):
            out[f"{side}_name"] = name
    # THE MIRROR'S OWN NUMERIC ID, kept because the row is no longer
    # STORED under it. `parse_schedule` rewrites `game_id` to away@home
    # so the ledger can join college totals like every other sport
    # (ab20781) — and every OTHER file on this mirror still keys by the
    # numeric id: player_stats_{season}.csv carries 401628319, the
    # closing-line file the same. Dropping it here is what left
    # `cfbstats.parse_player_stats` and `cfblines.parse_lines` looking up
    # 'espn:52@espn:59' in a table keyed 401628319 and joining zero rows.
    # Carried, not re-derived: only this parser still sees both.
    espn_id = str(r.get("game_id") or "").strip()
    if espn_id and not _blank(espn_id):
        out["espn_game_id"] = espn_id
    return _json.dumps(out, separators=(",", ":")) if out else None


def fetch_season(season: int, ttl: int = 86400 * 7,
                 id_to_abbr: dict | None = None) -> dict:
    """One season's finished FBS games, straight off the mirror."""
    rows = fetch_csv(SCHEDULE_URL.format(season=int(season)),
                     f"cfb_schedules_{int(season)}.csv", ttl=ttl)
    return parse_schedule(rows, season, id_to_abbr)


def load_season(path, season: int, id_to_abbr: dict | None = None) -> dict:
    """The same, from a CSV already on disk — for an offline backfill."""
    return parse_schedule(load_local_csv(path), season, id_to_abbr)


__all__ = ["SCHEDULE_URL", "DataUnavailable", "fetch_season", "load_season",
           "parse_schedule", "team_key"]
