"""Start A or B? Two to four players side by side, and the call.

Ethan, 2026-10-27: "I don't know how fantasy works … create more features
and think of more features and invent more things for our fantasy room."
The question every manager asks every week, "who do I start, A or B?", had
no tool: each player's week was its own row (docs/FANTASY.md, item 4).

What these hold: the chance one outscores the other is exact under the
head-to-head's model (two normals, a listed player as zero or his week);
the call is the most points at the chance he plays, except when a listed
player's inactives are out before the other locks, when it waits on him;
the clock note says which way the day runs; the floor and the ceiling speak
only when the points are close and both will play; a position with no
measured spread gets points and no chance; a free reader's answer carries
no member field; the server route, Ask and the room all use the one engine.

Run directly: `python3 tests/test_start_a_or_b.py`
"""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fantasy_compare as C                          # noqa: E402
from engine import fantasyweek as FW                             # noqa: E402

WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "fantasy.css").read_text(encoding="utf-8")


def _row(name, team="CIN", pos="RB", ppr=12.0, play=1.0, status=None, ko="13:00", date="2026-11-01", **kw):
    r = {"player": name, "team": team, "position": pos, "opponent": "PIT", "ppr": ppr,
         "half": round(ppr * 0.9, 2), "standard": round(ppr * 0.8, 2), "expected": round(ppr * play, 2),
         "play": play, "game": {"home": team, "away": "PIT", "date": date, "kickoff": ko}}
    sd, rg = FW.spread_for(pos, ppr), FW.range_for(pos, ppr)
    if sd is not None:
        r["sd"] = sd
    if rg is not None:
        r["range"] = list(rg)
    if status:
        r["status"] = status
    r.update(kw)
    return r


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# --- the chance --------------------------------------------------------------------------------

def test_the_chance_is_the_two_normals_when_both_play():
    a, b = C.model({"ppr": 15.0, "sd": 5.0}), C.model({"ppr": 10.0, "sd": 5.0})
    assert abs(C.beats(a, b) - _phi(5 / math.sqrt(50))) < 1e-9
    assert abs(C.beats(a, b) + C.beats(b, a) - 1) < 1e-9, "one of the two outscores the other"
    assert C.beats(a, dict(a)) == 0.5


def test_a_listed_player_is_zero_or_his_week():
    a = C.model({"ppr": 20.0, "sd": 6.0, "play": 0.5})
    b = C.model({"ppr": 10.0, "sd": 6.0})
    both = _phi(10 / math.sqrt(72))
    assert abs(C.beats(a, b) - 0.5 * both) < 1e-9, "half the time he sits and scores nothing"
    assert abs(C.beats(a, b, if_both_play=True) - both) < 1e-9
    assert abs(C.beats(b, a) - (0.5 * (1 - both) + 0.5)) < 1e-9, "a player who plays beats one who does not"


def test_no_spread_no_chance():
    assert C.beats(C.model({"ppr": 8.0}), C.model({"ppr": 7.0})) is None


def test_the_league_s_scoring_scales_the_week_and_its_spread():
    m = C.model({"ppr": 20.0, "half": 16.0, "sd": 8.0, "range": [10.0, 30.0]}, "half-ppr")
    assert m["if_plays"] == 16.0 and abs(m["sd"] - 6.4) < 1e-9 and (m["lo"], m["hi"]) == (8.0, 24.0)
    assert C.scoring_key("Half PPR") == "half" and C.scoring_key("standard") == "standard"
    assert C.scoring_key("anything") == "ppr"
    m = C.model({"ppr": 9.0, "range": [2.0, 14.815]})
    assert abs(m["sd"] - (12.815 / C.SPAN_SD)) < 1e-9, "a range with no spread gives one"


# --- the call ----------------------------------------------------------------------------------

def test_the_call_is_the_most_points_and_how_often():
    got = C.compare([_row("Back B", ppr=11.0), _row("Back A", ppr=16.0)])
    assert got["call"]["start"] == "Back A" and got["call"]["order"] == ["Back A", "Back B"]
    p = got["pairs"][0]["p"]
    assert p > 0.6 and got["call"]["text"] == f"Start Back A: he outscores Back B {round(p * 100)}% of the time."
    assert got["scoring"] == "PPR" and [c["player"] for c in got["players"]] == ["Back A", "Back B"]


def test_a_coin_flip_is_said_as_one():
    got = C.compare([_row("WR One", pos="WR", ppr=12.0), _row("WR Two", pos="WR", ppr=11.8)])
    assert got["call"]["coin"] and got["call"]["text"].startswith("A coin flip: WR One by 0.2 points")
    assert "Too close for the numbers to split them: either is a fine start." in got["notes"]


def test_a_listed_player_who_plays_first_is_waited_on():
    """His inactives are out 90 minutes before his own kickoff, before the
    other locks: nothing has to be decided on the chance."""
    got = C.compare([_row("Back A", ppr=15.0, play=0.65, status="Questionable", ko="13:00"),
                     _row("Back B", team="DET", ppr=11.0, ko="16:25")])
    call = got["call"]
    assert call["conditional"] and call["start"] == "Back A" and call["if_out"] == "Back B"
    p_if = got["pairs"][0]["p_if_both_play"]
    assert call["text"] == ("Wait on Back A (questionable, 65% to play): his inactives are out about "
                            "Sun 11:30 AM ET, before Back B's game locks. Active: start him (he outscores "
                            f"Back B {round(p_if * 100)}% of the time when he plays). Out: start Back B.")
    assert not any("Back A is questionable" in n for n in got["notes"]), "the call already said it"


def test_a_listed_player_who_plays_later_is_decided_on_the_chance():
    got = C.compare([_row("Back A", ppr=15.0, play=0.65, status="Questionable", ko="16:25"),
                     _row("Back B", team="DET", ppr=11.0, ko="13:00")])
    assert not got["call"]["conditional"] and got["call"]["start"] == "Back B", "11.0 beats 9.75 at his chance"
    note = next(n for n in got["notes"] if n.startswith("Back A is questionable"))
    assert "Back B locks before Back A's inactives are out (about Sun 2:55 PM ET)" in note
    assert "on the chance it is Back B" in note
    # The listed man who leads even at his chance: have a late bench player ready.
    got = C.compare([_row("Back A", ppr=22.0, play=0.8, status="Questionable", ko="16:25"),
                     _row("Back B", team="DET", ppr=11.0, ko="13:00")])
    assert got["call"]["start"] == "Back A" and not got["call"]["conditional"]
    assert any("only a bench player in a game at Sun 4:25 PM ET or later can replace him" in n
               for n in got["notes"])


def test_a_listed_player_who_loses_even_when_he_plays():
    got = C.compare([_row("Back A", ppr=9.0, play=0.6, status="Questionable", ko="13:00"),
                     _row("Back B", team="DET", ppr=14.0, ko="16:25")])
    assert got["call"]["start"] == "Back B" and not got["call"]["conditional"]
    assert "Back A is questionable, 60% to play, and even if he plays Back B is the better start." in got["notes"]


def test_an_out_player_is_out_and_said_once():
    got = C.compare([_row("Gone", pos="WR", ppr=14.0, play=0.0, status="Out"), _row("Here", pos="WR", ppr=8.0)])
    assert got["call"]["text"] == "Start Here: Gone is out."
    assert not any("scores nothing" in n for n in got["notes"])


def test_floor_and_ceiling_speak_only_when_close_and_both_play():
    wide = _row("Boom", pos="WR", ppr=12.0, sd=8.0, range=[1.0, 28.0])
    tight = _row("Steady", pos="WR", ppr=12.6, sd=4.0, range=[7.0, 19.0])
    got = C.compare([wide, tight])
    assert got["call"]["start"] == "Steady"
    assert any(n.startswith("Boom has the bigger week in him: one week in ten he passes 28.0") for n in got["notes"])
    far = C.compare([dict(wide, ppr=6.0, expected=6.0), tight])
    assert not any("bigger week" in n for n in far["notes"]), "six points apart, the points decide"
    listed = C.compare([dict(wide, play=0.7, expected=8.4, status="Questionable"), tight])
    assert not any("bigger week" in n or "safer start" in n for n in listed["notes"]), \
        "a listed man's floor is a zero"
    safe = C.compare([dict(wide, ppr=12.6, expected=12.6), dict(tight, ppr=12.0, expected=12.0)])
    assert any(n.startswith("Steady is the safer start: eight weeks in ten he scores at least 7.0") for n in safe["notes"])


def test_kickers_get_points_and_no_invented_chance():
    got = C.compare([_row("Kicker One", pos="K", ppr=8.0), _row("Kicker Two", pos="K", ppr=7.4)])
    assert got["call"]["p"] is None and got["call"]["text"] == "Start Kicker One: 0.6 more points this week."
    assert "No measured spread for kickers yet, so the call is on points alone, with no chance to outscore." in got["notes"]


def test_a_defense_is_they():
    a = {"player": "Baltimore Ravens", "team": "BAL", "position": "DEF", "ppr": 10.0, "expected": 10.0,
         "play": 1.0, "sd": 4.0, "range": [4.0, 16.0], "dst": {"sack": 3.1, "int": 0.8, "fum_rec": 0.5}}
    b = dict(a, player="Cleveland Browns", team="CLE", ppr=5.0, expected=5.0)
    got = C.compare([b, a])
    assert got["call"]["text"].startswith("Start Baltimore Ravens: they outscore Cleveland Browns")
    assert got["players"][0]["dst"] == {"sacks": 3.1, "takeaways": 1.3}


def test_fewer_than_two_is_an_error_and_four_is_the_most():
    assert C.compare([_row("One")]) == {"error": "pick two to four players"}
    got = C.compare([_row(f"P{i}", ppr=10.0 + i) for i in range(6)])
    assert len(got["players"]) == 4


# --- the clock ---------------------------------------------------------------------------------

def test_the_kickoff_reads_both_ways_the_board_writes_it():
    assert C.clock(C.kickoff({"date": "2026-11-01", "kickoff": "13:00"})) == "Sun 1:00 PM ET"
    assert C.clock(C.kickoff({"date": "2026-10-29", "kickoff": "20:15"})) == "Thu 8:15 PM ET"
    assert C.clock(C.kickoff({"kickoff": "2026-10-25T17:00:00Z"})) == "Sun 1:00 PM ET", "daylight time"
    assert C.clock(C.kickoff({"kickoff": "2026-11-08T18:00:00Z"})) == "Sun 1:00 PM ET", "standard time"
    assert C.kickoff({"date": "2026-11-01"}) is None and C.kickoff(None) is None
    assert C.kickoff({"date": "2026-11-01", "kickoff": "soon"}) is None


# --- the member's fields -----------------------------------------------------------------------

def test_a_free_reader_gets_no_member_field():
    full = _row("Back A", ppr=15.0, proj={"rush_yds": 70.0, "receptions": 3.2, "rec_yds": 24.0},
                td_prob=0.48, reasons=[{"step": "defense", "why": "PIT give up the most to backs"}],
                matchup={"grade": "soft", "text": "PIT allow 30 a game"})
    other = _row("Back B", team="DET", ppr=11.0)
    doc = {"players": [full, other]}
    paid = C.compare(doc["players"])["players"][0]
    assert paid["line"]["rush_yds"] == 70.0 and paid["td_prob"] == 0.48
    assert paid["why"] == ["PIT give up the most to backs"] and paid["matchup"]["grade"] == "soft"
    free = C.compare(FW.free_view(doc)["players"])["players"][0]
    assert not {"line", "td_prob", "why"} & set(free), sorted(free)
    assert free["matchup"]["grade"] == "soft" and free["floor"] is not None, "the free half is still there"


def test_pick_joins_the_week_s_spellings_and_any_defense_name():
    ravens = {"player": "Baltimore Ravens", "team": "BAL", "position": "DEF", "ppr": 9.0, "expected": 9.0}
    doc = {"players": [_row("Ja'Marr Chase", pos="WR"), _row("Breece Hall", team="NYJ"), ravens]}
    rows, unknown = C.pick(doc, ["ja'marr chase", "Ravens", "Nobody Atall", "Breece Hall", "Breece Hall", ""])
    assert [r["player"] for r in rows] == ["Ja'Marr Chase", "Baltimore Ravens", "Breece Hall"]
    assert unknown == ["Nobody Atall"]


# --- the server, Ask and the room --------------------------------------------------------------

def test_the_route_answers_from_the_week_the_reader_may_see():
    import server
    doc = {"week": 9, "players": [_row("Back A", ppr=15.0), _row("Back B", team="DET", ppr=11.0)]}
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
    h._fantasy_week = lambda: (doc, {"state": "free", "week": 9})
    h._fantasy_compare({"p": ["Back A", "Back B", "Ghost"], "scoring": ["half"]})
    h._fantasy_compare({"p": ["Back A"]})
    h._fantasy_week = lambda: ({}, {"state": "stale", "note": "Week 8's games are over"})
    h._fantasy_compare({"p": ["Back A", "Back B"]})
    code, body = sent[0]
    assert code == 200 and body["call"]["start"] == "Back A" and body["scoring"] == "half-PPR"
    assert body["unknown"] == ["Ghost"] and body["state"] == "free" and body["week"] == 9
    assert sent[1][1]["error"] == "Pick two to four of this week's players."
    assert sent[2][1] == {"state": "stale", "note": "Week 8's games are over"}
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/fantasy/compare"' in src
    i = src.index("def _fantasy_compare(")
    assert "self._fantasy_week()" in src[i:src.index("\n    def ", i + 10)], "the reader's own copy"


def test_ask_quotes_the_same_call():
    from engine import askbot as AB
    import tempfile
    import datetime as _dt
    soon = (_dt.date.today() + _dt.timedelta(days=3)).isoformat()
    doc = {"week": 9, "players": [_row("Back A", ppr=15.0, date=soon), _row("Back B", team="DET", ppr=11.0, date=soon)],
           "byes": [], "listed": {}, "teams": {"CIN": {"date": soon}, "DET": {"date": soon}}}
    d = Path(tempfile.mkdtemp())
    (d / FW.FILE).write_text(json.dumps(doc))
    was, AB.PAID_DIR = AB.PAID_DIR, str(d)
    hist = AB.HISTORY_DB
    AB.HISTORY_DB = str(d / "none.db")
    try:
        got = AB.fantasy_points({}, ["Back A", "back b"])
    finally:
        AB.PAID_DIR, AB.HISTORY_DB = was, hist
        shutil.rmtree(d, ignore_errors=True)
    assert got["compare"]["call"] == C.compare(doc["players"])["call"]
    assert "compare" in " ".join(AB.SYSTEM.split()) and "lead with its call" in " ".join(AB.SYSTEM.split())


def _fn(name):
    i = WEEK_JS.index(f"function {name}(")
    i = WEEK_JS.rindex("\n", 0, i) + 1
    return WEEK_JS[i:WEEK_JS.index("\n  }\n", i) + 4]


def test_the_room_draws_it_above_the_list_and_asks_the_server():
    room = _fn("room")
    assert room.index("${compareHTML(w)}") < room.index('class="rec-bf-group ffw-pos"')
    assert "fetch(`/api/fantasy/compare?${qs}`)" in WEEK_JS
    assert "if (ask !== cmpAsk) return;" in _fn("cmpRun"), "an older answer never paints over a newer pick"
    bind = _fn("bind")
    for hook in ("[data-ffcadd]", "[data-ffcdel]", "[data-ffcsc]", '"input"', '"keydown"'):
        assert hook in bind, hook
    assert "try {" in _fn("cmpScoring") and "CMP_SC_KEY" in _fn("cmpScoring")


def test_every_class_it_draws_is_styled():
    drawn = set(re.findall(r'\bffc-[a-z-]+', WEEK_JS)) - {"ffc-names", "ffc-in"} | {"ffc-in"}
    styled = set(re.findall(r'\.(ffc-[a-z-]+)', CSS))
    assert drawn <= styled | {"ffc-names"}, sorted(drawn - styled)
    assert "!important" not in CSS[CSS.index("START A OR B?"):]


def test_the_typed_name_and_the_stat_line_in_node():
    if not shutil.which("node"):
        return
    harness = ("const ffNorm=(s)=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');\n"
               + _fn("cmpFind") + _fn("cmpLine")
               + "\nconst w={players:[{player:\"Ja'Marr Chase\"},{player:'Chase Brown'},{player:'Breece Hall'}]};"
               "process.stdout.write(JSON.stringify([cmpFind(w,'breece'),cmpFind(w,'chase'),cmpFind(w,\"ja'marr chase\"),"
               "cmpFind(w,''),cmpLine({position:'QB',line:{pass_yds:251.4,pass_td:1.84,rush_yds:21}}),"
               "cmpLine({position:'WR',line:{receptions:5.83,rec_yds:71.2,rush_yds:1.2}})]));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = json.loads(out.stdout)
    assert got[0] == "Breece Hall" and got[1] is None, "two players hold 'chase': keep typing"
    assert got[2] == "Ja'Marr Chase" and got[3] is None
    assert got[4] == "251 pass yds, 1.8 pass TD, 21 rush yds"
    assert got[5] == "5.8 catches, 71 rec yds", "a receiver's yard of rushing is not his line"


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
