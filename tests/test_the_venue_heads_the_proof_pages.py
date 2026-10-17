"""The venue renders reach the proof and pick pages and the share card,
and on a phone a stadium card's prices lead its text.

Audit 2026-09-30, brand (roadmap #51). The renders were used on the home
cards, the hero and the game page; Record, Live, Edge and Most Likely —
where a signature asset carries most — were the plainest pages, and the
share card did not carry one either.
"""

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CARD = (ROOT / "web" / "og-card.html").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_a_band_heads_each_proof_and_pick_page_once():
    assert 'const VENUE_BAND_VIEWS = ["record", "live", "edge", "likely"];' in APP
    body = _fn("paintVenueBands")
    assert 'sec.querySelector(":scope > .venue-band")' in body, "once per page"
    assert 'aria-hidden="true"' in body and 'loading="lazy"' in body, "decorative and lazy"
    assert 'img.setAttribute("src", src)' in body, "a league switch swaps the picture"
    assert "if (band) band.remove();" in body, "a league with no render shows none"
    assert "paintVenueBands();" in _fn("enhanceSectionSubs")
    assert "venueSrc(`img/venues/variants/${fam}-gold.jpg`)" in _fn("venueBandSrc")
    for fam in ("football", "baseball", "basketball"):
        assert (ROOT / "web" / "img" / "venues" / "variants" / f"{fam}-gold.webp").exists(), fam


def test_the_band_is_low_and_the_phone_card_leads_with_prices():
    assert ".venue-band { position: relative; height: 64px;" in CSS
    m = re.search(r"@media \(max-width: 760px\) \{\s*\.venue-band \{ height: 44px; \}(.*?)\n\}", CSS, re.S)
    assert m and ".game-card .game-info > .gc-mkts { order: -1;" in m.group(1)


def test_the_share_card_carries_the_render_under_a_new_name():
    assert "img/venues/variants/football-gold.webp" in CARD
    assert HTML.count('content="og-card-v3.png"') == 2
    assert 'og-card-v3.png' in (ROOT / "tools" / "ogcard.py").read_text()
    assert 'og-card-v3.png' in (ROOT / "engine" / "routes.py").read_text()
    head = (ROOT / "web" / "og-card-v3.png").read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == (1200, 630)
    # The old name stays served: links already shared still unfurl.
    assert (ROOT / "web" / "og-card-v2.png").exists()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
