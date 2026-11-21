"""Huddles, play calls and performance: the study behind docs/HUDDLE_RESEARCH.md.

Ethan, 2026-10-31: "how teams huddle up with each other when receiving play
calls ... maybe they can't hear or pick up the call, and that can cause
confusion ... we should run research on that and see if that factors into
anything."

How a team huddles is recorded nowhere public. What the play-by-play does
record is whether each snap came out of a huddle (`no_huddle`), and the
symptoms a call that did not get through would leave: the offense's
pre-snap flags (false start, delay of game, illegal formation, shift,
motion, substitution, too many men), its timeouts away from the end of a
half, and botched snaps (`aborted_play`). (The play clock at the snap would
time the operation directly; nflverse's `play_clock` column is 0 on every
play.) This reads every regular-season snap of the seasons asked for off
the app's own cached reader (engine/sources/nflpbp) and prints the numbers
the page quotes:

  * no huddle against a huddle — in normal game situations (win chance
    20-80%, the first three quarters, not the last two minutes of a half),
    within the same team-season and down-and-distance, after a successful
    play and after an unsuccessful one, and on third down by distance;
  * the offense's pre-snap errors at home and on the road, by kind; its
    timeouts and botched snaps the same way; by venue, and whether a
    venue's number holds from one three-year span to the next; and whether
    home sides at the "noisiest" venues covered more;
  * whether any of it is a team trait (odd weeks against even weeks) and
    whether it tells us anything about an offense's next half-season that
    its efficiency did not.

Standard library only. Run: `python3 tools/huddle_study.py [first last]`
(2021 2026 by default).
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: The offense's own flags before the snap — the ones a call that did not
#: get through would draw.
PRESNAP = frozenset({"False Start", "Delay of Game", "Illegal Formation", "Illegal Shift",
                     "Illegal Motion", "Illegal Substitution", "Offensive Too Many Men on Field"})
COLUMNS = ("no_huddle", "penalty", "penalty_type", "penalty_team", "timeout", "timeout_team",
           "home_team", "away_team", "success", "season_type", "aborted_play", "qb_spike",
           "qb_kneel", "fixed_drive", "spread_line", "result")
#: A normal game situation: neither side close to a lock, before the fourth
#: quarter, and not the hurry-up of a half's last two minutes.
NEUTRAL_WP = (0.20, 0.80)
LATE_HALF_S = 120


def num(v, default=None):
    try:
        return default if v in (None, "", "NA") else float(v)
    except (TypeError, ValueError):
        return default


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def corr(xs, ys) -> float:
    xs, ys = list(xs), list(ys)
    mx, my = mean(xs), mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else float("nan")


def partial(x, y, z) -> float:
    """corr(x, y) with z held fixed."""
    rxy, rxz, ryz = corr(x, y), corr(x, z), corr(y, z)
    den = math.sqrt(max(1e-12, (1 - rxz ** 2) * (1 - ryz ** 2)))
    return (rxy - rxz * ryz) / den


def neutral(r: dict) -> bool:
    q, wp, hs = num(r.get("qtr")), num(r.get("wp")), num(r.get("half_seconds_remaining"))
    return (q is not None and q <= 3 and wp is not None and NEUTRAL_WP[0] <= wp <= NEUTRAL_WP[1]
            and hs is not None and hs > LATE_HALF_S)


def is_snap(r: dict) -> bool:
    """An offensive snap or a flag before one (a no-play), downs 1-4."""
    return bool(r.get("posteam")) and r.get("play_type") in ("run", "pass", "no_play") \
        and num(r.get("down")) in (1, 2, 3, 4)


def is_play(r: dict) -> bool:
    """A run or a pass with an EPA, spikes and kneels aside."""
    return (r.get("play_type") in ("run", "pass") and num(r.get("down")) in (1, 2, 3, 4)
            and num(r.get("epa")) is not None and num(r.get("qb_spike")) != 1 and num(r.get("qb_kneel")) != 1)


def presnap_error(r: dict) -> str:
    """The offense's own pre-snap flag on this row, or ""."""
    kind = r.get("penalty_type") or ""
    if num(r.get("penalty")) == 1 and r.get("penalty_team") == r.get("posteam") and kind in PRESNAP:
        return kind
    return ""


def load(first: int = 2021, last: int = 2026) -> list:
    from engine.sources import nflpbp
    rows = []
    for season in range(first, last + 1):
        for r in nflpbp.load_pbp_rows(season, columns=COLUMNS):
            if r.get("season_type") == "REG":
                r["season"] = season
                rows.append(r)
    return rows


# ─── no huddle ────────────────────────────────────────────────────────────────

def _dist(ytg) -> str:
    return "short" if ytg is not None and ytg <= 3 else "mid" if ytg is not None and ytg <= 7 else "long"


def no_huddle(rows: list) -> dict:
    """No huddle against a huddle, in normal game situations."""
    plays, last = [], {}
    for r in rows:
        if not is_play(r):
            continue
        key = (r.get("game_id"), r.get("fixed_drive"))
        before, last[key] = last.get(key), r
        if neutral(r):
            plays.append({"nh": num(r.get("no_huddle"), 0) == 1, "epa": num(r.get("epa")),
                          "succ": num(r.get("success"), 0), "down": int(num(r.get("down"))),
                          "ytg": num(r.get("ydstogo"), 10), "team": r.get("posteam"),
                          "season": r["season"], "week": int(num(r.get("week"), 0)),
                          "prev": None if before is None else num(before.get("success"), 0)})

    def split(sel):
        nh = [p for p in sel if p["nh"]]
        hu = [p for p in sel if not p["nh"]]
        return {"nh_n": len(nh), "nh_epa": mean(p["epa"] for p in nh), "nh_succ": mean(p["succ"] for p in nh),
                "hu_n": len(hu), "hu_epa": mean(p["epa"] for p in hu), "hu_succ": mean(p["succ"] for p in hu)}

    # The same team-season, down and distance: no huddle minus huddle,
    # weighted by the smaller side of each cell.
    cells = defaultdict(lambda: ([], []))
    for p in plays:
        cells[(p["season"], p["team"], p["down"], _dist(p["ytg"]))][0 if p["nh"] else 1].append(p["epa"])
    num_, den = 0.0, 0
    for nh, hu in cells.values():
        if len(nh) >= 3 and hu:
            w = min(len(nh), len(hu))
            num_ += (mean(nh) - mean(hu)) * w
            den += w
    out = {"all": split(plays), "within": num_ / den if den else float("nan"), "within_weight": den,
           "after_success": split([p for p in plays if p["prev"] == 1]),
           "after_failure": split([p for p in plays if p["prev"] == 0]),
           "followed_success": (mean(1.0 if p["prev"] == 1 else 0.0 for p in plays if p["nh"] and p["prev"] is not None),
                                mean(1.0 if p["prev"] == 1 else 0.0 for p in plays if not p["nh"] and p["prev"] is not None)),
           "first_after_success": split([p for p in plays if p["down"] == 1 and p["prev"] == 1]),
           "short": split([p for p in plays if p["ytg"] <= 1]),
           "early": split([p for p in plays if p["ytg"] > 1 and p["down"] <= 2]),
           "third": split([p for p in plays if p["ytg"] > 1 and p["down"] == 3]),
           "third_by_dist": {f"{lo}-{hi}": split([p for p in plays if p["down"] == 3 and lo <= p["ytg"] <= hi])
                             for lo, hi in ((2, 3), (4, 6), (7, 10), (11, 99))},
           "by_season": {s: split([p for p in plays if p["season"] == s]) for s in sorted({p["season"] for p in plays})},
           "third_by_season": {s: split([p for p in plays if p["season"] == s and p["down"] == 3 and p["ytg"] > 1])
                               for s in sorted({p["season"] for p in plays})}}
    # A trait? Odd weeks against even weeks, and the next half-season.
    rate = defaultdict(lambda: [0, 0])
    for p in plays:
        c = rate[(p["season"], p["team"], p["week"] % 2)]
        c[0] += int(p["nh"])
        c[1] += 1
    odd = [(k, v) for k, v in rate.items() if k[2] == 1 and v[1] >= 100 and rate[(k[0], k[1], 0)][1] >= 100]
    out["trait_r"] = corr([v[0] / v[1] for _k, v in odd],
                          [rate[(k[0], k[1], 0)][0] / rate[(k[0], k[1], 0)][1] for k, _v in odd])
    return out


# ─── a call that did not get through ─────────────────────────────────────────

def operation(rows: list) -> dict:
    """The offense's pre-snap errors, timeouts and botched snaps, per 100
    snaps, at home and on the road."""
    snaps = {True: 0, False: 0}
    kinds = defaultdict(lambda: {True: 0, False: 0})
    timeouts = {True: 0, False: 0}
    botched = {True: 0, False: 0}
    for r in rows:
        off = r.get("posteam")
        home = off == r.get("home_team")
        if is_snap(r):
            snaps[home] += 1
            kind = presnap_error(r)
            if kind:
                kinds[kind][home] += 1
                kinds["all"][home] += 1
        if num(r.get("aborted_play")) == 1 and off:
            botched[home] += 1
        # The offense's own timeout, away from the two-minute marks: the one
        # a play that will not get in on time costs.
        if num(r.get("timeout")) == 1 and r.get("timeout_team") and r.get("timeout_team") == off \
                and (num(r.get("half_seconds_remaining")) or 0) > LATE_HALF_S and (num(r.get("qtr")) or 9) <= 4:
            timeouts[home] += 1

    def per(d):
        return {side: 100.0 * d[side] / snaps[side] if snaps[side] else float("nan") for side in (True, False)}

    return {"snaps": snaps, "kinds": {k: per(v) for k, v in kinds.items()}, "counts": dict(kinds),
            "timeouts": per(timeouts), "botched": per(botched)}


def venues(rows: list, spans=((2021, 2022, 2023), (2024, 2025, 2026))) -> dict:
    """Visiting offenses' pre-snap errors at each home club's building; how
    well one span's number predicts the next; and the home side's record
    against the spread at the noisiest and quietest eight by the first."""
    def rates(seasons):
        snaps, errs = defaultdict(int), defaultdict(int)
        for r in rows:
            if r["season"] not in seasons or not is_snap(r) or r.get("posteam") == r.get("home_team"):
                continue
            snaps[r.get("home_team")] += 1
            errs[r.get("home_team")] += int(bool(presnap_error(r)))
        return {k: (errs[k], n) for k, n in snaps.items() if n >= 500}

    every = rates({r["season"] for r in rows})
    league = sum(e for e, _n in every.values()) / max(1, sum(n for _e, n in every.values()))
    a, b = rates(set(spans[0])), rates(set(spans[1]))
    both = sorted(set(a) & set(b))
    noisy = sorted(a, key=lambda k: -a[k][0] / a[k][1])[:8]
    quiet = sorted(a, key=lambda k: a[k][0] / a[k][1])[:8]
    games = {}
    for r in rows:
        if r["season"] in spans[1] and r.get("game_id") not in games and r.get("home_team"):
            games[r.get("game_id")] = (r.get("home_team"), num(r.get("spread_line")), num(r.get("result")))

    def covered(hosts):
        won = n = 0
        for home, spread, result in games.values():
            if home in hosts and spread is not None and result is not None and result != spread:
                n += 1
                won += int(result > spread)
        return won, n

    return {"league": league, "by_venue": every,
            "stable_r": corr([a[k][0] / a[k][1] for k in both], [b[k][0] / b[k][1] for k in both]),
            "noisy_ats": covered(set(noisy)), "quiet_ats": covered(set(quiet))}


def stability(rows: list) -> dict:
    """Is an offense's pre-snap error rate its own (odd weeks against even
    weeks), and does it tell anything about the next half-season that its
    efficiency did not (weeks 1-9 against 10 on)?"""
    snaps, errs, fs = defaultdict(int), defaultdict(int), defaultdict(int)
    epa = defaultdict(lambda: [0.0, 0])
    for r in rows:
        if is_snap(r):
            k = (r["season"], r.get("posteam"), int(num(r.get("week"), 0)))
            snaps[k] += 1
            kind = presnap_error(r)
            errs[k] += int(bool(kind))
            fs[k] += int(kind == "False Start")
        if is_play(r):
            e = epa[(r["season"], r.get("posteam"), int(num(r.get("week"), 0)))]
            e[0] += num(r.get("epa"))
            e[1] += 1

    def total(d, team_season, weeks):
        s, t = team_season
        return sum(v for (s2, t2, w), v in d.items() if s2 == s and t2 == t and w in weeks)

    team_seasons = sorted({(s, t) for s, t, _w in snaps})
    odd, even, fodd, feven = [], [], [], []
    first_epa, first_err, second_epa = [], [], []
    for ts in team_seasons:
        no = total(snaps, ts, range(1, 23, 2))
        ne = total(snaps, ts, range(2, 23, 2))
        if no >= 200 and ne >= 200:
            odd.append(total(errs, ts, range(1, 23, 2)) / no)
            even.append(total(errs, ts, range(2, 23, 2)) / ne)
            fodd.append(total(fs, ts, range(1, 23, 2)) / no)
            feven.append(total(fs, ts, range(2, 23, 2)) / ne)
        s, t = ts
        e1 = [v for (s2, t2, w), v in epa.items() if s2 == s and t2 == t and w <= 9]
        e2 = [v for (s2, t2, w), v in epa.items() if s2 == s and t2 == t and w >= 10]
        n1, n2 = sum(v[1] for v in e1), sum(v[1] for v in e2)
        if n1 >= 200 and n2 >= 200:
            first_epa.append(sum(v[0] for v in e1) / n1)
            second_epa.append(sum(v[0] for v in e2) / n2)
            first_err.append(total(errs, ts, range(1, 10)) / max(1, total(snaps, ts, range(1, 10))))
    return {"split_half_r": corr(odd, even), "false_start_r": corr(fodd, feven), "team_seasons": len(odd),
            "next_half_r": corr(first_err, second_epa), "epa_next_half_r": corr(first_epa, second_epa),
            "next_half_partial": partial(first_err, second_epa, first_epa), "halves": len(second_epa)}


# ─── the report ──────────────────────────────────────────────────────────────

def _side(d: dict) -> str:
    return (f"no huddle {d['nh_n']:,} plays, EPA {d['nh_epa']:+.3f}, success {d['nh_succ']:.1%} | "
            f"huddle {d['hu_n']:,}, EPA {d['hu_epa']:+.3f}, success {d['hu_succ']:.1%}")


def report(rows: list) -> list:
    seasons = sorted({r["season"] for r in rows})
    nh, op, ve, stb = no_huddle(rows), operation(rows), venues(rows), stability(rows)
    out = [f"HUDDLES AND PLAY CALLS · regular seasons {seasons[0]}-{seasons[-1]} · "
           f"{sum(op['snaps'].values()):,} offensive snaps",
           "", "No huddle against a huddle (normal game situations):",
           f"  all            {_side(nh['all'])}",
           f"  same team-season and down/distance: no huddle {nh['within']:+.3f} EPA a play",
           f"  after a successful play    {_side(nh['after_success'])}",
           f"  after an unsuccessful play {_side(nh['after_failure'])}",
           f"  share following a successful play: no huddle {nh['followed_success'][0]:.0%}, "
           f"huddle {nh['followed_success'][1]:.0%}",
           f"  1st down right after a success {_side(nh['first_after_success'])}",
           f"  a yard or less to go       {_side(nh['short'])}",
           f"  1st/2nd down, 2+ to go     {_side(nh['early'])}",
           f"  3rd down, 2+ to go         {_side(nh['third'])}"]
    out += [f"    3rd and {k:<6} {_side(v)}" for k, v in nh["third_by_dist"].items()]
    out += [f"    {s}: 3rd down converted without a huddle {v['nh_succ']:.0%} ({v['nh_n']}), "
            f"after a huddle {v['hu_succ']:.0%}" for s, v in nh["third_by_season"].items()]
    out += [f"  a team's no-huddle rate, odd weeks against even: r = {nh['trait_r']:.2f}",
            "", "A call that did not get through (per 100 offensive snaps, home | road):"]
    for kind in ("all", "False Start", "Delay of Game", "Illegal Formation", "Illegal Shift"):
        v = op["kinds"].get(kind)
        if v:
            out.append(f"  {kind:<18} {v[True]:.2f} | {v[False]:.2f}")
    out += [f"  offense timeouts   {op['timeouts'][True]:.2f} | {op['timeouts'][False]:.2f} (away from the two-minute marks)",
            f"  botched snaps      {op['botched'][True]:.2f} | {op['botched'][False]:.2f}",
            "", f"Venues: visiting offenses' pre-snap errors, league {100 * ve['league']:.2f} per 100 snaps"]
    ranked = sorted(ve["by_venue"].items(), key=lambda kv: -kv[1][0] / kv[1][1])
    for home, (e, n) in ranked[:3] + ranked[-3:]:
        z = (e - ve["league"] * n) / math.sqrt(max(1e-9, ve["league"] * n))
        out.append(f"  at {home:<4} {100 * e / n:.2f} ({e} on {n:,} snaps, z {z:+.1f})")
    (w1, n1), (w2, n2) = ve["noisy_ats"], ve["quiet_ats"]
    out += [f"  the same venue, 2021-23 against 2024-26: r = {ve['stable_r']:.2f}",
            f"  home sides at the eight noisiest (by 2021-23) covered {w1}/{n1} in 2024-26 "
            f"({w1 / max(1, n1):.1%}); at the eight quietest {w2}/{n2} ({w2 / max(1, n2):.1%})",
            "", "A team trait, and does it predict?",
            f"  pre-snap error rate, odd weeks against even: r = {stb['split_half_r']:.2f} "
            f"({stb['team_seasons']} team-seasons); false starts alone r = {stb['false_start_r']:.2f}",
            f"  weeks 1-9 error rate against weeks 10+ EPA a play: r = {stb['next_half_r']:.2f}; "
            f"with weeks 1-9 EPA held fixed: {stb['next_half_partial']:+.2f} "
            f"(weeks 1-9 EPA alone: r = {stb['epa_next_half_r']:.2f})"]
    return out


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    first, last = (int(args[0]), int(args[1])) if len(args) >= 2 else (2021, 2026)
    for line in report(load(first, last)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
