"""The payment-review flag: one switch, and nothing that routes around it.

Ethan, 2026-08-20: *"and yes lets remove what you think would hurt us in
the application till afte the review."*

WHAT THIS FILE IS ACTUALLY PROTECTING. The flag itself is one line and
needs no test. What needs a test is the promise attached to it: that
flipping one boolean is genuinely the whole change. That promise dies the
first time somebody writes a plain `<a href="https://polymarket...">` in
a new render path, because then the flag is off, the site still links
out, and nobody notices until a reviewer does.

So the tests below are mostly ABSENCE tests over the whole of app.js: no
hard-coded outbound anchor to a trading venue anywhere, no iframe whose
src can reach one, and the constant declared above the first line that
reads it. They fail loudly when a future change forgets the helper.

A note on how these are written, because it has bitten this repo five
times now: several of these check for a string that the SURROUNDING
COMMENTS also contain, since the comments explain the very mistake being
checked for. Every scan here strips comments first.

    python3 tests/test_review_mode.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VENUES = ("polymarket.com", "dexscreener.com", "geckoterminal.com")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _strip_js_comments(src):
    """Remove comments so a warning ABOUT a pattern is not read as one.

    THE FIRST VERSION OF THIS WAS A CHARACTER-BY-CHARACTER STATE MACHINE
    and it silently ate real code. JavaScript cannot be tokenized without
    a parser: a regex literal like /['"]/ is indistinguishable from a
    division followed by a string, so one such literal anywhere above
    left the scanner convinced it was inside a string, and the next
    hundred lines vanished from every absence test below. Absence tests
    that scan a file with a hole in it pass for the wrong reason, which is
    worse than not having them.

    So this does the boring thing instead. Block comments come out by
    regex, which is unambiguous because /* cannot appear in a JS regex
    literal without escaping. Line comments come out only when the // sits
    at the start of a line, which is how every one in this repo is
    written, and which can never match inside a URL — the case that
    matters, since half of what we scan for IS a URL.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"(?m)^[ \t]*//.*$", " ", src)
    return src


def _app():
    return _strip_js_comments(_read("web", "js", "app.js"))


# --------------------------------------------------------------- the flag

def test_the_flag_exists_and_is_off_for_the_review():
    app = _app()
    assert "const EXTERNAL_MARKET_LINKS = false;" in app, (
        "EXTERNAL_MARKET_LINKS is not declared false. If the Stripe "
        "application has been APPROVED, flipping it to true is the "
        "intended change — update this test in the same commit and say "
        "in the message that approval landed."
    )


def test_the_flag_is_declared_before_anything_reads_it():
    """A `const` read before its declaration line throws at load.

    Both consumers happen to sit inside function bodies today, which is
    why this has never fired. That is luck, not design: one top-level
    call above the declaration and the whole app is a blank page with a
    ReferenceError. Pin the ordering instead of relying on it.
    """
    app = _app()
    decl = app.index("const EXTERNAL_MARKET_LINKS") + len("const ")
    uses = [m.start() for m in re.finditer(r"EXTERNAL_MARKET_LINKS", app)]
    assert min(uses) == decl, (
        "something reads EXTERNAL_MARKET_LINKS above the line that "
        "declares it — that is a temporal dead zone, not a warning"
    )


def test_the_helper_returns_a_span_when_the_flag_is_off():
    app = _app()
    i = app.index("function extLink(")
    body = app[i:i + 500]
    assert "<a" in body and "<span" in body, \
        "extLink no longer has both an anchor and a non-anchor branch"
    assert "rel=\"noopener\"" in body, \
        "the anchor branch dropped rel=noopener — restore it before approval"


# ------------------------------------------------- nothing routes around it

def test_no_hardcoded_outbound_anchor_to_a_trading_venue():
    """The whole point. One helper, or the flag is decorative."""
    app = _app()
    for venue in VENUES:
        for m in re.finditer(r"href\s*=\s*[\"'`][^\"'`]*" + re.escape(venue), app):
            raise AssertionError(
                "a hard-coded link to %s at offset %d bypasses "
                "EXTERNAL_MARKET_LINKS — route it through extLink()"
                % (venue, m.start())
            )


def test_no_iframe_can_reach_a_venue_while_the_flag_is_off():
    app = _app()
    for m in re.finditer(r"<iframe[^>]*", app):
        tag = m.group(0)
        for venue in VENUES:
            assert venue not in tag, \
                "an iframe embeds %s directly instead of via the src gate" % venue


def test_the_chart_src_is_empty_while_the_flag_is_off():
    app = _app()
    # Anchor on the chart's own src, not the first `const src` in an
    # 18k-line file — that one belongs to something else entirely.
    i = app.index("geckoterminal.com/solana/pools")
    line = app[max(0, i - 400):i]
    assert "!EXTERNAL_MARKET_LINKS" in line, \
        "the meme-coin chart src no longer consults the review flag"


def test_an_empty_src_never_reaches_an_iframe():
    """`<iframe src="">` resolves to the CURRENT page.

    The first cut of this shipped `src=""` when the flag was off, which
    loads the whole app recursively inside its own chart dock. The fix is
    that an empty src renders a placeholder element instead, so this
    checks the iframe is emitted only on a truthy src.
    """
    app = _app()
    i = app.index("<iframe")
    before = app[max(0, i - 200):i]
    assert "src ?" in before or "src?" in before.replace(" ", ""), \
        "the iframe is no longer guarded by a truthy src check"
    assert "mc-chart-off" in app[i:i + 600], \
        "there is no placeholder for the flag-off case"


def test_the_market_row_url_is_gated_at_the_source():
    """Defence in depth: a consumer added later cannot resurrect the link."""
    app = _app()
    i = app.index("url: (EXTERNAL_MARKET_LINKS")
    assert i > 0, \
        "the market row's url field is no longer gated where it is built"


# ---------------------------------------------------------------- the dress

def test_the_placeholder_has_a_rule_so_the_dock_does_not_collapse():
    css = _read("web", "css", "styles.css")
    assert ".mc-chart-off {" in css, \
        "mc-chart-off is rendered but unstyled — the dock collapses"
    i = css.index(".mc-chart-off {")
    rule = css[i:i + 500]
    assert "min-height" in rule, \
        "the placeholder has no height, so the dock is a sliver"


def test_the_placeholder_does_not_pretend_the_numbers_changed():
    """Turning off a third-party chart changes nothing we computed.

    Said plainly, or a reader assumes the page is degraded.
    """
    app = _read("web", "js", "app.js")
    i = app.index("mc-chart-off")
    copy = app[i:i + 400]
    assert "unaffected" in copy, \
        "the placeholder no longer tells the reader our numbers are ours"


def test_the_restore_instruction_is_written_down():
    app = _read("web", "js", "app.js")   # comments ARE the subject here
    i = app.index("PAYMENT REVIEW MODE")
    block = app[i:i + 2600]
    assert "TO RESTORE AFTER APPROVAL" in block, \
        "the block no longer says how to undo itself"
    assert "docs/STRIPE_APPLICATION.md" in block, \
        "the block no longer points at the filed description"


def test_the_docs_name_the_flag():
    doc = _read("docs", "STRIPE_APPLICATION.md")
    assert "EXTERNAL_MARKET_LINKS" in doc, (
        "the application doc does not name the flag, so whoever reads it "
        "after approval will not know there is anything to switch back on"
    )


def test_the_crypto_page_still_exists():
    """We removed ambiguity, not a feature. Hiding one would be a lie."""
    app = _app()
    assert '"memes"' in app, \
        "the meme-coin view was removed — the filed description names it"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
