"""Our own read on a side or a total the boards do not price.

Ethan, 2026-10-13, under a graded slip whose Brewers moneyline and
Brewers-Dodgers under 7.5 both read "NOT ON OUR BOARD": "you didn't add
where if there's a pick [not] in the board we use our data to explain if
it's a good pick or not".

A board prices the sides and totals of the games on its own slate, at the
numbers the books had posted when it was built. A slip carries whatever a
book sells: a game on another day's slate, a total a run under the posted
one, a moneyline on a game the build saw before any book had a price. For
those this runs THE GAME MODEL THE BOARD WOULD HAVE RUN, off the same
history database the builds read:

  * NFL and MLB — team ratings from this season's finals (the previous
    season pooled in while this one is thin: `teamrates.ratings_for_season`)
    through the win curve, the margin and the totals projection of
    `engine.gamebets`; baseball adds the two starters off the board's own
    game card where it has the game, league-average arms where it does not,
    and says which;
  * college football — the opponent-adjusted ratings the college board
    prices from, on the constants `engine.cfb.ratings` has installed;
  * hockey — the goals model the NHL board prices its lines from
    (`engine.nhl.model`: each side's expected goals, Poisson, overtime and
    the shootout in the moneyline);
  * basketball — no board prices an NBA or WNBA game line, so the read uses
    the one game model we keep for them, the futures simulation's
    (`futures.win_prob` on `futuresdata.blended_ratings`), for the moneyline
    and the spread. Nothing of ours projects a basketball total, so a total
    gets the facts and no number.

THE MARKET HOLDS IT, as it holds every game line on the boards: the model's
chance is pulled toward the market's own number by the haircut
`engine.gamecal` measured for that sport and market (`gamebets.temper`),
and a raw disagreement past `MAX_CREDIBLE_EDGE` is named for what it is on
an efficiently priced line — our rating's error, not an edge. The market's
number is the board's own posted pair where it has one, else the slip's
price with a book's usual margin taken out, and the card says which.

THEN THE DATA BEHIND IT: each side's last ten finals, their meetings this
season, how often each side's games went over or under a total's number,
and where the board's own line sits when it prices a different one.

NOTHING HERE IS A PICK. A read is not journaled, posted, staked or put on
any board; it is our number for a ticket someone else built.
"""
from __future__ import annotations

import datetime as _dt
import math

GAME_MARKETS = ("moneyline", "spread", "total")
LEAGUES = ("nfl", "cfb", "mlb", "nhl", "nba", "wnba")
#: A two-way book's usual margin, for when the slip's own price is the only
#: one we hold: about 4.5 points on a moneyline pair, 4.8 at -110/-110.
TYPICAL_MARGIN = {"moneyline": 0.045, "spread": 0.0476, "total": 0.0476}
UNITS = {"nfl": "points", "cfb": "points", "mlb": "runs", "nhl": "goals", "nba": "points", "wnba": "points"}
WORD = {"nfl": "NFL", "cfb": "college football", "mlb": "baseball", "nhl": "hockey", "nba": "NBA",
        "wnba": "WNBA"}
#: Leagues where nothing of ours projects a game total.
NO_TOTAL_MODEL = ("nba", "wnba")
#: The finals the form line reads.
FORM_GAMES = 10
#: The board's own clamp on a game chance (gamebets.price_total and friends).
CLAMP = (0.02, 0.98)


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _today() -> str:
    return _dt.date.today().isoformat()


def _split(text) -> tuple[str, str, bool] | None:
    """(first, second, second_is_home) from "A @ B", "A at B" or "A vs B"."""
    t = " ".join(str(text or "").split())
    for sep, home_second in ((" @ ", True), ("@", True), (" at ", True), (" vs. ", False),
                             (" vs ", False), (" v ", False)):
        if sep in t:
            a, b = t.split(sep, 1)
            if a.strip() and b.strip():
                return a.strip(), b.strip(), home_second
    return None


def _one(text, league: str) -> str:
    """The one team code a phrase names in this league, or ""."""
    from .slipgrade import _codes
    got = _codes(text, league)
    return next(iter(got)) if len(got) == 1 else ""


def _board_game(board: dict, teams: set) -> dict | None:
    for g in (board or {}).get("games") or []:
        if isinstance(g, dict) and teams and teams <= {g.get("home"), g.get("away")}:
            return g
    return None


def _scheduled(conn, league: str, teams: set, today: str):
    """(home, away) of the next unplayed game on file with these teams in
    it (both, or the one), else of their latest meeting, else None."""
    if conn is None or not teams:
        return None
    marks = ",".join("?" * len(teams))
    rows = conn.execute(
        f"SELECT home, away, home_score, COALESCE(date, period) d FROM games WHERE sport=? "
        f"AND (home IN ({marks}) OR away IN ({marks})) ORDER BY d",
        (league, *teams, *teams)).fetchall()
    pick = [r for r in rows if teams <= {r[0], r[1]}]
    ahead = [r for r in pick if r[2] is None and str(r[3] or "") >= today]
    if ahead:
        return ahead[0][0], ahead[0][1]
    if len(teams) == 2 and pick:
        return pick[-1][0], pick[-1][1]
    return None


def teams_of(boards: dict, leg: dict, league: str, conn=None, today: str | None = None):
    """``(home, away, picked, board_game, how)`` — the game's two sides in
    this league's codes, the side a moneyline or spread backs, the board's
    own card for the game where it has one, and how home and away were
    told apart — or None when the slip's words do not name the game."""
    today = today or _today()
    picked = _one(leg.get("team"), league) if leg.get("market") != "total" else ""
    sp = _split(leg.get("game"))
    a = b = ""
    if sp:
        a, b = _one(sp[0], league), _one(sp[1], league)
    named = {x for x in (a, b, picked) if x}
    if not named:
        return None
    board = (boards or {}).get(league) or {}
    want = {a, b} - {""} if a and b else named
    g = _board_game(board, want)
    if g is not None:
        return g.get("home"), g.get("away"), picked, g, "board"
    if a and b and a != b:
        if sp and sp[2]:
            return b, a, picked, None, "slip"
        got = _scheduled(conn, league, {a, b}, today)
        if got:
            return got[0], got[1], picked, None, "schedule"
        return b, a, picked, None, "guess"
    got = _scheduled(conn, league, named, today)
    if got:
        return got[0], got[1], picked, None, "schedule"
    return None


# --- the models ---------------------------------------------------------------
def _cached(key, build):
    from .slipread import _cached as cached
    return cached(("slipgame",) + tuple(key), build)


def _ratings(conn, league: str, season: int):
    """``(ratings, seasons used, note)`` for the rating-model leagues."""
    from . import teamrates as TR
    from .slipread import _stamp

    def build():
        if league == "cfb":
            from . import gamebets as GB
            from .cfb import ratings as _cfb  # noqa: F401  — installs the college constants
            r, used = TR.adjusted_ratings_for_season(
                conn, "cfb", season, shrink=8.0, exclude_prefix="espn:",
                home_field=GB.HOME_FIELD.get("cfb", 0.0))
            return r, used
        return TR.ratings_for_season(conn, league, season)
    return _cached((league, season, _stamp(conn)), build)


def _hockey(conn, today: str):
    from .nhl import model as M
    from .seasons import recent_seasons
    from .slipread import _stamp
    seasons = recent_seasons("nhl", today)
    return _cached(("nhl-teams", tuple(seasons), _stamp(conn)),
                   lambda: M.team_profiles(conn, seasons=seasons))


def _hoops(conn, league: str, season: int):
    from . import futuresdata as FD
    from .slipread import _stamp
    return _cached((league, "blend", season, _stamp(conn)), lambda: FD.blended_ratings(conn, league, season))


def model(conn, league: str, home: str, away: str, g: dict | None, today: str | None = None) -> dict:
    """The game as our model for this league sees it: the home side's win
    chance, the margin and its spread, the total and its spread, and the
    inputs said in words. ``{"refused": why}`` where it cannot be read."""
    from . import gamebets as GB
    today = today or _today()
    season = _season(league, today)
    unit = UNITS[league]
    neutral = bool((g or {}).get("neutral"))
    if league in ("nfl", "mlb", "cfb"):
        ratings, used = _ratings(conn, league, season)
        H, A = (ratings or {}).get(home), (ratings or {}).get(away)
        if not H or not A:
            miss = [t for t, r in ((home, H), (away, A)) if not r]
            return {"refused": f"we hold no {'/'.join(str(s) for s in used)} results for {' or '.join(miss)}"}
        span = "–".join(str(s) for s in (used[0], used[-1])) if len(used) > 1 else str(used[0])
        inputs = [f"{home} {H.net:+.2f} and {away} {A.net:+.2f} {unit} a game against an average side "
                  f"({span} finals: {H.games} and {A.games} games)"]
        out = {"kind": "normal", "margin_sd": GB.MARGIN_SD[league], "total_sd": GB.TOTAL_SD[league],
               "home_pts": GB.project_team_points(league, H.off, A.def_),
               "away_pts": GB.project_team_points(league, A.off, H.def_),
               "total": GB.project_total(league, H.off, H.def_, A.off, A.def_), "inputs": inputs}
        if league == "mlb":
            pit = (g or {}).get("pitchers") or {}
            hp, ap = pit.get("home") or {}, pit.get("away") or {}
            hx = _num(hp.get("xera"), GB.LEAGUE_AVG_XERA)
            ax = _num(ap.get("xera"), GB.LEAGUE_AVG_XERA)
            out["margin"] = GB.mlb_margin(H.net, A.net, hx, ax)
            out["p_home"] = GB.mlb_win_prob(H.net, A.net, hx, ax)
            if hp.get("name") and ap.get("name"):
                out["starters"] = (f"{hp['name']} ({hx:.2f} xERA) for {home}, "
                                   f"{ap['name']} ({ax:.2f} xERA) for {away}")
            else:
                out["starters"] = (f"Not on our board yet — both priced as league-average arms "
                                   f"({GB.LEAGUE_AVG_XERA:.2f} xERA)")
        elif league == "nfl":
            out["margin"] = GB.game_margin("nfl", H.net, A.net, neutral)
            out["p_home"] = GB.nfl_win_prob(H.net, A.net, neutral)
        else:
            out["margin"] = GB.game_margin("cfb", H.net, A.net, neutral)
            sd = GB.MARGIN_SD["cfb"]
            out["p_home"] = (GB.cfb_win_prob(H.net, A.net) if not neutral else
                             max(0.005, min(0.995, _ncdf(out["margin"] / sd))))
        if neutral:
            inputs.append("a neutral site — no home field")
        return out
    if league == "nhl":
        from .nhl import model as M
        teams = _hockey(conn, today)
        lam = M.team_lambdas(teams or {}, home, away)
        if not lam:
            miss = [t for t in (home, away) if t not in (teams or {})]
            return {"refused": f"we hold no recent results for {' or '.join(miss) or 'these teams'}"}
        probs = M.game_probs(*lam)
        return {"kind": "poisson", "probs": probs, "p_home": probs["home_ml"],
                "home_pts": lam[0], "away_pts": lam[1], "total": lam[0] + lam[1],
                "margin": lam[0] - lam[1],
                "inputs": [f"expected goals {home} {lam[0]:.2f}, {away} {lam[1]:.2f} in regulation, "
                           f"from each side's goals for and against"]}
    from . import futures as F
    ratings, prior_share, played = _hoops(conn, league, season)
    rh, ra = (ratings or {}).get(home), (ratings or {}).get(away)
    if rh is None or ra is None:
        miss = [t for t, r in ((home, rh), (away, ra)) if r is None]
        return {"refused": f"we hold no results for {' or '.join(miss)}"}
    edge = 0.0 if neutral else F.HOME_EDGE.get(league, 2.0)
    words = (f"{home} {rh:+.1f} and {away} {ra:+.1f} points a game against an average side"
             + (f" ({prior_share:.0%} of it still last season's — {played} games played this one)"
                if prior_share >= 0.05 else ""))
    return {"kind": "logistic", "scale": F.MARGIN_SCALE.get(league, 8.5), "margin": (rh - ra) + edge,
            "p_home": F.win_prob(league, rh, ra, neutral), "inputs": [words],
            "no_total": True}


def _season(league: str, today: str) -> int:
    """The season a date belongs to: football's from August, the rest by
    the league's own window (engine.seasons)."""
    if league == "nfl":
        return int(today[:4]) if int(today[5:7]) >= 8 else int(today[:4]) - 1
    from .seasons import season_of
    return season_of(league, today)


def _ncdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def chance(m: dict, league: str, leg: dict, home: str, away: str, picked: str):
    """``(our raw chance for the leg's side at its number, why not)``."""
    market, side = leg["market"], leg.get("side")
    line = _num(leg.get("line"), 0.0)
    if market in ("moneyline", "spread") and picked not in (home, away):
        return None, "which side the slip backs is not one of the two teams"
    if market == "moneyline":
        if m["kind"] == "poisson":
            p = m["probs"]["home_ml"] if picked == home else m["probs"]["away_ml"]
        else:
            p = m["p_home"] if picked == home else 1.0 - m["p_home"]
    elif market == "spread":
        if m["kind"] == "poisson":
            key = f"{'home' if picked == home else 'away'}_{line:+g}"
            if key not in m["probs"]:
                return None, "our hockey model prices the puck line at 1.5 goals only"
            p = m["probs"][key]
        else:
            mt = m["margin"] if picked == home else -m["margin"]
            z = mt + line
            p = (1.0 / (1.0 + math.exp(-z / m["scale"])) if m["kind"] == "logistic"
                 else _ncdf(z / m["margin_sd"]))
    else:
        if m.get("no_total"):
            return None, f"nothing of ours projects a game total in the {WORD[league]}"
        if m["kind"] == "poisson":
            from .nhl import model as M
            over = M.total_over(m["probs"], line)
        else:
            over = _ncdf((m["total"] - line) / m["total_sd"])
        p = over if side == "over" else 1.0 - over
    return max(CLAMP[0], min(CLAMP[1], p)), ""


# --- the market ---------------------------------------------------------------
def market_fair(leg: dict, g: dict | None, home: str, picked: str):
    """``(the market's chance for the leg's side, where it came from)``: the
    board's own posted moneyline pair where it has the game, else the
    slip's price with a book's usual margin taken out, else (None, "")."""
    from .odds import devig_two_way
    from .slipgrade import implied, _odds
    if leg["market"] == "moneyline" and g and _odds(g.get("home_ml")) and _odds(g.get("away_ml")):
        fh, fa = devig_two_way(int(g["home_ml"]), int(g["away_ml"]))
        if 0.0 < fh < 1.0:
            return (fh if picked == home else fa), "board"
    q = implied(leg.get("odds"))
    if q is None:
        return None, ""
    return q / (1.0 + TYPICAL_MARGIN[leg["market"]]), "slip"


def held(raw: float, fair: float | None, league: str, market: str):
    """``(our chance, credible, the haircut, measured)`` — the raw model
    pulled toward the market's number as far as this sport and market have
    earned (`gamecal`), or by the standing half where nothing is measured."""
    from . import gamebets as GB
    from .betting import MARKET_SHRINK
    got = GB.measured_shrink(league, market)[0]
    shrink = MARKET_SHRINK if got is None else float(got)
    if fair is None:
        return raw, True, shrink, got is not None
    win, _edge, credible = GB.temper(raw, fair, league, market)
    return win, bool(credible), shrink, got is not None


# --- the data behind it -------------------------------------------------------
def _finals(conn, league: str, team: str, seasons: list, limit: int | None = None) -> list:
    if conn is None:
        return []
    order = "season DESC, period DESC" if league == "nfl" else "COALESCE(date, period) DESC"
    q = (f"SELECT home, away, home_score, away_score FROM games WHERE sport=? AND (home=? OR away=?) "
         f"AND home_score IS NOT NULL AND away_score IS NOT NULL "
         f"AND season IN ({','.join('?' * len(seasons))}) ORDER BY {order}")
    rows = conn.execute(q + (f" LIMIT {int(limit)}" if limit else ""), (league, team, team, *seasons)).fetchall()
    return [tuple(r) for r in rows]


def _form(rows: list, team: str) -> tuple[int, int, float, float] | None:
    if not rows:
        return None
    w = l = 0
    pf = pa = 0.0
    for h, _a, hs, as_ in rows:
        mine, theirs = (hs, as_) if h == team else (as_, hs)
        pf, pa = pf + float(mine), pa + float(theirs)
        if mine > theirs:
            w += 1
        elif mine < theirs:
            l += 1
    return w, l, pf / len(rows), pa / len(rows)


def facts(conn, league: str, leg: dict, home: str, away: str, picked: str, today: str | None = None) -> list:
    """The data a user reads beside the number: form, meetings, and for a
    total how often each side's games went its way."""
    today = today or _today()
    season = _season(league, today)
    unit = UNITS[league]
    out = []
    bits = []
    for t in (home, away):
        f = _form(_finals(conn, league, t, [season, season - 1], FORM_GAMES), t)
        if f:
            n = f[0] + f[1]
            bits.append(f"{t} {f[0]}-{f[1]} in their last {n} ({f[2]:.1f} scored, {f[3]:.1f} allowed)")
    if bits:
        out.append(("Form", "; ".join(bits)))
    met = [r for r in _finals(conn, league, home, [season]) if {r[0], r[1]} == {home, away}]
    if met:
        hw = sum(1 for h, _a, hs, as_ in met if (hs > as_) == (h == home) and hs != as_)
        avg = sum(float(r[2]) + float(r[3]) for r in met) / len(met)
        out.append(("Head to head", f"Met {len(met)} time{'s' if len(met) != 1 else ''} this season: "
                                    f"{home} {hw}-{len(met) - hw}, {avg:.1f} {unit} a game between them"))
    line = _num(leg.get("line"))
    if leg["market"] == "total" and line is not None:
        side = leg.get("side")
        bits = []
        for t in (home, away):
            rows = _finals(conn, league, t, [season])
            if rows:
                k = sum(1 for r in rows if ((float(r[2]) + float(r[3]) > line) if side == "over"
                                            else (float(r[2]) + float(r[3]) < line)))
                bits.append(f"{t}'s went {side} {line:g} in {k} of {len(rows)}")
        if bits:
            out.append(("Totals", f"This season's games: {'; '.join(bits)}"))
    return out


def why_off(boards: dict, league: str, leg: dict, g: dict | None, home: str, away: str) -> str:
    """Why the board did not carry this exact bet, in words."""
    board = (boards or {}).get(league)
    if not board:
        return f"no {WORD[league]} board is up right now"
    if g is None:
        return f"the {WORD[league]} board doesn't have this game on its slate"
    market = leg["market"]
    cards = [r for r in board.get("game_bets") or [] if isinstance(r, dict)
             and str(r.get("market") or r.get("bet_type") or "") == market
             and {r.get("home"), r.get("away")} == {home, away}]
    if not cards:
        return "no book had posted this market when the board was built"
    line = _num(leg.get("line"))
    lines = sorted({_num(r.get("line")) for r in cards if _num(r.get("line")) is not None})
    if market == "total" and lines and line is not None:
        return f"the board prices this total at {lines[0]:g}, not {line:g}"
    if market == "spread" and lines and line is not None:
        return f"the board prices this spread at {abs(lines[0]):g}, not {abs(line):g}"
    return "the board's card for this game is at a different number"


def read(boards: dict, leg: dict, conn=None, today: str | None = None) -> dict | None:
    """Our read on one side or total the boards do not price: a row with
    our chance, the market's, the model's inputs and the facts, or None
    where the slip's words do not name a game we can find."""
    if leg.get("market") not in GAME_MARKETS:
        return None
    today = today or _today()
    sport = str(leg.get("sport") or "").lower()
    leagues = [sport] if sport in LEAGUES else list(LEAGUES)
    own = conn is None
    if own:
        from .slipread import _connect
        conn = _connect()
    try:
        found = []
        for league in leagues:
            got = teams_of(boards, leg, league, conn, today)
            if got and got[0] and got[1] and got[0] != got[1]:
                found.append((league, got))
        if len(found) != 1:
            return None
        league, (home, away, picked, g, how) = found[0]
        row = {"league": league, "home": home, "away": away, "team": picked, "market": leg["market"],
               "side": leg.get("side"), "line": _num(leg.get("line")), "units": UNITS[league],
               "why_off": why_off(boards, league, leg, g, home, away), "refused": "", "facts": [],
               "reasons": [], "oriented": how, "prob": None, "raw_prob": None}
        if g:
            row["kickoff"] = " ".join(str(x) for x in (g.get("date"), g.get("kickoff")) if x)
        if conn is None:
            row["refused"] = "our results database is not on this server"
            row["facts"] = [("Our read", f"Not on our board — {row['why_off']}.")]
            return row
        m = model(conn, league, home, away, g, today)
        p, why_not = (None, m["refused"]) if m.get("refused") else chance(m, league, leg, home, away, picked)
        fair, src = market_fair(leg, g, home, picked)
        f = [("Our read", f"Not on our board — {row['why_off']}. So we ran our {WORD[league]} game model on it")]
        if how == "guess":
            f.append(("Watch", f"Home and away aren't on our file — priced with {home} at home"))
        if p is None:
            row["refused"] = why_not
            f.append(("Our model", f"Won't put a number on it: {why_not}"))
        else:
            prob, credible, shrink, measured = held(p, fair, league, leg["market"])
            row.update(raw_prob=round(p, 4), prob=round(prob, 4), credible=credible, shrink=round(shrink, 3),
                       market_fair=None if fair is None else round(fair, 4), fair_from=src,
                       proj_margin=_num(m.get("margin")), proj_total=_num(m.get("total")))
            main = _main_line(m, league, leg, home, away, picked, p)
            row["reasons"] = [main]
            f.append(("Our model", main))
            for t in m.get("inputs") or []:
                f.append(("Ratings", t[:1].upper() + t[1:]))
            if m.get("starters"):
                f.append(("Starters", m["starters"]))
            if fair is not None:
                from .slipgrade import implied
                need = implied(leg.get("odds"))
                said = ("the board's posted prices, the margin taken out, say" if src == "board"
                        else "your price with a book's usual margin taken out says about")
                f.append(("The market", (f"Your {int(leg['odds']):+d} needs {need:.0%}; " if need is not None else "")
                          + f"{said} {fair:.0%}"))
                f.append(("Held to the market",
                          (f"We keep {shrink:.0%} of our disagreement with the market — the share that has "
                           f"held up on past {WORD[league]} {leg['market']}s" if measured else
                           f"We keep {shrink:.0%} of our disagreement with the market — nothing is measured "
                           f"for {WORD[league]} {leg['market']}s yet, so the boards' standing half")
                          + f" — so {p:.0%} becomes {prob:.0%}"))
                if not credible:
                    f.append(("Watch", f"Our model and the market are {abs(p - fair):.0%} apart — on a line "
                                       f"this efficient that is more likely our rating's error than an edge"))
        f += facts(conn, league, leg, home, away, picked, today)
        cond = (((g or {}).get("conditions") or {}).get("why") or [])[:1]
        for c in cond:
            f.append(("Conditions", str(c)))
        row["facts"] = [(k, " ".join(str(t).split())[:260]) for k, t in f if t]
        return row
    finally:
        if own and conn is not None:
            conn.close()


def _main_line(m: dict, league: str, leg: dict, home: str, away: str, picked: str, p: float) -> str:
    unit = UNITS[league]
    line = _num(leg.get("line"), 0.0)
    if leg["market"] == "moneyline":
        if m["kind"] == "poisson":
            return f"{picked} wins {p:.0%} by our numbers, overtime and the shootout included"
        return f"Our ratings make {picked} {p:.0%} to win"
    if leg["market"] == "spread":
        mg = m.get("margin") or 0.0
        fav = home if mg >= 0 else away
        return (f"We project {fav} by {abs(mg):.1f} {unit}; {picked} {line:+g} covers {p:.0%} by our numbers")
    side = leg.get("side")
    if m.get("home_pts") is not None:
        return (f"We project {m['total']:.1f} {unit} ({home} {m['home_pts']:.1f}, {away} {m['away_pts']:.1f}) "
                f"against {line:g} — the {side} {p:.0%} by our numbers")
    return f"We project {m['total']:.1f} {unit} against {line:g} — the {side} {p:.0%} by our numbers"
