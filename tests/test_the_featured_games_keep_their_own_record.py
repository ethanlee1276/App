"""Ethan's featured games: Lions games, Thursday nights and Monday nights, dialed in with their own record (FEATURED1).

Ethan, 2026-11-19: "the main game reports that I want to focus on is any game
reports that has to do with a Lions game, any game reports on a Thursday night,
or any game reports on a Monday night. Those are the three main ones that we
need to have dialed in completely and have a separate record for."

engine/featured says which NFL games are featured (the Lions in it; a kickoff
on a Thursday or a Monday night, Eastern, from 6 PM), gives a featured game's
report a deeper card (six picks against four) and a line at its top saying how
games like it have done, and keeps the featured games' own record apart: the
report's picks at one unit a pick, the tickets its report carried at kickoff,
and who we said would win, for all of them, each kind and each game. The
league's record serves it (/api/report_record) and the Report Picks and Record
pages draw it, with a chip that lists only the featured games.

Run directly: `python3 tests/test_the_featured_games_keep_their_own_record.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import featured as F  # noqa: E402
from engine import gamereport as GR  # noqa: E402
from engine import parlayledger as PL  # noqa: E402
from engine import reportarchive as RA  # noqa: E402
from engine import reportrecord as RR  # noqa: E402

RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
REPORT_JS = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")


def test_which_games_are_featured():
    # Thursday Night Football, Eastern, from the board's "20:15" beside the date.
    assert F.tags("nfl", "2026-11-19", "20:15", "HOU", "IND") == ["thursday"]
    # Monday Night Football from a feed's UTC stamp: 01:15 Tuesday in UTC is 8:15 Monday night in the East.
    assert F.tags("nfl", "2026-11-24", "2026-11-24T01:15:00Z", "LA", "SF") == ["monday"]
    # The Lions, home or away, any day; on a Monday night, both.
    assert F.tags("nfl", "2026-11-15", "13:00", "DET", "NE") == ["lions"]
    assert F.tags("nfl", "2026-12-07", "20:15", "GB", "DET") == ["lions", "monday"]
    # Thanksgiving's day games are not Thursday nights; its night game is.
    assert F.tags("nfl", "2026-11-26", "12:30", "DET", "CHI") == ["lions"]
    assert F.tags("nfl", "2026-11-26", "16:30", "DAL", "KC") == []
    assert F.tags("nfl", "2026-11-26", "20:20", "BAL", "CIN") == ["thursday"]
    # A Sunday afternoon, and another league's Thursday night, are not.
    assert F.tags("nfl", "2026-11-22", "13:00", "BUF", "KC") == []
    assert F.tags("cfb", "2026-11-19", "19:30", "Navy", "Memphis") == []
    # No kickoff on the row: the day alone says it.
    assert F.tags("nfl", "2026-11-23", "", "PHI", "DAL") == ["monday"]
    assert F.of_game({"date": "2026-11-19", "kickoff": "20:15", "home": "HOU", "away": "IND"}, "nfl") == ["thursday"]
    assert F.words(["monday", "lions"]) == "Lions game · Monday night"


def _rows(n):
    teams = ("IND", "HOU")
    return [{"kind": "prop", "player": f"Player {i}", "team": teams[i % 2], "opponent": teams[1 - i % 2],
             "market": "receptions", "side": "OVER", "line": 3.5, "model_prob": 0.7 - i / 100, "tier": "strong"}
            for i in range(n)]


def test_a_featured_game_s_card_goes_to_six():
    def card(kinds):
        c = SimpleNamespace(featured=kinds, teams=("IND", "HOU"), result={"likely_board": {"rows": _rows(9)}})
        return [r["player"] for r in GR._card_rows(c)]
    assert len(card(["thursday"])) == GR.CARD_MAX_FEATURED == 6
    assert len(card([])) == GR.CARD_MAX == 4
    assert card(["thursday"])[:4] == card([]), "the same picks first, best first: two more behind them"


# --- the record --------------------------------------------------------------------------------
#: (date, label, away, home, kickoff, call right)
GAMES = [("2026-11-12", "2026-W11", "WAS", "NYG", "20:15", False),     # a Thursday night
         ("2026-11-15", "2026-W11", "NE", "DET", "13:00", True),       # the Lions
         ("2026-11-16", "2026-W11", "LAC", "BAL", "20:15", False),     # a Monday night
         ("2026-11-15", "2026-W11", "KC", "BUF", "16:25", True),       # none of them
         ("2026-11-26", "2026-W13", "KC", "DAL", "16:30", True),       # Thanksgiving afternoon: none of them
         ("2026-11-26", "2026-W13", "CHI", "DET", "12:30", True)]      # the Lions on Thanksgiving

BETS = [
    # (date, player, market, side, line, odds, status, category, team)
    ("2026-W11", "Jayden Daniels", "pass_yds", "OVER", 220.5, -110, "won", "report", "WAS"),
    ("2026-W11", "Malik Nabers", "rec_yds", "OVER", 70.5, -120, "lost", "report", "NYG"),
    ("2026-W11", "Jahmyr Gibbs", "rush_yds", "OVER", 74.5, 120, "won", "report", "DET"),
    ("2026-W11", "Sam LaPorta", "receptions", "OVER", 3.5, -125, "open", "report", "DET"),
    ("2026-W11", "Derrick Henry", "rush_yds", "OVER", 64.5, -240, "lost", "report", "BAL"),
    ("2026-W11", "BAL", "moneyline", "OVER", 0.5, -225, "lost", "report", None),
    ("2026-W11", "Charlie Kolar", "rec_yds", "OVER", 9.5, -190, "won", "report", "LAC"),
    ("2026-W11", "Zay Flowers", "receptions", "OVER", 4.5, -110, "push", "report", "BAL"),
    # Another book's row for a featured game, and a game that is not featured: neither is the record's.
    ("2026-W11", "Derrick Henry", "rush_yds", "OVER", 64.5, -240, "won", "likely", "BAL"),
    ("2026-W11", "Josh Allen", "pass_yds", "OVER", 240.5, -110, "won", "report", "BUF"),
    ("2026-W13", "Amon-Ra St. Brown", "receptions", "OVER", 6.5, -150, "won", "report", "DET"),
    ("2026-W13", "CeeDee Lamb", "receptions", "OVER", 6.5, -150, "won", "report", "DAL"),
]

#: (date, grade, source, status, pnl_units, at_start)
TICKETS = [("2026-W11", "LAC@BAL", "game_three", "lost", -1.0, 1),
           ("2026-W11", "LAC@BAL", "game_td", "lost", -1.0, 1),
           ("2026-W11", "LAC@BAL", "game_three", "won", 5.0, 0),          # replaced before kickoff
           ("2026-W11", "NE@DET", "game_three", "won", 4.5, 1),
           ("2026-W11", "KC@BUF", "game_three", "won", 6.0, 1),           # not featured
           ("2026-W13", "CHI@DET", "game_two", "open", None, 1)]


def _journal():
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, odds INTEGER, status TEXT, actual REAL, category TEXT, team TEXT)")
    conn.executemany("INSERT INTO bets (sport, date, player, market, side, line, odds, status, category, team) "
                     "VALUES ('nfl',?,?,?,?,?,?,?,?,?)", BETS)
    conn.executescript(PL.SCHEMA)
    PL.ensure_schema(conn)
    for i, (date, grade, src, status, pnl, start) in enumerate(TICKETS):
        conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status, pnl_units, "
                     "at_start) VALUES ('nfl', ?, ?, 'same_game', 3, ?, ?, ?, ?, ?)",
                     (date, f"k{i}", grade, src, status, pnl, start))
    conn.commit()
    conn.close()
    return p


def _archive():
    where = Path(tempfile.mkdtemp())
    for date, label, away, home, kickoff, right in GAMES:
        winner = home if right else away
        doc = {"sport": "nfl", "date": date, "label": label, "away": away, "home": home, "game": f"{away}@{home}",
               "kickoff": kickoff, "final": {"away": 17, "home": 24}, "results": {},
               "report": {"away": away, "home": home, "sections": [],
                          "graded": {"status": "graded", "right": 3, "graded": 5,
                                     "call": {"team": winner if right else home, "right": right}}}}
        RA.write(RA.path_for(where, "nfl", date, away, home), doc)
    RR.refresh(where, "nfl")
    return where


def test_the_featured_games_keep_a_record_of_their_own():
    path, where = _journal(), _archive()
    rec = F.record(where, "nfl", path)
    games = {g["game"]: g for g in rec["games"]}
    assert set(games) == {"WAS@NYG", "NE@DET", "LAC@BAL", "CHI@DET"}, "the Sunday and Thanksgiving-afternoon games are not"
    assert games["CHI@DET"]["kinds"] == ["lions"] and games["LAC@BAL"]["kinds"] == ["monday"]
    # The report's own book only, at one unit a pick at its price: Kolar's −190 win is +0.53.
    mon = games["LAC@BAL"]
    assert mon["picks"] == [1, 2, 1] and mon["units"] == -1.47, mon
    assert games["NE@DET"]["picks"] == [1, 0, 0] and games["NE@DET"]["units"] == 1.2 and games["NE@DET"]["open"] == 1
    # The tickets its report carried at kickoff: the version replaced before it is not the record's.
    assert mon["tickets"] == {"threes": [0, 1, -1.0], "scorers": [0, 1, -1.0]}, mon["tickets"]
    assert games["NE@DET"]["tickets"] == {"threes": [1, 0, 4.5]}
    assert games["CHI@DET"]["tickets"] == {} and games["CHI@DET"]["tickets_open"] == 1
    every = rec["all"]
    assert every["games"] == 4 and every["picks"] == [4, 3, 1] and every["open"] == 1
    assert every["units"] == round(-0.09 + 1.2 - 1.47 + 0.67, 2), every["units"]
    assert every["tickets"]["threes"] == [1, 1, 3.5] and every["call"] == [2, 4]
    assert set(rec["kinds"]) == {"lions", "thursday", "monday"}
    assert rec["kinds"]["lions"]["games"] == 2 and rec["kinds"]["thursday"]["picks"] == [1, 1, 0]
    assert F.line(rec["kinds"]["monday"], "monday") == (
        "Monday nights so far, 1 finished game: the reports' picks 1-2-1 (−1.5 units at one unit a pick); "
        "three-leg parlays 0 of 1; touchdown pairs 0 of 1; who wins 0 of 1.")
    assert F.line({}, "monday") == "", "nothing finished, nothing said"


def test_the_record_is_read_again_only_when_its_sources_move():
    path, where = _journal(), _archive()
    first = F.record(where, "nfl", path)
    assert F.record(where, "nfl", path) is first, "the same archive and journal: the same answer, not read again"
    conn = sqlite3.connect(path)
    conn.execute("UPDATE bets SET status='won' WHERE player='Sam LaPorta'")
    conn.commit()
    conn.close()
    again = F.record(where, "nfl", path)
    assert again is not first and again["all"]["picks"][0] == first["all"]["picks"][0] + 1 and again["all"]["open"] == 0


def test_a_featured_report_says_what_it_is_and_how_games_like_it_have_done():
    path, where = _journal(), _archive()
    b = F.badge("nfl", {"date": "2026-11-23", "kickoff": "20:15", "home": "PHI", "away": "DAL"}, where, path)
    assert b["kinds"] == ["monday"] and b["words"] == "Monday night"
    assert b["lines"] == [F.line(F.record(where, "nfl", path)["kinds"]["monday"], "monday")]
    assert F.badge("nfl", {"date": "2026-11-22", "kickoff": "13:00", "home": "BUF", "away": "KC"}, where, path) is None
    # A featured game with nothing finished like it yet: its kinds, no line.
    empty = Path(tempfile.mkdtemp())
    assert F.badge("nfl", {"date": "2026-11-19", "kickoff": "20:15", "home": "HOU", "away": "IND"}, empty, path) == {
        "kinds": ["thursday"], "words": "Thursday night", "lines": []}


def test_the_league_s_record_serves_it_and_any_other_league_s_does_not():
    from engine import ledger
    path, where = _journal(), _archive()
    keep = ledger.DEFAULT_DB
    ledger.DEFAULT_DB = path
    try:
        body = RR.record(where, "nfl")
    finally:
        ledger.DEFAULT_DB = keep
    assert body["featured"]["all"]["games"] == 4 and len(body["games"]) == 6
    assert "featured" not in RR.record(Path(tempfile.mkdtemp()), "nba")
    assert F.record(where, "nba", path) == {}


def test_the_board_marks_its_featured_games_and_their_reports_say_so():
    # The board's own rows carry it (public: who plays and when), for the game cards; each report its badge.
    result = {"date": "2026-W12", "likely_board": {"rows": []},
              "games": [{"home": "HOU", "away": "IND", "date": "2026-11-19", "kickoff": "20:15", "scan": {}},
                        {"home": "BUF", "away": "KC", "date": "2026-11-22", "kickoff": "13:00", "scan": {},
                         "featured": ["thursday"]}]}
    line = GR.attach(result, sport="nfl", conn=sqlite3.connect(":memory:"))
    assert line.startswith("Game reports: 2 game(s)"), line
    assert [g.get("featured") for g in result["games"]] == [["thursday"], None], "a stale mark is taken off"
    reps = {r["game"]: r for r in result["game_reports"]}
    assert reps["IND@HOU"]["featured"]["words"] == "Thursday night" and "featured" not in reps["KC@BUF"]
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '(g.featured || []).length ? `<span class="top-game-tag">Featured</span>`' in app, "the game card says so"


def test_ask_says_how_the_featured_games_have_done():
    from engine import askbot, ledger
    path, where = _journal(), _archive()
    keep_dir, keep_db = askbot._archive_dir, ledger.DEFAULT_DB
    askbot._archive_dir, ledger.DEFAULT_DB = (lambda: where), path
    try:
        got = askbot.report_record("nfl")
    finally:
        askbot._archive_dir, ledger.DEFAULT_DB = keep_dir, keep_db
    fx = got["leagues"]["nfl"]["featured_games"]
    assert fx["every_featured_game"].startswith("Featured games so far, 4 finished games: the reports' picks 4-3-1"), fx
    assert fx["monday_nights"].startswith("Monday nights so far, 1 finished game: the reports' picks 1-2-1"), fx
    assert set(fx) == {"every_featured_game", "lions_games", "thursday_nights", "monday_nights", "games"}
    assert [g["kinds"] for g in fx["games"]] == ["Lions game", "Monday night", "Lions game", "Thursday night"]


def test_the_pages_draw_the_featured_record_and_list_only_those_games():
    assert "function rpFeaturedHTML(fx)" in RP and "${rpFeaturedHTML(fx)}" in RP
    assert 'data-rpk-list="featured"' in RP and "fxKeys.has(" in RP, "the list's own chip: the featured games alone"
    assert "Featured games: Lions games, Thursday nights and Monday nights" in RP
    assert "function featuredHTML(f)" in REPORT_JS and "${featuredHTML(r.featured)}" in REPORT_JS


def test_in_a_browser_the_featured_record_draws_and_its_chip_lists_only_its_games():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    path, where = _journal(), _archive()
    rec = F.record(where, "nfl", path)
    games = [{"date": d, "away": a, "home": h, "game": f"{a}@{h}", "names": {}, "final": {"away": 17, "home": 24},
              "reads": [3, 5], "groups": {}, "call": {"team": h, "right": r}} for d, _l, a, h, _k, r in GAMES]
    record = json.dumps({"sport": "nfl", "totals": {"games": 6, "call": [4, 6], "reads": [18, 30]},
                         "recent": {"games": 6}, "recent_days": 30, "games": games, "more": 0, "featured": rec})
    board = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2026-W12", "recommendations": [],
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
                page.route("**/api/report_tickets?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                          body=json.dumps({"games": {}})))
                for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=board))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", wait_until="load")
                page.wait_for_function("() => typeof switchView === 'function' && state.data", timeout=20000)
                page.evaluate("window._rpWantFacts = true; switchView('reportpicks')")
                page.wait_for_function("() => document.querySelectorAll('.rpk-fact-row').length === 6", timeout=20000)
                drawn = page.evaluate("""() => ({
                    kinds: [...document.querySelectorAll('.rpk-fx-kind h5')].map((h) => h.firstChild.textContent.trim()),
                    games: document.querySelectorAll('.rpk-fx-game').length,
                    tags: [...document.querySelectorAll('.rpk-fx-tag')].map((t) => t.textContent),
                    first: document.querySelector('.rpk-fx-kind p').textContent.replace(/\\s+/g, ' ').trim(),
                    wide: document.documentElement.scrollWidth - innerWidth })""")
                page.click('[data-rpk-list="featured"]')
                page.wait_for_function("() => document.querySelectorAll('.rpk-fact-row').length === 4", timeout=20000)
                only = page.evaluate("""() => [...document.querySelectorAll('.rpk-fact-row .rpk-fact-game b')]
                    .map((b) => b.textContent)""")
                page.click('[data-rpk-list="all"]')
                page.wait_for_function("() => document.querySelectorAll('.rpk-fact-row').length === 6", timeout=20000)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert drawn["kinds"] == ["Every featured game", "Lions games", "Thursday nights", "Monday nights"], drawn
    assert drawn["games"] == 4 and sorted(set(drawn["tags"])) == ["Lions game", "Monday night", "Thursday night"], drawn
    assert drawn["first"].startswith("Picks 4-3-1 +0.3 units · Three-leg parlays 1 of 2 · Touchdown pairs 0 of 1 · "
                                     "Who wins 2 of 4"), drawn["first"]
    assert drawn["wide"] == 0, drawn
    assert len(only) == 4 and not any("Bills" in x or "Cowboys" in x for x in only), only
    assert not errors, errors


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"  FAIL {name}: {exc!r}")
    print(f"\n{'All' if not fails else fails} {'tests passed' if not fails else 'failed'}.")
    sys.exit(1 if fails else 0)
