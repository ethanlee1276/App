"""The team you are actually playing — head-to-head league sync (IDEAS #7).

The League Desk read your Sleeper league before this and answered every
question against the FIELD: here is your best lineup, here are the trades
available. You do not play the field. You play one specific roster this
week, and that changes which start is right.

THE CLAIM UNDER TEST, and it is the only interesting one: ranking bench
swaps by their effect on WIN PROBABILITY rather than on projected points
reproduces the advice every fantasy column gives — favourites want
floors, underdogs want ceilings — without anybody writing that rule
down. Two tests below run the same roster at +12 and at −12 and watch
the answer flip. Nothing in `engine/fantasy_h2h.py` knows the words
"favourite" or "underdog"; it knows a normal CDF.

The spread that makes any of it possible is measured, not assumed:
`fantasy_lineup.per_game` now carries `_sd`, the player's own weekly
standard deviation, with his POSITION's pooled spread standing in for
anyone too thin to have one of his own. A rookie with two identical
games would otherwise report certainty.

Run directly: `python3 tests/test_fantasy_h2h.py`
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import fantasy_h2h as H                           # noqa: E402
from engine import fantasy_lineup as fl                       # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# --- whose game is it ------------------------------------------------------

BOARD = [{"roster_id": 1, "matchup_id": 7}, {"roster_id": 4, "matchup_id": 7},
         {"roster_id": 2, "matchup_id": 8}, {"roster_id": 3, "matchup_id": 8}]


def test_the_opponent_comes_off_the_leagues_own_board():
    assert H.opponent_roster_id(BOARD, 1) == 4
    assert H.opponent_roster_id(BOARD, 4) == 1
    assert H.opponent_roster_id(BOARD, "2") == 3


def test_a_bye_or_an_unscheduled_league_names_nobody():
    """Picking somebody at random would be worse than saying nothing:
    every number on the panel would be about a game not being played."""
    assert H.opponent_roster_id(BOARD, 99) is None
    assert H.opponent_roster_id([], 1) is None
    assert H.opponent_roster_id([{"roster_id": 1, "matchup_id": 7}], 1) is None
    assert H.opponent_roster_id(BOARD, None) is None


# --- the table -------------------------------------------------------------

def test_the_standings_read_sleepers_split_points_fields():
    """Sleeper splits a team's points across `fpts` and `fpts_decimal`,
    and reading only the first loses the tenths that decide half the
    leagues in the country."""
    rows = H.standings([
        {"roster_id": 1, "owner_id": "u1",
         "settings": {"wins": 3, "losses": 1, "fpts": 412, "fpts_decimal": 55,
                      "fpts_against": 390, "fpts_against_decimal": 5}},
        {"roster_id": 2, "owner_id": "u2",
         "settings": {"wins": 3, "losses": 1, "fpts": 500}},
    ], {"u1": "Ethan", "u2": "Rival"})
    by = {t["team"]: t for t in rows}
    assert by["Ethan"]["points_for"] == 412.55
    assert by["Ethan"]["points_against"] == 390.05
    assert by["Rival"]["points_for"] == 500.0
    # Wins first, then points for — the default Sleeper tiebreak.
    assert rows[0]["team"] == "Rival" and rows[0]["rank"] == 1


def test_a_team_with_no_owner_still_appears():
    rows = H.standings([{"roster_id": 9, "settings": {}}], {})
    assert rows and rows[0]["team"] == "Team 9"


# --- the matchup -----------------------------------------------------------

SLOTS = ["QB", "RB", "WR", "BN"]


def _means(**over):
    base = {
        "QB1": {"position": "QB", "fp_ppr": 20.0, "_sd": 6.0, "_sd_basis": "own"},
        "RB1": {"position": "RB", "fp_ppr": 14.0, "_sd": 6.0, "_sd_basis": "own"},
        "Boom": {"position": "WR", "fp_ppr": 11.0, "_sd": 11.0, "_sd_basis": "own"},
        "Steady": {"position": "WR", "fp_ppr": 10.5, "_sd": 2.0, "_sd_basis": "own"},
        "OppQB": {"position": "QB", "fp_ppr": 18.0, "_sd": 6.0, "_sd_basis": "own"},
        "OppRB": {"position": "RB", "fp_ppr": 12.0, "_sd": 6.0, "_sd_basis": "own"},
        "OppWR": {"position": "WR", "fp_ppr": 9.0, "_sd": 5.0, "_sd_basis": "own"},
    }
    for k, v in over.items():
        base[k] = {**base.get(k, {}), **v}
    return base


MINE = [{"player": n, "position": p} for n, p in
        (("QB1", "QB"), ("RB1", "RB"), ("Boom", "WR"), ("Steady", "WR"))]
THEIRS = [{"player": n, "position": p} for n, p in
          (("OppQB", "QB"), ("OppRB", "RB"), ("OppWR", "WR"))]


def test_the_margin_and_its_spread_are_both_real_numbers():
    h = H.head_to_head(MINE, THEIRS, SLOTS, {}, _means())
    assert h["me"]["points"] == 45.0 and h["them"]["points"] == 39.0
    assert h["margin"] == 6.0
    # sqrt(6² + 6² + 11²) against sqrt(6² + 6² + 5²), summed in variance.
    assert abs(h["sd"] - (36 + 36 + 121 + 36 + 36 + 25) ** 0.5) < 0.02
    assert 0.5 < h["win_prob"] < 0.75


def test_a_bye_week_shows_your_half_and_invents_nothing():
    h = H.head_to_head(MINE, None, SLOTS, {}, _means())
    assert h["them"] is None and h["margin"] is None
    assert h["win_prob"] is None
    assert h["me"]["points"] == 45.0


def test_no_measured_spread_means_no_odds_rather_than_fake_ones():
    flat = _means()
    for v in flat.values():
        v["_sd"], v["_sd_basis"] = None, "none"
    h = H.head_to_head(MINE, THEIRS, SLOTS, {}, flat)
    assert h["margin"] == 6.0, "the margin is still countable"
    assert h["win_prob"] is None, "odds were quoted off no spread at all"
    assert set(h["unmeasured"]) >= {"QB1", "RB1", "OppQB"}


def test_a_starter_with_no_spread_is_named_not_filled_in():
    m = _means(RB1={"_sd": None, "_sd_basis": "none"})
    h = H.head_to_head(MINE, THEIRS, SLOTS, {}, m)
    assert "RB1" in h["unmeasured"]
    assert h["win_prob"] is not None, "one gap must not kill the whole read"


# --- the part that is not a rule anybody wrote ------------------------------

def _swaps_at(margin, means):
    h = H.head_to_head(MINE, THEIRS, SLOTS, {}, means)
    h = dict(h, margin=margin,
             win_prob=H.win_probability(margin, h["sd"]))
    return H.swings(h)


def test_a_favourite_is_told_to_play_it_safe():
    """+12 up: the 11-point-swing receiver is projected higher and is the
    wrong start, because the only way to lose from here is variance."""
    got = _swaps_at(12.0, _means())
    assert got, "no swap offered to a big favourite holding a boom/bust flex"
    assert got[0]["start"] == "Steady" and got[0]["sit"] == "Boom"
    assert got[0]["points"] < 0, "the safer start costs projected points"
    assert got[0]["gain"] > 0
    assert "safer" in got[0]["why"]


def test_an_underdog_is_told_to_take_the_swing():
    """−12 down, and the boom play is worth LESS in projection — the
    optimiser benches him and the head-to-head starts him anyway."""
    m = _means(Boom={"fp_ppr": 9.5, "_sd": 12.0})
    got = _swaps_at(-12.0, m)
    assert got, "no swap offered to a big underdog with a ceiling on the bench"
    assert got[0]["start"] == "Boom" and got[0]["sit"] == "Steady"
    assert got[0]["points"] < 0, "the ceiling start costs projected points"
    assert "ceiling" in got[0]["why"]


def test_the_same_roster_gets_opposite_advice_at_opposite_margins():
    """The whole point, in one assertion: nothing in the module knows the
    words favourite or underdog."""
    m = _means(Boom={"fp_ppr": 9.5, "_sd": 12.0})
    up = _swaps_at(12.0, m)
    down = _swaps_at(-12.0, m)
    assert not up or up[0]["start"] != "Boom", \
        "a big favourite was told to start the boom play"
    assert down and down[0]["start"] == "Boom"


def test_a_swap_that_does_not_help_is_not_offered():
    """The seated lineup is the baseline; a list of things not to do is
    not advice."""
    for m in (-2.0, 0.0, 2.0, 20.0, -20.0):
        for s in _swaps_at(m, _means()):
            assert s["gain"] > 0, s


def test_the_odds_are_a_normal_read_of_the_margin():
    assert H.win_probability(0.0, 20.0) == 0.5
    assert H.win_probability(20.0, 20.0) > 0.84
    assert H.win_probability(-20.0, 20.0) < 0.16
    assert H.win_probability(5.0, 0.0) is None, \
        "a zero spread makes every margin a certainty"


# --- the spread it all rests on --------------------------------------------

def _logs(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE player_game_logs (sport TEXT, season INT,
        period TEXT, game_id TEXT, player TEXT, team TEXT, opponent TEXT,
        position TEXT, home INT, market TEXT, value REAL)""")
    for i, (player, pos, val) in enumerate(rows):
        c.execute("INSERT INTO player_game_logs (sport,season,period,player,"
                  "position,market,value) VALUES ('nfl',2025,?,?,?,'fp_ppr',?)",
                  (str(i), player, pos, val))
    return c


def test_the_weekly_spread_is_measured_off_his_own_games():
    c = _logs([("A", "WR", v) for v in (5, 15, 5, 15, 5, 15)])
    got = fl.per_game(c, 2025)["A"]
    assert got["fp_ppr"] == 10.0
    assert got["_sd"] == 5.0 and got["_sd_basis"] == "own"


def test_a_thin_player_borrows_his_positions_spread_rather_than_claiming_none():
    """Two identical games is not evidence of consistency, and reporting
    SD 0 for it would put a rookie on the floor side of every decision."""
    rows = [("Vet", "WR", v) for v in (2, 18, 2, 18, 2, 18)]
    rows += [("Rook", "WR", 9.0), ("Rook", "WR", 9.0)]
    got = fl.per_game(_logs(rows), 2025)
    assert got["Rook"]["_sd_basis"] == "position"
    assert got["Rook"]["_sd"] > 0
    assert got["Vet"]["_sd_basis"] == "own"


def test_a_constant_scorer_does_not_produce_a_negative_variance():
    """Floating point can put a constant series a hair below zero, and a
    negative variance has no square root."""
    got = fl.per_game(_logs([("A", "WR", 7.25) for _ in range(9)]), 2025)["A"]
    assert got["_sd"] == 0.0


def test_the_spread_is_rescaled_into_the_leagues_own_points():
    """`_sd` is measured on PPR. A half-PPR league scores this player
    lower and his week-to-week swing scales with him — first-order, and
    the module says so rather than leaving the number on the wrong
    scale."""
    m = {"A": {"position": "WR", "fp_ppr": 20.0, "receptions": 5.0,
               "_sd": 8.0, "_sd_basis": "own"}}
    full = H.team_total([{"player": "A", "position": "WR"}], ["WR"], {}, m)
    half = H.team_total([{"player": "A", "position": "WR"}], ["WR"],
                        {"rec": 0.5}, m)
    assert half["points"] < full["points"]
    assert half["sd"] < full["sd"], "the spread stayed on the PPR scale"


# --- the wiring ------------------------------------------------------------

def test_the_matchup_board_is_allowlisted_and_the_proxy_stays_closed():
    from server import sleeper_path_ok as ok
    assert ok("league/1234567890/matchups/3")
    assert ok("state/nfl")
    assert not ok("league/1234567890/matchups/")
    assert not ok("league/1234567890/matchups/123")
    assert not ok("../../etc/passwd")


def test_the_desk_asks_the_league_which_week_it_is():
    """Not a calendar this server would have to guess with — the league's
    own `leg`, then Sleeper's NFL state."""
    src = _read("server.py")
    i = src.index('out["standings"] = fantasy_h2h.standings')
    block = src[i:i + 2200]
    assert '"leg"' in block and "state/nfl" in block
    assert "opponent_roster_id" in block and "head_to_head" in block


def test_the_panel_repeats_the_two_assumptions_rather_than_hiding_them():
    app = _read("web", "js", "app.js")
    i = app.index("function ffH2HHTML(")
    body = app[i:app.index("\nfunction ffStandingsHTML(", i)]
    assert "normally" in body and "independent" in body, \
        "the panel quotes odds without saying what they assume"
    assert "measured off both sides" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
