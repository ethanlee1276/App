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
    assert _mark_geometry(_read("web", "favicon.svg")) \
        == _mark_geometry(_read("web", "index.html")), \
        "bowl geometry drifted apart between the tab and the page"


def test_raster_icon_matches_the_svg():
    cx, cy, rx, ry = _mark_geometry(_read("web", "favicon.svg"))
    assert (cx, cy) == (make_icon.CX, make_icon.CY)
    assert (rx, ry) == (make_icon.RX, make_icon.RY)
    assert make_icon.NUDGE == (0.0, 0.0), \
        "an ellipse centred in its own box needs no optical nudge"


def test_stroke_width_matches_the_rasteriser():
    svg = _read("web", "favicon.svg")
    width = float(re.search(r'stroke-width="([\d.]+)"', svg).group(1))
    css = _read("web", "css", "styles.css")
    css_width = float(re.search(r"\.qmark\s*\{[^}]*stroke-width:\s*([\d.]+)",
                                css, re.S).group(1))
    assert width == css_width == make_icon.HALF * 2


def test_the_mark_is_one_unfilled_stroke():
    """The bowl is an outline. A fill turns it into a lozenge, and a second
    shape turns the logo into an illustration — the whole point of §6.1 is
    that the mark IS the venue system at its smallest scale, and at 16px
    only the silhouette survives anyway."""
    svg = _read("web", "favicon.svg")
    assert svg.count("<ellipse") == 1, "the mark grew a second shape"
    assert 'fill="none"' in svg
    assert "<path" not in svg and "<circle" not in svg, "the Q's tail is back"


def test_the_tile_is_square():
    """Radius 0 everywhere, spec §3.3 — including the icon, which is the
    one surface a rounded corner survives on by being baked into a PNG."""
    # Scoped to the RECT. `rx=` also appears on the ellipse itself, where it
    # is a radius and not a corner — the first version of this assertion
    # failed on the mark it was meant to protect.
    rect = re.search(r"<rect[^>]*/>", _read("web", "favicon.svg")).group(0)
    assert "rx=" not in rect, "the tile is rounded again"
    assert make_icon.CORNER == 0.0


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


def test_rendered_icon_is_byte_identical_to_the_committed_one():
    # Catches a hand-edited PNG as readily as a stale one.
    with open(os.path.join(WEB, "apple-touch-icon.png"), "rb") as fh:
        assert fh.read() == make_icon.render(180), "run: python3 make_icon.py"


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
    assert "<h1>Qellys Book</h1>" in html
    assert "<title>Qellys Book" in html
    assert 'apple-mobile-web-app-title" content="Qellys Book"' in html
    # A bare "Qelly" anywhere means a rename only got half-applied.
    for name in ("README.md", "GUIDE.md", "LAUNCH.md", "STRATEGY.md",
                 "server.py", "launch.py",
                 os.path.join("web", "index.html"),
                 os.path.join("docs", "PHONE.md")):
        assert not re.search(r"Qelly(?!s Book)", _read(name)), name


def test_the_mark_matches_the_design_system():
    """The favicon, the header tile and the home-screen icon are one
    brand or they are three. This fired for real when the accent moved
    off blue and the mark stayed behind — the tab would have been one
    colour and the site another."""
    # Flat panel, one accent, no gradient — the same chrome as everything
    # else. A gradient-filled tile reads as a sticker on a flat interface.
    svg = _read("web", "favicon.svg")
    assert "linearGradient" not in svg
    css = _read("web", "css", "styles.css")
    panel_2 = re.search(r"--panel-2:\s*(#[0-9a-fA-F]{6})", css).group(1)
    brand = re.search(r"--brand:\s*(#[0-9a-fA-F]{6})", css).group(1)
    assert panel_2.lower() in svg.lower(), "tile drifted off --panel-2"
    assert brand.lower() in svg.lower(), "stroke drifted off --brand"
    assert make_icon.INK == tuple(int(brand[i:i + 2], 16) for i in (1, 3, 5))
    assert make_icon.TOP == make_icon.BOT, "the tile must stay flat"


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
    rule = css[css.index(".brand h1 {"):]
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
