"""The founder's profile.

Ethan, 2026-10-07: "we need to also make my profile like the 'god' profile
on the website, i know u said sum about putting a gold star or sum next to
my name so lets do that and more."

What this pins:
  - only the box command (engine/socialfeed.crown) makes a founder; it
    needs a profile, gives the gold tick too, and no profile edit can set
    or keep it on someone else;
  - the founder flag rides everywhere the name does: the profile, posts,
    comments, people lists, leaderboards;
  - the founder (and nobody else) pins one post, and that post leads For
    You and Latest for every reader, once;
  - the moderation door on the server is the owner token OR the founder's
    own session, and the queue lists hidden items too so a hide can always
    be undone;
  - the page draws the Founder pill, the gold ring and the founder tools
    only from the server's flag.

Run directly: `python3 tests/test_founder.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam"):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    return conn, ids


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_only_the_box_command_crowns_and_it_needs_a_profile():
    conn, (ethan, sam) = _db()
    assert SF.crown(conn, "nobody@example.com")[0] == 404
    assert SF.crown(conn, "ethan@example.com")[0] == 409, "a profile comes first"
    assert SF.profile_set(conn, ethan, "Ethan", "Lions fan")[0] == 200
    code, out = SF.crown(conn, "ETHAN@example.com")
    assert code == 200 and out["profile"]["founder"] and out["profile"]["verified"]
    assert SF.is_founder(conn, ethan) and not SF.is_founder(conn, sam)
    # A profile save never touches the flag (no field for it), and taking it off works.
    assert SF.profile_set(conn, ethan, "Ethan", "new bio")[0] == 200
    assert SF.profile_of(conn, ethan)["founder"]
    assert SF.crown(conn, "ethan@example.com", on=False)[0] == 200
    assert not SF.is_founder(conn, ethan)


def test_the_flag_rides_on_posts_comments_and_people():
    conn, (ethan, sam) = _db()
    SF.profile_set(conn, ethan, "Ethan", "")
    SF.profile_set(conn, sam, "Sam", "")
    SF.crown(conn, "ethan@example.com")
    code, out = SF.create_talk(conn, ethan, "nfl", "Week 6", "Lions roll")
    assert code == 200
    pid = out["id"]
    assert SF.add_comment(conn, ethan, pid, "agreed")[0] == 200
    assert SF.add_comment(conn, sam, pid, "nah")[0] == 200
    posts = SF.feed(conn, viewer=sam, order="new")["posts"]
    assert posts[0]["founder"] is True
    det = SF.post_detail(conn, pid, sam)[1]["post"]
    marks = {c["handle"]: c["founder"] for c in det["comment_list"]}
    assert marks == {"Ethan": True, "Sam": False}
    code, page = SF.profile_page(conn, "Ethan", sam)
    assert code == 200 and page["profile"]["founder"] is True
    assert SF.profile_page(conn, "Sam", ethan)[1]["profile"]["founder"] is False


def test_the_founder_pins_one_post_and_it_leads_the_feed_once():
    conn, (ethan, sam) = _db()
    SF.profile_set(conn, ethan, "Ethan", "")
    SF.profile_set(conn, sam, "Sam", "")
    first = SF.create_talk(conn, sam, "nfl", "old take", "hm")[1]["id"]
    for i in range(3):
        SF.create_talk(conn, sam, "nfl", f"take {i}", "x", now=None)
    assert SF.pin(conn, sam, first)[0] == 403, "not the founder"
    SF.crown(conn, "ethan@example.com")
    assert SF.pin(conn, ethan, 999999)[0] == 404
    assert SF.pin(conn, ethan, first)[0] == 200
    for order in ("new", "hot"):
        posts = SF.feed(conn, viewer=sam, order=order)["posts"]
        assert posts[0]["id"] == first and posts[0]["pinned"], order
        assert [p["id"] for p in posts].count(first) == 1, "once, not twice"
    # Filters and later pages are left alone.
    assert not any(p.get("pinned") for p in SF.feed(conn, viewer=sam, order="new", sport="mlb")["posts"])
    # Pinning another replaces it; unpinning clears it.
    other = SF.feed(conn, viewer=sam, order="new")["posts"][1]["id"]
    SF.pin(conn, ethan, other)
    assert SF.pinned_id(conn) == other
    SF.pin(conn, ethan, other, on=False)
    assert SF.pinned_id(conn) is None
    # A hidden post cannot stay pinned at the top.
    SF.pin(conn, ethan, first)
    SF.set_hidden(conn, "post", first, True)
    assert SF.pinned_id(conn) is None


def test_the_queue_lists_hidden_items_so_a_hide_can_be_undone():
    conn, (ethan, sam) = _db()
    SF.profile_set(conn, sam, "Sam", "")
    pid = SF.create_talk(conn, sam, "nfl", "spam", "buy my picks")[1]["id"]
    assert SF.set_hidden(conn, "post", pid, True)[0] == 200
    items = SF.reported(conn)
    assert any(i["kind"] == "post" and i["id"] == pid and i["hidden"] and i["reports"] == 0 for i in items)
    SF.set_hidden(conn, "post", pid, False)
    assert not any(i["id"] == pid for i in SF.reported(conn))


def test_the_server_door_is_the_token_or_the_founders_session():
    src = _read("server.py")
    door = src[src.index("def _founder_or_owner"):src.index("def _feed_post")]
    assert "return not self._owner_refused()" in door and 'SF.is_founder(conn, who["id"])' in door
    post = src[src.index("def _feed_post"):src.index("def _social_get")]
    assert '"pin"' in post and "SF.pin(conn, uid," in post
    # crown is a box command: no route reaches it.
    assert "SF.crown(" not in src


def test_the_page_draws_the_founder_from_the_servers_flag():
    js = _read("web", "js", "social.js")
    assert 'p.founder\n    ? `<span class="fd-founder"' in js
    assert 'p && p.founder ? " fd-av-founder" : ""' in js
    assert '<section class="fd-card fd-prof${p.founder ? " founder" : ""}">' in js
    assert "const isBoss = () => !!(F.me && F.me.founder);" in js
    for act in ('act === "pin"', 'act === "mod-hide" || act === "mod-restore"', 'act === "verify"'):
        assert act in js, act
    assert 'if (isBoss()) tabs.push(["mod", "Moderation"]);' in js
    css = _read("web", "css", "social.css")
    for rule in (".fd-founder {", ".fd-av-founder {", ".fd-prof.founder {", ".fd-prof-crown {", ".fd-pinned {", ".fd-mod-row {"):
        assert rule in css, rule


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            n += 1
    print(f"\n{n} tests passed.")
