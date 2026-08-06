"""The masthead runs once, and the way back out of it has to work.

Measured on an iPhone 13, the full masthead is ~790px — mark, wordmark,
tagline, running ROI, record, the journaling promise, status chips — ahead
of the picks, on every single load. That block earns its space for a
first-time reader and earns nothing on the fifth visit, so it runs once and
then collapses to one line carrying the same two facts (what this is, what
the record is), with the full block one tap away.

Three things have to hold, and the third is the one that actually bit.

**It must only apply where it pays.** Above 1,248px the header lays the
identity and the status row side by side, so hiding the wordmark moved the
picks by negative one pixel. Trading the name of the site for that is not a
trade.

**Expanded must be identical to a first visit.** The first attempt brought
the block back with `display: revert`, which drops the whole author origin
and lands on the UA default — the wordmark returned as an inline <a>, mark
stacked above name, record run into one paragraph.

**The tap has to reach the button.** The theme toggle carries a 44px
invisible reach pseudo-element so its 36px box still clears the touch
floor. Its `position` was being set by an ID rule (`static`) that outranked
the class rule meant to make it `relative`, so the pseudo resolved against
the nearest positioned ancestor instead — the sticky `.topbar` — and parked
a 44x44 dead zone in the CENTRE of the header on every phone view. It ate
taps on whatever landed there, which is how it was found.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def _decls_only(css):
    """The stylesheet with /* comments */ removed.

    These rules are heavily commented, and the comments quote the wrong
    versions on purpose — the `display: revert` test below matched the
    sentence explaining why `display: revert` is wrong. A test that reads
    prose as code fails on its own documentation.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _media_block(css, header, containing=None):
    """The body of the `@media` rule opening with `header`.

    Brace-counted rather than regexed, because these blocks nest rules and
    a non-greedy match to the first `}` returns the first declaration.

    The same breakpoint is opened more than once in this stylesheet — the
    phone rules are spread across several blocks by topic — so `containing`
    selects which one, by a string that must be inside it.
    """
    css = _decls_only(css)
    at, found = 0, []
    while True:
        i = css.find(header, at)
        if i < 0:
            break
        start = css.index("{", i)
        depth, j = 0, start
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        else:
            raise AssertionError(f"unbalanced braces after {header!r}")
        found.append(css[start + 1:j])
        at = j
    assert found, f"no @media block opening {header!r}"
    if containing is None:
        return "\n".join(found)
    hits = [b for b in found if containing in b]
    assert hits, f"no {header!r} block contains {containing!r}"
    return hits[0]


# --- the reach pseudo needs a containing block -------------------------------
def test_the_theme_toggle_owns_its_own_reach_target():
    """The 44px hit expander must resolve against the toggle, not the topbar.

    This is the regression guard for a real defect, not a style preference.
    `.slate-meta .theme-toggle::after` is `position: absolute`, so it is
    placed against its nearest POSITIONED ancestor. If the toggle itself is
    unpositioned, that ancestor is `.topbar` — which is `position: sticky` —
    and `top/left: 50%` then centres a 44x44 invisible box in the middle of
    the header, over the content, swallowing taps.

    `static` and `relative` lay out identically here (no offsets are set),
    so this costs nothing and is purely about who the containing block is.
    """
    css = _read("web", "css", "styles.css")
    phone = _media_block(css, "@media (max-width: 760px)",
                         containing=".theme-toggle::after")
    assert ".theme-toggle::after" in phone, (
        "the reach pseudo moved out of the phone block — re-point this test "
        "at wherever it lives now, the containing-block rule travels with it"
    )
    decls = re.findall(r"#theme-toggle\s*\{([^}]*)\}", phone)
    assert decls, "no #theme-toggle rule in the phone block"
    for body in decls:
        pos = re.search(r"position\s*:\s*([a-z-]+)", body)
        if pos:
            assert pos.group(1) != "static", (
                "#theme-toggle is `position: static` in the same block that "
                "gives it a 44px absolutely-positioned reach pseudo. That "
                "pseudo will centre itself on the sticky .topbar instead and "
                "block taps in the middle of the header."
            )


def test_the_toggle_is_not_positioned_by_a_weaker_selector():
    """An ID rule beat the class rule that was meant to do this.

    `#theme-toggle` is (1,0,0); `.slate-meta .theme-toggle` is (0,2,0). The
    class rule's `position: relative` never applied, and nothing said so.
    Keep the positioning on the ID so it cannot be quietly outranked again.
    """
    css = _read("web", "css", "styles.css")
    phone = _media_block(css, "@media (max-width: 760px)",
                         containing=".theme-toggle::after")
    weaker = re.findall(r"\.slate-meta\s+\.theme-toggle\s*\{([^}]*)\}", phone)
    for body in weaker:
        assert "position" not in body, (
            "positioning the toggle from `.slate-meta .theme-toggle` is "
            "dead code — the `#theme-toggle` rule in the same block outranks "
            "it. Set position on the ID rule instead."
        )


# --- the compact masthead only where it pays --------------------------------
def test_the_compact_masthead_is_gated_to_where_it_saves_space():
    """Measured: 105px on a phone, 43px at 1024, -1px at 1280.

    So it runs below the width where the header stops stacking, and above
    that the site keeps its name.
    """
    css = _read("web", "css", "styles.css")
    assert ".masthead-brief { display: none; }" in css, (
        "the brief line must default to hidden, so the gate is what turns "
        "it on rather than what turns it off"
    )
    gate = _media_block(css, "@media (max-width: 1247px)",
                        containing=".masthead-brief")
    assert ":root.intro-seen .masthead-brief" in gate, (
        "the compact masthead escaped its width gate — on a wide desktop it "
        "hides the wordmark and buys nothing"
    )


def test_the_full_block_is_not_restored_with_revert():
    """`revert` drops the author origin, not just the one declaration.

    Both the `display: none` and the original `display: flex` are
    author-origin, so `revert` lands on the UA default and the masthead
    comes back as inline elements. The hide rule must instead not match
    while the brief is expanded.
    """
    css = _read("web", "css", "styles.css")
    gate = _media_block(css, "@media (max-width: 1247px)",
                        containing=".masthead-brief")
    assert "display: revert" not in gate, (
        "`display: revert` reverts past the stylesheet to the UA default — "
        "the expanded masthead will not match a first visit. Scope the hide "
        "with :not(:has(...)) so it simply stops applying."
    )
    assert ':not(:has(.masthead-brief[aria-expanded="true"]))' in gate, (
        "the hide rule has to exclude the expanded state, otherwise nothing "
        "brings the full masthead back"
    )


# --- a toggle has to toggle --------------------------------------------------
def test_the_brief_button_survives_being_expanded():
    """It must not hide itself on activation.

    A control that vanishes when used leaves no way back without a reload,
    and throws keyboard focus onto a removed element mid-interaction. The
    expanded state keeps the same button, demoted to a "Hide".
    """
    css = _read("web", "css", "styles.css")
    gate = _media_block(css, "@media (max-width: 1247px)",
                        containing=".masthead-brief")
    hidden = re.search(
        r':root\.intro-seen \.masthead-brief\[aria-expanded="true"\]\s*\{'
        r"([^}]*)\}",
        gate,
    )
    assert hidden, "no rule styles the expanded brief button"
    assert "display: none" not in hidden.group(1), (
        "the brief button hides itself when expanded — there is then no "
        "control to collapse it, and focus lands on nothing"
    )
    html = _read("web", "index.html")
    assert 'class="mb-hide"' in html, (
        "the expanded state needs a visible label saying what the button "
        "now does; an unlabelled row is not an affordance"
    )


def test_the_intro_flag_is_set_before_first_paint():
    """Otherwise the full masthead paints and then jumps away under a thumb.

    The class goes on <html> from an inline script in <head>, ahead of any
    body content — the same no-flash pattern the theme uses.
    """
    html = _read("web", "index.html")
    head = html[: html.index("</head>")]
    assert 'classList.add("intro-seen")' in head, (
        "the intro-seen class must be set in <head>; setting it from app.js "
        "means a paint of the full masthead followed by a reflow"
    )
    assert "qb-seen-intro" in head, "the flag must be read from storage in <head>"


def test_the_record_has_one_source():
    """The brief line and the full masthead cannot be allowed to disagree.

    Both are filled by renderStandingRecord() from the journal the Record
    page reads. A second formatter here would be a second thing to keep in
    step, and the running record is the one number this site is staking its
    credibility on.
    """
    js = _read("web", "js", "app.js")
    i = js.index("function renderStandingRecord")
    body = js[i:js.index("\nfunction ", i + 10)]
    assert "mb-rec" in body, (
        "#mb-rec must be filled by renderStandingRecord, not by its own "
        "formatting code — two renderings of the record can drift apart"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
