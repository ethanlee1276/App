"""A road favourite's line is stored the right way round, and every finished game names its close.

24 November 2026, comparing the leagues' boards key by key: Memphis was −185 at Charlotte and the board said
Memphis −5.5, but the line store (engine/lineopen) had it opening as Charlotte −4. crowd.home_spread read `spread`
as a size and took the home club for the favourite whenever the board named none, and only the NFL's board names
one: 5 of the NBA's 10 games that night, 3 of college basketball's 24 priced games and 2 of hockey's 7 were stored
on the wrong side of zero. The store is what the Record grades a spread bet's close against (the Record read an
average closing-line value of +2.0 runs on baseball's run lines and −6.0 points on the NBA's picks of the day), the
line's move and its "moved against the money" note, and the spread the prediction markets and the money split are
matched on.

Pinned here: the home club's number keeps its own sign unless a favourite is named; a road favourite is stored and
moves the right way, and its against-the-money note follows; the rows stored before are turned round once, from
their own moneylines, the NFL's never; a started game carries its close, which the page reads for a finished game
in every league (hockey's finished games had lost their lines on the first build after midnight, college
basketball's as each game ended, the NFL's moneylines were the not-offered zero); and the Record's banked closes are
read again by the settle's own function, by a command that takes the backup first.

Offline: temporary journal, history and crowd databases. Run directly:
`python3 tests/test_a_road_favorites_line_is_stored_the_right_way_round.py`
"""
import datetime as dt
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

from engine import crowd, db, ledger, lineopen                     # noqa: E402

NOW = 1_790_000_000
DAY = (dt.date.today() - dt.timedelta(days=3)).isoformat()
LATER = "2099-01-01T00:00Z"


def test_the_home_clubs_number_keeps_its_own_sign():
    # The NBA's, hockey's and college's boards: the home club's signed number, no favourite named.
    assert crowd.home_spread({"home": "CHA", "away": "MEM", "spread": 5.5}) == 5.5, "Memphis gives 5.5 at Charlotte"
    assert crowd.home_spread({"home": "NJD", "away": "CBJ", "spread": -1.5}) == -1.5
    # Baseball's board writes its favourite empty: the sign stands.
    assert crowd.home_spread({"home": "NYY", "away": "BOS", "spread": 1.5, "favorite": ""}) == 1.5
    # The NFL's names its favourite, which settles the sign.
    assert crowd.home_spread({"home": "BUF", "away": "MIA", "spread": -16.5, "favorite": "BUF"}) == -16.5
    assert crowd.home_spread({"home": "PHI", "away": "PIT", "spread": 3.5, "favorite": "PIT"}) == 3.5
    assert crowd.home_spread({"home": "PHI", "away": "PIT", "spread": -3.5, "favorite": "PIT"}) == 3.5
    for bad in (None, "", "x", float("nan")):
        assert crowd.home_spread({"home": "A", "away": "B", "spread": bad}) is None, bad


def _game(spread, home_ml, away_ml, **kw):
    return {"home": "CHA", "away": "MEM", "date": DAY, "kickoff": LATER, "spread": spread, "total": 218.5,
            "home_ml": home_ml, "away_ml": away_ml, **kw}


def test_a_road_favourite_is_stored_and_moves_the_right_way():
    c = sqlite3.connect(":memory:")
    lineopen.record(c, "nba", [_game(4.0, 145, -155)], NOW)
    lineopen.record(c, "nba", [_game(5.5, 196, -185)], NOW + 3600)
    assert c.execute("SELECT open_spread, now_spread FROM line_opens").fetchone() == (4.0, 5.5), \
        "Memphis opened −4 and closed −5.5: Charlotte's number is +4, then +5.5"
    # The money on Charlotte, the line moving toward Memphis: against the money.
    g = _game(5.5, 196, -185, money={"spread": {"home": 0.7}})
    lineopen.attach(c, "nba", [g], NOW + 3600)
    lo = g["line_open"]
    assert lo["spread_home"] == 4.0 and lo["spread_move"] == 1.5, lo
    assert lo["against_money"]["toward"] == "away" and lo["against_money"]["money_on"] == "home", lo
    assert "close" not in lo, "before the start there is no close yet"


def _old_store():
    """Rows as the old rule wrote them: every league but the NFL's with the home club as favourite."""
    c = sqlite3.connect(":memory:")
    lineopen.ensure_tables(c)
    rows = [
        # Memphis the road favourite (−155, then −185), stored as Charlotte −4 and −5.5.
        ("nba", DAY, "MEM", "CHA", NOW, -4.0, 218.5, 145, -155, NOW + 60, -5.5, 214.5, 196, -185),
        # Philadelphia the home favourite: right under either rule.
        ("nba", DAY, "POR", "PHI", NOW, -3.5, 228.5, -140, 132, NOW + 60, -2.5, 236.5, -135, 135),
        # Utah's puck line on the road, opened before its close was ever read.
        ("nhl", DAY, "UTA", "WPG", NOW, -1.5, 5.5, 100, -114, None, None, None, None, None),
        # No moneylines: nothing to read the favourite from.
        ("cbb", DAY, "CLT", "FGCU", NOW, -6.5, 150.5, None, None, None, None, None, None, None),
        # The NFL's board always named its favourite; its rows are never touched.
        ("nfl", DAY, "SF", "LAR", NOW, -2.5, 48.5, 130, -150, NOW + 60, -2.5, 48.5, 130, -150),
    ]
    c.executemany("INSERT INTO line_opens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return c


def test_the_old_rows_are_turned_round_once_from_their_own_moneylines():
    c = _old_store()
    assert lineopen.repair_signs(c) == 3, "Memphis's open and close, Utah's open"
    got = {(r[0], r[1]): r[2:] for r in c.execute(
        "SELECT sport, away, open_spread, now_spread FROM line_opens")}
    assert got[("nba", "MEM")] == (4.0, 5.5), got
    assert got[("nba", "POR")] == (-3.5, -2.5), got
    assert got[("nhl", "UTA")] == (1.5, None), got
    assert got[("cbb", "CLT")] == (-6.5, None), "no moneylines, no change"
    assert got[("nfl", "SF")] == (-2.5, -2.5), "the NFL's rows are never touched"
    assert c.execute("SELECT name, rows FROM line_open_fixes").fetchall() == [(lineopen.SIGN_FIX, 3)]
    assert lineopen.repair_signs(c) == 0, "once"
    assert c.execute("SELECT open_spread FROM line_opens WHERE away='MEM'").fetchone() == (4.0,)
    # Every build runs it, before it writes.
    src = (ROOT / "engine" / "lineopen.py").read_text(encoding="utf-8")
    rec = src[src.index("def record("):src.index("def against_money(")]
    assert "    ensure_tables(conn)\n    repair_signs(conn)\n" in rec


def test_a_started_game_carries_its_close():
    c = sqlite3.connect(":memory:")
    lineopen.record(c, "nfl", [{"home": "BUF", "away": "MIA", "date": DAY, "kickoff": "13:00", "spread": -16.5,
                                "favorite": "BUF", "total": 45.5, "home_ml": -1350, "away_ml": 980}], NOW)
    # After the game the board's moneylines are the not-offered zero; the close keeps the last pregame price.
    g = {"home": "BUF", "away": "MIA", "date": DAY, "kickoff": "13:00", "spread": -16.5, "favorite": "BUF",
         "total": 45.5, "home_ml": 0, "away_ml": 0, "live": {"state": "final"}}
    lineopen.attach(c, "nfl", [g], NOW + 86400)
    assert g["line_open"]["close"] == {"spread_home": -16.5, "total": 45.5, "home_ml": -1350, "away_ml": 980}, g
    # A game first seen on a dated price has no close to give.
    c2 = sqlite3.connect(":memory:")
    lineopen.record(c2, "nhl", [{"home": "NJD", "away": "CBJ", "date": DAY, "kickoff": LATER, "spread": -1.5,
                                 "total": 6.5, "home_ml": -190, "away_ml": 175, "price_stale": True}], NOW)
    g2 = {"home": "NJD", "away": "CBJ", "date": DAY, "kickoff": LATER, "live": {"state": "final"}}
    lineopen.attach(c2, "nhl", [g2], NOW)
    assert "close" not in g2["line_open"], g2


def _node(js):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_every_finished_game_names_its_close():
    from _app import decl
    got = _node(decl("spreadFav") + decl("closedLine") + """
      const nhl = {home: "NJD", away: "CBJ", spread: null, total: null, home_ml: null, away_ml: null,
                   line_open: {close: {spread_home: -1.5, total: 6.5, home_ml: -195, away_ml: 180}}};
      const road = {home: "CHA", away: "MEM", spread: 5.5, favorite: "CHA",
                    line_open: {close: {spread_home: 5.5, total: 214.5, home_ml: 196, away_ml: -185}}};
      const bare = {home: "A", away: "B", spread: -3};
      const a = closedLine(nhl), b = closedLine(road);
      console.log(JSON.stringify({a: [a.spread, a.total, a.home_ml, a.away_ml, spreadFav(a), a.closed],
                                  b: [spreadFav(b), b.favorite], bare: closedLine(bare) === bare}));""")
    if got is None:
        return
    assert got["a"] == [-1.5, 6.5, -195, 180, "NJD", True], got
    assert got["b"] == ["MEM", "MEM"], "the close's own sign names the favourite, not the board's word"
    assert got["bare"], "no stored close: the board's own fields"
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "const gl = isFinal ? closedLine(g) : g;" in det
    assert "Game lines${gl.closed\n      ? ` <span class=\"gp-panel-sub\">— the last line before the game started</span>` : \"\"}" in det
    assert "<b>${gpMl(gl.away_ml)}</b>" in det and "<b>${gpMl(gl.home_ml)}</b>" in det
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    card = app[app.index("function gameCard(g, i) {"):]
    assert "const favTxt = (!mkts && g.favorite && g.spread != null)" in card, "the NFL's card reads the close's favourite"
    assert card.index('if ((g.live || {}).state === "final") g = closedLine(g);') < card.index("const mkts = ")


def _world(games):
    t = Path(tempfile.mkdtemp())
    L, H = ledger.connect(t / "l.db"), db.connect(t / "h.db")
    H.executemany("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", games)
    H.commit()
    return L, H


def _settled(L, sport, player, line, close):
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category, closing_line) VALUES (?, ?, ?, ?, ?, 'spread', 'OVER', ?, -110, "
              "1, 0, 'won', 'board', ?)", (f"{DAY}T15:00:00", sport, DAY, DAY, player, line, close))
    L.commit()


def _store(rows):
    p = Path(tempfile.mkdtemp()) / "crowd.db"
    c = sqlite3.connect(p)
    lineopen.ensure_tables(c)
    c.executemany("INSERT INTO line_opens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return p, c


def test_the_records_closes_are_read_again():
    # Boston won 5-3 at New York, the road favourite at −145; Tampa Bay won 4-2 at home, favoured.
    L, H = _world([("mlb", 2026, DAY, "746201", DAY, "NYY", "BOS", 3, 5),
                   ("mlb", 2026, DAY, "746202", DAY, "TB", "TOR", 4, 2)])
    # Boston −1.5 is stored as line 1.5 (a spread is journaled negated); under the old rule it banked a close of
    # −1.5, a closing-line value of −3 runs on a run line that never moved.
    _settled(L, "mlb", "BOS", 1.5, -1.5)
    _settled(L, "mlb", "TB", 1.5, 1.5)
    path, c = _store([("mlb", DAY, "BOS", "NYY", NOW, -1.5, 8.5, 130, -150, NOW + 60, -1.5, 8.5, 125, -145),
                      ("mlb", DAY, "TOR", "TB", NOW, -1.5, 8.0, -140, 120, NOW + 60, -1.5, 8.0, -150, 130)])
    assert lineopen.repair_signs(c) == 2
    c.close()
    saved = crowd.DB_PATH
    crowd.DB_PATH = path
    try:
        dry = ledger.repair_spread_closes(L, H, apply=False)
        assert (dry["examined"], dry["changed"], dry["same"]) == (2, 1, 1), dry
        assert dry["sample"][0][1:] == ("mlb", "BOS", 1.5, -1.5, 1.5), dry["sample"]
        assert L.execute("SELECT closing_line FROM bets WHERE player='BOS'").fetchone()[0] == -1.5, "dry: no write"
        wet = ledger.repair_spread_closes(L, H, apply=True)
        assert wet["by_sport"] == {"mlb": 1}, wet
        clv = {r["player"]: ledger._bet_clv(r) for r in L.execute("SELECT * FROM bets")}
        assert clv == {"BOS": 0.0, "TB": 0.0}, clv
        again = ledger.repair_spread_closes(L, H, apply=True)
        assert (again["changed"], again["same"]) == (0, 2), again
        assert ledger.repair_spread_closes(L, H, sport="nfl")["examined"] == 0, "the NFL's closes were right"
    finally:
        crowd.DB_PATH = saved
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = launch.index("def repair_spread_closes(")
    body = launch[i:launch.index("\ndef ", i + 10)]
    assert '_backed_up("repair-spread-closes", history=False)' in body, "a write takes the backup first"
    assert body.index("lineopen.repair_signs(c)") < body.index("ledger.repair_spread_closes("), "the store first"
    assert '"--repair-spread-closes" in argv' in launch and '"--repair-spread-closes",' in launch


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
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
