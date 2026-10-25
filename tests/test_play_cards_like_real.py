"""Play cards like Real's, and two things Real's don't say.

Ethan, 2026-10-25, sending Real's first screen: a walk-off homer's card —
the score and the inning, a 9.8 in the corner, "Walk-off 3-run 416'
homer", "P. Alonso · 1/5, 3 rbi", "P. Fairbanks · 0.1 ip, 1 k, 2 er,
11 p", "15th homer this season", reactions, comments, share.

The number in the corner is engine/playmoments: the win chance the play
moved, from the feed's own number (ESPN's summary for football and
basketball, MLB's per-at-bat feed), squeezed onto 0–10. The lines and
the facts are counted off the game's own box score and plays (js/chat.js
pcBodyHTML). Ours also says the win chance before and after, and whether
the play tied it, put a side ahead or ended it.

    python3 tests/test_play_cards_like_real.py
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

from engine import playmoments as M                          # noqa: E402

CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "chat.css").read_text(encoding="utf-8")


def _ab(i, event, inning, half, away, home, rbi=0, **k):
    return {"kind": "atbat", "at_bat": i, "event": event, "inning": inning, "half": half,
            "away_score": away, "home_score": home, "rbi": rbi, "batter": k.get("batter", "Somebody"),
            "pitcher": k.get("pitcher", "A Pitcher"), **{x: v for x, v in k.items() if x not in ("batter", "pitcher")}}


# --- the number ---------------------------------------------------------------
def test_the_rating_is_the_win_chance_it_moved():
    rows = [{"id": "1", "kind": "football", "away_score": 0, "home_score": 0},
            {"id": "2", "kind": "football", "away_score": 0, "home_score": 0},
            {"id": "3", "kind": "football", "away_score": 0, "home_score": 7}]
    M.enrich(rows, "nfl", {"1": 50.0, "2": 48.0, "3": 70.0})
    assert "wpa" not in rows[0], "the first play has no play before it"
    assert rows[1]["wpa"] == -2.0 and rows[2]["wpa"] == 22.0
    assert rows[1]["rating"] < 2 and 6.5 < rows[2]["rating"] < 8
    big = [{"id": "a", "kind": "x"}, {"id": "b", "kind": "x"}]
    M.enrich(big, "nfl", {"a": 15.0, "b": 95.0})
    assert big[1]["rating"] >= 9.8, "an 80-point swing is the top of the scale"


def test_a_walk_off_is_one_and_says_so():
    rows = [_ab(70, "Strikeout", 10, "B", 7, 5), _ab(71, "Home Run", 10, "B", 7, 8, rbi=3, distance=416)]
    M.enrich(rows, "mlb", key=lambda r: r["at_bat"])
    assert rows[1]["swing"] == "walkoff" and rows[1]["rating"] >= 9.5
    top = [_ab(1, "Single", 9, "T", 3, 3), _ab(2, "Home Run", 9, "T", 4, 3, rbi=1)]
    M.enrich(top, "mlb")
    assert top[1].get("swing") == "go_ahead", "the top of the ninth ends nothing"


def test_a_tie_and_a_lead_are_named():
    rows = [{"kind": "hoops", "away_score": 50, "home_score": 52, "period": 2},
            {"kind": "hoops", "away_score": 52, "home_score": 52, "period": 2},
            {"kind": "hoops", "away_score": 55, "home_score": 52, "period": 2},
            {"kind": "hoops", "away_score": 57, "home_score": 52, "period": 2}]
    M.enrich(rows, "nba")
    assert [r.get("swing", "") for r in rows] == ["", "tying", "go_ahead", ""]
    goal = [{"kind": "goal", "period": 4, "away_score": 2, "home_score": 2},
            {"kind": "goal", "period": 4, "away_score": 2, "home_score": 3}]
    M.enrich(goal, "nhl")
    assert goal[1]["swing"] == "walkoff", "an overtime goal ends it"
    first = [{"kind": "goal", "period": 1, "away_score": 0, "home_score": 0},
             {"kind": "goal", "period": 1, "away_score": 1, "home_score": 0}]
    M.enrich(first, "nhl")
    assert "swing" not in first[1], "the first goal of the game is not a go-ahead goal"


def test_a_reading_never_claims_the_top_of_the_scale():
    """With no win chance on file the rating is a reading of the play,
    capped short of what only a measured swing or a walk-off reaches."""
    rows = [{"kind": "football", "event": "Rush", "period": 4, "away_score": 21, "home_score": 24},
            {"kind": "football", "event": "Passing Touchdown", "scoring": True, "period": 4,
             "away_score": 28, "home_score": 24}]
    M.enrich(rows, "nfl")
    assert rows[1]["swing"] == "go_ahead" and rows[1]["rating"] <= M.HEURISTIC_CAP
    assert "wp" not in rows[1], "no win chance is invented"


def test_the_feeds_are_read_as_they_come():
    espn = {"winprobability": [{"playId": "9", "homeWinPercentage": 0.734}, {"playId": "", "homeWinPercentage": 0.5},
                               {"playId": "8", "homeWinPercentage": 7}]}
    assert M.espn_win_chances(espn) == {"9": 73.4}
    assert M.espn_win_chances({}) == {} and M.espn_win_chances(None) == {}
    mlb = [{"atBatIndex": 3, "homeTeamWinProbability": 61.2}, {"about": {"atBatIndex": 4}, "homeTeamWinProbability": 70},
           {"atBatIndex": 5}, "junk"]
    assert M.mlb_win_chances(mlb) == {3: 61.2, 4: 70.0}
    assert M.mlb_win_chances({"not": "a list"}) == {}


def test_both_espn_parsers_rate_every_row_before_the_slice():
    from engine.sources import espnplays
    src = (ROOT / "engine" / "sources" / "espnplays.py").read_text()
    assert src.count("    _rate(rows, league, payload)\n    return rows[-limit:] if limit and limit > 0 else rows") == 2
    payload = {"drives": {"previous": [{"team": {"abbreviation": "PIT"}, "plays": [
        {"id": "11", "type": {"text": "Rush"}, "period": {"number": 1}, "statYardage": 3, "awayScore": 3, "homeScore": 3},
        {"id": "12", "type": {"text": "Passing Touchdown"}, "period": {"number": 1}, "statYardage": 40,
         "scoringPlay": True, "awayScore": 10, "homeScore": 3}]}]},
        "winprobability": [{"playId": "11", "homeWinPercentage": 0.55}, {"playId": "12", "homeWinPercentage": 0.38}]}
    rows = espnplays.football_plays(payload, "nfl", 1)
    assert len(rows) == 1 and rows[0]["wp"] == 38.0 and rows[0]["wpa"] == -17.0 and rows[0]["swing"] == "go_ahead"
    assert espnplays.big_play({"kind": "hoops", "event": "Layup", "rating": 6.0}), "a play that moved the game is big"


# --- baseball's facts ---------------------------------------------------------
def test_an_at_bat_carries_its_index_its_outs_and_how_far_it_went():
    from engine.mlb.sources import pbp
    pay = {"allPlays": [{"result": {"event": "Home Run", "rbi": 3, "awayScore": 7, "homeScore": 8},
                         "about": {"inning": 10, "halfInning": "bottom", "atBatIndex": 71},
                         "count": {"outs": 1},
                         "matchup": {"batter": {"fullName": "Pete Alonso"}, "pitcher": {"fullName": "Pete Fairbanks"}},
                         "playEvents": [{"isPitch": True, "details": {"isInPlay": True},
                                         "hitData": {"totalDistance": 416, "launchSpeed": 108}}]}]}
    row = pbp.recent_plays(pay)[0]
    assert row["at_bat"] == 71 and row["outs"] == 1 and row["distance"] == 416


def test_the_live_build_rates_each_at_bat_off_mlbs_win_chance():
    import live_build as LB
    import engine.mlb.sources.pbp as P
    pay = {"allPlays": [
        {"result": {"event": "Strikeout", "awayScore": 7, "homeScore": 5}, "about": {"inning": 10, "halfInning": "bottom", "atBatIndex": 70},
         "matchup": {"batter": {"fullName": "A"}, "pitcher": {"fullName": "P"}}},
        {"result": {"event": "Home Run", "rbi": 3, "awayScore": 7, "homeScore": 8}, "about": {"inning": 10, "halfInning": "bottom",
         "atBatIndex": 71}, "matchup": {"batter": {"fullName": "Pete Alonso"}, "pitcher": {"fullName": "P"}}}]}
    keep = (P.fetch_live_playbyplay, P.fetch_live_win_probability, LB._box_players)
    P.fetch_live_playbyplay = lambda pk, ttl=30: pay
    P.fetch_live_win_probability = lambda pk, ttl=10: [{"atBatIndex": 70, "homeTeamWinProbability": 18.0},
                                                      {"atBatIndex": 71, "homeTeamWinProbability": 100.0}]
    LB._box_players = lambda g: []
    try:
        games = [{"game_pk": 1, "home": "NYM", "away": "TB", "live": {"state": "live", "start_time": ""}}]
        LB.attach_plays(games)
    finally:
        P.fetch_live_playbyplay, P.fetch_live_win_probability, LB._box_players = keep
    hr = games[0]["plays"][-1]
    assert hr["wpa"] == 82.0 and hr["swing"] == "walkoff" and hr["rating"] >= 9.8
    assert games[0]["big"][-1] is hr


def test_the_box_row_carries_his_line_and_his_season_beside_the_stats():
    from engine.mlb.livestats import box_rows
    bs = {"teams": {"home": {"players": {"ID1": {
        "person": {"fullName": "Pete Alonso"}, "position": {"abbreviation": "1B"},
        "stats": {"batting": {"atBats": 5, "hits": 1, "rbi": 3, "homeRuns": 1, "plateAppearances": 5}, "pitching": {}},
        "seasonStats": {"batting": {"homeRuns": 15}}}}},
        "away": {"players": {"ID2": {"person": {"fullName": "Pete Fairbanks"}, "position": {"abbreviation": "P"},
                                     "stats": {"batting": {}, "pitching": {"inningsPitched": "0.1", "strikeOuts": 1,
                                                                           "earnedRuns": 2, "numberOfPitches": 11,
                                                                           "battersFaced": 3}}}}}}}
    rows = {r["player"]: r for r in box_rows(bs, "NYM", "TB")}
    assert rows["Pete Alonso"]["line"] == {"batting": {"ab": 5, "h": 1, "rbi": 3, "hr": 1}}
    assert rows["Pete Alonso"]["season_hr"] == 15
    assert rows["Pete Fairbanks"]["line"] == {"pitching": {"k": 1, "er": 2, "p": 11, "ip": "0.1"}}
    assert "line" not in rows["Pete Alonso"]["stats"], "the box table draws every key in stats"


# --- the card -----------------------------------------------------------------
def _fn(name):
    i = CHAT.index(f"function {name}(")
    return CHAT[i:CHAT.index("\n}\n", i) + 3]


def _const(name):
    i = CHAT.index(f"const {name} = ")
    return CHAT[i:CHAT.index(";\n", i) + 2]


def _run(body):
    node = shutil.which("node")
    if not node:
        return None
    js = "\n".join([
        "const chEsc = (s) => String(s == null ? '' : s);",
        "const chatPlayKey = (p) => String(p.id || p.at_bat || '');",
        "const playTitleOf = (p) => `${p.team ? p.team + ' ' : ''}${p.event}`;",
        "const playerAvatar = (n, t, o) => `<i data-a='${n}'></i>`;",
        _const("PC_SWING"), _const("PC_SFX"), _const("pcOrd"), _const("pcShort"), _const("pcNorm"),
        _fn("pcBox"), _fn("pcLine"), _fn("pcPeople"), _fn("pcTitle"), _fn("pcWin"), _fn("pcFacts"), _fn("pcBodyHTML"),
        body])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


GAME = {"home": "NYM", "away": "TB", "players": [
    {"player": "Pete Alonso", "line": {"batting": {"ab": 5, "h": 1, "rbi": 3, "hr": 1}}, "season_hr": 15},
    {"player": "Pete Fairbanks", "line": {"pitching": {"ip": "0.1", "k": 1, "er": 2, "p": 11}}}]}
WALKOFF = {"kind": "atbat", "at_bat": 71, "event": "Home Run", "rbi": 3, "distance": 416, "half": "B", "inning": 10,
           "batter": "Pete Alonso", "pitcher": "Pete Fairbanks", "swing": "walkoff", "wp": 100.0, "wpa": 82.0,
           "rating": 9.8, "away_score": 7, "home_score": 8}


def test_the_card_says_what_reals_says():
    out = _run(f"""const g = {json.dumps(GAME)}, p = {json.dumps(WALKOFF)};
      console.log(JSON.stringify({{ title: pcTitle(p, g), html: pcBodyHTML(p, g, [p], true) }}));""")
    if out is None:
        print("  SKIP node not installed")
        return
    assert out["title"] == "Walk-off 416-ft 3-run homer"
    html = out["html"]
    assert "<b>P. Alonso</b> · 1/5, 1 HR, 3 RBI" in html
    assert "<b>P. Fairbanks</b> · 0.1 IP, 1 K, 2 ER, 11 P" in html
    assert "15th homer this season" in html
    assert "NYM win chance 18% → 100%" in html, "and what Real's doesn't say"
    assert "pcard-swing" not in html, "the walk-off is in the headline already"


def test_a_season_count_is_right_whichever_side_of_the_play_the_box_is():
    """The box may be a pass behind the homer (it counts 14 and 0 tonight)
    or ahead of it (16 and 2, a second homer since): the first homer is
    the 15th either way."""
    first = dict(WALKOFF, at_bat=40, swing="", distance=None)
    later = dict(WALKOFF, at_bat=71)
    behind = dict(GAME, players=[{"player": "Pete Alonso", "line": {"batting": {"ab": 3, "h": 0, "hr": 0}}, "season_hr": 14}])
    ahead = dict(GAME, players=[{"player": "Pete Alonso", "line": {"batting": {"ab": 5, "h": 2, "hr": 2}}, "season_hr": 16}])
    out = _run(f"""const a = {json.dumps(first)}, b = {json.dumps(later)};
      console.log(JSON.stringify([pcFacts(a, {json.dumps(behind)}, [a], true), pcFacts(a, {json.dumps(ahead)}, [a, b], true),
                                  pcFacts(b, {json.dumps(ahead)}, [a, b], true)]));""")
    if out is None:
        return
    assert out[0] == ["15th homer this season"] and out[1] == ["15th homer this season"]
    assert out[2] == ["16th homer this season", "2nd homer tonight"]


def test_football_and_basketball_lines():
    g = {"home": "NO", "away": "PIT", "players": [
        {"player": "Aaron Rodgers", "stats": {"pass_cmp": 19, "pass_att": 30, "pass_yds": 212, "pass_td": 1, "pass_int": 0}},
        {"player": "DK Metcalf", "stats": {"receptions": 2, "rec_yds": 56, "rec_td": 1}},
        {"player": "Star Guard", "stats": {"pts": 31, "reb": 4, "ast": 9}}]}
    td = {"id": "7", "kind": "football", "event": "Passing Touchdown", "team": "PIT", "scoring": True,
          "players": ["Aaron Rodgers", "DK Metcalf"], "wp": 30.0, "wpa": -25.0}
    hoop = {"id": "8", "kind": "hoops", "event": "Three Point Jumper", "scoring": True, "points": 3, "player": "Star Guard"}
    out = _run(f"""const g = {json.dumps(g)};
      console.log(JSON.stringify([pcBodyHTML({json.dumps(td)}, g, null, false), pcBodyHTML({json.dumps(hoop)}, g, null, false)]));""")
    if out is None:
        return
    assert "<b>A. Rodgers</b> · 19/30, 212 yds, 1 TD" in out[0] and "<b>D. Metcalf</b> · 2 rec, 56 yds, 1 TD" in out[0]
    assert "PIT win chance 45% → 70%" in out[0], "the away side's chance is the complement"
    assert "<b>S. Guard</b> · 31 pts, 4 reb, 9 ast" in out[1] and "S. Guard has 31 points" in out[1]


def test_both_cards_carry_it_and_a_share():
    feed = _fn("pfItemHTML")
    room = _fn("chatPlayCardHTML")
    for body in (feed, room):
        assert "pcBodyHTML(" in body and "pcRate(p)" in body and "pcShareHTML(" in body
    assert "data-pc-share" in _fn("pcShareHTML")
    share = CHAT[CHAT.index("async function pcShare("):]
    share = share[:share.index("\n}\n")]
    assert "navigator.share" in share and "navigator.clipboard.writeText" in share and "/play/" in share
    app = (ROOT / "web" / "js" / "app.js").read_text()
    assert 'if (parts[2] === "play" && parts[3]) window._chatWantPlay' in app
    assert "chatOpen({ play: want.play })" in CHAT, "a shared play's link lands on its thread"
    for cls in (".pcard-row", ".pcard-title", ".pcard-line", ".pcard-win", ".pcard-fact", ".pcard-swing", ".pcard-rate", ".pcard-share"):
        assert cls in CSS, cls


def test_the_game_page_draws_the_win_chance_across_the_game():
    """What Real does not draw: the feed's own win chance after every play,
    one line, the swings of fifteen points or more dotted. Absent until a
    handful of plays carry a number."""
    detail = (ROOT / "web" / "js" / "detail.js").read_text()
    assert "${pbpWinChartHTML(d, league)}" in detail
    fn = detail[detail.index("function pbpWinChartHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert 'typeof r.wp === "number"' in fn and "if (rows.length < 4) return \"\";" in fn
    assert 'e.kind === "atbat"' in fn, "baseball reads its at-bats"
    assert "Math.abs(Number(r.wpa) || 0) >= 15" in fn
    css = (ROOT / "web" / "css" / "detail.css").read_text()
    assert ".pbp-wp-line" in css and "gradient" not in css[css.index(".pbp-wp {"):]


def test_a_groundout_is_not_a_big_play():
    """The rail's at-bats carry batted-ball data on every ball in play."""
    node = shutil.which("node")
    if not node:
        return
    rink = CHAT[CHAT.index("const PLAY_RINK_WORD = {"):CHAT.index("};", CHAT.index("const PLAY_RINK_WORD = {")) + 2]
    rows = [{"kind": "atbat", "event": "Groundout", "hit": {"distance": 90}},
            {"kind": "atbat", "event": "Double", "hit": {"distance": 300}},
            {"kind": "atbat", "event": "Strikeout"},
            {"kind": "atbat", "event": "Strikeout", "rating": 5.1},
            {"kind": "atbat", "event": "Single", "rbi": 1}]
    js = rink + "\n" + _fn("playIsBig").replace("function playIsBig", "function playIsBig") + \
        f"\nconsole.log(JSON.stringify({json.dumps(rows)}.map(playIsBig)));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [False, True, False, True, True]


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
