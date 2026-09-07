#!/usr/bin/env python3
"""Render web/og-card.html to the PNG every shared link shows.

    python3 tools/ogcard.py

WHY THIS IS A SCRIPT AND NOT A COMMENT. The regeneration steps used to
live in an HTML comment at the top of og-card.html — start a file server
on some port, write a Node one-liner, screenshot, remember the size. Four
manual steps run maybe twice a year is four chances to render the card at
the wrong viewport, or against a stale server, and nobody notices because
the only place the mistake shows up is inside somebody else's text
message. `tools/appicons.sh` exists for the same reason and the icons have
not drifted since.

WHAT IT GUARANTEES, checked rather than assumed:

  * 1200x630, the frame every scraper crops to (X, Facebook, LinkedIn,
    Discord, iMessage), read back out of the file it just wrote;
  * nothing overflows the frame. A fixed-size card silently CROPS — a
    grid column whose default min-width is `auto` grew past the right
    edge once and the render simply came back missing its artwork, with
    no error anywhere;
  * the page raised no script error, because the Overhead is drawn by
    js/visuals.js at load and a throw there produces an empty panel that
    looks like a design choice.

It renders through server.py, the real handler, for the same reason
rendercheck does: the card pulls the real stylesheet, the real vendored
fonts and the real Overhead, so a preview cannot drift from the site.
"""

from __future__ import annotations

import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Versioned on purpose. Scrapers cache a preview image by URL and hold it
#: for a long time — iMessage and Discord especially — so a redesign
#: written back to the same filename keeps showing the OLD card to
#: everybody who has already shared the link, and to plenty who have not.
#: A new name is the only refresh that works everywhere on the first try.
#: Bump the suffix on any change to the artwork, and update the two
#: <meta> tags in web/index.html with it.
OUT = os.path.join("web", "og-card-v2.png")
SIZE = (1200, 630)

CHROMIUM = os.environ.get(
    "CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def render(out_path: str = OUT) -> str:
    import rendercheck
    from playwright.sync_api import sync_playwright

    srv, port = rendercheck._serve()
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage",
                           "--disable-gpu"]}
            if os.path.exists(CHROMIUM):
                kw["executable_path"] = CHROMIUM
            browser = pw.chromium.launch(**kw)
            page = browser.new_page(
                viewport={"width": SIZE[0], "height": SIZE[1]},
                device_scale_factor=1)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/og-card.html",
                      wait_until="load")
            # The Overhead is drawn from a script at the end of the body,
            # and the vendored faces have to land before anything is
            # measured. Neither is a network wait this server can signal.
            page.wait_for_timeout(900)
            over = page.evaluate(
                "() => [document.documentElement.scrollWidth,"
                " document.documentElement.scrollHeight]")
            page.screenshot(path=os.path.join(ROOT, out_path))
            browser.close()
    finally:
        srv.shutdown()

    if errors:
        raise SystemExit("the card raised a script error, so the Overhead "
                         "may be missing:\n  " + "\n  ".join(errors))
    if tuple(over) != SIZE:
        raise SystemExit(
            f"content overflows the card: the page lays out {over[0]}x"
            f"{over[1]} inside a {SIZE[0]}x{SIZE[1]} frame, so the render "
            "is cropped. Check for a grid column without min-width: 0.")

    full = os.path.join(ROOT, out_path)
    with open(full, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("that is not a PNG")
    w, h = struct.unpack(">II", head[16:24])
    if (w, h) != SIZE:
        raise SystemExit(f"wrote {w}x{h}, wanted {SIZE[0]}x{SIZE[1]}")
    return full


if __name__ == "__main__":
    path = render()
    print(f"wrote {os.path.relpath(path, ROOT)} "
          f"({os.path.getsize(path) // 1024} KB, {SIZE[0]}x{SIZE[1]})")
    print("If the artwork changed, bump OUT here and the og:image / "
          "twitter:image tags in web/index.html — scrapers cache the old "
          "one by URL.")
