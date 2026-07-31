"""The About page, and the promises it has to keep.

This is the one page on the site a stranger reads top to bottom, and the
only one where being wrong is a legal problem rather than a modelling
one. So the tests are about substance, not markup: the disclaimers have
to actually be present, the page must not promise certainty anywhere, and
the help resources have to be real.

The load-bearing idea is that a page which hypes the model on the way to
a disclaimer has not really made the disclaimer. So there are assertions
both ways — the required warnings are there, AND the language that would
undercut them is absent.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def _about_source() -> str:
    app = _read("web", "js", "app.js")
    start = app.index("function renderAbout()")
    return app[start:app.index("\nasync function renderWhy()", start)]


# --- it exists and is reachable --------------------------------------------
def test_the_page_is_wired_end_to_end():
    html = _read("web", "index.html")
    assert 'id="view-about"' in html
    assert 'data-sport="about"' in html, "no way to reach it from the menu"
    app = _read("web", "js", "app.js")
    assert "function renderAbout()" in app
    assert "renderAbout();" in app, "defined but never called"
    assert '"about"' in app[app.index("const STANDALONE_MODES"):
                            app.index("const STANDALONE_MODES") + 120]


def test_the_freshness_chip_hides_on_a_page_with_no_data():
    """"Stale — built 10h ago" over a page of prose that has no build at
    all is a lie of scope."""
    app = _read("web", "js", "app.js")
    assert "REFERENCE_VIEWS" in app
    block = app[app.index("const REFERENCE_VIEWS"):]
    assert '"about"' in block[:120] and '"why"' in block[:120]
    fn = app[app.index("function updateAgo()"):]
    fn = fn[:fn.index("\n}\n")]
    assert "REFERENCE_VIEWS.includes(state.view)" in fn
    # Hidden, not display:none — the header row must not change height.
    assert 'visibility = "hidden"' in fn


# --- the disclaimers are actually there ------------------------------------
def test_it_says_plainly_that_this_is_not_a_sportsbook():
    src = _about_source()
    assert "not a sportsbook" in src
    assert "no money changes hands" in src
    assert "take no bets" in src.lower()


def test_it_says_plainly_that_this_is_not_betting_advice():
    src = _about_source()
    assert "not betting advice" in src.lower()
    assert "not financial advice" in src.lower()
    assert "general information" in src.lower()


def test_it_says_the_outcome_is_random_and_anything_can_happen():
    src = _about_source()
    assert "random" in src.lower()
    assert "No model can predict a single event" in src
    assert "guarantee" in src.lower()
    assert "Past results" in src


def test_it_covers_the_legal_ground():
    src = _about_source().lower()
    for required in ("legal gambling age", "21", "not legal everywhere",
                     "not affiliated", "trademarks", "no warranty",
                     "liability"):
        assert required in src, f"the legal section never mentions {required!r}"


def test_it_carries_real_responsible_gambling_help():
    src = _about_source()
    # The US national helpline number, exactly.
    assert "1-800-GAMBLER" in src and "1-800-426-2537" in src
    assert "ncpgambling.org" in src
    assert "begambleaware.org" in src
    assert "self-exclusion" in src
    # Every outbound link must be safe to open from our page.
    for anchor in re.findall(r"<a [^>]*>", src):
        if 'target="_blank"' in anchor:
            assert 'rel="noopener noreferrer"' in anchor, \
                f"unsafe external link: {anchor}"


def test_it_explains_the_one_place_pitch():
    src = _about_source()
    assert "one place" in src.lower()
    assert "ten sportsbooks" in src.lower() or "ten different" in src.lower()
    assert "public" in src.lower(), "the edge is aggregation, not secrets"


def test_it_explains_that_a_no_play_answer_is_the_system_working():
    src = _about_source()
    assert "no qualifying plays" in src.lower()
    assert "working rather than failing" in src


# --- and does NOT undercut them --------------------------------------------
def test_the_page_never_promises_a_winner():
    """A page that hypes on the way to a disclaimer hasn't disclaimed.

    Read sentence by sentence rather than as a substring: the page says
    "Nothing here is a guarantee, a lock, a sure thing" — which is the
    denial, not the promise — and a naive scan flags it as a violation.
    A sentence carrying a negation is doing the opposite of selling.
    """
    banned = ("guaranteed win", "sure thing", "can't lose", "cannot lose",
              "risk-free", "risk free", "easy money", "we guarantee",
              "always profitable", "beat the book every")
    negations = ("not ", "never", "nothing", "no ", "n't", "cannot")
    text = re.sub(r"<[^>]+>", " ", _about_source()).lower()
    for sentence in re.split(r"[.!?]", text):
        if any(n in sentence for n in negations):
            continue                      # a denial, not a claim
        for phrase in banned:
            assert phrase not in sentence, \
                f"the About page promises {phrase!r}: …{sentence.strip()[:90]}…"


def test_the_warning_sections_are_not_buried_below_the_marketing():
    """Order matters on a page people skim: the honest part has to be part
    of the page, not a footer."""
    src = _about_source()
    assert src.index("Anything can happen") < src.index("In one sentence")
    assert "The honest part" in src


def test_the_help_links_are_real_tap_targets_on_a_phone():
    """They were 15px tall — the most important links on the page and the
    hardest to hit. Somebody reaching for a helpline should not have to
    aim."""
    css = _read("web", "css", "styles.css")
    assert ".about-list a" in css
    coarse = css[css.rindex("@media (pointer: coarse)"):]
    assert ".about-list a" in coarse
    block = coarse[coarse.index(".about-list a"):]
    assert "padding: 12px" in block[:220]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
