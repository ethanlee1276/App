"""SCALPY NHL — EDGE HUNTER 1.0: the NHL's model for EDGE bets.

Ethan, 2026-10-03: "here is the model to use for nhl EDGE bets. this model
is not to be used for nhl most likely bets." Win-First (Scalpy NHL 1.0,
engine/nhl/model.py) asks what is most likely to happen and feeds Most
Likely; this asks what the book's price implies, what we think the true
chance is, how far apart they are — and whether the gap is REAL. The two
are never blended into one rating: a row carries Win-First's grade and
Edge Hunter's classification side by side.

A bet becomes an Edge Play only when both answers are yes:

  A. Is the price wrong?  Our probability (after the market haircut every
     board applies) minus the de-vigged market probability, against a
     per-market minimum (MARKET_MIN_EDGE — 3 points on a moneyline, 8 on
     an anytime scorer), with positive EV at the best price a reader can
     bet.
  B. Is our estimate good?  The FALSE-EDGE FILTER: a settled starter for a
     goalie-dependent bet, a stable role, a real sample, more than one
     book on the number, no injury designation, the shot model and the
     player's own record at the line pointing the same way, and at least
     two independent hockey reasons beyond the discrepancy itself ("Our
     formula just likes it" is not enough).

THE 100-POINT EDGE SCORE uses Ethan's weights (EDGE_WEIGHTS). Where our
data carries the factor it is scored; where it does not apply to a market
(a goalie's edge on a blocked-shots prop) its weight is left out and the
score is rescaled over the factors that do — so a prop is never marked
down for a factor that cannot touch it. SHOT QUALITY comes from our own
expected-goals model (engine/nhl/xg.py, fitted on the league's play-by-play):
where it has the shots, "process" reads the opponent's 5-on-5 expected goals
against a game for a goal-driven prop and each side's 5-on-5 xG share for a
game line, and "goalie" reads goals saved above expected (goals allowed ÷
expected, regressed); without it they fall back to shots for and against
from our box scores and the REGRESSED save rate (named when his raw rate
runs hot or cold against it — the regression hunting ground). WHAT OUR
DATA DOES NOT CARRY YET, said rather than faked: line combinations and PP
units (NHL EDGE / MoneyPuck are not wired). "deployment" reads ice time and
its trend; "special teams" reads power-play goals. Opening lines and CLV are tracked by the
journal like every board's.

Tiers (Ethan's): Elite 8%+ with strong support and low/moderate variance;
Strong 5-7.9%; Small 3-4.9%; Pass. Staking: quarter Kelly, capped by tier
(Elite 1.5u, Strong 1.0u, Small 0.5u) and at 0.25u for a high-variance
market (goals, assists) whatever its tier — "Edge does not mean lottery
tickets".
"""
from __future__ import annotations

MODEL = "Scalpy NHL — Edge Hunter 1.0"

#: The least probability edge each market needs to be a play — bigger for
#: the volatile markets, as Ethan set them.
MARKET_MIN_EDGE = {
    "moneyline": 0.03, "spread": 0.045, "total": 0.035, "team_total": 0.04,
    "sog": 0.05, "saves": 0.05, "blocks": 0.06, "points": 0.06,
    "assists": 0.07, "anytime_goal": 0.08, "goals": 0.10,
}
#: Probability-edge tiers.
TIERS = ((0.08, "Elite edge"), (0.05, "Strong edge"), (0.03, "Small edge"))
#: How much a single outcome swings, per market: Elite needs low/moderate.
VARIANCE = {"sog": "low", "saves": "low", "moneyline": "low", "spread": "moderate",
            "total": "moderate", "team_total": "moderate", "blocks": "moderate",
            "points": "moderate", "assists": "high", "anytime_goal": "high", "goals": "high"}
#: Ethan's 100-point edge score.
EDGE_WEIGHTS = {"discrepancy": 25, "process": 20, "goalie": 15, "deployment": 10, "volume": 10,
                "roster": 7, "special_teams": 5, "rest": 3, "market": 5}
LABELS = {"discrepancy": "Model vs market", "process": "Shot process", "goalie": "Goalie edge",
          "deployment": "Deployment", "volume": "Shot volume", "roster": "Injury / roster",
          "special_teams": "Special teams", "rest": "Rest", "market": "Market confirmation"}
#: A factor scoring this share of its weight counts as a supporting reason.
SUPPORT_SHARE = 0.6
#: Independent supporting reasons a play needs, and an Elite edge.
MIN_SUPPORT, ELITE_SUPPORT = 2, 3
#: Quarter Kelly, then these caps by tier; a high-variance market is
#: "speculative" and capped lower whatever its tier.
STAKE_CAP = {"Elite edge": 1.5, "Strong edge": 1.0, "Small edge": 0.5}
SPECULATIVE_CAP = 0.25
#: Fewer games than this is too small a sample to trust a discrepancy.
MIN_GAMES = 10
#: Markets whose outcome turns on who is in net (the skater's goal-driven
#: markets read the OPPOSING starter; saves read his own).
GOALIE_DEPENDENT = {"goals", "anytime_goal", "points", "assists", "saves",
                    "moneyline", "spread", "total"}
#: Skater markets that turn on goals (process reads chances allowed).
GOAL_DRIVEN = {"goals", "anytime_goal", "points", "assists"}
#: The player's own record at the line is "Model B"; it is shrunk toward
#: the market by this many phantom games before it votes.
RECORD_PRIOR_GAMES = 10


def classify(edge: float) -> str:
    for bar, label in TIERS:
        if edge >= bar:
            return label
    return "Pass"


def fair_odds(p: float) -> int | None:
    """American odds a probability is worth: 0.54 -> -117."""
    if not 0.0 < p < 1.0:
        return None
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def ev_per_dollar(p: float, odds: int) -> float:
    """P(win) x profit if it wins - P(loss) x the stake, per $1."""
    if not odds:
        return 0.0
    profit = odds / 100 if odds > 0 else 100 / -odds
    return p * profit - (1 - p)


def _a(market: str) -> str:
    """"a points" / "an anytime goal" — the market named with its article."""
    word = market.replace("_", " ")
    return ("an " if word[:1] in "aeiou" else "a ") + word


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _league_avg(teams: dict, key: str) -> float | None:
    vals = [t.get(key) for t in (teams or {}).values() if t.get(key)]
    return sum(vals) / len(vals) if vals else None


def _score(parts: dict) -> int:
    """The 100-point score over the factors that apply to this bet."""
    have = sum(EDGE_WEIGHTS[k] for k in parts)
    got = sum(pts for pts, _n in parts.values())
    return round(100 * got / have) if have else 0


def _record_vote(values: list, line: float, side: str, fair: float) -> float | None:
    """Model B: his own record at this line over his newest games, shrunk
    toward the market's number. None under a real sample."""
    vals = [float(v) for v in values or []][:20]
    if len(vals) < MIN_GAMES:
        return None
    hits = sum(1 for v in vals if (v > line if side == "OVER" else v < line))
    return (hits + fair * RECORD_PRIOR_GAMES) / (len(vals) + RECORD_PRIOR_GAMES)


def _finish(market: str, side_word: str, win: float, fair: float, edge: float, odds: int,
            book: str, credible: bool, parts: dict, passes: list, flags: list, context: dict) -> dict:
    """Score, filter, tier and stake one candidate."""
    from ..staking import kelly_units
    ev = ev_per_dollar(win, odds)
    supports = [k for k, (pts, _n) in parts.items()
                if k not in ("discrepancy", "roster") and pts >= SUPPORT_SHARE * EDGE_WEIGHTS[k]]
    need = MARKET_MIN_EDGE.get(market, 0.05)
    if not credible:
        passes.append("our number disagrees with the market by more than we credit")
    if edge < need:
        passes.append(f"edge {edge:+.1%} is under the {need:.0%} {_a(market)} bet needs")
    if ev <= 0:
        passes.append("no positive expected value at the best price")
    if len(supports) < MIN_SUPPORT and edge >= need:
        passes.append("fewer than two independent hockey reasons — only the formula likes it")
    variance = VARIANCE.get(market, "moderate")
    tier = classify(edge)
    if tier == "Elite edge" and (len(supports) < ELITE_SUPPORT or variance == "high" or flags):
        tier = "Strong edge"
    play = not passes and tier != "Pass"
    stake = 0.0
    if play:
        cap = SPECULATIVE_CAP if variance == "high" else STAKE_CAP[tier]
        stake = round(min(kelly_units(win, odds, 0.25), cap), 2)
        play = stake > 0
        if not play:
            passes.append("Kelly finds no stake at this price")
    why = [parts[k][1] for k in sorted(supports, key=lambda k: -parts[k][0]) if parts[k][1]]
    risks = passes or flags
    return {
        "model": MODEL, "market": market, "side": side_word,
        "classification": tier if play else "Pass", "tier_by_edge": classify(edge), "play": play,
        "best_book": book, "best_price": odds,
        "market_prob": round(fair, 4), "model_prob": round(win, 4), "edge": round(edge, 4),
        "min_edge": need, "fair_odds": fair_odds(win), "ev": round(ev, 4),
        "edge_score": _score(parts), "variance": variance, "stake_units": stake,
        "support": len(supports),
        "why_market_wrong": why[:4],
        "components": [{"key": k, "label": LABELS[k], "points": round(pts, 1), "weight": EDGE_WEIGHTS[k],
                        "note": note} for k, (pts, note) in parts.items()],
        "passes": passes, "flags": flags,
        "main_risk": risks[0] if risks else (f"{variance} variance market" if variance != "low"
                                             else "the price moving before puck drop"),
        **context,
    }


def assess_prop(market: str, side: str, line: float, win: float, fair: float, edge: float,
                odds: int, book: str, credible: bool, proj: dict, p: dict, team: str, opponent: str,
                ctx: dict | None = None, teams: dict | None = None, league: dict | None = None,
                quotes: list | None = None, scalpy_pass: str = "", injury_status: str = "") -> dict:
    """Edge Hunter's verdict on one priced prop (the side Edge pricing chose)."""
    ctx, teams, league = ctx or {}, teams or {}, league or {}
    me, them = ctx.get(team) or {}, ctx.get(opponent) or {}
    goalie = market == "saves"
    d = 1 if side == "OVER" else -1
    parts: dict = {}
    passes, flags = [], []

    parts["discrepancy"] = (EDGE_WEIGHTS["discrepancy"] * _clamp(edge / 0.10),
                            f"model {win:.0%} vs market {fair:.0%} ({edge:+.1%})")
    # PROCESS — for a goal-driven prop, the chances the opponent allows at
    # 5-on-5 (our expected goals); otherwise shots for and against a game.
    xavg, xopp = _league_avg(teams, "xga_ev"), (teams.get(opponent) or {}).get("xga_ev")
    key = "sog_for" if goalie else "sog_against"
    avg, opp_rate = _league_avg(teams, key), (teams.get(opponent) or {}).get(key)
    if market in GOAL_DRIVEN and xavg and xopp:
        z = xopp / xavg - 1
        parts["process"] = (EDGE_WEIGHTS["process"] * _clamp(d * z / 0.12),
                            f"{opponent} allows {xopp:.2f} expected goals a game at 5-on-5 ({z:+.0%} vs the league)")
    elif avg and opp_rate:
        z = opp_rate / avg - 1
        what = "takes" if goalie else "allows"
        parts["process"] = (EDGE_WEIGHTS["process"] * _clamp(d * z / 0.08),
                            f"{opponent} {what} {opp_rate:.1f} shots a game ({z:+.0%} vs the league)")
    # GOALIE — the probable starter's regressed save rate, and regression.
    lsv = league.get("sv")
    if goalie and me.get("sv") is not None and lsv:
        diff = me["sv"] - lsv
        parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + d * diff / 0.02),
                           f"{me.get('starter') or 'the starter'} saves .{round(me['sv'] * 1000):03d} "
                           f"regressed ({diff:+.3f} vs the league)"
                           + (f", {me['gsax']:+.1f} goals saved above expected lately"
                              if me.get("gsax") is not None else ""))
    elif market in GOALIE_DEPENDENT and not goalie:
        if not them.get("starter_sure"):
            passes.append(f"{opponent}'s starting goalie is not settled — no goalie-dependent bet")
        elif them.get("gskill") is not None:
            # Goals allowed ÷ expected, regressed: above 1 lets in more than
            # his shots were worth — more goals for this skater.
            lean = them["gskill"] - 1
            note = (f"faces {them.get('starter')}, {them.get('gsax', 0):+.1f} goals saved above expected "
                    f"lately (lets in {them['gskill']:.2f}× what his shots were worth, regressed)")
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + d * lean / 0.10), note)
        elif them.get("sv") is not None and lsv:
            diff = lsv - them["sv"]
            note = (f"faces {them.get('starter')}, .{round(them['sv'] * 1000):03d} regressed "
                    f"({-diff:+.3f} vs the league)")
            raw = them.get("raw_sv")
            if raw is not None and abs(raw - them["sv"]) >= 0.008:
                note += (f"; his raw .{round(raw * 1000):03d} runs "
                         f"{'hot' if raw > them['sv'] else 'cold'} — regression "
                         f"{'toward more' if raw > them['sv'] else 'toward fewer'} goals")
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + d * diff / 0.02), note)
    # DEPLOYMENT — ice time and its direction; a goalie's share of starts.
    games = [g for g in (p or {}).get("games") or [] if g.get("toi", 0) > 0]
    if goalie:
        share = me.get("starter_share") or 0.0
        parts["deployment"] = (EDGE_WEIGHTS["deployment"] * _clamp((share - 0.5) / 0.4),
                               f"started {share:.0%} of {team}'s recent games")
    else:
        t5 = [g["toi"] for g in games[:5]]
        t15 = [g["toi"] for g in games[5:15]]
        if len(t5) == 5 and len(t15) >= 5:
            move = sum(t5) / 5 / (sum(t15) / len(t15)) - 1
            parts["deployment"] = (EDGE_WEIGHTS["deployment"] * _clamp(0.5 + d * move / 0.20),
                                   f"ice time {sum(t5) / 5:.1f} min lately ({move:+.0%} on the 10 before)")
    # VOLUME — the projection against the number.
    mean = float(proj.get("mean") or 0.0)
    if line:
        gap = (mean - line) / max(line, 0.5)
        parts["volume"] = (EDGE_WEIGHTS["volume"] * _clamp(d * gap / 0.25),
                           f"projects {mean:.2f} against the {line:g} line")
    # ROSTER.
    if injury_status:
        passes.append(f"listed {injury_status} — lineup uncertain")
        parts["roster"] = (0.0, f"listed {injury_status}")
    else:
        parts["roster"] = (float(EDGE_WEIGHTS["roster"]), "no injury designation")
    # SPECIAL TEAMS — power-play goals as the PP-role signal.
    if not goalie and games:
        ppg = sum(g.get("ppg", 0.0) for g in games[:20])
        share = 1.0 if ppg >= 3 else 0.5 if ppg >= 1 else 0.0
        parts["special_teams"] = (EDGE_WEIGHTS["special_teams"] * (share if d > 0 else 1 - share),
                                  f"{int(ppg)} power-play goal(s) in his last 20")
    # REST.
    if not goalie and (me.get("b2b") or them.get("b2b")):
        tired_them = bool(them.get("b2b")) and not me.get("b2b")
        parts["rest"] = (EDGE_WEIGHTS["rest"] * (1.0 if tired_them == (d > 0) else 0.0),
                         f"{opponent if tired_them else team} on the second night of a back-to-back")
    if me.get("b2b"):
        flags.append("second night of a back-to-back")
    # MARKET CONFIRMATION — how many books are on this number, and agree.
    on_line = [q for q in quotes or [] if q.get("line") == line and q.get("over_odds")]
    books = len({q.get("book") for q in on_line})
    if books <= 1:
        passes.append("only one book on this number — the price may be stale")
        parts["market"] = (0.0, "one book on the number")
    else:
        parts["market"] = (EDGE_WEIGHTS["market"] * _clamp((books - 1) / 3),
                           f"{books} books on the {line:g} line")
    # THE REST OF THE FALSE-EDGE FILTER.
    if scalpy_pass:
        passes.append(f"role or script uncertain ({scalpy_pass})")
    if (proj.get("n") or len(games)) < MIN_GAMES:
        passes.append(f"only {proj.get('n') or len(games)} games of history — too small a sample")
    vote = _record_vote(proj.get("recent") or [], line, side, fair)
    if vote is not None and (vote - fair) * (win - fair) < 0:
        passes.append(f"models disagree: the shot model says {win:.0%}, his own record at "
                      f"{line:g} says {vote:.0%}")
    context = {
        "goalie": (f"{them.get('starter')} for {opponent}" if not goalie and them.get("starter")
                   else f"{me.get('starter')} in net" if goalie else "not settled"),
        "role": (f"{proj.get('toi', 0):.1f} min a game" if not goalie
                 else f"{me.get('starter_share', 0):.0%} of starts"),
        "game_script": (f"{team} {me['xg']:.2f} – {opponent} {them['xg']:.2f} expected goals"
                        if me.get("xg") is not None and them.get("xg") is not None else ""),
        "matchup": parts.get("process", (0, ""))[1],
        "record_vote": round(vote, 4) if vote is not None else None,
    }
    return _finish(market, side, win, fair, edge, odds, book, credible, parts, passes, flags, context)


def assess_game(card: dict, home: str, away: str, ctx: dict | None = None,
                teams: dict | None = None, league: dict | None = None) -> dict:
    """Edge Hunter's verdict on one game line (moneyline, puck line, total)."""
    ctx, teams, league = ctx or {}, teams or {}, league or {}
    market = card.get("bet_type") or card.get("market") or ""
    win, fair, edge = float(card.get("win_prob") or 0), float(card.get("fair_prob") or 0), float(card.get("edge") or 0)
    odds = int(card.get("odds") or 0)
    hc, ac = ctx.get(home) or {}, ctx.get(away) or {}
    parts: dict = {"discrepancy": (EDGE_WEIGHTS["discrepancy"] * _clamp(edge / 0.10),
                                   f"model {win:.0%} vs market {fair:.0%} ({edge:+.1%})")}
    passes, flags = [], []
    if not (hc.get("starter_sure") and ac.get("starter_sure")):
        passes.append("a starting goalie is not settled — no goalie-dependent bet")
    if market == "total":
        d = 1 if str(card.get("side") or "").lower() == "over" else -1
        lg = _league_avg(teams, "sog_for")
        both = [(teams.get(t) or {}).get("sog_for") for t in (home, away)]
        if lg and all(both):
            z = sum(both) / (2 * lg) - 1
            parts["process"] = (EDGE_WEIGHTS["process"] * _clamp(0.5 + d * z / 0.10),
                                f"the two clubs take {sum(both):.0f} shots a game together ({z:+.0%} vs the league)")
        lsv = league.get("sv")
        if hc.get("gskill") is not None and ac.get("gskill") is not None:
            lean = (hc["gskill"] + ac["gskill"]) / 2 - 1
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + d * lean / 0.08),
                               f"starters {hc.get('gsax', 0):+.1f} and {ac.get('gsax', 0):+.1f} goals saved "
                               f"above expected")
        elif lsv and hc.get("sv") is not None and ac.get("sv") is not None:
            diff = lsv - (hc["sv"] + ac["sv"]) / 2
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + d * diff / 0.015),
                               f"starters .{round(hc['sv'] * 1000):03d} and .{round(ac['sv'] * 1000):03d} regressed")
    else:
        team = card.get("team") or ""
        other = away if team == home else home
        mine, theirs = teams.get(team) or {}, teams.get(other) or {}
        if mine.get("xgf_ev") and theirs.get("xgf_ev") and mine.get("xga_ev") and theirs.get("xga_ev"):
            xshare = lambda t: t["xgf_ev"] / (t["xgf_ev"] + t["xga_ev"])  # noqa: E731
            gap = xshare(mine) - xshare(theirs)
            parts["process"] = (EDGE_WEIGHTS["process"] * _clamp(0.5 + gap / 0.08),
                                f"{team} holds {xshare(mine):.0%} of its games' 5-on-5 expected goals, "
                                f"{other} {xshare(theirs):.0%}")
        elif mine.get("sog_for") and theirs.get("sog_for"):
            share = lambda t: t["sog_for"] / max(t["sog_for"] + t.get("sog_against", t["sog_for"]), 1)  # noqa: E731
            gap = share(mine) - share(theirs)
            parts["process"] = (EDGE_WEIGHTS["process"] * _clamp(0.5 + gap / 0.06),
                                f"{team} wins {share(mine):.0%} of its games' shots, {other} {share(theirs):.0%}")
        mc, tc = ctx.get(team) or {}, ctx.get(other) or {}
        if mc.get("gskill") is not None and tc.get("gskill") is not None:
            gap = tc["gskill"] - mc["gskill"]
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + gap / 0.10),
                               f"{mc.get('starter')} {mc.get('gsax', 0):+.1f} vs "
                               f"{tc.get('starter')} {tc.get('gsax', 0):+.1f} goals saved above expected")
        elif mc.get("sv") is not None and tc.get("sv") is not None:
            gap = mc["sv"] - tc["sv"]
            parts["goalie"] = (EDGE_WEIGHTS["goalie"] * _clamp(0.5 + gap / 0.02),
                               f"{mc.get('starter')} .{round(mc['sv'] * 1000):03d} vs "
                               f"{tc.get('starter')} .{round(tc['sv'] * 1000):03d} regressed")
        if mc.get("b2b") or tc.get("b2b"):
            parts["rest"] = (EDGE_WEIGHTS["rest"] * (1.0 if tc.get("b2b") and not mc.get("b2b") else 0.0),
                             f"{other if tc.get('b2b') else team} on the second night of a back-to-back")
        if mc.get("b2b"):
            flags.append("second night of a back-to-back")
    if not card.get("credible", True):
        pass                                   # _finish says it
    context = {"goalie": f"{hc.get('starter') or '?'} / {ac.get('starter') or '?'}",
               "role": "", "matchup": parts.get("process", (0, ""))[1],
               "game_script": (f"{home} {hc['xg']:.2f} – {away} {ac['xg']:.2f} expected goals"
                               if hc.get("xg") is not None and ac.get("xg") is not None else ""),
               "record_vote": None}
    side = card.get("pick_label") or card.get("side") or ""
    return _finish(market, side, win, fair, edge, odds, card.get("book") or "", bool(card.get("credible", True)),
                   parts, passes, flags, context)


#: Pairs on one game that point opposite ways (Ethan's correlation engine):
#: a team's moneyline with its own goalie's saves UNDER, and the reverse.
def contradictions(plays: list[dict]) -> list[tuple[dict, dict, str]]:
    """``[(weaker, stronger, why)]`` among plays on the same game."""
    out = []
    for i, a in enumerate(plays):
        for b in plays[i + 1:]:
            why = _contradicts(a, b) or _contradicts(b, a)
            if why:
                weak, strong = sorted((a, b), key=lambda r: (r["edge_hunter"]["edge_score"],
                                                             r["edge_hunter"]["edge"]))
                out.append((weak, strong, why))
    return out


def _contradicts(a: dict, b: dict) -> str:
    """A moneyline on a team with a saves bet on either goalie that argues
    the other way: backing a team and its goalie facing a flood (OVER)
    is a mild contradiction; backing a team and the OTHER goalie under
    (few shots for the team you backed) is the strong one."""
    if a.get("bet_type") != "moneyline" or b.get("market") != "saves":
        return ""
    team = a.get("team")
    if b.get("team") != team and b.get("side") == "UNDER":
        return f"{team} to win needs shots on {b.get('player')}; his saves UNDER bets against them"
    if b.get("team") == team and b.get("side") == "OVER":
        return f"{team} to win usually means fewer shots on {b.get('player')}; his saves OVER bets on more"
    return ""
