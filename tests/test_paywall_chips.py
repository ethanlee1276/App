"""The chips and the cards that say what the site covers.

Ethan, 2026-08-22, circling it on his phone: *"we should be using emojis
matching what we are talking about here."*

WHAT WAS WRONG WITH THE DRAWN MARKS. The icon set has no football and no
baseball, so NFL and CFB both took `shield` and MLB, NBA and WNBA all took
the same `target`. Nine chips, five of them sports, two distinct marks
between them. The row exists to show breadth at a glance and three
identical circles say the opposite.

WHY THIS IS NOT A HOLE IN THE EMOJI AUDIT. tests/test_icons.py took emoji
out of the site because a *status mark* that changes shape per platform
and cannot take the colour of the thing it labels is not an icon set. Its
own exemption list names the sport logos — illustration, not status — and
`SPORTS[x].logo` has been 🏈 ⚾ 🏀 since long before this row existed.
These are the same glyphs, on the page that sells the thing they mark.

THE TEN FEATURE CARDS BELOW THE CHIPS have the same story and were done
in the same pass. The drawn set repeated itself there too: `target` on
Picks and props while the MLB chip also wore `target`, `chart` and
`rising` a hair apart from each other, `gem` doing duty for meme coins in
both rows.

    python3 tests/test_paywall_chips.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()

EMOJI = re.compile(r"[\U0001F300-\U0001FAFF⚠-➿☀-⛿]")


def _chips():
    m = re.search(r"const PW_SPORTS = \[(.*?)\n\];", APP, re.S)
    assert m, "PW_SPORTS is gone"
    return re.findall(r'\["([^"]+)",\s*"([^"]+)"\]', m.group(1))


def _sport_logos():
    """`SPORTS[x].logo` — what the rest of the site draws for each one."""
    out = {}
    for m in re.finditer(r'^\s{2}(\w+): \{ logo: "([^"]+)"', APP, re.M):
        out[m.group(1)] = m.group(2)
    return out


# --- the marks --------------------------------------------------------------
def test_every_chip_has_a_mark_and_a_label():
    chips = _chips()
    assert len(chips) >= 8, "the breadth row lost most of its breadth"
    for label, mark in chips:
        assert label.strip() and mark.strip(), (label, mark)


def test_every_mark_is_an_emoji():
    for label, mark in _chips():
        assert EMOJI.search(mark), (
            "%s still carries a drawn icon name (%r); the set has no "
            "football and no baseball, which is how five sports ended up "
            "sharing two marks" % (label, mark))


def test_the_row_is_not_the_same_glyph_over_and_over():
    """The failure being fixed, stated as a number. It was two distinct
    marks across nine chips."""
    marks = {m for _l, m in _chips()}
    assert len(marks) >= 6, (
        "only %d distinct marks across %d chips — the row is supposed to "
        "show breadth: %s" % (len(marks), len(_chips()), sorted(marks)))


def test_the_two_repeats_are_the_ones_that_should_repeat():
    """NFL and CFB are both football; NBA and WNBA are both basketball.
    Those sharing a glyph is correct. Anything else sharing one is the
    old bug coming back."""
    by_mark = {}
    for label, mark in _chips():
        by_mark.setdefault(mark, []).append(label)
    for mark, labels in by_mark.items():
        if len(labels) == 1:
            continue
        assert set(labels) in ({"NFL", "CFB"}, {"NBA", "WNBA"}), (
            "%s share %s and are not the same sport" % (labels, mark))


# --- and they agree with the rest of the site -------------------------------
def test_the_real_sports_use_the_same_glyph_the_app_uses():
    """The shop and the app must not disagree about what a baseball looks
    like. `SPORTS[x].logo` is the app's answer and predates this row."""
    logos = _sport_logos()
    assert logos, "SPORTS[].logo is gone; this test cannot check anything"
    chips = dict(_chips())
    for key, label in (("nfl", "NFL"), ("mlb", "MLB"), ("nba", "NBA"),
                       ("wnba", "WNBA"), ("cfb", "CFB")):
        if key not in logos or label not in chips:
            continue
        assert chips[label] == logos[key], (
            "the shop draws %s for %s and the app draws %s"
            % (chips[label], label, logos[key]))


# --- the feature cards ------------------------------------------------------
def _cards():
    return re.findall(r'feature\("([^"]+)",\s*"([^"]+)"', APP)


def test_every_feature_card_is_marked_with_an_emoji():
    cards = _cards()
    assert len(cards) >= 8, "the feature grid lost most of its cards"
    for mark, title in cards:
        assert EMOJI.search(mark), (
            "%r still carries a drawn icon name (%r)" % (title, mark))


def test_no_two_cards_wear_the_same_mark():
    """Unlike the sports, no two of these are the same thing — so any
    repeat here is the drawn set's problem coming back rather than an
    honest pair."""
    by_mark = {}
    for mark, title in _cards():
        by_mark.setdefault(mark, []).append(title)
    dupes = {m: t for m, t in by_mark.items() if len(t) > 1}
    assert not dupes, "cards sharing a mark: %s" % dupes


def test_a_card_and_a_chip_about_the_same_thing_agree():
    """Prediction markets and meme coins appear in both rows. Two glyphs
    for one subject on one page is the reader's problem, not a detail."""
    chips = dict(_chips())
    cards = {t: m for m, t in _cards()}
    for chip_label, card_title in (("Prediction markets", "Prediction markets"),
                                   ("Meme coins", "Meme coin scanner"),
                                   ("Fantasy", "The full fantasy suite")):
        if chip_label in chips and card_title in cards:
            assert chips[chip_label] == cards[card_title], (
                "the chip draws %s for %s and the card draws %s for %s"
                % (chips[chip_label], chip_label,
                   cards[card_title], card_title))


def test_the_card_glyph_is_sized_for_a_card():
    """It replaced a 20px drawn mark, not the chip's 15px one."""
    i = CSS.index(".pw-emoji.lg")
    rule = CSS[i:CSS.index("}", i)]
    assert "var(--fs-" in rule, "a raw size on the card glyph"


def test_the_modifier_comes_after_the_rule_it_modifies():
    """`.pw-emoji.lg` written above `.pw-emoji` loses its font-size to
    the base rule at equal specificity — and it did, on the first go."""
    assert CSS.index(".pw-emoji {") < CSS.index(".pw-emoji.lg"), (
        "the .lg modifier is declared before the base rule and is "
        "overridden by it")


def test_the_card_glyph_is_hidden_from_a_screen_reader():
    i = APP.index("const feature = (")
    block = APP[i:i + 500]
    assert 'aria-hidden="true"' in block


# --- how they render --------------------------------------------------------
def test_the_glyph_is_hidden_from_a_screen_reader():
    """The label is the very next node. "American football NFL" is a
    stutter, not a help."""
    i = APP.index('<div class="pw-sports">')
    block = APP[i:i + 600]
    assert 'aria-hidden="true"' in block, (
        "the emoji is announced alongside the label it duplicates")


def test_the_emoji_has_a_font_stack_of_its_own():
    """`--font-sans` is self-hosted and has no emoji glyphs, so without
    this the browser falls back per-codepoint to whatever it likes."""
    i = CSS.index(".pw-emoji")
    rule = CSS[i:CSS.index("}", i)]
    assert "font-family" in rule
    assert "Emoji" in rule, "no emoji family is named"


def test_the_emoji_size_is_on_the_ramp():
    """It is a text glyph, so it is subject to the same rule as text."""
    i = CSS.index(".pw-emoji")
    rule = CSS[i:CSS.index("}", i)]
    m = re.search(r"font-size:\s*([^;]+)", rule)
    assert m, "no size at all"
    assert "var(--fs-" in m.group(1), (
        "a raw font size on the one glyph that rides the baseline: %r"
        % m.group(1))


def test_it_does_not_drift_with_the_line_height():
    i = CSS.index(".pw-emoji")
    rule = CSS[i:CSS.index("}", i)]
    assert "line-height: 1" in rule, (
        "an emoji at the inherited line-height moves every time the type "
        "ramp does — the complaint in tests/test_icons.py's header")


def test_the_audit_that_removed_emoji_still_passes():
    """This row is the exemption, not a repeal. If test_icons ever starts
    failing, one of these two is wrong and it is worth knowing which."""
    import subprocess
    import sys
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "test_icons.py")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, (
        "the emoji audit fails with these chips in place:\n"
        + (r.stdout + r.stderr)[-600:])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
