"""The chips under an Ask answer say what they are, and only the useful ones show.

Ethan, 2026-09-23, a screenshot of "How has Josh Allen done against the
chargers" with ten chips circled under the answer: "What exactly are we
showing here, this is just cluttered garbage and we are not explaining what
this is." The chips were every board row the question's words touched: Josh
Allen's props, but also Keenan Allen's and Nick Allen's (a shortstop), all
through the one word "Allen", in one unlabelled pile, with labels like
"Josh Allen yes Anytime TD".

Now (engine/askbot.py, web/js/app.js askSourcesHTML):
  * a question that names a player in full does not reach his namesakes;
  * under the answer, two labelled rows: SOURCES (what it read) and ON
    TONIGHT'S BOARD (at most three picks for the player or game the answer
    is about, each a door to its pick page);
  * a chip reads the way a person says it: "Josh Allen · Over 149.5
    Passing Yards", "Josh Allen · Anytime TD".
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                # noqa: E402

_TMP = Path(tempfile.mkdtemp())
AB.CACHE_PATH = _TMP / "ask_cache.json"
AB.USAGE_PATH = _TMP / "ask_usage.json"
AB.HISTORY_DB = str(_TMP / "no_history.db")
os.environ["QB_ASK_WEB_DAILY"] = "0"
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _prop(player, team, market, label, side, line, **kw):
    return {"player": player, "team": team, "opponent": "LAC" if team == "BUF" else "", "market": market,
            "market_label": label, "side": side, "line": line, "odds": -110, "book": "FanDuel",
            "hit_prob": 0.55, "recommended": False, **kw}


NFL = {"sport": "nfl", "date": "2026-W04", "built_at": "2026-09-23T12:00:00",
       "games": [{"home": "BUF", "away": "LAC", "spread": -7.0, "total": 50.0}],
       "recommendations": [
           _prop("Josh Allen", "BUF", "pass_yds", "Passing Yards", "OVER", 149.5),
           _prop("Josh Allen", "BUF", "pass_tds", "Passing TDs", "UNDER", 1.5),
           _prop("Josh Allen", "BUF", "anytime_td", "Anytime TD", "YES", 0.5),
           _prop("Josh Allen", "BUF", "rush_yds", "Rushing Yards", "OVER", 30.5),
           _prop("Keenan Allen", "CHI", "rec_yds", "Receiving Yards", "UNDER", 43.5)]}
MLB = {"sport": "mlb", "generated_at": "2026-09-23T11:00:00", "games": [],
       "recommendations": [
           _prop("Nick Allen", "ATH", "hits", "Hits", "UNDER", 0.5),
           _prop("Nick Allen", "ATH", "total_bases", "Total Bases", "UNDER", 0.5),
           _prop("Nick Allen", "ATH", "home_runs", "Home Runs", "OVER", 0.5)]}
BOARDS = {"nfl": NFL, "mlb": MLB}
Q = "How has Josh Allen done against the chargers"


def test_a_player_named_in_full_does_not_reach_his_namesakes():
    who = {h[2].get("player") for h in AB._hits_all(BOARDS, Q, "nfl")}
    assert who == {"Josh Allen"}, who
    assert {h[2].get("player") for h in AB._hits_all(BOARDS, "how has Allen done lately", "nfl")} == \
        {"Josh Allen", "Keenan Allen", "Nick Allen"}, "a surname alone is ambiguous, and the model sorts it out"
    assert {h[2].get("player") for h in AB._hits(MLB, Q, AB.asked_in_full([NFL, MLB], Q))} == set(), \
        "across boards: the shortstop is not reached through the quarterback's surname"


def test_a_chip_reads_the_way_a_person_says_it():
    rows = NFL["recommendations"]
    assert AB.chip_label(rows[0]) == "Josh Allen · Over 149.5 Passing Yards"
    assert AB.chip_label(rows[1]) == "Josh Allen · Under 1.5 Passing TDs"
    assert AB.chip_label(rows[2]) == "Josh Allen · Anytime TD", "not 'Josh Allen yes Anytime TD'"
    assert AB.chip_label({**rows[2], "side": "NO"}) == "Josh Allen · No Anytime TD"
    assert AB.chip_label({**rows[0], "line": 150.0}) == "Josh Allen · Over 150 Passing Yards"
    assert AB.chip_label({"pick_label": "Chiefs -2.5", "player": "x"}) == "Chiefs -2.5"


def _answer(text, tool=None):
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if tool and calls["n"] == 1:
            blk = types.SimpleNamespace(type="tool_use", id="t1", name=tool[0], input=tool[1])
            return types.SimpleNamespace(content=[blk], stop_reason="tool_use", usage=None)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text, citations=None)],
                                     stop_reason="end_turn", usage=None)
    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def test_under_his_answer_the_sources_then_at_most_three_of_his_picks():
    (_TMP / "data").mkdir(exist_ok=True)
    out = AB.ask(NFL, Q, client=_answer("Josh Allen has one stored meeting with the Chargers, a win.",
                                        ("standings", {"sport": "nfl"})),
                 boards=BOARDS, data_dir=_TMP / "data")
    picks = [s for s in out["sources"] if s.get("kind") == "pick"]
    assert [s["label"] for s in picks] == ["Josh Allen · Over 149.5 Passing Yards",
                                           "Josh Allen · Under 1.5 Passing TDs",
                                           "Josh Allen · Anytime TD"], "three, and all his"
    assert all(s["prop"].startswith("Josh Allen|") for s in picks), "each a door to its pick page"
    read = [s for s in out["sources"] if s.get("kind") != "pick"]
    assert read and all("Allen" not in s["label"] for s in read)
    assert out["sources"][:len(read)] == read, "what it read first, then the picks"


def test_a_row_the_answer_does_not_talk_about_is_not_shown():
    src = [{"label": "Josh Allen · Over 149.5 Passing Yards", "prop": "Josh Allen|pass_yds|OVER|149.5", "kind": "pick"},
           {"label": "Keenan Allen · Under 43.5 Receiving Yards", "prop": "k", "kind": "pick"},
           {"label": "Bills -7", "prop": "", "kind": "pick"},
           {"label": "BUF @ LAC, lines and weather", "prop": ""},
           {"label": "Chiefs +3", "prop": "", "kind": "pick"},
           {"label": "The pick you asked from", "prop": "p", "kind": "pick"}]
    about = {"Josh Allen · Over 149.5 Passing Yards": ("josh allen", True),
             "Keenan Allen · Under 43.5 Receiving Yards": ("keenan allen", True),
             "Bills -7": ("", True), "Chiefs +3": ("", False), "The pick you asked from": (None, True)}
    got = [s["label"] for s in AB.shown_sources(src, "Josh Allen's Bills host the Chargers.", about)]
    assert got == ["BUF @ LAC, lines and weather", "Josh Allen · Over 149.5 Passing Yards", "Bills -7",
                   "The pick you asked from"], \
        "his name in the answer keeps his chip; Keenan is never mentioned; a team code alone is too weak"
    both = [s["label"] for s in AB.shown_sources(src, "Allen's Bills host the Chargers.", about)]
    assert not [x for x in both if "Allen ·" in x], "'Allen' alone could be either of them: neither"
    solo = {k: v for k, v in about.items() if not k.startswith("Keenan")}
    assert "Josh Allen · Over 149.5 Passing Yards" in [
        s["label"] for s in AB.shown_sources(src, "Allen's Bills host the Chargers.", solo)], \
        "a surname only one of them has is enough"
    none = [s["label"] for s in AB.shown_sources(src, "", about)]
    assert none == ["BUF @ LAC, lines and weather", "Bills -7", "The pick you asked from"]
    many = [{"label": f"r{i}", "prop": "", "kind": "pick"} for i in range(6)] + \
           [{"label": f"s{i}", "prop": ""} for i in range(9)]
    capped = AB.shown_sources(many, "", {f"r{i}": ("", True) for i in range(6)})
    assert len([s for s in capped if s.get("kind") == "pick"]) == AB.MAX_PICK_CHIPS == 3
    assert len([s for s in capped if s.get("kind") != "pick"]) == AB.MAX_READ_CHIPS == 6


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    esc = APP[APP.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fn = APP[APP.index("function askSourcesHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    prog = esc + "const escapeAttr = escapeHtml;\n" + fn + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_two_labelled_rows():
    got = _node("""return askSourcesHTML({ sources: [
        { label: "Josh Allen, game logs vs Los Angeles Chargers", prop: "" },
        { label: "espn.com", url: "https://www.espn.com/x", title: "t", prop: "" },
        { label: "Josh Allen · Over 149.5 Passing Yards", prop: "Josh Allen|pass_yds|OVER|149.5", kind: "pick" },
        { label: "Bills -7", prop: "", kind: "pick" },
        { label: "Josh Allen OVER 30.5 Rushing Yards", prop: "Josh Allen|rush_yds|OVER|30.5" },
        { label: "Nick Allen UNDER 0.5 Hits", prop: "Nick Allen|hits|UNDER|0.5" }] });""")
    if got is None:
        print("  SKIP node not installed")
        return
    first, second = got.split('<div class="ask-src ask-src-picks">')
    assert first.startswith('<div class="ask-src"><span class="ask-src-h">Sources</span>')
    assert "game logs vs Los Angeles Chargers" in first and 'href="https://www.espn.com/x"' in first
    assert second.startswith('<span class="ask-src-h">On tonight’s board <em>tap one for our full read</em></span>'), \
        "it says what the row is and what a tap does"
    assert second.count('class="ask-chip pick"') == 3, "at most three, a saved answer's unmarked ones too"
    assert 'data-prop="Josh Allen|pass_yds|OVER|149.5" tabindex="0" role="link">Josh Allen · Over 149.5 ' \
           'Passing Yards ›</span>' in second, "a door says it opens"
    assert "Nick Allen" not in got


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
