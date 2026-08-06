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


# The three renderers, and the class each one puts on its <svg>.
RENDERERS = {"stadium": "stadium", "ballpark": "stadium", "court": "field"}

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


def test_every_shape_a_renderer_draws_is_re_skinned():
    """The real guard. Not "does the path rule exist" — that is the last
    bug, and it would pass again the next time a `<polygon>` appears.

    For each renderer: every element type it emits must be named in a
    selector under that renderer's class, in the engraving block. If
    someone adds a shape and forgets the rule, the art quietly keeps its
    presentation-attribute colour on that sport only, which is exactly how
    the ballpark stayed green through an entire redesign.
    """
    js = _read("web", "js", "visuals.js")
    sels = _selectors(_engraving_block(_read("web", "css", "styles.css")))
    missing = []
    for fn, cls in RENDERERS.items():
        for tag in sorted(_emitted(js, fn)):
            if not _covers(sels, cls, tag):
                missing.append(f"{fn}() emits <{tag}> but no `.{cls} {tag}` rule")
    assert not missing, (
        "the engraving layer does not cover every shape these renderers "
        "draw, so the un-covered ones keep the raw fills written on the "
        "element:\n  " + "\n  ".join(missing)
    )


def test_the_ballpark_paths_are_outlined():
    """The specific regression. `ballpark()` is 13 paths; without this rule
    the stands, outfield fan, wall, infield dirt, infield grass and plate
    all keep the greens and browns out of visuals.js."""
    block = _engraving_block(_read("web", "css", "styles.css"))
    m = re.search(r"\.stadium path\s*\{([^}]*)\}", block)
    assert m, (
        "`.stadium path` is gone. `ballpark()` draws its whole body in "
        "<path>, so without it the MLB board renders the pre-redesign "
        "colour cartoon and nothing else fails."
    )
    assert "fill: none" in m.group(1), (
        "`.stadium path` must clear the fill — that is the entire point; "
        "the greens are written on the elements as presentation attributes"
    )


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


def test_the_mow_stripes_are_classed_and_dropped():
    """Filled at 18% they read as faint stripes. Engraved, each wedge is an
    arc plus two radii — five of those radiating from the plate is a cat's
    cradle over the infield. They carry no data, so they go. The football
    field's stripes survive because they are rectangles, which outline into
    parallel lines."""
    js = _read("web", "js", "visuals.js")
    assert 'class="mow"' in _fn_body(js, "ballpark"), (
        "the ballpark's mow stripes need a class so the engraving layer can "
        "drop them; without it they outline into a tangle"
    )
    block = _engraving_block(_read("web", "css", "styles.css"))
    assert re.search(r"\.stadium path\.mow\s*\{[^}]*display:\s*none", block)


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
    # The open question must stay open and visible, not get quietly closed.
    assert "UFC, Polymarket and Kalshi have no" in doc, (
        "the three sports with no venue are the unresolved part of this "
        "asset; if that line goes, the gap has been forgotten rather than "
        "solved"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
