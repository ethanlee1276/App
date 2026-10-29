"""Your month (engine/yourmonth, karma.me's `month`, js/karma.js krMonthHTML,
krMonthLineHTML, krMonthCanvas).

Ethan, 2026-10-29: "keep building". A month's recap: the live games a member
watched here, the days they earned karma on, the karma, their pick'em and
their Call it, on the Karma tab, with a picture for the share sheet, and as
the Live card's one line in a new month's first week. What these hold:

  * the month just ended for a new month's first seven days, else this one
    so far, in Eastern days;
  * only what the site already keeps for the member and shows them; never a
    bet, a stake or a pick (karma never pays for bets, and a picture of
    winnings would be an ad for betting), and nothing new kept;
  * in a phone browser: the Live card's line in the first week, the Karma
    tab's card, and a picture drawn.

Run directly: `python3 tests/test_your_month.py`
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import callit as CI                                   # noqa: E402
from engine import karma as K                                     # noqa: E402
from engine import pickem as PK                                   # noqa: E402
from engine import yourmonth as YM                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
ET = YM.ET


def _t(y, m, d, h=12):
    return dt.datetime(y, m, d, h, tzinfo=ET).timestamp()


def test_which_month_and_its_eastern_days():
    assert YM.which(_t(2026, 11, 1, 0)) == ("2026-10", True), "the 1st: the whole of the month before"
    assert YM.which(_t(2026, 11, 7, 23)) == ("2026-10", True)
    assert YM.which(_t(2026, 11, 8, 0)) == ("2026-11", False), "then this one so far"
    assert YM.which(_t(2026, 10, 29)) == ("2026-10", False)
    assert YM.which(_t(2027, 1, 3)) == ("2026-12", True), "across the year"
    # 23:30 Eastern on the 31st is November in UTC: still October here.
    assert YM.which(_t(2026, 10, 31, 23) + 1800) == ("2026-10", False)
    first, last, start, end = YM.bounds("2026-10")
    assert (first, last) == ("2026-10-01", "2026-10-31")
    assert start == _t(2026, 10, 1, 0) and end == _t(2026, 11, 1, 0), "midnight to midnight, Eastern"
    assert YM.bounds("2026-12")[:2] == ("2026-12-01", "2026-12-31")
    assert YM.bounds("2027-02")[1] == "2027-02-28"


def _db():
    c = sqlite3.connect(":memory:")
    K.ensure_tables(c)
    PK.ensure_tables(c)
    CI.ensure_tables(c)
    return c


def test_the_numbers_are_the_months_own():
    c = _db()
    ev = [(1, "watch_join", "a", 10, _t(2026, 10, 3), "2026-10-03"), (1, "watch", "b", 40, _t(2026, 10, 3), "2026-10-03"),
          (1, "day", "c", 5, _t(2026, 10, 9), "2026-10-09"), (1, "quest", "d", 30, _t(2026, 10, 31, 23), "2026-10-31"),
          (1, "day", "e", 5, _t(2026, 9, 30), "2026-09-30"),          # September
          (1, "day", "f", 5, _t(2026, 11, 1, 1), "2026-11-01"),       # November
          (2, "day", "g", 5, _t(2026, 10, 9), "2026-10-09")]          # someone else
    c.executemany("INSERT INTO karma_events (user_id, kind, ref, pts, at, day) VALUES (?,?,?,?,?,?)", ev)
    c.executemany("INSERT INTO karma_watch (user_id, room, league, first_at, last_at) VALUES (?,?,?,?,?)",
                  [(1, f"nfl:{i}", "nfl", _t(2026, 10, 2 + i), _t(2026, 10, 2 + i)) for i in range(4)]
                  + [(1, "nba:1", "nba", _t(2026, 10, 22), _t(2026, 10, 22)),
                     (1, "nba:0", "nba", _t(2026, 9, 29), _t(2026, 9, 29))])
    pick = "INSERT INTO pickem_picks (user_id, sport, week, gid, home, away, game_date, kickoff, pick, created_at, " \
           "updated_at, result) VALUES (1, 'nfl', ?, ?, 'BUF', 'KC', ?, 0, 'BUF', 0, 0, ?)"
    for i, (day, res) in enumerate((("2026-10-05", "won"), ("2026-10-12", "won"), ("2026-10-19", "lost"),
                                    ("2026-10-26", "push"), ("2026-10-26", None), ("2026-09-28", "won"))):
        c.execute(pick, (f"w{i}", f"g{i}", day, res))
    c.executemany("INSERT INTO callit_calls (user_id, game, unit, call, at, won) VALUES (?,?,?,?,?,?)",
                  [(1, "g1", f"u{i}", "x", _t(2026, 10, 10), won) for i, won in enumerate((1, 1, 0, None))]
                  + [(1, "g2", "u9", "x", _t(2026, 9, 10), 1)])
    m = YM.summary(c, 1, now=_t(2026, 11, 2))
    assert (m["month"], m["name"], m["whole"]) == ("2026-10", "October", True), m
    assert m["karma"] == 85 and m["days"] == 3, ("October's karma and the days it came on", m)
    assert m["watched"] == 5 and m["league"] == "NFL" and m["league_games"] == 4, m
    assert m["pickem"] == {"w": 2, "l": 1, "p": 1}, ("graded picks only", m)
    assert m["calls"] == {"n": 3, "right": 2}, ("decided calls only", m)
    assert m["any"]
    so_far = YM.summary(c, 1, now=_t(2026, 10, 29))
    assert not so_far["whole"] and so_far["karma"] == 85
    nobody = YM.summary(c, 3, now=_t(2026, 11, 2))
    assert not nobody["any"] and nobody["pickem"] is None and nobody["calls"] is None
    # A database no page has made the tables in: nothing, not an error.
    bare = YM.summary(sqlite3.connect(":memory:"), 1, now=_t(2026, 11, 2))
    assert not bare["any"] and bare["karma"] == 0


def test_never_a_bet_and_nothing_new_kept():
    src = READ("engine", "yourmonth.py")
    code = src[src.index('"""', 3) + 3:]                          # past the docstring, which says why
    for gone in ("mybets", "bet_clv", "user_data", "stake", "CREATE TABLE", "INSERT", "UPDATE"):
        assert gone not in code, gone
    m = YM.summary(_db(), 1, now=_t(2026, 11, 2))
    assert set(m) == {"month", "name", "whole", "from", "to", "karma", "days", "watched", "league", "league_games",
                      "pickem", "calls", "any"}, sorted(m)
    assert '"month": YM.summary(conn, uid, now=t)}' in READ("engine", "karma.py"), "the Karma tab's answer carries it"
    kjs = READ("web", "js", "karma.js")
    stats = kjs[kjs.index("function krMonthStats(m)"):kjs.index("function krMonthHTML(m)")]
    assert "bet" not in stats.lower() and "stake" not in stats.lower()
    assert "${krMonthHTML(v.month)}\n    ${krCampHTML(v)}" in kjs, "under the level, before the rest"
    line = kjs[kjs.index("function krMonthLineHTML(m)"):kjs.index("function krMonthCanvas(m, handle)")]
    assert 'if (!m || !m.whole || !m.any) return "";' in line, "the Live card's line only in a new month's first week"
    assert "${krAskHTML(d) || krMonthLineHTML(v.month) || krPickemHTML(v.pickem)}" in kjs, "one line, never three"
    share = kjs[kjs.index("async function krMonthShare(btn)"):kjs.index("function krRecentHTML(v)")]
    assert "exportCard(c, `qellys-${String(m.month || \"month\")}.png`, done);" in share
    assert 'if (act === "month-share") { krMonthShare(b); return; }' in kjs
    assert ".krm-grid { display: grid;" in READ("web", "css", "karma.css")


# --- in a phone browser ----------------------------------------------------------
def test_in_a_phone_browser_the_line_the_card_and_the_picture():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    import test_todays_question as TQ
    conn, (me, _sam) = TQ._db()
    month = {"month": "2026-10", "name": "October", "whole": True, "from": "2026-10-01", "to": "2026-10-31",
             "karma": 1240, "days": 19, "watched": 18, "league": "NFL", "league_games": 11,
             "pickem": {"w": 14, "l": 6, "p": 0}, "calls": {"n": 20, "right": 12}, "any": True}
    v = dict(K.me(conn, me), camp=None, quests=[], month=month)
    q = {"qkey": TQ.DAY, "text": "Who leads CIN in receiving yards this season?",
         "options": ["Tee Higgins", "Ja'Marr Chase", "Mike Gesicki", "Andrei Iosivas"], "mine": 1, "answer": 1,
         "open": False, "day": TQ.DAY, "league": "nfl", "game": "LAR @ CIN"}
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/feed/me*", ful(json.dumps({"me": who["profile"], "signed_in": True})))
                page.route("**/api/karma/me*", ful(json.dumps(v)))
                page.route("**/api/trivia/daily*", ful(json.dumps({"signed_in": True, "day": TQ.DAY, "q": q})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');"
                                     "localStorage.setItem('qb_new_2026_10_29','1');"
                                     f"localStorage.setItem('qb_kr_level','{v['level']}');}}catch(e){{}}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_selector(".kr-live .kr-month-line", timeout=15000)
                got["line"] = page.evaluate("""(() => { const b = document.querySelector('.kr-live .kr-month-line'),
                    r = b.getBoundingClientRect();
                    return { text: [...b.children].map((k) => k.textContent.replace(/\\s+/g, ' ').trim()).join(' '),
                    shown: r.height > 0, n: document.querySelectorAll('.kr-live .kr-ask').length }; })()""")
                page.click(".kr-live .kr-month-line")
                page.wait_for_selector("#kr-month .krm-stat", timeout=15000)
                page.wait_for_timeout(800)
                got["card"] = page.evaluate("""(() => { const c = document.getElementById('kr-month'),
                    r = c.getBoundingClientRect(), words = (e) => [...e.children].map((k) => k.textContent.trim()).join(' ');
                    return { head: words(c.querySelector('.kr-h')), bar: document.querySelector('.topbar').getBoundingClientRect().bottom,
                             stats: [...c.querySelectorAll('.krm-stat')].map(words),
                             top: r.top, right: r.right, w: innerWidth,
                             fine: (c.querySelector('.kr-fine') || {}).textContent || '' }; })()""")
                got["pic"] = page.evaluate("""(() => { const c = krMonthCanvas(KR.me.month, 'ethan');
                    return [c.width, c.height, c.toDataURL('image/png').length]; })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    line = got["line"]
    assert line["shown"] and line["n"] == 1, ("one line in the card", line)
    assert line["text"] == "🗓️ Your October · 18 live games watched See it ›", line
    card = got["card"]
    assert card["head"] == "Your October the whole month", card
    assert card["stats"] == ["18 live games watched", "19 days with karma", "+1,240 karma", "14–6 in pick'em",
                             "12 of 20 calls right"], card
    assert card["fine"] == "Watched most: NFL, 11 games.", card
    assert card["right"] <= card["w"] and card["bar"] <= card["top"] < 844, ("opened at the card, under the top bar", card)
    w, h, size = got["pic"]
    assert (w, h) == (1200, 630) and size > 20000, got["pic"]


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
