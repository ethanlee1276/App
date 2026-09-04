"""How old is the price beside the row.

`oddsapi._request` under `cache_only` "serves the cached copy at ANY age
and never touches the network". That is the right trade — the last paid
pull's real prices beat proxies, and college player markets cost five
credits a game against a day's allowance that often cannot buy one full
pull. What it costs is the ability to tell a price that is WRONG from a
price that is OLD, and the board's `priced_at` does not close the gap:
it dates the last time college SPENT, while `attach_player_quotes` buys
at most `PLAYER_EVENT_CAP` games a cycle and every other game keeps
whatever the last pull that reached it left on disk.

Ethan, 2026-09-04: "I'm noticing lines for CFB that's wrong. Like for
example, Cam Edward's on the Michigan state Spartans has a -300 line too
score a touchdown but on our site we are showing -155."
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, ROOT)

from engine.sources import fetch as _fetch                   # noqa: E402
from engine.sources import oddsapi as oa                     # noqa: E402


# --- the reader -------------------------------------------------------------
def test_the_name_is_the_one_the_fetcher_writes():
    """Re-deriving the digest at the call site would work until the day
    one of the two changed."""
    import inspect
    src = inspect.getsource(oa.fetch_event_odds)
    assert "event_cache_name(" in src, \
        "fetch_event_odds builds its own filename again"
    assert "hashlib.md5" not in src, "the digest is back in two places"


def test_the_name_carries_the_sport_and_the_request():
    a = oa.event_cache_name("e1", ["player_anytime_td"], None, "cfb")
    b = oa.event_cache_name("e1", ["player_anytime_td", "player_rush_yds"],
                            None, "cfb")
    c = oa.event_cache_name("e1", ["player_anytime_td"], None, "nfl")
    assert a.startswith("odds_event_cfb_e1_") and a.endswith(".json")
    assert c.startswith("odds_event_nfl_e1_")
    assert a != b, "two different market lists share one file again"


def test_the_name_does_not_depend_on_market_order():
    a = oa.event_cache_name("e1", ["a", "b"], None, "cfb")
    b = oa.event_cache_name("e1", ["b", "a"], None, "cfb")
    assert a == b


def test_nothing_cached_is_not_zero_seconds_old():
    """An unpriceable game and a stale one are different facts and must
    not share an answer."""
    assert oa.event_cache_age("no-such-event-id", ["player_anytime_td"],
                              sport="cfb") is None


def test_the_age_is_the_file_age(tmp=None):
    name = oa.event_cache_name("agetest", ["player_anytime_td"], None, "cfb")
    path = _fetch.CACHE_DIR / name
    _fetch.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bookmakers": []}))
    try:
        import os
        old = time.time() - 7200.0
        os.utime(path, (old, old))
        got = oa.event_cache_age("agetest", ["player_anytime_td"],
                                 sport="cfb", now=old + 7200.0)
        assert abs(got - 7200.0) < 2.0, got
    finally:
        path.unlink(missing_ok=True)


# --- the board --------------------------------------------------------------
def _slate():
    games = [{"game_id": "g0", "home": "H", "away": "A",
              "kickoff": "2026-08-29T20:00Z"}]
    priced = {"g0": {"event_id": "e0", "spread": (-7.0, -110, -110),
                     "total": (55.5, -110, -110)}}
    return games, priced


def _pull(age, cache_only=True):
    """Run the college quote pull with a stubbed fetch and a stubbed age."""
    import cfb_build as B
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl",
                   cache_only=False):
        return {"bookmakers": []}, oa.Quota()

    real_fetch, real_age = oa.fetch_event_odds, oa.event_cache_age
    oa.fetch_event_odds = fake_fetch
    oa.event_cache_age = lambda *a, **k: age
    try:
        games, priced = _slate()
        return B.attach_player_quotes(games, priced, cache_only=cache_only,
                                      now=now, cap=4)
    finally:
        oa.fetch_event_odds, oa.event_cache_age = real_fetch, real_age


def test_a_days_old_payload_says_so_on_the_board():
    _s, _l, note, age = _pull(3 * 86400.0)
    assert age == 3 * 86400.0
    assert "oldest quote on this board" in note, note
    assert "3.0 day(s) old" in note, note


def test_hours_are_reported_in_hours():
    _s, _l, note, age = _pull(5 * 3600.0)
    assert "5.0 hour(s) old" in note, note
    assert "day(s)" not in note, note


def test_an_ordinary_fresh_cycle_says_nothing_extra():
    """Under the TTL is the working state, not a warning. A line printed
    on every board is a line a reader learns to skip."""
    import cfb_build as B
    _s, _l, note, age = _pull(B.STALE_QUOTE_S - 60.0)
    assert age == B.STALE_QUOTE_S - 60.0
    assert "oldest quote" not in note, note


def test_nothing_on_disk_reports_no_age_rather_than_zero():
    _s, _l, note, age = _pull(None)
    assert age is None
    assert "oldest quote" not in note, note


def test_a_paid_pull_is_zero_seconds_old_whatever_was_there_before():
    """`_request` only serves the cache under cache_only or inside the
    30-minute TTL. A live pull that rewrote the file must not be dated by
    the payload it replaced."""
    _s, _l, note, age = _pull(9 * 86400.0, cache_only=False)
    assert age == 0.0, age
    assert "oldest quote" not in note, note


def test_a_paid_pull_served_from_inside_the_ttl_keeps_its_real_age():
    _s, _l, note, age = _pull(600.0, cache_only=False)
    assert age == 600.0, age


# --- what the page draws ----------------------------------------------------
def _app():
    return (Path(ROOT) / "web" / "js" / "app.js").read_text()


def test_the_page_draws_the_player_clock():
    src = _app()
    assert "os.player_priced_at" in src, \
        "the board publishes the stamp and the page ignores it"
    i = src.index("os.player_priced_at")
    seg = src[i:i + 200]
    assert "player prices" in seg, seg[:120]
    # OLDER, not newer: this is the mirror image of the game-lines clock
    # beside it, and getting the sign wrong would hide exactly the case
    # it exists for.
    assert "<" in seg.split("bits.push")[0], seg[:120]


def test_the_build_publishes_the_stamp():
    src = (Path(ROOT) / "cfb_build.py").read_text()
    needle = 'out["odds_status"]["player_priced_at"]'
    assert needle in src, "the build stopped publishing the stamp"
    i = src.index(needle)
    assert "quotes_age" in src[i - 200:i + 200], \
        "the stamp is no longer computed from the measured age"


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
