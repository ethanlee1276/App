"""Account Health from the reader's own log: the Record page's per-book
limit-risk score, run in the browser over the bets on My Bets.

Audit 2026-09-30, O12 (roadmap #43). The score existed only for the site's
own journal. A reader who logs bets (by hand or by CSV, both with a book
field) now sees their own per-book score, computed on the device from
their own rows, with the blind-spots list beside it. No sportsbook login,
no scraping, nothing uploaded.

These tests run the SHIPPED functions under node and hold the port equal
to engine.ledger.account_health on one set of bets, so the two scores
cannot drift into meaning different things.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()

from engine import ledger  # noqa: E402


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(body):
    node = shutil.which("node")
    if not node:
        return None
    prog = "\n".join([
        "const plural = (n, one) => `${n} ${one}${n === 1 ? '' : 's'}`;",
        "const escapeHtml = (s) => String(s);",
        _const("MB_HEALTH_MIN"), _const("MB_HEALTH_W"), _const("MB_HEALTH_BLIND"),
        _const("MB_PROP_WORDS"),
        _fn("mbDecimal"), _fn("mbMarket"), _fn("mbBetClv"), _fn("mbHealth"),
        _fn("mbHealthHTML"), body])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# (book, description, ledger market, stake, result)
BETS = (
    [("DraftKings", "Judge Over 1.5 total bases", "batter_total_bases", 25, "win")] * 4
    + [("DraftKings", "Soto Over 0.5 total bases", "batter_total_bases", 23.17, "loss")] * 2
    + [("DraftKings", "Yankees ML", "moneyline", 25, "win")] * 2
    + [("DraftKings", "Yankees -1.5", "spread", 18.4, "loss")] * 2
    + [("FanDuel", "Chiefs ML", "moneyline", 10, "win")] * 6
    + [("Caesars", "Lions -3", "spread", 50, "loss")] * 3
)


def _ledger_health():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE bets (status, category, date, book, closing_line, "
              "line, side, market, stake_dollars)")
    for book, _desc, mk, stake, res in BETS:
        c.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?)",
                  ("won" if res == "win" else "lost", "main", "2026-09-01",
                   book, None, 1.5, "OVER", mk, stake))
    return ledger.account_health(c)


def _js_bets():
    return [{"book": b, "desc": d, "stake": s, "odds": -110, "result": r}
            for b, d, _m, s, r in BETS]


def test_the_port_scores_the_same_as_the_ledger():
    py = {b["book"]: b for b in _ledger_health()["books"]}
    js = _node(f"console.log(JSON.stringify(mbHealth({json.dumps(_js_bets())})));")
    if js is None:
        print("  SKIP node not installed"); return
    got = {b["book"]: b for b in js["books"]}
    assert set(got) == set(py) == {"DraftKings", "FanDuel"}, (set(got), set(py))
    for book, p in py.items():
        g = got[book]
        for k in ("bets", "score", "band", "beat_close_rate", "concentration",
                  "prop_share", "sharp_stake_rate"):
            assert g[k] == p[k], (book, k, g[k], p[k])
        assert len(g["actions"]) == len(p["actions"]), (book, g["actions"], p["actions"])
    assert js["short"] == 1, "Caesars has three settled bets and is not scored"


def test_the_weights_and_floor_are_the_ledgers():
    assert f"const MB_HEALTH_MIN = {ledger.HEALTH_MIN_BETS};" in APP
    w = (ledger.HEALTH_W_CLV, ledger.HEALTH_W_CONCENTRATION, ledger.HEALTH_W_PROP_MIX,
         ledger.HEALTH_W_STAKES, ledger.HEALTH_W_VOLUME)
    assert ("const MB_HEALTH_W = { clv: %d, conc: %d, mix: %d, stakes: %d, vol: %d };" % w) in APP


def test_the_blind_spots_are_the_same_four_signals():
    js = _node("console.log(JSON.stringify(mbHealth([]).blind_spots));")
    if js is None:
        print("  SKIP node not installed"); return
    py = [s for s, _w in ledger.HEALTH_BLIND_SPOTS]
    assert [b["signal"] for b in js][-len(py):] == py
    # With no closes logged, the missing signal is named first.
    assert js[0]["signal"] == "Beating the closing line"


def test_markets_are_read_from_the_words():
    cases = {
        "Judge Over 1.5 total bases": ["total bases", True],
        "Mahomes Over 274.5 passing yards": ["passing yards", True],
        "Kelce anytime TD": ["touchdown scorer", True],
        "Jokic Over 11.5 rebounds": ["rebounds", True],
        "Yankees ML": ["moneyline", False],
        "Lions -3": ["spread", False],
        "Chiefs/Bills Over 47.5": ["total", False],
        "Yankees ML + Judge HR": ["parlays", False],
        "Something odd": None,
    }
    js = _node(f"const c = {json.dumps(list(cases))};"
               "console.log(JSON.stringify(c.map((d) => { const m = mbMarket(d); "
               "return m ? [m.market, m.prop] : null; })));")
    if js is None:
        print("  SKIP node not installed"); return
    assert dict(zip(cases, js)) == cases, dict(zip(cases, js))


def test_a_logged_close_measures_the_close():
    bets = [{"book": "BetMGM", "desc": "Lions -3", "stake": 20, "odds": -105,
             "close": -120 if i < 4 else 100, "result": "win"} for i in range(5)]
    js = _node(f"console.log(JSON.stringify(mbHealth({json.dumps(bets)})));")
    if js is None:
        print("  SKIP node not installed"); return
    b = js["books"][0]
    assert b["beat_close_rate"] == 0.8, b
    assert js["closes"] == 5
    assert js["blind_spots"][0]["signal"] != "Beating the closing line"
    assert "close: [" in _const("MB_HEADERS"), "a CSV close column is read"


def test_it_never_leaves_the_device_and_renders_on_my_bets():
    for name in ("mbMarket", "mbBetClv", "mbHealth", "mbHealthHTML"):
        body = _fn(name)
        assert not re.search(r"\bfetch\(|XMLHttpRequest|apiFetch|sendBeacon", body), name
    assert "${mbHealthHTML(bets)}" in _fn("renderMyBets")
    html = _node(f"console.log(JSON.stringify(mbHealthHTML({json.dumps(_js_bets())})));")
    if html is None:
        print("  SKIP node not installed"); return
    assert "What this score can’t see" in html and "DraftKings" in html
    assert "nothing uploaded" in html
    few = _node("console.log(JSON.stringify(mbHealthHTML([])));")
    assert "Appears once a book has 5 settled bets" in few


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
