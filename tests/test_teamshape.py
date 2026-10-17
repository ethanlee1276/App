"""Team shape (engine/teamshape.py) — the game page's two-team radar.

A radar is only honest when every axis is a measurement on one shared
scale. Defended here:

  * EVERY AXIS POINTS UP. Defense and steadiness are inverted at the
    source, so a higher percentile is always the better shape — a chart
    where one spoke means the opposite of the others is a trap.
  * RANKS, NOT Z-SCORES. One 60-point blowout outlier must not squash
    the league into the middle of the chart.
  * NO SHAPE FROM NOISE. Too few teams or too few games ships nothing,
    and the page keeps its fallback — same posture as every build extra.
  * THE SEASON IS THE LAST RANKABLE ONE, and the panel label carries it.

Run directly: `python3 tests/test_teamshape.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import teamshape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _conn(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, "
                 "home TEXT, away TEXT, home_score INT, away_score INT)")
    conn.executemany("INSERT INTO games VALUES ('nfl', 2025, ?, ?, ?, ?, ?)",
                     rows)
    return conn


def _league(n_teams=6):
    """A FULL double round robin where team T_i always scores 20+2i.

    Balanced on purpose: every team faces every other exactly twice, so
    points allowed is the mean of everyone else's fixed output — which
    falls as your own index rises. Offense AND defense both rank by
    index, deterministically, with no schedule luck in the fixture."""
    rows = []
    teams = [f"T{i}" for i in range(n_teams)]
    day = 0
    for h in teams:
        for a in teams:
            if h == a:
                continue
            day += 1
            rows.append((f"2025-10-{day:02d}", h, a,
                         20 + 2 * int(h[1:]), 20 + 2 * int(a[1:])))
    return rows


def test_every_axis_ranks_up_and_the_best_team_knows_it():
    shapes = teamshape.team_shapes(_conn(_league()), "nfl", 2025)
    assert len(shapes) == 6
    best, worst = shapes["T5"], shapes["T0"]
    assert best["pct"]["offense"] == 100.0
    assert worst["pct"]["offense"] == 0.0
    # Defense is INVERTED at the source: in the balanced fixture your
    # points allowed is the mean of everyone else's fixed output, so the
    # highest index also allows the least. Higher percentile = better
    # shape must hold on this axis too.
    assert best["pct"]["defense"] == 100.0
    assert worst["pct"]["defense"] == 0.0
    # And the raw block reports un-negated, readable units: T5 really
    # does allow FEWER points than T0.
    assert best["raw"]["offense"] > worst["raw"]["offense"]
    assert best["raw"]["defense"] < worst["raw"]["defense"]


def test_a_wild_outlier_cannot_squash_the_league():
    rows = _league()
    # One 70-point massacre for T5. Ranks move one slot at most; a
    # z-score scale would have shoved four teams into the middle.
    rows.append(("2025-11-01", "T5", "T0", 90, 3))
    shapes = teamshape.team_shapes(_conn(rows), "nfl", 2025)
    pcts = sorted(s["pct"]["offense"] for s in shapes.values())
    assert pcts[0] == 0.0 and pcts[-1] == 100.0
    assert pcts[1] >= 20.0, "the outlier compressed everyone else"


def test_too_small_a_league_or_sample_ships_nothing():
    assert teamshape.team_shapes(_conn([]), "nfl", 2025) == {}
    two = [("2025-10-01", "A", "B", 21, 17), ("2025-10-02", "B", "A", 20, 10),
           ("2025-10-03", "A", "B", 27, 13), ("2025-10-04", "B", "A", 30, 3)]
    assert teamshape.team_shapes(_conn(two), "nfl", 2025) == {}, \
        "two teams is a comparison, not a league"


def test_latest_shaped_season_falls_back_to_last_year_in_august():
    conn = _conn(_league())        # finals live in 2025 only
    assert teamshape.latest_shaped_season(conn, "nfl", 2026) == 2025
    assert teamshape.latest_shaped_season(
        sqlite3.connect(":memory:"), "nfl", 2026) is None



def _two_seasons(now_games):
    """2025: the full league above (T5 best offence, T0 worst). 2026:
    `now_games` rounds where the order is REVERSED — T0 now scores most."""
    conn = _conn(_league())
    teams = [f"T{i}" for i in range(6)]
    rows = []
    for r in range(now_games):
        for k in range(0, 6, 2):
            h, a = teams[(k + r) % 6], teams[(k + r + 1) % 6]
            rows.append((f"2026-09-{r * 3 + k + 1:02d}", h, a,
                         40 - 3 * int(h[1:]), 40 - 3 * int(a[1:])))
    conn.executemany("INSERT INTO games VALUES ('nfl', 2026, ?, ?, ?, ?, ?)", rows)
    return conn


def test_the_radar_blends_this_season_with_last_like_the_scan():
    """Ethan, 2026-09-27: "this chart should now be updated since it says
    2025 and we use a mix of 2025 and 2026". The radar takes this season
    at the scan's own measured split (gamescan.unit_share): half by six
    games, so a team whose offence turned round has climbed; the
    2025-only shape would not move."""
    conn = _two_seasons(6)
    only_last = teamshape.team_shapes(conn, "nfl", 2025)
    both = teamshape.blended_shapes(conn, "nfl", 2026)
    assert only_last["T0"]["pct"]["offense"] == 0.0
    assert both["T0"]["pct"]["offense"] > only_last["T0"]["pct"]["offense"]
    assert both["T0"]["games"] == 6 and both["T0"]["games_last"] == 10
    assert both["T0"]["blend"] == {"off": 0.5, "def": 0.5}, "the scan's own measured split"
    # An offence under a new starting QB takes this season faster, as in the scan.
    moved = teamshape.blended_shapes(conn, "nfl", 2026,
                                     {"T0": {"off": ["new starting QB (X)"], "def": [], "qb": ["off"]}})
    assert moved["T0"]["blend"] == {"off": round(6 / 9.5, 2), "def": 0.5}
    assert moved["T0"]["raw"]["offense"] > both["T0"]["raw"]["offense"]
    # Form is the last five finals whichever season they fell in: three
    # games in, the three plus last season's last two.
    three = _two_seasons(3)
    got = teamshape.blended_shapes(three, "nfl", 2026)
    stats = teamshape._season_stats(teamshape._finals(three, "nfl", 2026))
    last = teamshape._season_stats(teamshape._finals(three, "nfl", 2025))
    want = sum((last["T0"]["margins"] + stats["T0"]["margins"])[-5:]) / 5
    assert got["T0"]["raw"]["form"] == round(want, 1)
    # Before a 2026 game, last season stands alone.
    before = teamshape.blended_shapes(_conn(_league()), "nfl", 2026)
    assert before["T5"]["pct"] == teamshape.team_shapes(_conn(_league()), "nfl", 2025)["T5"]["pct"]


def test_the_build_ships_shapes_and_the_page_draws_them():
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("team_shapes")
    block = src[i - 600:i + 900]
    assert "latest_shaped_season" in src and "_ts.blended_shapes(_sconn, \"nfl\", args.season," in src
    assert 'result["team_shapes_season"] = args.season' in src
    assert "except Exception" in block, "shapes must never fail a build"
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    j = app.index("Team shapes")
    seg = app[j - 200:j + 3600]
    assert "data-echart-radar" in seg
    assert "gp-shape-tbl" in seg, \
        "the percentile table is the engine-less fallback and must ship"
    assert "not a projection" in seg, "the label must own what it is"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
