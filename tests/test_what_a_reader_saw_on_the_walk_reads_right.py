"""What a reader saw on the walk reads right (USEREYES1, 18 November 2026).

Walking the paywall, the Streak, hockey's Tonight, the college basketball
Record page and Zeno's page as a reader:

  * the Streak said "undefined day streak · best undefined" when the
    account's streak came back empty, and "Picks lock at first pitch" over a
    slate of college football receptions;
  * hockey's empty Tonight said "Kickoff 7:00 PM" (every league without its
    own word fell through to football's);
  * the paywall's newest fact-check said "We called the Villanova at 55%",
    the plan card said "Billed monthly. Cancel anytime." under the price and
    again under its button, and "+0.40 average closing-line value" never
    said +0.40 of what;
  * the Record page called college basketball "CBB" in its tabs, its week
    and a dozen chips, where every other page says NCAAB; drew "Combined ·
    edge + Most Likely boards 0-1" right under "Most Likely 0-1" for a
    league with no Edge bet settled; and said "graded once their games are
    final" under two tiles side by side;
  * Zeno's page labelled Sep 21–27 "This week" in November.

What these hold:

  * the Streak counts from 0 and every pick locks when its own game starts;
  * hockey says puck drop; football still says kickoff;
  * a school or a fighter is called by name ("We called Villanova"), a club
    with its article ("We called the Timberwolves");
  * the billing line is said once on a plan without a trial; the closing
    line's value says its unit;
  * every league label on the Record page is the strip's (NCAAB); the
    combined ribbon is left out when it is the Most Likely ribbon again; the
    riding tile alone says when picks grade;
  * a carried-in week is "This week" only while it is, then "Week of".

    python3 tests/test_what_a_reader_saw_on_the_walk_reads_right.py
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
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
ACCOUNT = (JS / "account.js").read_text(encoding="utf-8")
RECORD = (JS / "record.js").read_text(encoding="utf-8")
NODE = shutil.which("node") or "/opt/node22/bin/node"


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _const(src, name):
    i = src.index(f"const {name} = ")
    return src[i:src.index(";\n", i) + 2]


def _node(js):
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_the_streak_counts_from_nothing_and_locks_game_by_game():
    assert "<b>${me.current || 0}</b><span>day streak</span>" in ACCOUNT
    assert "best ${me.best || 0}</div>" in ACCOUNT
    assert "Each pick locks when its game starts." in ACCOUNT
    assert "Picks lock at first pitch" not in ACCOUNT


def test_hockey_says_puck_drop():
    if not os.path.exists(NODE):
        return
    got = _node(_fn(APP, "deckFirstWord")
                + "process.stdout.write(JSON.stringify(['nhl','nfl','cfb','mlb','cbb','ufc'].map(deckFirstWord)));")
    assert got == ["Puck drop", "Kickoff", "Kickoff", "First pitch", "Tip-off", "First bout"], got


def test_a_school_is_called_by_name_and_a_club_with_its_article():
    if not os.path.exists(NODE):
        return
    js = ("function icon() { return ''; }\n" + _fn(APP, "iconMark") + _fn(APP, "escapeHtml")
          + "const WF_LEAGUE = { nba: 'NBA', cbb: 'College basketball', cfb: 'College football', ufc: 'UFC' };\n"
          + _fn(ACCOUNT, "wfDay") + _fn(ACCOUNT, "flSampleHTML")
          + "const g = (league, team, right) => ({ league, final: { away: 61, home: 81 }, away: 'A', home: 'B',"
            " names: { A: team, B: 'Other' }, call: { team: 'A', chance: 0.55, right } });\n"
          + "process.stdout.write(JSON.stringify([flSampleHTML(g('cbb', 'Villanova', false)),"
            " flSampleHTML(g('nba', 'Timberwolves', true)), flSampleHTML(g('ufc', 'Ilia Topuria', true))]));")
    college, club, fighter = _node(js)
    assert "We called Villanova at 55% — wrong" in college, college
    assert "We called the Timberwolves at 55% — right" in club, club
    assert "We called Ilia Topuria at 55% — right" in fighter, fighter


def test_the_billing_line_is_said_once_and_the_close_says_its_unit():
    i = ACCOUNT.index('<div class="pw-cadence">${trial')
    card = ACCOUNT[i:ACCOUNT.index("</article>`;", i)]
    assert card.count("escapeHtml(pl.cadence)") == 1, "the line under the price, not again under the button"
    assert '? `<div class="pw-fine">Card required.' in card and ': ""}' in card, "a trial's fine print stays"
    assert "line points the close moved our way, on average, over ${o.clv_n} bets" in ACCOUNT
    assert "average closing-line value, ${o.clv_n} bets" not in ACCOUNT


def test_the_record_page_says_ncaab_and_each_thing_once():
    assert "function recLg(sp) {" in RECORD
    assert "(SPORT_META[sp] || {}).name" not in RECORD and "(SPORT_META[scope] || {}).name" not in RECORD
    assert "parts.push(btn(sp, recLg(sp)," in RECORD, "the league tabs"
    assert 'const name = scoped ? recLg(scope) : "";' in RECORD, "the week's header"
    for stale in ("escapeHtml(sp.toUpperCase())", "escapeHtml(s.toUpperCase())", '(m.sport || "").toUpperCase()',
                  '(w.sport || "").toUpperCase()', '(p.sport || "").toUpperCase()', "sport.toUpperCase()"):
        assert stale not in RECORD, stale
    if os.path.exists(NODE):
        got = _node("const LEAGUE_LABEL = { nba: 'NBA', cbb: 'NCAAB' };\n"
                    "const lgCode = (s) => LEAGUE_LABEL[s] || String(s || '').toUpperCase();\n"
                    + _fn(RECORD, "recLg") + "process.stdout.write(JSON.stringify(['cbb', 'nba', 'nhl'].map(recLg)));")
        assert got == ["NCAAB", "NBA", "NHL"], got
    assert "!sameTally(po, ov) && !(parts && sameTally(po, lo))" in _fn(APP, "recordRibbonsHTML")
    assert ': open ? "" : "graded once their games are final",' in _fn(RECORD, "rpPicksHTML")


def test_a_carried_in_week_is_this_week_only_while_it_is():
    import datetime as dt
    from engine import zeno

    def snap(as_of):
        p = os.path.join(tempfile.mkdtemp(), "zeno_snapshot.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"as_of": as_of, "windows": [
                {"key": "all", "label": "All time", "profit": 10, "roi": 0.1, "wins": 1, "losses": 1},
                {"key": "w", "label": "This week · Sep 21–27", "profit": 5, "roi": 0.5, "wins": 1, "losses": 0}]}, fh)
        return [w["label"] for w in zeno.load_snapshot(p)["windows"]]

    assert snap("2026-09-26T14:23:03") == ["All time", "Week of Sep 21–27"]
    today = dt.datetime.now().isoformat(timespec="seconds")
    assert snap(today) == ["All time", "This week · Sep 21–27"], "a snapshot read this week keeps its words"
    assert snap("not a date") == ["All time", "This week · Sep 21–27"], "an unreadable date changes nothing"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
