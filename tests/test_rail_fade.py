"""The rail fades its last line instead of guillotining it — conditionally.

Design-queue item, measured 2026-08-19 and acted on 2026-08-31: 1222px
of sidebar content in a 1036px box with overlay scrollbars showing
nothing, so the last visible line was sliced mid-sentence and read as
broken rather than as "more below".

THE FADE IS CONDITIONAL, AND THAT IS THE DESIGN. A mask on the bare
`.sidebar` would fade the final line even at the end of the scroll —
the same defect wearing a gradient. `.sb-more` is toggled by scroll
position: masked while content remains below, unmasked at the bottom.
Measured in Chromium at 1280×1100: overflowing=true → masked=true at
the top, masked=false scrolled to the end.

Run directly: `python3 tests/test_rail_fade.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_the_fade_rides_a_class_never_the_bare_element():
    css = _src("web", "css", "styles.css")
    at = css.index(".sidebar.sb-more")
    rule = css[at:css.index("}", at)]
    assert "mask-image" in rule and "var(--mask-more)" in rule
    assert "--mask-more: linear-gradient" in css, "the token must exist"
    # The bare rule stays maskless — a permanent fade would slice the
    # true last line at the end of the scroll.
    bare = css.index(".sidebar { position: sticky")
    bare_rule = css[bare:css.index("}", bare)]
    assert "mask-image" not in bare_rule


def test_the_toggle_reads_scroll_position_and_watches_content():
    js = _src("web", "js", "app.js")
    at = js.index('classList.toggle("sb-more"')
    block = js[at - 900:at + 900]
    assert "scrollTop + sb.clientHeight < sb.scrollHeight" in block
    assert 'addEventListener("scroll", sync' in block
    # The rail's CONTENT changes (league chips, folds, the ROI note)
    # without the box resizing, so a resize observer alone goes stale.
    assert "MutationObserver(sync)" in block


def test_both_webkit_and_standard_masks_are_set():
    """Safari still wants the prefix; a standard-only mask ships the
    guillotine back to every iPhone — the platform the complaint came
    from."""
    css = _src("web", "css", "styles.css")
    at = css.index(".sidebar.sb-more")
    rule = css[at:css.index("}", at)]
    assert "-webkit-mask-image" in rule and "\n  mask-image" in rule


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
