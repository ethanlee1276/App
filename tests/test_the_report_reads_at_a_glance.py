"""The game report reads at a glance (2026-11-15).

Ethan, after the names in "who gets the ball" were coloured: "Make the game
report less confusing too I liked the names colored it made it easier to
read". So, in every league's report (engine/gamereport.color_names,
mark_statuses; js/report.js):

  * a player with a read in this game is coloured the same in every section
    that names him: the short version, how each team plays, who's guarding
    who, the red zone, the scripts, the players to watch, the parlays —
    green for a breakout candidate or a favorable matchup, red for an
    unfavorable one;
  * a table's ranks are green in the league's top third and red in its
    bottom third, where 1st is the best (NBA pace, no better or worse at
    either end, stays plain; the scale was quarters until 2026-11-15, when
    the sentences' ranks were coloured too — test_the_report_colours_its_numbers);
  * the injury list's words are coloured: out and doubtful red, questionable
    amber;
  * a line's lead-in ("Who gets the targets:", "Kickoff:") is bold, so its
    subject stands out;
  * one key at the top says what the colours mean;
  * and the lines that read worst say it plainly: "True for every GB player
    below", the soft-spot corner said once, the red zone's names first, and
    "the touchdown matchup" where a scorer's line means touchdowns.

    python3 tests/test_the_report_reads_at_a_glance.py
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


def _research():
    import test_the_game_report_reads_like_the_research as T
    return T


def _leagues():
    import test_every_league_gets_a_game_report as LT
    return LT


def _sec(rep, key):
    return next((s for s in rep["sections"] if s["key"] == key), None)


def test_a_player_wears_his_colour_in_every_section_that_names_him():
    rep = _research()._report()
    seen: dict = {}
    for s in rep["sections"]:
        for b in s["blocks"]:
            for name, v in (b.get("names") or {}).items():
                seen.setdefault(name, set()).add((v["tone"], v["label"]))
                seen.setdefault(("where", name), set()).add(s["key"])
    assert all(len(v) == 1 for k, v in seen.items() if not isinstance(k, tuple)), "one colour a player"
    gibbs = seen[("where", "Jahmyr Gibbs")]
    assert {"short", "identity", "matchups", "redzone", "scripts", "watch"} <= gibbs, gibbs
    assert seen["Matthew Golden"] == {("down", "Unfavorable matchup")}
    assert ("where", "Brock Wright") in seen, "the scorer list names him, so it colours him"


def test_every_league_colours_its_named_players():
    LT = _leagues()
    board = LT._nhl_board()
    rep, _ = LT._attach(board, "nhl")
    names = {n: v["tone"] for s in rep["sections"] for b in s["blocks"] for n, v in (b.get("names") or {}).items()}
    assert names.get("Auston Matthews") == "up" and names.get("David Pastrnak") == "down", names
    board, meta = LT._nba_board()
    board["scan_reads"] = {"MIA@BOS": {"players": [
        LT._read("Bam Adebayo", "MIA", "BOS", "C", "breakout", "Breakout spot"),
        LT._read("Jayson Tatum", "BOS", "MIA", "F", "avoid", "Avoid")]}}
    rep, _ = LT._attach(board, "nba", meta=meta)
    carry = [b for b in _sec(rep, "carry")["blocks"] if b["type"] == "players"]
    assert carry[0]["names"] == {"Bam Adebayo": {"tone": "up", "label": "Breakout candidate"}}
    assert any("Bam Adebayo" in (b.get("names") or {}) for b in _sec(rep, "watch")["blocks"])


def test_the_injury_words_are_marked_in_the_injury_list_alone():
    rep = _research()._report()
    inj = _sec(rep, "injuries")
    marks = [b.get("marks") for b in inj["blocks"] if b["type"] == "list"]
    assert {"out": "down"} in marks and {"questionable": "warn"} in marks, marks
    assert all("marks" not in b for b in inj["blocks"] if b["type"] != "list"), "a sentence's 'out' is no status"
    # Other sections mark their own words (the red zone's "than an average
    # team"), never a status.
    assert not [k for s in rep["sections"] if s["key"] != "injuries" for b in s["blocks"]
                for k in (b.get("marks") or {}) if k in R.STATUS_TONE], \
        "'the inactive list comes out' is no status either"


def test_the_rank_tables_say_their_league_size():
    rep = _research()._report()
    tables = [b for b in _sec(rep, "rankings")["blocks"] if b["type"] == "table"]
    assert tables and all(b.get("rank_of") == 32 for b in tables)
    LT = _leagues()
    nhl, _ = LT._attach(LT._nhl_board(), "nhl")
    tape = next(b for b in _sec(nhl, "tape")["blocks"] if b["type"] == "table")
    assert tape["rank_of"] == 32
    src = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert '"rank_skip": [r["label"] for r in rows if r.get("plain")]' in src, "NBA pace stays plain"


def test_the_lines_that_read_worst_say_it_plainly():
    rep = _research()._report()
    text = R.to_text(rep)
    assert "True for every GB player below: DET gives up the most passing yards (320 a game)." in text
    assert "For all of" not in text
    # The soft spot is said once; the corners' line names the others.
    assert text.count("D.J. Reed (LCB) — 126.5 passer rating") == 1
    assert "DET's other corners: Roger McCreary (NB)" in text
    assert text.count("Brandon Cisse (RCB) — 142.8 passer rating") == 1 and "GB's corners:" not in text
    # 2026-11-15 ("we should be going of the actual factual numbers and not
    # 'our numbers'"): the red zone says this game's plays from the two units'
    # rates, and a player's counts where the play-by-play has them
    # (tests/test_the_red_zone_says_the_counts).
    assert ("GB runs about 10 plays a game inside the opponent's 20 (9% more than an average team); DET's defense "
            "allows about 9.8 (6% more than an average defense). Both are adjusted for the teams they've played. "
            "This game: about 10.6 for GB.") in text
    assert "by our numbers" not in text
    assert "GB allows the second-most touchdowns to running backs; the touchdown matchup backs him." in text
    assert "; the matchup backs him" not in text


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
            "const R = ctx.window.QBReport;")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_page_draws_lead_ins_ranks_and_injury_words():
    got = _node("""const B = R.block; process.stdout.write(JSON.stringify({
      lead: B({type: 'list', items: ['Kickoff: Sunday, Oct. 25, 4:25 PM ET.',
        'The inactive list comes out about 2:55 PM ET, 90 minutes before kickoff.',
        'DET favored. The rest: of it.',
        'A lead-in that runs far too long to be a label at all, past sixty characters: then the rest.']}),
      para: B({type: 'p', text: 'The line: DET by 3 at home, total 52.5.'}),
      note: B({type: 'note', text: 'Note: a quiet one.'}),
      ranks: B({type: 'table', rank_of: 32, rank_skip: ['Pace'], head: ['', 'GB', 'DET'], rows: [
        ['Pass EPA', '+0.19 · 4th', '+0.19 · 22nd'], ['Rush EPA', '−0.18 · 30th', '44% · 14th'],
        ['Goals', '3.60 (3rd)', '2.10 (32nd)'], ['Pace', '101.2 (1st)', '96.0 (30th)'], ['Run rate', '34%', '39%']]}),
      plain: B({type: 'table', head: ['', 'GB'], rows: [['Pass EPA', '+0.19 · 4th']]}),
      injury: B({type: 'list', marks: {out: 'down', questionable: 'warn'},
        items: ['Zach Tom (T) — out. GB is without its right tackle.', 'Sam LaPorta (TE) — questionable.']})}));""")
    if got is None:
        print("      (skipped: no Node)")
        return
    lead = got["lead"]
    assert '<li><b class="gr-lead">Kickoff:</b> Sunday, Oct. 25, 4:25 PM ET.</li>' in lead
    assert "<li>The inactive list comes out about 2:55 PM ET" in lead, "a clock is no lead-in"
    assert "<li>DET favored. The rest: of it.</li>" in lead, "a sentence before the colon is no label"
    assert lead.count("gr-lead") == 1, "a long first clause is no label either"
    assert got["para"].startswith('<p class="gr-p"><b class="gr-lead">The line:</b> DET by 3')
    assert "gr-lead" not in got["note"], "the notes stay quiet"
    r = got["ranks"]
    # Thirds of the league since 2026-11-15: 1st-11th green, 22nd-32nd red.
    assert '+0.19 · <span class="gr-rank up">4th</span>' in r and '+0.19 · <span class="gr-rank down">22nd</span>' in r
    assert '−0.18 · <span class="gr-rank down">30th</span>' in r and "44% · 14th" in r
    assert '3.60 (<span class="gr-rank up">3rd</span>)' in r and '2.10 (<span class="gr-rank down">32nd</span>)' in r
    assert "101.2 (1st)" in r and "96.0 (30th)" in r, "pace is no better or worse"
    assert "gr-rank" not in got["plain"], "only a table that says its league's size"
    inj = got["injury"]
    assert '— <span class="gr-mark down">out</span>. GB is without its right tackle.' in inj
    assert '— <span class="gr-mark warn">questionable</span>.' in inj and inj.count("gr-mark") == 2, \
        "'without' is no 'out'"


def test_one_key_at_the_top_and_none_where_nothing_is_coloured():
    rep = _research()._report()
    # The weather colours nothing (the facts do since 2026-11-15: a last
    # game's W is green — test_the_report_colours_its_numbers).
    bare = {**rep, "sections": [s for s in rep["sections"] if s["key"] == "weather"]}
    assert bare["sections"] and all(s["blocks"] for s in bare["sections"]), "a bare report still has words"
    got = _node(f"const rep = {json.dumps(rep, ensure_ascii=False)}; const bare = {json.dumps(bare, ensure_ascii=False)};"
                "process.stdout.write(JSON.stringify({full: R.html(rep, {}), bare: R.html(bare, {}),"
                " text: R.toText(rep, '')}));")
    if got is None:
        print("      (skipped: no Node)")
        return
    full = got["full"]
    assert full.count('class="gr-key"') == 1
    key = full[full.index('class="gr-key"'):full.index("</p>", full.index('class="gr-key"'))]
    assert "Green names" in key and "red names" in key and "green rank" in key and "bottom third" in key
    assert full.index('class="gr-key"') < full.index('id="gr-short"'), "before the first section"
    assert 'class="gr-key"' not in got["bare"], "a report with nothing coloured has no key"
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in full, bad
    # The copied report is words: no colour, no bold.
    assert "<" not in got["text"] and "gr-" not in got["text"]


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
