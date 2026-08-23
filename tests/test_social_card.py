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
    # THE NAME IS READ OUT OF THE MARKUP, not hard-coded here. The card
    # is versioned — scrapers cache a preview by URL and hold it for a
    # long time, so a redesign written back to the same filename keeps
    # showing the old card — and a test naming one version pins the site
    # to it. It checks the file the page actually points at.
    head = _head(_read("web", "index.html"))
    name = _meta(head, "property", "og:image")
    assert name and name.endswith(".png"), f"og:image is {name!r}"
    path = _root("web", name)
    assert os.path.exists(path), (
        f"{name} is missing; regenerate it with tools/ogcard.py")
    assert _meta(head, "name", "twitter:image") == name, (
        "og:image and twitter:image point at different files, so half the "
        "clients show the old card")
    with open(path, "rb") as fh:
        data = fh.read(24)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (1200, 630), f"card is {w}x{h}; scrapers crop 1.91:1 from 1200x630"

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


def test_the_card_wears_the_mark_the_site_wears():
    """Ethan found this in a group text, next to a promo code he had just
    sent his friends: the preview was still the amber ellipse and the
    pre-gold palette, two days after the site started wearing the QB
    crown. A preview is the brand for everyone who has not arrived yet,
    and it had quietly become a picture of a site that no longer exists."""
    src = _read("web", "og-card.html")
    body = src[src.index("<body"):]
    assert 'src="logo-qb.png"' in body, "the card is not wearing the QB mark"
    assert "<ellipse" not in body, "the retired ellipse mark is back"
    # And it is set the way the header sets it, rather than as a second
    # version of the wordmark.
    assert "text-transform: uppercase" in src and "letter-spacing: .19em" in src


def test_the_card_filename_is_versioned():
    """Scrapers cache a preview image by URL and hold it — iMessage and
    Discord especially. A redesign written back to the same filename keeps
    showing the OLD card to everybody who has already shared the link,
    which is the one audience a redesign is for."""
    head = _head(_read("web", "index.html"))
    name = _meta(head, "property", "og:image") or ""
    assert re.search(r"-v\d+\.png$", name), (
        f"{name!r} is unversioned, so the redesign will not reach anyone "
        "whose client already cached the old one")
    tool = _read("tools", "ogcard.py")
    assert name in tool, (
        "the renderer writes a different filename than the page serves")


def test_the_card_can_be_regenerated_by_one_command():
    """It used to be a four-step recipe in an HTML comment — start a
    server on some port, write a Node one-liner, screenshot, remember the
    viewport. Steps run twice a year are steps that get run wrong, and
    the only place the mistake shows up is inside somebody else's text
    message."""
    tool = _read("tools", "ogcard.py")
    assert "def render(" in tool
    # It has to REFUSE a bad render rather than write one. A fixed-size
    # card crops in silence, so overflow is not a warning.
    assert "overflows the card" in tool
    assert "raise SystemExit" in tool
    assert "pageerror" in tool, (
        "the Overhead is drawn by a script; a throw there leaves an empty "
        "panel that looks like a design choice")


def test_the_frame_is_checked_against_the_file_not_the_intention():
    """`screenshot` honours the viewport, and the viewport is set in the
    same file that asserts the size, so checking the constant against
    itself would prove nothing. It reads the PNG header back."""
    tool = _read("tools", "ogcard.py")
    assert "struct.unpack" in tool and "b\"\\x89PNG" in tool


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
