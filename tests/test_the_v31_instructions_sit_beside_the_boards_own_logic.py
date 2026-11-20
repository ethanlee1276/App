"""Their NFL Prop Bot instructions, v3.1, beside the board's own logic (step ZZ).

Ethan, 2026-11-20, pasting "NFL Prop Bot — Master Instructions v3.1": "Those
instructions should be used alongside what we've already talked about in
finding our most likely picks and game report picks with all of our data ...
These instructions should not be replacing anything." docs/
NFL_BET_CHECKING_METHOD.md maps every section to the site. What v3.1 added
that the site did not do yet, and now does:

  * the touchdown rule's fallback is "40%+ at plus money with EV of 6%+ and
    undeniable usage" (§11) — the plus price and the 6% are new. On the public
    receipts the NFL's 63 touchdown picks at 40-45% hit 36.5%;
  * "Big favorites' QB floors are otherwise normal; do not fade them for being
    favorites" (§4): the big-favorite rule caps pass attempts only;
  * "A new starting quarterback with too few attempts to rate: no pass-catcher
    legs on that team" (§8);
  * kept off parlays (§1): a quarterback's rushing over, a quarterback's
    rush-attempt under, a backup running back's yardage;
  * touchdown tickets (§11): "Never two pass catchers from one team."

A pick breaking one stays on the board, as every rule of theirs does.

    python3 tests/test_the_v31_instructions_sit_beside_the_boards_own_logic.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gameparlays as G                                   # noqa: E402
from engine import likelyboard as LB                                  # noqa: E402
from engine import qbchange as Q                                      # noqa: E402


def _td(prob, share=None, odds=None):
    return {"market": "anytime_td", "side": "YES", "model_prob": prob, "rz_share": share, "odds": odds,
            "rz_share_measured": True}


def test_45_percent_still_meets_the_touchdown_rule_at_any_price():
    for odds in (-160, 120, None):
        got = LB.td_rule(_td(0.47, 0.10, odds))
        assert got["meets"] and "45%" in got["why"], (odds, got)


def test_the_fallback_needs_a_plus_price_that_pays_six_percent():
    # 42% with the red-zone work: at +170 a unit returns 0.42 x 1.7 - 0.58 = +13.4%.
    paid = LB.td_rule(_td(0.42, 0.35, 170))
    assert paid["meets"] and "plus price" in paid["why"], paid
    # +120 is plus money and still loses at 42% (0.42 x 1.2 - 0.58 = -7.6%).
    thin = LB.td_rule(_td(0.42, 0.35, 120))
    assert not thin["meets"], thin
    minus = LB.td_rule(_td(0.42, 0.35, -110))
    assert not minus["meets"] and "plus-money price paying 6%" in minus["why"], minus
    assert not LB.td_rule(_td(0.42, 0.35, None))["meets"], "no price, nothing to pass it on"
    assert not LB.td_rule(_td(0.42, 0.20, 170))["meets"], "the red-zone role is still asked"
    assert not LB.td_rule(_td(0.38, 0.50, 250))["meets"], "under 40% the rule has no fallback"
    assert LB.TD_RULE_FALLBACK_EV == 0.06


def test_the_exact_price_where_six_percent_starts():
    # At 40% a unit needs +165 to return 6% (0.40 x 1.65 - 0.60 = 0.06).
    assert LB.td_rule(_td(0.40, 0.30, 165))["meets"]
    assert not LB.td_rule(_td(0.40, 0.30, 160))["meets"]


def _prop(market, side="OVER", flags=(), position="QB", **kw):
    return {"kind": "prop", "player": "A", "team": "DET", "market": market, "side": side, "line": 30.5,
            "position": position, "scout_flags": list(flags), **kw}


def test_a_big_favorites_completions_and_yards_are_not_faded():
    for market in ("pass_yds", "pass_cmp", "pass_td"):
        assert LB.method_fails(_prop(market, flags=["fav_pass_over"]), "nfl") == [], market
    got = LB.method_fails(_prop("pass_att", flags=["fav_pass_over"]), "nfl")
    assert got == [LB.METHOD_AVOID["fav_pass_over"]] and "pass attempts" in got[0], got


def test_no_pass_catcher_pick_behind_a_quarterback_too_new_to_rate():
    card = {"unrated": True, "tier": "downgrade", "replacement": "Rookie Passer"}
    for market in ("receptions", "rec_yds"):
        for side in ("OVER", "UNDER"):
            got = LB.method_fails(_prop(market, side=side, position="WR", qb_card=card), "nfl")
            assert got == [LB.METHOD_NEW_QB], (market, side, got)
    assert LB.method_fails(_prop("rush_yds", position="RB", qb_card=card), "nfl") == []
    assert LB.method_fails(_prop("pass_yds", position="QB", qb_card=card), "nfl") == []
    rated = dict(card, unrated=False)
    assert LB.method_fails(_prop("receptions", position="WR", qb_card=rated), "nfl") == []
    assert LB.method_fails(_prop("receptions", position="WR", qb_card=card), "nba") == []


def _change(attempts, status="OUT"):
    return {"team": "DET", "starter": "Jared Goff", "status": status, "replacement": "Hendon Hooker",
            "tier": "downgrade", "replacement_attempts": attempts, "starter_ypa": 7.9, "replacement_ypa": None,
            "league": "nfl"}


def test_the_quarterback_card_says_when_the_new_starter_cannot_be_rated():
    assert Q.card(_change(12)).get("unrated") is True
    assert "unrated" not in Q.card(_change(Q.GREEN_ATTEMPTS)), "50 passes is enough to rate"
    assert "unrated" not in Q.card(_change(0, status="RETURNS")), "the usual starter coming back is no new starter"


READS = {("jahmyr gibbs", "DET"): {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB",
                                   "usage": {"carry_share": 0.58}},
         ("david montgomery", "DET"): {"player": "David Montgomery", "team": "DET", "pos": "RB",
                                       "usage": {"carry_share": 0.34}},
         # 8.4 carries a game, 2.5 of them scrambles: called runs. 3.1 a game, 2.4 scrambles: scrambles.
         ("jayden daniels", "WAS"): {"player": "Jayden Daniels", "team": "WAS", "pos": "QB",
                                     "usage": {"carries_pg": 8.4}},
         ("jared goff", "DET"): {"player": "Jared Goff", "team": "DET", "pos": "QB", "usage": {"carries_pg": 3.1}}}
SCRAMBLES = G.scramble_rates({"games": [{"scan": {"charting": {"scrambles": {
    "WAS": [{"name": "J.Daniels", "scrambles": 25, "weeks": 10, "yds": 210}],
    "DET": [{"name": "J.Goff", "scrambles": 24, "weeks": 10, "yds": 90}]}}}}]})


def _leg(player, market, side="OVER", position="", team="DET", **kw):
    return {"player": player, "team": team, "opponent": "NYG", "market": market, "side": side, "line": 40.5,
            "odds": -120, "p": 0.62, "position": position, **kw}


def test_what_their_rules_keep_off_parlays():
    off = lambda leg, sport="nfl": G.off_parlays(sport, leg, READS, scrambles=SCRAMBLES)   # noqa: E731
    assert SCRAMBLES == {"WAS": [("J.Daniels", 2.5)], "DET": [("J.Goff", 2.4)]}, SCRAMBLES
    assert off(_leg("Jayden Daniels", "rush_yds", position="QB", team="WAS")) == "", \
        "most of the carries are called runs: their own 12 November ticket carried this leg"
    assert off(_leg("Jared Goff", "rush_yds", position="QB")) == "qb_rush_over", "2.4 of 3.1 carries are scrambles"
    assert off(_leg("Jared Goff", "rush_att", position="QB")) == "qb_rush_over"
    assert G.off_parlays("nfl", _leg("Jared Goff", "rush_yds", position="QB"), READS) == "", \
        "no charting on file: nothing says the carries are scrambles"
    assert off(_leg("Jared Goff", "rush_att", side="UNDER", position="QB")) == "qb_rush_att_under"
    assert off(_leg("Jared Goff", "rush_yds", side="UNDER", position="QB")) == "", \
        "their list names the attempts under, not the yards under"
    assert off(_leg("Jared Goff", "pass_yds", position="QB")) == ""
    assert off(_leg("David Montgomery", "rush_yds", position="RB")) == "backup_back"
    assert off(_leg("David Montgomery", "rec_yds")) == "backup_back", "the read gives a leg its position"
    assert off(_leg("David Montgomery", "rush_att", position="RB")) == "", "yardage, not carries"
    assert off(_leg("Jahmyr Gibbs", "rush_yds", position="RB")) == "", "the lead back"
    assert off(_leg("Craig Reynolds", "rush_yds", position="RB")) == "", "no usage on file: nothing says which"
    assert off(_leg("Amon-Ra St. Brown", "receptions", position="WR", _qb_unrated=True)) == "new_qb"
    assert off(_leg("Amon-Ra St. Brown", "receptions", position="WR")) == ""
    assert off(_leg("Jared Goff", "rush_yds", position="QB"), "nba") == "", "football's rules only"
    assert set(G.OFF_PARLAY_WORDS) == {"qb_rush_over", "qb_rush_att_under", "backup_back", "new_qb"}


def _row(player, market, side, prob, position, team="DET", **kw):
    return {"player": player, "team": team, "opponent": "NYG", "home": "DET", "away": "NYG", "market": market,
            "side": side, "line": 40.5, "odds": -130, "book": "FanDuel", "model_prob": prob, "has_market": True,
            "position": position, "bettable": True, "game_date": "2099-01-01", "kickoff": "2099-01-01T18:00:00Z", **kw}


def test_the_boards_legs_leave_those_picks_out_and_the_pick_stays_a_pick():
    rows = [_row("Jahmyr Gibbs", "rush_yds", "OVER", 0.66, "RB"),
            _row("David Montgomery", "rush_yds", "OVER", 0.65, "RB"),
            _row("Jared Goff", "rush_att", "UNDER", 0.70, "QB"),
            _row("Amon-Ra St. Brown", "receptions", "OVER", 0.68, "WR", qb_card={"unrated": True})]
    board = {"sport": "nfl", "most_likely": rows, "recommendations": [],
             "games": [{"home": "DET", "away": "NYG", "date": "2099-01-01", "kickoff": "2099-01-01T18:00:00Z"}],
             "scan_reads": {"NYG@DET": {"players": list(READS.values())}}}
    legs = {l["player"] for l in G.legs_for(board, "nfl")}
    assert legs == {"Jahmyr Gibbs"}, legs
    assert len(board["most_likely"]) == 4, "nothing is taken off the board"
    hoops = dict(board, sport="nba")
    assert len(G.legs_for(hoops, "nba")) == 4, "another league's legs are untouched"
    assert "our_rule" in G.PICK_FATES


def _scorer(player, position, team="DET"):
    # As the scorer legs reach a ticket: the side normalised (gameparlays._norm_side).
    return G._norm_side({"player": player, "team": team, "opponent": "NYG" if team == "DET" else "DET",
                         "market": "anytime_td", "side": "YES", "line": 0.5, "odds": 140, "p": 0.40,
                         "position": position})


def test_never_two_pass_catchers_from_one_team_on_a_touchdown_ticket():
    game = {"home": "DET", "away": "NYG", "spread": -6.5, "total": 47.5}
    fits, _rho, why, _cav = G.pair_link("nfl", _scorer("Amon-Ra St. Brown", "WR"), _scorer("Sam LaPorta", "TE"), game)
    assert not fits and "two pass catchers from one team" in why, why
    assert G.pair_link("nfl", _scorer("Amon-Ra St. Brown", "WR"), _scorer("Jahmyr Gibbs", "RB"), game)[0], \
        "a back beside a catcher still fits"
    assert G.pair_link("nfl", _scorer("Amon-Ra St. Brown", "WR"), _scorer("Malik Nabers", "WR", "NYG"), game)[0], \
        "one from each side fits"
    assert G.pair_link("nfl", _scorer("A", ""), _scorer("B", ""), game)[0], "no position on file: nothing to tell"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
