"""Friends and pick shares — the social layer's two structural rules.

Ethan, 2026-08-25: *"lets add a social network on the app where users
can send picks back and forth between there friends."*

What this file pins is not the happy path (the e2e sweep walks that) but
the two rules the feature is built around, because each one guards a
paywall or a privacy promise:

  * A SHARED PICK IS A POINTER, NEVER A COPY. The share carries the
    pick's identity — sport, date, player, market — and none of its
    content. Carried content would be the paywall's cleanest bypass:
    one subscriber feeding the paid board to any number of free
    friends, one share at a time.
  * FRIENDS FORM THROUGH INVITE LINKS, NEVER LOOKUP. Search-by-email is
    an oracle for which addresses hold accounts; invite tokens are
    unguessable and answer identically whether dead or fake.

Run directly: `python3 tests/test_social.py`
"""

import inspect
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import social as SOC                             # noqa: E402

GOOD = "correct-horse-battery"


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SOC.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey"):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    return conn, ids


def _befriend(conn, a, b):
    inv = SOC.invite_get_or_create(conn, a)
    code, out = SOC.invite_accept(conn, b, inv["token"])
    assert code == 200, out
    return out


# --- the pointer rule --------------------------------------------------------

def test_a_share_cannot_carry_content_by_signature():
    """The strongest form of the rule: there is no PARAMETER through
    which a side, a line, odds or an edge could arrive. Validation can
    be forgotten; a missing argument cannot."""
    params = set(inspect.signature(SOC.share_pick).parameters)
    assert params == {"conn", "from_id", "to_id", "sport", "date",
                      "player", "market", "note"}, params
    # The CODE (docstring aside — its prose names the words it refuses)
    # must not touch content fields either.
    src = inspect.getsource(SOC.share_pick)
    code = src.split('"""')[2]
    for word in ("side", "odds", "proj", "edge", "stake"):
        assert word not in code, \
            f"share_pick's code touches {word!r} — the pointer rule is drifting"


def test_the_stored_row_is_identity_plus_note_only():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    code, out = SOC.share_pick(conn, a, b, "nfl", "2026-09-13",
                               "Chris Olave", "rec_yds", "tail this")
    assert code == 200 and out["sent"] and not out["already"]
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM pick_shares").description]
    assert set(cols) == {"id", "from_id", "to_id", "sport", "date",
                         "player", "market", "note", "created_at", "seen"}


def test_the_server_reads_only_identity_fields_from_the_body():
    """The wiring half of the signature rule: the handler passes exactly
    the identity fields and the note, never body-spread."""
    srv = _read("server.py")
    i = srv.index("if path == \"send\":")
    body = srv[i:i + 900]
    assert "share_pick" in body
    for k in ('body.get("to")', 'body.get("sport")', 'body.get("date")',
              'body.get("player")', 'body.get("market")', 'body.get("note")'):
        assert k in body, f"send handler lost {k}"
    assert "**body" not in body


def test_strangers_cannot_send():
    conn, (a, _, c) = _db()
    code, out = SOC.share_pick(conn, a, c, "nfl", "2026-09-13",
                               "Chris Olave", "rec_yds")
    assert code == 403, out


def test_a_resend_is_a_dedupe_not_a_second_row():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "Chris Olave", "rec_yds")
    code, out = SOC.share_pick(conn, a, b, "nfl", "2026-09-13",
                               "Chris Olave", "rec_yds", "again")
    assert code == 200 and out["already"]
    n = conn.execute("SELECT COUNT(*) FROM pick_shares").fetchone()[0]
    assert n == 1


def test_the_note_is_capped_and_identity_is_required():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    code, _out = SOC.share_pick(conn, a, b, "nfl", "2026-09-13",
                                "Chris Olave", "rec_yds", "x" * 5000)
    assert code == 200
    note = conn.execute("SELECT note FROM pick_shares").fetchone()["note"]
    assert len(note) == SOC.MAX_NOTE
    code, out = SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "", "rec_yds")
    assert code == 400, out


def test_the_inbox_prunes_itself_on_write():
    """The lazy-fold rule: no cron is owed. INBOX_KEEP rows stand, the
    oldest fall off as new ones land."""
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    for i in range(SOC.INBOX_KEEP + 25):
        conn.execute(
            "INSERT INTO pick_shares (from_id, to_id, sport, date, player,"
            " market, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (a, b, "nfl", "2026-09-13", f"Player {i}", "rec_yds", "", i))
    SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "The Newest", "rec_yds")
    n = conn.execute("SELECT COUNT(*) FROM pick_shares WHERE to_id=?",
                     (b,)).fetchone()[0]
    assert n == SOC.INBOX_KEEP, n
    oldest = conn.execute("SELECT player FROM pick_shares WHERE to_id=? "
                          "ORDER BY created_at LIMIT 1", (b,)).fetchone()
    assert oldest["player"] != "Player 0", "the prune kept the oldest rows"


def test_reading_the_inbox_does_not_mark_seen():
    """The page says when it has SHOWN the rows; a background poll must
    not eat the badge."""
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "Chris Olave", "rec_yds")
    assert SOC.inbox(conn, b)["unseen"] == 1
    assert SOC.inbox(conn, b)["unseen"] == 1, "reading marked it seen"
    SOC.mark_seen(conn, b)
    assert SOC.inbox(conn, b)["unseen"] == 0


# --- parlays travel the same way --------------------------------------------

def test_a_parlay_share_carries_leg_identities_only():
    """The pointer rule, leg by leg: share_parlay reads exactly player
    and market out of each leg dict — a side, a line or a price in a
    crafted leg lands nowhere, and the stored JSON proves it."""
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    legs = [{"player": "Chris Olave", "market": "rec_yds",
             "side": "over", "line": 64.5, "odds": -115, "edge": 0.04},
            {"player": "Jahmyr Gibbs", "market": "rush_yds"}]
    code, out = SOC.share_parlay(conn, a, b, "nfl", "2026-09-13", legs, "lock")
    assert code == 200 and out["sent"], out
    blob = conn.execute("SELECT legs FROM parlay_shares").fetchone()["legs"]
    for word in ("side", "line", "odds", "edge", "64.5", "-115"):
        assert word not in blob, f"{word!r} leaked into a stored parlay"
    assert "Chris Olave" in blob and "rush_yds" in blob


def test_a_parlay_needs_two_to_eight_named_legs():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    one = [{"player": "X", "market": "m"}]
    assert SOC.share_parlay(conn, a, b, "nfl", "d", one)[0] == 400
    nine = [{"player": f"P{i}", "market": "m"} for i in range(9)]
    assert SOC.share_parlay(conn, a, b, "nfl", "d", nine)[0] == 400
    assert SOC.share_parlay(conn, a, b, "nfl", "d", one * 0 + [
        {"player": "A", "market": "m"}, {"player": "B", "market": "m"}])[0] == 200


def test_parlays_obey_friendship_and_dedupe():
    conn, (a, b, c) = _db()
    _befriend(conn, a, b)
    legs = [{"player": "A", "market": "m"}, {"player": "B", "market": "m"}]
    assert SOC.share_parlay(conn, a, c, "nfl", "d", legs)[0] == 403
    assert SOC.share_parlay(conn, a, b, "nfl", "d", legs)[0] == 200
    code, out = SOC.share_parlay(conn, a, b, "nfl", "d", legs, "again")
    assert code == 200 and out["already"]
    n = conn.execute("SELECT COUNT(*) FROM parlay_shares").fetchone()[0]
    assert n == 1


def test_the_inbox_merges_both_kinds_and_seen_covers_both():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_pick(conn, a, b, "nfl", "d", "Chris Olave", "rec_yds")
    SOC.share_parlay(conn, a, b, "nfl", "d",
                     [{"player": "A", "market": "m"},
                      {"player": "B", "market": "m"}])
    ib = SOC.inbox(conn, b)
    kinds = sorted(s["kind"] for s in ib["shares"])
    assert kinds == ["parlay", "pick"], kinds
    assert ib["unseen"] == 2
    SOC.mark_seen(conn, b)
    assert SOC.inbox(conn, b)["unseen"] == 0


def test_the_server_rebuilds_parlay_legs_key_by_key():
    """The wiring half: the handler constructs each leg from exactly
    player and market — never a spread of the client's dict."""
    srv = _read("server.py")
    i = srv.index('if path == "send-parlay":')
    body = srv[i:i + 900]
    assert 'str(l.get("player") or "")' in body
    assert 'str(l.get("market") or "")' in body
    assert "**" not in body, "a dict-spread would carry whatever a client sent"
    assert "share_parlay" in body


def test_deleting_and_exporting_cover_parlay_shares():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_parlay(conn, a, b, "nfl", "2026-09-13",
                     [{"player": "A", "market": "m"},
                      {"player": "B", "market": "m"}], "note")
    out = A.export_user(conn, a)
    sent = out.get("parlays_sent_to_friends")
    assert sent and sent[0]["legs"][0]["player"] == "A"
    assert "odds" not in repr(sent)
    A.delete_user(conn, a)
    n = conn.execute("SELECT COUNT(*) FROM parlay_shares").fetchone()[0]
    assert n == 0, "a parlay share outlived the account that sent it"


# --- the invite rule ---------------------------------------------------------

def test_one_live_invite_reused_not_reminted():
    """Mint once, keep it standing — a fresh token per view would orphan
    every link already texted out (the unsubscribe lesson)."""
    conn, (a, _, _) = _db()
    t1 = SOC.invite_get_or_create(conn, a)["token"]
    t2 = SOC.invite_get_or_create(conn, a)["token"]
    assert t1 == t2
    SOC.invite_revoke(conn, a)
    t3 = SOC.invite_get_or_create(conn, a)["token"]
    assert t3 != t1


def test_dead_and_fake_tokens_answer_identically():
    """An error that distinguishes "expired" from "never existed" is a
    token oracle."""
    conn, (a, b, _) = _db()
    tok = SOC.invite_get_or_create(conn, a)["token"]
    SOC.invite_revoke(conn, a)
    dead = SOC.invite_accept(conn, b, tok)
    fake = SOC.invite_accept(conn, b, "x" * len(tok))
    assert dead == fake, (dead, fake)
    assert dead[0] == 400


def test_an_expired_invite_is_dead():
    conn, (a, b, _) = _db()
    tok = SOC.invite_get_or_create(conn, a)["token"]
    conn.execute("UPDATE friend_invites SET created_at=?",
                 (time.time() - SOC.INVITE_TTL_S - 1,))
    code, out = SOC.invite_accept(conn, b, tok)
    assert code == 400 and out["error"] == "That invite is not live."
    # and get_or_create mints a replacement rather than serving the corpse
    assert SOC.invite_get_or_create(conn, a)["token"] != tok


def test_your_own_link_does_not_befriend_you():
    conn, (a, _, _) = _db()
    tok = SOC.invite_get_or_create(conn, a)["token"]
    code, out = SOC.invite_accept(conn, a, tok)
    assert code == 400 and "your own" in out["error"]


def test_acceptance_is_instantly_mutual_and_removal_closes_both_ways():
    """No pending state — and a one-sided removal would let the removed
    side keep sending."""
    conn, (a, b, _) = _db()
    out = _befriend(conn, a, b)
    assert out["already"] is False
    assert [f["id"] for f in SOC.friends_list(conn, a)] == [b]
    assert [f["id"] for f in SOC.friends_list(conn, b)] == [a]
    SOC.friend_remove(conn, a, b)
    assert SOC.friends_list(conn, a) == []
    assert SOC.friends_list(conn, b) == []
    code, _ = SOC.share_pick(conn, b, a, "nfl", "2026-09-13", "X", "rec_yds")
    assert code == 403, "the removed side can still send"


def test_the_friends_ceiling_holds_on_both_sides():
    """Lowered rather than filled: 100 real accounts is a lot of
    password hashing, and the rows are FK-checked so fakes won't insert.
    The comparison is what's under test, not the number."""
    conn, (a, b, c) = _db()
    _befriend(conn, a, c)
    old = SOC.MAX_FRIENDS
    SOC.MAX_FRIENDS = 1
    try:
        tok = SOC.invite_get_or_create(conn, a)["token"]
        code, out = SOC.invite_accept(conn, b, tok)
    finally:
        SOC.MAX_FRIENDS = old
    assert code == 400 and "full" in out["error"]


def test_no_lookup_endpoint_exists():
    """Friends form through links only. A search/lookup path in the
    social API would be the email oracle the module header refuses."""
    srv = _read("server.py")
    i = srv.index("def _social_post")
    body = srv[i:i + 400]
    assert ('"accept", "send", "send-parlay", "remove", "seen",\n'
            '                        "revoke-invite"') in body
    src = _read("engine", "social.py")
    assert "LIKE" not in src and "search" not in src.lower().replace(
        "search-by-email", "")


def test_display_name_never_repeats_the_full_address():
    conn, (a, b, _) = _db()
    assert SOC.display_name(conn, a) == "ethan"
    assert "@" not in SOC.display_name(conn, b)


# --- account promises --------------------------------------------------------

def test_deleting_an_account_severs_both_ends():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "Chris Olave", "rec_yds")
    A.delete_user(conn, a)
    assert SOC.friends_list(conn, b) == []
    for table, col in (("friendships", "friend_id"), ("pick_shares", "to_id")):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 0, f"{table} still holds rows after delete"
    n = conn.execute("SELECT COUNT(*) FROM friend_invites WHERE user_id=?",
                     (a,)).fetchone()[0]
    assert n == 0, "the dead account's invite link still works"


def test_the_export_carries_counts_and_identities_never_tokens():
    conn, (a, b, _) = _db()
    _befriend(conn, a, b)
    SOC.share_pick(conn, a, b, "nfl", "2026-09-13", "Chris Olave", "rec_yds",
                   "tail")
    out = A.export_user(conn, a)
    assert out["friends"] == {"count": 1}
    sent = out["picks_sent_to_friends"]
    assert sent and sent[0]["player"] == "Chris Olave"
    assert "side" not in sent[0] and "line" not in sent[0]
    tok = SOC.invite_get_or_create(conn, a)["token"]
    assert tok not in repr(out), "the invite token rides in the export"


# --- the front end's half ----------------------------------------------------

APPJS = _read("web", "js", "app.js")


def test_the_invite_travels_as_a_hash_route():
    """A clean path would unfurl in a link preview and leak whose invite
    it is; the fragment never reaches a scraper's server."""
    assert "`${location.origin}/#friend/${encodeURIComponent(token)}`" in APPJS
    i = APPJS.index("function entityRoute(h)")
    assert 'kind === "friend"' in APPJS[i:i + 2000]


def test_a_signed_out_open_stashes_and_sign_in_accepts():
    """The funnel rule: a link that answers "sign in first" and then
    forgets why you came is a funnel with a hole in the bottom."""
    assert 'PENDING_INVITE_KEY = "qb_pending_invite"' in APPJS
    assert "acceptPendingInvite" in APPJS
    i = APPJS.index("window.acctAuth")
    assert "acceptPendingInvite()" in APPJS[i:i + 3000], \
        "sign-in no longer fires the stashed invite"


def test_a_cold_load_resolves_unknown_before_deciding_signed_out():
    """_acctUser is null until boot's acctWho() answers, and both the
    invite route and the alerts inbox render before that. Null is
    UNKNOWN: treating it as signed-out stashed invites for people who
    were already signed in, and hid the inbox on a direct #alerts load."""
    i = APPJS.index("async function friendRoute(token)")
    assert "await acctWho()" in APPJS[i:i + 1200]
    j = APPJS.index("function renderAlerts()")
    body = APPJS[j:j + 1600]
    assert "if (!_acctUser) {" in body and "acctWho().then" in body


def test_the_copy_button_copies_the_invite_not_the_page():
    """The first cut called copyLink("",""), whose empty-slug fallback
    is location.href — the token never left the phone."""
    i = APPJS.index('[data-copy-invite]')
    assert "copyRawURL(inviteURL(" in APPJS[i:i + 600]


def test_the_send_panel_carries_identity_only():
    i = APPJS.index("function sendPanelHTML(r)")
    body = APPJS[i:APPJS.index("\n}", i)]
    for attr in ("data-send-player", "data-send-market", "data-send-date"):
        assert attr in body
    for word in ("data-send-side", "data-send-line", "data-send-odds"):
        assert word not in body


def test_the_inbox_row_is_a_door_only_onto_tonight_s_board():
    """A share from a past slate stays readable but inert — the board it
    pointed at is gone, and a door onto nothing is worse than no door.
    The logic lives in shareRowHTML since the Messages page landed —
    ONE renderer for a share row, used by Alerts and Messages both, so
    the two surfaces cannot disagree about what a share looks like."""
    i = APPJS.index("function shareRowHTML(sh)")
    body = APPJS[i:APPJS.index("\n}", i)]
    assert APPJS.count("sh.sport === state.sport ? findProp(slug) : null") >= 2, \
        "the door rule left the pick or the parlay branch"
    assert "off tonight’s board" in body
    j = APPJS.index("function friendInboxHTML()")
    fib = APPJS[j:APPJS.index("\n}", j)]
    assert "shareRowHTML" in fib, "Alerts grew its own share renderer"
    k = APPJS.index("async function renderMessages()")
    assert "shareRowHTML" in APPJS[k:k + 2500], \
        "Messages grew its own share renderer"


def test_seen_is_marked_after_display_not_on_fetch():
    i = APPJS.index("function renderAlerts()")
    body = APPJS[i:i + 2200]
    assert "/api/social/seen" in body
    assert "setTimeout" in body[:body.index("/api/social/seen")], \
        "seen fires on render, not after the reader has had a beat to look"


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
