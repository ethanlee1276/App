"""A college roster is every man on the team, not the ones who scored.

Ethan, 2026-09-19: *"a lot of CFB player dont show up in the player
search."*

The first fix taught the search to top up from
`web/data/rosters_cfb.json` — and it bought nothing, because that FILE
was built from the same place the search already read. `rosters_build`
listed college players from `player_game_logs`, and college counts
appearances from `pass_yds`, `carries` and `receptions` ALONE. So a page
calling itself a roster held the men who touched the ball and nobody
else: no lineman, no defender, no kicker, no backup. On this box that is
5,522 college names against a league of roughly fifteen thousand.

Two halves, and the first one was a no-op without the second:

  1. the roster file now comes from ESPN's published per-school roster —
     the same payload `fetch_team_roster` has been pulling for the
     transfer lookup and the headshot join since August, read a third
     way and keeping the display spelling this time;
  2. appearances stay the FALLBACK and still fill the games column, so
     playing time remains the measured number and stops deciding
     existence.

WHAT MUST NOT COME BACK. A roster built by fetching 134 schools is a
loop that can hang (45s a request, a stage that reruns every 45 minutes)
and a loop that can half-succeed. Both are pinned here: the sweep is on
a wall clock, and a school that did not load is REPORTED rather than
quietly absent.

Run directly:
`python3 tests/test_the_college_roster_is_the_roster_not_the_box_score.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import rosters_build                                           # noqa: E402
from engine import db as hist_db                               # noqa: E402
from engine import rosters, statlogs                           # noqa: E402
from engine.sources import cfbdata                             # noqa: E402

#: One ESPN roster payload: a quarterback who has thrown, a guard who
#: never will, and a man whose name is spelled with the punctuation the
#: box score drops.
PAYLOAD = {"athletes": [
    {"position": "offense", "items": [
        {"fullName": "Gunner Stockton", "jersey": "14",
         "position": {"abbreviation": "QB"},
         "headshot": {"href": "http://x/qb.png"}},
        {"fullName": "A.J. Terrell Jr.", "jersey": "8",
         "position": {"abbreviation": "WR"},
         "headshot": "http://x/wr.png"},
        # A relative path, which is what ESPN publishes for a man with
        # no portrait — a STRING, and not one a browser can load.
        {"fullName": "Micah Morris", "jersey": "66",
         "headshot": "/i/headshots/nophoto.png"},
    ]},
    {"position": "specialTeam", "items": [
        # And the other empty shape: a dict carrying no href at all.
        {"firstName": "Peyton", "lastName": "Woodring", "jersey": "99",
         "position": {"name": "Place Kicker"},
         "headshot": {"alt": "no portrait"}},
    ]},
]}


def _tmp():
    return tempfile.mkdtemp()


def _names(rows):
    return [r["player"] for r in rows]


# --- reading one school's payload --------------------------------------
def test_the_display_spelling_survives():
    """`parse_team_roster` normalises the name away, because the lookup
    it serves joins on the normalised key. A SEARCH needs the string a
    reader recognises — "A.J. Terrell Jr.", not "a j terrell"."""
    got = _names(cfbdata.parse_team_people(PAYLOAD))
    assert "A.J. Terrell Jr." in got, got
    assert "a j terrell" not in got, got


def test_everyone_comes_back_not_only_the_ball_carriers():
    """The whole complaint in one assertion: the guard and the kicker
    are on the team and were on no page."""
    got = _names(cfbdata.parse_team_people(PAYLOAD))
    assert "Micah Morris" in got, got
    assert "Peyton Woodring" in got, got
    assert len(got) == 4, got


def test_a_position_falls_back_to_the_group_rather_than_going_blank():
    """A payload that changes shape should cost a coarser position, not
    an empty roster — the rule `parse_team_roster` already follows."""
    by = {r["player"]: r["position"]
          for r in cfbdata.parse_team_people(PAYLOAD)}
    assert by["Gunner Stockton"] == "QB", by
    assert by["Micah Morris"] == "OFFENSE", by
    assert by["Peyton Woodring"] == "PLACE KICKER", by


def test_a_headshot_that_is_not_a_url_yields_no_face():
    """Same rule as `parse_team_headshots`: the page draws a helmet for
    an absent face and a broken image for a wrong one."""
    by = {r["player"]: r["headshot"]
          for r in cfbdata.parse_team_people(PAYLOAD)}
    # Both empty shapes, because only one of them is caught by reading
    # `href`: a relative path IS a string and survives that read. A
    # mutation run with the guard deleted passed until this line named
    # the shape the guard is actually for.
    assert by["Micah Morris"] == "", by
    assert by["Peyton Woodring"] == "", by
    assert by["A.J. Terrell Jr."] == "http://x/wr.png", by
    assert by["Gunner Stockton"] == "http://x/qb.png", by


def test_it_walks_the_same_athletes_as_the_other_two_readers():
    """`_athletes` exists so the transfer lookup and the headshot join
    cannot disagree about who is on a team. A third reader that walked
    the payload its own way would be the bug it was extracted to stop."""
    assert (len(cfbdata.parse_team_people(PAYLOAD))
            == len(cfbdata.parse_team_roster(PAYLOAD))), "the two disagree"
    import inspect
    src = inspect.getsource(cfbdata.parse_team_people)
    assert "_athletes(payload)" in src, "it walks the payload by itself"


# --- the whole league, on a clock --------------------------------------
#: The other school, so the league fixture is two ROSTERS rather than
#: one roster published twice — two hits for one name would then read as
#: a duplication bug instead of as two men who share it.
OTHER = {"athletes": [{"position": "defense", "items": [
    {"fullName": "Deone Walker", "jersey": "0",
     "position": {"abbreviation": "DT"}},
]}]}


class _Feed:
    """A stand-in for `fetch_team_roster`, so nothing here touches the
    network and a slow school can be made slow on purpose."""

    def __init__(self, bad=(), slow=(), clock=None):
        self.bad, self.slow, self.asked = set(bad), set(slow), []
        self.clock = clock

    def __call__(self, ident, ttl=0):
        self.asked.append(ident)
        if self.clock is not None and ident in self.slow:
            self.clock[0] += 1000.0
        if ident in self.bad:
            raise RuntimeError("roster would not load")
        return OTHER if str(ident) == "333" else PAYLOAD


def _with_feed(feed, fn, clock=None):
    real_fetch, real_time = cfbdata.fetch_team_roster, None
    cfbdata.fetch_team_roster = feed
    if clock is not None:
        import time
        real_time = time.monotonic
        time.monotonic = lambda: clock[0]
    try:
        return fn()
    finally:
        cfbdata.fetch_team_roster = real_fetch
        if real_time is not None:
            import time
            time.monotonic = real_time


def test_the_league_comes_back_keyed_by_abbreviation():
    feed = _Feed()
    got, missed = _with_feed(feed, lambda: cfbdata.fetch_people(
        {"UGA": "61", "BAMA": "333"}))
    assert sorted(got) == ["BAMA", "UGA"], got
    assert missed == [], missed
    assert sorted(feed.asked) == ["333", "61"], feed.asked


def test_a_school_that_will_not_load_is_reported_not_swallowed():
    """A build that published 110 of 134 schools looks exactly like one
    that published them all. That is the shape of failure this repo
    keeps paying for, so the shortfall comes back to the caller."""
    got, missed = _with_feed(_Feed(bad={"333"}), lambda: cfbdata.fetch_people(
        {"UGA": "61", "BAMA": "333"}))
    assert list(got) == ["UGA"], got
    assert missed == ["BAMA"], missed


def test_an_empty_payload_counts_as_missed_rather_than_as_a_team():
    """A school with nobody on it is not a school with an empty roster;
    it is a school we failed to read, and a zero that reports as success
    is how the page went quiet in the first place."""
    got, missed = _with_feed(
        _Feed(), lambda: cfbdata.fetch_people({"UGA": "61"}))
    assert list(got) == ["UGA"]
    real = cfbdata.parse_team_people
    try:
        cfbdata.parse_team_people = lambda p: []
        got, missed = _with_feed(
            _Feed(), lambda: cfbdata.fetch_people({"UGA": "61"}))
    finally:
        cfbdata.parse_team_people = real
    assert got == {} and missed == ["UGA"], (got, missed)


def test_the_sweep_stops_at_its_budget_and_says_what_it_skipped():
    """`fetch_json` waits 45 seconds before giving up. 134 schools
    against a dark feed is an hour and a half inside a stage that reruns
    every forty-five minutes — one step freezing the other twelve, which
    this site has already lived through once (2026-09-05). Past the
    budget the rest of the league is MISSED, not silently skipped."""
    clock = [0.0]
    feed = _Feed(slow={"61"}, clock=clock)
    got, missed = _with_feed(
        feed,
        lambda: cfbdata.fetch_people({"UGA": "61", "BAMA": "333",
                                      "LSU": "99"}, budget=300.0),
        clock=clock)
    assert list(got) == ["UGA"], got
    assert missed == ["BAMA", "LSU"], missed
    assert feed.asked == ["61"], "it kept asking past the budget"


# --- the payload the page and the search both read ---------------------
def _logs(path, player="Gunner Stockton", team="UGA", n=1):
    conn = hist_db.connect(path)
    hist_db.upsert_player_logs(conn, [{
        "sport": "cfb", "season": rosters_build.season_of(
            "cfb", dt.date.today().isoformat()),
        "period": "2026-09-13", "game_id": f"g{i}", "player": player,
        "team": team, "opponent": "CLEM", "position": "QB", "home": 1,
        "market": "pass_yds", "value": 240.0} for i in range(n)])
    return conn


def test_a_lineman_is_on_the_roster_with_no_games_against_his_name():
    out = rosters.cfb_feed_rosters(
        {"UGA": cfbdata.parse_team_people(PAYLOAD)})
    rows = out["teams"]["UGA"]["players"]
    by = {r["player"]: r for r in rows}
    assert out["player_count"] == 4, out
    assert by["Micah Morris"]["games"] == 0, by["Micah Morris"]


def test_a_man_with_no_carries_is_not_greyed_out_as_unavailable():
    """`from_game_logs` greys a man who has not appeared lately, which it
    can do because appearing is the only way it knows he exists. On a
    published roster nought games is the normal state of a healthy
    guard, and calling it unavailable greys out the offensive line."""
    out = rosters.cfb_feed_rosters(
        {"UGA": cfbdata.parse_team_people(PAYLOAD)})
    rows = out["teams"]["UGA"]["players"]
    assert not any(r["unavailable"] for r in rows), rows
    assert out["teams"]["UGA"]["unavailable"] == 0
    assert all(r["status"] == "" for r in rows), rows


def test_the_games_column_joins_on_the_normalised_name():
    """The two sides are spelled by different hands. Joining on the
    exact string is the mistake `injurylag` shipped the same morning —
    0 of 708 names matched, and the report read as "no edge" rather
    than "no join"."""
    path = os.path.join(_tmp(), "h.db")
    # The suffix, which is the difference the two sides actually have:
    # the roster publishes "Jr.", the box score does not. `normalize_name`
    # bridges that and the punctuation; it does NOT bridge "AJ" against
    # "A.J.", so this claims only what the shared key really buys.
    conn = _logs(path, player="A.J. Terrell", n=3)
    games = rosters.cfb_games_by_player(conn)
    conn.close()
    out = rosters.cfb_feed_rosters(
        {"UGA": cfbdata.parse_team_people(PAYLOAD)}, games)
    by = {r["player"]: r for r in out["teams"]["UGA"]["players"]}
    assert by["A.J. Terrell Jr."]["games"] == 3, by["A.J. Terrell Jr."]
    assert by["A.J. Terrell Jr."]["last_seen"] == "2026-09-13", by


def test_the_ball_carriers_still_lead_the_team_page():
    """Order is the page's answer to "who matters here". A roster sorted
    alphabetically would bury the quarterback among the long snappers."""
    out = rosters.cfb_feed_rosters(
        {"UGA": cfbdata.parse_team_people(PAYLOAD)})
    got = _names(out["teams"]["UGA"]["players"])
    assert got[0] == "Gunner Stockton", got
    assert got.index("A.J. Terrell Jr.") < got.index("Peyton Woodring"), got


# --- build, publish, search --------------------------------------------
def _built(bad=(), out_dir=None):
    """`payload_for` with the network stood in for."""
    out_dir = out_dir or _tmp()
    path = os.path.join(_tmp(), "h.db")
    conn = _logs(path)
    real_teams = cfbdata.fetch_teams
    real_parse = cfbdata.parse_teams
    try:
        cfbdata.fetch_teams = lambda ttl=0: {}
        cfbdata.parse_teams = lambda p: {"UGA": {"id": "61"},
                                         "BAMA": {"id": "333"}}
        blob = _with_feed(_Feed(bad=bad),
                          lambda: rosters_build.payload_for(conn, "cfb"))
    finally:
        cfbdata.fetch_teams = real_teams
        cfbdata.parse_teams = real_parse
        conn.close()
    return blob, path, out_dir


def test_the_published_file_says_it_is_a_roster_and_holds_the_bench():
    blob, _path, _d = _built()
    assert blob["source"] == "roster", blob["source"]
    assert blob["feed"] == "live", blob["feed"]
    assert blob["note"] == "", blob["note"]
    got = _names(blob["teams"]["UGA"]["players"])
    assert "Micah Morris" in got, got


def test_a_partial_league_is_published_WITH_the_shortfall_on_the_page():
    blob, _path, _d = _built(bad={"333"})
    assert "BAMA" not in blob["teams"], list(blob["teams"])
    assert "1 school" in blob["note"] and "BAMA" in blob["note"], blob["note"]


def test_a_dead_feed_falls_back_to_appearances_and_names_ITS_blind_spot():
    """Telling a college reader that pitchers do not bat would be a
    confident explanation of the wrong absence."""
    blob, _path, _d = _built(bad={"61", "333"})
    assert blob["source"] == "appearances", blob["source"]
    assert "lineman" in blob["note"] and "kicker" in blob["note"], blob["note"]
    assert "pitcher" not in blob["note"].lower(), blob["note"]


def test_baseball_still_owns_its_own_blind_spot_sentence():
    """The fallback sentence is per sport, and the older one must not
    have been replaced by the college wording."""
    assert "pitchers don't bat" in rosters_build.BLIND_SPOT["mlb"]


def test_the_search_finds_the_guard_once_the_build_has_published_him():
    """BOTH HALVES, JOINED. The search top-up shipped the same morning
    and bought nothing on its own, because the file it reads was built
    from the population it was meant to complete. This is the assertion
    that would have caught that."""
    blob, db_path, out_dir = _built()
    with open(os.path.join(out_dir, "rosters_cfb.json"), "w",
              encoding="utf-8") as fh:
        json.dump(blob, fh)
    statlogs._ROSTER.clear()
    hits = statlogs.search("cfb", "micah", db_path=db_path, data_dir=out_dir)
    assert _names(hits) == ["Micah Morris"], hits
    assert hits[0]["games"] == 0 and hits[0]["team"] == "UGA", hits[0]
    # And the other school's men came through the same build.
    assert _names(statlogs.search("cfb", "deone", db_path=db_path,
                                  data_dir=out_dir)) == ["Deone Walker"]


def test_the_appearance_built_page_is_what_this_replaced():
    """The before-picture, so the claim is pinned rather than assumed:
    built from logs, the guard and the kicker are not on the team."""
    path = os.path.join(_tmp(), "h.db")
    conn = _logs(path)
    out = rosters.from_game_logs(conn, "cfb")
    conn.close()
    got = _names(out["teams"].get("UGA", {}).get("players", []))
    assert got == ["Gunner Stockton"], got


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
