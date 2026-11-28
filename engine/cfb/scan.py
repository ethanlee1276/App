"""College football's tale of the tape, from our own box scores.

Ethan, 2026-11-23: "We want all the live pages to match each other ... NFL is kind of like the one we want to go off
of." Every other league's game page opens its facts on a Matchup scan: the NFL's units, and the tapes of the NBA, college
basketball and hockey (engine/nba/scan, engine/nhl). College football's scan (engine/gamescan.attach_cfb) ranks each
school's units from CFBD's advanced season table, and on 24 November no college game carried one: the page went from
the money card straight to "No prop prices for this game yet". This is the tape for every college game the CFBD scan
leaves bare, read from what the box already stores and nothing it has to ask for:

  * the scores (``games``, sport 'cfb'), for points a game and allowed;
  * every player's game (``player_game_logs``, sport 'cfb'), summed to the team's: passing and rushing yards, pass
    attempts, carries and the interceptions each passer threw, and the same for the side across the field.

FBS AGAINST FBS ONLY, as engine/cfb/defense rates the defences: a Saturday against an FCS school measures neither
side. Each stat is averaged over the games that carry it (a game with a score and no player rows still counts its
points). LAST SEASON FILLS IN EARLY: a school's numbers are this season's alone from its FULL_GAMES-th FBS game, and
before that last season's carry the rest, by ``games / FULL_GAMES``; the tape says the split while it lasts. Ranks are
out of the FBS schools rated, 1st the best: the most for, the fewest against (interceptions thrown: the fewest).

It never moves a number: the ratings, the lines and the players' own numbers are already inside our chances. The page
draws it in the other tapes' cells (web/js/detail.js nbaScanHTML). Standard library only.
"""
from __future__ import annotations

#: A school's numbers are this season's alone from its this-many-th FBS game.
FULL_GAMES = 6.0

#: The tape's rows: (stat, label, higher is better).
ROWS = (("pts", "Points a game", True), ("opp_pts", "Points allowed a game", False),
        ("pass_yds", "Passing yards a game", True), ("opp_pass_yds", "Passing yards allowed a game", False),
        ("rush_yds", "Rushing yards a game", True), ("opp_rush_yds", "Rushing yards allowed a game", False),
        ("ypa", "Yards a pass attempt", True), ("opp_ypa", "Yards a pass attempt allowed", False),
        ("ypc", "Yards a carry", True), ("opp_ypc", "Yards a carry allowed", False),
        ("ints", "Interceptions thrown a game", False), ("opp_ints", "Interceptions made a game", True))

#: The key matchups: (offence stat, defence stat, the offence said, the defence said — each with its rank as {r}).
MATCHUPS = (("pts", "opp_pts", "scoring ({r} in points a game)", "defense ({r} in points allowed)"),
            ("rush_yds", "opp_rush_yds", "running game ({r} in rushing yards)", "run defense ({r} in rushing yards allowed)"),
            ("pass_yds", "opp_pass_yds", "passing game ({r} in passing yards)", "pass defense ({r} in passing yards allowed)"),
            ("ypc", "opp_ypc", "yards a carry ({r})", "yards a carry allowed ({r})"),
            ("ypa", "opp_ypa", "yards a pass ({r})", "yards a pass allowed ({r})"))
#: An offence in the top third against a defence this share of the league further down (or the reverse).
EDGE_TOP_SHARE = 1 / 3
EDGE_GAP_SHARE = 0.35
#: The most key matchups a game lists.
EDGES_PER_GAME = 4

#: The player rows a team's game is summed from.
MARKETS = ("pass_yds", "pass_att", "pass_int", "rush_yds", "carries")


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def team_games(conn, season: int, before: str | None = None, fbs: set | None = None) -> dict:
    """{(team, day): {opp, pts, opp_pts, pass_yds, pass_att, pass_int, rush_yds, carries, and the opponent's same as
    opp_*}} for the season's FBS-against-FBS games played before ``before`` (an ISO date)."""
    from .defense import fbs_teams
    fbs = fbs_teams(conn, season) if fbs is None else fbs
    cut = str(before)[:10] if before else None
    games: dict = {}
    for day, home, away, hs, as_ in conn.execute(
            "SELECT COALESCE(NULLIF(date, ''), period), home, away, home_score, away_score FROM games "
            "WHERE sport='cfb' AND season=? AND home_score IS NOT NULL AND away_score IS NOT NULL", (int(season),)):
        day = str(day or "")[:10]
        if home not in fbs or away not in fbs or (cut and day >= cut):
            continue
        games[(home, day)] = {"opp": away, "pts": float(hs), "opp_pts": float(as_)}
        games[(away, day)] = {"opp": home, "pts": float(as_), "opp_pts": float(hs)}
    box: dict = {}
    q = ("SELECT period, team, opponent, market, SUM(value) FROM player_game_logs WHERE sport='cfb' AND season=? "
         "AND market IN (%s)" % ",".join("?" * len(MARKETS)))
    args: list = [int(season), *MARKETS]
    if cut:
        q += " AND period < ?"
        args.append(cut)
    for day, team, opp, market, total in conn.execute(q + " GROUP BY period, team, opponent, market", args):
        if team not in fbs or opp not in fbs:
            continue
        box.setdefault((team, str(day)[:10]), {"opp": opp})[market] = float(total or 0.0)
    out = {}
    for key, g in games.items():
        own = box.get(key) or {}
        theirs = box.get((g["opp"], key[1])) or {}
        row = dict(g)
        if own.get("opp") == g["opp"]:
            row.update({m: own[m] for m in MARKETS if m in own})
        if theirs.get("opp") == key[0]:
            row.update({f"opp_{m}": theirs[m] for m in MARKETS if m in theirs})
        out[key] = row
    return out


def season_numbers(rows: list[dict]) -> dict:
    """A school's season from its games: each stat over the games that carry it; the rates over their own sums."""
    def avg(k):
        vals = [r[k] for r in rows if r.get(k) is not None]
        return (sum(vals) / len(vals)) if vals else None

    def rate(num, den):
        pairs = [(r[num], r[den]) for r in rows if r.get(num) is not None and r.get(den)]
        d = sum(b for _a, b in pairs)
        return (sum(a for a, _b in pairs) / d) if d else None
    return {"games": len(rows), "pts": avg("pts"), "opp_pts": avg("opp_pts"),
            "pass_yds": avg("pass_yds"), "opp_pass_yds": avg("opp_pass_yds"),
            "rush_yds": avg("rush_yds"), "opp_rush_yds": avg("opp_rush_yds"),
            "ypa": rate("pass_yds", "pass_att"), "opp_ypa": rate("opp_pass_yds", "opp_pass_att"),
            "ypc": rate("rush_yds", "carries"), "opp_ypc": rate("opp_rush_yds", "opp_carries"),
            "ints": avg("pass_int"), "opp_ints": avg("opp_pass_int")}


def profiles_from(now_games: dict, last_games: dict | None = None) -> dict:
    """{"teams": {school: numbers + ranks + season_weight}, "league": {stat: the schools' average}, "n"}: this
    season's numbers, last season's filling in until FULL_GAMES, ranked among the schools rated."""
    def by_team(games):
        out: dict = {}
        for (team, _day), row in (games or {}).items():
            out.setdefault(team, []).append(row)
        return {t: season_numbers(rs) for t, rs in out.items()}
    now, last = by_team(now_games), by_team(last_games)
    teams: dict = {}
    for t in set(now) | set(last):
        n_now = (now.get(t) or {}).get("games") or 0
        w = 1.0 if t not in last else min(1.0, n_now / FULL_GAMES)
        p = {"games_season": n_now, "games_last": (last.get(t) or {}).get("games") or 0, "season_weight": round(w, 3)}
        for k, _label, _hi in ROWS:
            a, b = (now.get(t) or {}).get(k), (last.get(t) or {}).get(k)
            if a is not None and b is not None:
                p[k] = w * a + (1 - w) * b
            elif a is not None:
                p[k] = a
            elif b is not None and w < 1.0:
                # Last season's alone only while it still counts: a full season's games with no box rows for a
                # stat leave it blank, never last season's under this season's name.
                p[k] = b
        teams[t] = p
    # Ranked among the schools playing this season (a school with last season's games only is not on a slate).
    rated = {t: p for t, p in teams.items() if p["games_season"] > 0}
    for k, _label, hi in ROWS:
        vals = sorted(((p[k], t) for t, p in rated.items() if p.get(k) is not None), reverse=hi)
        for i, (_v, t) in enumerate(vals):
            rated[t].setdefault("ranks", {})[k] = i + 1
    league = {}
    for k, _label, _hi in ROWS:
        vals = [p[k] for p in rated.values() if p.get(k) is not None]
        if vals:
            league[k] = sum(vals) / len(vals)
    return {"teams": rated, "league": league, "n": len(rated)}


def profiles(conn, season: int, before: str | None = None) -> dict:
    """`profiles_from` for tonight's slate: this season's FBS games before ``before`` and last season's whole.

    KEPT UNTIL ITS ROWS CHANGE (engine/logcache), as the college defence ratings are: keyed on the two seasons'
    player logs, the day it stops before, the schools counted as FBS and the scores stored."""
    import hashlib
    from .. import logcache
    from .defense import fbs_teams
    season = int(season)
    fbs = fbs_teams(conn, season)
    scores = conn.execute("SELECT COUNT(*), SUM(home_score + away_score) FROM games WHERE sport='cfb' AND season IN (?, ?)",
                          (season - 1, season)).fetchone()
    extra = {"before": str(before)[:10] if before else None,
             "fbs": hashlib.sha1("|".join(sorted(fbs)).encode()).hexdigest(),
             "scores": [scores[0], scores[1]] if scores else None}
    return logcache.memo(conn, "cfb_tape", "cfb", (season - 1, season),
                         lambda: profiles_from(team_games(conn, season, before, fbs),
                                               team_games(conn, season - 1, None, fbs)),
                         code=(__file__,), extra=extra)


def _cell(v) -> str:
    return "—" if v is None else f"{v:.1f}"


def key_matchups(home: str, away: str, prof: dict) -> list:
    """Where one side's unit meets the other's at the far ends of the FBS, widest gap first: [{team, text, tone,
    gap, unit}]. At most one a unit family per side."""
    teams = (prof or {}).get("teams") or {}
    n = int((prof or {}).get("n") or len(teams) or 1)
    bar, top = max(2, round(n * EDGE_GAP_SHARE)), max(1, round(n * EDGE_TOP_SHARE))
    out = []
    for order, (off_k, def_k, off_w, def_w) in enumerate(MATCHUPS):
        for a, b in ((away, home), (home, away)):
            ra = ((teams.get(a) or {}).get("ranks") or {}).get(off_k)
            rb = ((teams.get(b) or {}).get("ranks") or {}).get(def_k)
            if not ra or not rb:
                continue
            gap = rb - ra
            said_a, said_b = off_w.format(r=_ord(ra)), def_w.format(r=_ord(rb))
            if gap >= bar and ra <= top:
                what = f"{a}'s {said_a} against {b}'s {said_b}"
                out.append({"team": a, "tone": "off", "gap": gap, "unit": off_k, "order": order, "text": f"Edge {a}: {what}"})
            elif -gap >= bar and rb <= top:
                what = f"{b}'s {said_b} against {a}'s {said_a}"
                out.append({"team": b, "tone": "def", "gap": -gap, "unit": def_k, "order": order, "text": f"Edge {b}: {what}"})
    out.sort(key=lambda e: (-e["gap"], e["order"], e["tone"] != "off", e["text"]))
    # The rates say again what the yards say: one edge a side for the run and one for the pass.
    family = {"rush_yds": "run", "opp_rush_yds": "run", "ypc": "run", "opp_ypc": "run",
              "pass_yds": "pass", "opp_pass_yds": "pass", "ypa": "pass", "opp_ypa": "pass"}
    seen, kept = set(), []
    for e in out:
        key = (e["team"], e["tone"], family.get(e["unit"], e["unit"]))
        if key in seen:
            continue
        seen.add(key)
        kept.append(e)
    return kept[:EDGES_PER_GAME]


def season_note(home: str, away: str, prof: dict) -> str:
    """How much of each side's numbers is still last season's."""
    teams = (prof or {}).get("teams") or {}
    bits = []
    for t in (away, home):
        p = teams.get(t) or {}
        w, n = _f(p.get("season_weight")), int(p.get("games_season") or 0)
        if w is None or w >= 0.95:
            continue
        bits.append(f"{t} {n} FBS game{'s' if n != 1 else ''} in, {round(w * 100)}% this season")
    return ("Team numbers blend this season with last: " + "; ".join(bits)) if bits else ""


def tape(home: str, away: str, prof: dict, game: dict | None = None) -> dict:
    """The game's tale of the tape in the other leagues' shape (engine/nba/scan.tape): each side's numbers with
    their FBS ranks, the rows for the page, the key matchups, the points the lines expect, the note and the basis.
    {} when neither school is rated."""
    teams = (prof or {}).get("teams") or {}
    if home not in teams and away not in teams:
        return {}
    n = int((prof or {}).get("n") or len(teams))
    rows = []
    for k, label, _hi in ROWS:
        a, h = (teams.get(away) or {}).get(k), (teams.get(home) or {}).get(k)
        if a is None and h is None:
            continue
        rows.append({"key": k, "label": label, "a": _cell(a), "h": _cell(h),
                     "ar": ((teams.get(away) or {}).get("ranks") or {}).get(k),
                     "hr": ((teams.get(home) or {}).get("ranks") or {}).get(k), "plain": False})
    spread, total = _f((game or {}).get("spread")), _f((game or {}).get("total"))
    if spread is not None and total and total > 0:
        rows.append({"key": "implied", "label": "Points the lines expect tonight",
                     "a": f"{(total + spread) / 2:.1f}", "h": f"{(total - spread) / 2:.1f}",
                     "ar": None, "hr": None, "plain": True})
    if not rows:
        return {}
    return {"rows": rows, "edges": key_matchups(home, away, prof), "teams": n,
            "note": season_note(home, away, prof),
            "basis": (f"Ranks out of {n} FBS teams, 1st the best: the most for, the fewest against (interceptions "
                      "thrown: the fewest). From this season's games between FBS teams, our own box scores. None "
                      "of this moves our numbers: the ratings, the lines and each player's own numbers are already "
                      "inside our chances.")}
