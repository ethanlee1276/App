"""Does a receiver who beats man coverage score more against a red-zone
man defence? Measured on top of the touchdown model before it moves anything.

    sudo -u qellys nice -n 19 python3 -m engine.tdmanfit
    sudo -u qellys nice -n 19 python3 -m engine.tdmanfit --dry-run

Ethan, 2026-10-04, with the Bengals @ Jaguars touchdown scan: "Jacksonville
plays roughly 65% man coverage in the red zone, second-most in the NFL, and
Higgins currently has the highest receiving grade against man coverage …
Jags use man in the red zone → Chase draws the most attention → Higgins
gets isolated." The yardage half of this idea was measured on 2026-09-24
(engine/scanfit `zone_fit`: a receiver's yards per target vs zone over vs
man, times the defence's zone rate) and was flat, t 0.1. This is the half
the scan actually bets: TOUCHDOWNS, against the defence's coverage INSIDE
ITS OWN 20.

WHAT IS MEASURED. Every WR and TE player-week the touchdown replay grades
(engine/tdbacktest), 2022 on. Two numbers, both from games before it:

  his man edge      (yards per target vs man − vs zone) ÷ his yards per
                    target, LAST season, where he drew MAN_MIN_TGTS man and
                    ZONE_MIN_TGTS zone targets (scanfit's split, sign
                    turned so positive = better against man);
  their RZ man rate the share of the opponent's coverage-labelled dropbacks
                    inside its own 20 played in man, this season before the
                    week, leaning on last season's rate until PRIOR_PLAYS
                    such dropbacks, minus the league's rate.

x = his man edge × their red-zone man rate over the league's. Positive is
the scan's case: good against man, facing a red-zone man defence.

THE BAR, WRITTEN BEFORE ANY BOX RUN (engine/tdinjfit's): on top of the
model's own logit, leave one season out; held-out log loss better pooled
AND in all but one season; b positive with a cluster-robust t of at least
MIN_T (clusters = the opponent's game); at least MIN_ROWS player-weeks with
x measured. Nothing here moves a number. A proven result earns a "history
says" line on the touchdown card first.

Standard library only. Reads the history database, nflverse play-by-play
and participation (cached the way engine/scanfit reads them).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate

SEASONS = (2022, 2023, 2024, 2025)
MAN_MIN_TGTS, ZONE_MIN_TGTS = 10, 20
PRIOR_PLAYS = 30.0
RZ_YARDS = 20
MIN_ROWS = 1500
MIN_T = 2.0
POSITIONS = ("WR", "TE")
STORE_VERSION = 1
_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def _store() -> Path:
    return Path(modelstate.path("td_man.json"))


def _f(v, d=0.0) -> float:
    try:
        return float(v) if v not in (None, "", "NA") else d
    except (TypeError, ValueError):
        return d


def name_key(name: str) -> str:
    """'T.Higgins', 'Tee Higgins', 'Tee Higgins Jr.' → 't higgins'."""
    s = re.sub(r"[^a-z. ]", "", str(name or "").lower()).replace(".", ". ")
    parts = [p.strip(".") for p in s.split() if p.strip(".")]
    while len(parts) > 1 and parts[-1] in _SUFFIX:
        parts.pop()
    if not parts:
        return ""
    return f"{parts[0][0]} {parts[-1]}" if len(parts) > 1 else parts[0]


def week_of(game_id: str) -> int:
    parts = str(game_id or "").split("_")
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0


def man_edges(part_prev: list[dict], plays_prev: list[dict]) -> dict:
    """{name key: man edge} from last season's targets."""
    from .sources import nflscheme as N
    merged: dict = {}
    for (_team, name), c in N.receiver_splits(part_prev, plays_prev).items():
        m = merged.setdefault(name_key(name), {"zone": [0, 0.0], "man": [0, 0.0]})
        for k in ("zone", "man"):
            m[k][0] += c[k][0]
            m[k][1] += c[k][1]
    out = {}
    for key, c in merged.items():
        (tz, yz), (tm, ym) = c["zone"], c["man"]
        if not key or tz < ZONE_MIN_TGTS or tm < MAN_MIN_TGTS:
            continue
        allt = (yz + ym) / (tz + tm)
        if allt > 0:
            out[key] = (ym / tm - yz / tz) / allt
    return out


def rz_looks(part_rows: list[dict], plays: list[dict]) -> list[tuple]:
    """[(week, defence, is_man)] for every coverage-labelled dropback inside
    the defence's own 20. The yard line comes from the play-by-play, joined
    on (game id, play id); the defence is the game's other team."""
    yard = {}
    for p in plays:
        yard[(p.get("game_id") or "", str(p.get("play_id") or "").split(".")[0])] = (
            _f(p.get("yardline_100"), 99.0), p.get("defteam") or "")
    out = []
    for r in part_rows:
        mz = (r.get("defense_man_zone_type") or "").upper()
        if mz not in ("MAN_COVERAGE", "ZONE_COVERAGE"):
            continue
        gid = r.get("nflverse_game_id") or ""
        got = yard.get((gid, str(r.get("play_id") or "").split(".")[0]))
        if not got or got[0] > RZ_YARDS:
            continue
        defence = got[1]
        if not defence:
            teams = gid.split("_")[2:4]
            pos = (r.get("possession_team") or "").strip()
            defence = next((t for t in teams if t != pos), "")
        if defence:
            out.append((week_of(gid), defence, mz == "MAN_COVERAGE"))
    return out


def rz_man_rates(looks: list[tuple], prior: dict | None = None) -> dict:
    """{week: {"league": rate, team: rate}} — each defence's red-zone man
    rate over the weeks BEFORE that week, blended toward last season's
    (``prior`` {team: rate}) by plays / (plays + PRIOR_PLAYS)."""
    weeks = sorted({w for w, _t, _m in looks if w > 0})
    out = {}
    for wk in weeks + [max(weeks) + 1 if weeks else 1]:
        man, tot = defaultdict(int), defaultdict(int)
        for w, team, is_man in looks:
            if 0 < w < wk:
                tot[team] += 1
                man[team] += int(is_man)
        teams = set(tot) | set(prior or {})
        rates = {}
        for t in teams:
            n = tot.get(t, 0)
            now = man[t] / n if n else None
            pri = (prior or {}).get(t)
            if now is None and pri is None:
                continue
            if now is None:
                rates[t] = pri
            elif pri is None:
                rates[t] = now
            else:
                w8 = n / (n + PRIOR_PLAYS)
                rates[t] = w8 * now + (1 - w8) * pri
        if rates:
            out[wk] = {"league": sum(rates.values()) / len(rates), **rates}
    return out


def season_rates(looks: list[tuple]) -> dict:
    """{team: red-zone man rate} over a whole season — next season's prior."""
    man, tot = defaultdict(int), defaultdict(int)
    for _w, team, is_man in looks:
        tot[team] += 1
        man[team] += int(is_man)
    return {t: man[t] / tot[t] for t in tot if tot[t]}


def _week(v) -> int:
    try:
        return int(str(v).split("-W")[-1].lstrip("0") or 0)
    except ValueError:
        return 0


def samples(rows: list[dict], edges_by_season: dict, rates_by_season: dict) -> list[tuple]:
    """[(season, cluster, logit p, x, scored)] for WR/TE rows where both his
    man edge and the opponent's red-zone man rate are measured."""
    from .tdfeatures import logit
    out = []
    for r in rows:
        if str(r.get("position") or "").upper() not in POSITIONS:
            continue
        season, wk = int(r["season"]), _week(r["week"])
        edge = edges_by_season.get(season, {}).get(name_key(r.get("player")))
        rates = rates_by_season.get(season, {}).get(wk)
        opp = str(r.get("opponent") or "")
        if edge is None or not rates or opp not in rates:
            continue
        x = edge * (rates[opp] - rates["league"])
        out.append((season, (season, wk, opp), logit(float(r["prob"])), x, int(r["scored"])))
    return out


def judge(data: list) -> dict:
    """The bar, on [(season, cluster, logit p, x, scored)]."""
    from .tdinjfit import _fit, _loss, cluster_t
    seasons = sorted({d[0] for d in data})
    per, better, base_sum, fit_sum = {}, 0, 0.0, 0.0
    for s in seasons:
        train = [d for d in data if d[0] != s]
        test = [d for d in data if d[0] == s]
        b0, _ = _fit(train, False)
        b1, _ = _fit(train, True)
        if b0 is None or b1 is None or not test:
            continue
        base, fit = _loss(b0, test, False), _loss(b1, test, True)
        per[s] = {"n": len(test), "gain": round((base - fit) / len(test), 6)}
        better += fit < base
        base_sum += base
        fit_sum += fit
    b, t = cluster_t(data) if data else (None, None)
    from .tdfeatures import sigmoid
    xs = sorted(d[3] for d in data)
    top = xs[int(len(xs) * 2 / 3)] if xs else 0.0

    def ratio(rs):
        exp = sum(sigmoid(d[2]) for d in rs)
        return round(sum(d[4] for d in rs) / exp, 3) if exp else None
    passed = bool(len(per) >= 2 and fit_sum < base_sum and better >= len(per) - 1
                  and b is not None and b > 0 and t is not None and t >= MIN_T
                  and len(data) >= MIN_ROWS)
    return {"n": len(data), "b": None if b is None else round(b, 4),
            "t": None if t is None else round(t, 2), "seasons": per, "better": better,
            "gain": round((base_sum - fit_sum) / len(data), 6) if data else 0.0,
            "scored_vs_model_top_third": ratio([d for d in data if d[3] >= top]),
            "scored_vs_model_rest": ratio([d for d in data if d[3] < top]),
            "passed": passed}


def load(yr: int) -> tuple:
    """(participation rows, play rows) for one season, slimmed as read."""
    from .sources import nflpbp, nflscheme as N
    plays = [{k: r.get(k) for k in ("game_id", "play_id", "posteam", "defteam", "yardline_100",
                                     "receiver_player_name", "yards_gained", "complete_pass")}
             for r in nflpbp.load_pbp_rows(yr, columns=("play_id", "defteam", "yardline_100", "season_type"))
             if r.get("season_type", "REG") == "REG"]
    part = [{k: r.get(k) for k in ("nflverse_game_id", "play_id", "possession_team",
                                    "defense_man_zone_type", "defense_coverage_type")}
            for r in N.load_participation(yr, ttl=10 ** 9) if r.get("defense_man_zone_type")]
    return part, plays


def measure(conn, seasons=SEASONS, loader=load) -> dict:
    from .tdbacktest import run
    rows: list = []
    run(conn, seasons=list(seasons), collect=rows.append)
    edges, rates = {}, {}
    prev = None
    for yr in [seasons[0] - 1, *seasons]:
        try:
            part, plays = loader(int(yr))
        except Exception as e:                                # noqa: BLE001
            print(f"  {yr}: participation or play-by-play unavailable ({type(e).__name__})")
            prev = None
            continue
        looks = rz_looks(part, plays)
        if prev is not None and yr in seasons:
            edges[yr] = man_edges(*prev["src"])
            rates[yr] = rz_man_rates(looks, prior=prev["rates"])
        prev = {"src": (part, [p for p in plays if p.get("receiver_player_name")]),
                "rates": season_rates(looks)}
    return judge(samples(rows, edges, rates))


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": STORE_VERSION, "proven": res if res["passed"] else None,
                             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                             .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")


def report(res: dict) -> str:
    per = ", ".join(f"{s} {d['gain']:+.5f}" for s, d in res["seasons"].items())
    return (f"  RED-ZONE MAN  good vs man × opponent's red-zone man rate → WR/TE touchdowns\n"
            f"      {res['n']:,} player-weeks measured; scored ÷ model {res['scored_vs_model_top_third']} "
            f"in the top third of x vs {res['scored_vs_model_rest']} the rest\n"
            f"      b {res['b']}  clustered t {res['t']}  held-out gain {res['gain']:+.6f} "
            f"(better {res['better']}/{len(res['seasons'])}: {per})  → "
            f"{'PROVEN' if res['passed'] else 'not proven'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.tdmanfit")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from . import db
    res = measure(db.connect())
    print(report(res))
    if not a.dry_run:
        save(res)
        print("saved; a proven result earns a history line on the touchdown card, never a number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
