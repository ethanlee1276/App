"""Venue art cache-busting: a rebuilt render must not keep an old URL.

Ethan, 2026-08-16, at work: "the stadiums will show old renders of the
stadiums on some games and the new renders on the others" — on the site
AND on the phone.

TWO BUGS WERE HERE, AND THE FIRST DIAGNOSIS ONLY FOUND THE SMALLER ONE.

The stale-cache one is real: the variants were rebuilt three times (the
4x cinematic upscale, the re-cut from the PNG original, the colour-seam
slicer) and every rebuild wrote the SAME filenames, so a browser holding
the old bytes had no reason to ask again. The version token fixes it, and
the first half of this file pins it.

But Ethan hard-refreshed and reported back: "the stadium issue is not
fixed." The bigger cause was in the files all along. `variants/` holds
TWO GENERATIONS — the three `*-steel.jpg` are the full 1536x1024 neutral
renders from the 2026-08-11 batch, and the fifteen colour files are TILES
CUT OUT OF a five-colour sheet, ~1000-1500px and visibly softer. The
picker chooses between them from the home team's kit, so which cards look
old is deterministic and permanent. That is what "some games old, some
new" actually was, and no cache token could ever have touched it.

Both failures are invisible in development, which is why they are pinned
here rather than trusted to a look: a fresh checkout has an empty cache,
and a developer who never sets two differently-kitted teams side by side
sees nothing wrong. Code review is the only place either one is catchable.
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


def test_only_one_generation_of_venue_art_can_reach_a_card():
    """Ethan, 2026-08-13, after the cache-bust shipped: "the stadium issue
    is not fixed."

    He was right, and the first diagnosis was wrong. `variants/` holds TWO
    generations: the three `*-steel.jpg` are full 1536x1024 neutral
    renders, and the fifteen colour files are tiles cut out of a colour
    sheet at ~1000-1500px, visibly softer and more heavily tinted. The
    picker chooses between them from the home team's kit, so which cards
    look old is DETERMINISTIC — which is why no amount of refreshing ever
    fixed it, and why it reads as "some games" rather than "the site".

    The colour rule stays; only the slots with matched art are served.
    """
    assert "VENUE_MATCHED" in APP
    m = re.search(r"const VENUE_MATCHED = new Set\(\[([^\]]*)\]\)", APP)
    assert m, "the matched-art set must be one named, greppable constant"
    slots = {x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()}
    assert slots, "an empty set would serve nothing"
    # Every slot named here must be backed by a file that exists, or the
    # gate hands out 404s instead of pictures.
    variants = os.path.join(ROOT, "web", "img", "venues", "variants")
    have = set(os.listdir(variants)) if os.path.isdir(variants) else set()
    for slot in slots:
        for fam in ("football", "baseball", "basketball"):
            assert f"{fam}-{slot}.jpg" in have, f"{fam}-{slot}.jpg is missing"
    # And the colour rule itself must survive — deleting it would make
    # restoring the colours a rewrite instead of a one-line revert.
    assert "VENUE_MATCHED.has(best)" in APP
    for colour in ("red", "gold", "green", "blue", "violet"):
        assert f'"{colour}"' in APP, f"the {colour} rung was deleted, not gated"


def test_a_live_game_shows_the_same_art_as_every_other_card():
    """Ethan reported "the stadium issue" THREE times. This was the cause
    the first two fixes could not reach.

    Live cards suppressed the photo entirely — `!isLive ? <img> : ""` —
    and drew the SVG ballpark instead, because the drawing lights the
    occupied bases and the status line below it had been changed to stop
    repeating them. So one card on the strip was a flat vector diagram
    beside photoreal stadiums, permanently, on every slate with a live
    game. That is a much bigger visual break than either the stale cache
    or the mixed generations, and it is the one his screenshot showed.

    Photo everywhere now, runners overlaid — his call, and the overlay is
    what makes it cost nothing.
    """
    assert "!isLive ? (() => {" not in APP, "live cards must not suppress the photo"
    assert "mlb && isLive ? runnerOverlay(g)" in APP


def test_the_runner_overlay_does_not_rest_on_colour_alone():
    """An occupied base is a FILLED bag, an empty one a hollow outline —
    a shape difference, not a hue difference — and the whole base state is
    stated in words for anything that reads neither."""
    vis = open(os.path.join(ROOT, "web", "js", "visuals.js"),
               encoding="utf-8").read()
    fn = vis[vis.index("function runnerOverlay"):vis.index("function ballpark")]
    assert 'fill="none"' in fn, "an empty base must be an outline, not a colour"
    assert 'class="on-base"' in fn, "an occupied base must be a filled bag"
    assert "runnerLabel(runners)" in fn, "the base state must be stated in words"
    # The class exists because `.stadium g rect { fill: none }` hollows out
    # every rect in the art and beats a presentation attribute — the exact
    # trap the drawn version paid for and documented.
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".venue-runners .on-base { fill:" in css


def test_the_overlay_does_not_land_on_top_of_another_chip():
    """Five things already sit on this art. Adding a sixth that overlaps
    one of them trades a visual bug for a visual bug.

    The map, measured rather than assumed:

        .status-badge    top-left        (LIVE / FINAL)
        .game-time-chip  top-left        (non-live only)
        .top-game-tag    top-right       (non-live only)
        .game-wx-chip    BOTTOM-LEFT     (non-live only)
        .gc-picks        bottom-CENTRE

    Bottom-left is shared with the weather chip, and that is SAFE for
    exactly one reason: the weather chip renders only when the game is
    not live and the overlay renders only when it is, so the two can
    never be on one card. That invariant is the whole reason the corner
    is free, so it is asserted rather than trusted — showing weather on a
    live card later would silently stack them.
    """
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    m = re.search(r"\.venue-runners \{([^}]*)\}", css)
    assert m, "the overlay must be positioned explicitly"
    assert "left" in m.group(1) and "bottom" in m.group(1), m.group(1)
    # The overlay is live-only.
    assert "mlb && isLive ? runnerOverlay(g)" in APP
    # The weather chip — the other bottom-left occupant — is not.
    i = APP.index("game-wx-chip")
    assert "!isLive && !isFinal" in APP[max(0, i - 400):i], \
        "the weather chip reached a live card — it now stacks on the runners"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
