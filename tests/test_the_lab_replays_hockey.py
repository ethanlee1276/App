"""The Lab replays hockey's props (2026-11-17).

The Lab grades each league's model by replaying it over stored games it
never saw at the time. Its run (engine/lab.SPORT_ORDER) left hockey out,
though hockey's walk (engine/nhl/backtest) has measured the ranking fit
since October and the Lab page already draws an "nhl" block. What these
hold:

  - hockey is in the run, before the UFC;
  - its props are the board's own model walked forward, one market per
    skater stat and the goalies' saves, over one load of the stored games;
  - a market starts only while the time left covers the one before it,
    and the markets not reached are named;
  - the game lines say plainly why they are not replayed (no harness walks
    hockey's goal model yet: the pricer's "no scoring baseline registered"
    now reads in plain words for every league it refuses), and the page
    draws the props.

    python3 tests/test_the_lab_replays_hockey.py
"""
import datetime as dt
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, lab as L                                             # noqa: E402
from engine.nhl import model as NM                                               # noqa: E402
from engine.seasons import season_of                                             # noqa: E402


def _world():
    """Two clubs, ten skaters and a starting goalie each, thirty games."""
    random.seed(7)
    conn = D.connect(":memory:")
    season = season_of("nhl", dt.date.today().isoformat())
    start = dt.date(season, 10, 8)
    rows = []
    for g in range(30):
        day = (start + dt.timedelta(days=2 * g)).isoformat()
        for club in ("EDM", "CGY"):
            for k in range(10):
                who = f"{club} Skater {k}"
                pos = "D" if k >= 7 else "C"
                sog = random.choice((0, 1, 2, 2, 3, 3, 4, 5))
                goals = 1 if random.random() < 0.12 else 0
                assists = random.choice((0, 0, 0, 1, 1, 2))
                for market, value in (("toi", 14.0 + k), ("sog", sog), ("goals", goals), ("assists", assists),
                                      ("points", goals + assists), ("blocks", random.choice((0, 0, 1, 2))),
                                      ("anytime_goal", goals)):
                    rows.append((season, day, f"{day}-{club}", who, club, pos, market, value))
            shots = random.randint(22, 34)
            for market, value in (("started", 1), ("shots_against", shots), ("saves", shots - random.randint(1, 4))):
                rows.append((season, day, f"{day}-{club}", f"{club} Goalie", club, "G", market, value))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, position, market, "
                     "value) VALUES ('nhl', ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return conn


def test_hockey_is_in_the_run_before_the_ufc():
    order = list(L.SPORT_ORDER)
    assert "nhl" in order and order.index("nhl") < order.index("ufc")
    page = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    at = page.index("async function renderLab()")
    assert '"nhl", "ufc"]' in page[at:at + 3000], "the page draws hockey's block"


def test_the_props_are_the_boards_model_walked_forward():
    conn = _world()
    blob = L.build_sport("nhl", conn, log=lambda *_: None)
    got = {m["market"]: m for m in blob["props"]["markets"]}
    assert set(got) == set(NM.SKATER_MARKETS) | set(NM.GOALIE_MARKETS), sorted(got)
    assert got["sog"]["label"] == "Shots on Goal"
    # Twenty skaters' games 6-30 are priced (five of their own come first); the goalies' too.
    assert {m: got[m]["n"] for m in got} == {**{m: 500 for m in NM.SKATER_MARKETS}, "saves": 50}
    assert all(got[m]["brier"] is not None and got[m]["bins"] for m in got)
    assert "not_reached" not in blob["props"]
    assert blob["game_lines"] == {"unavailable": "this league’s spreads and totals are priced by its own "
                                                 "model, which this replay does not walk yet"}, "said plainly"
    assert blob["replayed_at"]


def test_a_market_starts_only_while_the_time_covers_the_one_before():
    conn = _world()
    missed = []
    out = L.nhl_props(conn, log=lambda *_: None, budget_s=0.0001, missed=missed)
    markets = (*NM.SKATER_MARKETS, *NM.GOALIE_MARKETS)
    assert [m["market"] for m in out] == [markets[0]], "the first always starts"
    assert missed == list(markets[1:])


def test_no_stored_games_says_so():
    blob = L.build_sport("nhl", D.connect(":memory:"), log=lambda *_: None)
    assert blob["props"] == {"unavailable": "no stored hockey games deep enough to replay yet"}


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
