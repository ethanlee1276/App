"""The two emails: the morning card and the nightly recap.

Ethan, 2026-08-25: *"Comms — email makes it a company … A morning
'Today's Card' digest and a nightly settle recap, same content as the
site's anchor moments."*

Both are built; neither can be sent until a delivery provider exists
(docs/EMAIL.md). That split is deliberate and is tested here too — a
sender that appears to work and silently delivers nothing is the worst
possible state, because nobody finds out until somebody asks why they
never got the email.

The rules that matter most:

  * an email leaves the building and gets forwarded, so the gate applies
    to it more strictly than to a page;
  * a digest with nothing to say is not sent;
  * every message carries a working unsubscribe, and the token that
    makes it work never leaves the server except inside the email.

Run directly: `python3 tests/test_digest.py`
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import digest as D, mailer                       # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


PICKS = [
    {"recommended": True, "player": "Juan Soto", "market": "home_runs",
     "market_label": "Home Runs", "side": "OVER", "line": 0.5, "odds": 320,
     "book": "DK", "ev_per_unit": 0.11},
    {"recommended": True, "player": "Aaron Judge", "market": "total_bases",
     "market_label": "Total Bases", "side": "OVER", "line": 1.5, "odds": -115,
     "book": "FD", "ev_per_unit": 0.07},
    {"recommended": False, "player": "Passed Guy", "market": "hits"},
]


def _tree(files):
    """A throwaway `<root>/web/data` — the shape gate.board_source needs,
    or the fixture reads this machine's real boards instead."""
    tmp = tempfile.mkdtemp(prefix="qbdigest")
    data = os.path.join(tmp, "web", "data")
    os.makedirs(data)
    for name, doc in files.items():
        with open(os.path.join(data, name), "w") as fh:
            json.dump(doc, fh)
    return os.path.join(tmp, "web")


# --- the gate ----------------------------------------------------------------

def test_an_unentitled_digest_carries_counts_and_not_picks():
    """THE ONE THAT MATTERS. A page is fetched by somebody signed in
    right now; an email leaves the building, gets forwarded, and sits in
    an inbox indefinitely."""
    web = _tree({"mlb_recommendations.json": {"recommendations": PICKS}})
    try:
        msg = D.morning(entitled=False, web=web, token="t")
        blob = (msg["subject"] + msg["text"] + msg["html"]).lower()
        assert "2 pick" in blob, "it does not even say how many are behind it"
        for leak in ("juan soto", "aaron judge", "home runs", "+320", "over"):
            assert leak not in blob, f"the locked digest leaks {leak!r}"
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_an_entitled_digest_is_the_card():
    web = _tree({"mlb_recommendations.json": {"recommendations": PICKS}})
    try:
        msg = D.morning(entitled=True, web=web, token="t")
        assert "Juan Soto" in msg["text"] and "+320" in msg["text"]
        assert "Passed Guy" not in msg["text"], \
            "a pick the model did not recommend is in the email"
        assert "Juan Soto" in msg["html"]
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_the_best_pick_leads():
    web = _tree({"mlb_recommendations.json": {"recommendations": PICKS}})
    try:
        text = D.morning(web=web, token="t")["text"]
        assert text.index("Juan Soto") < text.index("Aaron Judge")
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_a_long_card_stops_listing_and_starts_counting():
    """An email is a nudge to open the site, not a replacement for it."""
    many = [dict(PICKS[0], player=f"P{i}", ev_per_unit=0.2 - i * 0.01)
            for i in range(12)]
    web = _tree({"mlb_recommendations.json": {"recommendations": many}})
    try:
        text = D.morning(web=web, token="t")["text"]
        assert text.count("  P") == D.MAX_PICKS
        assert f"…and {12 - D.MAX_PICKS} more" in text
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


# --- nothing to say ----------------------------------------------------------

def test_a_quiet_day_sends_nothing():
    """A daily email that arrives to announce there are no picks teaches
    people to filter it, and this model passes often enough that it
    would happen most weeks in February."""
    web = _tree({"mlb_recommendations.json": {"recommendations": []}})
    try:
        assert D.morning(web=web) is None
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_an_ungraded_night_sends_nothing():
    web = _tree({"feed.json": {"events": []}})
    try:
        assert D.nightly(web=web) is None
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_the_recap_reads_the_same_event_the_site_does():
    """The email and the page must not be able to disagree about what
    last night was. A second computation of "how did we do" is a second
    answer waiting to differ from the first."""
    web = _tree({"feed.json": {"events": [
        {"kind": "settle_recap", "date": "2026-08-23", "w": 1, "l": 9,
         "p": 0, "net_u": -8.1},
        {"kind": "settle_recap", "date": "2026-08-24", "w": 7, "l": 4,
         "p": 1, "net_u": 3.2},
    ]}})
    try:
        msg = D.nightly(web=web, token="t")
        assert "7-4-1" in msg["subject"] and "+3.2u" in msg["subject"], msg
        assert "1-9" not in msg["subject"], "it announced an older night"
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_a_losing_night_reads_exactly_the_same_way():
    """The nightly recap is free and it is the evidence. A digest that
    only goes out after a good night is an advertisement."""
    web = _tree({"feed.json": {"events": [
        {"kind": "settle_recap", "date": "2026-08-24", "w": 1, "l": 9,
         "p": 0, "net_u": -8.1}]}})
    try:
        msg = D.nightly(web=web, token="t")
        assert msg is not None and "-8.1u" in msg["subject"]
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


# --- the unsubscribe ---------------------------------------------------------

def test_every_message_carries_a_working_unsubscribe():
    """One spam report costs more deliverability than a hundred opens
    earn, and in the US a list you cannot leave is also illegal."""
    web = _tree({"mlb_recommendations.json": {"recommendations": PICKS},
                 "feed.json": {"events": [
                     {"kind": "settle_recap", "date": "2026-08-24", "w": 7,
                      "l": 4, "p": 1, "net_u": 3.2}]}})
    try:
        for msg in (D.morning(web=web, token="abc123"),
                    D.nightly(web=web, token="abc123")):
            assert "unsubscribe?t=abc123" in msg["text"]
            assert "unsubscribe?t=abc123" in msg["html"]
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users (id, email) VALUES (1, 'a@b.co')")
    conn.execute("INSERT INTO users (id, email) VALUES (2, 'c@d.co')")
    D.ensure_tables(conn)
    return conn


def test_the_token_survives_a_preference_change():
    """An unsubscribe link in a message sent last week has to keep
    working; re-minting on every toggle breaks every link delivered."""
    conn = _db()
    first = D.optin_set(conn, 1, True, True)["token"]
    again = D.optin_set(conn, 1, False, True)["token"]
    assert first and first == again


def test_one_click_turns_both_off():
    conn = _db()
    tok = D.optin_set(conn, 1, True, True)["token"]
    assert D.unsubscribe(conn, tok) is True
    st = D.optin_get(conn, 1)
    assert st["morning"] is False and st["nightly"] is False


def test_an_unknown_token_changes_nothing():
    conn = _db()
    D.optin_set(conn, 1, True, True)
    assert D.unsubscribe(conn, "not-a-real-token-at-all") is False
    assert D.optin_get(conn, 1)["morning"] is True
    # …and a short or empty one is refused before it reaches the database.
    assert D.unsubscribe(conn, "") is False
    assert D.unsubscribe(conn, "short") is False


def test_the_list_is_per_digest():
    conn = _db()
    D.optin_set(conn, 1, True, False)
    D.optin_set(conn, 2, False, True)
    assert [r["email"] for r in D.recipients(conn, "morning")] == ["a@b.co"]
    assert [r["email"] for r in D.recipients(conn, "nightly")] == ["c@d.co"]
    assert D.recipients(conn, "nonsense") == []


def test_the_address_is_joined_not_copied():
    """Two copies of somebody's email is one that goes stale the day they
    change it, and the wrong one is a message delivered to an address
    they thought they had removed."""
    src = _read("engine", "digest.py")
    i = src.index("def ensure_tables(conn)")
    body = src[i:src.index("\ndef optin_get", i)]
    assert "email" not in body.split("CREATE TABLE")[1].split(")")[0], \
        "the opt-in table stores its own copy of the address"


def test_the_token_never_leaves_the_server():
    """It is a bearer credential for one action. A page that holds it can
    leak it into a referrer, a screenshot or a support ticket."""
    server = _read("server.py")
    i = server.index('if path == "digest":')
    assert 'out.pop("token", None)' in server[i:i + 900]
    # The CODE, not the comment beside it: the block explains WHY the
    # token is withheld, so a naive search for the word fails on the
    # sentence saying it is not there.
    acct = _read("engine", "accounts.py")
    j = acct.index('if "digest_optin" in have:')
    body = acct[j:acct.index("return out", j)]
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.strip().startswith("#"))
    assert "SELECT morning, nightly FROM digest_optin" in code
    assert "token" not in code, "the data export carries the unsubscribe token"


def test_the_mailing_list_dies_with_the_account():
    acct = _read("engine", "accounts.py")
    i = acct.index("def delete_user")
    assert "digest_optin" in acct[i:acct.index("def export_user", i)]


# --- the sender --------------------------------------------------------------

def test_it_refuses_rather_than_pretending():
    """A sender that appears to work and delivers nothing is the worst of
    the three options."""
    saved = {k: os.environ.pop(k, None) for k in mailer.REQUIRED}
    try:
        assert mailer.configured() is False
        assert set(mailer.missing()) == set(mailer.REQUIRED)
        try:
            mailer.send("a@b.co", "s", "t")
        except RuntimeError as exc:
            assert "not configured" in str(exc)
            assert "QB_SMTP_PASS" in str(exc), "it does not say what is missing"
        else:
            raise AssertionError("it tried to send with nothing configured")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_a_password_is_never_in_an_error_message():
    """A key in a traceback is a key in a log file — the rule
    engine/stripeset.py already keeps for the Stripe secret."""
    src = _read("engine", "mailer.py")
    i = src.index("def send(")
    body = src[i:]
    assert "os.environ[ENV_PASS]" in body, "it does not read the password"
    # …but never into a message.
    for line in body.splitlines():
        if "raise" in line or "RuntimeError" in line:
            assert "ENV_PASS]" not in line and "environ[" not in line


def test_both_parts_are_always_sent():
    """A message with only an HTML part scores worse with every filter
    and is unreadable in the clients that strip it."""
    msg = mailer.message("a@b.co", "s", "the text", "<p>the html</p>")
    assert msg.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in parts and "text/html" in parts


def test_the_one_click_header_rides_along():
    """Gmail and Apple Mail put the control in their own chrome when this
    header is present, and a reader who finds it there does not press
    Report spam."""
    text = "body\n—\nStop these emails: https://qellysbook.com/unsubscribe?t=x\n"
    msg = mailer.message("a@b.co", "s", text)
    assert msg["List-Unsubscribe"] == "<https://qellysbook.com/unsubscribe?t=x>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_the_endpoint_answers_the_post_the_header_promises():
    """A List-Unsubscribe-Post that 405s is worse than no header at all:
    the client shows the control, the reader presses it, nothing
    happens."""
    server = _read("server.py")
    assert 'if parsed.path in ("/unsubscribe", "/unsubscribe/"):' in server
    i = server.index("def do_POST")
    assert "do_POST_unsubscribe" in server[i:i + 1200]


def test_the_unsubscribe_page_never_asks_who_you_are():
    server = _read("server.py")
    i = server.index("def _unsubscribe(self, query")
    body = server[i:server.index("def do_POST_unsubscribe", i)]
    assert "_account(" not in body and "SESSION_COOKIE" not in body
    assert "noindex" in server[server.index("_UNSUB_PAGE"):][:600]


def test_the_cli_prints_by_default_and_sends_on_a_flag():
    """The right way round for a thing that can mail several hundred
    people."""
    src = _read("digest.py")
    assert 'if "--send" in argv' in src
    assert "_preview(kind" in src
    i = src.index("def _send(kind")
    body = src[i:src.index("\ndef main", i)]
    assert "mailer.configured()" in body, "it would try with nothing set"


def test_the_three_steps_are_written_down():
    doc = _read("docs", "EMAIL.md")
    for needed in ("SPF", "DKIM", "DMARC", "QB_SMTP_HOST", "port 25"):
        assert needed in doc, needed


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
