"""The matchup scan's reasons are measured before any of them moves a number.

The game page says "None of this moves our numbers yet: a reason joins the
model once it has been measured against past games". engine/scanfit is
that measurement: each signal is credited only with what it adds on top
of the board's own matchup step, fitted walk-forward and held out a
season at a time, and it joins the model only under the rule college's
matchups were chosen by — positive held-out gain on average and in all
but one season.
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import scanfit as F                                  # noqa: E402


def test_a_corner_starts_on_snaps_and_is_out_when_he_does_not_play():
    snaps = [{"team": "ATL", "week": str(w), "game_type": "REG", "player": p, "position": "CB",
              "defense_pct": str(v)} for w, p, v in [
        (1, "A.J. Terrell", 1.0), (2, "A.J. Terrell", 0.95), (3, "A.J. Terrell", 0.9),
        (1, "Mike Hughes", 0.8), (2, "Mike Hughes", 0.4), (3, "Mike Hughes", 0.85),
        (1, "Clark Phillips", 0.2), (2, "Clark Phillips", 0.75), (3, "Clark Phillips", 0.1),
        (4, "Mike Hughes", 0.9), (4, "Clark Phillips", 0.8)]]
    table = F.corner_snaps(snaps)
    assert F.corners_out(table, "ATL", 4) == 1, "Terrell started all three and sat; Phillips started one"
    assert F.corners_out(table, "ATL", 5) is None, "no game that week"
    assert F.corners_out(table, "ATL", 3) is None, "fewer than three games before"


def test_missed_tackles_lean_on_last_season_early():
    now = {"ATL": {1: [3, 30], 2: [3, 30], 3: [3, 30]}, "GB": {1: [1, 30], 2: [1, 30], 3: [1, 30]}}
    got = F.missed_signal(now, None, 4)
    assert round(got["ATL"], 3) == round(0.1 / (12 / 180) - 1, 3), "9 of 90 against the league's 12 of 180"
    prior = {"ATL": {w: [1, 30] for w in range(1, 18)}}
    blended = F.missed_signal(now, prior, 4)
    assert blended["ATL"] < got["ATL"], "a tidy last season pulls three sloppy games back"
    assert F.missed_signal(now, None, 3) == {}, "two games is not a rate"


def test_a_zone_beater_splits_against_man():
    part = [{"nflverse_game_id": "g", "play_id": str(i), "defense_man_zone_type": mz,
             "defense_coverage_type": "COVER_3"}
            for i, mz in enumerate(["ZONE_COVERAGE"] * 20 + ["MAN_COVERAGE"] * 10)]
    plays = [{"game_id": "g", "play_id": str(i), "receiver_player_name": "D.London", "posteam": "ATL",
              "yards_gained": "10" if i < 20 else "5", "complete_pass": "1"} for i in range(30)]
    rel = F.zone_splits(part, plays)["D.London"]
    assert round(rel, 3) == round((10 - 5) / (250 / 30), 3)
    assert F.zone_splits(part[:25], plays[:25]) == {}, "five man targets is not a split"


def test_the_fit_finds_an_effect_and_holds_it_out_a_season_at_a_time():
    rnd = random.Random(7)
    pts = []
    for season in (2022, 2023, 2024, 2025):
        for _ in range(400):
            e, x = rnd.uniform(40, 90), rnd.uniform(-0.2, 0.2)
            pts.append((e, x, e * (1 + 0.8 * x) + rnd.gauss(0, 6), season))
    f = F.fit(pts)
    assert abs(f["b"] - 0.8) < 0.1 and f["se"] < 0.1
    res = F.study({("pass_defense", "rec_yds", "WR"): pts})[("pass_defense", "rec_yds", "WR")]
    assert res["passes"] and all(v > 0 for v in res["held_out"].values())
    noise = [(e, rnd.uniform(-0.2, 0.2), y, s) for e, _x, y, s in pts]
    assert not F.study({("pass_defense", "rec_yds", "WR"): noise})[("pass_defense", "rec_yds", "WR")]["passes"]


def test_a_one_sided_signal_does_not_soak_up_the_bias():
    """The trap the first run fell into (2026-09-24): a player's recent
    average overstates his next game by about 4½%, and a signal that is
    never negative — a corner out — took that bias for an effect (b
    −0.08 at 4 SE, when receivers did slightly BETTER with a corner out).
    The fit carries a level term, so the bias is the level's."""
    rnd = random.Random(11)
    pts = []
    for season in (2022, 2023, 2024, 2025):
        for _ in range(1500):
            e, x = rnd.uniform(40, 90), 1 if rnd.random() < 0.2 else 0
            pts.append((e, x, e * 0.955 + rnd.gauss(0, 12), season))
    got = F.study({("cb_out", "rec_yds", "WR"): pts})[("cb_out", "rec_yds", "WR")]
    assert abs(got["a"] + 0.045) < 0.01, "the bias is the level's"
    assert not got["passes"], got


def test_the_page_says_what_the_measurement_found():
    """2026-09-24, 2022-2025: nothing passed, so nothing moves a number
    and the game page, the pick page and Ask say it was tested. The day a
    re-run passes a signal, MEASURED changes and so must the sentence."""
    for name, sig in F.SIGNALS.items():
        for market, grp in sig["markets"]:
            assert (name, market, grp) in F.MEASURED, (name, market, grp)
    passing = [k for k, (b, se, held, mean) in F.MEASURED.items()
               if mean > 0 and sum(v > 0 for v in held) >= len(held) - 1 and abs(b) / se >= F.MIN_T]
    assert passing == []
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "none predicted a player’s line beyond those" in app and "also\n      noticed" in app
    ask = open(os.path.join(ROOT, "engine", "askbot.py"), encoding="utf-8").read()
    assert "moves none of our numbers" in ask


def test_the_charts_matchups_are_the_interaction_alone():
    """2026-10-13: where he goes against where they give ground (the carry
    and route charts' columns), over their overall — zero for a defence
    that is the same everywhere and for a player whose mix is the league's."""
    assert F.run_class("middle", "NA") == "in" and F.run_class("left", "guard") == "in"
    assert F.run_class("right", "tackle") == "out" and F.run_class("left", "end") == "out"
    assert F.run_class("left", "NA") == "" and F.run_class(None, None) == ""
    runs = []
    for wk in (1, 2, 3):
        for team, out_yds in (("DAL", 8), ("NYG", 4), ("PHI", 4), ("WAS", 4)):
            runs += [{"week": wk, "defteam": team, "rusher_player_id": "x", "run_location": "left",
                      "run_gap": "end", "rushing_yards": out_yds}] * 20
            runs += [{"week": wk, "defteam": team, "rusher_player_id": "x", "run_location": "middle",
                      "run_gap": "NA", "rushing_yards": 4}] * 20
    runs += [{"week": w, "defteam": "NYG", "rusher_player_id": "OUTSIDE", "run_location": "right",
              "run_gap": "tackle", "rushing_yards": 3} for w in (1, 2, 3) for _ in range(8)]
    runs += [{"week": w, "defteam": "NYG", "rusher_player_id": "EVEN", "run_location": loc,
              "run_gap": gap, "rushing_yards": 3}
             for w in (1, 2, 3) for loc, gap in (("left", "end"), ("middle", "NA")) for _ in range(4)]
    t = F.direction_table(runs)
    rel, weights = F.class_rel(t["def"], 4, F.DIR_SHRINK)
    assert rel["DAL"]["out"] > 1.2 and abs(rel["DAL"]["in"] - 1) < 0.05, \
        "DAL gives ground outside and is the league inside"
    out_fit = F.mix_fit(t["mine"]["OUTSIDE"], 4, rel["DAL"], weights, F.DIR_MIN)
    even_fit = F.mix_fit(t["mine"]["EVEN"], 4, rel["DAL"], weights, F.DIR_MIN)
    assert out_fit > 0.05, out_fit
    assert abs(even_fit) < 0.02, "his mix is near the league's: near zero"
    flat = {"in": 1.3, "out": 1.3}
    assert abs(F.mix_fit(t["mine"]["OUTSIDE"], 4, flat, weights, F.DIR_MIN)) < 1e-12, \
        "a defence bad everywhere is the matchup step the board already takes"
    assert F.mix_fit(t["mine"]["OUTSIDE"], 2, rel["DAL"], weights, F.DIR_MIN) is None, "8 carries is not a mix"
    assert F.mix_fit(t["mine"]["OUTSIDE"], 4, None, weights, F.DIR_MIN) is None

    plays = []
    for wk in (1, 2, 3):
        for team, left in (("DAL", 12), ("NYG", 7), ("PHI", 7)):
            for side, yds in (("left", left), ("middle", 7), ("right", 7)):
                plays += [{"week": wk, "defteam": team, "receiver_player_id": "x", "pass_location": side,
                           "complete_pass": 1, "yards_gained": yds, "yards_after_catch": 2}] * 10
    plays += [{"week": w, "defteam": "PHI", "receiver_player_id": "LEFTY", "pass_location": "left",
               "complete_pass": 0, "yards_gained": 0} for w in (1, 2, 3) for _ in range(6)]
    s = F.side_table(plays)
    rel, weights = F.class_rel(s["def"], 4, F.SIDE_SHRINK)
    assert set(weights) == {"L", "M", "R"}
    assert F.mix_fit(s["mine"]["LEFTY"], 4, rel["DAL"], weights, F.SIDE_MIN) > 0.05, \
        "a receiver thrown to the left, against the side DAL gives up"
    assert s["def"]["PHI"][-1] == (3, "L", 0.0), "a miss counts as a target with no yards"


def test_yards_after_the_catch_meet_a_defence_that_allows_them():
    plays = []
    for wk in (1, 2, 3):
        for team, yac in (("DAL", 9), ("NYG", 3), ("PHI", 3), ("WAS", 3)):
            plays += [{"week": wk, "defteam": team, "receiver_player_id": "x", "complete_pass": 1,
                       "yards_gained": 10, "yards_after_catch": yac}] * 10
        plays += [{"week": wk, "defteam": "NYG", "receiver_player_id": "SCREEN", "complete_pass": 1,
                   "yards_gained": 8, "yards_after_catch": 8}] * 3
        plays += [{"week": wk, "defteam": "NYG", "receiver_player_id": "DEEP", "complete_pass": 1,
                   "yards_gained": 25, "yards_after_catch": 1}] * 3
    t = F.yac_table(plays)
    rel, per_catch, share = F.yac_rel(t, 4)
    assert rel["DAL"] > 0 > rel["NYG"] and per_catch > 0 and 0 < share < 1
    screen = F.yac_lean(t["mine"]["SCREEN"], 4, share)
    deep = F.yac_lean(t["mine"]["DEEP"], 4, share)
    assert screen > 0 > deep, "a catch-and-run man leans on yards after the catch; a deep man does not"
    W = {"yac": (rel, per_catch, share)}
    mats = {"yac": t}
    x_screen = F.signal("yac_fit", W, "PHI", "DAL", {"player_id": "SCREEN"}, {}, {}, 4, mats=mats)
    x_deep = F.signal("yac_fit", W, "PHI", "DAL", {"player_id": "DEEP"}, {}, {}, 4, mats=mats)
    assert x_screen > 0 > x_deep
    assert F.signal("yac_fit", W, "PHI", "DAL", {"player_id": "SCREEN"}, {}, {}, 2, mats=mats) is None, \
        "six catches is not a lean"
    for name in ("run_direction", "side_fit", "yac_fit"):
        assert (name in F.PENDING) != (name in F.SIGNALS), "pending until measured, then a signal"
        assert all(m in F.MARKETS for m in (F.PENDING.get(name) or F.SIGNALS[name])["markets"])
    assert set(F.RUN_COLS) >= {"rusher_player_id", "run_location", "run_gap"}
    assert {"pass_location", "yards_after_catch", "receiver_player_id"} <= set(F.RECV_COLS)


def test_every_signal_names_the_markets_it_claims():
    for name, sig in F.SIGNALS.items():
        assert sig["markets"] and sig["says"], name
        for m in sig["markets"]:
            assert m in F.MARKETS, (name, m)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
