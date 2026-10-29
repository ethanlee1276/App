"""The email our own documents promise before a change takes effect
(engine/policynotice, its place in engine/lifecycle, web/terms.html).

The Privacy Policy's §13 says a change that materially affects a member is
emailed before it takes effect; the Terms' §15 says 30 days before. Ethan
approved the members' split (counted unless a member says no) and the
Terms' new rules on 2026-10-29, so what these hold:

  * once QB_POLICY_NOTICE names the change, each account made before it
    with an email address is told once, a few dozen an Eastern day,
    between ten and eight, never a phone sign-in's placeholder address;
  * a failed email stops the pass and is tried again later; one sent is
    never sent twice;
  * the record of it is named in the policy, in Download my data, and
    deleted with the account;
  * the Terms say when they apply to an older account, and keep the
    version that applies until then.

Run directly: `python3 tests/test_the_change_notice.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_POLICY_NOTICE", None)

from engine import accounts as A                                  # noqa: E402
from engine import policynotice as PN                             # noqa: E402
from engine import smsverify as SV                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOON = dt.datetime(2026, 10, 30, 12, tzinfo=PN.ET).timestamp()    # Friday, noon Eastern
PASS = "correct-horse-battery"


def _accounts(d, n=5):
    conn = A.connect(str(Path(d) / "acc.db"))
    ids = []
    for i in range(n):
        ids.append(int(A.create_user(conn, f"m{i}@example.com", PASS, confirmed=True)[1]["id"]))
    # Made before the change (create_user stamps the clock's own now).
    conn.execute("UPDATE users SET created_at = ?", (PN.SINCE - 86400,))
    conn.commit()
    return conn, ids


class _Armed:
    def __enter__(self):
        os.environ[PN.ENV] = PN.NOTICE

    def __exit__(self, *exc):
        os.environ.pop(PN.ENV, None)


def test_each_account_is_told_once_inside_the_day_and_its_hours():
    with tempfile.TemporaryDirectory() as d:
        conn, ids = _accounts(d, 6)
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (SV.placeholder_email("+15555550123"), ids[5]))
        new = int(A.create_user(conn, "new@example.com", PASS, confirmed=True)[1]["id"])
        conn.execute("UPDATE users SET created_at = ? WHERE id = ?", (PN.SINCE + 60, new))
        conn.commit()
        box = []
        send = lambda *a: box.append(a)                            # noqa: E731
        assert PN.run(conn, now=NOON, send=send) == 0 and not box, "not armed: nothing"
        keep = PN.DAY_MAX
        PN.DAY_MAX = 3
        try:
            with _Armed():
                assert PN.run(conn, now=NOON - 4 * 3600, send=send) == 0, "8 a.m.: not yet"
                assert PN.run(conn, now=NOON, send=send) == 3, "the day's allowance"
                assert PN.run(conn, now=NOON + 600, send=send) == 0, "and no more today"
                assert PN.run(conn, now=NOON + 86400, send=send) == 2, "the rest the next day"
                assert PN.run(conn, now=NOON + 2 * 86400, send=send) == 0, "each once"
        finally:
            PN.DAY_MAX = keep
        to = sorted(a[0] for a in box)
        assert to == [f"m{i}@example.com" for i in range(5)], ("never a phone's placeholder, never a new account", to)
        subject, text = box[0][1], box[0][2]
        assert "Terms and Privacy Policy" in subject and "Count my bets in the members' split" in text
        assert "30 days from this email" in text and "/privacy.html" in text and "never a player prop" in text
        assert PN.status(conn)["told"] == 5 and PN.status(conn)["to_go"] == 0


def test_a_failed_email_stops_the_pass_and_goes_later():
    def boom(*_a):
        raise OSError("relay down")
    with tempfile.TemporaryDirectory() as d:
        conn, _ids = _accounts(d, 3)
        with _Armed():
            assert PN.run(conn, now=NOON, send=boom, log=lambda *_: None) == 0
            assert PN.status(conn)["to_go"] == 3, "nothing marked told"
            box = []
            assert PN.run(conn, now=NOON + 900, send=lambda *a: box.append(a)) == 3 and len(box) == 3


def test_the_record_is_named_exported_and_deleted_with_the_account():
    with tempfile.TemporaryDirectory() as d:
        conn, ids = _accounts(d, 2)
        with _Armed():
            PN.run(conn, now=NOON, send=lambda *a: None)
        out = A.export_user(conn, ids[0])
        assert out["changes_we_emailed_you_about"] == [{"notice": PN.NOTICE, "sent_at": NOON}], out.get(
            "changes_we_emailed_you_about")
        A.delete_user(conn, ids[0])
        left = [tuple(r) for r in conn.execute("SELECT user_id FROM policy_notices")]
        assert left == [(ids[1],)], left
    policy = READ("web", "privacy.html")
    assert "<code>policy_notices</code>" in policy
    assert '("policy_notices", "changes to our documents we emailed you about")' in READ("engine", "yourdata.py")


def test_the_lifecycle_pass_sends_it_and_the_terms_say_when_they_apply():
    assert "lambda: PN.run(conn, now=t, log=log)" in READ("engine", "lifecycle.py")
    terms = " ".join(READ("web", "terms.html").split())
    assert "When this version applies." in terms and "30 days after we email the account's address" in terms
    assert 'href="terms-2026-10-26.html"' in terms and "28 November 2026" in terms
    old = READ("web", "terms-2026-10-26.html")
    assert "Last updated 26 October 2026" in old and 'name="robots" content="noindex"' in old
    assert "This is an earlier version, kept because it still applies to some" in old and 'href="terms.html"' in old
    # The dates in the words are the module's own.
    assert dt.datetime.fromtimestamp(PN.SINCE, PN.ET).date() == dt.date(2026, 10, 30)
    assert dt.datetime.fromtimestamp(PN.PHONE_FROM, PN.ET).strftime("%-d %B %Y %H:%M") == "6 November 2026 00:00"
    policy = " ".join(READ("web", "privacy.html").split())
    assert "from 6 November 2026), as §13 promises" in policy


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
