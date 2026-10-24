"""The exchange tier was dead on both sports, and the pair was in the data.

Ethan, off the droplet on 2026-09-16: 60 usable NFL markets and 42 usable
MLB markets, zero matched on either. `kalshi.match_game` requires both
clubs in the market's text; the exchange's titles name only the winner
("Buffalo wins", "New York Y wins"). A rule that needs two names against
a feed that publishes one can never fire, so the tier ranked FIRST on
`potd.EVIDENCE` had contributed nothing since the day it shipped.

The docs block that asked Ethan for the ticker shape (`WHEN_YOU_ARE_HOME`
KX-2) was asking for something this repository already had: the fixture
in tests/test_prediction_desk.py carries
`KXMLBGAME-26AUG111840CLEDET-CLE`, and both clubs are right there in the
middle segment. `match_game` was already feeding `event_ticker` into its
haystack and could not SEE them — `_name_tokens` splits on
non-alphanumerics, so `26AUG111840CLEDET` is one token and `"CLE" in hay`
is False.

WHAT THIS FILE DEFENDS is that the fix did not buy the match by
loosening the two-club rule, which is the thing that made the rule right
in the first place. Both codes are still required, and the ticker path
also demands that exactly one game on the board matches — so the case
that made a relaxed prose rule unsafe (the Yankees and the Mets are both
"New York") is refused rather than guessed.

Run directly: `python3 tests/test_the_exchange_finds_the_game_in_its_ticker.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import exchangefair                                 # noqa: E402
from engine.sources import kalshi                               # noqa: E402


def _market(**kw):
    """A market that clears `exchangefair.quality` — the guards are not
    what is under test here, so they are satisfied rather than stubbed."""
    m = {"ticker": "", "event_ticker": "", "title": "", "subtitle": "",
         "price_basis": "book", "spread_cents": 2.0, "prob": 0.58,
         "volume_24h": 5000.0, "open_interest": 5000.0}
    m.update(kw)
    return m


# --- the regression --------------------------------------------------------
def test_the_real_ticker_shape_this_repo_already_had_a_fixture_of():
    """`KXMLBGAME-26AUG111840CLEDET-CLE`, copied from
    tests/test_prediction_desk.py, against a board that names CLE @ DET.
    Before 2026-09-16 this returned None."""
    m = _market(ticker="KXMLBGAME-26AUG111840CLEDET-CLE",
                event_ticker="KXMLBGAME-26AUG111840CLEDET",
                title="Cleveland wins", subtitle="Cleveland")
    games = [{"home": "DET", "away": "CLE"}, {"home": "NYY", "away": "BOS"}]
    assert kalshi.match_game(m, games) == games[0]


def test_ethans_actual_nfl_market_matches_his_actual_board():
    """The two lines he pasted: exchange "Buffalo wins", board "DET @ BUF"."""
    m = _market(ticker="KXNFLGAME-25SEP14DETBUF-BUF",
                event_ticker="KXNFLGAME-25SEP14DETBUF",
                title="Buffalo wins", subtitle="Buffalo")
    games = [{"home": "ATL", "away": "CAR"}, {"home": "BUF", "away": "DET"}]
    assert kalshi.match_game(m, games) == games[1]


def test_a_prose_market_naming_both_clubs_still_matches_on_prose():
    """The original path, untouched — and it has to keep working on a
    market with no ticker at all."""
    m = _market(title="Will the Yankees beat the Red Sox?")
    games = [{"home": "NYY", "away": "BOS",
              "home_name": "New York Yankees", "away_name": "Boston Red Sox"}]
    assert kalshi.match_game(m, games) == games[0]


# --- what it still refuses --------------------------------------------------
def test_the_yankees_and_the_mets_are_still_not_guessed_at():
    """Ethan's MLB line was "New York Y wins", which tokenises to
    {NEW, YORK} and fits both New York clubs. With no ticker to settle
    it, the answer is still no answer."""
    m = _market(title="New York Y wins", subtitle="New York Y")
    games = [{"home": "NYY", "away": "BOS",
              "home_name": "New York Yankees", "away_name": "Boston Red Sox"},
             {"home": "NYM", "away": "ATL",
              "home_name": "New York Mets", "away_name": "Atlanta Braves"}]
    got, why = kalshi.match_game_verbose(m, games)
    assert got is None, got
    assert "both clubs" in why, why


def test_a_doubleheader_is_refused_rather_than_picked_between():
    """NOT A CONTRIVED AMBIGUITY. Two games between the same two clubs on
    the same day is ordinary baseball, and both of them match the pair in
    the ticker equally well. One of them is the market's and this cannot
    tell which."""
    m = _market(ticker="KXMLBGAME-26AUG11CLEDET-CLE",
                event_ticker="KXMLBGAME-26AUG11CLEDET", title="Cleveland wins")
    games = [{"home": "DET", "away": "CLE", "game_id": "g1"},
             {"home": "DET", "away": "CLE", "game_id": "g2"}]
    got, why = kalshi.match_game_verbose(m, games)
    assert got is None, got
    assert "more than one" in why, why


def test_one_club_in_the_ticker_is_not_enough():
    """The two-club rule is the point; the ticker path does not relax it."""
    m = _market(ticker="KXMLBGAME-26AUG11CLE-CLE",
                event_ticker="KXMLBGAME-26AUG11CLE", title="Cleveland wins")
    assert kalshi.match_game(m, [{"home": "DET", "away": "CLE"}]) is None


def test_a_one_character_code_can_never_carry_a_match():
    """A single letter is inside almost every ticker, so a board row with
    a truncated code must not sweep up whatever market it lands on."""
    m = _market(ticker="KXMLBGAME-26AUG111840CLEDET-CLE",
                event_ticker="KXMLBGAME-26AUG111840CLEDET")
    assert kalshi.match_game(m, [{"home": "D", "away": "C"}]) is None
    assert kalshi.match_game(m, [{"home": "DET", "away": "C"}]) is None


def test_the_series_name_is_not_a_place_for_a_club_code_to_hide():
    """`KXMLBGAME` is nine constant characters on every row of a league.
    Leaving them in the haystack only gives a two-letter code somewhere
    to hit by accident, so they come out first."""
    text = kalshi._ticker_text({"ticker": "KXNFLGAME-25SEP14DETBUF-BUF",
                                "event_ticker": "KXNFLGAME-25SEP14DETBUF"})
    assert "KXNFLGAME" not in text
    assert "DETBUF" in text and "25SEP14" in text


def test_a_futures_market_never_reaches_the_ticker_path():
    """`board()` is handed whatever markets its caller fetched, and the
    general /markets page carries futures. One club and a date cannot
    make a false pair — but a MATCHUP future names two, so the path is
    gated on the ticker belonging to a listed GAME series rather than on
    a pair being absent."""
    games = [{"home": "BOS", "away": "NYY", "home_name": "Boston Red Sox",
              "away_name": "New York Yankees"}]
    one = _market(ticker="KXMLBPLAYOFF-26-NYY", event_ticker="KXMLBPLAYOFF-26",
                  title="Yankees make the playoffs")
    assert kalshi.match_game(one, games) is None
    both = _market(ticker="KXWORLDSERIES-26-NYYBOS",
                   event_ticker="KXWORLDSERIES-26", title="Yankees win it all")
    assert kalshi.match_game(both, games) is None, \
        "a matchup future produced a pair and was taken as tonight's game"
    assert kalshi._ticker_text(both) == "", "the series gate did not fire"


def test_a_market_with_no_ticker_and_no_names_matches_nothing():
    got, why = kalshi.match_game_verbose(_market(), [{"home": "DET",
                                                     "away": "CLE"}])
    assert got is None and why


# --- the tier, end to end ---------------------------------------------------
def test_the_exchange_fair_actually_lands_on_the_row():
    """The whole point: a moneyline row comes out of `attach` carrying
    the exchange's number, which is what `potd.evidence` ranks first."""
    m = _market(ticker="KXMLBGAME-26AUG111840CLEDET-CLE",
                event_ticker="KXMLBGAME-26AUG111840CLEDET",
                title="Cleveland wins", subtitle="Cleveland", prob=0.58)
    rows = [{"market": "moneyline", "team": "CLE", "home": "DET",
             "away": "CLE"}]
    census = exchangefair.attach(rows, [m], [{"home": "DET", "away": "CLE"}],
                                 "mlb")
    assert census["attached"] == 1, census
    assert rows[0]["exchange_fair"] == 0.58
    assert rows[0]["exchange_ticker"] == m["ticker"]


def test_the_census_names_which_step_lost_the_market():
    """A funnel that reports one number cannot be acted on. This is the
    same habit every other census here keeps."""
    m = _market(title="New York Y wins")
    census = exchangefair.attach(
        [], [m], [{"home": "NYY", "away": "BOS", "home_name": "New York Yankees",
                   "away_name": "Boston Red Sox"},
                  {"home": "NYM", "away": "ATL", "home_name": "New York Mets",
                   "away_name": "Atlanta Braves"}], "mlb")
    assert census["markets matched to a game"] == 0
    named = [k for k in census if "clubs" in k or "more than one" in k]
    assert named, census


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
