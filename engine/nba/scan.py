"""The NBA matchup scan: a tale of the tape for every game, the key
matchups — where one side's offence meets the other's defence — and a read
on every key player: who could shine, who could struggle, who could break
out.

Ethan, 2026-10-20: "make sure nba is ready to go ... match nfl for like all
features and data ... We need offense vs defense ... We need matchup details
... reports for nba and key matchups and breakout players." The football,
baseball and hockey scans write `scan_reads` rows the page already draws
(the dashboard's two lists, the game page's reads, the one Most Likely
board's matchup check, the matchup picks), so this writes the same shape:
{player, team, opp, pos, read, label, pro, con, notes, lean, headshot,
usage}.

THE TAPE (free, team-level): each side's scoring and what it allows, its
offence and defence per 100 possessions, pace, shooting, the threes, the
glass and the turnovers, each with its league rank (engine/nba/teams), and
the points tonight's lines expect. THE KEY MATCHUPS are the units where one
side's offence ranks near the top and the other's defence near the bottom
(or the reverse), widest gap first — the NFL scan's "biggest mismatches".

WHAT A READ COUNTS, each a reason for or against:
  * the defence in his own stats — what tonight's opponent allows a game in
    the points, rebounds, assists and threes he produces, and where that
    ranks (engine/hoopsdvp, the measured matchup the projection reads);
  * the game — the points the lines expect his team to score, or, before
    lines post, the pace both teams play at;
  * his role — minutes up or down over his last five, his share of the
    team's plays up or down (once the shooting columns are stored), and
    what the logs show when tonight's ruled-out teammate sat
    (engine/nba/onoff — measured, never guessed);
  * the schedule — a back-to-back or a third game in four nights on either
    side (engine/nba/schedspots);
  * the blowout — a double-digit spread takes a starter's fourth quarter.

A breakout spot is a strong case built on role: minutes, usage or a
teammate's absence moving toward him.

IT NEVER MOVES OUR NUMBER. The projection already reads the defence in each
stat (engine/hoopsdvp, measured), the minutes model the rest and the
blowout; the read picks the SIDE the Most Likely board leans to and the
markets a matchup pick may take, exactly as every other league's does.
Standard library only.
"""
from __future__ import annotations

from .teams import FT_WEIGHT, PLAIN

#: What each read is called, as the other leagues' scans say it.
LABELS = {"breakout": "Breakout spot", "good": "Good matchup", "neutral": "Neutral",
          "tough": "Tough matchup", "avoid": "Avoid"}
#: The stats a read is about, the per-game production that makes each his,
#: and their words.
LEAN_STATS = (("pts", 8.0, "points"), ("reb", 4.5, "rebounds"),
              ("ast", 3.0, "assists"), ("fg3m", 1.2, "threes"))
#: The summed markets and their parts (engine/hoops.SUMS): a read leans a
#: combo only when it leans every part of it.
COMBOS = {"pra": ("pts", "reb", "ast"), "pts_reb": ("pts", "reb"),
          "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}
#: A defence rank in the top or bottom this many of the league is a reason.
RANK_EDGE = 8
#: At most this many of a read's reasons come from the defence's stat ranks,
#: each way — a soft defence in three of his stats is one matchup, not three.
DVP_MAX = 2
#: Minutes up or down this much over his last five is a role change.
MIN_TREND = 0.12
#: His share of the team's plays up or down this much (absolute) likewise.
USAGE_EDGE = 0.03
#: The points the lines expect a team to score, this far from the league's
#: average team, is a reason.
IMPLIED_EDGE = 4.0
#: Before the lines post: both teams' pace this far from the league's.
PACE_EDGE = 1.5
#: In the games tonight's absent teammate missed, his share of the team's
#: points this much higher is a measured reason (engine/nba/onoff).
INHERIT_EDGE = 0.02
#: A ruled-out teammate playing this many minutes opens a real role.
VACANCY_MPG = 24.0
#: Players read per team: the top this many by minutes, and anyone priced.
KEY_PLAYERS = 8
#: A rotation player, and a starter whose fourth quarter a blowout takes.
MIN_MPG = 12.0
STARTER_MPG = 28.0
#: The blowout watch's spread (engine/nba/schedspots).
BLOWOUT_SPREAD = 10.0
#: The schedule spots that tire a team, and how a read says each.
TIRED = {"b2b_home": "on the second night of a back-to-back",
         "3in4": "playing a third game in four nights",
         "4in6_road": "playing a fourth game in six nights"}
#: A key matchup: an offence in the top this many against a defence in the
#: bottom this many (or the reverse) ...
EDGE_TOP = 10
#: ... and at least this far apart in rank (scaled to the league's size).
EDGE_GAP_SHARE = 0.35
#: The most key matchups a game lists.
EDGES_PER_GAME = 5
#: Ruled out (the injury report's words, nba_build.OUT_STATUSES).
OUT = {"out", "doubtful", "suspended", "inactive"}

#: The tape's rows: (stat, label, format). Per-100 rows need possessions,
#: which need the shooting columns (engine/nba/teams); without them the
#: per-game rows stand in.
PER100_ROWS = (("pts", "Points a game", "n"), ("opp_pts", "Points allowed a game", "n"),
               ("ortg", "Offense: points per 100 possessions", "n"),
               ("drtg", "Defense: points allowed per 100", "n"),
               ("pace", "Pace: possessions per 48 minutes", "n"),
               ("efg", "Shooting (effective FG%)", "pct"),
               ("opp_efg", "Shooting allowed (effective FG%)", "pct"),
               ("fg3m", "Threes made a game", "n"), ("opp_fg3m", "Threes allowed a game", "n"),
               ("oreb_pct", "Offensive rebounding (share of misses)", "pct"),
               ("tov_pct", "Turnovers (share of plays)", "pct"),
               ("opp_tov_pct", "Turnovers forced (share of plays)", "pct"))
PER_GAME_ROWS = (("pts", "Points a game", "n"), ("opp_pts", "Points allowed a game", "n"),
                 ("fg3m", "Threes made a game", "n"), ("opp_fg3m", "Threes allowed a game", "n"),
                 ("reb", "Rebounds a game", "n"), ("opp_reb", "Rebounds allowed a game", "n"),
                 ("ast", "Assists a game", "n"), ("tov", "Turnovers a game", "n"),
                 ("opp_tov", "Turnovers forced a game", "n"))

#: The key matchups: (offence stat, defence stat, per-100 only, how the
#: offence is said, how the defence is said — each with its rank as {r}).
#: The per-game three stand in for the per-100 ones on a season stored
#: before the shooting columns.
MATCHUPS = (("ortg", "drtg", True, "offense ({r} in points per 100)", "defense ({r} in points allowed per 100)"),
            ("efg", "opp_efg", True, "shooting ({r} in effective FG%)", "shooting defense ({r})"),
            ("fg3m", "opp_fg3m", None, "three-point shooting ({r} in threes made)",
             "perimeter defense ({r} in threes allowed)"),
            ("oreb_pct", "dreb_pct", True, "offensive rebounding ({r})", "defensive rebounding ({r})"),
            ("tov_pct", "opp_tov_pct", True, "ball security ({r})", "pressure ({r} in turnovers forced)"),
            ("ftr", "opp_ftr", True, "trips to the line ({r})", "fouling ({r} in free throws allowed)"),
            ("pts", "opp_pts", False, "scoring ({r} in points a game)", "defense ({r} in points allowed)"),
            ("reb", "opp_reb", False, "rebounding ({r})", "rebounds allowed ({r})"),
            ("tov", "opp_tov", False, "ball security ({r})", "pressure ({r} in turnovers forced)"))


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _most(rank: int, word: str) -> str:
    """"the most" for first, "the 4th-most" after — same for "fewest"."""
    return f"the {word}" if rank == 1 else f"the {_ord(rank)}-{word}"


def _signed(x: float) -> str:
    """"+8.0" / "−9.8", the minus a minus."""
    return f"{x:+.1f}".replace("-", "\u2212")


def _a(num: str) -> str:
    """"an 11.5-point spread", "a 12.5-point spread"."""
    whole = num.split(".")[0]
    return "an" if num.startswith("8") or whole in ("11", "18") else "a"


def _avg(xs) -> float | None:
    vals = [float(x) for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _edge(n: int, most: int = RANK_EDGE) -> int:
    """RANK_EDGE scaled to a league of ``n`` (8 of 30; fewer of a small one)."""
    return max(1, min(most, round(int(n or 30) * 0.27)))


def _status(listed: dict | None, name: str) -> str:
    return str(((listed or {}).get(name) or {}).get("status") or "").strip().lower()


# --- the game ------------------------------------------------------------------------
def environment(g: dict, prof: dict) -> dict:
    """{team: {"implied", "league_pts", "pace", "league_pace", "spread"}} —
    the points each side's posted lines expect, and both teams' pace."""
    home, away = g.get("home"), g.get("away")
    teams, league = (prof or {}).get("teams") or {}, (prof or {}).get("league") or {}
    spread, total = _f(g.get("spread")), _f(g.get("total"))
    implied = {}
    if spread is not None and total and total > 0:
        implied = {home: (total - spread) / 2, away: (total + spread) / 2}
    paces = [_f((teams.get(t) or {}).get("pace")) for t in (home, away)]
    pace = sum(paces) / 2 if all(p is not None for p in paces) else None
    out = {}
    for t in (home, away):
        own = None if spread is None else (spread if t == home else -spread)
        out[t] = {"implied": implied.get(t), "league_pts": _f(league.get("pts")), "pace": pace,
                  "league_pace": _f(league.get("pace")), "spread": own, "total": total}
    return out


def rest_of(spots: list | None, home: str, away: str) -> dict:
    """{team: rest bucket} from tonight's schedule spots."""
    for r in spots or []:
        if isinstance(r, dict) and r.get("home") == home and r.get("away") == away:
            tm = r.get("teams") or {}
            return {home: (tm.get("home") or {}).get("rest") or "", away: (tm.get("away") or {}).get("rest") or ""}
    return {}


def _cell(v, fmt: str) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if fmt == "pct" else f"{v:.1f}"


def key_matchups(home: str, away: str, prof: dict) -> list:
    """The units where one side's offence meets the other's defence at the
    far ends of the league, widest gap first: [{team, text, tone, gap}]."""
    teams = (prof or {}).get("teams") or {}
    n = int((prof or {}).get("n") or len(teams) or 30)
    per100 = all("ortg" in (teams.get(t) or {}) for t in (home, away))
    bar = max(2, round(n * EDGE_GAP_SHARE))
    top, edge = max(1, min(EDGE_TOP, round(n / 3))), _edge(n)
    out = []
    for order, (off_k, def_k, needs, off_w, def_w) in enumerate(MATCHUPS):
        if (needs is True and not per100) or (needs is False and per100):
            continue
        for a, b in ((away, home), (home, away)):
            ra = ((teams.get(a) or {}).get("ranks") or {}).get(off_k)
            rb = ((teams.get(b) or {}).get("ranks") or {}).get(def_k)
            if not ra or not rb:
                continue
            gap = rb - ra
            said_a, said_b = off_w.format(r=_ord(ra)), def_w.format(r=_ord(rb))
            if gap >= bar and ra <= top:
                what = f"{a}'s {said_a} against {b}'s {said_b}"
                out.append({"team": a, "tone": "off", "gap": gap, "unit": off_k, "order": order,
                            "matchup": what, "text": f"Edge {a}: {what}"})
            elif -gap >= bar and rb <= top:
                what = f"{b}'s {said_b} against {a}'s {said_a}"
                out.append({"team": b, "tone": "def", "gap": -gap, "unit": def_k, "order": order,
                            "matchup": what, "text": f"Edge {b}: {what}"})
    # The widest gap first; on a tie, the unit the list names first (the
    # ratings before the shooting before the glass), then the offence's.
    out.sort(key=lambda e: (-e["gap"], e["order"], e["tone"] != "off", e["text"]))
    rp = {t: ((teams.get(t) or {}).get("ranks") or {}).get("pace") for t in (away, home)}
    if all(rp.values()):
        if all(r <= edge for r in rp.values()):
            out.insert(0, {"team": "", "tone": "pace", "gap": 0, "unit": "pace",
                           "text": f"Two of the fastest teams: {away} ({_ord(rp[away])} in pace) and {home} "
                                   f"({_ord(rp[home])}) — a high-possession night for every counting stat"})
        elif all(r > n - edge for r in rp.values()):
            out.insert(0, {"team": "", "tone": "pace", "gap": 0, "unit": "pace",
                           "text": f"Two of the slowest teams: {away} ({_ord(rp[away])} in pace) and {home} "
                                   f"({_ord(rp[home])}) — fewer possessions, fewer chances to clear a line"})
    return out[:EDGES_PER_GAME]


def tape(home: str, away: str, prof: dict, env: dict | None = None, rest: dict | None = None) -> dict:
    """The game's tale of the tape — each side's numbers with their league
    ranks, the rows formatted for the page and the report, the key
    matchups, and how much of each team is still last season."""
    teams = (prof or {}).get("teams") or {}
    n = int((prof or {}).get("n") or len(teams) or 30)
    per100 = all("ortg" in (teams.get(t) or {}) for t in (home, away))
    spec = PER100_ROWS if per100 else PER_GAME_ROWS
    sides = {}
    for t in (away, home):
        p = teams.get(t) or {}
        keep = {k: round(float(p[k]), 4) for k, _l, _f in spec if p.get(k) is not None}
        sides[t] = {**keep, "ranks": {k: r for k, r in (p.get("ranks") or {}).items() if k in keep},
                    "games_season": p.get("games_season"), "games_last": p.get("games_last"),
                    "season_weight": p.get("season_weight"),
                    "rest": (rest or {}).get(t, ""), "rest_word": TIRED.get((rest or {}).get(t, ""), ""),
                    "implied": (None if (env or {}).get(t, {}).get("implied") is None
                                else round(env[t]["implied"], 1))}
    rows = []
    for k, label, fmt in spec:
        a, h = (teams.get(away) or {}).get(k), (teams.get(home) or {}).get(k)
        if a is None and h is None:
            continue
        rows.append({"key": k, "label": label, "a": _cell(a, fmt), "h": _cell(h, fmt),
                     "ar": (sides[away]["ranks"] or {}).get(k), "hr": (sides[home]["ranks"] or {}).get(k),
                     "plain": k in PLAIN})
    if all(sides[t]["implied"] is not None for t in (away, home)):
        rows.append({"key": "implied", "label": "Points the lines expect tonight",
                     "a": f"{sides[away]['implied']:.1f}", "h": f"{sides[home]['implied']:.1f}",
                     "ar": None, "hr": None, "plain": True})
    if not rows:
        return {}
    return {"sides": sides, "rows": rows, "edges": key_matchups(home, away, prof), "teams": n,
            "per100": per100, "note": season_note(home, away, prof),
            "basis": ("Ranks out of " + str(n) + ", 1st the best — the most for, the fewest against "
                      "(pace: 1st the fastest). None of this moves our numbers: the defence in each "
                      "stat, the minutes and the schedule are already inside our chances; the reads "
                      "below pick a side for the Most Likely board.")}


def season_note(home: str, away: str, prof: dict) -> str:
    """How much of each side's numbers is still last season's."""
    teams = (prof or {}).get("teams") or {}
    ws = {t: (_f((teams.get(t) or {}).get("season_weight")), int((teams.get(t) or {}).get("games_season") or 0))
          for t in (away, home)}
    if all(w is not None and w <= 0.0 for w, _n in ws.values()):
        return ("Last season's numbers for both teams until this season's games count — a summer's "
                "trades are not in them")
    bits = []
    for t, (w, n) in ws.items():
        if w is None or w >= 0.95:
            continue
        bits.append(f"{t} last season's numbers alone" if w <= 0.0
                    else f"{t} {n} game{'s' if n != 1 else ''} in, {round(w * 100)}% this season")
    return ("Team numbers blend this season with last: " + "; ".join(bits)) if bits else ""


# --- a player -------------------------------------------------------------------------
def production(h: dict, n: int = 10) -> dict:
    """{stat: a game over his last ``n``} for the read's stats and minutes."""
    out = {"min": _avg((h.get("minutes") or [])[:n])}
    for k, _bar, _w in LEAN_STATS:
        out[k] = _avg((h.get(k) or [])[:n])
    return out


def usage_share(h: dict, team: str, nights: dict | None, first: int, last: int) -> float | None:
    """His share of the team's plays (shots, free-throw trips, turnovers)
    while he was on the floor, over his games ``first``..``last`` (newest
    first) — the standard usage rate. None without the shooting columns."""
    if not nights:
        return None
    weeks = (h.get("dates") or [])[first:last]
    me = them = 0.0
    for d in weeks:
        g = (h.get("by_week") or {}).get(d) or {}
        t = nights.get((team, str(d)[:10])) or {}
        if any(g.get(k) is None for k in ("fga", "fta", "tov", "min")) or not g.get("min"):
            continue
        if any(t.get(k) is None for k in ("fga", "fta", "tov")):
            continue
        plays_t = t["fga"] + FT_WEIGHT * t["fta"] + t["tov"]
        if plays_t <= 0:
            continue
        team_min = float(t.get("min") or 240.0)
        me += (g["fga"] + FT_WEIGHT * g["fta"] + g["tov"]) * (team_min / 5.0)
        them += float(g["min"]) * plays_t
    return me / them if them > 0 else None


def _dvp_reasons(made: dict, opp: str, dvp_opp: dict) -> tuple[list, list, set, set]:
    """(pro, con, soft stats, hard stats) from the defence's rank in each of
    his stats (engine/hoopsdvp: rank 1 allows the most)."""
    pro, con, soft, hard = [], [], set(), set()
    for k, bar, word in LEAN_STATS:
        if (made.get(k) or 0) < bar:
            continue
        r = (dvp_opp or {}).get(k) or {}
        rank, of, pg = r.get("rank"), r.get("of"), _f(r.get("pg"))
        if not rank or not of or pg is None:
            continue
        if rank <= _edge(of):
            soft.add(k)
            if len(pro) < DVP_MAX:
                pro.append(f"{opp} allows {_most(rank, 'most')} {word} a game ({pg:.1f})")
        elif rank > of - _edge(of):
            hard.add(k)
            if len(con) < DVP_MAX:
                con.append(f"{opp} allows {_most(of - rank + 1, 'fewest')} {word} a game ({pg:.1f})")
    return pro, con, soft, hard


def lean_markets(made: dict, side: str, soft: set, hard: set) -> list:
    """The markets a read points at: the stats he produces, less any whose
    defence argues the other way, and the combos all of whose parts are in."""
    against = hard if side == "over" else soft
    base = [k for k, bar, _w in LEAN_STATS if (made.get(k) or 0) >= bar and k not in against]
    combos = [c for c, parts in COMBOS.items()
              if not any(p in against for p in parts) and any(p in base for p in parts)]
    return base + combos


def read_player(name: str, h: dict, team: str, opp: str, *, dvp: dict | None = None,
                env: dict | None = None, rest: dict | None = None, vacancy: dict | None = None,
                nights: dict | None = None, status: str = "", headshot: str = "") -> dict:
    """One player's read against tonight's opponent."""
    pro, con, notes = [], [], []
    made = production(h)
    d_pro, d_con, soft, hard = _dvp_reasons(made, opp, (dvp or {}).get(opp) or {})
    pro += d_pro
    con += d_con
    e = (env or {}).get(team) or {}
    imp, lg = _f(e.get("implied")), _f(e.get("league_pts"))
    pace, lp = _f(e.get("pace")), _f(e.get("league_pace"))
    if imp is not None and lg is not None:
        if imp >= lg + IMPLIED_EDGE:
            pro.append(f"{team} is expected to score {imp:.1f} by the lines — {_signed(imp - lg)} on the league's average")
        elif imp <= lg - IMPLIED_EDGE:
            con.append(f"{team} is expected to score only {imp:.1f} by the lines — {_signed(imp - lg)} on the league's average")
    elif pace is not None and lp is not None:
        if pace >= lp + PACE_EDGE:
            pro.append(f"A fast game: {team} and {opp} average {pace:.1f} possessions per 48 between them "
                       f"({_signed(pace - lp)} on the league)")
        elif pace <= lp - PACE_EDGE:
            con.append(f"A slow game: {team} and {opp} average {pace:.1f} possessions per 48 between them "
                       f"({_signed(pace - lp)} on the league)")
    role = False
    mins = [float(m) for m in (h.get("minutes") or []) if m is not None]
    m5 = _avg(mins[:5]) if len(mins) >= 5 else None
    m_before = _avg(mins[5:15]) if len(mins) >= 10 else None
    if m5 is not None and m_before:
        move = m5 / m_before - 1
        if move >= MIN_TREND:
            pro.append(f"Minutes up {move:.0%} over his last five ({m5:.1f} a game, {m_before:.1f} before)")
            role = True
        elif move <= -MIN_TREND:
            con.append(f"Minutes down {abs(move):.0%} over his last five ({m5:.1f} a game, {m_before:.1f} before)")
    u5 = usage_share(h, team, nights, 0, 5)
    u_before = usage_share(h, team, nights, 5, 15)
    if u5 is not None and u_before is not None:
        if u5 - u_before >= USAGE_EDGE:
            pro.append(f"Usage up: {u5:.0%} of {team}'s plays while he is on the floor over his last five, "
                       f"{u_before:.0%} before")
            role = True
        elif u_before - u5 >= USAGE_EDGE:
            con.append(f"Usage down: {u5:.0%} of {team}'s plays while he is on the floor over his last five, "
                       f"{u_before:.0%} before")
    v = (vacancy or {}).get(team) or {}
    gone = [(n, m) for n, m in v.get("out") or [] if n != name]
    if gone:
        big, big_m = gone[0]
        inh = v.get("inherit") or {}
        b = (inh.get("beneficiaries") or {}).get(name) if inh.get("player") == big else None
        if inh.get("enough") and b and float(b.get("delta") or 0) >= INHERIT_EDGE:
            pro.append(f"In the {inh.get('n_out')} games {big} missed, he took {b['without']:.0%} of {team}'s "
                       f"points ({b['with']:.0%} with {big} playing)")
            role = True
        elif big_m >= VACANCY_MPG and (made.get("min") or 0) >= MIN_MPG:
            notes.append(f"{big} is out ({big_m:.0f} minutes a game) — his minutes and shots go to the "
                         f"rest of the rotation")
    mine, theirs = (rest or {}).get(team, ""), (rest or {}).get(opp, "")
    if theirs in TIRED and mine not in TIRED:
        pro.append(f"{opp} is {TIRED[theirs]}")
    elif mine in TIRED and theirs not in TIRED:
        con.append(f"{team} is {TIRED[mine]}")
    sp = _f(e.get("spread"))
    if sp is not None and abs(sp) >= BLOWOUT_SPREAD and (made.get("min") or 0) >= STARTER_MPG:
        num = f"{abs(sp):g}"
        con.append(f"{_a(num).capitalize()} {num}-point spread — a starter's fourth quarter is the first thing "
                   f"a blowout takes")
    # WHAT IS SHOWN, NEVER COUNTED.
    if status and status not in OUT:
        notes.insert(0, f"{name} is listed {status} himself — this read assumes he plays")
    form = [f"{_avg(h.get(k)[:5]):.1f} {w}" for k, bar, w in LEAN_STATS
            if (made.get(k) or 0) >= bar and len(h.get(k) or []) >= 5]
    if form:
        notes.append(f"{', '.join(form)} a game over his last five")
    opps = list(h.get("opps") or [])
    vs = [float(h["pts"][i]) for i, o in enumerate(opps[:len(h.get("pts") or [])]) if o == opp]
    if len(vs) >= 2:
        notes.append(f"{sum(vs) / len(vs):.1f} points a game in his last {len(vs)} against {opp}")
    att = [((h.get("by_week") or {}).get(d) or {}) for d in (h.get("dates") or [])[:5]]
    if att and all(g.get("fg3a") is not None for g in att):
        a3, m3 = sum(g["fg3a"] for g in att), sum(g.get("fg3m") or 0 for g in att)
        if a3 >= 5:
            notes.append(f"{m3:.0f} of {a3:.0f} from three over his last five ({m3 / a3:.0%})")
    score = len(pro) - len(con)
    key = ("breakout" if score >= 3 and role else "good" if score >= 2 else "neutral" if score >= 0
           else "tough" if score == -1 else "avoid")
    side = "over" if key in ("breakout", "good") else "under" if key in ("tough", "avoid") else ""
    usage = {"mpg": None if made.get("min") is None else round(made["min"], 1),
             "min5": None if m5 is None else round(m5, 1),
             "usg": None if u5 is None else round(u5, 3), "starter": bool(h.get("starter"))}
    out = {"player": name, "team": team, "opp": opp, "pos": "", "read": key, "label": LABELS[key],
           "pro": pro, "con": con, "notes": notes,
           "lean": lean_markets(made, side, soft, hard) if side else [],
           "headshot": headshot, "usage": usage}
    if status and status not in OUT:
        out["own_status"] = status.upper()
    return out


def scan(games: list, hist: dict, prof: dict, *, dvp: dict | None = None, spots: list | None = None,
         listed: dict | None = None, vacancy: dict | None = None, key_players: set | None = None,
         out_players: set | None = None, faces: dict | None = None, nights: dict | None = None) -> dict:
    """{"reads": {away@home: {"players": [...]}}, "tapes": {away@home: tape}}.

    ``key_players``: anyone with a priced prop gets a read whatever his
    minutes. ``out_players``: every book took his props down — no read, as
    a man the injury report rules out gets none."""
    key_players, out_players = set(key_players or ()), set(out_players or ())
    reads, tapes = {}, {}
    for g in games or []:
        home, away = g.get("home"), g.get("away")
        if not home or not away:
            continue
        k = f"{away}@{home}"
        env = environment(g, prof)
        rest = rest_of(spots, home, away)
        t = tape(home, away, prof, env=env, rest=rest)
        if t:
            tapes[k] = t
        rows = []
        for team, opp in ((away, home), (home, away)):
            roster = [(n, h) for n, h in (hist or {}).items() if h.get("team") == team
                      and n not in out_players and _status(listed, n) not in OUT
                      and len([m for m in (h.get("minutes") or [])[:10] if m is not None]) >= 3]
            roster.sort(key=lambda nh: (-(production(nh[1]).get("min") or 0.0), nh[0]))
            chosen = {n for n, h in roster[:KEY_PLAYERS] if (production(h).get("min") or 0) >= MIN_MPG}
            chosen |= {n for n, _h in roster if n in key_players}
            for n, h in roster:
                if n in chosen:
                    rows.append(read_player(n, h, team, opp, dvp=dvp, env=env, rest=rest, vacancy=vacancy,
                                            nights=nights, status=_status(listed, n),
                                            headshot=(faces or {}).get(n, "")))
        rows.sort(key=lambda x: (list(LABELS).index(x["read"]), -len(x["pro"]), x["player"]))
        if rows:
            reads[k] = {"players": rows}
    return {"reads": reads, "tapes": tapes}
