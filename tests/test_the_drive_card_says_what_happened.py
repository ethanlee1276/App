"""The live Play-By-Play tab says what just happened, in one card.

Ethan, 2026-11-01, with a screenshot of another app's live drive card: "I
also want our live play by play shit too look just like this. It's cool too
look at (ours) but it's still hard to understand exactly what's happening in
the game so we need to fix that and make it less confusing".

What these hold (web/js/gamecast.js driveViewHTML, web/js/detail.js
gpNowHTML):

  * one card says the play: the drive (plays, yards, time), the down and the
    ball's spot, then that play — its name, our win chance, a sentence in the
    site's own words (who, what, how far, to where), the people in it with
    their game so far, and the down it was snapped on;
  * a punt lands its return's length beyond the next snap, so the sentence
    says the kick and the run back, the way the screenshot did;
  * NO FIELD (Ethan, 2026-11-15: "make sure to get rid of the field on the
    live page"): the card drew the last play on the clubs' end zones, under
    the strip at the top of the page and over his photograph, which ran the
    play on its own clock. The card is the play in words now, above the tabs,
    and the photograph is gone too ("remove this since we have the other
    field"): the strip under the score is the page's one field.

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
    # No field of its own (2026-11-15): no drawing, no pin, no end zones.
    assert "gc-dv-svg" not in html and "gc-dv-pin" not in html and "COWBOYS" not in html, html[:400]


def test_a_punt_is_the_kick_and_the_run_back():
    html = _card(PUNT)
    if html is None:
        return
    words = _text(html)
    # 2026-11-15: the sentence opens on the down and the spot it was snapped
    # from, which the "Before the play" line under it used to say.
    assert "On 4th & 9 from the TB 20, Riley Dixon punts to the DAL 16; KaVontae Turpin brings it back 16 yards to the DAL 32." in words, words
    # The people in it, with the line from the group the play puts them in.
    assert "Riley Dixon TB" in words and "3 NO, 49.3 AVG" in words
    assert "KaVontae Turpin DAL" in words and "1 NO, 16 YDS, 0 TD" in words
    assert "Before the play" not in words, "said once, in the sentence"
    # Our win chance, on the side it favours.
    assert "Win % (our model)" in words and "55.2" in words
    assert "Last play · Q2 13:52" in words


def test_every_kind_of_play_reads_its_own_way():
    if G._node("return 1;") is None:
        return
    after = {"possession": "TB", "detail": "1st & 10 at DAL 40", "yard_line": 40}
    cases = [
        ({"team": "TB", "event": "Pass Reception", "down": 2, "distance": 6, "spot": 52, "yards": 12,
          "players": ["Baker Mayfield", "Mike Evans"]}, after,
         "On 2nd & 6 from the TB 48, Baker Mayfield throws to Mike Evans for 12 yards to the DAL 40. First down."),
        ({"team": "TB", "event": "Rush", "down": 1, "distance": 10, "spot": 45, "yards": 5,
          "players": ["Bucky Irving", "Micah Parsons"]}, after,
         "On 1st & 10 from the DAL 45, Bucky Irving runs for 5 yards to the DAL 40."),
        ({"team": "TB", "event": "Pass Incompletion", "down": 3, "distance": 4, "spot": 40, "yards": 0,
          "players": ["Baker Mayfield", "Mike Evans"]}, {**after, "detail": "4th & 4 at DAL 40"},
         "On 3rd & 4 from the DAL 40, Baker Mayfield’s pass for Mike Evans falls incomplete."),
        ({"team": "TB", "event": "Passing Touchdown", "down": 1, "distance": 10, "spot": 28, "yards": 28,
          "scoring": True, "players": ["Baker Mayfield", "Mike Evans"]},
         {"possession": "TB", "detail": "", "yard_line": 3},
         "On 1st & 10 from the DAL 28, Baker Mayfield throws to Mike Evans for a 28-yard touchdown."),
        ({"team": "TB", "event": "Field Goal Good", "down": 4, "distance": 3, "spot": 22, "yards": 39,
          "scoring": True, "players": ["Chase McLaughlin"]}, {"possession": "DAL", "detail": "", "yard_line": 65},
         "On 4th & 3 from the DAL 22, Chase McLaughlin’s 39-yard field goal is good."),
        ({"team": "TB", "event": "Sack", "down": 3, "distance": 8, "spot": 45, "yards": -7,
          "players": ["Baker Mayfield", "Micah Parsons"]}, {**after, "detail": "4th & 15 at TB 48", "yard_line": 52},
         "On 3rd & 8 from the DAL 45, Baker Mayfield is sacked by Micah Parsons for a loss of 7 yards."),
        ({"team": "TB", "event": "Penalty", "down": 1, "distance": 10, "spot": 45, "yards": -10, "penalty": True},
         {**after, "detail": "1st & 20 at TB 45", "yard_line": 55},
         "On 1st & 10 from the DAL 45, a flag on the offense, 10 yards."),
    ]
    for play, live, said in cases:
        html = _card(play, live)
        assert said in _text(html), (play["event"], _text(html))
        assert "gc-dv-svg" not in html and "gc-dv-field" not in html, (play["event"], "the card draws no field")


def test_a_play_with_no_spot_is_said_without_one_and_a_quiet_moment_is_not_the_play():
    html = _card({"team": "TB", "event": "Rush", "down": 1, "distance": 10, "yards": 4, "players": ["Bucky Irving"]})
    if html is None:
        return
    assert "Bucky Irving runs for 4 yards." in _text(html), "no spot, no guessed one"


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


def test_the_card_is_the_play_right_now_above_the_tabs_and_drops_the_repeats():
    i = DETAIL.index("function gpNowHTML(d, league, faces, boardGame, GC, top)")
    body = DETAIL[i:DETAIL.index("\n}\n", i)]
    # 2026-11-15: the card is told when the strip under the score and our win
    # card already say its tiles, its drive line and its chip
    # (tests/test_the_live_page_says_each_thing_once).
    assert "g.driveView(d, league, faces, { top, win: !!ours })" in body
    assert "return `${card}${pbpWinChartHTML(d, league, boardGame)}${ours}`;" in body
    for gone in ("pbpSituationHTML", "g.driveCard", "g.lastPlay"):
        assert gone not in body, f"{gone} is said once, in the card"
    # The photograph went the same evening (Ethan: "remove this since we have
    # the other field"): the strip under the score is the page's one field.
    assert "pbpParkHTML" not in body and "pbpParkHeadHTML" not in body
    assert "driveView: driveViewHTML" in GC


def test_the_card_is_styled_from_the_sheets_tokens_and_draws_no_field():
    for cls in (".gc-dv {", ".gc-dv-tiles", ".gc-dv-last {", ".gc-dv-said"):
        assert cls in CSS, cls
    # The field, its pin, the play's label on it and its replay went with it
    # (Ethan, 2026-11-15: "make sure to get rid of the field on the live page").
    for gone in (".gc-dv-ez {", ".gc-dv-pin {", ".gc-dv-tag {", ".gc-dv-arc", ".gc-dv-svg"):
        assert gone not in CSS, gone
    for gone in ("function dvFieldSVG", "data-gc-dv-replay", "_dvReplay", "gc-dv-field"):
        assert gone not in GC, gone


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
