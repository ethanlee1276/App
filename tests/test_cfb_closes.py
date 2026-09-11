"""CFB closing lines — the last CLV gap, closed.

The nightly harvest is journal-driven: any night a sport's bets journal,
its closes are harvested and closing-line value accrues. CFB was the
deliberate exception for one reason — a NAME. The odds-history parsers
key every price through a book-spelling → abbreviation map, and CFB's is
built at run time from the ESPN feed inside cfb_build, because 134
schools across reshuffling conferences is the table that rots the moment
it is hardcoded. So a harvest stored school names no settle pass could
join to a bet.

What this file pins:

  * THE MAP IS HARVESTED, NEVER HAND-WRITTEN. cfb_build resolves the
    book's names against the live feed to price its board anyway; those
    resolutions are written down as it goes.
  * ACCUMULATE, NEVER REPLACE. One Tuesday slate is a dozen games; a
    season is 134 schools. A build merges what it learned on top of what
    is stored, or a harvest's coverage would depend on which night it ran.
  * READ PER CALL, NOT AT IMPORT. A long-running process would otherwise
    hold the empty map it started with while builds beside it learned.
  * NO MAP, NO SPEND. An empty map means harvested rows would not join,
    which is the exact waste the old "CFB is absent" rule prevented.
  * THE FREE CLOSES ARE FREE. Game lines are already in memory on every
    build; storing them costs no credit and needs no name map at all.

Run directly: `python3 tests/test_cfb_closes.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import cfbteams, lineledger                      # noqa: E402
from engine.sources import oddshistory as oh                 # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _tmp_map():
    """Point the store at a temp file — a test must never write a real
    team map into the working tree."""
    path = os.path.join(tempfile.mkdtemp(), "cfb_teams.json")
    cfbteams.STATE_PATH = path
    return path


# --- the map -----------------------------------------------------------------

def test_the_map_accumulates_across_builds():
    _tmp_map()
    assert cfbteams.load() == {}
    assert cfbteams.remember({"Ohio State Buckeyes": "OSU",
                              "Michigan Wolverines": "MICH"}) == 2
    # A later, smaller slate must not shrink the map to its own teams.
    assert cfbteams.remember({"Texas Longhorns": "TEX"}) == 1
    assert set(cfbteams.load()) == {"Ohio State Buckeyes",
                                    "Michigan Wolverines", "Texas Longhorns"}


def test_relearning_the_same_name_writes_nothing():
    _tmp_map()
    cfbteams.remember({"Ohio State Buckeyes": "OSU"})
    assert cfbteams.remember({"Ohio State Buckeyes": "OSU"}) == 0, \
        "an unchanged map still reported new names — the count is a lie"


def test_a_renamed_school_self_corrects():
    """The reason this is a harvest and not a constant: the next build
    that prices that game overwrites the entry."""
    _tmp_map()
    cfbteams.remember({"Texas Longhorns": "TEX"})
    assert cfbteams.remember({"Texas Longhorns": "TEXAS"}) == 1
    assert cfbteams.load()["Texas Longhorns"] == "TEXAS"


def test_a_corrupt_or_missing_map_degrades_and_never_raises():
    path = _tmp_map()
    assert cfbteams.load() == {}, "a missing map should read as empty"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json at all")
    assert cfbteams.load() == {}, \
        "a torn map must not take the nightly job down with it"


def test_junk_never_enters_the_map():
    _tmp_map()
    cfbteams.remember({"": "X", "Real School": "", "A" * 200: "LONG",
                       "Ohio State Buckeyes": "OSU"})
    assert cfbteams.load() == {"Ohio State Buckeyes": "OSU"}


# --- the parsers -------------------------------------------------------------

def test_the_parsers_read_the_map_per_call_not_at_import():
    """The refresh cycle and the maintenance daemon run for days. Freezing
    the map into SPORT_CONFIG at import would leave them keying every
    harvest through the empty map they booted with."""
    _tmp_map()
    assert oh.teams_for("cfb") == {}
    cfbteams.remember({"Ohio State Buckeyes": "OSU"})
    assert oh.teams_for("cfb")["Ohio State Buckeyes"] == "OSU", \
        "the parsers cached an empty map"
    src = _read("engine", "sources", "oddshistory.py")
    i = src.index("def parse_snapshot")
    body = src[i:src.index("\ndef ", i)]
    assert 'cfg["teams"]' not in body, \
        "parse_snapshot went back to the frozen map"


def test_the_other_sports_keep_their_hardcoded_tables():
    _tmp_map()
    assert oh.teams_for("nfl"), "the NFL map vanished"
    assert oh.teams_for("mlb"), "the MLB map vanished"


def test_a_harvested_snapshot_stores_our_abbreviations():
    _tmp_map()
    cfbteams.remember({"Ohio State Buckeyes": "OSU",
                       "Michigan Wolverines": "MICH"})
    snap = oh.Snapshot(requested="2026-08-30T23:00:00Z",
                       taken="2026-08-30T22:58:00Z",
                       data={"id": "evt1", "home_team": "Ohio State Buckeyes",
                             "away_team": "Michigan Wolverines",
                             "bookmakers": []})
    hist = oh.parse_snapshot(snap, "cfb")
    assert (hist.home, hist.away) == ("OSU", "MICH"), \
        "harvested rows still carry school names no bet can join"


def test_scorer_markets_resolve_to_their_api_key():
    """Found while wiring CFB and it was breaking NFL too: the harvest
    asks for the markets actually bet, and `anytime_td` was passed
    through unresolved — a market key the API does not have — so the TD
    board has never had a closing line to be graded on."""
    assert oh.resolve_market_keys("nfl", ["anytime_td"]) == ["player_anytime_td"]
    assert oh.resolve_market_keys("cfb", ["anytime_td"]) == ["player_anytime_td"]
    # the ordinary props still resolve as before
    assert oh.resolve_market_keys("nfl", ["rec_yds"]) == ["player_reception_yds"]
    assert oh.resolve_market_keys("cfb", ["h2h", "spreads"]) == ["h2h", "spreads"]


# --- the spend gate ----------------------------------------------------------

def test_cfb_joined_the_harvest_but_not_before_the_map_exists():
    from engine import maintenance as mt
    assert "cfb" in mt._HARVEST_SPORTS
    _tmp_map()
    assert not mt._cfb_map_ready(), \
        "an empty map would spend credits on rows that cannot join"
    cfbteams.remember({"Ohio State Buckeyes": "OSU"})
    assert mt._cfb_map_ready()
    src = _read("engine", "maintenance.py")
    i = src.index("def _harvest_targets")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "_cfb_map_ready()" in body, "the gate is defined but never asked"


def test_the_cli_accepts_cfb():
    assert '"nfl", "mlb", "cfb"' in _read("harvest_odds.py")


# --- the free closes ---------------------------------------------------------

def test_game_lines_are_stored_from_a_dict_board_too():
    """MLB and NFL hand over Game dataclasses; CFB's board is plain
    dicts. The ROWS are identical, so one function reads both."""
    rows = lineledger.rows_for_games("cfb", [{
        "home": "OSU", "away": "MICH", "date": "2026-08-30",
        "spread": -7.5, "spread_home_odds": -110, "spread_away_odds": -110,
        "total": 52.5, "total_over_odds": -105, "total_under_odds": -115,
        "home_ml": -300, "away_ml": 240}])
    assert {r["market"] for r in rows} == {"spread", "total", "moneyline"}
    spread = next(r for r in rows if r["market"] == "spread")
    assert spread["player"] == "OSU" and spread["line"] == -7.5
    assert all(r["home"] == "OSU" and r["away"] == "MICH" for r in rows), \
        "the free closes must carry OUR abbreviations — they already do, " \
        "which is why this path needs no name map at all"


def test_a_priceless_game_writes_nothing():
    assert lineledger.rows_for_games("cfb", [
        {"home": "OSU", "away": "MICH", "date": "2026-08-30"}]) == [], \
        "a row of Nones makes 'no line seen' and 'the line was even' " \
        "the same stored fact"


def test_the_build_keeps_the_lines_it_already_paid_for():
    src = _read("cfb_build.py")
    assert 'lineledger.record(_lc, "cfb", _rows)' in src, \
        "CFB game bets settle with no closing line again"
    assert "cfbteams.remember(learned)" in src, \
        "the build stopped writing down the names it resolved"


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
