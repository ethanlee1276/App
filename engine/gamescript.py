"""One game script, said one way, everywhere it is said.

Ethan, 2026-09-02: "One thing I'm noticing is conflicting data with our
most likely page and the fantasy game script page. Example is lions vs
saint, ur showing it to be a heavy RB running game for the lions but then
recommending Goffs over passing yards. Also we should b showing the game
script under the player props too."

The numbers never disagreed — every page reads the same nflverse spread
and total — but three pages said them in three vocabularies. The Fantasy
page named an ARCHETYPE ("Favorite runs, dog throws"); the Most Likely
page said "favoured by 7 — +7% TD equity for a RB"; the prop card, when
it said anything, said "7.0-pt favorite — leading script leans pass
volume down (×0.97)". Read together that is one fact — Detroit is a
touchdown favourite in a high-total game, so the model expects them to
lead, lean on the run late, and throw a little less — and a Goff over
that survives it is a Goff over that survives it: the projection has
ALREADY taken the script out, and what is left is the matchup and the
line. Nothing on the prop card said so.

So this module is the single description, built from the spread and the
total, and every page carries the same one:

* `describe(spread, total, home, away)` — the archetype the Fantasy page
  has always used (`ARCHETYPES` lives here now; `engine.fantasy` imports
  it), both implied totals, the favourite, and the confidence sentence.
* `for_team(...)` — the same, seen from one sideline: this team's role,
  its implied points, and the lean the script gives it.
* `for_prop(game, team, market, position)` — what the PROJECTION did
  about it for this market, in the constants the projection actually
  uses (`engine.matchup.SCRIPT_COEF_PASS` for pass-catching volume, the
  rush tilt measured-and-not-applied, `touchdowns.script_td_multiplier`'s
  slopes for a touchdown), so the card cannot claim an adjustment the
  model did not make.
"""

from __future__ import annotations

from .statmath import clamp

#: (total band, spread band) → (name, what it means for fantasy usage).
#: The Fantasy page's table since 2026-08; unchanged, only moved.
ARCHETYPES = {
    ("high", "close"): ("Everyone eats", "High total, close spread — the best "
                        "environment in fantasy. Prime stacking."),
    ("high", "big"): ("Favorite runs, dog throws", "High total, big spread — "
                      "favorite's RB gets clock-killing volume; underdog WRs "
                      "get garbage-time targets. Underdog RB nearly unstartable."),
    ("low", "big"): ("Floor, no ceiling", "Low total, big spread — favorite's "
                     "RB is a floor play; fade the underdog backfield entirely."),
    ("low", "close"): ("Nobody's good", "Low total, close spread — downgrade "
                       "across the board."),
}

HIGH_TOTAL = 47.0          # at or above: a "high" total
BIG_SPREAD = 6.5           # at or above: a "big" spread
PICKEM = 1.0               # under this the script has no favourite


def confidence(spread_abs: float) -> str:
    """The Fantasy page's sentence, unchanged."""
    if spread_abs >= 7:
        return "high — favorites this size win ~79%"
    if spread_abs >= 3:
        return "moderate"
    return "coin flip — don't project a script off this"


def describe(spread: float, total: float, home: str = "", away: str = "") -> dict | None:
    """The game's script from its number. ``spread`` is the HOME number,
    negative when the home side is favoured; ``total`` the game total.
    None when there is no line to read."""
    try:
        spread = float(spread)
        total = float(total)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    home_imp = total / 2.0 - spread / 2.0
    away_imp = total - home_imp
    size = abs(spread)
    key = ("high" if total >= HIGH_TOTAL else "low",
           "big" if size >= BIG_SPREAD else "close")
    name, read = ARCHETYPES[key]
    favorite = "" if size < PICKEM else (home if spread < 0 else away)
    return {
        "spread": spread, "total": total, "home": home, "away": away,
        "home_implied": round(home_imp, 1), "away_implied": round(away_imp, 1),
        "favorite": favorite, "confidence": confidence(size),
        "archetype": name, "read": read,
    }


def for_team(spread: float, total: float, home: str, away: str, team: str) -> dict | None:
    """The same script from one sideline."""
    d = describe(spread, total, home, away)
    if d is None:
        return None
    is_home = team == home
    team_spread = spread if is_home else -spread          # negative = favoured
    size = abs(team_spread)
    role = ("pick'em" if size < PICKEM
            else "favorite" if team_spread < 0 else "underdog")
    # What the archetype means for THIS side, in one clause.
    if role == "favorite":
        lean = ("leads late and runs the clock — run volume up, pass volume "
                "a little down" if d["archetype"] in ("Favorite runs, dog throws",
                                                      "Floor, no ceiling")
                else "favored in a shootout — everyone eats")
    elif role == "underdog":
        lean = ("expected to trail and throw — pass volume up, the run "
                "shelved" if d["archetype"] in ("Favorite runs, dog throws",
                                                "Floor, no ceiling")
                else "close game, both offenses stay in it")
    else:
        lean = "no favorite — the number says nothing about who leads"
    d.update({"team": team, "opponent": away if is_home else home,
              "is_home": is_home, "team_spread": team_spread, "role": role,
              "team_implied": d["home_implied"] if is_home else d["away_implied"],
              "opp_implied": d["away_implied"] if is_home else d["home_implied"],
              "lean": lean})
    return d


#: How much of the script the projection layer actually applies, by
#: market — these are the projection's own constants, imported so the
#: card and the model cannot drift apart.
def projection_tilt(team_spread: float, market: str, position: str = "") -> tuple[float, str]:
    """``(multiplier, sentence)`` for what the projection did about the
    script on this market. 1.0 with the reason when it did nothing."""
    from .matchup import SCRIPT_COEF_PASS, SCRIPT_CLAMP
    m = (market or "").lower()
    pos = (position or "").upper()
    if m in ("pass_yds", "rec_yds", "receptions"):
        mult = clamp(1.0 + SCRIPT_COEF_PASS * team_spread, *SCRIPT_CLAMP)
        what = "passing volume" if m == "pass_yds" else "target volume"
        if abs(mult - 1.0) < 0.005:
            return 1.0, f"the projection leaves {what} where it was — the spread is too small to move it"
        return mult, (f"the projection already tilts {what} "
                      f"{'down' if mult < 1 else 'up'} ×{mult:.2f} for a "
                      f"{'leading' if team_spread < 0 else 'trailing'} script")
    if m == "rush_yds":
        return 1.0, ("no rush tilt is applied — five seasons of logs show no "
                     "usable relationship between a team's spread and its "
                     "back's yardage, so the projection does not invent one")
    if m == "anytime_td":
        lead = -team_spread
        if pos == "RB":
            mult = clamp(1.0 + 0.010 * lead, 0.88, 1.12)
        elif pos in ("WR", "TE"):
            mult = clamp(1.0 - 0.004 * lead, 0.95, 1.05)
        else:
            return 1.0, "the touchdown model lets a quarterback's rushing role carry itself — no script term"
        if abs(mult - 1.0) < 0.02 or abs(lead) < 3.0:
            return 1.0, "the touchdown model applies no script term at a spread this small"
        return mult, (f"the touchdown model gives a {pos} {(mult - 1) * 100:+.0f}% "
                      f"TD equity for a {abs(lead):.0f}-point "
                      f"{'favorite' if lead > 0 else 'underdog'}")
    return 1.0, "no script term applies to this market"


def for_prop(game, team: str, market: str, position: str = "") -> dict | None:
    """The script a prop card shows — the shared description plus what the
    projection did about it for this market. ``game`` is the slate's
    Game (spread = home number, total)."""
    if game is None:
        return None
    d = for_team(getattr(game, "spread", None), getattr(game, "total", None),
                 getattr(game, "home", ""), getattr(game, "away", ""), team)
    if d is None:
        return None
    mult, applied = projection_tilt(d["team_spread"], market, position)
    fav = d["favorite"]
    spread_abs = abs(d["spread"])
    line = f"{fav} by {spread_abs:g}" if fav else "pick'em"
    role = d["role"]
    by = "" if role == "pick'em" else f" by {abs(d['team_spread']):g}"
    implied = d["team_implied"]
    summary = (f"{d['archetype']}. {d['team']} {role}{by}, implied "
               f"{implied:g} points — {d['lean']}; {applied}.")
    d.update({"tilt": round(mult, 3), "applied": applied,
              "line": f"{line} at {d['total']:g}", "summary": summary})
    return d
