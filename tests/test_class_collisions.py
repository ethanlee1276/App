"""Two panels reaching for the same class name, and the later one winning.

Ethan's Record page has a splits table whose rows are a GRID — fixed
number columns are the entire reason its figures line up in a stack. On
2026-08-24 the UFC record-breakdown legend was written with the same
`.rb-row`/`.rb-dot`/`.rb-k`/`.rb-n`/`.rb-p` names and `display: flex`.
Same specificity, later in the file, so flex won. Every splits table on
the site lost its columns and packed its numbers against the left edge.

WHAT MAKES THIS WORTH A TEST FILE. Nothing threw. Nothing overflowed —
the row was still exactly as wide as its container. The full-page sweep
rendered it, measured it, found text inside it, and passed. It was
obvious in a screenshot in about a second and invisible to everything
automated, which is the combination that lets a regression ship.

So the check is on the ARRANGEMENT, not the appearance:

  1. No bare class selector may be given two different `display` values
     in two unrelated rules. That is the general form of the bug and it
     catches the next pair of names, not just this one.
  2. `.rb-row` in particular is a grid with a track list, pinned because
     it is the specific thing that broke.

Run directly: `python3 tests/test_class_collisions.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
NAKED = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


# Known and deliberate, not a collision to fix blind.
#
# `.mc-pick`/`.mc-picker`: the memecoin watchlist replaced an older
# horizontal strip of coin buttons and REUSED its class names on purpose
# — app.js says so at the render site ("Same machinery underneath").
# The watchlist's rules come later in the file, so the ones that conflict
# resolve the intended way. The superseded strip rules were never
# removed, though, and `.mc-picker .mc-pick` outranks the newer bare
# `.mc-pick` on specificity rather than order, so `flex: none` and
# `white-space: nowrap` still reach the watchlist rows.
#
# Left alone rather than tidied away: this page needs live coin data to
# render, the local fixture has none, and deleting CSS whose effect
# cannot be seen is how the bug above got written in the first place.
# Recorded here so it is written down and so the check below stays live
# for the next collision.
KNOWN = {".mc-pick", ".mc-picker"}


def _rules():
    """(context, selector, declarations) for every rule in the sheet.

    CONTEXT IS THE WHOLE POINT and the first draft dropped it. A rule
    inside `@media (max-width: 1279px)` that re-lays-out `.rail` from a
    sticky flex column into a grid of cards is the stylesheet working as
    intended; flattening the at-rules away made it look identical to two
    authors colliding. So each rule carries the at-rule prelude it sits
    under, and only rules sharing a context are ever compared.
    """
    out, stack, i = [], [], 0
    while i < len(NAKED):
        j = NAKED.find("{", i)
        if j < 0:
            break
        # close any wrappers that ended before this rule started
        seg = NAKED[i:j]
        for _ in range(seg.count("}")):
            if stack:
                stack.pop()
        sel = seg.replace("}", " ").strip()
        if sel.startswith("@"):
            stack.append(sel)
            i = j + 1
            continue
        depth, k = 0, j
        while k < len(NAKED):
            if NAKED[k] == "{":
                depth += 1
            elif NAKED[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append((" ".join(stack), sel, NAKED[j + 1:k]))
        i = k + 1
    return out


def _display(body):
    m = re.search(r"(?:^|;)\s*display:\s*([^;}]+)", body)
    return m.group(1).strip() if m else None


def test_no_bare_class_is_given_two_different_displays():
    """A single class, alone in its selector, laid out two ways.

    Only bare `.foo` selectors count. `.a .foo` and `.foo.bar` are
    deliberate overrides of a base rule and are how the stylesheet is
    meant to be written; `.foo { display: grid }` in one place and
    `.foo { display: flex }` in another is two authors who did not know
    about each other.
    """
    seen, clashes = {}, []
    for ctx, sel, body in _rules():
        disp = _display(body)
        # `none` is a hide, not a layout: a media query, a print rule or
        # a state class turning something off is the normal way to write
        # this stylesheet and has nothing to do with two panels fighting
        # over one name. Only competing layout modes are the bug.
        if not disp or disp == "none":
            continue
        for part in sel.split(","):
            part = part.strip()
            if not re.fullmatch(r"\.[\w-]+", part):
                continue
            prev = seen.get((ctx, part))
            if prev is not None and prev != disp and part not in KNOWN:
                clashes.append(f"{part}: {prev!r} vs {disp!r}")
            seen[(ctx, part)] = disp
    assert not clashes, (
        "two panels are sharing one class name — rename the newer one. "
        "This is exactly how the Record page's splits table lost its "
        "columns to the UFC legend:\n  " + "\n  ".join(clashes))
    assert any(p == ".rb-row" for _, p in seen), \
        "the splits row stopped declaring a display"


def test_the_splits_row_is_still_a_grid_with_columns():
    """The specific casualty. Its numbers line up because they are in
    tracks; as a flex row they pack left and the stack stops reading as a
    table at all."""
    rows = [b for ctx, s, b in _rules()
            if s.strip() == ".rb-row" and not ctx]
    assert len(rows) == 1, \
        f"expected one unconditional .rb-row rule, found {len(rows)}"
    assert _display(rows[0]) == "grid", \
        "the splits row is not a grid — its columns are gone"
    tracks = re.search(r"grid-template-columns:\s*([^;}]+)", rows[0])
    assert tracks, "the splits row is a grid with no track list"
    assert tracks.group(1).count("px") >= 3, \
        f"the number columns lost their fixed widths: {tracks.group(1)}"
    # FONT-RELATIVE UNITS ARE BANNED IN THIS TRACK LIST, and this is not
    # theoretical: capping the name column at `22ch` on 2026-08-24 broke
    # the alignment on the spot. `ch` and `em` resolve against the
    # font-size of the element the track is declared on, and `.rb-labels`
    # sets a smaller one for the header row — so the header computed a
    # narrower name column than the rows under it and the table stepped
    # out of line. Same shape as the collision above: a row that sizes
    # its own columns from its own type will not match its neighbours.
    for unit in ("ch", "em", "ex"):
        assert not re.search(rf"\d{unit}\b", tracks.group(1)), (
            f"the splits row sizes a column in {unit}, which resolves "
            f"against each row's own font-size: {tracks.group(1)}")


def test_the_ufc_legend_kept_its_own_names():
    """The rename, pinned so it is not quietly undone by someone tidying
    up what look like two spellings of one thing."""
    for suffix in ("row", "dot", "k", "n", "p"):
        assert f".urb-{suffix}" in NAKED, (
            f".urb-{suffix} is gone — the UFC legend is back on the "
            f"splits table's class names")
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("ufc-rb-legend")
    seg = app[i:i + 1400]
    assert 'class="rb-row"' not in seg, \
        "the UFC legend is emitting the splits table's class again"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
