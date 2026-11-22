"""A settled parlay reads like a betting app's "Recently Settled" list (step ACC, 22 November 2026).

Ethan, with a screenshot of one: "how you can scroll through and see how each leg is highlighted green if it
won, and if it's highlighted red, that leg lost, and then the whole parlay will be highlighted green if that
parlay won. So that's how I want it to look like when you scroll through the game report data, looking to see if
those parlays and picks won or lost." What these hold:

  * one drawing (app.js settledTicketHTML): the ticket's name over how it went and its legs' tally ("Won · 3
    wins", "Lost · 2 wins, 1 loss"), the units at its price on the right, then each leg in its own box, green
    when it won and red when it lost: the bet ("Over 249.5 · Joe Burrow Passing Yards"), and under it what he
    did, the clubs with the final score and the day ("409 · PIT 18 – 38 CIN · Final 11/15");
  * a finished game's report draws its tickets so, what the card said before the game one tap under them, and
    its picks green or red; Report Picks' finished games and the Record's newest tickets draw theirs so too;
  * the record hands each ticket its price and units, and each of the Record's newest its game's final and day;
  * in the browser, at a phone's width, in both themes: the colours are the theme's own, and nothing runs off
    the screen (QB_BROWSER_TESTS=1).

    python3 tests/test_a_settled_parlay_reads_like_a_betting_apps_list.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SETTLED = (ROOT / "web" / "js" / "settled.js").read_text(encoding="utf-8")
RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
RECORD = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
REPORT_JS = ROOT / "web" / "js" / "report.js"
CSS = (ROOT / "web" / "css" / "settled.css").read_text(encoding="utf-8")


def _settled_src() -> str:
    """The drawing itself (js/settled.js): its words, its helpers and the ticket."""
    return SETTLED


def _rp(name: str) -> str:
    at = RP.index(f"function {name}(")
    return RP[at:RP.index("\n}\n", at) + 3]


def _node(script: str, extra: str = ""):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, MINUS: '\\u2212',"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " RES_GAME_MARKETS: new Set(['moneyline', 'total', 'spread', 'team_total']),"
            " RES_SCORE_MARKETS: new Set(['anytime_td', 'anytime_goal', 'goals', 'first_td']),"
            " marketWord: (m) => ({ receptions: 'Receptions', rebounds: 'Rebounds' })[m] || m,"
            " icon: (n) => '[' + n + ']', teamMark: (t) => '<i class=\"tm\">' + t + '</i>',"
            " playerAvatar: (p) => '<i class=\"av\"></i>', teamsForSport: () => ({}), state: { sport: 'nfl' },"
            " teamName: (t) => ({ PHI: '76ers', IND: 'Pacers', CIN: 'Bengals' })[t] || t, plural: (n, w) => n + ' ' + w };"
            "vm.createContext(ctx);"
            f"vm.runInContext({json.dumps(_settled_src() + extra)}, ctx);")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


G = {"sport": "nfl", "home": "CIN", "away": "PIT", "final": {"home": 38, "away": 18}, "date": "2026-11-15"}
WON = {"title": "Three-leg parlay 1", "status": "won", "dec": 2.68, "legs": [
    {"bet": {"player": "Joe Burrow", "team": "CIN", "market": "pass_yds", "market_label": "Passing Yards",
             "side": "over", "line": 249.5}, "res": {"status": "won", "actual": 409}, "open": True},
    {"bet": {"player": "DK Metcalf", "team": "PIT", "market": "receptions", "side": "UNDER", "line": 4.5},
     "res": {"status": "won", "actual": 2}, "open": True},
    {"bet": {"player": "Chase Brown", "team": "CIN", "market": "rush_rec_yds", "market_label": "Rush + Rec Yards",
             "side": "over", "line": 59.5}, "res": {"status": "won", "actual": 83}, "open": True}]}
LOST = {"title": "Three-leg parlay 2", "status": "lost", "dec": 3.48, "legs": [
    {"bet": {"player": "Ja'Marr Chase", "team": "CIN", "market": "anytime_td", "side": "yes"},
     "res": {"status": "won", "actual": 2}},
    {"bet": {"team": "CIN", "market": "moneyline", "game": True}, "res": {"status": "won"}, "words": "Bengals to win",
     "open": True},
    {"bet": {"player": "Aaron Rodgers", "team": "PIT", "market": "pass_yds", "market_label": "Passing Yards",
             "side": "over", "line": 229.5}, "res": {"status": "lost", "actual": 194}}]}
WAIT = {"title": "Touchdown pair 1", "status": "pending", "dec": 4.1, "legs": [
    {"bet": {"player": "Jaylen Warren", "team": "PIT", "market": "anytime_td", "side": "yes"}, "res": {"status": "void"}},
    {"bet": {"player": "Tee Higgins", "team": "CIN", "market": "anytime_td", "side": "yes"},
     "res": {"status": "pending"}}]}


def test_one_drawing_says_each_leg_and_the_ticket():
    got = _node(f"const G = {json.dumps(G)};"
                f"process.stdout.write(JSON.stringify([{json.dumps(WON)}, {json.dumps(LOST)}, {json.dumps(WAIT)}]"
                ".map((t) => vm.runInContext('settledTicketHTML', ctx)(t, G))"
                ".concat([vm.runInContext('settledGameHTML', ctx)({ home: 'HOU', away: 'IND', date: '2026-11-16' })])));")
    if got is None:
        return
    won, lost, wait, unscored = got
    # The ticket: its colour, how it went, its legs' tally, the units at its price.
    assert won.startswith('<div class="st-tix won">'), won[:80]
    assert '<span class="st-tix-verdict">Won</span> · 3 wins' in won
    assert '<span class="st-tix-pay"><b>+1.68u</b><span>+168</span></span>' in won
    # Each leg in its box: the bet as the screenshot says it, then what he did, the clubs and the final, the day.
    assert '<li class="st-leg won" data-open="player:joe-burrow">' in won
    assert '<b class="st-leg-bet">Over 249.5 · Joe Burrow Passing Yards</b>' in won
    assert ('<span class="st-did">409</span><span class="st-dot" aria-hidden="true">·</span><span class="st-game">'
            '<span class="st-club">PIT</span><i class="tm">PIT</i><b class="st-score">18 – 38</b><i class="tm">CIN</i>'
            '<span class="st-club">CIN</span></span><span class="st-dot" aria-hidden="true">·</span>'
            '<span class="st-when">Final 11/15</span>') in won, won
    assert "Under 4.5 · DK Metcalf Receptions" in won and "Over 59.5 · Chase Brown Rush + Rec Yards" in won
    assert won.count('<span class="st-leg-mark won"><span class="st-sr">Won</span>[check]</span>') == 3
    # A lost ticket: red, its legs each their own colour; a game bet in its caller's words, a scorer as he scored.
    assert lost.startswith('<div class="st-tix lost">')
    assert '<span class="st-tix-verdict">Lost</span> · 2 wins, 1 loss' in lost and "<b>−1.00u</b><span>+248</span>" in lost
    assert "Ja&#39;Marr Chase · To score a touchdown" in lost and '<span class="st-did">Scored 2</span>' in lost
    assert '<li class="st-leg won"><span class="st-leg-text"><b class="st-leg-bet">Bengals to win</b>' in lost, \
        "a game bet: its words, no player's page, and the final says what happened"
    assert '<li class="st-leg lost">' in lost and '<span class="st-did">194</span>' in lost and "[cross]" in lost
    # Still waiting: plain, said in words, its price without units.
    assert wait.startswith('<div class="st-tix even">')
    assert '<span class="st-tix-verdict">Waiting</span> · 1 void, 1 waiting' in wait
    assert '<span class="st-tix-pay"><span>+310</span></span>' in wait
    assert "Didn’t play" in wait and "Waiting on the box score" in wait and wait.count("[dash]") == 2
    # No final on hand: the clubs and the day alone.
    assert unscored == ('<span class="st-game"><span class="st-club">IND</span><span>at</span><span class="st-club">HOU'
                        '</span></span><span class="st-dot" aria-hidden="true">·</span><span class="st-when">11/16</span>')


JB = {"market": "assists", "side": "over", "line": 2.5, "player": "Jaylen Brown", "team": "PHI"}
KCP = {"market": "rebounds", "side": "over", "line": 1.5, "player": "Kentavious Caldwell-Pope", "team": "PHI"}
RES = ("const st = { lost: { status: 'lost', actual: 2 }, won: { status: 'won', actual: 4 } };"
       "const grade = (b) => st[b.market === 'assists' ? 'lost' : 'won'];"
       "const words = (x) => x.status === 'lost' ? 'Lost · 2 assists' : 'Won · 4 rebounds';"
       "const ticket = (bets) => { const legs = bets.map(grade); return { status: legs.some((x) => x.status === 'lost')"
       " ? 'lost' : 'won', legs }; };"
       "const RES = { final: { home: 131, away: 124 }, home: 'PHI', away: 'IND', date: '2026-11-16', sport: 'nba',"
       " grade, words, ticket };")


def test_the_finished_report_draws_its_tickets_settled():
    rep = {"game": "IND@PHI", "minutes": 2, "sections": [
        {"key": "card", "title": "Our picks for this game", "blocks": [
            {"type": "picks", "items": [{"rank": 1, "pick": "Jaylen Brown over 2.5 assists", "bet": JB}]}]},
        {"key": "parlays", "title": "Parlays", "blocks": [
            {"type": "parlays", "kind": "three", "items": [{"title": "Parlay 1", "take": 150, "cls": "safe",
                                                           "cls_label": "Safe", "cls_why": "Both legs are short lines.",
                                                           "script": "What it needs: a close game", "legs": [
                {"pick": "Kentavious Caldwell-Pope over 1.5 rebounds", "bet": KCP, "why": ["He rebounds."]},
                {"pick": "Jaylen Brown over 2.5 assists", "bet": JB}]}]}]}]}
    g = {"home": "PHI", "away": "IND", "threes": [{"take_dec": 2.5, "joint": 0.4, "independent": 0.4, "legs": [
        {"player": "Kentavious Caldwell-Pope", "team": "PHI", "market": "rebounds", "market_label": "Rebounds",
         "side": "Over", "line": 1.5}]}], "scorers": []}
    got = _node(RES + f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
                "const R = ctx.window.QBReport;"
                f"const rep = {json.dumps(rep)}, g = {json.dumps(g)};"
                "process.stdout.write(JSON.stringify([R.html(rep, { results: RES }), R.html(rep),"
                " R.gameTickets(g, 'nba', { results: () => RES })]));")
    if got is None:
        return
    graded, plain, tickets = got
    t = graded[graded.index('<div class="st-tix'):]
    assert t.startswith('<div class="st-tix lost">') and "Lost</span> · 1 win, 1 loss" in t
    assert "<b>−1.00u</b><span>+150</span>" in t, "at the price the card said to take it at"
    # A leg the report wrote names its market in the reader's words, off its own words.
    assert "Over 1.5 · Kentavious Caldwell-Pope Rebounds" in t and "Over 2.5 · Jaylen Brown Assists" in t
    assert '<span class="st-club">IND</span><i class="tm">IND</i><b class="st-score">124 – 131</b>' in t
    assert '<span class="st-when">Final 11/16</span>' in t
    # What the card said before the game, one tap under it.
    more = t[t.index('<details class="st-tix-more"><summary>How we built it</summary>'):]
    assert "What it needs: a close game" in more and "Both legs are short lines." in more and "He rebounds." in more
    assert '<li class="gr-pick lost"' in graded, "the report's own pick wears how it went"
    assert "st-tix" not in plain and '<li class="gr-pick"' in plain, "before the final the report is as it was"
    assert tickets.count('<div class="st-tix won">') == 1 and "<b>+1.50u</b><span>+150</span>" in tickets
    assert "Over 1.5 · Kentavious Caldwell-Pope Rebounds" in tickets


def test_report_picks_draws_its_finished_games_so():
    extra = ("\nconst RP_WORDS = { receptions: 'Receptions' };\n"
             + RP[RP.index("const RP_SCORE = "):RP.index("};", RP.index("const RP_SCORE = ")) + 3]
             + RP[RP.index("const RP_SETTLED = "):RP.index("\n", RP.index("const RP_SETTLED = ")) + 1]
             + "".join(_rp(n) for n in ("rpBetWords", "rpSettledLeg", "rpSettledGame", "rpPickLI", "rpTicketsHTML")))
    row = {"date": "2026-11-15", "away": "NE", "home": "DET", "final": {"home": 31, "away": 17}}
    tix = [{"status": "won", "price_dec": 2.75, "pnl_units": 1.75, "legs": [
        {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER", "line": 74.5, "status": "won", "actual": 142},
        {"player": "Amon-Ra St. Brown", "market": "receptions", "side": "OVER", "line": 5.5, "status": "won", "actual": 8}]}]
    pick = {"player": "DET", "market": "spread", "side": "", "line": 3.5, "team": "DET", "game": True, "status": "lost"}
    got = _node(f"const row = {json.dumps(row)};"
                f"process.stdout.write(JSON.stringify([vm.runInContext('rpTicketsHTML', ctx)({json.dumps(tix)}, 'threes',"
                f" 'nfl', row), vm.runInContext('rpPickLI', ctx)({json.dumps(pick)}, row, 'nfl')]));", extra)
    if got is None:
        return
    ticket, spread = got
    assert ticket.startswith('<li class="rpk-st"><div class="st-tix won">') and "<b>+1.75u</b><span>+175</span>" in ticket
    assert "Over 74.5 · Jahmyr Gibbs rush_yds" in ticket and "Over 5.5 · Amon-Ra St. Brown Receptions" in ticket, \
        "the record's word for the market when the answer brings it"
    assert '<span class="st-club">NE</span><i class="tm">NE</i><b class="st-score">17 – 31</b>' in ticket
    assert spread.startswith('<li class="st-leg lost">') and '<b class="st-leg-bet">DET −3.5</b>' in spread, \
        "a game pick in the page's own words for it (rpBetWords), its final under it"
    for src in ("if (slot && x) slot.innerHTML = rpBetsHTML(x, sport, first && i === 0, rows[i]);",
                'rpTicketsHTML(threes, "threes", sport, game)', "picks.map((p) => rpPickLI(p, game, sport))",
                'const settled = fin && g && typeof settledLegHTML === "function" ? bets.map((r) => settledLegHTML({',
                '${settled ? `<ol class="st-legs">${settled}</ol>` : rows ?'):
        assert src in RP, src


def test_the_record_draws_its_newest_tickets_so():
    assert 'if (typeof settledTicketHTML === "function") return settled(t);' in RECORD
    assert "{ sport, home, away, final: t.final || null, date: day });" in RECORD
    assert "units: t.pnl_units, note: t.chance != null ? `we gave it ${Math.round(t.chance * 100)}%` : \"\"," in RECORD
    for rule in (".st-tix.won { border-color: color-mix(in oklab, var(--good) 75%, transparent);",
                 ".st-tix.lost { border-color: color-mix(in oklab, var(--bad) 60%, transparent);",
                 ".st-leg.won { border-color: var(--good); }", ".st-leg.lost { border-color: var(--bad); }"):
        assert rule in CSS, rule
    rcss = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    assert ".gr-pick.won { box-shadow: inset 0 0 0 1.5px var(--good); }" in rcss


def test_the_record_carries_each_tickets_price_units_final_and_day():
    from engine import db, ledger, parlayledger
    from engine import reportoutcome as O
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    parlayledger.ensure_schema(conn)
    for i, (status, pnl) in enumerate((("lost", -1.0), ("open", None))):
        cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, assumed_dec,"
                           " status, pnl_units, at_start) VALUES ('nfl', '2026-W11', ?, 'same_game', 2, 'IND@HOU',"
                           " 'game_three', 3.4818, ?, ?, 1)", (f"k{i}", status, pnl))
        for n, (player, st, actual) in enumerate((("C.J. Stroud", "lost", 194), ("Kayshon Boutte", "won", 2)), 1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, status, actual)"
                         " VALUES (?,?,?,?,?,?,?,?)", (cur.lastrowid, n, player, "pass_yds", "OVER", 229.5, st, actual))
    conn.commit()
    got = O.tickets(conn, "nfl", "2026-W11", "HOU", "IND")["threes"]
    assert (got[0]["status"], got[0]["price_dec"], got[0]["pnl_units"]) == ("lost", 3.4818, -1.0), got[0]
    assert got[1]["price_dec"] == 3.4818 and "pnl_units" not in got[1], "an open ticket has a price and no units yet"
    hist = os.path.join(tempfile.mkdtemp(), "h.db")
    h = db.connect(hist)
    h.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date)"
              " VALUES ('nfl', 2026, '011', 'g1', 'HOU', 'IND', 23, 20, '2026-11-16')")
    h.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score)"
              " VALUES ('nba', 2026, '2026-11-21', 'g2', 'SAC', 'BOS', 110, 118)")
    h.commit()
    h.close()
    rec = {"nfl": {"three": {"recent": [{"date": "2026-W11", "game": "IND@HOU"}, {"date": "2026-W11", "game": "A@B"}]}},
           "nba": {"two": {"recent": [{"date": "2026-11-21", "game": "BOS@SAC"}]}}}
    assert ledger._recent_finals(rec, hist) == 2
    assert rec["nfl"]["three"]["recent"][0] == {"date": "2026-W11", "game": "IND@HOU", "final": {"home": 23, "away": 20},
                                                "day": "2026-11-16"}, "the NFL's week found as a bet is graded"
    assert "final" not in rec["nfl"]["three"]["recent"][1], "a game the history does not hold is left as it was"
    assert rec["nba"]["two"]["recent"][0]["day"] == "2026-11-21"
    missing = os.path.join(tempfile.mkdtemp(), "none.db")
    assert ledger._recent_finals(rec, missing) == 0 and not os.path.exists(missing), "no history, no file left behind"
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert "        rec = parlayledger.game_parlay_record(conn)\n" in src and "    _recent_finals(rec)\n    return rec" in src
    assert set(ledger._game_parlay_record(None)) == {"error"}, "a failure never breaks the export"


SEE = """() => {
  const probe = (v) => { const i = document.createElement('i'); i.style.color = v; document.body.append(i);
    const c = getComputedStyle(i).color; i.remove(); return c; };
  const bc = (s) => { const e = document.querySelector(s); return e ? getComputedStyle(e).borderTopColor : null; };
  return { good: probe('var(--good)'), bad: probe('var(--bad)'), wonLeg: bc('#acc .st-leg.won'),
           lostLeg: bc('#acc .st-leg.lost'), wonTix: bc('#acc .st-tix.won'), plainTix: bc('#acc .st-tix.even'),
           wide: [...document.querySelectorAll('#acc *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
             .map((e) => e.className).slice(0, 5) };
}"""


def _browser():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    out, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for theme in ("dark", "light"):
                    ctx = browser.new_context(viewport={"width": 360, "height": 800}, service_workers="block")
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                                         "catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                    page.wait_for_function("typeof loadRoom === 'function'", timeout=20000)
                    # Never with the first paint: the drawing arrives with the pages that draw it.
                    assert page.evaluate("typeof settledTicketHTML") == "undefined"
                    page.evaluate("loadRoom('js/record.js', 'css/record.css')")
                    page.wait_for_function("typeof settledTicketHTML === 'function'", timeout=20000)
                    page.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
                    page.evaluate("""([g, ts]) => { const box = document.createElement('div'); box.id = 'acc';
                        box.innerHTML = ts.map((t) => settledTicketHTML(t, g)).join(''); document.body.prepend(box); }""",
                                  [G, [WON, LOST, WAIT]])
                    out[theme] = page.evaluate(SEE)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return out, errs


def test_in_the_browser_the_colours_are_the_themes_and_nothing_runs_off():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    out, errs = _browser()
    assert not errs, errs
    for theme, x in out.items():
        assert x["wonLeg"] == x["good"] and x["lostLeg"] == x["bad"], (theme, x)
        assert x["wonTix"] != x["plainTix"], (theme, x)
        assert x["wide"] == [], (theme, x)
    assert out["dark"]["good"] != out["light"]["good"], "each theme's own green"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
