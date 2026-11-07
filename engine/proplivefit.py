"""Does the live prop chance tell the truth? Measured on games already played.

Ethan, 2026-10-13: "the hedge calculator and better number and saving
uploaded slips too moneys and live chances for props mid game. Make sure
all of this has been done and will be done and is done for all sports".

engine/proplive puts a number on a prop in play: what the player has
banked, the share of regulation left, and a count distribution held to the
card's pregame chance. That is a model with no fitted parameters and one
stated assumption — the rest of his game runs at his pregame rate, the
first half telling it nothing beyond the number he banked. This replays
it on finished games and says how honest it is.

THE REPLAY. Every player-game where the player had a prop-sized role (his
recent average over the floor in FLOORS), stopped at each break:

  NFL  end of the first quarter, halftime, end of the third — off the
       nflverse play-by-play the ingest already caches
       (engine/sources/nflpbp), 2023-2025 by default: receiving yards,
       catches, rushing yards, carries, passing yards, attempts,
       completions.
  NHL  end of the first and second periods — shots on goal, the split off
       the stored shots (nhl_shots, engine/sources/nhlpbp) and the final
       off the stored box line (player_game_logs), so a game he took no
       shot in still counts.

At each stop the SHIPPING FUNCTION is asked (proplive.clock_chance, the one
the parlay checker calls) for the over at a line set where a book would
hang it — his recent average, rounded to the half below — and the answer
is scored against how the game ended.

THE PREGAME NUMBER IS A STAND-IN, said plainly. The live chance is held to
the card's pregame chance, and the cards of three seasons ago were not
kept for every player-game. So the stand-in is his last eight games: their
average is the mean, their spread the dispersion. It is a weaker pregame
number than the board's, which makes the KICKOFF chance worse here than in
production and leaves the question this answers — how the chance moves
from kickoff as the game is played — the same.

WHAT IT REPORTS, per market and stop:

  ours     the shipping model: banked + the rest at his pregame rate
  pregame  the kickoff chance, unchanged — what the slip said before the
           live chance existed (a number in play beats this or it is noise)
  pace     the rest at THIS game's rate so far — the opposite assumption
  blend    halfway between the two rates

as Brier scores (lower is better) and log loss, and the shipping model's
calibration — of the times it said 70-80%, how often the over landed. If
`blend` beats `ours`, the first half carries information about the second
beyond the banked number; that is a finding to put in front of Ethan, not
a change this makes. Nothing here writes a parameter anywhere.

THE NHL HALF needs the shots table filled (`ingest.py nhl-shots`); a box
without it reports the NFL half and says so.

    python3 -m engine.proplivefit                         # NFL 2023-2025
    python3 -m engine.proplivefit --sport nhl
    python3 -m engine.proplivefit --seasons 2024 2025 --json data/proplivefit.json

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from engine import proplive as PL

#: Where each replay stops: (label, the last period banked, share of
#: regulation left after it).
NFL_STOPS = (("end of Q1", 1, 0.75), ("halftime", 2, 0.5), ("end of Q3", 3, 0.25))
NHL_STOPS = (("end of P1", 1, 2.0 / 3.0), ("end of P2", 2, 1.0 / 3.0))

#: The pregame stand-in: his last WINDOW games, and none at all with fewer
#: than MIN_GAMES behind him.
WINDOW = 8
MIN_GAMES = 4

#: A recent average under this is not a role a book hangs a prop on.
FLOORS = {"rec_yds": 20.0, "receptions": 2.0, "rush_yds": 25.0, "rush_att": 7.0,
          "pass_yds": 150.0, "pass_att": 20.0, "pass_cmp": 13.0, "sog": 1.5}

NFL_MARKETS = ("rec_yds", "receptions", "rush_yds", "rush_att", "pass_yds", "pass_att", "pass_cmp")
NFL_SEASONS = (2023, 2024, 2025)
#: The play-by-play columns read beyond nflpbp.NEEDED.
NFL_COLUMNS = ("passing_yards", "receiving_yards", "rushing_yards", "pass_attempt",
               "rush_attempt", "two_point_attempt")

CAL_BINS = 10


def _f(v) -> float:
    try:
        if v in (None, "", "NA"):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---- the games ----------------------------------------------------------------
def nfl_play_stats(row: dict) -> list[tuple[str, str, float]]:
    """[(player, market, amount)] that one play-by-play row adds. A
    two-point try counts toward no stat; a sack is no pass attempt."""
    if _f(row.get("two_point_attempt")) >= 1:
        return []
    out: list[tuple[str, str, float]] = []
    kind = str(row.get("play_type") or "")
    passer = str(row.get("passer_player_name") or "")
    receiver = str(row.get("receiver_player_name") or "")
    rusher = str(row.get("rusher_player_name") or "")
    complete = _f(row.get("complete_pass")) >= 1
    if kind == "pass" and passer and _f(row.get("sack")) < 1:
        if row.get("pass_attempt") in (None, "", "NA") or _f(row.get("pass_attempt")) >= 1:
            out.append((passer, "pass_att", 1.0))
        if complete:
            out.append((passer, "pass_cmp", 1.0))
            yds = row.get("passing_yards")
            out.append((passer, "pass_yds", _f(yds if yds not in (None, "", "NA") else row.get("yards_gained"))))
    if kind == "pass" and receiver:
        # A target that falls incomplete adds nothing — and still puts him
        # in the game, so a no-catch afternoon counts as the zero it is.
        yds = row.get("receiving_yards")
        out.append((receiver, "receptions", 1.0 if complete else 0.0))
        out.append((receiver, "rec_yds", _f(yds if yds not in (None, "", "NA") else row.get("yards_gained"))
                    if complete else 0.0))
    if kind == "run" and rusher:
        out.append((rusher, "rush_att", 1.0))
        yds = row.get("rushing_yards")
        out.append((rusher, "rush_yds", _f(yds if yds not in (None, "", "NA") else row.get("yards_gained"))))
    return out


def nfl_games(rows) -> dict:
    """{(game_id, player): {market: {"final": v, "periods": {q: v}}}} off
    play-by-play rows. The game id ("2024_05_KC_NO") orders a player's
    games; overtime (quarter 5) counts toward the final, as a bet does."""
    acc: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for row in rows:
        gid = str(row.get("game_id") or "")
        try:
            q = int(_f(row.get("qtr")))
        except (TypeError, ValueError):
            continue
        if not gid or q < 1:
            continue
        for player, market, amount in nfl_play_stats(row):
            acc[(gid, player)][market][q] += amount
    out: dict = {}
    for key, markets in acc.items():
        out[key] = {m: {"final": sum(per.values()), "periods": dict(per)} for m, per in markets.items()}
    return out


def nhl_games(box_rows, shot_rows) -> dict:
    """{(date, player): {"sog": {"final", "periods"}}} — the final off the
    box line (so a game with no shot still counts), the period split off
    the stored shots, matched on the date and the name. A game whose
    shots were never stored for his team is left out: its split would
    read as nothing banked."""
    from engine.sources.oddsapi import normalize_name
    shots: dict = defaultdict(lambda: defaultdict(float))
    stored: set = set()
    for date, team, shooter, period in shot_rows:
        stored.add((str(date), str(team or "")))
        try:
            shots[(str(date), normalize_name(str(shooter or "")))][int(period)] += 1.0
        except (TypeError, ValueError):
            continue
    out: dict = {}
    for date, team, player, value in box_rows:
        if (str(date), str(team or "")) not in stored:
            continue
        per = dict(shots.get((str(date), normalize_name(str(player or ""))), {}))
        out[(str(date), str(player))] = {"sog": {"final": _f(value), "periods": per}}
    return out


# ---- the replay ---------------------------------------------------------------
def _stand_in(history: list[float]) -> tuple[float, float] | None:
    """(mean, SD) of his last games, or None with too few."""
    if len(history) < MIN_GAMES:
        return None
    h = history[-WINDOW:]
    mean = sum(h) / len(h)
    var = sum((v - mean) ** 2 for v in h) / (len(h) - 1)
    return mean, math.sqrt(max(var, 0.0))


def replay(games: dict, stops, markets=None) -> list[dict]:
    """One row per player-game, market and stop: the four arms' chances
    for the over and whether it landed."""
    seqs: dict = defaultdict(list)
    for (order, player), by_market in games.items():
        for market, g in by_market.items():
            if markets is None or market in markets:
                seqs[(player, market)].append((order, g))
    out: list[dict] = []
    for (player, market), seq in seqs.items():
        seq.sort(key=lambda x: x[0])
        history: list[float] = []
        for order, g in seq:
            final = float(g["final"])
            got = _stand_in(history)
            history.append(final)
            if got is None:
                continue
            mean, sd = got
            if mean < FLOORS.get(market, 0.0) or mean <= 0:
                continue
            row = {"projection": mean, "proj_std": sd}
            disp = PL.dispersion(row, market)
            line = math.floor(mean) + 0.5
            p0 = PL.p_over_full(line, mean, disp)
            hit = 1 if final > line else 0
            for label, last, share in stops:
                banked = sum(v for q, v in g["periods"].items() if q <= last)
                leg = {"market": market, "side": "over", "line": line, "prob": p0, "row": row,
                       "live": {"state": "live", "share_left": share, "current": banked}}
                ours = PL.clock_chance(leg, row)
                if ours is None:
                    continue
                pace_mean = banked / (1.0 - share) if share < 1.0 else mean
                blend_mean = 0.5 * mean + 0.5 * pace_mean
                pace, _ = PL.race("over", line, banked, share, pace_mean, disp)
                blend, _ = PL.race("over", line, banked, share, blend_mean, disp)
                out.append({"market": market, "stop": label, "player": player, "game": order,
                            "ours": ours["p"], "pregame": p0, "pace": pace, "blend": blend, "hit": hit})
    return out


# ---- the score ----------------------------------------------------------------
ARMS = ("ours", "pregame", "pace", "blend")


def _clamp(p: float) -> float:
    return min(1.0 - 1e-6, max(1e-6, float(p)))


def score(rows: list[dict]) -> dict:
    """{market: {stop: {n, rate, brier: {arm}, logloss, calibration}}}."""
    groups: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        groups[r["market"]][r["stop"]].append(r)
    out: dict = {}
    for market, stops in groups.items():
        out[market] = {}
        for stop, rs in stops.items():
            n = len(rs)
            brier = {a: round(sum((r[a] - r["hit"]) ** 2 for r in rs) / n, 4) for a in ARMS}
            ll = -sum(math.log(_clamp(r["ours"])) if r["hit"] else math.log(1.0 - _clamp(r["ours"]))
                      for r in rs) / n
            out[market][stop] = {"n": n, "rate": round(sum(r["hit"] for r in rs) / n, 4),
                                 "brier": brier, "logloss": round(ll, 4),
                                 "calibration": calibration(rs)}
    return out


def calibration(rows: list[dict], arm: str = "ours") -> list[dict]:
    """Of the times the arm said 70-80%, how often the over landed — one
    row per tenth of the scale that has any."""
    bins: dict = defaultdict(list)
    for r in rows:
        bins[min(CAL_BINS - 1, int(float(r[arm]) * CAL_BINS))].append(r)
    out = []
    for b in sorted(bins):
        rs = bins[b]
        out.append({"from": b / CAL_BINS, "to": (b + 1) / CAL_BINS, "n": len(rs),
                    "said": round(sum(r[arm] for r in rs) / len(rs), 4),
                    "landed": round(sum(r["hit"] for r in rs) / len(rs), 4)})
    return out


def report(scored: dict, title: str) -> str:
    """The table a person reads."""
    lines = [title, ""]
    for market in sorted(scored):
        stops = scored[market]
        n = max(v["n"] for v in stops.values())
        lines.append(f"{market}  ({n:,} player-games; the line is his recent average rounded to the half below)")
        lines.append("  stop          n       over%   Brier: ours  pregame  pace    blend   log loss")
        for stop, v in stops.items():
            b = v["brier"]
            lines.append(f"  {stop:<12}{v['n']:>7,}   {v['rate']:>6.1%}   {b['ours']:>10.4f}  {b['pregame']:.4f}  "
                         f"{b['pace']:.4f}  {b['blend']:.4f}  {v['logloss']:.4f}")
        for stop, v in stops.items():
            cal = " · ".join(f"{c['from']:.0%}-{c['to']:.0%}: {c['landed']:.0%} of {c['n']}"
                             for c in v["calibration"] if c["n"] >= 20)
            if cal:
                lines.append(f"  calibration, {stop}: {cal}")
        lines.append("")
    lines.append("Brier: lower is better. 'ours' is the shipping model; 'pregame' the kickoff chance unchanged;")
    lines.append("'pace' the rest at this game's rate; 'blend' halfway. Calibration: of the times we said")
    lines.append("that range, how often the over landed. Nothing here changes the model.")
    return "\n".join(lines)


# ---- the sources --------------------------------------------------------------
def load_nfl(seasons, rows_for=None) -> dict:
    """Every season's play-by-play, folded into player-games. ``rows_for``
    stands in for the cached CSV reader in tests."""
    if rows_for is None:
        from engine.sources import nflpbp

        def rows_for(season):
            return nflpbp.load_pbp_rows(season, columns=NFL_COLUMNS)
    games: dict = {}
    for season in seasons:
        try:
            games.update(nfl_games(rows_for(season)))
        except Exception as exc:                            # noqa: BLE001
            print(f"  {season}: play-by-play unavailable ({type(exc).__name__}: {exc})", file=sys.stderr)
    return games


def load_nhl(conn, seasons=None) -> dict:
    """The stored box lines and shots, folded into player-games."""
    q_box = "SELECT period, team, player, value FROM player_game_logs WHERE sport='nhl' AND market='sog'"
    q_shot = "SELECT date, team, shooter, period FROM nhl_shots WHERE kind IN ('sog', 'goal')"
    args: list = []
    if seasons:
        marks = ",".join("?" * len(seasons))
        q_box += f" AND season IN ({marks})"
        q_shot += f" AND season IN ({marks})"
        args = list(seasons)
    box = conn.execute(q_box, args).fetchall()
    shots = conn.execute(q_shot, args).fetchall()
    return nhl_games(box, shots)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay the live prop chance on finished games.")
    ap.add_argument("--sport", choices=("nfl", "nhl"), default="nfl")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--json", default="", help="also write the scores here")
    args = ap.parse_args(argv)
    if args.sport == "nfl":
        seasons = args.seasons or list(NFL_SEASONS)
        games = load_nfl(seasons)
        rows = replay(games, NFL_STOPS, NFL_MARKETS)
        title = f"Live prop chance, NFL {', '.join(map(str, seasons))}"
    else:
        import sqlite3
        from engine.db import DEFAULT_DB
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            games = load_nhl(conn, args.seasons)
        except sqlite3.OperationalError as exc:
            print(f"NHL tables not readable here: {exc}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        rows = replay(games, NHL_STOPS, ("sog",))
        title = "Live prop chance, NHL shots on goal" + (f" {args.seasons}" if args.seasons else "")
    if not rows:
        print("Nothing to replay: no player-games with enough history (is the data on this box?).")
        return 1
    scored = score(rows)
    print(report(scored, title))
    if args.json:
        Path(args.json).write_text(json.dumps({"title": title, "scores": scored}, indent=1))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
