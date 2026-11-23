"""A college game's picks and parlays wait for both schools' game-day availability reports (step ADF, decision 20).

The four conferences' schools post a last availability report on game day: the Big Ten's and the ACC's two hours
before kickoff, the SEC's and the Big 12's 90 minutes before, which is when college's games post their picks and
parlays. So, as an NFL game waits for both clubs' inactives (step ACB), a college game between two schools that file
(the build's ``availability_due``) posts at 90 minutes only once both schools' game-day reports are in
(``availability_in``), else the first build after they are, else 50 minutes before kickoff; a game whose schools
file nothing posts at 90 minutes as before.

Run directly: `python3 tests/test_a_college_games_picks_wait_for_its_game_day_reports.py`
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP                  # noqa: E402
from engine import gamereport as GR                   # noqa: E402

START = dt.datetime(2026, 11, 28, 20, 30, tzinfo=dt.timezone.utc)      # 3:30 PM ET
G = {"home": "ALA", "away": "AUB", "date": "2026-11-28", "kickoff": "2026-11-28T20:30:00Z"}


def _at(minutes_before):
    return START - dt.timedelta(minutes=minutes_before)


def test_a_game_between_two_reporting_schools_waits_for_both_game_day_reports():
    due = {"availability_due": ["ALA", "AUB", "UGA"], "availability_in": []}
    assert GP.inactives_ready(due, G, "cfb") is False
    assert GP.inactives_ready(dict(due, availability_in=["ALA"]), G, "cfb") is False
    assert GP.inactives_ready(dict(due, availability_in=["ALA", "AUB"]), G, "cfb") is True
    assert GP.post_due(START, "cfb", _at(85), False) == (False, _at(50), True), "its time, the reports not in"
    assert GP.post_due(START, "cfb", _at(85), True) == (True, _at(90), False)
    assert GP.post_due(START, "cfb", _at(49), False)[0] is True, "the deadline"


def test_a_game_whose_schools_file_nothing_posts_as_before():
    assert GP.inactives_ready({"availability_due": ["UGA"], "availability_in": []}, G, "cfb") is None
    assert GP.inactives_ready({}, G, "cfb") is None, "the board does not say: as before"
    one = {"availability_due": ["ALA"], "availability_in": ["ALA"]}
    assert GP.inactives_ready(one, G, "cfb") is True, "only the school that files owes its report"


def test_waiting_the_picks_and_the_parlays_say_what_for():
    w = GR.picks_wait("cfb", G, now=_at(85), ready=False)
    assert w["text"].startswith("Our picks for this game post once both schools' game-day availability reports are "
                                "in, at Sat 2:40 PM ET at the latest"), w["text"]
    x = dict(G, threes=[{"legs": []}])
    assert GP.hold_until_post(x, "cfb", now=_at(85), ready=False) == "2026-11-28T19:40:00Z"
    assert x["post_note"].startswith("This game's parlays post once both schools' game-day availability reports are in")
    assert GP.wait_words("nfl") == "both teams' inactives are in"


def test_the_college_build_says_whose_reports_are_in():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert 'out[_adk] = list(_avail_note.get("due") or [])' in src
    assert 'out[_aik] = list(_avail_note.get("final") or [])' in src
    inj = (ROOT / "engine" / "sources" / "injuries.py").read_text(encoding="utf-8")
    assert 'due=sorted({r["team"] for r in filed})' in inj
    assert 'final=sorted({r["team"] for r in filed if r.get("final")})' in inj


def test_a_college_sgpx_ticket_keeps_its_own_words():
    from engine import sgpx
    assert sgpx._waits_for_inactives("nfl") and not sgpx._waits_for_inactives("cfb")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
