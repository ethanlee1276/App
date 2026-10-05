#!/usr/bin/env python3
"""Can the model sort a market it does not carry yet? — measured.

    python3 marketfit.py                  # the cached 2021-2025 box scores
    python3 marketfit.py 2023 2024 2025   # other seasons (the last is held out)

Ethan, 2026-09-27: "we dont have a market for interceptions, QB over or
under rushing yards, or some other stuff that the ai recommends".

The repo's rule for a new market is measured before added
(sources/nflverse.POSITION_MARKETS, engine/passtd). This is that
measurement, for the markets a book hangs and this board did not carry:

  pass_att    a quarterback's pass attempts        player_pass_attempts
  pass_cmp    his completions                      player_pass_completions
  pass_int    his interceptions (1 or more)        player_pass_interceptions
  rush_att    a back's carries                     player_rush_attempts
  rush_yds    a QUARTERBACK's rushing yards        player_rush_yds (already bought)

plus the markets the board already carries, in the same harness, so the
new figures are read beside known ones rather than against a bar alone.

WALK-FORWARD, HELD OUT. Every game in the last season is projected from
the games before it only (this season and earlier, most recent first):
the passing-touchdown blend — career and last eight averaged, shrunk
toward the league by two notional games — and scored against a
trailing-average line (last five games, rounded to the half like a
book hangs it). The figure is ranking AUC: the chance a game that went
over is ranked above one that went under. Interceptions and passing
touchdowns are scored as one-or-more against a Poisson arm at the rate;
interceptions once more with the opponent's own rate (its games so far)
scaling the arm. Only rows with a real role — three prior games and a
recent role of 15 attempts / 8 carries / 4 targets a game — count, since
those are the men a book prices. A cluster bootstrap gives each figure
its ±.

Measured 2026-09-27 (held-out 2025):

    pass_att    QB   0.707 ± 0.023   n=531
    pass_cmp    QB   0.696 ± 0.023   n=527
    rush_att    RB   0.632 ± 0.023   n=638
    rush_yds    QB   0.616 ± 0.022   n=532     (0.536 in the first, coarser harness)
    rush_yds    RB   0.616 ± 0.023   n=653     same harness: a back ranks no better
    receptions  WR   0.619 ± 0.018   n=1045
    rec_yds     WR   0.603 ± 0.017   n=1107
    pass_td     QB   0.627 ± 0.027   n=539     (engine/passtd's own fit: 0.687)
    pass_int    QB   0.540 ± 0.028   n=539     a coin
    pass_int+opp     0.568 ± 0.026   n=539     still under the bar

So attempts, completions, carries and a quarterback's rushing went on
(engine/models PASS_ATT…, likely.RANK_AUC); interceptions did not. This
harness runs stricter than the one behind likely.RANK_AUC's older
figures (it scores catches at 0.619, not 0.770) — compare within it.

ROUND TWO, 2026-10-05 (Ethan: "QB interceptions … and any other market
we are missing that we can be winning in"). Interceptions get the arms
the first run lacked: his rate PER ATTEMPT times the attempts he is
projected to throw (a man who throws forty is at risk forty times), the
opponent's takeaway rate on top of that, and FTN's interception-worthy
throw rate (engine/sources/ftn, 2022 on) where the charting is cached —
each printed on its own line, so what moved the number is visible. And
the markets the book hangs that this board never asked for, from the
same box scores:

  rush_rec_yds   a back's rushing + receiving yards   player_rush_reception_yds
  pass_rush_yds  a quarterback's passing + rushing    player_pass_rush_reception_yds
  kick_pts       a kicker's points (3 a field goal, 1 a PAT)   player_kicking_points
  fg_made        his field goals                      player_field_goals
  tackles_ast    a defender's tackles + assists       player_tackles_assists

The kicking and tackle columns are in nflverse's newer stats schema; a
cache without them prints "column absent" for those rows rather than a
number. Nothing here moves a shelf — a figure that clears is wired by
hand (odds key, POSITION_MARKETS, RANK_AUC), as the volume markets were.

Reads the nflverse cache only (and the FTN cache when present); writes
nothing.
"""
from __future__ import annotations

import bisect
import csv
import math
import random
import sys
from collections import defaultdict

from engine.sources.fetch import CACHE_DIR

COLS = {"pass_int": "passing_interceptions", "pass_att": "attempts", "pass_cmp": "completions",
        "rush_att": "carries", "rush_yds": "rushing_yards", "receptions": "receptions",
        "pass_td": "passing_tds", "rec_yds": "receiving_yards",
        # THE SUMS (2026-10-05): a tuple is added up; "3*" weights a column.
        "rush_rec_yds": ("rushing_yards", "receiving_yards"),
        "pass_rush_yds": ("passing_yards", "rushing_yards"),
        "kick_pts": ("3*fg_made", "pat_made"), "fg_made": "fg_made",
        "tackles_ast": ("def_tackles_solo", "def_tackle_assists|def_tackles_with_assist")}
#: (market, position, how it is scored): "count1" is one-or-more on a
#: Poisson arm; "ou" is over/under a trailing-average line.
CANDIDATES = [("pass_int", "QB", "count1"), ("pass_td", "QB", "count1"), ("pass_att", "QB", "ou"),
              ("pass_cmp", "QB", "ou"), ("rush_att", "RB", "ou"), ("rush_yds", "QB", "ou"),
              ("rush_yds", "RB", "ou"), ("receptions", "WR", "ou"), ("rec_yds", "WR", "ou"),
              ("rush_rec_yds", "RB", "ou"), ("pass_rush_yds", "QB", "ou"),
              ("kick_pts", "K", "ou"), ("fg_made", "K", "ou"), ("tackles_ast", "DEF", "ou")]
ROLE_COL = {"QB": "attempts", "RB": "carries", "WR": "targets", "K": "kick_att", "DEF": "tackles_ast"}
ROLE_FLOOR = {"QB": 15.0, "RB": 8.0, "WR": 4.0, "K": 2.0, "DEF": 3.0}
#: The box score's defensive positions, read as one role: a book hangs
#: tackles on a linebacker and a safety alike.
DEF_POSITIONS = {"LB", "ILB", "OLB", "MLB", "CB", "S", "SS", "FS", "DB", "DE", "DT", "NT", "DL", "EDGE"}
#: Interceptions per attempt are shrunk toward the league's by this many
#: notional attempts — about three games of a starter's throws.
INT_PRIOR_ATT = 120.0
MIN_GAMES = 3
RECENT, PRIOR, LINE_GAMES = 8, 2, 5
BOOT = 200


def _f(r, k):
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


def _col(r, spec: str) -> float:
    """One column spec: ``"name"``, ``"3*name"`` or ``"a|b"`` (first present)."""
    w = 1.0
    if "*" in spec:
        wt, spec = spec.split("*", 1)
        w = float(wt)
    for name in spec.split("|"):
        if name in r:
            return w * _f(r, name)
    return 0.0


def value(r, mk: str) -> float:
    spec = COLS[mk]
    if isinstance(spec, tuple):
        return sum(_col(r, s) for s in spec)
    return _col(r, spec)


def has_columns(header, mk: str) -> bool:
    spec = COLS[mk]
    specs = spec if isinstance(spec, tuple) else (spec,)
    return all(any(n in header for n in s.split("*")[-1].split("|")) for s in specs)


def position(r) -> str:
    pos = (r.get("position") or "").upper()
    if pos in DEF_POSITIONS or (r.get("position_group") or "").upper() in ("LB", "DB", "DL"):
        return "DEF"
    return pos


def role_value(r, pos: str) -> float:
    col = ROLE_COL.get(pos)
    if col == "kick_att":
        return _f(r, "fg_att") + _f(r, "pat_att")
    if col == "tackles_ast":
        return value(r, "tackles_ast")
    return _f(r, col) if col else 0.0


def int_rate(att_hist: list, int_hist: list, league: dict, prior_att: float = INT_PRIOR_ATT):
    """Interceptions per attempt, career and the last eight averaged,
    shrunk toward the league's rate by ``prior_att`` notional attempts.
    The two histories are the same games, most recent first."""
    n = min(len(att_hist), len(int_hist))
    if n < MIN_GAMES or not league.get("pass_att") or not league.get("pass_int"):
        return None
    lg = league["pass_int"] / league["pass_att"]
    a_all, i_all = sum(att_hist[:n]), sum(int_hist[:n])
    k = min(n, 8)
    a_rec, i_rec = sum(att_hist[:k]), sum(int_hist[:k])
    return ((i_all + lg * prior_att) / (a_all + prior_att) + (i_rec + lg * prior_att) / (a_rec + prior_att)) / 2


def ftn_iw_history(seasons) -> dict:
    """{gsis id: [(season, week, iw, attempts)]} from the cached FTN
    charting, oldest first — {} when the cache is not on this box."""
    out: dict = {}
    try:
        from engine.sources import ftn
        for yr in seasons:
            if yr < ftn.FIRST_SEASON:
                continue
            for pid, weeks in ftn.qb_weeks(ftn.joined(yr, ttl=10 ** 9), yr).items():
                for season, week, c in weeks:
                    out.setdefault(pid, []).append((season, week, int(c.get("iw", 0)), int(c.get("attempts", 0))))
    except Exception as exc:                                       # noqa: BLE001
        print(f"  (FTN charting not read: {exc} — the interception-worthy arm is skipped)")
        return {}
    for v in out.values():
        v.sort()
    return out


def iw_rate_before(hist: list, season: int, week: int, n: int = 8, min_att: float = 100.0):
    """Interception-worthy throws per attempt over the last ``n`` charted
    weeks before (season, week), or None under ``min_att`` attempts."""
    before = [h for h in hist if (h[0], h[1]) < (season, week)][-n:]
    att = sum(h[3] for h in before)
    return sum(h[2] for h in before) / att if att >= min_att else None


def load(seasons) -> list:
    rows = []
    for yr in seasons:
        with open(CACHE_DIR / f"player_stats_{yr}.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("season_type") != "REG":
                    continue
                rows.append((yr, int(r["week"]), r["player_display_name"], position(r), r))
    rows.sort(key=lambda x: (x[0], x[1]))
    return rows


def present(rows) -> set:
    """The candidates whose columns this cache carries."""
    header = set()
    for _yr, _wk, _name, _pos, r in rows[:200]:
        header |= set(r.keys())
    return {mk for mk, _pos, _kind in CANDIDATES if has_columns(header, mk)}


def auc(pairs) -> tuple[float | None, int]:
    """[(score, outcome)] -> P(a hit is ranked above a miss)."""
    pos = [p for p, y in pairs if y]
    neg = sorted(p for p, y in pairs if not y)
    if not pos or not neg:
        return None, len(pairs)
    s = sum(bisect.bisect_left(neg, p) + 0.5 * (bisect.bisect_right(neg, p) - bisect.bisect_left(neg, p))
            for p in pos)
    return s / (len(pos) * len(neg)), len(pairs)


def boot(pairs, reps=BOOT, seed=1) -> float:
    rnd = random.Random(seed)
    got = []
    for _ in range(reps):
        a, _n = auc([rnd.choice(pairs) for _ in pairs])
        if a is not None:
            got.append(a)
    if len(got) < 2:
        return 0.0
    m = sum(got) / len(got)
    return (sum((g - m) ** 2 for g in got) / (len(got) - 1)) ** 0.5


def blend(vals, league) -> float:
    """engine/passtd.projection's shape: career and the last RECENT
    averaged, shrunk toward the league by PRIOR notional games."""
    career = sum(vals) / len(vals)
    window = vals[:RECENT]
    b = (career + sum(window) / len(window)) / 2
    return (b * len(vals) + league * PRIOR) / (len(vals) + PRIOR)


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def league_anchors(rows, held_out, have=None) -> dict:
    acc = defaultdict(list)
    have = have if have is not None else present(rows)
    for yr, _wk, _name, pos, r in rows:
        if yr >= held_out:
            continue
        for mk, want, _kind in CANDIDATES:
            if mk in have and pos == want and role_value(r, pos) >= ROLE_FLOOR[pos]:
                acc[mk].append(value(r, mk))
    return {mk: sum(v) / len(v) for mk, v in acc.items() if v}


def score(rows, held_out, iw: dict | None = None) -> dict:
    have = present(rows)
    league = league_anchors(rows, held_out, have)
    hist: dict = defaultdict(list)
    def_int: dict = defaultdict(list)
    scored: dict = defaultdict(list)
    iw = iw or {}
    for yr, wk, name, pos, r in rows:
        for mk, want, kind in CANDIDATES:
            if pos != want or mk not in league:
                continue
            y = value(r, mk)
            h, rh = hist[(name, mk)], hist[(name, "role")]
            if yr == held_out and len(h) >= MIN_GAMES and len(rh) >= 3 and sum(rh[:3]) / 3 >= ROLE_FLOOR[pos]:
                proj = blend(h, league[mk])
                if kind == "count1":
                    scored[(mk, pos)].append((1 - math.exp(-proj), y >= 1))
                    if mk == "pass_int":
                        od = def_int.get(r.get("opponent_team") or "") or []
                        opp_f = (sum(od[:12]) / len(od[:12])) / league[mk] if len(od) >= 4 else None
                        if opp_f is not None:
                            scored[("pass_int+opp", pos)].append((1 - math.exp(-proj * opp_f), y >= 1))
                        # THE RATE ARMS (round two): per attempt × projected
                        # attempts; the opponent on top; FTN's
                        # interception-worthy rate in place of his own
                        # count where the charting covers him.
                        att = hist[(name, "pass_att")]
                        ratio = int_rate(att, h, league)
                        if ratio is not None and len(att) >= MIN_GAMES and "pass_att" in league:
                            lam = ratio * blend(att, league["pass_att"])
                            scored[("pass_int/att×att", pos)].append((1 - math.exp(-lam), y >= 1))
                            if opp_f is not None:
                                scored[("pass_int/att×att+opp", pos)].append((1 - math.exp(-lam * opp_f), y >= 1))
                            rate_iw = iw_rate_before(iw.get(r.get("player_id") or "", []), yr, wk)
                            if rate_iw is not None and league.get("pass_att"):
                                # Interception-worthy throws that were caught, league-wide,
                                # is what turns an IW rate into an interception rate.
                                lam_iw = rate_iw * IW_TO_INT * blend(att, league["pass_att"])
                                lam_mix = (lam + lam_iw) / 2
                                scored[("pass_int+iw", pos)].append((1 - math.exp(-lam_iw * (opp_f or 1.0)), y >= 1))
                                scored[("pass_int+iw+own", pos)].append((1 - math.exp(-lam_mix * (opp_f or 1.0)), y >= 1))
                else:
                    last = h[:LINE_GAMES]
                    line = max(0.5, round(sum(last) / len(last) * 2) / 2 - 0.5)
                    career = sum(h) / len(h)
                    sd = (sum((v - career) ** 2 for v in h) / max(1, len(h) - 1)) ** 0.5 or 1.0
                    if y != line:
                        scored[(mk, pos)].append((1 - _norm_cdf((line + 0.5 - proj) / sd), y > line))
            h.insert(0, y)
            if mk == "pass_int":
                def_int[r.get("opponent_team") or ""].insert(0, y)
        if pos in ROLE_COL:
            hist[(name, "role")].insert(0, role_value(r, pos))
    return {k: (auc(v)[0], boot(v), len(v), sum(1 for _p, y in v if y) / len(v)) for k, v in scored.items()}


#: Roughly one charted interception-worthy throw in three is picked off
#: (FTN's own published rate, 2022-2024); a scale, not a fit — the arm is
#: ranked, and a constant factor cannot move an AUC.
IW_TO_INT = 0.33


def main(argv) -> int:
    seasons = [int(a) for a in argv] or [2021, 2022, 2023, 2024, 2025]
    rows = load(seasons)
    if not rows:
        print("No cached box scores to measure.")
        return 1
    held = seasons[-1]
    have = present(rows)
    absent = [mk for mk, _p, _k in CANDIDATES if mk not in have]
    print(f"\nRanking AUC, walk-forward, held-out {held} (fitted on nothing — the "
          f"passing-touchdown blend against a trailing-average line)\n")
    for (mk, pos), (a, se, n, base) in sorted(score(rows, held, ftn_iw_history(seasons)).items()):
        if a is None:
            print(f"  {mk:<22}{pos:<4} unscoreable (n={n})")
            continue
        word = "  clears 0.60" if a - se >= 0.60 else "  under the bar" if a + se < 0.60 else "  on the line"
        print(f"  {mk:<22}{pos:<4} AUC {a:.3f} ± {se:.3f}   n={n:<5} hit rate {base:.2f}{word}")
    for mk in absent:
        print(f"  {mk:<22}     column absent in this cache")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
