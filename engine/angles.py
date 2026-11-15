"""The angles: where each defence leaks to the players this offence has (2026-11-14).

Ethan, 2026-11-14, of the research reports he writes for himself: "it looks
at the player's defense and offense and tries to find good matchups ...
the Giants are blitz-heavy defense and forces Daniels to run, so it gives
credit to one of those props. It explains how the Commanders are not good
with tight end coverage and tight end targets and tight end touchdowns ...
it goes through teams' red zone usage for players and red zone percentages
and how much they run and throw ... And I feel like we get that
information, but it's not that updated and it's not correct most of the
time. And also, it's very hard to find that information if we are giving
it."

His Commanders–Giants report won three legs on four angles, each one a
defence's leak met by a player who uses it:

  * WR1: "WAS allows a league-high 96.5 yds/game to WR1s ... has let a
    receiver top 90 yards in 5 of its 8 games" → Nabers;
  * TE: "WAS leaks to TEs ... 8 TDs allowed to TEs in 8 games" → Likely;
  * QB legs: "NYG blitzed him on 62.2% of his dropbacks in Week 5 ... he
    scrambled on 18.9% of dropbacks ... recent games allowed 103 yds to
    Daniels, 64 to Joe Milton and 32 to Tyler Shough" → Daniels' rushing;
  * red zone: Skattebo's goal-line work, the Giants' run-first red zone.

The board had the pieces — the defence-versus-position ratings, the
charting, the red-zone counts — spread over five sections and none of them
put to a player. This module puts them together, per game, BEFORE the rest
of the report, as sentences a bettor reads once: the leak, its number and
rank, the player it points at and the market.

THE NUMBERS ARE THIS SEASON'S, from the history database's own game logs
(player_game_logs: every player's targets, catches, yards, carries and
touchdowns by week, with the opponent) and this season's FTN charting
(engine/sources/ftn: each defence's blitz by week and who it faced, each
quarterback's scrambles). A defence's "WR1" is the receiver with the most
targets on the team it faced, over that team's season.

SHOWN, NOT COUNTED. None of these moves a probability: the defence-versus-
position step the model prices with is engine/defensevs, measured; these
are the sentences that say why a pick makes sense, and why a matchup is one
to avoid.

Standard library only. Never raises out of ``nfl_tables`` or ``for_game``.
"""
from __future__ import annotations

from collections import defaultdict

#: A rank this close to either end of the league is an angle (1 gives up the most).
EDGE_RANKS = 8
#: A WR1 game "topped" this many yards (his reports' "a receiver top 90 yards").
WR1_BIG = 90
#: A quarterback whose legs are an angle: this many scrambles or rushing yards a game.
QB_SCRAMBLES, QB_RUSH_YDS = 2.5, 20.0
#: A blitz-heavy defence: this share of dropbacks.
BLITZ_HEAVY = 0.35
#: Weeks of a defence's blitz counted as "lately".
RECENT_WEEKS = 4
#: The markets the tables read.
MARKETS = ("targets", "receptions", "rec_yds", "rec_td", "rush_yds", "rush_att", "carries",
           "rz_car", "rz_tgt", "i5_car")


def _week(period) -> int:
    try:
        return int(str(period).lstrip("0") or 0)
    except ValueError:
        return 0


def _ord(n: int) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _most(rank: int, n: int) -> str:
    """"the most" / "the 4th-most" / "the 3rd-fewest" by a rank of n."""
    if rank <= n / 2:
        return "the most" if rank == 1 else f"the {_ord(rank)}-most"
    r = n - rank + 1
    return "the fewest" if r == 1 else f"the {_ord(r)}-fewest"


def nfl_tables(conn, season: int, before_week: int | None = None) -> dict:
    """{"wr1": {defence: …}, "te": {…}, "qb_rush": {…}, "rz": {offence: …},
    "n": teams} — this season's games before ``before_week``. {} when the
    logs cannot be read."""
    try:
        q = ("SELECT player, team, opponent, position, period, market, value FROM player_game_logs "
             "WHERE sport='nfl' AND season=? AND market IN (%s)" % ",".join("?" * len(MARKETS)))
        rows = conn.execute(q, (int(season), *MARKETS)).fetchall()
    except Exception:                                        # noqa: BLE001
        return {}
    cells: dict = defaultdict(dict)        # (player, team, week) -> {market: value}, plus opp/pos
    for r in rows:
        r = dict(r) if not isinstance(r, dict) else r
        w = _week(r.get("period"))
        if w <= 0 or (before_week and w >= int(before_week)):
            continue
        k = (r.get("player") or "", r.get("team") or "", w)
        c = cells[k]
        c[r.get("market")] = float(r.get("value") or 0)
        if r.get("opponent"):
            c["_opp"] = r["opponent"]
        if r.get("position") and r["position"] not in ("", "DEF", "K"):
            c["_pos"] = r["position"]
    if not cells:
        return {}
    # Each team's WR1: the wide receiver with the most targets over its season.
    targets: dict = defaultdict(float)
    pos_of: dict = {}
    for (p, t, _w), c in cells.items():
        targets[(t, p)] += c.get("targets", 0.0)
        if c.get("_pos"):
            pos_of[(t, p)] = c["_pos"]
    wr1: dict = {}
    for (t, p), n in targets.items():
        if pos_of.get((t, p)) == "WR" and n > 0 and (t not in wr1 or n > targets[(t, wr1[t])]):
            wr1[t] = p
    games: dict = defaultdict(lambda: defaultdict(lambda: {"wr1": None, "te": [0.0, 0.0, 0.0],
                                                          "qb": [], "seen": False}))
    rz: dict = defaultdict(lambda: {"car": 0.0, "tgt": 0.0, "players": defaultdict(lambda: [0.0, 0.0, 0.0])})
    for (p, t, w), c in cells.items():
        d = c.get("_opp")
        pos = c.get("_pos") or pos_of.get((t, p)) or ""
        if d:
            g = games[d][(t, w)]
            g["seen"] = True
            if wr1.get(t) == p:
                g["wr1"] = (p, c.get("receptions", 0.0), c.get("rec_yds", 0.0), c.get("rec_td", 0.0))
            if pos == "TE":
                g["te"][0] += c.get("receptions", 0.0)
                g["te"][1] += c.get("rec_yds", 0.0)
                g["te"][2] += c.get("rec_td", 0.0)
            if pos == "QB" and (c.get("rush_yds") or c.get("rush_att") or c.get("carries")):
                g["qb"].append((p, c.get("rush_yds", 0.0), c.get("rush_att", c.get("carries", 0.0))))
        z = rz[t]
        z["car"] += c.get("rz_car", 0.0)
        z["tgt"] += c.get("rz_tgt", 0.0)
        pz = z["players"][p]
        pz[0] += c.get("rz_car", 0.0)
        pz[1] += c.get("rz_tgt", 0.0)
        pz[2] += c.get("i5_car", 0.0)
    out = {"wr1": {}, "te": {}, "qb_rush": {}, "rz": {}, "season": int(season), "before_week": before_week}
    for d, by in games.items():
        gl = sorted(by.items(), key=lambda kv: kv[0][1])
        w1 = [(t, w, g["wr1"]) for (t, w), g in gl if g["wr1"]]
        if w1:
            n = len(w1)
            out["wr1"][d] = {"games": n, "rec": round(sum(x[2][1] for x in w1) / n, 1),
                             "yds": round(sum(x[2][2] for x in w1) / n, 1),
                             "td": int(sum(x[2][3] for x in w1)),
                             "big": sum(1 for x in w1 if x[2][2] >= WR1_BIG),
                             "log": [{"week": w, "team": t, "player": x[0], "rec": int(x[1]),
                                      "yds": int(x[2]), "td": int(x[3])} for t, w, x in w1][-4:]}
        n = len(gl)
        if n:
            te = [g["te"] for _k, g in gl]
            out["te"][d] = {"games": n, "rec": round(sum(x[0] for x in te) / n, 1),
                            "yds": round(sum(x[1] for x in te) / n, 1), "td": int(sum(x[2] for x in te))}
            qb = [((t, w), max(g["qb"], key=lambda q: q[1])) for (t, w), g in gl if g["qb"]]
            if qb:
                out["qb_rush"][d] = {"games": n, "yds": round(sum(q[1] for _k, q in qb) / n, 1),
                                     "log": [{"week": k[1], "team": k[0], "player": q[0], "yds": int(q[1])}
                                             for k, q in qb][-3:]}
    full = _full_names(cells)
    for t, z in rz.items():
        tot = z["car"] + z["tgt"]
        if tot <= 0:
            continue
        # One man under one name: the short form's numbers join the full one's.
        merged: dict = defaultdict(lambda: [0.0, 0.0, 0.0])
        for p, v in z["players"].items():
            m = merged[full.get((t, p), p)]
            for i in range(3):
                m[i] += v[i]
        z["players"] = merged
        top = sorted(((p, v) for p, v in z["players"].items() if v[0] + v[1] > 0),
                     key=lambda pv: -(pv[1][0] + pv[1][1]))[:3]
        out["rz"][t] = {"plays": int(tot), "run_share": round(z["car"] / tot, 3),
                        "top": [{"player": p, "car": int(v[0]), "tgt": int(v[1]), "i5": int(v[2]),
                                 "share": round((v[0] + v[1]) / tot, 3)} for p, v in top]}
    # Ranks: 1 gives up the most.
    for key, field in (("wr1", "yds"), ("te", "yds"), ("qb_rush", "yds")):
        order = sorted(out[key], key=lambda d: -out[key][d][field])
        for i, d in enumerate(order, 1):
            out[key][d]["rank"] = i
        out[f"n_{key}"] = len(order)
    return out


def _last(name: str) -> str:
    return " ".join(str(name or "").replace(".", " ").split()[-1:]).lower()


def _same_man(full: str, short: str) -> bool:
    """"Jayden Daniels" and the play-by-play's "J.Daniels"."""
    a, b = str(full or "").replace(".", " ").split(), str(short or "").replace(".", " ").split()
    return bool(a and b) and a[-1].lower() == b[-1].lower() and a[0][:1].lower() == b[0][:1].lower()


class _Club:
    """A club said the way the rest of the report says it (gamereport's
    team_np, team_owner and _many): "the Lions give up" and "the Lions'
    coverage" for a plural nickname, "Indiana gives up" for a school, the
    code where no name is known. Ethan's screenshot (2026-11-15) read
    "Lions gives up", "Lions's coverage", "Patriots runs on 55% of its
    red-zone plays": the nickname was dropped into a sentence written for
    a code."""

    def __init__(self, c, t: str):
        try:
            from .gamereport import _many, team_np, team_owner
            self.np, self.own, self.many = team_np(c, t), team_owner(c, t), bool(_many(c, t))
        except Exception:                                    # noqa: BLE001  (a context without the report's helpers)
            n = c.name(t)
            self.np, self.own, self.many = n, f"{n}'s", False
        self.its, self.it = ("their", "they") if self.many else ("its", "it")

    def v(self, one: str, more: str) -> str:
        """The verb for the club: "gives" or "give"."""
        return more if self.many else one

    @property
    def Np(self) -> str:
        """The club opening a sentence: "The Patriots"."""
        return self.np[:1].upper() + self.np[1:]


def _full_names(cells: dict) -> dict:
    """{(team, "R.Stevenson"): "Rhamondre Stevenson"}: the play-by-play's
    short names (the red-zone carries and targets) said as the box score
    says the same man on the same team — only where exactly one of that
    team's names matches, so two Stevensons never trade numbers."""
    names: dict = defaultdict(set)
    for (p, t, _w) in cells:
        if p and " " in p.strip() and "." not in p.split()[0]:
            names[t].add(p)
    out = {}
    for (p, t, _w) in cells:
        if not p or (t, p) in out or p in names[t]:
            continue
        hits = [n for n in names[t] if _same_man(n, p)]
        if len(hits) == 1:
            out[(t, p)] = hits[0]
    return out


def _sits(c, player: str) -> bool:
    """Whether the report has him out, doubtful or questionable, or marked
    as maybe sitting (engine/availability): by his name or the play-by-play's
    short form of it."""
    try:
        from .availability import statuses
        hurt = list(statuses(c))
    except Exception:                                        # noqa: BLE001
        hurt = []
    marked = [r.get("player") for r in getattr(c, "reads", []) or [] if r.get("availability")]
    me = " ".join(str(player or "").lower().replace(".", " ").split())
    return any(" ".join(str(h or "").lower().replace(".", " ").split()) == me or _same_man(h, player)
               for h in hurt + marked)


def _share(r: dict) -> float:
    u = r.get("usage") or {}
    return float(u.get("tgt_share") or 0.0)


def for_game(c, tables: dict) -> list[dict]:
    """The game's angles, each {"team", "player", "pos", "tone", "text",
    "points_to"}: for each offence against the defence it faces — its WR1
    against that defence's WR1 funnel, its tight end against its tight-end
    funnel, its quarterback's legs against its blitz and the quarterbacks
    who ran on it, its red-zone scorer. ``c`` is the report's context
    (engine/gamereport.Ctx); [] when there is nothing to say."""
    out: list = []
    try:
        tables = tables if tables is not None else (getattr(c, "angle_tables", None) or {})
        reads = [r for r in getattr(c, "reads", []) or [] if not r.get("availability")]
        ch = (getattr(c, "scan", {}) or {}).get("charting") or {}
        for off in c.teams:
            d = c.opp[off]
            mine = [r for r in reads if r.get("team") == off]
            D, O = _Club(c, d), _Club(c, off)
            # 1. The top receiver against what the defence gives the top receiver.
            wrs = sorted((r for r in mine if str(r.get("pos") or "").upper() == "WR"), key=lambda r: -_share(r))
            w = (tables.get("wr1") or {}).get(d)
            n = tables.get("n_wr1") or 32
            if wrs and w and w.get("games", 0) >= 3:
                r = wrs[0]
                if w["rank"] <= EDGE_RANKS:
                    out.append({"team": off, "player": r["player"], "pos": "WR", "tone": "up",
                                "points_to": "catches and yards",
                                "text": (f"{r['player']} against {D.own} coverage of No. 1 receivers: {D.np} "
                                         f"{D.v('gives', 'give')} up {w['yds']:.0f} yards and {w['rec']:.1f} catches a "
                                         f"game to the top receiver {D.it} {D.v('faces', 'face')} "
                                         f"({_most(w['rank'], n)} in the league), and {w['big']} of {w['games']} "
                                         f"topped {WR1_BIG}")})
                elif w["rank"] > n - EDGE_RANKS:
                    out.append({"team": off, "player": r["player"], "pos": "WR", "tone": "down",
                                "points_to": "yards",
                                "text": (f"{r['player']} against {D.np}: {D.it} {D.v('holds', 'hold')} the top "
                                         f"receiver {D.it} {D.v('faces', 'face')} to {w['yds']:.0f} yards a game "
                                         f"({_most(w['rank'], n)}) — a tough draw for his yards")})
            # 2. The tight end against the tight-end funnel.
            tes = sorted((r for r in mine if str(r.get("pos") or "").upper() == "TE"), key=lambda r: -_share(r))
            t = (tables.get("te") or {}).get(d)
            n = tables.get("n_te") or 32
            if tes and t and t.get("games", 0) >= 3:
                r = tes[0]
                if t["rank"] <= EDGE_RANKS:
                    out.append({"team": off, "player": r["player"], "pos": "TE", "tone": "up",
                                "points_to": "catches, yards and a touchdown",
                                "text": (f"{r['player']} against {D.own} tight-end coverage: {D.np} "
                                         f"{D.v('gives', 'give')} up {t['yds']:.0f} yards and {t['rec']:.1f} catches a "
                                         f"game to tight ends ({_most(t['rank'], n)}), and {t['td']} touchdowns to them "
                                         f"in {t['games']} games")})
                elif t["rank"] > n - EDGE_RANKS:
                    out.append({"team": off, "player": r["player"], "pos": "TE", "tone": "down",
                                "points_to": "yards",
                                "text": (f"{r['player']} against {D.np}: {D.it} {D.v('holds', 'hold')} tight ends "
                                         f"to {t['yds']:.0f} yards a game ({_most(t['rank'], n)})")})
            # 3. The quarterback's legs against the blitz and the quarterbacks who ran on it.
            qbs = [r for r in mine if str(r.get("pos") or "").upper() == "QB"]
            if qbs:
                q = qbs[0]
                u = q.get("usage") or {}
                scr = next((s for s in (ch.get("scrambles") or {}).get(off) or [] if _same_man(q["player"], s.get("name"))),
                           None)
                spg = (float(scr["scrambles"]) / max(1, int(scr.get("weeks") or 1))) if scr else 0.0
                ypg = float(u.get("rush_yds_pg") or 0.0)
                if spg >= QB_SCRAMBLES or ypg >= QB_RUSH_YDS:
                    bits = []
                    dd = (ch.get("defense") or {}).get(d) or {}
                    weeks = (ch.get("defense_weeks") or {}).get(d) or []
                    rate = dd.get("blitz_rate")
                    if rate is not None:
                        recent = weeks[-RECENT_WEEKS:]
                        db, bl = sum(x["dropbacks"] for x in recent), sum(x["blitz"] for x in recent)
                        said = f"{D.np} {D.v('blitzes', 'blitz')} on {float(rate):.0%} of dropbacks this season"
                        if db >= 60 and abs(bl / db - float(rate)) >= 0.04:
                            said += f" ({bl / db:.0%} over {D.its} last {len(recent)} games)"
                        met = next((x for x in reversed(weeks) if x.get("opp") == off and x.get("dropbacks")), None)
                        if met:
                            said += (f", and {met['blitz'] / met['dropbacks']:.0%} of {O.own} dropbacks when they "
                                     f"met in week {met['week']}")
                        bits.append(said)
                    if scr and scr.get("scrambles"):
                        per = float(scr["yds"]) / max(1, int(scr["scrambles"]))
                        bits.append(f"{q['player']} scrambles {spg:.1f} times a game for {per:.1f} yards a scramble")
                    elif ypg:
                        bits.append(f"{q['player']} runs for {ypg:.0f} yards a game")
                    qr = (tables.get("qb_rush") or {}).get(d)
                    if qr and qr.get("log"):
                        runs = [f"{x['yds']} ({x['player']})" for x in reversed(qr["log"])]
                        ran = ", ".join(runs[:-1]) + (" and " if len(runs) > 1 else "") + runs[-1]
                        bits.append(f"quarterbacks have run for {ran} yards against {D.np} in {D.its} last "
                                    f"{len(qr['log'])} games ({_most(qr['rank'], tables.get('n_qb_rush') or 32)} "
                                    f"quarterback rushing yards allowed)")
                    heavy = rate is not None and float(rate) >= BLITZ_HEAVY
                    soft = bool(qr) and qr.get("rank", 99) <= EDGE_RANKS
                    if bits and (heavy or soft):
                        out.append({"team": off, "player": q["player"], "pos": "QB", "tone": "up",
                                    "points_to": "rushing yards",
                                    "text": f"{q['player']}'s legs: " + "; ".join(bits)})
            # 4. The red zone: who gets the ball inside the 20 and how the offence uses it.
            z = (tables.get("rz") or {}).get(off)
            # Its red-zone man who plays: one the injury report names, or a
            # read marked as maybe sitting, is not where to look (INJ1).
            top = next((x for x in (z or {}).get("top") or [] if not _sits(c, x["player"])), None)
            if z and top and z.get("plays", 0) >= 10:
                who = next((r for r in mine if _same_man(r.get("player"), top["player"])), None)
                name = who["player"] if who else top["player"]
                bits = [f"{O.Np} {O.v('runs', 'run')} on {z['run_share']:.0%} of {O.its} red-zone plays"]
                use = []
                if top["car"]:
                    use.append(f"{top['car']} of {O.its} red-zone carries"
                               + (f" ({top['i5']} inside the 5)" if top["i5"] else ""))
                if top["tgt"]:
                    use.append(f"{top['tgt']} red-zone targets")
                bits.append(f"{name} has {' and '.join(use)} — {top['share']:.0%} of {O.its} red-zone touches")
                out.append({"team": off, "player": name, "pos": (who or {}).get("pos") or "", "tone": "up",
                            "points_to": "a touchdown", "text": "; ".join(bits)})
    except Exception as exc:                                 # noqa: BLE001
        # A failure must never cost the report its other sections, and the
        # angles found before it stand. But [] is also what a game with
        # nothing to say returns, so the failure prints its own line in the
        # build's log, which no quiet game does (tests/test_silent_failures).
        print(f"  ⚠️ angles not read for {getattr(c, 'away', '?')}@{getattr(c, 'home', '?')} ({exc})")
        return out
    return out
