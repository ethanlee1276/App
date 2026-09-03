"""Has any player prop ever been priced against a real book line?

`coverage._game_lines_layer` has asked this for spreads and totals since
the game model was caught pricing "for months against numbers nobody
wrote down". Nobody asked it about props, and on 2026-08-27 the answer
turned out to be no — not once, in any football market:

    mlb moneyline 157,488   nfl moneyline 131,840   mlb spread 103,252
    mlb total     103,246   nfl spread     65,920   nfl total    65,920
    mlb total_bases 48,007  mlb hits       15,990

Four configured NFL prop markets, an anytime-touchdown board, a grade
ladder pooled over four seasons — and zero harvested prices behind any of
it. Every one of those bets was replayed against a synthetic -110 at a
trailing average, which grades the PROJECTION honestly and says nothing
whatsoever about beating a book.

This suite pins the layer that now asks. The tests that matter are the
ones proving it looks at the database rather than at a list someone
maintains: a market the board quotes but the config cannot buy has to be
named, and the fix it prints must never be a command that spends credits
on a market the parser will drop.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import coverage as C
from engine import db


def _ledger_at(path):
    """An empty journal, so `_prop_markets` reads the stub and not the box."""
    from engine import ledger as _led
    _led.DEFAULT_DB = path
    conn = _led.connect()
    return conn


def _bet(conn, sport, market, status="won", category="main", closing=None):
    conn.execute(
        "INSERT OR REPLACE INTO bets (sport, date, player, market, status, "
        "category, closing_odds) VALUES (?,?,?,?,?,?,?)",
        (sport, "2025-09-07", f"p-{market}", market, status, category, closing))
    conn.commit()


# --- which markets a sport is on the hook for --------------------------------
def test_game_markets_are_never_counted_as_props():
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        tmp = os.path.join(tempfile.mkdtemp(), "l.db")
        conn = _ledger_at(tmp)
        for m in _led.GAME_MARKETS:
            _bet(conn, "nfl", m)
        conn.close()
        got = C._prop_markets("nfl")
        assert not (got & set(_led.GAME_MARKETS)), got
    finally:
        _led.DEFAULT_DB = saved


def test_a_yes_only_board_counts_even_though_no_config_can_name_it():
    """THE PREMISE MOVED AND THE POINT DID NOT. This used to read "CFB's
    markets map is empty", which was the sharpest available example: the
    college touchdown board published every Saturday and the buy config
    knew nothing about it. College gained a buy config on 2026-09-03
    (four yardage markets), so the example is now the narrower and more
    permanent one — anytime TD is Yes-only, has no over/under to buy,
    and can therefore NEVER appear in a markets map however complete it
    gets. `HOLD_MARKETS` is the only source that knows it."""
    from engine import ledger as _led
    from engine.sources.oddsapi import SPORT_CONFIG
    saved = _led.DEFAULT_DB
    try:
        _led.DEFAULT_DB = os.path.join(tempfile.mkdtemp(), "l.db")
        assert "anytime_td" not in SPORT_CONFIG["cfb"]["markets"].values()
        assert "anytime_td" in C._prop_markets("cfb")
        assert C._prop_markets("cfb") == {
            "anytime_td", "pass_yds", "rush_yds", "rec_yds", "receptions"}
    finally:
        _led.DEFAULT_DB = saved


def test_the_journal_adds_markets_the_config_never_named():
    """`carries` is in the NFL's own stat vocabulary and in neither the
    buy config nor `HOLD_MARKETS` — exactly the case the journal is here
    to catch."""
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        tmp = os.path.join(tempfile.mkdtemp(), "l.db")
        conn = _ledger_at(tmp)
        _bet(conn, "nfl", "carries")
        conn.close()
        assert "carries" in C._prop_markets("nfl")
    finally:
        _led.DEFAULT_DB = saved


def test_a_sport_is_never_held_to_another_sports_markets():
    """The journal held MLB rows carrying `rec_yds`, `receptions` and
    `pass_yds`. Unfiltered, this reported that MLB — a sport with 77,952
    stored prop prices covering all five of its real markets — had no
    harvested price for receiving yards, and then blamed MLB's buy config
    for it. A coverage page that invents a gap is worse than one that
    misses a gap: it spends the reader's attention on nothing."""
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        tmp = os.path.join(tempfile.mkdtemp(), "l.db")
        conn = _ledger_at(tmp)
        for market in ("rec_yds", "receptions", "pass_yds"):
            _bet(conn, "mlb", market)
        _bet(conn, "mlb", "hits")
        conn.close()
        got = C._prop_markets("mlb")
        assert got == {"hits", "home_runs", "outs", "strikeouts",
                       "total_bases"}, got
    finally:
        _led.DEFAULT_DB = saved


def test_the_filter_keeps_a_market_the_sport_really_does_board():
    """The filter must not eat a genuine gap. College receiving yards is
    in CFB's own vocabulary and cannot be bought — that is worth saying,
    and the same rule that drops MLB's `rec_yds` has to keep this one."""
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        tmp = os.path.join(tempfile.mkdtemp(), "l.db")
        conn = _ledger_at(tmp)
        _bet(conn, "cfb", "rec_yds")
        conn.close()
        assert "rec_yds" in C._prop_markets("cfb")
    finally:
        _led.DEFAULT_DB = saved


def test_buckets_that_grade_elsewhere_are_not_props():
    """A Kalshi ticker and a UFC fighter both sit in the `player` column
    and neither is a prop any harvest could buy."""
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        tmp = os.path.join(tempfile.mkdtemp(), "l.db")
        conn = _ledger_at(tmp)
        _bet(conn, "nfl", "SUPERBOWL-26", category="predmarket")
        conn.close()
        assert "SUPERBOWL-26" not in C._prop_markets("nfl")
    finally:
        _led.DEFAULT_DB = saved


# --- what is actually stored -------------------------------------------------
def _snap(sport, market, player, taken="2025-09-07T23:00:00Z"):
    return {"sport": sport, "taken_at": taken, "event_id": "e1",
            "home": "A", "away": "B", "player": player, "market": market,
            "book": "dk", "line": 4.5, "over_odds": -110, "under_odds": -110}


def test_stored_counts_come_from_the_table_and_drop_game_lines():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        _snap("nfl", "receptions", "aaron jones"),
        _snap("nfl", "receptions", "davante adams"),
        _snap("nfl", "spread", "KC"),
        _snap("mlb", "hits", "aaron judge"),
    ])
    got = C._stored_prop_markets(conn, "nfl")
    assert got == {"receptions": 2}, got


# --- the layer ---------------------------------------------------------------
def _layer(conn, sport, ledger_path=None):
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        _led.DEFAULT_DB = ledger_path or os.path.join(
            tempfile.mkdtemp(), "l.db")
        return C._prop_closes_layer(conn, sport)
    finally:
        _led.DEFAULT_DB = saved


def test_a_sport_with_no_prop_board_gets_no_row():
    """A layer that appears on every sport is furniture, not information."""
    conn = db.connect(":memory:")
    assert _layer(conn, "ufc") is None


def test_nothing_harvested_is_reported_as_missing_and_names_the_markets():
    conn = db.connect(":memory:")
    layer = _layer(conn, "nfl")
    assert layer.state == C.MISSING
    assert "receptions" in layer.detail
    assert "synthetic -110" in layer.detail
    # WHAT the synthetic -110 applies to. Forward bets are journaled at
    # the real book price they were taken at; it is the walk-forward
    # REPLAY that has no book behind it, and saying "every prop number
    # this sport has ever published" overclaimed that into a falsehood.
    assert "walk-forward replay" in layer.detail
    assert "ever published" not in layer.detail


def test_a_partly_harvested_sport_says_which_half_is_missing():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [_snap("nfl", "receptions", "a b"),
                                  _snap("nfl", "receptions", "c d")])
    layer = _layer(conn, "nfl")
    assert layer.state == C.PARTIAL
    assert "receptions" in layer.detail
    assert "pass_yds" in layer.detail
    assert layer.fix and "receptions" not in layer.fix, \
        "the fix must buy what is missing, not what is already stored"


def test_a_fully_harvested_sport_is_ok_and_prints_no_command():
    """EVERY market the sport is on the hook for, which for college is
    five since the prop board shipped — a store holding only touchdowns
    is now correctly reported as incomplete, so this seeds all five."""
    conn = db.connect(":memory:")
    rows = []
    for market in sorted(C._prop_markets("cfb")):
        for i in range(3):
            r = _snap("cfb", market, f"p{i}")
            r["taken_at"] = f"2025-09-0{i + 1}T23:00:00Z"
            rows.append(r)
    db.upsert_odds_history(conn, rows)
    layer = _layer(conn, "cfb")
    assert layer.state == C.OK, layer.detail
    assert "price row(s)" in layer.detail
    assert layer.fix == ""


def test_a_college_board_missing_its_yardage_closes_says_so():
    """The half of that which is now reachable: touchdowns harvested,
    the four yardage markets not. A college prop journaled with no close
    can never be graded for CLV, which is the whole point of the layer."""
    conn = db.connect(":memory:")
    rows = [_snap("cfb", "anytime_td", f"p{i}") for i in range(3)]
    for i, r in enumerate(rows):
        r["taken_at"] = f"2025-09-0{i + 1}T23:00:00Z"
    db.upsert_odds_history(conn, rows)
    layer = _layer(conn, "cfb")
    assert layer.state != C.OK
    assert "rec_yds" in layer.detail
    assert layer.fix.startswith("python3 harvest_odds.py cfb")


def test_the_forward_record_reports_how_many_bets_carry_a_close():
    """The historical question and the forward one are different, and the
    forward one is the only one a live board can still fix."""
    conn = db.connect(":memory:")
    tmp = os.path.join(tempfile.mkdtemp(), "l.db")
    led = _ledger_at(tmp)
    _bet(led, "nfl", "receptions", status="won", closing=-115)
    _bet(led, "nfl", "rec_yds", status="lost", closing=None)
    _bet(led, "nfl", "spread", status="won", closing=-110)   # not a prop
    led.close()
    layer = _layer(conn, "nfl", ledger_path=tmp)
    assert "1 of 2 settled prop bet(s) carry a closing price" in layer.detail


# --- the fix line must never cost money for nothing ---------------------------
def test_the_fix_never_buys_a_market_this_sport_cannot_read_back():
    """The exact waste `harvest_odds.py` already guards against at the
    request. A coverage page that PRINTS the wasteful command is the same
    hole with a friendlier face."""
    from engine.sources import oddshistory as oh
    for sport in ("nfl", "mlb", "cfb", "nba", "wnba"):
        fix = C._harvest_fix(sport, sorted(C._prop_markets(sport)))
        if not fix.startswith("python3"):
            continue
        asked = fix.split("--markets ", 1)[1].split(",")
        keys = oh.resolve_market_keys(sport, asked)
        assert not oh.unreadable_markets(sport, keys), \
            f"{sport}: fix line would spend credits on {asked}"


def test_a_market_the_parser_cannot_read_gets_an_explanation_not_a_command():
    """College yardage was this test's example until 2026-09-03, when it
    became buyable; the guard is asked about a market no parser knows
    instead, which is what it was always really about."""
    fix = C._harvest_fix("cfb", ["kicking_points"])
    assert not fix.startswith("python3")
    assert "SPORT_CONFIG" in fix and "store nothing" in fix


def test_college_yardage_is_a_command_now_that_it_can_be_read_back():
    fix = C._harvest_fix("cfb", ["rec_yds", "rush_yds"])
    assert fix.startswith("python3 harvest_odds.py cfb")
    assert "rec_yds,rush_yds" in fix


def test_no_markets_left_to_buy_prints_nothing_at_all():
    assert C._harvest_fix("nfl", []) == ""


# --- wiring ------------------------------------------------------------------
def test_every_sport_with_props_carries_the_layer():
    conn = db.connect(":memory:")
    from engine import ledger as _led
    saved = _led.DEFAULT_DB
    try:
        _led.DEFAULT_DB = os.path.join(tempfile.mkdtemp(), "l.db")
        for sport in ("nfl", "mlb", "nba", "wnba", "cfb"):
            names = [l.name for l in getattr(C, sport)(conn).layers]
            assert "Stored prop closes" in names, sport
        assert "Stored prop closes" not in [
            l.name for l in C.ufc(conn).layers]
    finally:
        _led.DEFAULT_DB = saved


def test_a_none_layer_is_dropped_by_the_container_not_by_each_builder():
    cov = C.SportCoverage("x", "X", [
        C.Layer("real", "why", C.OK), None, C.Layer("other", "why", C.OK)])
    assert [l.name for l in cov.layers] == ["real", "other"]
    assert cov.score == (2, 2)


def test_a_close_stored_on_the_schedule_counts_as_a_stored_close():
    """College football's closes come off the cfbfastR mirror into
    `games.spread`/`games.total`, not `odds_history`. Counting only the
    purchased table reported that the CFB board "prices spreads and
    totals it cannot check" on the day `gamecal` finished measuring its
    market haircut from 2,055 of exactly those closes."""
    conn = db.connect(":memory:")
    assert C._game_lines_layer(conn, "cfb").state == C.MISSING
    db.upsert_games(conn, [
        {"sport": "cfb", "season": 2025, "period": f"2025-09-{i % 28 + 1:02d}",
         "game_id": str(i), "home": "A", "away": "B",
         "home_score": 30.0, "away_score": 20.0,
         "spread": -3.5, "total": 54.5} for i in range(150)])
    layer = C._game_lines_layer(conn, "cfb")
    assert layer.state == C.OK
    assert "150 game(s)" in layer.detail


def test_a_game_with_no_line_is_not_counted_as_having_one():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [
        {"sport": "cfb", "season": 2025, "period": "2025-09-01",
         "game_id": str(i), "home": "A", "away": "B",
         "home_score": 30.0, "away_score": 20.0} for i in range(150)])
    assert C._game_lines_layer(conn, "cfb").state == C.MISSING


def test_the_names_helper_does_not_run_off_the_line():
    assert C._names(["a", "b"]) == "a, b"
    assert C._names([]) == "none"
    assert C._names(list("abcdef")) == "a, b, c, d (+2 more)"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
