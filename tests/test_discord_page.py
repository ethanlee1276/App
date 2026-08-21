"""The members' Discord: one page, three states, and one thing it must
never hand out.

Ethan, 2026-08-21, with a render: *"how exactly are we linking people the
discord? i say once someone makes an account then makes an account, the
first thing we should do is give them the link to join the discord server
… also we should add a discord tab or something so if someone doesnt join
immedietly, they still have the option to join later. i do wanna add the
main porpouse of this discord server is for me too select and pick out
picks i think are winners."*

THE THREE STATES

  welcome    Just paid. The toast, the eyebrow, and the invite.
  member     Came back to the tab weeks later. Same page, no confetti.
  visitor    Has not subscribed. The same page as a SALES page: what is
             inside, and a button to the plans where the join button goes.

THE ONE RULE. `s.discord` arrives on the status payload or it does not
arrive at all — the server sends it only to a caller it has decided is
entitled. web/js/app.js must never carry an invite of its own, because
app.js is a static asset served to every stranger who loads the site, and
the Discord is where the picks that people are paying for get posted.
Putting the invite in this file would be giving the product away in the
one place nobody would think to look for the leak.

    python3 tests/test_discord_page.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")
HTML = os.path.join(ROOT, "web", "index.html")
CSS = os.path.join(ROOT, "web", "css", "styles.css")


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


# --- the rule ---------------------------------------------------------------
def test_no_invite_is_written_into_the_script_every_stranger_downloads():
    """Not a hypothetical: `QB_DISCORD_INVITE` exists precisely so that
    the link lives in the environment and can be rotated with a config
    line and a restart."""
    src = _read(APP)
    for m in re.finditer(r"discord\.(gg|com)/[A-Za-z0-9]", src):
        raise AssertionError(
            "an invite in app.js at offset %d: %r"
            % (m.start(), src[m.start() - 80:m.start() + 40]))


def test_the_page_takes_the_invite_from_the_server_or_draws_none():
    body = _code(_fn(_read(APP), "discordPageHTML"))
    assert "s.discord" in body, (
        "the page does not read the server's answer at all")
    i = body.index("const invite = s && s.discord")
    assert i >= 0
    # Every href that could be the invite has to come from that variable.
    for m in re.finditer(r'href="\$\{escapeAttr\(([a-zA-Z_.]+)\)', body):
        assert m.group(1) in ("invite", "gram"), (
            "an outbound link from something other than the server's "
            "answer: %r" % m.group(1))


def test_a_visitor_who_has_not_paid_is_sent_to_the_plans():
    body = _code(_fn(_read(APP), "discordPageHTML"))
    assert "dcSeePlans()" in body, (
        "no way out of this page for somebody who has not subscribed")


def test_an_entitled_reader_with_no_invite_configured_is_told_so():
    """Rather than a button that goes nowhere. That state is a server
    somebody has not finished setting up, and a dead button spends the
    reader's click to say nothing."""
    body = _code(_fn(_read(APP), "discordPageHTML"))
    assert "dc-pending" in body


# --- the three states -------------------------------------------------------
def test_the_welcome_is_a_one_shot_and_the_page_is_not():
    """A welcome you can only see once is a welcome you cannot go back to.
    The page stays; the confetti is spent."""
    code = _code(_read(APP))
    assert "function dcTakeWelcome()" in code
    assert "removeItem(DC_WELCOME_KEY)" in code, (
        "the welcome is never spent, so it greets a two-year member every "
        "time they open the tab")
    body = _code(_fn(_read(APP), "discordPageHTML"))
    assert "welcome ?" in body, "nothing distinguishes the two states"


def test_the_welcome_is_armed_when_the_account_is_made():
    code = _code(_read(APP))
    auth = code[code.index("acctAuth = async function"):]
    auth = auth[:auth.index("\n};")]
    assert "dcMarkWelcome()" in auth, (
        "Ethan asked for this at account creation and nothing arms it there")
    assert 'mode === "signup"' in auth


def test_the_welcome_is_also_armed_by_a_payment_landing():
    """Signing up behind the wall and paying are two different moments,
    and the second is the one where a subscriber first has an invite to
    be given. Stripe returns them to /?paid=1#account, which is a receipt,
    not a welcome."""
    code = _code(_read(APP))
    # rindex: the first hit is the function's own declaration, and the
    # boot block that calls it is the last.
    i = code.rindex("paidReturnWait()")
    tail = code[i:i + 700]
    assert "dcMarkWelcome()" in tail and '"discord"' in tail, (
        "paying does not lead to the invite")


def test_localstorage_is_never_read_without_a_catch():
    """Private windows and blocked site data both throw on access, and an
    uncaught throw here happens during boot — which is a blank site."""
    code = _code(_read(APP))
    for m in re.finditer(r"localStorage\.(get|set|remove)Item\(DC_", code):
        head = code[max(0, m.start() - 220):m.start()]
        assert "try {" in head, (
            "an unguarded localStorage access at offset %d" % m.start())


# --- the way in -------------------------------------------------------------
def test_there_is_a_tab_and_it_points_at_a_real_view():
    html = _read(HTML)
    assert 'data-view="discord"' in html, (
        'Ethan: "we should add a discord tab or something so if someone '
        'doesnt join immedietly, they still have the option to join later"')
    assert 'id="view-discord"' in html, "the tab points at nothing"
    code = _code(_read(APP))
    order = code[code.index("const VIEW_ORDER"):]
    assert '"discord"' in order[:order.index("\n")], (
        "a routable view missing from VIEW_ORDER animates backwards")


def test_the_router_draws_it():
    """The bug that shipped twice: a view switched to but never rendered
    is a blank section, and it only shows up when somebody navigates to it
    by URL instead of by the button that rendered it first."""
    body = _code(_fn(_read(APP), "_switchViewNow"))
    assert 'if (name === "discord") renderDiscord();' in body


def test_it_is_reachable_from_behind_the_wall():
    """It is the sales page for the thing behind the wall. Blocking it
    would be blocking the pitch."""
    code = _code(_read(APP))
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", code)
    assert '"discord"' in m.group(1)


# --- what it says -----------------------------------------------------------
def test_the_page_says_what_the_server_is_for():
    """Ethan: "the main porpouse of this discord server is for me too
    select and pick out picks i think are winners"."""
    body = _fn(_read(APP), "discordPageHTML")
    assert "picks out the ones" in body and "Ethan" in body


def test_the_units_claim_is_attributed_rather_than_asserted():
    """+400 units is Ethan's own count of his own Instagram, not a figure
    this site graded. The Record page is what this site stands behind, and
    the difference has to be on the page — a performance number stated
    flatly in the site's own voice is a claim the site is making."""
    body = _fn(_read(APP), "discordPageHTML")
    i = body.index("+400 units")
    around = body[max(0, i - 400):i + 400]
    assert "his own count" in around, (
        "the figure reads as this site's, not as his")
    assert "#record" in around, (
        "the claim is made without pointing at the graded record beside it")


def test_nothing_in_the_room_panel_is_an_invented_message():
    """An illustration of a chat room is fine. Inventing posts, members
    and reaction counts to sit inside it would be inventing a track
    record — which is the one thing this whole site is built not to do."""
    code = _code(_read(APP))
    m = re.search(r"const DISCORD_ROOMS = \[(.*?)\n\];", code, re.S)
    assert m, "the panel is not built from a declared list of channels"
    rooms = m.group(1)
    # Channel names and group headings only: no sentences, no scores, no
    # counts, no player names.
    for bad in re.finditer(r"\b(\d+\.\d|OVER|UNDER|[+-]\d{2,})\b", rooms):
        raise AssertionError("a fabricated pick in the mock: %r"
                             % bad.group(0))
    body = _fn(_read(APP), "discordRoomsHTML")
    assert "aria-hidden" in body, (
        "a decorative mock read aloud to a screen reader as if it were "
        "content")


# --- the shell --------------------------------------------------------------
def test_the_page_has_styles():
    css = _read(CSS)
    for cls in ("dc-hero", "dc-main", "dc-mock", "dc-cta", "dc-grid",
                "dc-foot", "dc-toast", "sb-disc"):
        assert "." + cls in css, "unstyled: .%s" % cls


def test_the_room_panel_cannot_push_the_page_sideways():
    """A channel name is arbitrary text in a fixed column."""
    css = _read(CSS)
    rule = css[css.index(".dc-mock {"):]
    rule = rule[:rule.index("}")]
    assert "min-width: 0" in rule and "overflow: hidden" in rule


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
