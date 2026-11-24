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


def raised(rows, team: str, outs: set) -> dict:
    """{player: {market: multiplier}}: the game's picks on ``team`` whose projection the teammate step raised for
    one of ``outs`` (their `mate_card`: applied above 1, naming one of them out)."""
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
    got.pop("", None)
    return got


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
        parts = []
        per = "" if len(without) == 1 else " a game"
        for pg, name, pos, before_pg, yds in cands[:NAMED]:
            bit = f"{name} ({pos}) {_num(pg)}{per}"
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
            lines.append((f"{name} steps up: more {kind} than his own average", claim))
    if not lines:
        return None
    lift = raised(rows, team, {_key(n) for n in named_out} | {_key(o[0]) for o in outs})
    for player, mk in sorted(lift.items()):
        bits = _join([f"{MARKET_WORDS[m]} ×{v:.2f}" for m, v in sorted(mk.items())])
        lines.append((f"Our numbers raise {player}'s {bits}, the lift measured over four seasons for a player whose "
                      f"teammate ahead of him at his position is out, in every number we price on him", None))
    if vacated.get("targets", 0.0) >= ROOM_SHARE:
        m, se, n = ROOM_TE["receptions"]
        lines.append((f"When a third or more of a team's targets sat, over four seasons a tight end caught "
                      f"{(m - 1) * 100:.0f}% more than his own form (± {se * 100:.0f}%, {n} games) and a back no "
                      f"more: said here, not in our numbers, since it fell just short of our bar", None))
    return {"lines": lines, "outs": named_out, "vacated": vacated}


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


def bet_record(conn, since: str | None = None) -> dict:
    """{sport: {book: {"raised": [won, lost, pushed, units], "lowered": [...], "open": n}}}: the settled picks
    a teammate's absence (or return) moved, by league and book, from the journal's `mate_mult` (stamped from
    25 November 2026 on; nothing before it is guessed). {} before any. Never raises."""
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
            way = "raised" if float(mult) > 1 else "lowered"
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
        if str(getattr(c, "sport", "") or "") != "nfl" or getattr(c, "conn", None) is None:
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
        return ([_h("Who steps up")] + blocks) if blocks else []
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ who steps up not read ({type(exc).__name__}: {exc})")
        return []
