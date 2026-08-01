"""The six named tells of a generated interface, pinned as tests.

"lets audit the site and app for these 4 things" — Tailwind's default
palette; Inter or system-ui everywhere with one weight and one size ramp;
every container rounded-lg border shadow-sm; icons floating in pastel
circles; perfectly even vertical rhythm; Hero → three cards → CTA band.

The audit itself was a browser measurement — count what actually RENDERS,
because the CSS source will happily claim things the cascade overrules.
What lives here is the subset that can be checked from the source: the
specific regressions found, so they cannot come back quietly.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()


def _strip_comments(src):
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


# --- 1. Tailwind's stock palette --------------------------------------------
# The rendered audit found 51 distinct colours and zero exact hits. These are
# the ramp steps that show up in generated work most often; an exact match is
# the giveaway, because nobody arrives at #0f172a by eye.
TAILWIND = {
    "slate-900": "#0f172a", "slate-800": "#1e293b", "slate-700": "#334155",
    "slate-500": "#64748b", "slate-400": "#94a3b8", "slate-200": "#e2e8f0",
    "slate-50": "#f8fafc",
    "gray-900": "#111827", "gray-800": "#1f2937", "gray-500": "#6b7280",
    "gray-200": "#e5e7eb", "gray-50": "#f9fafb",
    "indigo-500": "#6366f1", "indigo-600": "#4f46e5", "indigo-400": "#818cf8",
    "violet-500": "#8b5cf6", "violet-600": "#7c3aed", "violet-400": "#a78bfa",
}


def test_no_stock_tailwind_ramp_step_is_used_verbatim():
    # Comments are stripped: the swatch we removed is NAMED in the comment
    # explaining why it was removed, and that note is the point.
    low = "".join(_strip_comments(s).lower() for s in (CSS, APP, VIS))
    hits = [name for name, hexv in TAILWIND.items() if hexv in low]
    assert not hits, f"stock Tailwind swatches used verbatim: {hits}"


# --- 2. One face, one weight, one ramp --------------------------------------
def test_svg_labels_use_the_pages_own_face():
    """SVG <text> does not inherit the page face the way HTML does. 294
    labels across the ballpark, field and court diagrams were rendering in
    system-ui while everything around them used Instrument Sans."""
    body = _strip_comments(CSS)
    assert re.search(r"svg\s+text\s*\{[^}]*font-family:\s*var\(--font-sans\)",
                     body), "no rule gives SVG text the page's sans"


def test_a_css_rule_beats_the_presentation_attribute_it_is_overriding():
    """font-family="system-ui" written on the element is a presentation
    attribute, which CSS outranks — so the rule above is enough and the
    attributes are merely noise. This pins the direction of that fight: if
    someone ever moves it to a style= attribute, CSS loses and the fix
    silently stops working."""
    assert 'style="font-family' not in VIS
    assert "style='font-family" not in VIS


def test_numbers_inside_the_diagrams_take_the_mono_like_numbers_elsewhere():
    body = _strip_comments(CSS)
    assert re.search(r"svg\s+text\.num[^{]*\{[^}]*var\(--font-mono\)", body)
    # ...and the selector is not decorative: something wears the class.
    assert '<text class="num"' in VIS, \
        "svg text.num matches nothing — the rule is dead code"


# --- 3. Every container the same rounded/border/shadow ----------------------
def test_radii_come_from_the_three_tokens_and_not_from_fourteen_guesses():
    """The audit found 1,2,3,4,6,7,8,9,10,11,12,13 and 16px all in use.
    Nobody picks both 9 and 10 and 11 — that is accretion, and accretion is
    what unconsidered looks like up close. Container radii use the tokens.
    Values at or below 4px are graphics (bar caps, sparkline ends), and
    999/50% is a pill or a dot; both keep their own."""
    body = _strip_comments(CSS)
    stray = set()
    for m in re.finditer(r"border-radius:\s*([^;}]+)", body):
        for tok in re.findall(r"(\d+(?:\.\d+)?)px", m.group(1)):
            v = float(tok)
            if 4 < v < 900:
                stray.add(v)
    assert not stray, (
        f"hardcoded container radii still in the stylesheet: {sorted(stray)} "
        "— use var(--radius) or var(--radius-lg)")


def test_the_inline_styles_in_the_renderer_obey_the_same_three_steps():
    """Half the stray radii were not in the stylesheet at all — they were
    style="" attributes on inputs and selects built in JavaScript, which is
    where a stylesheet audit will never look."""
    stray = set()
    for src in (APP, VIS):
        for m in re.finditer(r"border-radius:\s*(\d+(?:\.\d+)?)px", src):
            v = float(m.group(1))
            if 4 < v < 900:
                stray.add(v)
    assert not stray, f"inline container radii in the renderer: {sorted(stray)}"


def test_the_three_steps_are_actually_distinct():
    for token, value in (("--radius-sm", "4px"), ("--radius", "5px"),
                         ("--radius-lg", "10px")):
        assert re.search(rf"{token}:\s*{value}", CSS), f"{token} moved"


# --- 5. Perfectly even vertical rhythm --------------------------------------
def test_section_spacing_is_not_hand_tuned_inline_on_every_heading():
    """55 headings carried style="margin-top:Npx" at ten different values —
    0, 4, 8, 14, 16, 18, 20, 22, 24, 26. Ten values is not a rhythm and it
    is not a system; at those magnitudes they read identically, which is
    exactly the flat, even wallpaper the audit was looking for."""
    bad = re.findall(r'class="section-title[^"]*"\s+style="[^"]*margin', APP)
    bad += re.findall(r'style="[^"]*margin[^"]*"\s+class="section-title', APP)
    assert not bad, f"{len(bad)} section headings still tune their own margin"


def test_the_gap_before_a_new_section_is_bigger_than_the_gap_inside_one():
    """Density contrast is the whole point: a reader should be able to see
    where one section ends without reading a word of it."""
    body = _strip_comments(CSS)
    tops = re.findall(r"\.section-title\s*\{[^}]*margin-top:\s*(\d+)px", body)
    assert tops, "no .section-title margin-top survives in the stylesheet"
    assert max(int(t) for t in tops) >= 30, (
        f"section headings sit {tops} from what precedes them — not enough "
        "air to read as a break")


def test_a_heading_can_still_opt_out_when_it_directly_follows_its_own_lede():
    body = _strip_comments(CSS)
    assert ".section-title.tight" in body
    assert "section-title tight" in APP, "the escape hatch is never used"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
