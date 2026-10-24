"""How long a line runs, and how far apart the lines sit.

The two halves of whether a row of text is comfortable, and both had
drifted rather than been chosen.

LEADING, measured before the pass: 13 distinct values, **19 of them spread
across six numbers between 1.5 and 1.65**. That range is below what an eye
resolves, so the variation was cost with no effect — six ways to say the
same thing, each one a decision a future reader has to wonder about.

LENGTH: six measures from 62ch to 92ch. The comfortable band for running
text tops out around 75 characters. 78ch and 92ch were past it, and the 92
sat on a section subtitle set at `--fs-sm` — the line is longest in
characters precisely because the type is smallest.

After: three leading rungs, three measures, and four documented literals
that stay off the ladder because they are not leading or not prose.

Run directly: `python3 tests/test_measure.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()

#: The comment block explains the old numbers, so a raw search finds the
#: reasoning instead of the code.
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

LEADING = ("--lh-tight", "--lh-snug", "--lh-body")
MEASURES = ("--measure-tight", "--measure", "--measure-wide")

#: Values deliberately left as literals, each for a reason that is not
#: "nobody got round to it".
ALLOWED_LEADING = {"0", "1", ".96"}


def test_every_token_is_defined():
    for name in LEADING + MEASURES:
        assert re.search(rf"{name}:\s*\S+", DECLS), name


def test_the_leading_ladder_is_ordered_and_distinct():
    got = []
    for name in LEADING:
        m = re.search(rf"{name}:\s*([0-9.]+)\s*;", DECLS)
        assert m, name
        got.append(float(m.group(1)))
    assert got == sorted(got), got
    assert len(set(got)) == 3, got


def test_the_rungs_are_far_enough_apart_to_be_worth_having():
    """The fault being repaired was six values inside 0.15. Rungs that
    land back inside that range would recreate it with tokens on."""
    vals = [float(re.search(rf"{n}:\s*([0-9.]+)", DECLS).group(1))
            for n in LEADING]
    gaps = [b - a for a, b in zip(vals, vals[1:])]
    assert min(gaps) >= 0.10, gaps


def test_no_leading_is_written_as_a_bare_ratio():
    left = set(re.findall(r"line-height:\s*([0-9.]+)\s*[;}]", DECLS))
    assert left <= ALLOWED_LEADING, left - ALLOWED_LEADING


def test_the_literals_that_stay_are_the_ones_that_should():
    """0 kills descender space under an image, 1 is a single line that
    must not grow, .96 is optical tightening on the masthead. None of the
    three is leading for a paragraph."""
    for val in ("0", "1"):
        for m in re.finditer(rf"line-height:\s*{val}\s*[;}}]", DECLS):
            head = DECLS[max(0, m.start() - 300):m.start()]
            assert "{" in head
    # .96 was the serif masthead's optical squeeze; the NEW LOOK
    # wordmark (2026-08-11) is tracked caps at exactly 1 — covered by the
    # "1" case above, in the same nowrap rule.
    i = DECLS.index("letter-spacing: .34em")
    assert "nowrap" in DECLS[i:i + 200]


# --- line length -------------------------------------------------------------
def test_no_prose_measure_is_written_as_a_bare_ch():
    """34ch is the exception: it is an ellipsis truncation width on a
    nowrap element, which is a layout bound rather than a reading
    measure."""
    left = set(re.findall(r"max-width:\s*([0-9.]+ch)", DECLS))
    assert left <= {"34ch"}, left - {"34ch"}
    # EVERY one of them, not just the first. There are two now — the
    # truncated handle and the signed-in address on the wall — and
    # checking only DECLS.index() would have let a second, unrelated
    # 34ch through on the strength of the first one's nowrap.
    n = 0
    for m in re.finditer(r"max-width:\s*34ch", DECLS):
        n += 1
        assert "nowrap" in DECLS[max(0, m.start() - 300):m.start()], (
            "a 34ch measure on wrapping prose at offset %d" % m.start())
    assert n, "the exception is allowed but nothing uses it"


def test_every_measure_sits_inside_the_readable_band():
    """This is the substantive change, not just tidying: 78ch and 92ch
    were past the point where the eye loses the start of the next line."""
    for name in MEASURES:
        m = re.search(rf"{name}:\s*([0-9.]+)ch", DECLS)
        assert m, name
        assert 45 <= float(m.group(1)) <= 75, (name, m.group(1))


def test_the_measures_are_ordered():
    got = [float(re.search(rf"{n}:\s*([0-9.]+)ch", DECLS).group(1))
           for n in MEASURES]
    assert got == sorted(got), got


def test_the_widest_measure_is_actually_used():
    """A ladder whose top rung nothing references is two tokens wearing
    three names."""
    for name in MEASURES:
        assert f"var({name})" in DECLS, name


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
