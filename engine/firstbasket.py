"""First basket — who scores an NBA game's first points, by our numbers.

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... We want to be going
after what the data and tools that we have all put together says, not just off
of book lines." And, the same day: "still not seeing ... first basket scored
for NBA yet ... those bets need to show up on the long shot page."

THE RESEARCH (tools/first_basket_study.py over the box's every NBA shot and
free throw, `nba_shots`; runbook IV, 2026-10-31; docs/FIRST_TD_RESEARCH.md).
Every figure fitted on the seasons before the last and scored on the last:

  * 1,471 games with a basket. The team with the game's first shot scores
    the first points 71.9% of the time; the home team 53.8%.
  * WHO SHOOTS FIRST — the opening tip, mostly — is a lasting team trait:
    each team's history of taking the first shot beats a coin on the held-out
    games (log loss 0.6731 against 0.6931).
  * WHICH PLAYER: his share of his team's shots in the FIRST THREE MINUTES of
    its games picks the scorer best — 1.9874 nats on 158 held-out team first
    baskets, against 2.1341 for his share of all its shots, 2.1087 of its
    made shots, 2.1020 of its first-quarter shots and 2.0542 for a third of
    each. Who starts and who the first plays run through is the whole game.

THE MODEL:

  * P(home shoots first) = logistic(logit(HOME_FIRST_SHOT) + logit(rh) −
    logit(ra)), where rh and ra are each team's first-shot rate this season,
    smoothed toward even ((first shots + 2) / (games + 4)). HOME_FIRST_SHOT is
    what the two measured rates imply: 0.538 = q × 0.719 + (1 − q) × 0.281
    gives q = 0.587 for two teams with even tip records.
  * P(home scores first) = q × FIRST_SHOT_SCORES + (1 − q) × (1 −
    FIRST_SHOT_SCORES).
  * His share = EPS + his share of his team's first-three-minute shots this
    season (last season at half weight), normalised over the team's
    candidates — every player with a first-three-minute shot in one of its
    last RECENT_GAMES games.
  * P(he scores first) = P(his team scores first) × his share.

A PICK is a priced player our chance puts clearly above the price: MIN_EV at
the best bettable price, inside FIRST_BASKET_ODDS, one a game — the same bar
as the football boards' first touchdown (engine/firsttd), never the book's
shortest price. A game with no price on file shows its likeliest first scorers
by our numbers with the price that would make each a pick.

GRADED off the same table: the game's first made shot or free throw, by
action order — what the books settle "first basket" on.

Standard library only.
"""
from __future__ import annotations

import math

from . import firsttd as _ftd

#: The team with the game's first shot scores first this often (IV, 1,471 games).
FIRST_SHOT_SCORES = 0.719
#: The home team scores first this often (IV), and the first-shot rate that
#: implies for two teams with even tip records.
HOME_SCORES_FIRST = 0.538
HOME_FIRST_SHOT = (HOME_SCORES_FIRST - (1 - FIRST_SHOT_SCORES)) / (2 * FIRST_SHOT_SCORES - 1)
#: The first three minutes of the first quarter, in seconds left on its clock.
OPENING_S = 12 * 60 - 3 * 60
#: Last season's shots count this much against this season's.
LAST_SEASON = 0.5
#: The floor every candidate's share starts from (the study's 0.02).
EPS = 0.02
#: A candidate took a first-three-minute shot in one of his team's last
#: RECENT_GAMES games — the starters, and whoever the first plays run through.
RECENT_GAMES = 5
#: Smoothing for a team's first-shot rate: (first shots + PRIOR) / (games + 2·PRIOR).
PRIOR = 2

#: The price window and the bar, the football boards' own (engine/firsttd).
FIRST_BASKET_ODDS = _ftd.FIRST_TD_ODDS
MIN_EV = _ftd.MIN_EV
MIN_PROB = _ftd.MIN_PROB
PER_GAME = _ftd.PER_GAME
LIMIT = _ftd.LIMIT
OURS_PER_GAME = _ftd.OURS_PER_GAME

MARKET = "first_basket"
LABEL = "First Basket"


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _clock_s(clock) -> float:
    """Seconds left in the period from "11:45" or "PT11M45.00S"; -1 unknown."""
    c = str(clock or "")
    try:
        if c.startswith("PT"):
            m, s = c[2:].rstrip("S").split("M")
            return int(m) * 60 + float(s)
        if ":" in c:
            m, s = c.split(":")
            return int(m) * 60 + float(s)
    except ValueError:
        pass
    return -1.0


def first_shot_rate(first_shots: int, games: int) -> float:
    """A team's first-shot rate, smoothed toward even."""
    return (first_shots + PRIOR) / (games + 2 * PRIOR)


def home_shoots_first(rh: float, ra: float) -> float:
    """P(the home team takes the game's first shot) from both teams' rates."""
    return 1.0 / (1.0 + math.exp(-(_logit(HOME_FIRST_SHOT) + _logit(rh) - _logit(ra))))


def home_scores_first(q: float) -> float:
    """P(the home team scores the game's first points) from P(first shot)."""
    return q * FIRST_SHOT_SCORES + (1 - q) * (1 - FIRST_SHOT_SCORES)


def shares(players: dict) -> dict:
    """{player: share of his team's first baskets} for one team: EPS plus his
    share of its first-three-minute shots, normalised to one."""
    tot = sum(max(0.0, float(v)) for v in players.values())
    raw = {p: EPS + (max(0.0, float(v)) / tot if tot > 0 else 0.0) for p, v in players.items()}
    z = sum(raw.values()) or 1.0
    return {p: s / z for p, s in raw.items()}


# --- what the shots say (history.db `nba_shots`) ---------------------------------
def _canon(team: str) -> str:
    try:
        from .divisions import canonical
        return canonical("nba", str(team or "").upper())
    except Exception:                                         # noqa: BLE001
        return str(team or "").upper()


def season_of(date: str) -> int:
    """The NBA season a date belongs to, named for the year it starts in
    (engine/seasons: 2026-10-31 is the 2026 season)."""
    try:
        from .seasons import season_of as _so
        return int(_so("nba", str(date)[:10]))
    except Exception:                                         # noqa: BLE001
        y, m = int(str(date)[:4]), int(str(date)[5:7])
        return y if m >= 9 else y - 1


def read(conn, season: int, before: str | None = None) -> dict:
    """{"teams": {team: {"first": n, "games": n}}, "usage": {team: {player:
    weighted first-three-minute shots}}, "recent": {team: {players}}} from
    this season's and last season's first-quarter rows (before ``before``)."""
    q = ("SELECT season, date, game_id, action, player, team, period, clock "
         "FROM nba_shots WHERE season IN (?, ?) AND period = 1")
    args: list = [season, season - 1]
    if before:
        q += " AND date < ?"
        args.append(before)
    games: dict = {}
    for r in conn.execute(q, args):
        g = games.setdefault(r[2], {"season": int(r[0]), "date": str(r[1]), "rows": []})
        g["rows"].append((int(r[3] or 0), str(r[4] or ""), _canon(r[5]), _clock_s(r[7])))
    teams: dict = {}
    usage: dict = {}
    by_team_games: dict = {}
    for gid, g in games.items():
        rows = sorted(g["rows"])
        if not rows:
            continue
        here = {t for _a, _p, t, _c in rows}
        if g["season"] == season and len(here) == 2:
            first_team = rows[0][2]
            for t in here:
                d = teams.setdefault(t, {"first": 0, "games": 0})
                d["games"] += 1
                d["first"] += int(t == first_team)
        w = 1.0 if g["season"] == season else LAST_SEASON
        opening: dict = {}
        for _a, p, t, c in rows:
            if p and c >= OPENING_S:
                opening.setdefault(t, {}).setdefault(p, 0)
                opening[t][p] += 1
        for t, ps in opening.items():
            u = usage.setdefault(t, {})
            for p, n in ps.items():
                u[p] = u.get(p, 0.0) + w * n
            if g["season"] == season:
                by_team_games.setdefault(t, []).append((g["date"], gid, set(ps)))
    recent: dict = {}
    for t, lst in by_team_games.items():
        lst.sort()
        recent[t] = set().union(*(s for _d, _g, s in lst[-RECENT_GAMES:])) if lst else set()
    return {"teams": teams, "usage": usage, "recent": recent}


def candidates(data: dict, team: str) -> dict:
    """{player: weighted first-three-minute shots} for this team's candidates:
    its recent openers, or before it has a game this season, last season's
    eight busiest."""
    t = _canon(team)
    u = data.get("usage", {}).get(t, {})
    rec = data.get("recent", {}).get(t)
    if rec:
        return {p: u.get(p, 0.0) for p in rec}
    return dict(sorted(u.items(), key=lambda kv: -kv[1])[:8])


def game_probs(data: dict, home: str, away: str) -> list:
    """Every candidate's chance of scoring the game's first points."""
    th = data.get("teams", {}).get(_canon(home), {"first": 0, "games": 0})
    ta = data.get("teams", {}).get(_canon(away), {"first": 0, "games": 0})
    q = home_shoots_first(first_shot_rate(th["first"], th["games"]),
                          first_shot_rate(ta["first"], ta["games"]))
    ph = home_scores_first(q)
    rows = []
    for team, pt in ((home, ph), (away, 1.0 - ph)):
        for name, s in shares(candidates(data, team)).items():
            rows.append({"player": name, "team": team, "prob": pt * s,
                         "team_first": round(pt, 4), "first_shot": round(q if team == home else 1 - q, 4),
                         "share": round(s, 4)})
    rows.sort(key=lambda r: -r["prob"])
    return rows


def _who(name: str, team_rows: list):
    """The candidate row a quoted name belongs to: exact, then (initial, surname)."""
    from .sources.oddsapi import normalize_name
    n = normalize_name(name)
    for r in team_rows:
        if normalize_name(r["player"]) == n:
            return r
    parts = n.split()
    if len(parts) >= 2:
        key = (parts[0][:1], parts[-1])
        for r in team_rows:
            rp = normalize_name(r["player"]).split()
            if len(rp) >= 2 and (rp[0][:1], rp[-1]) == key:
                return r
    return None


def board(quotes: dict, games: list, conn=None, date: str = "", why: str = "") -> dict:
    """The NBA's Long Shots board, in engine/firsttd.board's shape:
    {"rows", "picks", "games", "quoted", "ours", "ours_games", "why"}.

    ``quotes`` is {key: {"player", "home", "away", "quotes"}} (the first
    basket market, `oddsapi.FIRST_BASKET_ODDS_TO_MARKET`); ``games`` the
    board's games (home, away, date, kickoff). Shots come from the history
    database (`read`), this season and last at half weight."""
    from .sources.oddsapi import best_scorer_price
    if conn is None:
        from . import db as _db
        conn = _db.connect()
    by_pair: dict = {}
    for qd in (quotes or {}).values():
        by_pair.setdefault((_canon(qd.get("home")), _canon(qd.get("away"))), []).append(qd)
    cache: dict = {}
    rows, n_games, ours, ours_games = [], 0, [], 0
    for g in games or []:
        home, away = g.get("home"), g.get("away")
        if not home or not away:
            continue
        season = season_of(g.get("date") or date)
        if season not in cache:
            cache[season] = read(conn, season, before=str(g.get("date") or date)[:10] or None)
        ranked = game_probs(cache[season], home, away)
        qs = by_pair.get((_canon(home), _canon(away))) or []
        common = {"market": MARKET, "market_label": LABEL, "game": f"{away}@{home}",
                  "matchup": f"{away} @ {home}", "game_date": g.get("date"),
                  "game_kickoff": g.get("kickoff")}
        if not qs:
            top = [r for r in ranked if r["prob"] > 0][:OURS_PER_GAME]
            ours_games += int(bool(top))
            for r in top:
                p = float(r["prob"])
                ours.append({"player": r["player"], "team": r["team"],
                             "opponent": away if r["team"] == home else home, **common,
                             "prob": round(p, 4), "team_first": r["team_first"], "share": r["share"],
                             "fair_odds": _ftd.fair_odds(p), "need_odds": _ftd.need_odds(p),
                             "priced": False})
            continue
        n_games += 1
        for qd in qs:
            hit = _who(qd.get("player") or "", ranked)
            if hit is None:
                continue
            best = best_scorer_price(qd.get("quotes") or [])
            if not best:
                continue
            p, odds = float(hit["prob"]), int(best["yes_odds"])
            imp, ev = _ftd.implied(odds), _ftd.expected_return(p, odds)
            team = hit["team"]
            rows.append({"player": qd.get("player") or hit["player"], "team": team,
                         "opponent": away if team == home else home, **common,
                         "side": "YES", "line": 0.5, "odds": odds, "book": best.get("book", ""),
                         "prob": round(p, 4), "model_prob": round(p, 4),
                         "team_first": hit["team_first"], "share": hit["share"],
                         "implied": round(imp, 4), "implied_prob": round(imp, 4),
                         "ev": round(ev, 4), "ev_per_unit": round(ev, 4),
                         "fair_odds": _ftd.fair_odds(p), "need_odds": _ftd.need_odds(p), "priced": True,
                         "primary_reason": (f"{team} score first {hit['team_first']:.0%} by the tip · "
                                            f"his share {hit['share']:.0%}"),
                         "reasons": [
                             f"{team} take the game's first shot {hit['first_shot']:.0%} of the time by both "
                             f"teams' tip records this season, and the team with the first shot scores first "
                             f"{FIRST_SHOT_SCORES:.0%} of the time (1,471 games).",
                             f"He takes {hit['share']:.0%} of {team}'s shots in the first three minutes of "
                             f"its games — the share that picks the first scorer best.",
                             f"Our chance {p:.1%} against {imp:.1%} in the price ({ev:+.0%} expected return).",
                         ]})
    rows.sort(key=lambda r: -r["prob"])
    picks = _ftd.pick([dict(r) for r in rows])
    for r in picks:
        r["grade"] = LABEL
        r["edge"] = round(r["prob"] - r["implied"], 4)
        r["stake_units"] = 0.1
        r["expected_opportunities"] = f"{r['share']:.0%}"
    ours.sort(key=lambda r: (str(r.get("game_kickoff") or ""), r["game"], -r["prob"]))
    out = {"rows": rows, "picks": picks, "games": n_games, "quoted": len(rows),
           "ours": ours, "ours_games": ours_games}
    if not rows:
        out["why"] = why_empty(why)
    return out


WHY_BUDGET = ("No first-basket prices were bought for tonight's games yet: the odds budget "
              "held the player pull. Below, who scores first by our numbers and the price "
              "that would make each one a pick.")
WHY_LATER = ("First-basket prices post closer to tip-off. Below, who scores first by our "
             "numbers and the price that would make each one a pick.")


def why_empty(note: str = "") -> str:
    n = str(note or "").lower()
    if "budget" in n or "held" in n or "capped at 0" in n:
        return WHY_BUDGET
    return WHY_LATER


def report(b: dict) -> str:
    """The build log's line."""
    unpriced = (f"; our top first scorers shown unpriced for {b['ours_games']} game(s)"
                if b.get("ours_games") else "")
    if not b.get("games"):
        return f"  First basket: no first-basket prices on this pull{unpriced}"
    return (f"  First basket: {b['quoted']} quoted player(s) across {b['games']} game(s); "
            f"{len(b['picks'])} pick(s) our chance puts {MIN_EV:.0%}+ above the price{unpriced}")


# --- grading (maintenance.settle_open) -------------------------------------------
def first_scorer(conn, team: str, date: str) -> dict | None:
    """{"player", "team"} for the first made shot or free throw of ``team``'s
    game on ``date``, by action order; None before the game is on file."""
    t = _canon(team)
    rows = conn.execute(
        "SELECT game_id, action, player, team, made FROM nba_shots WHERE date = ? "
        "ORDER BY game_id, action", (str(date)[:10],)).fetchall()
    games: dict = {}
    for gid, action, player, tm, made in rows:
        games.setdefault(gid, []).append((int(action or 0), str(player or ""), _canon(tm), int(made or 0)))
    for shots in games.values():
        if t not in {tm for _a, _p, tm, _m in shots}:
            continue
        for _a, player, tm, made in sorted(shots):
            if made:
                return {"player": player, "team": tm}
        return None
    return None


def settle(lconn, hconn=None) -> int:
    """Grade every open NBA first-basket bet whose game's shots are on file.
    It wins when he made the game's first basket; anyone else's loses it.
    One `ledger.settle` call per slate date — it keys on (player, market)."""
    from . import ledger as L
    from .sources.oddsapi import normalize_name
    rows = lconn.execute("SELECT * FROM bets WHERE status='open' AND market=? "
                         "AND LOWER(sport)='nba'", (MARKET,)).fetchall()
    if not rows:
        return 0
    if hconn is None:
        from . import db as _db
        hconn = _db.connect()
    actuals: dict = {}
    for b in rows:
        keys = b.keys()
        day = str((b["game_day"] if "game_day" in keys else "") or b["date"] or "")[:10]
        team = str((b["team"] if "team" in keys else "") or "")
        if not day or not team:
            continue
        first = first_scorer(hconn, team, day)
        if not first:
            continue
        won = normalize_name(first["player"]) == normalize_name(b["player"] or "")
        actuals.setdefault(b["date"], {})[(b["player"], MARKET)] = 1.0 if won else 0.0
    return sum(L.settle(lconn, a, sport="nba", date=d) for d, a in actuals.items())
