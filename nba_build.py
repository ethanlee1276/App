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


def slate_markets(league: str) -> tuple:
    """The markets this league's board prices: the five above, and for the
    NBA the three two-stat combos (`hoops.COMBOS`; Ethan's call,
    2026-10-13) and steals, blocks and turnovers (`hoops.COUNTS`,
    2026-10-14). The WNBA keeps its five — its odds request is its own
    (`oddsapi.SPORT_CONFIG`), and both calls were the NBA's."""
    from engine.hoops import COMBOS, COUNTS
    return SLATE_MARKETS + (tuple(COMBOS) + COUNTS if league == "nba" else ())


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
    def __init__(self, player, market, team=""):
        # THE TEAM RIDES ON THE PROP (2026-10-13). The odds index is keyed
        # by name and market across every game on the pull, and
        # `oddsapi._wrong_game` refuses a price from a game the prop's
        # team is not in — but only when the prop names a team, and this
        # one never did, so a man filed under last season's club took
        # whatever game priced his name.
        self.player, self.market, self.team = player, market, team
        self.lines = []


class _Slate:
    def __init__(self, games, props):
        self.games, self.props = games, props


def player_history(conn, teams: set[str], sport: str = "nba",
                   seasons: list[int] | None = None,
                   roster: dict | None = None,
                   moved: set | None = None) -> dict:
    """{player: {"team", "starter", "minutes": [...], stat: [...]}} newest
    first, last 20 games, for players on tonight's teams.

    ``seasons`` bounds the read. Only 20 games survive the slice no matter
    how many are loaded, so an unbounded query on a backfilled history
    sorts several seasons of rows to throw nearly all of them away — and
    for a player who has not appeared this year it would hand back last
    year's form as if it were current.

    ``roster`` is ``{normalized name: team}`` from the clubs' current
    rosters (`current_teams`). WHERE HE PLAYS NOW (2026-10-13): the logs
    file a man under the club he played for, so on opening night every
    summer move is still under his old team — projected for a game he is
    not in, and priced off whichever game named him. A man the roster
    places keeps only his games FOR THAT CLUB (the spec's reset rule: a
    trade resets the sample), so a new arrival has no prop until he has
    played three games for it — the floor every prop already has. A man
    the roster does not name keeps his history's team: a spelling the two
    feeds disagree on must never cost a player his board. ``moved``
    collects the names whose games for another club were set aside.
    """
    from engine import divisions
    from engine.sources.oddsapi import normalize_name
    hist: dict = {}
    # BOTH SPELLINGS OF A CLUB (2026-10-20). ESPN files six NBA clubs its own
    # way (GS, NY, NO, SA, UTAH, WSH) and the ingest wrote those until
    # 2026-10-14, when it moved to the league's codes — the codes tonight's
    # schedule speaks. A season stored before then and not read again
    # would hand the Warriors' players no history at all on opening night.
    # So the NBA asks for every spelling and files each row under the
    # league's code; the WNBA's rows are read as stored, as its board reads.
    canon = (lambda t: divisions.canonical(sport, t or "")) if sport == "nba" else (lambda t: t or "")
    asked = sorted({sp for t in teams for sp in (divisions.spellings(sport, t) if sport == "nba" else [t])})
    q = ("SELECT player, team, position, period, market, value, opponent, home "
         "FROM player_game_logs WHERE sport=? AND team IN (%s)"
         % ",".join("?" * len(asked)))
    args: list = [sport, *asked]
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args += list(seasons)
    rows = conn.execute(q + " ORDER BY period DESC", args).fetchall()
    now_at: dict = {}
    for r in rows:
        if roster:
            if r["player"] not in now_at:
                now_at[r["player"]] = roster.get(normalize_name(r["player"]))
            club = now_at[r["player"]]
            if club and divisions.canonical(sport, r["team"]) != club:
                if moved is not None:
                    moved.add(r["player"])
                continue
        p = hist.setdefault(r["player"], {"team": canon(r["team"]), "starter": None,
                                          "by_week": {}, "faced": {}})
        wk = p["by_week"].setdefault(r["period"], {})
        wk[r["market"]] = float(r["value"])
        # WHO HE PLAYED, AND WHERE: the pick page labels each past game
        # "vs BOS" as every other league's does, and reads his games
        # against tonight's opponent.
        p["faced"].setdefault(r["period"], (canon(r["opponent"]), 1 if r["home"] in (1, True, "1") else 0))
        if p["starter"] is None and r["market"] == "min":
            p["starter"] = r["position"] == "S"
    for p in hist.values():
        weeks = sorted(p["by_week"], reverse=True)[:20]
        p["minutes"] = [p["by_week"][w].get("min", 0.0) for w in weeks]
        p["dates"] = weeks                      # ISO dates, newest first
        p["opps"] = [p["faced"].get(w, ("", 1))[0] for w in weeks]
        p["homes"] = [p["faced"].get(w, ("", 1))[1] for w in weeks]
        for stat in ("pts", "reb", "ast", "fg3m"):
            p[stat] = [p["by_week"][w].get(stat, 0.0) for w in weeks]
        # PRA is the WNBA spec's headline tier-1 market and it needs no new
        # ingest — it is the sum of three columns we already store. Deriving
        # it here rather than fetching it also guarantees the history and
        # the line refer to the same three numbers.
        p["pra"] = [round(p["pts"][i] + p["reb"][i] + p["ast"][i], 1)
                    for i in range(len(weeks))]
        # The two-stat combos, the same way and for the same reason.
        from engine.hoops import COMBOS, COUNTS, carried
        for combo, (a, b) in COMBOS.items():
            p[combo] = [round(p[a][i] + p[b][i], 1) for i in range(len(weeks))]
        # Steals, blocks and turnovers: only his newest games whose box
        # stored them (`hoops.carried` — a missing row is not a zero), so
        # the list can be shorter than his minutes and lines up with them
        # game for game from the newest.
        if sport == "nba":
            games = [p["by_week"][w] for w in weeks]
            for stat in COUNTS:
                p[stat] = [games[i][stat] for i in range(carried(games, stat))]
    return hist


def current_teams(league: str, fetch=None) -> tuple[dict, list]:
    """``({normalized name: team}, [clubs that would not load])`` from ESPN's
    current rosters (`espnrosters.fetch_league`, the same six-hour cache the
    Rosters page reads), teams in this league's own abbreviations.

    A name on two rosters is left out — two men, or one caught mid-trade —
    so it can never move anybody; so is a club code the league's own map
    (`divisions.MAPS`) does not hold, because one alias the two feeds
    disagree on would otherwise set aside every game a whole club played.
    ``({}, [])`` when the feed cannot be read: every player then keeps the
    team of his newest game, which is what the board did before it asked."""
    from engine import divisions
    from engine.sources import espnrosters
    from engine.sources.oddsapi import normalize_name
    try:
        feed, missed = (fetch or (lambda: espnrosters.fetch_league(league)))()
    except Exception:                                       # noqa: BLE001
        return {}, []
    known = set(divisions.MAPS.get(league) or {})
    seen: dict = {}
    out: dict = {}
    for team, people in (feed or {}).items():
        club = divisions.canonical(league, team)
        for p in people or []:
            k = normalize_name(str(p.get("player") or ""))
            if k:
                seen[k] = seen.get(k, 0) + 1
                out[k] = club
    return ({k: t for k, t in out.items() if seen[k] == 1 and (not known or t in known)},
            list(missed or []))


#: ESPN designations that mean he is not playing tonight — the hoops twin of
#: `nhl_build.OUT_STATUSES`, with the NFL's DOUBTFUL (`rules.RULED_OUT`).
#: Anything else listed (Day-To-Day, Questionable, Probable, GTD) is a man
#: who may play: his number stands, and his picks wait for the lineup.
OUT_STATUSES = ("out", "doubtful", "suspension", "suspended", "injured reserve",
                "ir", "out for season", "inactive", "not with team")


def hoops_injuries(league: str, fetch=None) -> dict:
    """``{normalized name: {"player", "status", "injury"}}`` from ESPN's injury
    board for this league — the newest filing per player, no cleared-to-play
    notices; {} when the board cannot be read (a gap on our side, never a
    claim that everybody is healthy).

    THE ONE GAP WORTH MONEY (docs/WNBA_MODEL.md): "There is no availability
    feed for this league ... the model currently cannot see it." The feed
    existed all along — `espninjuries` carries both leagues for the
    Injuries page — and the build never read it. Two names alike keep the
    worse status: holding a healthy namesake costs a pick, missing a hurt
    one costs a bet."""
    from engine.sources import espninjuries as E
    from engine.sources.oddsapi import normalize_name
    try:
        rows = E.parse_injuries((fetch or (lambda: E.fetch_injuries(league)))())
    except Exception:                                       # noqa: BLE001
        return {}
    out: dict = {}
    for r in E.drop_stale_returns(E.current_rows(rows)):
        if E.is_return(r):
            continue
        k = normalize_name(str(r.get("player") or ""))
        status = str(r.get("status") or "").strip()
        if not k or not status:
            continue
        prev = out.get(k)
        if prev and prev["status"].lower() in OUT_STATUSES:
            continue
        out[k] = {"player": r["player"], "status": status, "injury": r.get("injury") or ""}
    return out


#: How recently an absent man must have played for his absence to be news:
#: within his club's last few games. One out since February is already in
#: every teammate's recent games, and saying "out tonight" on their cards
#: night after night would be noise dressed as a read.
NEW_ABSENCE_GAMES = 3


def absences(hist: dict, injuries: dict) -> dict:
    """``{team: [(player, minutes a game), ...]}`` — tonight's ruled-out men on
    each club who played in one of its last `NEW_ABSENCE_GAMES` games, the
    biggest role first."""
    from engine.sources.oddsapi import normalize_name
    recent: dict = {}
    for h in hist.values():
        recent.setdefault(h["team"], set()).update((h.get("by_week") or {}).keys())
    recent = {t: set(sorted(d, reverse=True)[:NEW_ABSENCE_GAMES]) for t, d in recent.items()}
    out: dict = {}
    for name, h in hist.items():
        inj = injuries.get(normalize_name(name))
        if not inj or inj["status"].strip().lower() not in OUT_STATUSES:
            continue
        if not recent.get(h["team"], set()) & set((h.get("by_week") or {}).keys()):
            continue
        mins = [float(m) for m in (h.get("minutes") or [])[:10]]
        if mins:
            out.setdefault(h["team"], []).append((name, sum(mins) / len(mins)))
    for team in out:
        out[team].sort(key=lambda t: -t[1])
    return out


def _team_rows(hist: dict, team: str, since: str) -> list[dict]:
    """The logs' rows for one club from ``since`` on, rebuilt from the history
    already read — `engine.nba.onoff`'s input, with no second query."""
    return [{"team": team, "period": d, "player": name, "market": m, "value": v}
            for name, h in hist.items() if h.get("team") == team
            for d, stats in (h.get("by_week") or {}).items() if d >= since
            for m, v in stats.items()]


def lineup_card(player: str, market: str, team: str, gone: dict, hist: dict,
                cache: dict | None = None) -> dict | None:
    """What a teammate's absence means for this prop, as the teammate card
    every league's pick draws (the NFL's engine/teammates shape: ``{team,
    out, headline, applied, note}``), or None with nobody out.

    EVIDENCE ONLY. The minutes model has a slot for the minutes a vacancy
    opens (`project_minutes(vacancy_minutes=...)`) and nothing fills it:
    moving the number is a pricing change, and redistribution measured by
    `engine/nba/onoff` has not passed the edge test. So the card says who
    is out and what the logs show when he sat — counted only from his first
    game for this club, so the games before he arrived are not "sat"."""
    from engine.nba import onoff
    away = [(n, m) for n, m in (gone or {}).get(team, []) if n != player]
    if not away:
        return None
    names = ", ".join(f"{n} ({m:.0f} min a game)" for n, m in away[:3])
    card = {"team": team, "out": [n for n, _m in away[:3]], "applied": 1.0,
            "headline": f"Out tonight: {names}",
            "note": ("Shown for you. Those minutes go to the rest of the rotation; our minutes "
                     "model does not move for it, and the book's line may already have.")}
    stat = market if market in onoff.STATS else None
    if stat is None:
        return card
    big = away[0][0]
    key = (team, big, stat)
    cache = {} if cache is None else cache
    if key not in cache:
        first = min((hist.get(big) or {}).get("by_week") or {"": None})
        cache[key] = onoff.inheritance(_team_rows(hist, team, first), team, big, stat)
    res = cache[key]
    b = (res.get("beneficiaries") or {}).get(player)
    if res.get("enough") and b:
        label = {"pts": "points", "min": "minutes", "reb": "rebounds", "ast": "assists",
                 "fg3m": "threes"}[stat]
        card["note"] += (f" In the {res['n_out']} games {big} missed, {player} took "
                         f"{b['without']:.0%} of the team's {label}, against {b['with']:.0%} "
                         f"with {big} on the floor ({b['n_without']} and {b['n_with']} games).")
    return card


def vacancy_for(player: str, team: str, gone: dict, hist: dict, listed: dict, k: float,
                tune=None, cache: dict | None = None) -> float:
    """The minutes tonight's absences open for ``player`` (engine/nba/vacancy):
    ``k`` × the ruled-out regulars' usual minutes, shared over his club's
    rotation — the men who played in its last `NEW_ABSENCE_GAMES` games and
    are not ruled out — by each one's own base minutes. 0.0 with ``k`` 0
    (the verdict has not held) or nobody out, so the slot stays empty."""
    away = (gone or {}).get(team) or []
    if not k or not away:
        return 0.0
    cache = {} if cache is None else cache
    if team not in cache:
        from engine.nba.minutes import base_minutes, role_minutes
        from engine.nba.vacancy import shares
        from engine.hoops import NBA
        out = {n for n, _m in away}
        days = set()
        for h in hist.values():
            if h.get("team") == team:
                days.update((h.get("by_week") or {}).keys())
        recent = set(sorted(days, reverse=True)[:NEW_ABSENCE_GAMES])
        rotation = {}
        for name, h in hist.items():
            if h.get("team") != team or name in out:
                continue
            if str((listed.get(name) or {}).get("status") or "").strip().lower() in OUT_STATUSES:
                continue
            if not recent & set((h.get("by_week") or {}).keys()):
                continue
            mins = [float(m) for m in (h.get("minutes") or [])]
            if len(mins) < 3:
                continue
            rotation[name] = base_minutes(role_minutes(mins)[0], tune or NBA) or 0.0
        cache[team] = shares(sum(m for _n, m in away), rotation, k)
    return float(cache[team].get(player) or 0.0)


def lineup_note(player: str, market: str, team: str, gone: dict, hist: dict,
                cache: dict | None = None) -> str:
    """The teammate card as one sentence, for the Edge card's context."""
    c = lineup_card(player, market, team, gone, hist, cache)
    if not c:
        return ""
    return f"{c['headline']}. {c['note'].replace('Shown for you. ', '')}"


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
    # The book named here is the one the card tells a reader to go to, so
    # the sharp reference is dropped before the shop — see
    # `engine.odds.bettable_lines`, and the fallback there for a line
    # only the sharp book quotes.
    from engine.odds import bettable_lines
    quotes = bettable_lines(quotes)
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
        from engine.sources.nbaespn import fetch_schedule, parse_schedule_day

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
    print(f"  Props buildable     {len(ready) * len(slate_markets(league))}")
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
            from engine.sources.nbaespn import (fetch_schedule,
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


def _board_lines_cached(league: str) -> bool:
    """Is a whole-slate game-lines payload on disk to read for free?

    The pacer decides whether to BUY one (`--board-odds`); this decides
    whether there is one to LOOK AT — nfl_build's `_with_board_cache`, for
    the payload `oddsapi.apply_board_lines_to_slate` writes ("lines" tag)."""
    try:
        from engine.sources.fetch import CACHE_DIR
        return (CACHE_DIR / f"odds_board_{league}_lines.json").is_file()
    except Exception:                                         # noqa: BLE001
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.date.today().isoformat())
    ap.add_argument("--odds", action="store_true",
                    help="buy fresh odds for this slate (spends API credits)")
    ap.add_argument("--cached-odds", action="store_true",
                    help="use the odds already on disk — no purchase")
    # The live line on its own budget lane (launch.NBA_LINES_CLOCK /
    # WNBA_LINES_CLOCK): one board pull for the slate while a game is live.
    ap.add_argument("--live-lines", action="store_true",
                    help="pull the in-play line for live games (its own budget lane)")
    # The game lines on their own (launch.NBA_BOARD_CLOCK): the whole slate's
    # moneyline, spread and total in one three-credit request, for a night the
    # props pull is declined. A cached copy is read free on every build.
    ap.add_argument("--board-odds", action="store_true",
                    help="buy the slate's game lines in one request (spends three API credits)")
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
    # ESPN FOR BOTH LEAGUES (the NBA since 2026-10-14: the league's own CDN
    # answers the box 403 Forbidden for every file — `engine/sources/nbaespn`).
    if args.league == "wnba":
        # ESPN, not the WNBA CDN. The CDN path was written by analogy with
        # the NBA's and never returned JSON on a real machine; this is the
        # endpoint family that already carries NFL scores and the whole
        # college football board here.
        from engine.sources.wnbaespn import fetch_schedule, parse_schedule_day
    else:
        from engine.sources.nbaespn import fetch_schedule, parse_schedule_day

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
        # NO PRESEASON (NBA readiness, 2026-09-24): starters play half their
        # minutes, so a regular-season projection of a preseason game is an
        # over the model has not earned. The games are dropped before
        # anything prices them; a preseason-only day publishes an honest
        # note, not picks.
        pre = [g for g in games if g.get("preseason")]
        games = [g for g in games if not g.get("preseason")]
        if pre and not games:
            out.update(status="preseason",
                       note=f"{len(pre)} preseason game(s) today — starters play half their "
                            f"minutes, so there are no picks until the regular season.")
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
    # The slate's game lines for the Pick of the Day (`potd.game_lines`),
    # filled once the odds are on the slate; empty on a night with none.
    potd_lines: list = []
    # What the game report needs that the board does not carry (engine/
    # leaguereport.nba_meta), filled below once the logs are read.
    _gr_meta: dict = {}
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
        # TONIGHT'S SCHEDULE SPOTS (engine/nba/schedspots): the rest bucket
        # the minutes model reads, the trip, the clock, the altitude, and
        # (once the lines are in, below) the blowout watch. Context on the
        # Toolbox; nothing here prices.
        from engine.nba import schedspots as _ss
        out["schedule_spots"] = _ss.spots(games, sched_days, args.date, args.league,
                                          {t: schedule_density(sched_days, t, args.date) for t in teams})
        # This season and last: early in a year a player's most recent 20
        # games run back into the previous season, so one is too few — and
        # six is a different player.
        from engine.seasons import recent_seasons
        # WHO PLAYS WHERE, AND WHO IS HURT (2026-10-13). The clubs' current
        # rosters place each man before his logs are read (`player_history`),
        # and ESPN's injury board — fetched for the Injuries page all along,
        # read by no build — says who sits tonight.
        roster, roster_missed = current_teams(args.league)
        injuries = hoops_injuries(args.league)
        moved: set = set()
        hist = player_history(conn, teams, sport=args.league,
                              seasons=recent_seasons(args.league, args.date),
                              roster=roster, moved=moved)
        from engine.sources.oddsapi import normalize_name as _nn
        listed = {p: injuries[_nn(p)] for p in hist if _nn(p) in injuries}
        gone = absences(hist, injuries)
        # THE MINUTES THOSE ABSENCES OPEN (engine/nba/vacancy), only once
        # nbavacancy.py's held-out verdict holds; k 0 leaves the slot empty.
        from engine.nba import vacancy as _vac
        _vac_k = _vac.k_for(args.league)
        _vac_cache: dict = {}
        out["availability"] = {
            "rosters_read": bool(roster), "roster_clubs_missed": sorted(roster_missed),
            "moved": sorted(moved),
            "injuries_read": bool(injuries),
            "listed": len(listed),
            "out": sum(1 for i in listed.values() if i["status"].strip().lower() in OUT_STATUSES),
        }
        # An unreadable feed prints as a warning (⚠️), so the journal hears
        # about it once (launch._keep_build_log) instead of never.
        print((f"Rosters: {len(roster)} player(s) placed by the clubs' current rosters"
               + (f" (⚠️ {len(roster_missed)} club(s) would not load)" if roster_missed else ""))
              if roster else
              "⚠️  Rosters unreadable — each player keeps the team of his newest game")
        if moved:
            print(f"  {len(moved)} player(s) in tonight's teams' logs play for another club now; "
                  f"their games for the old one are set aside: {', '.join(sorted(moved)[:8])}"
                  + (" …" if len(moved) > 8 else ""))
        print(f"Injuries: {len(listed)} designation(s) on tonight's players "
              f"({out['availability']['out']} out)" if injuries else
              "⚠️  Injury board unreadable — nobody is held for it, and that is a gap")
        # THE GAME REPORT'S OWN FACTS (engine/leaguereport): who carries each
        # team over his last ten, the injury report's names on each game,
        # and where each defence gives (engine/hoopsdvp). Never fatal. The
        # defence ratings are the matchup scan's too (below).
        _gr_rt, _gr_last = {}, False
        try:
            from engine import hoopsdvp as _gr_dvp
            from engine.leaguereport import nba_meta as _gr_nba_meta
            try:
                _gr_rt, _gr_last = _gr_dvp.board_ratings(conn, args.league, args.date)
            except Exception:                               # noqa: BLE001
                _gr_rt, _gr_last = {}, False
            _gr_meta = _gr_nba_meta(games, hist, listed, _gr_rt, _gr_last, injuries_read=bool(injuries))
        except Exception as _grx:                           # noqa: BLE001
            print(f"  ⚠️  game report facts skipped: {_grx}")

        slate = _Slate([_Game(g["home"], g["away"], g["kickoff"],
                              g.get("home_name", ""), g.get("away_name", ""))
                        for g in games], [])
        thin_counts = 0
        for player, h in hist.items():
            if len(h["minutes"]) >= 3:
                for stat in slate_markets(args.league):
                    # A count his newest three boxes did not store has no
                    # rate to price (`hoops.carried`): no prop, counted.
                    if len(h.get(stat) or ()) < 3:
                        thin_counts += 1
                        continue
                    slate.props.append(_Prop(player, stat, h["team"]))
        if thin_counts:
            print(f"Steals, blocks, turnovers: {thin_counts} prop(s) not built — fewer than 3 of the "
                  f"player's newest games stored them. Last season's: "
                  f"python3 ingest.py {args.league} --seasons 2025 --refresh")

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
                # A price from a game the player's team is not in, refused
                # (`_Prop.team`) — counted, because a refusal nobody can see
                # looks exactly like a book that never priced him.
                if getattr(res, "wrong_game", 0):
                    odds_note += (f"; {res.wrong_game} price(s) from a game the "
                                  f"player's team is not in, refused")
            except oddsapi.OddsAPIError as exc:
                odds_note = f"odds unavailable: {exc}"

        # THE GAME LINES ON THEIR OWN (2026-10-20, opening night). The only
        # paid pull this board had was the props pull — nineteen credits a
        # game on a small share of the day — so a night the pacer declined
        # it showed no moneyline, spread or total anywhere: Ethan's 76ers @
        # Knicks card read "lines post closer to tip-off" four minutes
        # before tip. The NFL's and college's cheap tier, for basketball:
        # one request for the whole slate (`--board-odds`), read back free
        # from the cache on every build, and never older than a price the
        # event pull already attached (`apply_board_lines_to_slate`). Games
        # under way are left out: the endpoint quotes them in play, and an
        # in-play number is not the game's pre-game line.
        if args.board_odds or _board_lines_cached(args.league):
            try:
                from engine.sources import oddsapi as _boa
                _pre = _Slate([sg for sg, g in zip(slate.games, games)
                               if (g.get("state") or "scheduled") == "scheduled"], [])
                if _pre.games:
                    _bres = _boa.apply_board_lines_to_slate(
                        _pre, sport=args.league, cache_only=not args.board_odds)
                    _how = (f"from 1 request (quota remaining {_bres.quota.remaining})"
                            if args.board_odds else "from the cached pull (no request)")
                    print(f"Game lines: {_bres.games_priced} of {len(_pre.games)} game(s) before "
                          f"tip-off {_how} — {_bres.moneylines} moneyline, {_bres.spreads} spread, "
                          f"{_bres.totals} total.")
            except Exception as exc:                        # noqa: BLE001
                print(f"⚠️  game lines unavailable: {exc}")

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
        # EVERY BOOK'S NUMBER for the men with an open pick and the men on
        # an injury report, kept when it changes (engine/proptape): the line
        # chart with every book on it reads it back (engine/linebooks).
        from engine.proptape import note_for as _tape_note
        print(_tape_note(args.league, slate))

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
        _ss.add_spreads(out.get("schedule_spots") or [], spread_by_team)
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
        # Tonight's defences, rated before any prop is priced: the matchup
        # is now read into the projection (engine/hoopsdvp.projection_mult,
        # measured 2026-09-27), not only shown under the pick.
        try:
            from engine import hoopsdvp as _dvp0
            _dvp_rating, _ = _dvp0.board_ratings(conn, args.league, args.date)
        except Exception as exc:                            # noqa: BLE001
            print(f"⚠️  matchup ratings skipped: {exc}")
            _dvp0, _dvp_rating = None, {}
        census = {"no_real_price": 0, "no_history": 0}
        props = []
        _onoff_cache: dict = {}
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
            _opp = next((g["away"] if g["home"] == h["team"] else g["home"]
                         for g in games if h["team"] in (g["home"], g["away"])), "")
            _dm, _dn = (_dvp0.projection_mult(args.league, _dvp_rating, _opp, prop.market)
                        if _dvp0 else (1.0, ""))
            _inj = listed.get(prop.player) or {}
            _status = str(_inj.get("status") or "").strip()
            _vac_min = vacancy_for(prop.player, h["team"], gone, hist, listed, _vac_k, tune, _vac_cache)
            _mate = lineup_card(prop.player, prop.market, h["team"], gone, hist, _onoff_cache)
            if _mate and _vac_min:
                _mate["note"] = _mate["note"].replace(
                    "our minutes model does not move for it",
                    f"our minutes model gives him {_vac_min:.1f} more of them (measured held out, "
                    f"nbavacancy.py)")
            props.append({
                "dvp_mult": _dm, "dvp_note": _dn,
                "vacancy_minutes": _vac_min,
                # THE INJURY BOARD ON THE PROP: ruled out is a grade-D
                # restriction (no bet, the card says why); listed and
                # playable is held until the lineup confirms, on the Edge
                # board (`evaluate_prop`) and on Most Likely
                # (`likely.admissible` reads `injury_status`). The number
                # itself does not move.
                "injury_status": _status,
                "restriction": _status.lower() in OUT_STATUSES,
                "lineup_note": (f"{_mate['headline']}. {_mate['note'].replace('Shown for you. ', '')}"
                                if _mate else ""),
                "mate_card": _mate,
                # Each game's opponent and home or away, for the pick page.
                "opps": h.get("opps") or [], "homes": h.get("homes") or [],
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
            # The ladders (2026-09-15), same shape, own maps — a rung is
            # never a main line and `_best_rung` reads its own field.
            alt_map, alt_sharp_map = {}, {}
            for pr in slate.props:
                if pr.lines:
                    lines_map[(pr.player, pr.market)] = [
                        {"book": ln.book, "line": ln.line,
                         "over_odds": ln.over_odds, "under_odds": ln.under_odds}
                        for ln in pr.lines]
                for attr, dest in (("alt_lines", alt_map),
                                   ("alt_sharp_lines", alt_sharp_map)):
                    rungs = getattr(pr, attr, None) or []
                    if rungs:
                        dest[(pr.player, pr.market)] = [
                            {"book": ln.book, "line": ln.line,
                             "over_odds": ln.over_odds, "under_odds": ln.under_odds}
                            for ln in rungs]
            dates_map = {name: h.get("dates", []) for name, h in hist.items()}
            # Photos come out of the same box scores that produced the stat
            # history — one table read, no second feed. A player we have
            # never ingested is simply absent and keeps the initials chip.
            from engine.db import player_assets
            recs = shared_recommendations(props, lines_map, dates_map,
                                          tune=tune,
                                          assets=player_assets(conn, args.league),
                                          alt_map=alt_map,
                                          alt_sharp_map=alt_sharp_map)
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
                                              stream_today, todays_rows)
                _today = todays_rows(stream_today())
                _mv = analyze(_today)
                _n_mv = annotate_recommendations(recs, _mv, price=False)
                # Today's tape on every priced pick, for the prop page's
                # own line chart (Ethan, 2026-09-05). Same rows, read once.
                from engine.linemoves import attach_series as _attach_series
                _ns = _attach_series(recs, _today)
                if _ns:
                    print(f"  Line series: {_ns} pick(s) carry today's tape.")
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
            # THE MATCHUP UNDER EVERY PICK (engine/hoopsdvp, 2026-09-27):
            # what tonight's defence allows a game in this stat and where
            # that ranks — and, measured, read into the projection above.
            try:
                from engine import hoopsdvp as _dvp
                _dvp_rt, _dvp_last = _dvp.board_ratings(conn, args.league, args.date)
                _dvp_n = _dvp.attach(recs, _dvp_rt, _dvp_last, args.league)
                print(f"Matchup cards: {_dvp_n} of {len(recs)} pick(s)"
                      f"{' (last season — too few games this season yet)' if _dvp_last else ''}.")
            except Exception as exc:                         # noqa: BLE001
                print(f"⚠️  matchup cards skipped: {exc}")
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
            # THE MONEYLINES TOO (2026-10-15), as the NHL board carries
            # them: the live page's Game Odds read them, and engine/lineopen
            # keeps a game's last pregame line only when both sides are
            # priced — which is what a settled NBA moneyline closes on
            # (ledger._game_close). 0 is "not offered" and is written as
            # nothing.
            by_pair = {(g.home, g.away): g for g in slate.games}
            for gd in out.get("games", []):
                g = by_pair.get((gd["home"], gd["away"]))
                if g is not None:
                    gd["spread"] = g.spread
                    gd["total"] = g.total
                    gd["home_ml"] = g.home_ml or None
                    gd["away_ml"] = g.away_ml or None
        except Exception as exc:
            print(f"⚠️  shared-schema layer skipped: {exc}")

        # THE MATCHUP SCAN (engine/nba/scan, 2026-10-20 — Ethan: "We need
        # offense vs defense ... matchup details ... key matchups and breakout
        # players"): a tale of the tape per game from every team's offence and
        # defence (engine/nba/teams), the key matchups, and a read on every
        # key player — could shine, could struggle, breakout — in the shape
        # the NFL, MLB and NHL scans write. It picks a side for Most Likely
        # (the leans below) and never moves a number. A failure is a line.
        _nba_leans: dict = {}
        _nba_lean_report: dict = {}
        try:
            from engine.nba import onoff as _onoff, scan as _nscan, teams as _nteams
            from engine.nba.pipeline import _face as _nface
            from engine.db import player_assets as _passets
            from engine.gamescan import leans_from_reads as _nleans_of
            from engine.sources.oddsapi import normalize_name as _pn
            _prof = _nteams.board_profiles(conn, args.league, args.date)
            _vacancy = {}
            for _t, _away in (gone or {}).items():
                _big = _away[0][0]
                _first = min((hist.get(_big) or {}).get("by_week") or {"": None})
                _vacancy[_t] = {"out": _away, "inherit": _onoff.inheritance(
                    _team_rows(hist, _t, _first), _t, _big, "pts")}
            _assets = _passets(conn, args.league)
            _faces = {n: (_nface(_assets, n) or "") for n in hist}
            _pulled = {_pn(n) for g in slate.games for n in (getattr(g, "pulled_players", None) or [])}
            _ns = _nscan.scan(out.get("games") or [], hist, _prof,
                              dvp=_gr_rt,
                              spots=out.get("schedule_spots"), listed=listed, vacancy=_vacancy,
                              key_players={r.get("player") for r in out.get("recommendations") or []},
                              out_players={n for n in hist if _pn(n) in _pulled},
                              faces=_faces, nights=_prof.get("nights"))
            out["scan_reads"] = _ns["reads"]
            for _gd in out.get("games") or []:
                _tp = _ns["tapes"].get(f"{_gd['away']}@{_gd['home']}")
                if _tp:
                    for _side in (_gd["away"], _gd["home"]):
                        _tp["sides"][_side]["injuries"] = sorted(
                            ({"player": p, "status": i.get("status") or "", "injury": i.get("injury") or ""}
                             for p, i in (listed or {}).items() if (hist.get(p) or {}).get("team") == _side),
                            key=lambda r: r["player"])
                    _gd["nba_tape"] = _tp
            _nba_leans = _nleans_of(out["scan_reads"])
            _nr = sum(len(v.get("players") or []) for v in _ns["reads"].values())
            print(f"  Matchup scan: {len(_ns['tapes'])} tape(s), {_nr} read(s), {len(_nba_leans)} lean(s) "
                  f"for Most Likely — team numbers {'per 100 possessions' if _prof.get('per100') else 'per game'}"
                  f" ({_prof.get('n', 0)} teams rated)")
            if not _prof.get("per100"):
                print(f"  (pace and per-100 ratings need the shooting columns: python3 ingest.py "
                      f"{args.league} --seasons 2025 --refresh)")
        except Exception as _nsx:                           # noqa: BLE001
            print(f"  ⚠️  NBA matchup scan skipped: {_nsx}")

        # THE GAME LINES PINNACLE QUOTED, for the Pick of the Day. This
        # board prices no game market and its Most Likely board carries
        # none (none is measured for basketball), and the day's pick is game
        # lines only — so without these the league could never name one.
        # Off the slate's own prices; the pick's bars all still hold
        # (`potd.game_lines`).
        try:
            from engine import potd as _potd_gl
            potd_lines = _potd_gl.game_lines(slate.games, args.date, out.get("games"))
        except Exception as exc:                          # noqa: BLE001
            print(f"⚠️  Pick of the Day game lines skipped: {exc}")

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
            _ml_kinds: dict = {}      # per kind and market — see mlb_build
            # The rows the display caps drop go to the Pick of the Day
            # and nowhere else — popped by `potd.attach`.
            from engine import potd as _potd_keys
            out[_potd_keys.POOL_KEY] = _ml_cut = []
            # THE BOARD THIS BUILD REPLACES, for the hold (likely.HOLD_MARGIN).
            from engine.likely import previous_board as _likely_prev
            _ml_turn: dict = {}
            # The likely legs the −250 cap keeps off — see cfb_build.
            _ml_past_cap: list = []
            out["most_likely"] = _likely_build(
                out.get("recommendations") or [], sport=args.league,
                census=_ml_census, census_by_kind=_ml_kinds, cut=_ml_cut,
                previous=_likely_prev(args.out, args.date), turnover=_ml_turn,
                leans=_nba_leans, lean_report=_nba_lean_report, past_cap=_ml_past_cap)
            out["likely_past_cap"] = _ml_past_cap
            # EVERY READ SAYS WHAT THE BOARD DID WITH IT (engine/gamescan
            # .stamp_picks): his pick on the read's side, the other side, or
            # why there is none — as the NFL's and MLB's reads do.
            if out.get("scan_reads"):
                from engine.gamescan import stamp_picks as _stamp_nba
                _stamp_nba(out["scan_reads"], _nba_lean_report, board=out["most_likely"])
            # EVERY GAME'S MATCHUP PICKS (engine/matchpicks, the NFL's shelf):
            # each read's markets on its side where our number agrees, at a
            # real sportsbook's price — journaled on paper, pooled into the
            # one board below.
            try:
                from engine.matchpicks import build as _mp_build
                out["matchup_picks"] = _mp_build(out.get("games") or [], out.get("scan_reads") or {},
                                                 [], out.get("recommendations") or [], sport=args.league)
                print(f"  Matchup picks: {sum(len(m.get('props') or []) for m in out['matchup_picks'])} "
                      f"across {len(out['matchup_picks'])} game(s)")
            except Exception as _mpx:                       # noqa: BLE001
                print(f"  ⚠️  matchup picks skipped: {_mpx}")
                out["matchup_picks"] = []
            out["likely_turnover"] = _ml_turn
            if not out["most_likely"]:
                from engine.rankfit import load as _rank_store
                if not any(k.startswith(f"{args.league}:")
                           for k in _rank_store()):
                    _ml_census["no market measured to rank yet"] = 1
            out["likely_census"] = _ml_census
            out["likely_census_by_kind"] = _ml_kinds
            out["board_guide"] = _hboards.guide(args.league)
            out["board_shelves"] = _hboards.shelves(args.league,
                                                    out["most_likely"])
        except Exception as exc:                          # noqa: BLE001
            print(f"⚠️  likelihood board skipped: {exc}")
        # THE ONE MOST LIKELY BOARD, as the NFL's (engine/likelyboard) —
        # the same cards on every sport's page. Basketball's matchup check
        # reads the projection's measured Matchup step (engine/hoopsdvp,
        # published on each row's chain), as baseball's reads its own.
        from engine import likelyboard as _lb
        print(f"  {_lb.attach(out, args.league)}")

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
                        from engine.staking import apply_drawdown as _dd_apply
                        _sc, _dr = _dd_apply(recs, dd)
                        print(f"  ⚠️  Drawdown rule active — "
                              f"{args.league.upper()} stakes halved"
                              + (f", {_dr} under the floor and dropped"
                                 if _dr else ""))
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
            # The matchup picks on paper, as the NFL's and MLB's (matchup_prop).
            from engine.matchpicks import journal_rows as _mp_rows
            _mp_n = ledger.log_most_likely(
                lconn, {"sport": args.league, "date": args.date, "games": out.get("games") or [],
                        "most_likely": _mp_rows(out.get("matchup_picks"), "prop")},
                depth=None, category="matchup_prop", grade_label="Matchup")
            if _mp_n:
                print(f"Matchup picks: {_mp_n} row(s) journaled on paper.")
            # The one board, per tier, on paper (engine/likelyboard).
            from engine import likelyboard as _lb
            _lb_n = _lb.journal(lconn, out, args.league, args.date)
            if _lb_n:
                print(f"Most Likely board: {_lb_n} row(s) journaled on paper.")
            # NOT THE PICK OF THE DAY: it is not on the board yet. It is
            # journaled after `potd.attach`, the relock and the publish —
            # see `ledger.journal_potd` at the end of this build.
            if ml:
                print(f"Most likely: {ml} row(s) journaled.")
            settled = ledger.settle_and_export(lconn, connect(), sport=args.league,
                                               logged=n + st)
            if n or st or settled:
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
        if _live_games and (args.odds or args.live_lines):
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

    # THE OPEN-BET TRACKER. Every board but MLB's lacked one, so this
    # league's Live tab read "No open bets on today's card" whatever the
    # journal held — and the tab's two panels (edge bets, Most Likely bets)
    # were empty here by construction. Same assembly as mlb_build's block,
    # behind one call (engine/livepicks.attach_tracker); a failure lands in
    # the JSON as `live_picks_error`, where the page can see it.
    from engine.livepicks import attach_tracker as _attach_tracker
    _tn = _attach_tracker(out, args.league)
    # THE PICK OF THE DAY, over the likelihood board this build just
    # assembled (engine/potd). One hook, every sport, so the bar cannot
    # drift between leagues; a failure lands in the JSON.
    from engine import potd as _potd
    # THE EXCHANGE'S FAIR BEFORE THE SELECTOR READS THE ROW. Order is
    # load-bearing: `potd.attach` picks off these rows, so a board
    # priced after the pick was chosen would carry exchange numbers
    # and a pick made without them — which looks like nothing wrong.
    from engine import exchangefair as _xf
    print(_xf.attach_to_board(out, args.league))
    # EVERY VENUE'S PRICE ON EVERY GAME, and the pregame record of them
    # that `engine/crowdfit` measures (engine/crowd). Never raises.
    from engine import crowd as _crowd
    print(_crowd.attach_to_board(out, args.league))
    # THE OPENING LINES, kept and compared (engine/lineopen) — after the crowd
    # hook, whose money split the against-the-money note reads.
    from engine import lineopen as _lo
    print(_lo.attach_to_board(out, args.league))
    # THE GAME REPORT (engine/leaguereport; Ethan, 2026-10-20: "I want you
    # too do all of it besides D"): every game written out, the NFL's
    # report in basketball's terms. Last of the game hooks, for the NFL's
    # reason: its market section reads the crowd and the opener.
    from engine import leaguereport as _lgr
    print(f"  {_lgr.attach(out, args.league, meta=_gr_meta, out=args.out)}")
    _pn = _potd.attach(out, args.league, lines=potd_lines)
    if _pn:
        print(_pn)
    if _tn:
        print(f"Open-bet tracker: {_tn}")
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    from engine import ledger as _led
    # THE DAY'S CLAIM OUTRANKS TONIGHT'S BOARD. `potd.build` above
    # chose from the rows on the board just now; if this sport already
    # locked a Pick of the Day today, that one is the day's pick and
    # this puts it back. Read-only, never fatal, and a no-op until a
    # lock exists — see `ledger.relock_potd` and `potd.relock`.
    #
    # IT RUNS BEFORE PUBLISH BECAUSE THE FILE IS THE CARD. The journal
    # is opened further down, long after the board has been written,
    # so a swap made there would never reach the page — which is how
    # the MLB card spent 2026-09-15 showing a below-bar lean while the
    # record held a pick made that morning.
    # THE GAME LINES BESIDE THE BOARD: a pick named from one is found there
    # when a later build re-points the card at the day's lock.
    out["pick_of_the_day"] = _led.relock_potd(
        out.get("pick_of_the_day") or {}, (out.get("most_likely") or []) + potd_lines)
    # HOW CURRENT THE STATS THE MODEL READ ARE (engine/freshness), on the
    # board for the page's banner and the build's self-check.
    from engine import freshness as _fresh
    _fresh.stamp_board(out, str(out.get("sport") or "nba"))
    gate.publish(out, p)
    # The light copy the Home page draws first (engine/lightboard),
    # published the same way so the paywall strips the same keys.
    try:
        from engine import lightboard
        _, _lfull = gate.publish(lightboard.light(out, str(out.get("sport") or "")), lightboard.light_path(p))
        print(lightboard.report(gate.board_source(p), _lfull))
    except Exception as _lexc:                                # noqa: BLE001
        print(f"⚠️  Light board skipped: {_lexc}")
    # TONIGHT IN FANTASY POINTS (engine/fantasy_daily, 2026-10-27): the
    # board's projections added up, beside it. Never fatal.
    from engine import fantasy_daily as _fd
    print("  " + _fd.build(str(out.get("sport") or args.league), out, p))
    # AND THE PICK OF THE DAY, to its own book — HERE, once it exists and
    # the relock above has re-pointed it at today's lock. The journal
    # block runs before `potd.attach`, so journaling it there recorded
    # nothing on every build from 2026-09-15 to 2026-10-14. Under the
    # league that made it (a WNBA pick goes to the bench's book).
    _jn = _led.journal_potd(out.get("pick_of_the_day") or {})
    if _jn:
        print(_jn)
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
