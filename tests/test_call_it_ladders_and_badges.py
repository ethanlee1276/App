"""Call it across every game: the ladders, the flame in the chat, the share.

The ideas list (2026-10-25, "the live game as a place to be", item 3):
a week's and a season's leaderboard across every game, a streak flame
beside a handle in the chat, and a "Called it" card to share at five in a
row (engine/callit ladder / current_streaks, engine/gamechat room_view,
js/detail.js ciLadderHTML, js/chat.js). What these hold:

  - a ladder ranks by calls right, then by fewer calls, over the span, and
    nobody stands on it under ten graded calls;
  - a flame is the current run of calls right (voids skipped), from three;
  - the room puts each author's flame on their messages; the chat draws it;
  - the game's card carries both ladders, and offers the share at five in a
    row and every five after, never in between.

    python3 tests/test_call_it_ladders_and_badges.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import callit as CI           # noqa: E402
from engine import gamechat as GC         # noqa: E402
from engine import socialfeed as SF       # noqa: E402

DETAIL = open(os.path.join(ROOT, "web", "js", "detail.js"), encoding="utf-8").read()
CHAT = open(os.path.join(ROOT, "web", "js", "chat.js"), encoding="utf-8").read()
NOW = 1793030400.0


def _db(d):
    conn = A.connect(Path(d) / "a.db")
    CI.ensure_tables(conn)
    SF.ensure_tables(conn)
    CI._cache.clear()
    return conn


def _fan(conn, handle):
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                       "VALUES (?, 'x', ?, 1, ?)", (f"{handle}@example.com", NOW, NOW))
    uid = int(cur.lastrowid)
    code, out = SF.profile_set(conn, uid, handle, "")
    assert code == 200, out
    return uid


def _calls(conn, uid, results, start=NOW - 3600, game="nfl_1"):
    for i, won in enumerate(results):
        conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at, result, won) VALUES (?,?,?,?,?,?,?)",
                     (uid, game, f"u{uid}_{i}", "td", start + i, "td" if won else ("punt" if won is not None else "void"),
                      None if won is None else int(won)))
    conn.commit()


def test_the_ladder_ranks_by_right_then_fewer_calls_and_needs_ten():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        a, b, c, e = (_fan(conn, h) for h in ("casey_k", "steelcurtain", "burrowszn", "newfan"))
        _calls(conn, a, [1] * 8 + [0] * 4)          # 8 of 12
        _calls(conn, b, [1] * 8 + [0] * 2)          # 8 of 10: same right, fewer calls
        _calls(conn, c, [1] * 9 + [0] * 6)          # 9 of 15
        _calls(conn, e, [1] * 5)                    # 5 of 5: under ten, not on it
        _calls(conn, a, [1] * 20, start=NOW - 30 * 86400, game="nfl_0")   # a month ago
        week = CI.ladder(conn, CI.week_start(NOW), now=NOW)
        assert [(r["handle"], r["right"], r["total"]) for r in week] == [
            ("burrowszn", 9, 15), ("steelcurtain", 8, 10), ("casey_k", 8, 12)]
        CI._cache.clear()
        season = CI.ladder(conn, NOW - 60 * 86400, now=NOW)
        assert season[0] == {"handle": "casey_k", "right": 28, "total": 32}
        conn.close()


def test_the_flame_is_the_run_now_voids_skipped_from_three():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        a, b, c = (_fan(conn, h) for h in ("casey_k", "steelcurtain", "burrowszn"))
        _calls(conn, a, [0, 1, 1, None, 1, 1])      # newest last: four right, a void inside
        _calls(conn, b, [1, 1, 1, 0])               # the last one missed
        _calls(conn, c, [0, 1, 1])                  # two: no flame yet
        assert CI.current_streaks(conn, [a, b, c], NOW) == {a: 4}
        conn.close()
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "b.db")
        CI._cache.clear()
        assert CI.current_streaks(conn, [1, 2], NOW) == {}, "no calls table yet: nobody has a flame"
        conn.close()


def test_the_room_carries_each_authors_flame():
    with tempfile.TemporaryDirectory() as d:
        conn = _db(d)
        a, b = _fan(conn, "casey_k"), _fan(conn, "steelcurtain")
        _calls(conn, a, [1] * 6)
        for uid, body in ((a, "called the TD"), (b, "lucky")):
            code, out = GC.send(conn, uid, "nfl_990123", body, now=time.time())
            assert code == 200, out
        code, out = GC.room_view(conn, "nfl_990123", None)
        assert code == 200
        by = {m["body"]: m["by"] for m in out["messages"]}
        assert by["called the TD"]["streak"] == 6 and "streak" not in by["lucky"]
        conn.close()
    assert 'Number(p.streak) >= 3 ? `<span class="gch-flame"' in CHAT


def test_the_cards_state_carries_both_ladders():
    src = open(os.path.join(ROOT, "engine", "callit.py"), encoding="utf-8").read()
    assert '"week": ladder(conn, week_start()), "season": ladder(conn, SEASON_START)}' in src


def _card(v, span="week"):
    i = DETAIL.index("function ciBodyHTML(")
    body = DETAIL[i:DETAIL.index("\n}\n", i) + 3]
    j = DETAIL.index("function ciLadderHTML(")
    lad = DETAIL[j:DETAIL.index("\n}\n", j) + 3]
    js = f"""
    const escapeHtml = (s) => String(s), escapeAttr = escapeHtml;
    const CI_WORD = {{ td: "Touchdown" }};
    const _ci = {{ note: "", span: {json.dumps(span)} }};
    {body}
    {lad}
    console.log(JSON.stringify(ciBodyHTML({json.dumps(v)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_card_draws_the_ladders_and_the_share_at_every_five():
    week = [{"handle": "burrowszn", "right": 9, "total": 15}]
    season = [{"handle": "casey_k", "right": 28, "total": 32}]
    v = {"open": None, "signed_in": True, "board": [], "game": {"right": 5, "total": 6}, "streak": 5, "best": 5,
         "week": week, "season": season}
    out = _card(v)
    assert 'data-ci-span="week">This week</button>' in out and "<b>burrowszn</b> 9 of 15" in out
    assert "casey_k" not in out
    assert "<b>casey_k</b> 28 of 32" in _card(v, "season")
    assert "I called 5 in a row on Qellys Book’s Call it." in out and "5 in a row — share it" in out
    assert "data-ci-share" in _card(dict(v, streak=10)) and "data-ci-share" not in _card(dict(v, streak=6))
    none = _card(dict(v, week=[], season=[]))
    assert "ci-ladder" not in none, "no ladder at all until somebody stands on one"
    quiet = _card(dict(v, week=[]))
    assert "Nobody has ten graded calls this week yet." in quiet


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
