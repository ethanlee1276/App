"""A football play in plain words (2026-10-25).

Ethan, on a live NFL game: "look at the play-by-play and look at the field
section where it shows it, because it's kind of buggy and there's some of
the wording that doesn't make sense."

The rows printed ESPN's type label with the yards glued on: "TEN · Pass
Interception Return" (the Titans threw it), "TEN · Kickoff +25" (the
Titans received it), "IND · Timeout" with GAINED 0 YDS under the field
(a timeout credited to the offence and given a yardage), "Punt +9".
app.js `footballWords` is now the one composer, and every place a play is
named reads it. These tests hold the words, the moments that are not
plays, and the repetition the page lost with them.

Run directly: `python3 tests/test_football_plays_read_like_a_person_wrote_them.py`
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
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
DETAIL_CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _piece(head):
    i = APP.index(head)
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n//")]
    return APP[i:min(e for e in ends if e != -1)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([
        "const escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');",
        "const trueMinus = (s) => s;",
        _piece("const FB_PERIOD"), _piece("function footballWords("), _piece("const fbClock"),
        _piece("const PLAYS_EMPTY"), _piece("function hockeyPeriod("), _piece("function playsHTML("),
        _piece("const DRIVE_RESULT"), _piece("function driveResultWord("),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src + "\n" + js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


#: ESPN's label and yards -> what the reader is told. The home side is
#: DAL, so a DAL snap at spot 70 is thirty yards from the goal.
CASES = [
    ({"event": "Rush", "yards": 5}, "Run for 5 yds", True),
    ({"event": "Rush", "yards": 0}, "Run, no gain", True),
    ({"event": "Rush", "yards": -3}, "Run for a loss of 3 yds", True),
    ({"event": "Pass Reception", "yards": 14}, "Pass complete for 14 yds", True),
    ({"event": "Pass Incompletion", "yards": 0}, "Pass incomplete", True),
    ({"event": "Sack", "yards": -6}, "Sacked for a loss of 6 yds", True),
    ({"event": "Passing Touchdown", "yards": 12}, "Touchdown pass, 12 yds", True),
    ({"event": "Rushing Touchdown", "yards": 1}, "Touchdown run, 1 yd", True),
    ({"event": "Pass Interception Return", "yards": 0, "turnover": True}, "Pass intercepted", True),
    ({"event": "Interception Return Touchdown", "yards": 0}, "Intercepted and returned for a touchdown", True),
    ({"event": "Fumble Recovery (Opponent)", "yards": 2, "turnover": True}, "Fumble lost", True),
    ({"event": "Fumble Recovery (Own)", "yards": 3}, "Fumble recovered for 3 yds", True),
    ({"event": "Kickoff", "yards": 25}, "Kickoff, returned 25 yds", True),
    ({"event": "Kickoff", "yards": 0}, "Kickoff", True),
    ({"event": "Kickoff Return Touchdown", "yards": 98}, "Kickoff returned for a touchdown", True),
    # A punt's yards are its RETURN (the real PIT @ NO feed: -3, 0, 20, 13).
    ({"event": "Punt", "yards": 20}, "Punt, returned 20 yds", True),
    ({"event": "Punt", "yards": -3}, "Punt", True),
    # A field goal's yards are the kick's own distance; the spot only fills in.
    ({"event": "Field Goal Good", "yards": 28, "team": "TB", "spot": 10}, "Field goal good, 28 yds", True),
    ({"event": "Field Goal Good", "yards": 0, "team": "DAL", "spot": 70}, "Field goal good, 47 yds", True),
    ({"event": "Field Goal Missed", "yards": 0, "team": "TB", "spot": 35}, "Field goal missed, 52 yds", True),
    ({"event": "Blocked Field Goal", "yards": 0}, "Field goal blocked", True),
    ({"event": "Penalty", "yards": -10}, "Penalty on the offense, 10 yds", True),
    ({"event": "Penalty", "yards": 5}, "Penalty on the defense, 5 yds", True),
    # A flag on a field-goal try carries the try's distance (4th & 3 at the 19: 37).
    ({"event": "Penalty", "yards": 37, "down": 4, "team": "TB", "spot": 19}, "Penalty on the field-goal try", True),
    ({"event": "Safety", "yards": 0}, "Safety", True),
    ({"event": "Timeout", "yards": 0}, "Timeout", False),
    ({"event": "End Period", "yards": 0, "period": 1}, "End of the 1st quarter", False),
    ({"event": "End of Half", "yards": 0}, "Halftime", False),
    ({"event": "End of Game", "yards": 0}, "Final", False),
    ({"event": "Two-minute warning", "yards": 0}, "Two-minute warning", False),
]


def test_every_play_type_reads_as_a_sentence_a_person_would_say():
    got = _node(f"""
      const g = {{home: "DAL", away: "TB"}};
      console.log(JSON.stringify({json.dumps([c[0] for c in CASES])}.map((p) => footballWords(p, g))));""")
    if got is None:
        print("  SKIP node not installed")
        return
    for (play, want, snap), w in zip(CASES, got):
        assert w["title"] == want, (play, w["title"], want)
        assert w["snap"] is snap, (play, w)
        # A moment in the game carries no team: nobody "did" a quarter's end,
        # and the feed does not say which side called a timeout.
        assert w["team"] is snap, (play, w)


def test_a_tv_timeout_is_not_a_row_at_all():
    got = _node("""
      console.log(JSON.stringify([footballWords({event: "Official Timeout"}, {}),
        playsHTML({home: "DAL", away: "TB", plays: [{kind: "football", event: "Official Timeout", team: "DAL", period: 1, clock: "5:21"}]})]));""")
    if got is None:
        print("  SKIP node not installed")
        return
    assert got[0]["quiet"] is True and got[0]["snap"] is False
    assert '<div class="lb-play' not in got[1].replace('<div class="lb-plays">', ""), \
        "twelve of them in one game, and none says anything"


def test_a_timeout_row_names_nobody_and_carries_no_yards_or_down():
    got = _node("""
      const rows = playsHTML({home: "DAL", away: "TB", plays: [
        {kind: "football", event: "Timeout", team: "DAL", period: 2, clock: "00:24", down: 3, distance: 16, yards: 0,
         away_score: 0, home_score: 10},
        {kind: "football", event: "Pass Interception Return", team: "TB", period: 2, clock: "02:00", down: 1,
         distance: 10, yards: 0, turnover: true, away_score: 0, home_score: 10},
        {kind: "football", event: "Field Goal Good", team: "DAL", spot: 70, period: 2, clock: "02:09", down: 4,
         distance: 2, yards: 0, scoring: true, away_score: 0, home_score: 10}]});
      console.log(JSON.stringify(rows));""")
    if got is None:
        print("  SKIP node not installed")
        return
    moment = got.split('<div class="lb-play ')[1]
    assert "lb-moment" in moment and "Timeout" in moment
    assert "DAL" not in moment and "3rd" not in moment and "0–10" not in moment
    assert "Q2 0:24" in moment, "the clock as a scoreboard writes it"
    assert "Pass intercepted" in got and "Interception Return" not in got
    assert ">Turnover<" in got and ">TO<" not in got, "a word, not an abbreviation"
    assert "Field goal good, 47 yds" in got and ">FG<" in got
    # The score rides on the play that changed it, not on every row.
    assert got.count("lb-pscore") == 1


def test_drive_heads_say_how_the_drive_ended():
    got = _node("""
      console.log(JSON.stringify(["Field Goal", "Downs", "Missed FG", "Touchdown", "", "INT"].map(
        (r) => driveResultWord({result: r}))));""")
    if got is None:
        print("  SKIP node not installed")
        return
    assert got == ["Field goal", "Turnover on downs", "Missed field goal", "Touchdown", "", "Interception"]
    body = _piece("function pbpGroups(")
    assert "driveResultWord(dr)" in body, "the rail's heads read the summary's own ending"
    assert "driveResultWord" in GC, "and so does the Play-by-play tab"


def test_the_photograph_and_the_last_play_card_keep_the_last_real_snap():
    assert 'r.kind === "football" && footballWords(r, d).snap' in DETAIL
    assert "find((p) => isSnap(p, d))" in GC, "the card titles the last snap"
    assert "sinceSnap(d, p)" in GC and "gc-last-since" in GC, "and names the moments after it under it"
    assert '" · penalty"' not in GC


def test_a_finished_game_says_final_whatever_the_file_froze_at():
    """PIT @ NO in London, 2026-10-25: the deep file's last write held the
    scoreboard at "Q4 0:34, live" under a play list ending "End of Game"."""
    assert 'const fast = (strip || []).find((g) => String(g.event_id) === String(event));' in DETAIL
    assert '((d.plays || []).slice(-1)[0] || {}).event === "End of Game"' in DETAIL
    assert 'state: "final", period: "Final", clock: "", detail: "",' in DETAIL
    assert "win_prob: undefined" in DETAIL, "no 99.9% with 0:34 left on a final"
    # …and before `lv` is read, so the header, the board and the gamecast all see it.
    assert DETAIL.index("const ended = ") < DETAIL.index("const lv = d.live || {};\n  const mark = ")


def test_a_punt_is_not_drawn_flying_its_return():
    assert 'const fly = kind === "fg" || word === "NO GOOD" ? (dir > 0 ? 110 : -10) : null;' in GC
    assert 'word === "PUNT" && gain >= 15' not in GC


def test_the_repeated_pieces_are_gone_on_a_phone():
    # One play list: the gamecast's tab, not the rail's copy under it.
    assert '"" : " pbp-has-tabs"' in DETAIL
    assert "@media (max-width: 980px) { .pbp-has-tabs .pbp-railcard { display: none; } }" in DETAIL_CSS
    # The club's short name where "Indianapolis Colts" ran into its score.
    assert 'class="pbp-nm-nick"' in DETAIL and ".pbp-hero .pbp-nm-full { display: none; }" in DETAIL_CSS
    assert '(league === "cfb" && t.loc) || t.nick' in DETAIL, "a college by its school"
    # The row's team class is its own: .lb-team is the Live card's column.
    assert ".lb-play .lb-side" in STYLES and 'class="lb-side"' in APP


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
