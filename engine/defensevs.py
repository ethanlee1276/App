"""Defense versus position: what each defense gives up, per game, to each position.

Ethan, 2026-09-23: "I was looking up top offenses and top defenses and
worst offenses and worst defenses and looking up what the exact player
matchups would be … where a really good offense and tight end might be
playing a really bad corner … the Lions corners were giving up a lot of
yards to Chris Olave during the Saints game. So then I went and took a
bunch of Bills wide receivers for touchdowns and that was all winning."

What the model had before this: one yards-allowed number per position,
averaged over every player who appeared (a defence that faced five
receivers looked stingier than one that faced three), WR1, WR2 and slot
all the same number, NOTHING for touchdowns allowed (the anytime-TD model
borrowed the yards number, at full strength), and no allowance for how
few games a September rating rests on.

What this is: for every defence, per GAME, the totals it conceded to each
position group — receiving yards, catches and touchdowns to wide
receivers, tight ends and backs, rushing yards and touchdowns to backs,
passing yards and touchdowns to quarterbacks — against the league's
average, walk-forward (only games before the week being priced), and
shrunk toward average by how many games it rests on:

    factor = 1 + (raw - 1) * games / (games + SHRINK_GAMES)

Two weeks of a secondary being torched is a signal and also mostly noise;
the shrink is how much of each. How much of a defence's factor actually
reaches ONE player is a separate, measured number per market and
position — TRANSFER below, from `python3 defensefit.py`
(engine/defensefit.py) — and which rating the model reads for it is
MODEL_STAT, also measured: for receivers that is the defence's overall
pass defence, and for touchdowns to receivers nothing, because nothing
predicted them.

What box scores cannot say: which corner covered which receiver. nflverse
has no coverage assignments; those come from paid charting (PFF, FTN's
full product). So "a bad corner" is measured here as what the defence
gives up to the position — which is what Olave's day against Detroit
shows up as.
"""
from __future__ import annotations

#: Position groups, from nflverse's `position` column.
GROUP_OF = {"QB": "QB", "WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB", "HB": "RB"}

#: stat -> (group, the columns summed, words)
STATS = {
    "qb_pass_yds": ("QB", ("passing_yards",), "passing yards"),
    "qb_pass_td": ("QB", ("passing_tds",), "passing TDs"),
    "wr_rec_yds": ("WR", ("receiving_yards",), "receiving yards to WRs"),
    "wr_rec": ("WR", ("receptions",), "catches by WRs"),
    "wr_td": ("WR", ("receiving_tds", "rushing_tds"), "TDs to WRs"),
    "te_rec_yds": ("TE", ("receiving_yards",), "receiving yards to TEs"),
    "te_rec": ("TE", ("receptions",), "catches by TEs"),
    "te_td": ("TE", ("receiving_tds", "rushing_tds"), "TDs to TEs"),
    "rb_rush_yds": ("RB", ("rushing_yards",), "rushing yards to RBs"),
    "rb_rec_yds": ("RB", ("receiving_yards",), "receiving yards to RBs"),
    "rb_rec": ("RB", ("receptions",), "catches by RBs"),
    "rb_td": ("RB", ("rushing_tds", "receiving_tds"), "TDs to RBs"),
}

#: Games of evidence that count as much as the league average does. Fitted
#: by engine/defensefit.py (the value that best predicts the next game).
SHRINK_GAMES = 12.0


def _f(row: dict, key: str) -> float:
    try:
        v = row.get(key)
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _week(row: dict) -> int:
    try:
        return int(float(row.get("week") or 0))
    except (TypeError, ValueError):
        return 0


def _regular(row: dict) -> bool:
    return str(row.get("season_type") or row.get("game_type") or "REG") in ("REG", "")


def allowed_by_game(rows: list[dict], upto_week: int) -> dict:
    """{defence: {week: {stat: total conceded}}} for regular-season weeks before ``upto_week``."""
    out: dict = {}
    for r in rows:
        wk = _week(r)
        if not (0 < wk < upto_week) or not _regular(r):
            continue
        team = str(r.get("opponent_team") or r.get("opponent") or "").strip()
        group = GROUP_OF.get(str(r.get("position") or r.get("position_group") or "").upper())
        if not team or not group:
            continue
        game = out.setdefault(team, {}).setdefault(wk, {s: 0.0 for s in STATS})
        for stat, (g, cols, _w) in STATS.items():
            if g == group:
                game[stat] += sum(_f(r, c) for c in cols)
    return out


def ratings(rows: list[dict], upto_week: int, shrink: float = SHRINK_GAMES,
            prior: dict | None = None) -> dict:
    """{defence: {stat: {"pg", "league", "raw", "factor", "rank", "of", "games"}}}.

    ``rank`` is 1 for the defence that gives up the MOST of that stat per
    game (the softest), so "ranked 1st" always reads as the best matchup.
    ``prior`` (last season's ratings) is where a defence starts from
    instead of the league average, when it is given."""
    games = allowed_by_game(rows, upto_week)
    per_game = {t: {s: sum(g[s] for g in wk.values()) / len(wk) for s in STATS}
                for t, wk in games.items() if wk}
    if not per_game:
        return {}
    league = {s: sum(p[s] for p in per_game.values()) / len(per_game) for s in STATS}
    out: dict = {}
    for team, p in per_game.items():
        n = len(games[team])
        row = {}
        for s in STATS:
            raw = p[s] / league[s] if league[s] > 0 else 1.0
            centre = 1.0
            if prior and team in prior and s in prior[team]:
                centre = float(prior[team][s].get("factor", 1.0))
            w = n / (n + shrink) if (n + shrink) > 0 else 1.0
            row[s] = {"pg": round(p[s], 2), "league": round(league[s], 2), "raw": round(raw, 4),
                      "factor": round(centre + (raw - centre) * w, 4), "games": n}
        out[team] = row
    teams = sorted(out)
    for s in STATS:
        order = sorted(teams, key=lambda t: (-out[t][s]["pg"], t))
        for i, t in enumerate(order):
            out[t][s]["rank"] = i + 1
            out[t][s]["of"] = len(order)
    return out


def stat_for(position: str, market: str) -> str | None:
    """Which defensive stat a prop on this position and market reads."""
    g = GROUP_OF.get(str(position or "").upper())
    if not g:
        return None
    if market in ("anytime_td", "td", "tds"):
        return {"QB": None, "WR": "wr_td", "TE": "te_td", "RB": "rb_td"}[g]
    if market == "pass_yds":
        return "qb_pass_yds" if g == "QB" else None
    if market == "rush_yds":
        return "rb_rush_yds" if g == "RB" else None
    if market == "rec_yds":
        return {"WR": "wr_rec_yds", "TE": "te_rec_yds", "RB": "rb_rec_yds"}.get(g)
    if market == "receptions":
        return {"WR": "wr_rec", "TE": "te_rec", "RB": "rb_rec"}.get(g)
    return None


#: WHICH RATING THE MODEL USES, per (market, position), where it differs
#: from the one shown. Measured four ways over 2022-2025 with each season
#: held out in turn (`python3 defensefit.py`):
#:
#:   * receivers and tight ends: what a defence gives up to THEIR position
#:     did not predict their next game beyond their own form (held-out
#:     gain −0.06% WR yards, −0.12% TE yards). The defence's overall pass
#:     defence did (+0.14%, +0.15%; catches +0.14%, +0.40%), so that is
#:     what prices them;
#:   * touchdowns to receivers and tight ends: nothing tried predicted them
#:     (−0.39% and −0.12% by position, −0.42% and −0.11% by pass defence),
#:     so the model leaves them alone. The matchup is still SHOWN;
#:   * everything else uses its own position's rating.
MODEL_STAT = {
    ("rec_yds", "WR"): "qb_pass_yds", ("receptions", "WR"): "qb_pass_yds",
    ("rec_yds", "TE"): "qb_pass_yds", ("receptions", "TE"): "qb_pass_yds",
    ("anytime_td", "WR"): None, ("anytime_td", "TE"): None, ("anytime_td", "QB"): None,
}


def model_stat(position: str, market: str) -> str | None:
    """The rating the projection multiplies by for this position and market, or None."""
    g = GROUP_OF.get(str(position or "").upper())
    if (market, g) in MODEL_STAT:
        return MODEL_STAT[(market, g)]
    return stat_for(position, market)


#: How much of a defence's factor reaches one player: ``1 + TRANSFER·(factor − 1)``.
#: Fitted on 2022-2025 with the ratings above (shrunk 12 games toward last
#: season's). Re-measure with `python3 defensefit.py`.
#: ±SE from the fit; the held-out gains are in the MODEL_STAT note above.
TRANSFER = {
    ("pass_yds", "QB"): 0.73,       # ±0.15   n 1,523   held-out +1.52%, every season positive
    ("rush_yds", "RB"): 0.72,       # ±0.11   n 3,027   held-out +1.46%, every season positive
    ("rec_yds", "RB"): 0.39,        # ±0.15   n 1,489   held-out +0.36%
    ("receptions", "RB"): 0.47,     # ±0.12   n 2,161   held-out +0.23%
    ("anytime_td", "RB"): 0.45,     # ±0.12   n 3,887   held-out +0.32%
    ("rec_yds", "WR"): 0.57,        # ±0.15   n 5,214   (pass defence) held-out +0.14%
    ("receptions", "WR"): 0.45,     # ±0.13   n 4,908   (pass defence) held-out +0.14%
    ("rec_yds", "TE"): 0.79,        # ±0.26   n 2,107   (pass defence) held-out +0.15%
    ("receptions", "TE"): 0.86,     # ±0.22   n 2,167   (pass defence) held-out +0.40%
}


def transfer(position: str, market: str) -> float:
    return TRANSFER.get((market, GROUP_OF.get(str(position or "").upper())), 0.0)


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def num(x) -> str:
    """155.53 → "155.5", 1.0 → "1": a per-game figure as a person reads it."""
    return f"{float(x):.1f}".rstrip("0").rstrip(".")


def matchup_card(team: str, rating: dict, stat: str, also: str | None = None) -> dict | None:
    """What goes under a pick: the defence, what it gives up to this position, where that ranks."""
    r = (rating or {}).get(stat)
    if not r:
        return None
    _g, _c, words = STATS[stat]
    games = r["games"]
    card = {"opponent": team, "stat": words, "per_game": round(float(r["pg"]), 1),
            "league": round(float(r["league"]), 1), "rank": r["rank"], "of": r["of"], "games": games,
            "text": (f"{team} allow {num(r['pg'])} {words} a game, the {_ord(r['rank'])}-most "
                     f"(league {num(r['league'])}), over {games} game{'s' if games != 1 else ''}")}
    t = (rating or {}).get(also) if also and also != stat else None
    if t:
        card["also"] = {"stat": STATS[also][2], "per_game": round(float(t["pg"]), 2), "rank": t["rank"],
                        "of": t["of"]}
        per = f"{float(t['pg']):.1f}" if also.endswith("_td") else num(t["pg"])
        card["text"] += f"; {per} {STATS[also][2]} a game ({_ord(t['rank'])}-most)"
    return card


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def effect(team: str, rating: dict, position: str, market: str) -> tuple[float, str, dict | None]:
    """(multiplier, reason, card) for one prop against this defence.

    The card shows what the defence gives up to the player's OWN position in
    this market, with a second line beside it (touchdowns under a yards
    prop, yards under a touchdown prop). The multiplier reads what was
    MEASURED to predict it (MODEL_STAT) at the measured strength (TRANSFER);
    where nothing predicted, it is 1.0 and the card says so."""
    show = stat_for(position, market)
    g = GROUP_OF.get(str(position or "").upper())
    also = (stat_for(position, "anytime_td") if market != "anytime_td"
            else {"WR": "wr_rec_yds", "TE": "te_rec_yds", "RB": "rb_rush_yds"}.get(g))
    card = matchup_card(team, rating, show, also) if show else None
    stat = model_stat(position, market)
    b = transfer(position, market)
    r = (rating or {}).get(stat) if stat else None
    if not r or not b:
        if card:
            card["model"] = {"reads": None, "applied": 1.0,
                             "note": "shown for you; it has not predicted this bet, so the model leaves it out"}
        return 1.0, "", card
    factor = _clamp(1.0 + b * (float(r["factor"]) - 1.0), 0.80, 1.25)
    words = STATS[stat][2]
    if card:
        card["model"] = {"reads": words, "applied": round(factor, 3)}
    reason = ""
    if factor >= 1.03:
        reason = (f"Soft matchup — {team} allow the {_ord(r['rank'])}-most {words} "
                  f"({num(r['pg'])} a game) (×{factor:.2f})")
    elif factor <= 0.97:
        best = r["of"] - r["rank"] + 1
        reason = (f"Tough matchup — {team} allow the {_ord(best)}-fewest {words} "
                  f"({num(r['pg'])} a game) (×{factor:.2f})")
    return factor, reason, card
