"""Long-shot engines — NFL anytime touchdowns and MLB home runs.

These markets are where undisciplined models lose money, so the tests assert the
*discipline* as much as the maths: opportunity beats recent scoring, the odds
windows hold, concentration limits hold, and implausible edges are refused.

Run directly: `python3 tests/test_longshots.py`
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.longshots import (
    prob_at_least_one, in_odds_window, select, build_pick,
    NFL_TD_ODDS, MLB_HR_ODDS,
)
from engine.touchdowns import (
    td_probability, team_implied_total, expected_team_tds, build_td_longshots,
)
from engine.mlb.homeruns import hr_probability, plate_appearances, build_hr_longshots
from engine.models import (
    Prop, Game, Team, DefenseProfile, Weather, GameLog, SportsbookLine, ANYTIME_TD,
)
from engine.mlb.models import (
    MLBProp, MLBGame, MLBGameLog, MLBWeather, Pitcher, StatcastProfile,
)


# --- shared ----------------------------------------------------------------
def test_prob_at_least_one_is_a_poisson_tail():
    assert prob_at_least_one(0.0) == 0.0
    assert 0.6 < prob_at_least_one(1.0) < 0.65      # 1 - e^-1
    assert prob_at_least_one(5.0) < 1.0             # never certain


def test_the_handbooks_overdispersion_shrink_is_not_applied():
    """Both handbooks say to shrink lambda by 0.93 above 0.80 (college
    0.90 above 1.20) because scoring supposedly produces more zeroes than
    Poisson. Measured over 3,688 NFL and 9,221 college player-games at a
    season rate of 0.50 or better, touchdown counts are tighter than
    Poisson at BOTH ends — 48.5% zeroes against 51.1% in the NFL, 2.4%
    three-or-more against 3.6% — with the missing mass on exactly one.

    So Poisson already under-states P(at least one), and the prescribed
    shrink would push a low number lower in the exact band it was meant
    to protect. Checked by behaviour, not by reading the docstring: an
    applied shrink shows up as a discontinuity at the threshold."""
    below, above = prob_at_least_one(0.79), prob_at_least_one(0.81)
    smooth = prob_at_least_one(0.80)
    assert below < smooth < above
    # A 0.93 shrink starting at 0.80 would drop the curve by ~2.5 points
    # right there; an unshrunk exponential moves by 0.004 across the same
    # step.
    assert above - below < 0.01
    for lam in (0.80, 1.20):
        assert abs(prob_at_least_one(lam) - (1.0 - math.exp(-lam))) < 1e-12


def test_odds_windows_match_the_strategy():
    # NFL widened to -150..+450 on 2026-08-25 (Ethan: "fix the odds range
    # for long shot picks") — the old +200 ceiling cut the board off at
    # exactly the mid-priced darts a Long Shots page exists for. The
    # floor is unchanged: heavy juice on a scorer market never pays.
    assert in_odds_window(-140, NFL_TD_ODDS) and in_odds_window(190, NFL_TD_ODDS)
    assert in_odds_window(420, NFL_TD_ODDS)          # the dart the page is for
    assert not in_odds_window(-260, NFL_TD_ODDS)     # too much juice
    # +700 was "lottery ticket" until 2026-08-27, when the model was
    # finally graded down there: over 9,327 sub-18% player-weeks its top
    # quintile out-scored its bottom by 7.4 points at z = 7.6, and the
    # fitted correction brings the worst band to 1.4 points off true.
    # The old ceiling's own reason — a proxy-fed model that "cannot
    # separate a sub-18% event from noise" — was falsified, so the EV
    # gate gets to decide instead of the window pre-empting it.
    assert in_odds_window(700, NFL_TD_ODDS)
    assert not in_odds_window(2000, NFL_TD_ODDS)     # still stops somewhere
    assert in_odds_window(300, MLB_HR_ODDS) and in_odds_window(640, MLB_HR_ODDS)
    assert not in_odds_window(180, MLB_HR_ODDS)      # too short for a HR
    assert not in_odds_window(900, MLB_HR_ODDS)
    # CFB has its own window — Saturday spreads run to -40, so both ends
    # sit wider than the NFL's.
    from engine.longshots import CFB_TD_ODDS
    assert in_odds_window(-180, CFB_TD_ODDS) and in_odds_window(550, CFB_TD_ODDS)
    assert not in_odds_window(-260, CFB_TD_ODDS)
    # Widened with the NFL's on the same evidence, keeping college one
    # notch out for its wilder distribution. NOTE the measurement behind
    # it is NFL's: college has no player game logs to replay, so its
    # ceiling rides on the football-shaped finding rather than its own.
    # That is a weaker claim and it is the reason CFB moved to +900
    # rather than further.
    assert in_odds_window(800, CFB_TD_ODDS)
    assert not in_odds_window(2000, CFB_TD_ODDS)


def test_implausible_edge_is_refused():
    """A 30-point disagreement with an efficiently-priced market is a data or
    modelling error, not an edge — it must not grade as a play."""
    pick = build_pick("X", "AAA", "BBB", "home_runs", "Home Runs", "DK", 400,
                      model_prob=0.55, under_odds=-600, opportunities=4.3,
                      opp_target=4.5, primary_reason="", reasons=[], caveats=[],
                      sport="mlb")
    assert pick.grade == "Pass"
    assert any("too large to trust" in c for c in pick.caveats)


# --- NFL touchdowns --------------------------------------------------------
def _nfl(pos, share, spread, total, weather=None, tds=None, vs_d=1.0):
    g = Game(home="KC", away="BUF", weather=weather or Weather(dome=True),
             spread=spread, total=total)
    opp = Team(abbr="BUF", name="Bills",
               defense=DefenseProfile(team="BUF", vs_rb_rush=vs_d, vs_wr1=vs_d, vs_te=vs_d))
    logs = [GameLog(week=i, opponent="X", value=float(v)) for i, v in enumerate(tds or [], 1)]
    p = Prop(player="Test", team="KC", opponent="BUF", position=pos, market=ANYTIME_TD,
             logs=logs, career_avg=0.4, vs_opponent_avg=None,
             lines=[SportsbookLine("DK", 0.5, 120, -160)])
    return td_probability(p, g, opp, share)


def test_implied_total_follows_the_spread():
    g = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-7.0, total=50.0)
    assert team_implied_total(g, "KC") == 28.5      # favourite gets the points
    assert team_implied_total(g, "BUF") == 21.5
    assert expected_team_tds(28.5) > expected_team_tds(21.5)


def test_game_script_moves_touchdown_probability():
    """The same back is worth far more as a big favourite in a high total."""
    good, _ = _nfl("RB", 0.65, -7.0, 51.0, tds=[1, 0, 1, 1, 0, 1])
    bad, _ = _nfl("RB", 0.65, +7.0, 38.0, tds=[1, 0, 1, 1, 0, 1])
    assert good > bad + 0.15


def test_scoreless_backup_is_not_rated_like_a_starter():
    """Six scoreless games is evidence of a low rate, not missing data — the
    old fallback to a position baseline badly overrated players like this."""
    backup, _ = _nfl("RB", 0.10, -3.0, 45.0, tds=[0, 0, 0, 0, 0, 0])
    starter, _ = _nfl("RB", 0.65, -3.0, 45.0, tds=[1, 0, 1, 1, 0, 1])
    assert backup < 0.15
    assert starter > backup * 2


def test_severe_weather_suppresses_passing_touchdowns():
    clear, _ = _nfl("WR", 0.28, -7.0, 51.0)
    windy, _ = _nfl("WR", 0.28, -7.0, 51.0,
                    weather=Weather(dome=False, wind_mph=25, temp_f=18))
    assert windy < clear


def test_red_zone_proxy_is_disclosed():
    _, info = _nfl("RB", 0.5, -3.0, 45.0, tds=[1, 0, 0, 1])
    assert any("inferred" in c for c in info["caveats"])


def test_td_board_respects_the_per_game_cap():
    """Three qualifying players in one game must yield at most two picks."""
    g = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-7.0, total=52.0)
    opp = Team(abbr="BUF", name="Bills", defense=DefenseProfile(team="BUF", vs_rb_rush=1.2))
    cands = []
    for name in ("A", "B", "C"):
        p = Prop(player=name, team="KC", opponent="BUF", position="RB", market=ANYTIME_TD,
                 logs=[GameLog(week=i, opponent="X", value=1.0) for i in range(1, 7)],
                 career_avg=1.0, vs_opponent_avg=None,
                 lines=[SportsbookLine("DK", 0.5, 150, -200)])
        cands.append({"prop": p, "game": g, "opponent": opp,
                      "opportunity_share": 0.5, "odds": 150, "book": "DK",
                      "under_odds": -200})
    assert len(build_td_longshots(cands, limit=6, per_game=2)) <= 2


# --- MLB home runs ---------------------------------------------------------
def _mlb(park="coors", wind="cross", mph=5, temp=72, barrel=0.13, spot=4, every=6):
    g = MLBGame(home="COL", away="NYY", park=park,
                weather=MLBWeather(temp_f=temp, wind_mph=mph, wind_dir_rel=wind),
                pitchers={"COL": Pitcher(name="P", throws="R", slg_allowed_vs_r=0.44,
                                         k_rate=0.20, xera=4.6)})
    p = MLBProp("Slugger", "NYY", "COL", "RF", "home_runs",
                [MLBGameLog(i, "X", 1.0 if i % every == 0 else 0.0) for i in range(1, 31)],
                0.2, None, [SportsbookLine("DK", 0.5, 350, -480)],
                bats="R", lineup_spot=spot,
                statcast=StatcastProfile(barrel_pct=barrel, hard_hit_pct=0.50,
                                         xslg=0.560, slg=0.530))
    return hr_probability(p, g)


def test_wind_direction_moves_home_run_probability():
    """Wind is one of the few edges the market is sometimes slow to price, so
    blowing out must beat calm, which must beat blowing in."""
    out, _ = _mlb(wind="out", mph=15)
    calm, _ = _mlb(wind="cross", mph=3)
    into, _ = _mlb(wind="in", mph=15)
    assert out > calm > into


def test_park_and_cold_suppress_home_runs():
    coors, _ = _mlb(park="coors", temp=85)
    pitchers_park, _ = _mlb(park="loandepot", temp=45)
    assert coors > pitchers_park


def test_contact_quality_beats_recent_results():
    elite, _ = _mlb(barrel=0.15)
    weak, _ = _mlb(barrel=0.04)
    assert elite > weak


def test_lineup_spot_changes_plate_appearances():
    assert plate_appearances(1) > plate_appearances(9)
    top, _ = _mlb(spot=2)
    bottom, _ = _mlb(spot=9)
    assert top > bottom


def test_missing_statcast_is_disclosed():
    g = MLBGame(home="COL", away="NYY", park="coors")
    p = MLBProp("NoData", "NYY", "COL", "RF", "home_runs",
                [MLBGameLog(i, "X", 0.0) for i in range(1, 11)], 0.1, None,
                [SportsbookLine("DK", 0.5, 500, -700)], bats="R", lineup_spot=5)
    _, info = hr_probability(p, g)
    assert any("Statcast" in c for c in info["caveats"])


def test_hr_board_caps_one_pick_per_team():
    g = MLBGame(home="COL", away="NYY", park="coors",
                weather=MLBWeather(temp_f=88, wind_mph=15, wind_dir_rel="out"),
                pitchers={"COL": Pitcher(name="P", throws="R", slg_allowed_vs_r=0.47)})
    cands = []
    for name in ("A", "B", "C"):
        p = MLBProp(name, "NYY", "COL", "RF", "home_runs",
                    [MLBGameLog(i, "X", 1.0 if i % 5 == 0 else 0.0) for i in range(1, 31)],
                    0.2, None, [SportsbookLine("DK", 0.5, 400, -550)],
                    bats="R", lineup_spot=3,
                    statcast=StatcastProfile(barrel_pct=0.13, hard_hit_pct=0.5))
        cands.append({"prop": p, "game": g, "odds": 400, "book": "DK", "under_odds": -550})
    assert len(build_hr_longshots(cands, limit=3, per_team=1)) <= 1


def test_board_ranks_by_edge_not_by_payout():
    """The biggest price is almost never the best bet — ranking by odds is how
    long-shot cards go broke.

    NET edge since 2026-08-30: the model against the price on offer,
    which is the same question the grade and the stake now ask. Ranking
    on the model's disagreement with the market instead put a bet we
    could not take above one we could."""
    from engine.longshots import LongShot

    def ls(name, net, odds):
        return LongShot(player=name, team=name, opponent="X", market="home_runs",
                        market_label="Home Runs", book="DK", odds=odds,
                        model_prob=0.2, implied_prob=0.2 - net, edge=net,
                        net_edge=net,
                        ev_per_unit=0.1, confidence=8.0, stake_units=0.5,
                        grade="Play", expected_opportunities=4.3, primary_reason="")

    picks = [ls("LongPrice", 0.02, 900), ls("BestEdge", 0.06, 300)]
    ranked = select(picks, per_key_cap=1, key=lambda p: p.team, limit=2)
    assert ranked[0].player == "BestEdge"


def test_hr_watchlist_ranks_by_model_probability():
    """The Long Shots page must answer "who could go deep tonight" even when
    no price clears the value bar — ranked by model probability with the
    price and EV shown honestly, real-priced overs only."""
    from engine.mlb.homeruns import hr_watchlist
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, HOME_RUNS
    from engine.models import SportsbookLine

    game = MLBGame(home="NYY", away="BOS", park="yankee")

    def cand(name, spot, hr_per_game, odds, book="DraftKings"):
        prop = MLBProp(name, "NYY", "BOS", "RF", HOME_RUNS,
                       [MLBGameLog(i, "X", hr_per_game) for i in range(1, 21)],
                       hr_per_game, None,
                       [SportsbookLine(book, 0.5, odds, 0)], lineup_spot=spot)
        return {"prop": prop, "game": game, "odds": odds, "book": book}

    rows = hr_watchlist([
        cand("Slugger", 2, 0.35, 320),
        cand("Slap Hitter", 8, 0.02, 800),
        cand("Proxy Guy", 1, 0.5, 400, book="proxy"),   # excluded: no real price
    ])
    assert [r["player"] for r in rows][:2] == ["Slugger", "Slap Hitter"]
    assert all(r["player"] != "Proxy Guy" for r in rows)
    top = rows[0]
    assert top["model_prob"] > rows[1]["model_prob"]
    assert 0 < top["implied_prob"] < 1 and "odds" in top
    assert "primary_reason" in top and top["ev_per_unit"] is not None


def test_hr_watchlist_rejects_mislined_and_broken_prices():
    """+2000 is a '2+ homers' price, not a 'hits a homer' price — comparing
    it to a 1+ HR probability manufactured 400%+ fake EV on the board."""
    from engine.mlb.homeruns import hr_watchlist
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog, HOME_RUNS
    from engine.models import SportsbookLine

    game = MLBGame(home="NYY", away="BOS", park="yankee")
    def cand(name, odds):
        prop = MLBProp(name, "NYY", "BOS", "RF", HOME_RUNS,
                       [MLBGameLog(i, "X", 0.3) for i in range(1, 21)], 0.3,
                       None, [SportsbookLine("DraftKings", 0.5, odds, 0)],
                       lineup_spot=3)
        return {"prop": prop, "game": game, "odds": odds, "book": "DraftKings"}

    rows = hr_watchlist([cand("Sane Price", 380), cand("Mislined", 2000)])
    assert [r["player"] for r in rows] == ["Sane Price"]
    assert all(r["ev_per_unit"] <= 0.60 for r in rows)
    assert "recent_values" in rows[0]




def test_hr_board_drops_the_tail_the_model_cannot_pick():
    """Measured on 214 settled bets: split by the model's own probability,
    the bottom two quartiles returned -37% and -39% while the top two
    returned +10.8% and +11.1% (z=2.09). The board no longer bets the tail
    it demonstrably cannot rank."""
    import inspect
    from engine.mlb.homeruns import build_hr_longshots, MIN_MODEL_PROB

    assert 0.05 < MIN_MODEL_PROB < 0.25
    sig = inspect.signature(build_hr_longshots)
    assert sig.parameters["min_prob"].default == MIN_MODEL_PROB
    # An empty board is still an empty board, floor or not.
    assert build_hr_longshots([], limit=3) == []


def test_impossible_under_never_inflates_the_devig():
    """A fabricated or stale under (-110 against a +318 over sums to 76% —
    a book that pays out more than it takes) once made the "de-vigged"
    implied HIGHER than the raw price's own 23.9%, and the market-shrunk
    model probability and EV rode up with it. An impossible pair must be
    priced as one-sided."""
    from engine.longshots import _price
    from engine.odds import american_to_prob

    implied_bad, exact_bad = _price(0.25, 318, -110)
    assert exact_bad is False                       # treated as one-sided
    assert implied_bad < american_to_prob(318)      # 6% hold stripped, never added
    # A sane pair still de-vigs exactly.
    implied_ok, exact_ok = _price(0.25, 318, -430)
    assert exact_ok is True
    assert implied_ok < american_to_prob(-430)


# --- the board is three rows, and there is no fourth ------------------------
def _built():
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.mlb.pipeline import run_mlb_slate
    return run_mlb_slate("data/mlb_sample_slate.json")


def test_the_long_shot_board_never_exceeds_three_rows():
    """It used to ship every real-priced home run on the slate — two hundred
    names most nights, below the three that were actually recommended. The
    three were the point; the wall buried them."""
    from engine.mlb.pipeline import LONGSHOT_BOARD
    d = _built()
    assert LONGSHOT_BOARD == 3
    assert len(d["long_shots"]) + len(d["longshot_watch"]) <= LONGSHOT_BOARD


def test_the_top_up_rows_never_duplicate_a_pick():
    d = _built()
    picks = {r.get("player") for r in d["long_shots"]}
    assert not (picks & {r.get("player") for r in d["longshot_watch"]})


def test_the_scanner_still_sees_the_whole_pool():
    """The trim is a publishing decision, not a data one. A scanner
    reporting "no plus-money props" while the site carries +400 home runs
    would be contradicting its own page — so it reads the untrimmed pool,
    which must therefore be able to exceed the board."""
    d = _built()
    n = len((d.get("market_scan") or {}).get("longshots") or [])
    assert n > len(d["long_shots"]) + len(d["longshot_watch"])


def test_the_recommended_page_features_the_same_three():
    """Both pages read hr_featured off the same stamp. Two lists computed
    separately would eventually disagree about which three."""
    d = _built()
    board = {r.get("player") for r in d["long_shots"] + d["longshot_watch"]}
    featured = {r["player"] for r in d["recommendations"]
                if r.get("hr_featured")}
    assert featured <= board
    assert len(featured) <= 3


def test_a_long_shot_carries_the_photo_its_prop_already_had():
    """Ethan, 2026-08-13: "we are not showing headshots on the longshot
    page either."

    The page was never the problem — it has always rendered
    `playerAvatar(..., {headshot: r.headshot})`. The LongShot dataclass
    simply had no such field, so `r.headshot` was undefined on every row
    and every card fell through to the drawn chip, while the prop object
    sitting beside the candidate carried the URL the whole time.

    Pinned on the dataclass and its dict because that is where the fact
    went missing; the two builders read it off the prop with getattr, so a
    prop without one costs a picture and never a board.
    """
    from engine.longshots import LongShot
    import dataclasses
    fields = {f.name for f in dataclasses.fields(LongShot)}
    assert "headshot" in fields, "the row cannot carry what it has no field for"
    ls = LongShot(
        player="X", team="SF", opponent="LA", market="anytime_td",
        market_label="Anytime TD", book="dk", odds=150, model_prob=0.4,
        implied_prob=0.38, edge=0.02, ev_per_unit=0.05, confidence=6.0,
        stake_units=0.5, grade="B", expected_opportunities=2.0,
        primary_reason="r", headshot="https://x/face.png")
    assert ls.to_dict()["headshot"] == "https://x/face.png"
    # Default is the empty string, so the key is always present: a missing
    # key and an empty one render identically and debug very differently.
    bare = dataclasses.replace(ls, headshot="")
    assert bare.to_dict()["headshot"] == ""


def test_both_long_shot_builders_read_the_photo_off_the_prop():
    """One field on the dataclass is only half a fix — the two builders
    have to actually copy it across, and neither may crash on a prop
    (or a test fixture) that predates the attribute."""
    import inspect
    from engine import touchdowns
    from engine.mlb import homeruns
    for mod in (touchdowns, homeruns):
        src = inspect.getsource(mod)
        assert 'headshot=getattr(prop, "headshot", "")' in src, mod.__name__


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
