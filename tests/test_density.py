"""Density contrast inside a card — design queue item 3.

A card is not a list of facts. It exists to answer one question, and the
number that answers it should be the number you see first. These cards
presented three numbers in three identical boxes and left the eye to pick.

The useful finding is that the site had ALREADY chosen the hero on every
card type — and said so with a border:

    prop card    HIT PROB · [EDGE] · EV / UNIT
    game bet     MODEL · BOOK IMPLIED · [EDGE]
    wallet flag  POSITION · ENTRY · [NOW]
    long shot    MODEL · BOOK IMPLIED · [EDGE] · RZ CHANCES
    fantasy      ACTUAL · XFP SAYS · [GAP]

So the item was not "pick the number". It was "say it with type instead of
a box", which is what the queue item asks for in as many words: size,
weight and colour, not borders.

Measured over 358 metric rows (8 sports x 10 views x 2 widths):

    hero size / supporting size   1.09x  ->  1.47x
    rows under 1.2x               100%   ->  0%
    hero colour distinct          314/348 -> 358/358
    emphasis carried by a box     348/348 -> 0/358

The 1.09x is the whole story of why this was invisible in review. The rule
said `font-size: 1.24em`, which reads like "24% bigger than the numbers
beside it" — but `em` on font-size resolves against the PARENT, and the
parent is `.metric` at the card's 15px, not the 17px the siblings are set
in. It rendered at 18.6px. Nobody sees 1.6px; everybody sees the box.

Weight is deliberately NOT one of the levers. These numbers are set in the
mono face, which ships 400 and 500 only, so asking for 800 gets a
synthesised smear. Size and colour do the work.

Still true and deliberately left: the hero does not outrank the card's
TITLE (the player or team name, 17px/800). 30px was tried and screenshotted
— the hero then fills its tile edge to edge while the supporting tiles go
mostly empty, and the row reads lopsided rather than ordered. Whether the
number should lead the whole card is a composition question, and
composition is queue item 4.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


CSS = _read("web", "css", "styles.css")
APP = _read("web", "js", "app.js")


def _strip_comments(src):
    return re.sub(r"/\*.*?\*/", " ", src, flags=re.S)


def _rule(selector, css=None):
    """The declaration block for an exact selector, comments stripped."""
    body = _strip_comments(css if css is not None else CSS)
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", body)
    assert m, f"no rule for {selector}"
    return m.group(1)


def _step(decl):
    """The pixel value behind a `font-size: var(--fs-N)` declaration."""
    m = re.search(r"font-size:\s*var\(--fs-([0-9a-z]+)\)", decl)
    assert m, f"not a ramp token: {decl.strip()[:60]}"
    return float(re.search(rf"--fs-{m.group(1)}: *([0-9.]+)px", CSS).group(1))


# --- the hero actually leads -------------------------------------------------
def test_the_hero_number_is_meaningfully_bigger_than_its_siblings():
    """1.47x, not 1.09x. The threshold is not arbitrary: at 1.09x the
    difference was 1.6 pixels, which no reader resolves, and the border was
    silently doing all the work."""
    hero = _step(_rule(".metric.primary .v"))
    support = _step(_rule(SUPPORTING))
    assert hero / support >= 1.4, \
        f"hero {hero}px vs supporting {support}px is only {hero/support:.2f}x"
    # And where :has() is unsupported, the supporting values stay at the base
    # size. The hero still has to lead there — less, but unmistakably.
    base = _step(_rule(".metric .v"))
    assert hero / base >= 1.25, \
        f"without :has() the hero leads by only {hero/base:.2f}x"


def test_the_hero_size_is_a_ramp_token_not_a_parent_relative_unit():
    """The original bug. `1.24em` resolves against `.metric`, not against
    the sibling values, so it expressed a relationship nobody intended and
    the rendered gap was a third of what the number implied."""
    decl = _rule(".metric.primary .v")
    assert "em;" not in decl and "em " not in decl.replace("letter-spacing", ""), \
        f"the hero is back on a relative unit: {decl.strip()}"
    assert "var(--fs-" in decl


SUPPORTING = ".metrics:has(.metric.primary) .metric:not(.primary) .v"


def test_the_supporting_numbers_actually_recede():
    """Half the job. Raising the hero alone leaves the card just as loud;
    the other two have to become the context they are."""
    hero = _step(_rule(".metric.primary .v"))
    support = _step(_rule(SUPPORTING))
    assert support < hero, f"supporting {support}px is not below hero {hero}px"
    assert "color: var(--text-body)" in _rule(SUPPORTING)


def test_only_rows_with_a_hero_recede():
    """Not every metric row is a hierarchy. The NFL game-script card shows
    "CHI implied" beside "GB implied" — the same quantity for both sides of
    one game. That is a COMPARISON, and receding half of a comparison does
    not clarify it, it just makes the card quieter. An unscoped rule shrank
    both sides of it with nothing rising to lead, which is a straight loss.

    Hence :has(). Where it is unsupported both stay at the base size and the
    hero still leads — a smaller version of the same idea, not a broken
    layout."""
    assert _step(_rule(".metric .v")) == \
        float(re.search(r"--fs-xl: *([0-9.]+)px", CSS).group(1)), \
        "the base metric size moved; comparison rows have no hero to lead them"
    body = _strip_comments(CSS)
    assert ":has(.metric.primary)" in body, \
        "the recession is unscoped and applies to comparison rows too"


# --- and does it with type, not chrome ---------------------------------------
def test_the_hero_is_not_marked_out_by_a_box():
    """The queue item's constraint, in as many words: size, weight and
    colour, not borders. A tint plus a border-colour override is exactly
    the thing it rules out, and it was the only signal that actually
    registered while the type difference sat at 9%."""
    body = _strip_comments(CSS)
    m = re.search(r"\.metric\.primary\s*\{([^}]*)\}", body)
    if m:
        for prop in ("background", "border", "box-shadow", "outline"):
            assert prop not in m.group(1), \
                f".metric.primary is back to using {prop} for emphasis"
    assert "color-mix(in srgb, var(--brand) 9%" not in body, \
        "the brand tint on the hero tile is back"


def test_only_the_hero_carries_a_semantic_colour():
    """When all three numbers on a card are green, green has stopped saying
    anything. The supporting values keep their SIGN — it is written into
    the glyph, "+39.3%" — and give up the colour."""
    body = _strip_comments(CSS)
    assert f"{SUPPORTING}.pos" in body
    assert f"{SUPPORTING}.neg" in body


def test_the_hero_colour_rule_cannot_be_beaten_by_specificity():
    """`.metric.primary .v` and `.metric .v.pos` are both three classes, so
    a plain `color:` on the former would win by source order and paint
    every edge figure white — deleting the one colour on the card that
    carries meaning. The :not() pair is what keeps green green."""
    body = _strip_comments(CSS)
    m = re.search(r"\.metric\.primary \.v\s*\{([^}]*)\}", body)
    assert m, "no .metric.primary .v rule"
    assert "color:" not in m.group(1), \
        "an unconditional colour here overrides .v.pos / .v.neg"
    assert ".metric.primary .v:not(.pos):not(.neg)" in body, \
        "an unsigned hero has nothing making it the brightest thing"


# --- every card that has a metric row names its hero -------------------------
def test_every_metrics_row_marks_one_tile_primary():
    """Five rows rendered with no hero at all — the four-up long shot row
    and the fantasy buy-low row, both of which HAVE the number (Edge, Gap)
    and just never marked it. Left alone they would have been the only
    rows on the site where the supporting values shrank with nothing
    stepping up to lead."""
    rows = re.findall(r'<div class="metrics">(.*?)\n\s*</div>', APP, re.S)
    assert len(rows) >= 5, f"only found {len(rows)} metric rows to check"
    bad = []
    for block in rows:
        n = len(re.findall(r'class="metric(?: primary)?"', block))
        heroes = block.count('class="metric primary"')
        # Two tiles is a comparison, not a ranking — see
        # test_only_rows_with_a_hero_recede. Three or more is a claim that
        # one of them matters most, and it has to say which.
        if n >= 3 and heroes != 1:
            bad.append(f"{heroes} heroes among {n} tiles: {block.strip()[:70]}")
    assert not bad, "metric rows without exactly one hero: " + "; ".join(bad)


def test_the_hero_is_the_number_the_card_is_organised_around():
    """Not a taste call — the site already made it. Edge is what the AVG
    EDGE tile, the min-edge slider and the whole Edge Board are about, so a
    card whose metric row contains Edge leads with Edge."""
    rows = re.findall(r'<div class="metrics">(.*?)\n\s*</div>', APP, re.S)
    for block in rows:
        if '>Edge<' not in block:
            continue
        m = re.search(r'class="metric primary"><div class="k">([^<]+)<', block)
        assert m and m.group(1).strip() == "Edge", \
            f"a row containing Edge leads with something else: {m and m.group(1)}"


# --- the small screen --------------------------------------------------------
def test_the_hero_gets_its_own_row_on_a_phone():
    """Three tiles into two columns strands the hero on a half-empty second
    row, which reads as a layout bug rather than a choice — worse than the
    flat version it replaced. It spans the full first row instead."""
    block = CSS[CSS.index("@media (max-width: 420px)"):]
    block = block[:block.index("\n}\n")]
    assert ".metrics .metric.primary" in block
    rule = _rule(".metrics .metric.primary", block)
    assert "grid-column: 1 / -1" in rule
    assert "order: -1" in rule, \
        "the hero should be read first on the screen with the least room"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
