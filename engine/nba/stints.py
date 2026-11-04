"""Who was on the floor, every second of a game: stints from the play-by-play.

Ethan, 2026-11-04: "work on the nba most likely and edge bets. Let's find
and invent more tools and data and sources to make better picks ... look at
how we kept looking for data and tools and resources for nfl to make better
picks and let's do that for nba."

THE SOURCE WE ALREADY HAD. The nightly reads every game's play-by-play from
cdn.nba.com (`sources.nbadata.fetch_playbyplay`) and kept only the shots
(engine/nba/shots). The same file logs every substitution, rebound, assist,
foul and turnover, and the official who called each foul. From the
substitutions this rebuilds the ten players on the floor at every moment,
and from that what a box score cannot say:

* **What a player did with a teammate off the floor.** The usage a star's
  absence opens, measured in every minute he sat, not only the games he
  missed (engine/nba/onoff reads whole games, and a star misses few).
* **His chances, not just his counts.** Rebounds against the misses there
  were to grab while he played; assists against the shots his teammates
  made while he played.
* **Possessions he was on the floor for**, so a rate is per chance, not per
  minute of a game that happened to be fast.
* **Garbage time**: minutes played with the game decided.
* **The crew**: the officials who called the fouls.

HOW THE FLOOR IS REBUILT. cdn.nba.com logs a substitution as an "out" and
an "in" at the moment it happens, and the changes between quarters at the
start of the next one, before its "Period Start". So the floor is carried
through the game, and each quarter's five are checked against the classic
inference: anyone who acts in a quarter before being subbed into it, or is
subbed out of it before being subbed in, started it. A team whose quarter
cannot be read as exactly five is recorded in ``quality`` rather than
guessed; a reader that needs every second (minutes) checks it.

Pure functions over a list of action dicts in cdn.nba.com's own shape (the
JSON's ``game.actions``; a CSV row with the same column names reads the
same, every value coerced here). No I/O.
"""

from __future__ import annotations

import re

#: A regulation quarter and an overtime, in seconds.
QUARTER_S = 720
OT_S = 300
#: Garbage time: the fourth quarter or later with the margin at least this
#: wide. The common public cut (pbpstats uses a sliding one; this is the
#: plain version, and every reader says which it used).
GARBAGE_MARGIN = 20
GARBAGE_FROM_PERIOD = 4

#: What each player's line inside one stint counts.
STINT_STATS = ("pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "tov")

_CLOCK = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")
#: Actions whose actor is not reliably on the floor: a technical can be
#: called on the bench, an ejection follows one. Never used to infer who
#: started a quarter (the player still gets the foul in his line).
_BENCH_OK = {("foul", "technical"), ("ejection", None), ("foul", "double technical")}


def clock_s(pt) -> float:
    """``PT11M56.00S`` → 716.0 seconds left in the period; ``None`` → 0."""
    m = _CLOCK.fullmatch(str(pt or "").strip())
    if not m:
        return 0.0
    return int(m.group(1) or 0) * 60 + float(m.group(2) or 0.0)


def period_len(period: int) -> int:
    return QUARTER_S if period <= 4 else OT_S


def elapsed(period: int, left: float) -> float:
    """Seconds since tip-off at ``left`` seconds remaining in ``period``."""
    before = QUARTER_S * min(period - 1, 4) + OT_S * max(period - 5, 0)
    return before + period_len(period) - left


def _pid(v) -> str:
    s = str(v if v is not None else "").strip()
    if not s:
        return ""
    try:
        n = int(float(s))
    except ValueError:
        return ""
    return str(n) if n > 0 else ""


def _int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def normalise(actions: list) -> list[dict]:
    """Every action as plain values, in the order they happened.

    ``orderNumber`` is the play-by-play's own running order; ``actionNumber``
    is not (an edited action keeps its number)."""
    out = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        sub = a.get("subType")
        out.append({
            "order": _int(a.get("orderNumber"), _int(a.get("actionNumber"))),
            "period": _int(a.get("period"), 1),
            "left": clock_s(a.get("clock")),
            "type": str(a.get("actionType") or "").lower(),
            "sub": (str(sub).lower() if sub not in (None, "") else None),
            "pid": _pid(a.get("personId")),
            "team": str(a.get("teamTricode") or ""),
            "assist": _pid(a.get("assistPersonId")),
            "steal": _pid(a.get("stealPersonId")),
            "block": _pid(a.get("blockPersonId")),
            "drawn": _pid(a.get("foulDrawnPersonId")),
            "official": _pid(a.get("officialId")),
            "result": str(a.get("shotResult") or "").lower(),
            "home": _int(a.get("scoreHome")),
            "away": _int(a.get("scoreAway")),
            "desc": str(a.get("description") or ""),
            "jump": [p for p in (_pid(a.get("jumpBallWonPersonId")),
                                 _pid(a.get("jumpBallLostPersonId"))) if p],
        })
    out.sort(key=lambda r: r["order"])
    return out


def _is_fg(r) -> bool:
    return r["type"] in ("2pt", "3pt")


def _ft_last(r) -> bool:
    """The last free throw of a trip: a miss on it is a live rebound."""
    s = r["sub"] or ""
    m = re.match(r"(\d) of (\d)", s)
    return bool(m) and m.group(1) == m.group(2)


def teams_of(acts: list[dict]) -> dict:
    """``{person: team}`` from the actions each player made himself, then,
    for a man who only ever appears beside someone else's action, from that
    action: an assist is the shooter's team's, a drawn foul and the losing
    side of a jump ball are the other team's."""
    seen: dict = {}
    for r in acts:
        if r["pid"] and r["team"] and r["type"] not in ("ejection",):
            seen.setdefault(r["pid"], {}).setdefault(r["team"], 0)
            seen[r["pid"]][r["team"]] += 1
    out = {p: max(t, key=t.get) for p, t in seen.items()}
    tms = sorted(set(out.values()))
    other = (lambda t: next((x for x in tms if x != t), "")) if len(tms) == 2 else (lambda t: "")
    for r in acts:
        if r["assist"] and r["assist"] not in out and r["team"]:
            out[r["assist"]] = r["team"]
        actor = out.get(r["pid"]) or r["team"]
        if r["drawn"] and r["drawn"] not in out and actor and other(actor):
            out[r["drawn"]] = other(actor)
        if r["type"] == "jumpball" and len(r["jump"]) == 2:
            won, lost = r["jump"]
            if won in out and lost not in out and other(out[won]):
                out[lost] = other(out[won])
            elif lost in out and won not in out and other(out[lost]):
                out[won] = other(out[lost])
    return out


def home_team(acts: list[dict]) -> str:
    """The team whose baskets move ``scoreHome``, or ""."""
    prev_h = prev_a = 0
    for r in acts:
        if r["type"] in ("2pt", "3pt", "freethrow") and r["result"] == "made" and r["team"]:
            if r["home"] > prev_h:
                return r["team"]
            if r["away"] > prev_a:
                tms = {x["team"] for x in acts if x["team"]}
                other = [t for t in tms if t != r["team"]]
                return other[0] if len(other) == 1 else ""
        prev_h, prev_a = max(prev_h, r["home"]), max(prev_a, r["away"])
    return ""


def _involved(r) -> list:
    """Everyone this action puts on the floor: the actor and the named
    assister, stealer, blocker, fouled player and jump-ball pair."""
    if (r["type"], r["sub"]) in _BENCH_OK or r["type"] == "ejection":
        return []
    return [p for p in (r["pid"], r["assist"], r["steal"], r["block"], r["drawn"], *r["jump"]) if p]


def quarter_starters(acts: list[dict], period: int, team_of: dict) -> dict:
    """``{team: [players]}`` on the floor when ``period`` started, read the
    classic way — acted in it before being subbed in, or subbed out before
    subbed in — with the between-quarter changes, which cdn.nba.com logs
    in the quarter before its "Period Start", applied first: subbed in
    there is on the floor at the start, subbed out there is not."""
    starters: dict = {}
    entered: set = set()
    benched: set = set()
    started = period == 1 and not any(
        r["period"] == 1 and r["type"] == "period" and r["sub"] == "start" for r in acts)
    for r in acts:
        if r["period"] != period:
            continue
        if r["type"] == "period" and r["sub"] == "start":
            started = True
            continue
        if r["type"] == "substitution":
            p = r["pid"]
            if not p:
                continue
            t = team_of.get(p) or r["team"]
            if not started:
                if r["sub"] == "in":
                    benched.discard(p)
                    if p not in starters.setdefault(t, []):
                        starters[t].append(p)
                elif r["sub"] == "out":
                    benched.add(p)
                    if p in starters.get(t, []):
                        starters[t].remove(p)
                continue
            if r["sub"] == "in":
                entered.add(p)
            elif r["sub"] == "out" and p not in entered and p not in benched:
                if p not in starters.setdefault(t, []):
                    starters[t].append(p)
            continue
        for p in _involved(r):
            if p in entered or p in benched:
                continue
            t = team_of.get(p)
            if t and p not in starters.setdefault(t, []):
                starters[t].append(p)
    return starters


def _blank(team: str) -> dict:
    return {"team": team, "sec": 0.0, "garbage_sec": 0.0,
            "pts": 0, "fgm": 0, "fga": 0, "fg3m": 0, "fg3a": 0, "ftm": 0, "fta": 0,
            "oreb": 0, "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0,
            "fouls_drawn": 0,
            # The floor around him while he played.
            "on_team_fga": 0, "on_team_fgm": 0, "on_team_fg3a": 0, "on_team_fta": 0,
            "on_team_tov": 0, "on_team_oreb": 0, "on_team_pts": 0,
            "on_opp_fga": 0, "on_opp_fgm": 0, "on_opp_fta": 0, "on_opp_tov": 0,
            "on_opp_oreb": 0, "on_opp_pts": 0,
            # Rebound chances: misses (field goals and last free throws)
            # while he was on, his team's and the other team's.
            "on_team_miss": 0, "on_opp_miss": 0,
            "pf_by_period": {}}


def rebuild(actions: list) -> dict:
    """The game, floor by floor.

    Returns ``{"home", "away", "players": {person: line}, "stints": [...],
    "officials": [ids], "quality": {"ok": bool, "periods": n, "bad": [...]}}``.
    A line carries the box score, seconds on the floor, seconds in garbage
    time, and the floor's counts while he was on it (``on_team_*``,
    ``on_opp_*``). A stint is ``{"t0", "t1", "period", "floor": {team:
    [five]}, "margin"}`` with the home side's margin at its start.
    """
    acts = normalise(actions)
    team_of = teams_of(acts)
    tms = sorted({t for t in team_of.values() if t})
    home = home_team(acts)
    away = next((t for t in tms if t != home), "") if home else ""
    if not home and len(tms) == 2:
        home, away = tms[1], tms[0]
    periods = sorted({r["period"] for r in acts if r["period"] >= 1})
    players: dict = {}
    stints: list = []
    officials: list = []
    bad: list = []

    def line(p):
        return players.setdefault(p, _blank(team_of.get(p, "")))

    floor: dict = {home: [], away: []}
    margin = 0                                   # home minus away
    t_last = 0.0
    stint_start = 0.0
    cur: dict = {}                               # {person: counts} this stint

    def stint_line(p):
        return cur.setdefault(p, dict.fromkeys(STINT_STATS, 0))

    def close_stint(t_now, period):
        nonlocal stint_start, cur
        if t_now > stint_start and all(len(floor.get(t, [])) for t in (home, away)):
            stints.append({"t0": round(stint_start, 1), "t1": round(t_now, 1),
                           "period": period, "margin": margin,
                           "floor": {t: list(floor[t]) for t in (home, away)},
                           "lines": cur})
        elif cur and stints:
            # Nothing elapsed (a change at the same instant): the counts
            # belong to the floor that was just closed.
            for q, c in cur.items():
                tgt = stints[-1]["lines"].setdefault(q, dict.fromkeys(STINT_STATS, 0))
                for k, v in c.items():
                    tgt[k] += v
        cur = {}
        stint_start = t_now

    def credit(t_now, period):
        """Seconds since the last action to everyone on the floor."""
        nonlocal t_last
        dt = t_now - t_last
        if dt > 0:
            garbage = period >= GARBAGE_FROM_PERIOD and abs(margin) >= GARBAGE_MARGIN
            for t in (home, away):
                for p in floor.get(t, []):
                    ln = line(p)
                    ln["sec"] += dt
                    if garbage:
                        ln["garbage_sec"] += dt
        t_last = max(t_last, t_now)

    for period in periods:
        starts = quarter_starters(acts, period, team_of)
        for t in (home, away):
            inferred = starts.get(t, [])
            carried = floor.get(t, [])
            # Quarter 1 has nothing carried. Later quarters carry the floor
            # through the between-quarter subs, which come first in the
            # quarter's actions; the inference checks it once they are in.
            if period == 1:
                if len(inferred) == 5:
                    floor[t] = list(inferred)
                else:
                    floor[t] = list(inferred[:5])
                    bad.append({"period": period, "team": t, "found": len(inferred)})
        p_start = elapsed(period, period_len(period))
        credit(p_start, period)
        t_last = p_start
        close_stint(p_start, period)
        checked = period == 1
        pre_in: dict = {home: [], away: []}       # subbed in before "Period Start"
        for r in [x for x in acts if x["period"] == period]:
            t_now = elapsed(period, r["left"])
            credit(t_now, period)
            if r["type"] == "period" and r["sub"] == "start" and not checked:
                # The between-quarter subs are in; check the carried five.
                # On the floor for certain: whoever acted in the quarter
                # before being subbed into it, and whoever was subbed in
                # before it started.
                close_stint(t_now, period)
                for t in (home, away):
                    sure = list(starts.get(t, []))
                    now5 = floor.get(t, [])
                    if len(now5) == 5 and all(p in now5 for p in sure):
                        continue
                    fix = (sure + [p for p in now5 if p not in sure])[:5]
                    if len(sure) > 5 or len(fix) != 5:
                        bad.append({"period": period, "team": t, "found": len(fix),
                                    "sure": len(sure)})
                    floor[t] = fix
                checked = True
                continue
            if r["type"] == "substitution" and not checked and r["sub"] == "in":
                t = team_of.get(r["pid"]) or r["team"]
                pre_in.setdefault(t, []).append(r["pid"])
            if r["type"] == "substitution":
                t = team_of.get(r["pid"]) or r["team"]
                if t not in floor:
                    continue
                # The interval up to now was played by the floor BEFORE
                # this change: close it first.
                close_stint(t_now, period)
                if r["sub"] == "out":
                    if r["pid"] in floor[t]:
                        floor[t].remove(r["pid"])
                    elif len(floor[t]) >= 5:
                        bad.append({"period": period, "team": t, "found": -1,
                                    "why": "out for a player not on the floor"})
                elif r["sub"] == "in" and r["pid"] and r["pid"] not in floor[t]:
                    floor[t].append(r["pid"])
                continue
            _count(r, team_of, floor, line, home, away, period, stint_line)
            if r["official"] and r["official"] not in officials:
                officials.append(r["official"])
            if r["type"] in ("2pt", "3pt", "freethrow") and r["result"] == "made":
                margin = r["home"] - r["away"]
        p_end = elapsed(period, 0.0)
        credit(p_end, period)
        close_stint(p_end, period)
    for p, ln in players.items():
        ln["sec"] = round(ln["sec"], 1)
        ln["garbage_sec"] = round(ln["garbage_sec"], 1)
    team_sec = {t: round(sum(ln["sec"] for ln in players.values() if ln["team"] == t), 1)
                for t in (home, away)}
    game_sec = elapsed(periods[-1], 0.0) if periods else 0.0
    ok = (not bad and all(abs(team_sec[t] - 5 * game_sec) < 1.0 for t in (home, away)))
    return {"home": home, "away": away, "players": players, "stints": stints,
            "officials": officials, "game_sec": game_sec,
            "quality": {"ok": ok, "periods": len(periods), "bad": bad, "team_sec": team_sec}}


def _count(r, team_of, floor, line, home, away, period, stint_line=None):
    """One action into the box score and the floor's counts."""
    typ, sub, p = r["type"], r["sub"], r["pid"]
    t = team_of.get(p) or r["team"]
    opp = away if t == home else home if t == away else ""

    def on(team):
        return floor.get(team, []) if team else []

    def bump(q, k, v=1):
        if stint_line is not None and q:
            stint_line(q)[k] += v

    if typ in ("2pt", "3pt"):
        made = r["result"] == "made"
        three = typ == "3pt"
        if p:
            ln = line(p)
            ln["fga"] += 1
            ln["fg3a"] += three
            bump(p, "fga")
            bump(p, "fg3a", int(three))
            if made:
                ln["fgm"] += 1
                ln["fg3m"] += three
                ln["pts"] += 3 if three else 2
                bump(p, "fg3m", int(three))
                bump(p, "pts", 3 if three else 2)
        for q in on(t):
            ln = line(q)
            ln["on_team_fga"] += 1
            ln["on_team_fg3a"] += three
            if made:
                ln["on_team_fgm"] += 1
                ln["on_team_pts"] += 3 if three else 2
            else:
                ln["on_team_miss"] += 1
        for q in on(opp):
            ln = line(q)
            ln["on_opp_fga"] += 1
            if made:
                ln["on_opp_fgm"] += 1
                ln["on_opp_pts"] += 3 if three else 2
            else:
                ln["on_opp_miss"] += 1
        if made and r["assist"]:
            line(r["assist"])["ast"] += 1
            bump(r["assist"], "ast")
        if r["block"]:
            pass                                # the block is its own action
    elif typ == "freethrow":
        made = r["result"] == "made"
        if p:
            ln = line(p)
            ln["fta"] += 1
            bump(p, "fta")
            if made:
                ln["ftm"] += 1
                ln["pts"] += 1
                bump(p, "pts")
        for q in on(t):
            ln = line(q)
            ln["on_team_fta"] += 1
            if made:
                ln["on_team_pts"] += 1
            elif _ft_last(r):
                ln["on_team_miss"] += 1
        for q in on(opp):
            ln = line(q)
            ln["on_opp_fta"] += 1
            if made:
                ln["on_opp_pts"] += 1
            elif _ft_last(r):
                ln["on_opp_miss"] += 1
    elif typ == "rebound":
        if p:
            ln = line(p)
            if sub == "offensive":
                ln["oreb"] += 1
            else:
                ln["dreb"] += 1
            bump(p, "reb")
        if sub == "offensive":
            team = t if p else r["team"]
            other = away if team == home else home if team == away else ""
            for q in on(team):
                line(q)["on_team_oreb"] += 1
            for q in on(other):
                line(q)["on_opp_oreb"] += 1
    elif typ == "turnover":
        if p:
            line(p)["tov"] += 1
            bump(p, "tov")
        team = t if p else r["team"]
        other = away if team == home else home if team == away else ""
        for q in on(team):
            line(q)["on_team_tov"] += 1
        for q in on(other):
            line(q)["on_opp_tov"] += 1
    elif typ == "steal":
        if p:
            line(p)["stl"] += 1
    elif typ == "block":
        if p:
            line(p)["blk"] += 1
    elif typ == "foul":
        if p and sub not in ("technical", "double technical"):
            ln = line(p)
            ln["pf"] += 1
            ln["pf_by_period"][period] = ln["pf_by_period"].get(period, 0) + 1
        if r["drawn"]:
            line(r["drawn"])["fouls_drawn"] += 1


def possessions(ln: dict, side: str = "team") -> float:
    """The floor's possessions while he was on, the usual estimate:
    FGA − OREB + TOV + 0.44 × FTA."""
    k = f"on_{side}_"
    return max(0.0, ln[k + "fga"] - ln[k + "oreb"] + ln[k + "tov"] + 0.44 * ln[k + "fta"])
