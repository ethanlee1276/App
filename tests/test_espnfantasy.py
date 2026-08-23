"""An ESPN league, read without a credential — or refused for a reason.

Ethan, 2026-08-15, asked to sync more than Sleeper and named ESPN.

THE BOUNDARY IS THE FEATURE. A PUBLIC ESPN league reads with no login at
all. A PRIVATE one needs `espn_s2` and `SWID`, which are session cookies
lifted from a logged-in browser: full account access, months of life, no
way to scope them to one league. This project does not take credentials,
so the private case gets a message naming the SETTING to change instead
of a prompt for cookies. The test that matters most in this file is the
one checking that message exists and that no cookie ever gets read.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH — measured, not
assumed: a probe to both ESPN hosts returned nothing through the
environment's proxy. So the parser is tested against the payload SHAPE,
and it is built to fail loudly rather than quietly:

  * an unrecognised shape RAISES; an empty league and an unparsed one
    look identical on a page and mean opposite things;
  * an unknown scoring `statId` is REPORTED, never dropped. This repo has
    already shipped one bug of exactly that kind — `pass_att` was read
    from a market that did not exist, and everything downstream read zero
    without a single error. A scoring rule silently ignored is a lineup
    silently wrong, so unknown ids come back in `unmapped`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.sources import espnfantasy as ef                  # noqa: E402
from engine.sources.fetch import DataUnavailable              # noqa: E402

#: ESPN's documented shape, trimmed to what is read.
PAYLOAD = {
    "settings": {
        "name": "The League",
        "scoringSettings": {"scoringItems": [
            {"statId": 3, "points": 0.04},      # passing yards
            {"statId": 4, "points": 6.0},       # passing TD — six-pointer
            {"statId": 20, "points": -2.0},     # interception
            {"statId": 24, "points": 0.1},      # rushing yards
            {"statId": 42, "points": 0.1},      # receiving yards
            {"statId": 53, "points": 0.5},      # receptions — half PPR
            {"statId": 999, "points": 2.0},     # something we do not know
            {"statId": 998, "points": 0.0},     # zero: not a real rule
        ]},
        "rosterSettings": {"lineupSlotCounts": {
            "0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "20": 6, "21": 1,
            "88": 3,                            # an IDP slot we do not model
        }},
    },
    "teams": [
        {"id": 1, "name": "Mine", "owners": ["{ABC}"], "roster": {"entries": [
            {"playerPoolEntry": {"player": {"fullName": "Jalen Hurts",
                                            "defaultPositionId": 1}}},
            {"playerPoolEntry": {"player": {"fullName": "Bijan Robinson",
                                            "defaultPositionId": 2}}},
            {"playerPoolEntry": {"player": {"fullName": "No Position",
                                            "defaultPositionId": 77}}},
        ]}},
        {"id": 2, "location": "Other", "nickname": "Guys", "owners": ["{XYZ}"],
         "roster": {"entries": [
             {"playerPoolEntry": {"player": {"fullName": "Puka Nacua",
                                             "defaultPositionId": 3}}},
         ]}},
    ],
}


# --- the boundary this adapter exists to hold -------------------------------
def test_no_credential_is_ever_read():
    """The standing rule, checked in the file most tempted to break it.
    ESPN's private-league path is one cookie away and this module must
    not take that step."""
    src = open(os.path.join(ROOT, "engine", "sources", "espnfantasy.py"),
               encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith(("#", "*")))
    # The words may appear in the EXPLANATION; they must not appear as a
    # header, a cookie jar or a request argument.
    for bad in ("Cookie:", "cookies=", "set_cookie", "CookieJar",
                'headers={"Cookie'):
        assert bad not in code, f"espnfantasy reached for {bad!r}"


def test_a_private_league_names_the_setting_rather_than_asking_for_cookies():
    """"Unauthorized" on its own sends the reader looking for a password
    field this app does not have.

    Tested by triggering the real path rather than grepping the source —
    the first cut checked for a phrase that was split across two lines and
    failed for a formatting reason while the behaviour was correct."""
    real = ef.fetch_text

    def refuse(*a, **k):
        raise DataUnavailable("HTTP Error 401: Unauthorized")
    ef.fetch_text = refuse
    try:
        ef.fetch_league(2025, "12345")
    except DataUnavailable as exc:
        msg = str(exc)
    else:
        raise AssertionError("a private league did not raise")
    finally:
        ef.fetch_text = real
    assert "PRIVATE" in msg
    assert "viewable by the public" in msg
    assert "does not take session cookies" in msg


# --- scoring ----------------------------------------------------------------
def test_the_scoring_map_reaches_the_shape_the_optimiser_reads():
    got = ef.parse_scoring(PAYLOAD)["scoring"]
    assert got["pass_yd"] == 0.04
    assert got["pass_td"] == 6.0            # the six-pointer, not the default
    assert got["rec"] == 0.5                # half PPR
    assert got["rec_yd"] == 0.1 and got["rush_yd"] == 0.1


def test_an_unknown_stat_id_is_reported_rather_than_dropped():
    """THE ONE THIS REPO HAS ALREADY PAID FOR. `pass_att` was read from a
    market that did not exist and everything downstream read zero without
    an error. A scoring rule silently ignored is a lineup silently
    wrong."""
    got = ef.parse_scoring(PAYLOAD)
    assert {"statId": 999, "points": 2.0} in got["unmapped"]


def test_a_zero_valued_rule_is_not_reported_as_a_surprise():
    """ESPN lists every possible rule, most of them at zero. Reporting
    those as unmapped would bury the one that matters in ninety that do
    not."""
    got = ef.parse_scoring(PAYLOAD)
    assert all(u["statId"] != 998 for u in got["unmapped"])


def test_a_payload_with_no_scoring_raises_rather_than_scoring_nothing():
    """An empty scoring map reads as a league that scores nothing, which
    would produce a confident lineup of zeros."""
    for broken in ({}, {"settings": {}}, {"settings": {"scoringSettings": {}}}):
        try:
            ef.parse_scoring(broken)
        except DataUnavailable:
            continue
        raise AssertionError(f"did not raise on {broken}")


# --- slots ------------------------------------------------------------------
def test_slot_counts_expand_into_the_flat_list_the_optimiser_reads():
    got = ef.parse_slots(PAYLOAD)
    assert got.count("QB") == 1 and got.count("RB") == 2
    assert got.count("WR") == 2 and got.count("TE") == 1
    assert got.count("FLEX") == 1


def test_bench_and_ir_come_through_and_are_dropped_downstream():
    """`starting_slots` is what removes them, and it is tested there — the
    adapter's job is to report the league as it is."""
    from engine import fantasy_lineup as fl
    got = ef.parse_slots(PAYLOAD)
    assert "BN" in got and "IR" in got
    assert "BN" not in fl.starting_slots(got)


def test_a_slot_we_do_not_model_is_skipped_not_guessed():
    got = ef.parse_slots(PAYLOAD)
    assert len([s for s in got if s not in ef.SLOT_IDS.values()]) == 0


def test_a_payload_with_no_roster_settings_raises():
    try:
        ef.parse_slots({"settings": {}})
    except DataUnavailable:
        return
    raise AssertionError("guessed a roster shape instead of raising")


# --- rosters ----------------------------------------------------------------
def test_every_team_comes_back_with_a_readable_label():
    got = ef.parse_rosters(PAYLOAD)
    assert set(got) == {"Mine", "Other Guys"}


def test_a_player_whose_position_we_cannot_read_is_dropped():
    """Seating an unknown position would put him in a slot the league
    rejects."""
    got = ef.parse_rosters(PAYLOAD)
    assert [p["player"] for p in got["Mine"]] == ["Jalen Hurts",
                                                  "Bijan Robinson"]


def test_a_payload_with_no_teams_raises():
    try:
        ef.parse_rosters({"settings": {}})
    except DataUnavailable:
        return
    raise AssertionError("returned an empty league instead of raising")


def test_the_owner_lookup_returns_none_for_a_stranger():
    """None is what stops the desk optimising somebody else's roster."""
    assert ef.owner_of(PAYLOAD, "{ABC}") == "Mine"
    assert ef.owner_of(PAYLOAD, "{XYZ}") == "Other Guys"
    assert ef.owner_of(PAYLOAD, "{NOPE}") is None
    assert ef.owner_of(PAYLOAD, "") is None


# --- the url ----------------------------------------------------------------
def test_the_views_are_asked_for_by_name():
    """Without them ESPN returns a skeleton with no settings and no
    rosters, which parses to an empty league rather than an error."""
    url = ef._url(2025, "12345")
    for view in ("mSettings", "mTeam", "mRoster"):
        assert f"view={view}" in url
    assert "/seasons/2025/" in url and "/leagues/12345" in url


def test_there_is_a_fallback_host():
    """ESPN moved fantasy reads between two hosts and both have answered
    recently; one 404 should not read as "no such league"."""
    assert ef.BASE != ef.FALLBACK
    src = open(os.path.join(ROOT, "engine", "sources", "espnfantasy.py"),
               encoding="utf-8").read()
    assert "for host in (BASE, FALLBACK)" in src


def test_the_adapter_shape_matches_what_the_desk_already_consumes():
    """The desk must never learn which platform it is talking to."""
    src = open(os.path.join(ROOT, "engine", "sources", "espnfantasy.py"),
               encoding="utf-8").read()
    i = src.index("def league(")
    body = src[i:]
    for key in ("name", "slots", "scoring", "rosters", "unmapped"):
        assert f'"{key}"' in body, key


# --- the wiring -------------------------------------------------------------
def test_the_desk_serves_espn_through_the_same_endpoint():
    """The answer is shared — `fantasy_lineup` and `fantasy_trade` never
    learn where the league came from. Only the READING differs, which is
    why the two platforms get separate handlers rather than one branched
    inline where they could drift into each other's assumptions."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert 'platform not in ("sleeper", "espn", "yahoo")' in src
    assert "def _league_desk_espn(" in src
    i = src.index("def _league_desk_espn(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert "fantasy_lineup.lineup(" in body
    assert "fantasy_trade.generate(" in body


def test_an_unknown_platform_is_refused_rather_than_defaulted():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"unknown platform"' in src


def test_unmapped_scoring_reaches_the_page():
    """A rule silently ignored is a lineup silently wrong, and ESPN's
    scoring ids have never been confirmed against a live response from
    this container."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _league_desk_espn(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert '"unmapped_scoring"' in body


# --- the door somebody can actually open ------------------------------------

def _app():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _fn(src, name):
    """A function body by brace matching, past its parameter list."""
    i = src.index("function " + name + "(")
    j, depth = src.index("(", i), 0
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = src.index("{", j), 0
    for k in range(start, len(src)):
        if src[k] == "{":
            d += 1
        elif src[k] == "}":
            d -= 1
            if not d:
                return src[i:k + 1]
    raise AssertionError(name + " never closes")


def test_the_page_can_reach_the_platform_this_module_implements():
    """BUILT AND UNREACHABLE until 2026-08-23. This module had twenty
    passing tests, server.py routed /api/leaguedesk?platform=espn to it,
    and renderLeagueDesk had taken a platform argument since the day it
    was written — and nothing on the page ever passed "espn". A finished
    platform behind a door with no handle."""
    app = _app()
    assert 'id="espn-zone"' in app, "no host for the connect card"
    assert "function renderEspnZone(" in app
    assert 'renderEspnZone();' in app, "defined but never called"
    assert '"espn", "espn-desk"' in app, (
        "the desk is never asked for an ESPN league")


def test_the_link_is_remembered_on_the_account_not_just_the_device():
    """Ethan: "seamlessly sync there fantasy accounts". Sleeper's
    username has ridden the synced profile since accounts shipped;
    linking on the phone and finding nothing on the laptop is not
    connecting once."""
    app = _app()
    gather = _fn(app, "acctGather")
    assert "ESPN_LEAGUE_KEY" in gather and "espn:" in gather, (
        "the ESPN link never leaves the device it was typed on")
    apply = _fn(app, "acctApplySection")
    assert "ESPN_LEAGUE_KEY" in apply, "a synced link is never adopted"


def test_a_profile_written_before_espn_existed_does_not_wipe_the_link():
    """`put` treats undefined as "remove", so a device syncing an older
    fantasy section would clear a link the phone had just made — every
    time. Absent means "this copy has nothing to say about ESPN", not
    "ESPN was disconnected"."""
    apply = _fn(_app(), "acctApplySection")
    assert '"espn" in d' in apply, (
        "an older profile without the field still writes it, which "
        "unlinks the league")
    assert '"espnTeam" in d' in apply


def test_the_card_refuses_a_league_id_the_server_would_refuse():
    """server.py answers 400 for anything that is not digits. Saying so
    in the box costs a keystroke; letting it through costs a round trip
    and an error card that reads like the league is missing."""
    zone = _fn(_app(), "renderEspnZone")
    assert "\\d{1,25}" in zone, "any string is accepted and sent"


def test_the_card_names_the_setting_rather_than_asking_for_a_cookie():
    """The limit this module is built around, restated where somebody
    hits it. A private ESPN league needs espn_s2 and SWID — session
    cookies that grant full account access, last months and cannot be
    scoped to one league — and the answer is the League Settings toggle,
    not a paste box."""
    import re as _re
    html = _fn(_app(), "espnConnectHTML")
    assert "Viewable by the public" in html
    # WHAT IT COLLECTS, not what it mentions. The first cut of this
    # asserted the word "password" was absent and failed on the card's
    # own reassurance — "Read-only and no password" — which is the
    # sentence that makes the point it was trying to check.
    ids = _re.findall(r'<input id="([^"]+)"', html)
    assert set(ids) <= {"espn-league-id", "espn-team-id"}, (
        f"the card collects something else: {ids}")
    assert 'type="password"' not in html
    assert "espn_s2" not in html and "SWID" not in html


def test_the_link_can_be_undone():
    """A connect with no disconnect is a setting somebody has to clear
    site data to change."""
    zone = _fn(_app(), "renderEspnZone")
    assert "espn-forget" in zone
    assert "removeItem(ESPN_LEAGUE_KEY)" in zone
    assert "removeItem(ESPN_TEAM_KEY)" in zone


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
