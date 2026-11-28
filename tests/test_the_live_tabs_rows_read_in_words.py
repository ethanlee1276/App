"""The Live tab's basketball and hockey cards say their plays in words, as the game page does.

Ethan, 2026-11-23: "We want all the live pages to match each other ... NFL is
kind of like the one we want to go off of." A football card's rows on the Live
tab read as our own lines ("CIN Joe Burrow sacked by Tim Settle for a loss of
6 yds"); a basketball card's read as a label ("MEM · Zach Edey — Defensive
Rebound"), where the game page says the same play as a sentence
(js/hoopscast.js said). The Live tab now asks the game page's file for its
words (`QBHoops.cardSay`, loaded once the tab shows a basketball game), with
the second name's part said only where the card's own players put that player
on the side it belongs to.

The card's players named a club by ESPN's code ("NO" where every page says
NOP; "MNFD" for a school the card calls espn:2365), so their marks on the
game page missed and the sides could not be read. Each row now takes the
card's code where the card has one, by the side's ESPN id, and says its side.

Hockey's game page says its plays from the NHL's own feed (js/rinkcast.js),
which the card did not carry. The rink pass now puts each game's newest few
league events on its card (`rink_plays`, livescore_build.card_rink; a pass
the feed does not answer keeps the last ones), and the Live tab draws them as
the game page's rows and words (`QBRink.cardRows`).

Offline. Run directly: `python3 tests/test_the_live_tabs_rows_read_in_words.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import livescore_build as B                                  # noqa: E402
from _app import decl                                        # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
HC = (ROOT / "web" / "js" / "hoopscast.js").read_text(encoding="utf-8")


def _block(tid, abbr, names):
    return {"team": {"id": tid, "abbreviation": abbr},
            "statistics": [{"names": ["MIN", "PTS", "REB", "AST"],
                            "athletes": [{"athlete": {"id": f"{tid}{i}", "displayName": n},
                                          "starter": i < 5, "stats": ["20", "10", "4", "2"]}
                                         for i, n in enumerate(names)]}]}


def test_each_player_row_takes_the_cards_club_code_and_says_its_side():
    payload = {"boxscore": {"players": [_block("21", "PHX", ["Devin Booker"]),
                                        _block("3", "NO", ["Zion Williamson"])]}}
    g = {"home": "NOP", "away": "PHX", "home_id": "3", "away_id": "21"}
    rows = {r["player"]: r for r in B.pbp_players("nba", payload, g)}
    assert rows["Zion Williamson"]["team"] == "NOP" and rows["Zion Williamson"]["side"] == "home"
    assert rows["Devin Booker"]["team"] == "PHX" and rows["Devin Booker"]["side"] == "away"


def test_a_school_the_card_has_no_code_for_keeps_espns_and_still_says_its_side():
    payload = {"boxscore": {"players": [_block("2365", "MNFD", ["A Guard"]),
                                        _block("2330", "LEM", ["B Forward"])]}}
    g = {"home": "LEM", "away": "espn:2365", "home_id": "2330", "away_id": "2365"}
    rows = {r["player"]: r for r in B.pbp_players("cbb", payload, g)}
    assert rows["A Guard"]["team"] == "MNFD" and rows["A Guard"]["side"] == "away"
    assert rows["B Forward"]["team"] == "LEM" and rows["B Forward"]["side"] == "home"


def test_a_card_without_the_sides_ids_leaves_the_rows_as_the_box_has_them():
    payload = {"boxscore": {"players": [_block("3", "NO", ["Zion Williamson"])]}}
    rows = B.pbp_players("nba", payload, {"home": "NOP", "away": "PHX"})
    assert rows[0]["team"] == "NO" and "side" not in rows[0]


STUBS = """
  globalThis.window = globalThis;
  globalThis.escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.teamNameIn = (lg, a) => ({ MEM: "Memphis Grizzlies", CHA: "Charlotte Hornets" })[a] || "";
  globalThis.chatPlayBadge = () => "";
"""


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([STUBS, decl("PLAYS_EMPTY"), decl("hockeyPeriod"), decl("halfPeriod"), decl("playsHTML"),
                     HC, f"console.log(JSON.stringify((() => {{ const Q = window.QBHoops; {js} }})()));"])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


#: A card as live_nba.json carries it: the sides by code, the box's names with their side.
CARD = {
    "home": "CHA", "away": "MEM", "event_id": "401",
    "players": [{"player": "Ty Jerome", "team": "MEM", "side": "away"},
                {"player": "Kris Murray", "team": "MEM", "side": "away"},
                {"player": "Brandon Miller", "team": "CHA", "side": "home"},
                {"player": "Sion James", "team": "CHA"}],
}
PLAYS = [
    {"kind": "hoops", "team": "MEM", "player": "Ty Jerome", "players": ["Ty Jerome", "Kris Murray"],
     "event": "Jump Shot", "scoring": True, "shot": True, "points": 3, "points_attempted": 3, "period": 2, "clock": "5:12"},
    {"kind": "hoops", "team": "CHA", "player": "Brandon Miller", "players": ["Brandon Miller", "Kris Murray"],
     "event": "Layup", "scoring": False, "shot": True, "points_attempted": 2, "period": 2, "clock": "4:58"},
    {"kind": "hoops", "team": "CHA", "player": "Sion James", "event": "Defensive Rebound", "period": 2, "clock": "4:40"},
    {"kind": "hoops", "team": "CHA", "player": "Brandon Miller", "players": ["Brandon Miller", "Ty Jerome"],
     "event": "Bad Pass Turnover", "period": 2, "clock": "4:31"},
    {"kind": "hoops", "team": "MEM", "player": "Ty Jerome", "players": ["Ty Jerome", "Somebody Else"],
     "event": "Jump Shot", "scoring": True, "shot": True, "points": 2, "points_attempted": 2, "period": 2, "clock": "4:20"},
    {"kind": "hoops", "team": "", "player": "", "event": "TV Timeout", "period": 2, "clock": "4:20"},
]


def test_a_cards_plays_are_said_as_the_game_page_says_them():
    got = _node(f"const say = Q.cardSay({json.dumps(CARD)}, 'nba'); return {json.dumps(PLAYS)}.map(say);")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got[0] == {"html": "<b>Ty Jerome</b> makes a 3-point jump shot, assist <b>Kris Murray</b>"}, got[0]
    assert got[1] == {"html": "<b>Brandon Miller</b> misses a layup, blocked by <b>Kris Murray</b>"}, got[1]
    # A name the card lists without a side is still placed by its club code.
    assert got[2] == {"html": "<b>Sion James</b> grabs a defensive rebound"}, got[2]
    assert got[3] == {"html": "<b>Brandon Miller</b> turns it over: bad pass, stolen by <b>Ty Jerome</b>"}, got[3]
    # A second name the card's players do not place is not given a part.
    assert got[4] == {"html": "<b>Ty Jerome</b> makes a jump shot"}, got[4]
    assert got[5] == {"moment": "Media timeout"}, got[5]


def test_the_card_row_reads_the_line_with_its_side_as_footballs_does():
    got = _node(f"""const g = {json.dumps(CARD)};
      return playsHTML({{ ...g, plays: {json.dumps(PLAYS[:1])}, say: Q.cardSay(g, "nba") }});""")
    if got is None:
        return
    assert ('<span class="lb-side">MEM</span> <b>Ty Jerome</b> makes a 3-point jump shot, assist <b>Kris Murray</b>'
            ' <span class="lb-rbi">+3</span>') in got, got
    assert "Ty Jerome — Jump Shot" not in got and "MEM · Ty Jerome" not in got


def test_a_college_card_says_its_halves():
    end = {"kind": "hoops", "team": "", "player": "", "event": "End Period", "period": 1, "clock": "0:00"}
    got = _node(f"""const g = {{ home: "KU", away: "DEN", players: [] }};
      return [Q.cardSay(g, "cbb")({json.dumps(end)}), Q.cardSay(g, "nba")({json.dumps(end)})];""")
    if got is None:
        return
    assert got == [{"moment": "End of the 1st half"}, {"moment": "End of the 1st quarter"}], got


RC = (ROOT / "web" / "js" / "rinkcast.js").read_text(encoding="utf-8")


def _ev(i, kind, team, player="", player2="", **kw):
    return {"id": i, "period": 2, "clock": kw.pop("clock", "04:31"), "kind": kind, "team": team,
            "player": player or None, "player2": player2 or None, "sc": "1551", **kw}


EVENTS = [
    _ev(1, "stoppage", "", reason="icing"),
    _ev(2, "faceoff", "NJD", "Nico Hischier", "Charlie Coyle", clock="05:19"),
    _ev(3, "sog", "NJD", "Connor Brown", "Cam Talbot", shot="wrist", clock="04:55"),
    _ev(4, "miss", "CBJ", "Mathieu Olivier", shot="wrist", reason="wide-right", clock="03:26"),
    _ev(5, "hit", "CBJ", "Dante Fabbro", "Amadeus Lombardi", clock="02:09"),
    _ev(6, "stoppage", "", reason="offside", clock="02:00"),
    _ev(7, "giveaway", "CBJ", "Dante Fabbro", clock="01:56"),
    _ev(8, "penalty", "CBJ", "Dante Fabbro", penalty="delaying-game-puck-over-glass", minutes=2, clock="01:39"),
    _ev(9, "goal", "NJD", "Connor Brown", shot="snap", assists=["Dougie Hamilton", "Jonas Siegenthaler"],
        score=[1, 2], clock="01:20"),
]


def test_a_hockey_card_carries_the_leagues_newest_events_without_its_whistles():
    rows = B.card_rink({"events": EVENTS})
    assert [e["id"] for e in rows] == [3, 4, 5, 7, 8, 9], "the newest six, stoppages left to the game page"
    assert B.card_rink({}) == [] and B.card_rink({"events": [None, {"kind": ""}]}) == []
    src = (ROOT / "livescore_build.py").read_text(encoding="utf-8")
    rink = src[src.index("def nhl_rink_pass("):src.index("def main(")]
    assert '_merge_rink(g, rink, Path(out_dir) / "pbp")\n            g["rink_plays"] = card_rink(rink)' in rink
    write = src[src.index("def write("):src.index("#: HOCKEY'S SKATER LINES")]
    assert 'if league == "nhl":\n        _carry_rink(payload.get("games") or [], prev)' in write
    assert 'if any(g.get("rink_plays") for g in payload.get("games") or []):' in write, "the card is written again with them"


def test_a_pass_the_league_does_not_answer_keeps_the_last_rows():
    prev = {"games": [{"event_id": "1", "rink_plays": [{"id": 3}]}, {"event_id": "2", "rink_plays": [{"id": 4}]},
                      {"event_id": "3", "rink_plays": [{"id": 5}]}]}
    games = [{"event_id": "1", "live": {"state": "live"}},
             {"event_id": "2", "live": {"state": "live"}, "rink_plays": [{"id": 9}]},
             {"event_id": "3", "live": {"state": "pre"}}]
    B._carry_rink(games, prev)
    assert games[0]["rink_plays"] == [{"id": 3}], "a live game keeps last pass's rows"
    assert games[1]["rink_plays"] == [{"id": 9}], "fresh rows are never replaced by old ones"
    assert "rink_plays" not in games[2], "only a game in progress"
    B._carry_rink(games, None)


def _rink(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([STUBS, decl("PLAYS_EMPTY"), decl("hockeyPeriod"), decl("halfPeriod"), decl("playsHTML"),
                     RC, f"console.log(JSON.stringify((() => {{ const R = window.QBRink; {js} }})()));"])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_hockey_cards_rows_are_said_as_the_game_page_says_them():
    card = {"home": "NJD", "away": "CBJ", "rink_plays": B.card_rink({"events": EVENTS})}
    got = _rink(f"""const g = {json.dumps(card)}, w = R.cardRows(g);
      return {{ says: w.rows.map(w.say), html: playsHTML({{ ...g, plays: w.rows.slice().reverse(), say: w.say }}),
               none: R.cardRows({{ home: "NJD", away: "CBJ", plays: [] }}) }};""")
    if got is None:
        return
    assert got["says"] == [
        {"html": "<b>Connor Brown</b> shoots (wrist), saved by <b>Cam Talbot</b>"},
        {"html": "<b>Mathieu Olivier</b> misses (wrist, wide right)"},
        {"html": "<b>Dante Fabbro</b> hits <b>Amadeus Lombardi</b>"},
        {"html": "Giveaway by <b>Dante Fabbro</b>"},
        {"html": "Delaying game puck over glass, 2 min on <b>Dante Fabbro</b>"},
        {"html": "<b>Connor Brown</b> scores (snap), from <b>Dougie Hamilton</b> and <b>Jonas Siegenthaler</b>"},
    ], got["says"]
    html = got["html"]
    # The newest on top, its side first as football's, a goal with its chip and the score it left.
    assert html.index("scores (snap)") < html.index("saved by"), "the newest play on top"
    assert ('<span class="lb-side">NJD</span> <b>Connor Brown</b> scores (snap), from <b>Dougie Hamilton</b> and '
            '<b>Jonas Siegenthaler</b> <span class="lb-rbi">GOAL</span>') in html
    assert '<span class="lb-pscore">1–2</span>' in html
    assert '<span class="lb-inn">P2 1:20</span>' in html, "the clock the header counts down, as the game page's rows"
    assert got["none"] is None, "a card the league's feed has not reached keeps ESPN's rows"


def test_a_baseball_cards_at_bats_are_said_as_the_game_page_says_them():
    """Baseball's words were the game page's file's (detail.js); they are app.js's now, for the Live tab's cards too."""
    node = shutil.which("node")
    if not node:
        return
    card = {"home": "NYY", "away": "BOS", "plays": [
        {"inning": 3, "half": "B", "batter": "Aaron Judge", "pitcher": "Garrett Crochet", "event": "Double",
         "event_type": "double", "rbi": 2, "scoring": True, "away_score": 1, "home_score": 3, "distance": 401},
        {"inning": 3, "half": "B", "batter": "Juan Soto", "pitcher": "Garrett Crochet", "event": "Strikeout",
         "event_type": "strikeout", "rbi": 0}]}
    src = "\n".join([STUBS, "const LIVE_WORDS = {};", decl("GP_BB_VERB"), decl("GP_BB_OUT"), decl("GP_BB_OFF"),
                     decl("gpAtBatWords"), decl("liveWords"), decl("PLAYS_EMPTY"), decl("hockeyPeriod"),
                     decl("halfPeriod"), decl("playsHTML"),
                     f"const g = {json.dumps(card)}, w = liveWords('mlb', g);",
                     "console.log(JSON.stringify(playsHTML({ ...g, plays: w.plays.slice().reverse(), say: w.say })));"])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html = json.loads(out.stdout)
    assert "<b>Aaron Judge</b> doubles off <b>Garrett Crochet</b>, 401 ft, 2 runs in." in html, html
    assert "<b>Juan Soto</b> strikes out off <b>Garrett Crochet</b>." in html, html
    assert "2 RBI" not in html, "the line says the runs; the chip is for the rows that cannot"
    assert "function gpAtBatWords(" not in (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8"), "one copy"


def test_the_live_tab_asks_for_the_words_once_and_draws_again_when_they_land():
    card = APP[APP.index("function liveCardHTML("):]
    card = card[:card.index("\n}\n")]
    assert "const words = liveWords(sport, g);" in card, "each card's rows and words, as the game page says them"
    assert "${playsHTML({ ...g, plays: words.plays.slice().reverse(), say: words.say," in card
    # A card saved for later shows no plays, the league's own included.
    assert "plays: [], rink_plays: [], line_track: null };" in card
    table = decl("LIVE_WORDS")
    for sport in ("nba", "wnba", "cbb"):
        assert f'{sport}: ["js/hoopscast.js", "css/hoopscast.css", "QBHoops"]' in table, sport
    assert 'nhl: ["js/rinkcast.js", "css/rinkcast.css", "QBRink"]' in table
    words = decl("liveWords")
    assert 'if (sport === "mlb") return { plays: g.plays || [], say: (p) => (p && p.batter ? { html: gpAtBatWords(p).html } : null) };' in words
    assert 'if (M && typeof M.cardSay === "function") return { plays: g.plays || [], say: M.cardSay(g, sport) };' in words
    assert "return ice ? { plays: ice.rows, say: ice.say } : { plays: g.plays || [], say: null };" in words
    load = decl("liveWordsLoad")
    # Its styles come with it, so the game page (detail.js gpSportMod) finds them in place.
    assert "if (!f || window[f[2]] || _liveWordFiles[f[0]]) continue;" in load, "fetched once, never on every draw"
    assert "loadRoom(f[0], f[1]).then((ok) => {" in load
    assert 'if (ok && state.view === "live") renderLiveBoard();' in load
    board = decl("renderLiveBoard")
    assert "liveTickArm(games);\n  liveWordsLoad(games);" in board
    assert "g.players, g.rink_plays]).concat(" in decl("liveSig"), "new league rows redraw the tab"
    assert "    cardSay,\n  };" in HC and "    cardRows,\n  };" in RC
    for css in ("hoopscast.css", "rinkcast.css"):
        sheet = (ROOT / "web" / "css" / css).read_text(encoding="utf-8")
        prefix = ".hc-" if css.startswith("hoops") else ".rc-"
        for sel in re.findall(r"([^{}]+)\{", re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)):
            sel = sel.strip()
            if sel.startswith("@") or re.fullmatch(r"(from|to|[\d.]+%)(\s*,\s*[\d.]+%)*", sel) or not sel:
                continue
            assert prefix in sel, f"{css}: {sel!r} would reach the Live tab"


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
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
