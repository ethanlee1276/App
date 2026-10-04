"""Does a top corner change what a receiver does — and who catches the rest?

    sudo -u qellys nice -n 19 python3 -m engine.cbfit

Ethan, 2026-10-04, after four Bengals @ Jaguars breakdowns: "yeah lets do
those." Two of their rules, stated as bettors state them:

  H1  Against a shutdown corner, a team's top receiver keeps his CATCHES
      better than his YARDS ("Hunter takes away the explosives, Burrow
      attacks him underneath — receptions over yards").
  H2  When the top receiver draws the top corner, the second receiver
      catches MORE than usual ("Chase draws Hunter, volume goes to
      Higgins").

Both are claims about history, so history is asked before either moves a
number or a card.

WHAT IS MEASURED. Every 2021+ regular-season game for every team's WR1 and
WR2 (by targets a game over his earlier games that season, two at least).
Each receiver's game is set against his own baseline — the mean of his
previous BASE_GAMES games, carried across seasons — as actual ÷ baseline,
for catches and for yards. The opponent's TOP CORNER is the defender who
had faced the most targets in that defence's earlier games that season
(PFR's advanced defence file; the most-targeted defender is a corner
nearly every time — this file names no positions, so that is the proxy,
and it is said). He is ELITE at a passer rating allowed of ELITE_RATING or
lower on MIN_DEF_TARGETS targets or more; every other game is the
comparison.

  H1 effect: mean(catch ratio − yards ratio) for a WR1 against an elite
             corner, minus the same for WR1s not against one.
  H2 effect: mean(catch ratio) for a WR2 whose team faces an elite corner,
             minus the same for WR2s whose team does not.

THE BAR, WRITTEN BEFORE ANY BOX RUN (engine/scouthist's): an effect is
PROVEN only if it is at least PROVEN_GAP in the claimed direction in BOTH
halves of the seasons, with at least PROVEN_N elite games in each half.
Anything else is reported and left alone. Nothing here moves a projection;
a proven rule earns a "history says" line on the case first.

Standard library only. Reads the history database and PFR's weekly
defence files (fetched and cached like the scan's).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
BASE_GAMES = 6
MIN_PRIOR = 3
ELITE_RATING = 80.0
MIN_DEF_TARGETS = 20
PROVEN_GAP = 0.03
PROVEN_N = 100
#: Floors so a quiet baseline cannot turn one catch into a ratio of six.
MIN_BASE = {"receptions": 1.5, "rec_yds": 15.0}
RATIO_CAP = 4.0

#: PFR's team codes where they differ from the history database's.
PFR_TEAM = {"GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF", "TAM": "TB",
            "LVR": "LV", "OAK": "LV", "SDG": "LAC", "STL": "LA", "LAR": "LA"}


def _store() -> Path:
    return Path(modelstate.path("cb_rules.json"))


def _f(v, d=0.0) -> float:
    try:
        return float(v) if v not in (None, "", "NA") else d
    except (TypeError, ValueError):
        return d


def receiver_games(conn, seasons=SEASONS) -> dict:
    """{(season, team, week): {player: {"targets", "receptions", "rec_yds", "opp"}}}."""
    out: dict = defaultdict(dict)
    marks = ",".join("?" * len(seasons))
    for r in conn.execute(
            f"SELECT season, period, player, team, opponent, market, value FROM player_game_logs "
            f"WHERE sport='nfl' AND position='WR' AND market IN ('targets','receptions','rec_yds') "
            f"AND season IN ({marks})", tuple(seasons)):
        try:
            wk = int(str(r[1]).lstrip("0") or 0)
        except ValueError:
            continue
        cell = out[(int(r[0]), r[3], wk)].setdefault(r[2], {"opp": r[4]})
        cell[r[5]] = _f(r[6])
    return out


def top_corners(def_rows: list[dict]) -> dict:
    """{(team, week): {"name", "targets", "rating"}} — each defence's most-
    targeted defender over its games BEFORE that week, with his passer
    rating allowed."""
    from .sources.nflscheme import passer_rating
    by: dict = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0]))
    weeks: dict = defaultdict(set)
    for r in def_rows:
        if (r.get("game_type") or "REG") != "REG":
            continue
        team = PFR_TEAM.get(r.get("team") or "", r.get("team") or "")
        wk = int(_f(r.get("week")))
        if not team or wk <= 0:
            continue
        weeks[team].add(wk)
        by[team][(wk, r.get("pfr_player_name") or "")] = [
            _f(r.get("def_targets")), _f(r.get("def_completions_allowed")), _f(r.get("def_yards_allowed")),
            _f(r.get("def_receiving_td_allowed")), _f(r.get("def_ints"))]
    out = {}
    for team, cells in by.items():
        for wk in sorted(weeks[team]) + [max(weeks[team]) + 1]:
            sums: dict = defaultdict(lambda: [0.0] * 5)
            for (w, name), v in cells.items():
                if w < wk:
                    sums[name] = [a + b for a, b in zip(sums[name], v)]
            if not sums:
                continue
            name, (t, c, y, td, i) = max(sums.items(), key=lambda kv: kv[1][0])
            out[(team, wk)] = {"name": name, "targets": t, "rating": passer_rating(t, c, y, td, i)}
    return out


def samples(games: dict, corners: dict) -> list[dict]:
    """One row per WR1/WR2 game: his rank, catch and yards ratios against
    his own baseline, and whether the opponent's top corner was elite."""
    history: dict = defaultdict(list)            # player -> [(season, week, rec, yds)]
    season_tgts: dict = defaultdict(lambda: defaultdict(list))   # (season, team) -> player -> targets
    out = []
    for (season, team, wk) in sorted(games, key=lambda k: (k[0], k[2], k[1])):
        players = games[(season, team, wk)]
        prior = season_tgts[(season, team)]
        ranked = sorted((p for p in players if len(prior.get(p, [])) >= 2),
                        key=lambda p: -sum(prior[p]) / len(prior[p]))
        for rank, p in enumerate(ranked[:2], start=1):
            past = history[p][-BASE_GAMES:]
            if len(past) < MIN_PRIOR:
                continue
            cell = players[p]
            base_rec = max(sum(x[2] for x in past) / len(past), MIN_BASE["receptions"])
            base_yds = max(sum(x[3] for x in past) / len(past), MIN_BASE["rec_yds"])
            cb = corners.get((cell.get("opp") or "", wk))
            elite = bool(cb and cb["targets"] >= MIN_DEF_TARGETS and cb["rating"] is not None
                         and cb["rating"] <= ELITE_RATING)
            out.append({"season": season, "rank": rank, "elite": elite,
                        "rec": min(cell.get("receptions", 0.0) / base_rec, RATIO_CAP),
                        "yds": min(cell.get("rec_yds", 0.0) / base_yds, RATIO_CAP)})
        for p, cell in players.items():
            history[p].append((season, wk, cell.get("receptions", 0.0), cell.get("rec_yds", 0.0)))
            prior[p].append(cell.get("targets", cell.get("receptions", 0.0)))
    return out


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def effects(rows: list[dict]) -> dict:
    """{"h1": {...}, "h2": {...}} — each with the effect, the two group
    sizes, and the effect in each half of the seasons."""
    seasons = sorted({r["season"] for r in rows})
    mid = seasons[len(seasons) // 2] if seasons else 0
    halves = (lambda r: r["season"] < mid, lambda r: r["season"] >= mid)

    def h1(rs):
        a = [r["rec"] - r["yds"] for r in rs if r["rank"] == 1 and r["elite"]]
        b = [r["rec"] - r["yds"] for r in rs if r["rank"] == 1 and not r["elite"]]
        return (None if not a or not b else _mean(a) - _mean(b)), len(a)

    def h2(rs):
        a = [r["rec"] for r in rs if r["rank"] == 2 and r["elite"]]
        b = [r["rec"] for r in rs if r["rank"] == 2 and not r["elite"]]
        return (None if not a or not b else _mean(a) - _mean(b)), len(a)

    out = {}
    for key, fn, claim in (("h1", h1, "WR1 keeps catches better than yards against an elite corner"),
                           ("h2", h2, "WR2 catches more when his team faces an elite corner")):
        eff, n = fn(rows)
        parts = [fn([r for r in rows if keep(r)]) for keep in halves]
        proven = bool(eff is not None and all(g is not None and g >= PROVEN_GAP and k >= PROVEN_N
                                              for g, k in parts))
        out[key] = {"claim": claim, "effect": None if eff is None else round(eff, 4), "n_elite": n,
                    "halves": [{"effect": None if g is None else round(g, 4), "n": k} for g, k in parts],
                    "split_at": mid, "proven": proven}
    return out


def measure(conn, seasons=SEASONS, load_def=None) -> dict:
    if load_def is None:
        from .sources.nflscheme import load_pfr_def as load_def
    games = receiver_games(conn, seasons)
    rows = []
    for yr in seasons:
        try:
            def_rows = load_def(int(yr))
        except Exception:                                    # noqa: BLE001
            def_rows = []
        # Corner keys are (team, week) within ONE season.
        rows += samples({k: v for k, v in games.items() if k[0] == yr}, top_corners(def_rows))
    return {"rows": len(rows), "effects": effects(rows)}


def save(res: dict, path=None) -> None:
    import datetime as _dt
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    proven = {k: v for k, v in res["effects"].items() if v["proven"]}
    p.write_text(json.dumps({"version": 1, "proven": proven,
                             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")},
                            indent=1), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.cbfit")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from . import db
    res = measure(db.connect())
    print(f"receiver games measured: {res['rows']:,} (WR1 and WR2, 2021+)")
    for key, e in res["effects"].items():
        halves = ", ".join(f"{h['effect']:+.3f} (n {h['n']})" if h["effect"] is not None else f"— (n {h['n']})"
                           for h in e["halves"])
        eff = f"{e['effect']:+.3f}" if e["effect"] is not None else "—"
        print(f"  {key.upper()}  {e['claim']}\n      effect {eff} on {e['n_elite']} elite-corner games; "
              f"halves split at {e['split_at']}: {halves}  → {'PROVEN' if e['proven'] else 'not proven'}")
    if not a.dry_run:
        save(res)
        print("saved; a proven rule earns a history line on the case, never a number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
