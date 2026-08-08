"""MLB player faces, and the CFB logos that came with the same pass.

Ethan, 2026-08-08: "ok do the espn shit."

MLB DID NOT NEED THE ESPN JOIN I SAID IT DID. Reporting the NBA/WNBA faces
I wrote that MLB was blocked behind a name→ESPN-athlete-id join, because we
ingest statsapi and statsapi gives MLB's own ids. That was true and
irrelevant: `MLBProp` has carried `person_id` since the splits work, MLB
serves its own headshots keyed by exactly that id, and the `headshot` field
the pipeline already emits was simply never filled. No join, no new feed.

BUT THIS URL IS CONSTRUCTED, WHICH THE HOOPS ONE WAS NOT. ESPN's box score
hands us a href, so the NBA and WNBA faces are taken and cannot be wrong
about their own shape. The Stats API publishes no photo URL, so there is
nothing to take and the path is built from knowledge — the same category as
`limit=400` and the User-Agent 403. It is therefore built to cost nothing
when wrong: `assets.py --probe` checks both URLs the page will request, and
on the board a bad one falls to the untransformed version and then to the
team-coloured chip, which is what MLB props draw today.

CFB LOGOS, SAME IDEA FROM THE OTHER END. ESPN keys 134 schools numerically
and I had this filed as "needs a team-ID map". It does not: `parse_teams`
already keeps ESPN's own `id` off ESPN's own teams feed, and the build
already ships that map in the slate payload. The board just had to prefer
it over the abbreviation. A hand-written 134-row map would have rotted the
first time a school rebranded.

Run directly: `python3 tests/test_faces_mlb.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _js():
    return _read("web", "js", "visuals.js")


# --- the MLB URL -------------------------------------------------------------
def test_the_face_is_addressed_by_the_id_we_already_carry():
    from engine.mlb.sources.mlbstats import headshot_url
    url = headshot_url(592450)
    assert "592450" in url, "the person id is not in the URL"
    assert url.startswith("https://"), url


def test_a_player_without_an_id_gets_no_url_rather_than_a_broken_one():
    """`_add_prop` bails on a falsy person_id, but a prop built any other
    way must not end up requesting /people/0/ or /people/None/ — that is a
    guaranteed 404 on every card that has it."""
    from engine.mlb.sources.mlbstats import headshot_url
    for bad in (0, -1, None, "", "abc", [], {}):
        assert headshot_url(bad) == "", repr(bad)


def test_the_id_is_coerced_so_a_string_id_still_resolves():
    """Ids arrive as strings from JSON and as ints from the dataclass."""
    from engine.mlb.sources.mlbstats import headshot_url
    assert headshot_url("592450") == headshot_url(592450)


def test_the_url_survives_the_resizer_that_will_rewrite_it():
    """THE BUG THIS PREVENTS, and the reason the URL carries a transform
    segment it does not appear to need.

    `facePreview` resizes a Cloudinary URL by replacing the FIRST path
    segment after /image/upload/. Handed a URL whose first segment is `v1`,
    it would eat `v1` and request a path that does not exist — 404 on every
    MLB face, and the fallback would hide it as "MLB just has no photos".

    So this replays the JavaScript's rewrite in Python and checks the
    identifying part of the path is still there afterwards."""
    from engine.mlb.sources.mlbstats import headshot_url
    url = headshot_url(592450)
    marker = "/image/upload/"
    assert marker in url, "not a Cloudinary path; facePreview will pass it through"
    head, tail = url.split(marker)
    rest = tail[tail.index("/") + 1:] if "/" in tail else tail
    rewritten = f"{head}{marker}f_auto,q_auto,w_112,h_112,c_fill,g_face/{rest}"
    assert "/v1/people/592450/" in rewritten, rewritten
    assert rewritten.endswith("/headshot/67/current"), rewritten


def test_the_untransformed_url_is_itself_a_real_request():
    """It is what the <img> swaps to on the first error, so it has to be a
    URL worth swapping to — a bare transform-less path would 404 twice and
    make the two-step fallback one step."""
    from engine.mlb.sources.mlbstats import headshot_url
    seg = headshot_url(592450).split("/image/upload/")[1].split("/")[0]
    assert seg and seg != "v1", "no transform segment to strip"
    assert "w_" in seg, f"the fallback URL asks for no size: {seg!r}"


# --- the wiring --------------------------------------------------------------
def test_every_prop_the_build_makes_gets_the_face():
    """One construction site for MLB props, so one place to fill it."""
    import inspect
    from engine.mlb.sources import statslogs
    src = inspect.getsource(statslogs._add_prop)
    assert "headshot=headshot_url(person_id)" in src


def test_the_pipeline_still_ships_the_field():
    """It has always emitted `prop.headshot`; that is why filling it is the
    whole change. If this ever stops, the faces vanish silently."""
    import inspect
    from engine.mlb import pipeline
    assert '"headshot": prop.headshot' in inspect.getsource(pipeline)


def test_the_probe_checks_the_two_urls_the_page_actually_requests():
    """A constructed URL that nothing verifies is how this project got
    `limit=400`. Both the resized request and its fallback are listed."""
    src = _read("assets.py")
    assert src.count("SHIPPED") >= 2, "the shipped URLs are not in the probe"
    assert "f_auto,q_auto,w_112,h_112,c_fill,g_face" in src
    assert "w_180,q_auto" in src


def test_the_probe_and_the_engine_agree_on_the_path():
    """Two copies of a URL drift, and the drift here is silent: the probe
    would keep reporting OK for a path the board no longer requests."""
    from engine.mlb.sources.mlbstats import headshot_url
    tail = headshot_url(592450).split("mlbstatic.com")[1]
    probe = _read("assets.py").replace('"\n         "', "").replace('"\n         "', "")
    flat = re.sub(r'"\s*\n\s*"', "", probe)
    assert tail in flat, f"the probe no longer tests {tail}"


# --- CFB logos ---------------------------------------------------------------
def test_the_college_id_comes_off_espns_own_feed():
    from engine.sources import cfbdata
    teams = cfbdata.parse_teams({"sports": [{"leagues": [{"teams": [
        {"team": {"id": 333, "abbreviation": "ALA", "displayName": "Alabama",
                  "color": "9E1B32", "alternateColor": "828A8F"}}]}]}]})
    assert teams["ALA"]["id"] == "333", teams


def test_the_board_prefers_the_id_over_the_abbreviation():
    """"ALA" against ESPN's ncaa key is a 404; 333 is Alabama. Our other
    four sports have no id in their colour dicts, so they are untouched."""
    js = _js()
    i = js.index("function teamMark(")
    body = js[i:i + 900]
    assert "logoUrl(t.id || abbr" in body, (
        "college draws by abbreviation again, which resolves for no school")


def test_the_college_team_map_reaches_the_page():
    """The ids are useless if the payload drops them — 134 schools ship in
    the slate rather than in a checked-in file precisely so they cannot go
    stale, and that only works if the build keeps writing them."""
    build = _read("cfb_build.py")
    assert 'out["teams"] = teams' in build
    app = _read("web", "js", "app.js")
    i = app.index("function teamsForSport(")
    assert "state.data && state.data.teams" in app[i:i + 400]


def test_the_conference_marker_is_read_from_either_place_espn_puts_it():
    """`--audit cfb` needs SOMETHING to tell a Big Ten school from a JUCO,
    and this is the only marker the payload offers. ESPN files it as a flat
    `conferenceId` on some rows and nested under `groups` on others."""
    from engine.sources import cfbdata
    p = {"sports": [{"leagues": [{"teams": [
        {"team": {"id": 333, "abbreviation": "ALA", "conferenceId": 8}},
        {"team": {"id": 2, "abbreviation": "AUB", "groups": {"id": "8"}}},
        {"team": {"id": 2048, "abbreviation": "AVILA"}},
    ]}]}]}
    t = cfbdata.parse_teams(p)
    assert t["ALA"]["conf"] == "8"
    assert t["AUB"]["conf"] == "8"
    assert t["AVILA"]["conf"] == "", "absent must read as unknown, not as 0"


def test_the_college_audit_drops_the_schools_that_cannot_reach_a_board():
    """MEASURED, 2026-08-08: the first run reported 92 misses out of 756 —
    Avila, Culver-Stockton, Haskell, Pikeville. `fetch_teams` already asks
    for groups=80 and the feed ignores it, returning ESPN's whole college
    database. 92 misses nobody can act on is how a real one gets missed."""
    import assets
    src = _read("assets.py")
    i = src.index("def _cfb_ids(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "fetch_conferences" in body, "nothing separates FBS from NAIA"
    assert "conf in confs" in body


def test_an_unreachable_groups_feed_is_not_read_as_no_conferences():
    """THE BUG THE SECOND AUDIT RUN EXPOSED. `fetch_conferences` answers {}
    when the groups endpoint won't respond — and on Ethan's machine,
    2026-08-08, it did not respond, while the teams feed was fine. The audit
    used that {} alone, decided no school was in any conference, and fell
    straight back to checking all 756 rows.

    `parse_scoreboard` never had this problem: it layered the built-in table
    underneath. The merge is now one function so the two cannot disagree."""
    from engine.sources import cfbdata
    # .get, not [], so a missing floor reports the claim rather than a
    # KeyError that says nothing about what went wrong.
    assert cfbdata.conference_ids({}).get("8") == "SEC", (
        "an empty live feed erases the built-in ids")
    assert cfbdata.conference_ids(None), "no floor at all"
    assert cfbdata.conference_ids({"8": "live name"})["8"] == "live name", (
        "the live feed must still win where it answers")
    src = _read("assets.py")
    i = src.index("def _cfb_ids(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "conference_ids(" in body, (
        "the audit is back to trusting the live feed on its own")


def test_the_scoreboard_and_the_audit_resolve_conferences_the_same_way():
    """Two merges that drift is exactly how one caller ends up correct and
    the other silently wrong, which is what happened here."""
    import inspect
    from engine.sources import cfbdata
    src = inspect.getsource(cfbdata.parse_scoreboard)
    assert "conference_ids(" in src
    assert "{**CONFERENCE_IDS" not in src, "the merge was copied back inline"


def test_an_unmarked_feed_audits_everything_and_says_so():
    """The filter is only as good as the marker. If ESPN stops sending it,
    the audit must go back to checking all of them and announce that —
    silently reporting a clean sheet it never earned is worse than noise."""
    src = _read("assets.py")
    i = src.index("def _cfb_ids(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "auditing all" in body
    # Anchored on the statement, not on where the slice ends — slicing to
    # the next `def` swept in the comment block that precedes it, so an
    # `endswith` here failed on a function that was perfectly correct.
    assert "return [(ab, tid) for ab, tid, _ in every]" in body, (
        "the no-marker path no longer falls back to the full list")


def test_the_audit_covers_college_from_the_feed_not_from_a_file():
    """There is no teams_cfb.js and there should not be one. Before this the
    audit printed "no teams file, skipped" — a whole sport reported as fine
    because nothing had looked at it."""
    import assets
    assert hasattr(assets, "_cfb_ids")
    src = _read("assets.py")
    i = src.index("def audit(")
    body = src[i:]
    assert '_cfb_ids()' in body, "the audit still cannot see college"


# --- the regression this pass was really about -------------------------------
def test_a_team_dictionary_in_the_third_argument_does_not_explode():
    """SHIPPED BROKEN AND CAUGHT HERE. The logo work overloaded teamMark's
    third parameter — historically the team DICTIONARY, matching `team()` —
    to also mean the sport. `offseasonHTML` passes a real dictionary there,
    so logoUrl reached `(sport || "").toLowerCase()` with an object, threw a
    TypeError, and took the whole NFL coach-change section down with it.

    Verified in node: the dict form threw, the string form did not."""
    js = _js()
    i = js.index("function teamMark(")
    sig = js[i:js.index(")", i) + 1]
    assert "sport" in sig, f"sport is not its own parameter: {sig}"
    body = js[i:i + 900]
    assert 'typeof src === "string"' in body, (
        "nothing distinguishes a team map from a sport name")


def test_no_call_site_passes_a_map_without_saying_which_sport():
    """The other half: with the two meanings separated, a call that passes a
    dictionary and NO sport silently falls back to whatever tab the visitor
    is on. offseasonHTML is always NFL however you got there — that is why
    it passes its own map in the first place."""
    app = _read("web", "js", "app.js")
    for m in re.finditer(r"teamMark\(", app):
        args, depth, k = [], 0, m.end()
        cur = ""
        while k < len(app):
            c = app[k]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            if c == "," and depth == 0:
                args.append(cur.strip()); cur = ""
            else:
                cur += c
            k += 1
        args.append(cur.strip())
        if len(args) >= 3 and args[2] not in ("null", ""):
            third = args[2]
            looks_like_a_sport = third.startswith('"') or third.startswith("'")
            assert looks_like_a_sport or len(args) >= 4, (
                f"teamMark({', '.join(args)}) passes a map with no sport")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
