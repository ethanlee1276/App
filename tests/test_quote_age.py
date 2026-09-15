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

AND THEN THE AGE GOT A CEILING (2026-09-08). Reporting a three-day-old
quote and using it anyway is what this file first pinned; four days
later the same class of report came back for the third time and Ethan
named the harm outright — "fake and false picks that can hurt us". A
payload past `oddsapi.MAX_PROP_PRICE_AGE` is refused rather than dated:
the game keeps no player quotes, the note says how old the payload was
and which knob widens the ceiling, and `player_priced_at` dates only
what was actually used. The "oldest quote" reading below still covers
the band it was written for — older than the TTL, younger than the
ceiling — which on the touchpoint cadence is the ordinary afternoon.

AND THEN THE CEILING SPLIT IN TWO (same day, hours later). One ceiling
at six hours refused every price the droplet had not re-pulled inside
six hours, which on a box whose pull runs every forty-five minutes but
whose network is not always up meant a board with almost nothing on it —
Ethan: "We have barely any moneylines show and barley and touchdowns
shown." Six hours is now the FRESHNESS bar, above which a price is not
fresh enough to RECOMMEND; forty-eight hours is the SHOW ceiling, above
which it is not worth showing at all. Between them the price goes on the
board carrying its age, because the last paid pull's real number beats
an empty shelf and beats a proxy.
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


def test_a_days_old_payload_is_refused_not_reported():
    """The pin this file shipped with said a three-day-old payload is used
    and dated. It is refused now (tests/test_stale_price_ceiling.py has
    the measurement): nothing was used, so nothing is dated, and the
    note says what happened and how old the payload was.

    Three days is past the SHOW ceiling too, so this case did not move
    when the ceiling split in two — only the knob it names did."""
    scorers, lines, note, age = _pull(3 * 86400.0)
    assert scorers == {} and lines == {}, (scorers, lines)
    assert age is None, "a refused payload must not date the board"
    assert "kept NO player quotes" in note and "72.0h old" in note, note
    assert "QB_MAX_PROP_PRICE_SHOW_AGE" in note, note
    assert "oldest quote on this board" not in note, note


def test_the_freshness_bar_marks_and_the_show_ceiling_refuses():
    """The single six-hour ceiling this test was written for became two
    (2026-09-08). Six hours is where a price stops being FRESH enough to
    recommend; forty-eight is where it stops being worth SHOWING at all.
    Between them the last paid pull's real price goes on the board with
    a warning, because refusing it emptied the touchdown shelf on the
    eve of Week 1 — Ethan: "barely and touchdowns shown"."""
    import engine.sources.oddsapi as O
    # Inside both: used, dated, no warning about it.
    _s, _l, note, age = _pull(6 * 3600.0 - 60.0)
    assert age == 6 * 3600.0 - 60.0, age
    assert "oldest quote on this board" in note, note
    assert "kept NO player quotes" not in note, note
    assert "shown and marked" not in note, note
    # Past the freshness bar, inside the show ceiling: KEPT and marked.
    _s, _l, note, age = _pull(6 * 3600.0 + 60.0)
    assert age == 6 * 3600.0 + 60.0, "a showable payload must still date the board"
    assert "shown and marked, not recommended" in note, note
    assert "kept NO player quotes" not in note, \
        "the footer calls a quote on the board a quote it never kept"
    # Past the show ceiling: refused, and nothing dates the board.
    _s, _l, note, age = _pull(O.MAX_PROP_PRICE_SHOW_AGE + 60.0)
    assert age is None, age
    assert "kept NO player quotes" in note, note


def test_the_two_ceilings_are_not_the_same_number():
    """A show ceiling equal to the freshness bar is the regression this
    split undid: every price past six hours vanishes instead of being
    labelled."""
    import engine.sources.oddsapi as O
    assert O.MAX_PROP_PRICE_SHOW_AGE > O.MAX_PROP_PRICE_AGE, \
        (O.MAX_PROP_PRICE_SHOW_AGE, O.MAX_PROP_PRICE_AGE)


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
