"""An account by phone: a code by text, no password (engine/smsverify).

Ethan, 2026-10-25, on Real's first screen: "you can either make an account
with an email or a phone number. So we should add that option as well."

Off until Twilio's three values are set; US and Canadian numbers only; a
cap on texts per number and per address; a phone account's email column
holds a placeholder nothing can be sent to.

    python3 tests/test_an_account_by_phone.py
"""

import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import smsverify as SV                              # noqa: E402

ENV = {SV.ENV_SID: "AC_test", SV.ENV_TOKEN: "tok_test", SV.ENV_SERVICE: "VA_test"}


def test_off_until_all_three_values_are_set():
    assert not SV.configured({})
    assert not SV.configured({SV.ENV_SID: "x", SV.ENV_TOKEN: "y"})
    assert SV.configured(ENV)


def test_a_swapped_sid_keeps_it_off_and_says_which():
    """2026-10-26: the Account SID went into the Verify slot too. Twilio's
    prefixes tell them apart (AC…, VA…), so the page offers no phone option
    that would fail on every tap, and the check names the one to fix
    without printing any value."""
    swapped = dict(ENV, **{SV.ENV_SERVICE: "AC_test"})
    assert not SV.configured(swapped)
    said = SV.problems(swapped)
    assert len(said) == 1 and said[0].startswith("TWILIO_VERIFY_SID should start with VA")
    assert "Account SID" in said[0] and "AC_test" not in said[0], "a value is never printed"
    assert SV.problems(ENV) == []
    assert "TWILIO_AUTH_TOKEN is not set" in " ".join(SV.problems({SV.ENV_SID: "AC_x", SV.ENV_SERVICE: "VA_x"}))


def test_only_a_north_american_mobile_shaped_number():
    assert SV.normalize("(415) 555-2671") == "+14155552671"
    assert SV.normalize("+1 415 555 2671") == "+14155552671"
    for bad in ("", "555-2671", "+44 20 7946 0958", "(015) 555-2671", "(415) 155-2671", "1234567890123"):
        assert SV.normalize(bad) == "", bad
    assert SV.say("+14155552671") == "(415) 555-2671"
    assert SV.placeholder_email("+14155552671") == "14155552671@phone.invalid"
    assert SV.is_placeholder("14155552671@phone.invalid") and not SV.is_placeholder("you@example.com")


def test_the_texts_are_capped_per_number_and_per_address():
    SV._sent.clear()
    n = "+14155552671"
    assert all(SV.allow(n, "1.1.1.1", now=100.0) for _ in range(SV.PER_NUMBER))
    assert not SV.allow(n, "1.1.1.1", now=101.0), "a fourth text to one number in the hour"
    assert SV.allow(n, "1.1.1.1", now=100.0 + SV.WINDOW_S + 1), "the hour passes"
    SV._sent.clear()
    nums = [f"+1415555{2600 + i}" for i in range(SV.PER_IP + 1)]
    got = [SV.allow(x, "2.2.2.2", now=10.0) for x in nums]
    assert got == [True] * SV.PER_IP + [False], "one address texting many numbers"
    SV._sent.clear()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_twilio_is_asked_with_the_number_and_the_code():
    seen = []

    def opener(req, timeout=15):
        seen.append((req.full_url, req.data.decode(), req.headers.get("Authorization", "")))
        status = "pending" if req.full_url.endswith("/Verifications") else "approved"
        return _Resp(json.dumps({"status": status}).encode())
    assert SV.start("+14155552671", env=ENV, opener=opener)
    assert SV.check("+14155552671", "123456", env=ENV, opener=opener)
    assert seen[0][0] == "https://verify.twilio.com/v2/Services/VA_test/Verifications"
    assert "To=%2B14155552671" in seen[0][1] and "Channel=sms" in seen[0][1]
    assert seen[1][0].endswith("/VerificationCheck") and "Code=123456" in seen[1][1]
    assert seen[0][2].startswith("Basic ")
    assert not SV.check("+14155552671", "12", env=ENV, opener=opener), "not a code at all"


def test_a_refusal_never_carries_the_token():
    import urllib.error

    def opener(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
    try:
        SV.start("+14155552671", env=ENV, opener=opener)
        raise AssertionError("no error")
    except SV.SmsUnavailable as exc:
        assert "tok_test" not in str(exc) and "AC_test" not in str(exc) and exc.__cause__ is None
    assert not SV.check("+14155552671", "123456", env=ENV, opener=opener), "a refusal is a wrong code"


def test_a_phone_account_has_a_placeholder_and_no_password():
    from engine import accounts as A
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        assert A.create_phone_user(conn, "+14155552671")[0] == 400, "the 21+ box"
        code, out = A.create_phone_user(conn, "+14155552671", confirmed=True)
        assert code == 200 and out["email"] == "14155552671@phone.invalid" and out["phone"] == "+14155552671"
        assert A.create_phone_user(conn, "+14155552671", confirmed=True)[0] == 409
        assert A.user_by_phone(conn, "+14155552671")["id"] == out["id"]
        assert A.user_by_phone(conn, "+14155550000") is None
        assert A.authenticate(conn, out["email"], "anything at all here")[0] != 200


def test_nothing_is_ever_mailed_to_a_placeholder():
    from engine import mailer
    try:
        mailer.send("14155552671@phone.invalid", "hi", "body")
        raise AssertionError("sent")
    except RuntimeError as exc:
        assert "phone" in str(exc)


def _handler(env_on):
    import server
    h = object.__new__(server.Handler)
    out = {}
    h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body), headers=headers)
    h._client_ip = lambda: "9.9.9.9"
    h._session_cookie = lambda token, clear=False: {"Set-Cookie": "qb=" + token}
    return h, out


def test_the_endpoints_off_then_on():
    import os
    from engine import accounts as A
    keep = {k: os.environ.get(k) for k in ENV}
    real_start, real_check = SV.start, SV.check
    try:
        for k in ENV:
            os.environ.pop(k, None)
        with tempfile.TemporaryDirectory() as d:
            conn = A.connect(Path(d) / "a.db")
            h, out = _handler(False)
            h._phone_auth(A, conn, "phone-start", {"phone": "4155552671"})
            assert out["code"] == 503, "off until configured"
            os.environ.update(ENV)
            SV._sent.clear()
            SV.start = lambda phone, env=None, opener=None: True
            SV.check = lambda phone, code, env=None, opener=None: code == "424242"
            h._phone_auth(A, conn, "phone-start", {"phone": "+44 20 7946 0958"})
            assert out["code"] == 400 and out["body"]["field"] == "phone"
            h._phone_auth(A, conn, "phone-start", {"phone": "4155552671"})
            assert out["code"] == 200 and out["body"]["to"] == "(415) 555-2671"
            h._phone_auth(A, conn, "phone-verify", {"phone": "4155552671", "code": "000000"})
            assert out["code"] == 400 and out["body"]["field"] == "code"
            h._phone_auth(A, conn, "phone-verify", {"phone": "4155552671", "code": "424242"})
            assert out["code"] == 404, "signing in with a number that has no account"
            h._phone_auth(A, conn, "phone-verify", {"phone": "4155552671", "code": "424242", "confirmed": True,
                                                    "handle": "casey_k"})
            assert out["code"] == 200 and out["body"]["signed_in"] and out["headers"]
            assert out["body"]["email"].endswith("@phone.invalid")
            h._phone_auth(A, conn, "phone-verify", {"phone": "(415) 555-2671", "code": "424242"})
            assert out["code"] == 200, "and signs in by the same number afterwards"
    finally:
        SV.start, SV.check = real_start, real_check
        SV._sent.clear()
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_the_page_offers_it_only_when_it_is_on():
    acct = (ROOT / "web" / "js" / "account.js").read_text()
    door = acct[acct.index("const phoneDoorHTML = "):acct.index("function phoneCardHTML(")]
    assert "(_acctUser || {}).phone_signup" in door
    assert '${phoneDoorHTML("signup")}' in acct and '${phoneDoorHTML("login")}' in acct
    srv = (ROOT / "server.py").read_text()
    assert '"phone_signup": __import__("engine.smsverify", fromlist=["x"]).configured()' in srv
    assert '"phone-start", "phone-verify"):' in srv
    priv = (ROOT / "web" / "privacy.html").read_text()
    assert "users.phone" in priv and "Twilio" in priv


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
