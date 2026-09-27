"""What each basketball defence gives up, per game, in the four prop stats.

The NFL has had its defence-versus-position read since 2026-09-23 (engine/
defensevs), college and MLB theirs since; basketball had one number — a
team's points allowed per game — and nothing under a pick said whom the
player was facing. This is the basketball read the data supports:

    for every defence, per GAME, the points, rebounds, assists and threes
    its opponents' players put up against it, against the league's
    average, walk-forward (only games before the one being priced), and
    shrunk toward average by how many games it rests on:

        factor = 1 + (raw - 1) * games / (games + SHRINK_GAMES)

WHY NOT BY POSITION. The logs carry a starter flag, not a position: the
league's box score names a position for the five starters only and
nothing for the bench, so "what PHX gives up to centres" cannot be built
from what we ingest without guessing a position for most of the rows.
What a defence allows in each STAT is measurable today, and it is most of
what a position split would say — a leaky rebounding defence shows up in
rebounds allowed whoever grabs them.

HOW MUCH MOVES A NUMBER. How much of a defence's factor reaches ONE
player is a measured number in every league (defensevs.TRANSFER); here
`python3 hoopsdvpfit.py` measured it on the box's logs (2026-09-27, the
same walk-forward shape as `defensefit.py`), and `projection_mult` reads
it into each projection — see TRANSFER.

Per game, not per possession: we do not ingest possessions, so a fast
team's defence reads a little worse than it is. Said on the card.
"""
from __future__ import annotations

#: The four stats every basketball prop board prices, and their words.
MARKETS = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes"}

#: Games of evidence worth as much as the league's average (the shrink).
SHRINK_GAMES = 8

#: A defence needs this many games before it is ranked at all.
MIN_GAMES = 3

#: Fewer games than this this season and the card reads last season's.
SEASON_MIN_GAMES = 5

#: How much of a defence's factor reaches one player's projection, per
#: league and market — MEASURED on the box, 2026-09-27 (hoopsdvpfit.py,
#: walk-forward, the slope of a player's result over his own baseline on
#: the defence's shrunk factor):
#:
#:     NBA 2024-25   points +1.52 ± 0.15   rebounds +1.44 ± 0.15
#:                   assists +1.13 ± 0.12  threes +1.13 ± 0.16
#:     WNBA 2021-26  points +0.79 ± 0.23   rebounds +0.78 ± 0.16
#:                   assists +1.28 ± 0.27  threes +0.89 ± 0.23
#:
#: Every one clears two standard errors. Capped at 1.0 — the whole lean,
#: never more: a slope over 1 is the shrink doing its job (the factor is
#: pulled toward average, so the part that survives reads larger), and
#: reading more than a defence's whole lean into one player is a claim
#: the fit cannot make.
TRANSFER = {
    "nba": {"pts": 1.0, "reb": 1.0, "ast": 1.0, "fg3m": 1.0},
    "wnba": {"pts": 0.79, "reb": 0.78, "ast": 1.0, "fg3m": 0.89},
}


def projection_mult(sport: str, rating: dict, opponent: str, market: str) -> tuple[float, str]:
    """``(multiplier, note)`` for one player's projection against tonight's
    defence: ``1 + TRANSFER * (factor - 1)``. (1.0, "") with no rating,
    no measured transfer, or a market the defences are not rated in."""
    t = (TRANSFER.get(str(sport or "").lower()) or {}).get(market) or 0.0
    r = ((rating or {}).get(opponent) or {}).get(market)
    if not t or not r or r.get("factor") is None:
        return 1.0, ""
    mult = round(1.0 + t * (float(r["factor"]) - 1.0), 4)
    if abs(mult - 1.0) < 0.005:
        return 1.0, ""
    return mult, (f"Matchup: {opponent} allow {r['pg']:.1f} {MARKETS[market]} a game "
                  f"({_ord(r['rank'])}-most of {r['of']}) — {(mult - 1) * 100:+.0f}% on his projection "
                  f"(measured: {'the whole' if t >= 1 else f'{t:.0%} of the'} defence's lean reaches one player)")


def allowed_by_game(rows) -> dict:
    """``{(defence, date): {market: total}}`` — each game's totals conceded.
    ``rows`` are ``(period, team, opponent, market, value)`` log rows; the
    OPPONENT is the defence the player's stat was scored against."""
    per: dict = {}
    for period, _team, opp, market, value in rows:
        if market not in MARKETS or not opp or value is None:
            continue
        slot = per.setdefault((str(opp), str(period)[:10]), {})
        slot[market] = slot.get(market, 0.0) + float(value)
    return per


def ratings(rows, before: str | None = None, shrink: float = SHRINK_GAMES) -> dict:
    """``{defence: {market: {pg, league, rank, of, games, factor}}}``.

    ``rank`` 1 is the defence that allows the MOST (the softest spot for
    an over), ``of`` how many defences were ranked. Walk-forward: with
    ``before`` set, only games strictly before that date count."""
    use = [r for r in rows if before is None or str(r[0])[:10] < before]
    per = allowed_by_game(use)
    by_def: dict = {}
    for (d, _day), got in per.items():
        for m, v in got.items():
            by_def.setdefault(d, {}).setdefault(m, []).append(v)
    out: dict = {}
    for m in MARKETS:
        pool = [v for dm in by_def.values() for v in dm.get(m, [])]
        if not pool:
            continue
        league = sum(pool) / len(pool)
        teams = {d: dm[m] for d, dm in by_def.items() if len(dm.get(m, [])) >= MIN_GAMES}
        ranked = sorted(teams, key=lambda d: (-sum(teams[d]) / len(teams[d]), d))
        for i, d in enumerate(ranked):
            vs = teams[d]
            n, pg = len(vs), sum(vs) / len(vs)
            raw = pg / league if league else 1.0
            out.setdefault(d, {})[m] = {
                "pg": round(pg, 1), "league": round(league, 1), "rank": i + 1,
                "of": len(ranked), "games": n,
                "factor": round(1.0 + (raw - 1.0) * n / (n + shrink), 4)}
    return out


def load(conn, sport: str, season: int) -> list:
    return [tuple(r) for r in conn.execute(
        "SELECT period, team, opponent, market, value FROM player_game_logs "
        "WHERE sport=? AND season=?", (sport, season)).fetchall()]


def load_with_players(conn, sport: str, seasons) -> list:
    """The log rows with the player's name as a sixth column — what
    `measure` needs to keep one baseline per player."""
    qs = ",".join("?" * len(seasons))
    return [tuple(r) for r in conn.execute(
        "SELECT period, team, opponent, market, value, player FROM player_game_logs "
        f"WHERE sport=? AND season IN ({qs})", (sport, *seasons)).fetchall()]


def board_ratings(conn, sport: str, date: str) -> tuple[dict, bool]:
    """``(ratings, last_season)`` for a board built on ``date``: this
    season's, walk-forward, or last season's whole when this one has too
    few games yet (opening night, the preseason)."""
    from .seasons import season_of
    season = season_of(sport, date)
    now = ratings(load(conn, sport, season), before=date)
    games = max((c["games"] for d in now.values() for c in d.values()), default=0)
    if games >= SEASON_MIN_GAMES:
        return now, False
    return ratings(load(conn, sport, season - 1)), True


def matchup_card(team: str, rating: dict, market: str, last_season: bool = False) -> dict | None:
    """What goes under a basketball pick: the defence, what it allows in
    this stat a game, where that ranks — and, until measured, that the
    model does not read it."""
    r = ((rating or {}).get(team) or {}).get(market)
    if not r or market not in MARKETS:
        return None
    words = f"{MARKETS[market]} allowed"
    when = "last season" if last_season else f"over {r['games']} game{'s' if r['games'] != 1 else ''}"
    card = {"opponent": team, "stat": words, "per_game": r["pg"], "league": r["league"],
            "rank": r["rank"], "of": r["of"], "games": r["games"],
            "text": (f"{team} allow {r['pg']:.1f} {MARKETS[market]} a game, the "
                     f"{_ord(r['rank'])}-most of {r['of']} (league {r['league']:.1f}), {when}"),
            "note": ("Read into the projection — measured on our basketball logs, the defence's lean "
                     "reaches one player (hoopsdvp.TRANSFER). Per game, not per possession.")}
    if last_season:
        card["last_season"] = True
    return card


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def attach(rows, rating: dict, last_season: bool = False) -> int:
    """Hang ``matchup_card`` on every pick row whose opponent and stat have a
    rating. Returns how many carry one. Never raises on a strange row."""
    n = 0
    for r in rows or []:
        if not isinstance(r, dict) or r.get("matchup_card"):
            continue
        card = matchup_card(str(r.get("opponent") or ""), rating, str(r.get("market") or ""),
                            last_season)
        if card:
            r["matchup_card"] = card
            n += 1
    return n


# --- measuring it: does the defence's rating reach one player? ---------------
#: A player's own baseline: his mean over this many prior games, with at
#: least BASE_MIN of them.
BASE_GAMES = 10
BASE_MIN = 5
#: A market's transfer is worth reading only past this many player-games,
#: and only if it clears two standard errors.
FIT_MIN_ROWS = 400
FIT_MIN_Z = 2.0


def measure(rows, shrink: float = SHRINK_GAMES) -> dict:
    """``{market: {rows, slope, se, verdict}}`` — how much of a defence's
    factor shows up in one player's line, walk-forward.

    For every player-game, with only EARLIER games known: the player's
    baseline (his last BASE_GAMES in that stat) and the defence's shrunk
    factor. The slope of ``value / baseline - 1`` on ``factor - 1`` is the
    TRANSFER: 1 means the defence's whole lean reaches him, 0 that it is
    noise for one player. Games are replayed a DATE at a time, so a game
    never sees its own day's totals."""
    rows = sorted((r for r in rows if r[3] in MARKETS and r[4] is not None and r[2]),
                  key=lambda r: str(r[0])[:10])
    days: dict = {}
    for r in rows:
        days.setdefault(str(r[0])[:10], []).append(r)
    cum: dict = {}          # (defence, market) -> [total conceded, games]
    lg: dict = {}           # market -> [total conceded, defence-games]
    hist: dict = {}         # (player-team key, market) -> [values]
    pts: dict = {m: [] for m in MARKETS}
    for day in sorted(days):
        today = days[day]
        # 1) price today's rows with what was known before today; the
        #    player is the 6th column (`load_with_players`), the team a
        #    stand-in only for the unit tests' five-column rows
        for r in today:
            player = r[5] if len(r) > 5 else r[1]
            m, v, opp = r[3], float(r[4]), str(r[2])
            prior = hist.get((player, m), [])
            c, L = cum.get((opp, m)), lg.get(m)
            if len(prior) >= BASE_MIN and c and L and c[1] >= MIN_GAMES and L[1]:
                base = sum(prior[-BASE_GAMES:]) / len(prior[-BASE_GAMES:])
                league = L[0] / L[1]
                if base > 0 and league > 0:
                    raw = (c[0] / c[1]) / league
                    f = 1.0 + (raw - 1.0) * c[1] / (c[1] + shrink)
                    pts[m].append((f - 1.0, v / base - 1.0))
        # 2) then learn today's games
        conceded: dict = {}
        for r in today:
            player = r[5] if len(r) > 5 else r[1]
            m, v, opp = r[3], float(r[4]), str(r[2])
            hist.setdefault((player, m), []).append(v)
            conceded[(opp, m)] = conceded.get((opp, m), 0.0) + v
        for (opp, m), tot in conceded.items():
            c = cum.setdefault((opp, m), [0.0, 0])
            c[0] += tot
            c[1] += 1
            L = lg.setdefault(m, [0.0, 0])
            L[0] += tot
            L[1] += 1
    out = {}
    for m, xy in pts.items():
        n = len(xy)
        if n < 3:
            out[m] = {"rows": n, "slope": None, "se": None, "verdict": f"not enough games yet ({n} of {FIT_MIN_ROWS})"}
            continue
        mx = sum(x for x, _ in xy) / n
        my = sum(y for _, y in xy) / n
        sxx = sum((x - mx) ** 2 for x, _ in xy)
        if sxx <= 0:
            out[m] = {"rows": n, "slope": None, "se": None, "verdict": "no spread in the defences yet"}
            continue
        b = sum((x - mx) * (y - my) for x, y in xy) / sxx
        resid = sum((y - my - b * (x - mx)) ** 2 for x, y in xy) / max(1, n - 2)
        se = (resid / sxx) ** 0.5
        if n < FIT_MIN_ROWS:
            verdict = f"not enough games yet ({n} of {FIT_MIN_ROWS})"
        elif se and abs(b / se) >= FIT_MIN_Z and b > 0:
            verdict = f"the defence reaches the player: about {min(b, 1.0):.2f} of its lean"
        else:
            verdict = "noise for one player — leave it out of the projection"
        out[m] = {"rows": n, "slope": round(b, 4), "se": round(se, 4), "verdict": verdict}
    return out
