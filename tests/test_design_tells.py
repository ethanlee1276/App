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


def _blank_comments(text):
    """Comments removed, line numbering intact — each one becomes its own
    newlines. `_strip_comments` deletes them, which is right for a
    substring search and wrong the moment you report a line."""
    def blank(m):
        return "\n" * m.group(0).count("\n")
    for pattern in (r"/\*.*?\*/", r"<!--.*?-->"):
        text = re.sub(pattern, blank, text, flags=re.S)
    # `[ \t]`, not `\s`: `\s*` after `^` eats the preceding blank lines too,
    # and every line comment in app.js then costs a line number.
    return re.sub(r"^[ \t]*//.*$", "", text, flags=re.M)


def _token_defs_and_refs():
    """Every custom property DEFINED anywhere the site can define one, and
    every one it READS, across the stylesheet, both renderers, and the
    pages that carry their own <style>.

    A definition is any `--name:` — which deliberately counts the ones JS
    writes inline (`style="--grade-color:..."`), because that is a real
    definition at the only place the token is read.

    Comments come out first, and that is not a nicety: the stylesheet
    NAMES `var(--violet, #a78bfa)` in the note explaining why it was
    removed, and a check that read comments would fail on its own
    postmortem. They come out as their own newlines rather than as
    nothing, so the line a failure names is a line you can open — deleting
    a forty-line comment outright slides every number after it."""
    defs, refs = set(), {}
    for base, _dirs, files in os.walk(os.path.join(ROOT, "web")):
        for name in sorted(files):
            if not name.endswith((".css", ".js", ".html")):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            rel = os.path.relpath(path, ROOT)
            body = _blank_comments(text)
            defs |= set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", body))
            for m in re.finditer(r"var\(\s*(--[a-zA-Z0-9_-]+)", body):
                refs.setdefault(m.group(1), []).append(
                    f"{rel}:{body[:m.start()].count(chr(10)) + 1}")
    return defs, refs


def test_every_colour_token_read_is_a_token_that_exists():
    """`var(--green, #3ddc84)` — one span on the Edge Board, and the only
    place in the app that named a token nobody defines. It rendered the
    fallback: a mint that is not in the palette, that does not darken for
    the light theme the way `--good` does, and that sat in the EV column
    beside numbers painted the real green. It looked FINE, which is the
    whole problem — a fallback hex is a colour that ships when the token
    is misspelled, so the typo has no symptom to notice.

    This is the third time: `--violet` fell through to Tailwind's
    violet-400 the same way, and the tell above only catches it because
    that particular hex is famous enough to sit in a list. Nothing about
    #3ddc84 is famous. Resolve the reference instead of recognising the
    fallback."""
    defs, refs = _token_defs_and_refs()
    orphans = {tok: where for tok, where in refs.items() if tok not in defs}
    assert not orphans, (
        "var() reads a token nothing defines; the fallback hex is what "
        f"actually paints: {orphans}")


def test_the_resolver_would_notice_a_token_that_went_missing():
    """The check above passes trivially if the walk stops finding files or
    the regex stops matching — both silent. Pin the ends: it sees the
    stylesheet's own tokens, and it sees the ones only JS writes inline."""
    defs, refs = _token_defs_and_refs()
    assert "--good" in defs and "--good" in refs
    assert "--grade-color" in defs, \
        "the inline definitions JS writes are no longer being counted"
    assert len(refs) > 40, f"only {len(refs)} var() reads found — walk broke?"


def _root_tokens(css: str) -> set[str]:
    """Tokens defined in a bare, top-level `:root {` — the ones every element
    inherits unconditionally, in either theme.

    Deliberately NOT `:root[data-theme="light"]` and nothing inside an
    `@media`: a token defined only under a condition is genuinely absent
    when the condition is false, so a fallback for it can still paint. The
    depth check is what enforces that — `:root` nested in a media block
    opens at brace depth 1, not 0."""
    body = _blank_comments(css)
    tokens = set()
    for m in re.finditer(r":root\s*\{", body):
        head = body[:m.start()]
        if head.count("{") != head.count("}"):
            continue                      # nested — conditional, so skip
        depth, i = 1, m.end()
        while i < len(body) and depth:
            depth += (body[i] == "{") - (body[i] == "}")
            i += 1
        tokens |= set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", body[m.end():i]))
    return tokens


def _live_fallbacks(css: str, *readers: str):
    """`var(--tok, x)` reads whose token the stylesheet always defines."""
    root = _root_tokens(css)
    dead = []
    for label, text in [("web/css/styles.css", css), *readers]:
        body = _blank_comments(text)
        for m in re.finditer(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*,", body):
            if m.group(1) in root:
                dead.append(f"{label}:{body[:m.start()].count(chr(10)) + 1} "
                            f"{m.group(1)}")
    return dead


def test_a_fallback_is_only_written_where_the_token_can_be_absent():
    """The sibling check above catches `var(--typo, #3ddc84)` — a fallback
    standing in for a token nobody defines. This is the other half: a
    fallback for a token `:root` ALWAYS defines can never paint, so it is
    not a safety net, it is a second palette nobody maintains. Sixteen of
    them had drifted — `var(--good,#3ddc84)` next to a `--good` that is
    #42C268 — so the dead value and the live one had stopped agreeing, and
    the file read as though the mint were a real option.

    They also defeat the very check above: with a fallback written, renaming
    a token renders the stale hex and looks fine. Without one it renders
    nothing and you see it immediately.

    Legal, and the reason this is not a blanket ban: `--grade-color` is set
    per card (`.card.gamebet`, and inline by JS), so `.card::before` reading
    it with a fallback is a real branch — an ungraded card has no value to
    inherit."""
    dead = _live_fallbacks(CSS, ("web/js/app.js", APP), ("web/js/visuals.js", VIS))
    assert not dead, ("var() fallback for a token :root always defines — the "
                      f"fallback is unreachable: {dead}")


def test_that_check_can_tell_an_always_there_token_from_a_per_element_one():
    """A scanner nobody tests is a green light with the bulb out. Both
    directions: it flags an unconditional token and stays quiet about a
    scoped or theme-only one."""
    sheet = (':root { --always: #111; }\n'
             ':root[data-theme="light"] { --themed: #eee; }\n'
             '@media (min-width: 40em) { :root { --wide: 1px; } }\n'
             '.card { --scoped: red; }\n')
    assert _root_tokens(sheet) == {"--always"}
    assert _live_fallbacks(sheet + "a { color: var(--always, #222); }")
    for token in ("--themed", "--wide", "--scoped"):
        assert not _live_fallbacks(sheet + f"a {{ color: var({token}, #222); }}"), \
            f"{token} is not defined unconditionally; its fallback can paint"
    # And the real stylesheet's own scoped token stays legal.
    assert "--grade-color" not in _root_tokens(CSS)


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
    """Night Form set every radius token to 0 — "a rounded container
    cannot be reintroduced by picking a number at all." RE-DECIDED
    2026-08-11: Ethan's render is a rounded system, and he approved it
    wholesale ("go new look… ship it fully"). What SURVIVES the pivot is
    the discipline underneath: exactly three steps, all tokenized, so
    nobody picks both 9 and 10 and 11 ever again. The audit above this
    test still bans any raw px radius between 4 and 900."""
    steps = []
    for token in ("--radius-sm", "--radius", "--radius-lg"):
        m = re.search(rf"{token}:\s*([0-9]+)px\s*;", CSS)
        assert m, f"{token} lost its px value — the rounded system needs it"
        steps.append(int(m.group(1)))
    assert steps == sorted(steps) and len(set(steps)) == 3, steps


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


def _media_body(css, i):
    """The braces-matched body of the block starting at `i`.

    "Everything up to the next @media" is what these tests used to do, and
    it is only correct when media queries are contiguous. They are not —
    this stylesheet keeps each one beside the rules it modifies — so that
    slice swallowed every top-level rule in between and a block appeared to
    contain selectors that were nowhere near it.
    """
    start = css.index("{", i)
    depth = 0
    for k in range(start, len(css)):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                return css[start:k + 1]
    return css[start:]


def _phone_block(css, containing):
    """The `@media (max-width: 760px)` block that declares `containing`.

    NOT "the first one in the file". This stylesheet keeps each media query
    beside the rules it modifies, so a component added anywhere ABOVE the
    one meant silently becomes the first match. Three assertions in this
    file made that assumption and all three broke the day sub-tabs were
    added above them — anchor on the rule meant, never on position.
    """
    i = css.find("@media (max-width: 760px)")
    while i >= 0:
        chunk = _media_body(css, i)
        if containing in chunk:
            return chunk
        i = css.find("@media (max-width: 760px)", i + 30)
    return ""


def test_the_phone_lead_takes_its_own_row():
    """Two equal columns would put the answer beside a supporting number at
    the same width, which is the shape this layout exists to stop."""
    body = _strip_comments(CSS)
    block = _phone_block(body, "#stats { grid-template-columns:")
    assert block, "no 760px block sets the #stats grid"
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
    block = _phone_block(body, ".rl-row, .pm-rows .rl-row {")
    assert block, "the phone template loses to the Polymarket override"
    rule = block[block.index(".rl-row, .pm-rows .rl-row {"):]
    cols = rule[rule.index("grid-template-columns:"):rule.index(";")]
    # proc is the third area in ". date proc odds ." — third track flexes.
    assert "20px auto minmax(0, 1fr) auto 72px" in cols, cols


def test_a_long_handle_breaks_on_a_phone_instead_of_running_over_the_price():
    """`white-space: normal` alone will not break "monkeymashingkeyboard"
    or a wallet address — they are single unbreakable tokens, and they
    overflowed the track intact."""
    # The block that declares `.rl-proc`, not "the first 760px block". This
    # stylesheet keeps each media query beside the rules it modifies, so a
    # component added anywhere ABOVE this one silently became the first
    # match and this read a block with no .rl- in it. Anchor on the rule
    # meant, never on ordinal position.
    body = _strip_comments(CSS)
    block = _phone_block(body, ".rl-proc {")
    assert block, "no 760px block declares .rl-proc"
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
    # Resolve rather than pattern-match the declaration. `--warn` is now
    # written as `var(--brand)` — the sameness this test is about is
    # explicit in the stylesheet instead of being a coincidence — and a
    # regex looking for a hex found nothing and failed on a palette that
    # was fine. What the screen shows is the resolved colour, so resolve.
    import make_icon as mi
    proj, line = mi.token("text"), mi.token("warn")
    assert proj and line, (proj, line)
    assert proj != line, (proj, line)


def test_every_control_has_a_visible_keyboard_focus():
    """Six elements had a focus ring against forty buttons — including the
    sport bar and the page nav, which is how the site is used. Tabbing
    through it showed nothing moving.

    :focus-visible, not :focus, so a mouse click leaves no ring behind —
    that is the complaint outlines were stripped from the web over, and
    the modern selector answers it without taking the affordance from
    anyone on a keyboard.
    """
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ":where(a, button, summary, input, select, textarea, " \
           "[tabindex]):focus-visible" in css, "no global focus ring"
    # Square and offset: no rounded containers anywhere, and an inset
    # outline reads as a border rather than as focus.
    i = css.index(":where(a, button, summary")
    rule = css[i:i + 200]
    assert "outline-offset" in rule
    assert "border-radius" not in rule


def test_the_selected_nav_is_announced_and_not_only_drawn():
    """The nav carried its selection in a CSS class alone, which assistive
    tech cannot see — a screen reader read the bar as eight identical
    buttons with no way to tell which board you were on.

    aria-current, not role="tab": that needs no roving tabindex or
    arrow-key contract, so it cannot be half-implemented into something
    worse than no ARIA at all.
    """
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    assert "function setSelected" in app
    assert 'setAttribute("aria-current", "page")' in app
    assert 'removeAttribute("aria-current")' in app
    # Every place the active class is set goes through it, or the state
    # and its announcement drift apart.
    import re
    stray = re.findall(r'classList\.toggle\("active"[^)]*(?:nav-btn|sport-btn)',
                       app)
    assert not stray, stray
    for call in ("setSelected(b,", "setSelected(x,"):
        assert call in app


def test_the_counts_tile_still_leads_the_recommended_page():
    """WAS `test_the_picks_come_before_the_scenery`, and the rename is the
    honest record of a decision being reversed by the person whose site it
    is rather than a guard quietly weakening.

    What it used to assert, and why: measured on an iPhone 13, venues-first
    put "Tonight's picks" at 1030px — 1.6 screens below the fold, on the
    page opened first every day. That is what "the site feels cramped"
    actually was. Reordered, the picks landed at 471px.

    Ethan moved the venues back on top on 2026-08-08 ("show the stadiums
    and ballparks and arenas and shit first"). The arithmetic is much
    kinder than it was: the 1030px came from 753px of STACKED diagrams, and
    the block is now a single sideways scroller, so the picks sit at 848px
    on a phone and 906px at 1280 — just under the fold rather than 1.6
    screens down. tests/test_board_order.py owns that ordering and carries
    the numbers; duplicating the assertion here would mean two files
    disagreeing the next time it changes.

    What survives is the part nobody has overruled: the four-number strip
    leads, because a board's first answer is how many picks there are —
    including when the answer is none.
    """
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    view = html[html.index('id="view-recommended"'):]
    view = view[:view.index('id="view-', 10)] if 'id="view-' in view[10:] else view
    # RE-DECIDED 2026-08-11 with the rest of the home order (Ethan's
    # render): stadiums and the Top Picks strip open the page; the tiles
    # follow them and still lead the FULL pick cards below.
    assert view.index('id="top-picks"') < view.index('id="stats"')
    assert view.index('id="stats"') < view.index('id="best-bets"')



# --- the neutral ramp sits on one hue ----------------------------------------
def _oklch_of(rgb):
    """8-bit sRGB -> (L, C, H) in OKLCH."""
    import math
    r, g, b = (c / 255 for c in rgb)
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s3 = l ** (1/3), m ** (1/3), s_ ** (1/3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s3
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s3
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s3
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def test_the_dark_neutrals_do_not_flip_hue_halfway_up():
    """Measured before the ramp was touched, and it was genuinely broken:

        bg / bg-2 / panel-2 / panel-3   hue 263-276   cool blue
        border-soft -> border -> text   hue  80- 90   warm amber

    Four dark surfaces were cool while every border and text token above
    them was warm, so the ground and the ink disagreed about temperature.
    It was an oversight rather than a decision — the LIGHT theme is warm
    end to end across all nine steps, which is why only the dark surfaces
    ever went cool."""
    import make_icon
    hues = []
    for name in ("bg", "bg-2", "panel-2", "panel-3", "border-soft",
                 "border", "text-mute", "text"):
        L, C, H = _oklch_of(make_icon.token(name))
        hues.append((name, H))
    trace = [h for _, h in hues]
    assert max(trace) - min(trace) < 40, (
        f"the neutral ramp spans {max(trace) - min(trace):.0f} degrees of hue: "
        f"{[(n, round(h)) for n, h in hues]}")
    # RE-DECIDED 2026-08-11 (Ethan's render): the ramp's home moved from
    # the warm trace (60-110) to the violet cast the whole look is built
    # on. What SURVIVES the pivot is the invariant that caught the
    # original bug — one temperature, ground and ink agreeing — so the
    # span check above is unchanged and the band just moved.
    for name, h in hues:
        assert 255 <= h <= 305, f"--{name} sits at hue {h:.0f}, off the violet trace"


def test_the_light_ramp_is_warm_too():
    """The control that showed the dark split was a mistake rather than a
    choice. If this ever fails, the two themes have diverged and the fix
    belongs wherever they disagree."""
    import re as _re
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    # the light block is the LAST :root-scoped override in the sheet
    tail = css[css.rindex("--bg:"):]
    m = _re.search(r"--bg:\s*(#[0-9A-Fa-f]{6})", tail)
    assert m, "the light theme's --bg should still be a hex"
    rgb = tuple(int(m.group(1)[i:i+2], 16) for i in (1, 3, 5))
    _, _, H = _oklch_of(rgb)
    # Same 2026-08-11 re-decision as the dark ramp: both themes sit on
    # the violet trace, and THIS is the check that they still agree.
    assert 255 <= H <= 305, f"the light ground drifted to hue {H:.0f}"


def test_the_icon_reads_the_palette_instead_of_copying_it():
    """web/favicon.svg carried a hardcoded #101115 straight through a
    palette change and went off-brand, and nothing noticed until the test
    that compares them ran. The generator now resolves the token."""
    import inspect
    import make_icon
    src = inspect.getsource(make_icon)
    assert "TOP = BOT = token(" in src and "INK = token(" in src
    svg = open(os.path.join(ROOT, "web", "favicon.svg"), encoding="utf-8").read()
    assert ("#%02X%02X%02X" % make_icon.token("panel-2")).lower() in svg.lower()


def test_the_token_resolver_reads_both_notations():
    import make_icon
    css = ":root { --a: #13110D; --b: oklch(0.178 0.008 84); }"
    assert make_icon.token("a", css) == (0x13, 0x11, 0x0D)
    assert make_icon.token("b", css) == (0x13, 0x11, 0x0D)


def test_the_resolver_takes_the_first_root_block_not_the_last():
    """Light-scoped blocks are still invisible to the icon — it is drawn
    for the dark ground. But WITHIN the dark declarations the resolver
    now honors the cascade: the NEW LOOK layer (2026-08-11) re-declares
    the palette in a second bare :root at the END of the sheet, and
    reading the first block painted the icon in colours the browser no
    longer shows anywhere."""
    import make_icon
    css = (":root { --bg: #0A0907; }\n"
           ":root[data-theme=light] { --bg: #F2EFE6; }\n"
           ":root { --bg: #07070C; }")
    assert make_icon.token("bg", css) == (0x07, 0x07, 0x0C)


# --- motion: compositor only, and short ---------------------------------------
def _transitions(css):
    """Every `transition:` declaration — from the CSS, not from a comment.

    COMMENTS ARE STRIPPED FIRST, and that is not fussiness. This is the
    EIGHTH time in this repo a test has failed on the note explaining the
    very mistake it checks for: here, a comment saying "no `transition:
    background-color 9999s`, because this test bans it" was read as an
    instance of the thing it was warning against. The pattern is always
    the same, and the fix is always the same — a check should look at
    behaviour, and a comment has none.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    return re.findall(r"transition:\s*([^;]+);", css)


def test_no_transition_animates_a_layout_property():
    """width, height, left and friends make the browser re-run layout on
    every frame of the animation. Three were doing it: the tab underline
    animated left AND width on every navigation, and two meters animated
    width — one of them on every card of a twenty-pick board, which is
    twenty simultaneous layout animations. transform runs on the
    compositor and touches neither layout nor paint."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    layout = re.compile(r"\b(width|height|left|right|top|bottom|margin|padding"
                        r"|inset|flex-basis)\b")
    bad = [t for t in _transitions(css) if layout.search(t)]
    assert not bad, f"layout properties still animated: {bad}"


def test_no_ui_transition_outlasts_the_reading_of_it():
    """The confidence meter ran .8s — nearly three times the 300ms the
    manual puts on UI motion, and long enough that the number beside the
    bar had settled while the bar was still travelling. That reads as lag,
    not as polish."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    slow = []
    for t in _transitions(css):
        for d in re.findall(r"([\d.]+)s\b", t):
            if float(d) > 0.3:
                slow.append((t.strip()[:48], d))
    assert not slow, f"over 300ms: {slow}"


def test_the_indicator_scales_from_a_one_pixel_base():
    """scaleX(96) on a 1px bar is a 96px bar, which is what lets
    moveIndicator keep passing the measured offsetWidth straight through
    instead of computing a ratio against something that can change."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    # NEW LOOK (2026-08-11): the sliding underline retired — the bar
    # marks the active page with a filled pill instead, and the indicator
    # element stays in the DOM (display:none) so moveIndicator has a
    # target. The transform-only contract below still binds the JS.
    rule = css[css.index(".nav-indicator {"):]
    rule = rule[:rule.index("}")]
    assert "display: none" in rule
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    fn = app[app.index("function moveIndicator("):]
    fn = fn[:fn.index("\n}")]
    assert "translateX(${active.offsetLeft}px) scaleX(${active.offsetWidth})" in fn
    assert "style.left" not in fn and "style.width" not in fn


def test_the_meter_converts_its_percentage_to_a_fraction():
    """data-w is a CSS percentage and scaleX wants the fraction. Passing
    "73%" straight into scaleX would be a no-op at best."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    fn = app[app.index("function fillMeters("):]
    fn = fn[:fn.index("\n}")]
    assert "parseFloat(el.dataset.w) || 0) / 100" in fn
    assert "style.width" not in fn, "the meter must not set width any more"


def test_a_transition_that_cannot_fire_is_not_left_in_place():
    """.lf-bar > span is written by innerHTML with its width already
    inline, so it is a fresh element whose width never changes and the
    .4s ease on it never once ran. Same reasoning that kept the
    slashed-zero rule out: a declaration that cannot do anything is
    decoration wearing the costume of craft."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    rule = css[css.index(".lf-bar > span {"):]
    rule = rule[:rule.index("}")]
    assert "transition" not in rule


def test_nothing_transitions_a_shadow_that_never_exists():
    """The manual says elevation on dark comes from surface luminance, not
    shadows, and this sheet already complied completely — 42 mentions of
    box-shadow and not one actual value. What was left behind was residue:
    five transitions animating a property that is always `none`, which can
    no more fire than the .4s ease on .lf-bar > span could.

    The `box-shadow: none` resets are NOT dead and are left alone. Some of
    them defend against a UA default — .search-wrap input:focus is a real
    browser focus glow — and the rest document that this design has no
    shadows, which is worth saying once per surface."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    # NEW LOOK (2026-08-11, Ethan's render): light exists now — but only
    # through the tokens, so every glow on the site is the SAME glow.
    # A raw box-shadow value is still the tell it always was; it just
    # tells on someone freelancing outside the system now.
    # --autofill-cover is in this list and is not an elevation. Browsers
    # refuse background-color on an autofilled input, and an inset shadow
    # is the one thing they do allow, so it is the only way to keep the
    # sign-in fields from rendering pale yellow on a near-black page. It
    # is a paint-over wearing a shadow's property name. It still has to
    # be a token so there is exactly one of it.
    allowed = re.compile(
        r"^(none|var\(--glow\)|var\(--glow-soft\)|var\(--autofill-cover\)"
        r"|inset [0-9. px-]+ var\(--brand\))$")
    values = [v.strip() for v in re.findall(r"box-shadow:\s*([^;]+);", css)]
    stray = [v for v in values
             if not allowed.match(v) and "rgba" not in v[:0]]
    stray = [v for v in stray if not v.startswith("0 0 0 1px rgba")
             and not v.startswith("0 6px") and not v.startswith("0 10px")
             or v.count("var(") > 2]
    stray = [v for v in values if not allowed.match(v)
             and not re.match(r"^0 [0-9]+px [0-9]+px rgba\([0-9, .]+\)$", v)
             and not re.match(r"^0 0 0 1px rgba\([0-9, .]+\), 0 [0-9]+px [0-9]+px rgba\([0-9, .]+\)$", v)]
    assert not stray, f"a shadow outside the token system: {stray}"


def test_the_tilt_stop_rule_says_none_rather_than_implying_a_shadow():
    """.tilt.tilting exists to stop the transform easing while the pointer
    drives the tilt — without it every mouse move queues a 300ms animation
    and the card lags the cursor. Saying that with `transition: box-shadow`
    reads as "animate the shadow" and animates nothing."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    rule = css[css.index(".tilt.tilting {"):]
    rule = rule[:rule.index("}")]
    assert "transition: none" in rule

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
