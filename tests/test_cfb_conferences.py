"""The CFB conference layer, and what its feed does and does not carry.

Ethan's `--audit cfb` run, 2026-08-08, reported the conferences feed silent
while the teams feed on the same host answered fine. That matters more than
an audit filter: `parse_scoreboard` resolves each team's conference through
this map, and `attention_tier` reads the conference to decide how hard the
market is looking at a game.

THREE GUESSES, THEN A MEASUREMENT. I proposed the host was refusing, then
the sports[0].leagues[0] envelope, then conferences nested under the FBS
group. All three are handled below because all three are real shapes for
this API. NONE of them was the cause. A shape dump finally showed it:

  * the group nodes carry NO ID, only teams do, so `{group_id: name}` was
    never buildable from this endpoint; and
  * the children are NCAA DIVISIONS — FBS, FCS, Division II, Division III —
    with no conference node anywhere in the tree, and their team lists
    paginate at 25.

The third guess shipped for one commit and was a pricing bug: it wired
those division labels into `parse_scoreboard`, which would have told
`attention_tier` that Alabama plays in "FBS" and priced the SEC as though
nobody was watching it. That wiring is gone, conference resolution is back
on `conferenceId` alone, and the tests below hold it there.

Nothing here was verifiable from the container, which cannot reach the host.
What it CAN do is stop a page being mistaken for a roster and a division
for a conference.

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
#: machine, after three wrong guesses about it. Two details are decisive and
#: neither was guessable:
#:
#:   * the GROUP NODES CARRY NO ID — only teams do — so {group_id: name},
#:     the map this module has asked this endpoint for since it was written,
#:     was never buildable from it; and
#:   * the four children are NCAA DIVISIONS, not conferences. There is no
#:     conference node in this tree at any depth.
#:
#: The second one nearly shipped as a pricing bug: a version of this file
#: asserted these labels were conferences, and parse_scoreboard would have
#: told attention_tier that Alabama plays in "FBS".
REAL = {"status": "ok", "groups": [
    {"name": "NCAA Division I", "abbreviation": "D1", "children": [
        {"name": "FBS", "abbreviation": "FBS", "teams": [
            {"id": "333", "abbreviation": "ALA"},
            {"id": "2", "abbreviation": "AUB"}]},
        {"name": "FCS", "abbreviation": "FCS", "teams": [
            {"id": "204", "abbreviation": "MONT"}]}]},
    {"name": "NCAA Lower", "children": [
        {"name": "NCAA Division II", "teams": [{"id": "2048"}]},
        {"name": "NCAA Division III", "teams": [{"id": "2049"}]}]}]}


# --- what the feed carries, named correctly ---------------------------------
def test_the_feed_is_read_as_team_to_division():
    got = C.parse_group_divisions(REAL)
    assert got == {"333": "FBS", "2": "FBS", "204": "FCS",
                   "2048": "NCAA Division II",
                   "2049": "NCAA Division III"}, got


def test_no_conference_is_claimed_from_this_feed():
    """THE MISTAKE THIS PREVENTS, and it was shipped for one commit. These
    labels are divisions. Handing them to parse_scoreboard would have told
    attention_tier that Alabama's conference is "FBS", dropping every
    power-five school out of the power set and pricing the SEC as though
    nobody was watching it."""
    import inspect
    src = inspect.getsource(C.parse_scoreboard)
    assert "parse_group_divisions" not in src
    assert "team_conf" not in src and "by_team" not in src, (
        "the division map is wired back into conference naming")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as fh:
        assert "group_divisions" not in fh.read(), (
            "the build passes divisions into the scoreboard parse")


def test_the_group_nodes_have_no_id_which_is_why_the_old_map_was_empty():
    """Kept as an assertion, not a comment: the moment ESPN adds ids here
    the {group_id: name} route becomes viable and somebody should be told
    rather than left maintaining two answers."""
    for grp in REAL["groups"]:
        assert "id" not in grp and "groupId" not in grp
        for child in grp["children"]:
            assert "id" not in child and "groupId" not in child
    assert C.parse_conferences(REAL) == {}, (
        "the id→name map is suddenly buildable; revisit fetch_conferences")


def test_a_page_is_not_a_roster():
    """Measured: four divisions, exactly 25 schools each, 100 total. That is
    a page size. A filter built from it would drop real FBS schools as
    confidently as it drops Avila, which is worse than no filter at all."""
    assert C.GROUP_PAGE == 25
    paged = {"groups": [{"name": "D1", "children": [
        {"name": "FBS", "teams": [{"id": str(i)} for i in range(25)]}]}]}
    assert len(C.parse_group_divisions(paged)) == C.GROUP_PAGE
    # Behaviour, not a grep. The first version of this checked that the
    # string "GROUP_PAGE" appeared in the function — which it still does, in
    # a print, so replacing the completeness test with `bool(division)` left
    # the assertion passing while the guard was gone.
    import assets
    teams = {f"T{i}": {"id": str(i)} for i in range(400)}
    page = {str(i): "FBS" for i in range(C.GROUP_PAGE)}
    got = _with_audit_feeds(teams, page, assets._cfb_ids)
    assert len(got) == 400, (
        f"a {C.GROUP_PAGE}-row page filtered the audit down to {len(got)}")
    whole = {str(i): ("FBS" if i < 300 else "NCAA Division III")
             for i in range(400)}
    got = _with_audit_feeds(teams, whole, assets._cfb_ids)
    assert len(got) == 300, f"a complete list did not filter: {len(got)}"


def _with_audit_feeds(teams, division, run):
    """Run the audit's team lookup against stubbed feeds."""
    real_fetch, real_parse = C.fetch_teams, C.parse_teams
    real_div = C.fetch_group_divisions
    C.fetch_teams = lambda *a, **k: {}
    C.parse_teams = lambda payload: teams
    C.fetch_group_divisions = lambda *a, **k: division
    try:
        return run()
    finally:
        C.fetch_teams, C.parse_teams = real_fetch, real_parse
        C.fetch_group_divisions = real_div


def test_a_deeper_nesting_keeps_the_division_not_the_leaf():
    """If ESPN ever puts conferences under the divisions, the division is
    still the honest label for what this function returns — and a leaf name
    like "East Division" must never become one."""
    deep = {"groups": [{"name": "D1", "children": [
        {"name": "FBS", "children": [
            {"name": "Southeastern Conference", "teams": [{"id": "333"}]}]}]}]}
    assert C.parse_group_divisions(deep) == {"333": "FBS"}


def test_a_school_hanging_off_the_top_level_keeps_that_name():
    indep = {"groups": [{"name": "FBS Independents", "teams": [{"id": "87"}]}]}
    assert C.parse_group_divisions(indep) == {"87": "FBS Independents"}


def test_the_division_map_survives_the_envelope_too():
    assert C.parse_group_divisions({"sports": [{"leagues": [REAL]}]}) \
        .get("333") == "FBS"


def test_a_malformed_groups_payload_is_empty_not_an_exception():
    for junk in ({}, {"groups": None}, {"groups": ["s", None, 7]},
                 {"groups": [{"teams": [{"id": "1"}]}]},
                 {"groups": [{"name": "X", "teams": ["not a dict"]}]}):
        assert C.parse_group_divisions(junk) == {}, junk


def test_the_truncation_is_reported_rather_than_passed_off_as_an_answer():
    """`--conferences` said OK to a 100-row page. Reporting a page as a
    complete answer is how the audit would have been quietly re-broken."""
    def fake(url, cache, ttl=0, user_agent=None):
        return {"groups": [{"name": "D1", "children": [
            {"name": "FBS", "teams": [{"id": str(i)} for i in range(25)]}]}]}

    report: list = []
    _with_fetch(fake, lambda: C.fetch_group_divisions(ttl=0, report=report))
    assert any("TRUNCATED" in n for _, _, n in report), report


def test_a_limit_shape_is_tried_since_the_lists_are_paginated():
    """fetch_teams sends limit=900 against this same API and gets 756 rows,
    which is reason to think the parameter is honoured here even though
    `groups` demonstrably is not."""
    assert any("limit" in lbl for lbl, _, _ in C.GROUP_CANDIDATES)


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
