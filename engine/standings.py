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
from dataclasses import dataclass, field, asdict

from . import divisions
from .seasons import season_of

# Points/runs per game are worth showing; the label differs by sport and
# so does what a bettor reads it for.
SCORE_LABEL = {"nfl": "PF/PA", "cfb": "PF/PA",
               "nba": "PPG", "wnba": "PPG", "mlb": "R/RA"}

#: Leagues that actually play ties. Everywhere else an equal-score row is
#: a game that did not finish (suspended, postponed) or one whose score we
#: never got — counting it as a tie is how baseball ended up with 70-69-1.
TIES_EXIST = {"nfl", "cfb"}


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


def _finished(conn, sport: str, seasons: list[int] | None):
    q = ("SELECT season, period, home, away, home_score, away_score "
         "FROM games WHERE sport=? AND home_score IS NOT NULL "
         "AND away_score IS NOT NULL")
    args: list = [sport]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    return conn.execute(q + " ORDER BY period", args).fetchall()


def compute(conn, sport: str, season: int | None = None,
            today: str | None = None, conferences: dict | None = None
            ) -> dict:
    """Standings for one season of one sport.

    ``conferences`` is an optional ``{team: conference}`` override, which
    is how college football gets its groups — 134 programs realigning
    every summer is not a static fact, so it rides in with the slate
    instead of living in a table that is wrong by September.
    """
    from .playoffs import is_postseason

    day = today or _dt.date.today().isoformat()
    season = season if season is not None else season_of(sport, day)
    # REGULAR SEASON ONLY. The games table holds postseason results too,
    # and counting them here is not a rounding error — it showed a 14-3
    # team as 17-4, gave nearly every club a one-game losing streak (the
    # last thing most teams do is lose a playoff game), and rewarded the
    # deepest run with the best "regular season" record. Standings and a
    # bracket are two different questions about the same rows.
    rows = [r for r in _finished(conn, sport, [season])
            if not is_postseason(sport, season, r["period"])]

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
    for r in rows:
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
        for me, opp, mine, theirs, at_home in (
                (home, away, hs, as_, True), (away, home, as_, hs, False)):
            me.points_for += mine
            me.points_against += theirs
            if mine > theirs:
                me.wins += 1
                me.home_wins += at_home
                me.away_wins += (not at_home)
                outcome = "W"
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
        rec.ties = int(r.get("ties") or 0) if sport in TIES_EXIST else 0
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
                   + (f"-{r.ties}" if r.ties else "")),
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
    d.pop("results", None)              # ordering detail, not page content
    return d


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
