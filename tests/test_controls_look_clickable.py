"""A control has to look like something you can press.

Ethan, 2026-09-09, with people on the site for the first time:

    "we show a lot of just menu buttons or, like, tab buttons, and it
    kinda hides really cool features that we have, like the mock draft
    and the calendar for the fantasy and the around the league and the
    game scripts … I feel like that's a big problem we have is a lot of
    our buttons blending in with the text on the site so you can't
    really tell their buttons or tabs."

The sub-tab row was the worst of it. An inactive tab had no fill, no
border and muted text — body copy that happened to be clickable — and the
only tell that the row was navigation at all was a 2px underline beneath
whichever tab was already selected. Eight rooms on the Fantasy page live
behind that row.

These are shape assertions, deliberately. Colour alone is not a tell
(`test_organization` already has a rank test making that argument for
headings); what makes a control read as one is that it has a SURFACE and
an EDGE, and that the selected one is unmistakable.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _css():
    return open(os.path.join(HERE, "web", "css", "styles.css"),
                encoding="utf-8").read()


def _rule(css, selector):
    """The declarations of the FIRST rule for this exact selector.

    Comments stripped first: this stylesheet argues with itself in prose
    above almost every block, and the paragraph above this one quotes the
    very declarations it replaced — `background: transparent` and all.
    A grep that reads the comment is a grep that passes on the old code.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    i = css.index(selector + " {")
    return css[i + len(selector) + 2:css.index("}", i)]


def test_an_idle_tab_has_a_surface_and_an_edge():
    r = _rule(_css(), ".subnav-btn")
    assert "background: var(--fill-subtle)" in r, \
        "an idle tab has no fill — it is text again"
    assert "border: var(--hairline) solid var(--border)" in r, \
        "an idle tab has no edge — it is text again"
    # `border: 0` was the whole bug. It must not come back by any route.
    assert not re.search(r"border:\s*0", r), "the tab dropped its border"
    assert "background: transparent" not in r


def test_the_idle_tab_is_not_the_faintest_text_on_the_page():
    """It was `--text-mute`, the same token the italic hint line under
    the bar uses. A tab and a caption should not be the same weight."""
    r = _rule(_css(), ".subnav-btn")
    assert "color: var(--text-dim)" in r, "tab label is back to caption grey"


def test_the_selected_tab_is_unmistakable():
    """A filled tab rather than an underline, because the row WRAPS on a
    phone — it must, a scrolling tab row is the draggable bar from
    2026-08-18 — and an underline on the first line of a wrapped row is
    easy to miss completely."""
    r = _rule(_css(), ".subnav-btn.active")
    assert "background: var(--brand)" in r, "the active tab is not filled"
    assert "color: var(--brand-ink)" in r, \
        "filled with the brand but the label was left unreadable on it"
    assert "font-weight: 700" in r


def test_the_tap_target_grew():
    """7px of vertical padding on a phone is a miss waiting to happen,
    and these are the rows that hide the mock draft and the calendar."""
    r = _rule(_css(), ".subnav-btn")
    m = re.search(r"padding:\s*(\d+)px\s+(\d+)px", r)
    assert m, "the tab lost its padding declaration"
    y, x = int(m.group(1)), int(m.group(2))
    assert y >= 9 and x >= 14, f"tap target shrank back to {y}x{x}"


def test_hover_moves_the_surface_not_only_the_ink():
    r = _rule(_css(), ".subnav-btn:hover")
    assert "background: var(--fill-hover)" in r, \
        "hover only changes the text colour, which reads as a link"


def _js():
    return open(os.path.join(HERE, "web", "js", "app.js"),
                encoding="utf-8").read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    return js[i:js.index("\nfunction ", i + 1)]


def _nocomments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def test_a_likelihood_card_says_which_of_the_three_it_is():
    """Ethan, 2026-09-09: "with the top picks, we don't really have any
    of the background of that highlighted, so it's hard to show or tell
    that, like, these are good picks."

    Every card fell through to `--grade-color`'s default, which is
    `--text-faint` — the whole board painted in the token reserved for
    the least important thing on a page."""
    js = _js()
    card = _nocomments(_fn(js, "likelyCard"))
    assert "likelyTier(r)" in card, "the card carries no tier at all"
    assert 'class="card longshot ${likelyTier(r)}"' in card


def test_the_tiers_are_the_engines_own_distinctions():
    """`reserve` and `bettable` are fields the build sets. A probability
    threshold picked here to make a nicer gradient would be a claim the
    measurements do not support, wearing the most confident colour."""
    tier = _nocomments(_fn(_js(), "likelyTier"))
    assert ".reserve" in tier and ".bettable" in tier
    assert not re.search(r"0\.[0-9]+", tier), \
        "a probability threshold was invented in the renderer"


def test_each_tier_paints_the_stripe_a_different_colour():
    css = _css()
    for cls, token in (("lk-top", "var(--brand)"),
                       ("lk-mid", "var(--good)")):
        r = _rule(css, f".card.longshot.{cls}")
        assert f"--grade-color: {token}" in r, f"{cls} stripe is wrong"
    # lk-low sets nothing: `.card::before` already falls back to the
    # faintest token, and `test_contrast` rations that token by counting
    # the RAW file — so a rule here, or even the token's name in a
    # comment, costs one of eight for a rendering that does not change.
    assert ".card.longshot.lk-low {" not in css, \
        "lk-low took a stripe rule it does not need"
    assert ".card.longshot.lk-low .grade.lk-pct" in css, \
        "lk-low still needs its pill rule"


def test_the_percentage_pill_is_no_longer_one_green_for_every_row():
    """It was `style="background:var(--good);color:#08130c"` inline on
    every card — a 48% read and a 71% read in identical green, which is a
    highlight that highlights everything."""
    card = _nocomments(_fn(_js(), "likelyCard"))
    assert "#08130c" not in card, "the hardcoded pill colour is back"
    assert "background:var(--good)" not in card.replace(" ", ""), \
        "the pill is hardcoded green again"
    assert 'class="grade lk-pct"' in card


def test_the_filled_pills_use_the_token_that_flips_with_the_theme():
    """`--brand-ink` means "text ON the accent". The hex it replaced was
    near-black in both themes, and the light theme's green is dark."""
    css = _css()
    for cls in ("lk-top", "lk-mid"):
        r = _rule(css, f".card.longshot.{cls} .grade.lk-pct")
        assert "color: var(--brand-ink)" in r, f"{cls} pill label"
    low = _rule(css, ".card.longshot.lk-low .grade.lk-pct")
    assert "background: none" in low, \
        "a below-the-bar row is filled like a pick, arguing with its own chip"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
