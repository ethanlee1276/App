"""A finished game's page says each thing once, and only what is true
(USEREYES1, 18 November 2026).

Walking a finished college game's page the way a member and a visitor see it
found three things: the final score in the page's own header and again at the
head of the "How our report did" card right under it; the locked report's
teaser saying "The game report" as its heading and again as its first words,
under a subtitle that called a game played days ago "tonight's board"; and,
under the final, "Books haven't posted prop prices for this game yet." What
these hold:

  * the game page's card heads itself "How our report did", the score said
    once, in the page's header; an old game's card (its play-by-play page,
    which has no header of its own) still carries the score;
  * the locked teaser names the report once, in its heading, says what it
    holds, and on a finished game says it was written before the game;
  * a finished game with no prop on its board shows no props section at all.

    python3 tests/test_a_finished_games_page_says_each_thing_once.py
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
REPORT_JS = ROOT / "web" / "js" / "report.js"


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_the_cards_head_says_what_it_is_on_the_game_page_and_the_score_elsewhere():
    page = _fn(DETAIL, "gpResultsHTML")
    assert "return gprCard(g, gameReportFor(g), rows, gp, { sport: state.sport, scored: true });" in page
    card = _fn(DETAIL, "gprCard")
    assert 'const score = o.scored ? `<span class="gpr-team">How our report did</span>` : fin.home != null' in card
    # Every other caller (an old game's play-by-play page, the record's game list) passes no `scored`.
    callers = [line for line in DETAIL.splitlines() if "gprCard(" in line and "function gprCard(" not in line]
    assert sum("scored: true" in line for line in callers) == 1, callers


def test_a_finished_game_with_no_props_shows_no_props_section():
    i = DETAIL.index('<div id="gp-sec-props">')
    assert DETAIL[i:i + 80].startswith('<div id="gp-sec-props">${isFinal && !shown.length ? "" : shown.length ? `')
    assert "const isFinal = live.state === \"final\";" in DETAIL


def test_the_locked_teaser_names_the_report_once_and_says_when_it_was_written():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not os.path.exists(node):
        print("      (skipped: no Node)")
        return
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const esc = (s) => String(s == null ? '' : s);"
        "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, slugify: (s) => s, teamName: (t) => t,"
        " playerAvatar: () => '', document: { addEventListener() {} } };"
        "vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
        "const R = ctx.window.QBReport;"
        "process.stdout.write(JSON.stringify([R.html(null, {sport: 'cbb'}),"
        " R.html(null, {sport: 'cbb', results: {final: {home: 80, away: 71}}})]));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    tonight, final = json.loads(out.stdout)
    for teaser in (tonight, final):
        assert teaser.count("The game report") == 1, teaser
        assert '<div class="card ms-locked">What it holds — ' in teaser and "part of the subscription" in teaser
    assert "from tonight’s board" in tonight and "before it started" not in tonight
    assert "the whole game written out before it started" in final and "tonight" not in final, final


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
