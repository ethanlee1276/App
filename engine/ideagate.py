"""The inventions, gated into the picks: each moves Most Likely and Edge only once its own held-out bar holds.

Ethan, 2026-10-17: "make sure we are wrapping all the features into the
most likely bets and edge bets where it makes sense. just cause we add
features and data and shit and say we did doesnt mean we are using them the
right way."

THE RULE. A reading joins a pick the moment the box measures it and it
holds — no hand-wiring after the result, which is how a passing measurement
could sit unread. Until a verdict says HOLDS nothing here changes a number,
and `state()` says, gate by gate, which verdict it waits on and what it
will move (`python3 -m engine.ideagate` on the box).

WHERE EACH ONE LANDS — at the earliest point it belongs, so Edge and Most
Likely read the same number:

  the projection (both boards)
    rookie    his college line, translated, is the prior a thin rookie
              sample shrinks toward (engine/rookies → sources/nflverse)
    role      the usage bridge's volume follows the detected role instead
              of four flat weeks (engine/rolechange → nflusage.volume_roles),
              and the touchdown card's snap share is the detected one
              (→ nflusage.snap_shares) — each share on its own verdict
    kicks     a kicker's field goals scale with the air's density
              (engine/kickphysics → projection, its own "air" step)
  the parlay pricer
    sim       two teammates' legs are joined with the simulated games'
              correlation (engine/playsim → parlays.relate)
  the Most Likely chance, and an Edge pick's refusal — the way the
  record's own corrections already work (likelycal, likelyctx)
    menu      a book's own menu that does not add up: the cheap side gains
              and the dear side loses, by the measured excess
    recipe    the outcome recipe sits far from the line: the side it points
              to gains, by the measured excess
    attention a spiked player's under gains and his over loses, by the
              measured excess
    copies    the market check compares our chance with the market's fair
              chance counted one vote per opinion, not the posted price
  the NHL game lines
    endgame   the final score's shape — score effects, the pulled goalie and
              the empty net — prices the puck line, the total and the
              moneyline (engine/nhl/endgame → nhl_build.game_bets)
  holds — a pick comes off Most Likely and off Edge
    practice  a listed man whose designation, practice and club say he
              plays under half the time
    range     the honest range puts his side under even, where the range
              was covered AND better calibrated than the model held out

  never a number, by design
    curve     the board's picks sit at the main line, where the two curves
              agree by construction; the ends are a reading
    autopsy   it says which step is wrong; it is not a step
    risk      My Bets only

The shifts from menu, recipe and attention on one pick add up and are
capped at MAX_SHIFT.

Standard library only.
"""

from __future__ import annotations

import json
import math
import os

#: The most the readings may move one pick's chance together.
MAX_SHIFT = 0.08
#: A listed man under this chance to play comes off.
HOLD_PLAYS = 0.5
#: A rookie with fewer NFL games than this this season is priced off the translation's prior.
ROOKIE_GAMES = 4
#: The share of a kicker's points that are field goals (three a make against
#: one an extra point, at the league's usual two makes and two and a half
#: extra points a game) — how much of kick_pts the air can move.
FG_SHARE = 0.7
#: The distances a team's field goals come from, evenly — the air's effect
#: is averaged over them.
KICK_DISTANCES = (25, 33, 40, 47, 53)
KICK_MARKETS = ("fg_made", "kick_pts")
#: Standard air's temperature (15 °C), for an open stadium's usual air.
STANDARD_F = 59.0
#: The role detector moves the usage bridge's volume within this range.
ROLE_RANGE = (0.6, 1.6)
SHARES = {"targets": "tgt", "carries": "car", "snap_pct": "snap"}

_cache: dict = {}


def _load(key: str, loader):
    """One saved file read once per change on disk (the builds price
    hundreds of props, each asking)."""
    from . import modelstate
    names = {"rookies": "rookies.json", "role": "rolechange.json", "sim": "playsim.json",
             "range": "conformal.json"}
    path = modelstate.path(names[key]) if key in names else None
    try:
        stamp = os.path.getmtime(path) if path else None
    except OSError:
        stamp = None
    hit = _cache.get(key)
    if hit and hit[0] == stamp and stamp is not None:
        return hit[1]
    data = loader() if stamp is not None or not path else {}
    _cache[key] = (stamp, data)
    return data


# ---- the verdicts --------------------------------------------------------------------------

def menu_verdict(sport: str) -> dict:
    from . import bookmenu
    return bookmenu.load_verdict(sport) or {}


def recipe_verdict(sport: str, market: str) -> dict:
    from . import bookrecipe
    return ((bookrecipe.load(sport).get(market) or {}).get("verdict")) or {}


def attention_verdict(sport: str) -> dict:
    from . import attention
    return attention.load_verdict(sport) or {}


def copies_verdict(sport: str) -> dict:
    from . import bookclusters
    return (bookclusters.load(sport).get("consensus")) or {}


def practice_verdict(sport: str) -> dict:
    from . import practice
    return (practice.load(sport).get("held_out")) or {}


def range_verdict(sport: str, market: str) -> dict:
    from . import conformal
    return ((_load("range", conformal.load).get("held_out") or {}).get(f"{sport}|{market}")) or {}


def range_proven(v: dict) -> bool:
    """Covered on the newest third AND better calibrated than the model there."""
    return bool(v.get("holds") and v.get("brier_range") is not None and v.get("brier_model") is not None
                and v["brier_range"] < v["brier_model"])


def kicks_verdict(sport: str) -> dict:
    from . import kickphysics
    return kickphysics.load(sport) or {}


def rookie_verdict(market: str) -> dict:
    from . import rookies
    return (((_load("rookies", rookies.load).get("rookies") or {}).get(market) or {}).get("held_out")) or {}


def role_verdict(key: str) -> dict:
    from . import rolechange
    return ((_load("role", rolechange.load).get("shares") or {}).get(key)) or {}


def sim_verdict() -> dict:
    from . import playsim
    return (_load("sim", playsim.load).get("verdict")) or {}


def endgame_verdict() -> dict:
    """The NHL endgame chain's held-out verdict (engine/nhl/endgame)."""
    from .nhl import endgame
    return endgame.verdict()


def curve_verdict(sport: str) -> dict:
    from . import altcurve
    return altcurve.load_verdict(sport) or {}


# ---- the projection hooks --------------------------------------------------------------------

def rookie_prior(player: str, market: str, nfl_games: int) -> float | None:
    """The translation of his last college season, as the prior a rookie's
    thin sample shrinks toward — only for a rookie this season, under
    ROOKIE_GAMES games, and only where the translation beat draft slot and
    his position's rookie mean held out."""
    if nfl_games >= ROOKIE_GAMES or not rookie_verdict(market).get("holds"):
        return None
    from . import rookies
    saved = _load("rookies", rookies.load)
    info = (saved.get("rookie_index") or {}).get(rookies._norm(player))
    col = ((info or {}).get("college") or {}).get(market)
    model = ((saved.get("rookies") or {}).get(market) or {}).get("fit")
    if not col or not model:
        return None
    return round(rookies.translate(model, col["pg"], info.get("pick") or rookies.UNDRAFTED), 2)


def role_forecast(market: str, shares: list) -> float | None:
    """The detector's forecast of his next share (targets, carries or snap
    share, in order, oldest first) once it beat the four-week average held
    out on that share; None otherwise."""
    key = SHARES.get(market)
    if not key or len(shares) < 4:
        return None
    g = role_verdict(key)
    if not (g.get("verdict") or {}).get("holds"):
        return None
    from . import rolechange
    s = g.get("settings") or rolechange.DEFAULT
    nxt = rolechange.detect(list(shares), s.get("hazard", rolechange.DEFAULT["hazard"]),
                            s.get("spread", rolechange.DEFAULT["spread"]))["next"]
    return float(nxt) if nxt else None


def role_ratio(opp_market: str, shares: list) -> float:
    """How far the detected role sits from his four-week share — the usage
    bridge's volume is scaled by it once the detector beat the four-week
    average held out on this share. 1.0 otherwise."""
    if opp_market not in ("targets", "carries"):
        return 1.0
    nxt = role_forecast(opp_market, shares)
    from . import rolechange
    base = sum(shares[-rolechange.BASELINE_WEEKS:]) / len(shares[-rolechange.BASELINE_WEEKS:]) if shares else 0
    if not nxt or base <= 0:
        return 1.0
    return max(ROLE_RANGE[0], min(ROLE_RANGE[1], nxt / base))


def usual_dev(fit: dict, team: str | None) -> float:
    """The air a kicker's own average was built in: half his home
    stadium's (its roof's air, or standard air at its altitude), half the
    league's usual — so a Denver kicker at home is not credited twice for
    air his record already flew through."""
    league = float(fit.get("mean_dev") or 0.0)
    if not team:
        return league
    from . import kickphysics as K
    from .stadiums import STADIUMS
    s = STADIUMS.get(str(team).upper())
    if not s:
        return league
    home = K.density_dev(K.air_density(K.DOME_F if s.roof in ("dome", "retractable") else STANDARD_F,
                                       float(s.altitude_ft or 0)))
    return league if home is None else 0.5 * home + 0.5 * league


def kick_factor(market: str, game, sport: str, team: str | None = None) -> tuple:
    """(multiplier, why) for a kicker's field goals in tonight's air
    against the air his average was built in (``usual_dev``), from a
    density fit that held; (1.0, "") otherwise."""
    if market not in KICK_MARKETS or sport not in ("nfl", "cfb") or game is None:
        return 1.0, ""
    fit = kicks_verdict(sport)
    if not fit.get("holds") or not fit.get("full"):
        return 1.0, ""
    from . import kickphysics as K
    w = getattr(game, "weather", None)
    dome = bool(getattr(w, "dome", False))
    if not dome and not (getattr(w, "measured", False) or getattr(w, "forecast", False)):
        # The 65° placeholder an unforecast outdoor game carries is not air
        # anyone measured (models.Weather.measured).
        return 1.0, ""
    temp = K.DOME_F if dome else getattr(w, "temp_f", None)
    dev = K.density_dev(K.air_density(temp, K._altitude(getattr(game, "home", "") or "")))
    if dev is None:
        return 1.0, ""

    def made(d):
        return sum(K.prob(fit["full"], {"distance": x, "outdoors": False, "wind": 0.0, "dens_dev": d})
                   for x in KICK_DISTANCES)
    usual = usual_dev(fit, team)
    f = made(dev) / made(usual)
    mult = f if market == "fg_made" else 1.0 + FG_SHARE * (f - 1.0)
    if abs(mult - 1.0) < 0.005:
        return 1.0, ""
    gap = dev - usual
    return round(mult, 4), (f"Tonight's air is {abs(gap) * 100:.0f}% {'thinner' if gap < 0 else 'thicker'} than the air "
                            f"his record was kicked in: field goals {(f - 1) * 100:+.1f}%, from a fit that held on "
                            f"held-out kicks")


def sim_rho(sport: str, a: dict, b: dict) -> float | None:
    """The simulated games' correlation for two teammates' legs, once the
    simulation beat the parlay pricer held out; None otherwise."""
    if sport not in ("nfl", "cfb") or not sim_verdict().get("holds"):
        return None
    from . import ideas
    sec = ((ideas.LAST.get(sport) or ideas.read(sport) or {}).get("sections") or {}).get("sim") or {}
    p = (sec.get("players") or {}).get(f"{a.get('player')}|{a.get('market')}")
    for link in (p or {}).get("links") or []:
        if link.get("player") == b.get("player") and link.get("market") == b.get("market"):
            return float(link["rho"])
    return None


# ---- the Most Likely chance and the Edge refusal ---------------------------------------------

def _ideas(sport: str) -> dict:
    from . import ideas
    return ideas.LAST.get(sport) or ideas.read(sport) or {}


def _side(r: dict) -> str:
    return str(r.get("side") or "").strip().lower()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class _Reads:
    """One build's readings and verdicts, loaded once."""

    def __init__(self, sport: str, data: dict | None = None):
        self.sport = sport
        self.secs = ((data if data is not None else _ideas(sport)) or {}).get("sections") or {}
        self.menu_v = menu_verdict(sport)
        self.att_v = attention_verdict(sport)
        self.copies_v = copies_verdict(sport)
        self.practice_v = practice_verdict(sport)
        self._recipe: dict = {}
        self._range: dict = {}

    def recipe(self, market):
        if market not in self._recipe:
            self._recipe[market] = recipe_verdict(self.sport, market)
        return self._recipe[market]

    def range(self, market):
        if market not in self._range:
            self._range[market] = range_verdict(self.sport, market)
        return self._range[market]


def shifts(r: dict, reads: _Reads) -> tuple:
    """(total shift to this pick's chance, the reasons) from the readings
    whose bar held — menu, recipe and attention. Signed for the pick's own
    side; capped at MAX_SHIFT."""
    side, player, market, line = _side(r), r.get("player"), r.get("market"), _num(r.get("line"))
    if side not in ("over", "under") or not player or not market:
        return 0.0, []
    total, why = 0.0, []
    from . import bookmenu
    best = None
    for m in bookmenu.for_player((reads.secs.get("menu") or {}).get("rows") or [], player):
        if not m.get("lean") or m.get("z") is None:
            continue
        par = m.get("parent") or {}
        if par.get("player") == player and par.get("market") == market:
            piece, favoured = "parent", ("over" if m["z"] > 0 else "under")
        elif any(p.get("player") == player and p.get("market") == market for p in m.get("parts") or []):
            piece, favoured = "parts", ("under" if m["z"] > 0 else "over")
        else:
            continue
        v = (reads.menu_v.get(m["check"]) or {}).get(piece) or {}
        if v.get("holds") and (best is None or abs(m["z"]) > abs(best[0])):
            best = (m["z"], favoured, float(v.get("excess") or 0.0), m.get("book"), m.get("label"))
    if best:
        s = best[2] if side == best[1] else -best[2]
        total += s
        why.append(f"{best[3]}'s menu does not add up ({best[4]}): measured {s:+.0%} on this side")
    rec = ((reads.secs.get("recipe") or {}).get("rows") or {}).get(f"{player}|{market}")
    rv = reads.recipe(market)
    if rec and rv.get("holds") and line is not None:
        from .bookrecipe import FLAG_SD
        gap = float(rec["expect"]) - line
        if abs(gap) >= FLAG_SD * float(rec.get("sd") or 1e9):
            favoured = "over" if gap > 0 else "under"
            s = float(rv.get("excess") or 0.0) * (1 if side == favoured else -1)
            total += s
            why.append(f"the outcome recipe expects {rec['expect']} against {line:g}: measured {s:+.0%} on this side")
    att = ((reads.secs.get("attention") or {}).get("players") or {}).get(player)
    if att and att.get("spike") and reads.att_v.get("holds"):
        ex = float(((reads.att_v.get("under_when_spiked") or {}).get("excess")) or 0.0)
        s = ex if side == "under" else -ex
        total += s
        why.append(f"the public is reading about him {att.get('ratio')}× more than usual: measured {s:+.0%} on this side")
    total = max(-MAX_SHIFT, min(MAX_SHIFT, total))
    return round(total, 4), why


def market_fair(r: dict, reads: _Reads) -> float | None:
    """The market's fair chance for this pick's side, one vote per opinion,
    once counting opinions beat counting books held out."""
    if not reads.copies_v.get("holds"):
        return None
    from . import bookclusters
    c = bookclusters.pick_view(reads.secs.get("copies") or {}, r.get("player"), r.get("market"))
    line, side = _num(r.get("line")), _side(r)
    if not c or c.get("by_group") is None or line is None or _num(c.get("line")) != line:
        return None
    p = float(c["by_group"])
    return round(p if side == "over" else 1.0 - p, 4) if side in ("over", "under") else None


def hold_reason(r: dict, reads: _Reads) -> str | None:
    """Why a proven reading takes this pick off, or None."""
    player, market, side = r.get("player"), r.get("market"), _side(r)
    if reads.practice_v.get("holds"):
        from . import practice
        pv = practice.pick_view(reads.secs.get("practice") or {}, player, market) or {}
        chance = pv.get("club") if pv.get("club") is not None else pv.get("league")
        if pv.get("designation") and chance is not None and float(chance) < HOLD_PLAYS:
            return (f"held back: men listed {pv['designation']} who {pv.get('practice') or 'had no practice note'} "
                    f"played {float(chance):.0%} of the time, on the record held out")
    v = reads.range(market) if market else {}
    proj, line = _num(r.get("projection")), _num(r.get("line"))
    if range_proven(v) and proj is not None and line is not None and side in ("over", "under"):
        from . import conformal
        cal = (_load("range", conformal.load).get("calibration") or {}).get(f"{reads.sport}|{market}")
        if cal:
            ch = conformal.side_chance(cal, proj, line, side)
            if ch < 0.5:
                return (f"held back: the honest range puts his {side} at {ch:.0%} — and that range was "
                        f"better calibrated than our chance on held-out picks")
    return None


def most_likely(rows: list, sport: str, data: dict | None = None) -> int:
    """The proven readings on the Most Likely pool, before its checks: a
    chance moved by the measured excess (``idea_note`` says why), the
    market's fair chance by opinion (``market_fair``), and a hold
    (``idea_hold``). Returns how many rows any of it touched."""
    reads = _Reads(sport, data)
    touched = 0
    for r in rows:
        if r.get("kind") == "game" or r.get("model_prob") is None:
            continue
        hit = False
        s, why = shifts(r, reads)
        # A posted pick keeps the number it went up at (likely._locked;
        # likelyboard.sync puts it back), so its chance is not moved here.
        if s and not r.get("locked"):
            raw = float(r["model_prob"])
            r["idea_raw_prob"] = raw
            # The journal keeps the FIRST claim, as likelyctx does, so the
            # record's own fits judge what we said, never this correction.
            r.setdefault("board_raw_prob", raw)
            r["model_prob"] = round(min(0.99, max(0.01, raw + s)), 4)
            r["idea_note"] = "; ".join(why)
            hit = True
        f = market_fair(r, reads)
        if f is not None:
            r["market_fair"] = f
            hit = True
        h = hold_reason(r, reads)
        if h:
            r["idea_hold"] = h
            hit = True
        touched += hit
    return touched


def edge(result: dict, sport: str, data: dict | None = None) -> int:
    """An Edge pick a proven reading holds, or whose edge it takes away, is
    refused with the reason. Returns how many."""
    from .odds import american_to_prob
    reads = _Reads(sport, data)
    n = 0
    for r in result.get("recommendations") or []:
        if not r.get("recommended") or r.get("hit_prob") is None:
            continue
        h = hold_reason(r, reads)
        s, why = shifts(r, reads)
        try:
            implied = american_to_prob(int(r.get("odds")))
        except (TypeError, ValueError):
            implied = None
        gone = s < 0 and implied is not None and float(r["hit_prob"]) + s <= implied
        if not (h or gone):
            continue
        reason = h or ("Refused: a proven reading takes the edge away — " + "; ".join(why))
        r["recommended"] = False
        r["stake_units"] = 0.0
        r["idea_refused"] = reason
        r["reasons"] = [reason] + list(r.get("reasons") or [])
        n += 1
    return n


# ---- the state of every gate -----------------------------------------------------------------

GATES = (
    ("rookie", "rookies", "the projection's prior for a thin rookie sample",
     lambda s: any(rookie_verdict(m).get("holds") for m in ("rec_yds", "receptions", "rush_yds"))),
    ("role", "rolechange", "the usage bridge's volume (targets, carries); the touchdown card's snap share",
     lambda s: any((role_verdict(k).get("verdict") or {}).get("holds") for k in ("tgt", "car", "snap"))),
    ("kicks", "kickphysics", "a kicker's field goals (fg_made, kick_pts)", lambda s: bool(kicks_verdict(s).get("holds"))),
    ("sim", "playsim", "the parlay pricer's correlation for two teammates", lambda s: bool(sim_verdict().get("holds"))),
    ("menu", "bookmenu", "Most Likely chance; Edge refusal",
     lambda s: any(v.get("holds") for sides in menu_verdict(s).values() for v in (sides or {}).values())),
    ("recipe", "bookrecipe", "Most Likely chance; Edge refusal",
     lambda s: any(recipe_verdict(s, m).get("holds") for m in ("rec_yds", "receptions", "rush_yds", "pass_yds"))),
    ("attention", "attention", "Most Likely chance; Edge refusal", lambda s: bool(attention_verdict(s).get("holds"))),
    ("copies", "bookclusters", "the Most Likely market check (fair chance by opinion)",
     lambda s: bool(copies_verdict(s).get("holds"))),
    ("practice", "practice", "holds a listed man unlikely to play off Most Likely and Edge",
     lambda s: bool(practice_verdict(s).get("holds"))),
    ("endgame", "nhl.endgame", "the NHL puck line, total and moneyline: the final score's shape (score effects, "
     "the pulled goalie, the empty net) — priced in nhl_build.game_bets",
     lambda s: s == "nhl" and bool(endgame_verdict().get("holds"))),
    ("range", "conformal", "holds a pick the honest range puts under even",
     lambda s: any(range_proven(v) for k, v in ((_load("range", __import__("engine.conformal", fromlist=["x"]).load)
                                                .get("held_out") or {}).items()) if k.startswith(f"{s}|"))),
)
NEVER = (("curve", "altcurve", "picks sit at the main line, where the curves agree by construction"),
         ("autopsy", "autopsy", "it names the step that is wrong; it is not a step"),
         ("risk", "risk", "My Bets only"))


def state(sport: str = "nfl") -> list:
    """[(name, module, what it moves, "HOLDS — applied" | "waiting on its verdict")]."""
    out = []
    for name, mod, moves, fn in GATES:
        out.append((name, mod, moves, "HOLDS — applied" if fn(sport) else "waiting on its verdict"))
    for name, mod, why in NEVER:
        out.append((name, mod, why, "never a number, by design"))
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Which of the inventions are moving picks, and which wait on their verdict")
    ap.add_argument("--sport", default="nfl", help="nfl, cfb or nhl (default nfl)")
    a = ap.parse_args(argv)
    print(f"The inventions in the picks — {a.sport}")
    for name, mod, moves, st in state(a.sport):
        print(f"  {name:<10} {st:<26} {moves}  (engine/{mod})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
