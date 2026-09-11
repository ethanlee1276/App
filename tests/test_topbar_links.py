"""The two outbound icons in the top bar, and the rule that separates them.

Ethan, 2026-08-22: *"the instagram button works perfect so lets do the same
for the discord server. then we can remove the discord button in the
account tab."*

SAME SHAPE, OPPOSITE RULE, and that is the whole point of this file.

  Instagram   a public profile. Sent to everybody, signed in or not.
              Hiding it from people who have not subscribed would hide it
              from everyone who might.

  Discord     the members' room, where the picks are posted. The server
              sends the invite ONLY to a caller it has decided is
              entitled. The icon is not hidden by a check the browser
              makes — the string is simply not in the response, and that
              is the only kind of gate that survives view-source.

Both hide when there is no link. Neither invents one.

    python3 tests/test_topbar_links.py
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


def _anchor(html, el_id):
    i = html.index('id="%s"' % el_id)
    return html[html.rindex("<a", 0, i):html.index("</a>", i) + 4]


# --- both of them -----------------------------------------------------------
def test_both_icons_exist_in_the_bar():
    html = _read(HTML)
    for el_id in ("nav-ig", "nav-dc"):
        assert 'id="%s"' % el_id in html, "no %s in the top bar" % el_id


def test_the_social_links_live_in_the_drawer_not_the_topbar():
    """Ethan, 2026-08-25, circling the icon row on his phone: "clean up
    this top row. Maybe put the discord and instagram button at the
    bottom of the 3bar menu page." Outbound social links are
    destinations, not tools you reach for mid-scroll — they moved to
    the drawer's footer with LABELS, because a drawer has the room the
    icon row never did. Same ids, so igMount's server-fed wiring holds.

    The remaining row is pinned in ORDER: the things that ping you
    (bell, messages), the status stamps, then you and your display
    (account, theme) in the corner every app keeps identity in."""
    html = _read(HTML)
    foot = html[html.index('class="sb-foot"'):html.index("</aside>")]
    assert 'id="nav-ig"' in foot and 'id="nav-dc"' in foot, \
        "the social links left the drawer footer"
    assert ">\n          Instagram</a>" in foot and "Discord</a>" in foot, \
        "the drawer versions lost their labels"
    bar = html[html.index('id="nav-search"'):html.index('id="theme-toggle"')]
    assert "nav-ig" not in bar and "nav-dc" not in bar, \
        "the icons are back in the top bar"
    for a, b in [("nav-bell", "nav-msg"), ("nav-msg", "data-source"),
                 ("slate-date", "nav-acct")]:
        assert bar.index('id="%s"' % a) < bar.index('id="%s"' % b), \
            f"topbar order broke between {a} and {b}"


def test_both_are_links_and_not_buttons():
    """Middle-click, long-press and "copy link address" are what people do
    with an icon that leaves the site."""
    html = _read(HTML)
    for el_id in ("nav-ig", "nav-dc"):
        a = _anchor(html, el_id)
        assert a.startswith("<a"), "%s is not an anchor" % el_id
        assert "onclick" not in a


def test_both_open_away_without_handing_over_the_window():
    html = _read(HTML)
    for el_id in ("nav-ig", "nav-dc"):
        a = _anchor(html, el_id)
        assert 'target="_blank"' in a, el_id
        assert "noopener" in a and "noreferrer" in a, el_id


def test_both_ship_hidden():
    """An install that has configured neither must ship neither, rather
    than two icons pointing at "#"."""
    html = _read(HTML)
    for el_id in ("nav-ig", "nav-dc"):
        a = _anchor(html, el_id)
        assert re.search(r"\bhidden\b", a.split(">")[0]), el_id


def test_both_carry_a_label_for_a_screen_reader():
    html = _read(HTML)
    for el_id in ("nav-ig", "nav-dc"):
        a = _anchor(html, el_id)
        assert "aria-label=" in a, "%s is an unlabelled icon" % el_id


def test_neither_wears_link_styling_in_a_row_of_buttons():
    """An anchor among <button>s brings its own underline and link
    colour. Moved here from tests/test_instagram_link.py when the two
    icons started sharing one rule — that file looked for `.nav-ig {`
    and the selector became `.nav-ig, .nav-dc {`."""
    css = _read(CSS)
    i = css.index(".nav-ig")
    rule = css[i:css.index("}", i)]
    assert ".nav-dc" in rule, "the two icons no longer share the rule"
    assert "text-decoration: none" in rule
    assert "color: inherit" in rule


def test_hiding_them_actually_hides_them():
    """`[hidden]` loses to `.meta-ico { display: grid }` at equal
    specificity, so the attribute alone leaves the icon on screen."""
    css = _read(CSS)
    for cls in (".nav-ig", ".nav-dc"):
        assert "%s[hidden] { display: none; }" % cls in css, (
            "%s can be 'hidden' and still visible" % cls)


def test_one_function_mounts_both():
    """Two copies of "no link, no icon" is two places to get it wrong."""
    code = _code(_read(APP))
    mount = code[code.index("function igMount("):]
    mount = mount[:mount.index("\n}") + 2]
    assert mount.count("barLink(") == 2, (
        "the two icons are mounted by different code")
    assert "instagram" in mount and "discord" in mount


def test_neither_invents_a_link():
    code = _code(_read(APP))
    bar = code[code.index("function barLink("):]
    bar = bar[:bar.index("\n}") + 2]
    assert "el.hidden = true" in bar
    assert 'removeAttribute("href")' in bar
    assert "http" not in bar, "a fallback URL, which is somebody else's page"


# --- the rule that separates them -------------------------------------------
def test_the_invite_is_gated_and_the_profile_is_not():
    """The whole design, checked on the server where it is decided."""
    src = _read(SERVER)
    i_disc = src.index('out["discord"] = invite')
    i_gram = src.index('out["instagram"] = gram')

    def indent_of(pos):
        line = src[src.rindex("\n", 0, pos) + 1:pos]
        return len(line) - len(line.lstrip())

    assert indent_of(i_disc) > indent_of(i_gram), (
        "the invite is no more deeply nested than the public profile — "
        "one of them is on the wrong side of the entitlement check")
    guard = src[max(0, i_disc - 500):i_disc]
    assert 'out.get("entitled")' in guard, (
        "the Discord invite is not behind an entitlement check")


def test_the_browser_makes_no_entitlement_decision_about_the_icon():
    """If app.js decided, the answer would be in app.js — and app.js is
    served to every anonymous visitor."""
    code = _code(_read(APP))
    mount = code[code.index("function igMount("):]
    mount = mount[:mount.index("\n}") + 2]
    for word in ("entitled", "paywall", "walled"):
        assert word not in mount, (
            "igMount checks %r; the absence of the string is the gate" % word)


def test_no_invite_is_compiled_into_anything_public():
    for name in ("index.html", "terms.html", "privacy.html",
                 os.path.join("js", "app.js")):
        blob = _read(os.path.join(ROOT, "web", name))
        assert "discord.gg" not in blob, "an invite shipped in %s" % name


# --- and it is gone from the account tab ------------------------------------
def test_the_account_panel_no_longer_draws_its_own():
    code = _code(_read(APP))
    assert "function discordHTML(" not in code, (
        'Ethan: "we can remove the discord button in the account tab"')
    i = code.index("async function renderBilling(")
    body = code[i:code.index("\n}", i)]
    assert "discord" not in body.lower(), (
        "the account panel still renders something Discord-shaped")


def test_the_places_it_does_live_still_work():
    """Ethan, 2026-08-22: "we can remove the discord button in the 'my
    book' section since we have one on the top of the page."

    Second row removed, and the same rule applies as when the account
    panel's copy went: taking one away must not take the others. What is
    left is the top-bar icon and the #discord page it opens — and the
    page must stay REACHABLE, which is the thing a sidebar row was doing
    and now nothing in the markup does."""
    code = _code(_read(APP))
    assert 'barLink("nav-dc"' in code, "the top-bar icon"
    assert "function discordPageHTML(" in code, "the #discord page"
    assert '"discord"' in code and "VIEW_ORDER" in code, \
        "the view is not routable, so the icon opens nothing"
    assert '"discord"' in code[code.index("const WALL_OPEN"):
                               code.index("const WALL_OPEN") + 200], \
        "the Discord page went behind the paywall when its row was removed"


def test_the_sidebar_no_longer_carries_a_discord_row():
    html = _read(HTML)
    assert 'data-view="discord"' not in html, (
        "the sidebar row is back — the top-bar icon already does this")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
