"""Share cards — a pick as a picture.

Ethan, 2026-08-25: *"Betting Twitter/Discord runs on screenshots.
Generate a clean share-card image per pick (player face, line, model
edge, your logo) … Every share is an ad with your domain on it."*

The failure this file exists to prevent is a button that does nothing.
Faces come from ESPN and MLB CDNs, and drawing a cross-origin image onto
a canvas TAINTS it — after which `toBlob` throws a SecurityError and
there is no card at all. The face is therefore attempted and never
required.

Run directly: `python3 tests/test_sharecard.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")


def test_a_tainted_canvas_cannot_happen():
    """crossOrigin="anonymous" makes the browser REFUSE an image whose
    CDN does not send the header that makes it safe, which fires onerror
    — and onerror is a fallback, not a failure. Without it the image
    loads, the canvas taints, and the export throws with no card."""
    i = APP.index("function _cardImage(src, cors)")
    body = APP[i:APP.index("\n}", i)]
    assert 'img.crossOrigin = "anonymous"' in body
    assert "img.onerror = () => resolve(null)" in body, \
        "a refused face would leave the card waiting forever"


def test_a_missing_face_still_draws_a_card():
    """Initials on the drawn chip, the same fallback the board uses. A
    card with initials beats a button that does nothing."""
    i = APP.index("async function shareCardCanvas(d)")
    body = APP[i:APP.index("\nasync function shareCard(", i)]
    assert "if (face) {" in body and "initials" in body


def test_the_logo_is_local_and_the_domain_is_on_every_card():
    """The card is the advertisement. A card that does not say where it
    came from is a screenshot of nothing."""
    i = APP.index("async function shareCardCanvas(d)")
    body = APP[i:APP.index("\nasync function shareCard(", i)]
    assert '_cardImage("logo-qb.png", false)' in body, \
        "the logo must not be loaded cross-origin — it is ours"
    assert "qellysbook.com" in body


def test_the_card_carries_the_reasoning_not_just_the_price():
    """A price with no model number behind it is a tout's graphic."""
    i = APP.index("async function shareCardCanvas(d)")
    body = APP[i:APP.index("\nasync function shareCard(", i)]
    assert '[["Model", d.proj], ["Hit", d.hit], ["Edge", d.edge]]' in body
    assert "Journaled at this price · graded in public" in body


def test_an_edge_that_rounds_to_zero_is_left_off():
    i = APP.index("function shareCardData(r)")
    body = APP[i:APP.index("\n}", i)]
    assert "Math.abs(r.edge * 100) >= 0.05" in body


def test_the_price_on_the_card_respects_the_reader_s_format():
    """Somebody who set decimal odds does not want −110 in the picture
    they are about to post."""
    i = APP.index("function shareCardData(r)")
    body = APP[i:APP.index("\n}", i)]
    assert "oddsTxt(r.odds)" in body


def test_it_is_the_same_shape_for_both_kinds_of_pick():
    """A game bet has no player and a prop has no matchup line; the
    drawing must not need to know which page it came from."""
    i = APP.index("function shareCardData(r)")
    body = APP[i:APP.index("\n}", i)]
    assert "const isGameBet" in body
    assert "return null" in body, "a row with nothing to say still draws"


def test_the_share_sheet_is_tried_before_a_download():
    """It is what actually gets a picture into a group chat, and a
    cancel is not a failure. Anchored on exportCard since the parlay
    card moved these rules there — one copy, shared by both drawings."""
    i = APP.index("function exportCard(canvas, name, done)")
    body = APP[i:APP.index("\n}", i)]
    assert "navigator.canShare({ files: [file] })" in body
    assert "a.download = name" in body, "no fallback on a desktop browser"
    assert "revokeObjectURL" in body, "the blob url leaks"
    assert "setTimeout(() => URL.revokeObjectURL" in body, \
        "revoked synchronously, Safari has not finished reading the blob"


def test_both_detail_pages_carry_the_button():
    assert 'data-card="${escapeAttr(propId(r))}"' in APP
    assert 'data-card="${escapeAttr(gameBetId(b))}"' in APP


def test_the_card_is_the_size_every_client_crops_to():
    assert "const CARD_W = 1200, CARD_H = 630;" in APP


def test_the_parlay_ticket_draws_too():
    """"Per pick/parlay" was the ask, and the first pass shipped only the
    pick half. A ticket is a LIST, so it is its own drawing: the legs
    stacked with sides and prices, the joint probability the chain
    models, and the price a book has to beat — the ticket's whole
    argument, and the number that makes the screenshot worth arguing
    with."""
    i = APP.index("async function shareParlayCanvas(t)")
    body = APP[i:APP.index("\nasync function shareParlay(", i)]
    assert "t.modeled_joint" in body and "t.required_american" in body
    assert "t.legs.slice(0, 4)" in body, "a 6-leg ticket would run off the card"
    assert "…and" in body, "the overflow legs vanish silently"
    assert "_cardImage" in body and "logo-qb.png" in body
    assert "qellysbook.com" in body
    # No faces by design: two headshots at this size are two thumbnails
    # fighting, and the legs are the point.
    assert "headshot" not in body
    assert 'data-parlay-card="${escapeAttr(String(t.rank))}"' in APP, \
        "no button on the ticket"


def test_both_cards_leave_through_one_export_path():
    """The share-sheet/download/revoke rules are where the
    browser-specific bugs live, and two copies of them drift."""
    assert "function exportCard(canvas, name, done)" in APP
    i = APP.index("async function shareCard(r, btn)")
    assert "exportCard(" in APP[i:APP.index("\n}", i) + 800]
    j = APP.index("async function shareParlay(t, btn)")
    assert "exportCard(" in APP[j:APP.index("\n}", j) + 800]
    # …and the rules live only in the one function now.
    assert APP.count("navigator.canShare && navigator.canShare({ files: [file] })") == 1


def test_the_font_stack_has_a_real_fallback():
    """Canvas silently substitutes when a family is missing, so a card
    would come out in Times without anybody being told."""
    i = APP.index("function cardFont(px, weight)")
    body = APP[i:APP.index("\n}", i)]
    assert "system-ui" in body and "sans-serif" in body
    i = APP.index("async function shareCardCanvas(d)")
    body = APP[i:APP.index("\nasync function shareCard(", i)]
    assert "document.fonts.ready" in body, \
        "the first card on a cold page draws in the fallback"


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
