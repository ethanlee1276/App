"""Live picks: pre-game journal rows tracked while their games run.

The rules under test: only LIVE games qualify (pre-game picks on unstarted
games stay in Tonight's Picks; finished ones settle overnight); progress
comes from the live boxscore and can lock an over ("cleared") or kill an
under ("busted") early; doubleheader legs route by game_number; and the
boxscore parser turns a raw MLB Stats payload into per-market lines.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.livepicks import assemble_live_picks
from engine.mlb.livestats import parse_live_stats


BOX = {"teams": {"home": {"players": {
    "ID1": {"person": {"fullName": "Freddie Freeman"},
            "stats": {"batting": {"hits": 2, "doubles": 1, "triples": 0,
                                  "homeRuns": 0}}},
    "ID2": {"person": {"fullName": "Ace Arm"},
            "stats": {"pitching": {"strikeOuts": 5, "inningsPitched": "5.2"},
                      "batting": {}}},
}}, "away": {"players": {
    "ID3": {"person": {"fullName": "Slug Away"},
            "stats": {"batting": {"hits": 1, "doubles": 0, "triples": 0,
                                  "homeRuns": 1}}},
}}}}


def test_parse_live_stats_computes_the_journal_markets():
    p = parse_live_stats(BOX)
    fred = p["freddie freeman"]
    assert fred["hits"] == 2 and fred["total_bases"] == 3     # 1B + 2B
    assert p["ace arm"]["strikeouts"] == 5
    slug = p["slug away"]
    assert slug["home_runs"] == 1 and slug["total_bases"] == 4  # 1B + HR


def _bet(player, market, side="OVER", line=1.5, odds=-110, stake=0.5):
    return {"player": player, "market": market, "side": side, "line": line,
            "odds": odds, "stake_units": stake}


def _rec(player, market, team, opp, gn=0):
    return {"player": player, "market": market, "market_label": market,
            "team": team, "opponent": opp, "game_number": gn}


LIVE_G = {"home": "LAD", "away": "SF", "game_number": 1,
          "live": {"state": "live", "period": "Top 6th",
                   "home_score": 3, "away_score": 2}}
PREGAME_G = {"home": "NYY", "away": "BOS",
             "live": {"state": "scheduled"}}


def test_only_live_games_qualify():
    bets = [_bet("Freddie Freeman", "total_bases"),
            _bet("Aaron Judge", "total_bases")]
    recs = [_rec("Freddie Freeman", "total_bases", "LAD", "SF"),
            _rec("Aaron Judge", "total_bases", "NYY", "BOS")]
    rows = assemble_live_picks(bets, recs, [LIVE_G, PREGAME_G],
                               parse_live_stats(BOX))
    assert [r["player"] for r in rows] == ["Freddie Freeman"]
    r = rows[0]
    assert r["status"] == "cleared"            # 3 TB > 1.5 — over locked in
    assert r["current"] == 3
    assert r["game"]["period"] == "Top 6th"


def test_under_can_bust_early_and_over_tracks():
    bets = [_bet("Freddie Freeman", "total_bases", side="UNDER", line=2.5),
            _bet("Ace Arm", "strikeouts", side="OVER", line=6.5)]
    recs = [_rec("Freddie Freeman", "total_bases", "LAD", "SF"),
            _rec("Ace Arm", "strikeouts", "LAD", "SF")]
    rows = assemble_live_picks(bets, recs, [LIVE_G], parse_live_stats(BOX))
    by = {r["player"]: r for r in rows}
    assert by["Freddie Freeman"]["status"] == "busted"    # 3 TB > under 2.5
    assert by["Ace Arm"]["status"] == "tracking"          # 5 Ks vs over 6.5
    # Cleared/busted ordering: good news first, busts last.
    assert rows[-1]["player"] == "Freddie Freeman"


def test_team_bets_and_doubleheaders_route_correctly():
    g2 = {**LIVE_G, "game_number": 2, "doubleheader": True}
    g1_final = {"home": "LAD", "away": "SF", "game_number": 1,
                "doubleheader": True, "live": {"state": "final"}}
    bets = [_bet("LAD", "moneyline", line=0.5),
            _bet("Cal Raleigh", "total_bases")]
    recs = [_rec("Cal Raleigh", "total_bases", "LAD", "SF", gn=2)]
    rows = assemble_live_picks(bets, recs, [g1_final, g2], {})
    assert {r["market"] for r in rows} == {"moneyline", "total_bases"}
    prop = next(r for r in rows if r["market"] == "total_bases")
    assert prop["game"]["game_number"] == 2       # routed to the live leg
    assert prop["status"] == "tracking" and prop["current"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
