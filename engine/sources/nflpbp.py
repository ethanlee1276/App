"""NFL play-by-play → real xFP, red-zone usage, and PROE.

The weekly-stats file says HOW MUCH a player was used; play-by-play says
WHERE. Two backs with 200 carries each are different bets when one's came
from his own 20 and the other's from the opponent's 1 — raw volume can't
see that, expected fantasy points can.

From one pass over the season's plays (streamed — the file is ~50k plays
by 370 columns, so rows are reduced to the handful of fields we need):

* a **value table**: average PPR points per opportunity by situation
  bucket (inside-5 / red-zone / open-field carries; red-zone / deep /
  short targets), fit from the season itself;
* **per player-week**: opportunity counts per bucket → xFP, plus the two
  usage numbers that carry TD equity (red-zone targets, inside-5 carries);
* **per team-week**: plays and pass rate over expectation — nflfastR ships
  ``pass_oe`` per play, so PROE is a clean average of intent vs situation.

Free nflverse release data, cached a day; everything degrades to a
reported skip when unreachable.
"""

from __future__ import annotations

import csv
import io

from .fetch import fetch_text, DataUnavailable

NEEDED = ("week", "posteam", "play_type", "yardline_100", "air_yards",
          "complete_pass", "yards_gained", "rush_touchdown", "pass_touchdown",
          "rusher_player_name", "receiver_player_name", "pass_oe")

CARRY_BUCKETS = ("car_i5", "car_rz", "car_open")
TARGET_BUCKETS = ("tgt_rz", "tgt_deep", "tgt_short")


def _pbp_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download/pbp"
    return [f"{base}/play_by_play_{season}.csv.gz",
            f"{base}/play_by_play_{season}.csv"]


def load_pbp_rows(season: int):
    """Yield minimal per-play dicts for a season (streamed from the cached
    CSV; the 370-column rows never materialize as dicts)."""
    last = None
    text = None
    for url in _pbp_urls(season):
        try:
            text = fetch_text(url, f"pbp_{season}.csv", ttl=86400, timeout=300)
            break
        except DataUnavailable as exc:
            last = exc
    if text is None:
        raise last or DataUnavailable(f"pbp {season} unavailable")
    rdr = csv.reader(io.StringIO(text))
    header = next(rdr)
    idx = {c: header.index(c) for c in NEEDED if c in header}
    for row in rdr:
        try:
            yield {c: row[i] for c, i in idx.items()}
        except IndexError:
            continue


def _f(v, default=0.0):
    try:
        if v in (None, "", "NA"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _carry_bucket(yl: float) -> str:
    return "car_i5" if yl <= 5 else "car_rz" if yl <= 20 else "car_open"


def _target_bucket(yl: float, air: float) -> str:
    return "tgt_rz" if yl <= 20 else "tgt_deep" if air >= 15 else "tgt_short"


def aggregate_pbp(rows) -> dict:
    """One pass: situation value table + player-week buckets + team PROE."""
    bucket_pts: dict[str, list] = {b: [0.0, 0] for b in CARRY_BUCKETS + TARGET_BUCKETS}
    players: dict[tuple, dict] = {}
    teams: dict[tuple, list] = {}

    for r in rows:
        try:
            wk = int(_f(r.get("week")))
        except ValueError:
            continue
        if wk <= 0:
            continue
        team = r.get("posteam") or ""
        ptype = r.get("play_type") or ""
        yl = _f(r.get("yardline_100"), 100.0)

        if ptype in ("run", "pass") and team:
            t = teams.setdefault((team, wk), [0, 0.0, 0])
            t[0] += 1
            oe = r.get("pass_oe")
            if oe not in (None, "", "NA"):
                t[1] += _f(oe)
                t[2] += 1

        if ptype == "run" and r.get("rusher_player_name"):
            b = _carry_bucket(yl)
            pts = 0.1 * _f(r.get("yards_gained")) + 6.0 * _f(r.get("rush_touchdown"))
            bucket_pts[b][0] += pts
            bucket_pts[b][1] += 1
            p = players.setdefault((r["rusher_player_name"], team, wk), {})
            p[b] = p.get(b, 0) + 1
        elif ptype == "pass" and r.get("receiver_player_name"):
            b = _target_bucket(yl, _f(r.get("air_yards")))
            comp = _f(r.get("complete_pass"))
            pts = comp * (1.0 + 0.1 * _f(r.get("yards_gained"))) \
                + 6.0 * _f(r.get("pass_touchdown"))
            bucket_pts[b][0] += pts
            bucket_pts[b][1] += 1
            p = players.setdefault((r["receiver_player_name"], team, wk), {})
            p[b] = p.get(b, 0) + 1

    values = {b: round(s / n, 4) if n >= 30 else None
              for b, (s, n) in bucket_pts.items()}
    return {"values": values, "players": players, "teams": teams}


def xfp_player_rows(agg: dict, season: int) -> list[dict]:
    """player_game_logs rows for markets xfp / rz_tgt / i5_car.

    Player names in pbp are abbreviated ("P.Mahomes") — the fantasy layer
    joins them to weekly-stat names by normalized form, so rows carry the
    pbp name as-is."""
    values = agg["values"]
    out = []
    for (player, team, wk), buckets in agg["players"].items():
        xfp = 0.0
        priced = True
        for b, n in buckets.items():
            v = values.get(b)
            if v is None:
                priced = False
                break
            xfp += n * v
        base = {"sport": "nfl", "season": season, "period": f"{wk:03d}",
                "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
                "opponent": "", "position": "", "home": 1}
        if priced:
            out.append({**base, "market": "xfp", "value": round(xfp, 2)})
        out.append({**base, "market": "rz_tgt",
                    "value": float(buckets.get("tgt_rz", 0))})
        out.append({**base, "market": "i5_car",
                    "value": float(buckets.get("car_i5", 0))})
        # ALL red-zone carries (inside-20, the inside-5s included) — the
        # touchdown model's measured-role input alongside rz_tgt/i5_car.
        out.append({**base, "market": "rz_car",
                    "value": float(buckets.get("car_i5", 0)
                                   + buckets.get("car_rz", 0))})
    return out


def team_week_rows(agg: dict, season: int) -> list[dict]:
    out = []
    for (team, wk), (plays, oe_sum, oe_n) in agg["teams"].items():
        out.append({"sport": "nfl", "season": season, "period": f"{wk:03d}",
                    "team": team, "plays": plays,
                    "proe": round(oe_sum / oe_n, 4) if oe_n >= 20 else None})
    return out
