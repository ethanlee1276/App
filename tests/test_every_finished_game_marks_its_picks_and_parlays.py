"""Every finished game on "How our reports did" marks each pick and parlay: a check or an X (TICKETMARKS1).

Ethan, 2026-11-17, a screenshot of Report Picks → How our reports did, the list
of every finished game: "I wanna be able too see each parlay and pick on this
page along side and x or checkmark if the whole parlay hit and if the
individual picks hit".

Under each finished game's checks, a strip of marks, one a pick and one a
ticket, the count that hit beside each kind; open, every pick by name and every
ticket with each of its legs, each with its mark and the number it finished
with (js/reportpicks.js rpBetsHTML). The picks are the report's own book and the
tickets the game's parlays and pairs, read off the record for each archived
game (engine/reportoutcome.for_games, /api/report_tickets), under the board's
label the journal files them by (the NFL's week) or the game's own day. What has
settled is free, as every settled row is; a pick or ticket still waiting on the
box score is a member's, and the rest are told how many. The list draws twenty
games at a time and asks for their picks a page at a time.

Run directly: `python3 tests/test_every_finished_game_marks_its_picks_and_parlays.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlayledger as PL  # noqa: E402
from engine import reportarchive as RA  # noqa: E402
from engine import reportoutcome as O  # noqa: E402

RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")

BETS = [
    # (sport, date, player, market, side, line, odds, status, actual, category, team)
    # NE at DET, filed under the NFL's week: the report's picks, and the same player in another book.
    ("nfl", "2026-W11", "Jahmyr Gibbs", "rush_yds", "OVER", 74.5, -115, "won", 142, "report", "DET"),
    ("nfl", "2026-W11", "Jahmyr Gibbs", "rush_yds", "OVER", 74.5, -115, "won", 142, "likely", "DET"),
    ("nfl", "2026-W11", "Drake Maye", "pass_yds", "OVER", 220.5, -110, "lost", 180, "report", "NE"),
    ("nfl", "2026-W11", "Sam LaPorta", "receptions", "OVER", 3.5, -125, "open", None, "report", "DET"),
    ("nfl", "2026-W11", "Hunter Henry", "receptions", "UNDER", 4.5, -120, "void", None, "report", "NE"),
    ("nfl", "2026-W11", "DET", "spread", "OVER", 3.5, -110, "won", 25, "report", None),
    # Not the report's: another book.
    ("nfl", "2026-W11", "Jared Goff", "pass_yds", "OVER", 230.5, -110, "won", 260, "main", "DET"),
    # An NBA game, filed under its own day.
    ("nba", "2026-11-16", "Jalen Brunson", "points", "OVER", 26.5, -110, "lost", 22, "report", "NYK"),
]


def _journal():
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, odds INTEGER, status TEXT, actual REAL, category TEXT, team TEXT)")
    conn.executemany("INSERT INTO bets (sport, date, player, market, side, line, odds, status, actual, category, team) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)", BETS)
    conn.executescript(PL.SCHEMA)

    def ticket(sport, date, grade, source, status, legs):
        cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status) "
                           "VALUES (?, ?, ?, 'same_game', ?, ?, ?, ?)",
                           (sport, date, f"{grade}-{source}-{status}-{len(legs)}", len(legs), grade, source, status))
        for i, (player, market, side, line, st, actual) in enumerate(legs, start=1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status, actual) "
                         "VALUES (?,?,?,?,?,?,?,?,?)", (cur.lastrowid, i, player, "", market, side, line, st, actual))
    ticket("nfl", "2026-W11", "NE@DET", "game_three", "won", [("Jahmyr Gibbs", "rush_yds", "OVER", 74.5, "won", 142),
                                                             ("Jared Goff", "pass_yds", "OVER", 230.5, "won", 260),
                                                             ("Sam LaPorta", "receptions", "OVER", 2.5, "won", 5)])
    ticket("nfl", "2026-W11", "NE@DET", "game_three", "lost", [("Jahmyr Gibbs", "rush_yds", "OVER", 74.5, "won", 142),
                                                              ("Drake Maye", "pass_yds", "OVER", 220.5, "lost", 180),
                                                              ("Jared Goff", "pass_yds", "OVER", 230.5, "won", 260)])
    ticket("nfl", "2026-W11", "NE@DET", "game_td", "open", [("Jahmyr Gibbs", "anytime_td", "OVER", 0.5, "open", None),
                                                           ("Amon-Ra St. Brown", "anytime_td", "OVER", 0.5, "won", 1)])
    ticket("nba", "2026-11-16", "BOS@NYK", "game_three", "lost", [("Jalen Brunson", "points", "OVER", 26.5, "lost", 22),
                                                                ("Jayson Tatum", "points", "OVER", 24.5, "lost", 20)])
    conn.commit()
    conn.close()
    return p


def _archive():
    where = Path(tempfile.mkdtemp())
    for sport, label, date, away, home in (("nfl", "2026-W11", "2026-11-15", "NE", "DET"),
                                            ("nfl", "2026-W11", "2026-11-15", "KC", "BUF"),
                                            ("nba", "2026-11-16", "2026-11-16", "BOS", "NYK")):
        doc = {"sport": sport, "date": date, "label": label, "away": away, "home": home, "game": f"{away}@{home}",
               "final": {"away": 10, "home": 35}, "report": {"away": away, "home": home, "sections": []}, "results": {}}
        RA.write(RA.path_for(where, sport, date, away, home), doc)
    return where


def test_each_finished_game_lists_its_report_picks_and_tickets_off_the_record():
    path, where = _journal(), _archive()
    got = O.for_games("nfl", [("2026-11-15", "NE", "DET"), ("2026-11-15", "KC", "BUF"), ("2026-11-15", "SF", "DAL")],
                      member=True, path=path, where=where)
    assert set(got) == {"2026-11-15|NE|DET", "2026-11-15|KC|BUF"}, "a game not archived is left out"
    assert got["2026-11-15|KC|BUF"] == {}, "an archived game the record holds nothing for says so"
    game = got["2026-11-15|NE|DET"]
    picks = {(p["player"], p["status"]) for p in game["picks"]}
    assert picks == {("Jahmyr Gibbs", "won"), ("Drake Maye", "lost"), ("Sam LaPorta", "pending"),
                     ("Hunter Henry", "void"), ("DET", "won")}, "the report's own book, filed under the week"
    assert not any(p.get("book") for p in game["picks"]), "the book is the page's business, not the reader's"
    gibbs = next(p for p in game["picks"] if p["player"] == "Jahmyr Gibbs")
    assert gibbs["actual"] == 142 and gibbs["line"] == 74.5 and gibbs["side"] == "OVER"
    assert [t["status"] for t in game["threes"]] == ["won", "lost"]
    assert [l["status"] for l in game["threes"][1]["legs"]] == ["won", "lost", "won"], "each leg its own mark"
    assert [t["status"] for t in game["scorers"]] == ["pending"]
    nba = O.for_games("nba", [("2026-11-16", "BOS", "NYK")], member=True, path=path, where=where)["2026-11-16|BOS|NYK"]
    assert [p["player"] for p in nba["picks"]] == ["Jalen Brunson"] and len(nba["threes"]) == 1, "filed under its day"


def test_what_has_settled_is_everyone_s_and_what_waits_is_a_member_s():
    path, where = _journal(), _archive()
    free = O.for_games("nfl", [("2026-11-15", "NE", "DET")], member=False, path=path, where=where)["2026-11-15|NE|DET"]
    assert {p["status"] for p in free["picks"]} == {"won", "lost", "void"}, "LaPorta waits on the box score"
    assert "scorers" not in free, "the open pair is a member's"
    assert free["held"] == 2, "and the rest are told how many"
    assert len(free["threes"]) == 2 and all(t["status"] in O.SETTLED for t in free["threes"])


def test_one_ask_names_a_screenful_and_a_name_that_is_not_one_is_passed_over():
    path, where = _journal(), _archive()
    keys = [("2026-11-15", "NE", "DET")] * (O.MAX_GAMES + 5) + [("../etc", "A", "B"), ("x",), None]
    got = O.for_games("nfl", keys, path=path, where=where)
    assert list(got) == ["2026-11-15|NE|DET"]
    assert O.MAX_GAMES >= int(re.search(r"const RP_FACT_PAGE = (\d+);", RP).group(1)), "a page of rows is one ask"
    assert O.for_games("nfl", [("2026-11-15", "NE", "DET")], path=Path(tempfile.mkdtemp()) / "none.db",
                       where=where) == {}, "no journal, nothing to say"


def test_the_answer_brings_the_reader_s_word_for_each_market():
    path, where = _journal(), _archive()
    games = O.for_games("nfl", [("2026-11-15", "NE", "DET")], path=path, where=where)
    words = O.market_words(games)
    assert words["rush_yds"] == "Rushing Yards" and words["anytime_td"] == "Anytime TD" and "spread" in words
    assert set(words) == {"rush_yds", "pass_yds", "receptions", "spread", "anytime_td"}, words
    assert '"words": reportoutcome.market_words(games)' in SERVER
    assert "Object.assign(RP_WORDS, body.words)" in RP and "(RP_WORDS[m] || marketWord(m))" in RP


def test_the_endpoint_is_routed_rate_limited_and_gated_on_what_still_waits():
    assert 'if parsed.path in ("/api/report_tickets", "/api/report_tickets/"):\n            return self._report_tickets(parse_qs(parsed.query))' in SERVER
    body = SERVER[SERVER.index("def _report_tickets(self, q):"):SERVER.index("def _report_archive(self, q):")]
    assert 'self._rate_limited(RATE_GAME_PER_MIN, "report_tickets")' in body
    assert "member = bool(self._entitled(conn, self._account(conn)))" in body
    assert "reportoutcome.for_games(league, keys[:reportoutcome.MAX_GAMES], member=member," in body
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        def get(q):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/report_tickets?{q}", timeout=20) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        assert get("league=n1&games=2026-11-15|NE|DET")[0] == 400
        assert get("league=nfl&games=nothing")[0] == 400
        code, out = get("league=nfl&games=2099-01-01|AAA|BBB")
        assert code == 200 and out["games"] == {} and out["league"] == "nfl" and out["words"] == {}, out
    finally:
        srv.shutdown()


def _fn(name):
    at = RP.index(f"function {name}(")
    return RP[at:RP.index("\n}\n", at) + 3]


def _render(game, sport="nfl", open_=True, words=None):
    helpers = "".join(_fn(n) for n in ("rpMk", "rpHit", "rpBetWords", "rpPickLI", "rpTicketWords", "rpTicketsHTML",
                                       "rpBetsHTML"))
    score = RP[RP.index("const RP_SCORE = "):RP.index("};", RP.index("const RP_SCORE = ")) + 3]
    score += "\nconst RP_WORDS = %s;\n" % json.dumps(words or {})
    js = """
const escapeHtml = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
const icon = (n) => `[${n}]`;
const MINUS = "\\u2212";
const RES_GAME_MARKETS = new Set(["moneyline", "total", "spread", "team_total"]);
const teamName = (t) => ({ DET: "Lions", NE: "Patriots" })[t] || t;
const marketWord = (m) => ({ rush_yds: "Rushing Yards", pass_yds: "Passing Yards", receptions: "Receptions" })[m] || m;
const plural = (n, one, many) => `${n} ${Number(n) === 1 ? one : (many || one + "s")}`;
%s
%s
process.stdout.write(rpBetsHTML(%s, %s, %s));
""" % (score, helpers, json.dumps(game), json.dumps(sport), "true" if open_ else "false")
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_page_marks_every_pick_every_ticket_and_every_leg():
    path, where = _journal(), _archive()
    game = O.for_games("nfl", [("2026-11-15", "NE", "DET")], member=True, path=path, where=where)["2026-11-15|NE|DET"]
    html = _render(game)
    strip = html[html.index('<summary class="rpk-bets-sum">'):html.index("</summary>")]
    assert re.findall(r'class="rpk-bets-k">([^<]+)<', strip) == ["Picks", "Parlays", "Touchdown pairs"]
    assert '<b class="won">2 of 3</b>' in strip, "the picks that hit of the ones won or lost: Gibbs and the spread"
    assert '<b class="">1 of 2</b>' in strip, "the parlays, one hit"
    marks = re.findall(r'class="rpk-mk (\w+)"', strip)
    assert marks == ["won", "lost", "wait", "push", "won", "won", "lost", "wait"], marks
    body = html[html.index('<div class="rpk-bets-body">'):]
    assert "Jahmyr Gibbs over 74.5 rushing yards" in body and "had 142" in body
    assert "Lions −3.5" in body, "a spread said as the club and its number"
    assert "didn’t play" in body and "waiting on the box score" in body
    assert "<b>Parlay 1</b> <span>Hit</span>" in body and "<b>Parlay 2</b> <span>Missed by one leg</span>" in body
    assert "<b>Touchdown pair 1</b>" in body and "Amon-Ra St. Brown to score a touchdown" in body
    tix = body[body.index("<b>Parlay 2</b>"):body.index("</ul></li>", body.index("<b>Parlay 2</b>"))]
    assert re.findall(r'class="rpk-mk (\w+)"', tix) == ["won", "lost", "won"], "the ticket's legs each marked"
    assert html.startswith('<details class="rpk-bets" open>'), "the newest game opens"
    said = _render(game, words=O.market_words({"g": game}))
    assert "Jahmyr Gibbs over 74.5 rushing yards" in said, "the engine's word for the market, when the answer brings it"
    assert not _render(game, open_=False).startswith('<details class="rpk-bets" open>')


def test_a_reader_without_the_subscription_is_told_what_waits():
    path, where = _journal(), _archive()
    free = O.for_games("nfl", [("2026-11-15", "NE", "DET")], member=False, path=path, where=where)["2026-11-15|NE|DET"]
    html = _render(free)
    assert "Touchdown pairs" not in html
    assert "2 more picks and tickets waiting on the box score: members see them now." in html
    assert _render({}) == "" and "1 more pick or ticket" in _render({"held": 1})


def test_the_list_draws_a_page_at_a_time_and_asks_for_its_marks():
    row = _fn("rpFactRowHTML")
    assert '<div class="rpk-fact-bets" data-rpk-bets="${escapeAttr(key)}"></div>' in row
    assert row.index("data-rpk-bets") < row.index("data-rpk-arch="), "under the checks, above the report"
    fill = RP[RP.index("async function rpFactsFill("):RP.index("/* EVERY PICK AND PARLAY, A CHECK OR AN X")]
    assert "games.slice(from, from + RP_FACT_PAGE)" in fill and "rpBetsFill(list, sport, rows, !from);" in fill
    assert 'more.textContent = `Show ${Math.min(left, RP_FACT_PAGE)} more ${left === 1 ? "game" : "games"}`;' in fill
    assert "list.addEventListener(\"click\"" in fill, "one listener for every row's report, the later rows too"
    bets = _fn("rpBetsFill")
    assert "fetch(`/api/report_tickets?${q}`, { credentials: \"same-origin\" })" in bets
    assert "need.join(\",\")" in bets and "RP_BETS.has(" in bets, "each game asked for once"
    for cls in (".rpk-mk.won", ".rpk-mk.lost", ".rpk-bets-sum", ".rpk-bet-legs", ".rpk-fact-more[hidden]"):
        assert cls + " {" in CSS, cls


def test_in_a_browser_the_list_marks_each_game_and_draws_the_rest_on_a_tap():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    games = [{"date": f"2026-11-{15 - i // 13:02d}", "away": f"A{i}", "home": f"H{i}", "game": f"A{i}@H{i}",
              "names": {}, "final": {"away": 10, "home": 20}, "reads": [3, 5], "groups": {},
              "call": {"team": f"H{i}", "right": True}} for i in range(25)]
    record = json.dumps({"sport": "nfl", "totals": {"games": 25, "call": [25, 25], "reads": [75, 125]},
                         "recent": {"games": 25}, "recent_days": 30, "games": games, "more": 0})
    asked = []

    def tickets(route):
        q = route.request.url.split("games=", 1)[1]
        keys = urllib.request.unquote(q.split("&")[0]).split(",")
        asked.append(len(keys))
        out = {k: {"picks": [{"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER", "line": 74.5,
                              "status": "won", "actual": 142},
                             {"player": "Drake Maye", "market": "pass_yds", "side": "OVER", "line": 220.5,
                              "status": "lost", "actual": 180}],
                   "threes": [{"status": "lost", "legs": [{"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER",
                                                           "line": 74.5, "status": "won", "actual": 142},
                                                          {"player": "Drake Maye", "market": "pass_yds", "side": "OVER",
                                                           "line": 220.5, "status": "lost", "actual": 180}]}]}
               for k in keys}
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"league": "nfl", "member": True, "games": out}))

    board = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2026-W11", "recommendations": [],
                        "most_likely": [], "games": [], "player_stats": {}, "report_bets": [], "game_parlays": {"games": []}})
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                page.route("**/api/report_record?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                         body=record))
                page.route("**/api/report_tickets?*", tickets)
                for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_function("() => typeof switchView === 'function' && state.data", timeout=20000)
                page.evaluate("window._rpWantFacts = true; switchView('reportpicks')")
                page.wait_for_function("() => document.querySelectorAll('.rpk-fact-bets .rpk-bets').length >= 20",
                                       timeout=20000)
                first = page.evaluate("""() => ({ rows: document.querySelectorAll('.rpk-fact-row').length,
                    marked: document.querySelectorAll('.rpk-fact-bets .rpk-bets').length,
                    open: [...document.querySelectorAll('.rpk-bets')].filter((d) => d.open).length,
                    won: document.querySelectorAll('.rpk-fact-row:first-child .rpk-bets-sum .rpk-mk.won').length,
                    lost: document.querySelectorAll('.rpk-fact-row:first-child .rpk-bets-sum .rpk-mk.lost').length,
                    more: document.querySelector('[data-rpk-more]').textContent,
                    wide: document.documentElement.scrollWidth - innerWidth })""")
                page.click("[data-rpk-more]")
                page.wait_for_function("() => document.querySelectorAll('.rpk-fact-bets .rpk-bets').length === 25",
                                       timeout=20000)
                after = page.evaluate("""() => ({ rows: document.querySelectorAll('.rpk-fact-row').length,
                    hidden: document.querySelector('[data-rpk-more]').hidden })""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert first == {"rows": 20, "marked": 20, "open": 1, "won": 1, "lost": 2, "more": "Show 5 more games", "wide": 0}, first
    assert after == {"rows": 25, "hidden": True}, after
    assert asked == [20, 5], f"one ask a page: {asked}"
    assert not errors, errors


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
