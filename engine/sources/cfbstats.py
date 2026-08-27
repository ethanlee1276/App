"""College football PLAYER production, play by play, from the mirror.

    https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/
        main/player_stats/csv/player_stats_<season>.csv
    https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/
        main/rosters/csv/cfb_rosters_<season>.csv

WHY THIS EXISTS. `engine.cfb.tds` builds the college anytime-touchdown
board, and its first rule is that a quoted player with no ingested usage
gets no pick — "a price with no opportunity evidence behind it is a
lottery ticket". The only feed that had ever fed it was ESPN's per-game
summary (`cfbdata.ingest_player_logs`), one HTTP request per game and
blocked outright by a standard egress policy. Measured 2026-08-27 the
database held TEN CFB player rows against 3,132 ingested games — so the
college TD board could not price anybody and would have shipped EMPTY on
the first Saturday of the season. This file is 197,904 rows for 2024 and
arrives in one request over the same raw.githubusercontent.com path the
schedules already use.

IT IS PLAY-LEVEL, NOT A BOX SCORE, AND THAT IS THE UPGRADE. Every row
carries ``yards_to_goal``, so college finally gets the signals that
carry the NFL touchdown model and that `engine.cfb.tds` says in its own
docstring it does not have: red-zone carries, inside-the-five carries
and red-zone receiving, on the same inside-20 / inside-5 cuts
`engine.sources.nflpbp` buckets (``rz_car`` / ``i5_car``). Until now the
college model inferred a scoring role from share of team YARDAGE — a
proxy it caps hard precisely because it overstates concentration.

THE PASSER AND THE RECEIVER ARE NOT RELIABLY IN THEIR OWN COLUMNS. This
is the load-bearing quirk of the feed, and reading it naively poisons
exactly the market this ingest exists to serve. On most plays
``completion_player`` is the quarterback and ``reception_player`` is the
receiver. On 898 of 53,472 completions in 2024 — 1.7%, and heavily
concentrated on touchdowns — the two arrive the other way round.
``touchdown_player`` does not settle it either: on a scoring pass it
sometimes names the passer and sometimes the receiver, and it is
inconsistent WITHIN a single team's season. Alabama's 2024 file names
Jalen Milroe, the quarterback, on 16 of 17 touchdown passes; Miami's
names the receiver on most of theirs.

The first cut of this parser inferred the rule from Alabama alone and
resolved "the scorer is whoever is not ``touchdown_player``" — which
handed Cam Ward 35 receiving touchdowns and would have fitted the
college touchdown model on a season where quarterbacks were the leading
receivers.

WHAT ACTUALLY SETTLES IT is a column that CANNOT be swapped, because it
only ever holds one name. ``incompletion_player``,
``sack_taken_player`` and ``interception_thrown_player`` are quarterback
columns by construction. Counted per team-season they say who throws;
on a completion the passer is whichever of the two names has the higher
count, and the other one caught it. ``touchdown_player`` is then read
for one thing only — whether the play was a touchdown — and never for
who scored it.

Graded against published 2024 lines the reconstruction lands where it
has to: Cam Ward 4,269 yards / 40 passing TDs (published 4,313 / 39),
Travis Hunter 15 receiving TDs (15), Xavier Restrepo 67-1,122-11
(69-1,127-11), Ashton Jeanty 29 rushing TDs (29). Rushing scores need no
rule at all: on all 4,838 rushing touchdowns in the file,
``touchdown_player`` is the ball carrier, and the parser asserts that
agreement rather than assuming it.

THERE ARE NO TARGETS HERE AND THIS FILE WILL NOT INVENT THEM. The NFL
side counts ``targets`` and ``rz_tgt`` off play-by-play that names the
intended receiver on every throw. This feed names him on 6,302 of
30,117 incompletions — 21%. A "targets" column built from what is
visible would have read Travis Hunter's 2024 at 92 against a published
120, and the site would have printed that number beside his name. So
the receiving-volume market here is ``receptions``, which the feed gets
exactly, and the red-zone receiving market is ``rz_rec`` — receptions
inside the twenty, deliberately NOT called ``rz_tgt``, because a name
the NFL model already reads must not arrive holding a different
quantity. The cost is real and is stated where the model uses it: a
red-zone look that falls incomplete is invisible, so ``rz_rec`` favours
the receiver who catches what he is thrown.

TEAMS ARE KEYED THROUGH THE GAMES WE ALREADY HAVE. The feed names
schools ("Western Kentucky"), the board keys them by abbreviation, and
the backfilled schedule keys them ``espn:<id>`` when the teams feed was
unreachable. Rather than carry a third naming, `parse_player_stats`
takes the games it is joining to — game id → both sides' key and both
sides' school name, straight out of what `engine.sources.cfbfastr`
already stored — and resolves each row against THAT GAME. A renamed
school, a duplicated nickname and an FCS opponent all resolve or get
skipped per game, and a player can never land on a team that was not
playing. Games we did not ingest are skipped, which is the same filter
the schedule applies: FBS vs FBS, final score known.

THE ROSTER FILE IS READ FOR THREE THINGS. It maps ESPN athlete id to a
position — college box scores carry none, which is why
`engine.cfb.tds.role_of` reverse-engineers a role from the usage mix. It
also carries the school's own spelling ("Tetairoa McMillan", where the
play file writes "Tetairoa Mcmillan") and the headshot URL, so college
player pages get a face and a correctly-cased name from a file we are
already fetching.

Standard library only.
"""

from __future__ import annotations

import csv
import io

from .fetch import fetch_text, DataUnavailable

STATS_URL = ("https://raw.githubusercontent.com/sportsdataverse/"
             "cfbfastR-data/main/player_stats/csv/player_stats_{season}.csv")

ROSTER_URL = ("https://raw.githubusercontent.com/sportsdataverse/"
              "cfbfastR-data/main/rosters/csv/cfb_rosters_{season}.csv")

#: The values this feed uses for "no value" — R's ``NA`` arrives as two
#: literal characters, and read as a name it is a player called NA.
BLANK = ("", "NA", "NULL", "None", "nan")

#: Columns that can only ever hold a passer, and therefore cannot be
#: swapped with a receiver. These decide who threw it; see the module
#: docstring for what happens to a parser that trusts the two-name
#: columns instead.
QB_COLUMNS = ("incompletion_player", "sack_taken_player",
              "interception_thrown_player")

#: Inside-20 and inside-5, the same cuts `engine.sources.nflpbp` buckets
#: on. Keeping them identical is what lets one touchdown model read both
#: footballs: `engine.touchdowns` and `engine.nflusage` interpret
#: ``rz_car`` as all carries inside the twenty (the inside-fives
#: included) and ``i5_car`` as the subset inside the five.
RED_ZONE = 20.0
INSIDE_5 = 5.0

#: Markets written for every player who touched the ball, zero included.
#: ``anytime_td`` is the outcome the board is graded on: a player-game
#: with no touchdown is the NEGATIVE case, and a walk-forward that only
#: ever sees scorers measures nothing. Everything else is written only
#: when non-zero — a row per market per player per game across a season
#: of college football is millions of rows, and "this receiver had no
#: carries" is not evidence anybody reads.
ALWAYS = ("anytime_td",)

#: Emitted in this order so an ingest log reads the way a box score does.
MARKETS = ("anytime_td", "carries", "rush_yds", "receptions", "rec_yds",
           "pass_yds", "rush_td", "rec_td", "pass_td",
           "rz_car", "rz_rec", "i5_car")

#: A touchdown and the kick after it. The unit the coverage audit below
#: converts credited touchdowns into points with.
TD_POINTS = 7.0

#: THE COVERAGE AUDIT, AND WHY A FEED THAT PARSES CLEANLY STILL CANNOT BE
#: TRUSTED. Weeks 10 through 16 of the 2025 file are missing their
#: scoring plays. Not mangled — ABSENT. The rows that survive look
#: perfect: real players, real yardage, real field position, and roughly
#: 1.5 touchdowns a game where every other week in four seasons has six.
#: Ingested as written, every player who scored in the back half of last
#: season is recorded as having scored NOTHING, and a touchdown model
#: fitted on it learns that college football stopped scoring in November.
#:
#: The audit needs no threshold pulled out of the air, because the games
#: table already holds the final scores. Credited offensive touchdowns,
#: valued at seven points, as a share of all points scored that week:
#:
#:     2022   w1-w14  70-83%          w15  57%
#:     2023   w1-w14  77-83%          w15   0%
#:     2024   w1-w16  77-95%
#:     2025   w2-w9   78-82%          w1 52%, w10-w16 30/14/19/14/18/6/0
#:
#: Healthy weeks never drop below 70 and broken ones never reach 60, and
#: the gap between them is not close. Below the floor a week's player
#: rows are DROPPED rather than stored with a false zero — the usage in
#: them is real, but there is no way to keep the carries and discard the
#: outcome when the outcome is what the board is graded on.
MIN_TD_COVERAGE = 0.60

#: An offensive touchdown is worth at least six points, so a game whose
#: credited touchdowns cannot fit inside its own final score is telling
#: us something is wrong on the other side of the ledger. A hard bound,
#: not a tuned one.
MIN_TD_POINTS = 6.0


def _blank(value) -> bool:
    return str(value).strip() in BLANK


def _name(value) -> str:
    return "" if _blank(value) else str(value).strip()


def _num(value, default=0.0) -> float:
    if _blank(value):
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _ytg(value):
    """Yards to the end zone, or None when the feed left it empty.

    None is not 100. A play with no field position must not be counted
    as a carry from midfield in one place and skipped in another — it is
    counted as a carry and excluded from the red-zone cuts, which is
    what "we do not know where this play was" actually means.
    """
    if _blank(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def split_pass(scores: dict, completion: str, reception: str) -> tuple:
    """``(passer, receiver)`` for one completed pass.

    ``scores`` is this team's ``{name: quarterback evidence}`` from
    `QB_COLUMNS`. The higher count throws it. Ties fall back to the
    columns as written, which is what they mean 98% of the time — and a
    tie is almost always two players with zero quarterback evidence
    each, i.e. a trick play the feed gives us no way to resolve.
    """
    if scores.get(reception, 0) > scores.get(completion, 0):
        return reception, completion
    return completion, reception


def _slot(bag: dict, key: tuple) -> dict:
    return bag.setdefault(key, {
        "carries": 0.0, "rush_yds": 0.0, "rush_td": 0.0,
        "receptions": 0.0, "rec_yds": 0.0, "rec_td": 0.0,
        "pass_yds": 0.0, "pass_td": 0.0,
        "rz_car": 0.0, "rz_rec": 0.0, "i5_car": 0.0,
    })


def _side_of(game: dict, team_name: str):
    """``(team_key, opponent_key, is_home)`` for one school in one game."""
    if not team_name:
        return None
    if team_name == game.get("home_name"):
        return game.get("home"), game.get("away"), True
    if team_name == game.get("away_name"):
        return game.get("away"), game.get("home"), False
    return None


def parse_player_stats(rows, season: int, games: dict,
                       roster: dict | None = None) -> dict:
    """Per-player-per-game ``player_game_logs`` rows from play rows.

    ``games`` maps game id → ``{"period", "home", "away", "home_name",
    "away_name"}`` — what `engine.sources.cfbfastr` already stored, so
    the join needs no school-name table. ``roster`` maps ESPN athlete id
    → ``{"position", "name", "headshot"}`` from `parse_rosters`; without
    one the rows carry an empty position and the feed's own spelling,
    and `engine.cfb.tds.role_of` infers a role from the usage mix
    exactly as it does today.

    Returns ``{"rows", "assets", "games", "players", "skipped"}``. Skip
    counts are returned, not printed: "the backfill ingested 640 of 798"
    is a finding, and a number that only ever appeared on a terminal
    somebody had already closed is how the last dead loop on this site
    stayed dead.

    One streamed pass. Completions are held back rather than resolved in
    flight, because who threw a pass in week 2 is decided by evidence
    that may not arrive until week 11.
    """
    roster = roster or {}
    bag: dict = {}
    seen_games: set = set()
    ids: dict = {}
    skipped: dict[str, int] = {}
    scores: dict = {}
    pending: list = []
    week_of: dict = {}
    week_points: dict = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for r in rows or []:
        gid = _name(r.get("game_id"))
        game = games.get(gid)
        if not game:
            skip("game not ingested")
            continue
        side = _side_of(game, _name(r.get("team")))
        if not side:
            skip("team not in this game")
            continue
        if gid not in seen_games:
            seen_games.add(gid)
            week = _name(r.get("week"))
            week_of[gid] = week
            week_points[week] = week_points.get(week, 0.0) \
                + _num(game.get("points"))
        team, opponent, home = side
        base = (gid, team, opponent, home)
        by_team = scores.setdefault(team, {})
        for column in QB_COLUMNS:
            qb = _name(r.get(column))
            if qb:
                by_team[qb] = by_team.get(qb, 0) + 1
                ids.setdefault((team, qb),
                               _name(r.get(column.replace("_player",
                                                          "_player_id"))))

        ytg = _ytg(r.get("yards_to_goal"))
        td = _name(r.get("touchdown_player"))

        rush = _name(r.get("rush_player"))
        if rush:
            ids.setdefault((team, rush), _name(r.get("rush_player_id")))
            s = _slot(bag, base + (rush,))
            s["carries"] += 1
            s["rush_yds"] += _num(r.get("rush_yds"))
            # On every rushing touchdown in the file this column IS the
            # ball carrier. Compared rather than assumed: if the feed
            # ever changes, the touchdown lands on nobody instead of on
            # the wrong player.
            if td and td == rush:
                s["rush_td"] += 1
            if ytg is not None and ytg <= RED_ZONE:
                s["rz_car"] += 1
                if ytg <= INSIDE_5:
                    s["i5_car"] += 1

        comp = _name(r.get("completion_player"))
        recv = _name(r.get("reception_player"))
        if comp and recv:
            ids.setdefault((team, comp), _name(r.get("completion_player_id")))
            ids.setdefault((team, recv), _name(r.get("reception_player_id")))
            pending.append((base, comp, recv,
                            _num(r.get("reception_yds"))
                            or _num(r.get("completion_yds")),
                            bool(td), ytg))

    for base, comp, recv, yds, scored, ytg in pending:
        team = base[1]
        passer, receiver = split_pass(scores.get(team, {}), comp, recv)
        s = _slot(bag, base + (receiver,))
        s["receptions"] += 1
        s["rec_yds"] += yds
        if ytg is not None and ytg <= RED_ZONE:
            s["rz_rec"] += 1
        q = _slot(bag, base + (passer,))
        q["pass_yds"] += yds
        if scored and passer != receiver:
            s["rec_td"] += 1
            q["pass_td"] += 1

    for slot in bag.values():
        slot["anytime_td"] = slot["rush_td"] + slot["rec_td"]
    dropped = _failing_weeks(bag, week_of, week_points, games, skipped)

    out, assets = [], {}
    for (gid, team, opponent, home, player), s in bag.items():
        if week_of.get(gid) in dropped:
            continue
        ident = ids.get((team, player), "")
        who = roster.get(ident) or {}
        display = who.get("name") or player
        if ident:
            assets[display] = {"sport": "cfb", "player": display,
                               "espn_id": ident,
                               "headshot": who.get("headshot", ""),
                               "seen": games[gid].get("period") or ""}
        base = {
            "sport": "cfb", "season": int(season),
            "period": games[gid].get("period") or "", "game_id": gid,
            "player": display, "team": team, "opponent": opponent,
            "position": who.get("position", ""), "home": 1 if home else 0,
        }
        for market in MARKETS:
            value = s.get(market, 0.0)
            if value or market in ALWAYS:
                out.append({**base, "market": market, "value": float(value)})
    return {"rows": out, "assets": list(assets.values()),
            "games": len(seen_games), "players": len(bag), "skipped": skipped}


def _failing_weeks(bag: dict, week_of: dict, week_points: dict,
                   games: dict, skipped: dict) -> set:
    """Weeks whose touchdowns the feed did not deliver — see MIN_TD_COVERAGE.

    Two audits, both against numbers we already trust. A WEEK whose
    credited touchdowns account for less than `MIN_TD_COVERAGE` of the
    points actually scored in it has lost its scoring plays. A GAME whose
    credited touchdowns cannot fit inside its own final score at six
    points each has gained some it should not have; its week goes too,
    because whatever produced it was not one game's problem.

    Counts land in ``skipped`` so the ingest reports them: a week
    silently dropped is the same failure as a week silently kept.
    """
    week_tds: dict = {}
    game_tds: dict = {}
    for (gid, _team, _opp, _home, _player), slot in bag.items():
        scored = slot.get("anytime_td", 0.0)
        if not scored:
            continue
        week_tds[week_of.get(gid)] = week_tds.get(week_of.get(gid), 0.0) + scored
        game_tds[gid] = game_tds.get(gid, 0.0) + scored

    failing = set()
    for week, points in week_points.items():
        if points <= 0:
            continue
        if week_tds.get(week, 0.0) * TD_POINTS / points < MIN_TD_COVERAGE:
            failing.add(week)
    for gid, scored in game_tds.items():
        points = _num((games.get(gid) or {}).get("points"))
        if points > 0 and scored * MIN_TD_POINTS > points:
            failing.add(week_of.get(gid))
    for week in sorted(failing, key=lambda w: (len(str(w)), str(w))):
        got = week_tds.get(week, 0.0) * TD_POINTS
        points = week_points.get(week, 0.0) or 1.0
        skipped[f"week {week}: the feed delivered {got / points:.0%} of the "
                f"week's points as touchdowns — scoring plays are missing, "
                f"so the week is dropped rather than stored as zeros"] = 1
    return failing


def parse_rosters(rows) -> dict:
    """``{athlete_id: {"position", "name", "headshot"}}``.

    Position because college box scores carry none; name because the
    play file lower-cases the second capital in "McMillan"; headshot
    because a college player page has had an empty frame where the NFL's
    has a face, and this file was already being fetched for the other
    two.
    """
    out: dict = {}
    for r in rows or []:
        ident = _name(r.get("athlete_id"))
        if not ident:
            continue
        first, last = _name(r.get("first_name")), _name(r.get("last_name"))
        out[ident] = {
            "position": _name(r.get("position")).upper(),
            "name": (first + " " + last).strip(),
            "headshot": _name(r.get("headshot_url")),
        }
    return out


def _stream(url: str, cache_name: str, ttl: int):
    """Rows of a cached CSV, WITHOUT materialising the whole file.

    A season of college plays is 197,904 rows across 70 columns. Built
    into a list of dicts that is roughly a gigabyte, on a droplet with
    one core and not much more than that — so the reader is handed to
    the parser and consumed once.
    """
    return csv.DictReader(io.StringIO(fetch_text(url, cache_name, ttl=ttl)))


def fetch_rosters(season: int, ttl: int = 86400 * 30) -> dict:
    """One season's roster map. A roster does not change after the
    season is over, so the cache is a month deep."""
    return parse_rosters(_stream(ROSTER_URL.format(season=int(season)),
                                 f"cfb_rosters_{int(season)}.csv", ttl))


def fetch_season(season: int, games: dict, ttl: int = 86400 * 7,
                 roster: dict | None = None) -> dict:
    """One season of player production, straight off the mirror."""
    return parse_player_stats(
        _stream(STATS_URL.format(season=int(season)),
                f"cfb_player_stats_{int(season)}.csv", ttl),
        season, games, roster)


def load_season(path, season: int, games: dict,
                roster: dict | None = None) -> dict:
    """The same, from a CSV already on disk — for an offline backfill."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return parse_player_stats(csv.DictReader(fh), season, games, roster)


__all__ = ["STATS_URL", "ROSTER_URL", "RED_ZONE", "INSIDE_5", "MARKETS",
           "QB_COLUMNS", "DataUnavailable", "fetch_season", "fetch_rosters",
           "load_season", "parse_player_stats", "parse_rosters", "split_pass"]
