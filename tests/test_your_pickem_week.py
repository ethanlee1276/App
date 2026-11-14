"""Your pick'em week comes back (engine/pickem, engine/karma, js/social.js;
Ethan, 2026-10-28: "keep building and adding more features").

Round one brought the pick'em to people before picks lock. This closes the
loop after the games:

  * Tuesday (Wednesday for a late final), once every pick of the week just
    over is graded, a player hears their record, their place, and their
    place among the friends who played, once a sport a week, unless they
    turned the pick'em pushes off; a perfect week says so;
  * two badges: pick'em winners, and perfect weeks;
  * a profile carries this season's pick'em record and place.

Run directly: `python3 tests/test_your_pickem_week.py`
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import karma as K                                    # noqa: E402
from engine import pickem as PK                                  # noqa: E402
from engine import pushalerts as PA                              # noqa: E402
from engine import pushmine as PM                                # noqa: E402
from engine import social as SOC                                 # noqa: E402
from engine import socialfeed as SF                              # noqa: E402

LAST_SUN = "2026-10-25"
GAMES = [("NYJ", "BUF"), ("DAL", "PHI"), ("SEA", "SF"), ("KC", "LV"), ("DEN", "LAC"), ("ARI", "LAR")]


def _week(*handles):
    """Last week's picks, graded: amy 3-1, bob 4-0, cal 2-2, dee 1-0 (her
    pushes off) and eve 1-0 with a game still open. amy and cal are friends."""
    from test_the_weekly_pickem import _conn, _seed, _t
    c = _conn(*handles)
    PK.ensure_tables(c)
    PM.ensure_tables(c)
    SOC.ensure_tables(c)
    for a, b in ((1, 3), (3, 1)):
        c.execute("INSERT INTO friendships (user_id, friend_id, created_at) VALUES (?,?,?)", (a, b, 0))
    lines = {1: "WWWL", 2: "WWWW", 3: "WWLL", 4: "W", 5: "W?"}
    for uid, line in lines.items():
        for i, res in enumerate(line):
            h, a = GAMES[i]
            gid = f"{LAST_SUN}|{a}@{h}"
            _seed(c, uid, gid, h, a, LAST_SUN, _t(2026, 10, 25, 17), h)
            if res != "?":
                c.execute("UPDATE pickem_picks SET result=? WHERE user_id=? AND gid=?",
                          ("won" if res == "W" else "lost", uid, gid))
    for uid in lines:
        assert PA.subscribe(c, f"{uid:064x}", "apns", user_id=uid, topics=("posted", "pickem"))[0] == 200
    PK.set_remind(c, 4, False)
    c.commit()
    return c


def _told(c, uid):
    return [tuple(r) for r in c.execute("SELECT title, body, url FROM push_mine WHERE user_id=? AND id LIKE "
                                        "'pickem:recap:%'", (uid,))]


def test_tuesday_brings_the_week_back_once():
    from test_the_weekly_pickem import _t
    c = _week("amy", "bob", "cal", "dee", "eve")
    assert PK.recap_pass(c, now=_t(2026, 10, 26, 18)) == 0, "Monday: the week is not over"
    assert PK.recap_pass(c, now=_t(2026, 10, 27, 13, 30)) == 0, "9:30 a.m. Eastern: too early"
    tue = _t(2026, 10, 27, 14, 30)                                  # Tuesday, 10:30 a.m. EDT
    assert PK.recap_pass(c, now=tue) == 3, "amy, bob and cal; dee said no, eve's week is still open"
    assert _told(c, 1) == [("Your NFL pick'em week: 3-1",
                            "2nd of 5 · 1st of 2 among your friends. This week's games are up.", "/#feed/pickem/nfl")]
    assert _told(c, 3)[0][1] == "3rd of 5 · 2nd of 2 among your friends. This week's games are up."
    assert _told(c, 2)[0][:2] == ("Your NFL pick'em week: 4-0", "1st of 5. This week's games are up."), \
        "no friends: no friends' place; four winners: not a perfect week"
    assert not _told(c, 4) and not _told(c, 5)
    assert PK.recap_pass(c, now=tue + 900) == 0, "once a week"
    assert c.execute("SELECT recap FROM pickem_prefs WHERE user_id=1").fetchone()[0] == "nfl:2026-10-20"
    # eve's last game grades overnight: Wednesday brings hers.
    c.execute("UPDATE pickem_picks SET result='won' WHERE user_id=5 AND result IS NULL")
    assert PK.recap_pass(c, now=_t(2026, 10, 28, 15)) == 1
    assert _told(c, 5)[0][:2] == ("Your NFL pick'em week: 2-0", "3rd of 5. This week's games are up.")
    assert PK.recap_pass(c, now=_t(2026, 10, 29, 15)) == 0, "Thursday: that week is let go"
    assert PM.TTL_S["pickem_recap"] == 12 * 3600


def test_a_perfect_week_says_so_and_the_switch_covers_both_pushes():
    from test_the_weekly_pickem import _conn, _seed, _t
    c = _conn("amy")
    PK.ensure_tables(c)
    PM.ensure_tables(c)
    for h, a in GAMES[:5]:
        _seed(c, 1, f"{LAST_SUN}|{a}@{h}", h, a, LAST_SUN, _t(2026, 10, 25, 17), h)
    c.execute("UPDATE pickem_picks SET result='won'")
    assert PA.subscribe(c, f"{1:064x}", "apns", user_id=1, topics=("pickem",))[0] == 200
    assert PK.recap_pass(c, now=_t(2026, 10, 27, 15)) == 1
    assert _told(c, 1)[0][:2] == ("Your NFL pick'em week: 5-0",
                                  "1st of 1 · a perfect week, +25 karma. This week's games are up.")
    c2 = _week("amy", "bob", "cal", "dee", "eve")
    PK.set_remind(c2, 1, False)
    assert PK.recap_pass(c2, now=_t(2026, 10, 27, 15)) == 2 and not _told(c2, 1), "off is off for both pushes"


def test_places_read_like_english():
    assert [PK._nth(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111, 112)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th", "112th"]


def test_badges_for_winners_and_perfect_weeks():
    c = _week("amy", "bob", "cal", "dee", "eve")
    K.ensure_tables(c)
    for i in range(12):
        K.award(c, 1, "pickem_won", f"nfl:g{i}", now=1_800_000_000 + i)
    K.award(c, 1, "pickem_week", "nfl:2026-10-20", now=1_800_000_100)
    b = {x["key"]: x for x in K.badges(c, 1)}
    assert (b["pickem"]["n"], b["pickem"]["tier"], b["pickem"]["next"]) == (12, 1, 50), b["pickem"]
    assert (b["perfect"]["n"], b["perfect"]["tier"], b["perfect"]["tier_name"]) == (1, 1, "Bronze"), b["perfect"]
    assert {"pickem", "perfect"} <= {f[0] for f in K.FAMILIES}
    kjs = (ROOT / "web" / "js" / "karma.js").read_text(encoding="utf-8")
    assert 'pickem: "🏈", perfect: "💯"' in kjs


def test_a_profile_carries_this_seasons_pickem():
    from test_the_weekly_pickem import _seed, _t
    c = _week("amy", "bob", "cal", "dee", "eve")
    now = _t(2026, 10, 28, 15)
    assert PK.season_lines(c, 1, now=now) == [{"sport": "nfl", "w": 3, "l": 1, "p": 0, "rank": 2, "players": 5}]
    _seed(c, 1, "2026-10-24|Army@Navy", "Navy", "Army", "2026-10-24", _t(2026, 10, 24, 16), "Navy", sport="cfb")
    c.execute("UPDATE pickem_picks SET result='lost' WHERE sport='cfb'")
    got = PK.season_lines(c, 1, now=now)
    assert [g["sport"] for g in got] == ["nfl", "cfb"] and got[1] == {"sport": "cfb", "w": 0, "l": 1, "p": 0,
                                                                      "rank": 1, "players": 1}, got
    assert PK.season_lines(c, 4, now=now)[0]["rank"] == 4, "a player whose pushes are off still has a record"
    assert PK.season_lines(c, 5, now=now)[0]["w"] == 1
    code, out = SF.profile_page(c, "amy")
    assert code == 200 and [g["sport"] for g in out["profile"]["pickem"]] == ["nfl", "cfb"], out["profile"].get("pickem")
    ex = SF.export_user(c, 4)["pickem_remind"]
    assert ex == [{"remind": PK.REMIND_OFF, "recap": ""}], ex


def test_the_profile_draws_the_line():
    from test_the_weekly_pickem import _node
    p = {"handle": "amy", "name": "Amy", "color": 1, "team": "", "since": 1_790_000_000, "bio": "",
         "record": {}, "record30": {}, "followers": 0, "following_count": 0, "tails": 0, "mutual": {"n": 0},
         "pickem": [{"sport": "nfl", "w": 55, "l": 36, "p": 0, "rank": 3, "players": 41},
                    {"sport": "cfb", "w": 12, "l": 8, "p": 1, "rank": 20, "players": 33}]}
    got = _node(f"process.stdout.write(JSON.stringify({{a: S.profileHeaderHTML({json.dumps(p)}, {{mine: true}}),"
                f"b: S.profileHeaderHTML({json.dumps(dict(p, pickem=[]))}, {{mine: true}})}}));")
    if got is None:
        return
    line = got["a"][got["a"].index("fd-prof-pk"):]
    line = " ".join(line[:line.index("</p>")].split())
    assert "Pick’em this season <span><b>NFL 55-36</b> #3 of 41</span> · <span><b>CFB 12-8-1</b> #20 of 33</span>" in line, line
    assert ".fd-prof-pk > span { white-space: nowrap; }" in (ROOT / "web" / "css" / "social.css").read_text(encoding="utf-8")
    assert "fd-prof-pk" not in got["b"], "nobody who has not played sees a line"


def test_the_page_and_the_policy_say_it():
    social = (ROOT / "web" / "js" / "social.js").read_text(encoding="utf-8")
    assert "<b>Pick’em pushes</b>" in social and "and your week's result on Tuesday." in social
    assert 'tfToast(on ? "On: pick’em pushes." : "Pick’em pushes off.");' in social
    policy = " ".join((ROOT / "web" / "privacy.html").read_text(encoding="utf-8").split())
    for want in ('unless you turned off "Pick’em pushes" on its page',
                 "and on the Tuesday after a week you played, your record that week and your place, overall and "
                 "among your friends who played.",
                 "this season's record and place show on your profile",
                 "and the last week whose result we sent you."):
        assert want in policy, want
    assert "return told + recap_pass(conn, now=t)" in (ROOT / "engine" / "pickem.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
