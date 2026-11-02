"""The live Play-By-Play tab says what just happened, in one card.

Ethan, 2026-11-01, with a screenshot of another app's live drive card: "I
also want our live play by play shit too look just like this. It's cool too
look at (ours) but it's still hard to understand exactly what's happening in
the game so we need to fix that and make it less confusing".

What these hold (web/js/gamecast.js driveViewHTML, web/js/detail.js
gpPlaysHTML):

  * one card leads the tab: the drive (plays, yards, time), the down and the
    ball's spot, the field with each end zone under its club's name, the
    offence's pin on the line of scrimmage, the line to gain, and the LAST
    PLAY ONLY drawn on it — a kick or a pass as an arc, a run or a return as
    an arrow, its result in words at its end;
  * under the drawing, that play: its name, our win chance, a sentence in the
    site's own words (who, what, how far, to where), the people in it with
    their game so far, and the down it was snapped on;
  * a punt lands its return's length beyond the next snap, so the field
    shows the kick and the run back, the way the screenshot did;
  * the bar chart of the drive, the second "Ball on" strip and the separate
    Last play card are gone from the tab; the photograph stays, under the
    win chance.

Run directly: `python3 tests/test_the_drive_card_says_what_happened.py`
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


class _Harness:
    """test_gamecast's node harness, imported when a test first needs it
    (a sibling test module is not imported at module scope: test_doctor)."""
    def __getattr__(self, name):
        import test_gamecast
        return getattr(test_gamecast, name)


G = _Harness()

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "gamecast.css").read_text(encoding="utf-8")


def _box():
    return [
        {"team": "TB", "groups": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"], "rows": [
                {"name": "Baker Mayfield", "stats": ["14/20", "168", "8.4", "1", "0"], "id": "3052587"}]},
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG"], "rows": [
                {"name": "Mike Evans", "stats": ["5", "71", "14.2", "1", "28"], "id": "16737"}]},
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"], "rows": [
                {"name": "Bucky Irving", "stats": ["9", "44", "4.9", "0", "12"], "id": "4596448"}]},
            {"name": "punting", "labels": ["NO", "YDS", "AVG", "TB", "In 20", "LONG"], "rows": [
                {"name": "Riley Dixon", "stats": ["3", "148", "49.3", "0", "1", "64"], "id": "2971573"}]},
            {"name": "kicking", "labels": ["FG", "PCT", "LONG", "XP", "PTS"], "rows": [
                {"name": "Chase McLaughlin", "stats": ["1/1", "100.0", "39", "1/1", "4"], "id": "3150744"}]},
            {"name": "defensive", "labels": ["TOT", "SOLO", "SACKS"], "rows": [
                {"name": "Vita Vea", "stats": ["3", "2", "1"], "id": "3134690"}]}]},
        {"team": "DAL", "groups": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT"], "rows": [
                {"name": "Dak Prescott", "stats": ["11/17", "120", "7.1", "0", "0"], "id": "2577417"}]},
            {"name": "puntReturns", "labels": ["NO", "YDS", "AVG", "LONG", "TD"], "rows": [
                {"name": "KaVontae Turpin", "stats": ["1", "16", "16.0", "16", "0"], "id": "4277380"}]},
            {"name": "defensive", "labels": ["TOT", "SOLO", "SACKS"], "rows": [
                {"name": "Micah Parsons", "stats": ["4", "3", "1"], "id": "4361423"}]}]},
    ]


def _doc(play, live=None):
    """TB at DAL in the second quarter; ``play`` is the newest snap."""
    lv = {"state": "live", "home_score": 6, "away_score": 7, "period": "Q2", "clock": "13:46",
          "detail": "1st & 10 at DAL 32", "yard_line": 32, "possession": "DAL",
          "win_prob": {"home_win_prob": 0.448, "away_win_prob": 0.552}}
    lv.update(live or {})
    p = {"kind": "football", "id": "p9", "period": 2, "clock": "13:52", "scoring": False, "turnover": False,
         "penalty": False, **play}
    return {"league": "nfl", "home": "DAL", "away": "TB", "live": lv, "box": _box(), "plays": [p],
            "drive": {"team": lv["possession"], "plays": 0, "yards": 0, "elapsed": "0:00", "period": 2}}


def _card(play, live=None):
    import json
    return G._node(f"return QBGamecast.driveView({json.dumps(_doc(play, live))}, 'nfl', {{}});")


def _text(html):
    import html as H
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", html)).split())


# --- the punt in the screenshot ---------------------------------------------------
PUNT = {"team": "TB", "event": "Punt", "down": 4, "distance": 9, "spot": 80, "yards": 16,
        "players": ["Riley Dixon", "KaVontae Turpin", "Vita Vea"]}


def test_the_card_leads_with_the_drive_the_down_and_the_ball():
    html = _card(PUNT)
    if html is None:
        return
    words = _text(html)
    assert 'data-gc-dv' in html and "Current drive" in words and "0 plays, 0 yards, 0:00" in words
    assert "Down 1st & 10" in words and "Ball on DAL 32" in words
    # Each end zone under its own club's name: home at the 0 end, away at the 100.
    assert "COWBOYS" in html and "BUCCANEERS" in html
    assert 'class="gc-dv-los"' in html and 'class="gc-dv-gain"' in html, "the line of scrimmage and the line to gain"
    # The offence's pin sits on the line: DAL's own 32 is 32 from the home goal line.
    pin = re.search(r'class="gc-dv-pin" style="left:([\d.]+)%;top:([\d.]+)%"', html)
    assert pin and 'class="mark">DAL<' in html[pin.end():pin.end() + 80], html[:400]


def test_a_punt_is_the_kick_and_the_run_back():
    html = _card(PUNT)
    if html is None:
        return
    # The kick through the air, then the return along the ground, with its length in words.
    assert html.count('class="gc-dv-arc"') == 1 and html.count('class="gc-dv-ret"') == 1
    assert ">16-yd return<" in html
    words = _text(html)
    assert "Riley Dixon punts to the DAL 16; KaVontae Turpin brings it back 16 yards to the DAL 32." in words, words
    # The people in it, with the line from the group the play puts them in.
    assert "Riley Dixon TB" in words and "3 NO, 49.3 AVG" in words
    assert "KaVontae Turpin DAL" in words and "1 NO, 16 YDS, 0 TD" in words
    assert "Before the play 4th & 9 at TB 20" in words
    # Our win chance, on the side it favours.
    assert "Win % (our model)" in words and "55.2" in words
    assert "Last play · Q2 13:52" in words


def test_every_kind_of_play_draws_and_reads_its_own_way():
    if G._node("return 1;") is None:
        return
    after = {"possession": "TB", "detail": "1st & 10 at DAL 40", "yard_line": 40}
    cases = [
        ({"team": "TB", "event": "Pass Reception", "down": 2, "distance": 6, "spot": 52, "yards": 12,
          "players": ["Baker Mayfield", "Mike Evans"]}, after,
         ['class="gc-dv-arc"', ">12-yd catch<"], "Baker Mayfield to Mike Evans for 12 yards to the DAL 40."),
        ({"team": "TB", "event": "Rush", "down": 1, "distance": 10, "spot": 45, "yards": 5,
          "players": ["Bucky Irving", "Micah Parsons"]}, after,
         ['class="gc-dv-run"', ">5-yd run<"], "Bucky Irving runs for 5 yards to the DAL 40."),
        ({"team": "TB", "event": "Pass Incompletion", "down": 3, "distance": 4, "spot": 40, "yards": 0,
          "players": ["Baker Mayfield", "Mike Evans"]}, {**after, "detail": "4th & 4 at DAL 40"},
         ['class="gc-dv-arc inc"', 'class="gc-dv-x"', ">Incomplete<"], "Baker Mayfield’s pass for Mike Evans falls incomplete."),
        ({"team": "TB", "event": "Passing Touchdown", "down": 1, "distance": 10, "spot": 28, "yards": 28,
          "scoring": True, "players": ["Baker Mayfield", "Mike Evans"]},
         {"possession": "TB", "detail": "", "yard_line": 3},
         [">Touchdown<", "gc-dv-tag td"], "Baker Mayfield finds Mike Evans for a 28-yard touchdown."),
        ({"team": "TB", "event": "Field Goal Good", "down": 4, "distance": 3, "spot": 22, "yards": 39,
          "scoring": True, "players": ["Chase McLaughlin"]}, {"possession": "DAL", "detail": "", "yard_line": 65},
         [">39-yd FG good<", "gc-dv-tag good"], "Chase McLaughlin’s 39-yard field goal is good."),
        ({"team": "TB", "event": "Sack", "down": 3, "distance": 8, "spot": 45, "yards": -7,
          "players": ["Baker Mayfield", "Micah Parsons"]}, {**after, "detail": "4th & 15 at TB 48", "yard_line": 52},
         [">Sack, −7<", "gc-dv-tag bad"], "Baker Mayfield is sacked by Micah Parsons for a loss of 7 yards."),
        ({"team": "TB", "event": "Penalty", "down": 1, "distance": 10, "spot": 45, "yards": -10, "penalty": True},
         {**after, "detail": "1st & 20 at TB 45", "yard_line": 55},
         ['class="gc-dv-run flag"', ">Flag, −10 yds<"], "Penalty on the offense, 10 yds."),
    ]
    for play, live, marks, said in cases:
        html = _card(play, live)
        for mark in marks:
            assert mark in html, (play["event"], mark)
        assert said in _text(html), (play["event"], _text(html))


def test_a_play_with_no_spot_draws_no_path_and_a_quiet_moment_is_not_the_play():
    html = _card({"team": "TB", "event": "Rush", "down": 1, "distance": 10, "yards": 4, "players": ["Bucky Irving"]})
    if html is None:
        return
    assert "gc-dv-arc" not in html and "gc-dv-run" not in html and "gc-dv-tag" not in html, "no spot, no guessed path"
    assert "Bucky Irving runs for 4 yards." in _text(html)
    assert "data-gc-dv-replay" not in html, "nothing drawn, nothing to replay"


def test_a_finished_drive_gives_way_to_the_side_with_the_ball():
    """The drive on file ended in the punt; the ball is the other side's,
    whose drive has not had a play: "0 plays, 0 yards, 0:00"."""
    import json
    doc = _doc(PUNT)
    doc["drive"] = {"team": "TB", "plays": 5, "yards": 17, "elapsed": "2:48", "period": 2, "result": "Punt"}
    # Then a TV timeout (nothing to a reader) and a team's own timeout (something).
    doc["plays"] += [{"kind": "football", "id": "p10", "period": 2, "clock": "13:46", "team": "DAL", "event": "Official Timeout"},
                     {"kind": "football", "id": "p11", "period": 2, "clock": "13:46", "team": "DAL", "event": "Timeout"}]
    html = G._node(f"return QBGamecast.driveView({json.dumps(doc)}, 'nfl', {{}});")
    if html is None:
        return
    head = html[html.index('class="gc-dv-head"'):html.index('class="gc-dv-end"')]
    assert 'class="mark">DAL<' in head and "0 plays, 0 yards, 0:00" in _text(head), _text(head)
    words = _text(html)
    assert "Timeout" in words and "TV timeout" not in words, words


def test_the_tab_leads_with_the_card_and_drops_the_repeats():
    i = DETAIL.index("function gpPlaysHTML(d, league, faces, boardGame, lastPlay, GC)")
    body = DETAIL[i:DETAIL.index("\n}\n", i)]
    assert "g.driveView(d, league, faces)" in body
    assert "return `${card}${live ? pbpCallItHTML(d, league) : \"\"}${win}${view}${chart}${gpDrivesHTML(d, league)}`;" in body
    for gone in ("pbpSituationHTML", "g.driveCard", "g.lastPlay"):
        assert gone not in body, f"{gone} is said once, in the card"
    assert "pbpParkHTML(d, league, boardGame, lastPlay)" in body, "the photograph stays"
    assert "driveView: driveViewHTML" in GC


def test_the_card_is_styled_from_the_sheets_tokens_and_moves_only_when_asked():
    for cls in (".gc-dv {", ".gc-dv-tiles", ".gc-dv-ez {", ".gc-dv-ezt", ".gc-dv-pin {", ".gc-dv-tag {",
                ".gc-dv-arc", ".gc-dv-run {", ".gc-dv-last {", ".gc-dv-said"):
        assert cls in CSS, cls
    assert "@media (prefers-reduced-motion: reduce) { .gc-dv-tag.late { animation: none; } .gc-dv-ball { display: none; } }" in CSS
    # The ball flies a play once, when it is new or on Replay, not on every poll's redraw.
    assert "const fly = _dvReplay || (!!id && id !== _dvDrawn);" in GC


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
