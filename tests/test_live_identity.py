"""A live bet must keep its game and its face after the market is pulled.

Ethan, 2026-08-13, on a Live Now screenshot: "this seems like its a
problem. it says it couldnt map the game AND its not showing the
heashshots of the players."

TWO SYMPTOMS, ONE CAUSE, and the shape of the failure is what named it.
Every unmapped row in that screenshot was a PITCHER prop — Davis Martin,
Andrew Abbott and Logan Gilbert strikeouts, Parker Messick and Kevin
Gausman outs — while the hitter props beside them (Chourio, Ohtani home
runs) mapped fine and carried real photos. A name-matching bug does not
sort itself by position. Market availability does: a book pulls its
pre-game pitcher markets the moment first pitch passes, and the tracker
placed a prop ONLY by an exact (player, market) hit on tonight's board.
No row, no game — and because the face was read off that same row, no
photo either.

The page's own footnote already promised the opposite: "a bet journals the
moment it's recommended and stays here until it settles — even if the pick
later drops off Tonight's Picks because prices moved." So the mapping was
contradicting the stated design rather than the design being unclear.

Three sources now answer the question, and the split between them is the
point: the exact-market row is still the ONLY one allowed to name the
bet's market, while placement and identity fall through to the same
player on any market, and then to the roster feed, which has no idea what
tonight's prices are.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.livepicks import assemble_live_picks
from engine import rosters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()

FACE = "https://img.mlbstatic.com/mlb-photos/.../663554/headshot/67/current"
LIVE_GAME = {"home": "SEA", "away": "CWS", "game_number": 1,
             "date": "2026-08-13", "kickoff": "2026-08-14T02:10:00Z",
             "live": {"state": "live", "period": "Top 3rd",
                      "home_score": 1, "away_score": 0}}
# The bet as the journal holds it: no team, no opponent, no face. That is
# the whole difficulty — the journal stores what was BET, not who he is.
K_BET = {"player": "Logan Gilbert", "market": "strikeouts", "side": "OVER",
         "line": 5.5, "odds": -115, "stake_units": 0.9}
IDENT = {"Logan Gilbert": {"team": "SEA", "headshot": FACE}}


# --- the mapping ------------------------------------------------------------
def test_a_pulled_market_no_longer_costs_the_bet_its_game():
    """The reported bug, reproduced at its own level: an empty board."""
    rows = assemble_live_picks([K_BET], [], [LIVE_GAME], {}, [], IDENT)
    assert len(rows) == 1
    assert rows[0]["status"] != "unmapped", \
        "the identity map was not consulted, so a live bet found no game"
    assert rows[0]["phase"] == "live"
    assert rows[0]["game"]["home"] == "SEA"


def test_and_it_keeps_its_face():
    rows = assemble_live_picks([K_BET], [], [LIVE_GAME], {}, [], IDENT)
    assert rows[0]["headshot"] == FACE


def test_without_the_identity_map_it_still_degrades_to_unmapped():
    """The negative control. If this passed either way, the test above
    would be proving nothing about the fallback."""
    rows = assemble_live_picks([K_BET], [], [LIVE_GAME], {}, [])
    assert rows[0]["status"] == "unmapped"


def test_the_same_player_on_another_market_places_the_bet():
    """Rung two. A pitcher whose strikeouts came down but whose outs are
    still up is in a game, and it is the same game either way."""
    outs = {"player": "Logan Gilbert", "team": "SEA", "opponent": "CWS",
            "market": "outs", "market_label": "Outs Recorded",
            "headshot": FACE}
    rows = assemble_live_picks([K_BET], [outs], [LIVE_GAME], {}, [])
    assert rows[0]["status"] != "unmapped"
    assert rows[0]["game"]["home"] == "SEA"


def test_a_cross_market_match_never_renames_the_bets_market():
    """THE TRAP IN THE FALLBACK, and the reason placement and labelling
    are two questions here rather than one.

    Borrowing a row for its team is safe. Borrowing it for its LABEL is
    not: it would print "Home Runs" over a strikeouts bet, which trades an
    honest "unmapped" for a confident wrong one — worse than the bug, and
    invisible on a page whose whole job is to be believed.
    """
    hr = {"player": "Logan Gilbert", "team": "SEA", "opponent": "CWS",
          "market": "home_runs", "market_label": "Home Runs 0.5+",
          "headshot": FACE}
    rows = assemble_live_picks([K_BET], [hr], [LIVE_GAME], {}, [])
    assert rows[0]["market"] == "strikeouts"
    assert "Home Run" not in rows[0]["market_label"], rows[0]["market_label"]


def test_an_exact_market_row_still_wins():
    """The fallbacks are a floor, not a replacement. When tonight's board
    does have the bet, its opponent and leg are richer than the roster's
    single team abbreviation and must keep being used."""
    exact = {"player": "Logan Gilbert", "team": "SEA", "opponent": "CWS",
             "market": "strikeouts", "market_label": "Strikeouts",
             "headshot": FACE}
    rows = assemble_live_picks([K_BET], [exact], [LIVE_GAME], {},
                               [], {"Logan Gilbert": {"team": "WRONG"}})
    assert rows[0]["team"] == "SEA"
    assert rows[0]["market_label"] == "Strikeouts"


def test_an_unmappable_bet_still_shows_its_face():
    """Not knowing which field a man is on is no reason to stop knowing
    what he looks like. The unmapped rows going faceless is half of what
    was reported, and it is a separate half — a bet whose game is not on
    tonight's slate at all still renders as a row, and that row should
    look like a person."""
    rows = assemble_live_picks([K_BET], [], [], {}, [], IDENT)
    assert rows[0]["status"] == "unmapped"
    assert rows[0]["headshot"] == FACE


def test_a_team_market_never_borrows_a_face():
    """`player` holds an ABBREVIATION on a moneyline and "AWAY@HOME" on a
    game total. A name lookup on either is a lookup for a player who does
    not exist, and any hit would be a collision."""
    ml = {"player": "SEA", "market": "moneyline", "side": "OVER",
          "line": 0.5, "odds": -140, "stake_units": 1.0}
    rows = assemble_live_picks([ml], [], [LIVE_GAME], {}, [],
                               {"SEA": {"team": "SEA", "headshot": FACE}})
    assert rows[0]["headshot"] == ""


# --- the identity map itself ------------------------------------------------
def _logs_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
                 "period TEXT, game_id TEXT, player TEXT, team TEXT, "
                 "opponent TEXT, position TEXT, home INTEGER, market TEXT, "
                 "value REAL)")
    return conn


def test_the_map_reads_every_market_not_the_appearance_market():
    """`from_game_logs` keys MLB on plate appearances, and in the
    universal-DH era no pitcher has one. Reusing that query here would
    have produced a map missing precisely the players it exists to
    rescue — the same defect, one file over, wearing a different name.
    """
    conn = _logs_db()
    conn.executemany(
        "INSERT INTO player_game_logs (sport, period, player, team, market, "
        "value) VALUES ('mlb', ?, ?, ?, ?, ?)",
        [("2026-08-10", "Logan Gilbert", "SEA", "strikeouts", 7.0),
         ("2026-08-10", "Cal Raleigh", "SEA", "pa", 4.0)])
    m = rosters.identity_map(conn, "mlb")
    assert m.get("Logan Gilbert", {}).get("team") == "SEA", \
        "a pitcher has no plate appearances and must still be found"


def test_a_traded_player_maps_to_his_current_club():
    conn = _logs_db()
    conn.executemany(
        "INSERT INTO player_game_logs (sport, period, player, team, market, "
        "value) VALUES ('mlb', ?, ?, ?, 'strikeouts', 6.0)",
        [("2026-06-01", "Journeyman Arm", "CWS"),
         ("2026-08-10", "Journeyman Arm", "SEA")])
    assert rosters.identity_map(conn, "mlb")["Journeyman Arm"]["team"] == "SEA"


def test_no_logs_table_is_no_identities_not_a_crash():
    """The tracker is a convenience on top of the journal. A database
    without the table must cost the fallback, never the page."""
    bare = sqlite3.connect(":memory:")
    assert rosters.identity_map(bare, "nfl") == {}


def test_the_build_never_lets_the_map_take_the_slate_down():
    """It reaches a feed and a database, so it can fail. Everything on
    this page is journaled facts that exist with or without it."""
    i = BUILD.index("identity_map(_hconn")
    block = BUILD[max(0, i - 900):i + 400]
    assert "try:" in block and "except Exception" in block
    assert "_ident = {}" in block, "a failure must leave an empty map, not raise"


def test_the_tracker_is_wired_to_it():
    """A fallback nobody passes is a fallback that does not exist — the
    exact failure mode of the long-shot board before it was wired in."""
    assert BUILD.count("_ident") >= 4, \
        "both assemble_live_picks calls must receive the identity map"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
