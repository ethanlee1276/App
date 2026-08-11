"""The accent set is one system, not four hex values that happen to coexist.

Measured before the pass, in OKLCH:

    token     C        H       uses
    brand     0.1704    76.4
    warn      0.1704    76.4   75     byte-identical to brand
    good      0.1654   155.2
    bad       0.1933    23.0
    cyan      0.0245    84.6    4     not cyan, and not dead
    plum      0.0222    84.6    1     not plum either

Three findings, only one of which is about chroma:

* `--warn` was the same hex as `--brand` in both themes. That is CORRECT
  per §1 of the redesign decisions — amber means "a condition is live or
  material", and the active nav item is such a condition — but written as
  two independent values it would silently split the first time either
  was edited. It is an alias now.
* `--cyan` is named for a hue this palette deliberately removed — it
  measures C 0.024 at hue 84.6, a warm near-neutral. It is NOT dead: four
  rules use it. This file's author deleted it on a broken `grep -c`
  pipeline that printed an empty count, which is why
  `test_every_var_reference_resolves` now exists.
* The three real accents spanned C 0.165 to 0.193. `--bad` was the most
  saturated AND the least legible (Lc 36), which is incoherent: it shouted
  loudest while being hardest to read. Equal chroma makes green, amber and
  red read as equal-weight siblings and leaves lightness to carry
  contrast, which is the dimension contrast actually depends on.

Run directly: `python3 tests/test_chroma.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contrast as ct                                          # noqa: E402
import make_icon as mi                                         # noqa: E402
import palettefit as pf                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

#: The semantic set. Every one of these encodes a meaning rather than
#: decorating, so they must carry equal visual weight.
ACCENTS = ("good", "warn", "bad")


def test_the_accents_share_one_chroma_step():
    """Unequal chroma makes one meaning shout over another for the same
    magnitude of information."""
    chromas = [pf.srgb_to_oklch(mi.token(t))[1] for t in ACCENTS]
    assert max(chromas) - min(chromas) < 0.005, dict(zip(ACCENTS, chromas))


def test_they_are_still_different_hues():
    """Equalising chroma must not have quietly equalised the colours. If
    green and red converge the encoding is gone."""
    hues = [pf.srgb_to_oklch(mi.token(t))[2] for t in ACCENTS]
    for i, a in enumerate(hues):
        for b in hues[i + 1:]:
            sep = abs(a - b) % 360
            assert min(sep, 360 - sep) > 40, hues


def test_warn_is_an_alias_and_cannot_silently_split_from_brand():
    """INVERTED 2026-08-11 with the brand itself: the alias existed
    because the old brand WAS amber ("amber is ONE colour", §1). The NEW
    LOOK brand is violet — a violet warning is a category error — so
    warn now owns its amber outright, and the pin flips: warn must NEVER
    resolve to the brand again."""
    assert mi.token("warn") != mi.token("brand"), \
        "warn is riding the violet brand — warnings have gone purple"
    L, C, H = pf.srgb_to_oklch(mi.token("warn"))
    assert 45 <= H <= 95, f"warn drifted off amber (hue {H:.0f})"


def test_both_themes_carry_the_alias():
    """The light theme is a separate block, and a fix applied to one half
    of a two-theme palette is half a fix. Since the split, that means:
    BOTH themes declare their own --warn hex after the old alias lines,
    so neither can fall back to the violet brand."""
    vals = [v.strip() for v in re.findall(r"--warn:\s*([^;]+);", DECLS)]
    # Cascade order: the old aliases still exist upstream and LOSE; the
    # two WINNING declarations (dark layer, then light layer) are hexes.
    assert len(vals) >= 2 and vals[-1].startswith("#") and vals[-2].startswith("#"), vals


def test_the_token_reader_follows_an_alias():
    """Aliasing dropped `warn` out of contrast.audit() silently, because
    audit swallows ValueError to skip tokens a theme does not define. A
    measurement quietly covering one thing fewer is the worst failure
    mode available here."""
    pairs = {r["ink"] for r in ct.audit()}
    assert "warn" in pairs, sorted(pairs)


def test_an_alias_chain_terminates_rather_than_hanging():
    css = ":root { --a: var(--b); --b: var(--c); --c: var(--a); }"
    try:
        mi.token("a", css)
    except ValueError as exc:
        assert "too deep" in str(exc), exc
    else:
        raise AssertionError("a cycle resolved to something")


#: Tokens set at runtime on an element rather than declared in :root.
#: Every one is written by app.js per card, so it is absent from the
#: stylesheet by design.
RUNTIME_TOKENS = {"--grade-color", "--profile-grad"}


def test_every_var_reference_resolves():
    """Deleting a token that is still referenced leaves the rules using it
    with no colour at all, and nothing about the page announces it.

    This exists because it happened: `--cyan` was removed from both themes
    on the strength of a `grep -c` pipeline that failed and printed an
    empty count, taking four live rules with it. A token census is cheap;
    trusting a count you did not read is not.
    """
    used = set(re.findall(r"var\((--[A-Za-z0-9_-]+)", DECLS))
    declared = set(re.findall(r"^\s*(--[A-Za-z0-9_-]+):", DECLS, flags=re.M))
    missing = used - declared - RUNTIME_TOKENS
    assert not missing, f"referenced but never defined: {sorted(missing)}"


def test_the_runtime_tokens_are_actually_written_by_the_page():
    """An allowlist that stops being true turns this test into a hole."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    for tok in RUNTIME_TOKENS:
        assert f"{tok}:" in app, tok


def test_the_misnamed_neutral_is_flagged_rather_than_silently_kept():
    """--cyan is a warm near-neutral. Keeping a wrong name without saying
    so is how the next reader trusts it."""
    L, C, H = pf.srgb_to_oklch(mi.token("cyan"))
    assert C < 0.05, C
    i = CSS.index("--cyan:")
    assert "no longer has" in CSS[max(0, i - 500):i]


def test_the_accents_still_clear_the_contrast_ratchet():
    """A chroma move changes lightness contrast slightly. The ladder is
    the constraint the palette answers to, not the other way round."""
    from tests.test_contrast import BASELINE, SLACK
    for ink in ACCENTS + ("brand",):
        for g in ct.GROUNDS:
            if (ink, g) not in BASELINE:
                continue
            got = abs(ct.lc(mi.token(ink), mi.token(g)))
            assert got >= BASELINE[(ink, g)] - SLACK, (ink, g, got)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
