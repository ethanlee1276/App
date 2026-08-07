"""What a shared link looks like before anyone arrives.

The site had no `og:` tags at all, and no meta description — a pasted link
rendered as a bare URL in every client that shows a preview. This is the
cheapest surface the Overhead can reach, and the only one on the
distinctiveness list that turns a share into a branded impression rather
than a line of text.

Two things here are load-bearing and easy to break later.

**The card carries no live numbers.** The running record belongs on the
site, where it updates. Baked into a static PNG it starts decaying the
moment it is written, and a stale ROI on a shared link is the single most
damaging thing this site could publish — the whole positioning is that the
numbers are real and current. The durable claim (every pick journaled at
its real price, graded in public) is true on any day, so that is what the
card says.

**The URLs are relative on purpose.** There is no host yet — `launch.py`
serves the site from a local directory — so there is no origin to write.
A placeholder domain would resolve to nothing, which is worse than a
relative path that every major scraper resolves against the page it found
it on. These begin working the moment the site has an address.
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _root(*parts):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), *parts)


def _read(*parts):
    with open(_root(*parts), encoding="utf-8") as fh:
        return fh.read()


def _head(html):
    return html[: html.index("</head>")]


def _meta(head, attr, name):
    m = re.search(rf'<meta\s+{attr}="{re.escape(name)}"\s+content="([^"]*)"', head)
    return m.group(1) if m else None


REQUIRED_OG = ["og:type", "og:site_name", "og:title", "og:description",
               "og:image", "og:image:width", "og:image:height", "og:image:alt"]
REQUIRED_TW = ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]


def test_a_pasted_link_has_something_to_show():
    head = _head(_read("web", "index.html"))
    missing = [k for k in REQUIRED_OG if _meta(head, "property", k) is None]
    missing += [k for k in REQUIRED_TW if _meta(head, "name", k) is None]
    assert not missing, f"no preview without these: {missing}"
    assert _meta(head, "name", "description"), (
        "a meta description is what a search result and several chat "
        "clients fall back to when they do not read og:"
    )
    assert _meta(head, "name", "twitter:card") == "summary_large_image", (
        "the default `summary` card crops to a small square and throws the "
        "Overhead away — the image is the entire point of doing this"
    )


def test_the_card_image_is_the_size_every_scraper_expects():
    """1200x630. Read out of the PNG header rather than trusted from the
    markup, because the tag and the file are two different things and it is
    the file that gets cropped."""
    path = _root("web", "og-card.png")
    assert os.path.exists(path), "og-card.png is missing; regenerate it from og-card.html"
    with open(path, "rb") as fh:
        data = fh.read(24)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "og-card.png is not a PNG"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (1200, 630), f"card is {w}x{h}; scrapers crop 1.91:1 from 1200x630"

    head = _head(_read("web", "index.html"))
    assert _meta(head, "property", "og:image:width") == str(w)
    assert _meta(head, "property", "og:image:height") == str(h), (
        "the declared dimensions must match the actual file, or clients "
        "reserve the wrong space and the card jumps"
    )
    # Twitter's ceiling is 5MB; anything near it is a slow preview anyway.
    assert os.path.getsize(path) < 2_000_000, "card is too heavy for a preview"


def test_no_live_number_is_baked_into_the_card():
    """The one mistake this card cannot make.

    A record or an ROI in a static image is wrong the day after it is
    written, and it would be wrong on the surface people see BEFORE they
    reach the site that would have corrected it.
    """
    src = _read("web", "og-card.html")
    body = src[src.index("<body"):]
    banned = re.findall(r"[-+]\d+(?:\.\d+)?%|\b\d+-\d+-\d+\b|\bROI\b", body)
    # The park factor drawn INSIDE the Overhead is a venue constant, not a
    # result — it is as live as the outfield wall. Everything else is out.
    banned = [b for b in banned if b not in ("+22%",)]
    assert not banned, (
        f"live-looking figures on a static card: {banned}. The record "
        "belongs on the site, where it updates."
    )
    assert "record" not in body.lower(), "no record on a card that cannot update"


def test_the_card_is_rendered_from_the_real_design_system():
    """A card hand-built somewhere else drifts from the site the first time
    either one changes, and then the preview is a version of the brand that
    no longer exists."""
    src = _read("web", "og-card.html")
    assert 'href="css/styles.css"' in src, "the card must use the real stylesheet"
    assert 'src="js/visuals.js"' in src, "the card must draw a real Overhead"
    assert "ballpark(" in src or "stadium(" in src or "octagon(" in src


def test_no_invented_domain():
    """Relative until there is a real origin. A guessed host resolves to
    nothing, which is strictly worse than a relative path."""
    head = _head(_read("web", "index.html"))
    for attr, keys in (("property", REQUIRED_OG), ("name", REQUIRED_TW)):
        for k in keys:
            v = _meta(head, attr, k) or ""
            if not v.startswith("http"):
                continue
            assert not re.search(r"example\.|yourdomain|localhost|TODO|CHANGEME", v, re.I), (
                f"{k} points at a placeholder ({v}); ship a relative path "
                "until the site has a real address"
            )


def test_the_theme_colour_matches_the_page():
    """It said #0f1420 — the pre-Night-Form panel — so the phone painted
    its chrome a different near-black to the page beneath it."""
    head = _head(_read("web", "index.html"))
    # Same trap as test_brand: a bare hex regex over the whole stylesheet
    # matches whichever theme happens to be written in hex, which stopped
    # being the dark one when the ramp moved to oklch().
    import make_icon
    bg = "#%02X%02X%02X" % make_icon.token("bg")
    assert (_meta(head, "name", "theme-color") or "").lower() == bg.lower(), (
        f"theme-color should be {bg}, the page's own background"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
