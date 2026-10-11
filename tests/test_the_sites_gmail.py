"""The site sends its password resets from its own Gmail, and publishes it.

Ethan, 2026-10-11: "i have an email for the site. its qellysbook@gmail.com.
also we have to have a forgot a password feture". The reset flow was built
and waiting on a mail relay; Gmail's SMTP server is that relay, with an app
password made on the account.

These check, one rule each: Gmail is recognised, an app password's spaces
come out (and only Gmail's), a bare address gets the site's name in front;
the digests never go out through Gmail and the account page does not offer
them there; reset emails stop at a daily cap that keeps the account well
under Gmail's limits; the test command sends, names an app-password
mistake when the login is refused, and never prints the password; the box
settings script refuses a mistyped mail setting; every page publishes the
one inbox, and the privacy page names Google as the service that carries
the reset email.

No network: every send here is a stand-in.

Run directly: `python3 tests/test_the_sites_gmail.py`
"""
import io
import os
import smtplib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_ENV_FILE"] = os.path.join(tempfile.mkdtemp(), "no-such-env")
os.environ["QB_ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "accounts.db")

from engine import mailer as M                                      # noqa: E402

GMAIL = {"QB_SMTP_HOST": "smtp.gmail.com", "QB_SMTP_PORT": "587",
         "QB_SMTP_USER": "qellysbook@gmail.com", "QB_SMTP_PASS": "abcd efgh ijkl mnop",
         "QB_MAIL_FROM": "qellysbook@gmail.com"}
SITE = "qellysbook@gmail.com"


class _env:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in M.REQUIRED + (M.ENV_PORT,)}
        for k in self.saved:
            os.environ.pop(k, None)
        os.environ.update(self.values)

    def __exit__(self, *_):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_gmail_is_recognised_and_its_app_password_loses_its_spaces():
    with _env(GMAIL):
        assert M.configured() and M.is_gmail()
        assert M._clean_password(os.environ["QB_SMTP_PASS"]) == "abcdefghijklmnop", \
            "Google shows the sixteen letters in groups of four"
    with _env({**GMAIL, "QB_SMTP_HOST": "smtp.postmarkapp.com"}):
        assert not M.is_gmail()
        assert M._clean_password("pass word") == "pass word", "another provider's space is real"


def test_a_bare_address_is_sent_as_qellys_book():
    with _env(GMAIL):
        assert M.sender() == "Qellys Book <qellysbook@gmail.com>"
        assert M.message("fan@example.com", "s", "t")["From"] == "Qellys Book <qellysbook@gmail.com>"
    with _env({**GMAIL, "QB_MAIL_FROM": "Picks Desk <qellysbook@gmail.com>"}):
        assert M.sender() == "Picks Desk <qellysbook@gmail.com>", "a name already given is kept"


def test_the_digests_never_go_out_through_gmail():
    with _env(GMAIL):
        assert not M.bulk_ok()
        import digest
        out = io.StringIO()
        with redirect_stdout(out):
            assert digest._send("morning") == 2
        assert "one-to-one" in out.getvalue() and "Nothing was sent" in out.getvalue()
    with _env({**GMAIL, "QB_SMTP_HOST": "smtp.postmarkapp.com"}):
        assert M.bulk_ok()
    server = _read("server.py")
    assert 'out["available"] = mailer.bulk_ok()' in server, \
        "the account page offers the digests only where they can be sent"


def test_reset_emails_stop_at_a_daily_cap():
    import server
    from engine import accounts as A
    assert server.RESET_MAIL_PER_DAY <= 200, "well under a personal Gmail's few hundred a day"
    sent = []
    real_send, real_cap = M.send, server.RESET_MAIL_PER_DAY
    M.send = lambda to, subject, text, html="": sent.append(to)
    server.RESET_MAIL_PER_DAY = 2
    server._RESET_SENT.clear()
    try:
        c = A.connect()
        for who in ("a@example.com", "b@example.com", "c@example.com"):
            A.create_user(c, who, "correct horse battery", confirmed=True)
        c.close()
        for who in ("a@example.com", "b@example.com", "c@example.com"):
            server._send_reset(who)
    finally:
        M.send, server.RESET_MAIL_PER_DAY = real_send, real_cap
        server._RESET_SENT.clear()
    assert sent == ["a@example.com", "b@example.com"], sent
    src = _read("server.py")
    body = src[src.index("def _send_reset("):src.index("\ndef ", src.index("def _send_reset(") + 1)]
    assert body.index("if not token:") < body.index("_reset_budget_ok()"), \
        "an address with no account never spends the allowance"


def test_the_test_command_sends_and_explains_a_refused_login():
    real = M.send
    try:
        with _env(GMAIL):
            got = []
            M.send = lambda to, subject, text, html="": got.append((to, subject))
            out = io.StringIO()
            with redirect_stdout(out):
                assert M._cli(["test", "ethan@example.com"]) == 0
            assert got == [("ethan@example.com", "Qellys Book: test email")]
            assert "Qellys Book <qellysbook@gmail.com>" in out.getvalue()

            def refuse(*_a, **_k):
                raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
            M.send = refuse
            out = io.StringIO()
            with redirect_stdout(out):
                assert M._cli(["test", "ethan@example.com"]) == 1
            said = out.getvalue()
            assert "APP PASSWORD" in said and "apppasswords" in said
            assert "abcd" not in said and "mnop" not in said, "the password is never printed"

            def unreachable(*_a, **_k):
                raise TimeoutError("timed out")
            M.send = unreachable
            out = io.StringIO()
            with redirect_stdout(out):
                assert M._cli(["test", "ethan@example.com"]) == 1
            assert "DigitalOcean" in out.getvalue() and "smtp.gmail.com" in out.getvalue(), \
                "a blocked mail port is named as the hosting company's block, not a bad password"
        with _env({}):
            out = io.StringIO()
            with redirect_stdout(out):
                assert M._cli(["test", "ethan@example.com"]) == 1
            assert "QB_SMTP_PASS" in out.getvalue() and "Nothing was sent" in out.getvalue()
    finally:
        M.send = real


def test_the_settings_script_refuses_a_mistyped_mail_setting():
    env_file = os.path.join(tempfile.mkdtemp(), "env")
    run = lambda *a: subprocess.run(["bash", os.path.join(ROOT, "deploy", "setenv.sh"), *a],  # noqa: E731
                                    env={**os.environ, "QB_ENV_FILE": env_file},
                                    capture_output=True, text=True)
    assert run("QB_SMTP_HOST", "https://smtp.gmail.com").returncode != 0
    assert run("QB_SMTP_PORT", "five-eight-seven").returncode != 0
    assert run("QB_SMTP_USER", "qellysbook").returncode != 0
    assert run("QB_MAIL_FROM", "qellysbook").returncode != 0
    for k, v in (("QB_SMTP_HOST", "smtp.gmail.com"), ("QB_SMTP_PORT", "587"),
                 ("QB_SMTP_USER", SITE), ("QB_MAIL_FROM", SITE)):
        assert run(k, v).returncode == 0, k
    assert open(env_file).read().count("=") == 4


def test_every_page_publishes_the_one_inbox():
    import server
    assert server.SUPPORT_EMAIL == SITE
    for rel in (("web", "js", "app.js"), ("web", "privacy.html"), ("web", "terms.html")):
        text = _read(*rel)
        assert f"mailto:{SITE}" in text, rel
        assert "support@qellysbook.com" not in text and "privacy@qellysbook.com" not in text, rel


def test_the_privacy_page_names_google_for_the_reset_email():
    privacy = _read("web", "privacy.html")
    i = privacy.index("<b>Google LLC</b>")
    assert "Forgot password" in privacy[i:i + 400] and "Gmail" in privacy[i:i + 400]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
