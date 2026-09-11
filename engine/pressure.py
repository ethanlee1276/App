"""Under pressure — how a team behaves when the game is close or the
market expected something of it.

Ethan, 2026-09-05: "Add under pressure data for teams, like clutch win %
and reliability % and comeback % and choke % and see if we can have that
as live data as well like when games are going."

Four rates per team, all counted from the finished games in the history
table — the same rows the standings are counted from, so the two pages
cannot disagree about a record — and every one defined by what we
actually hold, which is a final score and (for football) a closing
spread or moneyline:

  clutch       one-score games won ÷ one-score games played. A
               one-score game is one decided by at most ONE_SCORE
               points for the sport: eight in football (a touchdown and
               a two-point try), five in basketball, one run in
               baseball. A tie is a one-score game that was not won.
  reliability  games won as the favourite ÷ games played as the
               favourite. The favourite is the closing spread's side,
               or the shorter moneyline when the row has no spread.
  comeback     games won as the underdog ÷ games played as the
               underdog. Said plainly on the page: this is coming back
               from where the MARKET had the team, not from a deficit
               on the scoreboard. We do not store half-time or
               quarter scores, so "trailed at the half and won" is a
               claim this module cannot make yet; the play-by-play
               files carry running scores and a recorder for them is
               the next step, not this one.
  choke        one-score games LOST as the favourite ÷ games played as
               the favourite. The favourite had it within reach and let
               it go.

Percentages are 0–100 with one decimal. A team needs MIN_GAMES finished
games before its rate is ranked, and a season with fewer than four such
teams (Week 1 through Week 3 in the NFL, every year) falls back to the
season before — `season_used` says which one the numbers are from, and
the page prints it. A sport whose rows carry no closing line (baseball
and basketball as ingested today) keeps its clutch rate and says why the
other three are missing rather than showing 0% chokers.

Regular season only, like the standings: a playoff loss is not the same
kind of fact as a September one, and the bracket page owns those rows.
"""

from __future__ import annotations

import json

from . import divisions
from .ingest import ESPN_KEY_PREFIX
from .playoffs import is_postseason

#: The margin, inclusive, that makes a game "one-score" for the sport.
ONE_SCORE = {"nfl": 8, "cfb": 8, "nba": 5, "wnba": 5, "mlb": 1}

#: Finished games a team needs before its rates are ranked.
MIN_GAMES = 4

#: Teams that must clear MIN_GAMES for a season to count as measurable;
#: below this the season before is used instead.
MIN_TEAMS = 4

#: Games of the rate's OWN kind (one-score games for clutch, games as the
#: favourite for reliability and choke, as the underdog for comeback) a
#: team needs before that rate is ranked. Without this the comeback
#: column led with 100% on two games and choke with 100% on one — a
#: ranking of who happened to be an underdog least often.
MIN_RATE_N = 3

#: The rates, in the order the page ranks them, with the direction a
#: rank runs: high-first for the three virtues, high-first for choke too
#: — a column called "Choke" reads worst-first or it reads wrong.
RATES = ("clutch", "reliability", "comeback", "choke")

_EMPTY = {"games": 0, "wins": 0, "ties": 0,
          "one_score_games": 0, "one_score_wins": 0,
          "fav_games": 0, "fav_wins": 0, "fav_one_score_losses": 0,
          "dog_games": 0, "dog_wins": 0}


def favourite(spread, extra) -> str | None:
    """Which side the market favoured: "home", "away", or None.

    The games table stores the spread from the home side — negative
    means the home team was favoured (checked against four NFL and four
    college seasons: favourites so defined won 581 of 863 and 1,464 of
    1,952). A row with no spread falls back to the moneylines in
    `extra`, ``[home, away]`` in American odds, where the shorter price
    is the favourite. Equal prices, a pick'em, and no lines at all are
    all "nobody was favoured".
    """
    if spread is not None:
        try:
            s = float(spread)
        except (TypeError, ValueError):
            s = 0.0
        if s < 0:
            return "home"
        if s > 0:
            return "away"
        return None
    try:
        ml = (json.loads(extra) if isinstance(extra, str) else extra or {}).get("ml")
        home_ml, away_ml = float(ml[0]), float(ml[1])
    except (TypeError, ValueError, IndexError, KeyError, AttributeError):
        return None
    if home_ml == away_ml:
        return None
    return "home" if home_ml < away_ml else "away"


def _rows(conn, sport: str, season: int) -> list:
    return conn.execute(
        "SELECT period, home, away, home_score, away_score, spread, extra "
        "FROM games WHERE sport=? AND season=? AND home_score IS NOT NULL "
        "AND away_score IS NOT NULL ORDER BY period",
        (sport, season)).fetchall()


def _pct(num: int, den: int):
    return round(100.0 * num / den, 1) if den else None


def count(rows, sport: str, season: int, id_to_abbr: dict | None = None
          ) -> tuple[dict, bool]:
    """Per-team counters from finished rows → ``({team: counters}, lined)``.

    ``lined`` says whether ANY row carried a favourite; without one the
    three market-based rates have no denominator for anybody.
    """
    limit = ONE_SCORE.get(sport, 0)
    mapping = {str(k): str(v) for k, v in (id_to_abbr or {}).items()}
    teams: dict[str, dict] = {}
    lined = False

    def key(name: str) -> str:
        raw = str(name or "")
        if raw.startswith(ESPN_KEY_PREFIX):
            raw = mapping.get(raw[len(ESPN_KEY_PREFIX):], raw)
        return divisions.canonical(sport, raw)

    for r in rows:
        period, home, away, hs, as_, spread, extra = r[:7]
        if is_postseason(sport, season, period):
            continue
        hs, as_ = float(hs), float(as_)
        margin = abs(hs - as_)
        one_score = margin <= limit
        fav = favourite(spread, extra)
        lined = lined or fav is not None
        for side, name, mine, theirs in (("home", home, hs, as_),
                                         ("away", away, as_, hs)):
            t = teams.setdefault(key(name), dict(_EMPTY))
            won = mine > theirs
            t["games"] += 1
            t["wins"] += won
            t["ties"] += (mine == theirs)
            if one_score:
                t["one_score_games"] += 1
                t["one_score_wins"] += won
            if fav == side:
                t["fav_games"] += 1
                t["fav_wins"] += won
                if one_score and not won:
                    t["fav_one_score_losses"] += 1
            elif fav is not None:
                t["dog_games"] += 1
                t["dog_wins"] += won
    return teams, lined


def rates(t: dict) -> dict:
    """The four percentages for one team's counters (None = no basis)."""
    return {
        "clutch": _pct(t["one_score_wins"], t["one_score_games"]),
        "reliability": _pct(t["fav_wins"], t["fav_games"]),
        "comeback": _pct(t["dog_wins"], t["dog_games"]),
        "choke": _pct(t["fav_one_score_losses"], t["fav_games"]),
    }


def _measurable(teams: dict) -> int:
    return sum(1 for t in teams.values() if t["games"] >= MIN_GAMES)


def team_pressure(conn, sport: str, season: int,
                  id_to_abbr: dict | None = None) -> dict | None:
    """The under-pressure table for one sport, or None with nothing to say.

    Tries ``season``; when fewer than MIN_TEAMS teams have MIN_GAMES
    finished games it tries the season before and says so in
    ``season_used``. ``id_to_abbr`` rewrites college rows still keyed
    ``espn:<id>`` (see `ingest.remap_cfb_team_keys`); left None it
    reads the map a previous build persisted.
    """
    if sport not in ONE_SCORE:
        return None
    if id_to_abbr is None and sport == "cfb":
        from . import cfbteams
        id_to_abbr = cfbteams.load_ids() or None
    used, teams, lined = season, {}, False
    for candidate in (season, season - 1):
        teams, lined = count(_rows(conn, sport, candidate), sport, candidate,
                             id_to_abbr)
        used = candidate
        if _measurable(teams) >= MIN_TEAMS:
            break
    else:
        return None

    out_teams = {}
    for name, t in teams.items():
        out_teams[name] = {**t, **rates(t), "record": _record(t)}
    ranked = {}
    for rate in RATES:
        n_key = {"clutch": "one_score_games", "reliability": "fav_games",
                 "comeback": "dog_games", "choke": "fav_games"}[rate]
        pool = [(name, t) for name, t in out_teams.items()
                if t["games"] >= MIN_GAMES and t[rate] is not None
                and t[n_key] >= MIN_RATE_N]
        pool.sort(key=lambda nt: (-nt[1][rate], -nt[1][n_key], nt[0]))
        ranked[rate] = [{"rank": i + 1, "team": name, "value": t[rate],
                         "n": t[n_key], "record": t["record"]}
                        for i, (name, t) in enumerate(pool)]
    note = ""
    if not lined:
        note = (f"No closing lines on file for {sport.upper()} games, so "
                "reliability, comeback and choke — which need a favourite — "
                "are not shown. Clutch needs only the final score.")
    return {
        "sport": sport,
        "season": season,
        "season_used": used,
        "one_score": ONE_SCORE[sport],
        "min_games": MIN_GAMES,
        "min_rate_n": MIN_RATE_N,
        "lined": lined,
        "teams": out_teams,
        "ranked": ranked,
        "note": note,
    }


def _record(t: dict) -> str:
    losses = t["games"] - t["wins"] - t["ties"]
    return (f"{t['wins']}-{losses}-{t['ties']}" if t["ties"]
            else f"{t['wins']}-{losses}")
