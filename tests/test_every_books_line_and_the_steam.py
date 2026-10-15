"""Every book's line on a market, and the steam marked where they moved together.

Ethan, 2026-10-15, one of the sixteen ideas he asked to have built ("do
every one for every sport"): a line movement chart with every book on it
and steam marks. Context only; nothing on the board reads it.

What these hold: each book's series is its own quotes, one point per
distinct number, found under the books' folded spelling; a move is the
line, or the over's price by enough at the same line, signed toward the
over or the under; steam needs three books (and half of those quoting)
moving the same way inside the window, each move used once, and two books
are never steam; the prop tape now also keeps every book for the men with
an open pick, read from the journal read-only, and every sport's build
calls it; the endpoint asks for a membership like the boards; and the
pick page draws a step line per book with the marks and says what they
are.

Run directly: `python3 tests/test_every_books_line_and_the_steam.py`
"""
import datetime as dt
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                       # noqa: E402
from engine import linebooks as LB                               # noqa: E402
from engine import proptape as PT                                # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"
NOW = dt.datetime(2026, 10, 15, 20, 0, tzinfo=dt.timezone.utc)


def _row(conn, at, book, line, over, under=-110, player="josh allen", market="pass_yds"):
    D.upsert_odds_history(conn, [{"sport": "nfl", "taken_at": at, "event_id": "2026-10-19-BUF@MIA", "home": "MIA",
                                  "away": "BUF", "player": player, "market": market, "book": book, "line": line,
                                  "over_odds": over, "under_odds": under, "commence_time": "2026-10-19T17:00:00Z"}])


def _conn():
    conn = D.connect(":memory:")
    for book in ("fanduel", "draftkings", "betmgm", "caesars"):
        _row(conn, "2026-10-15T12:00:00Z", book, 245.5, -115)
    # Three books go up inside ten minutes: steam toward the over.
    _row(conn, "2026-10-15T14:00:00Z", "fanduel", 249.5, -115)
    _row(conn, "2026-10-15T14:04:00Z", "draftkings", 249.5, -112)
    _row(conn, "2026-10-15T14:09:00Z", "betmgm", 250.5, -110)
    # A repeat of the same number is no move.
    _row(conn, "2026-10-15T15:00:00Z", "fanduel", 249.5, -115)
    # Hours later one book drops alone: a move, not steam.
    _row(conn, "2026-10-15T18:00:00Z", "caesars", 244.5, -110)
    return conn


def test_each_book_is_its_own_series_under_the_books_spelling():
    s = LB.series(_conn(), "nfl", "Josh Allen", "pass_yds", now=NOW)
    assert set(s) == {"fanduel", "draftkings", "betmgm", "caesars"}
    assert [p["line"] for p in s["fanduel"]] == [245.5, 249.5], "the repeat at 15:00 is not a point"
    assert s["caesars"][-1] == {"at": "2026-10-15T18:00:00Z", "line": 244.5, "over": -110, "under": -110}
    assert LB.series(_conn(), "nfl", "Josh Allen", "pass_yds", hours=1, now=NOW) == {}, "outside the window"


def test_a_move_is_the_line_or_the_price_and_has_a_side():
    m = LB.moves({"a": [{"at": "1", "line": 5.5, "over": -110}, {"at": "2", "line": 6.5, "over": -110}],
                  "b": [{"at": "1", "line": 5.5, "over": -110}, {"at": "3", "line": 5.5, "over": -130}],
                  "c": [{"at": "1", "line": 5.5, "over": -110}, {"at": "4", "line": 5.5, "over": -112}]})
    assert [(x["book"], x["sign"], x["kind"]) for x in m] == [("a", 1, "line"), ("b", 1, "price")], \
        "two cents at the same line is noise, twenty is a move"
    down = LB.moves({"a": [{"at": "1", "line": 5.5, "over": -110}, {"at": "2", "line": 5.5, "over": +105}]})
    assert down[0]["sign"] == -1, "the over getting cheaper is pressure on the under"


def test_steam_needs_three_books_moving_together():
    conn = _conn()
    st = LB.steam(LB.series(conn, "nfl", "Josh Allen", "pass_yds", now=NOW))
    assert len(st) == 1, st
    assert st[0]["at"] == "2026-10-15T14:00:00Z" and st[0]["sign"] == 1 and st[0]["kind"] == "line"
    assert st[0]["books"] == ["betmgm", "draftkings", "fanduel"]
    two = {"a": [{"at": "2026-10-15T12:00", "line": 1.5, "over": -110}, {"at": "2026-10-15T12:05", "line": 2.5, "over": -110}],
           "b": [{"at": "2026-10-15T12:00", "line": 1.5, "over": -110}, {"at": "2026-10-15T12:06", "line": 2.5, "over": -110}]}
    assert LB.steam(two) == [], "two books are never steam"
    slow = {b: [{"at": "2026-10-15T12:00", "line": 1.5, "over": -110}, {"at": f"2026-10-15T1{i + 3}:00", "line": 2.5, "over": -110}]
            for i, b in enumerate("abc")}
    assert LB.steam(slow) == [], "an hour apart is drift, not steam"
    ch = LB.chart(conn, "nfl", "Josh Allen", "pass_yds", now=NOW)
    assert ch["n_books"] == 4 and ch["more"] == [] and ch["rule"]["books"] == LB.STEAM_BOOKS


def test_the_tape_keeps_every_book_for_men_with_an_open_pick():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.db"
        c = sqlite3.connect(ledger)
        c.execute("CREATE TABLE bets (sport, date, player, status)")
        c.executemany("INSERT INTO bets VALUES (?,?,?,?)", [
            ("nfl", "2026-10-15", "Josh Allen", "open"), ("nfl", "2026-10-15", "Settled Man", "won"),
            ("nfl", "2026-10-01", "Old Pick", "open"), ("nba", "2026-10-15", "Other League", "open")])
        c.commit()
        c.close()
        got = PT.posted("nfl", NOW, path=ledger)
        assert got == {PT._norm("Josh Allen")}, got
        assert PT.posted("nfl", NOW, path=Path(tmp) / "missing.db") == set()
        assert not (Path(tmp) / "missing.db").exists(), "the journal is never created"

    class Line:
        def __init__(self, book, line):
            self.book, self.line, self.over_odds, self.under_odds = book, line, -110, -110

    class Prop:
        player, market, team = "Josh Allen", "pass_yds", "BUF"
        lines = [Line("fanduel", 249.5), Line("draftkings", 248.5)]

    class Game:
        home, away, date = "MIA", "BUF", "2026-10-19"

    class Slate:
        games, props = [Game()], [Prop()]
    conn = D.connect(":memory:")
    assert "nothing to watch" in PT.record_note(conn, "nfl", Slate(), NOW)
    note = PT.record_note(conn, "nfl", Slate(), NOW, also={PT._norm("Josh Allen")})
    assert "2 moved price(s) stored" in note, note
    for build in ("nfl_build.py", "mlb_build.py", "nba_build.py", "nhl_build.py", "cfb_build.py"):
        src = (ROOT / build).read_text(encoding="utf-8")
        assert "_tape_note(" in src or 'also=proptape.posted("nfl")' in src, build
    src = (ROOT / "engine" / "proptape.py").read_text(encoding="utf-8")
    assert 'f"file:{path}?mode=ro", uri=True' in src


def test_the_endpoint_asks_for_a_membership():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/lines/books"' in srv
    i = srv.index("def _lines_books(")
    body = srv[i:srv.index("\n    def ", i + 10)]
    assert "if not self._entitled(aconn, who):" in body and "401 if not who else 402" in body
    assert body.index("_entitled") < body.index("LB.chart("), "who is asking, before anything is read"


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


def test_the_pick_page_draws_a_line_per_book_and_the_marks():
    ch = LB.chart(_conn(), "nfl", "Josh Allen", "pass_yds", now=NOW)
    flat = {"books": {"a": [{"at": "2026-10-15T12:00:00Z", "line": 0.5, "over": -150},
                            {"at": "2026-10-15T13:00:00Z", "line": 0.5, "over": -170}]}, "steam": [], "more": ["z"]}
    got = _node(f"process.stdout.write(JSON.stringify({{html: X.bookLinesHTML({json.dumps(ch)}),"
                f"flat: X.bookLinesHTML({json.dumps(flat)}), none: X.bookLinesHTML({{books: {{}}}}),"
                f"by: X.bookModel({json.dumps(ch)}).byLine}}));")
    if got is None:
        return
    html = got["html"]
    assert len(re.findall(r'class="xb-l xb-c\d"', html)) == 4 and got["by"] is True
    assert html.count('class="xb-steam up"') == 1 and "betmgm, draftkings, fanduel" in html
    assert "Every book’s line" in html and "toward the over" in html and "Steam is a mark, not a signal" in html
    assert "The line each book hung." in html and ">fanduel</td>" in html
    assert "the over’s price, as a chance" in got["flat"] and "Also quoting: z." in got["flat"]
    assert "No book-by-book history for this market yet" in got["none"]
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '<div id="pp-books"></div>' in app
    assert 'X.bookLines(document.getElementById("pp-books"), state.sport, r.player, r.market)' in app


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
