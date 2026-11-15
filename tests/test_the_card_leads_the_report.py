"""Our picks for the game lead the report, the way the research answered (2026-11-15).

Ethan: "you should be learning from all those reports ... the catches over
picks hit 83%, all picks hit 67% ... it's just so much more easier to go do
my own research than go looking at our app. And the point of our app is to
not have me go do the research because it's already done for me on the
app." His research chats answered a game with a card: the picks best to
worst, each with its book and price, the modeled hit rate, the fair price
and the most to pay, how often the player cleared the number, the matchup
and role behind it, then the parlay. The report (engine/gamereport.sec_card)
now opens on that card, built from the board's posted picks for the game,
with how each kind of pick has hit twice: on our board, and in the
hand-researched picks (engine/researchrecord).

    python3 tests/test_the_card_leads_the_report.py
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamereport as GR, researchrecord as RR  # noqa: E402

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
REPORT_CSS = os.path.join(ROOT, "web", "css", "report.css")


def _row(player, team, opp, market, label, side, line, prob, tier, book="DraftKings", odds=-150, **kw):
    return {"kind": "prop", "player": player, "team": team, "opponent": opp, "market": market,
            "market_label": label, "side": side, "line": line, "model_prob": prob, "tier": tier,
            "tier_label": {"top": "Top pick", "strong": "Strong", "look": "Worth a look"}[tier],
            "book": book, "odds": odds, **kw}


def _result(rows=None, held=None):
    g = {"home": "DET", "away": "GB", "date": "2099-10-25", "kickoff": "13:00", "spread": -2.5,
         "total": 47.5, "scan": {}}
    if rows is None:
        rows = [
            _row("Tucker Kraft", "GB", "DET", "receptions", "Receptions", "OVER", 3.5, 0.78, "top", odds=-190,
                 record_seen={"n": 412, "need": 40, "rate": 0.66, "claimed": 0.65}),
            _row("Bijan Robinson", "ATL", "SF", "rush_yds", "Rushing Yards", "OVER", 70.5, 0.80, "top"),
            _row("Jordan Love", "GB", "DET", "pass_cmp", "Pass Completions", "OVER", 21.5, 0.64, "strong",
                 book="FanDuel", odds=-110, record_seen={"n": 12, "need": 40}),
            _row("Tucker Kraft", "GB", "DET", "rec_yds", "Receiving Yards", "OVER", 30.5, 0.70, "strong"),
            {"kind": "game", "player": "DET ML", "team": "DET", "opponent": "GB", "home": "DET", "away": "GB",
             "market": "moneyline", "market_label": "Moneyline", "side": "DET", "line": None,
             "model_prob": 0.61, "tier": "look", "tier_label": "Worth a look", "book": "FanDuel", "odds": -140},
            _row("Jahmyr Gibbs", "DET", "GB", "anytime_td", "Anytime TD", "Yes", 0.5, 0.58, "look", odds=-150,
                 method_note="Worth a look, not higher — a back on a team the line has trailing"),
            _row("Sam LaPorta", "DET", "GB", "receptions", "Receptions", "OVER", 2.5, 0.57, "look"),
        ]
    reads = [{"player": "Tucker Kraft", "team": "GB", "pos": "TE", "read": "good",
              "pro": ["Detroit gives up the 4th-most catches to tight ends"], "con": [],
              "usage": {"tgt_share": 0.22, "targets_pg": 6.1}},
             {"player": "Jordan Love", "team": "GB", "pos": "QB", "read": "tough",
              "pro": [], "con": ["Detroit's pressure"], "usage": {"attempts_pg": 34.2}}]
    result = {"games": [g], "likely_board": {"rows": rows, "held": held or []},
              "scan_reads": {"GB@DET": {"players": reads}}}
    form = {"Tucker Kraft": {"log": [
        {"wk": 9, "opp": "CAR", "s": {"receptions": 6, "rec_yds": 48}},
        {"wk": 8, "opp": "PIT", "s": {"receptions": 5, "rec_yds": 40}},
        {"wk": 7, "opp": "ARI", "s": {"receptions": 4, "rec_yds": 33}},
        {"wk": 6, "opp": "CIN", "s": {"receptions": 3, "rec_yds": 21}},
        {"wk": 5, "opp": "DAL", "s": {"receptions": 7, "rec_yds": 70}},
        {"wk": 4, "opp": "CLE", "s": {"receptions": 5, "rec_yds": 52}}]}}
    return g, result, form


def _report(rows=None, held=None):
    g, result, form = _result(rows, held)
    return GR.build(g, result, sport="nfl", form=form, names={"GB": "Packers", "DET": "Lions"})


def _card(rep):
    return next((s for s in rep["sections"] if s["key"] == "card"), None)


def test_the_card_comes_first_and_ranks_the_games_posted_picks():
    rep = _report()
    keys = [s["key"] for s in rep["sections"]]
    assert keys[:2] == ["card", "short"], keys
    sec = _card(rep)
    assert sec["title"] == "Our picks for this game"
    items = sec["blocks"][0]["items"]
    assert [x["rank"] for x in items] == [1, 2, 3, 4]
    picks = [x["pick"] for x in items]
    # The board's order, one pick a player, this game's only, at most four.
    assert picks == ["Tucker Kraft over 3.5 receptions", "Jordan Love over 21.5 pass completions", "DET ML",
                     "Jahmyr Gibbs to score a touchdown"], picks
    assert not any("Bijan" in p or "LaPorta" in p for p in picks)


def test_each_pick_carries_what_the_research_carried():
    items = _card(_report())["blocks"][0]["items"]
    kraft, love, ml, gibbs = items
    assert kraft["price"] == "DraftKings −190" and kraft["tier"] == "Top pick"
    # 78% is −355 fair; the project's gate is −250, so that is the most to pay.
    assert kraft["numbers"] == "Our chance 78% · fair −355 · play to −250", kraft["numbers"]
    assert love["numbers"] == "Our chance 64% · fair −178 · play to −178", love["numbers"]
    assert kraft["form"] == "Over 3.5 in 5 of 6 games this season, 4 of the last 5 (last 5: 6, 5, 4, 3, 7)", kraft["form"]
    # The read's reason, in the report's plain words ("4th-most" said aloud).
    assert kraft["why"][0] == "Detroit gives up the fourth-most catches to tight ends", kraft["why"]
    assert any(w.startswith("His work: 22% of the targets") for w in kraft["why"]), kraft["why"]
    assert kraft["kind"] == ("Receptions overs: 66% of 412 on our board at this chance (we said 65%); "
                             "25 of 30 in our hand-researched picks"), kraft["kind"]
    # A tough read is not a reason for an over: Love's "con" is never one of
    # his reasons. It is said once, last, as the main way the pick loses
    # (2026-11-15, the research's final card).
    assert not any("pressure" in w for w in love["why"][:-1]), love["why"]
    assert love["why"][-1] == "The main way it loses: Detroit's pressure", love["why"]
    assert love["kind"] == ("Pass completions overs: 12 settled on our board at this chance, too few to say; "
                            "5 of 5 in our hand-researched picks"), love["kind"]
    assert ml["player"] == "" and ml["form"] == "" and ml["price"] == "FanDuel −140"
    assert gibbs["why"][-1].startswith("Worth a look, not higher"), gibbs["why"]
    # No board record on the pick, the research's own on touchdowns.
    assert gibbs["kind"] == "Touchdown picks: 39 of 71 in our hand-researched picks", gibbs["kind"]
    assert ml["kind"] == "", "no record either way: nothing said"


def test_a_game_with_nothing_posted_names_the_closest_and_what_holds_them():
    held = [_row("Tucker Kraft", "GB", "DET", "receptions", "Receptions", "OVER", 3.5, 0.53, "look",
                 held_note="held back: a prop under 60% on the tightened NFL board"),
            _row("Jordan Love", "GB", "DET", "pass_cmp", "Pass Completions", "OVER", 21.5, 0.52, "look",
                 held_note="on paper, not posted: picks of this kind ran hot — our rule records them"
                           " without posting them until 30 run honest")]
    for h in held:
        h["tier"] = "held"
    sec = _card(_report(rows=[], held=held))
    text = json.dumps(sec, ensure_ascii=False)
    assert sec["blocks"][0] == {"type": "p", "text": "No pick on this game clears our bars at the current lines."}
    items = next(b for b in sec["blocks"] if b["type"] == "list")["items"]
    assert items[0] == "Tucker Kraft over 3.5 receptions (53%): a prop under 60% on the tightened NFL board.", items
    assert "on paper, not posted" in items[1], items
    assert "picks" not in [b["type"] for b in sec["blocks"]], text
    # Nothing on the game at all: no card, the short version leads.
    rep = _report(rows=[], held=[])
    assert _card(rep) is None and rep["sections"][0]["key"] == "short"


def test_the_copied_report_carries_the_card():
    text = GR.to_text(_report())
    assert "OUR PICKS FOR THIS GAME" in text
    assert "  1. Tucker Kraft over 3.5 receptions — DraftKings −190 [Top pick]" in text, text[:1500]
    assert "      Our chance 78% · fair −355 · play to −250" in text
    assert text.index("OUR PICKS FOR THIS GAME") < text.index("THE SHORT VERSION")


def test_the_research_record_is_the_graded_chats():
    assert RR.line("nfl", "receptions", "Over") == "25 of 30 in our hand-researched picks"
    assert RR.line("nfl", "anytime_td", "Yes") == "39 of 71 in our hand-researched picks"
    assert RR.record("nfl", "pass_att", "UNDER") is None, "one graded leg says nothing"
    assert RR.record("nba", "points", "OVER") is None, "the spring's chats are not graded here"
    won = sum(w for w, n in RR.NFL.values())
    graded = sum(n for w, n in RR.NFL.values())
    # The five legs the table has no market for (team touchdowns and totals,
    # the game's touchdowns) all won: 112 of 166, the 67% Ethan quoted.
    assert (RR.NFL_ALL[0] - won, RR.NFL_ALL[1] - graded) == (5, 5)
    assert round(RR.NFL_ALL[0] / RR.NFL_ALL[1], 2) == 0.67
    assert round(25 / 30, 2) == 0.83


def test_the_page_draws_the_card_open_above_the_folds():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no Node)")
        return
    rep = _report()
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => t, playerAvatar: (p) => '' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;"
            f"const rep = {json.dumps(rep, ensure_ascii=False)};"
            "process.stdout.write(JSON.stringify({html: R.html(rep, {}), text: R.to_text ? R.to_text(rep) : ''}));")
    out = subprocess.run([node, "-e", head], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout)
    html = got["html"]
    assert '<section class="gr-sec" id="gr-card"><h3 class="gr-title">Our picks for this game</h3>' in html
    assert '<section class="gr-sec" id="gr-short">' in html, "the short version still reads open"
    assert html.index('id="gr-card"') < html.index('id="gr-short"')
    assert '<ol class="gr-picks">' in html and 'data-open="player:tucker-kraft"' in html
    assert '<p class="gr-pick-num">Our chance 78% · fair −355 · play to −250</p>' in html
    assert '<span class="gr-pick-tier">Top pick</span>' in html
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in html, bad
    css = open(REPORT_CSS, encoding="utf-8").read()
    rule = css[css.index(".gr-pick {"):css.index("}", css.index(".gr-pick {"))]
    assert "border:" not in rule and "outline" not in rule, "the site draws no hard lines"


def test_the_heartbeat_counts_the_reports_that_open_on_picks():
    """The reports are a paid key, stripped from the public copy: the
    heartbeat is where a live check sees the cards (launch._board_counts)."""
    import tempfile
    import launch as L
    with_picks, none = _report(), _report(rows=[], held=[dict(_row(
        "Tucker Kraft", "GB", "DET", "receptions", "Receptions", "OVER", 3.5, 0.53, "look"),
        tier="held", held_note="held back: under the bar")])
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_reports": [with_picks, none, _report(rows=[], held=[])]}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["reports"], got["cards"], got["cards_none"]) == (3, 1, 1), got


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
