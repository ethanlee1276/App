"""The WNBA script's context layer — pace, the layoff, and the star tax.

Three multipliers/rules the hoops chain priced at nothing:

§1.2 PACE. "Every counting prop scales close to linearly with
possessions" — a top-pace vs bottom-pace matchup swings volume lines
~10% before a word about the players. We hold no possession feed, but
the market total already prices pace times efficiency, so the factor is
built from tonight's total against the league norm and DAMPED BY HALF —
the total's excess is part pace (which scales volume) and part expected
efficiency (which mostly doesn't), and claiming the whole gap for
volume would double-count the half that isn't opportunity.

§6 THE LAYOFF. The 2026 season pauses Aug 31–Sep 16 for the World Cup
and resumes into an eight-day seeding sprint. The rule is written on
the GAP, not the calendar: any first game after a 10+ day team layoff
gets a shooting-efficiency haircut and a caveat, because both
populations dip in game one — World Cup players on tournament legs and
jet lag, stay-home players on 17 days of cold shooting. A date-keyed
rule would rot next season; a gap-keyed one prices every future break,
all-star pause, and postponement cluster for free.

§7 THE STAR TAX. WNBA prop handle concentrates on a few marquee names,
nearly all on overs, and books shade for it as a standing feature. The
rule set: marquee OVERS clear an extra point of required edge; marquee
UNDERS carry a structural subsidy worth saying out loud. Marquee is
gauged by the projection itself (a 20-point projection in a 40-minute
league IS the marquee tier), not by a name list that rots at every
trade. WNBA only — the tune flag decides, because the NBA's deeper
handle doesn't concentrate this way.

Standard library only.
"""

from __future__ import annotations

#: League-average game totals, the denominator of the environment
#: factor. Directional norms (WNBA totals run ~150-175 per the script;
#: NBA ~215-235), not fitted constants — the factor is damped and
#: clamped tightly enough that ±3 points of norm error moves a
#: projection by well under 1%.
LEAGUE_TOTAL = {"wnba": 162.0, "nba": 225.0}

#: Half the total's excess is credited to volume (see module docstring),
#: and the whole factor is clamped — a 20-point outlier total is a
#: blowout expectation, not a 12% volume promise.
ENV_DAMP = 0.5
ENV_CLAMP = 0.06

#: A team gap this long makes the next game a "first game back".
LAYOFF_DAYS = 10
#: The first-game-back haircut: threes are the noisiest shooting stat
#: and dip hardest; points dip mildly; rebounds/assists ride minutes
#: and legs, not stroke, and keep their number.
LAYOFF_EFF = {"fg3m": 0.95, "pts": 0.98, "pra": 0.985}

#: §7 — the marquee gauge and the extra point of required edge.
MARQUEE_PROJ_PTS = 20.0
STAR_TAX_EDGE = 0.01


def env_factor(game_total, league: str = "wnba") -> tuple[float, str | None]:
    """``(volume multiplier, reason line or None)`` from tonight's total."""
    try:
        total = float(game_total or 0.0)
    except (TypeError, ValueError):
        return 1.0, None
    norm = LEAGUE_TOTAL.get((league or "").lower())
    if not norm or total <= 0:
        return 1.0, None
    raw = (total / norm - 1.0) * ENV_DAMP
    mult = 1.0 + max(-ENV_CLAMP, min(ENV_CLAMP, raw))
    if abs(mult - 1.0) < 0.02:
        return mult, None
    word = "fast, high-scoring" if mult > 1 else "slow, low-scoring"
    return mult, (f"Total of {total:g} vs a ~{norm:g} league norm — a "
                  f"{word} environment ({(mult - 1) * 100:+.0f}% volume)")


def layoff_days(dates, game_date: str) -> int | None:
    """Days between the team's most recent logged game and tonight."""
    import datetime as _dt
    try:
        last = max(d for d in (dates or []) if d and d < game_date)
        a = _dt.date.fromisoformat(str(last)[:10])
        b = _dt.date.fromisoformat(str(game_date)[:10])
        return (b - a).days
    except (ValueError, TypeError):
        return None


def layoff_adjustment(days: int | None, stat: str) -> tuple[float, str | None]:
    """``(efficiency multiplier, caveat or None)`` for a first game back."""
    if not days or days < LAYOFF_DAYS:
        return 1.0, None
    mult = LAYOFF_EFF.get(stat, 1.0)
    return mult, (f"First game after a {days}-day layoff — shooting "
                  f"efficiency dips before legs return, for the rested "
                  f"and the tournament-worn alike")


def star_tax(stat: str, side: str, proj: float,
             tune_key: str = "wnba") -> tuple[float, str | None]:
    """``(extra required edge, reason or None)`` — §7's rule set."""
    if (tune_key or "").lower() != "wnba" or stat not in ("pts", "pra"):
        return 0.0, None
    marquee = proj >= (MARQUEE_PROJ_PTS if stat == "pts"
                       else MARQUEE_PROJ_PTS * 1.3)
    if not marquee:
        return 0.0, None
    if side == "OVER":
        return STAR_TAX_EDGE, ("Star tax — marquee overs carry the "
                               "public's shade, so this one must clear an "
                               "extra point of edge")
    return 0.0, ("Star tax works FOR this bet — marquee unders carry a "
                 "structural subsidy from the public's over money")
