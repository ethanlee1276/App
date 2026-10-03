"""The scout's flags on the Most Likely board, and the record's say on them.

    sudo -u qellys python3 -m engine.likelyctx fit --sport nfl          # measure; save only if it holds
    sudo -u qellys python3 -m engine.likelyctx fit --sport nfl --dry-run
    sudo -u qellys python3 -m engine.likelyctx show

Ethan, 2026-10-03: "think like a human when it comes to making the pick
selections ... using data on top of just general football knowledge."

TWO JOBS, kept apart on purpose.

1. THE READ (``annotate``) — every NFL board row gets the scout's flags
   (engine/scout.py: an under in a projected shootout, a rushing over on a
   team expected to trail, his first game back, a line set above his recent
   form…) and their sentences, drawn on the card under "Why?". That is
   information a reader weighs, the note a football person would write, and
   it moves no number.

2. THE CORRECTION (``fit`` / ``apply``) — a flag moves a number only once
   the graded record has shown, OUT OF SAMPLE, that picks carrying it hit
   less often than we said. The method is engine/likelycal's, with flags in
   place of makers: each flag with MIN_GROUP settled picks gets a k (0..1,
   by log loss): shown = price + k × (ours − price). A pick carrying several
   flags takes the smallest k — the most cautious. The whole correction is
   scored on five folds split by game, each fold's k fitted on the others,
   and saved only if the held-out log loss improves at the bottom of its 95%
   bootstrap interval. A chance is only ever lowered; nothing leaves the
   board; a correction that has not passed changes nothing.

THE RECORD'S CONTEXT is rebuilt from the history database — the game's
spread, total, weather and day, and his own results before it — by the same
code nflaudit.py reports with (``journal`` / ``context``), so the audit, the
fit and the board can never disagree about what a flag meant.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from . import scout as SC
from .likelycal import BOOT, FOLDS, K_GRID, SEED, _ll, price_chance, shrink

MIN_GROUP = 30
STORE = Path(os.environ.get("QB_LIKELY_CTX", "").strip()
             or (Path(__file__).resolve().parents[1] / "data" / "likely_context.json"))
#: The Most Likely books, in the order a pick is credited to one.
BOOKS = ("likely_live", "likely", "board", "td_scenario", "matchup_td", "matchup_prop", "bold")
SOURCE = {"likely_live": "list", "likely": "list", "board": "board", "td_scenario": "scenario",
          "matchup_td": "matchup", "matchup_prop": "matchup", "bold": "bold"}
#: Leagues the scout reads (football's flags are football's).
SPORTS = ("nfl",)


# --- the record, in its football context ----------------------------------------
def ro(path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def journal(ledger, sport: str = "nfl") -> list[dict]:
    """Every settled pick in the Most Likely books, each once, credited to
    the first book that holds it; ``sources`` lists every book it sat in.
    The claim is the board's RAW chance where it kept one (a pick the record
    already corrected is judged on what we first said)."""
    marks = ",".join("?" * len(BOOKS))
    rows = ledger.execute(
        f"SELECT * FROM bets WHERE LOWER(sport)=? AND category IN ({marks}) "
        "AND status IN ('won','lost') AND hit_prob IS NOT NULL", (sport, *BOOKS)).fetchall()
    by: dict = {}
    for r in sorted(rows, key=lambda r: BOOKS.index(r["category"])):
        d = dict(r)
        day = d.get("game_day") or d.get("date") or ""
        key = (day, d["player"], d["market"], str(d.get("side") or "").upper())
        if key in by:
            by[key]["sources"].add(SOURCE[d["category"]])
            continue
        raw = d.get("raw_prob")
        d.update(day=day, sources={SOURCE[d["category"]]}, won=d["status"] == "won",
                 p=float(raw if raw is not None else d["hit_prob"]))
        by[key] = d
    return list(by.values())


def _date(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def history_index(hist, players: set) -> tuple[dict, dict, dict]:
    """(games by id, games by team in date order, {player: [log rows]})."""
    games, by_team = {}, defaultdict(list)
    for g in hist.execute("SELECT * FROM games WHERE sport='nfl'"):
        g = dict(g)
        d = _date(g.get("date") or "")
        if d is None:
            continue
        g["_d"] = d
        games[g["game_id"]] = g
        for t in (g["home"], g["away"]):
            by_team[t].append(g)
    for t in by_team:
        by_team[t].sort(key=lambda g: g["_d"])
    logs = defaultdict(list)
    names = sorted(players)
    for i in range(0, len(names), 400):
        chunk = names[i:i + 400]
        q = ("SELECT player, season, game_id, team, position, market, value FROM player_game_logs "
             f"WHERE sport='nfl' AND player IN ({','.join('?' * len(chunk))})")
        for r in hist.execute(q, chunk):
            g = games.get(r["game_id"])
            if g is not None:
                logs[r["player"]].append({**dict(r), "_d": g["_d"]})
    return games, by_team, logs


def _outdoor(roof):
    roof = str(roof or "").lower()
    return None if not roof else roof in ("outdoors", "open", "outdoor")


def context(pick: dict, games: dict, by_team: dict, logs: dict) -> dict | None:
    """The scout's situation for one settled pick, from what was known
    before its game — or None when its game cannot be found."""
    day = _date(pick.get("day") or "")
    if day is None:
        return None
    mine = logs.get(pick["player"]) or []
    before = sorted((r for r in mine if r["_d"] < day), key=lambda r: r["_d"], reverse=True)
    team = pick.get("team") or (before[0]["team"] if before else "")
    near = [g for g in by_team.get(team, []) if abs((g["_d"] - day).days) <= 3]
    if not near:
        return None
    game = min(near, key=lambda g: abs((g["_d"] - day).days))
    gd = game["_d"]
    before = [r for r in before if r["_d"] < gd]
    vals = [r["value"] for r in before if r["market"] == pick["market"]]
    season = game.get("season")
    games_season = len({r["game_id"] for r in before if r.get("season") == season})
    played = {r["game_id"] for r in before}
    prev = [g for g in by_team.get(team, []) if g["_d"] < gd and g.get("season") == season]
    missed = bool(prev) and games_season > 0 and prev[-1]["game_id"] not in played
    position = next((r.get("position") for r in before if r.get("position")), "")
    s = SC.situation(pick["market"], pick.get("side") or "", line=pick.get("line"), position=position,
                     values=vals, game_spread=game.get("spread"), home=(team == game["home"]),
                     total=game.get("total"), wind=game.get("wind"), outdoor=_outdoor(game.get("roof")),
                     weekday=gd.weekday(), games_season=games_season, missed_last=missed)
    s["team"], s["game_id"] = team, game["game_id"]
    if game.get("home_score") is not None and game.get("away_score") is not None:
        mine_pts = game["home_score"] if team == game["home"] else game["away_score"]
        their = game["away_score"] if team == game["home"] else game["home_score"]
        s["final_margin"] = float(mine_pts) - float(their)
    return s


def flagged_journal(ledger, hist, sport: str = "nfl") -> list[dict]:
    """The journal with each pick's situation and flags attached."""
    rows = journal(ledger, sport)
    games, by_team, logs = history_index(hist, {r["player"] for r in rows})
    for r in rows:
        r["ctx"] = context(r, games, by_team, logs)
        r["flags"] = SC.flags(r["ctx"]) if r["ctx"] else []
    return rows


# --- the board: the read ---------------------------------------------------------
def _game_for(row: dict, games: list) -> dict | None:
    team, opp = row.get("team"), row.get("opponent")
    for g in games or []:
        if team in (g.get("home"), g.get("away")) and (not opp or opp in (g.get("home"), g.get("away"))):
            return g
    return None


def _weekday(g: dict):
    for k in ("kickoff", "date"):
        v = str(g.get(k) or "")
        try:
            return _dt.date.fromisoformat(v[:10]).weekday()
        except ValueError:
            continue
    return None


def annotate(rows: list[dict], result: dict) -> int:
    """Put ``scout_flags`` and ``scout_notes`` on every player row of the
    board; returns how many rows carry at least one. Moves no number."""
    games = result.get("games") or []
    recs = result.get("recommendations") or []
    last_week: dict = {}
    team_week: dict = {}
    for r in recs:
        weeks = [g.get("week") for g in (r.get("logs") or []) if isinstance(g.get("week"), (int, float))]
        if not weeks:
            continue
        last_week[r.get("player")] = max(last_week.get(r.get("player"), 0), max(weeks))
        team_week[r.get("team")] = max(team_week.get(r.get("team"), 0), max(weeks))
    n = 0
    for r in rows:
        if r.get("kind") == "game" or not r.get("player") or not r.get("market"):
            continue
        g = _game_for(r, games)
        w = (g or {}).get("weather") or {}
        team = r.get("team")
        lw, tw = last_week.get(r.get("player")), team_week.get(team)
        s = SC.situation(
            r["market"], r.get("side") or ("YES" if r["market"] == "anytime_td" else ""), line=r.get("line"),
            position=r.get("position") or "", values=r.get("recent_values") or [],
            game_spread=(g or {}).get("spread"), home=(team == (g or {}).get("home")) if g else None,
            total=(g or {}).get("total"), wind=w.get("wind_mph") if w.get("measured") else None,
            outdoor=(not w.get("dome")) if w else None, weekday=_weekday(g) if g else None,
            missed_last=(lw is not None and tw is not None and lw < tw))
        codes = SC.flags(s)
        r["scout_flags"] = codes
        r["scout_notes"] = SC.notes(codes)
        n += bool(codes)
    return n


# --- the correction ----------------------------------------------------------------
def _rows_for_fit(flagged: list[dict]) -> list[dict]:
    out = []
    for r in flagged:
        q = price_chance(r.get("odds"))
        if q is None:
            continue
        game = f"{r['day']}|{(r.get('ctx') or {}).get('game_id') or r.get('team') or r['player']}"
        out.append({"flags": list(r["flags"]), "p": float(r["p"]), "q": q, "won": bool(r["won"]), "game": game})
    return out


def fit_flags(rows: list[dict]) -> dict:
    """{flag: {"k", "n", "hit", "claimed"}} for flags on MIN_GROUP+ picks."""
    by: dict = defaultdict(list)
    for r in rows:
        for f in r["flags"]:
            by[f].append(r)
    out = {}
    for f, rs in by.items():
        if len(rs) < MIN_GROUP:
            continue
        best = min(K_GRID, key=lambda k: sum(_ll(shrink(x["p"], x["q"], k), x["won"]) for x in rs))
        out[f] = {"k": best, "n": len(rs), "hit": round(sum(x["won"] for x in rs) / len(rs), 4),
                  "claimed": round(sum(x["p"] for x in rs) / len(rs), 4)}
    return out


def _k_for(flags: list, ks: dict) -> float:
    return min([(ks.get(f) or {}).get("k", 1.0) for f in flags] or [1.0])


def held_out(rows: list[dict], folds=FOLDS, seed=SEED) -> dict:
    """Out-of-fold log loss, raw against corrected, games kept whole."""
    games = sorted({r["game"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    fold_of = {g: i % folds for i, g in enumerate(games)}
    per_game: dict = {}
    for f in range(folds):
        ks = fit_flags([r for r in rows if fold_of[r["game"]] != f])
        for r in rows:
            if fold_of[r["game"]] != f:
                continue
            k = _k_for(r["flags"], ks)
            cell = per_game.setdefault(r["game"], [0.0, 0.0, 0])
            cell[0] += _ll(r["p"], r["won"])
            cell[1] += _ll(shrink(r["p"], r["q"], k), r["won"])
            cell[2] += 1
    cells = list(per_game.values())
    n = sum(c[2] for c in cells)
    if not n:
        return {"n": 0}
    boots = []
    for _ in range(BOOT):
        pick = [cells[rng.randrange(len(cells))] for _ in cells]
        m = sum(c[2] for c in pick)
        boots.append((sum(c[0] for c in pick) - sum(c[1] for c in pick)) / m if m else 0.0)
    boots.sort()
    return {"n": n, "games": len(cells), "raw": round(sum(c[0] for c in cells) / n, 4),
            "corrected": round(sum(c[1] for c in cells) / n, 4),
            "gain": round((sum(c[0] for c in cells) - sum(c[1] for c in cells)) / n, 5),
            "lo": round(boots[int(0.025 * BOOT)], 5), "hi": round(boots[int(0.975 * BOOT) - 1], 5)}


def fit(ledger, hist, sport: str = "nfl") -> dict:
    rows = _rows_for_fit(flagged_journal(ledger, hist, sport))
    ho = held_out(rows) if rows else {"n": 0}
    flags = fit_flags(rows)
    return {"sport": sport, "n": len(rows), "held_out": ho, "flags": flags,
            "passed": bool(ho.get("n") and ho.get("lo", 0) > 0),
            "fitted_at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}


def load(path=None) -> dict:
    try:
        return json.loads(Path(path or STORE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(res: dict, path=None) -> None:
    p = Path(path or STORE)
    store = load(p)
    store[res["sport"]] = {"flags": res["flags"], "held_out": res["held_out"], "fitted_at": res["fitted_at"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)


def apply(rows: list[dict], sport: str, store: dict | None = None) -> int:
    """Lower each flagged row's chance toward its price by its most
    cautious proven flag; returns how many moved. The chance before rides
    along as ``ctx_raw_prob`` and the reason as ``ctx_note``."""
    ks = ((store if store is not None else load()).get(sport) or {}).get("flags") or {}
    moved = 0
    for r in rows:
        codes = r.get("scout_flags") or []
        if not codes or r.get("model_prob") is None:
            continue
        k = _k_for(codes, ks)
        q = price_chance(r.get("odds"))
        if k >= 1.0 or q is None:
            continue
        raw = float(r["model_prob"])
        adj = round(shrink(raw, q, k), 4)
        if adj >= raw:
            continue
        worst = min(codes, key=lambda f: (ks.get(f) or {}).get("k", 1.0))
        g = ks[worst]
        r["ctx_raw_prob"], r["model_prob"] = raw, adj
        # The journal keeps the FIRST claim (ledger reads board_raw_prob), so
        # the next fit judges what we said, never its own correction.
        r.setdefault("board_raw_prob", raw)
        r["ctx_note"] = (f"picks like this one ({SC.FLAGS[worst]}) have hit {g['hit']:.0%} of {g['n']} where we "
                         f"said {g['claimed']:.0%}, so this shows {adj:.0%} (it was {raw:.0%})")
        moved += 1
    return moved


# --- the command ---------------------------------------------------------------------
def _report(res: dict) -> None:
    ho = res["held_out"]
    print(f"\n=== {res['sport'].upper()}: {res['n']} settled picks with a price, read for the scout's flags")
    for f, v in sorted(res["flags"].items(), key=lambda kv: kv[1]["k"]):
        what = "left alone" if v["k"] >= 1.0 else f"pulled {1 - v['k']:.0%} of the way to the price"
        print(f"    {f:20} n {v['n']:4}  said {v['claimed']:.0%}  hit {v['hit']:.0%}  → {what}")
    if not ho.get("n"):
        print("    nothing to judge yet.")
        return
    print(f"    held out (5 folds by game, {ho['games']} games): log loss {ho['raw']} raw → {ho['corrected']} "
          f"corrected; gain {ho['gain']:+.4f}, 95% {ho['lo']:+.4f} to {ho['hi']:+.4f}")
    print("    PASSES — saved; the board reads it on its next build." if res["passed"]
          else "    NOT PROVEN — nothing saved; the flags stay notes on the card.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.likelyctx")
    ap.add_argument("cmd", choices=("fit", "show"), help="fit: measure and save if it holds; show: the store")
    ap.add_argument("--sport", default="nfl", help="the league to fit (default nfl)")
    ap.add_argument("--ledger", default="", help="ledger path (default data/ledger.db)")
    ap.add_argument("--history-db", default="", help="history path (default data/history.db)")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        print(json.dumps(load(), indent=1) or "{}")
        return 0
    from . import db, ledger
    res = fit(ro(a.ledger or ledger.DEFAULT_DB), ro(a.history_db or db.DEFAULT_DB), a.sport.lower())
    if res["passed"] and not a.dry_run:
        save(res)
    elif res["passed"]:
        print("(dry run: it would be saved)")
    _report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
