"""Emoji are not an icon set — design queue item 2.

The audit's complaint was not aesthetic. An emoji is a font glyph the
platform picks: a "won" tick is a different shape on iOS, Android and
Windows, it cannot take the colour of the thing it labels, and it sits on
the text baseline so it drifts every time the type ramp moves. Status marks
were the worst case, because they are the ones that carry a result.

Measured over 176 rendered pages (8 sports x 11 views x 2 widths):

    text nodes          1594 occurrences / 24 distinct  ->  506 / 13
    generated content    758 occurrences /  2 distinct  ->    0 /  0
    ----------------------------------------------------------------
    total               2352                            ->  506

TWO instrument lessons are baked into the tests below, because both were
found the hard way in this pass:

1. A census over two sports reported ZERO literal leaks while forty-two
   were rendering on the other six. Breadth is not optional.
2. A census that walks TEXT NODES cannot see `::before { content: "OK" }`.
   The two most-rendered marks on the whole site — one per reason bullet,
   on every card — hid behind that blind spot through a sweep that
   reported clean. Grep the stylesheet too.

What deliberately stays, so a later audit does not "fix" it:
  - arrows (-> in "890 -> 1 recommended") are punctuation between two
    numbers, not iconography;
  - the sport logos and the large empty-state / About-page glyphs are
    illustration at 34px, not status marks;
  - the lucky-clover chip is a tone choice, and the drawn set is
    deliberately austere.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
VIS = _read("web", "js", "visuals.js")
CSS = _read("web", "css", "styles.css")
HTML = _read("web", "index.html")


def _strip_css_comments(src):
    return re.sub(r"/\*.*?\*/", " ", src, flags=re.S)


def _strip_html_comments(src):
    """An <!-- --> comment fetches nothing, so it must not count as a
    fetch. The CSS side has been stripped since this file was written;
    the HTML side was not, and the first note explaining that PWA
    installs need https:// (mentioning the http:// they do not work on)
    failed the guard below for describing the rule it obeys."""
    return re.sub(r"<!--.*?-->", " ", src, flags=re.S)


def _lex(src):
    """Classify every character of a JS source as one of:

        code  '  "  `  //  /*

    One pass, because doing it in two does not work. A comment stripper that
    runs first eats the `//` in "https://…" and desynchronises everything
    after it; a string scanner that runs first trips over an apostrophe in a
    comment. They have to be the same state machine.

    Template literals nest: inside a backtick, `${` opens CODE again, which
    may contain another backtick. So the state is a stack, and `${` pushes a
    brace-depth counter rather than a flat flag — the flat version reported
    seventeen leaks that were not there.

    Regex literals have to be modelled too, for one concrete reason:
    escapeHtml contains /[&<>"']/g. Skip it and the `"` inside that
    character class opens a string that never closes, and everything after
    it is misclassified — which is exactly how the second draft of this
    file reported nine more leaks that were not there. Whether a `/` starts
    a regex or is division is decided by the previous significant token,
    the usual heuristic and sufficient for this source.

    Returns a list of (index, state) the length of the source.
    """
    # A `/` after any of these is a regex, not division.
    PRE = set("(,=:[!&|?{};+-*%~^") | {""}
    KW = ("return", "typeof", "case", "in", "of", "do", "else", "yield",
          "delete", "void", "instanceof", "new")

    def starts_regex(upto):
        s = upto.rstrip()
        if not s:
            return True
        if s[-1] in PRE:
            return True
        m = re.search(r"([A-Za-z_$][\w$]*)$", s)
        return bool(m and m.group(1) in KW)

    out = []
    stack = [["code", 0]]          # [kind, brace depth for ${ } tracking]
    i, n = 0, len(src)
    while i < n:
        kind = stack[-1][0]
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if kind == "//":
            if c == "\n":
                stack.pop()
                out.append((i, stack[-1][0]))
                i += 1
                continue
            out.append((i, kind)); i += 1; continue

        if kind == "/*":
            if c == "*" and nxt == "/":
                out.append((i, kind)); out.append((i + 1, kind))
                stack.pop(); i += 2; continue
            out.append((i, kind)); i += 1; continue

        if kind in ("'", '"', "`"):
            if c == "\\":
                out.append((i, kind))
                if i + 1 < n:
                    out.append((i + 1, kind))
                i += 2
                continue
            if c == kind:
                out.append((i, kind)); stack.pop(); i += 1; continue
            if kind == "`" and c == "$" and nxt == "{":
                out.append((i, kind)); out.append((i + 1, kind))
                stack.append(["code", 0]); i += 2; continue
            out.append((i, kind)); i += 1; continue

        # code
        if c == "/" and nxt == "/":
            stack.append(["//", 0]); continue
        if c == "/" and nxt == "*":
            stack.append(["/*", 0]); continue
        if c == "/" and starts_regex(src[:i]):
            j, in_class = i + 1, False
            while j < n:
                d = src[j]
                if d == "\\":
                    j += 2; continue
                if d == "[":
                    in_class = True
                elif d == "]":
                    in_class = False
                elif d == "/" and not in_class:
                    break
                elif d == "\n":
                    break            # unterminated: it was division after all
                j += 1
            for k in range(i, min(j + 1, n)):
                out.append((k, "code"))
            i = j + 1
            continue
        if c in "'\"`":
            out.append((i, "code")); stack.append([c, 0]); i += 1; continue
        if c == "{":
            stack[-1][1] += 1
        elif c == "}":
            if stack[-1][1] == 0 and len(stack) > 1:
                stack.pop()            # closes a ${ ... }
                out.append((i, stack[-1][0])); i += 1; continue
            stack[-1][1] -= 1
        out.append((i, "code")); i += 1
    return out


def _strip_js_comments(src):
    """Prose in a comment may legitimately NAME a glyph ("a check on Android
    is not the check on iOS") without rendering one, so the render-path
    assertions have to look past them."""
    return "".join(" " if k in ("//", "/*") else src[i]
                   for i, k in _lex(src))


# --- the drawn set itself ----------------------------------------------------
def test_the_icons_are_defined_in_this_repo_and_not_imported():
    """Lucide-in-a-pastel-circle is the exact tell the audit was checking
    for. Trading one recognisable stock look for another is not progress,
    and it also puts a CDN in the path of a page whose whole promise is
    that it renders with the network unplugged."""
    assert "const ICON_PATHS = {" in APP
    # Against CODE, not prose: the source comment explains why an icon
    # library was rejected, and naming the library there is the point.
    code = _strip_js_comments(APP).lower()
    css = _strip_css_comments(CSS).lower()
    for bad in ("lucide", "feather-icons", "heroicons", "font-awesome",
                "fontawesome", "material-icons", "bootstrap-icons", "phosphor"):
        assert bad not in code, f"{bad} was imported"
        assert bad not in css, f"{bad} reached the stylesheet"
        assert bad not in HTML.lower(), f"{bad} reached the page"
    # An icon font would arrive the same way a webfont does, and this page
    # is supposed to render with the network unplugged.
    shell = _strip_html_comments(HTML).lower().replace("http://www.w3.org", "")
    for host in ("http://", "https://", "//cdn.", "//unpkg", "//fonts.g"):
        assert host not in shell, f"{host} is being fetched by the page shell"


def test_every_icon_inherits_the_colour_of_what_says_it():
    """The point of drawing them. A won tick has to be able to be green and
    a lost cross red without two separate glyphs existing."""
    svg = APP[APP.index("function icon("):APP.index("function escapeHtml(")]
    assert 'stroke="currentColor"' in svg
    assert 'fill="none"' in svg
    assert "aria-hidden" in svg, "a decorative mark should not be announced twice"


def test_the_one_filled_mark_is_deliberate_and_labelled():
    """`dot` opts out of the stroke-only rule on purpose — a live indicator
    is noticed in peripheral vision, and an outline circle is not. If
    another one appears, it needs the same justification in writing."""
    paths = APP[APP.index("const ICON_PATHS = {"):APP.index("function icon(")]
    filled = re.findall(r"^\s*([a-z]+):.*?fill=\"currentColor\"",
                        paths, re.M | re.S)
    assert set(re.findall(r"(\w+):[^\n]*fill=\"currentColor\"", paths)) == {"dot"}, \
        f"unexplained filled icons: {filled}"


def test_no_call_site_asks_for_an_icon_that_does_not_exist():
    """icon() returns "" for an unknown name, so a typo deletes a status
    mark silently and the page still renders. Nothing else would catch it."""
    defined = set(re.findall(r"^\s*([a-z]+):",
                             APP[APP.index("const ICON_PATHS = {"):APP.index("function icon(")],
                             re.M))
    used = set(re.findall(r"icon\('([a-z]+)'", APP))
    assert used <= defined, f"icon() called with undefined names: {used - defined}"
    assert used, "no icons are being drawn at all"


# --- the two ways drawn markup turns back into visible text ------------------
def _leaks(src):
    return [src[:i].count("\n") + 1
            for i, kind in _lex(src)
            if kind in ("'", '"') and src.startswith("${icon(", i)]


def test_the_leak_detector_can_actually_fail():
    """A test that cannot fail is not a measurement. The four real leaks
    that shipped in the first pass of this item all looked exactly like the
    negative control below, and a scanner that mishandled nested templates
    reported seventeen more that did not exist — so pin BOTH directions."""
    assert _leaks("""const a = '${icon('warn')} nope';""")
    assert not _leaks("""const a = `${icon('warn')} fine`;""")
    # The nesting that broke the first attempt: a quoted string inside an
    # interpolation inside a template.
    assert not _leaks("""const a = `${x ? `${icon('warn')} y` : "z"}`;""")
    # A comment and a URL must not desynchronise the scan.
    assert not _leaks("""// see http://x/${icon('warn')}\nconst b = `${icon('check')}`;""")


def test_no_icon_call_sits_inside_a_string_that_cannot_interpolate():
    """`${icon('warn')}` inside a '...' or "..." is a LITERAL — the page
    shows the dollar-brace text. Four of these shipped in the first pass of
    this item and were only caught by rendering the view they lived on.
    This finds them at source level, on every view, including ones no
    fixture exercises."""
    bad = _leaks(APP)
    assert not bad, f"icon() interpolated inside a non-template string, lines {bad}"


def test_a_string_that_carries_an_icon_is_never_escaped_as_text():
    """The second leak class, and the subtler one. `sub` in gameContext
    gained an icon and was still being handed to escapeHtml at the point of
    use, so six sports rendered the raw <svg ...> as visible angle
    brackets. Escaping now happens on the DATA parts as they go in."""
    src = _strip_js_comments(APP)
    assert "escapeHtml(sub)" not in src, \
        "sub is markup now; escaping the assembled string prints the SVG"
    block = src[src.index("  let sub;"):src.index("  const art = mlb ?")]
    assert "esc(" in block, "the data parts inside sub stopped being escaped"
    assert "esc(g.attention_tier)" in block, "g.attention_tier goes in unescaped"
    # park_name moved out of `sub` and onto the card's venue line in the
    # 2026-08-11 fidelity pass — the escape obligation moved with it.
    card = src[src.index("function gameCard("):]
    card = card[:card.index("\n}")]
    assert "esc(g.park_name)" in card, "g.park_name goes in unescaped"


def test_the_icon_helper_is_not_shadowed_by_a_parameter():
    """`pillar = (icon, title, body) =>` shadowed the drawing helper for its
    whole body. Nothing broke, because that body only ever interpolated the
    parameter — but the next person to reach for a real icon inside a
    pillar would have got a silent string substitution instead."""
    src = _strip_js_comments(APP)
    for m in re.finditer(r"\(\s*icon\s*[,)]", src):
        ln = src[:m.start()].count("\n") + 1
        assert False, f"a parameter named `icon` shadows the helper at line {ln}"


# --- status marks, which the queue item said to do first ---------------------
# Every glyph the item named, plus the ones found alongside them. Checked
# against RENDER PATHS only: prose in a comment may name a glyph.
BANNED = {
    "✓": "check", "✔": "heavy check", "✅": "white check",
    "✕": "cross", "✖": "heavy cross", "✗": "ballot x",
    "✘": "heavy ballot x", "➖": "minus / push",
    "⛔": "no entry", "\U0001f534": "red circle / live",
    "\U0001f5d3": "calendar", "⚠": "warning", "\U0001f50d": "search",
    "⛰": "mountain / altitude", "\U0001f6d2": "cart / books",
    "⏳": "hourglass / pending", "\U0001f319": "moon",
    "☀": "sun", "☁": "cloud",
}


# Two slots are ILLUSTRATION, not iconography, and are allowed to hold a
# glyph: the 34px empty-state picture, and the About page's section
# pictograms (whose bodies may also quote a mark in prose — "negative
# factors get a red cross" describes what the reason list renders). A blanket
# ban would either fail here forever or push the ban into a comment where it
# stops being checked, so name the exceptions instead.
ILLUSTRATION = ('class="es-icon"', "pillar(")


def _illustrative(body, at):
    window = body[max(0, at - 400):at + 40]
    return any(marker in window for marker in ILLUSTRATION)


def test_no_status_mark_is_a_typed_character_in_the_renderer():
    found = []
    for name, src in (("app.js", APP), ("visuals.js", VIS)):
        body = _strip_js_comments(src)
        for ch, what in BANNED.items():
            for m in re.finditer(re.escape(ch), body):
                if _illustrative(body, m.start()):
                    continue
                ln = body[:m.start()].count("\n") + 1
                found.append(f"{name}:{ln} {what} ({ch!r})")
    assert not found, "status marks still typed rather than drawn: " + "; ".join(found)


def test_the_illustration_exemption_is_narrow():
    """The exemption is a hole in the test above, so measure its size. If it
    starts covering chips and status rows it has stopped being about 34px
    pictures and the ban has quietly been repealed."""
    body = _strip_js_comments(APP)
    exempt = sum(1 for ch in BANNED
                 for m in re.finditer(re.escape(ch), body)
                 if _illustrative(body, m.start()))
    assert exempt <= 6, f"{exempt} glyphs are claiming the illustration exemption"


def test_no_status_mark_survives_in_the_page_shell():
    for ch, what in BANNED.items():
        assert ch not in HTML, f"index.html still types {what}"


def test_the_stylesheet_draws_its_two_marks_rather_than_typing_them():
    """The blind spot. `content: "OK"` renders 650 times across the site and
    a text-node census sees none of it. These are masks so that
    background-color — and therefore the green/red split and the light
    theme — still drives them."""
    body = _strip_css_comments(CSS)
    for ch, what in BANNED.items():
        for m in re.finditer(r'content:\s*"([^"]*)"', body):
            assert ch not in m.group(1), f"generated content still types {what}"
    assert "--ic-check:" in CSS and "--ic-cross:" in CSS
    rule = body[body.index(".reasons li::before"):]
    rule = rule[:rule.index("}")]
    assert "mask" in rule and "var(--ic-check)" in rule
    assert "background-color: var(--good)" in rule, \
        "a mask without a background-color paints nothing at all"
    neg = body[body.index(".reasons li.neg::before"):]
    neg = neg[:neg.index("}")]
    assert "var(--ic-cross)" in neg and "background-color: var(--bad)" in neg
    # Safari is the primary target here — Ethan reads this on an iPhone.
    assert "-webkit-mask" in body, "the unprefixed mask alone drops Safari"


def test_the_stylesheet_marks_match_the_javascript_ones():
    """Two definitions of the same check is how they drift apart. If the
    geometry moves in one place it has to move in both."""
    js = re.search(r"check: '<path d=\"([^\"]+)\"", APP).group(1)
    css = re.search(r"--ic-check:.*?<path d=\"([^\"]+)\"", CSS, re.S).group(1)
    assert js == css, f"check geometry has drifted: {js!r} vs {css!r}"
    js = re.search(r"cross: '<path d=\"([^\"]+)\"", APP).group(1)
    css = re.search(r"--ic-cross:.*?<path d=\"([^\"]+)\"", CSS, re.S).group(1)
    assert js == css, f"cross geometry has drifted: {js!r} vs {css!r}"


def test_the_theme_toggle_can_hold_markup():
    """It was set with textContent, which would print the SVG source into
    the button. The switch to innerHTML is the whole reason the drawn moon
    renders at all."""
    line = [l for l in APP.splitlines() if 'icon(theme === "light"' in l]
    assert line, "the theme toggle stopped drawing its icon"
    assert "innerHTML" in line[0], "textContent would show the SVG as text"


# --- the deliberate exceptions ----------------------------------------------
def test_arrows_are_left_as_typography():
    """"890 -> 1 recommended" is punctuation between two numbers. Drawing it
    would be worse, and an audit that counts glyphs will keep flagging it,
    so the reason is written down in the source as well as here."""
    assert "→" in APP, "the arrows were converted; they are typography"
    assert "Arrows are left alone on purpose" in APP


def test_illustration_is_not_mistaken_for_iconography():
    """A 34px empty-state glyph and a sport logo are pictures, not status
    marks. They are allowed, and this records that it is a decision rather
    than an oversight."""
    body = _strip_js_comments(APP)
    assert 'class="es-icon"' in body
    assert "\U0001f3c8" in body, "the sport logos were flattened into the icon set"


def test_the_hand_drawn_art_contains_no_emoji():
    """visuals.js is the STYLE REFERENCE the queue item points at. An emoji
    inside the hand-drawn ballpark — a stadium glyph sitting on a drawn
    stadium — was the sharpest version of the tell on the whole site."""
    body = _strip_js_comments(VIS)
    strays = sorted({c for c in body if ord(c) > 0x2100 and c not in "—–·°→←"})
    assert not strays, f"emoji back inside the drawn art: {strays}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
