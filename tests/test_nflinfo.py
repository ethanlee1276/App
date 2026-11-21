"""The NFL information test: does any input beat the close?

Ethan, 2026-09-07: "start working on what u think we should put effort
into. I just want a wining nfl model for our best bets AND edge models."

`engine/nflinfo.py` is the instrument. These tests pin what makes its
answer trustworthy — the walk sees only the past, the starter is who
threw, the fitters recover what they are given, the bands are the
spec's — and pin the answer it gave, so the same pond is not fished
again without a reason.

Run directly: `python3 tests/test_nflinfo.py`
"""

import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine import nflinfo as N                              # noqa: E402


def _row(season, week, home, away, hs, as_, ml=(-110, -110), spread=-3.0,
         total=44.0, roof="outdoors", wind=None, temp=None):
    extra = {"ml": list(ml), "spread_odds": [-110, -110], "total_odds": [-110, -110]}
    return {"sport": "nfl", "season": season, "period": f"{week:03d}",
            "game_id": f"{season}-{week}-{away}@{home}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": spread, "total": total,
            "roof": roof, "surface": "grass", "temp": temp, "wind": wind,
            "extra": json.dumps(extra)}


def _db(games, logs=(), weeks=()):
    conn = db.connect(":memory:")
    db.upsert_games(conn, games)
    conn.executemany(
        "INSERT INTO player_game_logs (sport, season, period, game_id, player, team, "
        "opponent, position, home, market, value) VALUES ('nfl',?,?,?,?,?,?,?,?,?,?)", logs)
    conn.executemany(
        "INSERT INTO team_weeks (sport, season, period, team, plays, proe, off_epa, "
        "pass_epa, rush_epa, def_epa, pace) VALUES ('nfl',?,?,?,?,?,?,?,?,?,?)", weeks)
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def _season(season, teams=("A", "B", "C", "D"), weeks=8, wind=None):
    """A round of games; A beats everyone, D loses to everyone."""
    games, logs, tw = [], [], []
    order = [("A", "B", "C", "D"), ("A", "C", "B", "D"), ("A", "D", "B", "C")]
    for wk in range(1, weeks + 1):
        h1, a1, h2, a2 = order[wk % 3]
        for h, a in ((h1, a1), (h2, a2)):
            hs, as_ = (30, 10) if h < a else (10, 30)
            games.append(_row(season, wk, h, a, hs, as_, wind=wind))
            for team, opp, pts in ((h, a, hs), (a, h, as_)):
                qb = f"QB-{team}"
                logs += [(season, f"{wk:03d}", f"g{wk}", qb, team, opp, "QB", 1, "pass_att", 30.0),
                         (season, f"{wk:03d}", f"g{wk}", qb, team, opp, "QB", 1, "pass_yds", 240.0)]
                epa = 0.2 if team == "A" else (-0.2 if team == "D" else 0.0)
                tw.append((season, f"{wk:03d}", team, 60, 0.0, epa, epa, epa, -epa, 30.0))
    return games, logs, tw


# --- the walk sees only the past ---------------------------------------------
def test_features_come_from_earlier_weeks_only():
    """A team's EPA rating in week 5 is built from weeks 1-4 of THIS
    season (or last season's while this one is thin) — never from week
    5 itself and never from a later week."""
    games, logs, tw = _season(2024)
    conn = _db(games, logs, tw)
    rows = {(r.season, r.period, r.home, r.away): r for r in N.build_rows(conn)}
    # Week 1 of the first season: no history at all, so no rating features.
    first = next(r for r in rows.values() if r.period == "001")
    assert "epa_diff" not in first.f and "pts_wp" not in first.f
    # A meets D in weeks 2, 5 and 8. By week 8 A's EPA edge is the SHRUNK
    # average of the seven prior weeks: +0.4 net a week for A against
    # −0.4 for D, each times 7/(7+6) — and week 8's own score is not in it.
    late = next(r for r in rows.values() if r.period == "008" and "A" in (r.home, r.away)
                and "D" in (r.home, r.away))
    assert "epa_diff" in late.f
    sign = 1 if late.home == "A" else -1
    assert abs(sign * late.f["epa_diff"] - 0.8 * 7 / 13) < 1e-9, late.f["epa_diff"]


def test_the_starter_is_whoever_threw_the_most_and_a_change_is_noticed():
    games, logs, tw = _season(2024)
    # In week 7 team B starts a backup: he throws 25, the usual man 2.
    logs = [l for l in logs if not (l[1] == "007" and l[4] == "B" and l[3] == "QB-B")]
    logs += [(2024, "007", "g7", "Backup-B", "B", "X", "QB", 1, "pass_att", 25.0),
             (2024, "007", "g7", "Backup-B", "B", "X", "QB", 1, "pass_yds", 150.0),
             (2024, "007", "g7", "QB-B", "B", "X", "QB", 1, "pass_att", 2.0),
             (2024, "007", "g7", "QB-B", "B", "X", "QB", 1, "pass_yds", 10.0)]
    conn = _db(games, logs, tw)
    r = next(r for r in N.build_rows(conn) if r.period == "007" and "B" in (r.home, r.away))
    side = "h" if r.home == "B" else "a"
    assert r.f[f"qb_change_{side}"] == 1.0
    assert r.f[f"qb_starts_{side}"] == 0.0          # his first start
    # The usual starter's own week 6 row still reads as no change.
    r6 = next(r for r in N.build_rows(conn) if r.period == "006" and "B" in (r.home, r.away))
    side6 = "h" if r6.home == "B" else "a"
    assert r6.f[f"qb_change_{side6}"] == 0.0


def test_a_bye_is_the_week_a_team_did_not_play():
    games, logs, tw = _season(2024)
    # Remove team C's week 4 game entirely (and A's, its opponent).
    games = [g for g in games if not (g["period"] == "004" and "C" in (g["home"], g["away"]))]
    conn = _db(games, logs, tw)
    r = next(r for r in N.build_rows(conn) if r.period == "005" and "C" in (r.home, r.away))
    side = "h" if r.home == "C" else "a"
    assert r.f[f"bye_{side}"] == 1.0
    other = "a" if side == "h" else "h"
    assert r.f[f"bye_{other}"] in (0.0, 1.0)


def test_indoor_games_carry_no_wind_and_outdoor_ones_carry_the_recorded_wind():
    games, logs, tw = _season(2024, wind=14)
    games[0]["roof"] = "dome"
    conn = _db(games, logs, tw)
    rows = N.build_rows(conn)
    dome = next(r for r in rows if r.period == "001" and r.home == games[0]["home"])
    assert dome.f["indoor"] == 1.0 and dome.f["wind"] == 0.0
    out = next(r for r in rows if r.f.get("indoor") == 0.0)
    assert out.f["wind"] == 14.0


# --- the fitters --------------------------------------------------------------
def test_the_logistic_fit_recovers_a_planted_slope_with_the_market_as_offset():
    """Outcomes generated from P = sigmoid(offset + 0.8·x) on a symmetric
    design; the fit should land on 0.8 with the market's own log-odds
    held at one."""
    obs = []
    for off in (-0.5, 0.0, 0.5):
        for x in (-1.0, -0.5, 0.5, 1.0):
            p = 1 / (1 + math.exp(-(off + 0.8 * x)))
            # Fractional outcomes are not allowed, so plant the expectation
            # with weights: 100 copies, round(p·100) of them wins.
            wins = round(p * 100)
            obs += [([x], off, 1.0)] * wins + [([x], off, 0.0)] * (100 - wins)
    b, se = N.fit_logistic(obs)
    assert abs(b[0] - 0.8) < 0.03, b
    assert 0 < se[0] < 0.1


def test_the_least_squares_fit_recovers_a_planted_line():
    obs = [([x], 2.0 + 1.5 * x) for x in range(-5, 6)]
    b, se = N.fit_ols(obs)
    assert abs(b[0] - 2.0) < 1e-9 and abs(b[1] - 1.5) < 1e-9
    assert se[1] < 1e-6                                   # a perfect line


# --- the answer ----------------------------------------------------------------
def test_the_wind_bands_are_the_specs_own():
    """NFL_MODEL.md §7: 0–8, 8–12, 12–18, 18–25, 25+. A band chosen after
    looking at the data would be the finding choosing its own test."""
    assert N.WIND_BANDS == ((0, 8), (8, 12), (12, 18), (18, 25), (25, 99))
    spec = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "docs", "NFL_MODEL.md")).read()
    for a, b in ((0, 8), (8, 12), (12, 18), (18, 25)):
        assert f"{a}–{b}" in spec or f"{a}-{b}" in spec, (a, b)


def test_the_measurement_and_its_verdict_are_on_the_record():
    """Nothing held on the test seasons, and the wind rule that paid
    pooled lost on them. Re-measure before touching this; do not tune."""
    src = open(N.__file__).read()
    assert "MEASURED 2026-09-07" in src
    assert "Nothing holds." in src
    assert "ROI −13.2%" in src
    assert "forty-seven in 2024–25" in src
    assert "it is not shipped" in src
    # And nothing in a build reads this module.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("nfl_build.py", "engine/gamebets.py", "engine/likely.py"):
        assert "nflinfo" not in open(os.path.join(root, name)).read(), name


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
