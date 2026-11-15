"""The game report colours who gets the ball by his matchup read (2026-11-15).

Ethan circled DET's "Who gets the ball thrown to him" line on the NE-DET
report: "Also in this section, when we talk about player that get the ball,
we can make the letters of there name green or red depending on in they are
a breakout or favorite candidate or a unfavorable matchup". So
(engine/gamereport.NAME_TONE, name_tones; js/report.js):

  * every line that says who gets the ball — who gets the targets (who
    catches it, in college), who carries it, who gets the chances inside
    the 20 — carries its players' reads, and the page draws a breakout
    candidate or a favorable matchup in green, an unfavorable matchup in
    red and a neutral one plain; each name opens the player's page;
  * basketball's "Who carries each team" cards (NBA, WNBA, college) do the
    same;
  * a player ruled out or doubtful has no read on the page, so his name is
    never coloured;
  * a key under the section's title says what the colours mean, and the
    copied report stays words alone.

    python3 tests/test_the_report_colours_who_gets_the_ball.py
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
import test_the_game_report_reads_like_the_research as T             # noqa: E402
import test_every_league_gets_a_game_report as LT                    # noqa: E402

REPORT_JS = ROOT / "web" / "js" / "report.js"
REPORT_CSS = ROOT / "web" / "css" / "report.css"


def _sec(rep, key):
    return next(s for s in rep["sections"] if s["key"] == key)


def test_the_colour_follows_the_read():
    assert {k: v[0] for k, v in R.NAME_TONE.items()} == {
        "breakout": "up", "good": "up", "neutral": "", "tough": "down", "avoid": "down"}
    assert R.NAME_TONE["breakout"][1] == "Breakout candidate" and R.NAME_TONE["tough"][1] == "Unfavorable matchup"


def test_the_lines_that_say_who_gets_the_ball_carry_their_players_reads():
    rep = T._report()
    gb, det = [b for b in _sec(rep, "identity")["blocks"] if b["type"] == "list"]
    assert "Who gets the targets: Christian Watson (WR) 21% of the targets" in gb["items"][1]
    assert gb["names"] == {"Christian Watson": {"tone": "up", "label": "Favorable matchup"},
                           "Matthew Golden": {"tone": "down", "label": "Unfavorable matchup"}}
    assert det["names"]["Jahmyr Gibbs"] == {"tone": "up", "label": "Breakout candidate"}, \
        "he is in both the targets and the carries lines"
    assert det["names"]["Amon-Ra St. Brown"] == {"tone": "", "label": "Neutral matchup"}
    assert "Brock Wright" not in det["names"], "6% of the targets is under the tree's floor: not in the line"
    rz = _sec(rep, "redzone")["blocks"][0]
    assert (rz["names"]["Matthew Golden"]["tone"], rz["names"]["Jahmyr Gibbs"]["tone"]) == ("down", "up")
    # The scorer lists say in words what backs each scorer; they stay plain.
    assert all("names" not in b for b in _sec(rep, "redzone")["blocks"][1:])
    # A block that names nobody carries nothing, and the reading time
    # counts words, not colours.
    assert all("names" not in b for b in _sec(rep, "facts")["blocks"])
    assert R._words([{"type": "list", "items": [], "names": {"A B": {"tone": "up", "label": "x y z"}}}]) == 0


def test_a_player_who_will_not_play_is_never_coloured():
    board = T._board()
    board["games"][0]["scan"]["injuries"].append(
        {"team": "GB", "player": "Matthew Golden", "position": "WR", "status": "OUT"})
    c = R.Ctx(board["games"][0], board, names=T.NAMES)
    assert R.name_tones(c, "GB", ["Matthew Golden", "Christian Watson"]) == {
        "Christian Watson": {"tone": "up", "label": "Favorable matchup"}}
    rep = R.build(board["games"][0], board, allowed=T.ALLOWED, names=T.NAMES)
    gb = [b for b in _sec(rep, "identity")["blocks"] if b["type"] == "list"][0]
    assert "Matthew Golden" not in json.dumps(gb)
    # The other team's reads never colour this team's names.
    assert R.name_tones(c, "DET", ["Christian Watson"]) == {}


def _nba(sport):
    board, meta = LT._nba_board()
    board["scan_reads"] = {"MIA@BOS": {"players": [
        LT._read("Bam Adebayo", "MIA", "BOS", "C", "breakout", "Breakout spot"),
        LT._read("Jayson Tatum", "BOS", "MIA", "F", "avoid", "Avoid"),
        LT._read("Tyler Herro", "MIA", "BOS", "G", "good", "Good matchup")]}}
    if sport == "cbb":
        board["board_games"] = ["MIA@BOS"]            # college writes the games it prices
    rep, _line = LT._attach(board, sport, meta=meta)
    return [b for b in _sec(rep, "carry")["blocks"] if b["type"] == "players"]


def test_basketball_colours_who_carries_each_team():
    for sport in ("nba", "wnba", "cbb"):
        mia, bos = _nba(sport)
        assert mia["names"] == {"Bam Adebayo": {"tone": "up", "label": "Breakout candidate"}}, (sport, mia)
        assert bos["names"] == {"Jayson Tatum": {"tone": "down", "label": "Unfavorable matchup — avoid"}}, \
            (sport, bos, "Jaylen Brown has no read: no colour")


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


def _section_html(full, key):
    i = full.index(f'id="gr-{key}"')
    return full[i:full.index("</section>", i)]


def test_the_page_colours_each_name_opens_his_page_and_keys_the_colours():
    rep = T._report()
    got = _node(f"const rep = {json.dumps(rep, ensure_ascii=False)};"
                "process.stdout.write(JSON.stringify({full: R.html(rep, {}), text: R.toText(rep, '')}));")
    if got is None:
        print("      (skipped: no Node)")
        return
    ident = _section_html(got["full"], "identity")
    assert ('<span class="gr-name up" data-open="player:christian-watson" title="Favorable matchup">'
            'Christian Watson<span class="gr-sr"> (favorable matchup)</span></span> (WR) 21% of the targets') in ident
    assert '<span class="gr-name down" data-open="player:matthew-golden" title="Unfavorable matchup">' in ident
    assert '<span class="gr-name up" data-open="player:jahmyr-gibbs" title="Breakout candidate">' in ident
    # A neutral read: his page opens, no colour, nothing hidden said.
    assert ('<span class="gr-name" data-open="player:amon-ra-st-brown" title="Neutral matchup">'
            'Amon-Ra St. Brown</span>') in ident
    # The key, once, under the title of each section that colours a name —
    # in words that fit every league's players.
    assert ident.count("gr-name-key") == 1 and ident.index("gr-name-key") < ident.index("gr-h")
    assert "tap a name to open the player’s page" in ident and " his page" not in ident
    assert _section_html(got["full"], "redzone").count("gr-name-key") == 1
    assert "gr-name" not in _section_html(got["full"], "facts")
    # The copied report is words.
    assert "gr-name" not in got["text"] and "<span" not in got["text"]
    assert "Who gets the targets: Christian Watson (WR) 21% of the targets" in got["text"]


def test_a_name_is_marked_only_where_it_stands_whole():
    up, down = {"tone": "up", "label": "Breakout candidate"}, {"tone": "down", "label": "Avoid"}
    got = _node("const b = (items, names) => R.block({type: 'list', items, names});"
                "process.stdout.write(JSON.stringify(["
                " b(['Josh Allenby runs; Josh Allen throws'], {'Josh Allen': " + json.dumps(up) + "}),"
                " b(['Mike Williams Jr. (WR) and Mike Williams (WR)'], {'Mike Williams': " + json.dumps(up)
                + ", 'Mike Williams Jr.': " + json.dumps(down) + "}),"
                " b([\"Ja'Marr Chase (WR) 28% of the targets\"], {\"Ja'Marr Chase\": " + json.dumps(up) + "}),"
                " b(['Nobody named'], {}),"
                " R.block({type: 'players', names: {'Bam Adebayo': " + json.dumps(up) + "},"
                "   items: [{player: 'Bam Adebayo', team: 'MIA'}, {player: 'Bench Guy', team: 'MIA'}]})]));")
    if got is None:
        print("      (skipped: no Node)")
        return
    allen, williams, chase, plain, cards = got
    assert allen.count("gr-name") == 1 and "Josh Allenby runs" in allen
    assert allen.index("gr-name") > allen.index("Allenby"), "the whole name, not the start of a longer word"
    assert williams.count('class="gr-name down"') == 1 and williams.count('class="gr-name up"') == 1
    assert 'title="Avoid">Mike Williams Jr.' in williams, "the longer name wins where both fit"
    assert 'data-open="player:ja-marr-chase"' in chase and "Ja&#39;Marr Chase<span" in chase
    assert plain == '<ul class="gr-list"><li>Nobody named</li></ul>'
    assert '<b class="gr-name up" title="Breakout candidate">Bam Adebayo' in cards
    assert "<b>Bench Guy</b>" in cards, "no read, no colour"


def test_the_colours_are_the_sites_own_good_and_bad():
    css = REPORT_CSS.read_text(encoding="utf-8")
    assert ".gr-name.up { color: var(--good); }" in css and ".gr-name.down { color: var(--bad); }" in css
    assert ".gr-name[data-open] { cursor: pointer; }" in css
    assert ".gr-sr { position: absolute; width: 1px; height: 1px;" in css, "said to a screen reader, not drawn"


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
