"""The dashboard, to Ethan's render (2026-09-26).

"also fix how all of this is going off the page" — the rail's record
ribbons ran past the 280px column: the record and its number were held on
one unbreakable line (160px of room, 171px of text). And "here is a new
render of the dashboard page. i want you to match this render. i also
attached two renders of the backround images": the book's name on the
helmet banner, the quick links as tiles with a chevron, the football Pick
of the Day and the quiet Live now card on the ball-under-the-lights art,
and a green dot beside Live now.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
IMG = ROOT / "web" / "img" / "home"


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_two_backgrounds_ship_small_with_a_phone_size():
    for stem in ("qb-helmet", "nfl-ball"):
        big, small = IMG / f"{stem}.webp", IMG / f"{stem}@800.webp"
        assert big.read_bytes()[8:12] == b"WEBP" and small.read_bytes()[8:12] == b"WEBP"
        assert big.stat().st_size < 400_000 and small.stat().st_size < 120_000
        assert f"img/home/{stem}@800.webp 800w, img/home/{stem}.webp 1600w" in APP


def test_the_book_names_itself_on_the_helmet_inside_the_tools():
    """Inside #quick-tools, so it adds no new block above the picks
    (tests/test_board_order's list of what may sit there)."""
    tools = _fn("renderQuickTools")
    assert "${brandHeroHTML()}" in tools
    hero = _fn("brandHeroHTML")
    assert "<b>Qellys Book</b>" in hero and "Real data. Real edges. Real results." in hero
    assert 'aria-hidden="true"' in hero and 'alt=""' in hero, "the art is decoration"
    assert tools.count("${go}</a>") == 4, "every quick link carries its chevron"
    assert "  chev: '<path" in APP


def test_football_draws_the_ball_and_the_other_sports_keep_their_venue():
    art = _fn("potdBallArt")
    assert '["nfl", "cfb"].includes(state.sport)' in art and 'return "";' in art
    potd = _fn("renderPickOfTheDay")
    assert potd.count("potdBallArt()") >= 2 or "const art = potdBallArt();" in potd
    assert 'data-art="ball"' in potd
    assert '.potd-hero[data-art="ball"] { padding: 22px 26px; background-image: none; }' in CSS
    assert "mask-image: var(--grad-potd-mask);" in CSS, "the ball fades into the card, no seam"


def test_live_now_has_its_green_dot_and_the_quiet_card_its_field():
    live = _fn("deckLiveHTML")
    assert 'Live now <i class="hd-live-dot" aria-hidden="true"></i>' in live
    assert 'class="hd-field" aria-hidden="true"' in live and '["nfl", "cfb"]' in live
    assert ".hd-live-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--good); }" in CSS


def test_the_rail_ribbons_wrap_inside_the_column():
    """The record and its number are each whole, and the line breaks
    between them before the rail does."""
    assert '<span class="hd-big"><span class="hd-rec">${rec}</span> <b' in APP
    assert ".hd-rec { white-space: nowrap; }" in CSS
    assert ".rail-slip .hd-rw .hd-big { display: flex; flex-wrap: wrap; column-gap: 6px; white-space: normal; }" in CSS
    assert ".rail-slip .hd-rw > * { min-width: 0; overflow-wrap: anywhere; }" in CSS
    # the more specific rule wins over the older nowrap one
    older = CSS.index(".rail-slip .hd-big { white-space: nowrap; }")
    assert CSS.index(".rail-slip .hd-rw .hd-big {") > older


def test_the_new_gradients_are_tokens():
    for name in ("--grad-brand-side", "--grad-brand-foot", "--grad-potd-mask", "--grad-field-quiet"):
        assert re.search(rf"^  {name}: linear-gradient\(.*\);$", CSS, re.M), name


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
