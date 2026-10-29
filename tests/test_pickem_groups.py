"""Private pick'em groups (engine/pickgroups, engine/pickem view, server.py
/api/feed/pickem-group, js/social.js pickemGroupHTML).

Ethan, 2026-10-29: "keep building ... we want to keep user retainment", and
a lot of the members are 21 to 35. A group is the office pool: a name, an
invite link, and the pick'em's own tables counted over its members only.
What these hold:

  * a group needs a Social handle and a clean name; ten groups at most;
  * the link's code joins anybody with a handle, typed any case, with dashes;
    a wrong or retired code joins nobody;
  * the group's tables are the public ones cut to its members, and only a
    member is shown them;
  * the owner renames, removes and makes a new link (the old one dies);
    nobody else can; an owner who leaves hands it on, and the last one out
    deletes it; deleting an account leaves its groups the same way;
  * the page offers a chip a group, a start form, the invite, and an invite
    link that waits for a sign-up before it joins.

Run directly: `python3 tests/test_pickem_groups.py`
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import pickem as PK                                  # noqa: E402
from engine import pickgroups as PG                              # noqa: E402
from engine import socialfeed as SF                              # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


def _conn(*handles):
    from test_the_weekly_pickem import _conn as base
    c = base(*handles)
    PK.ensure_tables(c)
    PG.ensure_tables(c)
    return c


def test_a_group_needs_a_handle_and_a_clean_name():
    c = _conn("amy", None)
    assert PG.create(c, 2, "Sunday Squad")[0] == 403, "no handle, no group"
    for bad in ("x", "  ", "www.spam.com", "join https://x.io"):
        code, out = PG.create(c, 1, bad)
        assert code == 400, (bad, out)
    code, out = PG.create(c, 1, "  Sunday   Squad ")
    assert code == 200 and out["group"]["name"] == "Sunday Squad" and out["group"]["owner"], out
    assert out["group"]["members"] == 1 and len(out["group"]["code"]) == PG.CODE_LEN
    assert set(out["group"]["code"]) <= set(PG.ALPHABET) and not set("0O1IL") & set(out["group"]["code"])
    for i in range(PG.MAX_GROUPS - 1):
        assert PG.create(c, 1, f"Group {i}")[0] == 200
    assert PG.create(c, 1, "One too many")[0] == 400


def test_the_link_joins_and_a_wrong_or_old_one_does_not():
    c = _conn("amy", "bob", "cal", None)
    g = PG.create(c, 1, "Office Pool")[1]["group"]
    loose = "-".join([g["code"][:4].lower(), g["code"][4:]])
    code, out = PG.join(c, 2, loose)
    assert code == 200 and out["group"]["id"] == g["id"] and not out["group"]["owner"], out
    assert PG.join(c, 2, g["code"])[1].get("already") is True
    assert PG.join(c, 3, "ZZZZZZZZ")[0] == 404 and PG.join(c, 3, "short")[0] == 404
    assert PG.join(c, 4, g["code"])[0] == 403, "no handle, no seat"
    assert PG.peek(c, g["code"]) == {"name": "Office Pool", "members": 2, "by": "amy"}
    assert PG.peek(c, "nope") is None
    assert PG.new_code(c, 2, g["id"])[0] == 403, "only the owner makes a new link"
    fresh = PG.new_code(c, 1, g["id"])[1]["group"]["code"]
    assert fresh != g["code"] and PG.join(c, 3, g["code"])[0] == 404, "the old link is dead"
    assert PG.join(c, 3, fresh)[0] == 200


def test_only_a_member_sees_the_group_s_table_and_it_counts_only_them():
    from test_the_weekly_pickem import _seed, _t
    c = _conn("amy", "bob", "cal")
    g = PG.create(c, 1, "Pool")[1]["group"]
    PG.join(c, 2, g["code"])
    k = _t(2026, 10, 18, 17)
    for uid, res in ((1, "won"), (2, "lost"), (3, "won")):
        _seed(c, uid, "g1", "CHI", "GB", "2026-10-18", k, "GB")
        c.execute("UPDATE pickem_picks SET result=? WHERE user_id=?", (res, uid))
    now = _t(2026, 10, 19, 12)
    v = PK.view(c, "nfl", viewer=1, week=PK.week_of(k), now=now, group=g["id"])
    assert [x["id"] for x in v["groups"]] == [g["id"]] and v["group"]["name"] == "Pool"
    handles = [r["handle"] for r in v["group"]["week_table"]["rows"]]
    assert handles == ["amy", "bob"], handles
    assert len(v["week_table"]["rows"]) == 3, "the public table is untouched"
    outsider = PK.view(c, "nfl", viewer=3, week=PK.week_of(k), now=now, group=g["id"])
    assert outsider["group"] is None and outsider["groups"] == [], "a group is shown only to its members"
    assert PK.view(c, "nfl", viewer=None, now=now)["groups"] == []


def test_owner_tools_leaving_and_an_account_going():
    c = _conn("amy", "bob", "cal")
    g = PG.create(c, 1, "Pool")[1]["group"]
    PG.join(c, 2, g["code"])
    PG.join(c, 3, g["code"])
    assert PG.rename(c, 2, g["id"], "Mine now")[0] == 403 and PG.remove(c, 2, g["id"], "cal")[0] == 403
    assert PG.rename(c, 1, g["id"], "The Pool")[1]["group"]["name"] == "The Pool"
    assert PG.remove(c, 1, g["id"], "@cal")[0] == 200 and PG.members(c, g["id"]) == {1, 2}
    assert PG.remove(c, 1, g["id"], "amy")[0] == 404, "an owner leaves, not removes themself"
    assert PG.leave(c, 1, g["id"])[0] == 200
    assert PG.mine(c, 2)[0]["owner"] is True, "the earliest member left takes it over"
    SF.delete_user(c, 2)
    assert not c.execute("SELECT 1 FROM pickem_groups").fetchone(), "the last one out deletes it"
    assert not c.execute("SELECT 1 FROM pickem_group_members").fetchone()
    h = PG.create(c, 3, "Cal's")[1]["group"]
    out = SF.export_user(c, 3)
    assert out["pickem_groups"] == [{"name": "Cal's", "owner": True, "joined_at": out["pickem_groups"][0]["joined_at"]}]
    assert PG.act(c, 3, {"do": "leave", "group": h["id"]})[0] == 200 and PG.act(c, 3, {"do": "nope", "group": 1})[0] == 400


def test_tuesday_s_line_names_the_group_place():
    from engine import pushalerts as PA
    from engine import pushmine as PM
    from test_your_pickem_week import _week, _told
    from test_the_weekly_pickem import _t
    c = _week("amy", "bob", "cal", "dee", "eve")
    PG.ensure_tables(c)
    g = PG.create(c, 3, "Cal's Pool")[1]["group"]
    PG.join(c, 2, g["code"])
    assert PK.recap_pass(c, now=_t(2026, 10, 27, 18)) >= 1
    (title, body, _url), = _told(c, 3)
    assert "2nd of 2 in Cal's Pool" in body, body
    (_t1, amy, _u1), = _told(c, 1)
    assert " in " not in amy.split(". ")[0], "no group, no group line"


def test_the_server_routes_and_the_page():
    srv = READ("server.py")
    assert '"pickem-remind", "pickem-group"):' in srv and 'code, out = PG.act(conn, uid,' in srv
    at = srv.index('if path == "pickem-group":')
    assert 'rate_ok(f"pkgroup:{self._client_ip()}", 30)' in srv[at:at + 600], "the peek is rate-limited"
    assert 'group=_int(one("group")) or None' in srv
    js = READ("web", "js", "social.js")
    for want in ("function pickemGroupHTML(P)", "function pickemNewGroupHTML()", "function pickemJoinHTML(G, code)",
                 'const PK_JOIN_KEY = "qb_pk_join";', 'if (kind === "pickem" && arg === "join") {',
                 "`${location.origin}/#feed/pickem/join/${code}`", 'data-fd-form="pk-create"',
                 'data-fd="pk-kick"', "A new link stops the old one working.",
                 "if (waiting) { location.hash = `#feed/pickem/join/${waiting}`; return; }"):
        assert want in js, want
    # The scope's own chips drive the tables: a group's, the friends', everyone's.
    assert 'tbl(1, 1)' in js and 'tbl(0, 0)' in js
    policy = " ".join(READ("web", "privacy.html").split())
    assert "<code>pickem_groups</code>, <code>pickem_group_members</code>" in policy
    assert "anyone with its link sees its name, how many are in it" in policy


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
