"""First touchdown — who scores a game's first touchdown, by our numbers.

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... if we go by the
most likely scorer for each game, it's just going to be the person with the
lowest odds to score the touchdown first. But that's not what we want to be
selecting. We want to be going after what the data and tools that we have
all put together says, not just off of book lines."

THE RESEARCH (docs/FIRST_TD_RESEARCH.md; `python3 tools/first_td_study.py`
reruns every number from the nflverse play-by-play, 1,467 regular-season
games 2021 through week 8 of 2026):

  * 94.8% of first touchdowns are an offence's, 5.2% a defence's or a
    return's; 0.7% of games have none. 69% come in the first quarter.
  * WHICH TEAM. The favourite scores first 58.9% of the time. From the lines
    alone — logit P(home) = 0.073 + 0.478 x (home's implied points − away's)
    / 7, fitted on 2021-24 — the held-out 2025-26 log loss is 0.6654
    against a coin's 0.6931.
  * WHO RECEIVES is a coin flip before the toss: a team's kickoff history
    predicts nothing (held-out 0.6965, worse than the coin). After the toss
    it is worth a lot (0.6550) — the receiving team scores first 57.3% of
    the time — but that is known minutes before kickoff, not at build time.
  * WHICH PLAYER. Volume, not touchdowns. His share of his team's first
    touchdowns follows two-thirds his share of its carries and targets and
    one-third his share of its touchdowns (this season, last season at
    half weight). On 704 held-out team first touchdowns that scores 2.086
    nats against 2.369 for touchdown share alone — the shortcut a price
    built off anytime-touchdown odds takes.
  * HONEST ON GAMES IT NEVER SAW: said 6.2%, scored 6.3%; said 9.6%, 11.3%;
    said 14.2%, 15.6% (7,309 held-out player-games; log loss 0.1852 against
    0.1998 for the touchdown-share shortcut).

WHY THE LIKELIEST SCORER IS NOT THE PICK. Our top man per game scored first
12.9% of the time on the held-out games (we said 13.5%). Books charge about +450 to +600
for him (18% to 15% implied) inside a market holding 25-35%, so backing
the favourite is a steady loss. A pick here is a player OUR number puts
clearly above his price: `pick` asks an expected return of MIN_EV or better
at the best bettable price, inside FIRST_TD_ODDS, one a game.

Standard library only.
"""
from __future__ import annotations

import math

#: logit P(home team scores the game's first TD) = A + B x (home implied −
#: away implied) / 7. Fitted on 2021-24 (tools/first_td_study.py).
TEAM_A, TEAM_B = 0.073, 0.478
#: The share of first touchdowns an offence scores (5.2% defence/returns).
OFF_SHARE = 0.948
#: His share of his team's first touchdowns: carries + targets, and touchdowns.
BLEND = {"touch": 2 / 3, "td": 1 / 3}
#: Last season's games count this much against this season's.
LAST_SEASON = 0.5
#: The floor every candidate's share starts from, so a player with no
#: touches yet on file is unlikely rather than impossible. Chosen on the
#: 2021-24 games (0.002 to 0.15 tried; 0.03-0.04 best), scored on 2025-26:
#: 2.086 nats, against 2.134 at 0.002 and 2.369 for touchdown share alone.
EPS = 0.04
#: The candidates are the players his team USED lately — a touch in one of
#: its last RECENT_GAMES games — the research's "touched the ball in the
#: game", since the floor above is spread over every candidate.
RECENT_GAMES = 2

#: The price window. Below +250 the favourite's price never pays for the
#: market's hold; past +2500 our number cannot separate a real chance from
#: noise (the held-out rows under 2% said 1.1% and scored 1.9%).
FIRST_TD_ODDS = (250, 2500)
#: The expected return a pick needs at the best bettable price, and the
#: least chance we will call a pick at all.
MIN_EV = 0.10
MIN_PROB = 0.04
#: Picks per game, and on the board.
PER_GAME = 1
LIMIT = 8
#: OUR NUMBERS BEFORE THE PRICES (Ethan, 2026-10-31: "still not seeing first
#: touchdown bets ... those bets need to show up on the long shot page"). A
#: game whose first-touchdown prices are not on file yet — the odds budget
#: did not buy them, or they post later in the day — still shows its likeliest
#: first scorers by our numbers, each with the price that would make him a
#: pick (`need_odds`), so the page is never empty while the model has an
#: opinion. Nothing unpriced is a pick or journaled: a pick needs a price.
OURS_PER_GAME = 3

#: The stored stats a player's volume and touchdowns come from
#: (player_game_logs).
TOUCH_MARKETS = ("carries", "targets")
TD_MARKETS = ("rush_td", "rec_td")

#: COLLEGE (tools/cfb_first_td_study.py, cfbfastR's play-by-play, FBS
#: against FBS, regular season; docs/FIRST_TD_RESEARCH.md):
#:
#:   * WHICH TEAM: logit P(home) = −0.046 + 0.379 x home edge / 7, fitted on
#:     2021-24 and scored on 2025-26's 1,162 games: 0.6141 against a coin's
#:     0.6931. College lines say more than the NFL's (the favourite scores
#:     first 64.9% of the time, against 58.9%) because its spreads run wider.
#:   * AN OFFENCE scores it 96.0% of the time (4,174 games).
#:   * WHICH PLAYER: the NFL's blend wins here too — on 2023-24's 2,781 team
#:     first touchdowns, fitted on 2021-22, 2.178 nats against 2.186 for
#:     touchdown share and 2.192 for volume. The floor the training seasons
#:     chose is 0.06. (2025 and 2026 are left out of the player test: from
#:     2025 ESPN's play text changed and the file's receiver names arrive
#:     as "#21 J.Theodore caught at 09"; the team half does not need them.)
#:   * HONEST ON GAMES IT NEVER SAW: said 6.2%, scored 6.4%; said 9.6%,
#:     10.1%; said 14.2%, 15.7% (31,000 held-out player-games; log loss
#:     0.1759 against 0.1839 for every player alike).
#:
#: Every league's numbers in one place; NFL keeps the module's names above.
PARAMS = {
    "nfl": {"team_a": TEAM_A, "team_b": TEAM_B, "off_share": OFF_SHARE, "eps": EPS,
            "fav_rate": 0.589, "games": "1,467"},
    "cfb": {"team_a": -0.046, "team_b": 0.379, "off_share": 0.960, "eps": 0.06,
            "fav_rate": 0.649, "games": "4,174"},
}


def params(sport: str = "nfl") -> dict:
    """The fitted numbers for this league (the NFL's for any other)."""
    return PARAMS.get(str(sport or "nfl").lower(), PARAMS["nfl"])


def team_first(spread_home, sport: str = "nfl") -> float:
    """P(the home team scores the game's first touchdown).

    ``spread_home`` is the games table's home-relative spread — negative
    when the home team is favoured — so the home side's edge in implied
    points is −spread. None (no line) is a coin flip with the small home
    lean the fit found."""
    try:
        edge = -float(spread_home)
    except (TypeError, ValueError):
        edge = 0.0
    p = params(sport)
    return 1.0 / (1.0 + math.exp(-(p["team_a"] + p["team_b"] * edge / 7.0)))


def shares(players: dict, sport: str = "nfl") -> dict:
    """{player: share of his team's first touchdowns} for one team.

    ``players`` is {player: {"touch": carries + targets, "td": touchdowns}},
    each already season-weighted. Two-thirds volume share, one-third
    touchdown share, a small floor for everyone, normalised to one."""
    tt = sum(max(0.0, float(v.get("touch") or 0)) for v in players.values())
    td = sum(max(0.0, float(v.get("td") or 0)) for v in players.values())
    eps = params(sport)["eps"]
    raw = {}
    for name, v in players.items():
        s = eps
        if tt > 0:
            s += BLEND["touch"] * max(0.0, float(v.get("touch") or 0)) / tt
        if td > 0:
            s += BLEND["td"] * max(0.0, float(v.get("td") or 0)) / td
        raw[name] = s
    z = sum(raw.values()) or 1.0
    return {name: s / z for name, s in raw.items()}


def team_usage(conn, sport: str, season: int, team: str, before_period: str | None = None) -> dict:
    """{player: {"touch", "td", "games"}} for ``team`` from player_game_logs:
    this season (before ``before_period`` when given) and last season at
    LAST_SEASON weight — his rows for THIS team only, so a man who moved
    brings no old team's volume."""
    out: dict = {}
    q = ("SELECT season, period, player, market, value FROM player_game_logs "
         "WHERE sport=? AND team=? AND season IN (?, ?) AND market IN (?,?,?,?)")
    args = [sport, team, season, season - 1, *TOUCH_MARKETS, *TD_MARKETS]
    for r in conn.execute(q, args):
        s, period, player, market, value = r[0], str(r[1]), r[2], r[3], r[4]
        if s == season and before_period is not None and period >= str(before_period):
            continue
        w = 1.0 if s == season else LAST_SEASON
        d = out.setdefault(player, {"touch": 0.0, "td": 0.0, "games": set(), "used": set()})
        v = float(value or 0) * w
        if market in TOUCH_MARKETS:
            d["touch"] += v
            if s == season and v > 0:
                d["used"].add(period)
        else:
            d["td"] += v
        if s == season:
            d["games"].add(period)
    team_games = sorted({g for d in out.values() for g in d["games"]})
    recent = set(team_games[-RECENT_GAMES:])
    if recent:
        keep = {p for p, d in out.items() if d["used"] & recent}
    else:
        # Before his team has a game this season: last season's fourteen
        # busiest, the size of a team's touch list in one game.
        keep = set(sorted(out, key=lambda p: -out[p]["touch"])[:14])
    return {p: {"touch": d["touch"], "td": d["td"], "games": len(d["games"])}
            for p, d in out.items() if p in keep}


def game_probs(home_usage: dict, away_usage: dict, spread_home, home: str = "", away: str = "",
               sport: str = "nfl") -> list:
    """Every candidate's chance of scoring the game's first touchdown:
    P(his team's offence scores it) x his share of his team's first TDs."""
    ph = team_first(spread_home, sport)
    off = params(sport)["off_share"]
    rows = []
    for team, usage, pt in ((home, home_usage, ph), (away, away_usage, 1.0 - ph)):
        for name, s in shares(usage, sport).items():
            rows.append({"player": name, "team": team, "prob": off * pt * s,
                         "team_first": round(pt, 4), "share": round(s, 4)})
    rows.sort(key=lambda r: -r["prob"])
    return rows


def _decimal(odds: int) -> float:
    o = int(odds)
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / abs(o))


def implied(odds: int) -> float:
    return 1.0 / _decimal(odds)


def expected_return(prob: float, odds: int) -> float:
    """Profit per unit staked at ``odds`` if ``prob`` is right."""
    return prob * _decimal(odds) - 1.0


def american(decimal_odds: float) -> int:
    """The American price for a decimal one (2.0 and up is plus money)."""
    d = float(decimal_odds)
    if d >= 2.0:
        return int(round((d - 1.0) * 100))
    return -int(round(100.0 / (d - 1.0)))


def fair_odds(prob: float) -> int | None:
    """The price at which ``prob`` breaks even — our chance, as odds."""
    p = float(prob or 0.0)
    if not 0.0 < p < 1.0:
        return None
    return american(1.0 / p)


def need_odds(prob: float) -> int | None:
    """The SHORTEST price that makes ``prob`` a pick: MIN_EV at that price,
    never shorter than the window's floor (+250). None when nothing inside
    FIRST_TD_ODDS would do it, or the chance is under MIN_PROB."""
    p = float(prob or 0.0)
    if p < MIN_PROB or p >= 1.0:
        return None
    d = (1.0 + MIN_EV) / p
    am = int(math.ceil((d - 1.0) * 100.0)) if d >= 2.0 else FIRST_TD_ODDS[0]
    am = max(am, FIRST_TD_ODDS[0])
    return am if am <= FIRST_TD_ODDS[1] else None


#: The reader's line for a board with no first-touchdown price on it, from
#: the build's own odds note (`why_empty`).
WHY_BUDGET = ("No first-touchdown prices were bought for these games yet: the odds "
              "budget held today's player pull. Below, who scores first by our "
              "numbers and the price that would make each one a pick.")
WHY_LATER = ("First-touchdown prices are bought the morning of the games. Below, who "
             "scores first by our numbers and the price that would make each one a pick.")


def why_empty(note: str = "") -> str:
    """Why the board has no price, in a reader's words, from the build's
    player-pull note: the budget held the pull, or the prices come later."""
    n = str(note or "").lower()
    if "budget" in n and ("capped at 0" in n or "pulled 0" in n or " 0 of " in n):
        return WHY_BUDGET
    return WHY_LATER


def pick(rows: list, per_game: int = PER_GAME, limit: int = LIMIT) -> list:
    """The board: priced candidates our chance puts clearly above the price.

    ``rows`` carry ``prob``, ``odds`` (the best bettable price) and ``game``.
    Each gets ``ev`` and ``implied``; a pick clears MIN_PROB and MIN_EV inside
    FIRST_TD_ODDS. Ranked by expected return — never by price — one a game."""
    cands = []
    for r in rows:
        try:
            odds = int(r["odds"])
            p = float(r["prob"])
        except (KeyError, TypeError, ValueError):
            continue
        r["implied"] = round(implied(odds), 4)
        r["ev"] = round(expected_return(p, odds), 4)
        if not (FIRST_TD_ODDS[0] <= odds <= FIRST_TD_ODDS[1]):
            continue
        if p < MIN_PROB or r["ev"] < MIN_EV:
            continue
        cands.append(r)
    cands.sort(key=lambda r: (-r["ev"], -r["prob"]))
    out, seen = [], {}
    for r in cands:
        g = r.get("game") or ""
        if seen.get(g, 0) >= per_game:
            continue
        seen[g] = seen.get(g, 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    return out


def first_scorer(plays: list) -> dict | None:
    """The game's first touchdown from its plays in order: {"player",
    "player_id", "team", "offense"}, or None when nobody scored one. A play
    is a dict with nflverse's columns (touchdown, td_team, td_player_name,
    td_player_id, posteam, pass_touchdown, rush_touchdown)."""
    for p in plays:
        if str(p.get("touchdown")) not in ("1", "1.0") or not p.get("td_team") or p.get("td_team") == "NA":
            continue
        off = p.get("td_team") == p.get("posteam") and (
            str(p.get("pass_touchdown")) in ("1", "1.0") or str(p.get("rush_touchdown")) in ("1", "1.0"))
        return {"player": p.get("td_player_name") or "", "player_id": p.get("td_player_id") or "",
                "team": p["td_team"], "offense": bool(off)}
    return None


def scored_first(bet_player: str, bet_team: str, first: dict | None) -> bool:
    """Did this man score it? Play-by-play abbreviates ("J.Jacobs") where the
    journal keeps the full name, so both go through the same (initial,
    surname, team) key the usage maps join on."""
    if not first or not first.get("player"):
        return False
    from .fantasy import _short_key
    return _short_key(bet_player, bet_team) == _short_key(first["player"], first.get("team") or "")


# --- the board (nfl_build) -------------------------------------------------------
def _season_of(date: str) -> int:
    """The NFL season a slate date belongs to (a January game is last year's)."""
    try:
        y, m = int(str(date)[:4]), int(str(date)[5:7])
    except (TypeError, ValueError):
        import datetime as _dt
        t = _dt.date.today()
        y, m = t.year, t.month
    return y if m >= 3 else y - 1


def _team_of(name: str, home: str, away: str, hu: dict, au: dict):
    """Which side's usage holds this quoted name: exact, then the (initial,
    surname) key the usage maps join on. None when neither does."""
    from .fantasy import _short_key
    from .sources.oddsapi import normalize_name
    n = normalize_name(name)
    for team, usage in ((home, hu), (away, au)):
        for p in usage:
            if normalize_name(p) == n:
                return team, p
    for team, usage in ((home, hu), (away, au)):
        k = _short_key(name, team)
        for p in usage:
            if _short_key(p, team) == k:
                return team, p
    return None, None


def board(quotes: dict, games: list, sport: str = "nfl", conn=None, date: str = "",
          why: str = "") -> dict:
    """{"rows": every quoted player with our chance and the price,
    "picks": the value picks (`pick`), "games": n, "quoted": n,
    "ours": each unpriced game's likeliest first scorers by our numbers with
    the price that would make each a pick, "ours_games": n, "why": the
    reader's line when no game is priced}.

    ``quotes`` is `OddsMatch.first_td`; ``games`` the board's games (home,
    away, spread, date, kickoff). Usage comes from the history database
    (`team_usage`), this season and last at half weight. ``why`` is the
    build's player-pull note (`why_empty` turns it into the reader's line)."""
    from .sources.oddsapi import best_scorer_price
    if conn is None:
        from . import db as _db
        conn = _db.connect()
    by_pair: dict = {}
    for q in (quotes or {}).values():
        by_pair.setdefault((q.get("home"), q.get("away")), []).append(q)
    rows, n_games, ours, ours_games = [], 0, [], 0
    for g in games or []:
        home, away = g.get("home"), g.get("away")
        qs = by_pair.get((home, away)) or []
        if not home or not away:
            continue
        season = _season_of(g.get("date") or date)
        hu, au = team_usage(conn, sport, season, home), team_usage(conn, sport, season, away)
        ranked = game_probs(hu, au, g.get("spread"), home, away, sport)
        if not qs:
            # No price on file for this game: our likeliest first scorers,
            # with the price that would make each a pick. Never a pick.
            top = [r for r in ranked if r["prob"] > 0][:OURS_PER_GAME]
            if top:
                ours_games += 1
            for r in top:
                p = float(r["prob"])
                ours.append({"player": r["player"], "team": r["team"],
                             "opponent": away if r["team"] == home else home,
                             "market": "first_td", "market_label": "First Touchdown",
                             "game": f"{away}@{home}", "matchup": f"{away} @ {home}",
                             "game_date": g.get("date"), "game_kickoff": g.get("kickoff"),
                             "prob": round(p, 4), "team_first": r["team_first"],
                             "share": r["share"], "fair_odds": fair_odds(p),
                             "need_odds": need_odds(p), "priced": False})
            continue
        n_games += 1
        probs = {(r["team"], r["player"]): r for r in ranked}
        for q in qs:
            team, who = _team_of(q.get("player") or "", home, away, hu, au)
            if team is None:
                continue
            best = best_scorer_price(q.get("quotes") or [])
            if not best:
                continue
            base = probs.get((team, who)) or {}
            p = float(base.get("prob") or 0.0)
            odds = int(best["yes_odds"])
            imp, ev = implied(odds), expected_return(p, odds)
            tf, sh = base.get("team_first") or 0.0, base.get("share") or 0.0
            rows.append({"player": q.get("player") or who, "team": team,
                         "opponent": away if team == home else home, "market": "first_td",
                         "market_label": "First Touchdown", "side": "YES", "line": 0.5,
                         "game": f"{away}@{home}", "matchup": f"{away} @ {home}",
                         "game_date": g.get("date"), "game_kickoff": g.get("kickoff"),
                         "odds": odds, "book": best.get("book", ""),
                         "prob": round(p, 4), "model_prob": round(p, 4),
                         "team_first": tf, "share": sh,
                         "implied": round(imp, 4), "implied_prob": round(imp, 4),
                         "ev": round(ev, 4), "ev_per_unit": round(ev, 4),
                         "primary_reason": (f"{team} score first {tf:.0%} by the lines · "
                                            f"his share {sh:.0%}"),
                         "reasons": [
                             f"{team} score the game's first touchdown {tf:.0%} of the time by the lines "
                             f"(the favourite does {params(sport)['fav_rate']:.0%}, measured over "
                             f"{params(sport)['games']} games).",
                             f"He has {sh:.0%} of {team}'s first-touchdown share: two-thirds his share of "
                             f"their carries and targets, one-third his share of their touchdowns.",
                             f"Our chance {p:.1%} against {imp:.1%} in the price ({ev:+.0%} expected return).",
                         ]})
    rows.sort(key=lambda r: -r["prob"])
    picks = pick([dict(r) for r in rows])
    for r in picks:
        r["grade"] = "First TD"
        # The card's "Edge" is ours against the price's, in points; the
        # expected return rides in its own key and in the reasons.
        r["edge"] = round(r["prob"] - r["implied"], 4)
        r["stake_units"] = 0.1
        r["expected_opportunities"] = f"{r['share']:.0%}"
    for r in rows:
        r["fair_odds"] = fair_odds(r["prob"])
        r["need_odds"] = need_odds(r["prob"])
        r["priced"] = True
    ours.sort(key=lambda r: (str(r.get("game_kickoff") or ""), r["game"], -r["prob"]))
    out = {"rows": rows, "picks": picks, "games": n_games, "quoted": len(rows),
           "ours": ours, "ours_games": ours_games}
    if not rows:
        out["why"] = why_empty(why)
    return out


def report(b: dict) -> str:
    """The build log's line."""
    unpriced = (f"; our top first scorers shown unpriced for {b['ours_games']} game(s)"
                if b.get("ours_games") else "")
    if not b.get("games"):
        return f"  First touchdown: no first-touchdown prices on this pull{unpriced}"
    return (f"  First touchdown: {b['quoted']} quoted player(s) across {b['games']} game(s); "
            f"{len(b['picks'])} pick(s) our chance puts {MIN_EV:.0%}+ above the price{unpriced}")


# --- grading (maintenance.settle_open) --------------------------------------------
_PLAY_COLS = ["game_id", "season", "season_type", "week", "home_team", "away_team", "posteam",
              "touchdown", "td_team", "td_player_name", "td_player_id", "pass_touchdown",
              "rush_touchdown", "desc"]


def settle(lconn, plays_for=None) -> int:
    """Grade every open NFL first-touchdown bet whose game is over.

    ``plays_for(season)`` yields that season's plays in order (default: the
    cached nflverse play-by-play, `sources.nflpbp`). A game counts as over
    once its plays carry "END GAME". The bet wins when he scored the game's
    first touchdown; a defence's or nobody's first touchdown loses it."""
    import re
    from . import ledger as L
    rows = lconn.execute("SELECT * FROM bets WHERE status='open' AND market='first_td' "
                         "AND LOWER(sport)='nfl'").fetchall()
    if not rows:
        return 0
    if plays_for is None:
        from .sources import nflpbp

        def plays_for(season):
            return nflpbp.load_pbp_rows(season, columns=_PLAY_COLS)
    wanted: dict = {}
    for b in rows:
        m = re.match(r"^(\d{4})-W(\d{1,2})$", str(b["date"] or ""))
        if not m:
            continue
        wanted.setdefault(int(m.group(1)), set()).add(int(m.group(2)))
    games: dict = {}
    for season, weeks in wanted.items():
        for p in plays_for(season):
            if p.get("season_type") not in (None, "", "REG", "POST"):
                continue
            try:
                wk = int(float(p.get("week") or 0))
            except ValueError:
                continue
            if wk not in weeks:
                continue
            g = games.setdefault((season, wk, p.get("home_team"), p.get("away_team")),
                                 {"plays": [], "over": False})
            g["plays"].append(p)
            if "END GAME" in str(p.get("desc") or ""):
                g["over"] = True
    actuals: dict = {}          # {bet date: {(player, "first_td"): 1.0 | 0.0}}
    for b in rows:
        m = re.match(r"^(\d{4})-W(\d{1,2})$", str(b["date"] or ""))
        team = b["team"] if "team" in b.keys() else None
        if not m or not team:
            continue
        season, wk = int(m.group(1)), int(m.group(2))
        g = next((v for (s, w, h, a), v in games.items() if s == season and w == wk and team in (h, a)), None)
        if not g or not g["over"]:
            continue
        first = first_scorer(g["plays"])
        actuals.setdefault(b["date"], {})[(b["player"], "first_td")] = \
            1.0 if scored_first(b["player"], team, first) else 0.0
    # Per week: `ledger.settle` keys on (player, market), so one call for
    # two weeks would grade last week's open bet with this week's result.
    return sum(L.settle(lconn, a, sport="nfl", date=d) for d, a in actuals.items())
