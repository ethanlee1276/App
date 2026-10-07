"""The books' own icons, fetched on the box, read by the page off a manifest.

Ethan, 2026-10-07: "Can you maybe use real Sportsbook logos for that bet it
page?" Fixtures only: a fake fetcher stands in for the network.

Run directly: `python3 tests/test_booklogos.py`
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import booklogos as BL                                  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
PNG = BL.PNG_SIG + b"\x00" * 2000


def test_every_book_the_page_draws_has_a_domain_to_fetch_from():
    table = APP[APP.index("const BOOKS = {"):APP.index("const BOOK_ALIAS")]
    keys = set(re.findall(r"^  (\w+): \[", table, re.M))
    assert keys == set(BL.BOOK_DOMAINS), keys ^ set(BL.BOOK_DOMAINS)
    for d in BL.BOOK_DOMAINS.values():
        assert re.fullmatch(r"[a-z0-9.-]+\.[a-z]+", d), d
    assert BL.candidates("x.com")[0] == "https://x.com/apple-touch-icon.png"
    assert "google.com/s2/favicons?domain=x.com&sz=128" in BL.candidates("x.com")[-1]


def test_the_sites_own_icon_wins_a_placeholder_is_refused_and_a_miss_is_named():
    tmp = Path(tempfile.mkdtemp())
    calls = []
    def fake(url):
        calls.append(url)
        if url.startswith("https://sportsbook.fanduel.com/apple-touch-icon.png"):
            return PNG
        if "google.com" in url and "betrivers" in url:
            return BL.PNG_SIG + b"\x00" * 100           # the globe: too small to be a mark
        if "google.com" in url and "novig" in url:
            return PNG
        raise OSError("404")
    m = BL.fetch_all(tmp, get=fake, domains={"fanduel": "sportsbook.fanduel.com",
                                           "betrivers": "betrivers.com", "novig": "novig.us"})
    assert m["keys"] == ["fanduel", "novig"]
    assert (tmp / "fanduel.png").read_bytes() == PNG and (tmp / "novig.png").exists()
    assert not (tmp / "betrivers.png").exists() and "not a usable PNG" in m["missing"]["betrivers"]
    assert m["icons"]["fanduel"]["from"].startswith("https://sportsbook.fanduel.com/")
    assert m["icons"]["novig"]["from"].startswith("https://www.google.com/")
    back = json.loads((tmp / "manifest.json").read_text())
    assert back["keys"] == ["fanduel", "novig"] and back["fetched_at"]
    assert not BL.usable(b"GIF89a" + b"\x00" * 3000), "only a PNG"


def test_the_page_reads_the_manifest_when_the_sheet_opens_and_lays_icons_over_the_badges():
    fn = APP[APP.index("function bookLogosLoad("):APP.index("function betItClose(")]
    assert 'fetch("img/books/manifest.json"' in fn and "_bookLogos = new Set(" in fn
    assert 'img/books/${k}.png' in fn and 'data-onerr="remove"' in fn
    assert "bookLogosLoad().then(" in fn, "the sheet decorates itself when the list arrives"
    assert 'data-book="' in APP[APP.index("function bookMarkHTML("):APP.index("function betWords(")]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            n += 1
    print(f"\n{n} tests passed.")
