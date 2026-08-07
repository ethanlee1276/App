"""One motion system, and every transition on the page inside it.

Measured before the pass: 25 transition declarations using **8 distinct
durations** (.12 .14 .15 .18 .2 .24 .28 .3) and **4 easings**, of which the
browser default `ease` accounted for 21.

`ease` is the wrong curve for a control answering a tap. It is symmetric —
`cubic-bezier(.25, .1, .25, 1)` — so it accelerates slowly at both ends and
nothing visibly moves for the first several frames. By fraction of the
duration elapsed:

    elapsed     ease     ease-out
       5%       3.3%      20.2%      6.1x further
      10%       9.5%      39.7%      4.2x
      20%      29.5%      68.2%      2.3x

After: **3 durations, 2 curves, 0 bare values.** The spring survives on the
one element that should overshoot.

Run directly: `python3 tests/test_motion.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()

#: Comments explain the old values, so a raw search would match the
#: reasoning rather than the code — the mistake four other tests in this
#: repo made before it was worth writing down.
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

TRANSITIONS = re.findall(r"transition:\s*([^;]+);", DECLS)

DURATIONS = ("--dur-fast", "--dur-base", "--dur-slow")
EASINGS = ("--ease-out", "--ease-spring")


def test_every_token_is_defined():
    for name in DURATIONS + EASINGS:
        assert re.search(rf"{name}:\s*\S+", DECLS), name


def test_no_transition_carries_a_bare_duration():
    """The point of the pass. Eight ad-hoc durations became three tiers,
    and a raw `.2s` in a new rule is how a fourth one gets in."""
    bad = [t for t in TRANSITIONS
           if re.search(r"(^|\s)[0-9.]+m?s\b", t) and "var(--dur" not in t]
    assert not bad, bad


def test_no_transition_carries_a_bare_easing():
    bad = [t for t in TRANSITIONS
           if re.search(r"\bease\b|cubic-bezier|\blinear\b", t)
           and "var(--ease" not in t]
    assert not bad, bad


def test_the_default_ease_is_gone_entirely():
    """21 of 25 declarations used it. It is the specific curve this pass
    exists to remove, so it gets its own check rather than relying on the
    general one above."""
    for t in TRANSITIONS:
        assert not re.search(r"(^|[\s,])ease([\s,;]|$)", t), t


def test_the_ladder_has_three_rungs_and_they_are_ordered():
    got = []
    for name in DURATIONS:
        m = re.search(rf"{name}:\s*([0-9.]+)ms", DECLS)
        assert m, name
        got.append(float(m.group(1)))
    assert got == sorted(got), got
    assert len(set(got)) == 3, got


def test_only_one_thing_overshoots():
    """A spring on everything is a toy. It belongs on the element whose
    job is to feel physical — the nav indicator — and nowhere else."""
    springy = [t for t in TRANSITIONS if "--ease-spring" in t]
    assert len(springy) == 1, springy
    i = DECLS.index("var(--ease-spring)")
    block = DECLS[max(0, i - 400):i]
    assert "nav-indicator" in block, block[-200:]


def test_the_spring_actually_overshoots():
    """If its control points get 'tidied' to something monotonic it stops
    being a spring while keeping the name, which is worse than not having
    one."""
    m = re.search(r"--ease-spring:\s*cubic-bezier\(([^)]*)\)", DECLS)
    assert m, "no spring"
    y1 = float(m.group(1).split(",")[1])
    assert y1 > 1.0, f"y1={y1} does not overshoot"


def test_the_workhorse_curve_leaves_immediately():
    """The measured claim: a decelerating curve covers far more ground in
    the first tenth of its duration than the default does. If someone
    replaces it with an ease-in the page goes back to feeling stuck."""
    m = re.search(r"--ease-out:\s*cubic-bezier\(([^)]*)\)", DECLS)
    assert m, "no ease-out"
    x1, y1, _x2, _y2 = [float(v) for v in m.group(1).split(",")]
    # Rising faster than linear at the start is what "decelerating" means.
    assert y1 > x1, f"({x1}, {y1}) accelerates instead of decelerating"


# --- reduced motion ----------------------------------------------------------
def test_reduced_motion_covers_everything_not_a_shortlist():
    """Two narrow blocks used to opt out a disclosure chevron and the
    confidence bars, leaving every other animation running. A per-element
    opt-out cannot keep pace with a stylesheet."""
    blocks = re.findall(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}",
        DECLS, flags=re.S)
    assert blocks, "no reduced-motion support at all"
    universal = [b for b in blocks if re.search(r"\*,\s*\*::before", b)]
    assert universal, "reduced motion only names specific elements"
    body = universal[0]
    assert "transition-duration" in body and "!important" in body
    assert "animation-duration" in body


def test_reduced_motion_zeroes_rather_than_removes():
    """`transition: none` never fires transitionend, so anything waiting
    on that event hangs. A near-zero duration still fires it."""
    i = DECLS.index("*, *::before")
    body = DECLS[i:DECLS.index("}", DECLS.index("}", i) + 1)]
    assert re.search(r"transition-duration:\s*\.?0*1?ms", body), body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
