"""A live play says who did what, where, and what it changed (2026-11-15).

Ethan, on the live NE @ DET page, circling the drive card's "Touchdown / The
Lions for a 56-yard touchdown. / Before the play 3rd & 9 at DET 44": "also
the wording in the live play by play screen is confusing and doesnt make much
snese and is lacking detail of whats happening."

Two causes. The feed's names had been lost on every shotgun snap
(tests/test_pbp_play_names holds that fix). And the rows and the card said a
play by its category: "Pass complete for 7 yds · 2nd & 16", "Penalty on the
offense, 5 yds", a kickoff drawn flying backwards. Now:

  * the builder keeps the play's closed-list facts beside the names
    (engine/sources/espnplays._football_facts): where a pass went, the gap a
    run took, the defenders the play names after it, a touchback or a fair
    catch, and a flag's foul, the man flagged, his side, the yards, declined
    or offsetting. Each is a value from a list or a roster name; ESPN's
    sentence is still never kept;
  * a row reads like a caption (app.js footballLine): "Jared Goff throws deep
    right to Jameson Williams for a 56-yd touchdown";
  * the card's sentence opens on the down and the spot, and says what the
    play changed (gamecast dvSentence): "On 3rd & 9 from the DAL 44, Dak
    Prescott throws deep right to KaVontae Turpin for a 56-yard touchdown.
    Cowboys 13, Buccaneers 7.";
  * a kickoff, filed under the side that receives it with its spot counted
    from the kicking side's end, is drawn from the kicking 35 (gamecast dvPlay).

    python3 tests/test_a_play_says_who_did_what.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine.sources.espnplays import _football_facts, football_plays  # noqa: E402


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


ROWS = _Harness("test_football_plays_read_like_a_person_wrote_them")
CARD = _Harness("test_the_drive_card_says_what_happened")

ROSTER = ("Jared Goff", "Jameson Williams", "Christian Gonzalez", "Jahmyr Gibbs", "Christian Barmore",
          "Kayshon Boutte", "Brian Branch", "Drake Maye", "Hunter Henry", "Frank Ragnow", "Andy Borregales",
          "Jacob Saylors", "Bryce Baringer", "Kelvin Banks Jr.", "Kaleb Johnson", "Logan Jones", "Keion White")


def F(event, text):
    return _football_facts(text, ROSTER, event, "DET", "NE")


# --- the builder: the facts beside the names -----------------------------------
def test_where_a_pass_went_and_the_gap_a_run_took():
    assert F("Passing Touchdown", "(Shotgun) J.Goff pass deep right to J.Williams for 56 yards, TOUCHDOWN.") \
        == {"dir": "dr"}
    assert F("Rush", "J.Gibbs left end to DET 38 for 8 yards (C.Gonzalez).") \
        == {"dir": "le", "by": ["Christian Gonzalez"]}
    assert F("Rush", "(Shotgun) D.Maye scrambles right end to NE 40 for 12 yards (B.Branch).") \
        == {"dir": "re", "scramble": True, "by": ["Brian Branch"]}


def test_the_defenders_the_play_names_after_it():
    assert F("Sack", "(Shotgun) D.Maye sacked at NE 13 for -2 yards (sack split by K.White and C.Barmore).") \
        == {"by": ["Keion White", "Christian Barmore"]}
    assert F("Pass Incompletion", "(Shotgun) D.Maye pass incomplete deep left to H.Henry (B.Branch).") \
        == {"dir": "dl", "by": ["Brian Branch"]}
    # A hit on the passer in square brackets is not a breakup.
    assert "by" not in F("Pass Incompletion", "(Shotgun) D.Maye pass incomplete short right to H.Henry [K.White].")
    # The man who tackled an interception's return is not the play's defender.
    pick = F("Pass Interception Return", "(Shotgun) D.Maye pass short middle intended for H.Henry INTERCEPTED by "
             "B.Branch at NE 40. B.Branch to NE 30 for 10 yards (D.Maye).")
    assert pick == {"dir": "sm"}, pick


def test_a_flag_its_foul_its_man_its_side_and_its_yards():
    assert F("Penalty", "(Shotgun) PENALTY on NE-K.Boutte, False Start, 5 yards, enforced at DET 8 - No Play.") \
        == {"foul": "False Start", "foul_yards": 5, "foul_by": "Kayshon Boutte", "foul_team": "NE"}
    assert F("Penalty", "PENALTY on NE, Delay of Game, 5 yards, enforced at NE 30 - No Play.") \
        == {"foul": "Delay of Game", "foul_yards": 5, "foul_team": "NE"}
    # A flag that wiped out a run: no run to tell, only the flag.
    wiped = F("Penalty", "J.Gibbs left end to DET 38 for 8 yards (C.Gonzalez). PENALTY on DET-F.Ragnow, "
              "Offensive Holding, 10 yards, enforced at DET 30 - No Play.")
    assert wiped == {"foul": "Offensive Holding", "foul_yards": 10, "foul_by": "Frank Ragnow", "foul_team": "DET"}
    stood = F("Rush", "J.Gibbs right tackle to DET 40 for 10 yards (C.Gonzalez). PENALTY on NE-B.Branch, "
              "Defensive Holding, declined.")
    assert stood["foul_declined"] is True and stood["dir"] == "rt" and stood["by"] == ["Christian Gonzalez"]
    # The longest name wins: never "Pass Interference" out of "Defensive Pass Interference".
    assert F("Penalty", "PENALTY on NE-B.Branch, Defensive Pass Interference, 25 yards, enforced at NE 40 - No Play.")[
        "foul"] == "Defensive Pass Interference"
    assert F("Penalty", "PENALTY on NE-B.Branch, Face Mask, offsetting. PENALTY on DET-F.Ragnow, "
             "Unnecessary Roughness, offsetting.")["offsetting"] is True


def test_a_college_flag_names_its_man_in_brackets():
    """College writes "Texas Penalty, False Start (Kelvin Banks Jr.)", and a
    name that ends on its own full stop now matches before a bracket."""
    assert F("Penalty", "Texas Penalty, False Start (Kelvin Banks Jr.) to the TEX 20") \
        == {"foul": "False Start", "foul_by": "Kelvin Banks Jr."}
    run = F("Rush", "Kaleb Johnson run for 5 yds to the IOWA 30 Iowa Penalty, Offensive Holding (Logan Jones) "
            "10 yards to the IOWA 15")
    assert run == {"foul": "Offensive Holding", "foul_yards": 10, "foul_by": "Logan Jones"}, \
        "the flagged man is not a defender"
    # A side the feed writes that is not one of this game's two is left off.
    assert "foul_team" not in F("Penalty", "PENALTY on WAS, Delay of Game, 5 yards, enforced at NE 30 - No Play.")


def test_a_kick_says_a_touchback_or_a_fair_catch():
    assert F("Kickoff", "A.Borregales kicks 65 yards from NE 35 to end zone, Touchback to the DET 35.") \
        == {"touchback": True}
    assert F("Punt", "B.Baringer punts 45 yards to DET 20, Center-J.Cardona, fair catch by J.Saylors.") \
        == {"fair_catch": True}


def test_the_facts_ride_the_row_and_espns_words_do_not():
    pay = {
        "boxscore": {"players": [{"statistics": [{"athletes": [
            {"athlete": {"id": str(i), "displayName": n}} for i, n in enumerate(ROSTER, 1)]}]}]},
        "drives": {"previous": [{"id": "d1", "team": {"abbreviation": "NE"}, "plays": [
            {"id": "p1", "statYardage": -5, "type": {"text": "Penalty"}, "start": {"down": 3, "distance": 8},
             "text": "(Shotgun) PENALTY on NE-K.Boutte, False Start, 5 yards, enforced at DET 8 - No Play."},
            {"id": "p2", "statYardage": 56, "type": {"text": "Passing Touchdown"}, "start": {"down": 3, "distance": 9},
             "text": "(Shotgun) J.Goff pass deep right to J.Williams for 56 yards, TOUCHDOWN."}]}]}}
    flag, td = football_plays(pay, "nfl")[:2]
    assert flag["foul"] == "False Start" and flag["foul_by"] == "Kayshon Boutte" and flag["players"] == ["Kayshon Boutte"]
    assert td["dir"] == "dr" and td["players"] == ["Jared Goff", "Jameson Williams"]
    flat = " ".join(str(v) for row in (flag, td) for v in row.values())
    for words in ("PENALTY on", "enforced at", "No Play", "deep right", "for 56 yards", "Shotgun"):
        assert words not in flat, f"ESPN's wording is on the row ({words})"


# --- a row: who did what, in a line ---------------------------------------------
LINES = [
    ({"event": "Passing Touchdown", "yards": 56, "players": ["Jared Goff", "Jameson Williams"], "dir": "dr"},
     "<b>Jared Goff</b> throws deep right to <b>Jameson Williams</b> for a 56-yd touchdown"),
    ({"event": "Pass Reception", "yards": 7, "players": ["Jared Goff", "Jameson Williams"], "dir": "sl"},
     "<b>Jared Goff</b> throws short left to <b>Jameson Williams</b> for 7 yds"),
    ({"event": "Rush", "yards": 8, "players": ["Jahmyr Gibbs"], "dir": "mid", "by": ["Christian Gonzalez"]},
     "<b>Jahmyr Gibbs</b> runs up the middle for 8 yds"),
    ({"event": "Rush", "yards": -2, "players": ["Jahmyr Gibbs"], "dir": "le"},
     "<b>Jahmyr Gibbs</b> runs around left end for a loss of 2 yds"),
    ({"event": "Rushing Touchdown", "yards": 3, "players": ["Jahmyr Gibbs"], "dir": "rt"},
     "<b>Jahmyr Gibbs</b> runs off right tackle for a 3-yd touchdown"),
    ({"event": "Sack", "yards": -2, "players": ["Drake Maye"], "by": ["Keion White", "Christian Barmore"]},
     "<b>Drake Maye</b> sacked by <b>Keion White</b> and <b>Christian Barmore</b> for a loss of 2 yds"),
    ({"event": "Pass Incompletion", "players": ["Drake Maye", "Hunter Henry"], "dir": "dl", "by": ["Brian Branch"]},
     "<b>Drake Maye</b>’s pass deep left to <b>Hunter Henry</b> incomplete, broken up by <b>Brian Branch</b>"),
    ({"event": "Pass Interception Return", "players": ["Drake Maye", "Hunter Henry", "Brian Branch"], "dir": "sm",
      "turnover": True},
     "<b>Drake Maye</b>’s pass short middle for <b>Hunter Henry</b> intercepted by <b>Brian Branch</b>"),
    ({"event": "Penalty", "yards": -5, "players": ["Kayshon Boutte"], "foul": "False Start", "foul_by": "Kayshon Boutte",
      "foul_yards": 5}, "False start on <b>Kayshon Boutte</b>, 5 yds"),
    ({"event": "Penalty", "yards": -5, "foul": "Delay of Game", "foul_team": "NE", "foul_yards": 5},
     "Delay of game on NE, 5 yds"),
    ({"event": "Penalty", "yards": 0, "offsetting": True, "foul": "Face Mask"}, "Offsetting penalties"),
    ({"event": "Kickoff", "yards": 0, "players": ["Andy Borregales"], "touchback": True},
     "<b>Andy Borregales</b> kicks off, touchback"),
    ({"event": "Kickoff", "yards": 11, "players": ["Jake Bates", "Corey Kiner"]},
     "<b>Jake Bates</b> kicks off; <b>Corey Kiner</b> returns it 11 yds"),
    ({"event": "Punt", "yards": 0, "players": ["Bryce Baringer", "Jacob Saylors"], "fair_catch": True},
     "<b>Bryce Baringer</b> punts, fair catch by <b>Jacob Saylors</b>"),
    ({"event": "Field Goal Good", "yards": 33, "players": ["Andy Borregales"]},
     "<b>Andy Borregales</b> makes a 33-yd field goal"),
    ({"event": "Rush", "yards": 10, "players": ["Jahmyr Gibbs"], "dir": "rt", "foul": "Defensive Holding",
      "foul_by": "Brian Branch", "foul_declined": True},
     "<b>Jahmyr Gibbs</b> runs off right tackle for 10 yds · flag: defensive holding on <b>Brian Branch</b>, declined"),
    # Names that cannot say who did which keep the play's words, then the names.
    ({"event": "Pass Reception", "yards": 7, "players": ["Jared Goff"]}, "Pass complete for 7 yds · <b>Jared Goff</b>"),
    ({"event": "Pass Reception", "yards": 7}, "Pass complete for 7 yds"),
    ({"event": "Penalty", "yards": -10}, "Penalty on the offense, 10 yds"),
]


def test_each_kind_of_play_reads_as_a_line():
    got = ROWS._node(f"""
      const g = {{ home: "DET", away: "NE" }};
      console.log(JSON.stringify({json.dumps([c[0] for c in LINES])}.map((p) => footballLine(p, g, true))));""")
    if got is None:
        return
    for (play, want), line in zip(LINES, got):
        assert line == want, (play["event"], line, want)


def test_a_line_is_escaped_and_plain_without_html():
    got = ROWS._node("""
      const p = { event: "Rush", yards: 4, players: ["A <b>Bad</b> Name"] };
      console.log(JSON.stringify([footballLine(p, {}, true), footballLine(p, {}, false)]));""")
    if got is None:
        return
    assert got[0] == "<b>A &lt;b&gt;Bad&lt;/b&gt; Name</b> runs for 4 yds", got[0]
    assert got[1] == "A <b>Bad</b> Name runs for 4 yds"


def test_a_kickoff_row_carries_the_kicking_side():
    """Filed under DET, who received it; NE's kicker kicked it."""
    got = ROWS._node("""
      const rows = playsHTML({home: "DET", away: "NE", plays: [
        {kind: "football", event: "Kickoff", team: "DET", period: 1, clock: "9:12", yards: 26,
         players: ["Andy Borregales", "Jacob Saylors"]},
        {kind: "football", event: "Rush", team: "DET", period: 1, clock: "9:00", down: 2, distance: 10, yards: 8,
         players: ["Jahmyr Gibbs"], dir: "le"}]});
      console.log(JSON.stringify(rows));""")
    if got is None:
        return
    sides = re.findall(r'<span class="lb-side">(\w+)</span>', got)
    assert sides == ["NE", "DET"], sides
    assert "<b>Andy Borregales</b> kicks off; <b>Jacob Saylors</b> returns it 26 yds" in got
    assert "<b>Jahmyr Gibbs</b> runs around left end for 8 yds" in got


def test_the_row_and_the_drive_head_read_the_line():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    row = app[app.index("const footballRow = (p) =>"):]
    assert "footballLine(p, g, true)" in row[:row.index("\n  };")]
    assert 'typeof footballLine === "function" ? footballLine(key, d) : footballWords(key, d).title' in detail
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".pbp-layout .lb-play .lb-what { white-space: normal;" in css, "the rail's rows wrap, never cut off"


# --- the card: the sentence ---------------------------------------------------------
def _said(play, live=None, opts=None):
    doc = CARD._doc(play, live)
    html = CARD.G._node(f"return QBGamecast.driveView({json.dumps(doc)}, 'nfl', {{}}, {json.dumps(opts or {})});")
    if html is None:
        return None, None
    said = re.search(r'<p class="gc-dv-said">(.*?)</p>', html, re.S)
    import html as H
    return H.unescape(said.group(1)) if said else "", html


def test_ethans_touchdown_reads_who_threw_it_where_to_whom_and_the_score():
    said, _ = _said({"team": "DAL", "event": "Passing Touchdown", "down": 3, "distance": 9, "spot": 44, "yards": 56,
                     "scoring": True, "players": ["Dak Prescott", "KaVontae Turpin"], "dir": "dr",
                     "away_score": 7, "home_score": 13},
                    {"possession": "TB", "detail": "", "yard_line": 65})
    if said is None:
        return
    assert said == ("On 3rd & 9 from the DAL 44, Dak Prescott throws deep right to KaVontae Turpin for a 56-yard "
                    "touchdown. Cowboys 13, Buccaneers 7."), said


def test_the_card_tells_each_kind_with_what_it_changed():
    cases = [
        ({"team": "TB", "event": "Pass Incompletion", "down": 2, "distance": 6, "spot": 52, "yards": 0,
          "players": ["Baker Mayfield", "Mike Evans"], "dir": "dl", "by": ["Micah Parsons"]},
         {"possession": "TB", "detail": "3rd & 6 at TB 48", "yard_line": 52},
         "On 2nd & 6 from the TB 48, Baker Mayfield’s pass deep left for Mike Evans falls incomplete, "
         "broken up by Micah Parsons."),
        ({"team": "TB", "event": "Sack", "down": 3, "distance": 8, "spot": 45, "yards": -7,
          "players": ["Baker Mayfield"], "by": ["Micah Parsons"]},
         {"possession": "TB", "detail": "4th & 15 at TB 48", "yard_line": 52},
         "On 3rd & 8 from the DAL 45, Baker Mayfield is sacked by Micah Parsons for a loss of 7 yards."),
        ({"team": "TB", "event": "Rush", "down": 4, "distance": 2, "spot": 70, "yards": 1,
          "players": ["Bucky Irving"], "dir": "mid"},
         {"possession": "DAL", "detail": "1st & 10 at TB 31", "yard_line": 69},
         "On 4th & 2 from the TB 30, Bucky Irving runs up the middle for 1 yard to the TB 31. Turnover on downs."),
        ({"team": "DAL", "event": "Rush", "down": 2, "distance": 3, "spot": 40, "yards": 12,
          "players": ["KaVontae Turpin"], "dir": "le"},
         {"possession": "DAL", "detail": "1st & 10 at TB 48", "yard_line": 52},
         "On 2nd & 3 from the DAL 40, KaVontae Turpin runs around left end for 12 yards to the TB 48. First down."),
        ({"team": "DAL", "event": "Penalty", "down": 3, "distance": 8, "spot": 40, "yards": -5, "penalty": True,
          "foul": "False Start", "foul_by": "Dak Prescott", "foul_yards": 5},
         {"possession": "DAL", "detail": "3rd & 13 at DAL 35", "yard_line": 35},
         "On 3rd & 8 from the DAL 40, a flag: false start on Dak Prescott (Cowboys), 5 yards."),
        ({"team": "DAL", "event": "Rush", "down": 1, "distance": 10, "spot": 40, "yards": 4, "penalty": True,
          "players": ["KaVontae Turpin"], "foul": "Defensive Holding", "foul_by": "Vita Vea", "foul_declined": True},
         {"possession": "DAL", "detail": "2nd & 6 at DAL 44", "yard_line": 44},
         "On 1st & 10 from the DAL 40, KaVontae Turpin runs for 4 yards to the DAL 44. "
         "A flag for defensive holding on Vita Vea (Buccaneers) is declined."),
    ]
    for play, live, want in cases:
        said, html = _said(play, live)
        if said is None:
            return
        assert said == want, (play["event"], said)
        assert "Before the play" not in CARD._text(html), "the down is said once, in the sentence"


def test_a_kickoff_flies_from_the_kicking_sides_35():
    """Filed under DAL, who received it, at "35": TB kicked from its own 35
    (the 65 on the site's field), DAL brought it back 25 to its 30."""
    said, html = _said({"team": "DAL", "event": "Kickoff", "spot": 35, "yards": 25,
                        "players": ["Chase McLaughlin", "KaVontae Turpin"]},
                       {"possession": "DAL", "detail": "1st & 10 at DAL 30", "yard_line": 30})
    if said is None:
        return
    assert said == "Chase McLaughlin kicks off to the DAL 5; KaVontae Turpin brings it back 25 yards to the DAL 30.", said
    assert ">25-yd return<" in html and 'class="gc-dv-arc"' in html and 'class="gc-dv-ret"' in html
    # The arc starts at the TB 35 end of the field (right of midfield, where TB's end zone is drawn).
    arc = re.search(r'<path class="gc-dv-arc" d="M([\d.]+) ', html)
    mid = re.search(r'<text class="gc-dv-num" x="([\d.]+)"[^>]*>50<', html)
    assert arc and mid and float(arc.group(1)) > float(mid.group(1)), (arc and arc.group(1), mid and mid.group(1))


def test_a_touchback_lands_in_the_end_zone():
    said, html = _said({"team": "DAL", "event": "Kickoff", "spot": 35, "yards": 0, "touchback": True,
                        "players": ["Chase McLaughlin"]},
                       {"possession": "DAL", "detail": "1st & 10 at DAL 35", "yard_line": 35})
    if said is None:
        return
    assert said == "Chase McLaughlin kicks off into the end zone for a touchback.", said
    assert ">Touchback<" in html


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
