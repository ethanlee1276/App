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
* **per team-week**: plays, pass rate over expectation (nflfastR ships
  ``pass_oe`` per play, so PROE is a clean average of intent vs situation),
  **EPA per play** on offense (with pass/rush splits) and allowed on
  defense — the spec's efficiency layer, measured instead of inferred from
  box scores — and **neutral pace** (seconds between snaps with the game
  still in the balance: win probability 20–80%, first three quarters),
  the stable half of a totals/environment read.

Free nflverse release data, cached a day; everything degrades to a
reported skip when unreachable.
"""

from __future__ import annotations

import csv
import io

from .fetch import fetch_text, DataUnavailable

NEEDED = ("week", "posteam", "play_type", "yardline_100", "air_yards",
          "complete_pass", "yards_gained", "rush_touchdown", "pass_touchdown",
          "rusher_player_name", "receiver_player_name", "pass_oe",
          "game_id", "defteam", "epa", "wp", "qtr", "game_seconds_remaining")

# Neutral-pace guards: only snaps with the game in the balance (win prob
# 20–80%, quarters 1–3), and only believable snap-to-snap gaps — under 4s
# is a penalty replay artifact, over 45s spans a drive change or timeout.
PACE_WP = (0.20, 0.80)
PACE_GAP_S = (4.0, 45.0)

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


def _new_team() -> dict:
    return {"plays": 0, "oe": [0.0, 0], "epa": [0.0, 0],
            "pass_epa": [0.0, 0], "rush_epa": [0.0, 0], "pace": [0.0, 0]}


def aggregate_pbp(rows) -> dict:
    """One pass: situation value table + player-week buckets + team
    PROE / EPA (both sides of the ball) / neutral pace."""
    bucket_pts: dict[str, list] = {b: [0.0, 0] for b in CARRY_BUCKETS + TARGET_BUCKETS}
    players: dict[tuple, dict] = {}
    teams: dict[tuple, dict] = {}
    defense: dict[tuple, list] = {}
    last_snap: dict[tuple, float] = {}     # (game_id, posteam) → seconds left

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
            t = teams.setdefault((team, wk), _new_team())
            t["plays"] += 1
            oe = r.get("pass_oe")
            if oe not in (None, "", "NA"):
                # nflfastR ships pass_oe in PERCENTAGE POINTS (league avg
                # ≈ -2.3); everything downstream speaks fractions.
                t["oe"][0] += _f(oe) / 100.0
                t["oe"][1] += 1
            epa = r.get("epa")
            if epa not in (None, "", "NA"):
                v = _f(epa)
                t["epa"][0] += v
                t["epa"][1] += 1
                split = t["pass_epa"] if ptype == "pass" else t["rush_epa"]
                split[0] += v
                split[1] += 1
                dt = r.get("defteam") or ""
                if dt:
                    d = defense.setdefault((dt, wk), [0.0, 0])
                    d[0] += v
                    d[1] += 1
            # Neutral pace: gap to this team's PREVIOUS snap in the same
            # game, counted only while the game is in the balance.
            gid = r.get("game_id") or ""
            secs = _f(r.get("game_seconds_remaining"), -1.0)
            if gid and secs >= 0:
                wp = _f(r.get("wp"), -1.0)
                qtr = _f(r.get("qtr"), 5.0)
                prev = last_snap.get((gid, team))
                if (prev is not None and PACE_WP[0] <= wp <= PACE_WP[1]
                        and qtr <= 3):
                    gap = prev - secs
                    if PACE_GAP_S[0] <= gap <= PACE_GAP_S[1]:
                        t["pace"][0] += gap
                        t["pace"][1] += 1
                last_snap[(gid, team)] = secs

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
    return {"values": values, "players": players, "teams": teams,
            "defense": defense}


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


def _avg(pair, min_n):
    s, n = pair
    return round(s / n, 4) if n >= min_n else None


def team_week_rows(agg: dict, season: int) -> list[dict]:
    """team_weeks rows: volume + intent (PROE) + efficiency (EPA, both
    sides) + neutral pace. Minimum sample per stat, else NULL — a two-play
    week must not print an "EPA"."""
    out = []
    defense = agg.get("defense", {})
    # Union of both sides: in real data every team that defends also ran
    # offense that week, but the row must not silently vanish if not.
    for team, wk in sorted(set(agg["teams"]) | set(defense)):
        t = agg["teams"].get((team, wk)) or _new_team()
        out.append({
            "sport": "nfl", "season": season, "period": f"{wk:03d}",
            "team": team, "plays": t["plays"],
            "proe": _avg(t["oe"], 20),
            "off_epa": _avg(t["epa"], 20),
            "pass_epa": _avg(t["pass_epa"], 10),
            "rush_epa": _avg(t["rush_epa"], 8),
            "def_epa": _avg(defense.get((team, wk), [0.0, 0]), 20),
            "pace": _avg(t["pace"], 8),
        })
    return out
