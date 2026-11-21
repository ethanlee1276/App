"""Trivia in the stoppages: one question off the season logs at a break in a
live game, answered on the game page (docs/IDEAS.md, the live game list's
eleventh; built 2026-10-28, runbook FV).

What these hold:

  * a break is read off the game's own file: a timeout or the two-minute
    warning as the last play, the clock run out, the scoreboard holding
    (halftime, the end of a period, a delay), and baseball's middle and end
    of an inning; play on, or a game not live, is no break; and the page's
    copy of the rule (js/detail.js trStop) reads every case the same;
  * the questions come from the two teams' season logs under every
    spelling of a team: who leads one team in a stat, or who has the most
    of four across both, the leader in a shuffled place; a tied top two is
    never asked, and a team too early in its season is asked about last
    season, in words that say so;
  * a break asks the room's next question once, every reader sees the same
    one, and no question comes back in the same game; an answer is once
    per account and only while its break lasts, and the right name and the
    room's split show after answering, or once the break is over;
  * the endpoint reads the deep file like Call it, answers need an account,
    and the answers go with the account and are named in the policy;
  * and in a browser, a timeout on an NFL game page shows the four names,
    and a tap shows the answer and how the room did.

Run directly: `python3 tests/test_trivia_in_the_stoppages.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import trivia as TV  # noqa: E402

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")


def _doc(league="nfl", state="live", period="Q2", clock="4:12", hold="", last=None, eid="401"):
    plays = [{"id": "p1", "event": "Pass Reception"}]
    if last:
        plays.append({"id": "p2", "event": last})
    return {"league": league, "event_id": eid, "home": "CIN", "away": "LAR",
            "live": {"state": state, "period": period, "clock": clock, "hold": hold}, "plays": plays}


CASES = [
    ("timeout", _doc(last="Timeout"), "to:p2"),
    ("official timeout", _doc(last="Official Timeout"), "to:p2"),
    ("two-minute warning", _doc(last="Two-minute warning"), "to:p2"),
    ("clock run out", _doc(clock="0:00"), "brk:Q2"),
    ("halftime", _doc(clock="", hold="Halftime"), "hold:Q2:halftime"),
    ("end of the 3rd", _doc(period="Q3", clock="", hold="End of 3rd"), "hold:Q3:end of 3rd"),
    ("play on", _doc(last="Rush"), None),
    ("not live", _doc(state="final", clock="0:00"), None),
    ("mlb middle", _doc(league="mlb", period="Middle 5th", clock=""), "inn:Middle 5th"),
    ("mlb end", _doc(league="mlb", period="End 7th", clock=""), "inn:End 7th"),
    ("mlb top", _doc(league="mlb", period="Top 6th", clock=""), None),
]


def test_a_break_is_read_off_the_game_s_own_file():
    for name, doc, want in CASES:
        assert TV.stoppage(doc) == want, (name, TV.stoppage(doc))


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\nif (")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_page_reads_every_break_the_same_way():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    prog = f"""
      const TR_RUN_OUT = new Set(["0:00", "0.0", "0:00.0", "00:00"]);
      {_fn(DETAIL, "trStop")}
      const cases = {json.dumps([[n, d] for n, d, _w in CASES])};
      console.log(JSON.stringify(cases.map(([n, d]) => trStop(d, d.league) || null)));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [w for _n, _d, w in CASES]


# --- the questions --------------------------------------------------------------------------
def _hist(season=2026, cin_games=6, lar_games=6, tie=False):
    h = sqlite3.connect(":memory:")
    h.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, player TEXT, "
              "team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    rows = []

    def add(team, games, players):
        for g in range(games):
            for name, per in players:
                rows.append(("nfl", season, f"{g + 1:03d}", f"{team}{g}", name, team, "X", "WR", 1, "rec_yds", per))
    add("CIN", cin_games, [("Ja'Marr Chase", 100), ("Tee Higgins", 99 if tie else 70), ("Mike Gesicki", 40),
                           ("Andrei Iosivas", 30), ("Chase Brown", 20)])
    # The logs spell the Rams "LA"; the game file says "LAR".
    add("LA", lar_games, [("Puka Nacua", 110), ("Davante Adams", 80), ("Tyler Higbee", 30), ("Kyren Williams", 10)])
    # Last season's, for the fallback.
    for g in range(10):
        rows.append(("nfl", season - 1, f"{g + 1:03d}", f"old{g}", "Old Leader", "CIN", "X", "WR", 1, "rec_yds", 90))
        for name, per in (("Old Two", 50), ("Old Three", 40), ("Old Four", 30)):
            rows.append(("nfl", season - 1, f"{g + 1:03d}", f"old{g}", name, "CIN", "X", "WR", 1, "rec_yds", per))
    h.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return h


def _bank(**kw):
    TV._bank.clear()
    return TV.bank(_hist(**kw), "nfl", "CIN", "LAR", now=1000.0)


def test_the_questions_come_from_both_teams_season_logs():
    qs = {q["text"]: q for q in _bank()}
    cin = qs["Who leads CIN in receiving yards this season?"]
    assert len(cin["options"]) == 4 and cin["options"][cin["answer"]] == "Ja'Marr Chase", cin
    assert cin["why"] == "Ja'Marr Chase: 600 receiving yards" and "Chase Brown" not in cin["options"]
    lar = qs["Who leads LAR in receiving yards this season?"]
    assert lar["options"][lar["answer"]] == "Puka Nacua", "the Rams found under the logs' spelling"
    both = qs["Who has the most receiving yards this season of these four?"]
    assert sorted(both["options"]) == ["Davante Adams", "Ja'Marr Chase", "Puka Nacua", "Tee Higgins"]
    assert both["options"][both["answer"]] == "Puka Nacua"


def test_a_tie_at_the_top_is_never_asked():
    texts = [q["text"] for q in _bank(tie=True)]
    assert "Who leads CIN in receiving yards this season?" in texts, "100 v 99 is no tie"
    TV._bank.clear()
    h = _hist()
    h.execute("UPDATE player_game_logs SET value=100 WHERE player='Tee Higgins' AND season=2026")
    texts = [q["text"] for q in TV.bank(h, "nfl", "CIN", "LAR", now=1000.0)]
    assert "Who leads CIN in receiving yards this season?" not in texts


def test_a_young_season_asks_about_last_season_and_says_so():
    qs = {q["text"]: q for q in _bank(cin_games=2, lar_games=2)}
    q = qs["Who led CIN in receiving yards last season?"]
    assert q["options"][q["answer"]] == "Old Leader" and q["why"] == "Old Leader: 900 receiving yards"
    assert not any("this season" in t for t in qs), "both teams young: nothing asked about this season"


# --- asking and answering -------------------------------------------------------------------
def _acct():
    c = sqlite3.connect(":memory:")
    TV.ensure_tables(c)
    return c


def test_one_question_a_break_once_a_game_answered_once():
    TV._bank.clear()
    c, h = _acct(), _hist()
    to1 = _doc(last="Timeout")
    qkey, q = TV.ask(c, h, to1, now=1000.0)
    assert qkey == "to:p2" and q["text"]
    again = TV.state(c, h, None, to1, now=1001.0)
    assert again["open"]["text"] == q["text"] and "answer" not in again["open"], "the same question, unanswered"
    assert again["signed_in"] is False
    # Answers: once, only for this break, a real pick.
    code, out = TV.answer(c, h, 1, to1, "to:p2", q["answer"], now=1002.0)
    assert code == 200 and out["mine"] == q["answer"] and out["answer"] == q["answer"]
    assert out["split"][q["answer"]] == 1 and sum(out["split"]) == 1
    assert TV.answer(c, h, 1, to1, "to:p2", 0, now=1003.0)[0] == 409, "once"
    assert TV.answer(c, h, 2, to1, "brk:Q1", 0, now=1003.0)[0] == 409, "only the break's own question"
    assert TV.answer(c, h, 2, to1, "to:p2", 7, now=1003.0)[0] == 400
    code, out = TV.answer(c, h, 2, to1, "to:p2", (q["answer"] + 1) % 4, now=1004.0)
    assert code == 200 and sum(out["split"]) == 2
    # Play resumes: no open question, the last one with its answer for everyone.
    on = _doc(last="Rush")
    st = TV.state(c, h, 3, on, now=1100.0)
    assert st["open"] is None and st["last"]["text"] == q["text"] and st["last"]["answer"] == q["answer"]
    assert TV.answer(c, h, 3, on, "to:p2", 0, now=1101.0)[0] == 409, "over when the break is"
    # The next break asks a new question.
    k2, q2 = TV.ask(c, h, _doc(clock="0:00"), now=1200.0)
    assert k2 == "brk:Q2" and q2["text"] != q["text"]


def test_a_game_runs_out_of_questions_rather_than_repeat_one():
    TV._bank.clear()
    c, h = _acct(), _hist()
    asked = set()
    for i in range(12):
        doc = _doc(last="Timeout")
        doc["plays"][-1]["id"] = f"t{i}"
        _k, q = TV.ask(c, h, doc, now=1000.0 + i)
        if q is None:
            break
        assert q["text"] not in asked
        asked.add(q["text"])
    assert q is None and len(asked) == len(TV.bank(h, "nfl", "CIN", "LAR", now=1000.0))


def test_answers_and_questions_are_swept_after_three_days():
    TV._bank.clear()
    c, h = _acct(), _hist()
    TV.ask(c, h, _doc(last="Timeout"), now=1000.0)
    TV.answer(c, h, 1, _doc(last="Timeout"), "to:p2", 0, now=1000.0)
    TV.prune(c, now=1000.0 + TV.KEEP_S + 1)
    assert c.execute("SELECT COUNT(*) FROM trivia_asked").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM trivia_answers").fetchone()[0] == 0


# --- the endpoint, the policy, the account --------------------------------------------------
def test_the_endpoint_reads_the_game_like_call_it_and_answers_need_an_account():
    import server
    from engine import db as DB
    TV._bank.clear()
    keep, real = server.WEB, DB.connect
    with tempfile.TemporaryDirectory() as d:
        server.WEB = Path(d)
        (Path(d) / "data" / "pbp").mkdir(parents=True)
        doc = _doc(last="Timeout")
        doc.pop("league")
        (Path(d) / "data" / "pbp" / "nfl_401.json").write_text(json.dumps(doc))
        DB.connect = lambda *a, **k: _hist()
        out = {}
        h = object.__new__(server.Handler)
        h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
        h._account = lambda conn: None
        try:
            for bad in ("nfl2/401", "nfl/../x", "nfl/40a", "nfl/", "nfl/123456789012345", "soccer/1", "nfl/402"):
                h._trivia(bad)
                assert out["code"] == 404, bad
            h._trivia("nfl/401")
            assert out["code"] == 200 and out["body"]["open"]["qkey"] == "to:p2", out
            assert "answer" not in out["body"]["open"] and out["body"]["signed_in"] is False
            h._trivia("nfl/401", {"qkey": "to:p2", "pick": 0})
            assert out["code"] == 401, "an answer needs an account"
        finally:
            server.WEB, DB.connect = keep, real
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path.startswith("/api/trivia/"):\n            return self._trivia(' in src
    assert 'or parsed.path.startswith("/api/trivia/")' in src, "a POST body is read for it"


def test_the_answers_go_with_the_account_and_the_policy_names_them():
    acc = (ROOT / "engine" / "accounts.py").read_text(encoding="utf-8")
    gone = acc[acc.index("def delete_user("):acc.index("def export_user(")]
    assert '"trivia_answers"' in gone
    assert 'out["trivia_answers"] = rows' in acc[acc.index("def export_user("):]
    privacy = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    assert "<code>trivia_answers</code>" in privacy and "<code>trivia_asked</code>" in privacy


def test_the_card_rides_with_call_it_and_asks_only_in_a_break():
    ci = _fn(DETAIL, "pbpCallItHTML")
    assert "return `${pbpTriviaHTML(d, league)}<div class=\"card ci-card\"" in ci
    tr = _fn(DETAIL, "pbpTriviaHTML")
    assert "if (stop !== _tr.stop || (stop && Date.now() - _tr.at > 8000)) { _tr.stop = stop; trFetch(key); }" in tr
    body = _fn(DETAIL, "trBodyHTML")
    for part in ("escapeHtml(name)", "escapeHtml(q.text)", "escapeHtml(q.why)"):
        assert part in body, part
    assert "Make a free account to answer" in body


# --- in a browser (opt-in) ------------------------------------------------------------------
def test_in_a_browser_a_timeout_asks_and_a_tap_answers():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    live = {"state": "live", "period": "Q2", "clock": "4:12", "away_score": 7, "home_score": 3}
    plays = [{"kind": "football", "id": "p1", "period": 2, "clock": "4:20", "team": "LAR", "event": "Rush",
              "yards": 4, "away_score": 7, "home_score": 3},
             {"kind": "football", "id": "p2", "period": 2, "clock": "4:12", "team": "CIN", "event": "Timeout",
              "yards": 0, "away_score": 7, "home_score": 3}]
    pbp = {"league": "nfl", "event_id": "401", "home": "CIN", "away": "LAR", "generated_at": "2026-10-25T17:00:00Z",
           "live": live, "plays": plays, "drives": []}
    q = {"qkey": "to:p2", "text": "Who leads CIN in receiving yards this season?",
         "options": ["Tee Higgins", "Ja'Marr Chase", "Mike Gesicki", "Andrei Iosivas"], "mine": None, "open": True}
    answered = dict(q, mine=0, answer=1, why="Ja'Marr Chase: 600 receiving yards", split=[3, 9, 0, 0])
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    posted = []

    def trivia(route):
        if route.request.method == "POST":
            posted.append(json.loads(route.request.post_data or "{}"))
            body = answered
        else:
            body = {"signed_in": True, "open": q, "last": None}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            b = pw.chromium.launch(**kw)
            try:
                p = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block").new_page()
                errs = []
                p.on("pageerror", lambda e: errs.append(str(e)))
                p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                p.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                mk = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
                p.route("**/data/pbp/nfl_401.json*", mk(pbp))
                p.route("**/api/account/me*", mk(me))
                p.route("**/api/trivia/**", trivia)
                p.route("**/api/chat/room*", mk({"room": "nfl_401", "messages": [], "votes": {"home": 0, "away": 0}}))
                p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401", wait_until="load")
                p.wait_for_selector(".tr-card:not([hidden]) [data-tr-pick]", timeout=20000)
                card = " ".join(p.inner_text(".tr-card").split())
                assert "Who leads CIN in receiving yards this season?" in card and "Ja'Marr Chase" in card, card
                p.click(".tr-card [data-tr-pick='0']")
                p.wait_for_selector(".tr-card .tr-opt.is-right", timeout=10000)
                card = " ".join(p.inner_text(".tr-card").split())
                assert "Not this time — Ja'Marr Chase: 600 receiving yards · 12 answered" in card, card
                assert "75%" in card and "25%" in card, card
                assert posted == [{"qkey": "to:p2", "pick": 0}], posted
                assert p.query_selector(".tr-card .tr-opt.is-wrong .tr-name").inner_text() == "Tee Higgins"
                assert not errs, errs
            finally:
                b.close()
    finally:
        srv.shutdown()


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
