"""Bullpen fatigue — measured relief workload over the last two days.

A bullpen that covered nine innings across yesterday's doubleheader is not
the same bullpen tonight: the high-leverage arms are unavailable or gassed,
and the innings 6-9 that decide totals and late hitter production go to the
mop-up end of the pen. Books price bullpen QUALITY well; day-to-day
WORKLOAD is a situational input they're slower to fully price.

Everything comes from the free MLB Stats API boxscores we already fetch for
lineup projection: each team's last two completed games, relief innings =
everyone after the starter. Yesterday's innings count in full, the day
before at half weight (arms mostly bounce back after one rest day).

Discipline: the multiplier is a nudge (max +6% to opposing hitters),
applied only when the measured workload is clearly above normal, with a
readable reason on the card.
"""

from __future__ import annotations

from ..statmath import clamp

# A normal pen throws ~3-3.5 relief innings a night; the weighted two-day
# score therefore centers near 5. Below TIRED_MIN nothing fires.
YESTERDAY_WEIGHT = 1.0
DAY_BEFORE_WEIGHT = 0.5
TIRED_MIN = 6.0
PER_INNING = 0.012
FACTOR_MAX = 1.06


def ip_to_float(ip) -> float:
    """Baseball innings notation → real innings ("5.2" = 5 and 2 outs)."""
    try:
        s = str(ip)
        if "." in s:
            whole, outs = s.split(".", 1)
            return int(whole or 0) + int(outs or 0) / 3.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def parse_relief_innings(box: dict, side: str) -> float:
    """Relief innings for one side of a boxscore: every pitcher after the
    starter (the boxscore's ``pitchers`` list is in appearance order)."""
    team = (box.get("teams") or {}).get(side, {}) or {}
    order = team.get("pitchers", []) or []
    players = team.get("players", {}) or {}
    total = 0.0
    for pid in order[1:]:
        st = ((players.get(f"ID{pid}", {}) or {}).get("stats", {}) or {}) \
            .get("pitching", {}) or {}
        total += ip_to_float(st.get("inningsPitched", 0))
    return round(total, 1)


def fatigue_factor(score: float) -> float:
    """Workload score → multiplier on OPPOSING hitter production. 1.0 until
    the pen is clearly overworked, then ~1.2% per extra relief inning,
    capped — a nudge, not a lever."""
    if score < TIRED_MIN:
        return 1.0
    return round(clamp(1.0 + (score - TIRED_MIN) * PER_INNING, 1.0, FACTOR_MAX), 3)


#: The OTHER side of a tired pen, and the one this module originally
#: missed. A manager with no available relievers rides his starter
#: longer — that is the most reliably observable managerial behaviour in
#: baseball, and it lands directly on the outs market. Outs move more
#: than strikeouts because the extra work is innings, not stuff: a
#: sixth and seventh inning add outs at the starter's ordinary rate,
#: while his K rate per batter does not improve for being left in.
LEASH_PER_INNING = 0.010
LEASH_MAX = 1.05
#: Strikeouts inherit the leash at half strength — more batters faced,
#: same per-batter stuff, and a tiring starter's rate usually falls.
LEASH_K_SHARE = 0.5


def leash_factor(score: float, market_is_outs: bool = True) -> float:
    """Own-pen workload → multiplier on the STARTER's own length.

    Mirror image of :func:`fatigue_factor`: that one prices what a tired
    pen gives the opposing HITTERS, this one prices what it asks of the
    starter in front of it. Same shape, same discipline — flat until the
    workload is clearly abnormal, then a bounded nudge.

    **This factor is one-directional, and that is worth stating.** The
    clamp floors it at 1.0, so a tired pen can lengthen a start and a
    FRESH pen cannot shorten one — a manager with a full bullpen and a
    manager with an ordinary one produce the identical 1.000. Every
    adjustment this function can make pushes a pitcher projection UP.

    That is a defensible reading (the tired-pen effect is the reliably
    observable one; the rested-pen effect is real but weaker and less
    certain) and it is not being changed here. But it has a betting
    consequence that showed up in the record, so it is written down: on
    2026-08-06 the journal measured pitcher-market OVERS missing their
    claimed probability by 24.9% while pitcher UNDERS BEAT theirs by 9.1%
    — a 34-point asymmetry on 29 bets, against 3.9 points across 187
    hitter-market bets. A model that can only ever raise a pitcher
    projection is exactly what that pattern would look like.

    29 bets convicts nothing (z -1.66), so nothing here moves on it. The
    claim is registered in the hypothesis lab instead and re-tested free
    on every settle pass; if it hardens, THIS is the function to revisit,
    and the question to ask is whether "pen fresh" deserves a factor
    below 1.0 rather than the same 1.000 an ordinary pen gets.

    **The obvious next step has since been measured, and it lost.** The
    reason to care about the leash at all is the two-part story: a
    pitcher's stat is a RATE times a LENGTH, the manager sets the length,
    so model the length and the rest follows. `ratecheck.py` walked that
    forward over 6,792 real starts across 255 pitchers and found:

      * length is the STABLE term, not the volatile one — strikeouts per
        out varies 46.8% between starts, outs recorded only 26.6%. The
        premise is backwards.
      * projecting rate x predicted-length is WORSE than projecting the
        total directly (MAE 1.733 vs 1.727, z -3.02). Significant, though
        the effect is a third of a percent.
      * a PERFECT length prediction would be worth 0.166 MAE — real
        headroom, about 10% — but past length captures -4% of it.

    So do not rebuild the decomposition on past length; that path is
    closed by its own walk-forward. The 0.166 stands as a standing note:
    if a length predictor ever arrives from somewhere else (pitch counts,
    times-through-order, the pen state this module already scores), it is
    worth re-testing against that bound. "Use his last few starts" is
    measurably worse than not bothering.
    """
    if score is None or score < TIRED_MIN:
        return 1.0
    raw = (score - TIRED_MIN) * LEASH_PER_INNING
    if not market_is_outs:
        raw *= LEASH_K_SHARE
    cap = LEASH_MAX if market_is_outs else 1.0 + (LEASH_MAX - 1.0) * LEASH_K_SHARE
    return round(clamp(1.0 + raw, 1.0, cap), 3)


def fatigue_score(team_id: int, date: str) -> float | None:
    """Weighted relief innings for a team over the two days before ``date``.

    ``None`` when nothing could be measured (API unreachable / no recent
    games) — distinct from a measured 0.0 (fresh pen after an off day)."""
    import datetime as _dt
    from ..sources.fetch import DataUnavailable
    from .sources.statslogs import fetch_boxscore
    from .sources.mlbstats import STATS_BASE, _get_json

    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        return None
    day1 = (d - _dt.timedelta(days=1)).isoformat()
    day2 = (d - _dt.timedelta(days=2)).isoformat()
    try:
        sched = _get_json(
            f"{STATS_BASE}/schedule?sportId=1&teamId={team_id}"
            f"&startDate={day2}&endDate={day1}",
            f"mlb_pensched_{team_id}_{date}.json", ttl=21600)
    except DataUnavailable:
        return None

    score, measured = 0.0, False
    for day in sched.get("dates", []) or []:
        weight = YESTERDAY_WEIGHT if day.get("date") == day1 else DAY_BEFORE_WEIGHT
        for g in day.get("games", []) or []:
            state = ((g.get("status") or {}).get("abstractGameState") or "")
            pk = g.get("gamePk")
            if state != "Final" or not pk:
                continue
            home_id = (((g.get("teams") or {}).get("home") or {})
                       .get("team") or {}).get("id")
            side = "home" if home_id == team_id else "away"
            try:
                box = fetch_boxscore(pk)
            except DataUnavailable:
                continue
            score += weight * parse_relief_innings(box, side)
            measured = True
    return round(score, 1) if measured or sched.get("dates") is not None else None


def attach_fatigue(slate, team_ids: dict[str, int]) -> int:
    """Measure and attach each team's pen workload. Returns how many teams
    got a score. ``team_ids`` maps team abbreviation → MLB Stats team id."""
    n = 0
    for game in slate.games:
        for ab in (game.home, game.away):
            tid = team_ids.get(ab)
            if not tid:
                continue
            score = fatigue_score(tid, game.date or slate.date)
            if score is None:
                continue
            game.bullpen_fatigue[ab] = score
            n += 1
    return n
