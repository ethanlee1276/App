"""Team context as a PRICE, not a display — NFL Phase 2.

`engine/sources/nflpbp.py` has aggregated EPA, PROE and neutral pace per
team-week all along, and `engine/teamprofiles.py` serves them to the game
pages and the fantasy module. Nothing ever priced a prop with them: the
model doc's own line is "Model pricing hookup is Phase 2". This is it.

Two things make this harder than multiplying some numbers together.

FIRST, THE PROXIES ARE ALREADY THERE. engine/matchup.py hand-tunes an
approximation of every one of these inputs:

    _defense_factor      ≈ the opponent's def_epa
    favoured → run more  ≈ that team's proe
    total ≥ 48 → +plays  ≈ that team's pace

Stacking measurements on top of guesses double-counts. So the opponent's
defence is deliberately NOT read here — matchup.py owns that, and adding
def_epa would price the same thing twice. Pace and PROE are read, because
the spread and the total describe THIS game while pace and PROE describe
the team's standing tendency; those are different facts. Whether that is
true in practice is a question for the backtest, not for this docstring,
which is why the whole layer is switchable.

SECOND, LOOKAHEAD. A backtest of week 8 that reads season averages has
seen weeks 9-17. It would score beautifully and the live model would not
reproduce any of it, because in week 8 those games have not been played.
`profiles_through` exists solely to make that mistake impossible: it takes
the week being projected and reads strictly earlier ones.
"""

from __future__ import annotations

from .statmath import clamp

MIN_WEEKS = 4

# Markets whose volume rises with pass rate, and the one that falls.
PASS_MARKETS = {"pass_yds", "rec_yds", "receptions", "pass_tds", "completions"}
RUSH_MARKETS = {"rush_yds", "rush_att", "rush_tds"}

# How hard each measured input pushes. Deliberately gentle: sportsbook
# lines already price team tendency, so this is a nudge toward the measured
# number, not a replacement for the market's opinion.
PACE_CLAMP = (0.94, 1.07)      # ~30s vs ~34.5s per snap across the league
PROE_WEIGHT = 1.2              # PROE deltas run about ±0.05
EPA_WEIGHT = 0.25              # EPA/play deltas run about ±0.15
TOTAL_CLAMP = (0.90, 1.12)     # nothing here may run away with a projection


def profiles_through(conn, season: int, before_period: str,
                     last_n: int | None = 6, sport: str = "nfl",
                     min_weeks: int = MIN_WEEKS) -> dict:
    """{team: profile} using ONLY weeks before ``before_period``.

    The whole point. `teamprofiles.season_profiles` averages the season,
    including weeks that have not happened yet from the perspective of the
    game being priced — fine for a page showing how a team has played,
    fatal for a walk-forward backtest, which would learn from the future
    and report a number the live model can never reproduce.

    ``last_n`` keeps it a form window rather than a season average, taken
    from the weeks that survive the cut.
    """
    rows = conn.execute(
        "SELECT * FROM team_weeks WHERE sport=? AND season=? AND period<? "
        "ORDER BY team, period", (sport, season, before_period)).fetchall()
    by_team: dict[str, list] = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)

    stats = ("proe", "off_epa", "pass_epa", "rush_epa", "def_epa", "pace")
    out: dict[str, dict] = {}
    for team, weeks in by_team.items():
        # The sample guard applies to the team's TOTAL history, not to the
        # window taken from it. Checking after the slice meant any form
        # window shorter than min_weeks returned nothing at all — asking
        # for "the last 2 weeks" silently produced an empty profile and the
        # whole layer went quiet without saying why.
        if len(weeks) < min_weeks:
            continue                       # too little to say anything
        if last_n:
            weeks = weeks[-last_n:]
        prof: dict = {"weeks": len(weeks)}
        for s in stats:
            vals = [r[s] for r in weeks if r[s] is not None]
            prof[s] = (sum(vals) / len(vals)) if vals else None
        out[team] = prof
    return out


def league_means(profiles: dict) -> dict:
    """The zero point. "+0.06 EPA/play" means nothing on its own."""
    out: dict = {}
    for s in ("proe", "off_epa", "pass_epa", "rush_epa", "def_epa", "pace"):
        vals = [p[s] for p in profiles.values() if p.get(s) is not None]
        out[s] = (sum(vals) / len(vals)) if vals else None
    return out


def drift_reference(conn, season: int, before_period: str,
                    sport: str = "nfl") -> dict:
    """Each team's OWN season-to-date baseline, for the drift mode below."""
    return profiles_through(conn, season, before_period, last_n=None,
                            sport=sport, min_weeks=MIN_WEEKS)


def context_multiplier(profile: dict | None, league: dict,
                       market: str) -> tuple[float, list[str]]:
    """How this team's measured tendency shades a prop in ``market``.

    Returns ``(multiplier, reasons)``. A team with no usable profile gets
    exactly 1.0 and says nothing — silence beats inventing a nudge from
    two games, and early-season weeks are precisely when the sample is
    thinnest and the temptation greatest.
    """
    if not profile or not league:
        return 1.0, []
    reasons: list[str] = []
    mult = 1.0

    # Pace: seconds between snaps, so LOWER is faster and means more plays
    # for everyone on the field. Getting this sign backwards would invert
    # every volume adjustment in the model, silently.
    pace, lg_pace = profile.get("pace"), league.get("pace")
    if pace and lg_pace:
        f = clamp(lg_pace / pace, *PACE_CLAMP)
        mult *= f
        if abs(f - 1) >= 0.02:
            reasons.append(
                f"{'Fast' if f > 1 else 'Slow'} neutral pace — {pace:.1f}s "
                f"per snap vs {lg_pace:.1f}s league ({f - 1:+.0%} plays)")

    # PROE: pass rate over expected. Directly moves the pass/rush split,
    # which is volume, which is most of a prop.
    proe, lg_proe = profile.get("proe"), league.get("proe")
    if proe is not None and lg_proe is not None and (
            market in PASS_MARKETS or market in RUSH_MARKETS):
        d = proe - lg_proe
        f = 1.0 + PROE_WEIGHT * (d if market in PASS_MARKETS else -d)
        mult *= f
        if abs(f - 1) >= 0.02:
            side = "pass-heavy" if d > 0 else "run-heavy"
            reasons.append(f"Team is {side} — PROE {d:+.1%} vs league "
                           f"({f - 1:+.0%} for this market)")

    # Efficiency: yards per opportunity, from the side of the ball the
    # market actually lives on. Uses the team's OWN offence only; the
    # opponent's defence is matchup.py's job and pricing it here would
    # count the same fact twice.
    key = "pass_epa" if market in PASS_MARKETS else (
        "rush_epa" if market in RUSH_MARKETS else "off_epa")
    epa, lg_epa = profile.get(key), league.get(key)
    if epa is not None and lg_epa is not None:
        f = 1.0 + EPA_WEIGHT * (epa - lg_epa)
        mult *= f
        if abs(f - 1) >= 0.02:
            reasons.append(f"Offence {epa - lg_epa:+.2f} EPA/play vs league "
                           f"({f - 1:+.0%})")

    return clamp(mult, *TOTAL_CLAMP), reasons


def drift_multiplier(recent: dict | None, own_baseline: dict | None,
                     market: str) -> tuple[float, list[str]]:
    """Team tendency as CHANGE, not as level — the variant that can work.

    Pricing a team's pace and pass rate against the LEAGUE made the model
    worse on every axis that matters (MAE 23.09→23.28, ROI +13.5%→+1.0%
    over 2,626 props), and the reason is not subtle once seen: the
    projection starts from ``form.mean``, which is the player's own recent
    games ON THIS TEAM. A receiver in a fast, pass-heavy offence already
    carries that pace and that pass rate in his own numbers. Multiplying by
    the team's level counts it a second time and overshoots.

    Drift is the part form has NOT absorbed: this team over its last few
    weeks against this team over the season so far. A team that has just
    started playing faster has a player whose logs still describe the
    slower version. That is new information; the level was not.
    """
    if not recent or not own_baseline:
        return 1.0, []
    reasons: list[str] = []
    mult = 1.0

    pace, base_pace = recent.get("pace"), own_baseline.get("pace")
    if pace and base_pace:
        f = clamp(base_pace / pace, *PACE_CLAMP)
        mult *= f
        if abs(f - 1) >= 0.02:
            reasons.append(
                f"Playing {'faster' if f > 1 else 'slower'} lately — "
                f"{pace:.1f}s per snap vs its own {base_pace:.1f}s "
                f"({f - 1:+.0%} plays)")

    proe, base_proe = recent.get("proe"), own_baseline.get("proe")
    if (proe is not None and base_proe is not None
            and (market in PASS_MARKETS or market in RUSH_MARKETS)):
        d = proe - base_proe
        f = 1.0 + PROE_WEIGHT * (d if market in PASS_MARKETS else -d)
        mult *= f
        if abs(f - 1) >= 0.02:
            reasons.append(
                f"Throwing {'more' if d > 0 else 'less'} than its own norm — "
                f"PROE {d:+.1%} ({f - 1:+.0%} for this market)")

    return clamp(mult, *TOTAL_CLAMP), reasons
