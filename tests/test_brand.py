"""The Qelly brand mark has to stay one mark.

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
    """The <g> that holds the ring and the tail, numbers only."""
    m = re.search(r"<g[^>]*transform=\"translate\(([^)]*)\)\"[^>]*>(.*?)</g>",
                  svg_text, re.S)
    assert m, "no transformed <g> holding the mark"
    return _numbers(m.group(1)), _numbers(m.group(2))


def test_favicon_and_header_draw_the_same_q():
    fav_nudge, fav_paths = _mark_geometry(_read("web", "favicon.svg"))
    page_nudge, page_paths = _mark_geometry(_read("web", "index.html"))
    assert fav_nudge == page_nudge, "optical-centring nudge drifted apart"
    assert fav_paths == page_paths, "ring/tail geometry drifted apart"


def test_raster_icon_matches_the_svg():
    # favicon.svg: translate(x y), circle cx cy r, then the tail's two points.
    nudge, paths = _mark_geometry(_read("web", "favicon.svg"))
    cx, cy, r, ax, ay, bx, by = paths
    assert tuple(nudge) == make_icon.NUDGE
    assert (cx, cy, r) == (make_icon.CX, make_icon.CY, make_icon.R)
    assert (ax, ay) == make_icon.TAIL_A
    assert (bx, by) == make_icon.TAIL_B


def test_stroke_width_matches_the_rasteriser():
    svg = _read("web", "favicon.svg")
    width = float(re.search(r'stroke-width="([\d.]+)"', svg).group(1))
    css = _read("web", "css", "styles.css")
    css_width = float(re.search(r"\.qmark\s*\{[^}]*stroke-width:\s*([\d.]+)",
                                css, re.S).group(1))
    assert width == css_width == make_icon.HALF * 2


def test_tail_cap_is_flat_everywhere():
    # A round cap bulges into the counter and the Q reads as a magnifying
    # glass. Neither the SVGs nor the CSS may ask for one.
    assert "stroke-linecap" not in _read("web", "favicon.svg")
    css = _read("web", "css", "styles.css")
    qmark = re.search(r"\.qmark\s*\{([^}]*)\}", css, re.S).group(1)
    assert "linecap" not in qmark


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


def test_brand_is_constant_across_sports():
    # The tile used to be the sport emoji, which resized the header on every
    # switch. Nothing may write to it from JS again.
    app = _read("web", "js", "app.js")
    assert "brand-logo" not in app
    assert "brand-sport" not in app


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
