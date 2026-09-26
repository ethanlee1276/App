"""A college starting quarterback out, benched or back: noticed and shown.

Ethan, 2026-09-26: "look exactly what we did for NFL and make sure every
single thing is done for college football." The NFL build notices a
starting quarterback out (engine/qbchange) and puts the change under every
card of that team. College had no injury feed wired and no depth charts, so
it noticed nothing.

WHAT COLLEGE HAS, AND WHAT IT READS:

  * THE USUAL STARTER — the team's leading passer by yards over its
    logged games this season (last season's when this one has none);
  * LAST GAME'S STARTER — the leading passer of the team's newest game;
  * THIS WEEK'S — the quarterback the books priced a passing prop for. A
    book's menu is the market's own statement of who is expected to start,
    which in college, with no depth chart, is the best evidence there is;
  * ESPN'S COLLEGE INJURY BOARD (engine/sources/injuries.load_cfb_injuries).

  OUT       the usual starter is ruled out; his replacement is the priced
            quarterback, else the next passer by volume;
  BENCHED   the books priced someone else and the usual starter is not
            listed;
  RETURNS   the usual starter is priced this week after someone else
            started the team's last game — the Seattle case (Darnold back
            from Lock), which the NFL learned the hard way.

THE EFFECT IS NOT MEASURED FOR COLLEGE. The NFL's receivers-lose-10% came
from four seasons of NFL games (engine/qbfit); nothing like it has been run
on college, so the card is SHOWN on every row of that team and moves no
number — and says so. Standard library only.
"""
from __future__ import annotations

from ..qbchange import headline, detail

RULED_OUT = {"OUT", "IR", "DOUBTFUL"}


def passers(conn, season: int, teams) -> dict:
    """{team: {"season": n, "usual": name, "last": name, "by": {name: yards},
    "attempts": {name: games}}} from the college logs' passing yards."""
    teams = [t for t in teams if t]
    if not teams:
        return {}
    out: dict = {}
    for yr in (int(season), int(season) - 1):
        want = [t for t in teams if t not in out]
        if not want:
            break
        q = ("SELECT team, player, period, value FROM player_game_logs WHERE sport='cfb' "
             "AND market='pass_yds' AND season=? AND team IN (%s)" % ",".join("?" * len(want)))
        rows = conn.execute(q, [yr, *want]).fetchall()
        by_team: dict = {}
        for r in rows:
            team, player, period, value = r[0], r[1], str(r[2] or ""), float(r[3] or 0)
            t = by_team.setdefault(team, {"by": {}, "games": {}, "periods": {}})
            t["by"][player] = t["by"].get(player, 0.0) + value
            t["games"][player] = t["games"].get(player, 0) + 1
            t["periods"].setdefault(period, {})[player] = value
        for team, t in by_team.items():
            if not t["by"]:
                continue
            usual = max(t["by"], key=lambda p: t["by"][p])
            newest = max(t["periods"], key=lambda p: (len(p), p))
            last = max(t["periods"][newest], key=lambda p: t["periods"][newest][p])
            out[team] = {"season": yr, "usual": usual, "last": last,
                         "by": t["by"], "games": t["games"]}
    return out


def changes(qb: dict, injuries: list, priced_qbs: dict) -> dict:
    """{team: change} for every team whose quarterback situation moved.
    ``priced_qbs`` is {team: [names the books priced a passing prop for]}."""
    status = {(getattr(i, "team", ""), getattr(i, "player", "")): str(getattr(i, "status", "")).upper()
              for i in injuries or []}
    out: dict = {}
    for team, q in (qb or {}).items():
        usual, last = q["usual"], q["last"]
        st = status.get((team, usual), "")
        priced = [p for p in (priced_qbs or {}).get(team) or [] if p]
        this_week = priced[0] if len(priced) == 1 else None
        others = sorted((p for p in q["by"] if p != usual and status.get((team, p), "") not in RULED_OUT),
                        key=lambda p: -q["by"][p])
        base = {"team": team, "starter": usual, "tier": "unmeasured",
                "starter_games": q["games"].get(usual, 0)}
        if st in RULED_OUT:
            rep = this_week if this_week and this_week != usual else (others[0] if others else None)
            out[team] = {**base, "status": st, "replacement": rep,
                         "replacement_attempts": None}
        elif this_week and this_week != usual:
            out[team] = {**base, "status": "BENCHED", "replacement": this_week,
                         "replacement_attempts": None}
        elif this_week == usual and last != usual:
            # The usual starter back: `starter` is who filled in, as the
            # NFL's RETURNS reads (qbchange.headline).
            out[team] = {**base, "status": "RETURNS", "starter": last, "replacement": usual}
    return out


def card(ch: dict, own: bool = False) -> dict:
    """What goes under a pick of that team — shown, never applied."""
    if own and ch.get("status") == "RETURNS":
        note = f"Back as the starter; {ch['starter']} started the last game"
    elif own:
        note = f"Starting in place of {ch['starter']}"
    elif ch.get("status") == "RETURNS":
        note = "His usual quarterback is back — nothing to adjust"
    else:
        note = ("Shown for you, not priced: the NFL measured what a quarterback change does to "
                "his receivers; college has not been measured yet")
    words = headline(ch)
    if ch.get("status") == "BENCHED":
        words = f"{ch['replacement']} is the quarterback the books priced this week, not {ch['starter']}"
    return {"team": ch["team"], "starter": ch["starter"], "status": ch["status"],
            "replacement": ch.get("replacement"), "tier": ch.get("tier") or "unmeasured",
            "headline": words, "detail": detail(ch), "applied": 1.0, "note": note}


def read_game(game: dict, qb: dict, injuries: list) -> dict:
    """The game with ``qb_read`` — each side's likely starter off the logs
    and ESPN's board — for any side nobody confirmed by hand. Ethan,
    2026-09-26: "every game is saying QB Unconfirmed". The manual
    confirmation (engine/cfb/status, `launch.py --confirm-qb`) had never
    been filled in, so every card said it. This names the quarterback the
    data points to and why; it does NOT set ``qb_confirmed`` — whether this
    read may lift the conditional hold on game bets is Ethan's call."""
    status = {(getattr(i, "team", ""), getattr(i, "player", "")): str(getattr(i, "status", "")).upper()
              for i in injuries or []}
    st = game.get("qb_status") or {}
    read = {}
    for side in ("home", "away"):
        team = game.get(side) or ""
        if ((st.get(side) or {}).get("state") or "unknown") != "unknown":
            continue
        q = (qb or {}).get(team)
        if not q:
            continue
        usual, last = q["usual"], q["last"]
        listed = status.get((team, usual), "")
        if listed in RULED_OUT:
            nxt = sorted((p for p in q["by"] if p != usual and status.get((team, p), "") not in RULED_OUT),
                         key=lambda p: -q["by"][p])
            read[side] = {"starter": nxt[0] if nxt else "", "out": usual,
                          "why": f"{usual} is {listed.lower()} on ESPN's injury report"}
        elif last == usual:
            read[side] = {"starter": usual,
                          "why": "started the last game" + (f"; listed {listed.lower()}" if listed
                                                             else "; not on ESPN's injury report")}
        else:
            read[side] = {"starter": last, "why": f"started the last game ({usual} has the most yards)"}
    return {**game, "qb_read": read} if read else game


def stamp(rows, chs: dict) -> int:
    """Put the change's card on every row of that team (props, scorers,
    Most Likely rows): his own when he is one of the two quarterbacks."""
    n = 0
    for r in rows or []:
        if not isinstance(r, dict) or r.get("qb_card"):
            continue
        ch = (chs or {}).get(r.get("team") or "")
        if not ch:
            continue
        own = (r.get("player") or "") in (ch.get("starter"), ch.get("replacement"))
        r["qb_card"] = card(ch, own=own)
        n += 1
    return n
