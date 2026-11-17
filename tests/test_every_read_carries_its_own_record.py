"""Every read carries its own record, and our numbers are checked against the line.

Ethan, 2026-11-16, after the fact checks shipped: "Ok keep going". The round
after "we need to fact check ourselves after the game's over and see if we were
correct or not", and a yes to putting the reports' record where anyone can see it:

  * each graded section of a game report opens with how its kind of read has
    done on finished games so far (engine/reportrecord.track_lines), stamped by
    every league's build before a started game's report is kept;
  * the reports' record is drawn on the free Record page too, for the league in
    scope (js/record.js recFactsSlot, js/reportpicks.js rpFactsInto);
  * a finished prop says our number beside his ("Won · 31 points (our number
    26.4)"), the report's own picks included (engine/reportbets.FIELDS);
  * the record counts, over every finished player pick, how often our number
    was nearer what happened than the book's line (ledger.number_vs_line), on
    the Record page's Calibration room.

    python3 tests/test_every_read_carries_its_own_record.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import reportrecord as RR                                # noqa: E402


class _Fixtures:
    """The finished-game pick test's Node harness, imported when a test needs it."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_a_finished_game_says_how_every_pick_went"), attr)


P = _Fixtures()

TOTALS = {"games": 13, "since": "2026-11-12", "through": "2026-11-15", "call": [9, 13], "ratings": [10, 13],
          "reads": [130, 236], "groups": {"matchups": [43, 73], "candidates": [29, 60], "fades": [12, 14],
                                          "angles": [25, 55], "units": [9, 14], "script": [12, 20], "starters": [3, 6]},
          "injuries": [76, 76], "missed": 0, "tds": [11, 30, 10.4]}


def test_each_graded_section_says_how_its_kind_of_read_has_done():
    lines = RR.track_lines(TOTALS, "nfl")
    tail = ", on 13 finished NFL games since Nov 12."
    assert lines["matchups"] == "Our matchup reads so far: 43 of 73 right (59%)" + tail, lines["matchups"]
    assert lines["watch"] == ("Our record so far: breakout candidates beat their average 29 of 60 times (48%) and "
                              "fades fell short of it 12 of 14 times (86%)" + tail), lines["watch"]
    assert lines["trenches"] == lines["defense"] == lines["tape"] == \
        "Our offense-against-defense reads so far: 9 of 14 right (64%)" + tail
    assert lines["scripts"] == lines["script"] == "Our reads on how the game would go so far: 12 of 20 right (60%)" + tail
    assert "pitching" not in lines and "goalies" not in lines, "six starter reads are too few to say"
    assert lines["verdict"] == ("Who we think wins has been right in 9 of 13 (69%), our ratings alone in 10 of 13 "
                                "(77%)" + tail), lines["verdict"]
    assert lines["injuries"] == "Our injury report so far: 76 of 76 right (100%)" + tail
    assert lines["redzone"] == ("Our touchdown chances so far: 11 of the 30 players we gave one scored, where our "
                                "chances added up to 10.4" + tail), lines["redzone"]
    one = RR.track_lines(dict(TOTALS, games=1, call=[1, 1], groups={"fades": [9, 10]}, injuries=[2, 3], tds=[0, 0, 0]),
                         "nba")
    assert one == {"watch": "Our record so far: fades fell short of it 9 of 10 times (90%), on 1 finished NBA game "
                            "since Nov 12."}, one
    assert RR.track_lines({"games": 0}, "nfl") == {}
    missed = RR.track_lines(dict(TOTALS, missed=2), "nba")["injuries"]
    assert missed.startswith("Our injury report so far: 76 of 76 right (100%), with 2 regulars who sat and were not "
                             "on it, on 13 finished NBA games"), missed


def test_a_report_opens_each_section_on_its_record_once():
    where = Path(tempfile.mkdtemp())
    # A league's archive of one graded final: its record is too thin to say.
    assert RR.stamp_track([{"sections": [{"key": "matchups", "blocks": [{"type": "p", "text": "x"}]}]}],
                          where, "nfl") == 0
    reports = [{"sections": [
        {"key": "matchups", "blocks": [{"type": "track", "text": "old"}, {"type": "p", "text": "Read."}]},
        {"key": "facts", "blocks": [{"type": "list", "items": ["Kickoff."]}]}]}]
    import engine.reportrecord as mod
    real = mod.rows
    try:
        mod.rows = lambda where, sport, write=True: [{"date": "2026-11-15", "call": {"team": "DET", "right": True},
                                                      "groups": {"matchups": [8, 12]}, "reads": [8, 12]}]
        assert RR.stamp_track(reports, where, "nfl") == 1
        RR.stamp_track(reports, where, "nfl")
    finally:
        mod.rows = real
    blocks = reports[0]["sections"][0]["blocks"]
    assert [b["type"] for b in blocks] == ["track", "p"], "replaced, never doubled"
    assert blocks[0]["text"] == ("Our matchup reads so far: 8 of 12 right (67%), on 1 finished NFL game since "
                                 "Nov 15."), blocks[0]
    assert [b["type"] for b in reports[0]["sections"][1]["blocks"]] == ["list"], "a section with no graded reads"
    assert RR.stamp_track(reports, None, "nfl") == 0 and [b["type"] for b in reports[0]["sections"][0]["blocks"]] == \
        ["p"], "no build, no record: an old line is taken off, not left stale"
    from engine import gamereport as R
    assert R.stamp_track(reports, "nfl", None) == 0, "only a build stamps"
    for f in ("gamereport.py", "leaguereport.py"):
        src = (ROOT / "engine" / f).read_text(encoding="utf-8")
        i = src.index("        stamp_track(reports, sport, out)\n")
        assert src.index("reports, kept = keep_started(result, reports, sport, out, at, conn)", i) > i, \
            f"{f}: stamped before a started game's report is kept"
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'if (b.type === "track") return `<p class="gr-track">${escapeHtml(b.text)}</p>`;' in js
    assert '|| b.type === "track") out.push(b.text);' in js, "copied with the report"
    assert ".gr-track" in (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    rep = {"title": "x", "game": "a@b", "when": "w", "minutes": 1, "sections": [
        {"title": "Who's guarding who", "blocks": [{"type": "track", "text": "Our matchup reads so far: 8 of 12."}]}]}
    assert "[Our matchup reads so far: 8 of 12.]" in R.to_text(rep)


def test_the_record_page_draws_how_our_reports_did_for_the_league_in_scope():
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert "    + (scoped ? recFactsSlot(scope) : \"\")\n" in rec
    assert 'return `<div class="rec-facts" data-rec-facts="${escapeAttr(scope)}"></div>`;' in rec
    assert "  bindSubtabs(host);\n  recFactsMount(host);\n" in rec
    # ...and, once the games are listed, the tab's flat lists of the same picks and tickets give way to them
    # (tests/test_the_record_page_says_each_thing_once.py).
    assert ('if (typeof rpFactsInto === "function") rpFactsInto(el, el.dataset.recFacts)'
            '.then((games) => recReceiptsOnce(host, el, games));') in rec
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert ('function rpFactsInto(...a) { return roomCall(rpFactsInto, "rpFactsInto", "js/reportpicks.js", '
            '"css/reportpicks.css", a); }') in app, "the room loads on the Record page too"
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert "async function rpFactsInto(slot, league) {" in rp
    assert "const league = (sec && sec.dataset.rpkSport) || state.sport;" in rp, "a game opens in its own league"
    assert 'league ? ` data-rpk-sport="${escapeAttr(league)}"` : ""' in rp
    assert '${league ? "" : ` id="rpk-facts"`}' in rp, "one id on the page"


def test_a_finished_prop_says_our_number_beside_his():
    got = P._node(P.GAME + """
      const P2 = (r) => pickResult(r, G);
      const kcp = { player: 'Kentavious Caldwell-Pope', market: 'rebounds', side: 'Over', line: 1.5, projection: 2.84 };
      const whole = Object.assign({}, kcp, { projection: 3 });
      const none = Object.assign({}, kcp, { projection: null });
      const zero = Object.assign({}, kcp, { projection: 0 });
      return [pickResultWords(P2(kcp), kcp), pickResultWords(P2(whole), whole), pickResultWords(P2(none), none),
              pickResultWords(P2(zero), zero),
              pickResultWords(P2({ player: 'Joel Embiid', market: 'anytime_td', side: 'yes', projection: 0.4 }),
                              { market: 'anytime_td', projection: 0.4 })];""")
    if got is None:
        return
    assert got == ["Won · 4 rebounds (our number 2.8)", "Won · 4 rebounds (our number 3)", "Won · 4 rebounds",
                   "Won · 4 rebounds", "Lost · didn’t score"], got
    from engine import reportbets as RB
    assert "projection" in RB.FIELDS, "a report's own pick carries the number it was made on"


def _journal():
    from engine import ledger
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ins = ("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, projection, status, actual, category, "
           "leg) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")
    rows = []

    def add(sport, player, market, line, proj, actual, status="won", category="main", side="OVER", day="2026-11-15"):
        rows.append((day + "T00:00:00", sport, day, player, market, side, line, -110, proj, status, actual, category,
                     None))
    for i in range(12):            # points: ours nearer on 8, the line on 3, level on 1
        actual = 30.0 if i < 8 else 20.0 if i < 11 else 27.0
        add("nba", f"P{i}", "points", 24.5, 29.5, actual)
    for i in range(10):            # rebounds: ours nearer on 3 of 10
        add("nba", f"R{i}", "rebounds", 7.5, 9.5, 6.0 if i >= 3 else 10.0)
    add("nba", "P0", "points", 24.5, 29.5, 30.0, category="likely")          # the same pick in another book
    add("nba", "Team", "spread", -3.5, -6.0, 10.0)                            # a game bet
    add("nba", "Joel Embiid", "anytime_td", 0.5, 0.4, 1.0)                   # a yes-or-no market
    add("nba", "Open Guy", "points", 20.5, 25.0, None, status="open")          # not finished
    add("wnba", "Bench", "points", 15.5, 18.0, 19.0)                          # the bench
    add("nfl", "Gibbs", "rush_yds", 70.5, 80.0, 90.0)
    conn.executemany(ins, rows)
    conn.commit()
    return conn


def test_the_record_counts_how_often_our_number_beat_the_line():
    from engine import ledger
    conn = _journal()
    nba = ledger.number_vs_line(conn, "nba")
    assert (nba["picks"], nba["closer"], nba["farther"], nba["level"]) == (22, 11, 10, 1), nba
    assert nba["by_market"] == {}, "a market is listed on its own once twenty of its picks have finished"
    real = ledger.NUMBER_MARKET_MIN
    try:
        ledger.NUMBER_MARKET_MIN = 10
        assert ledger.number_vs_line(conn, "nba")["by_market"] == {"points": [8, 12], "rebounds": [3, 10]}
    finally:
        ledger.NUMBER_MARKET_MIN = real
    pooled = ledger.number_vs_line(conn)
    assert pooled["picks"] == 23 and pooled["closer"] == 12, ("the bench stays off the pooled figure", pooled)
    assert ledger.number_vs_line(conn, "nba", since="2026-11-16")["picks"] == 0
    assert {"number_vs_line", "number_vs_line_by_sport"} <= set(ledger.RECORD_PAGE_ONLY)
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert '"number_vs_line": number_vs_line(conn, since=since),' in src
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert ("+ recNumberSection(scoped ? (d.number_vs_line_by_sport || {})[scope] : d.number_vs_line, "
            "scoped ? scope : \"\")") in rec
    assert "function recNumberSection(x, scope) {" in rec and "Our number against the line" in rec


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
