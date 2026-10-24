"""Alerts that fire on a condition, not a schedule (IDEAS #6).

The Alerts page has always been a DIGEST — everything that changed on
everything — and it says so rather than pretending to be a push service.
That is the right default and it is not what somebody means by "tell me
when Chase's line moves". They mean: out of all of that, these are mine.

THREE SHAPES AND NO QUERY BUILDER, which the roadmap insisted on: a
player, a team, or a number. They are not chosen for tidiness, and that
is the first thing pinned here — each one is answerable off a field
`engine/feed.py` already publishes, so a watch never re-derives anything
and can never disagree with the feed it filters.

THE EDGE SHAPE IS THE ONE WITH A TRAP IN IT. An `edge_died` event is the
moment an edge STOPPED existing; firing "6% edge" on it would be a
notification about the opposite of what was asked for. Two tests hold
that line.

MATCHING IS STATELESS. A watch is a filter over the published feed, not
a subscription that has to be delivered, so nothing fired is stored: a
watch added at noon applies to the whole window immediately, and one
deleted stops mattering the same second.

Run directly: `python3 tests/test_alerts.py`
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import alerts as AL                                # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


EVENTS = [
    {"id": "a1", "ts": "2026-08-27T11:59:00", "sport": "nfl",
     "kind": "edge_appeared", "player": "Ja'Marr Chase", "team": "CIN",
     "opponent": "PIT", "label": "Receiving Yards", "edge": 0.071},
    {"id": "a2", "ts": "2026-08-27T11:58:00", "sport": "nfl",
     "kind": "line_move", "player": "Chase Brown", "team": "CIN",
     "opponent": "PIT", "label": "Rushing Yards", "edge": 0.021},
    {"id": "a3", "ts": "2026-08-27T11:57:00", "sport": "mlb",
     "kind": "edge_died", "player": "Aaron Judge", "team": "NYY",
     "opponent": "BOS", "label": "Total Bases", "edge": 0.20},
    {"id": "a4", "ts": "2026-08-27T11:56:00", "sport": "nfl",
     "kind": "released", "n": 2,
     "players": ["Puka Nacua (Receiving Yards)", "Kyren Williams (Rush Yds)"]},
    {"id": "a5", "ts": "2026-08-27T11:55:00", "sport": "nfl",
     "kind": "stale_line", "player": "Joe Burrow", "team": "CIN",
     "opponent": "PIT", "gap": 0.084},
]


def _w(kind, value):
    k, v = AL.normalize(kind, value)
    return {"kind": k, "value": v}


# --- the three shapes ------------------------------------------------------

def test_there_are_exactly_three_shapes():
    """The brief: "keep it to three shapes rather than building a query
    builder nobody uses"."""
    assert AL.KINDS == ("player", "team", "edge")


def test_a_player_watch_reads_a_name_the_way_people_type_it():
    for typed in ("Ja'Marr Chase", "jamarr chase", "JaMarr  Chase",
                  "ja marr chase"):
        assert AL.matches(EVENTS[0], "player", typed), typed
    assert not AL.matches(EVENTS[0], "player", "Chase Brown")


def test_a_team_watch_catches_both_sides_of_the_game():
    """"Anything in the Bengals game" includes the receiver playing
    against them — a watch that only read `team` would miss half of it."""
    assert AL.matches(EVENTS[0], "team", "CIN")
    assert AL.matches(EVENTS[0], "team", "PIT")
    assert not AL.matches(EVENTS[0], "team", "NYY")


def test_a_release_event_reaches_the_player_it_is_about():
    """One row summarises a whole lineup drop. His prop finally getting a
    price is the single most useful alert of the day, and it is the one
    that would not have fired."""
    assert AL.matches(EVENTS[3], "player", "Puka Nacua")
    assert AL.matches(EVENTS[3], "player", "kyren williams")
    assert not AL.matches(EVENTS[3], "player", "Ja'Marr Chase")


def test_the_edge_shape_reads_percent_because_that_is_what_people_say():
    """The board carries fractions; a person says six percent."""
    assert AL.matches(EVENTS[0], "edge", "7")
    assert not AL.matches(EVENTS[0], "edge", "8")
    assert AL.matches(EVENTS[4], "edge", "8"), "a stale quote's gap is an edge"


def test_the_edge_shape_never_fires_on_an_edge_that_just_died():
    """`edge_died` is the moment one STOPPED existing. Judge's row carries
    a 20% edge field and firing on it would be a notification about the
    opposite of what was asked for."""
    assert EVENTS[2]["edge"] == 0.20, "fixture no longer tests the trap"
    assert not AL.matches(EVENTS[2], "edge", "6")


def test_an_event_kind_with_no_live_edge_is_not_guessed_at():
    assert not AL.matches(EVENTS[3], "edge", "1")   # released: no edge field


# --- refusing what could never match ---------------------------------------

def test_a_shape_that_is_not_one_of_the_three_is_refused():
    for kind in ("vibes", "", None, "sport"):
        assert AL.normalize(kind, "x") is None, kind


def test_an_edge_outside_the_rails_is_refused_rather_than_stored():
    """Below the floor it matches everything, which is the digest again;
    above the ceiling it matches nothing, forever, silently."""
    assert AL.normalize("edge", "0.1") is None
    assert AL.normalize("edge", "90") is None
    assert AL.normalize("edge", "6.5%") == ("edge", "6.5")


def test_an_empty_or_enormous_value_is_refused():
    assert AL.normalize("player", "   ") is None
    assert AL.normalize("player", "!!!") is None, "punctuation is not a name"
    assert AL.normalize("player", "x" * 200) is None


def test_a_watch_keeps_the_spelling_the_reader_typed():
    """The chip shows it back to them; folding at rest would print
    "jamarrchase" on their own screen."""
    assert AL.normalize("player", "Ja'Marr Chase") == ("player", "Ja'Marr Chase")
    assert AL.normalize("team", " cin ") == ("team", "CIN")


# --- the list --------------------------------------------------------------

def test_fired_returns_only_mine_newest_first_and_says_which_watch():
    got = AL.fired(EVENTS, [_w("player", "jamarr chase"), _w("team", "CIN"),
                            _w("edge", "8")])
    assert [e["id"] for e in got] == ["a1", "a2", "a5"]
    assert got[0]["why"] == ["anything on Ja'Marr Chase"] or \
        "anything on jamarr chase" in got[0]["why"]
    assert len(got[0]["why"]) == 2, "an event caught twice names both watches"
    assert len(got[2]["why"]) == 2


def test_an_event_matched_by_two_watches_appears_once():
    got = AL.fired(EVENTS, [_w("player", "Ja'Marr Chase"), _w("team", "CIN")])
    assert [e["id"] for e in got].count("a1") == 1


def test_no_watches_is_no_alerts_rather_than_all_of_them():
    assert AL.fired(EVENTS, []) == []


def test_since_hides_what_has_already_been_read():
    ws = [_w("team", "CIN")]
    assert len(AL.fired(EVENTS, ws)) == 3
    assert len(AL.fired(EVENTS, ws, since="2026-08-27T11:58:00")) == 1
    assert AL.fired(EVENTS, ws, since="2026-08-27T12:00:00") == []


def test_the_seen_stamp_comes_off_the_events_not_a_clock():
    """A server a second ahead of the build would otherwise mark an event
    seen that nobody was ever shown."""
    assert AL.newest_ts(EVENTS) == "2026-08-27T11:59:00"
    assert AL.newest_ts([]) == ""


# --- storage ---------------------------------------------------------------

def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users (id, email) VALUES (1, 'e@x.com')")
    AL.ensure_tables(conn)
    return conn


def test_a_watch_round_trips_and_deletes():
    c = _db()
    code, out = AL.add_watch(c, 1, "player", "Ja'Marr Chase")
    assert code == 200 and len(out["watches"]) == 1
    wid = out["watches"][0]["id"]
    assert out["watches"][0]["label"] == "anything on Ja'Marr Chase"
    code, out = AL.remove_watch(c, 1, wid)
    assert code == 200 and out["watches"] == []


def test_the_same_watch_twice_is_one_watch():
    c = _db()
    AL.add_watch(c, 1, "team", "cin")
    _, out = AL.add_watch(c, 1, "team", "CIN")
    assert len(out["watches"]) == 1


def test_a_refused_shape_never_reaches_the_table():
    c = _db()
    code, out = AL.add_watch(c, 1, "vibes", "good ones")
    assert code == 400 and "three shapes" in out["error"]
    assert AL.list_watches(c, 1) == []


def test_the_list_has_a_ceiling():
    c = _db()
    for i in range(AL.MAX_WATCHES):
        AL.add_watch(c, 1, "player", f"Player {i}")
    code, out = AL.add_watch(c, 1, "player", "One More")
    assert code == 400 and "limit" in out["error"]
    assert len(AL.list_watches(c, 1)) == AL.MAX_WATCHES


def test_the_seen_stamp_only_ever_moves_forward():
    """A stale tab posting an old stamp would otherwise un-read
    everything that arrived while it sat there."""
    c = _db()
    AL.mark_seen(c, 1, "2026-08-27T11:59:00")
    AL.mark_seen(c, 1, "2026-08-27T09:00:00")
    assert AL.seen_ts(c, 1) == "2026-08-27T11:59:00"
    AL.mark_seen(c, 1, "")
    assert AL.seen_ts(c, 1) == "2026-08-27T11:59:00"


def test_one_readers_watches_are_their_own():
    c = _db()
    c.execute("INSERT INTO users (id, email) VALUES (2, 'other@x.com')")
    AL.add_watch(c, 1, "team", "CIN")
    AL.add_watch(c, 2, "team", "PIT")
    assert [w["value"] for w in AL.list_watches(c, 1)] == ["CIN"]
    # And one cannot delete the other's.
    other = AL.list_watches(c, 2)[0]["id"]
    AL.remove_watch(c, 1, other)
    assert len(AL.list_watches(c, 2)) == 1


# --- the wiring ------------------------------------------------------------

def test_the_feed_carries_the_team_a_watch_needs():
    """The team shape is only answerable because the feed publishes the
    field. It did not before this — the digest held the row's team and
    dropped it on the way into the event."""
    src = _read("engine", "feed.py")
    i = src.index("def digest(")
    assert '"team":' in src[i:i + 900]
    j = src.index("def base(kind, c, key")
    assert '"team": c.get("team"' in src[j:j + 600]


def test_an_alert_is_only_ever_a_filter_over_a_board_you_may_read():
    """Every feed entry names a pick, so feed.json is a paid file. An
    alert must not become the door around that."""
    src = _read("server.py")
    i = src.index("def _alerts_feed(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert "_entitled" in body and "board_source" in body
    assert "return []" in body, "outside the wall this must answer nothing"


def test_the_page_still_says_it_is_not_a_push_service():
    """It said so when it was only a digest, and a watch does not change
    the fact — Web Push needs crypto the standard library does not have,
    and that refusal is written up rather than quietly worked around."""
    app = _read("web", "js", "app.js")
    i = app.index("async function renderWatchZone(")
    body = app[i:app.index("\n/* THE FEED LEADS", i)]
    assert "not a push notification" in body
    assert "lock screen" in body


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
