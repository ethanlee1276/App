"""Every market on the prediction page is identified the same way.

Ethan, 2026-08-19: "We should be following the thumbnails they use on
Polly and Kalshi and everything."

The desk's recommendation rows already drew team logos. The board below
drew a bare venue letter for all forty rows — so the two halves of one
page identified markets in two different ways, and the half with more
rows had the weaker treatment.

ONE LADDER, best available first:

  1. a matched game   both teams' logos, reading as a fixture
  2. Polymarket art   the venue's own market icon, its URL untouched
  3. a weather row    the sun mark
  4. anything else    the venue badge it always had

Kalshi publishes no market art at all, which is why rung 1 exists rather
than the code simply asking each venue for a picture. Rung 2 is the only
remote image and the only rung that can fail in flight, so it carries an
onerror that swaps in the venue badge — a broken-image glyph in a row of
clean ones is worse than the badge it replaced.

Run directly: `python3 tests/test_market_thumbs.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

from engine import predmarket as pm                             # noqa: E402


def _mkt(**over):
    m = {"slug": "a-market", "question": "Will it?",
         "outcomes": '["Yes","No"]', "outcomePrices": '["0.62","0.38"]',
         "volume24hr": 100, "liquidity": 50,
         "endDate": "2026-09-01T00:00:00Z"}
    m.update(over)
    return m


# --- the venue's art, captured and bounded ----------------------------------
def test_polymarkets_own_icon_is_kept():
    url = "https://polymarket-upload.s3.us-east-2.amazonaws.com/x.png"
    assert pm.parse_markets([_mkt(icon=url)])[0]["image"] == url


def test_the_full_size_image_is_the_fallback_for_a_missing_icon():
    url = "https://polymarket-upload.s3.us-east-2.amazonaws.com/big.png"
    assert pm.parse_markets([_mkt(image=url)])[0]["image"] == url


def test_only_https_survives():
    """The URL is written straight into a src. A market's picture comes
    from a third party's field, and `javascript:` in an attribute we
    interpolate is the whole XSS class in one line."""
    for bad in ("javascript:alert(1)", "http://plain.example/x.png",
                "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", ""):
        assert pm.parse_markets([_mkt(icon=bad)])[0]["image"] == "", bad


def test_a_market_with_no_art_says_so_rather_than_carrying_a_broken_key():
    assert pm.parse_markets([_mkt()])[0]["image"] == ""


# --- one ladder, used everywhere --------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\nfunction ", i + 10)]


def test_the_ladder_has_all_four_rungs_in_order():
    fn = _fn("pmThumb")
    order = [fn.index("kx-thumb-pair"), fn.index("r.image"),
             fn.index("kx-thumb-ic"), fn.rindex("venueMark")]
    assert order == sorted(order), \
        "the thumbnail ladder no longer prefers the best available art"


def test_a_dead_image_becomes_the_venue_badge_not_a_broken_glyph():
    fn = _fn("pmThumb")
    assert "onerror" in fn and "data-fb" in fn, \
        "a third-party image that 404s would leave a broken-image icon"
    assert "venueMark(r.venue" in fn


def test_the_desk_and_the_board_draw_the_same_art():
    """Two copies of a picture-choosing rule drift the moment one venue
    gains a field. The desk keeps its own CAPTION — it labels by sport or
    city where the board labels by venue — and nothing else."""
    desk = _fn("deskThumb")
    assert "pmThumb(r" in desk, "the desk grew a second copy of the ladder"
    assert "kx-thumb-pair" not in desk, "the ladder is duplicated again"
    board = APP[APP.index("function pmBoardRowHTML("):]
    board = board[:board.index("\nfunction ", 10)]
    assert "pmThumb(r" in board, "the board is back to a bare venue letter"


def test_the_detail_panel_shows_the_same_face():
    fn = APP[APP.index("function pmDetailHTML("):]
    fn = fn[:fn.index("\nconst PM_BOARD_SHOWN")]
    assert "pmThumb(r" in fn


def test_the_image_reaches_the_board_row():
    """`pmVenueRows` is the projection every board row passes through —
    the same place the price tape went missing."""
    fn = APP[APP.index("function pmVenueRows("):]
    fn = fn[:fn.index("\nconst PM_BOARD_SHOWN")]
    assert "image: m.image" in fn, "Polymarket art never reaches the row"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
