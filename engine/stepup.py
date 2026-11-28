"""WHO STEPS UP: when a team's receivers or backs are ruled out, where their work goes (step AEC, 24 November 2026).

Ethan, 24 November: "the LA Rams receiver room is basically empty. Puka and Adams is out so now it's all their
other receivers and tight ends too step up so we need too gather data on who steps up in these situations on teams
... make sure it's in the bets and reports and measured with bets".

WHAT THE NUMBERS ALREADY DO (engine/teammates, measured on 2022-2025 and held out by season): a receiver, tight end
or back whose teammate ranked ahead of him at his position is ruled out is projected up, by the lift measured for
that case (a receiver's catches ×1.19 the first game the man ahead of him misses, ×1.10 after; a tight end's ×1.57;
a back's rushing ×1.66), and that moves the Most Likely and Edge picks on him. The game report never said it in one
place: its injury section named who was out and "a 31% share of LA's targets goes to other players", never to whom.

WHAT THIS ADDS, in the report's injury section, for each team with a receiver, tight end or back out who carried a
real share of the work (`TARGET_SHARE` of the targets or `CARRY_SHARE` of the carries this season):
  * who is out and what share of the targets (or carries) they took this season;
  * who took the work in this season's games without them, off the team's own box scores: each teammate's targets
    a game then, beside his targets a game with them playing;
  * which of the game's picks our numbers raise for it, and by how much (the props' `mate_card`);
  * each teammate named as stepping up, as a read the report grades after the game: his targets (carries, for a
    back) against his own average (engine/reportgrade, group "stepup"), so the Record says how often these reads
    are right.

MEASURED THE SAME DAY (2022-2025 snap counts and box scores, week 4 on, the projection's own form as the
expectation, scratch `roomfit.py`), the cases the numbers do NOT change, and why:
  * two ranked ahead of a top-three receiver out, against one: catches ×1.31 ± .23 (n 24) against ×1.18, yards
    ×1.58 ± .36 (n 23): larger, and too thin and too uneven by season (one of four the other way) to apply;
  * the fourth and fifth receivers, outside the depth order the lift is measured on: once the men ahead of them
    sit they produce about what their own form says (×0.96 to ×1.17), because their recent games as the fill-in
    already carry the role; a lift fitted on three seasons cut no error on the fourth, so none is added;
  * a tight end when a third or more of the team's targets sat at other positions: catches ×1.12 ± .07 (n 155),
    three seasons of four up, just short of the two-standard-error bar: said in the report (ROOM_TE), not priced;
  * a back when receivers sit: nothing (×0.89 to ×1.05), as matefit found in September.

Standard library only; every function here never raises into the report.
"""
from __future__ import annotations

#: An absence worth a line: this share of the team's targets (any receiver, tight end or back) or of its carries.
TARGET_SHARE, CARRY_SHARE = 0.10, 0.25
#: Teammates named as stepping up, a line.
NAMED = 3
#: The fewest targets (carries) a game a teammate needs in the games without them to be named.
MIN_PER_GAME = 2.0
#: A third or more of the targets out: the tight end's measured, unpriced lift is said (see the docstring).
ROOM_SHARE = 0.30
ROOM_TE = {"receptions": (1.120, 0.067, 155), "rec_yds": (1.122, 0.070, 156)}
#: The positions whose work each kind is (who may be named taking it), and whose absence leaves it: a back out
#: leaves his carries (his catches go with them, and the lift measured for his backup is on the ground).
KIND_POS = {"targets": ("WR", "TE", "RB", "FB"), "carries": ("RB", "FB")}
OUT_POS = {"targets": ("WR", "TE"), "carries": ("RB", "FB")}
#: The markets a raised projection is said in, and their words.
MARKET_WORDS = {"receptions": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards",
                "rush_att": "carries", "targets": "targets", "anytime_td": "touchdown chance"}
#: The report's grade group for these reads (engine/reportgrade.GROUPS).
GROUP = "stepup"
#: An absence is said while the man played in one of the team's last this-many games, whatever list he is on (the
#: week's report, injured reserve, the reserve list): the work he left is still being handed out. One gone longer
#: is in his teammates' own form already. Puka Nacua and Davante Adams went on injured reserve on 22 November.
RECENT_GAMES = 3


def _key(name) -> str:
    try:
        from .teammates import _norm
        return _norm(str(name or ""))
    except Exception:                                        # noqa: BLE001
        return "".join(ch for ch in str(name or "").lower() if ch.isalnum() or ch == " ").strip()


def usage_by_week(conn, season: int, team: str, before: int | None = None) -> dict:
    """{week: {player: {"pos", "targets", "carries", "rec_yds", "rush_yds"}}}: one team's regular-season weeks this
    season before ``before`` (every week when None), off the history's game logs. {} when there are none."""
    if conn is None or not team:
        return {}
    # By the table's own key (sport, season, period, game_id): the team's game ids, the weekly file's and the
    # same-night box score's (engine/boxsettle.BOX_SUFFIX), so the read is a lookup, never a walk of the market.
    last = min(18, int(before) - 1) if before is not None else 18
    periods = [f"{w:03d}" for w in range(1, last + 1)]
    if not periods:
        return {}
    ids = [f"{team}-{p}{tail}" for p in periods for tail in ("", "-box")]
    try:
        rows = conn.execute(
            f"SELECT period, player, position, market, value FROM player_game_logs WHERE sport='nfl' AND season=? "
            f"AND period IN ({','.join('?' * len(periods))}) AND game_id IN ({','.join('?' * len(ids))}) "
            f"AND team=? AND market IN ('targets','carries','rec_yds','rush_yds')",
            (int(season), *periods, *ids, team)).fetchall()
    except Exception:                                        # noqa: BLE001
        return {}
    out: dict = {}
    for period, player, pos, market, value in rows:
        try:
            wk = int(str(period))
        except (TypeError, ValueError):
            continue
        if wk <= 0 or wk > 18 or (before is not None and wk >= int(before)) or not player:
            continue
        d = out.setdefault(wk, {}).setdefault(player, {"pos": "", "targets": 0.0, "carries": 0.0,
                                                       "rec_yds": 0.0, "rush_yds": 0.0})
        if pos:
            d["pos"] = str(pos).upper()
        try:
            d[market] = float(value or 0.0)
        except (TypeError, ValueError):
            pass
    return out


def shares(weeks: dict, kind: str) -> dict:
    """{player: (his share of the team's ``kind`` over the weeks he played, games)}."""
    team = {w: sum(p.get(kind) or 0.0 for p in ps.values()) for w, ps in weeks.items()}
    got: dict = {}
    for w, ps in weeks.items():
        for name, p in ps.items():
            g = got.setdefault(name, [0.0, 0.0, 0])
            g[0] += p.get(kind) or 0.0
            g[1] += team[w]
            g[2] += 1
    return {n: (v[0] / v[1], v[2]) for n, v in got.items() if v[1] > 0}


def _per_game(weeks: dict, wks: list, name: str, kind: str) -> float | None:
    """His ``kind`` a game over the weeks he played among ``wks``; None when he played none of them."""
    vals = [weeks[w][name].get(kind) or 0.0 for w in wks if name in weeks.get(w, {})]
    return sum(vals) / len(vals) if vals else None


def _join(xs: list) -> str:
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else f"{', '.join(xs[:-1])} and {xs[-1]}" if xs else ""


def _num(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _weeks_words(wks: list) -> str:
    wks = sorted(wks)
    return f"week {wks[0]}" if len(wks) == 1 else f"weeks {_join([str(w) for w in wks])}"


def raised(rows, team: str, outs: set, kinds: dict | None = None) -> dict:
    """{player: {market: multiplier}}: the game's picks on ``team`` whose projection the teammate step raised for
    one of ``outs`` (their `mate_card`: applied above 1, naming one of them out). ``kinds``, when given, is filled
    {player: {market: "mate" | "room" | "both"}}: which measured lift moved it (engine/teammates, engine/room)."""
    got: dict = {}
    for r in rows or []:
        if not isinstance(r, dict) or str(r.get("team") or "") != team:
            continue
        c = r.get("mate_card") or {}
        try:
            mult = float(c.get("applied") or 1.0)
        except (TypeError, ValueError):
            continue
        if mult <= 1.0 + 1e-9 or not ({_key(o) for o in c.get("out") or []} & outs):
            continue
        m = str(r.get("market") or "")
        if m in MARKET_WORDS:
            got.setdefault(str(r.get("player") or ""), {})[m] = round(mult, 2)
            if kinds is not None:
                rm = float(((c.get("room") or {}).get("applied")) or 1.0)
                kind = ("room" if abs(rm - mult) < 1e-6 else "both") if rm > 1.0 + 1e-9 else "mate"
                kinds.setdefault(str(r.get("player") or ""), {})[m] = kind
    got.pop("", None)
    return got


#: How each lift is said beside a raised number.
#: IN A MEMBER'S WORDS (step AHY, 26 November 2026): these said "(engine/room)", a file name, and "×1.42" where a
#: reader says "by 42%".
LIFT_WORDS = {
    "mate": "the lift we measured over four seasons when a teammate ranked higher at the same position is out",
    "room": ("the lift we measured over ten seasons (2016-2025) for the receivers left beyond a team's top three "
             "when a fifth or more of its targets sit"),
}


def by_words(v) -> str:
    """A lift as a reader says it: 1.42 is "by 42%"."""
    return f"by {abs(float(v) - 1):.0%}"


def lift_bits(mk: dict) -> str:
    """"receiving yards by 42% and catches by 32%"."""
    return _join([f"{MARKET_WORDS.get(m, m)} {by_words(v)}" for m, v in sorted(mk.items())])


def _lift_line(player: str, mk: dict, kinds: dict) -> str:
    seen = {k for k in kinds.values()}
    why = [LIFT_WORDS[k] for k in ("mate", "room") if k in seen or "both" in seen]
    return f"Our numbers raise {player}'s {lift_bits(mk)}, {' and '.join(why)}"


def for_team(conn, season: int, week: int | None, team: str, team_name: str, outs: list, rows=None,
             reserve=()) -> dict | None:
    """The team's "who steps up": {"lines": [(text, claim or None)], "outs": [...], "vacated": {kind: share}}, or
    None when nobody out carried a real share of the work. ``outs`` is [(player, position, status)] ruled out;
    ``reserve`` the same for the team's reserve list; each is counted only while fresh (RECENT_GAMES)."""
    weeks = usage_by_week(conn, season, team, week)
    if not weeks or not (outs or reserve):
        return None
    recent = {_key(n) for w in sorted(weeks)[-RECENT_GAMES:] for n in weeks[w]}
    fresh, seen = [], set()
    for r in list(outs or []) + list(reserve or ()):
        k = _key(r[0])
        if k in recent and k not in seen:
            seen.add(k)
            fresh.append(r)
    outs = fresh
    if not outs:
        return None
    by_key: dict = {}
    for ps in weeks.values():
        for name in ps:
            by_key.setdefault(_key(name), name)
    lines: list = []
    vacated: dict = {}
    named_out: list = []
    found: list = []
    absent = {by_key[_key(o[0])] for o in outs if _key(o[0]) in by_key}
    for kind, bar in (("targets", TARGET_SHARE), ("carries", CARRY_SHARE)):
        sh = shares(weeks, kind)
        out_here = []
        for player, pos, status in outs:
            if str(pos or "").upper() not in OUT_POS[kind]:
                continue
            name = by_key.get(_key(player))
            if name and sh.get(name, (0.0, 0))[0] >= bar:
                out_here.append((name, str(pos or "").upper(), sh[name][0], str(status or "out").lower()))
        if not out_here:
            continue
        out_here.sort(key=lambda x: -x[2])
        total = min(1.0, sum(x[2] for x in out_here))
        vacated[kind] = round(total, 3)
        named_out += [x[0] for x in out_here if x[0] not in named_out]
        who = _join([f"{n} ({p}, {s:.0%} of the {kind})" for n, p, s, _st in out_here])
        lines.append((f"{team_name} without {who}: {total:.0%} of the {kind} this season to fill", None))
        names = {x[0] for x in out_here}
        all_weeks = sorted(weeks)
        without = [w for w in all_weeks if not any(n in weeks[w] for n in names)]
        withall = [w for w in all_weeks if all(n in weeks[w] for n in names)]
        them = "them" if len(names) > 1 else "that player"
        if not without and len(names) > 1:
            # NEVER OUT TOGETHER: the games without the one who carried the most of the work and missed any, the
            # others playing; "they have not missed a game" only when none of them has.
            for nm, _pos, _sh, _st in out_here:
                wo = [w for w in all_weeks if nm not in weeks[w]]
                if wo:
                    without, withall, them = wo, [w for w in all_weeks if nm in weeks[w]], nm
                    break
        if not without:
            lines.append((f"{'They have' if len(names) > 1 else 'That player has'} not missed a game this "
                          f"season, so there is no game of this team's own to read it from yet", None))
            continue
        cands = []
        for name in {n for w in without for n in weeks[w]} - absent:
            pos = next((weeks[w][name].get("pos") for w in without if name in weeks[w]), "")
            if pos not in KIND_POS[kind] or _key(name) not in recent:
                continue                          # another position's work, or not with the team lately
            pg = _per_game(weeks, without, name, kind)
            if pg is None or pg < MIN_PER_GAME:
                continue
            cands.append((pg, name, pos, _per_game(weeks, withall, name, kind),
                          _per_game(weeks, without, name, "rec_yds" if kind == "targets" else "rush_yds")))
        cands.sort(key=lambda x: (-x[0], x[1]))
        if not cands:
            continue
        found.append({"kind": kind, "out": [(n, p, round(sh, 3)) for n, p, sh, _st in out_here],
                      "vacated": round(total, 3), "weeks": sorted(without), "them": them,
                      "games": len(without), "when": _weeks_words(without),
                      "named": [{"player": name, "pos": pos, "per_game": round(pg, 1),
                                 "with": None if before_pg is None else round(before_pg, 1),
                                 "yards": round(yds, 1) if yds else None}
                                for pg, name, pos, before_pg, yds in cands[:NAMED]]})
        parts = []
        per = "" if len(without) == 1 else " a game"
        for pg, name, pos, before_pg, yds in cands[:NAMED]:
            # The count says what it counts (step AHY): "Tutu Atwell (WR) 9" was 9 targets.
            bit = f"{name} ({pos}) {_num(pg)} {kind}{per}"
            if before_pg is not None:
                bit += f" ({_num(before_pg)} a game with {them})"
            if yds:
                bit += f", {_num(yds)} yards{per}"
            parts.append(bit)
        games = "the only game" if len(without) == 1 else f"the {len(without)} games"
        lines.append((f"In {games} this season without {them} ({_weeks_words(without)}), the {kind} went to: "
                      + "; ".join(parts), None))
        # A STEP UP IS CLAIMED ONLY WHERE ONE WAS MEASURED: the out man's own position (engine/teammates), and a
        # tight end once a third of the targets are gone (ROOM_TE). A back named for targets when receivers sit is
        # said, never claimed: over four seasons backs got no more then.
        claim_pos = {x[1] for x in out_here} | ({"TE"} if kind == "targets" and total >= ROOM_SHARE else set())
        for pg, name, pos, before_pg, _yds in cands[:NAMED]:
            if pos not in claim_pos or (before_pg is not None and pg <= before_pg):
                continue                          # unmeasured, or no step up to read: he had as much with them
            claim = {"kind": "player", "player": name, "team": team, "pos": pos,
                     "stat": "targets" if kind == "targets" else "carries", "favors": "more", "group": GROUP}
            lines.append((f"{name} steps up: more {kind} than usual", claim))
    if not lines:
        return None
    kinds: dict = {}
    lift = raised(rows, team, {_key(n) for n in named_out} | {_key(o[0]) for o in outs}, kinds)
    for player, mk in sorted(lift.items()):
        lines.append((_lift_line(player, mk, kinds.get(player) or {}), None))
    if vacated.get("targets", 0.0) >= ROOM_SHARE:
        m, se, n = ROOM_TE["receptions"]
        lines.append((f"When a third or more of a team's targets sat, over four seasons a tight end caught "
                      f"{(m - 1) * 100:.0f}% more than usual (± {se * 100:.0f}%, {n} games) and a back no "
                      f"more: said here, not in our numbers, since it fell just short of our bar", None))
    return {"lines": lines, "outs": named_out, "vacated": vacated, "found": found, "lift": lift, "kinds": kinds}


# --- college football (step AEK) -----------------------------------------------------------------------------------
#: WHO STEPS UP, FOR COLLEGE (step AEK, 24 November 2026; rivalry week). College's props already take a measured
#: teammate-out step (engine/cfb/lineup, since 10 October: its own multipliers, fitted on college games, applied only
#: where they pass the NFL's rule), and its report never said it. College box scores log catches, not targets, and
#: no positions, so the block says what the logs hold and claims no graded read: who is out and his share of the
#: team's catches or carries; in this season's games where he has no catch or carry on record, who took them (each
#: man's per game then, beside his per game with him); and which picks our numbers raise for it. The season's games
#: are the lineup step's own read (engine/cfb/lineup.season_games), handed over on the board's working key below.
#: (kind, the box column, positions whose absence leaves it, positions that take it, the share that is worth a line,
#: the yards said beside it)
CFB_KINDS = (("catches", "receptions", ("WR", "TE"), ("WR", "TE", "RB"), TARGET_SHARE, "rec_yds"),
             ("carries", "rush_att", ("RB",), ("RB",), CARRY_SHARE, "rush_yds"))
#: The board's working key (dropped before the board is written, engine/gate) the college build leaves the lineup
#: step's season read under: {"players": {team: {name: {"role", "games"}}}, "team_days": {team: [day]}}.
CFB_GAMES_KEY = "_cfb_lineup_games"


def _cfb_value(g: dict, market: str) -> float:
    """One college game's column (a back's carries filed as either name)."""
    g = g or {}
    v = g.get(market)
    if v is None and market == "rush_att":
        v = g.get("carries")
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _days_words(days: list, season=None) -> str:
    from .gamereport import day_label
    labels = [day_label(d, season or str(d)[:4], season or str(d)[:4]) for d in sorted(days)]
    return _join(labels)


def for_cfb_team(players: dict, days: list, team: str, team_name: str, outs: list, rows=None, before: str = "",
                 positions: dict | None = None, season=None) -> dict | None:
    """College's "who steps up" for one team (CFB_KINDS): {"lines": [(text, None)], "outs": [...], "vacated":
    {kind: share}}, or None. ``players`` is the team's {name: {"role", "games": {day: {market: value}}}} and ``days``
    its logged days (engine/cfb/lineup.season_games); ``outs`` [(player, position, status)] ruled out, each counted
    while he played in one of the team's last RECENT_GAMES; ``positions`` {name key: position} the report's own reads
    say (the roster's, where the logs' guess can call a tight end a receiver)."""
    prior = [d for d in sorted(days or []) if not before or d < str(before)[:10]]
    if not prior or not outs or not players:
        return None
    pos_of = {k: str(v or "").upper() for k, v in (positions or {}).items() if v}

    def role(name):
        return pos_of.get(_key(name)) or str((players.get(name) or {}).get("role") or "").upper()
    recent_days = set(prior[-RECENT_GAMES:])
    recent = {_key(n) for n, p in players.items() if set((p or {}).get("games") or {}) & recent_days}
    by_key = {_key(n): n for n in players}
    fresh, seen = [], set()
    for r in outs:
        k = _key(r[0])
        if k in recent and k in by_key and k not in seen:
            seen.add(k)
            fresh.append((by_key[k], str(r[1] or "").upper(), r[2]))
    if not fresh:
        return None
    games = {n: (p or {}).get("games") or {} for n, p in players.items()}
    absent = {n for n, _p, _s in fresh}
    lines: list = []
    vacated: dict = {}
    named_out: list = []
    found: list = []
    for kind, market, out_pos, take_pos, bar, yds in CFB_KINDS:
        team_total = {d: sum(_cfb_value(g.get(d), market) for g in games.values()) for d in prior}

        def share(name, market=market, team_total=team_total):
            mine = sum(_cfb_value(games[name].get(d), market) for d in prior if d in games[name])
            tot = sum(team_total[d] for d in prior if d in games[name])
            return mine / tot if tot else 0.0
        out_here = []
        for name, pos, status in fresh:
            p = pos if pos in out_pos else role(name)
            if p not in out_pos:
                continue
            sh = share(name)
            if sh >= bar:
                out_here.append((name, p, sh, str(status or "out").lower()))
        if not out_here:
            continue
        out_here.sort(key=lambda x: -x[2])
        total = min(1.0, sum(x[2] for x in out_here))
        vacated[kind] = round(total, 3)
        named_out += [x[0] for x in out_here if x[0] not in named_out]
        who = _join([f"{n} ({p}, {sh:.0%} of the {kind})" for n, p, sh, _st in out_here])
        lines.append((f"{team_name} without {who}: {total:.0%} of the {kind} this season to fill", None))
        names = {x[0] for x in out_here}
        without = [d for d in prior if not any(d in games[n] for n in names)]
        withall = [d for d in prior if all(d in games[n] for n in names)]
        them = "them" if len(names) > 1 else "that player"
        if not without and len(names) > 1:
            for nm, _pos, _sh, _st in out_here:
                wo = [d for d in prior if d not in games[nm]]
                if wo:
                    without, withall, them = wo, [d for d in prior if d in games[nm]], nm
                    break
        if not without:
            lines.append((f"{'They have' if len(names) > 1 else 'That player has'} a catch or carry on record in "
                          f"every game this season, so there is no game of this team's own to read it from yet", None))
            continue
        cands = []
        for name in games:
            if name in absent or _key(name) not in recent or role(name) not in take_pos:
                continue
            played = [d for d in without if d in games[name]]
            if not played:
                continue
            pg = sum(_cfb_value(games[name][d], market) for d in played) / len(played)
            if pg < MIN_PER_GAME:
                continue
            w = [d for d in withall if d in games[name]]
            before_pg = sum(_cfb_value(games[name][d], market) for d in w) / len(w) if w else None
            ypg = sum(_cfb_value(games[name][d], yds) for d in played) / len(played)
            cands.append((pg, name, role(name), before_pg, ypg))
        cands.sort(key=lambda x: (-x[0], x[1]))
        if not cands:
            continue
        found.append({"kind": kind, "out": [(n, p, round(sh, 3)) for n, p, sh, _st in out_here],
                      "vacated": round(total, 3), "weeks": [], "them": them, "games": len(without),
                      "when": _days_words(without, season),
                      "named": [{"player": name, "pos": pos, "per_game": round(pg, 1),
                                 "with": None if before_pg is None else round(before_pg, 1),
                                 "yards": round(ypg, 1) if ypg else None}
                                for pg, name, pos, before_pg, ypg in cands[:NAMED]]})
        per = "" if len(without) == 1 else " a game"
        parts = []
        for pg, name, pos, before_pg, ypg in cands[:NAMED]:
            bit = f"{name} ({pos}) {_num(pg)} {kind}{per}"
            if before_pg is not None:
                bit += f" ({_num(before_pg)} a game with {them})"
            if ypg:
                bit += f", {_num(ypg)} yards{per}"
            parts.append(bit)
        n_words = "the only game" if len(without) == 1 else f"the {len(without)} games"
        had = "they had" if them == "them" else f"{them} had"
        lines.append((f"In {n_words} this season {had} no catch or carry on record ({_days_words(without, season)}), "
                      f"the {kind} went to: " + "; ".join(parts), None))
    if not lines:
        return None
    lift = raised(rows, team, {_key(n) for n in named_out} | {_key(o[0]) for o in outs})
    for player, mk in sorted(lift.items()):
        lines.append((f"Our numbers raise {player}'s {lift_bits(mk)}, the lift we measured on college games when a "
                      f"teammate ranked higher at the same position is out", None))
    return {"lines": lines, "outs": named_out, "vacated": vacated, "found": found, "lift": lift}


# --- the bets a teammate's absence moved, on the record ------------------------------------------------------------
#: The books a moved pick is counted in, each as its page names it (ledger: Edge's, Most Likely's, the reports').
BET_BOOKS = {"edge": ("main", "paper", "edge_held"), "likely": ("likely", "likely_live"), "report": ("report",)}
#: The multiplier a journal row keeps (ledger `bets.mate_mult`) lies in this range; anything else is no step.
MULT_RANGE = (0.2, 5.0)


def mate_mult(row) -> float | None:
    """The teammate step a priced row carries (its `mate_card`, engine/teammates), when it moved the row: the
    applied multiplier, else None. A report bet keeps it as ``mate_mult`` (engine/reportbets)."""
    try:
        get = row.get
    except AttributeError:
        return None
    raw = get("mate_mult")
    if raw is None:
        card = get("mate_card")
        if not isinstance(card, dict) or not card.get("case"):
            return None
        raw = card.get("applied")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if not MULT_RANGE[0] <= v <= MULT_RANGE[1] or abs(v - 1.0) < 1e-6:
        return None
    return round(v, 3)


def room_lifted(sport, mult) -> bool:
    """Is a journaled multiplier the room's own (engine/room.ROOM, step AHW)? The journal keeps the multiplier, not
    which step made it; the room's four NFL values are none of the NFL teammate step's (engine/teammates.EFFECT,
    EFFECT_SNAPS), so the value says it. A pick both steps moved carries their product and counts as raised."""
    if str(sport or "") != "nfl":
        return False
    try:
        from .room import ROOM
        v = float(mult)
    except Exception:                                        # noqa: BLE001
        return False
    return any(abs(v - x) < 0.0015 for x in set(ROOM.values()))


def bet_record(conn, since: str | None = None) -> dict:
    """{sport: {book: {"raised": [won, lost, pushed, units], "lowered": [...], "room": [...], "open": n}}}: the
    settled picks a teammate's absence (or return) moved, by league and book, from the journal's `mate_mult`
    (stamped from 25 November 2026 on; nothing before it is guessed), the room's own lift apart (`room_lifted`,
    from 26 November). {} before any. Never raises."""
    out: dict = {}
    try:
        cats = [c for cs in BET_BOOKS.values() for c in cs]
        q = (f"SELECT sport, category, mate_mult, status, pnl_units FROM bets WHERE mate_mult IS NOT NULL "
             f"AND category IN ({','.join('?' * len(cats))})" + (" AND date >= ?" if since else ""))
        rows = conn.execute(q, (*cats, *([since] if since else []))).fetchall()
    except Exception:                                        # noqa: BLE001
        return {}
    book_of = {c: b for b, cs in BET_BOOKS.items() for c in cs}
    for sport, cat, mult, status, units in rows:
        b = out.setdefault(str(sport), {}).setdefault(book_of.get(cat, "edge"), {})
        if status in ("won", "lost", "push"):
            way = ("room" if room_lifted(sport, mult) else "raised") if float(mult) > 1 else "lowered"
            x = b.setdefault(way, [0, 0, 0, 0.0])
            x[("won", "lost", "push").index(status)] += 1
            x[3] = round(x[3] + float(units or 0.0), 3)
        elif status == "open":
            b["open"] = b.get("open", 0) + 1
    return out


#: The board's key for this build's count (launch._board_counts puts it on the heartbeat).
CENSUS_KEY = "stepup"


def census(reports, result=None) -> dict:
    """{"teams": reports' teams with a "Who steps up" block, "reads": its step-up reads claimed for grading,
    "moved": board rows a teammate step moved}: counts only, {} when all are none."""
    teams = reads = 0
    for rep in reports or []:
        for sec in (rep or {}).get("sections") or [] if isinstance(rep, dict) else []:
            if not isinstance(sec, dict) or sec.get("key") != "injuries":
                continue
            on = False
            for b in sec.get("blocks") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "h":
                    on = b.get("text") == "Who steps up"
                elif on and b.get("type") == "list":
                    teams += 1
                    reads += sum(1 for cl in b.get("claims") or [] if isinstance(cl, dict) and cl.get("group") == GROUP)
    moved = sum(1 for k in ("recommendations", "most_likely") for r in (result or {}).get(k) or []
                if isinstance(r, dict) and mate_mult(r) is not None)
    got = {"teams": teams, "reads": reads, "moved": moved}
    return got if any(got.values()) else {}


def report_blocks(c) -> list:
    """The report's injury-section blocks: a "Who steps up" heading and each team's lines, its step-up reads
    claimed for grading (NFL; never raises: [] on anything it cannot read)."""
    try:
        sport = str(getattr(c, "sport", "") or "")
        if sport == "cfb":
            return _cfb_blocks(c)
        if sport != "nfl" or getattr(c, "conn", None) is None:
            return []
        from .gamescan import OUT_STATUSES
        from .gamereport import _claimed_list, _h, _week_of
        rows = [r for k in ("recommendations", "most_likely") for r in (c.result or {}).get(k) or []
                if isinstance(r, dict)]
        week = _week_of(c.result)
        blocks: list = []
        for t in c.teams:
            outs = [(r.get("player"), r.get("position"), r.get("status"))
                    for r in (c.scan or {}).get("injuries") or [] if isinstance(r, dict) and r.get("team") == t
                    and str(r.get("status") or "").upper() in OUT_STATUSES and not r.get("cleared")]
            reserve = [(r.get("player"), r.get("position"), r.get("status"))
                       for r in ((c.scan or {}).get("reserve") or {}).get(t) or [] if isinstance(r, dict)]
            got = for_team(c.conn, c.season, week, t, c.name(t), outs, rows, reserve)
            if got:
                blocks.append(_claimed_list(got["lines"]))
                # What the short version says from it (gamereport.stepup_sentence, step AHW).
                found = getattr(c, "stepup", None)
                if not isinstance(found, dict):
                    found = {}
                    setattr(c, "stepup", found)
                found[t] = got
        return ([_h("Who steps up")] + blocks) if blocks else []
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ who steps up not read ({type(exc).__name__}: {exc})")
        return []


def _cfb_blocks(c) -> list:
    """College's "Who steps up" blocks (`for_cfb_team`), off the lineup step's season read the build left on the
    board (CFB_GAMES_KEY); [] without it. Raises into `report_blocks`, which says so in the build log."""
    from .gamescan import OUT_STATUSES
    from .gamereport import _claimed_list, _h
    held = (c.result or {}).get(CFB_GAMES_KEY) or {}
    players, team_days = held.get("players") or {}, held.get("team_days") or {}
    if not players:
        return []
    rows = [r for k in ("recommendations", "most_likely") for r in (c.result or {}).get(k) or [] if isinstance(r, dict)]
    positions = {_key(r.get("player")): r.get("pos") for r in getattr(c, "reads", None) or []
                 if isinstance(r, dict) and r.get("player") and r.get("pos")}
    blocks: list = []
    for t in c.teams:
        outs = [(r.get("player"), r.get("position"), r.get("status"))
                for r in (c.scan or {}).get("injuries") or [] if isinstance(r, dict) and r.get("team") == t
                and str(r.get("status") or "").upper() in OUT_STATUSES and not r.get("cleared")]
        got = for_cfb_team(players.get(t) or {}, team_days.get(t) or [], t, c.name(t), outs, rows,
                           before=str((getattr(c, "g", None) or {}).get("date") or ""), positions=positions,
                           season=getattr(c, "season", None))
        if got:
            blocks.append(_claimed_list(got["lines"]))
            found = getattr(c, "stepup", None)
            if not isinstance(found, dict):
                found = {}
                setattr(c, "stepup", found)
            found[t] = got
    return ([_h("Who steps up")] + blocks) if blocks else []
