"""The game report colours its numbers good and bad (2026-11-15).

Ethan, circling "(3rd in the league)" and "(28th)" in the short version:
"We should also be giving these numbers green and red colors too, like if
it's good, then green, if it's bad, then red ... go through the whole game
report and all that and kind of add those features to make it easier to
read." So, in every league's report (js/report.js painted/goodPaint,
engine/gamereport "rank_of" and the red zone's marks):

  * a rank in a sentence is green in the league's top third and red in its
    bottom third, 1st the best — "(4th in the league)", "(22nd)", "ranks
    27th", "(13th of 49 running backs)" against its own 49, "the league's
    5th-ranked pass rush", "the eighth-worst rate", "the third-best";
  * a rank with no good or bad side of its own stays plain ("8th-most
    plays", "the third-highest total", "3rd-down rate", "bats 1st");
  * what a defense gives up is coloured for the defense: "gives up the
    second-most points" red, "the sixth-fewest" green, the near third only;
  * a result (W green, L red), a goalie's form against expected goals, a
    lineup against tonight's hand, the rest edge, a back-to-back's second
    night and a tired bullpen, and basketball's rest in the facts list
    ("rested" green there alone);
  * a name with initials ("Amon-Ra St. Brown (WR):") keeps its bold
    lead-in like every other;
  * the red zone's "more than an average team" green for an offense, and
    "more than an average defense" red for the defense allowing it;
  * a table's cells keep their table's own ranks (`rankCell`) and nothing
    else, so NBA pace and a table with no league size stay plain;
  * and the key at the top says it once: green is good for the team or
    player it's about, red is bad.

    python3 tests/test_the_report_colours_its_numbers.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R                                   # noqa: E402

REPORT_JS = ROOT / "web" / "js" / "report.js"


def _node(script):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;"
            "const rep = (of, blocks) => ({game: 'G', minutes: 1, rank_of: of,"
            " sections: [{key: 's', title: 'S', blocks}]});"
            "const card = (h) => h.slice(h.indexOf('gr-card'));"
            "const lines = (of, texts) => texts.map((t) => card(R.html(rep(of, [{type: 'note', text: t}]), {}))"
            "  .replace(/^[\\s\\S]*?<p class=\"gr-note\">/, '').replace(/<\\/p>[\\s\\S]*$/, ''));")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _up(w):
    return f'<span class="gr-rank up">{w}</span>'


def _down(w):
    return f'<span class="gr-rank down">{w}</span>'


def test_a_rank_in_a_sentence_takes_its_leagues_thirds():
    texts = ["GB's passing game (4th in the league) faces DET's pass defense (22nd).",
             "DET's pass protection (14th) holds.",
             "Cubs' bullpen ranks 27th; Phillies' bullpen ranks 6th.",
             "GB's offense (30th in the league; 5th this season alone) ranks 30th (13th this season alone).",
             "0.53 more rushing yards a carry than expected (13th of 49 running backs).",
             "DET's run defense (24th, allowing 3.4 a carry); IU's (12th in the country).",
             "GB's pass protection loses a starter against the league's 5th-ranked pass rush.",
             "54% of its trips (the eighth-worst rate in the league); 80% (the third-best); the best rate in the league."]
    got = _node(f"process.stdout.write(JSON.stringify(lines(32, {json.dumps(texts)})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    a, b, c, d, e, f, g, h = got
    assert f"({_up('4th')} in the league)" in a and f"({_down('22nd')})" in a, a
    assert "(14th)" in b and "gr-rank" not in b, "the middle third is plain"
    assert f"ranks {_down('27th')}" in c and f"ranks {_up('6th')}" in c, c
    assert (f"({_down('30th')} in the league; {_up('5th')} this season alone) ranks {_down('30th')} "
            "(13th this season alone)") in d, d
    assert f"({_up('13th')} of 49 running backs)" in e, "judged against its own 49: 13th is in the top 17"
    assert f"({_down('24th')}, allowing 3.4 a carry)" in f, f
    assert f"the league&#39;s {_up('5th')}-ranked pass rush" in g, g
    assert f"(the {_down('eighth-worst')} rate" in h and f"(the {_up('third-best')})" in h, h
    assert f"the {_up('best')} rate in the league" in h, h


def test_a_rank_with_no_good_side_stays_plain():
    texts = ["DET runs the 8th-most plays; the third-highest total of the week.",
             "Each cell shows the number and its rank (1st is best).",
             "Bats 1st — the most trips to the plate. A 1st-rounder on 3rd-down rate.",
             "BOS shoots the 11th-fewest a game and gets the third-most targets."]
    got = _node(f"process.stdout.write(JSON.stringify(lines(32, {json.dumps(texts)})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert all("gr-rank" not in x and "gr-mark" not in x for x in got), got


def test_a_rank_needs_a_league_size():
    texts = ["DET's pass defense (22nd) against a back (13th of 49 running backs)."]
    got = _node(f"process.stdout.write(JSON.stringify(lines(0, {json.dumps(texts)})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert "(22nd)" in got[0], "no league size, no colour"
    assert f"({_up('13th')} of 49" in got[0], "a rank that says its own field keeps it"


def test_what_a_defense_gives_up_is_coloured_for_the_defense():
    texts = ["True for every GB player below: DET gives up the most passing yards (320 a game).",
             "MIA's defense gives up the second-most points; BOS allows the sixth-fewest; GB gave up the fewest.",
             "TOR allows the 5th-most shots, and DET gives up the 15th-most yards."]
    got = _node(f"process.stdout.write(JSON.stringify(lines(32, {json.dumps(texts)})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    a, b, c = got
    assert f"DET gives up the {_down('most')} passing yards" in a, a
    assert f"gives up the {_down('second-most')} points" in b and f"allows the {_up('sixth-fewest')}" in b, b
    assert f"gave up the {_up('fewest')}" in b, b
    assert f"allows the {_down('5th-most')} shots" in c and "the 15th-most yards" in c, "the middle stays plain"


def test_results_goalies_lineups_and_rest_have_their_sides():
    texts = ["Packers' last game: W 23-13 vs DAL.", "Lions' last 3 games: L 21-45 at ARI; T 20-20 vs CHI.",
             "Jeremy Swayman has let in 3.4 more goals than expected lately; Stolarz has stopped 4.2 more goals than expected.",
             "PHI's lineup hits right-handed pitching 5% better than its average; CHC 3% worse than its average; NYY about its average.",
             "DET has the rest edge: 14 days to GB's 7.",
             "Heat: on the second night of a back-to-back. The Cubs' bullpen is tired: it threw 7.1 innings."]
    got = _node(f"process.stdout.write(JSON.stringify(lines(30, {json.dumps(texts)})));")
    if got is None:
        print("      (skipped: no Node)")
        return
    w, l, g, lin, rest, tired = got
    up = lambda x: f'<span class="gr-mark up">{x}</span>'          # noqa: E731
    down = lambda x: f'<span class="gr-mark down">{x}</span>'      # noqa: E731
    assert up("W 23-13") + " vs DAL" in w, w
    assert down("L 21-45") + " at ARI" in l and "T 20-20 vs CHI" in l and l.count("gr-mark") == 1, l
    assert down("let in 3.4 more goals than expected") in g and up("stopped 4.2 more goals than expected") in g, g
    assert up("5% better than its average") in lin and down("3% worse than its average") in lin, lin
    assert "about its average" in lin and lin.count("gr-mark") == 2, lin
    assert up("the rest edge") in rest, rest
    assert down("the second night of a back-to-back") in tired and down("is tired") in tired, tired


def test_basketball_rest_reads_for_its_team():
    LT = __import__("test_every_league_gets_a_game_report")
    board, meta = LT._nba_board()
    rep = LT._attach(board, "nba", meta=meta)[0]
    facts = next(s for s in rep["sections"] if s["key"] == "facts")
    marks = {k: v for b in facts["blocks"] for k, v in (b.get("marks") or {}).items()}
    assert marks == {"on the second night of a back-to-back": "down", "rested": "up"}, marks
    # Marked by the engine, in the facts alone: "rested" means nothing on its
    # own elsewhere ("for the rested and the tournament-worn alike").
    elsewhere = [k for s in rep["sections"] if s["key"] != "facts" for b in s["blocks"] for k in (b.get("marks") or {})]
    assert "rested" not in elsewhere, elsewhere
    got = _node("process.stdout.write(JSON.stringify(lines(30, ['A first game back, for the rested and the worn alike.'])));")
    if got is not None:
        assert "gr-mark" not in got[0], got


def test_a_name_with_initials_keeps_its_bold_lead_in():
    got = _node("""process.stdout.write(JSON.stringify(R.block({type: 'list', items: [
        'Amon-Ra St. Brown (WR): 43% to score.', 'D.J. Reed (LCB): soft.', 'DET by 3. The rest: of it.']})));""")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert '<b class="gr-lead">Amon-Ra St. Brown (WR):</b> 43% to score.' in got, got
    assert '<b class="gr-lead">D.J. Reed (LCB):</b> soft.' in got, got
    assert "<li>DET by 3. The rest: of it.</li>" in got, "a sentence that ends on a number is no label"


def test_a_tables_cells_keep_their_own_ranks():
    got = _node("""const h = card(R.html(rep(30, [
        {type: 'table', rank_of: 30, rank_skip: ['Pace'], head: ['', 'BOS', 'MIA'],
         rows: [['Pace', '101.2 (1st)', '96.0 (30th)'], ['Rating', '118.0 (2nd)', '108.5 (27th)']]},
        {type: 'table', head: ['', 'BOS'], rows: [['Goals', '3.60 (3rd)'], ['Last', 'W 110-99']]}]), {}));
      process.stdout.write(JSON.stringify(h));""")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert "101.2 (1st)" in got and "96.0 (30th)" in got, "pace is no better or worse, even with the report's size set"
    assert f"118.0 ({_up('2nd')})" in got and f"108.5 ({_down('27th')})" in got
    assert "3.60 (3rd)" in got and "W 110-99" in got, "a table that doesn't say its size stays plain"


def test_the_red_zone_colours_its_than_average():
    T = __import__("test_the_game_report_reads_like_the_research")
    rep = T._report()
    rz = next(s for s in rep["sections"] if s["key"] == "redzone")
    marks = {k: v for b in rz["blocks"] for k, v in (b.get("marks") or {}).items()}
    assert marks.get("9% more than an average team") == "up", marks
    assert marks.get("6% more than an average defense") == "down", marks
    assert "about average" not in marks
    assert "6% more than an average defense" in R.to_text(rep), "the defense says it's a defense"
    CT = __import__("test_the_college_game_report")
    rep = CT._report()[1]
    rz = next(s for s in rep["sections"] if s["key"] == "redzone")
    marks = {k: v for b in rz["blocks"] for k, v in (b.get("marks") or {}).items()}
    assert marks.get("31% fewer than an average defense") == "up", marks
    assert marks.get("22% more than an average team") == "up", marks
    # And the marks never reach the copied words.
    text = R.to_text(rep)
    assert "22% more than an average team" in text and "'up'" not in text and "marks" not in text


def test_every_report_says_its_league_size():
    T = __import__("test_the_game_report_reads_like_the_research")
    assert T._report()["rank_of"] == 32
    LT = __import__("test_every_league_gets_a_game_report")
    assert LT._attach(LT._nhl_board(), "nhl")[0]["rank_of"] == 32
    board, meta = LT._nba_board()
    assert LT._attach(board, "nba", meta=meta)[0]["rank_of"] == 30
    assert LT._attach(LT._mlb_board(), "mlb")[0]["rank_of"] == 30
    CT = __import__("test_the_college_game_report")
    assert CT._report()[1]["rank_of"] == 136, "college football: the teams its ranks are against"
    assert R.TEXT_RANK_OF == {"mlb": 30, "nba": 30, "wnba": 15, "cbb": 365, "nhl": 32}


def test_the_key_names_only_the_colours_drawn():
    got = _node("""const key = (blocks, of) => { const h = R.html(rep(of, blocks), {});
        const i = h.indexOf('class="gr-key"'); return i < 0 ? '' : h.slice(i, h.indexOf('</p>', i)); };
      process.stdout.write(JSON.stringify({
        result: key([{type: 'list', items: ["Packers' last game: W 23-13 vs DAL."]}], 32),
        amber: key([{type: 'list', marks: {questionable: 'warn'}, items: ['Sam LaPorta (TE) — questionable.']}], 32),
        rank: key([{type: 'p', text: "GB's passing game (4th in the league)."}], 32),
        middle: key([{type: 'p', text: "GB's passing game (14th in the league)."}], 32),
        none: key([{type: 'p', text: 'Kickoff: Sunday.'}], 32)}));""")
    if got is None:
        print("      (skipped: no Node)")
        return
    assert "Green</span> is good for the team or player it’s about" in got["result"], got["result"]
    assert "good news for the" in got["result"] and "Green names" not in got["result"]
    assert "green rank" not in got["result"] and "Amber" not in got["result"]
    assert "Amber</span> is a player listed as questionable" in got["amber"] and "is good for" not in got["amber"]
    assert "green rank" in got["rank"] and "bottom third" in got["rank"]
    assert got["middle"] == "" and got["none"] == "", "nothing coloured, no key"


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
                traceback.print_exc(limit=5)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
