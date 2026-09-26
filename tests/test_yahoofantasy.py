"""A Yahoo league, read through OAuth2 — and the boundary that allows it.

Ethan, 2026-08-15, named Yahoo among the platforms he plays in.

WHY YAHOO IS BUILT AND A PRIVATE ESPN LEAGUE IS NOT, in one sentence:
Yahoo's flow never shows this app a password, the user approves it on
Yahoo's own screen, and the token can be revoked from a Yahoo account
page — where ESPN's private path wants two session cookies that grant
full account access and cannot be scoped or revoked short of a logout.
The first tests in this file pin that difference so it cannot erode.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH — probed, and
fantasysports.yahooapis.com returns nothing through the proxy. So the
network is never touched here. What IS tested is everything that decides
whether the first real run works:

  * the request SHAPES (auth url, token exchange, refresh) — pure
    functions returning `(url, headers, body)` for exactly this reason;
  * the WALKER, against Yahoo's genuinely strange JSON: lists inside
    dicts inside lists, numeric string keys, `count` fields;
  * the NAME MAP, including the trap that Yahoo sends two different names
    per stat ("Passing Yards" and "Pass Yds") and a map holding one of
    them silently scores a league wrong.

The last one is the reason this file is long. This repo has already
shipped a bug of exactly that kind — `pass_att` read from a market that
did not exist, with every consumer downstream reading zero and not one
error raised.
"""

import io
import json
import os
import sys
import tempfile
import tokenize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "engine", "sources", "yahoofantasy.py")

from engine.sources import yahoofantasy as yf                  # noqa: E402
from engine.sources.fetch import DataUnavailable               # noqa: E402


def _code_tokens():
    """``(names, strings)`` from the module's source.

    Grepping raw source for "password" matches the module's own
    EXPLANATION of why it takes none — and so does grepping code, because
    the message shown when credentials are missing SAYS "no password is
    ever shared with this app". That sentence is the feature. A guard
    that fires on it is a guard that teaches you to ignore it.

    So the two are separated: an IDENTIFIER named for a password is a
    password being handled, and a string used as a FIELD KEY is one being
    sent. A password named in a sentence is neither.
    """
    names, strings = [], []
    with open(SRC, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.NAME:
                names.append(tok.string)
            elif tok.type == tokenize.STRING:
                strings.append(tok.string)
    return names, strings


#: Yahoo's league settings, in the shape its API documents: the league is a
#: LIST whose first element is metadata and whose second holds `settings`,
#: itself a list of one dict. Nothing here indexes that; it is written this
#: way precisely so the walker has to cope with it.
SETTINGS = {"fantasy_content": {"league": [
    {"league_key": "461.l.1234567", "league_id": "1234567",
     "name": "Sunday Money", "season": "2026", "num_teams": "12"},
    {"settings": [{
        "draft_type": "live",
        "roster_positions": [
            {"roster_position": {"position": "QB", "position_type": "O",
                                 "count": 1}},
            {"roster_position": {"position": "WR", "position_type": "O",
                                 "count": 2}},
            {"roster_position": {"position": "RB", "position_type": "O",
                                 "count": 2}},
            {"roster_position": {"position": "TE", "position_type": "O",
                                 "count": 1}},
            {"roster_position": {"position": "W/R/T", "count": 1}},
            {"roster_position": {"position": "Q/W/R/T", "count": 1}},
            {"roster_position": {"position": "K", "count": 1}},
            {"roster_position": {"position": "DEF", "count": 1}},
            {"roster_position": {"position": "BN", "count": 6}},
            {"roster_position": {"position": "IR", "count": 1}},
            {"roster_position": {"position": "D", "count": 2}},   # IDP
        ],
        "stat_categories": {"stats": [
            {"stat": {"stat_id": 4, "name": "Passing Yards",
                      "display_name": "Pass Yds", "position_type": "O"}},
            {"stat": {"stat_id": 5, "name": "Passing Touchdowns",
                      "display_name": "Pass TD", "position_type": "O"}},
            {"stat": {"stat_id": 6, "name": "Interceptions",
                      "display_name": "Int", "position_type": "O"}},
            {"stat": {"stat_id": 9, "name": "Rushing Yards",
                      "display_name": "Rush Yds", "position_type": "O"}},
            {"stat": {"stat_id": 10, "name": "Rushing Touchdowns",
                      "display_name": "Rush TD", "position_type": "O"}},
            {"stat": {"stat_id": 11, "name": "Receptions",
                      "display_name": "Rec", "position_type": "O"}},
            {"stat": {"stat_id": 12, "name": "Reception Yards",
                      "display_name": "Rec Yds", "position_type": "O"}},
            {"stat": {"stat_id": 13, "name": "Reception Touchdowns",
                      "display_name": "Rec TD", "position_type": "O"}},
            {"stat": {"stat_id": 19, "name": "Field Goals 0-19 Yards",
                      "display_name": "FG 0-19", "position_type": "K"}},
            {"stat": {"stat_id": 31, "name": "Points Allowed",
                      "display_name": "Pts Allow", "position_type": "DT"}},
            {"stat": {"stat_id": 78, "name": "Targets",
                      "display_name": "Tgt", "position_type": "O"}},
        ]},
        "stat_modifiers": {"stats": [
            {"stat": {"stat_id": 4, "value": "0.04"}},
            {"stat": {"stat_id": 5, "value": "6"}},        # six-point pass TD
            {"stat": {"stat_id": 6, "value": "-1"}},       # not PPR's -2
            {"stat": {"stat_id": 9, "value": "0.1"}},
            {"stat": {"stat_id": 10, "value": "6"}},
            {"stat": {"stat_id": 11, "value": "0.5"}},     # half PPR
            {"stat": {"stat_id": 12, "value": "0.1"}},
            {"stat": {"stat_id": 13, "value": "6"}},
            {"stat": {"stat_id": 19, "value": "3"}},       # kicker
            {"stat": {"stat_id": 31, "value": "-0.5"}},    # team defense
            {"stat": {"stat_id": 78, "value": "0.25"}},    # offence, unmapped
            {"stat": {"stat_id": 57, "value": "0"}},       # priced at nothing
        ]},
    }]},
]}}

#: The teams+roster payload, with the numeric-string keys and `count`
#: fields Yahoo really sends.
TEAMS = {"fantasy_content": {"league": [
    {"league_key": "461.l.1234567", "name": "Sunday Money"},
    {"teams": {
        "count": 2,
        "0": {"team": [
            [{"team_key": "461.l.1234567.t.1"}, {"team_id": "1"},
             {"name": "Bench Mob"}, {"is_owned_by_current_login": 1},
             {"managers": [{"manager": {"nickname": "Ethan"}}]}],
            {"roster": {"0": {"players": {
                "count": 2,
                "0": {"player": [[{"player_key": "461.p.1"},
                                  {"name": {"full": "Jalen Hurts",
                                            "first": "Jalen"}},
                                  {"display_position": "QB"},
                                  {"primary_position": "QB"}]]},
                "1": {"player": [[{"player_key": "461.p.2"},
                                  {"name": {"full": "Puka Nacua"}},
                                  {"display_position": "WR"}]]},
            }}}},
        ]},
        "1": {"team": [
            [{"team_key": "461.l.1234567.t.2"}, {"team_id": "2"},
             {"name": "Third And Long"}, {"is_owned_by_current_login": 0}],
            {"roster": {"0": {"players": {
                "count": 2,
                "0": {"player": [[{"name": {"full": "Bijan Robinson"}},
                                  {"display_position": "RB"}]]},
                "1": {"player": [[{"name": {"full": "Some Linebacker"}},
                                  {"display_position": "LB"}]]},
            }}}},
        ]},
    }},
]}}


# --- the boundary that lets this platform be built at all -------------------
def test_no_password_is_ever_handled():
    """The standing rule. Yahoo is built BECAUSE the flow avoids this —
    if a password field ever appears here, the reason for building Yahoo
    at all has gone.

    Note what this does NOT flag: the message shown when credentials are
    missing ends "no password is ever shared with this app". Saying so is
    the point; a guard that fails on its own promise is noise."""
    names, strings = _code_tokens()
    for bad in ("password", "passwd", "pwd"):
        assert not any(bad in n.lower() for n in names), \
            f"yahoofantasy has an identifier named for a {bad}"
    # And not sent as a form field either, which is the other half.
    for s in strings:
        low = s.lower()
        for bad in ('"password"', "'password'", "password=", '"passwd"'):
            assert bad not in low, f"yahoofantasy sends {bad}"


def test_the_only_secrets_are_the_registered_app_credentials():
    """A client id and secret identify the APP, not the user. They are
    not a login: with them and nothing else you cannot read anybody's
    league — a human still has to approve it on Yahoo's screen."""
    names, strings = _code_tokens()
    flat = " ".join(strings)
    assert "YAHOO_CLIENT_ID" in flat and "YAHOO_CLIENT_SECRET" in flat
    assert "YAHOO_PASSWORD" not in flat


def test_approval_happens_on_yahoos_own_domain():
    """Not on a form we render. A consent screen served by anyone but the
    provider is a phishing page, whoever wrote it."""
    url = yf.authorize_url("CID")
    assert url.startswith("https://api.login.yahoo.com/")
    assert "client_id=CID" in url and "response_type=code" in url


def test_the_out_of_band_flow_is_the_default_redirect():
    """This site is served on a LAN address with no public HTTPS name, so
    there is no redirect URI to register. `oob` is Yahoo's supported
    answer for exactly that shape — it shows a code to paste."""
    assert yf.OOB == "oob"
    assert "redirect_uri=oob" in yf.authorize_url("CID")
    assert "redirect_uri=oob" not in yf.authorize_url("CID", "https://x/cb")


# --- the token, and where it lives ------------------------------------------
def test_the_token_exchange_sends_the_secret_in_a_header_not_a_query():
    """A query string lands in server logs, browser history and proxy
    logs. Basic auth in a header does not."""
    url, headers, body = yf.token_request("CODE", "CID", "SEC")
    assert "SEC" not in url and b"SEC" not in body
    assert headers["Authorization"].startswith("Basic ")
    assert b"grant_type=authorization_code" in body and b"code=CODE" in body


def test_a_refresh_reuses_the_same_shape():
    url, headers, body = yf.refresh_request("RT", "CID", "SEC")
    assert url == yf.TOKEN_URL
    assert b"grant_type=refresh_token" in body and b"refresh_token=RT" in body
    assert "SEC" not in url


def test_the_token_file_is_owner_only_before_anything_is_written_to_it():
    """0600 at CREATION, not after. A token that is world-readable for
    even one moment on a shared machine has already leaked, and chmod
    after the write is exactly that window."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "sub", "tok.json")
        assert yf.save_token({"access_token": "A", "refresh_token": "R"}, p)
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    src = open(SRC, encoding="utf-8").read()
    assert "0o600" in src.split("def save_token")[1].split("os.fdopen")[0], \
        "the mode is not set on the open() that creates the file"


def test_a_stored_token_round_trips_and_a_missing_one_is_not_an_error():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tok.json")
        assert yf.load_token(p) == {}
        assert yf.connected(p) is False
        yf.save_token({"access_token": "A", "refresh_token": "R"}, p)
        assert yf.load_token(p)["refresh_token"] == "R"
        assert yf.connected(p) is True


def test_connected_means_a_refresh_token_not_an_access_token():
    """An access token lasts an hour. Reporting "connected" off one means
    the page says connected until it silently is not."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tok.json")
        yf.save_token({"access_token": "A"}, p)
        assert yf.connected(p) is False


def test_an_expiry_is_stored_as_an_absolute_time():
    """`expires_in: 3600` is meaningless once it is on disk — it has to
    become a moment, or a token written an hour ago reads as fresh."""
    got = yf._stamp({"expires_in": 3600})
    import time as _t
    assert 3500 < got["expires_at"] - _t.time() < 3600


def test_a_refresh_that_omits_a_new_refresh_token_keeps_the_old_one():
    """Yahoo returns a new refresh token on most refreshes and omits it
    on some. Overwriting with nothing disconnects the app at the next
    expiry for no reason at all."""
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def access_token")[1].split("\ndef ")[0]
    assert "merged = dict(tok)" in body and "merged.update(fresh)" in body


# --- Yahoo's JSON -----------------------------------------------------------
def test_the_walker_finds_a_value_through_lists_dicts_and_numeric_keys():
    """The shape is real, not invented for the test: Yahoo nests a list
    inside a dict inside a list, keyed "0", "1", with `count` alongside."""
    assert yf.find_first(SETTINGS, "league_key") == "461.l.1234567"
    assert yf.find_first(SETTINGS, "season") == "2026"
    keys = yf.find_all(TEAMS, "team_key")
    assert keys == ["461.l.1234567.t.1", "461.l.1234567.t.2"]


def test_the_walker_returns_every_match_not_just_the_first():
    assert len(yf.find_all(SETTINGS, "stat_id")) == 23     # 11 named, 12 priced


def test_a_missing_key_is_a_default_rather_than_an_exception():
    assert yf.find_first(SETTINGS, "nothing_like_this") is None
    assert yf.find_first(SETTINGS, "nope", "fallback") == "fallback"
    assert yf.find_all(None, "x") == [] and yf.find_all(7, "x") == []


# --- scoring ----------------------------------------------------------------
def test_scoring_is_mapped_by_name_and_reaches_the_optimisers_keys():
    got = yf.parse_scoring(SETTINGS)["scoring"]
    assert got["pass_yd"] == 0.04
    assert got["pass_td"] == 6.0            # the six-pointer, not PPR's 4
    assert got["pass_int"] == -1.0          # not PPR's -2 either
    assert got["rec"] == 0.5                # half PPR
    assert got["rec_yd"] == 0.1 and got["rush_yd"] == 0.1
    assert got["rush_td"] == 6.0 and got["rec_td"] == 6.0


def test_both_of_yahoos_two_names_per_stat_map_to_the_same_key():
    """THE TRAP IN THIS ADAPTER. Yahoo sends `name` "Passing Yards" AND
    `display_name` "Pass Yds" — different words for one stat. A map
    holding only the long form scores nothing at all if a payload carries
    the short one, and the failure is silent: the league simply comes back
    as though it agreed with PPR everywhere."""
    long_only = {"stat_categories": {"stats": [
        {"stat": {"stat_id": 4, "name": "Passing Yards"}}]},
        "stat_modifiers": {"stats": [{"stat": {"stat_id": 4,
                                               "value": "0.05"}}]}}
    short_only = {"stat_categories": {"stats": [
        {"stat": {"stat_id": 4, "display_name": "Pass Yds"}}]},
        "stat_modifiers": {"stats": [{"stat": {"stat_id": 4,
                                               "value": "0.05"}}]}}
    assert yf.parse_scoring(long_only)["scoring"] == {"pass_yd": 0.05}
    assert yf.parse_scoring(short_only)["scoring"] == {"pass_yd": 0.05}


def test_yahoos_own_spelling_of_receiving_stats_is_handled():
    """Yahoo says "Reception Yards" where every other platform says
    "Receiving". Both are in the map because which one arrives is not
    something this container can confirm against a live response."""
    assert yf.STAT_NAMES["reception yards"] == "rec_yd"
    assert yf.STAT_NAMES["receiving yards"] == "rec_yd"


def test_an_offensive_rule_we_cannot_place_is_reported_not_dropped():
    """THE ONE THIS REPO HAS ALREADY PAID FOR. A scoring rule silently
    ignored is a lineup silently wrong."""
    got = yf.parse_scoring(SETTINGS)["unmapped"]
    assert [u["name"] for u in got] == ["Targets"]
    assert got[0]["points"] == 0.25


def test_kicker_and_defense_rules_are_separated_from_ones_we_got_wrong():
    """Both are unapplied; only one is a bug. This app does not project
    kickers, and calling eight field-goal-distance rules "could not be
    mapped" buries the ninth rule that genuinely was missed."""
    got = yf.parse_scoring(SETTINGS)
    names = [u["name"] for u in got["not_modelled"]]
    assert "Field Goals 0-19 Yards" in names and "Points Allowed" in names
    assert all(u["name"] not in names for u in got["unmapped"])


def test_a_rule_priced_at_zero_is_not_reported_as_a_surprise():
    """Yahoo lists rules a league does not use at 0. Reporting those
    would bury the one that matters under thirty that do not."""
    got = yf.parse_scoring(SETTINGS)
    assert all(str(u["stat_id"]) != "57" for u in got["unmapped"])


def test_a_payload_with_no_modifiers_raises_rather_than_scoring_nothing():
    """An empty scoring map reads as a league that scores nothing, which
    produces a confident lineup of zeros — the worst possible output,
    because it looks like an answer."""
    for broken in ({}, {"fantasy_content": {}},
                   {"stat_categories": {"stats": []}}):
        try:
            yf.parse_scoring(broken)
        except DataUnavailable:
            continue
        raise AssertionError(f"did not raise on {broken}")


def test_the_touchdown_rates_are_now_actually_consumed():
    """`rush_td` and `rec_td` were produced by every adapter and read by
    nothing, so a league scoring a rushing touchdown at 4 was scored at
    PPR's 6 in silence. Either the difference gets applied, or it gets
    reported — never neither."""
    from engine import fantasy_lineup as fl
    assert "rush_td" in fl.PPR_BASELINE and "rec_td" in fl.PPR_BASELINE
    means = {"fp_ppr": 10.0, "position": "RB", "rush_td": 0.5}
    got = fl.league_points(means, {"rush_td": 4.0})
    assert got["points"] == 9.0             # 10 + (4-6) * 0.5
    blind = fl.league_points({"fp_ppr": 10.0, "position": "RB"},
                             {"rush_td": 4.0})
    assert blind["exact"] is False and "rush_td" in blind["missing"]


def test_a_receivers_passing_stats_are_zero_rather_than_missing():
    """Found the first time a Yahoo league rendered: CeeDee Lamb came back
    flagged "could not adjust for pass_int, pass_td". The ingest stores
    passing markets for quarterbacks only, so for a receiver an absent
    value means zero — a fact, not a gap.

    Left alone, EVERY receiver, back and tight end would carry that
    warning forever, and a flag that fires on every row of the table is
    one nobody reads. It would have buried a real gap the day one
    appeared."""
    from engine import fantasy_lineup as fl
    wr = fl.league_points({"fp_ppr": 15.0, "position": "WR",
                           "receptions": 6.0},
                          {"pass_td": 6.0, "pass_int": -1.0, "rec": 1.0})
    assert wr["exact"] is True and wr["missing"] == []
    # A QUARTERBACK with the same hole is still a real gap, and still said.
    qb = fl.league_points({"fp_ppr": 20.0, "position": "QB"},
                          {"pass_td": 6.0})
    assert qb["exact"] is False and "pass_td" in qb["missing"]


# --- slots ------------------------------------------------------------------
def test_roster_positions_expand_into_the_flat_list_the_optimiser_reads():
    got = yf.parse_slots(SETTINGS)
    assert got.count("QB") == 1 and got.count("RB") == 2
    assert got.count("WR") == 2 and got.count("TE") == 1
    assert got.count("BN") == 6


def test_yahoos_flex_codes_become_the_slots_the_assignment_understands():
    """"W/R/T" and "Q/W/R/T" are Yahoo's flex and superflex. A superflex
    read as a bench seat costs you a starting quarterback every week."""
    got = yf.parse_slots(SETTINGS)
    assert "FLEX" in got and "SUPER_FLEX" in got
    from engine import fantasy_lineup as fl
    assert fl.SLOT_ELIGIBILITY["SUPER_FLEX"] == {"QB", "RB", "WR", "TE"}


def test_a_slot_we_do_not_model_is_skipped_rather_than_guessed():
    got = yf.parse_slots(SETTINGS)
    assert all(s in yf.SLOT_NAMES.values() for s in got)
    assert "D" not in got                    # the IDP slot


def test_bench_and_ir_come_through_and_are_dropped_downstream():
    from engine import fantasy_lineup as fl
    got = yf.parse_slots(SETTINGS)
    assert "BN" in got and "IR" in got
    start = fl.starting_slots(got)
    assert "BN" not in start and "IR" not in start
    assert len(start) == 10


def test_a_payload_with_no_roster_positions_raises():
    try:
        yf.parse_slots({"fantasy_content": {"league": [{"name": "x"}]}})
    except DataUnavailable:
        return
    raise AssertionError("guessed a roster shape instead of raising")


# --- rosters ----------------------------------------------------------------
def test_every_team_comes_back_with_its_roster():
    got = yf.parse_rosters(TEAMS)
    assert set(got) == {"Bench Mob", "Third And Long"}
    assert [p["player"] for p in got["Bench Mob"]] == ["Jalen Hurts",
                                                       "Puka Nacua"]


def test_a_team_name_is_never_read_off_a_players_name_block():
    """A player's `name` is a DICT of first/last/full and it lives inside
    the same team node as the team's own string `name`. Taking the first
    match without checking the type produces a team called
    "{'full': 'Jalen Hurts'}"."""
    got = yf.parse_rosters(TEAMS)
    assert all(isinstance(k, str) and not k.startswith("{") for k in got)


def test_a_position_we_cannot_seat_is_dropped():
    """Seating a linebacker in a FLEX would propose a lineup the league
    rejects."""
    got = yf.parse_rosters(TEAMS)
    assert [p["player"] for p in got["Third And Long"]] == ["Bijan Robinson"]


def test_a_multi_position_player_takes_his_first_listed_position():
    got = yf.parse_rosters({"team": [
        [{"name": "T"}], {"roster": {"0": {"players": {"0": {"player": [
            [{"name": {"full": "Taysom Hill"}},
             {"display_position": "TE,QB"}]]}}}}}]})
    assert got["T"] == [{"player": "Taysom Hill", "position": "TE"}]


def test_a_payload_with_no_teams_raises():
    try:
        yf.parse_rosters({"fantasy_content": {"league": [{"name": "x"}]}})
    except DataUnavailable:
        return
    raise AssertionError("returned an empty league instead of raising")


def test_your_own_team_is_identified_by_yahoos_flag_not_by_a_typed_id():
    """Yahoo says which team is yours. That is better than anything the
    user could type: nothing to look up, and it cannot select somebody
    else's roster by accident."""
    assert yf.my_team(TEAMS) == "Bench Mob"


def test_no_flag_means_none_rather_than_a_guess():
    """None is what stops the desk optimising a stranger's team."""
    stripped = json.loads(json.dumps(TEAMS).replace(
        '"is_owned_by_current_login": 1', '"is_owned_by_current_login": 0'))
    assert yf.my_team(stripped) is None


# --- the reads --------------------------------------------------------------
def test_a_bare_number_is_refused_with_the_shape_of_a_real_league_key():
    """Yahoo keys look like `461.l.1234567`. A user pasting the number
    they see in the URL gets told what is missing, not a 404."""
    for bad in ("1234567", "", "461.1234567", "abc.l.1", "461.l.x"):
        try:
            yf.league(bad)
        except DataUnavailable as exc:
            assert "461.l.1234567" in str(exc)
            continue
        raise AssertionError(f"accepted {bad!r} as a league key")


def test_the_api_asks_for_json_and_never_puts_the_token_in_the_url():
    """A bearer token in a query string ends up in logs. In a header it
    does not."""
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def api_get")[1].split("\ndef ")[0]
    assert 'format=json' in body
    assert '"Authorization": f"Bearer {tok}"' in body
    assert "access_token=" not in body


def test_a_dead_access_token_is_retried_once_and_not_looped_on():
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def api_get")[1].split("\ndef ")[0]
    assert "for attempt in (1, 2)" in body
    assert "exc.code == 401 and attempt == 1" in body


def test_a_league_you_are_not_in_says_so_rather_than_reporting_it_empty():
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def api_get")[1].split("\ndef ")[0]
    assert "only read leagues you are actually in" in body


def test_the_token_endpoints_error_never_quotes_our_own_headers():
    """The client secret lives in the Authorization header, and an error
    string carrying it would reach a log, a traceback or a page."""
    src = open(SRC, encoding="utf-8").read()
    body = src.split("def _post")[1].split("\ndef ")[0]
    assert "{headers" not in body and "headers!r" not in body


def test_a_used_code_gets_an_explanation_rather_than_a_status_number():
    """Yahoo's codes are single-use and short-lived, and "HTTP 400" sends
    the reader looking for a bug that is not there."""
    src = open(SRC, encoding="utf-8").read()
    assert "single-use" in src


def test_nothing_is_stored_when_yahoo_replies_without_a_token():
    real = yf._post
    yf._post = lambda *a, **k: {"error": "nope"}
    os.environ.setdefault("YAHOO_CLIENT_ID", "test-id")
    os.environ.setdefault("YAHOO_CLIENT_SECRET", "test-secret")
    try:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "tok.json")
            try:
                yf.exchange_code("CODE", path=p)
            except DataUnavailable:
                assert not os.path.exists(p)
                return
            raise AssertionError("reported a connection it did not make")
    finally:
        yf._post = real


def test_the_exchange_never_hands_a_token_back_to_its_caller():
    """The browser is told THAT it worked, not the secret that makes it
    work — the server is the only thing that ever sees the token."""
    real = yf._post
    yf._post = lambda *a, **k: {"access_token": "A", "refresh_token": "R",
                                "expires_in": 3600}
    os.environ.setdefault("YAHOO_CLIENT_ID", "test-id")
    os.environ.setdefault("YAHOO_CLIENT_SECRET", "test-secret")
    try:
        with tempfile.TemporaryDirectory() as d:
            got = yf.exchange_code("CODE", path=os.path.join(d, "tok.json"))
        flat = json.dumps(got)
        assert "A" not in json.dumps(list(got.values()))
        assert "access_token" not in flat and "refresh_token" not in flat
        assert got["connected"] is True
    finally:
        yf._post = real


# --- the shared shape -------------------------------------------------------
def test_the_adapter_shape_matches_what_the_desk_already_consumes():
    """The desk must never learn which platform it is talking to."""
    src = open(SRC, encoding="utf-8").read()
    body = src[src.index("def league("):]
    for key in ("name", "slots", "scoring", "rosters", "unmapped", "mine"):
        assert f'"{key}"' in body, key


def test_the_parsed_league_actually_optimises():
    """End to end on the fixture, with no network: settings and rosters
    in, a legal lineup out. This is the test that would have caught a
    parser that returns plausible-looking rubbish."""
    from engine import fantasy_lineup as fl
    slots = fl.starting_slots(yf.parse_slots(SETTINGS))
    scoring = yf.parse_scoring(SETTINGS)["scoring"]
    rosters = yf.parse_rosters(TEAMS)
    means = {"Jalen Hurts": {"fp_ppr": 22.0, "position": "QB", "_games": 17,
                             "pass_td": 1.8, "pass_int": 0.6,
                             "pass_yds": 250.0},
             "Puka Nacua": {"fp_ppr": 16.0, "position": "WR", "_games": 17,
                            "receptions": 7.0, "rec_yds": 85.0}}
    got = fl.lineup(rosters["Bench Mob"], slots, scoring, means)
    seated = [s["player"] for s in got["starters"] if s.get("player")]
    assert "Jalen Hurts" in seated and "Puka Nacua" in seated
    # Half PPR costs Nacua half a point per catch against the PPR base.
    nacua = [s for s in got["starters"] if s.get("player") == "Puka Nacua"][0]
    assert nacua["points"] < 16.0


# --- the wiring -------------------------------------------------------------
def test_the_desk_serves_yahoo_through_the_same_endpoint():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"yahoo"' in src
    assert "def _league_desk_yahoo(" in src
    i = src.index("def _league_desk_yahoo(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert "fantasy_lineup.lineup(" in body
    assert "fantasy_trade.generate(" in body
    assert '"unmapped_scoring"' in body


def test_the_league_key_is_not_forced_through_the_numeric_check():
    """`\\d{1,25}` is right for Sleeper and ESPN and rejects every Yahoo
    key ever issued."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _league_desk(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert 'platform == "yahoo"' in body


def test_the_server_never_sends_a_token_to_the_browser():
    """The whole point of storing it server-side."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    for i in [m for m in range(len(src)) if src.startswith("yahoo", m)]:
        line = src[src.rfind("\n", 0, i) + 1:src.find("\n", i)]
        if "access_token" in line or "refresh_token" in line:
            assert "json.dumps" not in line, line


def test_the_connect_endpoint_exists_and_takes_a_pasted_code():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert "/api/yahoo" in src
    assert "exchange_code" in src


def test_connecting_and_disconnecting_are_restricted_to_this_machine():
    """READING the site is LAN-wide and always has been. Granting or
    revoking a third party's access to a Yahoo account is not the same
    kind of action, and a phone on the same coffee-shop wifi should not
    be able to take it."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def _yahoo_post("):]
    body = body[:body.index("\n    def ")]
    assert "self._local_only()" in body
    guard = src[src.index("def _local_only("):]
    guard = guard[:guard.index("\n    def ")]
    assert "127.0.0.1" in guard and "::1" in guard


def test_an_approval_code_is_validated_before_it_is_sent_anywhere():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def _yahoo_post("):]
    body = body[:body.index("\n    def ")]
    assert "re.fullmatch" in body


def test_the_status_endpoint_reports_existence_and_never_the_token():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def _yahoo("):]
    body = body[:body.index("\n    def ")]
    i = body.index('if path == "status"')
    status = body[i:body.index('if path == "start"')]
    assert "yf.connected()" in status
    assert "access_token" not in status and "load_token" not in status


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
