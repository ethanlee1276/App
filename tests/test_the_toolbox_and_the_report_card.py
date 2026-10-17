"""The Toolbox (calculators, the college upset meter) and My Bets' report card.

Ethan, 2026-10-15, of sixteen brainstormed features: "do every one for
every sport. i want every feature and idea u listed done and finished and
pushed to the site." This is the first slice: the calculators every sport
shares, college football's upset meter, and the report card that reads a
reader's own log back to them — plus the one server half, our close on a
logged bet that matches a settled pick of ours.

What these hold: the arithmetic is right; the meter shows the board's own
published chance and never a sharp book's; the report card grades wins
against the prices taken, not against a coin, and says when a run is
still inside luck; the close lookup answers only from settled picks and
only when exactly one pick fits; and the page reaches all of it.

Run directly: `python3 tests/test_the_toolbox_and_the_report_card.py`
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, reportcard                            # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _node(body: str):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx);"
              "const X = ctx.window.QBExtras;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_odds_arithmetic():
    got = _node("process.stdout.write(JSON.stringify({"
                "d: [X.dec(-110), X.dec('+150'), X.dec('−200'), X.dec(50), X.dec('')],"
                "am: [X.toAm(0.6), X.toAm(0.25), X.decToAm(2.5), X.decToAm(1.5)],"
                "v: X.noVig([-110, -110]), three: X.noVig([150, 220, 240]), bad: X.noVig([-110]),"
                "p: X.parlay([{odds: -110}, {odds: -110, p: 0.6}]), p2: X.parlay([{odds: -110, p: 0.55}, {odds: 120, p: 0.5}]),"
                "k: X.kelly(0.55, -110, 0.25, 1000), k0: X.kelly(0.45, -110, 1, 1000)}));")
    if got is None:
        return
    assert abs(got["d"][0] - (1 + 100 / 110)) < 1e-9 and got["d"][1] == 2.5 and got["d"][2] == 1.5
    assert got["d"][3] is None and got["d"][4] is None
    assert got["am"] == [-150, 300, 150, -200]
    v = got["v"]
    assert abs(v["hold"] - (1 - 1 / (2 * 110 / 210))) < 1e-9 and v["mult"] == [0.5, 0.5]
    t = got["three"]
    assert abs(sum(t["mult"]) - 1) < 1e-9 and abs(sum(t["power"]) - 1) < 1e-6
    assert t["power"][0] > t["mult"][0], "power leans the hold onto the long sides"
    assert got["bad"] is None
    assert got["p"]["legs"] == 2 and got["p"]["american"] == 264 and got["p"]["mine"] is None
    assert abs(got["p2"]["mine"] - 0.275) < 1e-9 and got["p2"]["ev"] is not None
    k = got["k"]
    assert abs(k["full"] - 0.055) < 1e-9 and abs(k["stake"] - 0.01375) < 1e-9 and abs(k["dollars"] - 13.75) < 1e-6
    assert got["k0"]["full"] < 0 and got["k0"]["stake"] == 0


def test_the_middle_finder():
    """Ethan, 2026-10-17: "invent new tools". Over 44.5 at one book and
    under 47.5 at another: the stakes balance either single win, the
    outside costs the two holds, between them wins both. A counted stat
    pushes on a whole-number line; a gap the wrong way loses both; prices
    generous enough lock a profit (an arbitrage)."""
    got = _node("""process.stdout.write(JSON.stringify({
      a: X.middle({overLine: 44.5, overOdds: -110, underLine: 47.5, underOdds: -110, mean: 46, sd: 13, stake: 200}),
      c: X.middle({overLine: 6, overOdds: -110, underLine: 8, underOdds: -110, mean: 7, sd: 1.5, counted: true, stake: 200}),
      r: X.middle({overLine: 48.5, overOdds: -110, underLine: 45.5, underOdds: -110}),
      arb: X.middle({overLine: 44.5, overOdds: 110, underLine: 44.5, underOdds: 105}),
      bad: X.middle({overLine: 'x', overOdds: -110, underLine: 47.5, underOdds: -110})}));""")
    if got is None:
        return
    a = got["a"]
    assert abs(a["stakes"][0] - 100) < 1e-9 and abs(a["stakes"][1] - 100) < 1e-9
    assert abs(a["outside"] - (100 * (1 + 100 / 110) - 200)) < 1e-9 and a["both"] > 180
    assert 0.08 < a["pMiddle"] < 0.10 and a["ev"] > 0 and abs(a["breakeven"] - (-a["outside"]) / (a["outside"] + 200)) < 1e-9
    c = got["c"]
    assert c["pPush"] > 0.3, "a whole-number line pushes that bet on the number"
    assert 0.2 < c["pMiddle"] < 0.3, "only 7 lands strictly between 6 and 8"
    assert got["r"]["reverse"] and got["r"]["pMiddle"] == 0 and got["r"]["ev"] < got["a"]["ev"]
    assert got["arb"]["arb"] and got["arb"]["outside"] > 0
    assert got["bad"] is None


def test_the_bankroll_simulator():
    got = _node("""process.stdout.write(JSON.stringify({
      edge: X.bankrollSim({bankroll: 1000, bets: 400, price: -110, hit: 0.56, rule: 'pct', size: 2, paths: 800, seed: 3}),
      again: X.bankrollSim({bankroll: 1000, bets: 400, price: -110, hit: 0.56, rule: 'pct', size: 2, paths: 800, seed: 3}),
      none: X.bankrollSim({bankroll: 1000, bets: 400, price: -110, hit: 0.5, rule: 'flat', size: 100, paths: 800}),
      kelly: X.bankrollSim({bankroll: 1000, bets: 400, price: -110, hit: 0.45, rule: 'kelly', size: 0.25, paths: 300}),
      bad: X.bankrollSim({bankroll: 1000, bets: 400, price: -110, hit: 0})}));""")
    if got is None:
        return
    e = got["edge"]
    assert e["median"] > 1000 and e["upChance"] > 0.6 and e["p10"] < e["median"] < e["p90"]
    assert e == got["again"], "the same seed reads the same"
    assert len(e["band"]) == 20 and e["band"][-1]["bet"] == 400
    n = got["none"]
    assert n["ev"] < 0 and n["ruinChance"] > 0.5, "flat $100 on $1,000 with no edge ruins most runs"
    k = got["kelly"]
    assert k["kelly"] == 0 and k["median"] == 1000, "Kelly with no edge stakes nothing"
    assert got["bad"] is None


def test_the_slate_sizer_bets_less_on_bets_that_lose_together():
    """Two 56% bets at -110 from one game, one from another. Alone each
    earns Kelly's 7.6%; together the same-game pair earns less, the
    unrelated one about its own, and the answer is exact — identical bets
    get identical stakes, and every way the slate can land is counted."""
    got = _node("""process.stdout.write(JSON.stringify({
      k: X.slateKelly([{p: 0.56, odds: -110, group: 'A'}, {p: 0.56, odds: -110, group: 'a'}, {p: 0.56, odds: -110}], {rho: 0.5}),
      ind: X.slateKelly([{p: 0.56, odds: -110}, {p: 0.56, odds: -110}], {rho: 0.5}),
      one: X.slateKelly([{p: 0.56, odds: -110}]),
      pats: X.slatePatterns([{p: 0.6, g: 'A'}, {p: 0.6, g: 'A'}], 0.5).map((x) => x.p),
      none: X.slateKelly([{p: 0.4, odds: -110}])}));""")
    if got is None:
        return
    k = got["k"]
    alone = (0.56 * (1 + 100 / 110) - 1) / (100 / 110)
    assert abs(k["alone"][0] - alone) < 1e-9
    assert abs(k["joint"][0] - k["joint"][1]) < 1e-6, "identical bets, identical stakes"
    assert k["joint"][0] < alone - 0.01, "the same-game pair earns less together"
    assert k["joint"][2] > k["joint"][0] + 0.005, "the unrelated bet keeps more"
    assert k["allLose"] > k["indepLose"] + 0.01
    assert k["patterns"] == 8 and abs(k["stake"][0] - 0.25 * k["joint"][0]) < 1e-12
    assert abs(got["one"]["joint"][0] - got["one"]["alone"][0]) < 1e-6, "one bet alone is plain Kelly"
    assert abs(got["ind"]["joint"][0] - got["ind"]["joint"][1]) < 1e-6
    assert abs(sum(got["pats"]) - 1) < 1e-9 and got["pats"][3] > 0.36 + 0.03, "a shared draw: both win more often"
    assert got["none"]["joint"][0] == 0, "no edge, no stake"


def test_the_strategy_lab_reads_the_headline_record_compactly():
    """ledger.lab_rows: the headline record's settled, staked rows, oldest
    first, each saying which half of the record it is, nothing a record
    page does not already show; a benched league and a row before the
    epoch stay out; the server hands it out ungated and cached."""
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    rows = [("2026-09-01", "nfl", "rec_yds", "OVER", -110, 0.61, "won", 0.91, 1.0, "main"),
            ("2026-09-02", "cfb", "spread", "OVER", 105, 0.55, "lost", -1.0, 1.0, "likely"),
            ("2026-09-03", "wnba", "pts", "UNDER", -115, 0.6, "won", 0.87, 1.0, "main"),
            ("2026-07-01", "nfl", "rec_yds", "OVER", -110, 0.6, "won", 0.91, 1.0, "main"),
            ("2026-09-04", "nfl", "rec_yds", "OVER", -110, 0.6, "open", 0.0, 1.0, "main")]
    for d, sp, mk, sd, o, hp, st, u, su, cat in rows:
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, status, "
                  "pnl_units, stake_units, stake_dollars, category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                  (f"{d}T12:00:00", sp, d, d, "P", mk, sd, 1.5, o, hp, st, u, su, cat))
    L.commit()
    got = ledger.lab_rows(L)
    cols = got["cols"]
    assert cols == ["day", "sport", "kind", "market", "side", "odds", "claimed", "result", "units", "staked", "book"]
    assert [r[cols.index("sport")] for r in got["rows"]] == ["nfl", "cfb"], got["rows"]
    first, second = got["rows"]
    assert first[cols.index("kind")] == "prop" and second[cols.index("kind")] == "line"
    assert first[cols.index("book")] == "edge" and second[cols.index("book")] == "likely"
    assert first[cols.index("result")] == "w" and second[cols.index("result")] == "l"
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/record/lab", "/api/record/lab/"):' in src
    i = src.index("def _record_lab(self):")
    assert "_LAB_CACHE" in src[i:i + 1600] and "L.lab_rows(conn)" in src[i:i + 1600]


def test_the_strategy_lab_says_how_much_luck_explains():
    got = _node("""
      const cols = ['day','sport','kind','market','side','odds','claimed','result','units','staked','book'];
      let s = 7; const r = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
      const mk = (hit, n) => { const out = []; for (let i = 0; i < n; i++) { const w = r() < hit;
        out.push(['2026-09-' + String(1 + i % 28).padStart(2, '0'), i % 3 ? 'nfl' : 'cfb', 'prop', 'rec_yds',
                  i % 2 ? 'OVER' : 'UNDER', -110, 0.6, w ? 'w' : 'l', w ? 100 / 110 : -1, 1, 'edge']); } return out; };
      const good = mk(0.62, 600), coin = mk(0.5, 600);
      process.stdout.write(JSON.stringify({
        good: X.labStats(good, cols), coin: X.labStats(coin, cols), again: X.labStats(good, cols),
        unders: X.labFilter(good, cols, {side: 'under'}).length, cfb: X.labFilter(good, cols, {sport: 'cfb'}).length,
        shorter: X.labFilter(good, cols, {minOdds: '-105'}).length, chance: X.labFilter(good, cols, {minChance: 65}).length,
        none: X.labStats([], cols)}));""")
    if got is None:
        return
    g, c = got["good"], got["coin"]
    assert g["roi"] > 0.08 and g["luck"] < 0.01, "62% at -110 over 600 bets: luck rarely does that"
    assert c["luck"] > 0.5, "a coin at -110 is what luck does"
    assert g["lo"] < g["roi"] < g["hi"] and g["drawdown"] > 0
    assert g == got["again"], "the luck check is seeded"
    assert got["unders"] == 300 and got["cfb"] == 200 and got["shorter"] == 0 and got["chance"] == 0
    assert got["none"] is None


def test_every_calculator_draws_its_numbers():
    """Each card's inputs, read the way the page reads them, give text."""
    got = _node("""
      const box = (vals) => ({ dataset: {}, querySelector: (s) => { const k = s.match(/"(.+)"/)[1]; return k in vals ? { value: vals[k] } : null; } });
      process.stdout.write(JSON.stringify({
        conv: [X.CALC.conv(box({'conv-in': '-110'})), X.CALC.conv(box({'conv-in': '2.50'})), X.CALC.conv(box({'conv-in': '40%'})), X.CALC.conv(box({'conv-in': 'abc'}))],
        vig: X.CALC.vig(box({'vig-1': '-115', 'vig-2': '-105', 'vig-3': '', 'vig-4': ''})),
        parlay: X.CALC.parlay(box({'pl-o1': '-110', 'pl-o2': '+120', 'pl-p1': '', 'pl-p2': ''})),
        kelly: X.CALC.kelly(box({'ky-p': '45', 'ky-o': '-110', 'ky-f': '0.25', 'ky-r': '1000'})),
        ev: X.CALC.ev(box({'ev-o': '+150', 'ev-p': '42', 'ev-s': '100'}))}));""")
    if got is None:
        return
    conv = got["conv"]
    assert "−110" in conv[0] and "1.909" in conv[0] and "52.4%" in conv[0]
    assert "+150" in conv[1] and "40.0%" in conv[1]
    assert "+150" in conv[2], conv[2]
    assert "Type an American price" in conv[3]
    assert "Book’s hold" in got["vig"] and "4.50%" in got["vig"] and "Ordinary main-line juice" in got["vig"]
    assert "Pays" in got["parlay"] and "independent" in got["parlay"]
    assert "No bet." in got["kelly"]
    assert "Needs to hit" in got["ev"] and "40.0%" in got["ev"] and "earns 5.0% of the stake" in got["ev"]


GAME_BETS = [
    {"market": "moneyline", "home": "Kansas", "away": "Utah", "home_odds": 150, "away_odds": -170,
     "win_prob": 0.55, "pick_is_home": False},
    {"market": "moneyline", "home": "Ohio State", "away": "Purdue", "home_odds": -900, "away_odds": 600,
     "win_prob": 0.86, "pick_is_home": True},
    # The sharp book's number, not ours: never on the meter.
    {"market": "moneyline", "home": "A", "away": "B", "home_odds": 120, "away_odds": -140, "win_prob": 0.7,
     "pick_is_home": False, "sharp_anchored": True},
    # Under way: no pre-game read.
    {"market": "moneyline", "home": "C", "away": "D", "home_odds": 200, "away_odds": -240, "win_prob": 0.6,
     "pick_is_home": False, "started": True},
    {"market": "spread", "home": "Kansas", "away": "Utah", "line": 3.5},
    # The same game twice (a second card): counted once.
    {"market": "moneyline", "home": "Kansas", "away": "Utah", "home_odds": 150, "away_odds": -170,
     "win_prob": 0.55, "pick_is_home": False},
]


def test_the_upset_meter_reads_the_boards_own_number():
    got = _node(f"const r = X.upsets({json.dumps(GAME_BETS)});"
                "process.stdout.write(JSON.stringify({r, tiers: r.map(X.upsetTier),"
                f"html: X.upsetsHTML({{game_bets: {json.dumps(GAME_BETS)}}}),"
                "empty: X.upsetsHTML({game_bets: []}), locked: X.upsetsHTML({game_bets: [], locked: {game_bets: 4}})}));")
    if got is None:
        return
    r = got["r"]
    assert [x["dog"] for x in r] == ["Kansas", "Purdue"], r
    kan = r[0]
    assert abs(kan["ours"] - 0.45) < 1e-9 and kan["dogHome"] is True and kan["price"] == 150
    fair = (1 / 2.5) / (1 / 2.5 + 170 / 270)
    assert abs(kan["market"] - fair) < 1e-9 and abs(kan["gap"] - (0.45 - fair)) < 1e-9
    assert got["tiers"][0] == ["alert", "Upset alert"] and got["tiers"][1] == ["long", "Long shot"]
    assert "Context, not a pick" in got["html"] and "never staked" in got["html"]
    assert "No college moneylines on the board yet" in got["empty"]
    assert "membership" in got["locked"] and "#paywall" in got["locked"]


BETS = ([{"id": f"w{i}", "sport": "NFL", "date": "2026-10-05", "desc": "Lions -3.5", "odds": -110, "result": "win"}
         for i in range(14)]
        + [{"id": f"l{i}", "sport": "NFL", "date": "2026-10-05", "desc": "Lions -3.5", "odds": -110, "result": "loss"}
           for i in range(8)]
        + [{"id": "p", "sport": "MLB", "date": "2026-10-06", "desc": "Judge Over 1.5 total bases", "odds": 150,
            "result": "push"},
           {"id": "o", "sport": "MLB", "date": "2026-10-06", "desc": "open one", "odds": 150, "result": "pending"},
           {"id": "c", "sport": "NBA", "date": "2026-10-07", "desc": "Tatum Over 27.5 points", "odds": -105,
            "result": "win", "close": -125},
           {"id": "x", "sport": "NBA", "date": "2026-10-07", "desc": "no price", "odds": "", "result": "win"}])


def test_the_report_card_grades_against_the_prices_taken():
    got = _node(f"const r = X.report({json.dumps(BETS)}, {{w1: {{close: -130}}, l1: {{close: -100}}}});"
                f"process.stdout.write(JSON.stringify({{r, few: X.report({json.dumps(BETS[:5])}, {{}}),"
                f"none: X.report([], {{}}), html: X.reportHTML({json.dumps(BETS)}, {{}})}}));")
    if got is None:
        return
    r = got["r"]
    a = r["all"]
    assert a["n"] == 23 and a["wins"] == 15, a                     # the push, the open bet and the unpriced one are out
    need = (22 * (110 / 210) + 105 / 205) / 23
    assert abs(a["need"] - need) < 1e-9 and abs(a["hit"] - 15 / 23) < 1e-9
    assert r["verdict"][0] == "good", r["verdict"]                  # 15 of 23 against ~52%: about +1.4 sd
    assert {g["key"] for g in r["bands"]} == {"Favourites"}
    assert {g["key"] for g in r["sports"]} == {"NFL", "NBA"}
    c = r["clv"]
    assert c["n"] == 3 and c["ours"] == 2 and c["beat"] == 2, c     # own close on "c", ours on w1 and l1
    own = next(x for x in c["rows"] if x["id"] == "c")
    assert abs(own["v"] - (125 / 225 - 105 / 205)) < 1e-9
    assert "too few to tell skill from a run" in got["few"]["verdict"][1]
    assert got["none"]["all"]["n"] == 0
    assert "Look up our closes" in got["html"] and "never the stake or the book" in got["html"]


def _ledger():
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "ledger.db")
    rows = [("nfl", "2026-10-05", "Amon-Ra St. Brown", "rec_yds", "OVER", 64.5, -115, "won", -130),
            ("nfl", "2026-10-05", "Amon-Ra St. Brown", "receptions", "OVER", 6.5, -120, "lost", -110),
            ("nfl", "2026-10-05", "Jared Goff", "pass_yds", "OVER", 255.5, -110, "open", -120),
            ("mlb", "2026-10-06", "Ronald Acuña Jr.", "hits", "OVER", 0.5, -200, "won", -220),
            ("mlb", "2026-10-06", "New York Yankees", "moneyline", "", 0.0, -140, "won", -155),
            ("nba", "2026-10-07", "Jayson Tatum", "points", "OVER", 27.5, -110, "lost", None)]
    for sport, date, player, market, side, line, odds, status, close in rows:
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, status, closing_odds, category) "
                     "VALUES (?,?,?,?,?,?,?,?,?, 'board')", (sport, date, player, market, side, line, odds, status, close))
    conn.commit()
    return conn


def test_our_close_comes_only_from_one_settled_pick():
    conn = _ledger()
    asks = [{"id": "a", "sport": "NFL", "date": "2026-10-05", "desc": "Amon-Ra St. Brown Over 64.5 rec yds -115"},
            {"id": "b", "sport": "nfl", "date": "2026-10-05", "desc": "Amon-Ra St Brown o6.5 receptions"},
            {"id": "c", "sport": "nfl", "date": "2026-10-05", "desc": "Jared Goff Over 255.5 passing yards"},
            {"id": "d", "sport": "mlb", "date": "2026-10-06", "desc": "Ronald Acuna Over 0.5 hits"},
            {"id": "e", "sport": "mlb", "date": "2026-10-06", "desc": "Yankees ML"},
            {"id": "f", "sport": "nba", "date": "2026-10-07", "desc": "Tatum Over 27.5 points"},
            {"id": "g", "sport": "nfl", "date": "2026-10-05", "desc": "Amon-Ra St. Brown Under 64.5 rec yds"},
            {"id": "h", "sport": "nfl", "date": "2026-10-05", "desc": "Amon-Ra St. Brown Over 70.5 rec yds"},
            {"id": "i", "sport": "golf", "date": "2026-10-05", "desc": "Amon-Ra St. Brown Over 64.5"},
            {"id": "j", "sport": "nfl", "date": "10/05/2026", "desc": "Amon-Ra St. Brown Over 64.5"},
            "not a bet"]
    got = reportcard.closes(conn, asks)
    assert got["a"]["close"] == -130 and got["a"]["market"] == "rec_yds" and got["a"]["label"]
    assert got["b"]["close"] == -110, got.get("b")
    assert "c" not in got, "an open pick is never answered"
    assert got["d"]["close"] == -220, "accents and a suffix fold the way the journal folds them"
    assert got["e"]["close"] == -155, "a moneyline is matched on the team's last word"
    assert "f" not in got, "no close on file, nothing returned"
    assert "g" not in got and "h" not in got, "the side and the number must both fit"
    assert "i" not in got and "j" not in got
    two = reportcard.closes(conn, [{"id": "k", "sport": "nfl", "date": "2026-10-05",
                                    "desc": "Amon-Ra St. Brown Over"}])
    assert two == {}, "two picks fit and the words name neither market: no guess"


def test_the_lookup_is_bounded_and_says_what_it_keeps():
    many = [{"id": str(i), "sport": "nfl", "date": "2026-10-05", "desc": "x" * 500} for i in range(1000)]
    clean = reportcard.clean(many)
    assert len(clean) == reportcard.MAX_BETS and all(len(b["desc"]) <= 160 for b in clean)
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/mybets/closes"' in src and "reportcard.closes(conn, body.get(\"bets\"))" in src
    assert "status IN ('won','lost','push')" in (ROOT / "engine" / "reportcard.py").read_text()


def test_the_page_reaches_the_toolbox_and_the_card():
    assert 'id="view-tools"' in HTML and '<div id="tools-body"></div>' in HTML
    assert 'data-view="tools"' in HTML
    assert '"mybets", "tools", "account"' in APP, "VIEW_ORDER names the page"
    assert 'if (name === "tools") renderTools();' in APP
    assert '["tools-body", () => renderTools()]' in APP, "a board load redraws it for the new sport"
    assert '"view:tools"' in APP, "the phone's More sheet lists it"
    assert 's.src = "js/extras.js"' in APP and 'css.href = "css/extras.css"' in APP
    assert "X.reportCard(document.getElementById(\"mb-report\"))" in APP
    assert '`<div id="mb-report"></div>`' in APP
    wall = APP[APP.index("const WALL_OPEN"):APP.index("];", APP.index("const WALL_OPEN"))]
    assert '"tools"' in wall, "the calculators are free"


def test_the_module_keeps_the_house_rules():
    src = EXTRAS.read_text(encoding="utf-8")
    assert "onclick" not in src and "eval(" not in src
    assert "window.QBExtras" in src
    css = (ROOT / "web" / "css" / "extras.css").read_text(encoding="utf-8")
    import re
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "colours come from the tokens"
    assert "gradient" not in css
    for m in re.finditer(r"transition:[^;]*", css):
        if m.group(0).strip() == "transition: none":
            continue
        assert "var(--dur-" in m.group(0) and "var(--ease-" in m.group(0), m.group(0)
    defined = set(re.findall(r"(--[a-z0-9-]+):", (ROOT / "web" / "css" / "styles.css").read_text()))
    for v in set(re.findall(r"var\((--[a-z0-9-]+)", css)):
        assert v in defined, v


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
