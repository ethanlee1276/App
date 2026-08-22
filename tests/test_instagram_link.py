"""The Instagram icon in the top bar.

Ethan, 2026-08-22: *"we should add a little instagram icon at the top of
the page and if you click it, it will take you right to my instagram
page."*

THE HANDLE IS NOT IN THE REPOSITORY. It comes from `QB_INSTAGRAM` on the
box, the same source the Discord page cites, so there is one place to
change it and no dead icon on an install that has never set one. Hardcoded
in index.html it would be a second copy to forget, and a link to nowhere
on any other deployment.

IT IS DRAWN TWICE, and that is not duplication for its own sake.
`body.walled` hides the whole top bar, so behind the paywall the bar's
copy is invisible — to exactly the visitor a link to a public profile is
most worth showing. `paywallHTML` draws its own into the wall's header.

AND IT IS NOT GATED. Unlike the Discord invite, which the server sends
only to entitled callers, this is a public profile anybody can already
find. Showing it to somebody who has not subscribed is the point.

    python3 tests/test_instagram_link.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")
HTML = os.path.join(ROOT, "web", "index.html")
CSS = os.path.join(ROOT, "web", "css", "styles.css")
SERVER = os.path.join(ROOT, "server.py")


def _read(p):
    return open(p, encoding="utf-8").read()


def _code(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _fn(src, name):
    start = src.index("function " + name + "(")
    depth, seen = 0, False
    for j in range(src.index("(", start), len(src)):
        if src[j] == "{":
            depth += 1
            seen = True
        elif src[j] == "}":
            depth -= 1
            if seen and depth == 0:
                return src[start:j + 1]
    raise AssertionError(name + " never closes")


# --- where the address comes from -------------------------------------------
def test_no_handle_is_hardcoded_anywhere_in_the_web_tree():
    """One place to change it, and nothing to go stale."""
    for root, _dirs, files in os.walk(os.path.join(ROOT, "web")):
        for name in files:
            if not name.endswith((".html", ".js", ".css", ".webmanifest")):
                continue
            path = os.path.join(root, name)
            text = _read(path)
            for m in re.finditer(r"(?:www\.)?instagram\.com/[A-Za-z0-9_.]+",
                                 text):
                raise AssertionError(
                    "a hardcoded profile in %s: %r"
                    % (os.path.relpath(path, ROOT), m.group(0)))


def test_the_server_sends_it_to_everybody_and_not_only_subscribers():
    """The opposite rule to the Discord invite, on purpose. A public
    profile behind the paywall would be a link nobody who might subscribe
    ever sees."""
    src = _read(SERVER)
    i = src.index('out["instagram"]')
    head = src[:i]
    # The entitled branch closes before this runs. If it did not, the line
    # would sit inside `if out.get("entitled")`.
    gated = head.rindex('if out.get("entitled")')
    invite = head.rindex('out["discord"]')
    assert invite > gated, "this test no longer locates the gated branch"
    # Same indentation as the `if who:` block's parent, not deeper.
    line = src[src.rindex("\n", 0, i) + 1:i]
    indent = len(line) - len(line.lstrip())
    disc_line = src[src.rindex("\n", 0, invite) + 1:invite]
    assert indent < len(disc_line) - len(disc_line.lstrip()), (
        "the Instagram link is nested as deeply as the gated invite, so "
        "only paying customers are shown a public profile")


def test_the_icon_is_hidden_until_the_server_says_there_is_one():
    html = _read(HTML)
    i = html.index('id="nav-ig"')
    tag = html[html.rindex("<a", 0, i):html.index(">", i) + 1]
    assert "hidden" in tag, (
        "an install with no QB_INSTAGRAM ships an icon linking to '#'")
    assert 'href="#"' in tag, "the placeholder href is not inert"
    body = _code(_fn(_code(_read(APP)), "igMount"))
    assert "el.hidden = true" in body, (
        "nothing hides it again if the link is removed")


# --- what happens when it is clicked ----------------------------------------
def test_it_opens_away_from_the_site_without_handing_over_the_window():
    """`target=_blank` without `rel=noopener` gives the opened page a
    handle on this one through `window.opener`."""
    html = _read(HTML)
    i = html.index('id="nav-ig"')
    tag = html[html.rindex("<a", 0, i):html.index(">", i) + 1]
    assert 'target="_blank"' in tag
    assert "noopener" in tag and "noreferrer" in tag
    wall = _fn(_read(APP), "paywallHTML")
    j = wall.index("pw-ig")
    near = wall[j:j + 400]
    assert 'target="_blank"' in near
    assert "noopener" in near and "noreferrer" in near


def test_it_is_a_link_and_not_a_button_with_a_click_handler():
    """Middle-click, long-press and "copy link address" are what people
    do with an icon that leaves the site, and none of them work on a
    button."""
    html = _read(HTML)
    i = html.index('id="nav-ig"')
    assert html[html.rindex("<", 0, i):i].startswith("<a"), (
        "the top-bar icon is not an anchor")
    assert "onclick" not in html[html.rindex("<a", 0, i):html.index(">", i)]


def test_the_address_is_escaped_where_it_is_interpolated():
    """It arrives from a config file somebody typed."""
    wall = _fn(_read(APP), "paywallHTML")
    j = wall.index("pw-ig")
    near = wall[j:j + 300]
    assert "escapeAttr(status.instagram)" in near, (
        "an unescaped attribute built from configuration")


# --- both places it appears -------------------------------------------------
def test_the_wall_carries_its_own_because_it_hides_the_top_bar():
    css = _read(CSS)
    assert re.search(r"body\.walled[^{]*\.topbar[^{]*\{[^}]*display:\s*none",
                     css, re.S) or "body.walled .topbar" in css, (
        "this test assumes the wall hides the top bar; if that changed, "
        "the second icon may be redundant")
    assert "pw-ig" in _read(APP), "the wall has no Instagram link"
    assert ".pw-ig" in css, "unstyled"


def test_both_copies_point_at_the_same_configured_address():
    app = _code(_read(APP))
    assert "_pwStatus.instagram" in app or "_pwStatus && _pwStatus.instagram" in app
    assert "status.instagram" in app
    # Neither invents a fallback.
    assert not re.search(r"instagram\s*\|\|\s*[\"']http", app), (
        "a default profile is a link to somebody else's page")


def test_drawing_it_costs_no_extra_request():
    """It is decoration. A fetch of its own would be a request per page
    load for an icon."""
    body = _code(_fn(_code(_read(APP)), "igMount"))
    assert "fetch(" not in body, "the icon fetches its own configuration"


def test_it_is_mounted_when_the_status_is_refreshed():
    app = _code(_read(APP))
    check = _fn(app, "paywallCheck")
    assert "igMount()" in check, (
        "nothing calls it, so the icon never appears")


# --- the shell --------------------------------------------------------------
def test_the_anchor_does_not_wear_link_styling_in_a_row_of_buttons():
    css = _read(CSS)
    assert ".nav-ig" in css
    rule = css[css.index(".nav-ig {"):]
    rule = rule[:rule.index("}")]
    assert "text-decoration: none" in rule, (
        "an underline under an icon in the top bar")


def test_hiding_it_actually_hides_it():
    """`[hidden]` loses to any `display` rule with equal specificity, and
    .meta-ico sets `display: grid`."""
    css = _read(CSS)
    assert ".nav-ig[hidden] { display: none; }" in css, (
        "the icon is display:grid from .meta-ico, so the hidden attribute "
        "alone leaves it on screen")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
