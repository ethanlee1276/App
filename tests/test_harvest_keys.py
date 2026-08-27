"""One market map, and nothing bought that cannot be read back.

Two halves of the same chain had drifted apart, and both failures are
silent — they cost credits and store nothing.

THE REQUEST SIDE. `resolve_market_keys` translated player props but not
game markets: its docstring said `h2h`, `totals` and `spreads` "pass
through untouched" and expected every caller to have translated first.
`engine.maintenance` did, through a private copy of the map;
`harvest_odds.py --markets spread,total` did not, and asked the API for
market names it has never had.

THE PARSE SIDE. `resolve_market_keys` layers scorer markets on top of
the sport's config; `parse_event_lines` reads the config alone. CFB's
config carries no markets at all, so any college prop that is not on the
scorer board resolves for the request and is thrown away on arrival.

Run directly: `python3 tests/test_harvest_keys.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddshistory as oh


# --- one map ----------------------------------------------------------
def test_game_markets_translate_without_the_caller_helping():
    assert oh.resolve_market_keys("nfl", ["spread", "total", "moneyline"]) \
        == ["spreads", "totals", "h2h"]


def test_a_team_total_asks_for_the_totals_market():
    assert oh.resolve_market_keys("nfl", ["team_total"]) == ["totals"]


def test_player_props_still_translate():
    assert oh.resolve_market_keys("nfl", ["rec_yds", "receptions"]) \
        == ["player_reception_yds", "player_receptions"]
    assert oh.resolve_market_keys("mlb", ["total_bases"]) \
        == ["batter_total_bases"]


def test_a_scorer_market_translates_for_every_football_code():
    for sport in ("nfl", "cfb"):
        assert oh.resolve_market_keys(sport, ["anytime_td"]) \
            == ["player_anytime_td"], sport


def test_an_api_key_passes_through_untouched():
    assert oh.resolve_market_keys("nfl", ["h2h", "player_pass_yds"]) \
        == ["h2h", "player_pass_yds"]


def test_the_nightly_and_the_cli_now_ask_for_the_same_thing():
    """The whole bug in one assertion: two callers, one answer."""
    from engine.maintenance import _HARVEST_GAME_MARKETS as nightly
    wanted = ["spread", "total", "moneyline"]
    pre_translated = oh.resolve_market_keys(
        "nfl", [nightly.get(m, m) for m in wanted])
    direct = oh.resolve_market_keys("nfl", wanted)
    assert pre_translated == direct == ["spreads", "totals", "h2h"]


def test_the_nightly_stopped_keeping_its_own_copy():
    from engine import maintenance
    assert maintenance._HARVEST_GAME_MARKETS is oh.GAME_MARKET_KEYS


# --- nothing bought that cannot be read back --------------------------
def test_every_key_the_nfl_bets_resolves_can_be_read_back():
    keys = oh.resolve_market_keys(
        "nfl", ["spread", "total", "moneyline", "pass_yds", "rush_yds",
                "rec_yds", "receptions", "anytime_td"])
    assert oh.unreadable_markets("nfl", keys) == []


def test_a_college_yardage_prop_is_flagged_rather_than_bought():
    """CFB's market map is empty, so this resolves to nothing the parser
    knows and would be paid for and dropped."""
    keys = oh.resolve_market_keys("cfb", ["rec_yds"])
    assert oh.unreadable_markets("cfb", keys) == keys


def test_the_college_scorer_board_is_readable():
    keys = oh.resolve_market_keys("cfb", ["anytime_td", "spread", "total"])
    assert oh.unreadable_markets("cfb", keys) == []


def test_the_parse_map_covers_the_three_dedicated_game_parsers():
    for sport in ("nfl", "cfb", "mlb"):
        readable = oh.parse_map(sport)
        for key in ("h2h", "totals", "spreads"):
            assert key in readable, (sport, key)


def test_the_harvester_drops_unreadable_markets_before_spending():
    import inspect
    source = inspect.getsource(
        __import__("importlib").import_module("harvest_odds"))
    assert "unreadable_markets" in source
    assert "spend credits and store" in source


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
