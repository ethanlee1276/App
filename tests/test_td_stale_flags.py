"""Touchdown flags are sampled by the stale shadow book, in both leagues.

Ethan, 2026-09-07: "you worked on the NFL and CFB TD Model and made it
better."

The best-measured signal in this repository — a book a point under the
field's consensus beat the close 64.8% of the time — was sampled at a
flat 0.1u on yardage props and never on the one prop market the
football edge boards actually stake, the anytime touchdown. Two gaps:
`price_props` skips the touchdown market (the long-shot board prices
it), so no touchdown row ever reached `stale_quotes`; and the journal's
settleable set had no `anytime_td`, so a flag could not have been
written even if one had. The per-book quotes were on the prop the
whole time. Now every touchdown quote reaches the scan on both boards,
a flag journals as OVER 0.5, and it settles from the same game-log rows
the long-shot book grades on.

Run directly: `python3 tests/test_td_stale_flags.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger, pipeline                       # noqa: E402
from engine.models import ANYTIME_TD, SportsbookLine, Prop    # noqa: E402
from engine.sources import oddsapi                            # noqa: E402


class _Game:
    def __init__(self, date, state="scheduled"):
        self.date = date
        self.live = type("L", (), {"state": state})()


class _Slate:
    def __init__(self, props, game):
        self.props = props
        self._game = game

    def game_for(self, prop):
        return self._game


def _prop(player, market, lines):
    return Prop(player=player, team="DET", opponent="NO", position="RB", market=market,
                logs=[], career_avg=0.0, vs_opponent_avg=None, lines=lines)


def _td(player, quotes):
    """A touchdown prop with one Yes/No pair per book at 0.5."""
    return _prop(player, ANYTIME_TD, [SportsbookLine(b, 0.5, y, n) for b, y, n in quotes])


def test_the_market_settles_in_the_shadow_book():
    assert "anytime_td" in ledger.STALE_SETTLEABLE
    assert "anytime_td" in ledger.SETTLEABLE_LONGSHOTS, "the long-shot book already grades it"


def test_touchdown_quotes_reach_the_scan_one_row_per_player():
    slate = _Slate([
        # Three books; DraftKings pays +200 where the field pays +150/+160.
        _td("Jahmyr Gibbs", [("DraftKings", 200, -260), ("FanDuel", 150, -190),
                             ("BetMGM", 160, -200)]),
        _td("Sam LaPorta", [("DraftKings", 300, None), ("FanDuel", 300, None),
                            ("BetMGM", 300, None)]),
        # Not a touchdown prop: not this scan's business.
        _prop("Jared Goff", "pass_yds", [SportsbookLine("DraftKings", 250.5, -110, -110)]),
        # A proxy is not a quote.
        _td("Nobody", [("proxy", 250, -110)]),
    ], _Game("2026-09-14"))
    rows = pipeline.td_scan_rows(slate)
    assert [r["player"] for r in rows] == ["Jahmyr Gibbs", "Sam LaPorta"], rows
    g = rows[0]
    assert g["market"] == "anytime_td" and g["has_market"] is True and g["game_date"] == "2026-09-14"
    assert g["all_lines"][0] == {"book": "DraftKings", "line": 0.5, "over_odds": 200, "under_odds": -260}
    assert rows[1]["all_lines"][0]["under_odds"] == 0, "a Yes-only quote has no under, not a fake one"
    flags = pipeline.market_scan([], extra=rows)["stale"]
    # Both sides are scanned: the Yes at DraftKings (+200 against a
    # +150/+160 field, 5.9 points) and the No at FanDuel (−190 against
    # −260/−200, 3.9 points). Gap-sorted, one flag per side; LaPorta's
    # Yes-only quotes, all +300, flag nothing.
    assert [(f["player"], f["book"], f["side"], f["odds"]) for f in flags] == \
        [("Jahmyr Gibbs", "DraftKings", "OVER", 200), ("Jahmyr Gibbs", "FanDuel", "UNDER", -190)], flags
    f = flags[0]
    assert (f["market"], f["line"]) == ("anytime_td", 0.5)
    assert f["gap_pts"] >= 1.0 and f["books_compared"] == 3
    # The scan's other outputs are untouched by touchdown rows — an arb
    # needs two sides and a Yes/No market has one price.
    assert pipeline.market_scan([], extra=rows)["arbs"] == []


def test_a_live_game_is_flagged_but_never_journaled():
    slate = _Slate([_td("Jahmyr Gibbs", [("DraftKings", 200, -260), ("FanDuel", 150, -190),
                                         ("BetMGM", 160, -200)])], _Game("2026-09-14", "live"))
    rows = pipeline.td_scan_rows(slate)
    assert rows[0]["live"] is True
    scan = pipeline.market_scan([], extra=rows)
    conn = ledger.connect(":memory:")
    assert ledger.log_stale_flags(conn, {"sport": "nfl", "date": "2026-W02", "market_scan": scan}) == 0


def test_a_flag_journals_as_over_half_and_settles_from_the_game_log():
    """A Saturday already played (the settler grades today's and
    yesterday's dates only on positive proof the game finished)."""
    slate = _Slate([_td("Runner A", [("DraftKings", 200, -260), ("FanDuel", 150, -190),
                                     ("BetMGM", 160, -200)])], _Game("2026-09-05"))
    scan = pipeline.market_scan([], extra=pipeline.td_scan_rows(slate))
    lconn = ledger.connect(":memory:")
    # Two flags (the Yes and the No), one journal key per player and
    # market: the larger gap — the Yes — is the row, as the journal's
    # own note says.
    assert ledger.log_stale_flags(lconn, {"sport": "cfb", "date": "2026-09-05", "market_scan": scan}) == 1
    row = dict(lconn.execute("SELECT sport, date, player, market, side, line, book, odds, "
                             "stake_units, category, status FROM bets").fetchone())
    assert row == {"sport": "cfb", "date": "2026-09-05", "player": "Runner A",
                   "market": "anytime_td", "side": "OVER", "line": 0.5, "book": "DraftKings",
                   "odds": 200, "stake_units": 0.1, "category": "stale", "status": "open"}, row
    # He scored: the flag settles won from the same rows the long-shot
    # book grades on.
    hist = db.connect(":memory:")
    hist.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, "
                 "opponent, position, home, market, value) VALUES "
                 "('cfb', 2026, '2026-09-05', 'g1', 'Runner A', 'TOL', 'BGSU', 'RB', 1, "
                 "'anytime_td', 1)")
    hist.commit()
    assert ledger.settle_from_history(lconn, hist, sport="cfb") == 1
    got = dict(lconn.execute("SELECT status, pnl_units FROM bets").fetchone())
    assert got["status"] == "won" and abs(got["pnl_units"] - 0.2) < 1e-9, got


def test_both_boards_hand_their_touchdown_quotes_to_the_scan():
    src = inspect.getsource(pipeline.run_slate)
    assert "_market_scan(results, ls, extra=td_scan_rows(slate))" in src
    import cfb_build
    src = inspect.getsource(cfb_build.main)
    assert "extra=td_scan_rows(games, td_quotes)" in src
    # And the scan itself sends the extra rows to the stale scan only.
    src = inspect.getsource(pipeline._market_scan)
    i = src.index("scan_recommendations(results)")
    j = src.index("results = list(results) + list(extra or [])")
    k = src.index('out["stale"] = stale_quotes(results)')
    assert i < j < k, "the arb scan runs on the field alone; the stale scan sees the touchdown rows"


def test_college_rows_carry_the_real_name_from_the_quote():
    ev = {"bookmakers": [
        {"key": k, "title": t, "markets": [{"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "Runner A", "price": y},
            {"name": "No", "description": "Runner A", "price": n}]}]}
        for k, t, y, n in (("draftkings", "DraftKings", 200, -260),
                           ("fanduel", "FanDuel", 150, -190),
                           ("betmgm", "BetMGM", 160, -200))]}
    quotes = oddsapi.parse_event_scorers(ev)
    key = ("runner a", "anytime_td")
    assert all(q["player"] == "Runner A" for q in quotes[key]), quotes
    import cfb_build
    games = [{"game_id": "g0", "home": "TOL", "away": "BGSU", "date": "2026-09-12"}]
    rows = cfb_build.td_scan_rows(games, {0: {"runner a": quotes[key]}})
    assert len(rows) == 1 and rows[0]["player"] == "Runner A"
    assert rows[0]["game_date"] == "2026-09-12" and rows[0]["live"] is False
    assert [ln["book"] for ln in rows[0]["all_lines"]] == ["DraftKings", "FanDuel", "BetMGM"]
    flags = pipeline.market_scan([], extra=rows)["stale"]
    assert [(f["player"], f["book"], f["side"]) for f in flags] == \
        [("Runner A", "DraftKings", "OVER"), ("Runner A", "FanDuel", "UNDER")], flags
    # A quote without a name (an older cache) builds no row rather than
    # a row nothing can settle.
    nameless = [{k: v for k, v in q.items() if k != "player"} for q in quotes[key]]
    assert cfb_build.td_scan_rows(games, {0: {"runner a": nameless}}) == []


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
