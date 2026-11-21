"""Was the report right? A finished game's report, read against its box score (2026-11-16).

Ethan, 2026-11-16, with a finished Pacers at 76ers page: "We should be able to
tell after the game on this screen if the matchups that we reported were good
or not, or if someone was like a breakout target or a favorable candidate, we
should report on if they actually did good or not, and if we were correct in
our game report. In all of our offense and defense matchup, we should report on
if we were correct on that or not too. Like, people should be able to go back
and still look at this data and see if we were right or not."

The picks, the parlays and the call on who wins were graded already
(engine/gameresults, js/report.js). What was not graded was everything else
the report says, the reads. Now, on a finished game, each read is read against
the box score (the history database's player_game_logs, the record's own
source, located by the record's own clause, ledger._hist_where):

  * A PLAYER'S READ — a matchup read ("Who's guarding who"), a breakout
    candidate or a fade ("Players to watch"), a starting pitcher or goalie, an
    angle: his number in the stat the read leans on (its `lean`, else his
    position's stat, DEFAULT_STAT), against his own average over his last
    LAST_N games before this one. A favorable read is right when he beat it,
    an unfavorable one when he fell short. A player with no line in a box that
    has his team's did not play; fewer than MIN_N games before this one is no
    average, and the number is shown without a verdict.
  * AN OFFENSE AGAINST A DEFENSE — the claims the report wrote beside its lines
    (`claims`, one a line or None): a team's stat against its own average (the
    run game the trenches gave an edge, the shots a hockey team was expected to
    pile up), the stat a defense was said to give up or hold down against the
    number it allows a game, and basketball's key matchups, the offense's unit
    on the night (engine/nba/teams.season_profiles, the same arithmetic as its
    season's) against its own number coming in.

Each graded card and line carries `grade` (`grades` on a list, aligned with its
items), and the report a summary (`graded`) and a first section, "How this
report did". Nothing here moves a number or a pick. Standard library only;
`grade` never raises.
"""
from __future__ import annotations

#: His last games before this one, for his average; fewer than MIN_N is none.
LAST_N, MIN_N = 10, 2
#: A team's last games, for its own average.
TEAM_LAST_N = 10
#: Bumped when the grading or its words change, so a final graded and archived
#: before is graded again once (gamereport._graded_from_archive). 2: the call
#: said "right — Celtics, our call, won", 2026-11-16. 3: the report's numbers,
#: its injury report and its touchdown chances checked too, a basketball
#: player who sat never graded on a zero, his minutes beside a grade, the best
#: calls and the biggest misses (engine/reportfacts), 2026-11-16. 4: in plain,
#: player-neutral words ("31 points; the last 2 games averaged 26"), the lines
#: said as the favorite and the total, our pick to win in the past tense, the
#: standouts weighed fairly on a count near nothing and kept as rows for the
#: game's page (`best_rows`, `worst_rows`), 2026-11-16.
GRADE_VERSION = 4
#: The basketball leagues, whose box files a man who sat with zero minutes.
HOOPS = ("nba", "wnba", "cbb")

#: The stat a read is graded on when it names none: by league, then position
#: ("" is anyone else).
DEFAULT_STAT = {
    "nfl": {"QB": "pass_yds", "RB": "rush_yds", "FB": "rush_yds", "WR": "rec_yds", "TE": "rec_yds", "": "rec_yds"},
    "cfb": {"QB": "pass_yds", "RB": "rush_yds", "FB": "rush_yds", "WR": "rec_yds", "TE": "rec_yds", "": "rec_yds"},
    "nba": {"": "pts"}, "wnba": {"": "pts"}, "cbb": {"": "pts"},
    "nhl": {"G": "saves", "": "points"},
    "mlb": {"P": "strikeouts", "SP": "strikeouts", "RP": "strikeouts", "": "total_bases"},
}
#: The summed markets, and their parts as the box score stores them.
SUMS = {"pra": ("pts", "reb", "ast"), "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"),
        "reb_ast": ("reb", "ast"), "rush_rec_yds": ("rush_yds", "rec_yds"),
        "pass_rush_yds": ("pass_yds", "rush_yds", "rec_yds")}
#: A yes-or-no market is a read's last choice: a count says more.
YES_NO = ("anytime_td", "anytime_goal", "first_td", "first_basket")
#: Each stat in words: (one, many).
STAT_WORDS = {
    "pass_yds": ("passing yard", "passing yards"), "rush_yds": ("rushing yard", "rushing yards"),
    "rec_yds": ("receiving yard", "receiving yards"), "receptions": ("catch", "catches"),
    "rush_att": ("carry", "carries"), "carries": ("carry", "carries"), "pass_td": ("touchdown pass",
    "touchdown passes"), "pass_tds": ("touchdown pass", "touchdown passes"),
    "anytime_td": ("touchdown", "touchdowns"), "rush_rec_yds": ("rushing and receiving yard",
    "rushing and receiving yards"), "pass_rush_yds": ("yard from scrimmage", "yards from scrimmage"),
    "pts": ("point", "points"), "reb": ("rebound", "rebounds"), "ast": ("assist", "assists"),
    "fg3m": ("three", "threes"), "pra": ("point, rebound and assist", "points, rebounds and assists"),
    "pts_reb": ("point and rebound", "points and rebounds"), "pts_ast": ("point and assist", "points and assists"),
    "reb_ast": ("rebound and assist", "rebounds and assists"), "stl": ("steal", "steals"),
    "blk": ("block", "blocks"), "tov": ("turnover", "turnovers"),
    "sog": ("shot on goal", "shots on goal"), "points": ("point", "points"), "goals": ("goal", "goals"),
    "assists": ("assist", "assists"), "saves": ("save", "saves"), "anytime_goal": ("goal", "goals"),
    "hits": ("hit", "hits"), "total_bases": ("total base", "total bases"), "strikeouts": ("strikeout",
    "strikeouts"), "outs": ("out", "outs"),
}
#: Basketball's units as a night reads them (engine/nba/teams): how each is said.
UNIT_WORDS = {
    "ortg": ("scored", "{v:.1f} points per 100 possessions"), "efg": ("shot", "an effective {p}"),
    "fg3m": ("made", "{n} threes"), "oreb_pct": ("grabbed", "{p} of its own misses"),
    "tov_pct": ("turned it over on", "{p} of its possessions"), "ftr": ("got to the line", "{v:.2f} free throws a shot"),
    "pts": ("scored", "{n} points"), "reb": ("grabbed", "{n} rebounds"), "tov": ("turned it over", "{n} times"),
}
#: The groups the summary counts, in the order it says them.
GROUPS = (("matchups", "Matchup reads"), ("candidates", "Breakout candidates"), ("fades", "Fades"),
          ("starters", "Starters"), ("angles", "The angles"), ("units", "Offense against defense"),
          ("script", "How the game would go"))
#: How each group's right answer is said.
RIGHT_WORDS = {"candidates": "beat their average", "fades": "fell short of it"}


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _words(stat: str, v) -> str:
    one, many = STAT_WORDS.get(stat, (stat.replace("_", " "), stat.replace("_", " ")))
    return f"{_num(v)} {one if float(v) == 1 else many}"


def _and(xs) -> str:
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def _norm(name) -> str:
    from .gameresults import norm
    return norm(name)


# --- where the game sits in the box-score table ------------------------------------------------
def _nfl_week(label: str):
    from .ledger import _NFL_WEEK_DATE
    m = _NFL_WEEK_DATE.match(str(label or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _game_clause(sport: str, g: dict, label: str) -> tuple[str, list] | None:
    """The record's own clause for this game's rows (ledger._hist_where):
    football by its season and week, every other league by its day."""
    if sport == "nfl":
        if not _nfl_week(label):
            return None
        from .ledger import _hist_where
        return _hist_where({"sport": sport, "date": label})
    day = str((g or {}).get("date") or "")[:10]
    if len(day) != 10:
        return None
    return "sport=? AND period=?", [sport, day]


def _before_clause(sport: str, g: dict, label: str) -> tuple[str, list] | None:
    """Every game before this one, this season and last."""
    if sport == "nfl":
        wk = _nfl_week(label)
        if not wk:
            return None
        s, w = wk
        return ("sport=? AND season >= ? AND (season < ? OR (season = ? AND period < ?))",
                [sport, s - 1, s, s, f"{w:03d}"])
    day = str((g or {}).get("date") or "")[:10]
    if len(day) != 10:
        return None
    import datetime as _dt
    try:
        floor = (_dt.date.fromisoformat(day) - _dt.timedelta(days=400)).isoformat()
    except ValueError:
        return None
    return "sport=? AND period < ? AND period >= ?", [sport, day, floor]


def _value(stats: dict, stat: str):
    if stat in SUMS:
        parts = [_f(stats.get(p)) for p in SUMS[stat]]
        return None if any(p is None for p in parts) else sum(parts)
    return _f(stats.get(stat))


def _parts(stat: str) -> tuple:
    return SUMS.get(stat, (stat,))


class Box:
    """One game's box score: each player's numbers and each team's totals."""

    def __init__(self, rows):
        self.players: dict = {}
        self.teams: dict = {}
        for player, team, market, value in rows:
            v = _f(value)
            if v is None or not player:
                continue
            p = self.players.setdefault(_norm(player), {"player": player, "team": team, "stats": {}})
            p["stats"][market] = v
            t = self.teams.setdefault(team, {})
            t[market] = t.get(market, 0.0) + v

    def has(self, team: str) -> bool:
        return bool(self.teams.get(team))


def box(conn, sport: str, g: dict, label: str, markets) -> Box | None:
    """This game's rows for its two clubs, or None when the clause cannot be
    written. An empty Box is a box score not in yet."""
    where = _game_clause(sport, g, label)
    if where is None or conn is None:
        return None
    clause, args = where
    mk = sorted({m for st in markets for m in _parts(st)})
    if not mk:
        return Box([])
    q = (f"SELECT player, team, market, value FROM player_game_logs WHERE {clause} "
         f"AND market IN ({','.join('?' * len(mk))}) AND team IN (?, ?)")
    return Box(conn.execute(q, (*args, *mk, g.get("home"), g.get("away"))).fetchall())


def history(conn, sport: str, g: dict, label: str, players: dict) -> dict:
    """``{(player as stored, stat): [values, newest first]}``, his games before
    this one (at most LAST_N), for ``players`` = {name as stored: {stats}}."""
    where = _before_clause(sport, g, label)
    if where is None or not players or conn is None:
        return {}
    clause, args = where
    mk = sorted({m for sts in players.values() for st in sts for m in _parts(st)}
                | ({"min"} if sport in HOOPS else set()))
    names = sorted(players)
    q = (f"SELECT player, market, season, period, value FROM player_game_logs WHERE {clause} "
         f"AND player IN ({','.join('?' * len(names))}) AND market IN ({','.join('?' * len(mk))})")
    games: dict = {}
    for player, market, season, period, value in conn.execute(q, (*args, *names, *mk)).fetchall():
        v = _f(value)
        if v is None:
            continue
        games.setdefault(player, {}).setdefault((season, str(period)), {})[market] = v
    out: dict = {}
    for player, by_game in games.items():
        order = sorted(by_game, reverse=True)
        if sport in HOOPS:
            # A night he sat (the box files him with zero minutes) is no game of his.
            order = [k for k in order if by_game[k].get("min") != 0.0]
        for st in players.get(player) or ():
            vals = [_value(by_game[k], st) for k in order]
            out[(player, st)] = [v for v in vals if v is not None][:LAST_N]
    return out


def team_history(conn, sport: str, g: dict, label: str, team: str, stat: str) -> list:
    """The club's per-game totals in ``stat`` before this game, newest first."""
    where = _before_clause(sport, g, label)
    if where is None or conn is None:
        return []
    clause, args = where
    mk = list(_parts(stat))
    q = (f"SELECT season, period, market, SUM(value) FROM player_game_logs WHERE {clause} "
         f"AND market IN ({','.join('?' * len(mk))}) AND team=? GROUP BY season, period, market")
    games: dict = {}
    for season, period, market, total in conn.execute(q, (*args, *mk, team)).fetchall():
        v = _f(total)
        if v is not None:
            games.setdefault((season, str(period)), {})[market] = v
    vals = [_value(games[k], stat) for k in sorted(games, reverse=True)]
    return [v for v in vals if v is not None][:TEAM_LAST_N]


# --- one read -----------------------------------------------------------------------------------
def favors(verdict: str) -> str | None:
    """Which way a card's read points: "more" for a favorable read or a
    breakout candidate, "less" for an unfavorable one or a fade."""
    v = str(verdict or "").lower()
    if v in ("favorable", "up"):
        return "more"
    if v in ("unfavorable", "down"):
        return "less"
    return None


def stat_for(sport: str, item: dict) -> str:
    """The stat a card is graded on: the first count its read leans on, a
    yes-or-no market only when it names nothing else, else its position's."""
    lean = [str(m) for m in (item or {}).get("lean") or [] if m]
    counts = [m for m in lean if m not in YES_NO]
    if counts:
        return counts[0]
    if lean:
        return lean[0]
    table = DEFAULT_STAT.get(sport) or {"": "pts"}
    pos = str((item or {}).get("pos") or "").upper()
    return table.get(pos) or table.get("")


def verdict_of(way: str, actual: float, avg: float) -> str:
    if actual == avg:
        return "even"
    return "right" if (actual > avg) == (way == "more") else "wrong"


def player_grade(sport: str, item: dict, bx: Box | None, hist: dict, way: str | None = None) -> dict | None:
    """One card's grade: {"stat", "actual", "avg", "n", "status", "words"}."""
    way = way or favors(item.get("verdict"))
    if not way or not item.get("player"):
        return None
    stat = item.get("stat") or stat_for(sport, item)
    team = item.get("team") or ""
    if bx is None or not bx.teams:
        return {"stat": stat, "status": "pending", "words": "Waiting on the box score."}
    mine = bx.players.get(_norm(item["player"]))
    if mine is None:
        if team and not bx.has(team):
            return {"stat": stat, "status": "pending", "words": "Waiting on the box score."}
        return {"stat": stat, "status": "dnp", "words": "Didn’t play."}
    if sport in HOOPS and _f(mine["stats"].get("min")) == 0.0:
        # The NBA's box files a man who sat with zero minutes and zeros.
        return {"stat": stat, "status": "dnp", "words": "Didn’t play."}
    actual = _value(mine["stats"], stat)
    if actual is None:
        return {"stat": stat, "status": "dnp", "words": f"No {STAT_WORDS.get(stat, (stat, stat))[1]} in the box score."}
    past = hist.get((mine["player"], stat)) or []
    out = {"stat": stat, "actual": actual}
    if len(past) < MIN_N:
        out.update(status="new", words=f"{_words(stat, actual)}; too few games before this one for an average.")
        return _with_volume(sport, item, mine, hist, stat, out)
    avg = round(sum(past) / len(past), 1)
    st = verdict_of(way, actual, avg)
    head = {"right": "Right", "wrong": "Wrong", "even": "Even"}[st]
    # PLAIN AND PLAYER-NEUTRAL (GRADE_VERSION 4): the night, then the games
    # before it — "Right: 31 points; the last 2 games averaged 26."
    out.update(avg=avg, n=len(past), status=st,
               words=f"{head}: {_words(stat, actual)}; the last {len(past)} games averaged {_num(avg)}.")
    return _with_volume(sport, item, mine, hist, stat, out)


def _with_volume(sport: str, item: dict, mine: dict, hist: dict, stat: str, out: dict) -> dict:
    """WHY A READ MISSED, OR HIT (engine/reportfacts.volume_note): his
    minutes, time on ice, carries, catches or throws beside his grade when
    they were far off his own."""
    from . import reportfacts as F
    vs = F.volume_stat(sport, item)
    if not vs or vs[0] in _parts(stat):
        return out
    note = F.volume_note(sport, item, mine, hist.get((mine["player"], vs[0])) or [])
    if note:
        out["vol"] = note
        out["words"] = f"{out['words']} {note['words']}"
    return out


# --- one offense against one defense -----------------------------------------------------------
def team_grade(sport: str, claim: dict, bx: Box | None, conn, g: dict, label: str) -> dict | None:
    """A team claim's grade, by its kind:

      * "team": the club's stat on the night against its own average (the
        claim's ``base``, else its last TEAM_LAST_N games), the way it favors;
      * "allowed": what the defense's opponent made of each stat (``checks``),
        against the number the defense allows a game;
      * "unit": basketball's unit for the offense on the night
        (engine/nba/teams.season_profiles) against its number coming in."""
    kind = (claim or {}).get("kind")
    if kind not in ("team", "allowed", "unit"):
        return None
    if bx is None or not bx.teams:
        return {"status": "pending", "words": "Waiting on the box score."}
    if kind == "team":
        team, stat, way = claim.get("team"), claim.get("stat"), claim.get("favors")
        if not team or not stat or way not in ("more", "less") or not bx.has(team):
            return None
        actual = _value(bx.teams.get(team) or {}, stat)
        base = _f(claim.get("base"))
        n = None
        if base is None:
            past = team_history(conn, sport, g, label, team, stat)
            if len(past) < MIN_N:
                return None
            base, n = round(sum(past) / len(past), 1), len(past)
        if actual is None:
            return None
        st = verdict_of(way, actual, base)
        span = f" over its last {n} games" if n else " a game"
        return {"stat": stat, "actual": actual, "avg": base, "status": st,
                "words": f"{ {'right': 'Right', 'wrong': 'Wrong', 'even': 'Even'}[st]}: {team} had "
                         f"{_words(stat, actual)} (averages {_num(base)}{span})."}
    if kind == "allowed":
        team, opp = claim.get("team"), claim.get("opp")
        if not team or not opp or not bx.has(opp):
            return None
        said, rights, n = [], 0, 0
        for ch in claim.get("checks") or []:
            stat, pg, side = ch.get("stat"), _f(ch.get("pg")), ch.get("side")
            got = _value(bx.teams.get(opp) or {}, stat) if stat else None
            if got is None or pg is None or side not in ("soft", "hard"):
                continue
            st = verdict_of("more" if side == "soft" else "less", got, pg)
            n += 1
            rights += st == "right"
            said.append((_words(stat, got), st, pg))
        if not n:
            return None
        st = "right" if rights == n else "wrong" if rights == 0 else "split"
        head = {"right": "Right", "wrong": "Wrong", "split": f"{rights} of {n} right"}[st]
        parts = [f"{w} ({'' if n == 1 else (x + '; ')}it allows {_num(pg)} a game)" for w, x, pg in said]
        return {"status": st, "right": rights, "of": n,
                "words": f"{head}: {team} gave up {_and(parts)} to {opp}."}
    # "unit": basketball's offense against defense, on the night's own possessions.
    off, dfn, unit = claim.get("off"), claim.get("def"), claim.get("unit")
    way, base = claim.get("favors"), _f(claim.get("base"))
    if not off or not dfn or not unit or way not in ("more", "less") or base is None:
        return None
    if not (bx.has(off) and bx.has(dfn)):
        return None
    from .nba import teams as T
    day = str((g or {}).get("date") or "")[:10] or "night"
    night = {(off, day): dict(bx.teams.get(off) or {}, opp=dfn), (dfn, day): dict(bx.teams.get(dfn) or {}, opp=off)}
    prof = (T.season_profiles(night, min_games=1).get(off) or {})
    actual = _f(prof.get(unit))
    if actual is None:
        return None
    st = verdict_of(way, actual, base)
    verb, shape = UNIT_WORDS.get(unit, ("had", "{v:.2f} in " + unit))

    def said(v):
        return shape.format(v=v, n=_num(v), p=f"{v * 100:.1f}%")
    head = {"right": "Right", "wrong": "Wrong", "even": "Even"}[st]
    avg = f"{base * 100:.1f}%" if "{p}" in shape else _num(round(base, 1)) if "{n}" in shape else f"{base:.2f}" \
        if unit == "ftr" else f"{base:.1f}"
    return {"stat": unit, "actual": round(actual, 4), "avg": base, "status": st,
            "words": f"{head}: {off} {verb} {said(actual)} against {dfn} (averages {avg})."}


# --- the whole report ----------------------------------------------------------------------------
def _group(section_key: str, item: dict) -> str | None:
    if section_key == "matchups":
        return "matchups"
    if section_key == "watch":
        return "candidates" if item.get("verdict") == "up" else "fades" if item.get("verdict") == "down" else None
    if section_key in ("pitching", "goalies"):
        return "starters"
    return None


def _cards(report: dict):
    """(section key, item) for every player card the report's reads draw."""
    for s in (report or {}).get("sections") or []:
        for b in s.get("blocks") or []:
            if isinstance(b, dict) and b.get("type") == "verdicts":
                for it in b.get("items") or []:
                    if isinstance(it, dict) and it.get("player"):
                        yield s.get("key"), it


def _claim_lists(report: dict):
    """(section key, block) for every list that carries claims."""
    for s in (report or {}).get("sections") or []:
        for b in s.get("blocks") or []:
            if isinstance(b, dict) and b.get("type") == "list" and isinstance(b.get("claims"), list):
                yield s.get("key"), b


def call_line(report: dict, g: dict) -> dict | None:
    """Who we think wins, against the final score."""
    lv = (g or {}).get("live") or {}
    a, h = _f(lv.get("away_score")), _f(lv.get("home_score"))
    if a is None or h is None or a == h:
        return None
    won = g["home"] if h > a else g["away"]
    for s in report.get("sections") or []:
        if s.get("key") == "verdict":
            for b in s.get("blocks") or []:
                if b.get("type") == "winner" and b.get("team"):
                    right = b["team"] == won
                    us = b.get("name") or b["team"]
                    score = f"{_num(max(a, h))}-{_num(min(a, h))}"
                    return {"right": right, "team": b["team"], "won": won,
                            "words": (f"right — {us} won {score}" if right else
                                      f"wrong — we picked {us}; {b.get('other_name') or won} won {score}")}
    return None


def grade(report: dict, g: dict, conn, sport: str, label: str = "") -> dict | None:
    """Every read on a finished game's report, graded in place; the summary,
    also kept on the report as ``graded`` and drawn as its first section.
    None for a game not over; never raises."""
    try:
        return _grade(report, g, conn, sport, label)
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ the report for {g.get('away')}@{g.get('home')} not graded ({type(exc).__name__}: {exc})")
        return None


def _claim_paras(report: dict):
    """(section key, block) for every paragraph that carries a claim."""
    for s in (report or {}).get("sections") or []:
        for b in s.get("blocks") or []:
            if isinstance(b, dict) and b.get("type") == "p" and isinstance(b.get("claim"), dict):
                yield s.get("key"), b


#: The box-score stats that say a man played, and how much, by league.
PRESENCE = {"nba": ("min", "pts"), "wnba": ("min", "pts"), "cbb": ("min", "pts"),
            "nhl": ("toi", "points", "saves")}


def _grade(report: dict, g: dict, conn, sport: str, label: str) -> dict | None:
    if not isinstance(report, dict) or str(((g or {}).get("live") or {}).get("state") or "") != "final":
        return None
    from . import reportfacts as F
    sport = str(sport or report.get("sport") or "").lower()
    cards = list(_cards(report))
    for _k, it in cards:
        it.pop("grade", None)
    lists = list(_claim_lists(report))
    paras = list(_claim_paras(report))
    stats = {stat_for(sport, it) for _k, it in cards}
    kinds = set()
    for cl in [cl for _k, b in lists for cl in b.get("claims") or []] + [b["claim"] for _k, b in paras]:
        if isinstance(cl, dict):
            kinds.add(cl.get("kind"))
            stats.add(cl.get("stat") or "")
            stats.update(ch.get("stat") or "" for ch in cl.get("checks") or [])
            if cl.get("kind") in ("unit", "pace"):
                from .nba import teams as T
                stats.update(T.BOX)
    if "td" in kinds:
        stats.add("anytime_td")
    # What says a man played, and how much (his minutes beside a grade, the
    # injury report, the regulars who sat).
    stats.update(PRESENCE.get(sport) or (F.FOOT_LINES if sport in ("nfl", "cfb") else ()))
    for _k, it in cards:
        vs = F.volume_stat(sport, it)
        if vs:
            stats.add(vs[0])
    stats.discard("")
    bx = box(conn, sport, g, label, stats)
    # His history, one read for the whole report: every graded player's stats.
    want: dict = {}
    if bx is not None:
        for _k, it in cards:
            mine = bx.players.get(_norm(it.get("player")))
            if mine and favors(it.get("verdict")):
                sts = want.setdefault(mine["player"], set())
                sts.add(stat_for(sport, it))
                vs = F.volume_stat(sport, it)
                if vs:
                    sts.add(vs[0])
    hist = history(conn, sport, g, label, want) if want else {}
    counts = {k: {"right": 0, "wrong": 0, "even": 0, "graded": 0, "dnp": 0, "pending": 0} for k, _w in GROUPS}
    marks: list = []

    def count(group, gr):
        if not group or not gr:
            return
        c = counts[group]
        st = gr.get("status")
        if st in ("right", "wrong", "even"):
            c[st] += 1
            c["graded"] += 1
        elif st == "split":
            c["right"] += int(gr.get("right") or 0)
            c["wrong"] += int(gr.get("of") or 0) - int(gr.get("right") or 0)
            c["graded"] += int(gr.get("of") or 0)
        elif st in ("dnp", "pending"):
            c[st] += 1
    for key, it in cards:
        gr = player_grade(sport, it, bx, hist)
        if gr:
            it["grade"] = gr
            grp = _group(key, it)
            count(grp, gr)
            marks.append(F.standout(grp, it, gr, favors(it.get("verdict"))))
    tds, injuries, listed = [], [], set()
    for key, b in lists:
        grades = []
        for cl in b.get("claims") or []:
            gr = None
            if isinstance(cl, dict):
                kind = cl.get("kind")
                if kind == "player":
                    pk = {"player": cl.get("player"), "team": cl.get("team"), "pos": cl.get("pos"),
                          "stat": cl.get("stat"), "lean": cl.get("lean")}
                    mine = bx.players.get(_norm(cl.get("player"))) if bx is not None else None
                    sts = {cl.get("stat") or stat_for(sport, pk)}
                    vs = F.volume_stat(sport, pk)
                    if vs:
                        sts.add(vs[0])
                    extra = history(conn, sport, g, label, {mine["player"]: sts}) if mine else {}
                    gr = player_grade(sport, pk, bx, extra, way=cl.get("favors"))
                    grp = "angles" if key == "angles" else "units"
                    count(grp, gr)
                    marks.append(F.standout(grp, pk, gr, cl.get("favors")))
                elif kind in ("team", "allowed", "unit"):
                    gr = team_grade(sport, cl, bx, conn, g, label)
                    count("units", gr)
                    marks.append(F.standout("units", None, gr, cl.get("favors")))
                elif kind in F.GAME_KINDS:
                    gr = F.claim_grade(sport, cl, bx, g, report)
                    count("script", gr)
                elif kind == "td":
                    gr = F.claim_grade(sport, cl, bx, g, report)
                    if gr:
                        tds.append(gr)
                elif kind == "injury":
                    listed.add(_norm(cl.get("player")))
                    gr = F.claim_grade(sport, cl, bx, g, report)
                    if gr:
                        injuries.append(gr)
            grades.append(gr)
        if any(grades):
            b["grades"] = grades
        else:
            b.pop("grades", None)
    for _key, b in paras:
        b.pop("grade", None)
        gr = F.claim_grade(sport, b["claim"], bx, g, report)
        if gr:
            b["grade"] = gr
            count("script", gr)
    call = call_line(report, g)
    pending = bx is None or not bx.teams
    summary = {"version": GRADE_VERSION, "status": "pending" if pending else "graded",
               "call": call, "groups": [], "right": 0, "graded": 0}
    for key, what in GROUPS:
        c = counts[key]
        if c["graded"] or c["dnp"]:
            summary["groups"].append({"key": key, "what": what, **c})
            summary["right"] += c["right"]
            summary["graded"] += c["graded"]
    # THE NUMBERS BEFORE THE GAME, THE INJURY REPORT AND THE TOUCHDOWN CHANCES
    # (engine/reportfacts), each beside the reads, none counted among them.
    for name, fn in (("ratings", F.ratings_check), ("sim", F.sim_check)):
        x = fn(report, g)
        if x:
            summary[name] = x
    score = F.score_check(report, g, sport)
    if score:
        summary["score"] = score
    miss = F.missed(sport, report, bx, conn, g, label, listed) if not pending else []
    inj = _injury_summary(injuries, miss, sport, F.names_of(report, g))
    if inj and injury_words(inj):
        inj["words"] = injury_words(inj)
        summary["injuries"] = inj
    shot = [t for t in tds if t.get("status") in ("hit", "miss")]
    if shot:
        td = {"n": len(shot), "scored": sum(t["status"] == "hit" for t in shot),
              "expected": round(sum(_f(t.get("p")) or 0.0 for t in shot), 2)}
        td["words"] = (f"{td['scored']} of the {td['n']} players we gave one scored; our chances added up to "
                       f"{td['expected']:.1f}")
        summary["tds"] = td
    best, worst = F.standouts(marks)
    if best:
        summary["best"] = best
        summary["best_rows"] = F.standout_rows(marks, good=True)
    if worst:
        summary["worst"] = worst
        summary["worst_rows"] = F.standout_rows(marks, good=False)
    report["graded"] = summary
    _summary_section(report, summary)
    return summary


def _injury_summary(rows: list, miss: list, sport: str, names: dict) -> dict | None:
    """The injury report's check in counts, and the regulars who sat off it."""
    from . import reportfacts as F
    done = [r for r in rows if r and r.get("status") != "pending"]
    if not done and not miss:
        return None
    out = {"sits": 0, "sat": 0, "plays": 0, "played": 0, "maybe_played": 0, "maybe_sat": 0, "nostats": 0,
           "right": 0, "wrong": 0}
    for r in done:
        says, st = r.get("says"), r.get("status")
        if says == "sits" and st in ("right", "wrong"):
            out["sits"] += 1
            out["sat"] += st == "right"
        elif says == "plays" and st in ("right", "wrong"):
            out["plays"] += 1
            out["played"] += st == "right"
        elif st == "played":
            out["maybe_played"] += 1
        elif st == "sat":
            out["maybe_sat"] += 1
        elif r.get("played") is None:
            out["nostats"] += 1
        if st in ("right", "wrong"):
            out[st] += 1
    out["missed"] = [F.missed_words(m, sport, names) for m in miss]
    out["missed_names"] = [m["player"] for m in miss]
    out["wrong"] += len(miss)
    out["checks_missed"] = sport in F.VOLUME
    return out


def injury_words(inj: dict) -> str:
    """The injury report's check in one sentence's parts."""
    parts = []
    if inj.get("sits"):
        parts.append(f"{inj['sat']} of the {inj['sits']} listed out or doubtful sat" if inj["sits"] > 1 else
                     ("the one listed out or doubtful sat" if inj["sat"] else "the one listed out or doubtful played"))
    if inj.get("plays") == 1:
        parts.append(f"the one listed probable {'played' if inj['played'] else 'sat'}")
    elif inj.get("plays"):
        parts.append(f"{inj['played']} of the {inj['plays']} listed probable played")
    q = int(inj.get("maybe_played") or 0) + int(inj.get("maybe_sat") or 0)
    if q == 1:
        parts.append(f"the one listed questionable or day-to-day {'played' if inj['maybe_played'] else 'sat'}")
    elif q:
        parts.append(f"of the {q} listed questionable or day-to-day, {inj['maybe_played']} played and "
                     f"{inj['maybe_sat']} sat")
    names = inj.get("missed_names") or []
    if names:
        parts.append(f"{len(names)} regular{'s' if len(names) > 1 else ''} sat without being on it "
                     f"({', '.join(names)})")
    elif inj.get("checks_missed"):
        parts.append("no regular sat without being on it")
    return "; ".join(parts)


def summary_lines(summary: dict) -> list:
    """The summary in sentences, as the report's first section says it."""
    out = []
    call = summary.get("call")
    if call:
        out.append(f"Our pick to win: {call['words']}")
    if summary.get("ratings"):
        out.append(f"Our team ratings alone (unproven): {summary['ratings']['words']}")
    if summary.get("sim"):
        out.append(f"Our simulation: {summary['sim']['words']}")
    if summary.get("score"):
        out.append(f"The lines: {summary['score']['words']}")
    for grp in summary.get("groups") or []:
        n, r = int(grp.get("graded") or 0), int(grp.get("right") or 0)
        if not n:
            if grp.get("dnp"):
                out.append(f"{grp['what']}: none to grade ({grp['dnp']} didn’t play)")
            continue
        ok = RIGHT_WORDS.get(grp["key"], "right")
        tail = f"; {grp['dnp']} didn’t play" if grp.get("dnp") else ""
        out.append(f"{grp['what']}: {r} of {n} {ok}{tail}")
    inj = summary.get("injuries")
    if inj and inj.get("words"):
        out.append(f"The injury report: {inj['words']}")
    td = summary.get("tds")
    if td and td.get("words"):
        out.append(f"Touchdown chances: {td['words']}")
    return out


def _summary_section(report: dict, summary: dict) -> None:
    """The report's first section, "How this report did" (replaced, never doubled)."""
    secs = [s for s in report.get("sections") or [] if s.get("key") != "graded"]
    lines = summary_lines(summary)
    blocks = []
    if summary.get("status") == "pending":
        blocks.append({"type": "p", "text": "The box score is not in yet: every read below is graded once it is."})
    if lines:
        blocks.append({"type": "list", "items": [l if l.endswith(".") else l + "." for l in lines]})
    if summary.get("graded"):
        blocks.append({"type": "p", "text": f"In all, {summary['right']} of the report’s {summary['graded']} graded "
                                            f"reads {'was' if summary['right'] == 1 else 'were'} right."})
    if summary.get("best"):
        blocks += [{"type": "h", "text": "What we got most right"}, {"type": "list", "items": list(summary["best"])}]
    if summary.get("worst"):
        blocks += [{"type": "h", "text": "What we got most wrong"}, {"type": "list", "items": list(summary["worst"])}]
    if (summary.get("injuries") or {}).get("missed"):
        blocks += [{"type": "h", "text": "Missing from our injury report"},
                   {"type": "list", "items": list(summary["injuries"]["missed"])}]
    blocks.append({"type": "note", "text": (
        "Each player’s read is graded on the stat it leans on, against the player’s own average over the games "
        "before this one: a favorable read or a breakout candidate is right when the night beat it, an unfavorable "
        "read or a fade when it fell short. An offense against a defense is graded on the night’s numbers against the team’s own, "
        "and how the game would go on its final score. The lines, our team ratings, the simulation, the injury "
        "report and the touchdown chances are checked on their own lines, never counted among the reads. Our picks "
        "and parlays are graded at their own lines, on their cards.")})
    report["sections"] = [{"key": "graded", "title": "How this report did", "blocks": blocks}] + secs
