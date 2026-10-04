"""Which open bets were struck on a line the board no longer shows?

Ethan, 2026-09-09, minutes after the rematch bug was fixed: "should we
also check the nfl edge bets and see and fix what bets were placed with
the wrong lines. all we confirmed was the money lines was wrong but we
have no clue if the player props or anything like that is also wrong."

HE IS RIGHT, AND THE PROP EXPOSURE IS THE WORSE HALF. The moneyline
damage announced itself — a price landed on the wrong team and the
favourite inverted, which is visible to anyone with a sportsbook open. A
prop's damage is invisible. `apply_odds_to_slate` indexes player lines by
PLAYER:

    index.setdefault(k, []).extend(lines)

so a rematch that matched a Week 1 slate game had its November prop lines
appended to the SAME player key, and `best_over_line` then shopped across
both weeks. A Week 1 receiving-yards prop could be priced off the
November game's number: same player, same market, different game, and
nothing on the card to say which.

The scale is in the board's own counters. Before the fix the NFL build
reported `events 21` on a sixteen-game slate; after, `events 16`. Five
event payloads were fetched and indexed that were not this week's games.

This audit is the answer to "what do we do about the bets already
placed", and it deliberately does not accuse: a line that moved is not
proof, because lines move. It puts every open position with a changed
number in one place so a person can decide.
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import launch                                                # noqa: E402
from engine import ledger                                    # noqa: E402
from engine.sources import fetch as _fetch                   # noqa: E402


def _board(line=68.5, **kw):
    b = {"games": [{"home": "MIN", "away": "GB", "date": "2026-09-13"}],
         "recommendations": [
             {"player": "Justin Jefferson", "market": "rec_yds",
              "side": "OVER", "line": line, "odds": -110, "book": "FanDuel"}],
         "most_likely": [], "long_shots": []}
    b.update(kw)
    return b


def _bet(conn, player="Justin Jefferson", market="rec_yds", line=68.5,
         category="main", odds=-110):
    conn.execute(
        "INSERT INTO bets (date, sport, player, market, side, line, odds, "
        "book, status, category, stake_units) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-W01", "nfl", player, market, "OVER", line, odds, "FanDuel",
         "open", category, 1.0))
    conn.commit()


def _run(board, bets=(), cached_events=(), sport="nfl"):
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "recommendations.json").write_text(
        json.dumps(board))
    cache = tmp / "cache"
    cache.mkdir()
    for i, ev in enumerate(cached_events):
        (cache / f"odds_event_{sport}_e{i}_tag.json").write_text(json.dumps(ev))
    db = tmp / "ledger.db"
    conn = ledger.connect(str(db))
    for kw in bets:
        _bet(conn, **kw)
    old_root, old_cache, old_db = launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB
    launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB = tmp, cache, db
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch.bet_audit(sport)
        return buf.getvalue()
    finally:
        launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB = (
            old_root, old_cache, old_db)


def _ev(when, home="Green Bay Packers", away="Minnesota Vikings"):
    return {"home_team": home, "away_team": away, "commence_time": when}


def test_a_bet_on_a_number_the_board_no_longer_shows_is_named():
    """THE question Ethan asked. The position was struck at 68.5; the
    board now says 74.5. Same player, same market, a different number —
    which is exactly what a November line merged into a September card
    leaves behind."""
    out = _run(_board(line=74.5), bets=[{"line": 68.5}])
    assert "LINE MOVED  Justin Jefferson OVER 68.5 rec_yds" in out, out
    assert "board now: OVER 74.5" in out, out
    assert "1 on a DIFFERENT number" in out, out


def test_a_bet_on_the_same_number_is_not_dragged_in():
    """An audit that flags everything is an audit nobody reads."""
    out = _run(_board(line=68.5), bets=[{"line": 68.5}])
    assert "LINE MOVED" not in out, out
    assert "1 on the same number" in out, out


def test_a_position_the_board_has_dropped_is_summarised_not_listed():
    """Not the same finding as a moved line: the pick is gone rather than
    repriced. And it is summarised BY MARKET, because the first live run
    printed fifty long shots one per line and buried eleven real findings
    under them. Fifty scorer props vanishing together is one fact about
    that market's build."""
    out = _run(_board(), bets=[{"player": "A", "market": "anytime_td"},
                               {"player": "B", "market": "anytime_td"},
                               {"player": "C", "market": "anytime_td"}])
    assert "OFF THE BOARD  3 position(s)" in out, out
    assert "3  main/anytime_td" in out, out
    assert "OFF THE BOARD  A" not in out, out


def test_the_payloads_from_another_week_are_named():
    """The contaminating pulls, by game and by file. This is the evidence
    that the prop index was merged across weeks, not an inference from
    it."""
    out = _run(_board(), cached_events=[_ev("2026-11-15T18:00:00Z"),
                                        _ev("2026-09-13T20:25:00Z")])
    assert "1 cached event payload(s) are for games NOT on this slate" in out \
        or "1 cached event payload(s) are for" in out, out
    assert "2026-11-15" in out and "Minnesota Vikings @ Green Bay Packers" in out
    assert "2026-09-13" not in out.split("bets")[0].split("2026-11-15")[1]


def test_a_clean_cache_says_so_rather_than_staying_silent():
    """Silence reads as approval. If nothing from another week was
    indexed, the report has to say that in words."""
    out = _run(_board(), cached_events=[_ev("2026-09-13T20:25:00Z")])
    assert "every cached event payload is for a game on this slate" in out, out


def test_a_board_with_no_dates_refuses_to_guess():
    """Without the slate's own days there is nothing to compare a
    payload's kickoff against, and reporting "all clean" from that would
    be the tool lying about a check it never made."""
    board = _board()
    board["games"] = [{"home": "MIN", "away": "GB"}]
    out = _run(board, cached_events=[_ev("2026-11-15T18:00:00Z")])
    assert "cannot tell this slate's payloads from any other week's" in out, out
    assert "NOT on this slate" not in out


def test_it_does_not_accuse_a_line_of_being_wrong():
    """Lines move. The report says so where a reader will see it, or the
    next person treats every ordinary move as a bug."""
    out = _run(_board(line=74.5), bets=[{"line": 68.5}])
    assert "not proof the bet was struck on a bad number" in out, out


def test_it_reads_the_full_board_not_the_redacted_copy():
    """`recommendations` is a paid key. Audited off the public copy this
    would report every open position as OFF THE BOARD — an alarm on a
    healthy system, which is how a tool stops being read."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    (tmp / "web" / "data" / "recommendations.json").write_text(
        json.dumps(_board(line=68.5, recommendations=[])))
    (tmp / "data" / "built").mkdir(parents=True)
    (tmp / "data" / "built" / "recommendations.json").write_text(
        json.dumps(_board(line=68.5)))
    db = tmp / "ledger.db"
    conn = ledger.connect(str(db))
    _bet(conn)
    cache = tmp / "cache"; cache.mkdir()
    old_root, old_cache, old_db = launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB
    launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB = tmp, cache, db
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch.bet_audit("nfl")
        out = buf.getvalue()
    finally:
        launch.ROOT, _fetch.CACHE_DIR, ledger.DEFAULT_DB = (
            old_root, old_cache, old_db)
    assert "data/built" in out, out
    assert "OFF THE BOARD" not in out, out


# --- the Most Likely book ---------------------------------------------------
#
# Ethan, 2026-09-09: "also all the lines for the most likley bets, not
# just the edge bets." Its rows go through the same index, but they are
# shaped differently enough that a naive match would have reported the
# whole likelihood book as missing or moved — an alarm on a healthy
# system, which is the failure this session has already committed twice.


def _likely_board(odds=-118, line=0.0):
    return {"games": [{"home": "MIN", "away": "GB", "date": "2026-09-13"}],
            "recommendations": [],
            "most_likely": [
                {"player": "MIN ML", "team": "MIN", "pick": "MIN",
                 "market": "moneyline", "line": line, "odds": odds,
                 "book": "FanDuel", "kind": "game"},
                {"player": "Justin Jefferson", "market": "rec_yds",
                 "side": "OVER", "line": 68.5, "odds": -110,
                 "book": "FanDuel", "kind": "prop"}],
            "long_shots": []}


def test_a_likelihood_moneyline_is_found_by_its_team_not_its_label():
    """The board calls it "MIN ML"; the journal stores "MIN". Keyed on the
    label alone every likelihood moneyline reads as OFF THE BOARD."""
    out = _run(_likely_board(),
               bets=[{"player": "MIN", "market": "moneyline", "line": 0.5,
                      "odds": -118, "category": "likely"}])
    assert "OFF THE BOARD" not in out, out
    assert "1 on the same number" in out, out


def test_a_moneyline_is_judged_on_its_price_because_it_has_no_line():
    """The journal gives a moneyline a 0.5 placeholder line and the board
    gives it 0.0. Comparing those two would flag every moneyline in the
    book; the number actually struck is the PRICE."""
    out = _run(_likely_board(odds=-220),
               bets=[{"player": "MIN", "market": "moneyline", "line": 0.5,
                      "odds": -118, "category": "likely"}])
    assert "PRICE MOVED  MIN moneyline @ -118" in out, out
    assert "board now: -220" in out, out
    assert "LINE MOVED" not in out, out


def test_a_likelihood_prop_is_checked_on_its_line_like_any_other():
    out = _run(_likely_board(),
               bets=[{"player": "Justin Jefferson", "line": 74.5,
                      "category": "likely"}])
    assert "LINE MOVED  Justin Jefferson" in out, out


def test_the_markets_whose_lines_are_stored_transformed_are_not_guessed_at():
    """A spread journals NEGATED so the standard grader applies, and the
    zero-line markets journal 0.5. Compared raw, every one of them reads
    as moved — a report that calls the whole book wrong is worth less
    than no report."""
    board = _likely_board()
    board["most_likely"].append(
        {"player": "MIN -1.5", "team": "MIN", "market": "spread",
         "line": -1.5, "odds": -110, "book": "FanDuel", "kind": "game"})
    out = _run(board, bets=[{"player": "MIN", "market": "spread",
                             "line": 1.5, "category": "likely"}])
    assert "NOT CHECKED  MIN spread" in out, out
    assert "LINE MOVED" not in out, out
    assert "1 not checked" in out, out


def test_a_foreign_venue_is_excluded_and_counted():
    """The first live run listed 155 Kalshi tickers as OFF THE BOARD.
    They are a different venue with their own tickers, never published on
    the sportsbook board, so there was never anything to compare them
    against — and printing them is what made the report unreadable."""
    out = _run(_board(), bets=[{"player": "KXNFLGAME-X", "market": "kalshi_ml",
                                "category": "predmarket"},
                               {"line": 68.5}])
    assert "1 open position(s) in predmarket" in out, out
    assert "KXNFLGAME-X" not in out, out
    assert "1 open · 1 on the same number" in out, out


def test_a_moved_line_in_an_affected_game_is_singled_out():
    """THE finding, separated from the noise. A payload from another week
    merged its props in by player name, so the players at risk are the
    ones in THOSE games. Every other moved line is ordinary movement or
    an alternate rung."""
    board = _board(line=74.5)
    board["recommendations"][0]["team"] = "MIN"
    out = _run(board, bets=[{"line": 68.5}],
               cached_events=[_ev("2026-11-15T18:00:00Z")])
    assert "AFFECTED GAME" in out, out
    assert "1 of the 1 are on players in the games whose payloads came " \
           "from another week" in out, out


def test_a_moved_line_in_a_clean_game_is_not_dressed_up_as_one():
    board = _board(line=74.5)
    board["recommendations"][0]["team"] = "DET"
    out = _run(board, bets=[{"line": 68.5}],
               cached_events=[_ev("2026-11-15T18:00:00Z")])
    assert "AFFECTED GAME" not in out, out
    assert "0 of the 1 are on players" in out, out


def test_with_no_stray_payload_it_says_the_bug_cannot_be_the_cause():
    """Movement is movement. If nothing from another week is cached there
    is no mechanism, and saying so stops a clean report reading as an
    open question."""
    out = _run(_board(line=74.5), bets=[{"line": 68.5}],
               cached_events=[_ev("2026-09-13T20:25:00Z")])
    assert "none of these can be the rematch bug" in out, out


def test_the_rung_explanation_is_on_the_page():
    """The first live run's biggest category was alternate rungs — a bet
    at 49.5 @ -192 against a board showing 59.5 @ -130 — and read without
    that sentence every one of them looks like a corrupted number."""
    out = _run(_board(line=74.5), bets=[{"line": 68.5}])
    assert "ALTERNATE RUNG" in out, out
    assert "the ladder working, not a corrupted number" in out, out


def test_the_flag_is_wired():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--bet-audit"' in src and "bet_audit(who)" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
