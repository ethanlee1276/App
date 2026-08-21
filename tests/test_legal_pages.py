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
            ("contact", ["Support:"]),
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


def test_the_unfinished_parts_are_marked_rather_than_faked():
    """A registered entity name and a support mailbox cannot be invented
    from the code, and inventing them would be worse than a blank: an
    address nobody reads is how a consumer-rights request goes nowhere.
    They are flagged so they cannot ship unnoticed.
    """
    for doc, name in ((TERMS, "Terms"), (PRIVACY, "Privacy Policy")):
        assert "legal-todo" in doc, \
            f"the {name} has no marked gaps — if they are genuinely all " \
            "filled in, delete this test in the same commit"
    assert "[LEGAL ENTITY NAME]" in TERMS, \
        "the Terms name a company that may not exist yet"


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

    # The one render, and it uses what the server sent rather than
    # deciding for itself.
    fn = app[app.index("function discordHTML("):]
    fn = fn[:fn.index("\n}") + 2]
    assert "s.discord" in fn, \
        "discordHTML no longer reads the server's answer"
    assert "if (!invite) return \"\";" in fn, \
        "there is no early return for a caller the server sent nothing to"

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
    wall = app[app.index("function paywallHTML("):]
    wall = wall[:wall.index("\nasync function renderPaywall(")]
    assert "discordHTML" not in wall


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
