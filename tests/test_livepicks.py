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


def test_every_open_bet_gets_a_phase():
    """Live bets track, not-started bets show as upcoming — the section
    answers "where are my 5 open bets" in ALL states, not just mid-game."""
    bets = [_bet("Freddie Freeman", "total_bases"),
            _bet("Aaron Judge", "total_bases")]
    recs = [_rec("Freddie Freeman", "total_bases", "LAD", "SF"),
            _rec("Aaron Judge", "total_bases", "NYY", "BOS")]
    rows = assemble_live_picks(bets, recs, [LIVE_G, PREGAME_G],
                               parse_live_stats(BOX))
    assert [r["player"] for r in rows] == ["Freddie Freeman", "Aaron Judge"]
    live, upcoming = rows
    assert live["status"] == "cleared"         # 3 TB > 1.5 — over locked in
    assert live["current"] == 3 and live["game"]["period"] == "Top 6th"
    assert upcoming["status"] == "upcoming" and upcoming["phase"] == "upcoming"


def test_final_games_grade_provisionally():
    """A finished game grades on the spot — prop from the boxscore stat,
    moneyline from the final score — flagged pending until the official
    overnight settle."""
    final_g = {"home": "LAD", "away": "SF", "game_number": 1,
               "live": {"state": "final", "home_score": 5, "away_score": 2}}
    bets = [_bet("Freddie Freeman", "total_bases", side="OVER", line=1.5),
            _bet("Ace Arm", "strikeouts", side="OVER", line=6.5),
            _bet("LAD", "moneyline", line=0.5),
            _bet("SF", "moneyline", line=0.5)]
    recs = [_rec("Freddie Freeman", "total_bases", "LAD", "SF"),
            _rec("Ace Arm", "strikeouts", "LAD", "SF")]
    rows = assemble_live_picks(bets, recs, [final_g], parse_live_stats(BOX))
    by = {(r["player"], r["market"]): r for r in rows}
    assert by[("Freddie Freeman", "total_bases")]["status"] == "won_pending"   # 3 > 1.5
    assert by[("Ace Arm", "strikeouts")]["status"] == "lost_pending"           # 5 < 6.5
    assert by[("LAD", "moneyline")]["status"] == "won_pending"                 # 5-2
    assert by[("SF", "moneyline")]["status"] == "lost_pending"
    # Winners sort ahead of losers, everything ahead of upcoming.
    assert rows[0]["status"] == "won_pending"


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


def test_unmatchable_bets_still_show():
    """An open bet the current board can't place (lineup changed, prop
    dropped this cycle) must STILL appear — the section's count has to
    match the Record's open count, always."""
    bets = [_bet("Ghost Hitter", "total_bases"),
            _bet("Freddie Freeman", "total_bases")]
    recs = [_rec("Freddie Freeman", "total_bases", "LAD", "SF")]
    rows = assemble_live_picks(bets, recs, [LIVE_G], parse_live_stats(BOX))
    assert len(rows) == 2
    ghost = next(r for r in rows if r["player"] == "Ghost Hitter")
    assert ghost["status"] == "unmapped" and ghost["phase"] == "upcoming"
    assert rows[-1] is ghost                     # unmapped sorts last


# Runner at the TRUE END — a test defined after it never runs.
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
