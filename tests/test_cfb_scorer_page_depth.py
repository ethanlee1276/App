"""College scorers had no game log on any row, priced or watched.

Ethan, 2026-09-10, on the NFL board: "when you click on props from the
most likely, it pulls up the search page with the player on there", and
then "it's not showing the last five games. or the shop the price. for
the form or how the line is moving today."

The NFL's two lists were fixed that day. College's were not, and could
not be by the same change: `build_cfb_td_longshots` builds both its
picks and its watch rows out of a USAGE TABLE — season means — and never
holds a `Prop`, so there was no `.logs` and no `.lines` to copy across.
A college scorer has never had a game-log chart anywhere on the site.

The numbers were on disk the whole time. `sources.cfbstats` writes
`anytime_td` per player-game beside the yardage markets, and nothing read
them. That is this file's subject: a lookup nobody had written, not data
that was absent.

WHAT IT COSTS is more than three blank sections. `propOpenable` opens a
card only when it can see three games, so a row with no log is not a door
at all and `likelyDoor` falls back to `data-player-page` — the search
page in the report above. Every college touchdown row on the Most Likely
board went there.

THE ORDERING TRAP is the one `cfb.props.filed_usage` documents: a carried
game from last November is OLDER than this September's opener, and the
form windows read the list positionally. Season DESC then period DESC,
or the Last-5 shows the wrong five.

Run directly: `python3 tests/test_cfb_scorer_page_depth.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db as DB                                   # noqa: E402
from engine.cfb import tds as T                               # noqa: E402
from engine.longshots import YES_LINE                         # noqa: E402

#: The six windows `propFormRows` reads by name.
FORM_KEYS = {"last1", "last3", "last5", "last10", "season",
             "career", "vs_opponent"}


def _conn():
    return DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))


def _log(conn, season, period, gid, player, team, market="anytime_td",
         value=1.0, opponent="CLEM", home=1):
    conn.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, "
        "player, team, opponent, home, market, value) VALUES "
        "('cfb', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (season, period, gid, player, team, opponent, home, market, value))


# --- the lookup -------------------------------------------------------------
def test_it_reads_the_touchdown_rows_and_nothing_else():
    conn = _conn()
    _log(conn, 2026, "2026-09-05", "g1", "Nate Frazier", "UGA", value=2.0)
    _log(conn, 2026, "2026-09-05", "g1", "Nate Frazier", "UGA",
         market="rush_yds", value=118.0)
    conn.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, "
        "player, team, market, value) VALUES "
        "('nfl', 2026, '1', 'n1', 'Nate Frazier', 'UGA', 'anytime_td', 1.0)")
    conn.commit()
    got = T.td_game_logs(conn)
    assert list(got) == [("UGA", "nate frazier")], got
    assert [g["value"] for g in got[("UGA", "nate frazier")]] == [2.0], \
        "a yardage row or another sport's row reached the touchdown log"


def test_it_is_keyed_by_the_filing_team_the_way_usage_is():
    """Two men share a name across 130-odd rosters. `merged_usage` keys
    on (team, normalized name) and this must agree, or a transfer reads
    one player's log under another's card."""
    conn = _conn()
    _log(conn, 2026, "2026-09-05", "g1", "Nate Frazier", "UGA", value=1.0)
    _log(conn, 2026, "2026-09-05", "g2", "Nate Frazier", "CLEM", value=3.0)
    conn.commit()
    got = T.td_game_logs(conn)
    assert got[("UGA", "nate frazier")][0]["value"] == 1.0
    assert got[("CLEM", "nate frazier")][0]["value"] == 3.0


def test_last_novembers_game_is_older_than_this_septembers_opener():
    """The form windows read the list POSITIONALLY, so a carried game
    from last November must not sit above this September's opener.

    On today's feeds `period` is a full date — `sources.cfbfastr` and
    `sources.cfbdata` both write `g["date"]` into it — so on this data
    the date alone happens to order it correctly. The season term is
    what makes that a guarantee rather than a coincidence; the next test
    is the one that can tell them apart."""
    conn = _conn()
    _log(conn, 2025, "2025-11-22", "g9", "Nate Frazier", "UGA", value=9.0)
    _log(conn, 2026, "2026-09-05", "g1", "Nate Frazier", "UGA", value=1.0)
    conn.commit()
    got = T.td_game_logs(conn)[("UGA", "nate frazier")]
    assert [g["value"] for g in got] == [1.0, 9.0], got
    assert got[0]["season"] == 2026


def test_the_season_decides_first_when_the_period_is_not_a_date():
    """`cfb.props.filed_usage` reads the same column and documents this
    as the trap it is: week 12 of last season sorts ABOVE week 1 of this
    one on any comparison that looks at the period alone. Nothing writes
    a bare week number into cfb today — this pins the contract, not a
    feed — and it is the assertion that makes the season term load
    bearing rather than decorative."""
    conn = _conn()
    _log(conn, 2025, "12", "g9", "Nate Frazier", "UGA", value=9.0)
    _log(conn, 2026, "1", "g1", "Nate Frazier", "UGA", value=1.0)
    conn.commit()
    got = T.td_game_logs(conn)[("UGA", "nate frazier")]
    assert [g["value"] for g in got] == [1.0, 9.0], \
        "last season's week 12 is sitting above this season's opener"


def test_it_stops_at_the_two_newest_seasons_and_at_the_page_length():
    conn = _conn()
    for season in (2023, 2024, 2025, 2026):
        for w in range(1, 9):
            _log(conn, season, f"{season}-w{w:02d}", f"g{season}{w}",
                 "Nate Frazier", "UGA", value=float(season))
    conn.commit()
    got = T.td_game_logs(conn)[("UGA", "nate frazier")]
    assert len(got) == T.TD_LOG_GAMES
    assert {g["season"] for g in got} == {2026, 2025}, \
        "the query reached past the seasons it scopes to"


def test_an_empty_table_is_an_empty_map_not_a_crash():
    """A board built before any college box score is ingested shows what
    it can prove and nothing more."""
    assert T.td_game_logs(_conn()) == {}


# --- the four fields --------------------------------------------------------
def test_the_keys_are_spelled_the_way_the_prop_page_reads_them():
    logs = [{"week": "2026-09-05", "season": 2026, "opponent": "CLEM",
             "value": 2.0, "home": True}]
    quotes = [{"book": "DraftKings", "yes_odds": 210, "no_odds": -260},
              {"book": "FanDuel", "yes_odds": 195, "no_odds": None}]
    d = T.scorer_depth(logs, quotes)
    assert d["logs"] == logs
    assert set(d["form"]) == FORM_KEYS
    assert d["recent_values"] == [2.0]
    assert d["all_lines"] == [
        {"book": "DraftKings", "line": YES_LINE,
         "over_odds": 210, "under_odds": -260},
        {"book": "FanDuel", "line": YES_LINE,
         "over_odds": 195, "under_odds": None}]


def test_the_line_is_the_one_the_shop_strip_compares_against():
    """`quotesForSide` sorts a quote whose line differs from the row's
    into the OFF-THE-FIELD list. A scorer's line is 0.5 on both sides of
    that comparison or every real price reads as an alternate."""
    d = T.scorer_depth([], [{"book": "DraftKings", "yes_odds": 150}])
    assert d["all_lines"][0]["line"] == YES_LINE == 0.5


def test_a_scorer_with_no_history_shows_nothing_rather_than_zeroes():
    """A freshman in week one has no average. A 0.0 in the Last-5 box is
    a claim that he has been held out of the end zone."""
    d = T.scorer_depth([], [])
    assert d["logs"] == [] and d["recent_values"] == []
    assert set(d["form"]) == FORM_KEYS
    assert all(v is None for v in d["form"].values())


def test_a_quote_with_no_book_is_not_a_price():
    assert T.scorer_depth([], [{"yes_odds": 150}, None])["all_lines"] == []


# --- both lists read it -----------------------------------------------------
def test_both_college_lists_carry_the_page():
    """They are two descriptions of one board and drifted apart on the
    NFL side precisely because only one of them was given this."""
    src = open(os.path.join(ROOT, "engine", "cfb", "tds.py"),
               encoding="utf-8").read()
    body = src[src.index("def build_cfb_td_longshots("):]
    assert body.count("scorer_depth(") == 2, \
        "one of the college lists no longer carries the page"
    assert "logs_by_player = td_game_logs(conn)" in body, \
        "the logs are read per row rather than once for the board"
    assert body.index("logs_by_player = td_game_logs(conn)") \
        < body.index("for gi, player_quotes"), \
        "the read moved inside the game loop"


def test_the_college_form_comes_from_the_shared_helper():
    """`longshots.scorer_form` is where both football chains read their
    windows, so a rename cannot blank one league's Form card alone."""
    src = open(os.path.join(ROOT, "engine", "cfb", "tds.py"),
               encoding="utf-8").read()
    assert "scorer_form(" in src and "def scorer_form(" not in src


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
