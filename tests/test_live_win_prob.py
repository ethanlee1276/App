"""The live win probability, from the tracker row to the page.

Ethan, 2026-08-14: "Are we able too track the win probability of bets we
have made live too? Like player props and shit based of the current live
lines they would display durring the game."

`test_liveprops.py` covers the arithmetic. This covers the wiring, which
is where a correct number can still end up attached to the wrong bet, and
the labelling, which is where two different KINDS of number can end up
looking like one.

THE TWO SOURCES ARE NOT THE SAME CLAIM.

  moneyline   the live market's own de-vigged price, already on the game
              from `livelines` at one credit for the whole slate
  props       ours, computed from what the player banked against how many
              cracks he has left, because books pull prop markets at
              first pitch and bill per game to be asked

Showing both as a bare percentage would let a reader think we agree with
the book on a market where we ARE the book, or the reverse. Each row says
which one it is.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()

from engine.livepicks import assemble_live_picks                # noqa: E402

def _rec(player, market, projection, team, opp="MIL"):
    """A board row. `team`/`opponent` are what place the bet on a game —
    without them every bet below lands in the unmapped bucket and the
    test passes for the wrong reason."""
    return {"player": player, "market": market, "projection": projection,
            "team": team, "opponent": opp, "market_label": market}


MEANS = [
    _rec("Ian Happ", "total_bases", 1.75, "CHC"),
    _rec("Ian Happ", "hits", 1.05, "CHC"),
    _rec("Ian Happ", "home_runs", 0.16, "CHC"),
    _rec("Ace Starter", "strikeouts", 6.2, "MIL", "CHC"),
]
PROGRESS = {
    "ian happ": {"hits": 1.0, "total_bases": 1.0, "home_runs": 0.0,
                 "spot": 2, "pa": 3.0},
    "nico hoerner": {"hits": 0.0, "total_bases": 0.0, "spot": 1, "pa": 3.0},
    "ace starter": {"strikeouts": 5.0, "bf": 21.0},
}


def _game(**kw):
    g = {"home": "CHC", "away": "MIL", "game_number": 1, "date": "2026-08-14",
         "live": {"state": "live", "home_score": 2, "away_score": 1,
                  "period": "Bot 6th",
                  "situation": {"inning": 6, "half": "Bottom", "outs": 1,
                                "batter": "Nico Hoerner"}}}
    g.update(kw)
    return g


def _bet(player, market, side="OVER", line=1.5, team="CHC"):
    return {"player": player, "market": market, "side": side, "line": line,
            "odds": -110, "stake_units": 1, "team": team, "category": "main"}


def _rows(bets, games=None, pitching=None):
    return assemble_live_picks(bets, MEANS, games or [_game()], PROGRESS, [],
                               {}, pitching if pitching is not None
                               else {"ace starter"})


def _one(bets, **kw):
    return _rows(bets, **kw)[0]


# --- props ------------------------------------------------------------------
def test_a_live_prop_gets_a_probability():
    r = _one([_bet("Ian Happ", "total_bases")])
    assert r["live_prob"] is not None and 0.0 < r["live_prob"] < 1.0


def test_the_number_answers_the_BET_not_the_over():
    """An under ticket asking "will the over hit" and being shown the
    answer is the worst available failure: confidently backwards."""
    o = _one([_bet("Ian Happ", "total_bases", "OVER")])["live_prob"]
    u = _one([_bet("Ian Happ", "total_bases", "UNDER")])["live_prob"]
    assert abs(o + u - 1.0) < 1e-9


def test_a_bet_whose_game_has_not_started_gets_nothing():
    g = _game()
    g["live"] = {"state": "scheduled"}
    assert _one([_bet("Ian Happ", "total_bases")], games=[g])["live_prob"] is None


def test_a_player_the_boxscore_does_not_name_gets_nothing():
    """No batting slot means no way to count his remaining trips, and a
    remaining-trip count invented from nothing is what makes a live
    number confidently wrong."""
    assert _one([_bet("Nobody Here", "total_bases")])["live_prob"] is None


def test_a_market_with_no_projection_on_either_board_gets_nothing():
    bare = [_rec("Ian Happ", "total_bases", None, "CHC")]
    bare[0].pop("projection")
    rows = assemble_live_picks([_bet("Ian Happ", "total_bases")], bare,
                               [_game()], PROGRESS, [], {}, set())
    assert rows[0]["status"] != "unmapped"      # it mapped; it just has no mean
    assert rows[0]["live_prob"] is None


def test_the_long_shot_board_supplies_its_own_means():
    """A home-run bet is journaled from the Long Shots board and is not on
    the main recommendations list. Reading only that list left every
    long shot without a live number — the same class of bug as the
    unmapped long shots on Ethan's Live Now screenshot."""
    ls = [_rec("Ian Happ", "home_runs", 0.16, "CHC")]
    rows = assemble_live_picks([_bet("Ian Happ", "home_runs", line=0.5)], [],
                               [_game()], PROGRESS, ls, {}, set())
    assert rows[0]["live_prob"] is not None


# --- pitchers ---------------------------------------------------------------
def test_a_pitcher_still_in_the_game_gets_a_forecast():
    r = _one([_bet("Ace Starter", "strikeouts", line=5.5, team="MIL")])
    assert 0.0 < r["live_prob"] < 1.0


def test_a_pitcher_who_has_been_pulled_is_settled():
    """He has five strikeouts against a 5.5 line and is out of the game.
    There is nothing left to forecast, and this is the single most useful
    thing the tracker can say about the bet."""
    r = _one([_bet("Ace Starter", "strikeouts", line=5.5, team="MIL")],
             pitching=set())
    assert r["live_prob"] == 0.0


def test_a_pulled_pitcher_over_the_line_is_locked():
    p = dict(PROGRESS)
    p["ace starter"] = {"strikeouts": 7.0, "bf": 24.0}
    rows = assemble_live_picks([_bet("Ace Starter", "strikeouts", line=5.5, team="MIL")],
                               MEANS, [_game()], p, [], {}, set())
    assert rows[0]["live_prob"] == 1.0


# --- moneyline: the market's number, not ours -------------------------------
def _ml_game():
    g = _game()
    g["line_track"] = {"home": "CHC", "values": [63.2, 58.0, 51.0],
                       "labels": ["a", "b", "c"], "opened": 51.0,
                       "now": 63.2, "points": 3}
    return g


def test_a_moneyline_reads_the_live_market():
    """We already paid one credit for this number across the whole slate.
    Computing our own instead would be inventing a disagreement with a
    price we bought."""
    r = _one([_bet("CHC", "moneyline", line=0.5)], games=[_ml_game()])
    assert abs(r["live_prob"] - 0.632) < 1e-9


def test_the_away_side_is_the_complement():
    r = _one([_bet("MIL", "moneyline", line=0.5, team="MIL")], games=[_ml_game()])
    assert abs(r["live_prob"] - 0.368) < 1e-9


def test_a_moneyline_with_no_track_yet_gets_nothing():
    """Most games have no live line for their first half hour."""
    assert _one([_bet("CHC", "moneyline", line=0.5)])["live_prob"] is None


def test_spread_and_total_get_nothing():
    """Both would need a live run-scoring model we do not have, and the
    market prices them on separate keys that cost a credit each per pull.
    Neither is built, so neither gets a number."""
    for market, line in (("spread", -1.5), ("total", 8.5)):
        r = _one([_bet("CHC", market, line=line)], games=[_ml_game()])
        assert r["live_prob"] is None, market


# --- the build wiring -------------------------------------------------------
def test_the_build_passes_who_is_pitching():
    assert "pitching |= current_pitchers(_box)" in BUILD
    assert "result[\"games\"], progress, _ls, _ident,\n" in BUILD \
        and "pitching)" in BUILD


def test_the_pitcher_set_is_only_built_for_live_games():
    """A finished game's last pitcher is not "still in" anything, and
    counting him would keep a settled prop reporting as a forecast."""
    i = BUILD.index("pitching |= current_pitchers(_box)")
    assert 'g.live.state == "live"' in BUILD[max(0, i - 120):i]


def test_the_live_line_is_attached_before_the_tracker_reads_it():
    """The moneyline number comes off `game["line_track"]`. If the
    tracker ran first, every moneyline would silently report None while
    the chart sat on the card two panels away."""
    assert BUILD.index("_ll.attach(") < BUILD.index("rows = assemble_live_picks(")


# --- the render -------------------------------------------------------------
def _block():
    i = APP.index("const winProb = (r) =>")
    return APP[i:APP.index("\n  };", i)]


def test_the_row_renders_it():
    i = APP.index("${progressBar(r)}")
    assert "${winProb(r)}" in APP[i:i + 80]


def test_a_row_without_a_number_renders_nothing():
    assert 'if (p == null || r.phase !== "live") return "";' in _block()


def test_a_certainty_is_not_dressed_up_as_a_forecast():
    """A banked over says CLEARED and a bet with no chances left says NO
    CHANCES LEFT, both in words, in the verdict column. Repeating either
    as a percentage adds nothing and reads as a model boasting about a
    fact it did not predict."""
    assert "if (p <= 0 || p >= 1) return" in _block()


def test_a_long_shot_is_not_rounded_down_to_dead():
    """CAUGHT IN CHROMIUM. Rounding put "0%" on a live 0.4% home-run
    ticket — the same number a bet that can no longer cash gets. Holding
    a long shot and holding a corpse are very different things."""
    b = _block()
    assert '"<1"' in b and '">99"' in b


def test_a_bet_with_no_chances_left_says_so_in_words():
    """THE GAP THE SCREENSHOT SHOWED. A starter pulled two strikeouts
    short rendered "5 so far · needs 2 more" and nothing else, all night,
    about a bet that was already over. The verdict column now says it."""
    i = APP.index('r.status === "dead"')
    block = APP[i:i + 500]
    assert "NO CHANCES LEFT" in block
    assert "out of the game" in block and "won\u2019t bat again" in block \
        or "won’t bat again" in block


def test_a_dead_bets_progress_bar_is_not_painted_as_active():
    """The verdict column says NO CHANCES LEFT in red while the bar below
    it sat brand-purple, which is the colour of a bet still running."""
    i = APP.index("const bad = r.status ===")
    assert '"dead"' in APP[i:i + 160]


def test_a_dead_bet_sorts_with_the_other_losses():
    """It is a settled loss in everything but the official grade, so it
    belongs beside BUSTED rather than up with the live action."""
    from engine.livepicks import assemble_live_picks as _a
    src = __import__("inspect").getsource(_a)
    assert '"busted": 2, "dead": 2' in src


def test_the_two_sources_are_labelled_differently():
    """A market number and a model number are different kinds of claim. A
    reader who cannot tell them apart cannot tell whether we agree with
    the book or ARE the book."""
    b = _block()
    assert "live market" in b and "our model" in b
    assert 'r.market === "moneyline"' in b


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
