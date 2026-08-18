"""The possession-level game sim (engine/drivesim.py) — NFL first.

Ethan, 2026-08-18: "are we running simulations and running the games
and bets 1000s of times over?" MLB was; this brings the clock sports.
What is defended here:

  * CALIBRATION IS AN IDENTITY, NOT A HOPE. The sim's expected points
    must reproduce the implied points it was anchored to — the sim's
    value is the SHAPE, and a sim that argues with its own anchor is
    just noise with extra steps.
  * EMERGENT REALISM. Nobody told the model the NFL margin's standard
    deviation, yet drives that score {0,3,7} at league rates must land
    it in the empirical 13-ish window. If a parameter change walks the
    sd out of [11, 16], the game being simulated is no longer football.
    (Basketball runs documented-hot — independent possessions carry no
    garbage-time pull — so its band is wide and one-sided.)
  * THE SEAT IS NOT TAKEN. ENABLED ships False; the build journals the
    sim's claims for the Weeks 1-4 reconciliation and prices nothing.
  * DETERMINISM. Seeded runs reproduce, same convention as the MLB sim.

Run directly: `python3 tests/test_drivesim.py`
"""

import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import drivesim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_clock_sport_has_a_shape_and_ufc_deliberately_does_not():
    assert set(drivesim.SPORTS) == {"nfl", "cfb", "nba", "wnba"}, \
        "MLB has its own PA sim; UFC has no possession structure to model"
    for cfg in drivesim.SPORTS.values():
        assert abs(sum(w for _, w in cfg["score_mix"]) - 1.0) < 1e-9


def test_implied_points_matches_the_house_convention():
    # BUF −1.5 in a 44.5 game implied 23.0 — the number the player page
    # printed and Ethan checked by hand.
    home, away = drivesim.implied_points(-1.5, 44.5)
    assert round(home, 1) == 23.0 and round(away, 1) == 21.5


def test_the_sim_reproduces_its_own_anchor():
    for sport, spread, total, tol in (("nfl", -3.5, 47.0, 0.5),
                                      ("cfb", -7.0, 55.5, 0.6),
                                      ("nba", -6.5, 224.0, 1.2),
                                      ("wnba", -4.5, 162.0, 1.0)):
        card = drivesim.simulate(sport, spread, total, trials=6000)
        home_mu, away_mu = drivesim.implied_points(spread, total)
        sim_home = (card.total_mean + card.margin_mean) / 2
        sim_away = (card.total_mean - card.margin_mean) / 2
        assert abs(sim_home - home_mu) < tol, f"{sport} home drifted"
        assert abs(sim_away - away_mu) < tol, f"{sport} away drifted"


def test_the_nfl_margin_is_football_shaped():
    card = drivesim.simulate("nfl", -3.0, 45.0, trials=8000)
    assert 11.0 <= card.margin_sd <= 16.0, \
        f"margin sd {card.margin_sd:.1f} — this is not football"
    # Basketball: documented hot, never absurd.
    hoops = drivesim.simulate("nba", -4.0, 226.0, trials=4000)
    assert 12.0 <= hoops.margin_sd <= 20.0


def test_a_bigger_favorite_wins_more():
    p = [drivesim.simulate("nfl", s, 45.0, trials=5000).p_home_win
         for s in (-1.0, -4.5, -9.5)]
    assert p[0] < p[1] < p[2]
    assert p[2] > 0.72, "a 9.5-point favorite is not a coin flip"


def test_cover_and_over_shares_sum_and_push_is_counted():
    card = drivesim.simulate("nfl", -3.0, 44.0, trials=5000)
    cov = card.p_cover()
    assert abs(sum(cov.values()) - 1.0) < 1e-9
    assert cov["push"] > 0, "an integer spread pushes sometimes"
    ovr = card.p_over()
    assert abs(sum(ovr.values()) - 1.0) < 1e-9
    assert ovr["push"] > 0, "an integer total pushes sometimes"
    j = card.joint()
    assert 0.0 < j["cover_and_over"] < 1.0
    assert abs(j["lift"] - (j["cover_and_over"] - j["independent"])) < 1e-9


def test_seeded_runs_reproduce():
    a = drivesim.simulate("nfl", -2.5, 46.5, trials=2000, seed=7)
    b = drivesim.simulate("nfl", -2.5, 46.5, trials=2000, seed=7)
    assert a.margins == b.margins and a.totals == b.totals


def test_the_seat_is_not_taken_until_the_reconciliation_says_so():
    assert drivesim.ENABLED is False, \
        "nothing prices off the sim before the Weeks 1-4 verdict"
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("drivesim.journal_records")
    block = src[i - 700:i + 400]
    assert "drivesim.journal(" in block
    assert "ENABLED stays False" in block, \
        "the wiring must say out loud that it records and never prices"


def test_journal_records_skip_unpriced_games_and_never_die():
    games = [
        {"date": "2026-09-13", "home": "KC", "away": "DEN",
         "spread": -3.0, "total": 42.5},
        {"date": "2026-09-13", "home": "SEA", "away": "NE"},   # no line
    ]
    recs = drivesim.journal_records(games, "nfl", trials=800)
    assert len(recs) == 1
    r = recs[0]
    assert r["home"] == "KC" and 0.0 < r["p_home_win"] < 1.0
    assert 0.0 < r["p_cover_and_over"] < 1.0
    # The append is never fatal: a read-only data/ builds exactly the same.
    with mock.patch.object(drivesim, "LOG_PATH", "/no/such/dir/x.jsonl"):
        drivesim.journal(recs)                        # must not raise
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "log.jsonl")
        with mock.patch.object(drivesim, "LOG_PATH", path):
            drivesim.journal(recs)
        lines = open(path, encoding="utf-8").read().strip().splitlines()
        assert len(lines) == 1 and json.loads(lines[0])["home"] == "KC"


def test_the_journal_is_gitignored():
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "data/drivesim_log.jsonl" in gi


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
