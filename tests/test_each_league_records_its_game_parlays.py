"""Each league's Record page keeps the record of its game parlays and their legs
(2026-11-16).

Ethan: "you did not put the 'parlays for this game' on the record page. We wanna
see if the legs and the parlays we recommend are hitting so each sport needs to
have a record of that on the record page."

engine/parlayledger.game_parlay_record reads every game report's three-leg
parlays and scorer pairs out of the journal, league by league and kind by kind:
the tickets that hit and their units at one unit a ticket, the legs that hit,
leg by market, the tickets that lost by one leg, and the newest tickets with
every leg's result. record.json carries it for the Record page alone
(ledger.RECORD_PAGE_ONLY), and js/record.js draws it above the folds in "The Game
Report Picks and Parlays" (recReportBook, gpParlaysHTML): a league's own cards in
its scope, one table of every league on All.

Run directly: `python3 tests/test_each_league_records_its_game_parlays.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import ledger, parlayledger                                 # noqa: E402

RECORD = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")


def _ticket(conn, sport, source, date, game, status, joint, dec, legs, at_start=1):
    """One journaled ticket and its legs: (player, market, side, line, odds,
    our chance, status, what the player did). ``at_start``: in its game's set
    at the start (parlayledger.mark_at_start), the tickets the record counts."""
    lost = sum(1 for l in legs if l[6] == "lost")
    won = sum(1 for l in legs if l[6] == "won")
    pnl = round(dec - 1.0, 4) if status == "won" else -1.0 if status == "lost" else None
    n = conn.execute("SELECT COUNT(*) FROM parlays").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, modeled_joint, "
        "assumed_dec, status, pnl_units, legs_won, legs_lost, legs_void, at_start) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sport, date, f"{game}|{n}", "same_game", len(legs), game, source, joint, dec, status, pnl,
         won if status != "open" else None, lost if status != "open" else None,
         sum(1 for l in legs if l[6] == "void") if status != "open" else None, at_start))
    for i, l in enumerate(legs, 1):
        conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, odds, p_final, "
                     "status, actual) VALUES (?,?,?,?,?,?,?,?,?,?)", (cur.lastrowid, i, *l))
    return cur.lastrowid


def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    parlayledger.ensure_schema(conn)
    three, td = "game_three", "game_td"
    _ticket(conn, "nfl", three, "2026-W10", "CIN@PIT", "won", 0.30, 3.2, [
        ("Chase Brown", "receptions", "OVER", 3.5, -190, 0.70, "won", 5),
        ("Joe Burrow", "pass_td", "OVER", 1.5, -205, 0.68, "won", 2),
        ("Rico Dowdle", "receptions", "OVER", 1.5, -230, 0.70, "won", 3)])
    _ticket(conn, "nfl", three, "2026-W10", "CIN@PIT", "lost", 0.28, 3.0, [
        ("DK Metcalf", "receptions", "UNDER", 4.5, -138, 0.58, "lost", 6),
        ("Joe Burrow", "pass_cmp", "OVER", 24.5, -240, 0.70, "won", 27),
        ("Dohnte Meyers", "receptions", "OVER", 1.5, -250, 0.72, "won", 2)])
    _ticket(conn, "nfl", three, "2026-W11", "DET@WAS", "lost", 0.25, 3.4, [
        ("Jared Goff", "pass_yds", "OVER", 249.5, -150, 0.60, "lost", 201),
        ("Amon-Ra St. Brown", "receptions", "OVER", 6.5, -140, 0.58, "lost", 4),
        ("Jahmyr Gibbs", "rush_yds", "OVER", 69.5, -130, 0.57, "void", None)])
    _ticket(conn, "nfl", three, "2026-W11", "DET@WAS", "open", 0.27, 3.1, [
        ("Jared Goff", "pass_td", "OVER", 1.5, -160, 0.62, "open", None)])
    _ticket(conn, "nfl", td, "2026-W11", "DET@WAS", "won", 0.20, 5.5, [
        ("Jahmyr Gibbs", "anytime_td", "OVER", 0.5, -150, 0.55, "won", 1),
        ("Terry McLaurin", "anytime_td", "OVER", 0.5, 160, 0.38, "won", 1)])
    _ticket(conn, "nhl", three, "2026-11-15", "BOS@TOR", "lost", 0.30, 3.1, [
        ("Auston Matthews", "shots", "OVER", 3.5, -150, 0.60, "won", 5),
        ("David Pastrnak", "points", "OVER", 0.5, -200, 0.66, "lost", 0),
        ("William Nylander", "shots", "OVER", 2.5, -160, 0.62, "won", 4)])
    # A benched league and another screen's ticket: neither is a game report's record.
    _ticket(conn, "wnba", three, "2026-08-01", "LV@NY", "won", 0.30, 3.0, [
        ("A'ja Wilson", "points", "OVER", 22.5, -150, 0.60, "won", 30)])
    _ticket(conn, "nfl", "edge", "2026-W10", "CIN@PIT", "won", 0.40, 2.6, [
        ("Joe Burrow", "pass_yds", "OVER", 249.5, -110, 0.55, "won", 280)])
    conn.commit()
    return conn


def test_each_league_keeps_its_tickets_and_their_legs():
    rec = parlayledger.game_parlay_record(_journal())
    assert set(rec) == {"nfl", "nhl"}, "a benched league stays off the record page"
    b = rec["nfl"]["three"]
    assert (b["graded"], b["wins"], b["losses"], b["open"]) == (3, 1, 2, 1), "another screen's ticket is not counted"
    assert b["net_units"] == 0.2 and abs(b["roi"] - 0.0667) < 1e-4
    assert abs(b["chance"] - 0.277) < 1e-3, "our average chance on the tickets"
    assert b["one_away"] == 1, "one ticket lost by one leg, one by two"
    assert b["since"] == "2026-W10"
    assert (b["legs"]["graded"], b["legs"]["won"], b["legs"]["lost"]) == (8, 5, 3), "a void leg is neither"
    assert abs(b["legs"]["chance"] - 0.6575) < 1e-3
    assert [(m["market"], m["won"], m["graded"]) for m in b["markets"]] == [
        ("receptions", 3, 5), ("pass_cmp", 1, 1), ("pass_td", 1, 1), ("pass_yds", 0, 1)], "most legs first"
    assert [t["game"] for t in b["recent"]] == ["DET@WAS", "CIN@PIT", "CIN@PIT"], "the newest first, graded only"
    newest = b["recent"][0]
    assert newest["status"] == "lost" and newest["chance"] == 0.25 and newest["price_dec"] == 3.4
    assert [l["player"] for l in newest["legs"]] == ["Jared Goff", "Amon-Ra St. Brown", "Jahmyr Gibbs"]
    assert newest["legs"][0]["actual"] == 201 and "actual" not in newest["legs"][2], "a void leg has no number"
    td = rec["nfl"]["scorers"]
    assert (td["graded"], td["wins"], td["net_units"]) == (1, 1, 4.5)
    assert set(rec["nhl"]) == {"three"} and rec["nhl"]["three"]["one_away"] == 1


def test_a_leg_on_two_tickets_counts_once_by_market():
    """The Record page, 18 November 2026: "109 of 180 legs" (each once) over
    "Rebounds 110 of 202", the market rows counting every ticket a leg rode."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    parlayledger.ensure_schema(conn)
    shared = ("Chase Brown", "receptions", "OVER", 3.5, -190, 0.70, "won", 5)
    _ticket(conn, "nfl", "game_three", "2026-W10", "CIN@PIT", "lost", 0.30, 3.2, [
        shared, ("Joe Burrow", "pass_td", "OVER", 1.5, -205, 0.68, "lost", 1),
        ("Rico Dowdle", "receptions", "OVER", 1.5, -230, 0.70, "won", 3)])
    _ticket(conn, "nfl", "game_three", "2026-W10", "CIN@PIT", "won", 0.28, 3.0, [
        shared, ("Ja'Marr Chase", "receptions", "OVER", 5.5, -150, 0.62, "won", 8),
        ("Tee Higgins", "receptions", "OVER", 3.5, -160, 0.63, "won", 5)])
    conn.commit()
    b = parlayledger.game_parlay_record(conn)["nfl"]["three"]
    assert b["legs"]["once"]["graded"] == 5 and b["legs"]["graded"] == 6, b["legs"]
    rows = {m["market"]: (m["won"], m["graded"]) for m in b["markets"]}
    assert rows == {"receptions": (4, 4), "pass_td": (0, 1)}, rows
    assert sum(g for _w, g in rows.values()) == b["legs"]["once"]["graded"], "the market rows add up to the legs line"


def test_the_record_ships_it_for_the_record_page_alone():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert '"game_parlay_record": _game_parlay_record(conn),' in src
    assert "game_parlay_record" in ledger.RECORD_PAGE_ONLY, "the home page's slim copy leaves it out"
    broken = ledger._game_parlay_record(None)
    assert set(broken) == {"error"}, "a failure never breaks the export"


def test_it_sits_above_the_folds_with_the_reports_own_record():
    assert "parlays: d.game_parlay_record }, scoped ? scope : \"\");\n  const receipts = calendar" in RECORD
    i = RECORD.index("const receipts = calendar")
    block = RECORD[i:RECORD.index("+ foldClose", i)]
    gp = block.index("    + reportBook\n")
    facts = block.index("    + (scoped ? recFactsSlot(scope) : \"\")\n")
    fold = block.index('+ foldOpen("Most Likely, Pick of the Day and Zeno")')
    assert gp < facts < fold, "neither waits on the main book's floor"
    assert block.count("recFactsSlot(") == 1, "the reports' fact check is drawn once"


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    start = RECORD.index("const tlAmerican = ")
    code = RECORD[start:RECORD.index("/* The Most Likely paper record.")]
    js = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const escapeHtml = esc; const icon = (n) => `[${n}]`; const PARLAY_RATE_FLOOR = 10;"
          "const marketWord = (m) => ({ receptions: 'Receptions', pass_td: 'Passing TDs', shots: 'Shots on goal',"
          " points: 'Points', anytime_td: 'Anytime TD' })[m] || m;"
          "const toneOf = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');"
          "const trueMinus = (s) => String(s); const american = (o) => (o > 0 ? `+${o}` : `${o}`);"
          "const formatGameDate = (d) => `day ${d}`; const lgCode = (s) => s.toUpperCase();"
          "const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;"
          "const SPORT_META = { nfl: {}, mlb: {}, nba: {}, cbb: {}, cfb: {}, nhl: {} };"
          "function recTile(k, v, sub, o) { return `<tile k=\"${k}\" v=\"${v}\" tone=\"${(o || {}).tone || ''}\">${sub || ''}</tile>`; }\n"
          + code + f"\nprocess.stdout.write(JSON.stringify((() => {{ {body} }})()));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_a_league_sees_its_tickets_legs_and_markets():
    rec = parlayledger.game_parlay_record(_journal())
    got = _node(f"const R = {json.dumps(rec)}; const B = (p, s) => recReportBook({{ parlays: p }}, s);"
                " return [B(R, 'nfl'), B(R, 'nhl'), B(R, 'mlb'), B({ error: 'x' }, 'nfl'), recReportBook(null, '')];")
    if got is None:
        return
    nfl, nhl, mlb, broken, none = got
    assert "The Game Report Picks and Parlays" in nfl and "[ticket]" in nfl
    assert "Three-leg parlays" in nfl and "Touchdown pairs" in nfl, "each kind on its own card"
    assert 'k="Tickets that hit" v="1 of 3"' in nfl and "+0.20u at one unit a ticket" in nfl
    assert "we gave them 28% on average" in nfl and "1 open" in nfl
    assert 'k="Legs that hit" v="5 of 8"' in nfl and "we gave the legs 66% on average" in nfl
    assert "1 of the 2 tickets that lost missed by a single leg." in nfl, "the near misses, said under the tiles"
    assert "Lost by one leg" not in nfl, "a third tile wraps alone on a phone"
    assert '<span class="rl-proc bad">0 of 2 legs</span>' in nfl, "a void leg is neither hit nor miss"
    assert '<span class="rl-proc warn">2 of 3 legs</span>' in nfl and '<span class="rl-proc good">3 of 3 legs</span>' in nfl
    assert "Legs by market" in nfl and "<b>3 of 5</b> legs hit · 60%" in nfl
    assert "Week 11" in nfl and "since Week 10" in nfl and "DET at WAS" in nfl
    assert "Jahmyr Gibbs to score a touchdown <span class=\"rr-mute\">· scored 1</span>" in nfl
    assert "over 0.5" not in nfl, "a scorer leg as the card says it"
    assert "Jared Goff over 249.5 <span class=\"rr-mute\">pass_yds · had 201</span>" in nfl
    assert "every pick and parlay our NFL game reports posted" in nfl
    assert "Goal-scorer" not in nhl and "Three-leg parlays" in nhl and "Shots on goal · had 5" in nhl
    assert mlb == "" and broken == "" and none == "", "nothing to show draws nothing"


def test_all_leagues_get_one_table_in_the_sites_order():
    rec = parlayledger.game_parlay_record(_journal())
    got = _node(f"return recReportBook({{ parlays: {json.dumps(rec)} }}, '');")
    if got is None:
        return
    assert "<table class=\"agate rec-gp-table\">" in got and "pick a league above" in got
    import re
    rows = got.split("<tr>")[2:]
    assert [re.search(r"<b>(\w+)</b>", r).group(1) for r in rows] == ["NFL", "NFL", "NHL"], "the site's league order"
    assert 'class="rec-gp-kind">Three-leg parlays<' in rows[0] and 'class="rec-gp-kind">Touchdown pairs<' in rows[1]
    assert '1 of 3<span class="rec-gp-pct">33%</span>' in rows[0] and '5 of 8<span class="rec-gp-pct">63%</span>' in rows[0]
    assert len(re.findall(r"<th[ >]", got)) == 4, "four columns fit a phone"


def test_the_styles_are_written_for_it():
    css = (ROOT / "web" / "css" / "record.css").read_text(encoding="utf-8")
    for sel in (".rec-gp + .rec-gp", ".rec-gp-recent .rl-row", ".rec-gp-note", ".rec-gp-close",
                ".rec-gp-kind, .rec-gp-pct", ".rec-rp-head"):
        assert sel in css, sel
    for cls in ('"card rec-report rec-gp"', '"rec-gp-recent"', '"rec-gp-note"', '"rec-gp-close"', '"rec-gp-kind"',
                '"rec-gp-pct"', '"agate rec-gp-table"'):
        assert cls in RECORD, cls


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
