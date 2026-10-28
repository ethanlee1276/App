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
  the stable half of a totals/environment read; and since 2026-10-20 the
  **turnovers** both ways and the **coaching tendencies** the game report
  writes out (Ethan: "do all of it besides D") — fourth-and-short calls,
  two-point tries, and how often the team passes up or down two scores.

Free nflverse release data, cached a day; everything degrades to a
reported skip when unreachable.
"""

from __future__ import annotations

import csv

from .fetch import fetch_text, DataUnavailable

NEEDED = ("week", "posteam", "play_type", "yardline_100", "air_yards",
          "complete_pass", "yards_gained", "rush_touchdown", "pass_touchdown",
          "rusher_player_name", "receiver_player_name", "pass_oe",
          "game_id", "defteam", "epa", "wp", "qtr", "game_seconds_remaining",
          # The passer's pocket (2026-10-08): his throws with and without
          # a hit, for the clean-pocket completion split on his card.
          "passer_player_name", "qb_hit", "sack",
          # Turnovers and the coaching tendencies (2026-10-20): the game
          # report's season numbers and its coaching section.
          "down", "ydstogo", "punt_attempt", "field_goal_attempt",
          "fourth_down_converted", "two_point_attempt", "two_point_conv_result",
          "interception", "fumble_lost", "fumbled_1_team", "score_differential",
          "qb_dropback", "half_seconds_remaining")

#: The pocket split's player_game_logs markets: attempts and completions
#: on throws when the passer was NOT hit, and when he was (sacks aside —
#: a sack is no throw). PFF's "completion % when kept clean" counts every
#: pressure; the play-by-play records hits and sacks, so this is the
#: free half of it, and the card calls it what it is.
POCKET_MARKETS = ("att_clean", "cmp_clean", "att_hit", "cmp_hit")

# Neutral-pace guards: only snaps with the game in the balance (win prob
# 20–80%, quarters 1–3), and only believable snap-to-snap gaps — under 4s
# is a penalty replay artifact, over 45s spans a drive change or timeout.
PACE_WP = (0.20, 0.80)
PACE_GAP_S = (4.0, 45.0)

#: THE COACHING TENDENCIES, each read where the call is the coach's and
#: not the clock's: never in the last two minutes of a half, never in
#: overtime (two-point tries aside — every one counts, as a box score
#: counts them). A fourth down counts as a go-or-kick decision at this many
#: yards to go or fewer, past his own 30 (``yardline_100`` 70 or less),
#: with his win chance between 10% and 90% — and only when he went for it,
#: punted or tried a field goal (a penalty's replay is not a decision).
GO4_YDS = 2
GO4_YARDLINE = 70
GO4_WP = (0.10, 0.90)
LATE_HALF_S = 120
#: "Up two scores" / "down two scores" for the pass-rate split.
SCRIPT_MARGIN = 8

#: The per-team-week counts the turnovers and the tendencies keep; each
#: is a team_weeks column (engine/db.TEAM_WEEK_COLS).
TENDENCY_KEYS = ("giveaways", "takeaways", "go4_opps", "go4_att", "go4_conv",
                 "two_pt_att", "two_pt_conv", "lead_plays", "lead_pass",
                 "trail_plays", "trail_pass")

CARRY_BUCKETS = ("car_i5", "car_rz", "car_open")
TARGET_BUCKETS = ("tgt_rz", "tgt_deep", "tgt_short")

#: TARGET DEPTH (2026-10-08, from the Bucs-Cowboys research: "4.2 air
#: yards per target", "Lamb works the short and intermediate zones",
#: "Egbuka's deep targets against Porter"). Where a receiver's targets
#: come from, by air yards alone — the conventional cuts: short under 10,
#: intermediate 10-19, deep 20 and more. Counted per player-week beside
#: the xFP buckets (which stay as they are: they are priced), and per
#: defence-week in engine/sources/nflunits (targets and yards allowed in
#: each zone), so a card can say "58% of his targets are short throws;
#: DAL ranks 24th of 32 against them". Shown, not in the number, until
#: engine/scanfit measures it.
MID_AIR = 10.0
DEEP_AIR = 20.0
DEPTH_ZONES = ("short", "mid", "deep")
DEPTH_MARKETS = {"short": "tgt_short", "mid": "tgt_mid", "deep": "tgt_deep"}


def depth_zone(air: float) -> str:
    """short / mid / deep from the air yards of one target."""
    return "deep" if air >= DEEP_AIR else "mid" if air >= MID_AIR else "short"


def _pbp_urls(season: int) -> list[str]:
    base = "https://github.com/nflverse/nflverse-data/releases/download/pbp"
    return [f"{base}/play_by_play_{season}.csv.gz",
            f"{base}/play_by_play_{season}.csv"]


def load_pbp_rows(season: int, columns=None):
    """Yield minimal per-play dicts for a season (streamed from the cached
    CSV; the 370-column rows never materialize as dicts). ``columns``
    widens the default set (`NEEDED`) — the unit ratings ride the same
    read (engine/sources/nflunits.UNIT_COLS)."""
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
    # THE LINES, NOT A StringIO (2026-10-13). A StringIO that is read
    # holds its text as four bytes a character: a season's ~98 MB file
    # peaked at 490 MB, inside a service capped at 1600 MB. The same rows
    # off the split lines peak at 214 MB — checked identical, row for
    # row, on every season 2021-2026.
    lines = text.splitlines(keepends=True)
    text = None
    rdr = csv.reader(lines)
    header = next(rdr)
    want = tuple(dict.fromkeys(tuple(NEEDED) + tuple(columns or ())))
    idx = {c: header.index(c) for c in want if c in header}
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
            "pass_epa": [0.0, 0], "rush_epa": [0.0, 0], "pace": [0.0, 0],
            **{k: 0 for k in TENDENCY_KEYS}}


def _tendencies(r: dict, teams: dict, team: str, wk: int, ptype: str, yl: float) -> None:
    """One play's turnovers and coaching calls into ``teams``."""
    dt = r.get("defteam") or ""
    if team and dt:
        # TURNOVERS on every play, special teams too: an interception is
        # the offense's; a lost fumble is whoever fumbled it (a muffed punt
        # is the return team's, and that team is not the offense).
        if _f(r.get("interception")) == 1:
            teams.setdefault((team, wk), _new_team())["giveaways"] += 1
            teams.setdefault((dt, wk), _new_team())["takeaways"] += 1
        if _f(r.get("fumble_lost")) == 1:
            lost = r.get("fumbled_1_team") or team
            won = dt if lost == team else team
            teams.setdefault((lost, wk), _new_team())["giveaways"] += 1
            teams.setdefault((won, wk), _new_team())["takeaways"] += 1
    if not team or ptype in ("no_play", "qb_kneel", "qb_spike", ""):
        return
    if _f(r.get("two_point_attempt")) == 1:
        # Every try, at any hour: the count is the record a box score keeps.
        t = teams.setdefault((team, wk), _new_team())
        t["two_pt_att"] += 1
        t["two_pt_conv"] += int(str(r.get("two_point_conv_result") or "").lower() == "success")
        return
    if _f(r.get("qtr"), 5.0) > 4 or _f(r.get("half_seconds_remaining"), 0.0) < LATE_HALF_S:
        return
    t = teams.setdefault((team, wk), _new_team())
    down = _f(r.get("down"))
    if down == 4 and _f(r.get("ydstogo"), 99.0) <= GO4_YDS and yl <= GO4_YARDLINE \
            and GO4_WP[0] <= _f(r.get("wp"), -1.0) <= GO4_WP[1]:
        kicked = _f(r.get("punt_attempt")) == 1 or _f(r.get("field_goal_attempt")) == 1
        went = ptype in ("run", "pass") and not kicked
        if kicked or went:
            t["go4_opps"] += 1
            if went:
                t["go4_att"] += 1
                t["go4_conv"] += int(_f(r.get("fourth_down_converted")) == 1)
    if ptype in ("run", "pass") and 1 <= down <= 4:
        sd = r.get("score_differential")
        if sd in (None, "", "NA"):
            return
        side = "lead" if _f(sd) >= SCRIPT_MARGIN else "trail" if _f(sd) <= -SCRIPT_MARGIN else ""
        if side:
            t[f"{side}_plays"] += 1
            t[f"{side}_pass"] += int(_f(r.get("qb_dropback")) == 1)


def aggregate_pbp(rows, also=None) -> dict:
    """One pass: situation value table + player-week buckets + team
    PROE / EPA (both sides of the ball) / neutral pace. ``also`` is called
    with every play first, so a second fold (the unit ratings) shares the
    single read of the file."""
    bucket_pts: dict[str, list] = {b: [0.0, 0] for b in CARRY_BUCKETS + TARGET_BUCKETS}
    players: dict[tuple, dict] = {}
    teams: dict[tuple, dict] = {}
    defense: dict[tuple, list] = {}
    last_snap: dict[tuple, float] = {}     # (game_id, posteam) → seconds left

    for r in rows:
        if also is not None:
            also(r)
        try:
            wk = int(_f(r.get("week")))
        except ValueError:
            continue
        if wk <= 0:
            continue
        team = r.get("posteam") or ""
        ptype = r.get("play_type") or ""
        yl = _f(r.get("yardline_100"), 100.0)
        _tendencies(r, teams, team, wk, ptype, yl)

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

        if ptype == "pass" and r.get("passer_player_name") and _f(r.get("sack")) != 1:
            # A throw (not a sack), hit or not hit: the pocket split.
            q = players.setdefault((r["passer_player_name"], team, wk), {})
            hit = _f(r.get("qb_hit")) == 1
            q["_att_hit" if hit else "_att_clean"] = q.get("_att_hit" if hit else "_att_clean", 0) + 1
            if _f(r.get("complete_pass")) == 1:
                q["_cmp_hit" if hit else "_cmp_clean"] = q.get("_cmp_hit" if hit else "_cmp_clean", 0) + 1
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
            # INSIDE-THE-10 TARGETS, the receiver's goal-line work (Ethan's
            # other model reads St. Brown's and LaPorta's "3 targets inside
            # the 10", 2026-09-27). Kept under an underscore key so it is a
            # count, never an xFP bucket — `xfp_player_rows` prices only the
            # situation buckets.
            if yl <= 10:
                p["_i10_tgt"] = p.get("_i10_tgt", 0) + 1
            # His target depth — a count, never an xFP bucket. A target
            # with no air yards recorded (a throwaway charted to him, a
            # batted ball) is left out rather than called short.
            araw = r.get("air_yards")
            if araw not in (None, "", "NA"):
                dz = "_dep_" + depth_zone(_f(araw))
                p[dz] = p.get(dz, 0) + 1

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
            if b.startswith("_"):
                continue
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
        out.append({**base, "market": "i10_tgt", "value": float(buckets.get("_i10_tgt", 0))})
        # Targets by depth (tgt_short / tgt_mid / tgt_deep), for the
        # receiver's mix on his card (engine/nflusage.depth_mix).
        for z, mk in DEPTH_MARKETS.items():
            out.append({**base, "market": mk, "value": float(buckets.get("_dep_" + z, 0))})
        # The pocket split, for passers only (a row with a throw in it).
        if any(("_" + mk) in buckets for mk in POCKET_MARKETS):
            for mk in POCKET_MARKETS:
                out.append({**base, "market": mk, "value": float(buckets.get("_" + mk, 0))})
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
            **{k: int(t.get(k) or 0) for k in TENDENCY_KEYS},
        })
    return out


# --- whole past seasons ----------------------------------------------------------
def fill_team_weeks(conn, seasons, load=None) -> dict:
    """team_weeks for whole seasons from their play-by-play, one season at a
    time (a season's file is ~100 MB): {season: {"rows", "takeaways"}}, or
    the reason a season was skipped.

    THE BACKFILL (2026-10-28). The turnovers and the coaching tendencies
    have been counted since 2026-10-20, but the nightly refresh reads only
    the current season, so every season before it kept NULL in those
    columns: the defense fit (dstfit.py) measured the league at zero
    takeaways a game, and last season's weeks read as none in this
    season's rates. Everything else in a row comes off the same read, so
    rewriting it whole changes nothing that was already there."""
    from .. import db
    load = load or load_pbp_rows
    out: dict = {}
    for season in seasons:
        try:
            rows = team_week_rows(aggregate_pbp(load(season)), season)
        except DataUnavailable as exc:
            out[season] = str(exc)
            continue
        out[season] = {"rows": db.upsert_team_weeks(conn, rows),
                       "takeaways": sum(int(r.get("takeaways") or 0) for r in rows)}
    return out


def _seasons(spec: str) -> list[int]:
    """2023-2025, 2024 or 2023,2025 → the seasons."""
    out: set = set()
    for part in str(spec).split(","):
        a, _, b = part.strip().partition("-")
        if a:
            out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Write team_weeks (turnovers, coaching tendencies, PROE, EPA, "
                                             "pace) for whole NFL seasons from their play-by-play.")
    ap.add_argument("--team-weeks", required=True, metavar="SEASONS", help="e.g. 2023-2025, 2024 or 2023,2025")
    args = ap.parse_args(argv)
    from .. import db
    conn = db.connect()
    try:
        got = fill_team_weeks(conn, _seasons(args.team_weeks))
    finally:
        conn.close()
    skipped = 0
    for season, r in got.items():
        if isinstance(r, str):
            skipped += 1
            print(f"  {season}: skipped, {r}")
        else:
            per = r["takeaways"] / r["rows"] if r["rows"] else 0.0
            print(f"  {season}: {r['rows']:,} team weeks, {r['takeaways']:,} takeaways ({per:.2f} a team-game)")
    return 1 if skipped or not got else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
