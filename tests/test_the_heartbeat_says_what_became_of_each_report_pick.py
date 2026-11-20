"""The heartbeat says what became of each report pick as a parlay leg
(2026-11-19, PICKLEGS1).

Ethan, 2026-11-19: "work on the game reports and make better picks and make
better selections with the information we're given ... the parlays we make are
not doing good, so work on that." A game's three-leg tickets are its report's
own picks (GPLEGS1), and on the Thursday the Sunday props were bought three
Sunday games' reports carried 12 player picks of which the board priced 3 as
legs. The heartbeat said how many, and nothing said what the other nine were:
a tackle (no parlay carries one), a benched market, a matchup pick no leg
source holds, a scorer the touchdown field prices alone, a row a leg source
refuses, or the player's line at another number.

What these hold:

  * `gameparlays._picks_census` sorts each of a report's player picks into one
    fate (PICK_FATES), counts only, and `from_report` keeps them on the game's
    entry (``pick_fates``); a report with no player pick keeps none;
  * the heartbeat adds a league's up over its games still to play
    (``pick_fates``, with ``picks`` their sum), and a started game's kept
    entry is not counted;
  * no pick rides in either: a count per fate, never a name.

    python3 tests/test_the_heartbeat_says_what_became_of_each_report_pick.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
SUNDAY = {"home": "PHI", "away": "DAL", "date": "2099-11-15", "kickoff": "13:00"}
THURSDAY = dt.datetime(2099, 11, 12, 14, 0)


def _rec(player, market, p, line=2.5, team="PHI", book="DraftKings"):
    return {"player": player, "team": team, "opponent": "DAL" if team == "PHI" else "PHI", "home": "PHI",
            "away": "DAL", "position": "WR", "market": market, "side": "Over", "line": line, "odds": -150,
            "book": book, "hit_prob": p, "has_market": True, "recommended": False, "game_date": "2099-11-15",
            "kickoff": "2099-11-15T13:00:00-05:00", "reasons": [f"Projection clears {line}"]}


def _pick(player, market, line=2.5, side="OVER"):
    return {"player": player, "market": market, "side": side, "line": line}


def _board():
    b = EG.board()
    b["games"] = b["games"] + [SUNDAY]
    b["recommendations"] = (
        [_rec("S Strong", "receptions", 0.66), _rec("F Fill", "rush_att", 0.55, team="DAL"),
         _rec("L Low", "rec_yds", 0.45), _rec("O Line", "receptions", 0.62, line=2.5),
         # A row a leg source holds and will not use: no real book behind its price.
         _rec("R Refused", "rush_yds", 0.64, book="proxy")]
        # Enough priced props that the game is past waiting on its props (PROPS_BOUGHT_MIN).
        + [_rec(f"P {i}", "rec_yds", 0.51, team="DAL" if i % 2 else "PHI") for i in range(GP.PROPS_BOUGHT_MIN)])
    b["matchup_picks"] = [{"game": "DAL@PHI", "home": "PHI", "away": "DAL", "td": [],
                           "props": [{"player": "M Matchup", "team": "PHI", "market": "rush_yds", "side": "OVER",
                                      "line": 48.5, "odds": -120, "book": "FanDuel", "model_prob": 0.58}]}]
    b["td_field"] = [{"player": "T Dee", "team": "PHI", "market": "anytime_td", "odds": 120, "model_prob": 0.44}]
    return b


PICKS = [_pick("S Strong", "receptions"), _pick("F Fill", "rush_att"), _pick("L Low", "rec_yds"),
         _pick("K Tackler", "tackles_ast", 6.5), _pick("B Bench", "pass_cmp", 21.5),
         _pick("O Line", "receptions", 4.5), _pick("R Refused", "rush_yds"),
         _pick("M Matchup", "rush_yds", 48.5), _pick("T Dee", "anytime_td", 0.5), _pick("Q Nobody", "rec_yds", 40.5),
         # A game bet is no player pick: never counted.
         {"player": "PHI", "market": "moneyline", "side": "OVER", "line": 0.5, "game": True}]


def test_a_refused_pick_says_why():
    """A row a leg source holds and will not use, by why: ruled out, no real book, past the price cap, a
    number the Edge path refuses; the first of those any of its rows shows."""
    ok = _rec("X", "rec_yds", 0.6)
    assert GP._refused_why([dict(ok, injury_status="Out")]) == "refused_out"
    assert GP._refused_why([dict(ok, book="proxy")]) == GP._refused_why([dict(ok, bettable=False)]) == "refused_book"
    assert GP._refused_why([dict(ok, odds=None)]) == "refused_book"
    assert GP._refused_why([dict(ok, odds=-400)]) == "refused_price", "past the -250 cap: no parlay leg"
    assert GP._refused_why([dict(ok, raw_prob=0.80, fair_prob=0.55)]) == "refused_edge", "25 points off the fair price"
    assert GP._refused_why([dict(ok, odds=-400), dict(ok, injury_status="OUT")]) == "refused_out"
    assert GP._refused_why([ok]) == "refused" and GP._refused_why([]) == "refused"
    # A row with a real price speaks first (20 November 2026): a pick held by a priced row and a projection
    # with no market is refused for its priced row's reason, not "no real book".
    proj = dict(ok, has_market=False, odds=None, book="")
    assert GP._refused_why([dict(ok, odds=-400), proj]) == "refused_price"
    assert GP._refused_why([proj, dict(ok, raw_prob=0.80, fair_prob=0.55)]) == "refused_edge"
    assert GP._refused_why([proj, ok]) == "refused", "priced and usable: the reason is something else"
    assert GP._refused_why([proj, dict(ok, book="proxy")]) == "refused_book", "no row with a real price"
    assert GP._refused_why([proj, dict(ok, injury_status="Out")]) == "refused_out"
    assert {"refused_out", "refused_book", "refused_price", "refused_edge", "refused"} <= set(GP.PICK_FATES)


def test_each_pick_is_sorted_into_one_fate():
    b = _board()
    b["game_parlays"] = GP.build(b, "nfl", now=THURSDAY)
    x = GP.from_report(b, "nfl", SUNDAY, PICKS, now=THURSDAY)
    assert x["report_picks"] == 10, x["report_picks"]
    assert x["pick_fates"] == {"strong": 1, "fill": 1, "low": 1, "no_parlay": 1, "benched": 1, "other_line": 1,
                               "refused_book": 1, "matchup_only": 1, "scorer_only": 1, "absent": 1}, x["pick_fates"]
    assert sum(x["pick_fates"].values()) == x["report_picks"], "every player pick has exactly one fate"
    assert set(x["pick_fates"]) <= set(GP.PICK_FATES)
    # Counts and nothing else: no name rides in the entry's census.
    assert all(isinstance(v, int) for v in x["pick_fates"].values())
    assert not any(p["player"] in json.dumps(x["pick_fates"]) for p in PICKS)
    # A report with no player pick keeps none, and a rebuild clears an older one.
    x["pick_fates"] = {"strong": 9}
    GP.from_report(b, "nfl", SUNDAY, [PICKS[-1]], now=THURSDAY)
    assert "pick_fates" not in x, x.get("pick_fates")
    assert GP._picks_census(b, "nfl", SUNDAY, [], now=THURSDAY) == {}
    assert GP._picks_census({}, "nfl", SUNDAY, PICKS, now=THURSDAY).get("no_parlay") == 1, "a bare board: never raises"


def test_the_heartbeat_adds_a_leagues_up_over_its_games_still_to_play():
    import launch as L
    t = {"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}
    games = [{"home": "A", "threes": [t, t], "pick_fates": {"strong": 4, "no_parlay": 1}},
             {"home": "B", "threes": [], "legs_wider": 9, "legs_own": 1, "legs_from": "report", "report_picks": 4,
              "picks_priced": 1, "pick_fates": {"strong": 1, "matchup_only": 2, "scorer_only": 1}},
             # A started game's kept entry is the record's now: not counted.
             {"home": "C", "threes": [t, t], "kept": "Sun 1:00 PM ET", "pick_fates": {"strong": 6}},
             {"home": "D", "threes": [t, t]}]
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": games, "counts": {"games": 4, "threes": 6}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["pick_fates"] == {"picks": 9, "strong": 5, "no_parlay": 1, "matchup_only": 2, "scorer_only": 1}, got
    # A league whose reports carry no player pick says nothing.
    for g in games:
        g.pop("pick_fates", None)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            assert "pick_fates" not in L._board_counts(path)
        finally:
            L._full_copy = was


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
