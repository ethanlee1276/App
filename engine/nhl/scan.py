"""The NHL matchup scan: a tale of the tape for every game and a read on
every key player — who could shine, who could struggle.

Ethan, 2026-10-03: "dive deeper into looking at what features we have for
NFL and implement them into NHL ... I know we could use the who could do
good and who could struggle and all that." The NFL and MLB scans write
`scan_reads` rows the page already draws (the dashboard's two lists, the
game page's reads, the one Most Likely board's matchup check), so this
writes the same shape: {player, team, opp, pos, read, label, pro, con,
notes, lean, headshot, usage}.

SHOT QUALITY (engine/nhl/xg.py): where our expected-goals model has the
shots, the tape adds each side's 5-on-5 expected goals for and against, a
skater's read weighs the chances the opponent allows and the opposing
starter's goals saved above expected (over his save rate), and a note
says when a shooter's goals run hot or cold against what his shots were
worth — the regression a price may not have caught.

WHAT A READ COUNTS, in Scalpy NHL 1.0's order (the starting goalie first,
then the opponent's 5-on-5 process as our box scores carry it, then the
game's expected goals, then rest and role). It never moves our number —
the projection already carries the opponent's shots, the goalie and the
expected goals; the read picks the SIDE the Most Likely board leans to,
exactly as the NFL's does.
"""
from __future__ import annotations

from . import model as M

#: What each read is called, as the football and baseball scans say it.
LABELS = {"breakout": "Breakout spot", "good": "Good matchup", "neutral": "Neutral",
          "tough": "Tough matchup", "avoid": "Avoid"}
#: The markets a skater's read leans; a starter's leans his saves.
SKATER_LEANS = ["sog", "points", "assists", "goals", "anytime_goal"]
GOALIE_LEANS = ["saves"]
#: A rank in the top or bottom this many of the league is worth a reason.
RANK_EDGE = 8
#: A goalie this far off the league save rate (regressed) is worth a reason.
SV_EDGE = 0.006
#: Expected regulation goals for a team that counts as a high / low night.
HIGH_XG, LOW_XG = 3.3, 2.5
#: A starter this many goals above or below expected is worth a reason.
GSAX_EDGE = 3.0
#: A skater counts as "key" for a read: the team's top this many by ice time.
KEY_SKATERS = 9


def _label(pro: list, con: list, breakout: bool) -> tuple[str, str]:
    score = len(pro) - len(con)
    key = ("breakout" if score >= 3 and breakout else "good" if score >= 2
           else "neutral" if score >= 0 else "tough" if score == -1 else "avoid")
    return key, LABELS[key]


def _ranks(teams: dict, key: str, high_is_more: bool = True) -> dict:
    """{team: 1..N}, 1 = the most of ``key``."""
    vals = [(t, v[key]) for t, v in teams.items() if v.get(key) is not None]
    vals.sort(key=lambda kv: -kv[1] if high_is_more else kv[1])
    return {t: i + 1 for i, (t, _v) in enumerate(vals)}


def tape(home: str, away: str, teams: dict, ctx: dict) -> dict:
    """The game's tale of the tape: each side's goals and shots for and
    against a game with their league ranks, the probable starters, rest,
    and the expected goals — the free half of the scan."""
    n = len(teams) or 32
    rk = {k: _ranks(teams, k, hi) for k, hi in (("gf", True), ("ga", False),
                                                ("sog_for", True), ("sog_against", False),
                                                ("xgf_ev", True), ("xga_ev", False))}
    sides = {}
    for t in (away, home):
        prof, c = teams.get(t) or {}, ctx.get(t) or {}
        sides[t] = {
            "gf": prof.get("gf"), "ga": prof.get("ga"), "sog_for": prof.get("sog_for"),
            "sog_against": prof.get("sog_against"),
            "xgf_ev": round(prof["xgf_ev"], 2) if prof.get("xgf_ev") is not None else None,
            "xga_ev": round(prof["xga_ev"], 2) if prof.get("xga_ev") is not None else None,
            "starter_gsax": c.get("gsax"),
            "ranks": {k: rk[k].get(t) for k in rk if rk[k] or not k.startswith("x")},
            "starter": c.get("starter"), "starter_sv": c.get("sv"), "starter_share": c.get("starter_share"),
            "starter_sure": bool(c.get("starter_sure")), "b2b": bool(c.get("b2b")),
            "xg": round(c["xg"], 2) if c.get("xg") is not None else None,
            "season_weight": prof.get("season_weight"), "gp_season": prof.get("gp_season"),
        }
    return {"sides": sides, "teams": n}


def read_skater(name: str, p: dict, team: str, opp: str, teams: dict, ctx: dict, league: dict,
                headshot: str = "", xp: dict | None = None) -> dict:
    """One skater's read against tonight's opponent. ``xp`` is his
    engine.nhl.xg player summary, when the shot model has him."""
    pro, con, notes = [], [], []
    me, them = ctx.get(team) or {}, ctx.get(opp) or {}
    shots_rank = _ranks(teams, "sog_against", high_is_more=True).get(opp)
    ga_rank = _ranks(teams, "ga", high_is_more=True).get(opp)
    xga_rank = _ranks(teams, "xga_ev", high_is_more=True).get(opp)
    if shots_rank and shots_rank <= RANK_EDGE:
        pro.append(f"{opp} gives up {_most(shots_rank, 'most')} shots a game")
    elif shots_rank and shots_rank > len(teams) - RANK_EDGE:
        con.append(f"{opp} allows {_most(len(teams) - shots_rank + 1, 'fewest')} shots a game")
    if xga_rank and xga_rank <= RANK_EDGE:
        pro.append(f"{opp} gives up {_most(xga_rank, 'most')} 5-on-5 chances (expected goals against)")
    elif xga_rank and xga_rank > len(teams) - RANK_EDGE:
        con.append(f"{opp} allows {_most(len(teams) - xga_rank + 1, 'fewest')} 5-on-5 chances")
    sv, lsv = them.get("sv"), league.get("sv", M.LEAGUE_SV)
    gsax = them.get("gsax")
    if them.get("starter") and them.get("starter_sure") and gsax is not None:
        if gsax <= -GSAX_EDGE:
            pro.append(f"Faces {them['starter']}, {gsax:+.1f} goals saved above expected lately — letting in more than his shots are worth")
        elif gsax >= GSAX_EDGE:
            con.append(f"Faces {them['starter']}, {gsax:+.1f} goals saved above expected lately")
    elif them.get("starter") and them.get("starter_sure") and sv is not None:
        if sv <= lsv - SV_EDGE:
            pro.append(f"Faces {them['starter']}, .{round(sv * 1000):03d} save rate — below the league")
        elif sv >= lsv + SV_EDGE:
            con.append(f"Faces {them['starter']}, .{round(sv * 1000):03d} save rate — among the better starters")
    elif ga_rank and ga_rank <= RANK_EDGE:
        pro.append(f"{opp} allows {_most(ga_rank, 'most')} goals a game")
    xg = me.get("xg")
    if xg is not None and xg >= HIGH_XG:
        pro.append(f"{team} is expected to score {xg:.1f} — a high-event night")
    elif xg is not None and xg <= LOW_XG:
        con.append(f"{team} is expected to score only {xg:.1f}")
    games = [g for g in (p.get("games") or []) if g.get("toi", 0) > 0]
    t5 = [g["toi"] for g in games[:5]]
    t15 = [g["toi"] for g in games[5:15]]
    if len(t5) == 5 and len(t15) >= 5:
        move = sum(t5) / 5 / (sum(t15) / len(t15)) - 1
        if move >= 0.10:
            pro.append(f"Ice time up {move:.0%} over his last five games")
        elif move <= -0.10:
            con.append(f"Ice time down {abs(move):.0%} over his last five games")
    if them.get("b2b") and not me.get("b2b"):
        pro.append(f"{opp} is on the second night of a back-to-back")
    elif me.get("b2b") and not them.get("b2b"):
        con.append(f"{team} is on the second night of a back-to-back")
    sog = [g.get("sog", 0.0) for g in games[:10]]
    ppg = sum(g.get("ppg", 0.0) for g in games[:20])
    if ppg >= 3:
        notes.append(f"{int(ppg)} power-play goals in his last 20 — on the top unit")
    if len(sog) >= 5:
        notes.append(f"{sum(sog[:5]) / 5:.1f} shots a game his last five, {sum(sog) / len(sog):.1f} his last ten")
    if xp and xp.get("iff"):
        luck = xp["goals"] - xp["ixg"]
        notes.append(f"{xp['ixg']:.1f} expected goals, {xp['goals']} scored over his last {xp['games']}"
                     + (f" — finishing {'hot, due to cool' if luck > 0 else 'cold, due to warm'}"
                        if abs(luck) >= M.LUCK_GOALS else ""))
    volume = len(sog) >= 5 and sum(sog) / len(sog) >= 3.0
    key, label = _label(pro, con, volume)
    toi = sum(t5) / len(t5) if t5 else None
    return {"player": name, "team": team, "opp": opp, "pos": p.get("position") or "",
            "read": key, "label": label, "pro": pro, "con": con, "notes": notes, "lean": list(SKATER_LEANS),
            "headshot": headshot, "usage": {"toi": round(toi, 1) if toi else None}}


def read_goalie(name: str, team: str, opp: str, teams: dict, ctx: dict, headshot: str = "") -> dict:
    """The probable starter's read: how many shots he should see, and
    whether the game stays close enough for them to count."""
    pro, con, notes = [], [], []
    me, them = ctx.get(team) or {}, ctx.get(opp) or {}
    shots_rank = _ranks(teams, "sog_for", high_is_more=True).get(opp)
    if shots_rank and shots_rank <= RANK_EDGE:
        pro.append(f"{opp} shoots {_most(shots_rank, 'most')} a game")
    elif shots_rank and shots_rank > len(teams) - RANK_EDGE:
        con.append(f"{opp} shoots {_most(len(teams) - shots_rank + 1, 'fewest')} a game")
    allow_rank = _ranks(teams, "sog_against", high_is_more=True).get(team)
    if allow_rank and allow_rank <= RANK_EDGE:
        pro.append(f"{team} gives up {_most(allow_rank, 'most')} shots — busy night in net")
    elif allow_rank and allow_rank > len(teams) - RANK_EDGE:
        con.append(f"{team} allows {_most(len(teams) - allow_rank + 1, 'fewest')} shots")
    if me.get("xg") is not None and them.get("xg") is not None and them["xg"] - me["xg"] >= 1.0:
        con.append("A lopsided game — the goalie can be pulled and the script changes")
    if not me.get("starter_sure"):
        con.append("Starter not settled — the back-to-back or a split crease")
    notes.append(f"Started {me.get('starter_share', 0):.0%} of {team}'s last {M.STARTER_WINDOW}")
    if me.get("gsax") is not None:
        notes.append(f"{me['gsax']:+.1f} goals saved above expected lately")
    key, label = _label(pro, con, False)
    return {"player": name, "team": team, "opp": opp, "pos": "G", "read": key, "label": label,
            "pro": pro, "con": con, "notes": notes, "lean": list(GOALIE_LEANS), "headshot": headshot,
            "usage": {"starter_share": me.get("starter_share")}}


def scan(games: list[dict], players: dict, teams: dict, ctx: dict, league: dict,
         assets: dict | None = None, key_players: set | None = None, out_players: set | None = None,
         xg_players: dict | None = None) -> dict:
    """{"reads": {away@home: {"players": [...]}}, "tapes": {away@home: tape}}.

    ``key_players``: anyone with a priced prop gets a read whatever his ice
    time. ``out_players``: ruled out (the injury report, or every book took
    his props down) — no read for them."""
    assets = assets or {}
    key_players = key_players or set()
    out_players = out_players or set()
    reads, tapes = {}, {}
    for g in games:
        home, away = g["home"], g["away"]
        k = f"{away}@{home}"
        tapes[k] = tape(home, away, teams, ctx)
        rows = []
        for team, opp in ((away, home), (home, away)):
            skaters = [(n, p) for n, p in players.items() if p["team"] == team and p["position"] != "G"
                       and n not in out_players]
            skaters.sort(key=lambda np: -sum(x.get("toi", 0) for x in np[1]["games"][:10]))
            chosen = {n for n, _p in skaters[:KEY_SKATERS]} | {n for n, _p in skaters if n in key_players}
            for n, p in skaters:
                if n in chosen:
                    rows.append(read_skater(n, p, team, opp, teams, ctx, league,
                                            (assets.get(n) or {}).get("headshot", ""),
                                            xp=(xg_players or {}).get(n)))
            starter = (ctx.get(team) or {}).get("starter")
            if starter and starter not in out_players:
                rows.append(read_goalie(starter, team, opp, teams, ctx,
                                        (assets.get(starter) or {}).get("headshot", "")))
        rows.sort(key=lambda x: (list(LABELS).index(x["read"]), -len(x["pro"])))
        if rows:
            reads[k] = {"players": rows}
    return {"reads": reads, "tapes": tapes}


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _most(rank: int, word: str) -> str:
    """"the most" for first, "the 4th-most" after — same for "fewest"."""
    return f"the {word}" if rank == 1 else f"the {_ord(rank)}-{word}"
