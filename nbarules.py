"""Do the rotation's minutes rules hold on this box's own seasons? (read-only)

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbarules.py

engine/nba/minutes reads three things the board's number did not know
until 2026-11-04 (docs/NBA_LAB.md, "The scout"): HIS FIRST GAMES BACK play
light, by how many games he missed (and his second after two or more); a
ROLE THAT JUST JUMPED mostly holds; a REGULAR'S RETURN takes minutes back
from the men who covered for him. They were measured in the lab on two
full seasons of the league's public box scores, each rule fitted on one
season and judged on the other, and the values fitted on both are the
ones the board runs (`hoops.NBA`).

This asks the box's own stored seasons the same question, at the values
the board runs: every player-game a man of 15+ minutes a game played (5+
games for the club first), through the board's own projection
(`pipeline.project`, the league's fitted tuning, the vacancy at whatever
k the box has saved), the full model against the same model with one rule
taken out. Each side gets its own level factor, fitted on the whole
season, because the calibration downstream corrects the board's overall
level and a rule must not take credit for that.

THE BAR, written before the first box run: in every season with 100 or
more games a rule touches, the squared error of minutes AND of points in
those games is lower with the rule. HOLDS, or the seasons where it does
not. If one does not hold, ``QB_NBA_ROTATION=0`` in /etc/qellys/env turns
all three off at the next build (`engine/nba/minutes.rotation_on`), and
the result belongs in the lab's notes.

THE STARTING FIVE'S NEWS (engine/nba/starters, 2026-11-04) is replayed
beside them on the same rows — who started each game is in the logs, the
club's last five not in tonight's box stand for the injury report's news,
and a returning regular's last start says he started before he sat — and
judged by the same bar in its own column. Its verdict is filed apart
(engine/nba/switches ``starters``), so the two never switch each other.

Opened read-only. Changes nothing. Standard library only.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: The rows measured: a man of this many minutes a game over his last ten
#: for the club, with this many games for it first (the lab's).
PRICED_MIN = 15.0
PRIOR_GAMES = 5
#: The bar's floor: a season with fewer touched games is shown, not judged.
MIN_TOUCHED = 100
RULES = ("role jump", "first game back", "second game back", "a regular's return")
#: THE STARTING FIVE'S NEWS (engine/nba/starters, 2026-11-04) is judged the
#: same way and files its own verdict (engine/nba/switches ``starters``), so
#: a season where it stops paying cannot take the rotation's three with it.
FIVE = "the starting five"
#: A verdict with no season to judge, which files nothing.
NOT_JUDGED = "no season has enough games a rule touches to judge"


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _usual(past: list) -> float:
    last = past[-10:]
    return sum(s.get("min", 0.0) for _d, s in last) / len(last) if len(last) >= 3 else 0.0


def cases(clubs: dict, tune, k_vac: float = 0.0) -> list:
    """Every measured player-game: ``{season, min, pts, prop, touched}`` —
    the prop as the board would build it (his own return, a regular's
    return, the vacancy at ``k_vac``), ``touched`` the rules that read it."""
    from engine.nba.minutes import (RETURN_MISSED, RETURN_REGULAR_MIN, base_minutes,
                                    role_jump, role_minutes)
    from engine.nba.starters import read as _five_read
    five_coef = dict(getattr(tune, "starter_news", None) or {})
    out = []
    for (season, _team), games in sorted(clubs.items()):
        dates = sorted(games)
        hist: dict = {}
        last_five: set = set()
        for i, d in enumerate(dates):
            game = games[d]
            prior_dates = dates[:i]
            played = {n for n, s in game.items() if s.get("min", 0.0) > 0}
            recent = set(prior_dates[-3:])
            last2 = set(prior_dates[-RETURN_MISSED:])
            # A REGULAR'S RETURN: in tonight's box, gone from the club's last two.
            back = [(n, _usual(hist[n])) for n in played
                    if len(prior_dates) >= RETURN_MISSED and len(hist.get(n, [])) >= 3
                    and _usual(hist[n]) >= RETURN_REGULAR_MIN and not ({x for x, _s in hist[n]} & last2)]
            # A FRESH ABSENCE (nbavacancy's): a regular who played lately, not in the box.
            absent = sum(_usual(p) for n, p in hist.items()
                         if n not in played and _usual(p) >= 24.0 and {x for x, _s in p[-3:]} & recent)
            bases = {}
            for n in played:
                prior = list(reversed(hist.get(n, [])[-20:]))
                if len(prior) >= 3:
                    bases[n] = base_minutes(role_minutes([p.get("min", 0.0) for _d, p in prior])[0], tune) or 0.0
            total = sum(b for b in bases.values() if b > 0)
            from engine.nba.vacancy import weight
            claims = sum(weight(b) for b in bases.values())
            back_names = {n for n, _m in back}
            back_total = sum(m for _n, m in back)
            # THE STARTING FIVE'S NEWS: the club's last five not in tonight's
            # box (the injury report's news, as the box read it after), and
            # the returning regulars who started before they sat.
            five_gone = {n for n in last_five if n not in played}
            five_backs = {n for n, _m in back if hist.get(n) and hist[n][-1][1].get("starter")}
            for n in played:
                past = hist.get(n, [])
                prior = list(reversed(past[-20:]))
                if len(prior) < PRIOR_GAMES:
                    continue
                mins = [p.get("min", 0.0) for _d, p in prior]
                if sum(mins[:10]) / len(mins[:10]) < PRICED_MIN:
                    continue
                his = {x for x, _s in past}
                missed = 0
                for x in reversed(prior_dates):
                    if x in his:
                        break
                    missed += 1
                second = False
                if not missed:
                    run = 0
                    for x in reversed(prior_dates[:-1]):
                        if x in his:
                            break
                        run += 1
                    else:
                        run = 0
                    second = run >= RETURN_MISSED
                share = (bases.get(n, 0.0) / total) if total > 0 else 0.0
                # The vacancy shares by room (engine/nba/vacancy.weight); the
                # return runs it backwards by base minutes, as it was measured.
                claim = (weight(bases.get(n, 0.0)) / claims) if claims > 0 else 0.0
                ret = (tune.return_share * back_total * share) if back and n not in back_names else 0.0
                starts = [bool(p.get("starter")) for _d, p in prior]
                prop = {"player": n, "market": "pts", "minutes": mins,
                        "values": [p.get("pts", 0.0) for _d, p in prior],
                        "is_starter": bool(prior[0][1].get("starter")), "spread": 0.0,
                        "is_favorite": False, "rest": "1day", "player_mult": 1.0,
                        "vacancy_minutes": k_vac * absent * claim,
                        "missed_games": missed, "second_game_back": second, "return_minutes": ret,
                        "starts": starts, "five_out": len(five_gone - {n}),
                        "five_back": len(five_backs - {n})}
                base = base_minutes(role_minutes(mins)[0], tune)
                touched = set()
                if base is not None and role_jump(base, mins, tune) != base:
                    touched.add("role jump")
                if missed:
                    touched.add("first game back")
                elif second:
                    touched.add("second game back")
                if ret > 0:
                    touched.add("a regular's return")
                if five_coef and abs(sum(float(five_coef.get(k, 0.0) or 0.0) * v for k, v in
                                         _five_read(starts, prop["five_out"], prop["five_back"]).items())) > 1e-9:
                    touched.add(FIVE)
                out.append({"season": season, "min": game[n].get("min", 0.0), "pts": game[n].get("pts", 0.0),
                            "prop": prop, "touched": touched})
            for n, s in game.items():
                if s.get("min", 0.0) > 0:
                    hist.setdefault(n, []).append((d, s))
            last_five = {n for n in played if game[n].get("starter")}
    return out


def _without(rule: str, tune, prop: dict):
    if rule == "role jump":
        return replace(tune, role_jump_weight=0.0), prop
    if rule == "first game back":
        return replace(tune, back_mult=()), prop
    if rule == "second game back":
        return replace(tune, second_back_mult=1.0), prop
    if rule == FIVE:
        return replace(tune, starter_news={}), prop
    return tune, dict(prop, return_minutes=0.0)


def measure(rows: list, tune) -> dict:
    """``{season: {"n", rule: {"n", "minutes", "points"}}}`` — the share of
    squared error each rule takes off in the games it touches (positive =
    better with it), each side on its own season-wide level factor."""
    from engine.nba.pipeline import project
    preds: dict = {}
    for r in rows:
        full = project(r["prop"], tune)
        if "skip" in full:
            continue
        got = {"full": (float(full["proj_min"]), float(full["projection"]))}
        for rule in (*RULES, FIVE):
            t, p = _without(rule, tune, r["prop"])
            pj = project(p, t)
            got[rule] = (float(pj["proj_min"]), float(pj["projection"])) if "skip" not in pj else got["full"]
        preds[id(r)] = got
    out: dict = {}
    for season in sorted({r["season"] for r in rows}):
        rs = [r for r in rows if r["season"] == season and id(r) in preds]
        res = {"n": len(rs)}
        levels = {}
        for key in ("full", *RULES, FIVE):
            for j, stat in ((0, "min"), (1, "pts")):
                num = sum(r[stat] * preds[id(r)][key][j] for r in rs)
                den = sum(preds[id(r)][key][j] ** 2 for r in rs)
                levels[(key, j)] = num / den if den else 1.0
        for rule in (*RULES, FIVE):
            sub = [r for r in rs if rule in r["touched"]]
            cell = {"n": len(sub)}
            for j, stat, name in ((0, "min", "minutes"), (1, "pts", "points")):
                e1 = sum((r[stat] - levels[("full", j)] * preds[id(r)]["full"][j]) ** 2 for r in sub)
                e0 = sum((r[stat] - levels[(rule, j)] * preds[id(r)][rule][j]) ** 2 for r in sub)
                cell[name] = (1 - e1 / e0) if e0 else 0.0
            res[rule] = cell
        out[season] = res
    return out


def verdict(res: dict, rules: tuple = RULES) -> tuple[bool, list]:
    """``(holds, why not)`` for ``rules``: the rotation's three by default,
    ``(FIVE,)`` for the starting five's news."""
    why = []
    judged = 0
    for season, by in sorted(res.items()):
        for rule in rules:
            c = by.get(rule) or {}
            if c.get("n", 0) < MIN_TOUCHED:
                continue
            judged += 1
            if not (c["minutes"] > 0 and c["points"] > 0):
                why.append(f"{rule} in {season}: minutes {100 * c['minutes']:+.2f}%, points {100 * c['points']:+.2f}%")
    if not judged:
        return False, [NOT_JUDGED]
    return not why, why


def report(res: dict, k_vac: float) -> list:
    lines = ["NBA ROTATION RULES ON THIS BOX'S OWN SEASONS — the board's values, each rule taken out in turn",
             f"(every game a man of {PRICED_MIN:.0f}+ minutes a game played; the vacancy at k {k_vac:g}; "
             "squared error the rule takes off in the games it touches, each side on its own level)", ""]
    lines.append(f"{'season':<8}{'games':>8}  " + "".join(f"{r:>30}" for r in (*RULES, FIVE)))
    for season, by in sorted(res.items()):
        cells = []
        for rule in (*RULES, FIVE):
            c = by.get(rule) or {}
            cells.append(f"n {c.get('n', 0):5d} min {100 * c.get('minutes', 0):+5.1f}% pts {100 * c.get('points', 0):+5.1f}%"
                         if c.get("n") else "—")
        lines.append(f"{season!s:<8}{by['n']:>8}  " + "".join(f"{x:>30}" for x in cells))
    ok, why = verdict(res)
    lines += ["", f"THE BAR (every season with {MIN_TOUCHED}+ touched games: minutes AND points better with the rule): "
              + ("HOLDS — the board keeps all three." if ok else
                 "DOES NOT HOLD: " + "; ".join(why[:6])
                 + " — set QB_NBA_ROTATION=0 in /etc/qellys/env to turn the three off, and send this.")]
    ok5, why5 = verdict(res, (FIVE,))
    lines += [f"THE STARTING FIVE'S NEWS (engine/nba/starters), the same bar: "
              + ("HOLDS — the board keeps it." if ok5 else
                 "NOT JUDGED: no season has enough games it touches — its switch stays as it is."
                 if why5 == [NOT_JUDGED] else
                 "DOES NOT HOLD: " + "; ".join(why5[:6])
                 + " — the weekly refit's run turns it off; QB_NBA_STARTERS=0 in /etc/qellys/env does it by hand.")]
    lines.append("Read-only: nothing was changed.")
    return lines


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    sport = "nba"
    # Measured with the rules on, whatever the board's switch says: this is
    # the run that decides the switch.
    import os
    os.environ["QB_NBA_ROTATION"] = "1"
    os.environ["QB_NBA_STARTERS"] = "1"
    from engine import db
    import nbavacancy
    conn = _ro(db.DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    try:
        clubs = nbavacancy.load(conn, sport)
        try:
            from engine.hoops_fit import fitted_tuning
            tune, _rep = fitted_tuning(conn, sport)
        except Exception:                                   # noqa: BLE001
            from engine.hoops import NBA as tune
    finally:
        conn.close()
    if not clubs:
        print("No NBA logs stored.")
        return 0
    from engine.nba.vacancy import k_for
    k_vac = k_for(sport)
    from engine import playerfit
    keep = playerfit.mult_for
    playerfit.mult_for = lambda *a, **k: 1.0
    try:
        res = measure(cases(clubs, tune, k_vac), tune)
    finally:
        playerfit.mult_for = keep
    for line in report(res, k_vac):
        if "--save" in argv and line.startswith("Read-only"):
            continue                                  # it files a verdict below
        print(line)
    if "--save" in argv:
        # The weekly deep refit runs it this way: the rules follow the box's
        # own seasons at once (engine/nba/switches), on or off. A season too
        # thin to judge leaves the switch as it was.
        from engine.nba import switches
        for name, rules in (("rotation", RULES), ("starters", (FIVE,))):
            ok, why = verdict(res, rules)
            if why == [NOT_JUDGED]:
                print(f"{name} verdict not filed: no season has enough games a rule touches")
            else:
                print(f"{name} verdict filed: {switches.record_check(name, ok, '; '.join(why[:6]) or 'holds in every season judged', follow=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
