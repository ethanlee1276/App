"""Is the twelve-row conference table still right? Derive it, don't recall it.

Fallout from #93. ESPN's groups feed turned out to carry no conference names
at all — three runs, four URL shapes, same answer — so `CONFERENCE_IDS` in
`engine/sources/cfbdata.py` is now the ONLY source for a game's conference.
That matters because `attention_tier` reads the conference to decide how much
of an edge the CFB model believes, and the table still lists `Pac-12`, which
after realignment is two schools rather than a conference.

NEITHER SOURCE CAN ANSWER ALONE, which is why this is a join. CFBD knows
which conference each school is in and knows nothing about ESPN's numeric
ids. The ESPN scoreboard stamps every team with a `conferenceId` and never
says what it is called. One school in both gives one row of
`{conferenceId: name}`; a Saturday gives most of the table.

PROBE ONLY — it prints a comparison and changes nothing. Both CFBD's response
shape and the join's hit rate are unverified, because this container reaches
neither host. So anything that fails gets its shape dumped rather than
guessed at, which is the whole lesson of the four rounds this cost on ESPN's
groups feed: a payload dump should be the first move, not the fourth.

Run directly: `python3 tests/test_conf_table.py`
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbd, cfbdata

import assets

#: CFBD's /teams shape, as far as this needs it.
CFBD_ROWS = [
    {"school": "Alabama", "conference": "SEC"},
    {"school": "Ohio State", "conference": "Big Ten"},
    {"school": "Oregon", "conference": "Big Ten"},
    {"school": "Washington State", "conference": "Pac-12"},
]

#: ESPN's scoreboard, competitors stamped with conferenceId and nothing else
#: that says what the conference is called.
SLATE = {"events": [
    {"competitions": [{"competitors": [
        {"team": {"location": "Alabama", "conferenceId": 8}},
        {"team": {"location": "Ohio State", "conferenceId": 5}},
    ]}]},
    {"competitions": [{"competitors": [
        {"team": {"location": "Oregon", "conferenceId": 5}},
        {"team": {"location": "Washington State", "conferenceId": 9}},
    ]}]},
]}


def _run(cfbd_rows=CFBD_ROWS, slate=None, date="2025-11-01"):
    """Run the probe against stubbed feeds and return what it printed."""
    slate = SLATE if slate is None else slate
    real_get, real_sb = cfbd._get, cfbdata.fetch_scoreboard
    cfbd._get = lambda path, params, cache, api_key=None, ttl=0: (
        cfbd_rows if path in ("/teams", "/teams/fbs", "/conferences") else [])
    cfbdata.fetch_scoreboard = lambda d, ttl=0, **k: slate
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = assets.probe_conference_table(date)
    finally:
        cfbd._get, cfbdata.fetch_scoreboard = real_get, real_sb
    return code, buf.getvalue()


# --- the join ----------------------------------------------------------------
def test_an_id_gets_its_name_from_the_school_both_feeds_share():
    """8 is SEC because Alabama appears in both, not because anyone recalled
    that 8 is SEC."""
    _, out = _run()
    line = next(l for l in out.splitlines() if l.strip().startswith("8 "))
    assert "matches" in line, line


def test_a_conference_that_moved_on_is_named_as_such():
    """The row this whole exercise is about. If CFBD says Washington State's
    conference is now something else, 9 must not keep reading Pac-12."""
    rows = [dict(r) for r in CFBD_ROWS]
    rows[3]["conference"] = "Mountain West"
    _, out = _run(rows)
    line = next(l for l in out.splitlines() if l.strip().startswith("9 "))
    assert "RENAMED -> Mountain West" in line, line


def test_an_id_the_table_has_never_heard_of_is_flagged_new():
    """Realignment adds as well as removes, and a conference we cannot name
    goes to attention_tier as empty — read as standard, never as soft."""
    rows = CFBD_ROWS + [{"school": "Boise State", "conference": "Pac-12"}]
    slate = {"events": [{"competitions": [{"competitors": [
        {"team": {"location": "Boise State", "conferenceId": 777}},
    ]}]}]}
    _, out = _run(rows, slate)
    assert "NEW -> Pac-12" in out, out


def test_one_misjoined_school_cannot_rename_a_conference():
    """Names are matched loosely across two feeds, so some join will be
    wrong eventually. Majority per id means a single bad row is outvoted
    rather than renaming the Big Ten."""
    # The bad row goes FIRST. With it last, "first seen wins" and "majority
    # wins" give the same answer and this proves nothing — which is exactly
    # what the first version of this test did.
    rows = CFBD_ROWS + [{"school": "Ohio", "conference": "MAC"}]
    slate = {"events": [{"competitions": [{"competitors": [
        {"team": {"location": "Ohio", "conferenceId": 5}},
    ]}]}, {"competitions": [{"competitors": [
        {"team": {"location": "Ohio State", "conferenceId": 5}},
        {"team": {"location": "Oregon", "conferenceId": 5}},
    ]}]}]}
    _, out = _run(rows, slate)
    line = next(l for l in out.splitlines() if l.strip().startswith("5 "))
    assert "matches" in line, line


def test_a_row_no_game_touched_is_not_reported_as_wrong():
    """Most of the table is absent from any single slate. Calling that a
    miss would bury the real ones — the failure mode --audit cfb already
    had with its 92 phantom misses."""
    _, out = _run()
    line = next(l for l in out.splitlines() if l.strip().startswith("15 "))
    assert "not on this slate" in line, line
    assert "RENAMED" not in line and "NEW" not in line


def test_the_match_is_loose_enough_to_survive_two_spellings():
    """CFBD says "Texas A&M", ESPN says "Texas A&M Aggies" or "Texas A M".
    An exact-string join would report the whole table unverifiable."""
    rows = [{"school": "Texas A&M", "conference": "SEC"}]
    slate = {"events": [{"competitions": [{"competitors": [
        {"team": {"location": "Texas A M", "conferenceId": 8}},
    ]}]}]}
    _, out = _run(rows, slate)
    assert "1 joined to a CFBD conference, 0 not" in out, out


# --- it is a probe -----------------------------------------------------------
def test_it_changes_nothing():
    """A table this feeds into pricing does not get rewritten by a
    diagnostic on the strength of one slate."""
    before = dict(cfbdata.CONFERENCE_IDS)
    _run()
    assert cfbdata.CONFERENCE_IDS == before


def test_a_missing_key_says_so_and_stops():
    """CFBD is key-gated. Without it there is nothing to join to, and the
    honest output is "unverified", not a table that looks confirmed."""
    real = cfbd._get

    def boom(*a, **k):
        raise cfbd.CFBDUnavailable("No CollegeFootballData key.")

    cfbd._get = boom
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = assets.probe_conference_table("2025-11-01")
    finally:
        cfbd._get = real
    assert code == 1
    assert "stays unverified" in buf.getvalue()


def test_the_team_endpoints_are_asked_before_the_conference_one():
    """MEASURED ON ETHAN'S KEY: /conferences answers 106 rows, and they are
    conferences — id, name, abbreviation, classification — not schools. It
    was first in the list, so the probe opened by dumping a payload that was
    never going to carry a school/conference pair."""
    import inspect
    src = inspect.getsource(assets.probe_conference_table)
    i, j = src.index('"/teams/fbs"'), src.index('"/conferences"')
    assert i < j, "the conference endpoint is asked before the team ones"


def test_conference_rows_are_named_as_such_rather_than_dumped():
    """A different question answered correctly is not a broken response, and
    a shape dump for one reads as a fault."""
    rows = [{"id": 8, "name": "SEC", "short_name": "SEC",
             "classification": "fbs"}]
    _, out = _run(rows)
    assert "CONFERENCE rows, not schools" in out, out


def test_a_shape_that_carries_no_conference_is_dumped_not_guessed_at():
    """THE LESSON FROM THE GROUPS FEED, applied before it costs anything.
    Four rounds went by there because the diagnostic reported "parsed
    nothing" without showing what came back."""
    _, out = _run([{"school": "Alabama", "mascot": "Tide"}])
    assert "no school/conference pair" in out
    assert "dict(" in out, "the shape was not dumped"


def test_it_reads_the_cache_past_rather_than_a_stale_answer():
    """A cached CFBD response is exactly the thing that would make a rotted
    table look confirmed."""
    import inspect
    src = inspect.getsource(assets.probe_conference_table)
    assert "ttl=0" in src


def test_the_probe_is_reachable_from_the_command_line():
    import inspect
    src = inspect.getsource(assets.main)
    assert '"--conf-table"' in src
    assert "probe_conference_table(" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
