"""Venue art cache-busting: a rebuilt render must not keep an old URL.

Ethan, 2026-08-16, at work: "the stadiums will show old renders of the
stadiums on some games and the new renders on the others" — on the site
AND on the phone.

Nothing was wrong with the files. `web/img/venues/variants/` holds one
generation and the per-team photo directories are empty, so every card
falls to a variant. The bug is that the variants were REBUILT three times
(the 4x cinematic upscale, the re-cut from the PNG original, the
colour-seam slicer) and every rebuild wrote the same filenames.
`baseball-blue.jpg` is a different picture than it was last week and its
URL never changed, so a browser holding the old bytes has no reason to
ask for them again.

That is also why it looked random rather than broken: which cards are
stale depends on which VARIANT each one uses and when that particular
file entered the cache. Two cards on one screen legitimately pull
different files, so one can be current and the other a week old.

These tests pin the property that fixes it — every venue URL carries the
version token — because the failure is invisible in development. A fresh
checkout has an empty cache and looks perfect no matter what the markup
says; only a browser that visited before the rebuild can see it, which
means code review is the only place it can be caught.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_every_venue_image_url_carries_the_version():
    """No raw `img/venues/....jpg` may reach an src or data-alt.

    The scan is deliberately over the whole file rather than over the
    three call sites known today: the next venue image someone adds is
    exactly the one that will be forgotten, and it will look fine on
    their machine.
    """
    # Matches a venue path inside an attribute — the places a browser
    # actually fetches from. Prose and comments naming the path are fine.
    bad = []
    for m in re.finditer(r'(src|data-alt)\s*=\s*"([^"]*img/venues/[^"]*)"', APP):
        url = m.group(2)
        if "venueSrc(" not in url and "?v=" not in url:
            bad.append(url)
    assert not bad, (
        "venue image URLs with no cache-busting version — a rebuilt render "
        "will not reach anyone who visited before it: " + "; ".join(bad))


def test_the_version_token_is_a_single_named_constant():
    """One knob, so a rebuild is one edit and cannot half-land."""
    assert re.search(r'const VENUE_ART_V = "[^"]+";', APP)
    assert "const venueSrc = (path) =>" in APP
    # And it is actually used, not merely defined.
    assert APP.count("venueSrc(") >= 4


def test_the_constant_says_when_to_bump_it():
    """A cache-busting token nobody knows to change is worse than none —
    it reads as solved while the next rebuild reintroduces the bug."""
    i = APP.index("const VENUE_ART_V")
    note = APP[max(0, i - 2000):i]
    assert "BUMP IT WHENEVER THE RENDERS ARE REBUILT" in note
    assert "venues_ingest" in note


def test_the_fallback_hop_keeps_the_version():
    """`vpFall` swaps src for data-alt when a team photo is missing. If
    the alt were unversioned the fallback — which is what MOST cards use,
    since the per-team photo directories are empty — would be the stale
    one, and the fix would appear to work on the few teams with photos."""
    m = re.search(r"window\.vpFall = \(el\) => \{.*?\};", APP, re.S)
    assert m, "vpFall not found"
    # It copies data-alt verbatim, so the guarantee has to hold at the
    # point the attribute is written. Assert that, not the copy.
    for m2 in re.finditer(r'data-alt="([^"]*)"', APP):
        if "img/venues/" in m2.group(1):
            assert "venueSrc(" in m2.group(1), m2.group(1)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
