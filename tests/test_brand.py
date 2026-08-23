"""The Qellys Book brand mark has to stay one mark.

The Q is drawn three times — as CSS-styled SVG in the header, as a
standalone favicon, and rasterised into the iOS home-screen icon. Nothing
in the build ties them together, so a nudge to one and not the others
would ship a tab icon that doesn't match the page. These tests are that
tie. They also cover the plumbing that made the icons reachable at all:
the server has to know what a .png is, or iOS gets
application/octet-stream and shows a blank home-screen tile.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_icon
from server import CONTENT_TYPES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _numbers(text):
    """Every number in a blob of SVG, as floats — geometry, order-sensitive."""
    return [float(n) for n in re.findall(r"-?\d+\.?\d*", text)]


def _mark_geometry(svg_text):
    """The bowl ellipse, numbers only — cx, cy, rx, ry.

    The mark used to be a circle plus a crossing tail inside a translated
    <g>, and this helper read that <g>. It is the venue bowl now (redesign
    spec §6.1): one ellipse, no group, no optical nudge, because a
    symmetric shape needs no correction."""
    m = re.search(r"<ellipse[^>]*/>", svg_text)
    assert m, "no <ellipse> holding the mark"
    return _numbers(m.group(0))


def test_favicon_and_header_draw_the_same_mark():
    """THE INVARIANT SURVIVES THE ARTWORK, 2026-08-23.

    This compared ellipse geometry between favicon.svg and index.html,
    because the mark WAS an ellipse somebody drew. Ethan: "i really like
    the QB logo it has so we should use that for the site logo but take
    away where it says qellys book below it" — so it is a crop of his own
    icon now, photographic gold leaf with no vector of it.

    What was worth protecting is unchanged and is the reason this test
    exists: the tab and the page must not drift into two different
    marks. Same source file, checked by name."""
    head = _read("web", "index.html")
    m = re.search(r'<link rel="icon" href="([^"]+)"', head)
    assert m, "no tab icon at all"
    tab = m.group(1)
    assert '<img class="qmark" src="logo-qb.png"' in head, \
        "the header no longer wears the artwork"
    for f in (tab, "logo-qb.png"):
        assert os.path.isfile(os.path.join(ROOT, "web", f)), f"missing {f}"
    # Same picture in both, not just two files with the right names.
    assert "data:image/png;base64," in _read("web", tab), \
        "the tab icon is not the embedded artwork"


def test_the_tab_and_the_header_are_cut_from_one_source():
    """Same crop, two sizes. Compared as PIXELS rather than as file
    names, because two files can carry the right names and different
    artwork — which is exactly the drift the old geometry check caught
    when the mark was a shape."""
    import base64 as _b64
    import io as _io
    try:
        from PIL import Image
    except ImportError:                       # stdlib-only machines
        return
    svg = _read("web", "favicon.svg")
    raw = _b64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", svg).group(1))
    a = Image.open(_io.BytesIO(raw)).convert("RGB")
    b = Image.open(os.path.join(ROOT, "web", "logo-qb.png")).convert("RGB")
    a = a.resize((32, 32)); b = b.resize((32, 32))
    diff = sum(abs(x - y) for pa, pb in zip(a.getdata(), b.getdata())
               for x, y in zip(pa, pb)) / (32 * 32 * 3)
    assert diff < 12, (
        f"the tab icon and the header logo are different pictures "
        f"(mean channel difference {diff:.1f})")


def test_the_drawn_mark_is_no_longer_what_ships():
    """make_icon.py DRAWS a flat ellipse and is kept for its token
    reader, which two other test files import. Ethan, 2026-08-22: "Use
    the actual image, don't make your own." Nothing it draws may reach
    web/ again."""
    svg = _read("web", "favicon.svg")
    assert "<ellipse" not in svg, "the drawn ellipse is back in the tab icon"
    assert "data:image/png;base64," in svg


def test_the_crop_lands_in_the_empty_band_under_the_mark():
    """THE ASK, CHECKED AGAINST THE SOURCE. Ethan: "use that for the site
    logo but take away where it says qellys book below it" — the words
    already sit beside the logo in .brand-words, so an icon carrying them
    prints the name twice at two sizes.

    The cut is a constant (tools/appicons.sh owns it) and this is what
    makes that safe: rows 804-846 of the artwork carry no ink at all, so
    the crop's bottom edge has to fall inside that band. A box in a build
    script is a claim; this measures it.

    My first version of this measured the bottom of the SHIPPED mark and
    failed at peak 231 — which was the Q and the B, not the wordmark. It
    was checking the wrong picture."""
    try:
        from PIL import Image
    except ImportError:
        return
    sh = open(os.path.join(ROOT, "tools", "appicons.sh"),
              encoding="utf-8").read()
    m = re.search(r'QB_CROP="(\d+),(\d+),(\d+),(\d+)"', sh)
    assert m, "the crop is not recorded where the build script can use it"
    _, _, _, bottom = (int(g) for g in m.groups())
    im = Image.open(os.path.join(ROOT, "brand", "appicon-1254.png")).convert("L")
    w, h = im.size
    px = list(im.tobytes())
    band = range(int(w * .18), int(w * .82))
    row = lambda y: max(px[y * w + x] for x in band)
    assert row(bottom) < 40, (
        f"the crop's bottom edge (y={bottom}) cuts through ink (peak "
        f"{row(bottom)}) — it should land in the empty band under the QB")
    # …and it must not be so high that it clips the mark itself.
    assert row(bottom - 60) > 60, (
        "the crop stops well above the mark, so it is losing the QB")


def test_the_mark_is_the_artwork_and_not_a_drawing():
    """THREE TESTS RETIRED HERE 2026-08-23, together and on purpose:
    stroke width matching the rasteriser, "one unfilled stroke", and "the
    tile is square". Every one of them was a specification for the drawn
    ellipse — its outline, its lack of fill, its zero corner radius — and
    the mark is photographic gold leaf now with none of those properties.

    Keeping them by loosening each would have left three assertions that
    no longer describe anything. What replaces them is the property that
    matters at 16px: it is Ethan's file, embedded, and the ellipse the
    repo used to draw is gone from the shipped tree."""
    svg = _read("web", "favicon.svg")
    assert "data:image/png;base64," in svg
    assert "<ellipse" not in svg and "<circle" not in svg
    assert "stroke" not in svg, "a drawn stroke is back on the mark"
    # The tile IS rounded now, which the retired test forbade: it reads as
    # an app icon rather than a photo pasted into the bar, and the radius
    # is baked into the alpha rather than asserted in CSS.
    css = _read("web", "css", "styles.css")
    rule = css[css.index(".qmark {"):]
    assert "border-radius" in rule[:rule.index("}")]


def test_the_page_links_both_icons():
    html = _read("web", "index.html")
    assert 'rel="icon" href="favicon.svg"' in html
    assert 'rel="apple-touch-icon" href="apple-touch-icon.png"' in html
    assert os.path.isfile(os.path.join(WEB, "favicon.svg"))
    assert os.path.isfile(os.path.join(WEB, "apple-touch-icon.png"))


def test_icon_png_is_a_real_180px_png():
    with open(os.path.join(WEB, "apple-touch-icon.png"), "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    assert (width, height) == (180, 180), "iOS wants the 180pt icon"


def test_the_home_screen_icon_is_ethans_artwork_not_the_drawn_mark():
    """Ethan, 2026-08-22, with a render attached: "can you use this render
    for the app icon when we save it too our Home Screen for mobile. Use
    the actual image, don't make your own."

    THIS TEST USED TO ASSERT THE OPPOSITE — that the shipped PNG was
    byte-identical to `make_icon.render(180)`, which draws the flat Q in
    pure stdlib. That was the right guard while the icon WAS generated:
    it caught a hand-edited PNG as readily as a stale one. It is the
    wrong guard now, because the generator is no longer the source of
    truth and re-running it would quietly overwrite the artwork.

    So: the shipped icon must NOT be the drawn mark, and the artwork it
    came from has to be committed beside it. `make_icon.py` still works
    and still documents the mark; it just no longer decides what ships.
    """
    with open(os.path.join(WEB, "apple-touch-icon.png"), "rb") as fh:
        shipped = fh.read()
    assert shipped != make_icon.render(180), (
        "the drawn mark is back on the home screen — someone re-ran "
        "make_icon.py over the artwork")
    src = os.path.join(ROOT, "brand", "appicon-1254.png")
    assert os.path.isfile(src), (
        "the source artwork is not committed, so nothing can be "
        "regenerated from it")
    with open(src, "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(head[16:20], "big") >= 512, \
        "the source is smaller than the largest icon made from it"


def test_every_icon_the_manifest_names_exists_at_the_size_it_claims():
    """A manifest entry pointing at a missing file is an install prompt
    that silently offers no icon."""
    import json
    with open(os.path.join(WEB, "manifest.webmanifest"), encoding="utf-8") as fh:
        icons = json.load(fh)["icons"]
    assert icons, "the manifest lists no icons"
    for row in icons:
        path = os.path.join(WEB, row["src"])
        assert os.path.isfile(path), f"{row['src']} is missing"
        with open(path, "rb") as fh:
            head = fh.read(24)
        assert head[:8] == b"\x89PNG\r\n\x1a\n", row["src"]
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        assert f"{w}x{h}" == row["sizes"], \
            f"{row['src']} is {w}x{h}, the manifest says {row['sizes']}"


def test_the_maskable_icon_is_not_the_full_bleed_one():
    """Android crops a maskable icon to a circle and keeps the central
    80%. Pointing that at the full-bleed artwork loses the crown off the
    top and the word BOOK off the bottom — on the one icon the reader
    looks at every day."""
    import json
    with open(os.path.join(WEB, "manifest.webmanifest"), encoding="utf-8") as fh:
        icons = json.load(fh)["icons"]
    mask = [r for r in icons if r.get("purpose") == "maskable"]
    assert mask, "no maskable icon — Android will letterbox its own"
    plain = {r["src"] for r in icons if r.get("purpose") != "maskable"}
    for r in mask:
        assert r["src"] not in plain, (
            f"{r['src']} is served as both maskable and any — one of the "
            f"two is being cropped wrong")


def test_server_serves_icons_as_images():
    assert CONTENT_TYPES[".png"] == "image/png"
    assert CONTENT_TYPES[".svg"] == "image/svg+xml"


def test_favicon_ico_falls_back_to_the_svg():
    # Browsers probe /favicon.ico before parsing <link rel="icon">, so
    # without the alias every page load logs a meaningless 404.
    src = _read("server.py")
    assert '"/favicon.ico"' in src and '"/favicon.svg"' in src


def test_the_old_name_is_gone():
    # "Gridiron" is somebody else's trademark; it must not creep back in.
    # engine/sources/fetch.py matters most: its User-Agent is the name we
    # hand to every third-party API we call.
    for name in ("README.md", "GUIDE.md", "LAUNCH.md", "STRATEGY.md",
                 "server.py", "launch.py",
                 os.path.join("engine", "sources", "fetch.py"),
                 os.path.join("web", "index.html"),
                 os.path.join("web", "js", "app.js"),
                 os.path.join("docs", "PHONE.md")):
        assert "gridiron" not in _read(name).lower(), name


def test_the_name_is_spelled_the_same_everywhere():
    html = _read("web", "index.html")
    # NEW LOOK (2026-08-11): the wordmark is two words in one h1 — the
    # span carries the quieter BOOKS; CSS uppercases both. The spelling is
    # still typed exactly once and matches the title/og everywhere.
    #
    # SINGULAR SINCE 2026-08-22, on Ethan's instruction: "there should be
    # no s at the end of books, it should only be qellys book". It ran
    # plural for two days on an earlier instruction of his, so this
    # assertion has now caught the rename in BOTH directions — which is
    # exactly what it is for.
    #
    # It is caught HERE rather than by the `Qelly(?!s)` sweep below,
    # because markup splits the name. A search-and-replace over the
    # string cannot see `Qellys <span>Books</span>`, so the wordmark is
    # the one surface a rename leaves behind, every time, in either
    # direction. It also now matches the domain, which was always
    # qellysbook.com.
    assert "<h1>Qellys <span>Book</span></h1>" in html
    # And the plural must not survive anywhere in the shipped shell.
    assert "Qellys Books" not in html, \
        "a plural 'Qellys Books' survived the rename"
    assert "<title>Qellys Book" in html
    assert 'apple-mobile-web-app-title" content="Qellys Book"' in html
    # A bare "Qelly" anywhere means a rename only got half-applied.
    for name in ("README.md", "GUIDE.md", "LAUNCH.md", "STRATEGY.md",
                 "server.py", "launch.py",
                 os.path.join("web", "index.html"),
                 os.path.join("docs", "PHONE.md")):
        # NEW LOOK (2026-08-11): the wordmark splits across a span, the My
        # Bets copy says "a Qellys account", and the picks strip is
        # "Qellys' top picks" — the brand can stand alone now. What the
        # pin still catches: "Qelly" without the s (the typo it was born
        # for), and the canonical name drifting in title/og.
        assert not re.search(r"Qelly(?!s)", _read(name)), name


def test_the_mark_matches_the_design_system():
    """The favicon, the header tile and the home-screen icon are one
    brand or they are three. This fired for real when the accent moved
    off blue and the mark stayed behind — the tab would have been one
    colour and the site another."""
    # Flat panel, one accent, no gradient — the same chrome as everything
    # else. A gradient-filled tile reads as a sticker on a flat interface.
    svg = _read("web", "favicon.svg")
    assert "linearGradient" not in svg
    # RETIRED 2026-08-23 WITH THE DRAWN MARK. This resolved --panel-2 and
    # --gold through make_icon.token and asserted both hexes appeared in
    # the SVG, which is how you check a mark the repo draws from the
    # site's own tokens. The mark is Ethan's artwork now — gold leaf,
    # stadium light, a texture no token describes — so there is no hex to
    # match and matching one would mean the drawing had come back.
    #
    # The token discipline it protected has not gone anywhere; it moved
    # to the surfaces that are still drawn. tests/test_contrast.py and
    # tests/test_chroma.py both import make_icon.token and hold the whole
    # palette to it, which is why that reader is kept.
    svg = _read("web", "favicon.svg")
    assert "data:image/png;base64," in svg, (
        "the tab icon is a drawing again rather than the artwork")
    assert "#" not in svg.split("base64,")[0], (
        "a hardcoded colour crept back into the mark")


def test_brand_is_constant_across_sports():
    # The tile used to be the sport emoji, which resized the header on every
    # switch. Nothing may write to it from JS again.
    app = _read("web", "js", "app.js")
    assert "brand-logo" not in app
    assert "brand-sport" not in app



def test_the_masthead_is_set_in_the_display_face():
    """Brand identity, which is this file's job. Whether the weight it asks
    for is one the face actually SHIPS is checked in test_typography.py,
    which derives the allowed set from the @font-face declarations — this
    test used to duplicate that check against a hardcoded 400 and went
    stale the moment the family changed."""
    css = _read("web", "css", "styles.css")
    rule = css[css.index(".brand-words h1 {"):]
    rule = rule[:rule.index("}") + 1]
    assert "font-family: var(--font-display)" in rule, \
        "the masthead fell back to the body face"


def test_the_type_is_self_hosted():
    """Everything else on this site works with the network unplugged and
    the fonts have to as well — a board that renders in Times New Roman
    the one night the wifi drops is not a board you trust."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = _read("web", "css", "styles.css")
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css
    html = _read("web", "index.html")
    assert "fonts.googleapis.com" not in html
    # Named rather than counted, so dropping a family shows up here rather
    # than as a silent fallback to the platform's default serif.
    for f in ("archivo-narrow.woff2", "archivo-narrow-700.woff2",
              "bodoni-moda-700.woff2", "bodoni-moda-900.woff2",
              "plex-mono.woff2", "plex-mono-500.woff2", "plex-mono-600.woff2"):
        assert os.path.isfile(os.path.join(root, "web", "fonts", f)), f
        assert f in css, f"{f} is on disk but nothing loads it"
    assert "font-display: swap" in css, "text would be invisible while loading"


def test_numbers_are_tabular_everywhere():
    """Every figure sits in a column next to another figure. Proportional
    digits make those columns wobble as the numbers change, which on a
    board refreshing every minute reads as the page twitching."""
    css = _read("web", "css", "styles.css")
    body = css[css.index("body {"):]
    body = body[:body.index("}") + 1]
    assert "tabular-nums" in body

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
