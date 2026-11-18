"""Standings: the league's own numbers, with our own count as the backup.

The page asks "what are the standings", and only the league can answer
that — so `from_feed` is the primary path and `compute` is the fallback.
Ethan, 2026-08-12: "This is not live or real data at all." He was looking
at MLB clubs carrying TIES (70-69-1, 66-68-4) in a sport that has none,
because a half-ingested season counted differently from the league and
nothing on the page said so.

`compute` still earns its place, and is what runs when a feed is
unreachable:

* **It cannot disagree with the rest of the site.** The team ratings, the
  settlement and the standings all read the same games, so a record on the
  standings page and a record in a matchup card are the same fact.
* **It is honest about partial data.** A season half-ingested shows the
  games it has and says how many, rather than presenting an incomplete
  table as the league's actual standings.
* **It works for every sport at once**, including the ones with no free
  standings feed.

Whichever path ran, the payload says which in `source`, and the page
prints it. A number that came from counting our rows must never wear the
authority of the league's own table.

Ties are handled per sport rather than generically: the NFL plays them and
counts them as half a win, MLB and basketball do not have them at all —
so in those sports an equal-score row is an unfinished or unscored game,
and is skipped rather than recorded as a tie nobody played. The sort is
the *display* order — division leaders and seeds — and it is deliberately
NOT presented as the league's official tiebreaker, which involves
head-to-head, common opponents and conference records that a
half-ingested season cannot reproduce. Saying "our order" is better than
quietly being wrong about theirs.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field, asdict

from . import divisions
from .seasons import season_of

# Points/runs per game are worth showing; the label differs by sport and
# so does what a bettor reads it for.
SCORE_LABEL = {"nfl": "PF/PA", "cfb": "PF/PA",
               "nba": "PPG", "wnba": "PPG", "mlb": "R/RA", "nhl": "GF/GA", "cbb": "PPG"}

#: Leagues that actually play ties. Everywhere else an equal-score row is
#: a game that did not finish (suspended, postponed) or one whose score we
#: never got — counting it as a tie is how baseball ended up with 70-69-1.
TIES_EXIST = {"nfl", "cfb"}

#: Hockey has no ties but an overtime/shootout loss is its own column and
#: worth a point. The league's feed carries it; it rides in ``ties`` so the
#: win percentage below is hockey's points percentage exactly
#: ((2W + OTL) / 2GP = (W + OTL/2) / GP). Our own count (``compute``)
#: cannot tell an overtime loss from a regulation one and stays W-L.
OTL_SPORTS = {"nhl"}


@dataclass
class Record:
    team: str
    conference: str = ""
    division: str = ""
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    home_wins: int = 0
    home_losses: int = 0
    away_wins: int = 0
    away_losses: int = 0
    streak: int = 0                     # + wins, - losses
    #: Hockey's first tiebreaker after points: wins inside sixty minutes.
    #: Counted for a points league only (`_row` drops it elsewhere).
    reg_wins: int = 0
    last10: list = field(default_factory=list)   # newest last, "W"/"L"/"T"
    #: A feed's own last-ten record ("6-4"). Set only when the league
    #: publishes it; the ordered run above is ours and cannot be derived
    #: from a season total, so without either the page shows a dash rather
    #: than the 0-0 an empty list would otherwise render as.
    last10_text: str = ""
    results: list = field(default_factory=list)  # ordered W/L/T

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def pct(self) -> float:
        """Win percentage, counting a tie as half a win (NFL convention)."""
        n = self.games
        return round((self.wins + 0.5 * self.ties) / n, 4) if n else 0.0

    @property
    def diff(self) -> float:
        return round(self.points_for - self.points_against, 1)


#: Leagues whose games table can hold one game more than once: college
#: football's three writers (engine/cfbdedupe, each fixed where it writes; its
#: --apply removes the copies they left). A pair of schools never plays twice
#: in two days, so until it has run, one pair's rows a day or less apart are
#: one game. Live, 18 November 2026: Utah 19-0 and Ohio State 16-7 in
#: November, 1,122 games counted where about 700 were played.
COPIES = ("cfb",)


def _day(period):
    try:
        return _dt.date.fromisoformat(str(period)[:10])
    except (TypeError, ValueError):
        return None


def once(sport: str, rows, name=None) -> list:
    """``rows`` with a game filed more than once counted once, in a COPIES
    league (any other league's rows come back as they are). Each row reads
    by name: period, home, away and, when the query has it, game_id. The copy
    kept is never a provisional box copy ("-box"), then the schedule's
    away@home row, then the earliest (cfbdedupe's choices). ``name`` turns a
    stored team into its canonical code."""
    rows = list(rows)
    if sport not in COPIES:
        return rows
    canon = name or (lambda t: divisions.canonical(sport, t))

    def gid(r):
        try:
            return str(r["game_id"] or "")
        except (IndexError, KeyError):
            return ""
    pairs: dict = {}
    for i, r in enumerate(rows):
        pairs.setdefault(frozenset((canon(r["home"]), canon(r["away"]))), []).append(i)
    keep = set()
    for idx in pairs.values():
        idx.sort(key=lambda i: str(rows[i]["period"] or ""))
        group, start = [], None
        for i in idx + [None]:
            d = _day(rows[i]["period"]) if i is not None else None
            if group and (i is None or d is None or start is None or (d - start).days > 1):
                keep.add(min(group, key=lambda j: (gid(rows[j]).endswith("-box"), "@" not in gid(rows[j]),
                                                   str(rows[j]["period"] or ""))))
                group = []
            if i is None:
                break
            if not group:
                start = d
            group.append(i)
    return _one_side_once([r for i, r in enumerate(rows) if i in keep], canon, gid)


def _one_side_once(rows: list, canon, gid) -> list:
    """…AND ONE GAME FILED UNDER TWO CODES FOR ONE SIDE (2026-11-18).
    Western Michigan at Buffalo on 3 October sat as "WMU@BUF" and
    "WMU@BUFF", the same 20-17: the pair above never met, and Western
    Michigan's page said 9-3 for 8-3 (Air Force sits as "AF" and "AFA",
    Albany as "ALB" and "UALB"). A football team plays once in two days, so
    two finals with the same team on the same side, a day or less apart and
    the same score, are one game; the copy kept is chosen as above. Rows
    without both scores are left as they are."""
    def score(r, k):
        try:
            v = r[k]
        except (IndexError, KeyError):
            return None
        try:
            return None if v is None or v == "" else float(v)
        except (TypeError, ValueError):
            return None

    rank = lambda j: (gid(rows[j]).endswith("-box"), "@" not in gid(rows[j]),   # noqa: E731
                      str(rows[j]["period"] or ""))
    drop: set = set()
    seen: dict = {}
    for i in sorted(range(len(rows)), key=lambda k: str(rows[k]["period"] or "")):
        d = _day(rows[i]["period"])
        hs, aw = score(rows[i], "home_score"), score(rows[i], "away_score")
        if d is None or hs is None or aw is None:
            continue
        for side in ("home", "away"):
            key = (side, canon(rows[i][side]), hs, aw)
            prev = seen.get(key)
            if prev and prev[0] not in drop and i not in drop and (d - prev[1]).days <= 1:
                drop.add(max(prev[0], i, key=rank))
            if i not in drop:
                seen[key] = (i, d)
    return [r for k, r in enumerate(rows) if k not in drop]


def _finished(conn, sport: str, seasons: list[int] | None):
    q = ("SELECT season, period, home, away, home_score, away_score, extra, game_id "
         "FROM games WHERE sport=? AND home_score IS NOT NULL "
         "AND away_score IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    return once(sport, conn.execute(q + " ORDER BY period", args).fetchall())


#: How a hockey game ended (engine/sources/nhldata stores the API's
#: periodDescriptor.periodType as `ended_in`). A loss in either is the
#: NHL's third column — an overtime loss, worth one point — and not a loss.
PAST_REGULATION = ("OT", "SO")
#: The NHL API's game type for a playoff game. Hockey is not in
#: playoffs.POSTSEASON (its first playoff day moves every spring), so the
#: stored type is what keeps a Cup run out of the regular-season table.
NHL_PLAYOFF_TYPE = 3


def _hockey(r) -> tuple[int | None, str]:
    """(game type, how it ended) from a stored hockey row — (None, "")
    when the row carries neither, which counts it as a regulation game."""
    try:
        ex = json.loads(r["extra"] or "{}")
    except (TypeError, ValueError, IndexError, KeyError):
        return None, ""
    if not isinstance(ex, dict):
        return None, ""
    try:
        kind = int(ex.get("type")) if ex.get("type") is not None else None
    except (TypeError, ValueError):
        kind = None
    return kind, str(ex.get("ended_in") or "").upper()


def _regular(conn, sport: str, season: int):
    """The regular season's finished rows, each with whether it went past
    regulation — the one filter the table and every reader of its games
    share. No postseason (playoffs.POSTSEASON's dates or weeks) and no
    hockey playoff game (its stored type)."""
    from .playoffs import is_postseason
    for r in _finished(conn, sport, [season]):
        if is_postseason(sport, season, r["period"]):
            continue
        kind, ended = _hockey(r) if sport in OTL_SPORTS else (None, "")
        if kind == NHL_PLAYOFF_TYPE:
            continue
        yield r, ended in PAST_REGULATION


def season_games(conn, sport: str, season: int) -> list[dict]:
    """The games the table counts, one dict each, names canonical: for a
    reader that needs who beat whom (a head-to-head tiebreaker), not only
    the totals. A row with equal scores in a sport without ties is left
    out, as the table leaves it out."""
    out = []
    for r, past in _regular(conn, sport, season):
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        if hs == as_ and sport not in TIES_EXIST:
            continue
        out.append({"home": divisions.canonical(sport, r["home"]),
                    "away": divisions.canonical(sport, r["away"]),
                    "home_score": hs, "away_score": as_, "past_regulation": past})
    return out


def team_rows(table: dict):
    """Every team row of a standings payload, in table order.

    THE ONE READER OF THE SHAPE `_grouped` WRITES. The season simulation
    read `group["rows"]` from August to November 2026 while this module has
    always written `group["teams"]` — so every league's projection started
    each club at 0-0 and played out only the games left, and nothing
    failed, because an empty table is a valid table. A caller iterates
    this instead of the dict.
    """
    for group in (table or {}).get("groups") or []:
        yield from group.get("teams") or []


def compute(conn, sport: str, season: int | None = None,
            today: str | None = None, conferences: dict | None = None
            ) -> dict:
    """Standings for one season of one sport.

    ``conferences`` is an optional ``{team: conference}`` override, which
    is how college football gets its groups — 134 programs realigning
    every summer is not a static fact, so it rides in with the slate
    instead of living in a table that is wrong by September.
    """
    day = today or _dt.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    # REGULAR SEASON ONLY. The games table holds postseason results too,
    # and counting them here is not a rounding error — it showed a 14-3
    # team as 17-4, gave nearly every club a one-game losing streak (the
    # last thing most teams do is lose a playoff game), and rewarded the
    # deepest run with the best "regular season" record. Standings and a
    # bracket are two different questions about the same rows.
    # Each row with whether it went past regulation, read once: an
    # overtime or shootout loss is the NHL's third column (the slot `ties`
    # holds for a points league, as `from_feed` fills it) — a point banked,
    # not a loss. Counted as a loss, a club's points came up short by every
    # one it took past regulation.
    rows = list(_regular(conn, sport, season))

    table: dict[str, Record] = {}

    def _rec(name: str) -> Record:
        key = divisions.canonical(sport, name)
        if key not in table:
            conf, div = divisions.group_of(sport, key)
            if conferences:
                conf = conferences.get(key) or conferences.get(name) or conf
            table[key] = Record(team=key, conference=conf, division=div)
        return table[key]

    skipped_unfinished = 0
    for r, past_regulation in rows:
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        # In a sport with no ties, equal scores mean the row is not a
        # finished game — a suspension, a postponement, or a score we
        # never received. It is not half a result, so it is not counted:
        # letting it through inflated games played, moved every pct and
        # diff, and put a .504 club on top of a division.
        if hs == as_ and sport not in TIES_EXIST:
            skipped_unfinished += 1
            continue
        home, away = _rec(r["home"]), _rec(r["away"])
        for me, _opp, mine, theirs, at_home in (
                (home, away, hs, as_, True), (away, home, as_, hs, False)):
            me.points_for += mine
            me.points_against += theirs
            if mine > theirs:
                me.wins += 1
                me.home_wins += at_home
                me.away_wins += (not at_home)
                me.reg_wins += not past_regulation
                outcome = "W"
            elif mine < theirs and past_regulation:
                me.ties += 1
                outcome = "T"
            elif mine < theirs:
                me.losses += 1
                me.home_losses += at_home
                me.away_losses += (not at_home)
                outcome = "L"
            else:
                me.ties += 1
                outcome = "T"
            me.results.append(outcome)

    for rec in table.values():
        rec.last10 = rec.results[-10:]
        # A streak is the current run only, and a tie ENDS one rather than
        # extending it — "W4" through a tie would be a claim about form
        # that the results do not support.
        run, last = 0, ""
        for ch in reversed(rec.results):
            if ch == "T" or (last and ch != last):
                break
            last, run = ch, run + 1
        rec.streak = run if last == "W" else -run if last == "L" else 0

    return {
        "sport": sport,
        "season": season,
        "games_counted": len(rows) - skipped_unfinished,
        "unfinished_skipped": skipped_unfinished,
        # WHERE THESE NUMBERS CAME FROM, said in the payload so the page
        # can say it too: counted from the games we have ingested, which
        # is not the same claim as the league's own table.
        "source": "computed",
        "groups": _grouped(sport, table),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "score_label": SCORE_LABEL.get(sport, "PF/PA"),
        # Said out loud on the page. Our order is win percentage and point
        # differential; a league's real tiebreakers run through head-to-head
        # and common opponents, which a partially-ingested season cannot
        # reproduce. Claiming to be the official order would be the kind of
        # small lie that is only found when it matters.
        "order_note": ("ordered by win % then point differential — our own "
                       "order, not the league's official tiebreakers"),
    }


def from_feed(sport: str, rows: list[dict], season: int,
              conferences: dict | None = None) -> dict:
    """The league's own standings, in the shape the page already renders.

    Takes parsed rows from `engine.sources.leaguestandings` and keeps only
    the NUMBERS from them. Grouping still comes from `engine.divisions`
    and the order from `_sort_key`, so the page cannot disagree with
    itself about which division a club is in, and a feed reorganizing its
    envelope cannot silently reorganize the league.

    `last10` is left empty: neither feed publishes the ordered run, and a
    label invented from a season record would be a number nobody measured.
    """
    table: dict[str, Record] = {}
    for r in rows:
        key = divisions.canonical(sport, r.get("team") or "")
        if not key:
            continue
        conf, div = divisions.group_of(sport, key)
        if conferences:
            conf = conferences.get(key) or conf
        rec = Record(team=key, conference=conf, division=div)
        rec.wins = int(r.get("wins") or 0)
        rec.losses = int(r.get("losses") or 0)
        rec.ties = int(r.get("ties") or 0) if sport in TIES_EXIST | OTL_SPORTS else 0
        rec.points_for = float(r.get("points_for") or 0.0)
        rec.points_against = float(r.get("points_against") or 0.0)
        rec.home_wins = int(r.get("home_wins") or 0)
        rec.home_losses = int(r.get("home_losses") or 0)
        rec.away_wins = int(r.get("away_wins") or 0)
        rec.away_losses = int(r.get("away_losses") or 0)
        rec.streak = int(r.get("streak") or 0)
        rec.last10_text = str(r.get("last10") or "")
        table[key] = rec

    return {
        "sport": sport,
        "season": season,
        "games_counted": sum(r.games for r in table.values()) // 2,
        "unfinished_skipped": 0,
        "source": "league",
        "groups": _grouped(sport, table),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "score_label": SCORE_LABEL.get(sport, "PF/PA"),
        "order_note": ("the league's own records, grouped by our division "
                       "table and ordered by win % then run/point "
                       "differential — not the league's official tiebreakers"),
    }


def zero_table(sport: str, season: int) -> dict:
    """Every club in the league's alignment at 0-0 — the honest table for
    a season that has opened with no game finished yet. Built through
    `from_feed` so it is the same shape as the league's own table."""
    rows = [{"team": t} for t in divisions.MAPS.get(sport, {})]
    out = from_feed(sport, rows, season)
    out["source"] = "alignment"
    out["order_note"] = "no game finished yet — every club 0-0, in the league's divisions"
    return out


def _sort_key(r: Record):
    return (-r.pct, -r.diff, -r.wins, r.team)


def _grouped(sport: str, table: dict[str, Record]) -> list[dict]:
    """Conference → division → sorted teams, with sensible fallbacks."""
    buckets: dict[tuple, list] = {}
    for rec in table.values():
        buckets.setdefault((rec.conference or "League", rec.division or ""),
                           []).append(rec)

    out = []
    for (conf, div), recs in sorted(buckets.items()):
        recs.sort(key=_sort_key)
        out.append({
            "conference": conf, "division": div,
            "label": f"{conf} {div}".strip(),
            "teams": [_row(sport, i + 1, r) for i, r in enumerate(recs)],
        })
    return out


def _row(sport: str, rank: int, r: Record) -> dict:
    d = asdict(r)
    n = max(1, r.games)
    d.update({
        "rank": rank, "games": r.games, "pct": r.pct, "diff": r.diff,
        "pf_per_game": round(r.points_for / n, 1),
        "pa_per_game": round(r.points_against / n, 1),
        "record": (f"{r.wins}-{r.losses}"
                   + (f"-{r.ties}" if r.ties or sport in OTL_SPORTS else "")),
        "home": f"{r.home_wins}-{r.home_losses}",
        "away": f"{r.away_wins}-{r.away_losses}",
        "streak_label": ("—" if not r.streak else
                         f"{'W' if r.streak > 0 else 'L'}{abs(r.streak)}"),
        "last10_label": (
            r.last10_text if r.last10_text
            else (f"{r.last10.count('W')}-{r.last10.count('L')}"
                  + (f"-{r.last10.count('T')}"
                     if r.last10.count('T') else "")) if r.last10
            else "—"),
    })
    if sport in OTL_SPORTS:
        d["otl"] = r.ties
        d["points"] = 2 * r.wins + r.ties
    else:
        d.pop("reg_wins", None)
    d.pop("results", None)              # ordering detail, not page content
    return d


#: Sports whose pages carry the offense/defense unit rankings. Ethan,
#: 2026-09-02: "For nfl and cfb on the rankings page, we should have a
#: section ranking the current ranking for teams defense and offense."
UNIT_RANKING_SPORTS = ("nfl", "cfb")


def unit_rankings(table: dict) -> dict | None:
    """Scoring offense and scoring defense, ranked league-wide.

    Built from the SAME rows the standings table shows — points per game
    scored (offense, high is good) and allowed (defense, low is good) —
    so the two sections can never disagree with the table above them.
    Labeled "scoring" honestly: we hold league-wide points, not yardage,
    and a section called "offense rankings" built on points alone should
    say which measure it means. None for other sports, thin seasons, and
    the preseason wait — an unplayed season has no rankings to claim.
    """
    if table.get("sport") not in UNIT_RANKING_SPORTS:
        return None
    rows = [t for t in team_rows(table) if t.get("games")]
    if len(rows) < 4:
        return None

    def entries(ordered, key):
        return [{"rank": i + 1, "team": t["team"], "value": t[key],
                 "games": t["games"], "record": t["record"]}
                for i, t in enumerate(ordered)]

    off = sorted(rows, key=lambda t: (-t["pf_per_game"], t["team"]))
    dfn = sorted(rows, key=lambda t: (t["pa_per_game"], t["team"]))
    return {"measure": "points per game",
            "offense": entries(off, "pf_per_game"),
            "defense": entries(dfn, "pa_per_game")}


def conference_seeds(standings: dict, per_conference: int = 8) -> list[dict]:
    """Who would be seeded where if the season ended today.

    Explicitly a PROJECTION off our own table, never presented as a
    clinched bracket — see `engine.playoffs`, which only ever draws a real
    one from games that were actually played.
    """
    by_conf: dict[str, list] = {}
    for grp in standings.get("groups", []):
        by_conf.setdefault(grp["conference"], []).extend(grp["teams"])
    out = []
    for conf, teams in sorted(by_conf.items()):
        teams = sorted(teams, key=lambda t: (-t["pct"], -t["diff"]))
        out.append({"conference": conf,
                    "seeds": [{**t, "seed": i + 1}
                              for i, t in enumerate(teams[:per_conference])]})
    return out
