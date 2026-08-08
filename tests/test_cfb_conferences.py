"""The CFB conference layer, after the groups feed went quiet.

Ethan's `--audit cfb` run, 2026-08-08, reported the conferences feed silent
while the teams feed on the same host answered fine. That matters more than
an audit filter: `parse_scoreboard` resolves each team's conference through
this map, `attention_tier` reads the conference to decide how hard the
market is looking at a game, and with the live feed gone the whole sport
falls back to a twelve-row table that `cfbdata`'s own header says exists to
be overridden — "conferences in this sport move around constantly."

TWO FAILURES LOOKED IDENTICAL FROM OUTSIDE, and only one of them is the
host's fault:

  1. the groups endpoint refuses or 404s, or
  2. it answers fine and the payload parses to nothing, because the
     conferences are nested under the FBS group's `children` and the parser
     only ever looked one level down. Read that way, the whole feed yields
     `{"80": "FBS"}` — one useless entry, reported as success.

So the parse now walks the tree, the fetch tries more than one shape, and
`assets.py --conferences` says which of the two actually happened. None of
that could be verified from the container, which cannot reach the host at
all; what it CAN do is make sure the second failure is impossible and the
first is legible.

Run directly: `python3 tests/test_cfb_conferences.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbdata as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: What `groups=80` plausibly answers with: the FBS group, conferences
#: hanging off it. This is the shape that parsed to one useless entry.
NESTED = {"groups": [{"id": "80", "name": "FBS", "children": [
    {"groupId": "8", "shortName": "SEC"},
    {"groupId": "5", "name": "Big Ten Conference"},
    {"groupId": "151", "name": "FCS"},
]}]}


# --- the parse ---------------------------------------------------------------
def test_conferences_nested_under_the_parent_group_are_found():
    """THE SILENT FAILURE. One level deep this payload yields {"80": "FBS"}
    and reports success, so every game on the board resolves to no
    conference and attention_tier reads them all as standard."""
    got = C.parse_conferences(NESTED)
    assert got.get("8") == "SEC", got
    assert got.get("5") == "Big Ten", got
    assert got.get("151") == "FCS", got


def test_the_flat_shapes_still_parse():
    """Both shapes this module already handled. A fix for one payload that
    breaks the others is not a fix."""
    assert C.parse_conferences({"groups": [{"groupId": "8", "name": "SEC"}]}) \
        == {"8": "SEC"}
    assert C.parse_conferences({"children": [{"id": "8", "name": "SEC"}]}) \
        == {"8": "SEC"}


def test_a_payload_of_junk_is_empty_not_an_exception():
    """This runs inside the CFB build. A TypeError here takes the board
    down over a feed that changed shape."""
    for junk in ({}, {"groups": None}, {"groups": ["a string", None, 7]},
                 {"groups": [{}]}, {"children": [{"id": "8"}]}):
        assert C.parse_conferences(junk) == {}, junk


def test_the_walk_cannot_run_away_on_a_self_referencing_payload():
    """Depth-bounded rather than trusting a feed to be a tree."""
    node = {"id": "1", "name": "One"}
    node["children"] = [node]
    assert C.parse_conferences({"groups": [node]}) == {"1": "One"}


# --- the merge, which is what the board actually reads -----------------------
def test_the_built_in_table_is_the_floor_and_the_live_feed_the_improvement():
    assert C.conference_ids({}).get("8") == "SEC"
    assert C.conference_ids({"8": "live"}).get("8") == "live"
    assert C.conference_ids({"999": "New"}).get("999") == "New"


def test_the_scoreboard_resolves_through_the_same_merge():
    """`parse_scoreboard` and `--audit cfb` disagreeing about this is the
    bug that put 756 schools back in the audit."""
    import inspect
    src = inspect.getsource(C.parse_scoreboard)
    assert "conference_ids(" in src
    assert "{**CONFERENCE_IDS" not in src, "the merge was copied back inline"


# --- the fetch ladder --------------------------------------------------------
def test_more_than_one_shape_is_tried():
    """The single shape this sent stopped producing conferences. Sending
    only that one again is not a diagnosis."""
    assert len(C.GROUP_CANDIDATES) >= 2
    labels = [lbl for lbl, _, _ in C.GROUP_CANDIDATES]
    assert len(set(labels)) == len(labels), "candidates share a label"


def test_each_candidate_caches_under_its_own_name():
    """Two shapes sharing a cache file means the first answer is served for
    the second URL, and the ladder tests one thing three times."""
    caches = [c for _, _, c in C.GROUP_CANDIDATES]
    assert len(set(caches)) == len(caches), caches


def test_the_shape_that_ships_first_is_the_one_that_used_to_work():
    """Not a rewrite. The historical URL stays the first ask, so if it
    starts answering again nothing extra is requested."""
    assert C.GROUP_CANDIDATES[0][1].endswith(f"?groups={C.FBS_GROUP}")


def test_a_lone_parent_group_is_not_accepted_as_the_answer():
    """{"80": "FBS"} is one entry and it is not a conference list. Taking it
    would stop the ladder on the exact payload that caused this."""
    calls: list = []

    def fake(url, cache, ttl=0, user_agent=None):
        calls.append(url)
        # First shape: the parent only. Second: the real thing.
        return ({"groups": [{"id": "80", "name": "FBS"}]} if len(calls) == 1
                else NESTED)

    got = _with_fetch(fake, lambda: C.fetch_conferences(ttl=0))
    assert len(calls) == 2, f"stopped early on the parent-only payload: {calls}"
    assert got.get("8") == "SEC", got


def test_the_first_usable_answer_wins_and_nothing_further_is_requested():
    calls: list = []

    def fake(url, cache, ttl=0, user_agent=None):
        calls.append(url)
        return NESTED

    got = _with_fetch(fake, lambda: C.fetch_conferences(ttl=0))
    assert len(calls) == 1, calls
    assert len(got) > 1


def test_an_unreachable_shape_does_not_end_the_ladder():
    """A 404 on the historical URL is the whole reason for the alternatives.
    Raising there would make them unreachable."""
    calls: list = []

    def fake(url, cache, ttl=0, user_agent=None):
        calls.append(url)
        if len(calls) < len(C.GROUP_CANDIDATES):
            raise C.DataUnavailable("404", status=404)
        return NESTED

    got = _with_fetch(fake, lambda: C.fetch_conferences(ttl=0))
    assert len(calls) == len(C.GROUP_CANDIDATES)
    assert got.get("8") == "SEC"


def test_everything_failing_is_an_empty_map_not_a_raise():
    """The CFB build calls this on every run. `conference_ids` supplies the
    floor; this must not be the thing that stops a board rendering."""
    def fake(url, cache, ttl=0, user_agent=None):
        raise C.DataUnavailable("nope", status=503)

    assert _with_fetch(fake, lambda: C.fetch_conferences(ttl=0)) == {}


def test_the_report_names_which_shape_did_what():
    """Without this the diagnostic can only say "something failed", which is
    what we already knew and could not act on."""
    def fake(url, cache, ttl=0, user_agent=None):
        raise C.DataUnavailable("boom", status=404)

    report: list = []
    _with_fetch(fake, lambda: C.fetch_conferences(ttl=0, report=report))
    assert len(report) == len(C.GROUP_CANDIDATES)
    for label, count, note in report:
        assert count == 0
        assert note.startswith("unreachable"), note


def test_the_report_distinguishes_refused_from_parsed_empty():
    """The two need different fixes and looked identical before."""
    def fake(url, cache, ttl=0, user_agent=None):
        return {"groups": []}

    report: list = []
    _with_fetch(fake, lambda: C.fetch_conferences(ttl=0, report=report))
    assert all(not n.startswith("unreachable") for _, _, n in report), report


# --- the diagnostic ----------------------------------------------------------
def test_the_diagnostic_bypasses_the_cache():
    """A stale espn_cfb_groups.json is one of the candidate explanations, so
    reading it would answer the wrong question."""
    import inspect
    import assets
    src = inspect.getsource(assets.probe_conferences)
    assert "ttl=0" in src, "the diagnostic reads whatever is on disk"


def test_the_diagnostic_checks_the_built_in_table_for_rot():
    """The live feed exists to stop that table going stale. If it is down we
    are running on the table, and whether IT is still right is the question
    that actually affects pricing."""
    import inspect
    import assets
    src = inspect.getsource(assets.probe_conferences)
    assert "CONFERENCE_IDS" in src
    assert "GONE" in src and "RENAMED" in src


def test_the_diagnostic_is_reachable_from_the_command_line():
    import inspect
    import assets
    src = inspect.getsource(assets.main)
    assert '"--conferences"' in src
    assert "probe_conferences()" in src


def _with_fetch(fake, run):
    """Swap cfbdata's fetch_json for the duration of one call."""
    real = C.fetch_json
    C.fetch_json = fake
    try:
        return run()
    finally:
        C.fetch_json = real


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
