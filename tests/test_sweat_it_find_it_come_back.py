"""Round three of the ideas (docs/IDEAS.md, 2026-10-27 later: "sweat it,
find it, keep coming back"). Ethan: "think of more ideas and build them all
too." Nine, each held here:

  1. WHAT HAS TO HAPPEN: a live leg says how many more an over needs or an
     under can give up (web/js/slip.js needWords; engine/askbot.needs for Ask).
  2. STREAKS: "5 straight" on a prop row when he has cleared tonight's number
     in each of his last four or more (app.js hitChipsHTML).
  3. OUR PARLAY, IN YOUR SLIP: "Load into my slip" on each engine ticket.
  4. THE LINE'S PATH on Ask's price card (askcards.prices_card tape, ask.js
     askTapeHTML).
  5. ASK ABOUT YOUR TEAMS: the paperclip's "My teams and players"
     (ask.js askFollows; askbot.clean_follows / follows_facts; server.py).
  6. YOUR STAKE, FILLED IN: Track it starts at your unit times our stake.
  7. WHAT BRINGS YOU HERE?: one tap on sign-up, and the new account lands there.
  8. KEYBOARD SHORTCUTS: a for Ask, 1 to 7 the leagues, ? the list.
  9. YOUR WEEK, BY PUSH: Monday morning, last week's record, money and best win.

Run directly: `python3 tests/test_sweat_it_find_it_come_back.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_MODELS_DIR"] = os.path.join(_DIR, "models")
os.environ["QB_LIKELY_CAL"] = os.path.join(_DIR, "likely_calibration.json")
os.environ["QB_SITE_URL"] = "https://qellysbook.example"

from engine import accounts as A                                  # noqa: E402
from engine import askbot as AB                                   # noqa: E402
from engine import askcards as AC                                 # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text(encoding="utf-8")
ASK = (WEB / "js" / "ask.js").read_text(encoding="utf-8")
SLIP = (WEB / "js" / "slip.js").read_text(encoding="utf-8")
ACCT = (WEB / "js" / "account.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _node(src: str):
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def _fn(text: str, name: str) -> str:
    i = text.index(f"function {name}(")
    j = text.index("\n}\n", i) if text[i - 1] == "\n" or i == 0 else text.index("\n  }\n", i)
    return text[i:j + 2]


# 1 --------------------------------------------------------------------------------------
CASES = [({"side": "over", "line": 259.5, "market": "pass_yds"}, 180, "Needs 80 more"),
         ({"side": "under", "line": 259.5, "market": "pass_yds"}, 180, "Can give up 79 more"),
         ({"side": "over", "line": 5, "market": "receptions"}, 5, "Needs 1 more"),
         ({"side": "over", "line": 5, "market": "receptions"}, 6, "Cleared"),
         ({"side": "under", "line": 5, "market": "receptions"}, 5, "On the number: a push now, one more loses"),
         ({"side": "under", "line": 5, "market": "receptions"}, 6, "Past the number"),
         ({"side": "over", "line": 0.5, "market": "anytime_td"}, 0, "Needs one"),
         ({"side": "under", "line": 0.5, "market": "anytime_td"}, 1, "Lost: he has one")]


def test_a_live_leg_says_what_has_to_happen_in_ask_and_on_the_live_tab():
    for leg, now, want in CASES:
        assert AB.needs(leg, now) == want, (leg, now, AB.needs(leg, now))
    assert AB.needs({"market": "moneyline", "line": 1}, 3) == ""
    got = AB._leg_now({"player": "Josh Allen", "side": "over", "line": 259.5, "market": "pass_yds",
                       "live": {"state": "live", "current": 180}})
    assert got["what_has_to_happen"] == "Needs 80 more"
    final = AB._leg_now({"side": "over", "line": 259.5, "market": "pass_yds", "live": {"state": "final", "current": 300}})
    assert "what_has_to_happen" not in final, "only while it is live"
    assert 'if (g.state === "live") bits.push(esc(needWords(l, g.current, line)));' in SLIP
    if not NODE:
        return
    fn = SLIP[SLIP.index("  function needWords("):]
    fn = fn[:fn.index("\n  }\n") + 4]
    got = _node("const num = (x) => String(x);\n" + fn + f"""
const cases = {json.dumps(CASES)};
process.stdout.write(JSON.stringify(cases.map(([l, n, w]) => [needWords(l, n, l.line === 0.5 ? 0.5 : Number(l.line)), w])));""")
    for js, want in got:
        assert js == want, (js, want)


# 2 --------------------------------------------------------------------------------------
def test_a_streak_is_said_as_a_run():
    if not NODE:
        return
    fn = APP[APP.index("function hitChipsHTML(r) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    got = _node("""const escapeAttr = (x) => String(x);
const icon = (n) => `<i data-ic="${n}"></i>`;
""" + fn + """
process.stdout.write(JSON.stringify([
  hitChipsHTML({ recent_values: [8, 7, 9, 4, 6, 7], line: 5.5, side: "over" }),
  hitChipsHTML({ recent_values: [8, 7, 9, 6, 7, 2, 8], line: 5.5, side: "over" }),
  hitChipsHTML({ recent_values: [3, 2, 4, 1, 9], line: 5.5, side: "under" })]));""")
    assert "straight" not in got[0], "three is not a streak"
    assert '<b>5</b> straight' in got[1] and 'class="hit-chip hot"' in got[1] and 'data-ic="hot"' in got[1]
    assert '<b>4</b> straight' in got[2], "an under's run counts games under the number"
    css = (WEB / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".hit-chip.hot {" in css


# 3 --------------------------------------------------------------------------------------
def test_our_parlay_loads_into_your_slip():
    tk = APP[APP.index("function parlayTicket(t, live) {"):]
    tk = tk[:tk.index("\n}\n")]
    assert 'data-parlay-slip="${escapeAttr(String(t.rank))}">Load into my slip</button>' in tk
    h = APP[APP.index('e.target.closest("[data-parlay-slip]")') - 200:]
    h = h[:h.index("\n});\n")]
    assert '_slip = { sport: "", date: "", legs: [] };' in h, "the ticket replaces what the slip held"
    assert "slipToggle(findSlipRow(l.player ? propId(l) : gameBetId(l)) || l)" in h, "each leg as the board has it"
    assert "_slipOpen = n > 0;" in h and "slipRender();" in h


# 4 --------------------------------------------------------------------------------------
def test_the_price_card_draws_the_lines_path():
    out = {"picks": [{"pick": "Josh Allen UNDER 259.5 Passing Yards", "league": "nfl", "player": "Josh Allen",
                      "side": "UNDER", "line": 259.5, "market": "pass_yds", "our_price": -110, "our_book": "FanDuel",
                      "books": [{"book": "FanDuel", "line": 259.5, "under_odds": -110}],
                      "line_since_open": [{"line": 262.5, "minutes_ago": 900}, {"line": 261.5, "minutes_ago": 400},
                                          {"line": 259.5, "minutes_ago": 30}]}]}
    card = AC.prices_card(out)
    assert card["tape"] == [{"line": 262.5, "minutes_ago": 900}, {"line": 261.5, "minutes_ago": 400},
                            {"line": 259.5, "minutes_ago": 30}]
    out["picks"][0]["line_since_open"] = out["picks"][0]["line_since_open"][:1]
    assert "tape" not in AC.prices_card(out), "one point is not a path"
    assert "${askTapeHTML(c.tape)}" in ASK
    if not NODE:
        return
    fn = ASK[ASK.index("function askTapeHTML(tape) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    got = _node("const escapeHtml = (x) => String(x); const escapeAttr = escapeHtml;\n" + fn + """
process.stdout.write(JSON.stringify([askTapeHTML([{line: 262.5}, {line: 261.5}, {line: 259.5}]), askTapeHTML([{line: 1}])]));""")
    assert got[0].startswith('<div class="ask-tape"><svg') and "<path d=\"M4 " in got[0] and "H" in got[0]
    assert "<em>262.5</em><b>259.5</b>" in got[0] and got[1] == ""


# 5 --------------------------------------------------------------------------------------
BOARDS = {"nfl": {"games": [{"home": "BUF", "away": "KC", "date": "2026-11-02", "kickoff": "16:25"},
                            {"home": "DAL", "away": "NYG", "date": "2026-11-02"}],
                  "most_likely": [{"player": "Josh Allen", "team": "BUF", "opponent": "KC", "market": "pass_yds",
                                   "market_label": "Passing Yards", "side": "UNDER", "line": 259.5, "model_prob": 0.62},
                                  {"player": "CeeDee Lamb", "team": "DAL", "opponent": "NYG", "side": "OVER", "line": 79.5,
                                   "model_prob": 0.57}],
                  "recommendations": [{"player": "Puka Nacua", "team": "LA", "side": "OVER", "line": 5.5,
                                       "hit_prob": 0.66, "market": "receptions"}]}}


def test_ask_can_be_about_your_teams_and_players():
    f = AB.clean_follows({"teams": ["nfl:BUF", "nfl:bad code!", "nba:bos"], "players": ["Puka  Nacua", "", "Puka Nacua"]})
    assert f == {"teams": [{"league": "nfl", "team": "BUF"}, {"league": "nba", "team": "BOS"}], "players": ["Puka Nacua"]}
    facts = AB.follows_facts(f, BOARDS)
    assert facts["teams"] == ["NFL BUF", "NBA BOS"] and facts["tonights_games"][0]["game"] == "KC @ BUF"
    who = {p["player"] for p in facts["our_picks_on_them"]}
    assert who == {"Josh Allen", "Puka Nacua"}, "your team's pick and your player's, nobody else's"
    allen = next(p for p in facts["our_picks_on_them"] if p["player"] == "Josh Allen")
    assert allen["board"] == "Most Likely" and allen["our_chance"] == 0.62
    assert 'not mine and not follows else ""' in (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8"), \
        "an answer about your teams is yours alone: never cached"
    assert "the_readers_teams_and_players" in AB.SYSTEM
    assert 'follows = AB.clean_follows(body.get("follows")) if body.get("follows") else None' in SERVER
    assert SERVER.count("follows=follows") == 2, "both the plain and the streamed answer"
    assert "follows: a.follows ? askFollows() : undefined" in ASK
    assert "data-ask-follows" in ASK and "ASK_SUGGEST_FOLLOWS" in ASK
    assert "a.follows" not in APP[APP.index("function askSave() {"):][:300], "this visit only: never stored"


# 6 --------------------------------------------------------------------------------------
def test_track_it_starts_at_your_stake():
    assert "stake_units" in AC.BET_KEYS
    assert 'value="${askStakeGuess(b)}"' in ASK
    if not NODE:
        return
    fn = ASK[ASK.index("function askStakeGuess(b) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    got = _node("let u = 25; const unitDollars = () => u;\n" + fn + """
const a = askStakeGuess({ stake_units: 1.5 }), b = askStakeGuess({}); u = 0; const c = askStakeGuess({ stake_units: 2 });
process.stdout.write(JSON.stringify([a, b, c]));""")
    assert got == ["38", "25", ""], got


# 7 --------------------------------------------------------------------------------------
def test_what_brings_you_here_sets_where_you_land():
    assert "${suWhyHTML()}" in ACCT and 'data-su-why="${k}"' in ACCT
    assert 'localStorage.setItem("qb_why", t.dataset.suWhy)' in ACCT
    assert 'back || whyLand(1) || "#live") : back || whyLand() || dcFirstStop();' in APP
    if not NODE:
        return
    fn = APP[APP.index("function whyLand(free) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    got = _node("""const store = {}; const localStorage = { getItem: (k) => store[k] ?? null,
  setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } };
""" + fn + """
const out = [];
for (const [w, free] of [["fantasy", 0], ["picks", 0], ["picks", 1], ["bets", 1], ["", 0]]) {
  if (w) localStorage.setItem("qb_why", w); out.push(whyLand(free));
}
out.push(localStorage.getItem("qb_why"));
process.stdout.write(JSON.stringify(out));""")
    assert got == ["#fantasy", "#likely", "", "#mybets", "", None], got


# 8 --------------------------------------------------------------------------------------
def test_the_keys_on_a_keyboard():
    blk = APP[APP.index("// THE REST OF THE KEYS"):]
    blk = blk[:blk.index("\n  });\n")]
    assert 'if (e.key === "a") return switchView("ask");' in blk
    assert 'document.querySelectorAll(".sportbar-in .sport-btn")[e.key - 1]' in blk
    assert "/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)" in blk, "never while typing"
    assert "e.metaKey || e.ctrlKey || e.altKey" in blk


# 9 --------------------------------------------------------------------------------------
GOOD = "correct horse battery"
#: Monday 2026-11-02, 10:00 in New York (15:00 UTC).
MONDAY = 1_793_631_600.0


def test_your_week_by_push():
    rows = [{"id": "1", "desc": "Josh Allen Under 259.5", "odds": -110, "stake": 22, "date": "2026-10-27", "result": "win"},
            {"id": "2", "desc": "2-leg parlay", "odds": 165, "stake": 10, "date": "2026-10-28", "result": "win"},
            {"id": "3", "desc": "Henry Over 84.5", "odds": -115, "stake": 20, "date": "2026-10-30", "result": "loss"},
            {"id": "4", "desc": "too old", "odds": 100, "stake": 50, "date": "2026-10-20", "result": "win"},
            {"id": "5", "desc": "open", "odds": 100, "stake": 5, "date": "2026-10-31", "result": "pending"}]
    got = PM.week_summary(rows, "2026-10-26", "2026-11-01")
    assert got == {"w": 2, "l": 1, "p": 0, "net": 16.5, "best": "Josh Allen Under 259.5"}, got
    assert PM.week_summary(rows, "2026-11-02", "2026-11-08") is None
    conn = A.connect()
    try:
        code, out = A.create_user(conn, "week@example.com", GOOD, confirmed=True)
        uid = out["id"]
        A.save_sections(conn, uid, {"mybets": {"ts": 1, "data": {"rows": rows, "deleted": []}}})
        PM.ensure_tables(conn)
        assert PM.week_pass(conn, now=MONDAY) == 0, "nobody's phone asked for their bets"
        PA.subscribe(conn, "https://fcm.googleapis.com/fcm/send/week:APA91bHxyz", topics=["bets"], user_id=uid)
        assert PM.week_pass(conn, now=MONDAY - 6 * 3600) == 0, "Monday from nine, Eastern"
        assert PM.week_pass(conn, now=MONDAY - 86400) == 0, "a Sunday is not a Monday"
        assert PM.week_pass(conn, now=MONDAY) == 1
        assert PM.week_pass(conn, now=MONDAY + 1800) == 0, "once a week"
        msg = conn.execute("SELECT id, kind, title, body, url FROM push_mine WHERE user_id=?", (uid,)).fetchall()
        assert len(msg) == 1
        mid, topic, title, body, url = msg[0]
        assert mid == "bets:week:2026-W44" and topic == "bets" and url == "/#mybets"
        assert title == "Your week: 2–1, +$16.50" and body == "Best win: Josh Allen Under 259.5. My Bets has every one."
    finally:
        conn.close()
    src = (ROOT / "engine" / "pushmine.py").read_text(encoding="utf-8")
    assert 'told += week_pass(conn, now=t)' in src, "the minute's pass runs it"


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
