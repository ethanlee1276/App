"""Every fantasy league link, in one place — the Account page.

Ethan, 2026-08-23: "add all the account syncs and logins for fanstasy on
the actual account page so its all together and that would make the most
sense on where that would be."

THE FAULT BEING FIXED WAS TWO FORMS FOR ONE THING. Sleeper's username
box, ESPN's league-id box and Yahoo's approval card each lived on the
Fantasy page, and each rendered a Disconnect of its own. Neither copy
redrew the other, so a league could be linked on one surface and unlinked
on another with both still showing their own idea of the state. The site
already had the rule and had written it down for sign-in — `acctStripHTML`
exists because "two forms for one thing is how a password gets typed into
the wrong one" — and leagues had simply never been held to it.

So: the FORMS live once, on Account. The Fantasy page keeps the panels it
is actually for and wears a strip naming what is linked.

The two properties worth pinning, because both are easy to undo by
accident:

  * exactly ONE element carries each connect id. `getElementById` returns
    the first match, so a second copy is not a duplicate — it is a form
    that silently writes nothing anybody is looking at. This repo has
    already paid for that once (test_organization's two `sleeper-zone`s).
  * the links render SIGNED OUT as well as in. They live in this browser
    and work without an account; an account only carries them to your
    other devices. Sending somebody from Fantasy to a sign-in wall with
    no way to link would be worse than the duplicate forms.

Run directly: `python3 tests/test_fantasy_links.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _css():
    return open(os.path.join(ROOT, "web", "css", "styles.css"),
                encoding="utf-8").read()


def _fn(src, name):
    """A function body by brace matching, past its parameter list.

    Brace matching rather than a fixed slice: `APP[i:i+400]` has produced
    nine false failures in this repo, every one of them a test that moved
    when something ABOVE it grew.
    """
    i = src.index("function " + name + "(")
    j, depth = src.index("(", i), 0
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = src.index("{", j), 0
    for k in range(start, len(src)):
        if src[k] == "{":
            d += 1
        elif src[k] == "}":
            d -= 1
            if not d:
                return src[i:k + 1]
    raise AssertionError(name + " never closes")


# --- one form, one place ------------------------------------------------------
def test_each_connect_control_has_exactly_one_home():
    """An id written twice is not a duplicate, it is a dead form: the
    handler binds to whichever copy `getElementById` reaches first, and
    typing into the other one does nothing at all."""
    app = _app()
    for one in ('id="sleeper-username"', 'id="sleeper-connect"',
                'id="espn-league-id"', 'id="espn-team-id"',
                'id="espn-connect"', 'id="yahoo-zone"'):
        assert app.count(one) == 1, f"{one} is written {app.count(one)} times"


def test_the_fantasy_page_does_not_carry_a_second_copy():
    """The whole point. If a connect card comes back here, the strip
    below is lying about where leagues are managed."""
    app = _app()
    body = _fn(app, "renderFantasy")
    for form in ("sleeperConnectHTML", "espnConnectHTML", "renderYahooZone"):
        assert form not in body, f"{form} is back on the Fantasy page"


def test_the_forms_are_reached_from_the_account_page():
    app = _app()
    links = _fn(app, "ffLinksHTML")
    assert 'id="ffl-sleeper"' in links and 'id="ffl-espn"' in links
    render = _fn(app, "renderFantasyLinks")
    for call in ("renderFflSleeper()", "renderFflEspn()", "renderYahooZone()"):
        assert call in render, f"{call} is never made"
    assert "renderFantasyLinks();" in _fn(app, "renderAccount"), (
        "the hosts are drawn and never filled")


def test_they_render_signed_out_as_well_as_in():
    """The links live in this browser and do not need an account. A
    person following "Link a league" from Fantasy while signed out must
    not land on a sign-in wall — that is a dead end, and worse than the
    duplicate forms this replaced."""
    screen = _fn(_app(), "acctScreenHTML")
    assert screen.count("${ffLinksHTML()}") == 2, (
        "the links are missing from one of the two account screens")
    signed_out = screen[screen.index("acct-hero"):]
    assert "${ffLinksHTML()}" in signed_out, "signed out has no way to link"


# --- and one way back out -----------------------------------------------------
def test_every_link_can_be_undone_where_it_was_made():
    """A connect with no disconnect is a setting somebody has to clear
    site data to change — and a disconnect on a DIFFERENT page from the
    connect is the split this commit removed."""
    app = _app()
    sl = _fn(app, "renderFflSleeper")
    assert "ffl-sleeper-off" in sl
    assert 'removeItem("ff_user")' in sl
    assert 'removeItem("ff_league")' in sl, (
        "the chosen league outlives the account that owned it")
    es = _fn(app, "renderFflEspn")
    assert "ffl-espn-off" in es
    assert "removeItem(ESPN_LEAGUE_KEY)" in es


def test_the_old_disconnect_did_not_stay_behind_on_the_panel():
    app = _app()
    assert "sleeper-disconnect" not in app, (
        "two Disconnects for one link, on two pages, neither redrawing "
        "the other")
    assert "espn-forget" not in app


def test_which_league_you_are_looking_at_stayed_on_the_page_that_lists_them():
    """Not everything moved. The league PICKER only exists once Sleeper
    has answered with your leagues, which happens on the Fantasy page —
    choosing which of your own leagues to view is a viewing choice, not
    a link."""
    panel = _fn(_app(), "renderSleeperPanel")
    assert 'id="sleeper-league"' in panel


# --- what the page that lost the forms says instead ---------------------------
def test_the_strip_names_what_is_linked_rather_than_only_pointing():
    """"Manage leagues" with no state is a page telling you to go
    somewhere and find out. The strip answers the question first."""
    strip = _fn(_app(), "ffLinkStripHTML")
    assert 'localStorage.getItem("ff_user")' in strip
    assert "ESPN_LEAGUE_KEY" in strip
    assert "switchView('account', true)" in strip, "no way across"
    assert "Link a league" in strip and "Manage leagues" in strip, (
        "the strip reads the same whether or not anything is linked")


def test_the_strip_is_on_both_of_the_fantasy_page_branches():
    """The offseason branch is the one that matters: an empty usage feed
    is exactly when somebody is drafting and wants their league."""
    body = _fn(_app(), "renderFantasy")
    assert body.count("ffLinkStripHTML()") == 2, (
        "one of the two Fantasy renders has no way across")
    head = body[:body.index("setStandaloneSource")]
    assert "ffLinkStripHTML()" in head, "the no-season branch is stranded"


def test_the_strip_is_styled_rather_than_inheriting_whatever_is_nearby():
    css = _css()
    assert ".ff-link-strip" in css
    assert ".ffl {" in css, "the account section is unstyled"


# --- the boundary this project does not cross ---------------------------------
def test_moving_the_forms_did_not_move_a_password_field_in_with_them():
    """The site takes no platform credential, and gathering every login
    onto one page is the moment that is easiest to quietly change.
    Checked by what the cards COLLECT, not by what they mention — an
    earlier version of this assertion failed on a card's own reassurance,
    "Read-only and no password"."""
    app = _app()
    links = "".join(_fn(app, n) for n in
                    ("ffLinksHTML", "renderFflSleeper", "renderFflEspn",
                     "sleeperConnectHTML", "espnConnectHTML"))
    ids = set(re.findall(r'<input id="([^"]+)"', links))
    assert ids <= {"sleeper-username", "espn-league-id", "espn-team-id"}, (
        f"the account page now collects something else: {sorted(ids)}")
    assert 'type="password"' not in links
    for cookie in ("espn_s2", "SWID", "autocomplete=\"current-password\""):
        assert cookie not in links, cookie


def test_a_link_made_here_still_rides_the_synced_profile():
    """"Connect it once" is the feature. Linking on the phone and finding
    nothing on the laptop is not connecting once — and the touch is the
    only thing that pushes it, so a move that dropped it would break the
    sync silently."""
    app = _app()
    for name in ("renderFflSleeper", "renderFflEspn"):
        body = _fn(app, name)
        assert body.count('acctTouch("fantasy")') == 2, (
            f"{name} does not push both the connect and the disconnect")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
