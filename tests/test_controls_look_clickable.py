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


def _read_js():
    return open(os.path.join(HERE, "web", "js", "app.js"),
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


def test_every_room_is_named_and_described_on_arrival():
    """Ethan, 2026-09-09: "it kinda hides really cool features that we
    have, like the mock draft and the calendar for the fantasy and the
    around the league and the game scripts … it's so cool information
    that we hide."

    The descriptions were never missing. Every group carries one in
    `g[2]`, and the bar rendered exactly ONE — the active room's —
    throwing the other seven away on every render."""
    fn = _nocomments(_fn(_js(), "subtabbedHTML"))
    assert "room-index" in fn, "no index is built"
    assert "data-roomjump" in fn
    assert "rc-what" in fn, "the index names rooms without saying what is in them"
    # It reads g[2] — the SAME description the hint line uses, not a
    # second set of copy that can drift from it.
    i = fn.index("room-index")
    assert "g[2]" in fn[i:i + 500], "the index invented its own descriptions"


def test_the_index_is_opt_in_so_it_does_not_restyle_two_other_pages():
    """Record and Players are roomed too. Switching them on as a side
    effect of fixing Fantasy is how a change nobody asked for ships."""
    js = _js()
    fn = _nocomments(_fn(js, "subtabbedHTML"))
    assert "(opts || {}).index" in fn, "the index is unconditional"
    i = js.index('subtabbedHTML("fantasy"')
    assert "{ index: true }" in js[i:js.index("_ffFoot", i)], \
        "Fantasy — the page with eight rooms — does not ask for it"
    for other in ('subtabbedHTML("record"', 'subtabbedHTML("players"'):
        if other in js:
            j = js.index(other)
            assert "index: true" not in js[j:j + 3000], \
                f"{other} was switched on without being asked"


def test_an_index_card_opens_the_room_through_the_same_switch():
    """Two code paths for "open a room" is two chances for the tab bar,
    the panels and the hint to disagree about which room is open."""
    bind = _nocomments(_fn(_js(), "bindSubtabs"))
    assert "data-roomjump" in bind, "the index cards are decorative"
    i = bind.index("data-roomjump")
    assert "show(" in bind[i:i + 400], "a card does not call show()"
    # And a card is NOT a .subnav-btn. If it were, it would take the
    # active fill too, and two things on screen would claim to be the
    # current tab.
    card = _nocomments(_fn(_js(), "subtabbedHTML"))
    i = card.index("room-card")
    assert "subnav-btn" not in card[i - 200:i + 200], \
        "an index card is styled as a tab and will fight the real one"


def test_an_index_card_is_shaped_like_a_control():
    css = _css()
    r = _rule(css, ".room-card")
    assert "background: var(--fill-subtle)" in r
    assert "border: var(--hairline) solid var(--border)" in r
    assert "cursor: pointer" in r
    hover = _rule(css, ".room-card:hover")
    assert "background: var(--fill-hover)" in hover


def test_a_text_button_is_at_least_a_link():
    """`.btn-quiet` carried the SAME recipe the sub-tabs had — no fill, no
    edge, `--text-mute` ink — in eleven more places, which is why the tab
    fix could not be the whole of Ethan's complaint.

    An underline rather than the tab's fill, and the distinction is the
    point: these sit inside sentences and beside headings. A filled chip
    in running text claims the weight of a primary action for something
    that undoes navigation, which is a worse lie than a quiet one. They
    are links, so they look like links."""
    r = _rule(_css(), ".btn-quiet")
    assert "text-decoration: underline" in r, \
        "a text button with no underline is indistinguishable from text"
    assert "color: var(--text-dim)" in r, "still the faintest-but-one ink"
    assert "color: var(--text-mute)" not in r
    # The tap target was already honest here and must stay that way.
    assert "min-height: 40px" in r


def test_a_door_is_not_a_link():
    """Two of the eleven were not links at all. `gp-pbp-door` opens the
    whole play-by-play page; `gp-showbets` reveals five bets the page is
    holding back — the exact "hides really cool features" Ethan named.
    Those wear `.btn ghost`, which this design already owns, rather than
    being shouted at inside the quiet class."""
    js = _read_js()
    for door in ("gp-pbp-door", "gp-showbets"):
        i = js.index(f'id="{door}"')
        tag = js.rindex("<button", 0, i)
        assert "btn ghost" in js[tag:i], f"{door} is still a text button"
        assert "btn-quiet" not in js[tag:i], f"{door} kept the quiet class"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
