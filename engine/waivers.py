"""The waiver-wire board — who just gained a role, and why.

The draft kit is a two-week product. This is the one a manager opens
fourteen times a season, and the question is always the same: *whose
job just changed?* Everything else about a waiver claim follows from
that.

WHAT THIS DELIBERATELY DOES NOT CLAIM. It does not say "free agent".
The site cannot see your league — there is no league sync — so any
claim about who is AVAILABLE would be a guess dressed as a fact, and
the one thing this project does not do is print numbers it cannot
stand behind. What it can say precisely is who just gained
opportunity, which is the half a waiver claim is actually buying; you
know better than we do which of them your league left on the wire.

TWO SIGNALS, BOTH MEASURED FROM OUR OWN DATA:

* **Vacancies.** A skill player is Out, Doubtful or on IR, so his
  team's touches at that position have to go somewhere. The
  beneficiaries are named, ranked by the share they ALREADY hold,
  because the back who was second in line is the one who inherits the
  job — not the name a headline picks.
* **Rising roles.** `fantasy.usage_board` already computes the number
  that matters: last week's target or carry share minus the prior four
  weeks' average. A jump there is a coordinator making a decision, and
  volume is far stickier week to week than the yards it produces.

A row earns its place by ONE of those, and carries the sentence that
put it there — never a score with no story behind it.

Standard library only; every input is already on the board.
"""

from __future__ import annotations

#: Statuses that vacate a role. QUESTIONABLE is deliberately absent: it
#: resolves to "played" often enough that treating it as a vacancy would
#: fill the board with jobs nobody actually lost.
VACATING = {"OUT", "DOUBTFUL", "IR", "INJURED RESERVE", "PUP",
            "SUSPENDED", "NFI"}

#: Only the positions a fantasy roster starts. A vacancy at guard moves
#: nothing anyone can claim.
SKILL = {"QB", "RB", "WR", "TE"}

#: How far last week's share must jump over the prior four-week average
#: before it is a role change rather than one loud game. Three points of
#: target share is roughly one extra look a game — small enough to catch
#: a change early, big enough that noise does not fill the board.
RISING_DELTA = 0.03

#: A rising row needs a real denominator behind it.
MIN_WEEKS = 3

#: How many rows each section carries. A waiver board longer than this
#: is a list to read rather than a shortlist to act on.
LIMIT = 8


def _norm_status(s: str) -> str:
    return str(s or "").strip().upper()


def team_key(name: str) -> str:
    """One team spelling both sides can be compared on.

    The injury feed writes clubs out in full ("Kansas City Chiefs") and
    the usage rows carry abbreviations ("KC"), so the naive comparison
    matches nothing — which is not an empty board, it is a SILENT one,
    and a vacancy section that never fires looks exactly like a quiet
    week. Resolved through the same club map the odds layer already
    keeps, with the input passed through unchanged when it is already an
    abbreviation (or a club nobody has mapped).
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    try:
        from .sources.oddsapi import TEAM_ABBR
        if raw in TEAM_ABBR:
            return TEAM_ABBR[raw]
        upper = raw.upper()
        for full, abbr in TEAM_ABBR.items():
            if full.upper() == upper or abbr == upper:
                return abbr
    except Exception:                                        # noqa: BLE001
        pass
    return raw.upper()


def vacancies(injuries: list[dict], usage: list[dict],
              limit: int = LIMIT) -> list[dict]:
    """``[{player, team, position, why, ...}]`` — who inherits a job.

    ``injuries`` is the injury board's own rows (team, player, position,
    status); ``usage`` is `fantasy.usage_board`. Teams are matched on
    the usage rows' abbreviation where the injury feed carries a full
    club name, so the join is done on whichever field both sides share.
    """
    out: list[dict] = []
    by_team: dict = {}
    for u in usage or []:
        key = (team_key(u.get("team")), str(u.get("position") or "").upper())
        by_team.setdefault(key, []).append(u)
    for inj in injuries or []:
        status = _norm_status(inj.get("status"))
        pos = str(inj.get("position") or "").upper()
        if status not in VACATING or pos not in SKILL:
            continue
        hurt = str(inj.get("player") or "")
        # Both sides resolved to the same spelling before comparing —
        # see team_key for why the naive match silently found nothing.
        mates = by_team.get((team_key(inj.get("team")), pos), [])
        for m in mates:
            if str(m.get("player") or "") == hurt:
                continue
            out.append({
                "player": m.get("player"), "team": m.get("team"),
                "position": pos, "kind": "vacancy",
                "share": m.get("season"), "delta": m.get("delta"),
                "fp_pg": m.get("fp_pg"), "headshot": m.get("headshot", ""),
                "why": f"{hurt} is {status.title()} — that {pos} work has to "
                       f"go somewhere, and he already holds "
                       f"{(m.get('season') or 0):.0%} of it",
            })
    # The man already second in line inherits the job, so the share he
    # HOLDS ranks this list, not the size of the name that vacated it.
    out.sort(key=lambda r: -(r.get("share") or 0))
    return out[:limit]


def rising(usage: list[dict], limit: int = LIMIT,
           min_delta: float = RISING_DELTA) -> list[dict]:
    """The biggest role GAINS — a coordinator's decision, not a box score.

    Volume is stickier week to week than the yards it produces, which is
    why this reads share rather than fantasy points: a 30-point game on
    four touches says nothing about next week, and one extra series a
    game says quite a lot.
    """
    out = []
    for u in usage or []:
        delta = u.get("delta")
        if delta is None or delta < min_delta:
            continue
        if int(u.get("weeks") or 0) < MIN_WEEKS:
            continue
        if str(u.get("position") or "").upper() not in SKILL:
            continue
        metric = u.get("metric") or "share"
        out.append({
            "player": u.get("player"), "team": u.get("team"),
            "position": str(u.get("position") or "").upper(),
            "kind": "rising", "share": u.get("last"), "delta": delta,
            "fp_pg": u.get("fp_pg"), "headshot": u.get("headshot", ""),
            "why": f"{metric} up {delta:+.0%} on his last four weeks — "
                   f"now {(u.get('last') or 0):.0%}",
        })
    out.sort(key=lambda r: -(r.get("delta") or 0))
    return out[:limit]


def board(usage: list[dict], injuries: list[dict] | None = None,
          limit: int = LIMIT) -> dict:
    """Both sections plus the sentence the page leads with.

    A player who appears in BOTH lists is left in both on purpose: "he
    is inheriting a job AND his share was already climbing" is two
    reasons to claim him, and collapsing them would hide the stronger
    one behind the earlier one.
    """
    vac = vacancies(injuries or [], usage or [], limit=limit)
    ris = rising(usage or [], limit=limit)
    return {
        "vacancies": vac,
        "rising": ris,
        "note": ("Role changes, not availability — the site cannot see "
                 "your league, so it never guesses who is on your wire. "
                 "Both lists are measured from our own usage data: who "
                 "just lost a job, and whose share just jumped."),
    }


# --- the start/sit half ------------------------------------------------------
# "Who to add" and "who to start" are different questions. The first is
# about a role changing; this one is about the SPOT — the same player is
# a different play against a shootout than against a team that will run
# out the clock on him.
#
# WHAT THIS IS, precisely: opportunity times environment. A player's
# share of his team's work, multiplied by the points his offense is
# expected to score (the market's implied team total), nudged by how much
# that offense throws relative to the situation it is in. It is NOT a
# projection of fantasy points — there is no per-week points model here,
# and dressing this number up as one would be exactly the fake precision
# this project refuses. It answers "whose spot is best", which is the
# question a start/sit call actually turns on.
#
# QUARTERBACKS ARE ABSENT, on purpose. Every usage share here is targets
# or carries; a quarterback has neither, so his row would score ~0 and
# rank last. Streaming a QB is nearly pure team environment, which needs
# a depth chart to say WHO is starting — and guessing that is how a
# board recommends a backup. Named here rather than quietly missing.

#: Positions whose usage share is a real number.
STREAM_POSITIONS = ("RB", "WR", "TE")

#: How hard pass-rate-over-expectation tilts a play. PROE runs roughly
#: ±8 points across a season, so this turns that full span into about
#: ±12% on the score — enough to separate two similar spots, never
#: enough to outrank a genuine difference in role or environment.
PROE_TILT = 1.5

#: Below this the share is a bit part, and a bit part in a great spot is
#: still a bit part.
MIN_STREAM_SHARE = 0.08


def _next_scripts(scripts: list[dict]) -> dict:
    """``{team abbr: script}`` for each team's NEXT unplayed game.

    game_scripts already returns only unplayed games ordered by week, so
    the first row a team appears in is the one being started for.
    """
    out: dict = {}
    for g in scripts or []:
        for side, opp in (("home", "away"), ("away", "home")):
            team = team_key(g.get(side))
            if not team or team in out:
                continue
            out[team] = {
                "implied": g.get(f"{side}_implied"),
                "proe": g.get(f"{side}_proe"),
                "opponent": team_key(g.get(opp)),
                "week": g.get("week"), "archetype": g.get("archetype"),
            }
    return out


def streamers(usage: list[dict], scripts: list[dict],
              per_position: int = 5) -> dict:
    """``{position: [rows]}`` — the best spots this week, by position.

    Ranked on share x implied team total, tilted by pass-rate over
    expectation: a run-lean offense helps its back and costs its
    receivers, and the reverse. Every row shows the two numbers behind
    it so the ranking can be argued with.
    """
    env = _next_scripts(scripts)
    out: dict = {}
    for u in usage or []:
        pos = str(u.get("position") or "").upper()
        if pos not in STREAM_POSITIONS:
            continue
        share = u.get("last")
        if share is None:
            share = u.get("season")
        if share is None or share < MIN_STREAM_SHARE:
            continue
        if int(u.get("weeks") or 0) < MIN_WEEKS:
            continue
        spot = env.get(team_key(u.get("team")))
        if not spot or spot.get("implied") is None:
            continue
        implied = float(spot["implied"])
        proe = spot.get("proe")
        # A PROE of ±0.05 is a rounding artefact, not a pass lean — it is
        # what the field holds before any play-by-play is ingested. Kept
        # out of both the arithmetic and the sentence, because "-0.0 pass
        # rate over expectation" on every row is noise wearing the shape
        # of a measurement.
        if proe is not None and abs(float(proe)) < 0.1:
            proe = None
        tilt = 1.0
        if proe is not None:
            # A back gains from a run-lean offense; a pass-catcher loses.
            lean = float(proe) / 100.0 * PROE_TILT
            tilt = (1.0 - lean) if pos == "RB" else (1.0 + lean)
        score = share * implied * tilt
        out.setdefault(pos, []).append({
            "player": u.get("player"), "team": u.get("team"),
            "position": pos, "opponent": spot.get("opponent"),
            "share": round(share, 3), "implied": round(implied, 1),
            "proe": proe, "score": round(score, 2),
            "fp_pg": u.get("fp_pg"), "headshot": u.get("headshot", ""),
            "why": f"{(share):.0%} of the work in an offense the market has "
                   f"scoring {implied:.1f}"
                   + (f" · {proe:+.1f} pass rate over expectation"
                      if proe is not None else ""),
        })
    for pos in out:
        out[pos].sort(key=lambda r: -(r.get("score") or 0))
        out[pos] = out[pos][:per_position]
    return out
