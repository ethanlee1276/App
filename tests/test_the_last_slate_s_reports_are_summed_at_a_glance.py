"""The last slate's reports, summed at a glance on Report Picks (2026-11-19,
LASTNIGHT1).

Ethan, 2026-11-19: "Clearly we're doing okay on the picks, but the parlays we
make are not doing good ... don't come back till the parlays are better and
making money." Whether last night's picks hit and its parlays did was two tabs
and a scroll away, a game at a time. One of mine: the newest day with a
finished game, summed in one line above today's picks.

What these hold:

  * `reportrecord.last_slate` sums the newest day's games on a league's record:
    its reports' picks at one unit a pick at the price posted, each kind of
    ticket as the Record counts it (the set each report carried at the start),
    and the calls; an earlier day's games are not in it, nor a ticket the board
    replaced before the start;
  * it is read again only when the archive or the journal moved, and a league
    with no finished game has none;
  * the league's record serves it (/api/report_record ``last_slate``), every
    league's, and the page draws it above today's picks: the day in words, the
    line in the league's own word for its scorer pairs, and a way to each game.

    python3 tests/test_the_last_slate_s_reports_are_summed_at_a_glance.py
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
sys.path.insert(0, str(ROOT / "tests"))

FX = __import__("test_the_featured_games_keep_their_own_record")   # the shared journal and archive (a sibling test)
from engine import reportrecord as RR  # noqa: E402

RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")


def test_the_newest_day_s_games_are_summed():
    path, where = FX._journal(), FX._archive()
    got = RR.last_slate(where, "nfl", path)
    # Thanksgiving's two games (26 November), featured or not: the Lions' and the Cowboys'.
    assert got["date"] == "2026-11-26" and got["games"] == 2, got
    # Each report's own picks at one unit a pick: two −150 winners are +0.67 apiece.
    assert got["picks"] == [2, 0, 0] and got["units"] == 1.34 and got["open"] == 0, got
    # The set each report carried at the start: one two-leg ticket still waiting on its game.
    assert got["tickets"] == {"threes": [0, 0, 0.0], "twos": [0, 0, 0.0], "scorers": [0, 0, 0.0]}, got["tickets"]
    assert got["tickets_open"] == 1 and got["call"] == [2, 2], got
    # No earlier day's game is in it (the Sunday the Lions won a three-leg ticket), and no other league's.
    assert RR.last_slate(Path(tempfile.mkdtemp()), "nba", path) == {}


def test_a_ticket_replaced_before_the_start_is_not_the_slate_s():
    path = FX._journal()
    where = Path(tempfile.mkdtemp())
    # Monday night alone on the record: its kept ticket lost, and the version replaced before kickoff won.
    date, label, away, home, kickoff, right = FX.GAMES[2]
    FX.RA.write(FX.RA.path_for(where, "nfl", date, away, home), {
        "sport": "nfl", "date": date, "label": label, "away": away, "home": home, "game": f"{away}@{home}",
        "kickoff": kickoff, "final": {"away": 23, "home": 20}, "results": {},
        "report": {"away": away, "home": home, "sections": [],
                   "graded": {"status": "graded", "right": 3, "graded": 5, "call": {"team": home, "right": right}}}})
    RR.refresh(where, "nfl")
    got = RR.last_slate(where, "nfl", path)
    assert got["date"] == "2026-11-16" and got["games"] == 1
    assert got["picks"] == [1, 2, 1] and got["units"] == -1.47, got
    assert got["tickets"]["threes"] == [0, 1, -1.0] and got["tickets"]["scorers"] == [0, 1, -1.0], got["tickets"]
    assert got["call"] == [0, 1]


def test_it_is_read_again_only_when_its_sources_move():
    path, where = FX._journal(), FX._archive()
    first = RR.last_slate(where, "nfl", path)
    assert RR.last_slate(where, "nfl", path) is first, "the same archive and journal: not read again"
    conn = sqlite3.connect(path)
    conn.execute("UPDATE parlays SET status='won', pnl_units=1.6 WHERE grade='CHI@DET'")
    conn.commit()
    conn.close()
    again = RR.last_slate(where, "nfl", path)
    assert again is not first and again["tickets"]["twos"] == [1, 0, 1.6] and again["tickets_open"] == 0, again


def test_the_league_s_record_serves_it():
    from engine import ledger
    path, where = FX._journal(), FX._archive()
    keep = ledger.DEFAULT_DB
    ledger.DEFAULT_DB = path
    try:
        body = RR.record(where, "nfl")
    finally:
        ledger.DEFAULT_DB = keep
    assert body["last_slate"]["date"] == "2026-11-26" and body["last_slate"]["games"] == 2
    assert "last_slate" not in RR.record(Path(tempfile.mkdtemp()), "nba"), "no finished game, nothing said"


def test_ask_says_how_the_last_slate_went():
    from engine import askbot, ledger
    path, where = FX._journal(), FX._archive()
    keep_dir, keep_db = askbot._archive_dir, ledger.DEFAULT_DB
    askbot._archive_dir, ledger.DEFAULT_DB = (lambda: where), path
    try:
        got = askbot.report_record("nfl")["leagues"]["nfl"]["last_slate"]
    finally:
        askbot._archive_dir, ledger.DEFAULT_DB = keep_dir, keep_db
    assert got == {"date": "2026-11-26", "games": 2, "report_picks": "2-0", "units_at_one_unit_a_pick": 1.34,
                   "still_waiting_on_the_box_score": 1, "call_right": "2 of 2"}, got


def _fn(name):
    at = RP.index(f"function {name}(")
    return RP[at:RP.index("\n}\n", at) + 3]


def _draw(ls, sport, now="2026-11-27T15:00:00Z"):
    consts = RP[RP.index("const RP_FX_TICKETS = "):RP.index("\n", RP.index("const RP_FX_TICKETS = ")) + 1]
    js = """
const escapeHtml = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
const icon = (n) => `[${n}]`;
const plural = (n, one, many) => `${n} ${Number(n) === 1 ? one : (many || one + "s")}`;
const formatGameDate = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-US",
  { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const recapDayLabel = (date, y) => (!date || date === y ? "Last night"
  : new Date(date + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" }));
const _now = Date.parse(%s);
Date.now = () => _now;
%s
%s
process.stdout.write(rpSlateHTML(%s, %s));
""" % (json.dumps(now), consts, "".join(_fn(n) for n in ("rpFxSigned", "rpFxLine", "rpSlateHTML")),
       json.dumps(ls), json.dumps(sport))
    node = shutil.which("node") or "/opt/node22/bin/node"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return " ".join(out.stdout.split())


SLATE = {"date": "2026-11-26", "games": 12, "picks": [54, 20, 1], "units": 3.1, "open": 0,
         "tickets": {"threes": [9, 11, 6.2], "twos": [8, 4, 5.5], "scorers": [1, 3, -0.4]}, "tickets_open": 2,
         "call": [7, 12]}


def test_the_page_draws_it_above_today_s_picks():
    html = _draw(SLATE, "nhl")
    assert '<h4 class="rpk-slate-h">Last night<span>12 games</span></h4>' in html, html
    assert "Picks <b>54-20-1</b>" in html and '<span class="rpk-fx-u won">+3.1 units</span>' in html
    assert "Three-leg parlays <b>9 of 20</b>" in html and "Two-leg parlays <b>8 of 12</b>" in html
    assert "Goal-scorer pairs <b>1 of 4</b>" in html and "Touchdown pairs" not in html, "the league's own word"
    assert "Who wins <b>7 of 12</b>" in html and "2 still waiting on the box score" in html
    assert "data-rpk-slate-go" in html and "Each game, pick by pick" in html
    # Football's slate two days on is said by its day, and its pairs are touchdown pairs.
    old = _draw(dict(SLATE, date="2026-11-22"), "nfl")
    assert '<h4 class="rpk-slate-h">Sunday, Nov 22<span>12 games</span></h4>' in old, old
    assert "Touchdown pairs <b>1 of 4</b>" in old
    # Games that finished this evening are today's so far, by the reader's own calendar.
    tonight = _draw(dict(SLATE, date="2026-11-27", games=3), "nba")
    assert '<h4 class="rpk-slate-h">Today so far<span>3 games</span></h4>' in tonight, tonight
    # Nothing finished, nothing drawn.
    assert _draw(None, "nba") == "" and _draw({"date": "2026-11-26", "games": 0}, "nba") == ""
    # The slot sits above today's picks, is filled from the record the facts tab reads, and has its styles.
    # Under the door to Best Parlays (21 November), above the day's picks.
    assert '`<div data-rpk-slate></div>${today}`' in RP and "rpSlateFill(host, state.sport);" in RP
    assert "draw(rpSlateSeen(sport, b.last_slate || null));" in RP
    assert ".rpk-slate {" in CSS and ".rpk-slate-go" in CSS


def test_the_card_draws_in_the_real_page_and_opens_each_game():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    games = [{"date": "2026-11-26", "away": "CHI", "home": "DET", "game": "CHI@DET", "names": {},
              "final": {"away": 17, "home": 24}, "reads": [3, 5], "groups": {}, "call": {"team": "DET", "right": True}}]
    record = json.dumps({"sport": "nfl", "totals": {"games": 1, "call": [1, 1], "reads": [3, 5]},
                         "recent": {"games": 1}, "recent_days": 30, "games": games, "more": 0, "last_slate": SLATE})
    board = json.dumps({"sport": "nfl", "generated_from": "live", "date": "2026-W13", "recommendations": [],
                        "most_likely": [], "games": [], "player_stats": {}, "report_bets": [],
                        "game_parlays": {"games": []}})
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
                page.evaluate("switchView('reportpicks')")
                page.wait_for_selector(".rpk-slate", timeout=20000)
                drawn = page.evaluate("""() => {
                    const card = document.querySelector('.rpk-slate');
                    const today = document.querySelector('.subgroup[data-subgroup="today"]');
                    return { text: card.innerText.replace(/\s+/g, ' ').trim(),
                             // First of the day's own (the door to Best Parlays is the page's switch since ABR).
                             first: today.firstElementChild.hasAttribute('data-rpk-slate'),
                             kept: !!(JSON.parse(localStorage.getItem('qb.rpkSlate') || '{}').nfl || {}).games,
                             wide: document.documentElement.scrollWidth - innerWidth };
                }""")
                shot = os.environ.get("QB_SHOT_DIR")
                if shot:
                    page.screenshot(path=os.path.join(shot, "rpk-slate.png"))
                page.click("[data-rpk-slate-go]")
                page.wait_for_function("""() => !document.querySelector('.subgroup[data-subgroup="facts"]').hidden""",
                                       timeout=20000)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
    assert "12 games" in drawn["text"] and "Picks 54-20-1 +3.1 units" in drawn["text"], drawn["text"]
    assert "Three-leg parlays 9 of 20" in drawn["text"] and "Touchdown pairs 1 of 4" in drawn["text"], drawn["text"]
    assert drawn["first"], "above today's picks"
    assert drawn["kept"], "remembered, so a return visit draws it at once"
    assert drawn["wide"] <= 0, "no sideways scroll on a phone"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
