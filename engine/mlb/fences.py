"""In how many of the 30 parks would this ball have been a home run? An estimate.

Ethan, 2026-10-15, from the brainstorm he asked to have built: MLB
"homer in X of 30 parks". The hit page already draws every ball a hitter put
in play from MLB's own feed — where it landed (its spray angle) and how far
it went (the feed's `totalDistance`). This lays that ball over every park's
fence: the distance down each line and to centre (engine/mlb/parks), the
fence between them drawn straight from pole to centre, and the wall's
height down each line.

THE ESTIMATE, SAID PLAINLY. A ball clears a park when its distance reaches
the fence there plus the wall's height in feet (a ball coming down at about
45 degrees loses a foot of height for each foot it travels, so an eight-foot
wall wants eight more feet). It does not fly the ball again: no air, no
altitude, no wind, no weather and no ball that hits the top of a wall. The
real outfields curve and jut where these straight fences do not. So the page
calls it an estimate, and nothing on the board reads it.
"""

from __future__ import annotations

#: Foul poles at 45 degrees either side of straightaway centre.
POLE_DEG = 45.0
#: Beyond this angle from centre a ball's wall is the line's (left or
#: right); inside it, the wall is CENTRE_WALL_FT.
LINE_WALL_DEG = 15.0
CENTRE_WALL_FT = 8.0
#: Balls this short, or hit on the ground or straight up, are not asked.
MIN_FT = 250.0
ASKED = ("fly_ball", "line_drive")


def fence_at(park, angle: float) -> float | None:
    """Feet to the fence at ``angle`` (negative toward left), or None foul."""
    if angle is None or abs(angle) > POLE_DEG:
        return None
    if angle <= 0:
        return park.lf_ft + (park.cf_ft - park.lf_ft) * (angle + POLE_DEG) / POLE_DEG
    return park.cf_ft + (park.rf_ft - park.cf_ft) * angle / POLE_DEG


def wall_at(park, angle: float) -> float:
    if angle <= -LINE_WALL_DEG:
        return float(park.lf_wall_ft or CENTRE_WALL_FT)
    if angle >= LINE_WALL_DEG:
        return float(park.rf_wall_ft or CENTRE_WALL_FT)
    return CENTRE_WALL_FT


def clears(park, distance: float, angle: float) -> bool:
    f = fence_at(park, angle)
    return f is not None and distance >= f + wall_at(park, angle)


def parks_out(distance, angle, trajectory: str = "fly_ball") -> list[str] | None:
    """The parks (by key) this ball is out of, or None when it is not asked
    (no distance or angle, too short, on the ground, foul)."""
    from .parks import PARKS
    if distance is None or angle is None or trajectory not in ASKED:
        return None
    if distance < MIN_FT or abs(angle) > POLE_DEG:
        return None
    return [k for k, p in PARKS.items() if clears(p, float(distance), float(angle))]


def season_block(pas: list[dict], limit: int = 12) -> dict | None:
    """The hit page's card: his home runs, each with its count of parks, and
    the balls in play that were not home runs but would have been in some.
    ``pas`` are the chart's plate appearances carrying ``pk`` (the count)
    and ``pko`` (the keys out of), with ``et``, ``d``, the game's date and
    opponent as ``date`` and ``opp``."""
    asked = [p for p in pas if p.get("pk") is not None]
    if not asked:
        return None
    hrs = sorted([p for p in asked if p.get("et") == "home_run"], key=lambda p: -p["pk"])
    near = sorted([p for p in asked if p.get("et") != "home_run" and p["pk"] > 0], key=lambda p: (-p["pk"], -(p.get("d") or 0)))
    from .parks import PARKS

    def row(p):
        # The shorter list, by club: the parks it was out of when that is
        # half or fewer, otherwise the parks that would have held it.
        got = set(p.get("pko") or [])
        short = sorted(PARKS[k].team for k in got) if len(got) <= len(PARKS) // 2 else \
            sorted(v.team for k, v in PARKS.items() if k not in got)
        return {"date": p.get("date", ""), "opp": p.get("opp", ""), "d": p.get("d"), "n": p["pk"],
                "et": p.get("et", ""), "ev": p.get("ev", ""), "ls": p.get("ls"),
                "out_of" if len(got) <= len(PARKS) // 2 else "held_by": short}
    return {"hr": [row(p) for p in hrs], "near": [row(p) for p in near[:limit]], "parks": len(PARKS),
            "no_doubt": sum(1 for p in hrs if p["pk"] == len(PARKS)),
            "doubters": sum(1 for p in hrs if p["pk"] <= len(PARKS) // 2), "near_n": len(near)}
