"""Each Most Likely pick shows its bigger lines — the price, our chance, what it is worth — never as a pick.

Ethan, 2026-10-23: "I don't understand why we recommend just the low -240
40 yard line tho. If we know a player can do well we should be
recommending the higher line bc obv it would have hit." Shown the history
(receivers projected 50 to 60 yards cleared 40 in 64% of games, 60 in 42%,
80 in 26%), he chose to keep the pick the likeliest line and show the
bigger ones beside it: each with the best bettable price, our chance and
the price at which it is worth betting, marked where the price beats our
chance (engine/likely.bigger_lines).

What these hold: the bigger lines run further out on the pick's own side,
nearest first, shopped to the best bettable price; they span the ladder
rather than crowding its next half-yard; a marked line clears the Pick of
the Day's own EV floor and is never the one left off; a long shot, a
number our curve and the book's own price disagree on, a price nobody can
bet, a broken two-sided quote and a further-out number paying less than the
pick (the box's under 14.5 at -9900, 2026-10-24) are not listed; the pick itself does not move; the journal stakes
the pick and nothing else; and both card layouts draw the fold, which
opens without leaving the board.

Run directly: `python3 tests/test_likely_bigger_lines.py`
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                          # noqa: E402
from engine import likely as K                                     # noqa: E402
from engine import potd                                            # noqa: E402
from engine.odds import expected_value                             # noqa: E402

#: The real fitted mixture from 2026-08-30 (see tests/test_likely.py).
FITS = {"rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60}}


def _ln(book, line, over, under=None):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _receiver(**kw):
    """A 72-yard receiver whose likeliest line inside the cap is 40+ at -240."""
    got = {"player": "A Receiver", "team": "CHI", "opponent": "NE", "market": "rec_yds",
           "market_label": "Receiving Yards", "side": "over", "line": 64.5, "book": "DraftKings",
           "odds": -115, "has_market": True, "fair_prob": 0.5, "hit_prob": 0.5, "raw_prob": 0.5,
           "projection": 72.0, "recent_values": [81, 57, 73, 90, 62, 76], "reasons": ["because"],
           "date": "2026-10-25", "game_date": "2026-10-25",
           "all_lines": [_ln("FanDuel", 64.5, -112, -112)],
           "alt_lines": [_ln("DraftKings", 39.5, -240, 190), _ln("DraftKings", 49.5, -165, 130),
                         _ln("DraftKings", 59.5, -120, -105), _ln("DraftKings", 69.5, 125, -160),
                         _ln("DraftKings", 79.5, 185, -250), _ln("DraftKings", 89.5, 270, -380),
                         _ln("DraftKings", 99.5, 380, -550), _ln("FanDuel", 69.5, 135, -170)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def _american(p):
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _spaced(r):
    """The listed lines that are not marked step down by BIGGER_STEP each."""
    last = r["model_prob"]
    plain = [c for c in r["bigger_lines"] if not c["better"]]
    for c in plain:
        assert last - c["prob"] >= K.BIGGER_STEP - 1e-9, (last, c)
        last = c["prob"]
    return plain


def _pick(prop):
    board = K.build([prop], sport="nfl", fits=FITS)
    assert len(board) == 1, board
    return board[0]


def test_the_pick_stays_the_likeliest_line_and_lists_the_bigger_ones():
    r = _pick(_receiver())
    assert (r["side"], r["line"], r["odds"]) == ("over", 39.5, -240), "the pick itself does not move"
    got = r["bigger_lines"]
    assert [c["line"] for c in got] == [49.5, 59.5, 69.5, 99.5], got
    assert all(c["side"] == "over" for c in got)
    seventy = got[2]
    assert (seventy["odds"], seventy["book"]) == (135, "FanDuel"), "shopped to the best price"
    for c in got:
        assert c["prob"] == round(K._prob_at(_receiver(), "rec_yds", "over", c["line"], FITS), 4)
        p = c["prob"]
        fair = expected_value(p, c["worth_at"])
        assert abs(fair) < 0.02, (c, fair)


def test_they_span_the_ladder_and_a_marked_line_is_never_left_off():
    r = _pick(_receiver())
    assert len(_spaced(r)) <= K.BIGGER_SHOWN
    marked = [c for c in r["bigger_lines"] if c["better"]]
    assert [c["line"] for c in marked] == [99.5], "past the three spaced lines, and still listed"
    # A second book's ladder in half-yards between the first's rungs: the
    # list still steps down the ladder rather than along its next yard.
    dense = _receiver(alt_lines=_receiver()["alt_lines"] + [
        _ln("BetMGM", 44.5, -200, 160), _ln("BetMGM", 45.5, -190, 150), _ln("BetMGM", 46.5, -180, 145)])
    lines = [c["line"] for c in _spaced(_pick(dense))]
    assert len({44.5, 45.5, 46.5} & set(lines)) <= 1, lines


def test_marked_means_the_pick_of_the_days_own_floor():
    prop, pick = _receiver(), {"side": "over", "line": 39.5, "model_prob": 0.74, "market": "rec_yds"}
    p = K._prob_at(prop, "rec_yds", "over", 99.5, FITS)
    seen = set()
    for odds in (330, 380, 450):
        prop = _receiver(alt_lines=[_ln("DraftKings", 99.5, odds, -550)])
        got = {c["line"]: c for c in K.bigger_lines(prop, pick, FITS)}
        assert got[99.5]["better"] == (expected_value(p, odds) >= potd.MIN_EV), odds
        seen.add(got[99.5]["better"])
    assert seen == {True, False}, "both sides of the floor were asked"


def test_an_under_pick_goes_down_the_ladder():
    base = _receiver(projection=40.0, recent_values=[35, 41, 28, 44, 39, 36], alt_lines=[], all_lines=[])
    ladder = []
    for line in (59.5, 49.5, 39.5, 29.5):
        p = K._prob_at(base, "rec_yds", "under", line, FITS)
        ladder.append(_ln("DraftKings", line, _american(1 - p + 0.02), _american(p + 0.02)))
    pick = {"side": "under", "line": 59.5, "market": "rec_yds",
            "model_prob": K._prob_at(base, "rec_yds", "under", 59.5, FITS)}
    got = K.bigger_lines(dict(base, alt_lines=ladder), pick, FITS)
    assert got and all(c["side"] == "under" and c["line"] < 59.5 for c in got), got
    assert [c["line"] for c in got] == sorted((c["line"] for c in got), reverse=True), "nearest first"
    assert not any(c["better"] for c in got), "a book's own price, vig on top, is not priced better"


def test_what_is_never_listed():
    pick = {"side": "over", "line": 39.5, "model_prob": 0.74, "market": "rec_yds"}

    def lines(*ladder):
        return [c["line"] for c in K.bigger_lines(_receiver(alt_lines=list(ladder), all_lines=[]), pick, FITS)]
    assert lines(_ln("proxy", 59.5, 140, -170), _ln("Pinnacle", 69.5, 160, -190)) == [], "nobody can bet those"
    assert lines(_ln("DraftKings", 59.5, 99999, -170)) == [], "a price no book could post"
    assert lines(_ln("DraftKings", 119.5, 900, -1500)) == [], "under one in five is a long shot"
    assert lines(_ln("DraftKings", 59.5, -400, 300)) == [], "our chance and the book's own price disagree"
    assert lines(_ln("DraftKings", 29.5, -500, 350)) == [], "a smaller line is not a bigger one"
    assert lines(_ln("DraftKings", 59.5, -120, -105)) == [59.5], "and the same number, sanely priced, is"


def test_a_broken_or_stale_quote_is_not_a_bigger_line():
    pick = {"side": "under", "line": 19.5, "odds": -114, "model_prob": 0.56, "market": "rec_yds"}
    base = _receiver(projection=20.0, recent_values=[18, 25, 12, 30, 15, 22], all_lines=[])

    def lines(*ladder, at=pick):
        return [(c["line"], c["odds"]) for c in K.bigger_lines(dict(base, alt_lines=list(ladder)), at, FITS)]
    p = K._prob_at(base, "rec_yds", "under", 14.5, FITS)
    fair = _ln("DraftKings", 14.5, _american(1 - p + 0.025), _american(p + 0.025))
    assert lines(fair) == [(14.5, fair["under_odds"])], "the sane price is listed"
    assert lines(_ln("DraftKings", 14.5, -110, -9900)) == [], "both sides heavy: a suspended pair"
    assert lines(_ln("DraftKings", 14.5, 0, -9900)) == [], "one side, far from our chance"
    stale = _ln("DraftKings", 14.5, -150, 120)
    assert lines(stale) == [(14.5, 120)], "pays more than a -114 pick"
    assert lines(stale, at=dict(pick, odds=150)) == [], "less likely than a +150 pick and pays less"


def test_the_journal_stakes_the_pick_and_nothing_else():
    r = _pick(_receiver())
    assert r["bigger_lines"]
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_most_likely(conn, {"sport": "nfl", "date": "2026-W08", "most_likely": [r]})
    got = conn.execute("SELECT side, line, odds FROM bets WHERE player = 'A Receiver'").fetchall()
    assert [(str(s).lower(), float(ln), int(o)) for s, ln, o in got] == [("over", 39.5, -240)], got
    for path in ("engine/ledger.py", "engine/potd.py", "engine/parlays.py",
                 "engine/likelysize.py", "nfl_build.py"):
        assert "bigger_lines" not in open(os.path.join(ROOT, path), encoding="utf-8").read(), path
    # The board reads them for one thing: holding their chances to its price
    # rule (likelyboard.trust_bigger), never to stake or rank them.
    board = open(os.path.join(ROOT, "engine", "likelyboard.py"), encoding="utf-8").read()
    at = board.index("def trust_bigger(")
    body = board[at:board.index("\ndef ", at + 1)]
    assert board.count('"bigger_lines"') == body.count('"bigger_lines"') == 1


def test_both_layouts_draw_the_fold_and_it_opens_in_place():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    at = app.index("function likelyBiggerHTML(r)")
    body = app[at:app.index("\n}\n", at)]
    assert "american(c.odds)" in body and "american(c.worth_at)" in body and "wholePct(c.prob)" in body
    assert "priced better than its chance" in body and "Never staked or journaled." in body
    ob = app[app.index("function obCardHTML("):]
    assert "${likelyBiggerHTML(r)}" in ob[:ob.index("\n}\n")], "the one-board card"
    card = app[app.index("function likelyCard(r)"):]
    assert "${likelyBiggerHTML(r)}" in card[:card.index("\n}\n")], "the shelf card"
    # the shelf card is a door: a fold inside it reads, it does not navigate
    assert app.count("if (card && foldInside(card, e.target)) return;") == 2, "click and keyboard"
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    assert ".ob-bigger { grid-column: 1 / -1;" in css, "a full-width last row on the one-board card"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
