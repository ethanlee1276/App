"""NFL rest watch — who is safe, who is dead, and who might sit starters.

The December trap the incentive tracker does not cover: a team that has
already clinched rests starters in Weeks 17-18, and a team that is
mathematically dead shuts its veterans down — so a prop priced off a
player's season-long usage is a bet on a rotation that no longer exists.
"Recommend props accordingly" means three different strengths of claim,
and this module is careful to keep them apart:

* **Certain, computed** — from our own ingested finals, using only
  dominance arguments that hold REGARDLESS of the league's tiebreakers:

    - *division clinched*: every division rival's best possible finish is
      strictly worse than this team's worst possible finish. A division
      title is a berth, so the berth is certain.
    - *eliminated*: at least seven conference teams are guaranteed to
      finish strictly ahead. At most four of them can be division
      winners, so at least three occupy wildcard seats — all seven seeds
      are gone.

  These tests miss clinches that arrive via tiebreakers (they fire a
  week later than the league's official X's) but they NEVER claim a
  status falsely — a board should be late before it is wrong.

* **Risk, computed** — a certain status only matters for usage in the
  final stretch (Week 15 on). A clinched team gets a REST RISK flag, an
  eliminated team a SHUTDOWN RISK flag. These decorate matching prop
  cards as warnings; they never gate, because coaches differ.

* **Announced, curated** — "coach says starters sit Sunday" is beat-writer
  reporting with no feed, so it lives in data/nfl_rest_watch.json exactly
  like the incentive table. An announced rest is the one thing strong
  enough to GATE: the prop flips to Pass, because a bet on a player whose
  own coach benched him is not a model edge, it is a stale price.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .divisions import NFL as NFL_DIVISIONS

REST_PATH = Path("data/nfl_rest_watch.json")
REGULAR_SEASON_GAMES = 17
#: The stretch where a certain status starts bending usage.
RISK_FROM_WEEK = 15


def load_rest_watch(path: Path | str | None = None) -> dict:
    p = Path(path if path is not None else REST_PATH)
    try:
        raw = json.loads(p.read_text()) if p.is_file() else {}
        if not isinstance(raw, dict):
            raw = {}
    except (ValueError, OSError):
        raw = {}
    entries = [e for e in (raw.get("entries") or []) if isinstance(e, dict)
               and e.get("team")]
    return {"season": raw.get("season"), "entries": entries}


def _week_no(period: str) -> int | None:
    """"2026-W14" → 14; anything else → None."""
    s = str(period or "")
    if "-W" not in s:
        return None
    try:
        return int(s.split("-W")[1])
    except (ValueError, IndexError):
        return None


def standings(hconn, season: int) -> dict:
    """{team: wins/losses/ties/played/remaining/pts/max_pts} from our own
    finals. Points = 2W + T, so ties never force a float comparison into
    the certainty math."""
    rows = hconn.execute(
        "SELECT home, away, home_score, away_score, period FROM games "
        "WHERE sport='nfl' AND season=? AND home_score IS NOT NULL",
        (season,)).fetchall()
    out = {t: {"wins": 0, "losses": 0, "ties": 0, "played": 0}
           for t in NFL_DIVISIONS}
    last_week = 0
    for r in rows:
        h, a = r["home"], r["away"]
        if h not in out or a not in out:
            continue
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        for t in (h, a):
            out[t]["played"] += 1
        if hs == as_:
            out[h]["ties"] += 1
            out[a]["ties"] += 1
        else:
            w, l = (h, a) if hs > as_ else (a, h)
            out[w]["wins"] += 1
            out[l]["losses"] += 1
        last_week = max(last_week, _week_no(r["period"]) or 0)
    for t, s in out.items():
        s["pts"] = 2 * s["wins"] + s["ties"]
        s["remaining"] = max(0, REGULAR_SEASON_GAMES - s["played"])
        s["max_pts"] = s["pts"] + 2 * s["remaining"]
    return {"teams": out, "week": last_week + 1 if last_week else 0}


def picture(hconn, season: int | None = None,
            rest_path: Path | str | None = None) -> dict:
    """Every team's status, under the certainty rules stated above."""
    from .seasons import season_of
    season = int(season or season_of("nfl", _dt.date.today().isoformat()))
    st = standings(hconn, season)
    teams, week = st["teams"], st["week"]
    conf_of = {t: cd[0] for t, cd in NFL_DIVISIONS.items()}
    div_of = dict(NFL_DIVISIONS)
    out = {}
    for t, s in teams.items():
        rivals_div = [r for r in teams if r != t and div_of[r] == div_of[t]]
        div_clinched = s["played"] > 0 and all(
            teams[r]["max_pts"] < s["pts"] for r in rivals_div)
        ahead_for_sure = sum(
            1 for r in teams
            if r != t and conf_of[r] == conf_of[t]
            and teams[r]["pts"] > s["max_pts"])
        eliminated = s["played"] > 0 and ahead_for_sure >= 7
        status = ("clinched — division" if div_clinched
                  else "eliminated" if eliminated else "in the hunt")
        risk = ""
        if week >= RISK_FROM_WEEK and div_clinched:
            risk = "rest risk"
        elif week >= RISK_FROM_WEEK and eliminated:
            risk = "shutdown risk"
        out[t] = {**{k: s[k] for k in ("wins", "losses", "ties",
                                       "remaining")},
                  "status": status, "risk": risk, "note": ""}
    announced = []
    for e in load_rest_watch(rest_path)["entries"]:
        team = str(e.get("team") or "").upper()
        wk = e.get("week")
        if team in out and (wk is None or int(wk) == week):
            out[team]["risk"] = "announced rest"
            out[team]["note"] = str(e.get("note") or "")
            announced.append(team)
    return {"season": season, "week": week, "teams": out,
            "announced": sorted(set(announced)),
            "active": week >= RISK_FROM_WEEK or bool(announced),
            "note": "" if week >= RISK_FROM_WEEK else (
                "The playoff picture starts bending usage around Week "
                f"{RISK_FROM_WEEK}. Statuses are computed from our own "
                "ingested finals with tiebreaker-free certainty rules; "
                "announced rests go in data/nfl_rest_watch.json.")}


def decorate(recommendations: list[dict], pic: dict) -> dict:
    """Apply the three strengths of claim to matching prop cards.

    Announced rest GATES: recommended flips off, the grade says Pass, and
    the reason names the coach's decision — the journal gate then skips
    it like any other non-recommendation. Computed risks WARN: a reason
    the human weighs, with the probability untouched.
    """
    teams = pic.get("teams") or {}
    gated = warned = 0
    for r in recommendations:
        t = str(r.get("team") or "").upper()
        s = teams.get(t)
        if not s or not s.get("risk"):
            continue
        if s["risk"] == "announced rest":
            r["recommended"] = False
            r["grade"] = "Pass"
            r.setdefault("reasons", []).insert(0,
                f"Announced rest: {t} is sitting starters this week"
                + (f" — {s['note']}" if s.get("note") else "")
                + ". A season-usage prop on a benched rotation is a stale "
                  "price, not an edge")
            gated += 1
        else:
            label = ("has clinched — starters may rest or leave early"
                     if s["risk"] == "rest risk"
                     else "is eliminated — veterans may be shut down")
            r.setdefault("reasons", []).append(
                f"Playoff picture: {t} {label}. Week "
                f"{pic.get('week', '?')} usage can detach from the season "
                f"the projection was built on")
            warned += 1
    return {"gated": gated, "warned": warned}
