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
def _store() -> Path:
    """data/models/likely_context.json — see likelycal._store."""
    from . import modelstate
    return Path(os.environ.get("QB_LIKELY_CTX", "").strip() or modelstate.path("likely_context.json"))
#: The Most Likely books, in the order a pick is credited to one.
BOOKS = ("likely_live", "likely", "board", "td_scenario", "matchup_td", "matchup_prop", "bold")
SOURCE = {"likely_live": "list", "likely": "list", "board": "board", "td_scenario": "scenario",
          "matchup_td": "matchup", "matchup_prop": "matchup", "bold": "bold"}
#: Leagues the scout reads (football's flags are football's). College
#: joined 2026-10-09 with its own thresholds (scout.LEAGUE): the same reads
#: and the same held-out bar, fitted on college's own record only.
SPORTS = ("nfl", "cfb")


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


#: WHICH STORED NFL GAMES WERE PLAYED ABROAD. The games table keeps no
#: location, so the schedule file on disk (nflverse games.csv, the one the
#: build already caches) says: every regular-season game at a neutral site
#: — in the NFL an international one. Read from disk only, never fetched.
_ABROAD: dict = {}


def abroad_keys(path=None) -> set:
    """{(season, week, home team)} for every regular-season neutral-site NFL
    game in the cached schedule; an empty set without one."""
    import csv as _csv
    from .sources.fetch import CACHE_DIR
    p = Path(path) if path else Path(CACHE_DIR) / "games.csv"
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        return set()
    if _ABROAD.get("stamp") != stamp:
        keys = set()
        try:
            with open(p, newline="", encoding="utf-8") as fh:
                for r in _csv.DictReader(fh):
                    try:
                        season, week = int(r.get("season") or 0), int(float(r.get("week") or 0))
                    except ValueError:
                        continue
                    if str(r.get("location") or "").lower() == "neutral" and 1 <= week <= 18:
                        keys.add((season, week, str(r.get("home_team") or "")))
        except (OSError, ValueError):
            keys = set()
        _ABROAD["stamp"], _ABROAD["keys"] = stamp, keys
    return _ABROAD["keys"]


def history_index(hist, players: set, sport: str = "nfl") -> tuple[dict, dict, dict]:
    """(games by id, games by team in date order, {player: [log rows]}).

    THE TWO TABLES DO NOT SHARE A GAME ID: games writes "LV@KC", the
    player logs write "LV-004" (engine/corrfit.py found the same). The
    first box run of the audit (2026-10-03) joined on the id, found no
    log for anyone, and so called every pick a thin sample. A log row
    meets its game on what both tables do share: season, week, team.
    Each log row's ``game_id`` is rewritten to its game's, so everything
    downstream compares like with like."""
    games, by_team = {}, defaultdict(list)
    abroad = abroad_keys() if sport == "nfl" else set()
    for g in hist.execute("SELECT * FROM games WHERE sport=?", (sport,)):
        g = dict(g)
        g["abroad"] = (g.get("season"), _week(g.get("period")), g.get("home")) in abroad
        # COLLEGE'S PERIOD IS ITS DATE. The college ingest writes the kickoff
        # date into ``period`` ("2025-10-04", engine/sources/cfbfastr) and
        # leaves ``date`` empty; read as a week it is no week at all, so the
        # first college runs (2026-10-09) dropped every college game — the
        # replay found no seasons and 0 of 689 picks met their game.
        d = _date(g.get("date") or "") or _date(g.get("period") or "")
        if d is None:
            # Older schedule rows were written before the kickoff date was
            # kept (engine/ingest.nfl_game_rows). The week still orders
            # them; the weekday is unknown and says so.
            wk = _week(g.get("period"))
            if not isinstance(wk, int) or not g.get("season"):
                continue
            # College opens a week before the NFL; a week off is all the
            # ordering needs, and the weekday says "unknown" either way.
            d = _dt.date(int(g["season"]), 9, 7 if sport == "nfl" else 1) + _dt.timedelta(weeks=wk - 1)
            g["_approx"] = True
        g["_d"] = d
        # "BUF@KC" IS NOT A GAME, it is a fixture that recurs every season.
        # Keyed on it alone, each season's game overwrote the last one's,
        # and the 2026-10-03 replay found only 2025-26. The id carries its
        # season and week from here on.
        g["raw_id"] = g["game_id"]
        g["game_id"] = f"{g.get('season')}|{g.get('period')}|{g['game_id']}"
        games[g["game_id"]] = g
        for t in (g["home"], g["away"]):
            by_team[t].append(g)
    for t in by_team:
        by_team[t].sort(key=lambda g: g["_d"])
    by_key = game_keys(games)
    logs = defaultdict(list)
    names = sorted(players)
    for i in range(0, len(names), 400):
        chunk = names[i:i + 400]
        q = ("SELECT player, season, period, game_id, team, position, market, value FROM player_game_logs "
             f"WHERE sport=? AND player IN ({','.join('?' * len(chunk))})")
        for r in hist.execute(q, [sport, *chunk]):
            g = log_game(r, games, by_key)
            if g is not None:
                logs[r["player"]].append({**dict(r), "game_id": g["game_id"], "_d": g["_d"]})
    return games, by_team, logs


def _week(period):
    """"004", "4" and 4 are the same week."""
    try:
        return int(str(period).strip())
    except (TypeError, ValueError):
        return str(period or "")


def log_game(r, games: dict, by_key: dict) -> dict | None:
    """The game a player-log row belongs to: by id where the ids agree,
    else by (season, week, team)."""
    return games.get(r["game_id"]) or by_key.get((r["season"], _week(r["period"]), r["team"]))


def game_keys(games: dict) -> dict:
    """{(season, week, team): game} — the key log rows meet games on."""
    out = {}
    for g in games.values():
        for t in (g["home"], g["away"]):
            out[(g.get("season"), _week(g.get("period")), t)] = g
    return out


def _outdoor(roof):
    roof = str(roof or "").lower()
    return None if not roof else roof in ("outdoors", "open", "outdoor")


def context(pick: dict, games: dict, by_team: dict, logs: dict, sport: str = "nfl") -> dict | None:
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
                     weekday=None if game.get("_approx") else gd.weekday(), games_season=games_season,
                     missed_last=missed, league=sport, abroad=game.get("abroad"))
    s["team"], s["game_id"] = team, game["game_id"]
    if game.get("home_score") is not None and game.get("away_score") is not None:
        mine_pts = game["home_score"] if team == game["home"] else game["away_score"]
        their = game["away_score"] if team == game["home"] else game["home_score"]
        s["final_margin"] = float(mine_pts) - float(their)
    return s


def flagged_journal(ledger, hist, sport: str = "nfl") -> list[dict]:
    """The journal with each pick's situation and flags attached."""
    rows = journal(ledger, sport)
    games, by_team, logs = history_index(hist, {r["player"] for r in rows}, sport)
    for r in rows:
        r["ctx"] = context(r, games, by_team, logs, sport)
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


def _abroad_game(g: dict) -> bool:
    """A board game at a neutral site whose venue is an international one
    (engine/nflwx.venue_coords) — never a domestic relocation or a Super
    Bowl."""
    from .nflwx import venue_coords
    return bool(g.get("neutral_site")) and venue_coords(g.get("venue") or "") is not None


def annotate(rows: list[dict], result: dict, sport: str = "nfl") -> int:
    """Put ``scout_flags`` and ``scout_notes`` on every player row of the
    board; returns how many rows carry at least one. Moves no number.
    ``sport`` picks the league's thresholds (scout.LEAGUE)."""
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
    # His share of his team's targets and his place among them, from the
    # scan's usage read (the thin_target_over flag).
    usage: dict = {}
    for game in (result.get("scan_reads") or {}).values():
        for x in (game or {}).get("players") or []:
            if x.get("player") and isinstance(x.get("usage"), dict):
                usage[x["player"]] = (x.get("team"), x["usage"])
    by_team: dict = {}
    for name, (team, u) in usage.items():
        by_team.setdefault(team, []).append((float(u.get("targets_pg") or 0.0), name))
    tgt_rank = {name: i + 1 for team, lst in by_team.items()
                for i, (_t, name) in enumerate(sorted(lst, key=lambda x: (-x[0], x[1])))}
    n = 0
    for r in rows:
        if r.get("kind") == "game" or not r.get("player") or not r.get("market"):
            continue
        g = _game_for(r, games)
        u = (usage.get(r["player"]) or (None, {}))[1]
        w = (g or {}).get("weather") or {}
        team = r.get("team")
        lw, tw = last_week.get(r.get("player")), team_week.get(team)
        s = SC.situation(
            r["market"], r.get("side") or ("YES" if r["market"] == "anytime_td" else ""), line=r.get("line"),
            position=r.get("position") or "", values=r.get("recent_values") or [],
            game_spread=(g or {}).get("spread"), home=(team == (g or {}).get("home")) if g else None,
            total=(g or {}).get("total"), wind=w.get("wind_mph") if w.get("measured") else None,
            outdoor=(not w.get("dome")) if w else None, weekday=_weekday(g) if g else None,
            missed_last=(lw is not None and tw is not None and lw < tw),
            tgt_share=u.get("tgt_share") if u.get("targets_pg") else None,
            tgt_rank=tgt_rank.get(r["player"]), league=sport,
            abroad=_abroad_game(g) if g else None)
        codes = SC.flags(s)
        r["scout_flags"] = codes
        r["scout_notes"] = SC.notes(codes, sport)
        n += bool(codes)
    return n


# --- the correction ----------------------------------------------------------------
#: A "flag" up on more than this share of the record is not a situation, it
#: is the record — whose over-claiming is engine/likelycal's to correct, by
#: maker and side. Written 2026-10-03 after the first box run, where a broken
#: join raised thin_sample on 395 of 395 picks and the fit "proved" it by
#: pulling every pick to its price.
MAX_SHARE = 0.5


def maker(sources) -> str:
    """The likelycal group a journal pick falls in, read the way the board
    reads a row (likelycal.source_of_row): bold first, then the list, the
    matchup picks, the scenarios."""
    src = set(sources or ())
    for name in ("bold", "list", "matchup", "scenario"):
        if name in src:
            return name
    return "list"


def _cal_base(r: dict, q: float, cal: dict) -> float:
    """What the board shows once likelycal has run — the number this
    correction is stacked on, so the two never correct the same loss twice."""
    from .likelycal import k_for, side_of
    g = k_for(cal, f"{maker(r.get('sources'))}|{side_of(r.get('side'))}") or {}
    k = g.get("k", 1.0)
    return float(r["p"]) if k >= 1.0 else shrink(float(r["p"]), q, k)


def _rows_for_fit(flagged: list[dict], cal: dict | None = None) -> list[dict]:
    out = []
    for r in flagged:
        q = price_chance(r.get("odds"))
        if q is None:
            continue
        game = f"{r['day']}|{(r.get('ctx') or {}).get('game_id') or r.get('team') or r['player']}"
        out.append({"flags": list(r["flags"]), "p": _cal_base(r, q, cal or {}), "q": q,
                    "won": bool(r["won"]), "game": game})
    return out


def fit_flags(rows: list[dict]) -> dict:
    """{flag: {"k", "n", "hit", "claimed"}} for flags on MIN_GROUP+ picks
    and on no more than MAX_SHARE of them."""
    by: dict = defaultdict(list)
    for r in rows:
        for f in r["flags"]:
            by[f].append(r)
    out = {}
    for f, rs in by.items():
        if len(rs) < MIN_GROUP or len(rs) > MAX_SHARE * len(rows):
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


def fit(ledger, hist, sport: str = "nfl", cal: dict | None = None, flagged: list | None = None) -> dict:
    """``cal`` = the likelycal groups the board applies first (default: its
    store), so "raw" below means what the board shows after likelycal."""
    if cal is None:
        from . import likelycal
        cal = (likelycal.load().get(sport) or {}).get("groups") or {}
    if flagged is None:
        flagged = flagged_journal(ledger, hist, sport)
    rows = _rows_for_fit(flagged, cal)
    ho = held_out(rows) if rows else {"n": 0}
    flags = fit_flags(rows)
    seen = defaultdict(int)
    for r in rows:
        for f in r["flags"]:
            seen[f] += 1
    return {"sport": sport, "n": len(rows), "held_out": ho, "flags": flags, "after_cal": bool(cal),
            "too_common": sorted(f for f, n in seen.items() if n > MAX_SHARE * len(rows)),
            "with_context": sum(1 for r in flagged if r.get("ctx")),
            "passed": bool(ho.get("n") and ho.get("lo", 0) > 0),
            "fitted_at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}


def load(path=None) -> dict:
    try:
        return json.loads(Path(path or _store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    store = load(p)
    store[res["sport"]] = {"flags": res["flags"], "held_out": res["held_out"], "fitted_at": res["fitted_at"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)


def apply(rows: list[dict], sport: str, store: dict | None = None, history: dict | None = None) -> int:
    """Lower each flagged row's chance by what is proven about its flags,
    taking whichever of two corrections lowers it more (never both):

      * the RECORD's (``fit``): toward its price by its most cautious flag's k;
      * HISTORY's (engine/scouthist): by the shift 2021+ games proved for
        that flag on this market and side, never below its price.

    Returns how many moved. The chance before rides along as
    ``ctx_raw_prob`` and the reason as ``ctx_note``."""
    from . import scouthist
    ks = ((store if store is not None else load()).get(sport) or {}).get("flags") or {}
    hist = history if history is not None else scouthist.load(sport=sport)
    moved = 0
    for r in rows:
        codes = r.get("scout_flags") or []
        q = price_chance(r.get("odds"))
        if not codes or r.get("model_prob") is None or q is None:
            continue
        raw = float(r["model_prob"])
        k = _k_for(codes, ks)
        by_record = round(shrink(raw, q, k), 4) if k < 1.0 else raw
        side = r.get("side") or ("YES" if r.get("market") == "anytime_td" else "")
        shift, hflag = scouthist.shift_for(codes, r.get("market") or "", side, hist)
        by_history = round(max(min(raw, q), raw + shift), 4) if shift < 0 else raw
        adj = min(by_record, by_history)
        if adj >= raw:
            continue
        r["ctx_raw_prob"], r["model_prob"] = raw, adj
        # The journal keeps the FIRST claim (ledger reads board_raw_prob), so
        # the next fit judges what we said, never its own correction.
        r.setdefault("board_raw_prob", raw)
        if by_history <= by_record:
            r["ctx_note"] = (f"{SC.note(hflag, sport)}: in 2021+ games picks like this hit {abs(shift):.0%} less "
                             f"often than usual, so this shows {adj:.0%} (it was {raw:.0%})")
        else:
            worst = min(codes, key=lambda f: (ks.get(f) or {}).get("k", 1.0))
            g = ks[worst]
            r["ctx_note"] = (f"picks like this one ({SC.note(worst, sport)}) have hit {g['hit']:.0%} of {g['n']} where "
                             f"we said {g['claimed']:.0%}, so this shows {adj:.0%} (it was {raw:.0%})")
        moved += 1
    return moved


# --- the command ---------------------------------------------------------------------
def _report(res: dict) -> None:
    ho = res["held_out"]
    print(f"\n=== {res['sport'].upper()}: {res['n']} settled picks with a price, read for the scout's flags "
          f"({res.get('with_context', 0)} matched to their game)")
    print("    stacked on the record's calibration (likelycal) already in the store" if res.get("after_cal")
          else "    no likelycal store yet — measured against the board's raw numbers")
    for f in res.get("too_common") or []:
        print(f"    {f:20} up on more than half the picks — that is the whole record, likelycal's job; skipped")
    for f, v in sorted(res["flags"].items(), key=lambda kv: kv[1]["k"]):
        what = "left alone" if v["k"] >= 1.0 else f"pulled {1 - v['k']:.0%} of the way to the price"
        print(f"    {f:20} n {v['n']:4}  said {v['claimed']:.0%}  hit {v['hit']:.0%}  → {what}")
    if not ho.get("n"):
        print("    nothing to judge yet.")
        return
    print(f"    held out (5 folds by game, {ho['games']} games): log loss {ho['raw']} raw → {ho['corrected']} "
          f"corrected; gain {ho['gain']:+.4f}, 95% {ho['lo']:+.4f} to {ho['hi']:+.4f}")
    if not res["passed"]:
        print("    NOT PROVEN — nothing saved; the flags stay notes on the card.")
    elif res.get("dry_run"):
        print("    PASSES — dry run, nothing saved; run it without --dry-run to save.")
    else:
        print("    PASSES — saved; the board reads it on its next build.")


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
    res["dry_run"] = a.dry_run
    if res["passed"] and not a.dry_run:
        save(res)
    _report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
