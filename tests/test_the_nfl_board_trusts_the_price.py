"""The NFL one board shows the price's number where ours runs above it.

pricetrust.py (step 109), tried week by week on settled board picks the
choice never saw: on the NFL board the weeks chose w = 1, T = 0 — never a
chance above the books' de-vigged price — and held-out log loss fell from
0.6966 to 0.6852 over 199 picks, every week better. Ethan, 2026-10-17:
"yes nfl board". engine/likelyboard.trust_price, behind QB_PRICE_TRUST.

The same rule holds each pick's bigger lines (likelyboard.trust_bigger,
2026-10-24): the box marked 196 of them "priced better than its chance" on
our curve's numbers, above the market's.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pricetrust as PT                                               # noqa: E402
from engine import ledger, likelyboard as LB                          # noqa: E402
from engine.odds import devig_two_way                                 # noqa: E402

QUOTES = [{"book": "draftkings", "line": 6.5, "over_odds": -200, "under_odds": 160},
          {"book": "fanduel", "line": 6.5, "over_odds": -190, "under_odds": 150},
          {"book": "betmgm", "line": 6.5, "over_odds": -210, "under_odds": 170},
          # Another number is another event; the proxy is no opinion.
          {"book": "caesars", "line": 7.5, "over_odds": -120, "under_odds": 100},
          {"book": "proxy", "line": 6.5, "over_odds": -400, "under_odds": 300}]


def _field_over():
    fairs = sorted(devig_two_way(q["over_odds"], q["under_odds"])[0] for q in QUOTES[:3])
    return fairs[1]


def _row(prob=0.80, side="OVER", **kw):
    return {"kind": "prop", "player": "Amon-Ra St. Brown", "team": "DET", "opponent": "NYJ",
            "market": "receptions", "side": side, "line": 6.5, "odds": -190, "book": "FanDuel",
            "model_prob": prob, "implied_prob": 0.64, **kw}


def _result(rows, quotes=QUOTES):
    return {"games": [], "most_likely": rows, "matchup_picks": [], "td_scenarios": [],
            "recommendations": [{"player": "Amon-Ra St. Brown", "market": "receptions", "all_lines": list(quotes)}]}


def test_the_market_chance_is_the_field_at_the_picks_own_line():
    quotes = LB.book_quotes(_result([]))
    market, books = LB.market_chance(_row(), quotes)
    assert books == 3, "three books at 6.5; the 7.5 quote and the proxy are not in it"
    assert abs(market - _field_over()) < 1e-9
    under, _ = LB.market_chance(_row(side="UNDER"), quotes)
    assert abs(under - (1.0 - _field_over())) < 1e-9
    assert LB.market_chance(_row(), LB.book_quotes(_result([], QUOTES[:2]))) is None, \
        "under three books there is no field, as pricetrust left such picks out"


def test_above_the_market_the_board_shows_the_markets_number():
    r = _row(prob=0.80)
    assert LB.trust_price([r], _result([]), "nfl") == 1
    assert abs(r["model_prob"] - round(_field_over(), 4)) < 1e-9
    assert r["trust_from"] == 0.80 and r["board_raw_prob"] == 0.80
    assert r["market_books"] == 3 and "we said 80%" in r["trust_note"]


def test_at_or_under_the_market_nothing_moves():
    r = _row(prob=0.55)
    assert LB.trust_price([r], _result([]), "nfl") == 0
    assert r["model_prob"] == 0.55 and "trust_from" not in r


def test_only_where_the_test_passed_and_only_while_switched_on():
    r = _row(prob=0.80)
    assert LB.trust_price([r], _result([]), "mlb") == 0 and r["model_prob"] == 0.80
    was = os.environ.get(LB.PRICE_TRUST_ENV)
    os.environ[LB.PRICE_TRUST_ENV] = "off"
    try:
        assert LB.trust_price([r], _result([]), "nfl") == 0 and r["model_prob"] == 0.80
    finally:
        if was is None:
            os.environ.pop(LB.PRICE_TRUST_ENV, None)
        else:
            os.environ[LB.PRICE_TRUST_ENV] = was


def test_a_posted_pick_is_judged_by_the_price_too():
    """A posted pick keeps its line, price and book; its chance is today's on
    every build, so the price judges it. Skipping posted picks left the box's
    first board after the change at 247 picks, none at the price."""
    r = _row(prob=0.80, locked=True)
    stats = {}
    assert LB.trust_price([r], _result([]), "nfl", stats=stats) == 1
    assert abs(r["model_prob"] - round(_field_over(), 4)) < 1e-9 and r["line"] == 6.5 and r["odds"] == -190
    assert stats == {"on": True, "rows": 1, "no_quotes": 0, "thin": 0, "fielded": 1, "above": 1, "moved": 1,
                     "posted": 1, "bigger_unmarked": 0}


def test_the_handoff_keeps_the_price_on_a_posted_pick_and_the_list_shows_it():
    """harmonize gives a posted pick the list's number back; the price judges
    that number again, and the list row shows what the board shows."""
    listed = _row(prob=0.82, locked=True)
    res = _result([listed])
    board = LB.build(res, sport="nfl", calibration={}, band_verdict=None)
    res["likely_board"] = board
    (b,) = board["rows"]
    LB.harmonize(res)
    want = round(_field_over(), 4)
    assert abs(b["model_prob"] - want) < 1e-9 and b["trust_from"] == 0.82
    assert abs(listed["model_prob"] - want) < 1e-9 and listed["listed_prob"] == 0.82
    assert "de-vigged price says" in listed["trust_note"]
    assert board["price_trust"]["moved"] == 1 and board["price_trust"]["posted"] == 1


def test_the_counts_say_where_a_pick_without_a_field_fell():
    stats = {}
    rows = [_row(prob=0.80), dict(_row(prob=0.80), line=9.5), dict(_row(prob=0.80), player="Nobody Quoted")]
    LB.trust_price(rows, _result([]), "nfl", stats=stats)
    assert (stats["fielded"], stats["thin"], stats["no_quotes"]) == (1, 1, 1), stats


def test_switched_off_the_build_says_so():
    was = os.environ.get(LB.PRICE_TRUST_ENV)
    os.environ[LB.PRICE_TRUST_ENV] = "off"
    try:
        board = LB.build(_result([_row(prob=0.80)]), sport="nfl", calibration={}, band_verdict=None)
    finally:
        if was is None:
            os.environ.pop(LB.PRICE_TRUST_ENV, None)
        else:
            os.environ[LB.PRICE_TRUST_ENV] = was
    assert board["price_trust"] == {"on": False, "rows": 0, "no_quotes": 0, "thin": 0, "fielded": 0, "above": 0,
                                    "moved": 0, "posted": 0, "bigger_unmarked": 0}
    assert board["rows"][0]["model_prob"] == 0.80


def test_the_board_checks_tiers_and_ranks_on_the_price_number():
    hot = _row(prob=0.80)
    board = LB.build(_result([hot]), sport="nfl", calibration={}, band_verdict=None)
    (row,) = board["rows"]
    assert abs(row["model_prob"] - round(_field_over(), 4)) < 1e-9
    assert "books' de-vigged price says" in row["check_notes"]["model"]
    mlb = LB.build(_result([_row(prob=0.80)]), sport="mlb", calibration={}, band_verdict=None)
    assert mlb["rows"][0]["model_prob"] == 0.80, "MLB's board is not on the rule"


def test_under_even_at_the_price_it_is_held_unless_the_matchup_backs_it():
    cheap = [dict(q, over_odds=q["under_odds"], under_odds=q["over_odds"]) for q in QUOTES]
    board = LB.build(_result([_row(prob=0.70)], cheap), sport="nfl", calibration={}, band_verdict=None)
    assert not board["rows"]
    (held,) = board["held"]
    assert held["model_prob"] < LB.DROP_FLOOR and "books' price gives it" in held["held_note"]


def test_the_journal_keeps_the_chance_before_the_price():
    conn = ledger.connect(":memory:")
    result = {"sport": "nfl", "date": "2030-W04",
              "games": [{"home": "BUF", "away": "MIA", "date": "2030-09-29", "kickoff": "13:00"}],
              "most_likely": [{"player": "A", "team": "MIA", "market": "receptions", "side": "OVER",
                               "line": 3.5, "odds": -110, "model_prob": 0.61, "trust_from": 0.74,
                               "board_raw_prob": 0.74, "book": "DraftKings"}]}
    assert ledger.log_most_likely(conn, result, depth=None, category="board", grade_label="Strong") == 1
    assert tuple(conn.execute("SELECT hit_prob, trust_from FROM bets").fetchone()) == (0.61, 0.74)


def test_pricetrust_re_tests_the_rule_on_what_it_was_applied_to():
    bets = [{"id": 1, "date": "2030-W04", "hit_prob": 0.61, "trust_from": 0.74, "market_p": 0.61, "status": "won"},
            {"id": 2, "date": "2030-W04", "hit_prob": 0.58, "trust_from": None, "market_p": 0.55, "status": "lost"}]
    ours = {r["id"]: r["ours"] for r in PT.scorable(bets)}
    assert ours == {1: 0.74, 2: 0.58}


LADDER = [{"book": b, "line": 8.5, "over_odds": o, "under_odds": u}
          for b, o, u in (("draftkings", 140, -175), ("fanduel", 135, -170), ("betmgm", 145, -180))]


def _bigger(prob, odds=145, extra=False, fair=None):
    return {"side": "over", "line": 8.5, "odds": odds, "book": "BetMGM", "prob": prob, "worth_at": 0,
            "better": True, "fair": fair, **({"extra": True} if extra else {})}


def test_the_bigger_lines_are_held_to_the_market_at_their_own_number():
    field = sorted(devig_two_way(q["over_odds"], q["under_odds"])[0] for q in LADDER)[1]
    r = _row(prob=0.80, bigger_lines=[_bigger(0.55), _bigger(0.52, extra=True)])
    res = _result([], QUOTES + LADDER)
    LB.trust_price([r], res, "nfl", stats=(st := {}))
    got = r["bigger_lines"]
    assert len(got) == 1, "the line listed only for its mark goes with the mark"
    c = got[0]
    assert c["raw_prob"] == 0.55 and abs(c["prob"] - round(field, 4)) < 1e-9
    assert c["better"] is False, "at the market's own chance, a book's price is no bargain"
    assert c["worth_at"] > 145, "and the worth-it price is read off the shown chance"
    assert st["bigger_unmarked"] == 2
    # Where the books' field is thin, the line's own book, de-vigged.
    lone = _row(prob=0.80, bigger_lines=[_bigger(0.55, fair=0.38)])
    LB.trust_price([lone], _result([]), "nfl")
    assert lone["bigger_lines"][0]["prob"] == 0.38
    # No market at all: our chance stands, as a pick's does.
    bare = _row(prob=0.80, bigger_lines=[_bigger(0.55)])
    LB.trust_price([bare], _result([]), "nfl")
    assert bare["bigger_lines"][0]["prob"] == 0.55 and bare["bigger_lines"][0]["better"] is True
    # A true line-shop survives: the market's chance at a price better than the field's.
    shop = _row(prob=0.80, bigger_lines=[_bigger(0.55, odds=230)])
    LB.trust_price([shop], res, "nfl")
    assert shop["bigger_lines"][0]["better"] is True
    # The other leagues, and the switch, leave them alone.
    other = _row(prob=0.80, bigger_lines=[_bigger(0.55)])
    LB.trust_price([other], res, "mlb")
    assert other["bigger_lines"][0]["prob"] == 0.55


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
