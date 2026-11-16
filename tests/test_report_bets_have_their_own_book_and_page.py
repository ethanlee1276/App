"""Every bet and parlay the game reports post: their own book on the Record
page, and a page of their own.

Ethan, 2026-11-16: "all bets and parlays made from the game reports should be
categorized as 'report' bets under each sport on the record page and also we
should have a page like the most likely bets page but all game report parlays
and bets."

engine/reportbets reads the bets a finished report shows (its picks card, its
matchup reads' picks, its breakout candidates' and fades' picks), each matched
to the board row it came from and tagged with where the report shows it; the
board carries them as `report_bets` (paid); the pass that journals every
board's parlays writes them to the record under `report`, the Most Likely way.
The record export carries the book pooled and per sport with its receipts, and
the Record page draws it beside the reports' parlays (record.js
recReportSection), in no other book's total. The Report Picks page lists them
game by game with each game's tickets (js/reportpicks.js).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import reportbets as RB  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
RECORD = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
REPORT_JS = ROOT / "web" / "js" / "report.js"

ROW = {"kind": "prop", "player": "Jaylen Brown", "team": "BOS", "opponent": "IND", "market": "assists",
       "market_label": "Assists", "side": "Over", "line": 2.5, "odds": -150, "book": "DraftKings",
       "model_prob": 0.64, "headshot": "https://x/jb.png", "tier_label": "Strong", "game_date": "2026-11-16",
       "reasons": ["a long note the list need not carry"]}
READ = {"player": "Pascal Siakam", "team": "IND", "pos": "F", "headshot": "https://x/ps.png", "read": "breakout",
        "matchup_pick": {"market": "points", "market_label": "Points", "side": "over", "line": 20.5, "odds": -115,
                         "book": "FanDuel", "model_prob": 0.58}}
GAME_ROW = {"kind": "game", "player": "BOS ML", "pick_label": "Celtics ML", "team": "BOS", "market": "moneyline",
            "bet_type": "moneyline",
            "side": "", "line": None, "odds": -140, "book": "BetMGM", "model_prob": 0.6, "matchup": "IND @ BOS"}


def _sections():
    from engine.gameresults import bet_of, read_bet
    jb, ps, ml = bet_of(ROW), read_bet(READ), bet_of(GAME_ROW)
    return [
        {"key": "card", "blocks": [{"type": "picks", "items": [{"rank": 1, "bet": jb}, {"rank": 2, "bet": ml},
                                                                {"rank": 3}]}]},
        {"key": "verdict", "blocks": [{"type": "winner", "team": "BOS"}]},
        {"key": "matchups", "blocks": [{"type": "verdicts", "items": [{"verdict": "favorable", "bet": jb}]}]},
        {"key": "watch", "blocks": [{"type": "verdicts", "items": [{"verdict": "up", "bet": ps},
                                                                   {"verdict": "down", "bet": dict(jb, side="under")}]}]},
    ]


def test_each_bet_the_report_shows_once_with_its_price_and_where_it_shows():
    rows = RB.bets_of(_sections(), RB.pool([ROW, GAME_ROW], [READ]))
    by = {(r.get("player"), r["market"], str(r.get("side") or "").lower()): r for r in rows}
    assert len(rows) == 4, rows
    jb = by[("Jaylen Brown", "assists", "over")]
    assert jb["sources"] == ["card", "read"], "his card pick is his read's pick too: one row, both places"
    assert (jb["odds"], jb["book"], jb["model_prob"], jb["tier_label"]) == (-150, "DraftKings", 0.64, "Strong")
    assert "reasons" not in jb, "the list keeps what the page shows and the record journals"
    ps = by[("Pascal Siakam", "points", "over")]
    assert ps["sources"] == ["breakout"] and ps["team"] == "IND" and ps["headshot"] == "https://x/ps.png"
    assert (ps["odds"], ps["model_prob"], ps["position"]) == (-115, 0.58, "F"), "the read's own pick, its face on it"
    assert by[("Jaylen Brown", "assists", "under")]["sources"] == ["fade"], "a fade's pick is its own bet"
    ml = by[("BOS ML", "moneyline", "")]
    assert ml["kind"] == "game" and ml["odds"] == -140 and ml["matchup"] == "IND @ BOS"
    assert ml["pick_label"] == "Celtics ML", "the row's own words for a game bet (app.js deckPickRow reads them)"
    assert RB.bets_of([{"key": "card", "blocks": [{"type": "picks", "items": [{"bet": {"market": "assists",
             "side": "over", "line": 1.5, "player": "No Row"}}]}]}])[0] == {
        "player": "No Row", "market": "assists", "side": "over", "line": 1.5, "sources": ["card"]}, \
        "a bet with no board row stays on the list, with no price for the record to take"


def test_the_board_carries_them_and_the_reports_no_longer_do():
    result = {"game_reports": [{"game": "IND@BOS", "away": "IND", "home": "BOS",
                                "_bets": RB.bets_of(_sections(), RB.pool([ROW, GAME_ROW], [READ]))},
                               {"game": "NYK@PHI", "away": "NYK", "home": "PHI"}]}
    assert RB.attach(result) == 4
    assert all("_bets" not in r for r in result["game_reports"])
    assert {b["game"] for b in result[RB.KEY]} == {"IND@BOS"}
    assert all(b["home"] == "BOS" and b["away"] == "IND" for b in result[RB.KEY])
    empty = {"game_reports": [{"game": "A@B"}], RB.KEY: [{"stale": 1}]}
    assert RB.attach(empty) == 0 and RB.KEY not in empty, "no bets, no list left behind"
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "bets = reportbets.bets_of(sections, reportbets.pool(_card_rows(c), c.reads))" in gr
    assert '**({"_bets": bets} if bets else {}),' in gr, "every league's report, in the step they share"
    lr = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert gr.count("n_bets = _lift_bets(result)") == 1 and lr.count("n_bets = _lift_bets(result)") == 1
    from engine import gate
    assert RB.KEY in gate.PAID_KEYS, "the picks under another name: paid"


def test_the_record_journals_them_in_their_own_book_the_most_likely_way():
    from engine import ledger
    conn = ledger.connect(":memory:")
    rows = [dict(r, game="IND@BOS") for r in RB.bets_of(_sections(), RB.pool([ROW, GAME_ROW], [READ]))]
    rows.append({"player": "No Price", "market": "assists", "side": "over", "line": 1.5, "sources": ["card"],
                 "model_prob": 0.7, "game": "IND@BOS"})
    board = {"date": "2026-11-16", "games": [], RB.KEY: rows}
    n = RB.journal(conn, board, "nba")
    got = conn.execute("SELECT player, market, side, category, stake_units, stake_dollars FROM bets").fetchall()
    assert n == 3 and len(got) == 3, [tuple(g) for g in got]
    assert {g[3] for g in got} == {"report"}
    assert all(g[4] == 0.1 and not g[5] for g in got), "a flat 0.1 unit, no money"
    assert {(g[0], g[1], g[2]) for g in got} == {("Jaylen Brown", "assists", "OVER"), ("BOS", "moneyline", "OVER"),
                                                 ("Pascal Siakam", "points", "OVER")}, \
        "a game bet keyed off its club; the fade's under and No Price carry no price: no bet"
    assert RB.journal(conn, board, "nba") == 0, "a pick already in the book is not written twice"
    assert ledger.REPORT_CATEGORY == RB.CATEGORY
    assert RB.CATEGORY not in ledger.RECOMMENDED_CATEGORIES, "a lens on other books' picks: in no chip or total"
    pl = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
    assert "reportbets.journal(conn, board, sport)" in pl and "board = json.loads(path.read_text())" in pl
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    for k in ('"report": performance(conn, category=REPORT_CATEGORY, since=since),', '"report_by_sport": {',
              '"report_recent": recent_settled(conn, REPORT_RECENT_LIMIT, category=REPORT_CATEGORY,'):
        assert k in src, k


def _node(js):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


STUBS = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
         "const escapeHtml = esc, escapeAttr = esc; const MINUS = '−';"
         "const icon = (n) => `<i data-ic=\"${n}\"></i>`;"
         "const plural = (n, one) => `${n} ${n === 1 ? one : one + 's'}`;"
         "const american = (o) => (o > 0 ? '+' : '') + o; const marketWord = (m) => ({ assists: 'Assists' })[m] || m;"
         "const SPORT_META = { nba: { name: 'NBA' } };\n")


def test_the_record_page_draws_the_book_and_the_reports_parlays():
    i = RECORD.index("function recReportSection(rep, scope, recent, game) {")
    fn = RECORD[i:RECORD.index("\n}\n", i) + 3]
    rep = {"settled": 12, "open": 3, "wins": 8, "losses": 4, "pushes": 0, "net_units": 0.42, "win_rate": 0.667}
    game = {"three": {"graded": 9, "wins": 2, "net_units": -1.5, "by_sport": {"nba": {"graded": 4, "wins": 1,
                                                                                         "net_units": 0.8}}},
            "scorers": {"graded": 0, "open": 6, "by_sport": {}}}
    recent = [{"date": "2026-11-15", "sport": "nba", "player": "Jaylen Brown", "market": "assists", "line": 2.5,
               "odds": -150, "status": "won"},
              {"date": "2026-11-15", "sport": "nhl", "player": "A Skater", "market": "shots", "line": 2.5,
               "odds": -120, "status": "lost"}]
    got = _node(STUBS + fn + f"""
      process.stdout.write(JSON.stringify([recReportSection({json.dumps(rep)}, 'nba', {json.dumps(recent)},
        {json.dumps(game)}), recReportSection({json.dumps(rep)}, '', {json.dumps(recent)}, {json.dumps(game)}),
        recReportSection(null, 'nhl', [], {{}})]));""")
    if got is None:
        return
    nba, pooled, none = got
    assert ">Report bets" in nba and "posted for NBA, graded on its own" in nba
    assert '<b class="rr-big">8-4</b>' in nba and '<span class="rr-pos">+0.42u</span>' in nba
    assert "Jaylen Brown" in nba and "A Skater" not in nba, "the league's own receipts"
    assert "<b>1 of 4</b> hit" in nba and "Three-leg parlays" in nba
    assert "Scorer pairs" not in nba, "a pool with nothing graded in the league draws nothing there"
    assert "<b>2 of 9</b> hit" in pooled and "6 open, none graded yet" in pooled and "A Skater" in pooled
    assert "none of it is added into their totals" in nba
    assert none == ""
    assert "+ recReportSection(scoped ? (d.report_by_sport || {})[scope] : d.report, scoped ? scope : \"\"," in RECORD
    css = (ROOT / "web" / "css" / "record.css").read_text(encoding="utf-8")
    assert ".rec-report .rr-pos { color: var(--good);" in css


def test_report_picks_has_a_door_everywhere_a_page_does():
    assert 'data-view="reportpicks" id="reportpicks-tab"' in HTML and '<section class="view" id="view-reportpicks">' in HTML
    assert '<div id="reportpicks-body"></div>' in HTML
    assert ('function renderReportPicks(...a) { return roomCall(renderReportPicks, "renderReportPicks", '
            '"js/reportpicks.js", "css/reportpicks.css", a); }') in APP
    assert '  if (name === "reportpicks") renderReportPicks();' in APP
    assert '["reportpicks-body", () => renderReportPicks(), true],' in APP
    for lst in ('const VIEW_ORDER = [', 'const BOARD_VIEWS = [', 'const SWIPE_VIEWS = ['):
        i = APP.index(lst)
        assert '"reportpicks"' in APP[i:APP.index("];", i)], lst
    assert '"view:parlays", "view:reportpicks"' in APP, "the phone's menu"
    assert 'ufc: ["parlays", "reportpicks",' in APP, "a fight card has no game reports"
    assert '"js/reportpicks.js", "css/reportpicks.css",' in (ROOT / "engine" / "shrink.py").read_text(encoding="utf-8")
    assert '"/js/reportpicks.js", "/css/reportpicks.css",' in (ROOT / "web" / "sw.js").read_text(encoding="utf-8")


def test_the_page_lays_each_game_out_with_its_picks_then_its_tickets():
    rows = [dict(r, game="IND@BOS", home="BOS", away="IND")
            for r in RB.bets_of(_sections(), RB.pool([ROW, GAME_ROW], [READ]))]
    d = {"games": [{"away": "NYK", "home": "PHI", "date": "2026-11-16"}, {"away": "IND", "home": "BOS",
                                                                          "date": "2026-11-16", "kickoff": "19:30"}],
         "report_bets": rows,
         "game_parlays": {"games": [{"away": "IND", "home": "BOS", "threes": [{}, {}], "scorers": [{}]},
                                    {"away": "NYK", "home": "PHI", "threes": [{}], "scorers": []}]}}
    rec = {"report_by_sport": {"nba": {"settled": 5, "wins": 3, "losses": 2, "net_units": -0.1}},
           "two_leg": {"game": {"three": {"by_sport": {"nba": {"graded": 6, "wins": 1}}}, "scorers": {}}}}
    got = _node(STUBS + """
      const state = { sport: 'nba' };
      const teamName = (t) => ({ BOS: 'Celtics', IND: 'Pacers', NYK: 'Knicks', PHI: '76ers' })[t] || t;
      const whenLabel = (dt, k) => k ? 'Tonight 7:30 PM' : '';
      const gameId = (g) => `${g.date}_${g.away}@${g.home}`;
      const likelyOpen = (r) => ` data-open="likely:${r.player}"`;
      const deckPickRow = (r, o) => `<row ${o.door}>${r.player}|${o.note}</row>`;
      """ + PAGE + f"""
      const d = {json.dumps(d)};
      const bos = rpGameHTML(d, 'IND@BOS', d.report_bets, d.game_parlays.games[0]);
      const phi = rpGameHTML(d, 'NYK@PHI', [], d.game_parlays.games[1]);
      process.stdout.write(JSON.stringify([bos, phi, rpRecordLine({json.dumps(rec)}, 'nba'), rpRecordLine({{}}, 'nba')]));""")
    if got is None:
        return
    bos, phi, line, empty = got
    assert '<section class="rpk-game" id="rpk-IND-BOS">' in bos and "<b>Pacers at Celtics</b>" in bos
    assert "Tonight 7:30 PM · 4 picks · 2 parlays · 1 scorer pair" in bos
    assert 'data-gid="2026-11-16_IND@BOS">Open the report</button>' in bos, "the game opens with its report"
    assert '<row  data-open="likely:Jaylen Brown">Jaylen Brown|Our picks · Matchup read</row>' in bos
    assert "Pascal Siakam|Breakout candidate</row>" in bos and "|Fade</row>" in bos
    assert '<div class="rpk-tix" data-rpk-tix="IND@BOS"></div>' in bos, "its tickets, filled by the report's own renderer"
    assert "No single pick on this game clears our bars." in phi and 'data-rpk-tix="NYK@PHI"' in phi
    assert line == "On the record so far: picks 3-2 (−0.10u) · three-leg parlays 1 of 6 hit."
    assert empty == ""
    assert "R.gameTickets(x.tix, state.sport, { results: () => reportResults(rpGame(d, el.dataset.rpkTix)) })" in PAGE
    assert 'host.innerHTML = memberLockHTML("Report Picks",' in PAGE, "the reports' picks are a member's"


def test_one_game_s_tickets_draw_the_way_the_parlays_page_draws_them():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    leg = {"player": "Jaylen Brown", "team": "BOS", "market": "assists", "side": "over", "line": 2.5, "odds": -150,
           "book": "DraftKings", "p": 0.64}
    g = {"away": "IND", "home": "BOS", "threes": [{"legs": [leg, dict(leg, player="Pascal Siakam")], "joint": 0.4}],
         "scorers": [], "scorers_note": "No pair clears the bar."}
    js = ("const vm = require('vm'); const fs = require('fs');"
          "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, slugify: (s) => s, teamName: (t) => t,"
          " playerAvatar: () => '' }; vm.createContext(ctx);"
          f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
          f"const g = {json.dumps(g)}; const R = ctx.window.QBReport;"
          "process.stdout.write(JSON.stringify([R.gameTickets(g, 'nba'), R.gameParlays({ games: [g] }, 'nba')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    one, page = json.loads(out.stdout)
    assert "Pascal Siakam" in one and "No pair clears the bar." in one
    assert one.strip() in page, "the Parlays page draws each game through the same function"


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
