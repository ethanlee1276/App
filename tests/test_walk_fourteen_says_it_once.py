"""Walk 14's fixes (2026-11-18, step YD): the Colts at the Texans' game page,
the Streak and a league's Record page, read as a reader would on a phone.

  - NRG Stadium's panel said the roof four times (the conditions chip above it,
    its own chip, its note, the weather card) and the turf twice (the facts
    line and a chip). The surface is its chip; the roof is the conditions
    chip's and the weather card's; an indoor venue's note keeps what it says
    beyond the two (the Superdome's scoring, U.S. Bank Stadium's noise);
  - the exchanges' lines read "Over 44.5 49% (+106) on Polymarket" and the same
    words "on Kalshi": one line at one price, said once, naming both;
  - the Streak, opened from the NBA tab, showed Charlie McAvoy's shots on goal
    and named no league; a night that is one league's names it in its heading,
    a night that mixes them names each row's; its days read in words;
  - a league's Record page opened its profit calendar on "No edge bet has
    settled here yet." with the Most Likely book's days one tap away; an
    unchosen calendar opens on the book with days (tests/test_profit_calendar.py),
    and the calendar moved to the Record page's own file.

    python3 tests/test_walk_fourteen_says_it_once.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
DETAIL = (JS / "detail.js").read_text(encoding="utf-8")
ACCT = (JS / "account.js").read_text(encoding="utf-8")

from engine.stadiums import STADIUMS                                            # noqa: E402


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _line(src: str, start: str) -> str:
    i = src.index(start)
    return src[i:src.index("\n", i)]


def _node(prog: str):
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


HARNESS = "\n".join([
    _fn(APP, "escapeHtml"),
    'const MINUS = "−"; const icon = (n) => `<i data-icon="${n}"></i>`; const teamName = (t) => t;',
    "const pctPrice = (p) => `${Math.round(Number(p) * 100)}%`;",
    _line(DETAIL, "const ROOF_SAID = "),
    _fn(DETAIL, "venueNoteBeyondRoof"),
    _fn(DETAIL, "stadiumTonightHTML"),
    _fn(DETAIL, "stadiumPanel"),
    _fn(DETAIL, "crowdLinesHTML"),
])


def test_the_venue_panel_says_each_fact_once():
    nrg = {"name": "NRG Stadium", "roof": "retractable", "surface": "turf", "capacity": 72220, "opened": 2002,
           "plays": STADIUMS["HOU"].plays}
    nola = {"name": "Caesars Superdome", "roof": "dome", "surface": "turf", "capacity": 73208, "opened": 1975,
            "plays": STADIUMS["NO"].plays}
    lambeau = {"name": "Lambeau Field", "roof": "outdoors", "surface": "grass", "capacity": 81441, "opened": 1957,
               "plays": STADIUMS["GB"].plays}
    retract = ("Retractable roof — read as closed: these roofs were shut for 9 home games in 10 from 2016 to 2025 "
               "and open only on fair days, never in rain, so the weather is left out")
    got = _node(HARNESS + f"""
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const hou = stadiumPanel({{stadium: {json.dumps(nrg)}, weather: {{dome: true}},
                                 conditions: {{why: [{json.dumps(retract)}]}}}});
      const no = stadiumPanel({{stadium: {json.dumps(nola)}, weather: {{dome: true}},
                                conditions: {{why: ["Dome game — no weather impact on the passing game"]}}}});
      const gb = stadiumPanel({{stadium: {json.dumps(lambeau)}, weather: {{temp_f: 41, wind_mph: 9}},
                                conditions: {{why: ["Wind 9 mph forecast"]}}}});
      const bare = stadiumPanel({{stadium: {json.dumps(nrg)}, weather: {{dome: true}}}});
      console.log(JSON.stringify({{hou: text(hou), no: text(no), gb: text(gb), bare: text(bare)}}));""")
    if got is None:
        return
    hou = got["hou"]
    assert hou.count("Retractable roof") == 1 and "read as closed" in hou, f"the roof once, in the weather card: {hou}"
    assert hou.startswith("NRG Stadium Opened 2002 · 72,220 seats Turf "), hou
    assert hou.lower().count("turf") == 1 and "Gulf heat" not in hou, hou
    no = got["no"]
    assert "Historically one of the highest-scoring environments in the league." in no, "what it says beyond the roof"
    assert "Fixed dome" not in no and no.lower().count("turf") == 1, no
    gb = got["gb"]
    assert "Open air" in gb and "Open air in Green Bay." in gb and "Grass" in gb, "outdoors: the chip and the note"
    assert "grass" not in gb.replace("Grass", ""), "the surface once"
    assert "Gulf heat" in got["bare"], "with no weather card to say the roof, the venue's note says it"


def test_every_indoor_note_keeps_only_what_the_page_does_not_say():
    notes = {k: s.plays for k, s in STADIUMS.items() if s.roof != "outdoors"}
    got = _node(HARNESS + f"""
      const notes = {json.dumps(notes)};
      console.log(JSON.stringify(Object.fromEntries(Object.entries(notes).map(([k, n]) => [k, venueNoteBeyondRoof(n)]))));""")
    if got is None:
        return
    assert got.pop("MIN") == "One of the louder indoor buildings."
    assert got.pop("NO") == "Historically one of the highest-scoring environments in the league."
    assert set(got.values()) == {""}, f"every other indoor note was its roof and surface: {got}"


def test_one_line_at_one_price_is_said_once_naming_both():
    got = _node(HARNESS + """
      const g = {home: "HOU", away: "IND"};
      const same = crowdLinesHTML(g, {spread_home_line: -3.5, total_line: 44.5,
        poly_home_cover: 0.52, poly_over: 0.49, kalshi_home_cover: 0.55, kalshi_over: 0.49});
      const one = crowdLinesHTML(g, {total_line: 44.5, poly_over: 0.49});
      const none = crowdLinesHTML(g, {total_line: 44.5});
      const items = (h) => (h.match(/<li>[\\s\\S]*?<\\/li>/g) || []).map((x) => x.replace(/<[^>]+>/g, "").replace(/\\s+/g, " ").trim());
      console.log(JSON.stringify({same: items(same), one: items(one), none}));""")
    if got is None:
        return
    assert got["same"] == ["HOU −3.5 covers 52% on Polymarket", "Over 44.5 49% on Polymarket and Kalshi",
                           "HOU −3.5 covers 55% on Kalshi"], got["same"]
    assert got["one"] == ["Over 44.5 49% on Polymarket"]
    assert got["none"] == ""


def test_the_streak_names_its_league():
    i = ACCT.index("const WF_LEAGUE = ")
    table = ACCT[i:ACCT.index(";\n", i) + 2]
    prog = "\n".join([
        _fn(APP, "escapeHtml"), table,
        "const icon = (n) => ``; const formatKickoff = () => \"7:00 PM\";",
        _fn(ACCT, "stkLeagues"), _fn(ACCT, "stkLeagueWord"), _fn(ACCT, "stkQuestionRow"),
    ]) + """
      const q = {qid: "q1", sport: "nhl", player: "Charlie McAvoy", label: "Shots on goal", game: "BOS @ TOR",
                 line: 2.5, lock: "2099-01-01T00:00:00Z"};
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      console.log(JSON.stringify({
        mixed: text(stkQuestionRow(q, null, false, true, true)),
        alone: text(stkQuestionRow(q, null, false, true, false)),
        leagues: stkLeagues([q, {sport: "nba"}, {sport: "nhl"}]),
        cbb: stkLeagueWord("cbb"),
      }));"""
    got = _node(prog)
    if got is None:
        return
    assert "Shots on goal · BOS @ TOR · NHL" in got["mixed"], got["mixed"]
    assert "NHL" not in got["alone"], "one league's night says it once, in its heading"
    assert got["leagues"] == ["nhl", "nba"] and got["cbb"] == "College basketball"
    body = _fn(ACCT, "renderStreak")
    assert "Tonight${leagues.length === 1 ? ` in ${escapeHtml(sportLabel(leagues[0]))}` : \"\"}" in body
    assert "stkQuestionRow(q, myToday[q.qid], locked, signedIn, leagues.length > 1)" in body
    assert "escapeHtml(formatGameDate(d) || d)" in body, "a past night's day in words"
    assert "const lastDay = escapeHtml(formatGameDate(me.last_day) || me.last_day || \"\");" in body


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
