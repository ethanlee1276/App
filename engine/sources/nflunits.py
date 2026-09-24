"""NFL units per team-week, both sides of the ball, from play-by-play.

Ethan, 2026-09-24, with a matchup breakdown for Falcons @ Packers beside
him: "ranking the defenses and offenses and looking at where exactly in
the defense and offense is good and bad". The breakdown ranked eight
units a side — overall, passing, rushing, pressure, explosive plays —
from a paid model. These are the same units measured from the free
nflverse play-by-play the site already reads:

* **overall** — EPA per play and success rate on every run and dropback;
* **passing** — EPA per dropback (sacks and scrambles included: the
  pass rush and the quarterback's legs are part of the passing game);
* **rushing** — EPA per designed run, success, yards per carry;
* **explosive** — dropbacks gaining 20+ and runs gaining 10+;
* **pressure** — sacks plus quarterback hits per dropback: what an
  offensive line allows and a pass rush generates. (The per-play
  pressure charting lives in the participation file, which nflverse
  publishes a season behind; hits and sacks are in every week.)

One row per team-week per side, as SUMS, so the reader can blend weeks
and seasons exactly (engine/gamescan divides). Standard library only.
"""

from __future__ import annotations

#: The play-by-play columns this reads, beside `nflpbp.NEEDED`.
UNIT_COLS = ("week", "season_type", "posteam", "defteam", "play_type",
             "qb_dropback", "rush", "qb_scramble", "epa", "success",
             "yards_gained", "sack", "qb_hit", "two_point_attempt")

#: What counts as explosive: the conventional cut, dropbacks and runs apart.
PASS_EXPLOSIVE_YDS = 20
RUSH_EXPLOSIVE_YDS = 10


def _f(v, default=0.0):
    try:
        if v in (None, "", "NA"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _blank() -> dict:
    return {"plays": 0, "epa": 0.0, "success": 0.0,
            "dropbacks": 0, "pass_epa": 0.0, "pass_success": 0.0, "pass_expl": 0,
            "rushes": 0, "rush_epa": 0.0, "rush_success": 0.0, "rush_yds": 0.0,
            "rush_expl": 0, "sacks": 0, "hits": 0}


class Units:
    """Folds plays one at a time (`add`), so it can ride the same stream
    as `nflpbp.aggregate_pbp` instead of reading a 100 MB file twice."""

    def __init__(self):
        self.cells: dict = {}          # (team, week, side) -> sums
        self.opp: dict = {}            # (team, week) -> opponent

    def add(self, r: dict) -> None:
        if (r.get("season_type") or "REG") != "REG":
            return
        wk = int(_f(r.get("week")))
        off, dfn = r.get("posteam") or "", r.get("defteam") or ""
        if wk <= 0 or not off or not dfn:
            return
        if _f(r.get("two_point_attempt")) == 1:
            return
        dropback = _f(r.get("qb_dropback")) == 1
        rush = _f(r.get("rush")) == 1 and not dropback
        if not (dropback or rush):
            return
        epa_raw = r.get("epa")
        if epa_raw in (None, "", "NA"):
            return
        epa, succ = _f(epa_raw), _f(r.get("success"))
        yds = _f(r.get("yards_gained"))
        self.opp[(off, wk)] = dfn
        self.opp[(dfn, wk)] = off
        for team, side in ((off, "off"), (dfn, "def")):
            c = self.cells.setdefault((team, wk, side), _blank())
            c["plays"] += 1
            c["epa"] += epa
            c["success"] += succ
            if dropback:
                c["dropbacks"] += 1
                c["pass_epa"] += epa
                c["pass_success"] += succ
                c["pass_expl"] += int(yds >= PASS_EXPLOSIVE_YDS)
                c["sacks"] += int(_f(r.get("sack")) == 1)
                c["hits"] += int(_f(r.get("qb_hit")) == 1 and _f(r.get("sack")) != 1)
            else:
                c["rushes"] += 1
                c["rush_epa"] += epa
                c["rush_success"] += succ
                c["rush_yds"] += yds
                c["rush_expl"] += int(yds >= RUSH_EXPLOSIVE_YDS)

    def rows(self, season: int, sport: str = "nfl") -> list[dict]:
        out = []
        for (team, wk, side), c in sorted(self.cells.items()):
            out.append({"sport": sport, "season": int(season), "period": f"{wk:03d}",
                        "team": team, "side": side, "opp": self.opp.get((team, wk), ""),
                        **{k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in c.items()}})
        return out


def unit_week_rows(rows, season: int) -> list[dict]:
    """Every play in ``rows`` folded into team-week unit rows."""
    u = Units()
    for r in rows:
        u.add(r)
    return u.rows(season)
