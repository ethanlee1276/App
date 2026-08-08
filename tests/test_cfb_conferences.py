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


#: WHAT THE ENDPOINT ACTUALLY RETURNS. Measured 2026-08-08 from Ethan's
#: machine, after two wrong guesses about it. The decisive detail is that
#: the GROUP NODES CARRY NO ID — only teams do — so {group_id: name}, the
#: map this module has asked this endpoint for since it was written, was
#: never buildable from it.
REAL = {"status": "ok", "groups": [
    {"name": "NCAA Division I-A", "abbreviation": "FBS", "children": [
        {"name": "Southeastern Conference", "abbreviation": "SEC", "teams": [
            {"id": "333", "abbreviation": "ALA"},
            {"id": "2", "abbreviation": "AUB"}]},
        {"name": "Big Ten Conference", "abbreviation": "B1G", "teams": [
            {"id": "194", "abbreviation": "OSU"}]}]},
    {"name": "NCAA Division I-AA", "abbreviation": "FCS", "children": [
        {"name": "Big Sky Conference", "teams": [
            {"id": "204", "abbreviation": "MONT"}]}]}]}


# --- the map the feed can actually produce ----------------------------------
def test_the_feed_is_read_as_team_to_conference():
    got = C.parse_group_teams(REAL)
    assert got == {"333": "SEC", "2": "SEC", "194": "Big Ten",
                   "204": "Big Sky Conference"}, got


def test_the_group_nodes_have_no_id_which_is_the_whole_finding():
    """Kept as an assertion rather than a comment, because the moment ESPN
    adds ids here the old `{group_id: name}` route becomes viable again and
    somebody should be told rather than left maintaining two answers."""
    for grp in REAL["groups"]:
        assert "id" not in grp and "groupId" not in grp
        for child in grp["children"]:
            assert "id" not in child and "groupId" not in child
    assert C.parse_conferences(REAL) == {}, (
        "the id→name map is suddenly buildable; revisit fetch_conferences")


def test_a_division_does_not_become_the_conference():
    """Some conferences split into divisions that also carry teams. Naming a
    school's conference "East Division" would be worse than useless to
    attention_tier, which reads it to judge how hard the market is looking."""
    div = {"groups": [{"name": "FBS", "children": [
        {"name": "Conference USA", "children": [
            {"name": "East Division", "teams": [{"id": "9"}]},
            {"name": "West Division", "teams": [{"id": "10"}]}]}]}]}
    assert C.parse_group_teams(div) == {"9": "Conference USA",
                                        "10": "Conference USA"}


def test_a_school_hanging_off_the_top_level_keeps_that_name():
    """Independents have no conference node between them and the division."""
    indep = {"groups": [{"name": "FBS Independents",
                         "teams": [{"id": "87"}]}]}
    assert C.parse_group_teams(indep) == {"87": "FBS Independents"}


def test_the_division_of_college_football_is_not_a_conference():
    """"NCAA Division I-A" is not what anyone means by a school's
    conference, and it must not leak out as one."""
    assert "NCAA Division I-A" not in C.parse_group_teams(REAL).values()


def test_the_team_map_survives_the_envelope_too():
    env = {"sports": [{"leagues": [REAL]}]}
    assert C.parse_group_teams(env).get("333") == "SEC"


def test_a_malformed_groups_payload_is_empty_not_an_exception():
    for junk in ({}, {"groups": None}, {"groups": ["s", None, 7]},
                 {"groups": [{"teams": [{"id": "1"}]}]},   # no name anywhere
                 {"groups": [{"name": "X", "teams": ["not a dict"]}]}):
        assert C.parse_group_teams(junk) == {}, junk


# --- what reads it -----------------------------------------------------------
def test_the_live_map_wins_over_the_checked_in_table():
    """The conferenceId route resolves through twelve rows checked into the
    source file. Schools change conference every year; the file does not."""
    sb = {"events": [{"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "333", "abbreviation": "ALA",
                                      "conferenceId": 8}},
        {"homeAway": "away", "team": {"id": "194", "abbreviation": "OSU",
                                      "conferenceId": 8}},
    ]}]}]}
    games = C.parse_scoreboard(sb, None, {"194": "Big Ten"})
    assert games[0]["away_conference"] == "Big Ten", games[0]
    # The one with no live entry still resolves the old way.
    assert games[0]["home_conference"] == "SEC", games[0]


def test_without_the_live_map_nothing_changes():
    """It is an improvement layered on, not a replacement. A CFB build that
    cannot reach the groups feed must behave exactly as it did before."""
    sb = {"events": [{"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "333", "abbreviation": "ALA",
                                      "conferenceId": 8}},
        {"homeAway": "away", "team": {"id": "194", "abbreviation": "OSU",
                                      "conferenceId": 5}},
    ]}]}]}
    # Comparing the two calls alone proves nothing — a change that broke
    # both identically would still pass. The values are the assertion.
    for got in (C.parse_scoreboard(sb), C.parse_scoreboard(sb, None, {})):
        assert got[0]["home_conference"] == "SEC", got
        assert got[0]["away_conference"] == "Big Ten", got


def test_the_range_loader_fetches_the_map_once_not_once_a_day():
    """A season backfill is ~180 days. The map is cached for a week, so a
    per-day lookup asks the cache 180 times for an answer that cannot have
    changed."""
    import inspect
    src = inspect.getsource(C.load_range)
    i = src.index("while day <= d1:")
    assert "fetch_group_teams" not in src[i:], "the fetch moved into the loop"
    assert "fetch_group_teams" in src[:i]


def test_the_build_passes_the_live_map_through():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("cfbdata.parse_scoreboard(")
    assert "team_conf" in src[i - 300:i + 200], (
        "the build resolves conferences from the checked-in table only")


def test_the_audit_filters_on_the_list_not_on_an_inferred_field():
    """The previous filter looked for a `conferenceId` on the teams payload.
    Measured runs showed it is not there. This one uses the enumeration the
    groups feed gives directly, which is a list rather than an inference."""
    src = _read_root("assets.py")
    i = src.index("def _cfb_ids(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "fetch_group_teams()" in body
    assert "in_a_conference" in body


def _read_root(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, name), encoding="utf-8") as fh:
        return fh.read()


# --- the parse ---------------------------------------------------------------
def test_conferences_nested_under_the_parent_group_are_found():
    """THE SILENT FAILURE. One level deep this payload yields {"80": "FBS"}
    and reports success, so every game on the board resolves to no
    conference and attention_tier reads them all as standard."""
    got = C.parse_conferences(NESTED)
    assert got.get("8") == "SEC", got
    assert got.get("5") == "Big Ten", got
    assert got.get("151") == "FCS", got


def test_the_api_envelope_is_unwrapped():
    """THE ACTUAL CAUSE, measured 2026-08-08. All three URL shapes REACHED
    the host and returned valid JSON, and all three parsed to nothing — so
    the feed was never down. This API wraps its collections in
    sports[0].leagues[0].<thing>; `parse_teams` has unwrapped exactly that
    since it was written and this function never did, so it was reading the
    top level of an envelope that has nothing at the top level."""
    env = {"sports": [{"leagues": [{"groups": [
        {"groupId": "8", "shortName": "SEC"},
        {"groupId": "5", "name": "Big Ten Conference"},
    ]}]}]}
    got = C.parse_conferences(env)
    assert got.get("8") == "SEC", got
    assert got.get("5") == "Big Ten", got


def test_the_envelope_and_the_nesting_compose():
    """Both candidate causes at once, which is the shape nobody has ruled
    out: conferences under the FBS group, inside the envelope."""
    env = {"sports": [{"leagues": [{"groups": [
        {"id": "80", "name": "FBS",
         "children": [{"groupId": "8", "shortName": "SEC"}]}]}]}]}
    assert C.parse_conferences(env).get("8") == "SEC"


def test_a_broken_envelope_does_not_raise():
    """A feed half-way through a shape change must not take the build down."""
    for junk in ({"sports": []}, {"sports": [{"leagues": []}]},
                 {"sports": "nope"}, {"sports": [{"leagues": ["x"]}]},
                 {"sports": [{}]}):
        assert C.parse_conferences(junk) == {}, junk


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


def test_the_diagnostic_shows_the_shape_when_a_feed_answers_with_nothing():
    """The first diagnostic said "parsed nothing" and stopped. That named the
    symptom and hid the cause — the payload was right there and nobody could
    see where in it the conferences were. It prints keys and lengths, never
    contents: a feed's contents do not belong in a chat log."""
    import assets
    p = {"sports": [{"id": "20", "name": "Football", "leagues": [
        {"id": "23", "groups": [{"groupId": "8", "shortName": "SEC"}]}]}]}
    lines = "\n".join(assets._sketch(p))
    assert "sports" in lines and "leagues" in lines and "groups" in lines, lines
    assert "SEC" not in lines, "the sketch is leaking contents, not shape"


def test_the_shape_dump_cannot_run_away_on_a_large_payload():
    """756 schools came back from the teams feed. An unbounded dump of
    something that size is not a diagnostic, it is a wall."""
    import assets
    big = {"items": [{"a": {"b": {"c": [{"d": i} for i in range(500)]}}}
                     for _ in range(500)]}
    assert len(assets._sketch(big)) < 60


def test_the_shape_is_only_dumped_when_it_is_the_useful_answer():
    """A refused host has no payload to describe, and a shape that worked
    needs no explaining. Printing either would bury the one that matters."""
    import inspect
    import assets
    src = inspect.getsource(assets.probe_conferences)
    assert 'note.startswith("unreachable")' in src
    assert "count > 1 or" in src


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
