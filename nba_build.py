#!/usr/bin/env python3
"""Build the NBA (Scalpy) slate: minutes engine → distributions → clamp →
gate, against real de-vigged prices.

    python3 nba_build.py 2026-01-15 --cached-odds --out web/data/nba.json

Schedule from the free NBA CDN; player history from our own ingested logs
(minutes first — run `python3 ingest.py nba --from ... --to ...` to build
history); prices from The Odds API (budgeted, same pacer as MLB/NFL).
Offseason → an honest status page, not fake picks.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from engine.db import connect
from engine.hoops import for_league
from engine.sources.fetch import DataUnavailable
from engine.nba.pipeline import run_nba_slate
from engine import gate


# The markets the slate prices. PRA rides along because it is the WNBA
# spec's headline tier-1 market and it is free — player props bill per
# event, not per market — and it is derived from three columns already
# ingested, so it needs no new feed.
SLATE_MARKETS = ("pts", "reb", "ast", "fg3m", "pra")


class _Game:
    def __init__(self, home, away, kickoff, home_name="", away_name=""):
        self.home, self.away, self.kickoff = home, away, kickoff
        # The schedule feed's own full team names, carried so the odds
        # adapter can join on them instead of on a hand-written table of
        # abbreviations that disagrees with this feed's.
        self.home_name, self.away_name = home_name, away_name
        self.live = None
        self.spread = None
        self.home_ml = self.away_ml = 0
        self.total = None


class _Prop:
    def __init__(self, player, market):
        self.player, self.market = player, market
        self.lines = []


class _Slate:
    def __init__(self, games, props):
        self.games, self.props = games, props


def player_history(conn, teams: set[str], sport: str = "nba",
                   seasons: list[int] | None = None) -> dict:
    """{player: {"team", "starter", "minutes": [...], stat: [...]}} newest
    first, last 20 games, for players on tonight's teams.

    ``seasons`` bounds the read. Only 20 games survive the slice no matter
    how many are loaded, so an unbounded query on a backfilled history
    sorts several seasons of rows to throw nearly all of them away — and
    for a player who has not appeared this year it would hand back last
    year's form as if it were current.
    """
    hist: dict = {}
    q = ("SELECT player, team, position, period, market, value "
         "FROM player_game_logs WHERE sport=? AND team IN (%s)"
         % ",".join("?" * len(teams)))
    args: list = [sport, *teams]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    rows = conn.execute(q + " ORDER BY period DESC", args).fetchall()
    for r in rows:
        p = hist.setdefault(r["player"], {"team": r["team"], "starter": None,
                                          "by_week": {}})
        wk = p["by_week"].setdefault(r["period"], {})
        wk[r["market"]] = float(r["value"])
        if p["starter"] is None and r["market"] == "min":
            p["starter"] = r["position"] == "S"
    for p in hist.values():
        weeks = sorted(p["by_week"], reverse=True)[:20]
        p["minutes"] = [p["by_week"][w].get("min", 0.0) for w in weeks]
        p["dates"] = weeks                      # ISO dates, newest first
        for stat in ("pts", "reb", "ast", "fg3m"):
            p[stat] = [p["by_week"][w].get(stat, 0.0) for w in weeks]
        # PRA is the WNBA spec's headline tier-1 market and it needs no new
        # ingest — it is the sum of three columns we already store. Deriving
        # it here rather than fetching it also guarantees the history and
        # the line refer to the same three numbers.
        p["pra"] = [round(p["pts"][i] + p["reb"][i] + p["ast"][i], 1)
                    for i in range(len(weeks))]
    return hist


def _ctx_layoff(dates, game_date: str):
    """Days since this player's team last played, for the layoff rule."""
    try:
        from engine.nba.context import layoff_days
        return layoff_days(dates, game_date)
    except Exception:                                       # noqa: BLE001
        return None


def schedule_density(schedule_days: dict, team: str, date: str) -> dict:
    """§6 — how compressed this team's last week has been.

    A ~44-game season inside ~4.5 months makes the WNBA schedule denser
    than the NBA's, and density is the part that survived charter flights:
    raw travel matters less now, games-per-days still matters.
    """
    import datetime as _d
    try:
        d0 = _d.date.fromisoformat(date)
    except ValueError:
        return {"rest": "1day", "games_in_4": 0, "games_in_6": 0}
    played = set()
    for offset in range(1, 7):
        day = (d0 - _d.timedelta(days=offset)).isoformat()
        for g in schedule_days.get(day, []):
            if team in (g.get("home"), g.get("away")):
                played.add(offset)
    in_4 = sum(1 for o in played if o <= 3)
    in_6 = sum(1 for o in played if o <= 5)
    if 1 in played:
        rest = "3in4" if in_4 >= 2 else "b2b_home"
    elif in_6 >= 3:
        rest = "4in6_road"
    elif not played:
        rest = "2plus"
    else:
        rest = "1day"
    return {"rest": rest, "games_in_4": in_4 + 1, "games_in_6": in_6 + 1}


def schedule_fit(density: dict) -> float:
    """0-1 for the §8 grade: a rested team is a clean spot, a team on its
    third game in four nights is not."""
    return {"2plus": 1.0, "1day": 0.85, "b2b_home": 0.55,
            "3in4": 0.4, "4in6_road": 0.35}.get(density.get("rest"), 0.7)


def defense_ratings(conn, sport: str) -> dict:
    """{team: points allowed per game} — the only matchup read the ingested
    data actually supports.

    The spec asks for points allowed PER POSSESSION and is right that
    per-game is pace-polluted. We do not ingest possessions, so this is
    labelled as what it is and scored as a directional input rather than
    the headline — which is also what §6 says to do with small-sample
    defensive splits.
    """
    rows = conn.execute(
        "SELECT home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL", (sport,)).fetchall()
    agg: dict = {}
    for r in rows:
        agg.setdefault(r["home"], [0.0, 0]);  agg[r["home"]][0] += float(r["away_score"]); agg[r["home"]][1] += 1
        agg.setdefault(r["away"], [0.0, 0]);  agg[r["away"]][0] += float(r["home_score"]); agg[r["away"]][1] += 1
    return {t: round(pa / n, 2) for t, (pa, n) in agg.items() if n >= 5}


def matchup_fit(defense: dict, opponent: str) -> float:
    """0-1: is this a defence worth attacking? Half when we can't tell."""
    if not defense or opponent not in defense:
        return 0.5
    vals = sorted(defense.values())
    rank = sum(1 for v in vals if v < defense[opponent]) / max(1, len(vals) - 1)
    # Leakier defence (higher points allowed) = better spot for an Over.
    return round(0.35 + 0.5 * rank, 3)


def best_two_way(lines) -> tuple | None:
    """Most-quoted line value, best Over and best Under across books."""
    by_line: dict = {}
    for ln in lines:
        if ln.over_odds and ln.under_odds:
            by_line.setdefault(ln.line, []).append(ln)
    if not by_line:
        return None
    line, quotes = max(by_line.items(), key=lambda kv: len(kv[1]))
    over = max(quotes, key=lambda l: l.over_odds)
    under = max(quotes, key=lambda l: l.under_odds)
    return line, over.over_odds, under.under_odds, over.book


def diagnose(league: str, date: str) -> None:
    """Why does this board have no props? Answer it with counts, not guesses.

    Every prop here is projected from stored player game logs, and the query
    that finds them is narrow on purpose — this sport, these teams, these
    seasons. Any one of the three failing produces the same symptom: a slate
    with games on it and nothing to bet. From the outside those look
    identical, and from the terminal they were invisible.

    So print each filter and what survives it. The line that drops to zero
    is the answer.
    """
    from engine.seasons import recent_seasons
    if league == "wnba":
        from engine.sources.wnbaespn import fetch_schedule, parse_schedule_day
    else:
        from engine.sources.nbadata import fetch_schedule, parse_schedule_day

    L = league.upper()
    print(f"\n{L} prop diagnosis for {date}")
    try:
        games = parse_schedule_day(fetch_schedule(), date)
    except DataUnavailable as exc:
        print(f"  Schedule            UNREACHABLE — {exc}")
        print(f"  Nothing downstream can work without it. Fix the feed first.")
        return
    print(f"  Schedule            {len(games)} game(s)"
          + (": " + ", ".join(f"{g['away']}@{g['home']}" for g in games[:6])
             if games else " — nothing scheduled, so no props is correct"))
    if not games:
        return

    teams = {t for g in games for t in (g["home"], g["away"])}
    seasons = recent_seasons(league, date)
    print(f"  Teams tonight       {', '.join(sorted(teams))}")
    print(f"  Seasons queried     {seasons}")

    conn = connect()
    total = conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                         (league,)).fetchone()[0]
    print(f"  Logs in DB          {total:,} row(s) for {league}")
    if not total:
        print(f"  ✗ No player logs at all. Fix: python3 ingest.py {league} "
              f"--seasons 2021-2026")
        return

    by_season = conn.execute(
        "SELECT season, COUNT(*) n FROM player_game_logs WHERE sport=? "
        "GROUP BY season ORDER BY season", (league,)).fetchall()
    print("    by season         "
          + " · ".join(f"{r['season']}: {r['n']:,}" for r in by_season))
    in_window = sum(r["n"] for r in by_season if r["season"] in seasons)
    if not in_window:
        print(f"  ✗ Logs exist, but NONE in the seasons this board reads "
              f"({seasons}). The ingest and the query disagree about which "
              f"year these games belong to.")
        return

    codes = {r["team"] for r in conn.execute(
        "SELECT DISTINCT team FROM player_game_logs WHERE sport=? "
        "AND season IN (%s)" % ",".join("?" * len(seasons)),
        (league, *seasons))}
    print(f"    team codes seen   {', '.join(sorted(codes))}")
    hit, miss = teams & codes, teams - codes
    print(f"  Team-code match     {len(hit)} of {len(teams)} tonight's teams "
          f"appear in the logs")
    if miss:
        print(f"  ✗ No logs under: {', '.join(sorted(miss))}")
        print(f"    The schedule feed and the ingest are naming the same "
              f"clubs differently, so the query matches nothing. This is a "
              f"code fix, not an ingest — nothing you re-run will help.")
        if not hit:
            return

    hist = player_history(conn, teams, sport=league, seasons=seasons)
    ready = [p for p, h in hist.items() if len(h["minutes"]) >= 3]
    print(f"  Players found       {len(hist)}")
    print(f"  With 3+ games       {len(ready)}")
    print(f"  Props buildable     {len(ready) * len(SLATE_MARKETS)}")
    if not ready and hist:
        print(f"  ✗ Players are in the logs but none has three games in "
              f"{seasons} — too early in the season to project anyone.")
    elif ready and not miss:
        print(f"  ✓ The history is fine. If the board is still empty, the "
              f"props are being built and then filtered — check the gate "
              f"census under \"Where tonight's props died\" on the page.")
    elif ready:
        # Partial match. Saying "the history is fine" here would contradict
        # the ✗ three lines up, and a report that argues with itself is
        # worse than one that says nothing.
        print(f"  ⚠️  Only the matched teams can be priced — tonight's board "
              f"will be missing every player on {', '.join(sorted(miss))}.")


#: How far back to look before calling an empty date the offseason. Wide
#: enough to span an All-Star break, which is the longest gap a running
#: hoops season produces.
LOOKBACK_DAYS = 10


def _recent_slate(args, tune) -> tuple[int, bool]:
    """``(games found, did we manage to look)`` over the days before this.

    THE SECOND VALUE IS THE POINT, and it is the same distinction
    `cfb_build._recent_games` had to learn: "we looked and the league is
    dormant" and "we could not look" are different facts, and only the
    first is the offseason. A fetch that fails must not publish a claim
    about the league on the strength of our own failure.
    """
    import datetime as _d
    try:
        day = _d.date.fromisoformat(args.date)
    except ValueError:
        return 0, False
    # IMPORTED HERE, per league, because `main()` does the same and these
    # names exist nowhere else. The first cut of this function called
    # `parse_schedule_day` as though it were module-level — it is not,
    # and that is the same scoping mistake that had just been fixed one
    # file over. A test caught it; nothing in the source would have.
    league = getattr(args, "league", "nba")
    try:
        if league == "wnba":
            from engine.sources.wnbaespn import (fetch_schedule,
                                                 parse_schedule_day)
        else:
            from engine.sources.nbadata import (fetch_schedule,
                                                parse_schedule_day)
    except Exception:                                      # noqa: BLE001
        return 0, False
    found, looked = 0, 0
    for n in range(1, LOOKBACK_DAYS + 1):
        past = (day - _d.timedelta(days=n)).isoformat()
        try:
            rows = parse_schedule_day(fetch_schedule(), past)
        except Exception:                                  # noqa: BLE001
            continue
        looked += 1
        found += len(rows or [])
    return found, bool(looked)


def _live_block(g: dict) -> dict | None:
    """The shared `live` shape every other board emits, from `gameStatus`.

    None when the game has not started, because a `live` block that says
    "scheduled" is indistinguishable from one the build forgot to fill —
    and the site's own empty check is what draws the pre-game card.
    """
    # TWO FEED SHAPES, ONE BLOCK. The NBA's CDN speaks numeric
    # `gameStatus` (1 scheduled, 2 live, 3 final); the WNBA path now
    # rides ESPN's scoreboard, whose rows carry a string `state` and a
    # separate running score. This function read only the number — so
    # after the ESPN parser learned to say "live", every WNBA game still
    # arrived here as None-status and rendered as not started. The
    # comment above already says it: nothing carried it the last two
    # inches. This was the second inch.
    status = g.get("status")
    if status == 2 or g.get("state") == "live":
        state = "live"
    elif status == 3 or g.get("state") == "final" or g.get("completed"):
        state = "final"
    else:
        return None
    if state == "final":
        home, away = g.get("home_score"), g.get("away_score")
    else:
        # The running score where the feed carries one (ESPN does;
        # Scalpy's schedule does not). `home_score` stays final-only on
        # the ESPN rows so settlement cannot read a third-quarter score
        # as a result — the live pair is the display copy.
        home = g.get("live_home_score", g.get("home_score"))
        away = g.get("live_away_score", g.get("away_score"))
    return {"state": state, "home_score": home, "away_score": away,
            # ESPN carries a clock ("Q3 4:21"); Scalpy's schedule feed
            # does not, and an invented one is worse than none: the card
            # falls back to the state word rather than printing "Q1
            # 12:00" for a game in the fourth.
            "detail": (g.get("clock") or
                       ("final" if state == "final" else "in progress"))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--cached-odds", action="store_true")
    ap.add_argument("--out", default="web/data/nba.json")
    # One build, two leagues. The WNBA runs the same Scalpy pipeline on the
    # same JSON shapes from its own CDN; what differs is the tuning (a
    # 40-minute game) and the fact that its tuning has never been fitted to
    # WNBA results — see engine/hoops.py.
    ap.add_argument("--league", choices=["nba", "wnba"], default="nba")
    ap.add_argument("--diagnose", action="store_true",
                    help="report exactly where this board loses its props "
                         "(schedule teams vs stored logs) and exit")
    args = ap.parse_args()
    if args.diagnose:
        diagnose(args.league, args.date)
        return
    tune = for_league(args.league)
    # Swap in whatever this league's OWN results can measure. The WNBA
    # shipped inheriting the NBA's margin SD and stat spreads because
    # there was no WNBA sample to fit them against; there is one now, and
    # an inherited number that could be measured is just a wrong number
    # with a good excuse. Anything still unmeasurable keeps the inherited
    # value and says so — this never flips `calibrated`, because fitting
    # constants and earning the right to bet are different claims.
    try:
        from engine.db import connect as _fconn
        from engine.hoops_fit import fitted_tuning, describe
        _fc = _fconn()
        try:
            tune, _fit_report = fitted_tuning(_fc, args.league)
        finally:
            _fc.close()
        if _fit_report["fitted"]:
            print(describe(_fit_report))
    except Exception as exc:  # noqa: BLE001 — a failed fit must not stop a build
        print(f"⚠️  Tuning fit unavailable — using inherited numbers.\n   {exc}")
    if args.league == "wnba":
        # ESPN, not the WNBA CDN. The CDN path was written by analogy with
        # the NBA's and never returned JSON on a real machine; this is the
        # endpoint family that already carries NFL scores and the whole
        # college football board here.
        from engine.sources.wnbaespn import fetch_schedule, parse_schedule_day
    else:
        from engine.sources.nbadata import fetch_schedule, parse_schedule_day

    out: dict = {"generated_at": datetime.datetime.now()
                 .isoformat(timespec="seconds"), "date": args.date,
                 "sport": args.league,
                 "generated_from": f"live-{args.league}",
                 "probation": tune.probation,
                 "tuning": {"calibrated": tune.calibrated,
                            "inherited_from": tune.inherited_from,
                            "note": tune.note},
                 "recommendations": [], "game_bets": [], "long_shots": [],
                 "longshot_watch": [], "most_likely": [], "board_shelves": [],
                 "market_scan": {"stale": [], "arbs": [], "middles": [],
                                 "low_holds": [], "longshots": []},
                 "counts": {"props_analyzed": 0, "recommended": 0}}

    try:
        games = parse_schedule_day(fetch_schedule(), args.date)
    except DataUnavailable as exc:
        out.update(status="unreachable", note=str(exc))
        games, yesterday = [], []
    else:
        # SEPARATELY, because on the ESPN path each parse is its own
        # fetch: sharing one try meant yesterday's scoreboard failing
        # threw away a slate that had already been read, and the board
        # published "unreachable" over games it was holding. Yesterday
        # only feeds the back-to-back read — that degrades; the slate
        # does not go down with it.
        try:
            yesterday = parse_schedule_day(
                fetch_schedule(), (datetime.date.fromisoformat(args.date)
                                   - datetime.timedelta(days=1)).isoformat())
        except DataUnavailable:
            yesterday = []

    # The slate's games ride in the JSON like every other board's: it's how
    # the launcher's pacer knows the slate is live, what a refresh costs,
    # and when the pre-game window opens (kickoffs are UTC ISO stamps).
    # `live` RIDES ALONG, and its absence was a real defect. Every other
    # board emits it and the site reads it to draw LIVE and FINAL; this
    # one emitted home/away/date/kickoff only, so on 2026-08-09 at 8pm the
    # WNBA board still showed three games that had finished hours earlier
    # as though they had not started. The feed knew — `gameStatus` is 1
    # scheduled, 2 live, 3 final, and `parse_schedule_day` has always
    # returned it. Nothing carried it the last two inches.
    out["games"] = [{"home": g["home"], "away": g["away"], "date": args.date,
                     "kickoff": g.get("kickoff", ""),
                     "live": _live_block(g)} for g in games]

    if not games and "status" not in out:
        # "OFFSEASON" FROM A SINGLE EMPTY DAY IS NOT A FINDING. This
        # asserted it whenever today had no games — no lookback, no
        # evidence — and on 2026-08-31, a Sunday in the middle of a WNBA
        # season that runs into September, the board said the league was
        # out of season because that one date was quiet.
        #
        # `cfb_build` made the same claim and was corrected the same day;
        # it at least looked back ten days first. This one did not look
        # at all. A quiet Monday, a bye, an All-Star break and a finished
        # season all produce zero games, and only the last is what the
        # word means.
        recent, looked = _recent_slate(args, tune)
        if not looked:
            out.update(status="schedule unknown",
                       note=f"No {tune.name} games came back for this date, "
                            f"and the lookback that would say whether the "
                            f"season is running could not be fetched either. "
                            f"That is a gap on our side, not a claim that "
                            f"the league is finished.")
        elif recent:
            out.update(status="no games today",
                       note=f"No {tune.name} games on this date, but the "
                            f"season is running — {recent} game(s) in the "
                            f"last {LOOKBACK_DAYS} days. A quiet date, not "
                            f"the offseason.")
        else:
            out.update(status="offseason",
                       note=f"No {tune.name} games on this date, and none in "
                            f"the last {LOOKBACK_DAYS} days either. The engine "
                            "(minutes model, "
                            "distributions, humility clamp, approval gate) is built "
                            "and tested — it goes live with the schedule.")

    picks_result = None
    if games:
        played_yday = {t for g in yesterday
                       for t in (g["home"], g["away"])}
        # §6 schedule density needs a week of schedule, not just yesterday:
        # "three games in four nights" and "four in six" are the reads that
        # survived charter flights, and one day of lookback cannot see them.
        sched_days: dict = {}
        try:
            _sched = fetch_schedule()
            for _off in range(1, 7):
                _day = (datetime.date.fromisoformat(args.date)
                        - datetime.timedelta(days=_off)).isoformat()
                sched_days[_day] = parse_schedule_day(_sched, _day)
        except DataUnavailable:
            sched_days = {}
        conn = connect()
        teams = {t for g in games for t in (g["home"], g["away"])}
        # This season and last: early in a year a player's most recent 20
        # games run back into the previous season, so one is too few — and
        # six is a different player.
        from engine.seasons import recent_seasons
        hist = player_history(conn, teams, sport=args.league,
                              seasons=recent_seasons(args.league, args.date))

        slate = _Slate([_Game(g["home"], g["away"], g["kickoff"],
                              g.get("home_name", ""), g.get("away_name", ""))
                        for g in games], [])
        for player, h in hist.items():
            if len(h["minutes"]) >= 3:
                for stat in SLATE_MARKETS:
                    slate.props.append(_Prop(player, stat))

        # Every prop on this board is projected from stored game logs, so an
        # empty history produces an empty board that looks exactly like a
        # quiet night. It is not the same thing at all, and the WNBA hit it:
        # games on the schedule, a live season, and zero props, because the
        # league had never been ingested. Say which of the two it is — here
        # in the terminal, and on the page via `history_gap` below.
        if games and not slate.props:
            # NO `fix` COMMAND IN THE PAYLOAD. This dict is served to the
            # public site, and it used to carry the shell command that
            # repairs the gap — which the page then printed, in a <code>
            # block, to every visitor. Ethan, 2026-08-23: "lets get all
            # the little things like this telling ME what to do off the
            # website since this website is live for anyone to use." The
            # instruction still prints below, in the terminal, where the
            # person who can act on it is standing.
            out["history_gap"] = {
                "teams": sorted(teams),
                "players_found": len(hist),
                "seasons": recent_seasons(args.league, args.date),
            }
            print(f"\n⚠️  {len(games)} {args.league.upper()} game(s) on the "
                  f"schedule and NO props to build.")
            print(f"    Props come from stored player logs, and this database "
                  f"has {len(hist)} player(s) with any history for tonight's "
                  f"teams (a prop needs 3+ games).")
            print(f"    Fix: python3 ingest.py {args.league} "
                  f"--seasons 2021-2026")

        odds_note = "no odds requested — engine ran with no bettable prices"
        if args.odds or args.cached_odds:
            from engine.sources import oddsapi
            try:
                res = oddsapi.apply_odds_to_slate(
                    slate, sport=args.league,
                    cache_only=args.cached_odds and not args.odds)
                odds_note = (f"matched {res.matched} props across "
                             f"{res.events_used} events"
                             + (" (cached)" if res.from_cache else ""))
                # A game the book priced and we failed to place is a whole
                # slate's worth of prices thrown away, and it is invisible
                # downstream — its props land in "no real book price"
                # looking exactly like markets the book never offered.
                # A cached rebuild with no payload for the newly-matched
                # events looks exactly like a rebuild where nothing
                # improved — the events place on the slate and then vanish
                # because nobody ever paid for them. Say which it was.
                if res.cache_misses:
                    odds_note += (f"; {res.cache_misses} matched event(s) "
                                  f"have no cached prices")
                    print(f"\n  {res.cache_misses} event(s) matched the slate "
                          f"but were never paid for, so there are no cached "
                          f"prices to read.\n  Their props stay in 'no real "
                          f"book price' until the next live pull.")
                if res.dropped_events:
                    odds_note += (f"; {len(res.dropped_events)} event(s) "
                                  f"DROPPED — see the odds diagnosis")
                    print(f"\n⚠️  {len(res.dropped_events)} priced event(s) "
                          f"could not be placed on the slate:")
                    for d in res.dropped_events:
                        print(f"    {d['away']} @ {d['home']}  — {d['reason']}"
                              + (f" (unmapped: {', '.join(d['unmapped'])})"
                                 if d.get("unmapped") else "")
                              + (f" (mapped to {'@'.join(d['mapped_to'])})"
                                 if d.get("mapped_to") else ""))
                    print(f"    Every prop in those games is counted under "
                          f"'no real book price'.")
            except oddsapi.OddsAPIError as exc:
                odds_note = f"odds unavailable: {exc}"

        # Stale-line scan across every book's quotes — the sampler signal
        # MLB and NFL already journal. It must run HERE: the pipeline only
        # ever sees the best two-way quote, and the scanner needs the field.
        try:
            from engine.marketscan import stale_quotes
            from engine.nba.pipeline import MARKET_LABELS as _ML
            started_teams: set = set()
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            for g in games:
                k = (g.get("kickoff") or "").replace("Z", "+00:00")
                try:
                    if datetime.datetime.fromisoformat(k) <= now_utc:
                        started_teams |= {g["home"], g["away"]}
                except ValueError:
                    pass
            scan_rows = [{
                "player": pr.player, "market": pr.market,
                "market_label": _ML.get(pr.market, pr.market),
                "game_date": args.date, "live": False,
                "warnings": (["Game already started"]
                             if hist.get(pr.player, {}).get("team")
                             in started_teams else []),
                "all_lines": [{"book": ln.book, "line": ln.line,
                               "over_odds": ln.over_odds,
                               "under_odds": ln.under_odds}
                              for ln in pr.lines],
            } for pr in slate.props if pr.lines]
            out["market_scan"] = {"stale": stale_quotes(scan_rows)}
        except Exception:
            out["market_scan"] = {"stale": []}

        spread_by_team: dict = {}
        total_by_team: dict = {}
        for g in slate.games:
            if g.spread is not None:
                spread_by_team[g.home] = (float(g.spread), float(g.spread) < 0)
                spread_by_team[g.away] = (-float(g.spread), float(g.spread) > 0)
            if g.total is not None:
                total_by_team[g.home] = float(g.total)
                total_by_team[g.away] = float(g.total)

        defense = defense_ratings(conn, args.league)
        density = {t: schedule_density(sched_days, t, args.date) for t in teams}
        # §8 freshness: how recently the price we would bet was actually
        # fetched. There is no availability feed for either league, so this
        # tops out below 1.0 on purpose — and with it the grade, which is
        # why half-Kelly (A+, 90) stays out of reach until one exists.
        fresh = 0.9 if (args.odds and "cached" not in odds_note) else 0.5
        if "unavailable" in odds_note:
            fresh = 0.2

        # Count what gets dropped here. This loop silently discarded every
        # prop without a two-way book price, which is most of them most of
        # the time, and nothing downstream knew the difference between "the
        # model rejected 430 props" and "we never had a price for any of
        # them". On the WNBA board those two produced the identical blank
        # page — 430 props buildable from history, zero priced, no census,
        # no explanation anywhere.
        census = {"no_real_price": 0, "no_history": 0}
        props = []
        for prop in slate.props:
            two = best_two_way(prop.lines)
            h = hist.get(prop.player)
            if not h:
                census["no_history"] += 1
                continue
            if not two:
                census["no_real_price"] += 1
                continue
            line, over_odds, under_odds, book = two
            spread, fav = spread_by_team.get(h["team"], (0.0, False))
            props.append({
                "player": prop.player, "team": h["team"],
                "opponent": next((g["away"] if g["home"] == h["team"]
                                  else g["home"] for g in games
                                  if h["team"] in (g["home"], g["away"])), ""),
                "market": prop.market, "line": line,
                "over_odds": over_odds, "under_odds": under_odds,
                "book": book, "minutes": h["minutes"],
                "values": h[prop.market], "is_starter": bool(h["starter"]),
                "spread": spread, "is_favorite": fav,
                # The context layer's inputs (engine/nba/context.py):
                # tonight's total prices the scoring environment, and the
                # gap since the team's last logged game prices the
                # first-game-back dip — the World Cup resumption above all.
                "game_total": total_by_team.get(h["team"]),
                "days_off": _ctx_layoff(h.get("dates"), args.date),
                "rest": density.get(h["team"], {}).get(
                    "rest", "b2b_home" if h["team"] in played_yday else "1day"),
                "density": density.get(h["team"], {}),
                "freshness": fresh,
                "schedule_fit": schedule_fit(density.get(h["team"], {})),
                "matchup_fit": matchup_fit(defense, next(
                    (g["away"] if g["home"] == h["team"] else g["home"]
                     for g in games if h["team"] in (g["home"], g["away"])), "")),
                # No per-prop line-movement feed exists for either league;
                # scoring this neutral is the honest answer, and it is
                # listed as parked rather than quietly assumed favourable.
                "movement_fit": 0.5,
            })

        # §1.3 — the menu's two accounting identities, audited per team
        # and PUBLISHED. Listed points must square with the team total;
        # implied minutes must approach 200. A menu that fails either is
        # named, with the unmoved players the missing production sits on.
        try:
            from engine.nba.coherence import menu_audit
            out["menu_audit"] = menu_audit(
                props, [{"home": g.home, "away": g.away,
                         "total": g.total, "spread": g.spread}
                        for g in slate.games], tune)
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  menu audit skipped: {exc}")
            out["menu_audit"] = []

        picks_result = run_nba_slate(props, tune=tune, meta={
            "games": len(games), "odds": odds_note,
            "teams_on_b2b": sorted(played_yday & teams),
        })
        out.update(status="slate", **picks_result)
        # The build's own drops and the pipeline's, in one table. Without the
        # first two rows an empty board reads as "the model hated everything"
        # when the truth is usually "no book had priced any of it yet".
        out["gate_census"] = {**census, **(picks_result.get("gate_census") or {})}
        out["counts"]["props_built"] = len(slate.props)

        # Shared-schema layer: the same slate shape NFL/MLB emit, so the
        # seven shared pages can render NBA. Scalpy's own keys stay put.
        try:
            from engine.nba.pipeline import shared_recommendations
            lines_map = {}
            for pr in slate.props:
                if pr.lines:
                    lines_map[(pr.player, pr.market)] = [
                        {"book": ln.book, "line": ln.line,
                         "over_odds": ln.over_odds, "under_odds": ln.under_odds}
                        for ln in pr.lines]
            dates_map = {name: h.get("dates", []) for name, h in hist.items()}
            # Photos come out of the same box scores that produced the stat
            # history — one table read, no second feed. A player we have
            # never ingested is simply absent and keeps the initials chip.
            from engine.db import player_assets
            recs = shared_recommendations(props, lines_map, dates_map,
                                          tune=tune,
                                          assets=player_assets(conn, args.league))
            # Movement, EVIDENCE-ONLY (§4). The snapshot history has been
            # written for this league all along — apply_odds_to_slate
            # records every paid pull — while the doc said "no per-prop
            # movement history is stored yet" and nothing ever read it.
            # `price=False` stamps line_move, the first mover and the
            # reason/warning, and skips quality.apply_movement: movement
            # rejecting Scalpy picks is a pricing change nobody approved,
            # and on MLB it is vetoing on a still-unmeasured signal (#80).
            try:
                from engine.linemoves import (analyze, annotate_recommendations,
                                              load_history, todays_rows)
                _mv = analyze(todays_rows(load_history()))
                _n_mv = annotate_recommendations(recs, _mv, price=False)
                if _n_mv:
                    print(f"Line movement: stamped on {_n_mv} pick(s), "
                          f"evidence only — nothing re-graded.")
            except Exception:                                # noqa: BLE001
                pass
            # §7's explicit pair flags — mechanisms named, nothing
            # rejected. Basketball has no true incoherence to mirror
            # baseball's; every hoops pair argument runs through pace or
            # usage, and deciding those outweigh the model is pricing.
            try:
                from engine.correlation import flag_hoops_correlations
                _corr = flag_hoops_correlations(recs)
                if _corr["flagged"]:
                    print(f"Correlations: {_corr['flagged']} pair flag(s) "
                          f"named on the card — evidence, nothing rejected.")
            except Exception:                                # noqa: BLE001
                pass
            out["recommendations"] = recs
            # SAY HOW MANY FACES JOINED. Ethan ingested 100 of 105 WNBA
            # photos and every card still drew initials, because the
            # lookup matched on a raw name and the two feeds disagree
            # about apostrophes. A stored photo that never reaches a card
            # is invisible from both ends — the ingest reports success and
            # the site just looks plain.
            from engine.nba.pipeline import FACE_JOIN as _fj
            if _fj["want"]:
                print(f"Player faces: {_fj['got']} of {_fj['want']} props "
                      f"matched a stored photo"
                      + ("" if _fj["got"] else
                         "  ← none joined; check the name spellings in "
                         "player_assets"))
            # MERGED, NOT REPLACED. This assigned a fresh dict and threw
            # away `props_built`, set sixty lines above — the one number
            # that separates "we only had four players' worth of history"
            # from "we built two hundred props and a book priced four".
            # Those need opposite fixes and the page could not tell them
            # apart, which is exactly what the census three hundred lines
            # up was added to prevent: "430 props buildable from history,
            # zero priced, no census, no explanation anywhere."
            #
            # `props_analyzed` counts rows that got a REAL PRICE, so on
            # its own it always looks like the model considered almost
            # nothing.
            out["counts"] = {**(out.get("counts") or {}),
                             **picks_result["counts"],
                             "props_analyzed": len(recs),
                             "recommended": sum(1 for r in recs
                                                if r["recommended"])}
            from engine.marketscan import scan_recommendations
            ms = scan_recommendations(recs)
            ms["stale"] = (out.get("market_scan") or {}).get("stale", [])
            out["market_scan"] = ms
            # Odds attach set spread/total on the slate games after the
            # games list was written — carry them across for game cards.
            by_pair = {(g.home, g.away): g for g in slate.games}
            for gd in out.get("games", []):
                g = by_pair.get((gd["home"], gd["away"]))
                if g is not None:
                    gd["spread"] = g.spread
                    gd["total"] = g.total
        except Exception as exc:
            print(f"⚠️  shared-schema layer skipped: {exc}")

        # THE LIKELIHOOD BOARD, for hoops. Same maker and same one bar
        # as every other league's (likely.admissible), and the same
        # earned-per-market rule: rows appear only for markets
        # engine.rankfit has measured to rank ON THIS BOX — the weekly
        # pass fits wnba/nba wherever their logs are ingested, and until
        # it has, this board is honestly empty with the census saying so.
        try:
            from engine.likely import build as _likely_build
            from engine import boards as _hboards
            _ml_census: dict = {}
            out["most_likely"] = _likely_build(
                out.get("recommendations") or [], sport=args.league,
                census=_ml_census)
            if not out["most_likely"]:
                from engine.rankfit import load as _rank_store
                if not any(k.startswith(f"{args.league}:")
                           for k in _rank_store()):
                    _ml_census["no market measured to rank yet"] = 1
            out["likely_census"] = _ml_census
            out["board_guide"] = _hboards.guide(args.league)
            out["board_shelves"] = _hboards.shelves(args.league,
                                                    out["most_likely"])
        except Exception as exc:                          # noqa: BLE001
            print(f"⚠️  likelihood board skipped: {exc}")

        # Journal picks + stale flags under the league that produced them —
        # this build runs as BOTH leagues, and journaling "nba" while the
        # settle sweep below reads args.league filed every WNBA pick where
        # no results ingest could ever find it. Settles from our own
        # ingested boxscores — flags journal even on a no-pick night.
        try:
            from engine import ledger
            lconn = ledger.connect()
            n = 0
            if picks_result["picks"]:
                recs = [{"player": p["player"], "market": p["market"],
                         "side": p["side"], "line": p["line"],
                         "book": p["book"], "odds": p["odds"],
                         "projection": p["projection"],
                         "hit_prob": p["p_final"], "edge": p["edge"],
                         "confidence": round(p["p_final"] * 10, 1),
                         "grade": "Play", "stake_units": p["stake_units"],
                         # The assumption the whole bet rests on (§11.8),
                         # journaled so the loss review can separate a
                         # rotation miss from a shooting night.
                         "proj_minutes": p.get("proj_minutes"),
                         "recommended": True}
                        for p in picks_result["picks"]]
                # Same drawdown circuit-breaker as NFL/MLB: 10u off the
                # journal's peak halves every stake until recovery.
                try:
                    dd = ledger.drawdown_factor(lconn, sport=args.league)
                    if dd < 1.0:
                        for p in recs:
                            p["stake_units"] = round(p["stake_units"] * dd, 2)
                        print(f"  ⚠️  Drawdown rule active — "
                              f"{args.league.upper()} stakes halved")
                except Exception:
                    pass
                n = ledger.log_recommendations(
                    lconn, {"sport": args.league, "date": args.date,
                            "recommendations": recs})
            st = ledger.log_stale_flags(
                lconn, {"sport": args.league, "date": args.date,
                        "market_scan": out.get("market_scan") or {}})
            # The likelihood board's paper book — hoops joined the board
            # on 2026-08-31, and its markets settle from the same
            # player_game_logs the ingest already writes.
            ml = ledger.log_most_likely(
                lconn, {"sport": args.league, "date": args.date,
                        "most_likely": out.get("most_likely") or []})
            if ml:
                print(f"Most likely: {ml} row(s) journaled.")
            settled = ledger.settle_from_history(lconn, connect(), sport=args.league)
            if n or st or settled:
                ledger.export_json(lconn, "web/data/record.json")
                print(f"Journal: {n} {args.league.upper()} pick(s) + {st} "
                      f"stale flag(s) logged, {settled} settled.")
        except Exception as exc:
            print(f"⚠️  NBA journal skipped: {exc}")
        conn.close()

    # §14: the parlay screen runs over the board that just cleared the
    # singles gates. §7 defers to Scalpy 3.0 for the NBA; §8 tightens the
    # WNBA hard — spread >= 9 kills favourite star props, Tier 3 is banned in
    # any ticket, and cross-game tickets are banned outright.
    # The outside view: what similar past spots actually did, counted off
    # this LEAGUE's own logs (never the other's — a WNBA minute and an NBA
    # minute are different units). Evidence only, never a price input.
    from engine.pipeline import _attach_comps
    out["comps"] = _attach_comps(out.get("recommendations") or [], args.league)
    from engine.parlays import attach
    attach(out, args.league)

    # The live win-probability track (2026-08-18, Ethan: "we should be
    # showing that for ALL live games") — same wiring as mlb_build and
    # nfl_build: the pull costs one credit for the whole slate and only
    # happens while a game is live; attaching from disk is free.
    try:
        from engine import livelines as _ll
        from engine.sources.oddsapi import NBA_TEAM_ABBR, WNBA_TEAM_ABBR
        _names = WNBA_TEAM_ABBR if args.league == "wnba" else NBA_TEAM_ABBR
        _live_games = [g for g in out.get("games") or []
                       if (g.get("live") or {}).get("state") == "live"]
        if _live_games and args.odds:
            _n, _note = _ll.pull_and_record(args.league, _names)
            if _n:
                print(f"  Live line: {_note}")
        _midnight = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        _tracked = _ll.attach(out.get("games") or [], args.league,
                              since=_midnight)
        if _tracked:
            print(f"  Live line: charting {_tracked} game(s)")
    except Exception as _exc:                                 # noqa: BLE001
        print(f"  ⚠️  live line tracking unavailable: {_exc}")

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p)
    if picks_result:
        c = picks_result["counts"]
        print(f"NBA {args.date}: {c['props_analyzed']} props → "
              f"{c['picks']} pick(s), {c['near_misses']} near-miss(es). "
              f"Wrote {args.out}")
        if picks_result["no_qualifying"]:
            print("No qualifying plays at current lines — correct output, "
                  "not a failure.")
    else:
        print(f"NBA {args.date}: {out['status']}. Wrote {args.out}")


if __name__ == "__main__":
    main()
