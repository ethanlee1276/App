"""Walk-forward moneyline backtest against harvested book prices.

The prop backtest answers "does the player model beat the book?"; this answers
the same question for the GAME model. It replays the season chronologically:
for each game with a harvested closing moneyline, team ratings are computed
from games strictly BEFORE that date (same shrinkage as
:mod:`engine.teamrates`), the production pricing (:func:`gamebets
.price_moneyline` on :func:`gamebets.mlb_win_prob` / ``nfl_win_prob``) decides
a side, and the final score settles it.

Honesty notes:
  * Harvested moneylines are the BEST price across books at the snapshot —
    slightly kinder than any single book's close.
  * Doubleheaders collapse to one row (games are keyed by date+matchup), so a
    twin bill contributes a single settled game.
  * The replayed model is ratings-only — no starting pitcher, park, or rest
    context — so this measures the floor of the game model, not the ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import starters_by_game
from .gamebets import SCORING_BASELINE, mlb_win_prob, nfl_win_prob, price_moneyline
from .odds import american_to_decimal, devig_two_way

# Same shrinkage as engine.teamrates.compute_team_ratings: early-season records
# are regressed toward league average.
SHRINK = 6.0
# A starter's record firms up over this many starts before it's fully trusted.
PITCHER_SHRINK = 5.0


def moneyline_closes(conn, sport: str, book: str = "best") -> dict:
    """``{(date, home, away): {team: odds}}`` for one book — the last
    harvested snapshot on each date is that day's close. ``book="best"`` is
    the shopped-best aggregate; a book title (e.g. ``"Pinnacle"``) selects
    that book's own prices."""
    q = ("SELECT taken_at, home, away, player, over_odds FROM odds_history "
         "WHERE sport=? AND market='moneyline' AND book=? ORDER BY taken_at")
    out: dict = {}
    for r in conn.execute(q, (sport, book)):
        date = str(r["taken_at"])[:10]
        game = out.setdefault((date, r["home"], r["away"]), {})
        # Ordered by taken_at, so later same-date snapshots overwrite.
        game[r["player"]] = r["over_odds"]
    return out


@dataclass
class MoneylineBacktest:
    sport: str = "mlb"
    use_pitchers: bool = False
    starters_known: int = 0    # quoted games where both starters were stored
    games_seen: int = 0        # completed games walked over
    games_quoted: int = 0      # had a harvested price AND enough team history
    n_bets: int = 0
    wins: int = 0
    staked: float = 0.0
    net: float = 0.0
    brier: float = 0.0         # of P(home win) over every quoted game
    home_rate: float = 0.0     # how often home actually won (quoted games)
    mean_home_prob: float = 0.0
    #: Which numbers were replayed — see `GameLineBacktest.source`.
    source: str = "real harvested closes"
    grades: dict = field(default_factory=dict)
    prices: dict = field(default_factory=dict)   # favorite vs underdog picks

    @property
    def roi(self) -> float:
        return (self.net / self.staked) if self.staked else 0.0

    def summary(self) -> str:
        flavor = "pitcher-aware" if self.use_pitchers else "ratings only"
        lines = [
            f"{self.sport.upper()} moneyline backtest · {self.source} · {flavor}",
            f"  Games       {self.games_seen} completed, "
            f"{self.games_quoted} with a book price + team history",
        ]
        if self.use_pitchers and self.games_quoted:
            lines.append(f"  Starters    known for {self.starters_known}"
                         f"/{self.games_quoted} quoted games")
        if self.games_quoted:
            lines.append(
                f"  Model       Brier {self.brier:.4f}   mean P(home) "
                f"{self.mean_home_prob:.0%} vs actual home wins {self.home_rate:.0%}")
        if self.n_bets:
            lines.append(
                f"  Bets        {self.n_bets} placed, {self.wins} won "
                f"({self.wins / self.n_bets:.1%})  ROI {self.roi:+.1%}  "
                f"net {self.net:+.2f}u")
            for name in ("Strong Play", "Play", "Lean"):
                g = self.grades.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:11} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
            for name in ("favorite", "underdog"):
                g = self.prices.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:11} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
        elif self.games_quoted:
            lines.append("  Bets        none graded above Pass")
        if not self.games_quoted:
            lines.append("  No games had both a harvested moneyline and enough "
                         "team history — harvest h2h odds first (harvest_odds.py "
                         "--markets h2h)")
        elif self.source.startswith("schedule"):
            lines.append("  Priced vs the market's CLOSING CONSENSUS from the "
                         "schedule feed — beating it is beating the field, "
                         "which is a different (and harder) claim than "
                         "beating one book's posted number")
        else:
            lines.append("  Priced vs REAL closing moneylines (best across "
                         "books) — a genuine market-relative result")
        return "\n".join(lines)


def _pitcher_quality(p_agg: dict, name: str | None, baseline: float) -> float:
    """A starter's quality as runs allowed by his team per start, shrunk
    toward the league baseline. Passed into ``mlb_win_prob`` in place of xERA
    — only the home/away DIFFERENCE matters there, so the centering constant
    cancels and an unknown starter is exactly neutral."""
    if not name or name not in p_agg:
        return baseline
    runs, n = p_agg[name]
    if not n:
        return baseline
    return baseline + (runs / n - baseline) * (n / (n + PITCHER_SHRINK))


def _rating(agg: dict, team: str, baseline: float) -> float | None:
    """Net rating from running (points-for, points-against, games) sums —
    identical math to teamrates.compute_team_ratings."""
    pf, pa, n = agg.get(team, (0.0, 0.0, 0))
    if not n:
        return None
    factor = n / (n + SHRINK)
    off = (pf / n - baseline) * factor
    def_ = (pa / n - baseline) * factor
    return off - def_


def backtest_moneylines(conn, sport: str = "mlb", min_team_games: int = 15,
                        use_pitchers: bool = False) -> MoneylineBacktest:
    """Replay every completed game in the DB, betting only where a harvested
    moneyline exists and both teams have ``min_team_games`` of prior history.

    ``use_pitchers`` (MLB) adds each starter's walk-forward quality — runs
    allowed by his team per start, shrunk over ``PITCHER_SHRINK`` starts — via
    the same pitcher term the live model uses, so a single run A/Bs the
    ratings-only floor against the pitcher-aware model on identical games.
    """
    closes = moneyline_closes(conn, sport)
    # Harvested first, schedule second — see `schedule_closes` for why the
    # provenance is reported rather than blurred.
    source = "real harvested closes"
    if not closes:
        closes = {k: {k[1]: h, k[2]: a}
                  for k, (h, a) in schedule_moneylines(conn, sport).items()}
        if closes:
            source = "schedule closes · nflverse closing consensus"
    baseline = SCORING_BASELINE.get(sport, 0.0)
    # Named, not defaulted. `else nfl_win_prob` meant any sport we had not
    # thought about — college football most obviously — would be replayed
    # with the NFL's win curve and the NFL's hard-coded 13.5-point margin
    # SD, and would produce a confident, wrong backtest that looked exactly
    # like a real one. A model that has no curve here should say so.
    CURVES = {"mlb": mlb_win_prob, "nfl": nfl_win_prob}
    if sport not in CURVES:
        raise ValueError(
            f"No win-probability curve for {sport!r}. This backtest replays "
            f"games through a sport's OWN margin model; borrowing another "
            f"league's would produce a confident number about nothing. "
            f"Supported: {', '.join(sorted(CURVES))}.")
    win_prob = CURVES[sport]
    use_pitchers = use_pitchers and sport == "mlb"
    starters = starters_by_game(conn, sport) if use_pitchers else {}

    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()

    r = MoneylineBacktest(sport=sport, use_pitchers=use_pitchers, source=source)
    agg: dict[str, tuple[float, float, int]] = {}
    p_agg: dict[str, tuple[float, int]] = {}   # pitcher -> (runs allowed, starts)
    sq_err = 0.0
    home_wins = 0
    prob_sum = 0.0

    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        sp = starters.get((date, f"{away}@{home}"), {})

        quote = closes.get((date, home, away))
        h_net = _rating(agg, home, baseline)
        a_net = _rating(agg, away, baseline)
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)
        home_ml = quote.get(home) if quote else None
        away_ml = quote.get(away) if quote else None

        if enough and home_ml is not None and away_ml is not None:
            if use_pitchers:
                if sp.get(home) and sp.get(away):
                    r.starters_known += 1
                wp_home = mlb_win_prob(
                    h_net, a_net,
                    _pitcher_quality(p_agg, sp.get(home), baseline),
                    _pitcher_quality(p_agg, sp.get(away), baseline))
            else:
                wp_home = win_prob(h_net, a_net)
            home_won = hs > as_
            r.games_quoted += 1
            sq_err += (wp_home - (1.0 if home_won else 0.0)) ** 2
            home_wins += 1 if home_won else 0
            prob_sum += wp_home

            # `sport` matters: it selects the MEASURED market haircut
            # (engine.gamecal). Without it this replayed a pricer no board
            # runs, and reported bets production would never place.
            rec = price_moneyline(home, away, wp_home,
                                  int(home_ml), int(away_ml), sport=sport)
            if rec.grade != "Pass":
                stake = rec.stake_units if rec.stake_units > 0 else 1.0
                won = home_won == rec.pick_is_home
                gain = ((american_to_decimal(rec.odds) - 1.0) * stake
                        if won else -stake)
                r.n_bets += 1
                r.wins += 1 if won else 0
                r.staked += stake
                r.net += gain
                for key, bucket in ((rec.grade, r.grades),
                                    ("favorite" if rec.odds < 0 else "underdog",
                                     r.prices)):
                    b = bucket.setdefault(key, {"n_bets": 0, "wins": 0,
                                                "staked": 0.0, "net": 0.0})
                    b["n_bets"] += 1
                    b["wins"] += 1 if won else 0
                    b["staked"] += stake
                    b["net"] += gain

        # Only after any bet: today's result joins each team's — and each
        # starter's — history.
        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)
        if use_pitchers:
            for starter, allowed in ((sp.get(home), as_), (sp.get(away), hs)):
                if starter:
                    runs, n = p_agg.get(starter, (0.0, 0))
                    p_agg[starter] = (runs + allowed, n + 1)

    if r.games_quoted:
        r.brier = sq_err / r.games_quoted
        r.home_rate = home_wins / r.games_quoted
        r.mean_home_prob = prob_sum / r.games_quoted
    return r


# --- sharp-anchor strategy ---------------------------------------------------
@dataclass
class SharpAnchorReport:
    """P&L of the sharp-anchor strategy: de-vig the sharp book's two-sided
    price as fair probability, bet the shopped soft-book price whenever it
    pays better than fair. No model opinion involved — the "edge" is purely
    one book disagreeing with a sharper one."""
    sport: str = "mlb"
    sharp: str = "Pinnacle"
    min_ev: float = 0.015
    max_ev: float = 0.15
    games_seen: int = 0        # completed games walked over
    games_priced: int = 0      # had BOTH a sharp pair and a soft best price
    n_bets: int = 0
    wins: int = 0
    staked: float = 0.0
    net: float = 0.0
    ev_sum: float = 0.0        # claimed EV at bet time, for honesty checks
    suspicious: int = 0        # "edges" past max_ev — broken prices, not bets
    prices: dict = field(default_factory=dict)   # favorite vs underdog
    ev_buckets: dict = field(default_factory=dict)

    @property
    def roi(self) -> float:
        return (self.net / self.staked) if self.staked else 0.0

    def summary(self) -> str:
        lines = [
            f"{self.sport.upper()} sharp-anchor backtest · {self.sharp} de-vig "
            f"vs shopped soft-book closes (min EV {self.min_ev:.1%})",
            f"  Games       {self.games_seen} completed, "
            f"{self.games_priced} with both a {self.sharp} pair and a soft price",
        ]
        if not self.games_priced:
            lines.append(f"  No games priced — harvest {self.sharp} closes first:")
            lines.append("    python3 harvest_odds.py mlb --from <start> --to <end> "
                         "--markets h2h --books pinnacle --budget 2500")
            return "\n".join(lines)
        if self.suspicious:
            lines.append(
                f"  Filtered    {self.suspicious} \"edge(s)\" above "
                f"{self.max_ev:.0%} EV — a closing gap that size is a broken "
                f"price (in-play or suspended market), not a bet")
        if self.n_bets:
            lines.append(
                f"  Bets        {self.n_bets} placed, {self.wins} won "
                f"({self.wins / self.n_bets:.1%})  ROI {self.roi:+.1%}  "
                f"net {self.net:+.2f}u   (avg claimed EV "
                f"{self.ev_sum / self.n_bets:+.1%})")
            for name, g in sorted(self.ev_buckets.items()):
                if g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        EV {name:7} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
            for name in ("favorite", "underdog"):
                g = self.prices.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:9} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
        else:
            lines.append("  Bets        none cleared the EV bar — soft closes "
                         "rarely stray this far from sharp closes; edges live "
                         "earlier in the day")
        return "\n".join(lines)


def backtest_sharp_anchor(conn, sport: str = "mlb", sharp: str = "Pinnacle",
                          min_ev: float = 0.015,
                          max_ev: float = 0.15) -> SharpAnchorReport:
    """Replay the season betting ONLY price disagreements: soft-book best
    price vs the sharp book's de-vigged fair probability, settled by the
    final score. This is the strategy's honest floor — it compares closing
    prices to closing prices, and soft books have mostly converged to sharp
    ones by then; a live version gets to act earlier, when gaps are wider."""
    sharp_closes = moneyline_closes(conn, sport, book=sharp)
    soft_closes = moneyline_closes(conn, sport, book="best")

    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()

    r = SharpAnchorReport(sport=sport, sharp=sharp, min_ev=min_ev, max_ev=max_ev)
    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        sp = sharp_closes.get((date, home, away)) or {}
        soft = soft_closes.get((date, home, away)) or {}
        if home not in sp or away not in sp or (home not in soft and away not in soft):
            continue
        r.games_priced += 1
        fair_home, fair_away = devig_two_way(int(sp[home]), int(sp[away]))

        for team, fair_p, won in ((home, fair_home, hs > as_),
                                  (away, fair_away, as_ > hs)):
            odds = soft.get(team)
            if odds is None:
                continue
            odds = int(odds)
            ev = fair_p * american_to_decimal(odds) - 1.0
            if ev < min_ev:
                continue
            if ev > max_ev:
                r.suspicious += 1
                continue
            eb = r.ev_buckets.setdefault(
                "<4%" if ev < 0.04 else ("4-8%" if ev < 0.08 else "8-15%"),
                {"n_bets": 0, "wins": 0, "staked": 0.0, "net": 0.0})
            gain = (american_to_decimal(odds) - 1.0) if won else -1.0
            r.n_bets += 1
            r.wins += 1 if won else 0
            r.staked += 1.0
            r.net += gain
            r.ev_sum += ev
            for b in (r.prices.setdefault(
                          "favorite" if odds < 0 else "underdog",
                          {"n_bets": 0, "wins": 0, "staked": 0.0, "net": 0.0}),
                      eb):
                b["n_bets"] += 1
                b["wins"] += 1 if won else 0
                b["staked"] += 1.0
                b["net"] += gain
    return r


# ===========================================================================
# Spreads and totals — the layer that had never been graded
# ===========================================================================
# The moneyline backtest above has existed for a while. Spreads and totals
# never had one, for a boring reason: the closing numbers were not stored.
# The build asked the API for h2h, spreads and totals, attached all three to
# the slate, priced bets off all three — and journaled only h2h. So the
# spread/total model could be argued about and not measured, which is how it
# ended up shipping with no market shrink and no credibility ceiling at all.
#
# engine.lineledger now writes those closes on every build (free — the
# prices are already in memory), and engine.sources.oddshistory stores them
# on a paid historical harvest. This replays them.

def game_line_closes(conn, sport: str, market: str, book: str = "best") -> dict:
    """``{(date, home, away): (line, odds_a, odds_b)}`` — last snapshot wins.

    For a total: ``(line, over_odds, under_odds)``. For a spread: the HOME
    team's number and ``(home_odds, away_odds)``.
    """
    q = ("SELECT taken_at, home, away, line, over_odds, under_odds "
         "FROM odds_history WHERE sport=? AND market=? AND book=? "
         "ORDER BY taken_at")
    out: dict = {}
    for r in conn.execute(q, (sport, market, book)):
        if r["line"] is None or r["over_odds"] is None or r["under_odds"] is None:
            continue
        out[(str(r["taken_at"])[:10], r["home"], r["away"])] = (
            float(r["line"]), int(r["over_odds"]), int(r["under_odds"]))
    return out


#: Whose consensus a schedule close actually is. "nflverse" was hardcoded
#: into the header, which was right for the only sport that had schedule
#: closes and became a false label the day college football's arrived off
#: the cfbfastR mirror.
SCHEDULE_FEED = {"nfl": "nflverse", "cfb": "cfbfastR mirror"}


def schedule_closes(conn, sport: str, market: str,
                    require_prices: bool = True) -> dict:
    """The same shape as `game_line_closes`, read off the SCHEDULE.

    THE GAP THIS CLOSES, measured 2026-08-27 after ingesting four NFL
    seasons: 1,139 completed games, and the backtest reported "0 with a
    stored close" for every market — then advised harvesting the numbers
    from a paid odds API. They were on disk the whole time. nflverse
    ships the closing spread, total, both spread prices, both total
    prices and both moneylines in the same schedule row as the scores,
    and `engine/ingest.nfl_game_rows` now keeps all of them.

    PROVENANCE DIFFERS FROM A HARVEST AND THE CALLER IS TOLD, because
    these are not one book's quote: nflverse's spread_line and total_line
    are the market's closing consensus. That is arguably a better thing
    to grade a model against than any single book — you cannot beat a
    number nobody offered — but it is a different claim, and a backtest
    that blurred the two would be reporting an edge over the field as an
    edge over a counter.

    ``require_prices`` exists for a feed that carries the LINE and not
    the two prices beside it. College football's closes arrive that way
    (`engine.sources.cfblines`): the mirror publishes every book's
    number and no -110s. That is fatal for a backtest, which has to
    price a bet — and irrelevant to `engine.gamecal`, which measures how
    far our number sits from the market's number and never reads a
    price. So the caller says which it is, and a priceless close comes
    back as ``(line, None, None)`` rather than being silently dropped
    into "0 graded games with a close".
    """
    import json as _json
    # `extra` holds the two prices, so it is required only when prices
    # are. Demanding it unconditionally means a feed that stores a LINE
    # and nothing else has its closes dropped before the
    # `require_prices` flag ever gets a say — the exact failure that flag
    # exists to prevent, one query earlier.
    q = ("SELECT period, home, away, spread, total, extra FROM games "
         "WHERE sport=? AND home_score IS NOT NULL")
    if require_prices:
        q += " AND extra IS NOT NULL"
    out: dict = {}
    for r in conn.execute(q, (sport,)):
        try:
            px = _json.loads(r["extra"] or "{}")
        except (TypeError, ValueError):
            px = {}
        if market == "total":
            line, pair = r["total"], px.get("total_odds")
        else:
            line, pair = r["spread"], px.get("spread_odds")
        if line is None:
            continue
        if not pair or len(pair) != 2:
            if require_prices:
                continue
            out[(str(r["period"]), r["home"], r["away"])] = (
                float(line), None, None)
            continue
        out[(str(r["period"]), r["home"], r["away"])] = (
            float(line), int(pair[0]), int(pair[1]))
    return out


def schedule_moneylines(conn, sport: str) -> dict:
    """``{(period, home, away): (home_odds, away_odds)}`` off the schedule."""
    import json as _json
    out: dict = {}
    for r in conn.execute(
            "SELECT period, home, away, extra FROM games WHERE sport=? "
            "AND home_score IS NOT NULL AND extra IS NOT NULL", (sport,)):
        try:
            ml = (_json.loads(r["extra"] or "{}") or {}).get("ml")
        except (TypeError, ValueError):
            continue
        if not ml or len(ml) != 2:
            continue
        out[(str(r["period"]), r["home"], r["away"])] = (int(ml[0]), int(ml[1]))
    return out


@dataclass
class GameLineBacktest:
    sport: str = "mlb"
    market: str = "total"
    games_seen: int = 0
    games_quoted: int = 0      # had a stored close AND enough team history
    n_bets: int = 0
    wins: int = 0
    pushes: int = 0
    staked: float = 0.0
    net: float = 0.0
    refused: int = 0
    #: Games whose stored close carries a LINE but no price. They measure
    #: the projection and can never be bet — counted apart so the gap is
    #: visible rather than inferred from a small `n_bets`.
    unpriced: int = 0           # priced, but over the credibility ceiling
    mae: float = 0.0           # mean |projection - closing number|, in points
    # WHERE THE NUMBERS CAME FROM. A harvested close is one book's quote at
    # one instant; a schedule close is the market's closing consensus. Beating
    # the second is not the same claim as beating the first, so the header
    # says which one was replayed rather than letting the reader assume.
    source: str = "real stored closes"
    _abs_err: float = 0.0
    grades: dict = field(default_factory=dict)

    @property
    def roi(self) -> float:
        return (self.net / self.staked) if self.staked else 0.0

    def summary(self) -> str:
        lines = [
            f"{self.sport.upper()} {self.market} backtest · {self.source}",
            f"  Games       {self.games_seen} completed, "
            f"{self.games_quoted} with a stored close + team history",
        ]
        if self.games_quoted:
            # The number that actually matters. If the model sits four points
            # off the closing number on average, no gate downstream can save
            # it — and that is exactly what an inflated edge board looks like
            # from the inside.
            lines.append(f"  Projection  off the closing number by "
                         f"{self.mae:.2f} pts on average")
            lines.append(f"  Refused     {self.refused} priced games exceeded the "
                         f"credibility ceiling")
        if self.n_bets:
            decided = self.n_bets - self.pushes
            rate = (self.wins / decided) if decided else 0.0
            lines.append(
                f"  Bets        {self.n_bets} placed, {self.wins} won, "
                f"{self.pushes} push ({rate:.1%})  ROI {self.roi:+.1%}  "
                f"net {self.net:+.2f}u")
            for name in ("Strong Play", "Play"):
                g = self.grades.get(name)
                if g and g["n_bets"]:
                    roi = g["net"] / g["staked"] if g["staked"] else 0.0
                    lines.append(f"        {name:11} {g['n_bets']:>4} bets, "
                                 f"{g['wins']} won  ROI {roi:+.1%}")
            # 30 bets is noise dressed as a verdict; say so on the same line
            # as the ROI rather than in a footnote nobody reads.
            if self.n_bets < 100:
                lines.append(f"  ⚠️  {self.n_bets} bets is not a verdict — at this "
                             f"sample a ±{1.0 / max(self.n_bets, 1) ** 0.5:.0%} "
                             f"swing is ordinary luck")
        elif self.games_quoted:
            lines.append("  Bets        none graded above Pass")
        if not self.games_quoted:
            lines.append(f"  No stored {self.market} closes for {self.sport}. "
                         f"They accumulate free on every build from now on "
                         f"(engine.lineledger); for past dates, harvest with "
                         f"harvest_odds.py.")
        return "\n".join(lines)


def _settle_total(line: float, side: str, hs: float, as_: float):
    """(won, push) for an over/under on the combined score."""
    combined = hs + as_
    if combined == line:
        return False, True
    return ((combined > line) if side == "Over" else (combined < line)), False


def _settle_spread(line: float, picked_home: bool, hs: float, as_: float):
    """(won, push). ``line`` is the HOME number; home covers when the
    margin plus its spread is positive."""
    edge = (hs - as_) + line
    if edge == 0:
        return False, True
    return (edge > 0) == picked_home, False


def backtest_game_lines(conn, sport: str, market: str = "total",
                        min_team_games: int = 15) -> GameLineBacktest:
    """Replay stored spread/total closes through the PRODUCTION pricer.

    Deliberately calls gamebets.price_total / price_spread rather than
    reimplementing them, so the shrink, the credibility ceiling and the
    grade ladder under test are the ones that ship. A backtest of a model
    you do not run is a number about nothing.
    """
    from .gamebets import (price_total, price_spread, project_total,
                           project_team_points, game_margin, _sd, SCORING_BASELINE)
    if market not in ("total", "spread"):
        raise ValueError(f"market must be 'total' or 'spread', got {market!r}")
    # Refuse rather than borrow, same as the pricer: a sport with no
    # registered variance cannot be replayed through another league's.
    baseline = _sd(SCORING_BASELINE, sport, "scoring baseline")

    # A UNION, NOT AN OR-ELSE. This read the harvested closes and fell
    # back to the schedule only when the harvest was COMPLETELY empty —
    # so one stored row for one game hid the schedule's numbers for every
    # other game in the database. `engine.gamecal` had the identical bug
    # and the identical fix ("Stop a harvest that cannot join from hiding
    # a schedule that can"), where a single date-keyed harvested row
    # shadowed 899 week-keyed schedule closes.
    #
    # Schedule first so a harvested row OVERWRITES it: a stored book
    # close is a real counter's number and outranks a consensus.
    #
    # `require_prices=False` because a close with no price still measures
    # the LINE, and college football's 3,132 mirror closes are all
    # priceless — under the old default the CFB game model had thousands
    # of stored closes and no way to be graded against any of them. What
    # a priceless close may NOT do is produce a bet; see below.
    schedule = schedule_closes(conn, sport, market, require_prices=False)
    harvested = game_line_closes(conn, sport, market)
    closes = dict(schedule)
    closes.update(harvested)
    # THE PROVENANCE IS NAMED, and the feed with it. A harvested close is
    # one counter's quote; a schedule close is the field's consensus, and
    # a report that blurred them would present an edge over the field as
    # an edge over a book. Now that both can appear in one replay, the
    # header has to say when they did.
    feed = SCHEDULE_FEED.get(sport, "schedule")
    consensus = f"schedule closes · {feed} closing consensus"
    if harvested and len(closes) > len(harvested):
        source = f"real stored closes, topped up from {consensus}"
    elif harvested:
        source = "real stored closes"
    else:
        source = consensus
    rows = conn.execute(
        "SELECT period, home, away, home_score, away_score FROM games "
        "WHERE sport=? AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period", (sport,)).fetchall()

    r = GameLineBacktest(sport=sport, market=market, source=source)
    agg: dict[str, tuple[float, float, int]] = {}

    for row in rows:
        date, home, away = row["period"], row["home"], row["away"]
        hs, as_ = float(row["home_score"]), float(row["away_score"])
        r.games_seen += 1
        quote = closes.get((date, home, away))
        enough = (agg.get(home, (0, 0, 0))[2] >= min_team_games
                  and agg.get(away, (0, 0, 0))[2] >= min_team_games)

        if quote and enough:
            h_off, h_def = _split(agg, home, baseline)
            a_off, a_def = _split(agg, away, baseline)
            line, odds_a, odds_b = quote
            r.games_quoted += 1

            # THE PROJECTION AGAINST THE LINE, which needs no price. This
            # is the half of the measurement a priceless close can still
            # answer, and for college football it is the only half there
            # is.
            if market == "total":
                proj = project_total(sport, h_off, h_def, a_off, a_def)
                r._abs_err += abs(proj - line)
            else:
                h_net = h_off - h_def
                a_net = a_off - a_def
                proj = game_margin(sport, h_net, a_net)
                # The stored line is the home number; the card may back away.
                r._abs_err += abs(proj + line)

            # NO PRICE, NO BET. The pricer needs two real numbers — it
            # raises on None — and defaulting them to -110 would publish
            # an ROI computed against a price no book ever offered, which
            # is the one thing this replay exists to avoid. Counted, so
            # the gap is visible rather than implied by a small n_bets.
            if odds_a is None or odds_b is None:
                r.unpriced += 1
                pf, pa, n = agg.get(home, (0.0, 0.0, 0))
                agg[home] = (pf + hs, pa + as_, n + 1)
                pf, pa, n = agg.get(away, (0.0, 0.0, 0))
                agg[away] = (pf + as_, pa + hs, n + 1)
                continue

            if market == "total":
                card = price_total(sport, home, away, proj, line, odds_a, odds_b)
                settle = lambda: _settle_total(line, card["side"], hs, as_)
            else:
                card = price_spread(sport, home, away, proj, line, odds_a, odds_b)
                picked_home = card["team"] == home
                settle = lambda: _settle_spread(line, picked_home, hs, as_)

            if not card["credible"]:
                r.refused += 1
            if card["grade"] != "Pass":
                won, push = settle()
                stake = card["stake_units"] if card["stake_units"] > 0 else 1.0
                gain = (0.0 if push else
                        ((american_to_decimal(card["odds"]) - 1.0) * stake
                         if won else -stake))
                r.n_bets += 1
                r.wins += 1 if won else 0
                r.pushes += 1 if push else 0
                r.staked += 0.0 if push else stake
                r.net += gain
                b = r.grades.setdefault(card["grade"], {"n_bets": 0, "wins": 0,
                                                        "staked": 0.0, "net": 0.0})
                b["n_bets"] += 1
                b["wins"] += 1 if won else 0
                b["staked"] += 0.0 if push else stake
                b["net"] += gain

        pf, pa, n = agg.get(home, (0.0, 0.0, 0))
        agg[home] = (pf + hs, pa + as_, n + 1)
        pf, pa, n = agg.get(away, (0.0, 0.0, 0))
        agg[away] = (pf + as_, pa + hs, n + 1)

    if r.games_quoted:
        r.mae = r._abs_err / r.games_quoted
    return r


def _split(agg: dict, team: str, baseline: float) -> tuple[float, float]:
    """(offense, defense) ratings vs league baseline — the same shrunk form
    engine.teamrates computes, so the replay prices what the live board
    would have priced."""
    pf, pa, n = agg.get(team, (0.0, 0.0, 0))
    if not n:
        return 0.0, 0.0
    factor = n / (n + SHRINK)
    return (pf / n - baseline) * factor, (pa / n - baseline) * factor
