"""The notice for 2 November's changes, and the Terms' §5.7 written as the site works.

Ethan, 2026-11-02, "do number one too": §5.7 promised a member whose renewal
failed that they would not be cut off on the first failure, and the site has
paused access at once since 12 October. §5.7 now says so, and that Stripe
cancels the subscription when its retries run out (Ethan: that setting "was
already turned on"). It is a change that affects a member, so it waits 30
days after the email our documents promise (Terms §15); the same email tells
them the rest of 2 November. What these hold:

  * the change is the third in engine/policynotice's ORDER, armed by name,
    sent to accounts made before 3 November with a real address, in the
    same allowance and hours as the others, after them;
  * its email says what §5.7 now says and the date it takes effect for that
    account (30 days on), the two trial rules and the policy's two additions;
  * the Terms carry the new §5.7, and say when it applies to an older
    account and what applies until then, with the module's own dates;
  * the runbook arms it with the other two.

Run directly: `python3 tests/test_the_november_notice.py`
"""
import datetime as dt
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_POLICY_NOTICE", None)

from engine import accounts as A                                  # noqa: E402
from engine import policynotice as PN                             # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOON = dt.datetime(2026, 11, 4, 12, tzinfo=PN.ET).timestamp()     # Wednesday, noon Eastern
FLAT = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))  # noqa: E731


def test_it_is_the_third_change_and_goes_to_older_accounts_with_an_address():
    assert PN.ORDER == (PN.NOTICE, PN.WHOSON, PN.TRIALS) and PN.TRIALS == "2026-11-02"
    assert dt.datetime.fromtimestamp(PN.TRIALS_SINCE, PN.ET).strftime("%-d %B %Y %H:%M") == "3 November 2026 00:00"
    assert dt.datetime.fromtimestamp(PN.TRIALS_PHONE_FROM, PN.ET).strftime("%-d %B %Y") == "2 December 2026"
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(str(Path(d) / "acc.db"))
        old = int(A.create_user(conn, "old@example.com", "correct-horse-battery", confirmed=True)[1]["id"])
        new = int(A.create_user(conn, "new@example.com", "correct-horse-battery", confirmed=True)[1]["id"])
        _c, phone = A.create_phone_user(conn, "+15555550142", confirmed=True)
        conn.execute("UPDATE users SET created_at = ? WHERE id IN (?, ?)", (PN.TRIALS_SINCE - 86400, old, phone["id"]))
        conn.execute("UPDATE users SET created_at = ? WHERE id = ?", (PN.TRIALS_SINCE + 3600, new))
        conn.commit()
        assert [u for u, _e in PN.pending(conn, PN.TRIALS)] == [old], "made later read it; a phone has no address"
        os.environ[PN.ENV] = "2026-10-29,2026-11-01,2026-11-02"
        try:
            sent = []
            PN.run(conn, now=NOON, send=lambda to, s, t, h: sent.append((to, t)))
        finally:
            os.environ.pop(PN.ENV, None)
        mine = [t for to, t in sent if to == "old@example.com"]
        assert any("(2 November 2026)" in t for t in mine), "the 2 November email went, after the older ones"
        assert PN.pending(conn, PN.TRIALS) == [] and PN.status(conn, PN.TRIALS)["told"] == 1
        conn.close()


def test_the_email_says_what_changes_and_when():
    subject, text, html = PN.message(NOON, "https://example.com/", notice=PN.TRIALS)
    assert subject == "Changes to the Qellys Book Terms and Privacy Policy"
    assert "(2 November 2026)" in text and "your access to members' features stays on for one more day" in text
    assert "if the payment has not gone through by the end of that day, access pauses until it does" in text
    assert "If it is still unpaid when Stripe's retries run out, the subscription is cancelled" in text
    assert "For your account this takes effect on 4 December 2026, 30 days from this email." in text
    assert "one free trial per person: an email address or a card that has had one cannot start another" in text
    assert "(§2.3)" in text and "(§2.14)" in text
    assert "https://example.com/terms.html" in text and "qellysbook@gmail.com" in text
    assert "<li><b>A payment that does not go through (Terms §5.7).</b>" in html


def test_the_terms_carry_the_new_section_and_say_when_it_applies():
    terms = READ("web", "terms.html")
    flat = FLAT(terms)
    sec = flat[flat.index("5.7 Failed payments"):flat.index("5.8 The members’ Discord")]
    assert "If a charge does not go through — the first charge after a free trial, or a renewal — your access" in sec
    assert "stays on for one more day (24 hours from the failed charge)" in sec
    assert "if the payment has not gone through by the end of that day, access pauses until it does" in sec
    assert "the subscription is cancelled and nothing further is charged" in sec
    assert "we do not cut you off" not in sec, "the old promise is gone from the section"
    note = flat[flat.index("When this version applies."):flat.index("1. Who we are")]
    assert "The same day’s change to §5.7" in note and "an account made from 3 November 2026" in note
    assert "on 2 December 2026" in note and "30 days after we email the account’s address about it" in note
    assert "Until then §5.7 applies to it as it read before: “If a renewal charge fails" in note
    assert 'id="failed-payments"' in terms and "Last updated 3 November 2026" in terms


def test_the_runbook_arms_it_with_the_other_two():
    book = READ("docs", "WHEN_YOU_ARE_HOME.md")
    assert "sudo ./deploy/setenv.sh QB_POLICY_NOTICE 2026-10-29,2026-11-01,2026-11-02" in book
    assert "QB_POLICY_NOTICE 2026-10-29,2026-11-01,2026-11-02" in READ("docs", "RUN_NEXT.md")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
