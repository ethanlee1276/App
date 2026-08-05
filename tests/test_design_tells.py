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


def _strip_js(text: str) -> str:
    """JS with block and line comments removed, for negative assertions.
    A comment that explains why a pattern is wrong necessarily contains the
    pattern."""
    import re as _re
    text = _re.sub(r"/\*.*?\*/", "", text, flags=_re.S)
    return _re.sub(r"^\s*//.*$", "", text, flags=_re.M)
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


def test_there_is_no_radius_left_to_have_steps():
    """This used to assert three distinct radius steps — 4/5/10 — as the fix
    for an audit that found fourteen values in use (1,2,3,4,6,7,8,9,10,11,
    12,13,16). Three beat fourteen.

    Night Form retires the question: radius 0 everywhere, spec §3.3, so a
    rounded container cannot be reintroduced by picking a number at all.
    The tokens stay defined because ~90 rules reference them; they just
    resolve to nothing.

    50% survives on purpose. An avatar mask, a status dot and a score ring
    are GRAPHICS, not containers, and squaring them is not what "no rounded
    cards" meant."""
    for token in ("--radius-sm", "--radius", "--radius-lg"):
        assert re.search(rf"{token}:\s*0\s*;", CSS), f"{token} is not 0"
    body = _strip(CSS) if "_strip" in globals() else re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)
    stray = sorted({v for v in re.findall(r"border-radius:\s*([^;}]+)", body)
                    if v.strip() not in ("0", "50%")})
    assert not stray, f"rounded containers are back: {stray}"


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
# --- fewer, larger ----------------------------------------------------------
#
# MEASURED 2026-08-02 across five boards at 1280px and 390px: four tiles,
# every value 30px, every column 307px — a dominance ratio (largest value /
# median value) of exactly 1.000 on 10 of 10 boards. None of them was the
# answer. After: 1.773 mean, and 0 of 10 boards flat.


def test_the_recommended_tiles_have_one_lead():
    """Four numbers at one size means the reader has to weigh all four to
    find out which one the page is about."""
    i = APP.index("const tiles = [")
    block = APP[i:i + 1600]
    assert block.count("lead: true") == 1, "exactly one tile leads"


def test_the_lead_is_the_bets_count_and_it_comes_first():
    """The page is called Recommended and the question it is opened with is
    "what am I betting tonight". Not props analyzed, which is how much was
    considered to get there."""
    i = APP.index("const tiles = [")
    block = APP[i:i + 1600]
    first = block.index('k: "Recommended bets"')
    assert first < block.index('Props analyzed')
    assert "lead: true" in block[first:first + 120]


def test_the_lead_column_is_wider_than_the_others():
    """Composition, not just type. Equal columns were half of why no tile
    read as the answer, and auto-fit could only ever produce equal ones."""
    body = _strip_comments(CSS)
    assert "#stats { grid-template-columns: 1.7fr 1fr 1fr 1fr; }" in body


def test_the_lead_layout_never_touches_the_shared_stats_class():
    """`.stats` is used by eleven containers — the Record page's eight KPI
    rows, the game panel, and more — carrying anything from three to five
    tiles. Pinning it to four tracks pushed the Record page's fifth tile
    onto a second row, where it read as an orphaned box on desktop AND on
    the phone. Every rule for the Recommended lead is scoped to #stats,
    which is that one container.
    """
    body = _strip_comments(CSS)
    i = body.index(".stats { display: grid;")
    assert "auto-fit" in body[i:i + 160], "the shared grid must stay auto-fit"
    # And no lead rule may be written against the bare class.
    for sel in (".stats > .tile.lead", ".stats > .tile:not(.lead)"):
        assert sel not in body, f"{sel} leaks the lead layout to every user"


def test_the_lead_value_is_two_ramp_steps_above_the_rest():
    body = _strip_comments(CSS)
    assert "#stats > .tile.lead .v { font-size: var(--fs-4xl); }" in body
    assert "#stats > .tile:not(.lead) .v { font-size: var(--fs-2xl);" in body


def test_no_new_type_token_was_invented_for_it():
    """The item says a composition change, not a token change — and reaching
    for a bigger font is exactly how you dodge doing the composition."""
    body = _strip_comments(CSS)
    assert "--fs-5xl" not in body


def test_the_phone_lead_takes_its_own_row():
    """Two equal columns would put the answer beside a supporting number at
    the same width, which is the shape this layout exists to stop."""
    body = _strip_comments(CSS)
    i = body.index("@media (max-width: 760px)")
    nxt = body.index("@media", i + 10)
    block = body[i:nxt]
    assert "#stats { grid-template-columns: repeat(3, 1fr)" in block
    assert "grid-column: 1 / -1" in block
    # The shared class keeps its own two-column phone grid.
    assert ".stats { grid-template-columns: repeat(2, 1fr); gap: 10px; }" in block


def test_the_narrow_labels_reserve_both_their_lines():
    """"Suggested exposure" wraps in a narrow column and its number then sat
    17px below the other two, so the row of context read as a staircase."""
    body = _strip_comments(CSS)
    assert "#stats > .tile:not(.lead) .k { min-height: 2.9em; }" in body


def test_the_phone_rules_live_beside_the_rule_they_must_beat():
    """A second breakpoint further up the file lost silently to this one and
    the phone grid stayed at two columns while the new rule said three."""
    body = _strip_comments(CSS)
    assert "@media (max-width: 719px)" not in body


# --- the cascade collision that put the box back ----------------------------
def test_the_tile_is_not_in_the_shared_card_rule():
    """§6.6 says a tile has no background and no border box — just a single
    vertical rule between columns. That rule is declared at the top of the
    stylesheet; ~950 lines later `.card, .game-card, .tile, .stat, .topplay`
    re-added `background` and `border: 1px` at the SAME specificity, and
    being later it won. Every tile on the site had a box.

    The visible symptom was on the Record page: `.stats > .tile:first-child`
    strips only the LEFT border, so the ROI tile sat in a three-sided box
    whose bottom edge ran 2px under its own sub-line — inside
    `overflow: hidden`, which read as the text being cut off.
    """
    body = _strip_comments(CSS)
    i = body.index(".card, .game-card")
    rule = body[i:body.index("{", i)]
    assert ".tile" not in rule, "the shared card rule silently re-boxes .tile"


def test_the_tile_does_not_clip_its_own_text():
    """`overflow: hidden` was left behind when the tile's radial wash was
    removed. Nothing clips to a tile any more, and a text block that
    silently truncates is worse than one that pushes its box taller."""
    body = _strip_comments(CSS)
    i = body.index(".tile {")
    assert "overflow: hidden" not in body[i:body.index("}", i)]


# --- a name in a number's column --------------------------------------------
def test_the_verdict_column_clips_instead_of_running_over_the_price():
    """.rl-proc holds a two-word verdict in most tables and a Polymarket
    trader handle in one — which can be a 42-character wallet address, in a
    fixed 90px track. Without min-width:0 the grid item refuses to shrink
    below its content and the name renders straight across the price and the
    P&L. Measured at up to 225px of overhang."""
    body = _strip_comments(CSS)
    i = body.index(".rl-proc {")
    rule = body[i:body.index("}", i)]
    for prop in ("min-width: 0", "overflow: hidden", "text-overflow: ellipsis"):
        assert prop in rule, prop


def test_the_polymarket_table_widens_that_column_rather_than_ellipsizing_a_wallet():
    """Clipping alone turned "0x3DFb…eea1" into "0x3…", which identifies
    nobody — the last four characters are how a wallet is recognised and
    they are exactly what an ellipsis eats."""
    body = _strip_comments(CSS)
    assert ".pm-rows .rl-row" in body
    rule = body[body.index(".pm-rows .rl-row"):]
    rule = rule[:rule.index("}")]
    assert "grid-template-columns" in rule
    assert 'class="card pm-rows"' in APP


def test_a_wallet_shaped_name_is_shortened_whichever_field_it_arrived_in():
    """Polymarket returns the address in `name` for traders who never set a
    display name, so `name || shortWallet(wallet)` took the branch that
    skips shortening and rendered all 42 characters."""
    assert "function traderLabel(" in APP
    assert "looksLikeWallet" in APP
    # And nothing still takes the old un-shortened branch. Stripped of
    # comments first: the paragraph explaining WHY that branch was wrong
    # quotes it, and a naive search finds the explanation and calls it the
    # defect. That exact mistake cost real time on a :nth-of-type rule.
    assert "name || shortWallet(" not in _strip_js(APP)


def test_the_phone_row_gives_the_flexible_track_to_the_name_not_the_price():
    """A media query adds no specificity, so `.pm-rows .rl-row` (two
    classes) beat the phone's `.rl-row` (one) and imposed the desktop
    six-column template on a five-area layout: the 1fr column computed to
    0px and the trader name rendered on top of the price. Matching the
    specificity is the fix.

    And within the phone template the flexible track is proc, not odds: a
    price is three characters and never flexes, while a handle is the only
    thing here whose length is unbounded."""
    body = _strip_comments(CSS)
    i = body.index("@media (max-width: 760px)")
    block = body[i:body.index("@media", i + 30)]
    assert ".rl-row, .pm-rows .rl-row {" in block, \
        "the phone template loses to the Polymarket override"
    rule = block[block.index(".rl-row, .pm-rows .rl-row {"):]
    cols = rule[rule.index("grid-template-columns:"):rule.index(";")]
    # proc is the third area in ". date proc odds ." — third track flexes.
    assert "20px auto minmax(0, 1fr) auto 72px" in cols, cols


def test_a_long_handle_breaks_on_a_phone_instead_of_running_over_the_price():
    """`white-space: normal` alone will not break "monkeymashingkeyboard"
    or a wallet address — they are single unbreakable tokens, and they
    overflowed the track intact."""
    body = _strip_comments(CSS)
    i = body.index("@media (max-width: 760px)")
    block = body[i:body.index("@media", i + 30)]
    j = block.index(".rl-proc {")
    rule = block[j:block.index("}", j)]
    assert "overflow-wrap: anywhere" in rule
    # And it must not ALSO clip: a phone has no hover to reveal a title.
    assert "overflow: visible" in rule


def test_the_projection_legend_names_the_dot_it_is_actually_beside():
    """A legend's whole job is saying which marker is which, and this one
    was painted from a different token than the markers.

    `.legend .proj::before` read var(--brand) while the dot it labels reads
    var(--text) — and since --brand and --warn are the same amber, the
    legend rendered TWO amber bullets for a track carrying one amber dot
    and one bone dot. Anyone matching them up got the projection and the
    line backwards. Caught on a phone screenshot, not by a test.

    Pinned as an identity between the marker and its swatch, so a future
    palette change cannot separate them again."""
    body = _strip_comments(CSS)

    def token_of(selector):
        """The token that PAINTS this selector.

        Scans every rule the selector appears in, because the dots share a
        geometry rule (`.proj-dot, .line-dot { position… }`) that carries
        no colour at all — taking the first match found that one and
        reported the component as unpainted."""
        out, i = None, body.find(selector)
        while i != -1:
            rule = body[i:body.index("}", i)]
            m = re.search(r"(?:background|color):\s*var\((--[\w-]+)\)", rule)
            if m:
                out = m.group(1)
                break
            i = body.find(selector, i + 1)
        assert out, selector
        return out

    assert token_of(".proj-dot {") == token_of(".legend .proj::before")
    assert token_of(".line-dot {") == token_of(".legend .line::before")
    # And the two series must not be the same colour as each other, or the
    # legend is useless however consistent it is.
    assert token_of(".proj-dot {") != token_of(".line-dot {")


def test_the_two_projbar_series_resolve_to_different_hexes():
    """Consistent tokens are not enough: --brand and --warn are literally
    the same amber, so two DIFFERENT token names can still paint one
    colour. The dots have to be distinguishable on the screen."""
    def hex_for(token, block):
        m = re.search(rf"{token}:\s*(#[0-9A-Fa-f]{{3,8}})", block)
        return m.group(1).lower() if m else None

    body = _strip_comments(CSS)
    # The dark theme block is the :root default in this sheet.
    root = body[body.index(":root"):body.index("}", body.index(":root"))]
    proj, line = hex_for("--text", root), hex_for("--warn", root)
    assert proj and line, (proj, line)
    assert proj != line, (proj, line)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
