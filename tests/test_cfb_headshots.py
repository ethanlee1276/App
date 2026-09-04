"""College players wore a drawn helmet while their photo was already arriving.

Ethan, 2026-09-04: "can we make sure we get the head shots for college
football for the players".

NOTHING NEEDED BUILDING ON THE PAGE. `visuals.playerAvatar` has always
taken `opts.headshot`, drawn the team helmet when there is none, and —
on an image error — removed the photo so the helmet comes back. Every
college card already passed `headshot: r.headshot`. The field was simply
never set: `engine/cfb/props` built each `Prop` without it and the
dataclass default is "".

AND THE FEED WAS ALREADY BEING FETCHED. `cfbdata.fetch_team_roster`
pulls ESPN's roster once per slate team on a day's cache — it is how a
week-one transfer gets placed at all — and `parse_team_roster` kept the
POSITION and discarded every other field on the athlete, portrait
included. So this costs one dictionary, not one request.

THE MAP IS BUILT WHERE THE SLATE LIST ALREADY IS, inside `build_props`,
beside the `rosters_for` call that needs the same team identifiers.
Threading a `headshots=` argument down from `cfb_build` was the first
cut and it was wrong: it rebuilt the team list from keys I had guessed
at (`home_id`/`away_id`, which do not exist), and two places deciding
which teams are playing is one place too many.

COVERAGE IS PARTIAL AND SAYING SO IS THE POINT. Walk-ons and true
freshmen often have no portrait, and NFL has the same gap. A feed that
stops publishing faces and a join that stops matching names look
identical on the page — every card in a helmet — and want opposite
fixes, so the census carries both numbers and the build prints them.

Run directly: `python3 tests/test_cfb_headshots.py`
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import cfbdata                            # noqa: E402
from engine.sources.cfbdata import (parse_team_headshots,     # noqa: E402
                                    parse_team_roster)

FACE1 = "https://a.espncdn.com/i/headshots/college-football/players/full/1.png"
FACE2 = "https://a.espncdn.com/i/headshots/college-football/players/full/2.png"


def _payload():
    """ESPN's roster shape, as `parse_team_roster` was written against —
    athletes grouped, the real position on each item, and the portrait in
    BOTH the shapes the site API publishes."""
    return {"athletes": [{"position": "offense", "items": [
        {"fullName": "Alpha Back", "position": {"abbreviation": "RB"},
         "headshot": {"href": FACE1, "alt": "Alpha Back"}},
        {"fullName": "Beta Wide", "position": {"abbreviation": "WR"},
         "headshot": FACE2},
        {"fullName": "Gamma Walkon", "position": {"abbreviation": "TE"}},
        {"fullName": "Delta Null", "position": {"abbreviation": "TE"},
         "headshot": None},
        {"fullName": "Eps NoHref", "position": {"abbreviation": "TE"},
         "headshot": {"alt": "no href here"}},
        {"fullName": "Zeta Relative", "position": {"abbreviation": "TE"},
         "headshot": "/relative/path.png"},
    ]}]}


class _Stub:
    """Swap the one network call for a payload, and put it back."""

    def __init__(self, fn):
        self.fn, self.real = fn, cfbdata.fetch_team_roster

    def __enter__(self):
        cfbdata.fetch_team_roster = self.fn
        return self

    def __exit__(self, *_):
        cfbdata.fetch_team_roster = self.real


# --- the parse ---------------------------------------------------------------
def test_both_shapes_espn_publishes_are_read():
    got = parse_team_headshots(_payload())
    assert got.get("alpha back") == FACE1, "the {href: ...} shape was missed"
    assert got.get("beta wide") == FACE2, "the bare-string shape was missed"


def test_a_player_without_a_portrait_gets_no_entry_rather_than_a_guess():
    """THE FAILURE MODE THAT MATTERS. `playerAvatar` draws the team
    helmet for a row with no headshot, so an ABSENT face is a finished
    design. A fabricated or relative URL is a broken image on a card."""
    got = parse_team_headshots(_payload())
    for who in ("gamma walkon", "delta null", "eps nohref", "zeta relative"):
        assert who not in got, f"{who} was given a portrait it does not have"
    assert len(got) == 2, got


def test_the_position_read_is_unchanged():
    """`parse_team_roster` is load-bearing for the week-one transfer
    lookup. Sharing its walk must not change a single answer it gives."""
    got = parse_team_roster(_payload())
    assert got == {"alpha back": "RB", "beta wide": "WR",
                   "gamma walkon": "TE", "delta null": "TE",
                   "eps nohref": "TE", "zeta relative": "TE"}, got


def test_the_two_readers_walk_the_same_athletes():
    """One extracted generator, not two copies of the loop. Two readers
    of one feed that disagree about which athletes exist is a bug waiting
    for a payload change — the same mistake the odds slate's day filter
    made when its rule was copied instead of shared."""
    import inspect
    src = inspect.getsource(cfbdata)
    assert src.count("def _athletes(") == 1
    for fn in ("parse_team_roster", "parse_team_headshots"):
        body = inspect.getsource(getattr(cfbdata, fn))
        assert "_athletes(payload)" in body, f"{fn} carries its own walk"


# --- the fetch ---------------------------------------------------------------
def test_a_roster_that_will_not_load_costs_faces_not_the_board():
    """Never fatal. A team ESPN will not serve contributes nothing and
    those players fall back to the helmet — which is what every college
    card shows today, so the floor is the status quo."""
    def boom(team_id, ttl=0):
        raise RuntimeError("ESPN unavailable")
    with _Stub(boom):
        assert cfbdata.fetch_headshots(["espn:333", "espn:61"]) == {}


def test_the_same_name_on_two_rosters_does_not_flap():
    """`rosters_for` DROPS an ambiguous name, because putting a back on
    the wrong side of a spread changes a bet. A portrait does not, so
    this keeps the first rather than dropping the face of everyone who
    shares a name with a player at another school."""
    with _Stub(lambda team_id, ttl=0: _payload()):
        a = cfbdata.fetch_headshots(["espn:1", "espn:2"])
        b = cfbdata.fetch_headshots(["espn:2", "espn:1"])
    assert a == b == {"alpha back": FACE1, "beta wide": FACE2}, (a, b)


def test_no_teams_asks_for_nothing():
    def explode(team_id, ttl=0):
        raise AssertionError("fetched a roster for an empty slate")
    with _Stub(explode):
        assert cfbdata.fetch_headshots([]) == {}
        assert cfbdata.fetch_headshots([None, ""]) == {}


# --- it reaches a prop -------------------------------------------------------
def _db():
    """A slate's worth of college logs, enough for one real prop."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE player_game_logs (
        sport TEXT, season INT, period TEXT, game_id TEXT, player TEXT,
        team TEXT, opponent TEXT, position TEXT, market TEXT, value REAL,
        home INT)""")
    rows = []
    for i in range(8):
        for market, val in (("rush_yds", 85.0), ("carries", 17.0)):
            rows.append(("cfb", 2025, f"2025-10-{i + 1:02d}", f"g{i}",
                         "Alpha Back", "UGA", "BAMA", "RB", market, val, 1))
    conn.executemany("INSERT INTO player_game_logs VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_the_face_lands_on_a_real_prop():
    """END TO END through the actual builder, not a source read. The
    field is keyed on the same normalised name the usage and roster
    lookups already join on — if that key ever drifts, every card silently
    reverts to a helmet and nothing raises."""
    from engine.cfb import props as cfbprops
    conn = _db()
    games = [{"home": "UGA", "away": "BAMA", "game_id": "g99"}]
    census: dict = {}
    with _Stub(lambda team_id, ttl=0: _payload()):
        built = cfbprops.build_props(conn, games, 2025, census=census)
    mine = [p for p in built if p.player == "Alpha Back"]
    assert mine, f"the fixture built no prop for him: census={census}"
    assert mine[0].headshot == FACE1, \
        f"the prop carries no face: {mine[0].headshot!r}"
    assert census.get("headshots") == len(mine), census
    assert census.get("headshot_pool") == 2, census


def test_the_published_row_carries_it():
    """`pipeline._rec_to_dict` is the shared step both football boards
    publish through, so college inherits the field NFL already had."""
    src = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    assert '"headshot": prop.headshot' in src


def test_the_build_prints_what_the_join_found():
    """Two numbers, because a dead FEED and a dead JOIN look identical on
    the page and want opposite fixes."""
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert "Headshots:" in src
    assert "headshot_pool" in src


def test_the_page_needs_no_college_branch():
    """It already fell back to the helmet and already read the field."""
    vis = open(os.path.join(ROOT, "web", "js", "visuals.js"),
               encoding="utf-8").read()
    assert "if (opts.headshot)" in vis
    assert "headshot: null" in vis, "the no-face fallback path is gone"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
