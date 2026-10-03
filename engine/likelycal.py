"""The Most Likely board's chances, made honest by its own record.

    sudo -u qellys python3 -m engine.likelycal fit --sport nfl      # measure; save only if it holds
    sudo -u qellys python3 -m engine.likelycal fit --sport nfl --dry-run
    sudo -u qellys python3 -m engine.likelycal show

Ethan, 2026-10-03, after the box's record check: "I don't want to really
get rid of any most likely bets ... I just want to use the everything we've
collected ... make the picks better, make what we recommend better."

WHAT THE RECORD SAID (2026-10-03, the NFL board, 300 settled):
  * the Most Likely list's own picks hold up — said 65%, hit 65% over 372;
  * the board's other picks do not: the matchup picks went 18-43 and the
    "bolder than the books" picks 23-38, while claiming the list's kind of
    number, and the board's unders claimed 63% and hit 49% (every sport);
  * the record check vouched for them anyway, because it reads the list's
    record for the same market, side and band — the honest picks' record,
    lent to picks from somewhere else.

WHAT THIS DOES. Nothing is removed. Each board pick's chance is pulled
toward the price's own chance by as much as picks LIKE IT — the same sport,
the same maker (the list, the matchup picks, the touchdown scenarios, the
bold rows) and the same side — have earned in the journal:

    shown = price's chance + k × (our chance − price's chance),  0 ≤ k ≤ 1

k = 1 leaves a group's number alone (its record backs it); k = 0 says its
record is no better than the price. A chance is only ever lowered, never
raised. The tiers, the ranking and the card then read the honest number, so
a pick that hit 30% stops wearing "Top pick" and one that holds up rises.
The price's chance is the American price's implied chance with an average
4.5% two-way hold taken out (DEVIG).

HOW IT IS KEPT FROM FITTING NOISE. k is chosen per group by log loss, and
only for groups of MIN_GROUP settled picks. Before anything is saved the
whole correction is scored on picks it was not fitted on: five folds split
by game (day and team), each fold's k fitted on the other four. The NFL
board is one week old, so a split by date would leave a few dozen picks to
judge; a split by game keeps every slate's picks on one side. THE BAR,
WRITTEN BEFORE ANY RUN: the held-out log loss must improve, at the bottom
of its 95% interval (a bootstrap over games). Pass → the k's fitted on
every pick are saved to the store the board reads on its next build. Fail
→ nothing is saved and the board keeps its own numbers. The record keeps
the board's raw chance beside the shown one (`raw_prob`), so the next fit
reads the raw claim and never compounds its own correction.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import random
import sys
from pathlib import Path

DEVIG = 1.045
MIN_GROUP = 40
FOLDS = 5
BOOT = 2000
SEED = 20261003
K_GRID = tuple(round(i * 0.05, 2) for i in range(21))
def _store() -> Path:
    """data/models/likely_calibration.json (engine/modelstate: a fit belongs
    to the box that measured it, and the suite sandboxes the directory —
    engine/boardlearn refits this nightly, so a test must never reach the
    real one). Read at call time, so the sandbox is honoured."""
    from . import modelstate
    return Path(os.environ.get("QB_LIKELY_CAL", "").strip() or modelstate.path("likely_calibration.json"))
#: The other books a board pick can also sit in, asked in this order.
SOURCE_BOOKS = (("bold", ("bold",)), ("matchup", ("matchup_td", "matchup_prop")),
                ("scenario", ("td_scenario",)))
SOURCE_WORDS = {"list": "Most Likely list", "matchup": "matchup picks",
                "scenario": "touchdown scenarios", "bold": "bolder-than-the-books picks"}


def price_chance(odds) -> float | None:
    """The price's own chance, the average hold taken out."""
    try:
        o = int(float(odds))
    except (TypeError, ValueError):
        return None
    if abs(o) < 100:
        return None
    p = ((-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)) / DEVIG
    return min(0.98, max(0.02, p))


def side_of(side) -> str:
    s = str(side or "").lower()
    return "under" if s in ("under", "no") else "over"


def source_of_row(r: dict) -> str:
    """A board row's maker, as the build sees it (r["sources"], r["bold"])."""
    src = r.get("sources") or []
    if r.get("bold"):
        return "bold"
    if "likely" in src:
        return "list"
    if "matchup" in src:
        return "matchup"
    if "scenario" in src:
        return "scenario"
    return "list"


def shrink(p: float, q: float, k: float) -> float:
    adj = q + k * (p - q)
    return min(p, max(0.02, min(0.98, adj)))


def _ll(p: float, won: bool) -> float:
    p = min(0.999, max(0.001, p))
    return -math.log(p if won else 1 - p)


# --- the journal ----------------------------------------------------------
def journal_rows(conn, sport: str) -> list[dict]:
    """Settled Most Likely picks, each ONCE, tagged with the maker the board
    credits it to (bold first, then the list, the matchup picks, the
    scenarios — `source_of_row`'s order), at the raw claim.

    It reads the journal through engine/likelyctx.journal, the same reading
    nflaudit.py reports from. Until 2026-10-04 it matched a board row to the
    other books on the `date` column, and the box's first fit (494 NFL
    picks) printed no bold group at all while the audit, keyed on the game
    day, found 61 bold picks hitting 38% where we said 75%: the worst maker
    on the board was invisible to the one correction built for it."""
    from .likelyctx import journal, maker
    out = []
    for r in journal(conn, sport):
        row = _row(r, maker(r["sources"]))
        if row is not None:
            out.append(row)
    return out


def _row(r, source):
    q = price_chance(r["odds"])
    if q is None:
        return None
    return {"group": f"{source}|{side_of(r['side'])}", "p": float(r["p"]), "q": q,
            "won": bool(r["won"]),
            "game": f"{r['day']}|{r.get('team') or r['player']}"}


# --- the fit ----------------------------------------------------------------
def fit_groups(rows: list[dict]) -> dict:
    """{group: {"k", "n", "hit", "claimed", "price"}} for groups of
    MIN_GROUP or more; smaller groups are left alone (absent)."""
    by: dict = {}
    for r in rows:
        by.setdefault(r["group"], []).append(r)
    out = {}
    for g, rs in by.items():
        if len(rs) < MIN_GROUP:
            continue
        best = min(K_GRID, key=lambda k: sum(_ll(shrink(x["p"], x["q"], k), x["won"]) for x in rs))
        out[g] = {"k": best, "n": len(rs),
                  "hit": round(sum(x["won"] for x in rs) / len(rs), 4),
                  "claimed": round(sum(x["p"] for x in rs) / len(rs), 4),
                  "price": round(sum(x["q"] for x in rs) / len(rs), 4)}
    return out


def held_out(rows: list[dict], folds=FOLDS, seed=SEED) -> dict:
    """Out-of-fold log loss, raw against corrected, games kept whole."""
    games = sorted({r["game"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    fold_of = {g: i % folds for i, g in enumerate(games)}
    per_game: dict = {}
    for f in range(folds):
        train = [r for r in rows if fold_of[r["game"]] != f]
        ks = fit_groups(train)
        for r in rows:
            if fold_of[r["game"]] != f:
                continue
            k = (ks.get(r["group"]) or {}).get("k", 1.0)
            raw, adj = _ll(r["p"], r["won"]), _ll(shrink(r["p"], r["q"], k), r["won"])
            cell = per_game.setdefault(r["game"], [0.0, 0.0, 0])
            cell[0] += raw
            cell[1] += adj
            cell[2] += 1
    cells = list(per_game.values())
    n = sum(c[2] for c in cells)
    if not n:
        return {"n": 0}
    gain = (sum(c[0] for c in cells) - sum(c[1] for c in cells)) / n
    boots = []
    for _ in range(BOOT):
        pick = [cells[rng.randrange(len(cells))] for _ in cells]
        m = sum(c[2] for c in pick)
        boots.append((sum(c[0] for c in pick) - sum(c[1] for c in pick)) / m if m else 0.0)
    boots.sort()
    return {"n": n, "games": len(cells), "raw": round(sum(c[0] for c in cells) / n, 4),
            "corrected": round(sum(c[1] for c in cells) / n, 4), "gain": round(gain, 5),
            "lo": round(boots[int(0.025 * BOOT)], 5), "hi": round(boots[int(0.975 * BOOT) - 1], 5)}


def fit(conn, sport: str) -> dict:
    rows = journal_rows(conn, sport)
    ho = held_out(rows) if rows else {"n": 0}
    groups = fit_groups(rows)
    passed = bool(ho.get("n") and ho.get("lo", 0) > 0)
    return {"sport": sport, "n": len(rows), "held_out": ho, "groups": groups, "passed": passed,
            "fitted_at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}


# --- the store and the board -----------------------------------------------
def load(path=None) -> dict:
    p = Path(path) if path else _store()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(res: dict, path=None) -> None:
    p = Path(path) if path else _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    store = load(p)
    store[res["sport"]] = {"groups": {g: {"k": v["k"], "n": v["n"], "hit": v["hit"], "claimed": v["claimed"]}
                                      for g, v in res["groups"].items()},
                           "held_out": res["held_out"], "fitted_at": res["fitted_at"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)


def apply(rows: list[dict], sport: str, store: dict | None = None) -> int:
    """Correct each board row's chance in place, before its checks; returns
    how many moved. The raw chance rides along as ``board_raw_prob`` (the
    journal keeps it as ``raw_prob``) and the reason as ``cal_note``."""
    groups = ((store if store is not None else load()).get(sport) or {}).get("groups") or {}
    moved = 0
    for r in rows:
        if r.get("model_prob") is None:
            continue
        g = groups.get(f"{source_of_row(r)}|{side_of(r.get('side'))}")
        q = price_chance(r.get("odds"))
        if not g or q is None or g["k"] >= 1.0:
            continue
        raw = float(r["model_prob"])
        adj = round(shrink(raw, q, g["k"]), 4)
        if adj >= raw:
            continue
        r["board_raw_prob"] = raw
        r["model_prob"] = adj
        src = source_of_row(r)
        r["cal_note"] = (f"{SOURCE_WORDS.get(src, src)} on the {side_of(r.get('side'))} have hit "
                         f"{g['hit']:.0%} of {g['n']} where we said {g['claimed']:.0%}, so this shows "
                         f"{adj:.0%} (our raw number was {raw:.0%})")
        moved += 1
    return moved


# --- the command ------------------------------------------------------------
def _report(res: dict) -> None:
    ho = res["held_out"]
    print(f"\n=== {res['sport'].upper()}: {res['n']} settled picks the correction can learn from")
    for g, v in sorted(res["groups"].items(), key=lambda kv: -kv[1]["n"]):
        src, side = g.split("|")
        what = "left alone" if v["k"] >= 1.0 else f"pulled {1 - v['k']:.0%} of the way to the price"
        print(f"    {SOURCE_WORDS.get(src, src):28} {side:5}  n {v['n']:4}  said {v['claimed']:.0%}  "
              f"price {v['price']:.0%}  hit {v['hit']:.0%}  → {what}")
    if not ho.get("n"):
        print("    nothing to judge yet.")
        return
    print(f"    held out (5 folds by game, {ho['games']} games): log loss {ho['raw']} raw → "
          f"{ho['corrected']} corrected; gain {ho['gain']:+.4f}, 95% {ho['lo']:+.4f} to {ho['hi']:+.4f}")
    print("    PASSES — " + ("saved; the board reads it on its next build." if res["passed"] else "")
          if res["passed"] else "    NOT PROVEN — nothing saved; the board keeps its own numbers.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.likelycal")
    ap.add_argument("cmd", choices=("fit", "show"), help="fit: measure and save if it holds; show: the store")
    ap.add_argument("--sport", default="nfl", help="the league to fit (default nfl)")
    ap.add_argument("--db", default="", help="ledger path (default data/ledger.db)")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        print(json.dumps(load(), indent=1) or "{}")
        return 0
    import sqlite3
    from . import ledger
    path = a.db or str(ledger.DEFAULT_DB)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    res = fit(conn, a.sport.lower())
    if res["passed"] and not a.dry_run:
        save(res)
    elif res["passed"]:
        print("(dry run: it would be saved)")
    _report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
