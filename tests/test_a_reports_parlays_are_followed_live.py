"""A game report's parlays are followed while the game is played (20 November 2026).

Ethan, 2026-11-19: "do any other work and ideas you think will help the site in any way", beside "make those
[parlays] better". The Live tab followed the Edge and Most Likely picks and the slips a reader saved; the tickets
every game report builds were followed nowhere once the game kicked off. What these hold:

  * for a game under way, each posted ticket with each leg's number off the live loop's own files, what the leg
    still needs in one plain line, and where the ticket stands: alive with how many legs are in, down to its last
    leg, won, or lost at the first leg that missed (engine/reportlive);
  * a game not started is not followed, a ticket held on paper is not listed, and a finished game's legs settle
    on the final box;
  * every league's leg is read the same way (hockey off the league's own box file);
  * the tickets are a member's: the endpoint answers a reader without the membership with counts and no ticket,
    and the page draws them on the Live tab from the report's own script.

    python3 tests/test_a_reports_parlays_are_followed_live.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import reportlive as RL  # noqa: E402


def _leg(who, team, market, label, side, line, p=0.66, **more):
    return {"player": who, "team": team, "market": market, "market_label": label, "side": side, "line": line,
            "odds": -180, "book": "DraftKings", "p": p, **more}


def _ticket(*legs, joint=0.31):
    return {"legs": list(legs), "joint": joint, "independent": joint, "fair_words": "+223", "take_words": "+236"}


def _fast(d, state="live"):
    base = Path(d)
    (base / "pbp").mkdir(parents=True, exist_ok=True)
    (base / "live_nba.json").write_text(json.dumps({"games": [
        {"event_id": "77", "home": "TOR", "away": "NYK",
         "live": {"state": state, "home_score": 80, "away_score": 78, "period": 3, "clock": "4:12"}},
        {"event_id": "88", "home": "LAL", "away": "BOS", "live": {"state": "scheduled"}}]}))
    (base / "pbp" / "nba_77.json").write_text(json.dumps({"league": "nba", "event_id": "77", "players": [
        {"player": "Jalen Brunson", "team": "NYK", "stats": {"pts": 26, "reb": 2, "ast": 5}},
        {"player": "Scottie Barnes", "team": "TOR", "stats": {"pts": 14, "reb": 9, "ast": 4}},
        {"player": "Karl-Anthony Towns", "team": "NYK", "stats": {"pts": 11, "reb": 7, "ast": 1}}]}))
    (base / "live_nhl.json").write_text(json.dumps({"games": [
        {"event_id": "9", "home": "EDM", "away": "CGY",
         "live": {"state": "live", "home_score": 2, "away_score": 1, "period": 2, "clock": "9:00"}}]}))
    (base / "live_nhl_box.json").write_text(json.dumps({"games": [
        {"home": "EDM", "away": "CGY", "players": [{"player": "Connor McDavid", "team": "EDM",
                                                    "stats": {"sog": 3, "points": 2, "goals": 1}}]}]}))
    return base


NBA = {"game_parlays": {"games": [
    {"away": "NYK", "home": "TOR", "date": "2026-11-19", "kept": "Thu 7:02 PM ET",
     "threes": [_ticket(_leg("Jalen Brunson", "NYK", "pts", "Points", "OVER", 24.5, headshot="https://x/jb.png"),
                        _leg("Scottie Barnes", "TOR", "reb", "Rebounds", "OVER", 10.5),
                        _leg("Karl-Anthony Towns", "NYK", "pts", "Points", "UNDER", 21.5)),
                _ticket(_leg("Jalen Brunson", "NYK", "ast", "Assists", "UNDER", 4.5),
                        _leg("Scottie Barnes", "TOR", "pts", "Points", "OVER", 20.5),
                        _leg("Karl-Anthony Towns", "NYK", "reb", "Rebounds", "OVER", 6.5))],
     "twos": [], "paper_twos": [_ticket(_leg("Jalen Brunson", "NYK", "pts", "Points", "OVER", 24.5),
                                        _leg("Scottie Barnes", "TOR", "pts", "Points", "OVER", 12.5))],
     "scorers": []},
    {"away": "BOS", "home": "LAL", "date": "2026-11-19",
     "threes": [_ticket(_leg("Jayson Tatum", "BOS", "pts", "Points", "OVER", 26.5),
                        _leg("LeBron James", "LAL", "ast", "Assists", "OVER", 7.5),
                        _leg("Jaylen Brown", "BOS", "reb", "Rebounds", "OVER", 5.5))], "twos": [], "scorers": []}]}}
NHL = {"game_parlays": {"games": [
    {"away": "CGY", "home": "EDM", "date": "2026-11-19", "threes": [], "twos": [],
     "scorers": [_ticket(_leg("Connor McDavid", "EDM", "anytime_goal", "Anytime goal", "YES", 0.5),
                         _leg("Nazem Kadri", "CGY", "anytime_goal", "Anytime goal", "YES", 0.5), joint=0.22)]}]}}


def test_a_game_under_way_has_each_ticket_with_each_legs_number_and_what_it_needs():
    with tempfile.TemporaryDirectory() as d:
        games = RL.league("nba", NBA, _fast(d), time.time())
    assert [(g["away"], g["home"]) for g in games] == [("NYK", "TOR")], "the game not started is not followed"
    g = games[0]
    assert (g["state"], g["clock"], g["away_score"], g["home_score"]) == ("live", "Q3 4:12", 78, 80)
    assert [t["title"] for t in g["tickets"]] == ["Parlay 1", "Parlay 2"], "the paper two-leg ticket is not listed"
    one, two = g["tickets"]
    brunson, barnes, towns = one["legs"]
    assert brunson == {"player": "Jalen Brunson", "team": "NYK", "pick": brunson["pick"], "market": "pts",
                       "side": "over", "line": 24.5, "headshot": "https://x/jb.png", "current": 26.0, "result": "won"}
    assert "24.5" in brunson["pick"] and "points" in brunson["pick"].lower()
    assert barnes["current"] == 9.0 and barnes["need"] == "Needs 2 more" and "result" not in barnes
    assert towns["current"] == 11.0 and towns["need"] == "Can give up 10 more"
    assert (one["state"], one["won"], one["left"], one["of"]) == ("alive", 1, 2, 3)
    assert one["words"] == "Alive: 1 of 3 legs in" and one["chance"] == 0.31
    # An under already past its number has lost, whatever the clock says, and the ticket with it.
    assert two["legs"][0]["result"] == "lost" and two["state"] == "lost"
    assert two["words"] == "Lost: Jalen Brunson missed"
    assert two["legs"][2]["result"] == "won", "the other legs still say where they stand"


def test_a_finished_game_settles_on_the_final_box_and_the_last_leg_is_named():
    with tempfile.TemporaryDirectory() as d:
        final = RL.league("nba", NBA, _fast(d, "final"), time.time())[0]
    one = final["tickets"][0]
    assert final["state"] == "final" and final["clock"] == "Final"
    assert [l.get("result") for l in one["legs"]] == ["won", "lost", "won"] and one["state"] == "lost"
    assert all("need" not in l for l in one["legs"]), "nothing is still needed once the game is over"
    legs = lambda *res: [{"player": f"P{i}", "result": r} for i, r in enumerate(res)]   # noqa: E731
    assert RL.standing(legs("won", "won", None))["words"] == "One leg to go: P2"
    assert RL.standing(legs("won", "won", "won")) == {"state": "won", "won": 3, "left": 0, "of": 3,
                                                      "words": "Won: all 3 legs hit"}
    assert RL.standing(legs("won", "won"))["words"] == "Won: both legs hit"
    assert RL.standing(legs("won", "push", "won"))["words"] == "Won: 2 of 3 legs hit, the other pushed"
    assert RL.standing(legs(None, None))["words"] == "Alive: no leg in yet"
    assert RL.standing(legs("push", "push"))["state"] == "push"


def test_the_words_for_what_a_leg_needs():
    need = RL.need_words
    assert need("over", 24.5, 18) == "Needs 7 more" and need("over", 24.5, 25) == "Cleared"
    assert need("over", 6, 6) == "Needs 1 more", "a whole number pushes at the number"
    assert need("under", 21.5, 11) == "Can give up 10 more" and need("under", 21.5, 22) == "Past the number"
    assert need("under", 6, 6) == "On the number: a push now, one more loses"
    assert need("yes", 0.5, 0) == "Needs one" and need("yes", 0.5, 1) == "Done: has one"
    assert need("over", None, 3) == "" and need("over", 2.5, None) == ""
    # The saved slip's leg says the same words on the page (js/slip.js): one wording, two homes.
    slip = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
    for words in ('"Done: has one"', '"Needs one"', '"Cleared"', '"On the number: a push now, one more loses"',
                  '"Past the number"', "`Needs ${num(over - now)} more`", "`Can give up ${num(top - now)} more`"):
        assert words in slip, words


def test_hockey_reads_its_own_box_and_every_league_is_one_snapshot():
    with tempfile.TemporaryDirectory() as d:
        base = _fast(d)
        now = time.time()
        boards = {"nba": NBA, "nhl": NHL, "nfl": {"game_parlays": {"games": []}}, "cfb": None}
        RL.forget()
        doc = RL.snapshot(boards, base, now)
        assert [x["league"] for x in doc["leagues"]] == ["nba", "nhl"], "a league with nothing followed is left out"
        pair = doc["leagues"][1]["games"][0]["tickets"][0]
        assert pair["title"] == "Goal scorer pair 1" and pair["kind"] == "scorers"
        mcdavid, kadri = pair["legs"]
        assert mcdavid["result"] == "won" and mcdavid["line"] == 0.5 and mcdavid["current"] == 1.0
        assert kadri.get("note") == "not in the box score yet" and "result" not in kadri
        assert pair["words"] == "One leg to go: Nazem Kadri"
        assert (doc["live"], doc["tickets"]) == (2, 3)
        # Served from memory for a few seconds (every member's Live tab asks), the boards not loaded again.
        loads = []
        again = lambda: loads.append(1) or boards   # noqa: E731
        assert RL.snapshot(again, base, now + 3) is doc and not loads
        assert RL.snapshot(again, base, now + RL.CACHE_S + 1) is not doc and loads == [1]
        # What a reader without the membership is told: counts, and no ticket.
        assert RL.counts(doc) == {"locked": True, "at": int(now), "live": 2, "games": 2, "tickets": 3}
    # A stopped loop follows nothing, and a board with no parlays is no error.
    with tempfile.TemporaryDirectory() as d:
        assert RL.league("nba", NBA, Path(d), time.time()) == []
    assert RL.league("nba", {}, None, time.time()) == [] and RL.league("nba", {"game_parlays": "x"}, None) == []
    RL.forget()


def test_the_endpoint_is_a_members_and_everyone_else_gets_the_counts():
    import server
    from engine import askbot, gate
    out = {}
    h = object.__new__(server.Handler)
    h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
    h._rate_limited = lambda limit, bucket="read": False
    keep = (askbot.board_at, gate.enabled, gate.board_source, RL.live_state)
    with tempfile.TemporaryDirectory() as d:
        base, now = _fast(d), time.time()
        asked = []
        try:
            RL.live_state = lambda leg, fast_dir=None, t=None: keep[3](leg, base, now)
            askbot.board_at = lambda path: (asked.append(str(path)) or {"nba.json": NBA, "nhl.json": NHL}.get(Path(path).name))
            gate.board_source = lambda path: Path("/private") / Path(path).name
            # The paywall off (a machine with no accounts): the tickets, as every board is.
            gate.enabled = lambda: False
            RL.forget()
            h._report_live()
            assert out["code"] == 200 and out["body"]["tickets"] == 3 and len(out["body"]["leagues"]) == 2
            assert all(a.startswith("/private/") for a in asked) and len(asked) == len(server.LIVE_FILES), \
                "every league's board, from the private copy"
            # The paywall on: a member gets the tickets, anyone else the counts and nothing of a ticket.
            gate.enabled = lambda: True

            class Conn:
                def close(self):
                    pass
            server_acct = server._acct
            server._acct = lambda: type("A", (), {"connect": staticmethod(lambda: Conn())})
            try:
                h._account = lambda conn: {"id": 7}
                h._entitled = lambda conn, who: True
                h._report_live()
                assert out["body"]["leagues"][0]["games"][0]["tickets"][0]["legs"][0]["player"] == "Jalen Brunson"
                h._entitled = lambda conn, who: False
                h._report_live()
                assert out["code"] == 200 and out["body"]["locked"] is True
                assert set(out["body"]) == {"locked", "at", "live", "games", "tickets"} and out["body"]["tickets"] == 3
                assert "Brunson" not in json.dumps(out["body"]), "no ticket, no leg, no name"
            finally:
                server._acct = server_acct
        finally:
            askbot.board_at, gate.enabled, gate.board_source, RL.live_state = keep
            RL.forget()
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/report_live", "/api/report_live/"):' in src
    fn = src[src.index("    def _report_live(self):"):src.index("    def _report_archive(self, q):")]
    assert 'self._rate_limited(RATE_GAME_PER_MIN, "report_live")' in fn
    assert "doc if member else reportlive.counts(doc)" in fn


def test_ask_can_say_whether_a_reports_parlay_is_still_alive():
    from engine import askbot as AB
    keep = RL.live_state
    with tempfile.TemporaryDirectory() as d:
        base, now = _fast(d), time.time()
        RL.live_state = lambda leg, fast_dir=None, t=None: keep(leg, base, now)
        try:
            got = AB.report_parlays_live({"nba": NBA, "nhl": NHL}, "nba")
            live = AB.our_picks_live({"nba": NBA, "nhl": NHL}, "all", data_dir=d)
        finally:
            RL.live_state = keep
    assert [(x["league"], x["game"], x["state"]) for x in got] == [("nba", "NYK @ TOR", "live")]
    assert got[0]["score"] == "NYK 78, TOR 80" and got[0]["clock"] == "Q3 4:12"
    one = got[0]["tickets"][0]
    assert one["ticket"] == "Parlay 1" and one["standing"] == "Alive: 1 of 3 legs in"
    assert one["our_chance_before_the_game"] == 0.31
    assert one["legs"][0] == {"pick": "Jalen Brunson over 24.5 points", "has": 26.0, "result": "won"}
    assert one["legs"][1] == {"pick": "Scottie Barnes over 10.5 rebounds", "has": 9.0, "need": "Needs 2 more"}
    # The live picks tool carries them, every league asked for, and says so to the model.
    assert [x["league"] for x in live["game_report_parlays"]] == ["nba", "nhl"]
    tool = next(t for t in AB.TOOLS if t.get("name") == "our_picks_live")
    assert "the game reports' parlays leg by leg" in tool["description"]
    assert AB.report_parlays_live({"nba": {}}, "nba") == [] and "our_picks_live" in AB.NO_CACHE_TOOLS


def _draw(doc, opts="{}", fn="liveTickets"):
    import shutil
    import subprocess
    node = shutil.which("node") or "/opt/node22/bin/node"
    js = ("const vm = require('vm'); const fs = require('fs');"
          "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, slugify: (s) => s, teamName: (t) => t,"
          " playerAvatar: (n, t, o) => `[face ${n} ${t} ${o.size} ${o.headshot || 'none'}]` }; vm.createContext(ctx);"
          f"vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'web' / 'js' / 'report.js'))}, 'utf8'), ctx);"
          f"process.stdout.write(ctx.window.QBReport.{fn}({json.dumps(doc)}, {opts}));")
    got = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-1500:]
    return " ".join(got.stdout.split())


def test_the_live_tab_draws_each_game_ticket_and_leg():
    with tempfile.TemporaryDirectory() as d:
        RL.forget()
        doc = RL.snapshot({"nba": NBA, "nhl": NHL}, _fast(d), time.time())
        RL.forget()
    html = _draw(doc)
    assert html.startswith('<div class="grl"><div class="section-title">Our report parlays, live')
    assert '<p class="grl-tally">2 alive · 1 lost</p>' in html
    assert ('<div class="card grl-game live"> <div class="grl-game-h"><b>NYK 78 – 80 TOR</b>'
            '<span class="grl-clock live">Q3 4:12</span><span class="grl-lg">NBA</span></div>') in html
    one, two = html.split('<div class="grl-t s-')[1:3]
    assert one.startswith('alive"> <div class="grl-t-h"><b>Parlay 1</b><span class="grl-dots" aria-hidden="true">'
                          '<i class="won"></i><i></i><i></i></span> <span class="grl-t-st">Alive: 1 of 3 legs in</span>')
    # A leg: the face and the name, the pick's own words, where it stands, the number so far against its line.
    assert ('<li class="grl-leg r-won"> <div class="grl-leg-h"><span class="gr-parlay-who"><span class="gr-parlay-face">'
            '[face Jalen Brunson NYK 24 https://x/jb.png]</span><b>Jalen Brunson</b></span>'
            '<span class="grl-pick">over 24.5 points</span><span class="grl-chip won">In</span></div>') in one
    assert 'Has <b data-tick="rl:nba|NYK@TOR|three0|0" data-tick-v="26">26</b> of 24.5</span>' in one
    assert '<i style="width:100%"></i>' in one, "past its number, the bar is full and no more"
    # Still live: what it needs, at the end of its number's row, beside the bar.
    assert '<i style="width:86%"></i></span><span class="grl-need">Needs 2 more</span></div>' in one
    # An under's number climbing is bad news: its tick is inverted, its row says under.
    assert '<li class="grl-leg under">' in one and 'data-tick-v="11" data-tick-mode="invert">11</b> of 21.5' in one
    assert '<span class="grl-need">Can give up 10 more</span>' in one
    assert two.startswith('lost">') and '<span class="grl-t-st">Lost: Jalen Brunson missed</span>' in two
    assert '<span class="grl-chip lost">Missed</span>' in two
    # A scorer's leg has no "of 0.5" and no bar; a player not in the box yet says so.
    pair = html.split('<div class="grl-t s-')[3]
    assert "<b>Goal scorer pair 1</b>" in pair and 'data-tick-v="1">1</b></span></div>' in pair
    assert '<div class="grl-leg-m"><span class="grl-need quiet">not in the box score yet</span></div>' in pair
    assert "of 0.5" not in pair
    for bad in ("undefined", "NaN", "[object", "null"):
        assert bad not in html, bad


def test_a_locked_reader_a_saved_game_and_a_quiet_night():
    with tempfile.TemporaryDirectory() as d:
        RL.forget()
        doc = RL.snapshot({"nba": NBA}, _fast(d), time.time())
        RL.forget()
    # A reader without the membership: the report's script draws nothing (it is never loaded for them); the
    # page's own lock card says how many are followed (app.js reportLiveLockHTML).
    assert _draw(RL.counts(doc)) == ""
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    lock = app[app.index("function reportLiveLockHTML(doc) {"):app.index("function reportLiveGameHTML(")]
    assert 'memberLockHTML(`${n("tickets", "ticket")} being followed in ${n("games", "game")}`' in lock
    assert "The reports and their picks are part of the subscription." in lock
    ask = app[app.index("async function reportLiveAsk() {"):app.index("function reportLiveLockHTML(doc) {")]
    assert "if (doc.tickets > 0 && !doc.locked) await loadReport();" in ask, "no report script for a locked reader"
    assert "doc.locked ? 4 * RL_MS : RL_MS" in ask, "a count is asked for a quarter as often"
    draw = app[app.index("function reportLiveDraw() {"):app.index("function reportLiveSlot(")]
    assert ": doc.locked ? reportLiveLockHTML(doc)" in draw
    # A game saved for later keeps its score and its tickets to itself.
    veiled = _draw(doc, "{ spoiled: (league, g) => league === 'nba' && g.home === 'TOR' }")
    assert "<b>NYK at TOR</b>" in veiled and "Spoiler-free" in veiled and "78" not in veiled
    assert "You saved this game for later" in veiled and "grl-t s-" not in veiled
    # Nothing followed: nothing drawn, not an empty heading.
    assert _draw({"at": 1, "leagues": [], "live": 0, "tickets": 0}) == "" and _draw({}) == ""


def test_the_page_asks_on_the_live_tab_and_only_loads_the_report_script_for_a_ticket():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fn = app[app.index("async function reportLiveAsk() {"):]
    fn = fn[:fn.index("\n}\n") + 3]
    assert 'fetch("/api/report_live", { credentials: "same-origin" })' in fn
    assert "if (doc.tickets > 0 && !doc.locked) await loadReport();" in fn, "no ticket, no script"
    assert "if (doc.live > 0) _rl.timer = setTimeout(reportLiveAsk, doc.locked ? 4 * RL_MS : RL_MS);" in fn
    assert 'state.view !== "live" && state.view !== "pbp"' in fn and "document.hidden" in fn
    draw = app[app.index("function reportLiveDraw() {"):app.index("function reportLiveSlot(")]
    assert "if (html !== _rl.html) h.innerHTML = _rl.html = html;" in draw, "a draw that changes nothing changes nothing"
    assert "if (el._rlHtml === html) return;" in draw
    board = app[app.index("async function renderLiveBoard() {"):]
    assert "liveSlips();\n  reportLiveAsk();" in board[:600]
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert html.index('<div id="live-board"></div>') < html.index('<div id="live-report"></div>') < html.index('<div id="live-slips"></div>')
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    for rule in (".grl-t.s-won { --tone: var(--good); }", ".grl-t.s-lost { --tone: var(--bad); }",
                 "@media (prefers-reduced-motion: reduce) { .grl-prog i { transition: none; } }"):
        assert rule in css, rule


def test_a_live_games_own_page_carries_its_tickets_in_every_sport():
    """The picks rail every sport's live page draws (the one page's Our picks tab and side list, and the
    ballpark's own tab: app.js pbpPropsHTML) ends in a slot for the game's own tickets, filled from the same read."""
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    rail = app[app.index("function pbpPropsHTML(d, league) {"):app.index("function openPbp(")]
    assert "const tickets = reportLiveSlot(d, league);" in rail
    assert rail.count("${tickets}") == 3, "with picks, with none, and on another league's board"
    assert rail.index("if (isWalled())") < rail.index("reportLiveSlot(d, league)"), "a member's, like the picks over it"
    slot = app[app.index("function reportLiveSlot(d, league) {"):app.index("/* A SLIP SHARED IN (2026-10-24)")]
    assert 'data-rl="${escapeAttr(`${league}|${d.away}|${d.home}`)}"' in slot and "reportLiveAsk();" in slot
    # Every sport's page but baseball's is the one page since 21 November 2026 (detail.js gpPageHTML): its Our
    # picks tab and the list beside its plays draw the rail, and so does baseball's own tab. The sport files
    # bring their parts to that page and draw no rail of their own.
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    for fn in ("gpPicksHTML", "gpRailPicksHTML"):
        body = det[det.index(f"function {fn}("):]
        assert "pbpPropsHTML(d, league)" in body[:body.index("\n}\n")], fn
    assert 'tab === "props" ? pbpPropsHTML(d, league)' in det, "baseball's tab"
    for page in ("gamecast.js", "hoopscast.js", "rinkcast.js"):
        assert "pbpPropsHTML(" not in (ROOT / "web" / "js" / page).read_text(encoding="utf-8"), page
    with tempfile.TemporaryDirectory() as d:
        RL.forget()
        doc = RL.snapshot({"nba": NBA, "nhl": NHL}, _fast(d), time.time())
        RL.forget()
    one = _draw(doc, '"nba", "NYK", "TOR"', fn="liveGame")
    assert one.startswith('<div class="pbp-picks-head">Our report parlays<span class="mini">2</span></div> '
                          '<div class="grl grl-rail"><div class="grl-t s-alive">')
    assert "grl-game-h" not in one, "the page has the score already"
    assert "Lost: Jalen Brunson missed" in one and "Goal scorer pair" not in one, "this game's, no other's"
    assert _draw(doc, '"nba", "BOS", "LAL"', fn="liveGame") == "" and _draw({"locked": True, "tickets": 3}, '"nba", "NYK", "TOR"', fn="liveGame") == ""


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
