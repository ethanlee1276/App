"""College prices a quarterback's attempts and completions and a back's carries.

Ethan, 2026-10-05: "for nfl and CFB For the most likely bets, we need to
implement picks for QB interceptions, QB Pass Attempts, QB Completions,
and any other market we are missing". The NFL board added attempts,
completions and carries on 2026-09-27; college carried none, and its
play feed did not count completions or interceptions at all. Checks: the
play feed counts completions, interceptions and carries-as-a-market and
writes the zero where the opportunity is on the record; the ESPN box
splits "C/ATT" the same way; the prop builder, the rank walk, the three
fitters and the odds request all name the same markets; the college odds
config maps the three keys behind the drop-and-retry guard; the
deploy-day cache fallback still finds the pull before them; and the
measurement harness's role and rate helpers read the way they say.

Run directly: `python3 tests/test_college_prices_the_volume_markets.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import cfbstats as C                            # noqa: E402
from engine.sources import cfbdata as D                             # noqa: E402
from engine.sources import oddsapi as O                             # noqa: E402
from engine.cfb import props as P                                   # noqa: E402
from engine import rankfit, logwalk                                 # noqa: E402

GAMES = {"401": {"period": "003", "home": "UGA", "away": "OSU",
                 "home_name": "Georgia", "away_name": "Ohio State", "points": 0}}


def _play(**kw):
    row = {"game_id": "401", "season": "2024", "week": "3", "team": "Georgia",
           "opponent": "Ohio State", "yards_to_goal": "40", "down": "1", "distance": "10"}
    row.update(kw)
    return row


def _value(out, player, market):
    for r in out["rows"]:
        if r["player"] == player and r["market"] == market:
            return r["value"]
    return None


def test_the_play_feed_counts_completions_interceptions_and_carries():
    plays = [
        _play(completion_player="QB", reception_player="WR", reception_yds="12"),
        _play(completion_player="QB", reception_player="WR", reception_yds="8"),
        _play(incompletion_player="QB", incompletion_stat="1"),
        _play(interception_thrown_player="QB", interception_thrown_stat="1"),
        _play(rush_player="RB", rush_yds="4"),
        _play(rush_player="RB", rush_yds="9"),
    ]
    out = C.parse_player_stats(plays, 2024, GAMES)
    assert _value(out, "QB", "pass_att") == 4.0
    assert _value(out, "QB", "pass_cmp") == 2.0
    assert _value(out, "QB", "pass_int") == 1.0
    assert _value(out, "RB", "rush_att") == 2.0 == _value(out, "RB", "carries")
    assert _value(out, "WR", "pass_cmp") is None, "a receiver is not charged a completion"


def test_a_passer_who_was_not_picked_off_is_a_zero_not_a_gap():
    out = C.parse_player_stats([_play(completion_player="QB", reception_player="WR", reception_yds="5")],
                               2024, GAMES)
    assert _value(out, "QB", "pass_int") == 0.0 and _value(out, "QB", "pass_cmp") == 1.0
    assert C.ZERO_WHEN["pass_cmp"] == C.ZERO_WHEN["pass_int"] == "pass_att"
    assert C.ZERO_WHEN["rush_att"] == "carries"
    assert {"pass_cmp", "pass_int", "rush_att"} <= set(C.MARKETS)


def test_the_espn_box_splits_completions_over_attempts():
    assert D._split_pair("18/25") == (18.0, 25.0) and D._split_pair("264") is None
    payload = {"boxscore": {"players": [{"team": {"abbreviation": "UGA"}, "statistics": [
        {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"],
         "athletes": [{"athlete": {"displayName": "G. Stockton", "id": "9"},
                       "stats": ["18/25", "264", "10.6", "2", "1"]}]},
        {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
         "athletes": [{"athlete": {"displayName": "N. Frazier", "id": "7"},
                       "stats": ["19", "112", "5.9", "1", "38"]}]}]}]}}
    rows = {r["player"]: r["stats"] for r in D.parse_summary(payload)}
    assert rows["G. Stockton"]["pass_cmp"] == 18.0 and rows["G. Stockton"]["pass_att"] == 25.0
    assert rows["G. Stockton"]["pass_int"] == 1.0
    assert rows["N. Frazier"]["rush_att"] == rows["N. Frazier"]["carries"] == 19.0


def test_every_table_names_the_same_eight_markets():
    """Seven on 2026-10-05 morning; eight that evening, when interceptions
    joined (engine/passint)."""
    import calibrate, formfit, playerfit
    eight = {"pass_yds", "rush_yds", "rec_yds", "receptions", "pass_att", "pass_cmp", "rush_att", "pass_int"}
    assert set(P.MARKETS) == set(rankfit.MARKETS["cfb"]) == eight
    assert set(P._COLUMN) == set(P._POSITION) == set(P._MIN_MEAN) == eight
    for mod in (calibrate, formfit, playerfit):
        assert set(mod.SPORT_MARKETS["cfb"]) == eight, mod.__name__
    assert set(O.CFB_ODDS_TO_MARKET.values()) == eight
    assert P._POSITION["pass_att"] == P._POSITION["pass_cmp"] == P._POSITION["pass_int"] == "QB"
    assert P._POSITION["rush_att"] == "RB"
    for m in ("pass_att", "pass_cmp", "pass_int", "rush_att"):
        assert m in logwalk._POSITION


def test_the_college_request_buys_the_three_keys_behind_the_guard():
    import cfb_build as B
    keys = ("player_pass_attempts", "player_pass_completions", "player_rush_attempts")
    assert set(keys) <= set(B.PLAYER_MARKETS) and set(keys) <= O.UNPROVEN_MARKETS
    assert O.SPORT_CONFIG["cfb"]["markets"] is O.CFB_ODDS_TO_MARKET
    assert B.CREDITS_PER_EVENT == 13       # twelve that morning; thirteen with interceptions
    assert B.PLAYER_MARKETS_PRIOR == [m for m in B.PLAYER_MARKETS
                                      if m not in keys and m != "player_pass_interceptions"]
    src = open(ROOT / "cfb_build.py", encoding="utf-8").read()
    assert "for _markets in PLAYER_MARKETS_FALLBACKS" in src and "PLAYER_MARKETS_PRIOR]" in src


def test_the_harness_reads_roles_and_rates_the_way_it_says():
    import cfbmarketfit as M
    assert M.role_of("QB", {}) == "QB" and M.role_of("TE", {}) == "WR" and M.role_of("FB", {}) == "RB"
    assert M.role_of("", {"pass_att": [30, 28, 31]}) == "QB"
    assert M.role_of("", {"pass_att": [0, 0, 0], "carries": [12, 9, 10]}) == "RB"
    assert M.role_of("", {"pass_att": [0, 0], "carries": [1]}) is None
    league = {"pass_att": 30.0, "pass_int": 0.6}
    # A clean passer sits under the league rate; a reckless one above it;
    # both pulled toward 0.02 by the prior.
    clean = M.int_rate([30] * 10, [0] * 10, league)
    wild = M.int_rate([30] * 10, [2] * 10, league)
    assert clean is not None and 0.0 < clean < 0.02 < wild < 0.0667
    assert M.int_rate([30] * 2, [0] * 2, league) is None, "too few games"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
