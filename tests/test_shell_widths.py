"""The sidebar and the rail are one decision, not three.

Ethan, 2026-08-24: "are we able to make these two side just a little bit
smaller too give the main page more room."

MEASURED BEFORE MOVING THEM. At 1440 the sidebar was 240 and the rail
304, leaving main 896px. Walked down in 8px steps in Chromium watching
the nav labels for a wrap: nothing wrapped or clipped even at 180, so the
limit was never the type — it is how cramped the league pills look three
across, and 208 is the last width where they still breathe. The rail
keeps more, at 280, because its content is prose rather than labels and
it is the one that gets ugly first.

Main gains 56px: 896 -> 952 at 1440.

The width lives in a token because it is written in three places — the
two-column shell, the three-column shell, and the breakpoint where the
rail drops below the content. Two of those three are easy to miss, and a
shell whose columns disagree is the bug that once put main in the
sidebar's track and rendered the whole shop as a stub.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _strip_comments(src):
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


BODY = _strip_comments(CSS)


def test_both_widths_are_tokens():
    assert "--sidebar-w:" in BODY and "--rail-w:" in BODY


def test_they_are_declared_where_the_census_can_see_them():
    """The first draft put both on one line in a `:root` of their own,
    4,500 lines into the file. test_chroma's token census reads
    declarations with `^\s*--name:` — one per line — so to it they were
    referenced and never defined, which is the shape of the bug that
    census exists to catch (a token deleted while rules still use it).

    It was right twice over: tokens scattered through a stylesheet are
    tokens nobody can find. They live with --topbar-h now, which is where
    the other layout token already was."""
    i = CSS.index("--topbar-h:")
    block = CSS[i - 200:i + 700]
    assert "--sidebar-w:" in block and "--rail-w:" in block, \
        "the shell widths drifted away from the layout tokens"
    for tok in ("--sidebar-w", "--rail-w"):
        assert re.search(rf"^\s*{tok}:", CSS, re.M), \
            f"{tok} is not declared one-per-line; the census cannot see it"


def test_no_shell_column_hardcodes_a_width():
    """The three places the shell's columns are declared must all read
    the token, or two of them drift and the layout disagrees with itself
    at exactly one breakpoint."""
    found = 0
    for m in re.finditer(
            r"([^\n{}]*\.shell[^\n{}]*)\{([^}]*?grid-template-columns:([^;]+);)",
            BODY):
        sel, cols = m.group(1).strip(), m.group(3)
        # `body.walled .shell` is the paywalled page: one column, no
        # sidebar to size. It has no business in this check and swept in
        # on the first draft of it.
        if "walled" in sel or "minmax(0, 1fr)" == cols.strip():
            continue
        found += 1
        assert "var(--sidebar-w)" in cols, f"{sel}: {cols}"
    assert found >= 3, (
        f"only {found} shell column declaration(s) found — the three that "
        f"must agree are the two-column shell, the three-column shell, and "
        f"the breakpoint where the rail drops below")


def test_the_sidebar_is_narrower_than_it_was():
    w = int(re.search(r"--sidebar-w:\s*(\d+)px", BODY).group(1))
    assert w < 240, "the sidebar is back to its old width"
    # And not so narrow the league pills stop fitting three across. 208
    # was the measured floor; anything under 200 was visibly cramped.
    assert w >= 200, f"{w}px crowds the league pills"


def test_the_rail_is_narrower_than_it_was_but_keeps_more():
    r = int(re.search(r"--rail-w:\s*(\d+)px", BODY).group(1))
    s = int(re.search(r"--sidebar-w:\s*(\d+)px", BODY).group(1))
    assert r < 304, "the rail is back to its old width"
    assert r > s, "the rail carries prose and must stay wider than the nav"


def test_the_comments_do_not_still_quote_the_old_number():
    """Five comments described the shell as `240px`. A record that
    contradicts the code is worse than no record."""
    for stale in ("first column is 240px wide",
                  "skip .shell — its 240px rail",
                  "`.shell` is `240px minmax(0,1fr)`",
                  "main down to a 240px stub"):
        assert stale not in CSS, f"a comment still says: {stale}"
    # ONE 240px STAYS, and it is not a stale claim: "Measured at 1280:
    # sidebar 1039px, main 240px" records what a past LAYOUT BUG looked
    # like. Rewriting a measurement because a token moved would destroy
    # the evidence the comment exists to keep. The first draft of this
    # test grepped every line and flagged it, which is the wrong lesson
    # to teach the next person who reads a number in a comment.
    assert "Measured at 1280: sidebar 1039px, main 240px" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
