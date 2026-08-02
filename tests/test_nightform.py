"""Night Form — the migrated visual language, pinned.

The redesign spec's §8 is a list of the specific things that made the site
read as generated, with the instruction: *"Treat any of them appearing in a
diff as a bug."* That is a test, not a paragraph, so it is one here.

This file guards the SHAPE of the direction. The preservation contract —
that nothing was lost while the shape changed — is `test_preservation.py`
plus `tools/inventory.mjs --diff`, and the two are deliberately separate:
one says the site still says everything it said, the other says it says it
in the new voice.

Two decisions in `docs/REDESIGN_DECISIONS.md` deliberately override the
spec and are asserted here in their overridden form, so a later pass that
reads only the spec cannot "fix" them back:

  - green and red stay on result numbers; amber narrows to live and
    material conditions
  - the venue cards keep every field and lead the Recommended page
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


CSS = _read("web", "css", "styles.css")
APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")


def _nc(css=None):
    """Comments stripped. Every rule below explains itself in a comment that
    names the thing it is banning, so an uncommented search finds its own
    documentation and passes for the wrong reason."""
    return re.sub(r"/\*.*?\*/", " ", css if css is not None else CSS, flags=re.S)


def _tokens(theme="dark"):
    body = _nc()
    if theme == "dark":
        block = body[body.index(":root {"):body.index(':root[data-theme="light"]')]
    else:
        i = body.index(':root[data-theme="light"] {')
        block = body[i:body.index("}", i)]
    return dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", block))


# --- §8, one test per anti-pattern ------------------------------------------
def test_no_rounded_containers_anywhere():
    """§8.1. 50% survives on purpose: an avatar mask, a status dot and a
    score ring are graphics, not containers."""
    stray = sorted({v.strip() for v in re.findall(r"border-radius:\s*([^;}]+)", _nc())
                    if v.strip() not in ("0", "50%")})
    assert not stray, f"rounded containers are back: {stray}"
    for token in ("--radius", "--radius-sm", "--radius-lg"):
        assert re.search(rf"{token}:\s*0\s*;", CSS), f"{token} is not 0"


def test_no_box_shadow_anywhere():
    """§8.4. Depth comes from rules and value contrast, not from a drop
    shadow under every panel."""
    stray = sorted({v.strip() for v in re.findall(r"box-shadow:\s*([^;}]+)", _nc())
                    if v.strip() != "none"})
    assert not stray, f"shadows are back: {stray}"


def test_no_gradients_in_the_chrome():
    """§8.7. The skeleton shimmer is the one survivor — it is a loading
    ANIMATION, and a flat one cannot read as motion."""
    body = _nc()
    hits = [m for m in re.findall(r"(?:linear|radial|conic)-gradient\([^;]*", body)
            if "--skeleton" not in m]
    lines = [body[:m.start()].count("\n") + 1
             for m in re.finditer(r"(?:linear|radial|conic)-gradient\(", body)
             if "skeleton" not in body[max(0, m.start() - 120):m.start()]]
    assert not lines, f"gradients at lines {lines}"


def test_the_display_face_is_not_a_default_sans():
    """§8.3. Inter, system-ui or -apple-system as the DISPLAY face is the
    single most recognisable generated-site tell."""
    fam = re.search(r"--font-display:\s*([^;]+);", CSS).group(1)
    first = fam.split(",")[0].strip().strip('"')
    assert first == "Bodoni Moda", f"display face is {first}"
    for bad in ("Inter", "system-ui", "-apple-system"):
        assert not fam.strip().startswith(bad)


def test_no_pure_white_text():
    """§8.10. #fff on near-black is the highest-contrast pairing available
    and nothing on a page of small figures needs it."""
    for theme in ("dark", "light"):
        t = _tokens(theme)
        for k in ("--text", "--text-dim", "--text-body"):
            v = t.get(k, "").strip().lower()
            assert v not in ("#fff", "#ffffff", "white"), f"{theme} {k} is white"


def test_no_emerald_and_no_violet():
    """§8.2 bans emerald as the accent and §3.1 bans violet outright. Green
    STAYS as a result colour by Ethan's call — see REDESIGN_DECISIONS.md §1
    — but not Tailwind's, and not as the brand."""
    body = _nc().lower()
    for tell in ("#22c55e", "#a78bfa", "#8b5cf6", "#6366f1"):
        assert tell not in body, f"{tell} is back in the palette"


def test_filter_chips_are_not_filled_slabs():
    """§8.9. The active scope on the Record page was a filled amber slab,
    which made the loudest thing on a page about a P&L curve the word
    "MLB"."""
    rule = re.search(r"\.rec-scope\.active\s*\{([^}]*)\}", _nc()).group(1)
    assert "background: none" in rule, "the active filter chip is filled again"
    assert "border-bottom-color" in rule, "it lost the underline"


def test_the_nav_is_labels_over_a_rule_not_a_row_of_pills():
    """§6.3. Both levels — league switcher and section nav."""
    nav = re.search(r"\.nav \{([^}]*)\}", _nc()).group(1)
    assert "background: none" in nav and "border-bottom" in nav
    ind = re.search(r"\.nav-indicator \{([^}]*)\}", _nc()).group(1)
    assert "height: 2px" in ind, "the active tab is a slab again, not a rule"
    sport = re.search(r"\.sport-btn\.active \{([^}]*)\}", _nc()).group(1)
    assert "border-bottom-color: var(--brand)" in sport


def test_stat_tiles_are_ruled_columns_not_four_equal_cards():
    """§8.6 and §6.6 — "a row of four equal KPI tiles with a big number and
    a small label" is named as an anti-pattern, and it was the shape the
    Recommended page opened with."""
    tile = re.search(r"\.tile \{([^}]*)\}", _nc()).group(1)
    assert "background: none" in tile
    assert "border: 0" in tile and "border-left" in tile


# --- the two overridden decisions -------------------------------------------
def test_green_and_red_still_carry_results():
    """REDESIGN_DECISIONS.md §1. The spec routes winning numbers through
    amber; overridden, because Ethan reads this board nightly. A later pass
    reading only the spec would revert it."""
    for theme in ("dark", "light"):
        t = _tokens(theme)
        good, bad, warn = t["--good"].strip(), t["--bad"].strip(), t["--warn"].strip()
        assert good != warn, f"{theme}: --good collapsed into the amber accent"
        assert bad != warn, f"{theme}: --bad collapsed into the amber accent"
    assert os.path.exists(os.path.join(ROOT, "docs", "REDESIGN_DECISIONS.md"))


def test_amber_is_reserved_for_live_and_material_conditions():
    """The other half of the split. If --warn and --brand diverge, amber has
    stopped being one idea."""
    for theme in ("dark", "light"):
        t = _tokens(theme)
        assert t["--warn"].strip().lower() == t["--brand"].strip().lower(), \
            f"{theme}: the accent and the condition colour drifted apart"


def test_the_venue_art_is_engraved_from_the_stylesheet():
    """The art is re-skinned through the cascade rather than by rewriting
    three drawing functions — SVG presentation attributes lose to CSS, so
    every <text>, score and label in visuals.js survives untouched. That is
    the property worth pinning: if these rules go, the art silently returns
    to team-tinted gradients."""
    body = _nc()
    assert ".stadium > ellipse" in body, "the bowl lost its engraving rule"
    assert ".stadium text, .field text" in body
    assert ".wind .stream" in body, "the wind gauge lost its engraving rule"


def test_the_live_badge_is_amber_not_red():
    """Live is a CONDITION, not a loss. The old badge was a red gradient
    lozenge, which said "bad" about a game that is merely in progress."""
    rule = re.search(r"\.status-badge\.live \{([^}]*)\}", _nc()).group(1)
    assert "var(--warn)" in rule
    assert "gradient" not in rule


def test_the_why_chips_read_as_apparatus_not_as_disabled_buttons():
    """§6.7. A grey outlined box beside a heading reads as a control
    somebody switched off — the opposite of what these are."""
    rule = re.search(r"\.why-toggle \{([^}]*)\}", _nc()).group(1)
    assert "border: 0" in rule and "background: none" in rule
    assert "color: var(--brand)" in rule
    assert ".why-toggle::after" in _nc(), "the dagger is gone"


# --- §3.4 motion, and §3.1 accent discipline --------------------------------
def test_no_entrance_animations_or_scroll_reveals():
    """§3.4 names them: "Forbidden: scroll reveals, entrance animations,
    parallax, skeleton shimmer, anything above 500ms."

    A rendered audit found 55-61 animated elements on every view — every
    card fading up 16px on a stagger, a sparkline drawing itself over 1.1s,
    a projection bar growing from zero, and 27 sparkline endpoints pinging
    forever. A betting board is read in a hurry; content that arrives late
    is content you scrolled past."""
    body = _nc()
    for gone in ("@keyframes viewIn", "@keyframes draw", "@keyframes growW"):
        assert gone not in body, f"{gone} is back"
    reveal = re.search(r"\.reveal, \.reveal\.in \{([^}]*)\}", body)
    assert reveal and "transition: none" in reveal.group(1), \
        "the staggered scroll reveal is back"
    # ALL matching blocks, not the first. These selectors appear twice — a
    # geometry rule and a motion rule — and `re.search` finds the geometry
    # one, so this asserted on source order rather than on what renders. The
    # same mistake broke a type-ramp test on `.section-title` once already.
    for dead in (".spark-pulse", ".proj-dot, .line-dot"):
        blocks = re.findall(re.escape(dead) + r"\s*\{([^}]*)\}", body)
        assert blocks, f"{dead} has no rule at all"
        assert any("animation: none" in b for b in blocks), \
            f"{dead} animates again"


def test_the_permitted_motion_survived():
    """A negative control. §3.4 PERMITS the live dot pulse and the wind
    stream, and a test that just banned every animation would pass by
    deleting the two things the spec asked to keep."""
    body = _nc()
    # Anchored on a word boundary. The loose substring form passed when the
    # rule was renamed to `livePulseGONE`, which is exactly the deletion the
    # control exists to catch.
    for name in ("livePulse", "windflow"):
        assert re.search(rf"@keyframes {name}\b", body), \
            f"the permitted {name} animation was deleted"


def test_amber_is_not_used_for_grades_stakes_or_confidence():
    """§3.1: "If a screen has more than ~8 amber elements visible, something
    is being decorated rather than encoded."

    The Recommended page measured 41. The three biggest contributors were
    all category errors against our own rule (REDESIGN_DECISIONS.md §1):
    amber marks a CONDITION as live or material, and a grade is a verdict, a
    stake is a number, and a confidence bar is a number whose LENGTH already
    says the same thing. 41 -> 21, and what is left is live games."""
    body = _nc()
    play = re.findall(r"\.grade\.play \{([^}]*)\}", body)
    assert play and all("var(--brand)" not in b and "var(--warn)" not in b
                        for b in play), "PLAY badges are amber again"
    stake = re.search(r"\.chip\.stake \{([^}]*)\}", body).group(1)
    assert "var(--brand)" not in stake, "the stake chip is amber again"
    assert "var(--warn)" not in APP[APP.index("function confMeter("):
                                    APP.index("function confMeter(") + 700], \
        "the confidence bar is amber again"


def test_the_standing_record_is_in_the_masthead():
    """§9, and Ethan asked for it directly. It reads from the SAME journal
    the Record page reads, because two renderings of one number drift and a
    masthead that disagrees with the Record page is worse than none."""
    assert 'id="standing-record"' in HTML
    assert "async function renderStandingRecord()" in APP
    fn = APP[APP.index("async function renderStandingRecord()"):]
    fn = fn[:fn.index("\nasync function renderRecord(")]
    assert "loadRecordOnce()" in fn, "it reads a second source"
    assert "no settled picks yet" in fn, \
        "an empty journal would print 0.0%, which is a claim it cannot make"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
