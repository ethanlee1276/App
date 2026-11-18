"""A finished game's page says how every pick, parlay, leg and read turned out.

Ethan, 2026-11-16, with a finished Pacers at 76ers page: "when a game is
already over and someone goes and clicks on this game page ... we need to
show in all of these including stuff I didn't show what the outcome was of
the game and if these props won or lost and if the parlays won or lost and
what legs won and lost and if our game report and reads was correct ... And
that needs to be done for all sports."

engine/gameresults reads the journal's own verdicts (engine/ledger grades
every posted pick against the box score) for the board being published and
stamps them on it (engine/gate.publish, every league from one place) as the
paid `pick_results`: the actual number for each graded player and market, or
a void. The page grades each pick it shows at that pick's own line and side
the journal's way (app.js pickResult), and a game bet off the final score:
every card wears its result, the report marks its picks, its read picks, each
parlay leg and ticket and the call, the Parlays page marks each finished
game's tickets, and a finished game's page opens on the final and a count.
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
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameresults as GR  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
REPORT_JS = ROOT / "web" / "js" / "report.js"
GRADER = APP[APP.index("/* WHAT HAPPENED, ON A FINISHED GAME"):APP.index("//: The weather lines a game page's header")]


def _journal(rows):
    """A journal file with the columns the verdicts are read from."""
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, date TEXT, player TEXT, market TEXT, "
                 "side TEXT, line REAL, status TEXT, actual REAL, category TEXT, leg INTEGER)")
    conn.executemany("INSERT INTO bets (sport, date, player, market, side, line, status, actual, category, leg) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return p


ROWS = [("nba", "2026-11-15", "Jaylen Brown", "assists", "OVER", 2.5, "lost", 2, "most_likely", None),
        ("nba", "2026-11-15", "Jaylen Brown", "assists", "OVER", 2.5, "lost", 2, "parlay_leg", None),
        ("nba", "2026-11-15", "Kentavious Caldwell-Pope", "rebounds", "OVER", 1.5, "won", 4, "main", None),
        ("nba", "2026-11-15", "Aaron Nesmith", "threes", "OVER", 0.5, "void", None, "most_likely", None),
        ("nba", "2026-11-15", "Pascal Siakam", "assists", "OVER", 1.5, "open", None, "most_likely", None),
        ("nba", "2026-11-15", "PHI ML", "moneyline", "", 0.0, "won", 1, "game", None),
        ("nba", "2026-11-14", "Jaylen Brown", "assists", "OVER", 2.5, "won", 9, "most_likely", None),
        ("mlb", "2026-11-15", "Aaron Judge", "hits", "OVER", 0.5, "won", 2, "main", 2),
        ("nfl", "2026-W10", "Jahmyr Gibbs", "anytime_td", "OVER", 0.5, "won", 2, "parlay_leg", None)]


def test_the_journal_s_verdicts_are_read_for_one_board_and_never_written():
    p = _journal(ROWS)
    got = GR.read("nba", "2026-11-15", p)
    assert got == {"jaylenbrown|assists": {"a": 2.0}, "kentaviouscaldwellpope|rebounds": {"a": 4.0},
                   "aaronnesmith|threes": {"v": 1}}, got
    assert "pascalsiakam|assists" not in got, "an open pick waits"
    assert GR.read("mlb", "2026-11-15", p) == {"aaronjudge|hits|2": {"a": 2.0}}, "a doubleheader's second game"
    assert GR.read("nba", "2026-11-15", Path(tempfile.mkdtemp()) / "none.db") == {}, "no journal, nothing stamped"
    assert GR.key("Luka Dončić", "points") == "lukadoncic|points"


def test_the_publish_stamps_every_league_s_board_and_keeps_it_paid():
    p = _journal(ROWS)
    board = {"sport": "nba", "date": "2026-11-15", "games": []}
    assert GR.stamp(board, "nba.json", p) == 3 and len(board[GR.KEY]) == 3
    stale = {"sport": "nba", "date": "2026-11-13", "games": [], GR.KEY: {"x|y": {"a": 1}}}
    assert GR.stamp(stale, "nba.json", p) == 0 and GR.KEY not in stale, "nothing graded, nothing left behind"
    other = {"sport": "nba", "chances": {}}
    assert GR.stamp(other, "nba_cup.json", p) == 0 and GR.KEY not in other, "only a sports board"
    # The NFL's and MLB's original boards name no sport: the file does.
    nfl = {"date": "2026-W10", "games": []}
    assert GR.stamp(nfl, "recommendations.json", p) == 1 and nfl[GR.KEY] == {"jahmyrgibbs|anytime_td": {"a": 2.0}}
    assert GR.stamp({"date": "2026-W10", "games": []}, "/srv/web/data/recommendations.json", p) == 1
    assert GR.stamp({"date": "2026-W10", "games": []}, "elsewhere.json", p) == 0, "no sport, no guess"
    from engine import gate
    assert GR.KEY in gate.PAID_KEYS
    public = gate.redact(dict(board), "nba.json")
    assert public[GR.KEY] == {} and public["locked"][GR.KEY] == 3, "the verdicts name the picks: paid"
    pub = (ROOT / "engine" / "gate.py").read_text(encoding="utf-8")
    assert pub.index("betlinks.stamp(payload, label)") < pub.index("gameresults.stamp(payload, label)")


def test_the_report_s_picks_reads_and_legs_carry_the_pick_itself():
    assert GR.bet_of({"player": "Jaylen Brown", "team": "PHI", "market": "assists", "side": "Over", "line": 2.5}) == \
        {"market": "assists", "side": "over", "line": 2.5, "player": "Jaylen Brown", "team": "PHI"}
    game = GR.bet_of({"kind": "game", "player": "PHI ML", "team": "PHI", "opponent": "IND", "market": "moneyline",
                      "side": "", "line": None})
    assert game["game"] is True and "player" not in game and game["team"] == "PHI"
    read = {"player": "Jaylen Brown", "team": "PHI",
            "matchup_pick": {"market": "assists", "side": "over", "line": 2.5, "held_note": "held back: 60%"}}
    assert GR.read_bet(read) is None, "a held-back pick is no pick"
    read["pick"] = {"market": "assists", "side": "over", "line": 2.5}
    assert GR.read_bet(read)["player"] == "Jaylen Brown"
    from engine import gameparlays as GP
    leg = {"player": "Jaylen Brown", "team": "PHI", "market": "assists", "side": "Over", "line": 2.5, "p": 0.64,
           "odds": -250, "book": "BetMGM"}
    card = GP.card({"legs": [leg, dict(leg, player="Tyrese Maxey", market="points", line=20.5)], "joint": 0.4,
                    "independent": 0.38}, 1, "three", "nba")
    assert card["legs"][0]["bet"] == {"market": "assists", "side": "over", "line": 2.5, "player": "Jaylen Brown",
                                      "team": "PHI"}
    from engine import breakouts
    up = breakouts.card(dict(read, pro=["usage up"]), "up", pick="Most Likely pick: Jaylen Brown over 2.5 assists")
    assert up["bet"]["market"] == "assists"
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '**({"bet": _bet_of(r)} if _bet_of(r) else {})' in gr and '"bet": _read_bet(r)' in gr


def _node(body, prelude=""):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    js = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const escapeHtml = esc, escapeAttr = esc; const NAMES = { PHI: '76ers', IND: 'Pacers' };"
          "const teamName = (t) => NAMES[t] || t; let state = { view: 'game', data: {} }; let CARD_GAME = null;"
          "function cardInGame(r) { return CARD_GAME; }\n"
          + GRADER + "\n" + prelude + f"\nprocess.stdout.write(JSON.stringify((() => {{ {body} }})()));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


GAME = ("const G = { home: 'PHI', away: 'IND', live: { state: 'final', home_score: 131, away_score: 124 } };"
        "state.data = { games: [G], pick_results: { 'jaylenbrown|assists': { a: 2 }, "
        "'kentaviouscaldwellpope|rebounds': { a: 4 }, 'aaronnesmith|threes': { v: 1 }, "
        "'joelembiid|anytime_td': { a: 0 }, 'tyresemaxey|points': { a: 20.5 } } };")


def test_each_pick_is_graded_at_its_own_line_and_side_the_journal_s_way():
    got = _node(GAME + """
      const P = (r) => pickResult(r, G);
      return {
        over_lost: P({ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5 }),
        under_won: P({ player: 'Jaylen Brown', market: 'assists', side: 'Under', line: 2.5 }),
        lower_line: P({ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 1.5 }),
        push: P({ player: 'Tyrese Maxey', market: 'points', side: 'Over', line: 20.5 }),
        void: P({ player: 'Aaron Nesmith', market: 'threes', side: 'Over', line: 0.5 }),
        waiting: P({ player: 'Pascal Siakam', market: 'assists', side: 'Over', line: 1.5 }),
        scorer: P({ player: 'Joel Embiid', market: 'anytime_td', side: 'yes', line: null }),
        ml: P({ kind: 'game', market: 'moneyline', team: 'PHI', side: '', line: null }),
        spread: P({ kind: 'game', market: 'spread', team: 'IND', side: '', line: 7.5 }),
        spread_push: P({ kind: 'game', market: 'spread', team: 'PHI', side: '', line: -7 }),
        total: P({ kind: 'game', market: 'total', side: 'over', line: 249.5 }),
        team_total: P({ kind: 'game', market: 'team_total', team: 'IND', side: 'under', line: 120.5 }),
        keyed: P({ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5, game: 'IND@PHI' }),
        before: pickResult({ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5 },
                           { home: 'PHI', away: 'IND', live: { state: 'live' } }),
      };""")
    if got is None:
        return
    assert got["over_lost"] == {"status": "lost", "actual": 2} and got["under_won"]["status"] == "won"
    assert got["lower_line"]["status"] == "won", "graded at the line the card shows"
    assert got["push"]["status"] == "push", "level is a push (ledger._grade_side_aware)"
    assert got["void"] == {"status": "void"} and got["waiting"] == {"status": "pending"}
    assert got["scorer"]["status"] == "lost", "an anytime scorer needs one"
    assert got["ml"] == {"status": "won", "said": "76ers 131–124"}
    assert got["spread"]["status"] == "won" and got["spread_push"]["status"] == "push"
    assert got["total"] == {"status": "won", "said": "255 scored"}
    assert got["team_total"]["status"] == "lost", "124 is over 120.5"
    assert got["before"] is None, "nothing shows before the final"
    assert got["keyed"] == {"status": "lost", "actual": 2}, \
        "a row naming its game (a first scorer's, a report pick's) is still a player's pick"


def test_the_words_the_tickets_and_the_ribbon():
    got = _node(GAME + """
      const P = (r) => pickResult(r, G);
      const jb = { player: 'Jaylen Brown', market: 'assists', market_label: 'Assists', side: 'Over', line: 2.5 };
      const kcp = { player: 'Kentavious Caldwell-Pope', market: 'rebounds', side: 'Over', line: 1.5 };
      const nes = { player: 'Aaron Nesmith', market: 'threes', side: 'Over', line: 0.5 };
      const sia = { player: 'Pascal Siakam', market: 'assists', side: 'Over', line: 1.5 };
      return {
        words: [pickResultWords(P(jb), jb), pickResultWords(P(kcp), kcp),
                pickResultWords(P({ player: 'Joel Embiid', market: 'anytime_td', side: 'yes' }), { market: 'anytime_td' }),
                pickResultWords(P({ kind: 'game', market: 'moneyline', team: 'PHI' }), {}),
                pickResultWords(P(nes), nes), pickResultWords(P(sia), sia)],
        lost: ticketResult([kcp, jb], G).status, won: ticketResult([kcp], G).status,
        void_leg: ticketResult([kcp, nes], G).status, waiting: ticketResult([kcp, sia], G).status,
        ribbon: (CARD_GAME = G, pickResultHTML(jb)), span: pickResultHTML(kcp, 'span'),
        none: (CARD_GAME = null, state.data.games = [], pickResultHTML(jb)),
      };""")
    if got is None:
        return
    assert got["words"] == ["Lost · 2 assists", "Won · 4 rebounds", "Lost · didn’t score", "Won · 76ers 131–124",
                            "Void — didn’t play", "Final — waiting on the box score"], got["words"]
    assert (got["lost"], got["won"], got["void_leg"], got["waiting"]) == ("lost", "won", "won", "pending")
    assert got["ribbon"] == '<div class="pr-res pr-lost">Lost · 2 assists</div>'
    assert got["span"] == '<span class="pr-res pr-won">Won · 4 rebounds</span>'
    assert got["none"] == "", "a card whose game is not found says nothing"


def test_every_card_that_draws_a_pick_wears_its_result():
    assert APP.count("${pickResultHTML(r)}") == 3 and "${pickResultHTML(r, \"span\")}" in APP
    assert '${pickResultHTML(Object.assign({ kind: "game" }, r))}' in APP, "a game bet, off the score"
    for cls in ("pr-res pr-won", "pr-res pr-lost", "pr-res pr-push", "pr-res pr-void", "pr-res pr-pending"):
        assert f'"{cls}"' in APP, cls
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".pr-won { color: var(--good);" in css and ".pr-lost { color: var(--bad);" in css


def test_the_deck_s_rows_and_the_pick_of_the_day_wear_it_too():
    """The Tonight list and the Pick of the Day draw picks as rows (app.js
    deckPickRow); a finished game's row says how it went. The Pick of the
    Day's row draws a cut-down copy of the pick, so it is graded on the
    whole pick: the copy has no market to find its grade by."""
    body = APP[APP.index("function deckPickRow(r, opts) {"):APP.index("function potdHeroHTML(d) {")]
    assert 'const res = o.result === false ? "" : pickResultHTML(o.result || r, "span");' in body
    assert "${note}${res}</div>" in body
    hero = APP[APP.index("function potdHeroHTML(d) {"):APP.index("function sameTally(a, b) {")]
    assert "model_prob: pick.model_prob }, { result: pick })" in hero
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".hd-what span.pr-res { display: inline-flex;" in css, "a deck row's spans are plain lines otherwise"
    assert ".hd-what .pr-won { color: var(--good); }" in css and ".hd-what .pr-lost { color: var(--bad); }" in css
    got = _node(GAME + """
      CARD_GAME = G;
      const pick = { player: 'Jaylen Brown', market: 'assists', market_label: 'Assists', side: 'Over', line: 2.5,
                     team: 'PHI', opponent: 'IND' };
      const copy = { player: pick.player, side: pick.side, line: pick.line, market_label: pick.market_label,
                     team: pick.team, opponent: pick.opponent };
      return [pickResultHTML(pick, 'span'), pickResultHTML(copy, 'span')];""")
    if got is None:
        return
    assert got[0] == '<span class="pr-res pr-lost">Lost · 2 assists</span>'
    assert "waiting on the box score" in got[1], "the copy alone would wait forever"


def _report(script):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => ({ PHI: '76ers', IND: 'Pacers' })[t] || t, playerAvatar: (p) => '' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;"
            "const st = { lost: { status: 'lost', actual: 2 }, won: { status: 'won', actual: 4 } };"
            "const grade = (b) => st[b.market === 'assists' ? 'lost' : 'won'];"
            "const words = (x) => x.status === 'lost' ? 'Lost · 2 assists' : 'Won · 4 rebounds';"
            "const ticket = (bets) => { const legs = bets.map(grade); return { status: legs.some((x) => x.status === 'lost')"
            " ? 'lost' : 'won', legs }; };"
            "const RES = { final: { home: 131, away: 124 }, home: 'PHI', away: 'IND', grade, words, ticket };")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_report_marks_its_picks_reads_tickets_and_call():
    jb = {"market": "assists", "side": "over", "line": 2.5, "player": "Jaylen Brown", "team": "PHI"}
    kcp = {"market": "rebounds", "side": "over", "line": 1.5, "player": "Kentavious Caldwell-Pope", "team": "PHI"}
    rep = {"game": "IND@PHI", "minutes": 2, "sections": [
        {"key": "verdict", "title": "Who we think wins", "blocks": [
            {"type": "winner", "team": "PHI", "other": "IND", "name": "76ers", "other_name": "Pacers", "chance": 0.62,
             "word": "Favored", "ratings": {"team": "IND", "name": "Pacers", "chance": 0.52, "same": False}}]},
        {"key": "card", "title": "Our picks for this game", "blocks": [
            {"type": "picks", "items": [{"rank": 1, "pick": "Jaylen Brown over 2.5 assists", "bet": jb}]}]},
        {"key": "parlays", "title": "Parlays", "blocks": [
            {"type": "parlays", "kind": "three", "items": [{"title": "Parlay 1", "legs": [
                {"pick": "Kentavious Caldwell-Pope over 1.5 rebounds", "bet": kcp},
                {"pick": "Jaylen Brown over 2.5 assists", "bet": jb}]}]}]},
        {"key": "breakouts", "title": "Breakouts", "blocks": [
            {"type": "verdicts", "items": [{"title": "Jaylen Brown", "player": "Jaylen Brown", "verdict": "up",
                                            "pick": "Most Likely pick: Jaylen Brown over 2.5 assists", "bet": jb}]}]}]}
    got = _report(f"const rep = {json.dumps(rep)}; process.stdout.write(JSON.stringify("
                  "[R.html(rep, { results: RES }), R.html(rep)]));")
    if got is None:
        return
    graded, plain = got
    assert '<div class="gr-res-call won">Right: 76ers won — Pacers 124, 76ers 131 · our ratings alone: wrong</div>' in graded
    assert graded.count('<span class="gr-res lost">Lost · 2 assists</span>') == 3, "the pick, the leg and the read"
    assert '<span class="gr-res won">Won · 4 rebounds</span>' in graded
    assert '<span class="gr-res lost">Ticket lost · 1 of 2 legs hit</span>' in graded
    assert "gr-res" not in plain, "before the final the report is as it was"


def test_the_go_to_scorer_s_read_says_whether_he_scored():
    """A football read's go-to scorer line ("the Lions' likeliest scorer —
    64% to score by our numbers") is a read too: on a finished game it says
    whether he scored, once the record has graded a touchdown on him, and
    nothing until then or when it has none."""
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '**({"scorer_bet": _bet_of({"player": r.get("player"), "team": off,' in gr
    assert '"market": "anytime_td", "side": "yes", "line": None})}' in gr
    bet = GR.bet_of({"player": "Jahmyr Gibbs", "team": "DET", "market": "anytime_td", "side": "yes", "line": None})
    assert bet == {"market": "anytime_td", "side": "yes", "line": None, "player": "Jahmyr Gibbs", "team": "DET"}
    card = {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "verdict": "favorable", "label": "FAVORABLE",
            "title": "Jahmyr Gibbs vs NE's run defense", "role": "", "form": [],
            "why": ["The Lions' likeliest scorer — 64% to score by our numbers.", "Volume up."], "scorer_bet": bet}
    rep = {"game": "NE@DET", "minutes": 1, "sections": [{"key": "matchups", "title": "Matchups", "blocks": [
        {"type": "verdicts", "items": [card]}]}]}
    got = _report(f"""const rep = {json.dumps(rep)};
      const as = (status, actual) => R.html(rep, {{ results: Object.assign({{}}, RES, {{ grade: () => ({{ status, actual }}) }}) }});
      process.stdout.write(JSON.stringify([as('won', 1), as('won', 2), as('lost', 0), as('void'), as('pending'),
                                           R.html(rep, {{}})]));""")
    if got is None:
        return
    one, two, none, void, waiting, before = got
    assert ('64% to score by our numbers. <span class="gr-res won">Scored</span></li>') in one, one[:600]
    assert '<span class="gr-res won">Scored 2</span>' in two
    assert '<span class="gr-res lost">Didn’t score</span>' in none
    assert '<span class="gr-res even">Didn’t play</span>' in void
    assert "gr-res" not in waiting, "no grade yet: no tag, never a wait that may not end"
    assert "gr-res" not in before
    assert "Volume up.</li>" in one and "Volume up. <span" not in one, "on his scorer line only"


def test_report_picks_marks_each_finished_game_s_tickets():
    """Each game's tickets say how they went once it is final, drawn by the
    report's own gameTickets on the Report Picks page (the Parlays page that
    drew them too left every league 2026-11-16)."""
    g = {"home": "PHI", "away": "IND", "threes": [{"joint": 0.31, "independent": 0.29, "legs": [
        {"player": "Kentavious Caldwell-Pope", "team": "PHI", "market": "rebounds", "side": "Over", "line": 1.5}]}],
        "scorers": []}
    got = _report(f"const g = {json.dumps(g)}; process.stdout.write(JSON.stringify("
                  "[R.gameTickets(g, 'nba', { results: (x) => x.home === 'PHI' ? RES : null }), R.gameTickets(g, 'nba')]));")
    if got is None:
        return
    assert '<span class="gr-res won">Ticket won</span>' in got[0] and '<span class="gr-res won">Won · 4 rebounds</span>' in got[0]
    assert "gr-res" not in got[1]
    rp = open(os.path.join(ROOT, "web", "js", "reportpicks.js"), encoding="utf-8").read()
    assert ("R.gameTickets(x.tix, state.sport, { results: () => reportResults(rpGame(d, el.dataset.rpkTix)) })"
            in rp), "Report Picks hands each game's grader to its tickets"


def test_a_finished_game_s_page_opens_on_the_final_and_how_we_did():
    page = DETAIL[DETAIL.index("function renderGamePage() {"):]
    assert page.index("${gpResultsHTML(g, [...likelies, ...shown, ...betsShown, ...shots,") < page.index("${gpJumpHTML([")
    assert "const results = reportResults(g);" in DETAIL and "{ results }" in DETAIL
    fn = DETAIL[DETAIL.index("function gpResultsHTML(g, rows) {"):DETAIL.index("function gameReportHTML(g, extras) {")]
    got = _node(GAME + """
      state.sport = 'nba';
      state.data.game_parlays = { games: [{ home: 'PHI', away: 'IND',
        threes: [{ legs: [{ player: 'Kentavious Caldwell-Pope', market: 'rebounds', side: 'Over', line: 1.5 }] },
                 { legs: [{ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5 }] }], scorers: [] }] };
      const rows = [{ player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5 },
                    { player: 'Jaylen Brown', market: 'assists', side: 'Over', line: 2.5 },
                    { player: 'Kentavious Caldwell-Pope', market: 'rebounds', side: 'Over', line: 1.5 },
                    { player: 'Aaron Nesmith', market: 'threes', side: 'Over', line: 0.5 }];
      return [gpResultsHTML(G, rows), gpResultsHTML({ home: 'PHI', away: 'IND', live: { state: 'live' } }, rows)];""",
                prelude="function gameReportFor(g) { return { sections: [{ key: 'verdict', blocks: [{ type: 'winner', "
                        "team: 'IND', chance: 0.55 }] }] }; }\nconst icon = (n) => `<i class=\"ic-${n}\"></i>`;"
                        "const marketWord = (k) => k;\n" + fn)
    if got is None:
        return
    final, live = got
    # The game page's own score sits right above the card (2026-11-18): the card says what it is for instead.
    assert '<span class="gp-res-k">Final</span><span class="gpr-team">How our report did</span>' in final, final
    assert "Pacers 124" not in final.split("gpr-rows")[0], "the score once, in the page's own header"
    # Each row in its color (GAMEFINAL1): even picks amber, half the tickets amber, a missed call red.
    assert ('<li class="gpr-row gpr-warn"><span class="gpr-mark" aria-hidden="true"><i class="ic-dash"></i></span>\n'
            '    <span class="gpr-k">Our picks</span><span class="gpr-v"><b class="gpr-won">1 won</b> · '
            '<b class="gpr-lost">1 lost</b> · 1 void (didn’t play)</span></li>') in final, final
    assert '<span class="gpr-k">3-leg parlays</span><span class="gpr-v"><b>1 of 2 hit</b></span>' in final, final
    assert ('<li class="gpr-row gpr-bad">' in final and '<span class="gpr-k">Our pick to win</span><span class="gpr-v">'
            '<b>Pacers (55%)</b> — 76ers won 131–124</span>' in final), final
    # The report's one verdict: its pick to win was wrong and it graded no read.
    assert '<div class="gpr-verdict gpr-bad" role="status">' in final and "The report got this game wrong" in final
    assert "he finished" not in final and " his " not in final, "player-neutral copy"
    assert live == "", "nothing before the final"


def test_a_finished_game_s_picks_and_parlays_come_off_the_record_when_the_page_has_none():
    """A game that started before its report was kept (engine/reportkeep) shows no pick and no ticket of its own;
    the record's (engine/reportoutcome, the report's `outcome`) are counted and listed instead (GAMEFINAL1)."""
    fn = DETAIL[DETAIL.index("function gpResultsHTML(g, rows) {"):DETAIL.index("function gameReportHTML(g, extras) {")]
    rep = {"sections": [{"key": "verdict", "blocks": [{"type": "winner", "team": "PHI", "chance": 0.62}]}],
           "graded": {"status": "graded", "right": 5, "graded": 7, "groups": [
               {"key": "matchups", "what": "Matchup reads", "right": 4, "graded": 5, "dnp": 0},
               {"key": "fades", "what": "Fades", "right": 1, "graded": 2, "dnp": 1}],
               "score": {"words": "76ers −3.5, won by 7 (covered); total 224.5, 255 scored (over)"},
               "best_rows": [{"player": "Tyrese Maxey", "label": "a favorable matchup", "words": "31 points; the last 5 games averaged 24."}],
               "worst": ["Pascal Siakam, a fade: 28 points; the last 5 games averaged 21."],
               "injuries": {"words": "the one listed out or doubtful sat", "right": 1, "wrong": 0,
                            "missed": ["Not on our injury report: Andrew Nembhard (Pacers) didn’t play."]}},
           "outcome": {"picks": [{"player": "Tyrese Maxey", "market": "points", "side": "OVER", "line": 22.5,
                                  "status": "won", "actual": 31},
                                 {"player": "PHI", "team": "PHI", "market": "spread", "side": "OVER", "line": 3.5,
                                  "status": "won", "game": True},
                                 {"player": "Pascal Siakam", "market": "points", "side": "UNDER", "line": 20.5,
                                  "status": "lost", "actual": 28}],
                       "tickets": {"threes": [{"status": "won", "legs": [
                           {"player": "Tyrese Maxey", "market": "points", "side": "OVER", "line": 22.5, "status": "won", "actual": 31},
                           {"player": "Joel Embiid", "market": "rebounds", "side": "OVER", "line": 8.5, "status": "won", "actual": 11}]}]}}}
    got = _node(GAME + f"state.sport = 'nba'; return gpResultsHTML(G, []);",
                prelude=f"const REP = {json.dumps(rep)}; function gameReportFor(g) {{ return REP; }}\n"
                        "const icon = (n) => `<i class=\"ic-${n}\"></i>`; const marketWord = (k) => k;\n" + fn)
    if got is None:
        return
    assert '<div class="gpr-verdict gpr-good" role="status">' in got and "The report got this game mostly right" in got
    assert "Picked the winner · 5 of 7 reads right" in got, got
    assert '<b class="gpr-won">2 won</b> · <b class="gpr-lost">1 lost</b>' in got, got
    assert "Tyrese Maxey over 22.5 points <span class=\"gpr-mute\">— had 31</span>" in got, got
    assert "76ers −3.5" in got, "the journal's negated spread is said the bettor's way"
    assert "Pascal Siakam under 20.5 points" in got
    assert '<span class="gpr-k">3-leg parlays</span><span class="gpr-v"><b>1 of 1 hit</b></span>' in got
    assert 'gpr-chip gpr-good">Matchup reads\n      4/5' in got and "· 1 didn’t play" in got
    assert "<b>Tyrese Maxey</b> <span class=\"gpr-mute\">(a favorable matchup)</span> — 31 points" in got
    assert "Pascal Siakam, a fade: 28 points" in got, "a grade archived before the rows still lists its misses"
    assert "Not on our injury report: Andrew Nembhard" in got
    assert '<li class="gpr-row gpr-info">' in got and "76ers −3.5, won by 7 (covered)" in got, "the lines, plain"
    assert "The picks and parlays are from our record" in got


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
