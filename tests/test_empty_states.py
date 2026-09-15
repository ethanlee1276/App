"""One situation, one treatment — and three sizes of it.

Ethan, 2026-08-23, on the public-eye pass, choosing option B: make the
empty states consistent, leave the calculator prompts alone.

The audit found two visual languages for "nothing here yet". 27 places
used `.empty-slate` — a mark, a title, a sentence. 29 used `.loading`, a
class meant for text that is about to be REPLACED, which reserves 60px of
centred padding for a line that is never going anywhere. The weaker one
was on more pages.

SWAPPING ALL 29 TO THE SLATE WOULD HAVE BEEN THE WRONG FIX for half of
them. A 22px mark, a title and a sub is right when a whole VIEW is empty;
the Record page's sampler panels are one line each inside a page that
already carries twelve sections, and giving every one that furniture
makes the page worse rather than more consistent.

So there are three treatments and each says what it is for:

    .loading      text that is about to be replaced
    .empty-slate  a whole view has nothing in it
    .panel-empty  a panel inside a populated page has nothing YET
    .list-note    a caveat under content that IS there

The rule this file guards is that `.loading` means only the first one.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

#: A message is transient only if it says it is still happening.
STILL_HAPPENING = ("simulating", "loading", "reading", "syncing", "checking",
                   "fetching", "working")


def _loading_messages():
    out = []
    for m in re.finditer(r'class="loading"[^>]*>(.{0,120})', APP, re.S):
        out.append(" ".join(m.group(1).split()))
    return out


def test_loading_is_only_ever_used_for_something_still_happening():
    """The rule. Every one of these has to be text a visitor will see
    replaced within a second or two."""
    bad = [t for t in _loading_messages()
           if not t.lower().lstrip("${").startswith(STILL_HAPPENING)]
    assert not bad, ("permanent text wearing the loading treatment:\n  "
                     + "\n  ".join(t[:70] for t in bad))


def test_the_permanent_messages_moved_rather_than_vanished():
    """A conversion that quietly dropped a sentence would pass the test
    above and lose the thing the sentence said."""
    for said in ("Nothing settled yet",
                 "No open bets on today",
                 "Flags settle as their markets resolve",
                 "Nobody outside the sustainable band right now",
                 "No market clears the gate right now",
                 "Nothing to pass on"):
        assert said in APP, said


def test_every_size_has_a_helper_so_they_cannot_drift_apart():
    assert "function emptySlate(" in APP
    assert "function panelEmpty(" in APP
    assert APP.count("function emptySlate(") == 1
    assert APP.count("function panelEmpty(") == 1


def test_the_helpers_escape_what_they_are_given():
    """Every call site was already writing a sentence into a template.
    Centralising the escaping is the half that stops one of them growing
    an injection later."""
    for name in ("emptySlate", "panelEmpty"):
        i = APP.index(f"function {name}(")
        body = APP[i:APP.index("\n}", i)]
        assert "escapeHtml(" in body, name


def test_each_treatment_is_styled():
    for cls in (".loading", ".empty-slate", ".panel-empty", ".list-note"):
        assert cls in CSS, cls


def test_the_panel_note_does_not_reserve_a_screenful():
    """The defect being fixed: `.loading` sets 60px of padding, which for
    a one-line note inside a card is a box of nothing."""
    i = CSS.index(".panel-empty {")
    rule = CSS[i:CSS.index("}", i)]
    px = [int(n) for n in re.findall(r"padding:[^;]*?(\d+)px", rule)]
    assert px and max(px) <= 20, f"the light treatment is not light: {rule}"


def test_the_calculators_keep_their_prompts():
    """Ethan's own carve-out. "Enter both sides as American odds" is a
    form hint, not an empty state — a mark and a title would be worse."""
    for hint in ("Enter both sides as American odds",
                 "Enter a win probability",
                 "Enter odds for at least two legs"):
        assert hint in APP, hint
        i = APP.index(hint)
        assert "empty-slate" not in APP[max(0, i - 200):i], \
            f"a calculator prompt grew a slate: {hint}"


def test_a_whole_empty_board_gets_the_slate_not_a_grey_line():
    """The first thing a visitor sees on a board with nothing priced."""
    i = APP.index("censusFunnelHTML()}`;")
    block = APP[i - 700:i]
    assert 'class="empty-slate"' in block
    assert "msgTitle" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
