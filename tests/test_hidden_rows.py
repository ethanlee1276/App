"""The drawer's shape does not change when the sport does.

Ethan, 2026-08-22, with a screenshot of the Library group carrying two of
its six rows: *"where did all the tabs go in the library section"* — and
then, once told: *"the buttons in the menu change depending on what sport
you have selected. That can be confusing for a user since I didn't even
know that."* Then: *"or if theres a better and more professional and user
friendly way to solve that issue then do that."*

HIDDEN_VIEWS is right about WHICH rows a sport cannot serve — a Rosters
page for 134 college programs with no player feed can only ever say "no
data", and a tab that can only say that is worse than no tab. What was
wrong was removing them: a menu that silently re-flows between leagues
reads as a broken site, and the person who built it thought it was one.

So the rows stay, dimmed, and answer a tap with the reason. Same rows,
same order, same height in every sport.

    python3 tests/test_hidden_rows.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


def _block(src, decl):
    """A `const NAME = {...};` body, by brace matching.

    Not a fixed-width window. Several checks in this suite have measured
    the wrong thing because a comment grew above the line they were
    hunting for, and this file's subject is a comment-heavy map.
    """
    start = src.index(decl)
    depth, seen = 0, False
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth, seen = depth + 1, True
        elif src[i] == "}":
            depth -= 1
            if seen and not depth:
                return src[src.index("{", start) + 1:i]
    raise AssertionError(decl + " never closes")


def _fn(name):
    start = APP.index(name)
    depth, seen = 0, False
    for i in range(APP.index("{", start), len(APP)):
        if APP[i] == "{":
            depth, seen = depth + 1, True
        elif APP[i] == "}":
            depth -= 1
            if seen and not depth:
                return APP[start:i + 1]
    raise AssertionError(name + " never closes")


def _strip_strings(text):
    """Prose out, structure left. The reasons are sentences with colons
    and commas in them and would otherwise read as keys."""
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)


def hidden_views():
    raw = _block(APP, "const HIDDEN_VIEWS = {")
    out = {}
    for m in re.finditer(r"(\w+):\s*\[([^\]]*)\]", raw, re.S):
        out[m.group(1)] = re.findall(r'"([^"]+)"', m.group(2))
    return out


def hidden_why():
    raw = _block(APP, "const HIDDEN_WHY = {")
    out = {}
    for m in re.finditer(r"(\w+):\s*\{", raw):
        depth, j = 0, m.end() - 1
        while j < len(raw):
            if raw[j] == "{":
                depth += 1
            elif raw[j] == "}":
                depth -= 1
                if not depth:
                    break
            j += 1
        # Prose out first: the reasons are sentences, and one of them
        # says "§9.1 caps..." — anything scanning for `word:` has to be
        # looking at structure, not at English.
        inner = _strip_strings(raw[m.end():j])
        out[m.group(1)] = set(re.findall(r"(\w+):", inner))
    return out


# --- the rule ---------------------------------------------------------------
def test_a_row_this_sport_cannot_serve_is_dimmed_not_removed():
    """The whole change. `display: none` is what made the drawer a
    different height on every league and sent Ethan looking for a bug."""
    body = _fn("function markOffRows(")
    assert 'classList.toggle("off", off)' in body, (
        "rows are not marked, so nothing can style or intercept them")
    # The only display assignment left is the one that CLEARS a previous
    # sport's hiding, and it must set the row visible, never hidden.
    for m in re.finditer(r'style\.display\s*=\s*("[^"]*")', body):
        assert m.group(1) == '""', (
            "markOffRows still hides a row: display = %s" % m.group(1))
    assert 'display = "none"' not in _fn("function applySport("), (
        "applySport hides rows again behind markOffRows' back")


def test_every_hidden_row_has_a_reason_written_for_it():
    """DERIVED FROM HIDDEN_VIEWS, so adding a sport or a view there
    without a sentence is a failing test rather than a row that dims
    itself and then cannot say why."""
    views, why = hidden_views(), hidden_why()
    missing = []
    for sport, rows in views.items():
        for view in rows:
            # `parlays` is a sub-tab, not a drawer row; it is barred
            # elsewhere and has no button to dim. Reasons for it are
            # welcome but not required.
            if view == "parlays":
                continue
            if view not in why.get(sport, set()):
                missing.append(f"{sport}/{view}")
    assert not missing, (
        "hidden with no reason to give a reader who taps it: "
        + ", ".join(sorted(missing)))


def test_no_reason_is_written_for_a_row_that_is_not_hidden():
    """The other direction: a stale sentence for a row that came back is
    a reason nobody will ever see, and it rots quietly."""
    views, why = hidden_views(), hidden_why()
    stray = []
    for sport, rows in why.items():
        for view in rows:
            if view not in views.get(sport, []):
                stray.append(f"{sport}/{view}")
    assert not stray, "a reason for a row this sport does show: " + ", ".join(stray)


def test_a_dimmed_row_answers_the_tap_instead_of_navigating():
    """A dead button spends the reader's click to say nothing — the same
    complaint that got the Discord page its pending state. It is also the
    enforcement point: switchView would otherwise route to a view
    HIDDEN_VIEWS bars."""
    body = _fn("function bind(")
    i = body.index('if (!b.dataset.view) return;')
    j = body.index("switchView(b.dataset.view, true);")
    between = body[i:j]
    assert 'classList.contains("off")' in between and "toggleWhyRow(b)" in between, (
        "a dimmed row still falls through to switchView")


def test_tapping_a_dimmed_row_does_not_close_the_drawer():
    """FOUND IN A REAL BROWSER, not by reading this. The reason line
    rendered 320px to the left of a 390px viewport, because the generic
    "picking a page ends the interaction" listener slid the drawer out
    at the instant the answer appeared — tap, menu gone, nothing visibly
    happened. Picking a dimmed row is not picking a page."""
    body = _fn("function initMobileMenu(")
    i = body.index('closeMobileMenu("nav button")')
    head = body[:i]
    k = head.rindex('addEventListener("click"')
    assert 'classList.contains("off")' in head[k:], (
        "the drawer still closes under the reason it just opened")


def test_only_one_reason_is_open_at_a_time():
    """Every dimmed row open at once is the block of prose this
    replaced."""
    body = _fn("function toggleWhyRow(")
    assert 'querySelectorAll(".sb-why").forEach' in body
    assert "n.remove()" in body


def test_the_row_is_a_disclosure_rather_than_a_disabled_control():
    """`aria-disabled` announces "this does nothing" to a screen reader
    while the row opens the one sentence that reader most needs — and
    Playwright refused to click it for exactly that reason. The
    unavailability belongs in the description, not in a claim that the
    control is inert."""
    body = _fn("function markOffRows(")
    assert "aria-disabled" not in body, (
        "an actionable row announced as disabled")
    assert 'setAttribute("aria-expanded"' in body
    assert "b.title =" in body, "nothing carries the reason on hover"
    assert 'setAttribute("aria-controls"' in _fn("function toggleWhyRow(")


def test_switching_sports_clears_the_previous_ones_marks():
    """HIDDEN_VIEWS differs per sport and nothing else ever clears the
    class, the title or the reason line."""
    body = _fn("function markOffRows(")
    for gone in ('removeAttribute("aria-expanded")',
                 'removeAttribute("title")', "line.remove()"):
        assert gone in body, "a previous sport's %s survives the switch" % gone


# --- what it looks like -----------------------------------------------------
def test_the_dimmed_state_is_not_carried_by_colour_alone():
    """Opacity and a mark, not a hue. A reader who cannot tell the two
    greys apart still has the em dash and the reason."""
    rule = CSS[CSS.index(".sb-item.off {"):]
    rule = rule[:rule.index("}")]
    assert "opacity" in rule
    assert ".sb-item.off::after" in CSS and 'content: "—"' in CSS


def test_the_reason_line_is_styled_and_cannot_push_the_drawer_sideways():
    rule = CSS[CSS.index(".sb-why {"):]
    rule = rule[:rule.index("}")]
    for prop in ("font-size", "color", "padding"):
        assert prop in rule, "unstyled reason line: no %s" % prop
    assert "sbWhyIn" in CSS


def test_every_row_the_map_names_exists_in_the_drawer():
    """A sport hiding a view with no button is a line of config that can
    never do anything — and would hide the fact that the row it meant to
    name was renamed."""
    missing = set()
    for rows in hidden_views().values():
        for view in rows:
            if view == "parlays":
                continue
            if f'data-view="{view}"' not in HTML:
                missing.add(view)
    assert not missing, "HIDDEN_VIEWS names rows the drawer does not have: %s" % (
        sorted(missing),)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
