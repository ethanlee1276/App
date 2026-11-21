"""Touchdown tickets stay apart from stat parlays, and a game line is no player prop (step AAH, 2026-11-21).

Ethan's own instructions (NFL Prop Bot v3.1, section 1): "2-leg parlays by default. 3+ legs only when
asked. TD parlays stay separate from stat parlays." Section 11: "TD MODULE (separate from stat parlays, 2
legs maximum)." The site said it did this ("Touchdown pairs are their own tickets, and prop tickets carry
player props only"), and it did not: a Most Likely touchdown pick was a leg like any other, and a Most
Likely moneyline row became a leg with nothing to say it was a game line.

How it was found. The heartbeat counts the parlay legs with no book at their number. Two readings of the
code named causes the next board did not bear out (picks carried at a posted number: 0 legs; an under's
price lost to its book's ladder: 3 legs), so the heartbeat was made to count the kind of each such leg
(launch._board_counts ``one_book_gaps``). The NFL's 32 were 28 anytime-touchdown legs and 4 moneylines.
What these hold:

  * In football a touchdown scorer is no leg of a three-leg or two-leg stat ticket; it rides the touchdown
    pairs, which are built as they were.
  * A game line (moneyline, spread, total, team total) is no leg of one in any league.
  * Hockey's goal scorers are left as they were, and the heartbeat counts them.
  * A report's touchdown pick says where it went (the pick census, "td_apart").
  * A scorer leg carries no line: its number is 0.5, so its books can be read.

    python3 tests/test_touchdown_tickets_stay_apart_from_stat_parlays.py
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, likely  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME
STAT = ("threes", "twos")


def _scorer(market="anytime_td", line=None):
    """A Most Likely scorer pick: likelier than every stat pick on the fixture board, and with no line."""
    r = EG._td("Cam Skattebo", "NYG", "RB", 0.74, -240)
    r.update(market=market, market_label="Anytime TD" if market == "anytime_td" else "Anytime Goal", line=line,
             book="DraftKings")
    return r


def _moneyline():
    return {"player": "Giants", "team": "NYG", "opponent": "WAS", "home": "NYG", "away": "WAS", "kind": "game",
            "market": "moneyline", "market_label": "Moneyline", "side": "", "line": None, "odds": -180,
            "book": "DraftKings", "model_prob": 0.73, "game_date": "2099-11-12",
            "kickoff": "2099-11-12T20:15:00-05:00"}


def _board(*extra):
    b = EG.board()
    b["most_likely"] = list(extra) + b["most_likely"]
    return b


def _markets(legs):
    return {l.get("market") for l in legs}


def _ticket_markets(g):
    return {l.get("market") for k in STAT for t in g.get(k) or [] for l in t["legs"]}


def test_in_football_a_touchdown_scorer_is_no_stat_leg():
    for sport in ("nfl", "cfb"):
        legs = GP.legs_for(_board(_scorer(), _scorer("first_td")), sport)
        assert legs and not _markets(legs) & {"anytime_td", "first_td"}, (sport, _markets(legs))
    assert GP.SCORERS_APART == ("nfl", "cfb") == GP.OFF_PARLAY_SPORTS
    assert GP._TD == ("anytime_td", "first_td", "anytime_scorer")
    # A quarterback's passing touchdowns are a stat, not a scorer.
    qb = EG._ml("Jayden Daniels", "WAS", "QB", "pass_td", "Over", 0.5, 0.71, -230, "Passing TDs")
    assert "pass_td" in _markets(GP.legs_for(_board(qb), "nfl"))


def test_a_game_line_is_no_stat_leg_in_any_league():
    for sport in ("nfl", "cfb", "nba", "nhl", "mlb"):
        legs = GP.legs_for(_board(_moneyline()), sport)
        assert "moneyline" not in _markets(legs), sport
    for market in ("spread", "total", "team_total"):
        assert market not in _markets(GP.legs_for(_board(dict(_moneyline(), market=market, line=-2.5)), "nfl"))
    assert GP.GAME_LINE_MARKETS == likely.GAME_MARKETS, "the Most Likely board's own game markets"


def test_no_stat_ticket_holds_one_and_the_touchdown_pairs_are_built_as_they_were():
    b = _board(_scorer(), _moneyline())
    g = GP.build(b, "nfl")["games"][0]
    assert len(g["threes"]) == 3 and len(g["twos"]) == 3
    assert not _ticket_markets(g) & {"anytime_td", "moneyline"}, _ticket_markets(g)
    # The same tickets a board without those two rows makes: they changed nothing.
    plain = GP.build(EG.board(), "nfl")["games"][0]
    for k in STAT:
        assert [GP.ident(t) for t in g[k]] == [GP.ident(t) for t in plain[k]], k
    # The touchdown pairs come off the touchdown field (`scorer_legs`), untouched.
    assert len(g["scorers"]) == 3 and [GP.ident(t) for t in g["scorers"]] == [GP.ident(t) for t in plain["scorers"]]
    assert {l["market"] for t in g["scorers"] for l in t["legs"]} == {"anytime_td"}
    # A report's rebuild is held to the same.
    tp = __import__("test_the_parlays_are_made_of_the_reports_picks")
    b["game_parlays"] = GP.build(b, "nfl")
    picks = tp.PICKS + [tp._pick("Cam Skattebo", "anytime_td", "OVER", None)]
    x = GP.from_report(b, "nfl", GAME, picks)
    assert not _ticket_markets(x) & {"anytime_td", "moneyline"}
    assert x["pick_fates"].get("td_apart") == 1, x["pick_fates"]
    assert GP.PICK_FATES[:2] == ("read", "td_apart")


def test_hockeys_goal_scorers_are_left_as_they_were():
    legs = GP.legs_for(_board(_scorer("anytime_goal")), "nhl")
    assert "anytime_goal" in _markets(legs), "its tickets are not v3.1's, and its record is good"
    assert "nhl" not in GP.SCORERS_APART


def test_a_scorer_legs_number_is_a_half():
    leg = {"player": "Cam Skattebo", "market": "anytime_goal", "side": "Over", "line": None}
    assert GP._leg_line(leg) == 0.5 and GP._leg_line(dict(leg, market="anytime_td")) == 0.5
    assert GP._leg_line(dict(leg, market="goals", line=1.5)) == 1.5, "its own line where it has one"
    assert GP._leg_line({"player": "X", "market": "receptions", "line": None}) is None
    assert GP._leg_line({"player": "X", "market": "receptions", "line": "4.5"}) == 4.5 and GP._leg_line(None) is None
    board = {"recommendations": [{"player": "Cam Skattebo", "market": "anytime_goal", "side": "OVER", "line": 0.5,
                                  "all_lines": [{"book": "DraftKings", "line": 0.5, "over_odds": 150, "under_odds": 0},
                                                {"book": "FanDuel", "line": 0.5, "over_odds": 160, "under_odds": 0}]}]}
    idx = GP.quote_index(board)
    assert GP.book_prices(leg, idx) == {"draftkings": ("DraftKings", 150), "fanduel": ("FanDuel", 160)}
    assert GP.leg_quoted(leg, idx) == "quoted" and GP.leg_gap(leg, board) is None
    # A stat leg with no number still has nothing to read, and says so.
    assert GP.book_prices({"player": "Cam Skattebo", "market": "anytime_goal_x", "side": "Over", "line": None}, idx) == {}


def _counts(b):
    import launch as L
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            return L._board_counts(path)
        finally:
            L._full_copy = was


def test_the_heartbeat_counts_scorers_on_stat_tickets():
    b = _board(_scorer(), _moneyline())
    GP.attach(b, "nfl")
    got = _counts(b)
    assert got["scorer_legs_on_props"] == 0, got.get("scorer_legs_on_props")
    # (The fixture files no book's quotes, so its legs read "no_quote"; none of them is a scorer or a game line,
    # which is what the NFL's 32 were.)
    kinds = (got.get("one_book_gaps") or {}).get("market") or {}
    assert not set(kinds) & {"anytime_td", "moneyline"}, kinds
    # Hockey, where a goal scorer may still ride one.
    h = _board(_scorer("anytime_goal"))
    GP.attach(h, "nhl")
    n = sum(l["market"] == "anytime_goal" for g in h["game_parlays"]["games"] for k in STAT for t in g.get(k) or []
            for l in t["legs"])
    assert n >= 1 and _counts(h)["scorer_legs_on_props"] == n
    # A league with no scorer market says nothing of them.
    nba = EG.board()
    GP.attach(nba, "nba")
    assert "scorer_legs_on_props" not in _counts(nba)


if __name__ == "__main__":
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
