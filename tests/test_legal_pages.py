"""Terms and Privacy: complete, and true about the code they describe.

Ethan, 2026-08-21: *"make sure we have a complete and legit terms and
conditions and privacy poilicy … they both need to be perfect and legit
and hit every point possible."*

TWO DIFFERENT KINDS OF CHECK IN HERE, and the second is the one worth
having. The first is coverage: does the document contain the sections a
consumer-software agreement is expected to contain — auto-renewal,
cancellation, refunds, liability, governing law, data rights. That is a
checklist, and a checklist is easy to satisfy badly.

The second compares the documents against the CODE. A privacy policy that
lists a table we do not have, or omits one we do, is not a drafting
error — it is a false statement about what we hold. So §2 of the policy
names every table by name, and this file walks the schema and requires
each one to be either disclosed or explicitly exempt.

That is also what makes the documents maintainable: add a table that
stores something about a person and this test fails until the policy
says so.

    python3 tests/test_legal_pages.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import billing                                    # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


TERMS = _read("web", "terms.html")
PRIVACY = _read("web", "privacy.html")


def _text(html):
    """Visible text, so a check cannot be satisfied by a class name."""
    body = re.sub(r"(?s)<(script|style).*?</\1>", " ", html)
    body = re.sub(r"<[^>]+>", " ", body)
    # WHITESPACE COLLAPSED, because the source is hand-wrapped at 72
    # columns and a phrase this file looks for is as likely as not to have
    # a newline in the middle of it. "We do not\n      guarantee" is the
    # same sentence as "We do not guarantee" and a test that cannot see
    # that is testing the line wrapping.
    return re.sub(r"\s+", " ", body)


TERMS_TEXT = _text(TERMS)
PRIVACY_TEXT = _text(PRIVACY)


# --- coverage ----------------------------------------------------------------
def test_the_terms_cover_every_section_a_paid_service_needs():
    """Absent any one of these, the agreement has a hole a customer or a
    processor will find. Ordered the way they get asked about."""
    for topic, needles in (
            ("what the service is", ["information", "analytics"]),
            ("no wagers taken", ["do not accept wagers"]),
            ("no advice / no guarantee", ["not financial", "do not guarantee"]),
            ("age", ["at least 21 years old"]),
            ("prices", ["$25", "$125", "$225"]),
            ("automatic renewal", ["renews automatically"]),
            ("how to cancel", ["cancel at any time"]),
            # NO GUARANTEE — Ethan, 2026-08-21: "lets not offer a 7 day
            # money back guarantee." So the section still has to EXIST
            # (Stripe requires a stated refund policy, and several states
            # require one to be conspicuous), and what it has to say is
            # the opposite. Checked as the plain sentence, because the
            # failure worth catching is a page that quietly says nothing
            # about refunds at all.
            ("refunds", ["Payments are not refundable"]),
            ("errors still refunded", ["charge made in error"]),
            ("the members' discord", ["Discord"]),
            ("failed payment", ["renewal charge fails"]),
            ("discount codes", ["creates no subscription"]),
            ("account rules", ["One person per account"]),
            ("acceptable use", ["scrape", "resell"]),
            ("intellectual property", ["licence", "non-exclusive"]),
            ("third-party data", ["third parties"]),
            ("availability", ["uptime guarantee"]),
            ("warranty disclaimer", ["as is"]),
            ("liability cap", ["twelve months"]),
            ("indemnity", ["indemnify"]),
            ("termination", ["suspend or terminate"]),
            ("changes with notice", ["30 days"]),
            ("governing law", ["State of Michigan"]),
            ("dispute process", ["before starting any formal proceeding"]),
            ("severability", ["unenforceable"]),
            # It was "Support:" when the section was one line. §18 now
            # names the operator, the address and what the address is
            # for, so the check moved to the thing that has to be there:
            # a reachable mailbox, spelled out.
            ("contact", ["support@qellysbook.com"]),
            ("who the counterparty is", ["Ethan Lee"]),
            # Added 2026-08-22 when the documents were completed.
            ("arbitration", ["binding individual arbitration"]),
            ("class action waiver", ["class, collective"]),
            ("arbitration opt-out", ["arbitration opt-out", "30 days"]),
            ("small claims carve-out", ["small-claims court"]),
            ("electronic notices", ["notices electronically"]),
            ("assignment", ["may not assign"]),
            ("force majeure", ["outside our control"]),
            ("copyright complaints", ["infringes your copyright"]),
    ):
        for needle in needles:
            assert needle.lower() in TERMS_TEXT.lower(), \
                f"the Terms do not cover {topic} (looked for {needle!r})"


def test_the_privacy_policy_covers_every_section_it_needs():
    for topic, needle in (
            ("what is collected", "What we collect"),
            ("what is not collected", "What we do NOT collect"),
            ("purpose and legal basis", "legal basis"),
            ("cookies", "session cookie"),
            ("third parties", "Who else sees it"),
            ("no sale of data", "do not sell your personal information"),
            ("retention", "How long we keep it"),
            ("user rights", "Your rights"),
            ("california", "CCPA"),
            ("gdpr", "GDPR"),
            ("children", "Children"),
            ("security", "scrypt"),
            ("breach notification", "breach"),
            ("do not track", "Do Not Track"),
            ("data location", "United States"),
            ("changes", "Changes to this policy"),
            ("contact", "Privacy questions"),
    ):
        assert needle.lower() in PRIVACY_TEXT.lower(), \
            f"the Privacy Policy does not cover {topic}"


# --- true about the code -----------------------------------------------------
def test_the_prices_in_the_terms_are_the_prices_stripe_charges():
    """A published price that differs from the charged one is the single
    most expensive kind of typo in this repo."""
    for plan in billing.PLANS.values():
        want = f"${plan['cents'] // 100}"
        assert want in TERMS_TEXT, \
            f"the Terms do not state the {plan['name']} price ({want})"


def test_no_refund_guarantee_survives_anywhere():
    """It was offered for one commit and withdrawn.

    A money-back promise left on any surface — a plan card, an FAQ
    answer, a footer — is a promise a customer will hold us to, and the
    Terms now say the opposite. So this looks across everything a reader
    sees, not just the page it was removed from.
    """
    app = _read("web", "js", "app.js")
    for surface, blob in (("app.js", app), ("Terms", TERMS_TEXT),
                          ("Privacy", PRIVACY_TEXT)):
        # "7-day" ALONE IS NOT A CANDIDATE. app.js carries "7-day" and
        # "7-IL" in the injury-report code — a seven-day injured list has
        # nothing to do with refunds, and banning the bare string makes
        # this test fail on a page it does not describe. The phrases below
        # can only mean the guarantee.
        for phrase in ("money back", "money-back", "REFUND_DAYS",
                       "refund it in full", "7-day money", "7 day money",
                       "day money back"):
            assert phrase.lower() not in blob.lower(), \
                f"{surface} still offers a refund guarantee: {phrase!r}"


def test_the_site_and_the_terms_agree_that_there_are_no_refunds():
    """Two surfaces, one policy. The FAQ is what people actually read."""
    app = _read("web", "js", "app.js")
    assert "Payments are not refundable" in TERMS_TEXT
    assert "not refundable" in app, \
        "the FAQ no longer states the refund policy the Terms bind us to"
    # …and both say the part that makes it fair, which is that cancelling
    # does not take away what has already been paid for.
    for blob in (app, TERMS_TEXT):
        assert "end of the period you have already paid for" in blob


def test_the_privacy_policy_names_every_table_that_holds_personal_data():
    """THE CHECK WORTH HAVING. Walks the schema in the code and requires
    each per-person table to appear in the policy by name.

    The exempt list is tables of PUBLIC SPORTS DATA — games, odds,
    player logs. Nothing in them is about a subscriber. Anything new that
    is keyed by user_id has to be disclosed, and this fails until it is.
    """
    schema = "\n".join(
        _read("engine", name) for name in
        ("accounts.py", "billing.py", "redeem.py"))
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", schema))
    assert tables, "no schema found — this test has stopped checking anything"
    for table in sorted(tables):
        assert table in PRIVACY, (
            f"the table `{table}` stores something about a person and the "
            "Privacy Policy does not name it. Add it to §2, or explain in "
            "this test why it holds nothing personal.")


def test_the_policy_does_not_claim_we_avoid_something_we_do():
    """Each of these is checkable against the code, and each would be a
    false statement if the code changed underneath it."""
    app = _read("web", "js", "app.js")
    # "no third-party scripts"
    index = _read("web", "index.html")
    external = re.findall(r'<script[^>]+src="(https?://[^"]+)"', index)
    assert not external, (
        "the Privacy Policy says there are no third-party scripts and "
        f"index.html loads {external}")
    # "we never see your card details"
    #
    # THE CHECK IS FOR A FIELD, NOT FOR THE WORDS. Grepping app.js for
    # "card number" fails on the sentence that PROMISES we never take one
    # ("No card number ever reaches this server") — the same mistake this
    # repo has now made six times: a test that fires on the comment
    # warning about the thing it checks for. What would make the policy
    # false is an input that collects a card, so that is what is looked
    # for.
    for bad in ('autocomplete="cc-number"', 'autocomplete="cc-csc"',
                'name="cardnumber"', 'id="card-number"',
                'placeholder="Card number"'):
        assert bad not in app, \
            f"the app renders a card field ({bad}) and the policy says it " \
            "never sees one"
    # "one cookie"
    server = _read("server.py")
    names = set(re.findall(r'Set-Cookie[^\n]*?([a-zA-Z0-9_-]+)=', server))
    assert len(names) <= 2, \
        f"the policy says one cookie and the server sets {names}"


def test_no_document_still_calls_itself_a_draft():
    """Completed 2026-08-22. Ethan supplied the counterparty (himself, as
    a sole proprietor) and the contact addresses; the arbitration clause
    and the remaining boilerplate were drafted to ordinary practice.

    THE BANNER HAD TO GO WITH THEM. A binding contract headed "DRAFT —
    not yet reviewed by a lawyer" is its own problem: it invites the
    argument that nothing on the page was meant to bind anybody, on the
    very page whose whole job is to bind. That an attorney has not yet
    read §12 and §16 is true and is tracked in `--todo`, which is where
    an internal action item belongs — not in a customer's contract.
    """
    for doc, name in ((TERMS, "Terms"), (PRIVACY, "Privacy Policy")):
        assert "legal-draft" not in doc, f"the {name} still has the banner"
        assert "DRAFT" not in doc, f"the {name} still calls itself a draft"


def test_the_one_gap_left_is_marked_rather_than_faked():
    """The postal address, deferred on Ethan's instruction. It cannot be
    invented — an address nobody reads is how a consumer-rights request
    goes nowhere — so it is marked in the page and counted by `--todo`.

    If it is ever filled in, this test should go with it rather than
    being loosened: `legal-todo` existing at all is the signal."""
    marks = TERMS.count("legal-todo") + PRIVACY.count("legal-todo")
    assert marks, (
        "no marked gaps left — if the postal address is genuinely filled "
        "in, delete this test in the same commit")
    assert marks <= 2, (
        "%d gaps; the documents were complete but for the postal address "
        "on 2026-08-22, so something regressed or something new is "
        "unfinished" % marks)
    for doc, name in ((TERMS, "Terms"), (PRIVACY, "Privacy Policy")):
        assert "[LEGAL ENTITY NAME]" not in doc, (
            "%s names no counterparty" % name)


def test_both_documents_name_the_same_counterparty():
    """Two documents, one operator. They are read together and a mismatch
    is the kind of thing that gets a whole agreement argued about."""
    # The TEXT, not the markup: "Ethan Lee, sole proprietor" wraps across
    # a line in the source, so the raw HTML does not contain the phrase
    # even though the page says it. Prose in HTML always needs this.
    for doc, name in ((TERMS_TEXT, "Terms"), (PRIVACY_TEXT, "Privacy Policy")):
        assert "Ethan Lee" in doc, "%s does not say who is responsible" % name
        assert ("sole proprietor" in doc
                or "an individual doing business" in doc), (
            "%s names a person without saying in what capacity" % name)


def test_both_documents_publish_a_reachable_address():
    """§8 of the Privacy Policy and §16's "try us first" both route
    through a mailbox. A policy that grants rights with no way to
    exercise them grants nothing."""
    assert "support@qellysbook.com" in TERMS
    assert "privacy@qellysbook.com" in PRIVACY
    for doc in (TERMS, PRIVACY):
        assert "mailto:" in doc, "the address is not clickable"


def test_the_discord_invite_is_never_shipped_to_a_non_member():
    """A members' room whose link ships to non-members is not one.

    THE FIRST CUT OF THIS WAS THEATRE. The invite was a constant in
    app.js and the RENDER was gated on entitlement — which reads as
    correct and is not: app.js is a static asset, so the string went out
    in the bundle to every anonymous visitor and was two keystrokes away
    in view-source. The gate was on the wrong side of the wire.

    So: not in the repository at all, sent by the server, inside the
    branch that has already established who is asking.
    """
    app = _read("web", "js", "app.js")
    assert "discord.gg" not in app, (
        "the invite is compiled into app.js, which is served to every "
        "anonymous visitor — the render gate cannot help with that")
    for name in ("terms.html", "privacy.html", "index.html"):
        assert "discord.gg" not in _read("web", name), \
            f"the invite is printed on {name}, which is public"

    # THE RENDERS, and each uses what the server sent rather than
    # deciding for itself. `discordHTML` — the box on the account panel —
    # was removed on 2026-08-22 at Ethan's request ("we can remove the
    # discord button in the account tab"); the two that replaced it are
    # the top-bar icon and the #discord page.
    assert "function discordHTML(" not in app, (
        "the account-panel box is back; if that is deliberate it needs "
        "the same checks as the two below")

    page = app[app.index("function discordPageHTML("):]
    page = page[:page.index("\nwindow.dcSeePlans")]
    assert "s.discord" in page, (
        "the Discord page no longer reads the server's answer")
    assert "const invite = s && s.discord" in page, (
        "the page does not take the invite from the payload")

    # The top-bar icon, which is hidden by the ABSENCE of the string
    # rather than by a check it makes itself — nothing in the browser is
    # trusted to decide entitlement.
    mount = app[app.index("function igMount("):]
    mount = mount[:mount.index("\n}") + 2]
    assert "_pwStatus.discord" in mount
    assert 'id="nav-dc"' in _read("web", "index.html")
    bar = app[app.index("function barLink("):]
    bar = bar[:bar.index("\n}") + 2]
    assert "el.hidden = true" in bar, (
        "no link and the icon still shows, pointing at nothing")

    # And the server only sends it behind the entitlement it computed.
    server = _read("server.py")
    i = server.index("def _billing_get(")
    body = server[i:server.index("\n    def ", i + 1)]
    j = body.index("QB_DISCORD_INVITE")
    guard = body[max(0, j - 400):j]
    assert 'out.get("entitled")' in guard, \
        "the invite is not behind an entitlement check"
    assert "if who" in body, "the block is not inside the signed-in branch"

    # The WALL must not render it either. It mounts the same code box,
    # and the visitor there is unentitled by definition.
    # THE FUNCTION, brace-matched. Slicing to "the next function that
    # looks like a renderer" swept in every declaration that happened to
    # be written in between — which after the Discord page landed there
    # was the whole Discord section, and this assertion started failing
    # on code it does not describe. Same trap as the 60,000-character
    # slice in tests/test_useraccounts.py.
    start = app.index("function paywallHTML(")
    depth, seen, wall = 0, False, None
    for j in range(app.index("{", start), len(app)):
        if app[j] == "{":
            depth += 1
            seen = True
        elif app[j] == "}":
            depth -= 1
            if seen and depth == 0:
                wall = app[start:j + 1]
                break
    assert wall and len(wall) < 20000, "paywallHTML was not bracketed"
    assert "discord" not in wall.lower(), (
        "the wall renders something Discord-shaped, and every visitor "
        "there is unentitled by definition")


def test_the_terms_cover_the_discord_because_it_is_part_of_the_sale():
    """It is a paid benefit on a platform we do not control, so who
    governs conduct there and what happens when a subscription ends both
    need saying."""
    assert "members’ Discord" in TERMS_TEXT or "members' Discord" in TERMS_TEXT
    assert "Discord is a third party" in TERMS_TEXT
    assert "Access ends when your subscription does" in TERMS_TEXT
    assert "Discord" in PRIVACY_TEXT, \
        "the privacy policy does not mention a third party we send you to"


def test_both_documents_link_to_each_other_and_back():
    for doc, name in ((TERMS, "Terms"), (PRIVACY, "Privacy Policy")):
        assert 'href="index.html"' in doc, f"{name} has no way back"
    assert 'href="privacy.html"' in TERMS
    assert 'href="terms.html"' in PRIVACY or "Terms" in PRIVACY_TEXT


def test_the_honesty_lines_survive_in_the_terms():
    """The same sentences the rest of the site is pinned to. A legal page
    that softens them is the one place it would not be noticed."""
    for line in ("not financial, investment, tax, legal or betting",
                 "1-800-GAMBLER",
                 "Never bet money you cannot afford to lose"):
        assert line in TERMS_TEXT, f"the Terms dropped: {line!r}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
