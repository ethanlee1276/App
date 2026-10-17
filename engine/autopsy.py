"""The loss autopsy — every graded pick's miss split into volume and efficiency, summed into the step that is wrong most.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 12. `engine/causes`
tags a loss "blowout", "short run" or "variance", which says what the game
was like, not which part of our number broke. A receiving-yards pick has
two parts: how many times he is thrown to (the usage step) and what he
does with each target (the per-touch step). A loss on four targets is a
different mistake from a loss on eleven targets and three yards a catch.

THE SPLIT, EXACT. With the projection P, his role going in (the targets,
carries or attempts a game over his four games before, `nflusage`'s window)
O, what he got O' and what he did A:

    A − P  =  (O' − O) · P/O        the volume part
           +  O' · (A/O' − P/O)     the efficiency part

which add to the miss with nothing left over. A market that is its own
opportunity (carries, attempts) is all volume.

THE TAGS, most specific first, on each loss: "left early" (his snap share
under LEFT_EARLY of his usual — the injury or exit step), "script" (a
blowout final, `causes.BLOWOUT_MARGIN`, and the volume part against the
pick), then "volume" or "efficiency" when that part carried SHARE of what
went against the pick, else "both".

WHICH STEP IS WRONG MOST, MEASURED AGAINST THE WINS. A part goes against
a pick in wins too, so a raw count of losses would blame whichever step is
noisiest. Each step's rate of going against the pick among losses is set
beside its rate among wins; a step is named only if its excess has z ≥
MIN_Z (two proportions) over at least MIN_LOSSES losses. Until then the
page says no step stands out. Nothing on the board reads any of it.

Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import re
import time

#: Each market's opportunity in the logs.
DECOMP = {"rec_yds": "targets", "receptions": "targets", "rush_yds": "carries", "rush_att": "carries",
          "pass_yds": "pass_att", "pass_cmp": "pass_att", "pass_att": "pass_att"}
VOLUME_ONLY = {"rush_att", "pass_att"}
ROLE_GAMES = 4
MIN_ROLE_GAMES = 2
LEFT_EARLY = 0.6
USUAL_SNAPS = 0.4
SHARE = 0.6
MIN_Z = 2.0
MIN_LOSSES = 100
REFRESH_SECONDS = 86400
STORE = "autopsy.json"
STEPS = {"volume": "the usage step (how much he is used)", "efficiency": "the per-touch step (what he does with each)",
         "script": "the game-script step", "left_early": "availability (an injury or an early exit)"}


def _norm(name):
    from .backtest import _norm as n
    return n(name)


def season_week(date) -> tuple | None:
    m = re.match(r"^(\d{4})-W(\d{1,2})$", str(date or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def decompose(proj: float, actual: float, opp_exp, opp_act, volume_only: bool = False) -> dict | None:
    """The miss as volume + efficiency; None without a role going in."""
    miss = float(actual) - float(proj)
    if volume_only:
        return {"volume": round(miss, 2), "efficiency": 0.0}
    if not opp_exp or opp_act is None:
        return None
    vol = (float(opp_act) - float(opp_exp)) * float(proj) / float(opp_exp)
    return {"volume": round(vol, 2), "efficiency": round(miss - vol, 2)}


def against(parts: dict, side: str) -> tuple:
    """How much each part went against the pick (positive hurt it)."""
    s = 1.0 if str(side).upper().startswith("O") else -1.0
    return (-s * parts["volume"], -s * parts["efficiency"])


def tag(parts: dict, side: str, snaps_usual=None, snaps=None, blowout: bool = False) -> str:
    av, ae = against(parts, side)
    if snaps_usual and snaps is not None and snaps_usual >= USUAL_SNAPS and snaps < LEFT_EARLY * snaps_usual:
        return "left early"
    if blowout and av > 0:
        return "script"
    tot = max(av, 0.0) + max(ae, 0.0)
    if tot <= 0:
        return "both"
    if av >= SHARE * tot:
        return "volume"
    if ae >= SHARE * tot:
        return "efficiency"
    return "both"


# ---- the journal and the logs ------------------------------------------------------------

def graded_picks(lconn) -> list:
    """Every graded pick in a market we can split, once (a pick journaled
    under two categories counts once), oldest first."""
    seen, out = set(), []
    marks = ",".join("?" * len(DECOMP))
    for r in lconn.execute(f"SELECT sport, date, player, market, side, line, projection, actual, status FROM bets "
                           f"WHERE status IN ('won','lost') AND actual IS NOT NULL AND projection IS NOT NULL "
                           f"AND market IN ({marks}) ORDER BY date, id", tuple(DECOMP)):
        sw = season_week(r[1])
        key = (r[0], r[1], r[2], r[3])
        if not sw or key in seen:
            continue
        seen.add(key)
        out.append({"sport": r[0], "date": r[1], "season": sw[0], "week": sw[1], "player": r[2], "market": r[3],
                    "side": r[4] or "", "line": r[5], "projection": float(r[6]), "actual": float(r[7]),
                    "won": r[8] == "won"})
    return out


def usage_index(hconn, sport: str, seasons) -> dict:
    """``{(norm player, season): {week: {market: value}}}`` for the
    opportunity markets and snap share."""
    seasons = sorted(set(seasons))
    if not seasons:
        return {}
    markets = sorted(set(DECOMP.values()) | {"snap_pct"})
    out: dict = {}
    for r in hconn.execute(
            "SELECT season, period, player, market, value FROM player_game_logs WHERE sport=? AND market IN (%s) "
            "AND season IN (%s)" % (",".join("?" * len(markets)), ",".join("?" * len(seasons))),
            (sport, *markets, *seasons)):
        try:
            out.setdefault((_norm(r[2]), int(r[0])), {}).setdefault(int(r[1]), {})[r[3]] = float(r[4] or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def role_going_in(weeks: dict, week: int, market: str):
    prior = [weeks[w][market] for w in sorted(weeks) if w < week and market in weeks[w]][-ROLE_GAMES:]
    return sum(prior) / len(prior) if len(prior) >= MIN_ROLE_GAMES else None


def _blowout(hconn, p) -> bool:
    from . import causes
    import sqlite3
    threshold = causes.BLOWOUT_MARGIN.get(p["sport"])
    if not threshold:
        return False
    try:
        margin = causes._final_margin(hconn, p)
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        return False                                  # no clean link to the game is no evidence of a blowout
    return margin is not None and margin >= threshold


def autopsy(picks: list, usage: dict, blowout=None) -> list:
    """Each pick with its split, the parts against it, and (for a loss) its tag."""
    out = []
    for p in picks:
        weeks = usage.get((_norm(p["player"]), p["season"])) or {}
        opp = DECOMP[p["market"]]
        now = weeks.get(p["week"]) or {}
        parts = decompose(p["projection"], p["actual"], role_going_in(weeks, p["week"], opp), now.get(opp),
                          p["market"] in VOLUME_ONLY)
        if parts is None:
            continue
        usual = role_going_in(weeks, p["week"], "snap_pct")
        blown = bool(blowout(p)) if blowout else False
        av, ae = against(parts, p["side"])
        left = bool(usual and usual >= USUAL_SNAPS and now.get("snap_pct") is not None
                    and now["snap_pct"] < LEFT_EARLY * usual)
        out.append({**p, "parts": parts, "against": {"volume": round(av, 2), "efficiency": round(ae, 2)},
                    "flags": {"volume": av > 0, "efficiency": ae > 0, "script": blown and av > 0, "left_early": left},
                    "tag": None if p["won"] else tag(parts, p["side"], usual, now.get("snap_pct"), blown)})
    return out


def summarize(rows: list) -> dict:
    """Tag shares among losses, and each step's rate of going against the
    pick in losses beside its rate in wins."""
    losses = [r for r in rows if not r["won"]]
    wins = [r for r in rows if r["won"]]
    tags: dict = {}
    for r in losses:
        tags[r["tag"]] = tags.get(r["tag"], 0) + 1
    steps = {}
    for step in STEPS:
        nl, nw = len(losses), len(wins)
        if not nl or not nw:
            continue
        pl = sum(r["flags"][step] for r in losses) / nl
        pw = sum(r["flags"][step] for r in wins) / nw
        pool = (pl * nl + pw * nw) / (nl + nw)
        se = math.sqrt(pool * (1 - pool) * (1 / nl + 1 / nw)) if 0 < pool < 1 else 0.0
        steps[step] = {"losses": round(pl, 3), "wins": round(pw, 3), "excess": round(pl - pw, 3),
                       "z": round((pl - pw) / se, 2) if se else None}
    named = [s for s, v in steps.items() if (v["z"] or 0) >= MIN_Z and v["excess"] > 0]
    worst = max(named, key=lambda s: steps[s]["excess"]) if named and len(losses) >= MIN_LOSSES else None
    return {"losses": len(losses), "wins": len(wins), "tags": tags, "steps": steps, "wrong_most": worst,
            "wrong_most_label": STEPS.get(worst)}


def build(rows: list) -> dict:
    """What the pick page reads: each sport-market's summary and every
    player's last three graded picks in each market."""
    by_market: dict = {}
    for r in rows:
        by_market.setdefault(f"{r['sport']}|{r['market']}", []).append(r)
    players: dict = {}
    for r in rows:
        players.setdefault(f"{r['sport']}|{r['player']}|{r['market']}", []).append(
            {"date": r["date"], "side": r["side"], "line": r["line"], "projection": r["projection"],
             "actual": r["actual"], "won": r["won"], "parts": r["parts"], "tag": r["tag"]})
    return {"built_at": time.time(), "all": summarize(rows),
            "markets": {k: summarize(v) for k, v in by_market.items()},
            "players": {k: v[-3:] for k, v in players.items()}}


# ---- storage, the box, the ideas file -----------------------------------------------------

def save(res: dict) -> str:
    from . import modelstate
    p = modelstate.path(STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(res, fh)
    os.replace(tmp, p)
    return p


def load() -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def run(lconn, hconn) -> dict:
    picks = graded_picks(lconn)
    usage: dict = {}
    for sport in sorted({p["sport"] for p in picks}):
        usage.update(usage_index(hconn, sport, [p["season"] for p in picks if p["sport"] == sport]))
    return build(autopsy(picks, usage, lambda p: _blowout(hconn, p)))


def refresh(max_age: float = REFRESH_SECONDS) -> bool:
    """Rebuild the saved autopsy when it is older than a day — the builds
    keep it current without anyone running the command."""
    if time.time() - float(load().get("built_at") or 0) < max_age:
        return False
    from . import db as _db
    from . import ledger as _ledger
    lconn, hconn = _ledger.connect(), _db.connect()
    try:
        save(run(lconn, hconn))
    finally:
        lconn.close()
        hconn.close()
    return True


def ideas_section(props, games, board, sport):
    saved = load()
    if not saved:
        return {"rows": {}}
    rows = {}
    for r in (board or {}).get("recommendations") or []:
        m = r.get("market")
        summ = (saved.get("markets") or {}).get(f"{sport}|{m}")
        if m not in DECOMP or not summ:
            continue
        rows[f"{r.get('player')}|{m}"] = {"market": m, "summary": summ,
                                          "his": (saved.get("players") or {}).get(f"{sport}|{r.get('player')}|{m}") or []}
    return {"rows": rows}


def journal(sport, sec):
    refresh()


def pick_view(sec, player, market, side="", line=None):
    return (sec.get("rows") or {}).get(f"{player}|{market}")


def game_view(sec, home, away):
    return None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Every graded pick's miss split into volume and efficiency; the step wrong most")
    ap.add_argument("--save", action="store_true", help="keep the autopsy for the pick page")
    a = ap.parse_args(argv)
    from . import db as _db
    from . import ledger as _ledger
    lconn, hconn = _ledger.connect(), _db.connect()
    try:
        res = run(lconn, hconn)
    finally:
        lconn.close()
        hconn.close()
    s = res["all"]
    print(f"The loss autopsy — {s['losses']} graded losses and {s['wins']} wins we can split")
    for key, m in sorted(res["markets"].items(), key=lambda kv: -kv[1]["losses"]):
        tags = ", ".join(f"{t} {n}" for t, n in sorted(m["tags"].items(), key=lambda kv: -kv[1]))
        print(f"  {key}: {m['losses']} losses — {tags}")
        for step, v in m["steps"].items():
            print(f"    {step:<11} against the pick in {v['losses']:.0%} of losses, {v['wins']:.0%} of wins "
                  f"(excess {v['excess']:+.0%}, z {v['z']})")
        print(f"    wrong most: {m['wrong_most_label'] or 'no step stands out yet'}")
    print(f"  ALL: wrong most — {s['wrong_most_label'] or 'no step stands out yet'} "
          f"(a step is named at z ≥ {MIN_Z} over ≥ {MIN_LOSSES} losses)")
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
