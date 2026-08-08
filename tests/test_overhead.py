"""The Overhead — the venue diagram, and the grammar it is not allowed to drift out of.

The Overhead is the site's distinctive asset: a plan view of where the game
is played, engraved, with the conditions a price was set in drawn around
it. `docs/THE_OVERHEAD.md` is the constitution; this file is the part of it
a machine can enforce.

The bug that prompted these tests is the one worth understanding, because
it is silent and it will happen again.

The engraving is applied from the STYLESHEET, not by rewriting the drawing
code. SVG presentation attributes (`fill="#2a9d54"` written on the element)
sit at the very bottom of the cascade, so any CSS rule beats them — which
means the art can be re-skinned without touching three drawing functions
and risking a dropped label. That is a good decision and it stays.

Its failure mode is that the re-skin is only as complete as its selector
list. Night Form shipped `.field path` and no `.stadium path`. `court()`
is a `.field`, so it was fine. `stadium()` happens to draw its bowl out of
`<line>`, `<ellipse>` and `<rect>`, so it was fine BY ACCIDENT.
`ballpark()` draws its stands, outfield fan, wall, infield and plate as
thirteen `<path>` elements — and every one of them kept its green.

So the MLB board, the one with the most history and the one that opens
first, rendered the pre-redesign colour cartoon for the entire life of the
redesign, and nothing failed. Two renderers out of three followed the
grammar and the third looked fine to every test we had.

The guard below is therefore not "does the path rule exist" (too narrow —
it would pass again the next time someone adds a `<polygon>`). It is:
**every element type a renderer actually emits must be matched by a rule
in the engraving block for that renderer's class.**
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(css):
    """CSS without /* */ — these rules carry long notes that quote the very
    strings the assertions look for."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _engraving_block(css):
    """The `Venue art — engraving` section of the stylesheet."""
    start = css.index("Venue art — engraving")
    end = css.index("The wind gauge, engraved", start)
    return _strip_comments(css[start:end])


def _fn_body(js, name):
    """One renderer's source, from `function name(` to the next top-level
    `function` or comment banner."""
    i = js.index(f"function {name}(")
    nxt = js.find("\nfunction ", i + 1)
    ban = js.find("\n/* ----", i + 1)
    ends = [x for x in (nxt, ban) if x > 0]
    return js[i:min(ends)] if ends else js[i:]


# Every renderer, and the class each one puts on its <svg>.
#
# `octagon` and `marketRule` are the answer to the question §4 of the
# constitution used to leave open: what the Overhead is for a sport with no
# building. UFC turned out to HAVE one — the promotion's own facility uses
# a 25-foot cage and arenas use 30, a difference the model already prices —
# so it gets a venue drawing like everyone else. Prediction markets have no
# room at all, so the space a price is set in is the probability line, and
# that is what gets drawn.
#
# They are in this dict so the coverage test below governs them too. A new
# Overhead that is not listed here is a drawing nothing checks.
RENDERERS = {"stadium": "stadium", "ballpark": "stadium", "court": "field",
             "octagon": "stadium", "marketRule": "stadium"}

# Emitted by every renderer but deliberately unstyled by the engraving
# layer: <defs> and its gradient children paint nothing once fills are
# removed, and <g> is a grouping element with no surface of its own.
NOT_PAINTED = {"defs", "radialGradient", "linearGradient", "stop", "g", "svg"}


def _emitted(js, fn):
    body = _fn_body(js, fn)
    tags = set(re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)\b", body))
    return {t for t in tags if t not in NOT_PAINTED}


def _selectors(block):
    """Every individual selector in the block, comma-split and normalised."""
    out = []
    for prelude in re.findall(r"([^{}]+)\{", block):
        for sel in prelude.split(","):
            sel = " ".join(sel.split())
            if sel:
                out.append(sel)
    return out


# `.cls tag` or `.cls > tag`, optionally with trailing pseudo-classes.
# Deliberately strict: it must be the BARE element under the class.
#
# The loose version of this check passed while the bug was present, which
# is the worst outcome a test can have. `.stadium g[stroke] path` and
# `.stadium path.mow` both contain ".stadium" and "path", so a substring
# search called <path> covered when the only rules touching it were one
# scoped to an attribute-qualified ancestor and one that hides five
# decorative wedges. Neither re-skins the thirteen paths that matter.
def _covers(selectors, cls, tag):
    pat = re.compile(rf"^\.{cls}\s*>?\s*{tag}(:[a-zA-Z-]+(\([^)]*\))?)*$")
    return any(pat.match(s) for s in selectors)


def test_the_ground_rule_covers_every_renderer():
    """WHAT REPLACED THE COVERAGE GUARD, and why the replacement is
    narrower on purpose.

    This file used to assert that EVERY element type a renderer emits is
    matched by a rule in the engraving block — because the block's job was
    to strip every presentation-attribute fill, and it was only as complete
    as its selector list. `ballpark()` draws thirteen `<path>`s, Night Form
    shipped `.field path` and no `.stadium path`, and the MLB board rendered
    the pre-redesign colour cartoon for the entire life of the redesign
    while every test passed.

    Ethan put the colour back on 2026-08-08, so stripping fills is no
    longer the block's job and that invariant is false by design — the
    greens and browns are now the point. Deleting the file would throw away
    the lesson with the rule, so what survives is the part that is still
    load-bearing: the art sits on the PAGE'S ground, not on its own navy
    sky. Rendered without this, the venues read as three cards pasted in
    from a different website.

    Still keyed off what the renderers actually emit rather than a literal
    selector, so it cannot be satisfied by a rule that matches nothing.
    """
    js = _read("web", "js", "visuals.js")
    sels = _selectors(_engraving_block(_read("web", "css", "styles.css")))
    missing = []
    for fn, cls in RENDERERS.items():
        if "rect" not in _emitted(js, fn):
            continue                     # nothing to stand on
        if not _covers(sels, cls, "rect"):
            missing.append(f"{fn}() draws its ground as <rect> but no "
                           f"`.{cls} rect` rule flattens it")
    assert not missing, "\n  ".join(missing)


def test_the_sky_wash_is_still_flattened_to_the_page_ground():
    """The one rule the whole treatment rests on. `visuals.js` paints a
    radial navy gradient behind every venue; on a near-black page that is a
    second background showing through."""
    block = _engraving_block(_read("web", "css", "styles.css"))
    m = re.search(r"\.stadium > rect:first-of-type,\s*"
                  r"\.field > rect:first-of-type\s*\{([^}]*)\}", block)
    assert m, "the sky wash is no longer flattened to the page's ground"
    assert "var(--bg-2)" in m.group(1), m.group(1)


def test_the_labels_survive_a_coloured_surface():
    """`--text-dim` was chosen when the ground under every label was flat
    and identical. With the colour back, the same label sits on Vikings
    purple or Marlins teal — "MIN" across a purple dome vanished outright
    in the first render.

    A ground-coloured outline under the glyphs fixes it once for every
    surface without asking what is underneath, and inverts with the theme
    for free because both ends are tokens. The alternative — restoring the
    old per-team ideal-contrast fill — brings back a third type system on
    the card."""
    block = _engraving_block(_read("web", "css", "styles.css"))
    m = re.search(r"\.stadium text, \.field text\s*\{([^}]*)\}", block)
    assert m, "the art's labels are no longer styled at all"
    body = m.group(1)
    assert "paint-order" in body, "no halo — labels will drop out on colour"
    assert "var(--bg-2)" in body, "the halo must be the page's own ground"
    assert "var(--font-mono)" in body, "the art's type system drifted"


def test_the_art_has_no_rounded_corners():
    """Zero radius is a house rule everywhere else in Night Form. The art
    was the last place still drawing rx (rx="6" on the football field and
    end zones, rx="7.5" on the plaques)."""
    block = _engraving_block(_read("web", "css", "styles.css"))
    assert re.search(r"rx:\s*0", block), (
        "nothing zeroes `rx` in the engraving block; an rx written on the "
        "element survives, and `rx` is a CSS geometry property, which is "
        "the only way to unset it without editing the drawing code"
    )


def test_the_mow_stripes_keep_their_class_even_though_they_are_visible_again():
    """They were hidden for a reason that no longer applies. Filled at 18%
    they read as faint stripes; ENGRAVED, each wedge becomes an arc plus
    two radii, and five of those radiating from the plate is a cat's cradle
    over the infield. Outlining is what made them unreadable, not the
    stripes themselves — so with the fills back on (2026-08-08) they return
    to what they always were.

    The CLASS still has to be there. It is the only handle anything has on
    them, it costs nothing, and the day someone wants a line-art variant
    again it is the difference between one CSS rule and re-reading a
    drawing function.
    """
    js = _read("web", "js", "visuals.js")
    assert 'class="mow"' in _fn_body(js, "ballpark"), (
        "the ballpark's mow stripes lost their class — the one handle any "
        "future re-skin has on them"
    )
    block = _engraving_block(_read("web", "css", "styles.css"))
    assert not re.search(r"\.stadium path\.mow\s*\{[^}]*display:\s*none", block), (
        "the mow stripes are hidden again while the art is in colour, "
        "which drops texture for a reason that only applied to outlines"
    )


def test_every_renderer_shares_one_canvas():
    """LOCKED, per the constitution. The Overhead is one asset with three
    drawings, not three diagrams that happen to sit near each other — if
    the viewBox drifts, so does line weight relative to everything else."""
    js = _read("web", "js", "visuals.js")
    for fn in RENDERERS:
        body = _fn_body(js, fn)
        assert "240 150" in body or "0 0 ${w} ${h}" in body, (
            f"{fn}() left the shared 240x150 canvas"
        )
        assert 'preserveAspectRatio="xMidYMid meet"' in body, (
            f"{fn}() must keep the shared aspect-ratio contract"
        )


def test_the_constitution_exists_and_names_the_asset():
    """A distinctive asset that is not written down is a style, and a style
    drifts. The name is the thing that makes repetition possible — you
    cannot repeat what you have no word for."""
    doc = _read("docs", "THE_OVERHEAD.md")
    assert "the Overhead" in doc
    for section in ("What is LOCKED", "What VARIES"):
        assert section in doc, f"the constitution lost its `{section}` section"
    # The rule that covers every sport, including the ones with no room.
    assert "Draw the space a price is set in" in doc, (
        "the constitution lost the one line that decides what an Overhead "
        "is for a market with no building"
    )
    # And the next gap has to stay visible the way the last one did.
    assert "Still open" in doc, (
        "an asset with nothing open is an asset nobody is looking at; the "
        "surfaces the Overhead is not on yet belong in this file"
    )


def test_the_cage_is_drawn_to_scale():
    """The whole reason UFC gets a venue drawing rather than an exemption.

    A 25-foot cage and a 30-foot cage have to be visibly different sizes,
    or the octagon is decoration — a constant shape carrying no data, which
    is what this was first assumed to be. The model prices the difference;
    the drawing has to show it.
    """
    js = _read("web", "js", "visuals.js")
    body = _fn_body(js, "octagon")
    assert "CAGE_R" in body, "the octagon must size itself from the cage"
    m = re.search(r"CAGE_R\s*=\s*\{([^}]*)\}", js)
    assert m, "no CAGE_R table"
    radii = dict(re.findall(r"(\d+)\s*:\s*(\d+)", m.group(1)))
    assert set(radii) == {"25", "30"}, "the two real cage sizes, per environment.py"
    assert int(radii["25"]) < int(radii["30"]), (
        "the small cage must draw smaller — otherwise the drawing says the "
        "two venues are the same and the model says they are not"
    )


def test_the_market_rule_stays_clear_of_the_locked_corners():
    """The plaques own y=128 in every Overhead and that is locked.

    The first layout put the probability axis on y=118 with its numbers on
    y=133, which ran the scale straight through both plaques.
    """
    js = _read("web", "js", "visuals.js")
    body = _fn_body(js, "marketRule")
    m = re.search(r"AXIS\s*=\s*(\d+)", body)
    assert m, "marketRule must name its axis position"
    axis = int(m.group(1))
    assert axis + 13 < 128, (
        f"the axis at y={axis} puts its labels at y={axis + 13}, on top of "
        "the plaques at y=128"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
