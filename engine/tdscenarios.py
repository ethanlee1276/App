"""Touchdown scenarios: a scorer built from our own matchup data, not from
his price.

Ethan, 2026-09-26: "i dont give a shit about edge, i want to use our data
for offense and defense and where offense players do good and what
defense players do bad to create a senario where a specific player can get
a touchdown, mixed with redsone usage and redzone trips and all that shit
... me and my other ai went through defense and offense and where the
lions do bad and bills do good and saints do good and figure out thar
chris olave and josh allen and dalton kincaide could have breakout games
and get tdss and thats exactly what happened."

That is a different product from the value board (which asks whether our
chance beats the price) and from the Most Likely shelf (which seats the
highest chances over a floor). A scenario reads four things off the data
the site already carries, for every player the matchup scan wrote a read
on and the touchdown model priced:

  offense    the points the lines expect from his team (the implied total);
  defense    where the opponent's defence ranks against his position —
             the pass defence for a receiver or tight end, the run defence
             for a back — this season leading last season 55/45
             (gamescan.season_share);
  usage      his share of the targets or the carries;
  red zone   the red-zone chances the model expects him to get.

Each is scored 0–2; a player is a scenario when he scores at least
SCENARIO_MIN (of 10, with red-zone trips the fifth reading) with the
defence, the usage and the red zone all counting,
and never when he is on the injury report (the Most Likely board's rule). Scenarios are
ranked by OUR chance of the touchdown, so the shelf reads top down the way
the touchdown shelf does, and each carries the four lines that made it.
Scorers already seated on the Most Likely touchdown shelf are left off —
they are picks already.

MEASURED SEPARATELY. engine/tdmatchfit found that a bad defence adds
nothing to a receiver's touchdown chance beyond the game total, so the
chance shown is the model's, unmoved; the scenario is a SELECTION rule,
and the journal tracks it on paper under its own category so that in a
few weeks the record, not an argument, says how these do.
"""
from __future__ import annotations

#: The four readings and their bars: (strong, ok).
OFFENSE_POINTS = (24.0, 21.0)          # implied team points
DEFENSE_RANK = (26, 20)                # opponent's unit rank of 32, higher = softer
TARGET_SHARE = (0.24, 0.18)            # WR / TE
CARRY_SHARE = (0.55, 0.40)             # RB
RED_ZONE_CHANCES = (1.5, 0.9)          # expected red-zone touches
#: Red-zone trips (engine/redzone): his offence's red-zone plays per game
#: and the opponent's allowed, each against the league, averaged. (strong, ok).
TRIPS_REL = (0.15, 0.05)
#: A scenario scores at least this of 10, with defence, usage and his red
#: zone all counting. Was 5 of 8 before red-zone trips joined (2026-09-26).
SCENARIO_MIN = 6
#: How many the shelf carries.
LIMIT = 8

_GROUP = {"WR": "wr", "TE": "wr", "RB": "rb"}


def _pts(value, bars) -> int:
    if value is None:
        return 0
    strong, ok = bars
    return 2 if value >= strong else 1 if value >= ok else 0


def _ord(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def score(read: dict, opp_units: dict | None, n_teams: int = 32,
          rz_own: dict | None = None, rz_opp: dict | None = None) -> dict | None:
    """The four readings for one read carrying a touchdown stamp, or None
    when he is not a scenario. ``opp_units`` is the scan's rating for the
    opponent ({"def": {"passing": {"rank"}, "rushing": {"rank"}}, "blend"})."""
    td = read.get("td") or {}
    pos = str(read.get("pos") or read.get("position") or "").upper()
    grp = _GROUP.get(pos)
    if not grp or td.get("model_prob") is None or not td.get("odds"):
        return None
    # NEVER A PLAYER WHO IS LISTED. Ethan, 2026-09-26: Zay Flowers on this
    # shelf — "this player isn't even playing for this game." The Most
    # Likely board holds any listed player until inactives confirm
    # (likely.admissible); a scenario answers to the same rule.
    if str(td.get("injury_status") or "").strip() or read.get("own_status"):
        return None
    u = read.get("usage") or {}
    implied = td.get("implied_total")
    unit = "passing" if grp == "wr" else "rushing"
    rank = (((opp_units or {}).get("def") or {}).get(unit) or {}).get("rank")
    share = u.get("tgt_share") if grp == "wr" else u.get("carry_share")
    rz = td.get("rz_chances")
    off_rel = (rz_own or {}).get("off_rel")
    def_rel = (rz_opp or {}).get("def_rel")
    trips = [v for v in (off_rel, def_rel) if v is not None]
    trips_rel = sum(trips) / len(trips) if trips else None
    pts = {"offense": _pts(implied, OFFENSE_POINTS),
           "defense": _pts(rank, DEFENSE_RANK),
           "usage": _pts(share, TARGET_SHARE if grp == "wr" else CARRY_SHARE),
           "red_zone": _pts(rz, RED_ZONE_CHANCES),
           "trips": _pts(trips_rel, TRIPS_REL)}
    total = sum(pts.values())
    # THE RED ZONE IS REQUIRED, like the defence and the usage. Flowers again:
    # "it says 0.0 redzone chances expected yet we display this pick." A
    # touchdown case with no red-zone role is not one.
    if total < SCENARIO_MIN or not pts["defense"] or not pts["usage"] or not pts["red_zone"]:
        return None
    team, opp = read.get("team") or "", read.get("opp") or ""
    blend = (opp_units or {}).get("blend")
    lines = []
    if implied is not None:
        lines.append(f"{team} expected to score {float(implied):.1f} by the lines")
    if rank is not None:
        lines.append(f"{opp}’s {'pass' if grp == 'wr' else 'run'} defence ranks {_ord(rank)} of {n_teams}"
                     + (f" ({blend:.0%} this season, the rest last)" if blend is not None else ""))
    if share is not None:
        lines.append(f"{float(share):.0%} of the {'targets' if grp == 'wr' else 'carries'}"
                     + (f" · {u['snap_pct']:.0%} of the snaps" if u.get("snap_pct") is not None else ""))
    if rz is not None:
        before, then = td.get("rz_before"), td.get("rz_then_implied")
        moved = before is not None and then and implied is not None and abs(float(rz) - float(before)) >= 0.05
        lines.append(f"{float(rz):.1f} expected red-zone chances"
                     + (f" this week ({float(before):.1f} a game before, scaled to {float(implied):.1f} "
                        f"expected points from {float(then):.1f})" if moved else ""))
    # RED-ZONE TRIPS: how often his offence gets inside the 20, and how
    # often their defence lets teams in (engine/redzone).
    if trips:
        pct = lambda v: f"{v * 100:+.0f}%"                     # noqa: E731
        bits = []
        if off_rel is not None:
            bits.append(f"{team} runs {(rz_own or {}).get('off'):g} red-zone plays a game ({pct(off_rel)} vs the league)")
        if def_rel is not None:
            bits.append(f"{opp} allows {(rz_opp or {}).get('def'):g} ({pct(def_rel)})")
        lines.append(" · ".join(bits))
    # HIS QUARTERBACK, WHEN THE STARTER IS OUT. Ethan, 2026-09-26: "last
    # week the starting QB for that team was announced out for the season
    # so no way that number is correct now." The lines above already carry
    # it through the implied total; this says it in words.
    if td.get("qb_change"):
        lines.append(f"QB change: {td['qb_change']} — the lines above already account for it")
    return {"points": pts, "score": total, "lines": lines}


def build(result: dict, n_teams: int = 32, limit: int = LIMIT) -> list:
    """Scenario rows for the board, ranked by our chance, from the reads
    (`scan_reads`) and each game's scan units."""
    units_by_team: dict = {}
    rz_by_team: dict = {}
    for g in result.get("games") or []:
        for t, u in ((g.get("scan") or {}).get("units") or {}).items():
            units_by_team[t] = u
        for t, r in ((g.get("scan") or {}).get("redzone") or {}).items():
            rz_by_team[t] = r
    seated = {(r.get("player") or "") for r in result.get("most_likely") or []
              if isinstance(r, dict) and r.get("kind") == "td" and not r.get("reserve")}
    out = []
    for key, game in (result.get("scan_reads") or {}).items():
        for x in game.get("players") or []:
            if (x.get("player") or "") in seated:
                continue
            s = score(x, units_by_team.get(x.get("opp") or ""), n_teams,
                      rz_own=rz_by_team.get(x.get("team") or ""), rz_opp=rz_by_team.get(x.get("opp") or ""))
            if not s:
                continue
            td = x["td"]
            out.append({
                "kind": "td", "scenario": True, "player": x.get("player"), "team": x.get("team"),
                "opponent": x.get("opp"), "position": str(x.get("pos") or "").upper(),
                "market": "anytime_td", "market_label": "Anytime TD", "side": "YES", "line": 0.5,
                "odds": td.get("odds"), "book": td.get("book") or "",
                "model_prob": float(td["model_prob"]), "game": key,
                "read": x.get("read"), "label": x.get("label"), "headshot": x.get("headshot") or "",
                "scenario_score": s["score"], "scenario_points": s["points"], "scenario_lines": s["lines"],
                "on_board": bool(td.get("on_board")),
            })
    out.sort(key=lambda r: (-r["model_prob"], -r["scenario_score"]))
    return out[:limit]
