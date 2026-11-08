"""A finished game's box score is read again at most every half hour, and a
copy taken while it was played is never kept (engine/boxsettle.summary_final,
_final_summary, FINAL_SUMMARY_TTL_S; ingest_for_open).

The summary's cache lives four seconds, for the live board, so every
five-minute settle pass downloaded every finished football game's summary
again for as long as a prop on it waited (often until the next morning's
official file): a college Saturday's finished games, every pass, all
evening, and twice as many once every conference's games reached the board.
What these hold:

  * a summary says its game is over when ESPN marks it completed or its
    state "post"; one in play, or one that cannot be read, does not;
  * a copy that says the game is over is taken for up to half an hour; any
    other is replaced by a fresh one; a fetcher without a ``ttl`` is asked
    plainly;
  * the box-score ingest reads through that rule, and the real fetcher
    takes a ``ttl``.

Run directly: `python3 tests/test_a_finished_games_box_score_is_reread_half_hourly.py`
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B                                  # noqa: E402


def _summary(state="post", completed=True):
    return {"header": {"competitions": [{"status": {"type": {"state": state,
                                                             "completed": completed}}}]},
            "boxscore": {"players": []}}


def test_a_summary_says_its_game_is_over_only_when_espn_does():
    assert B.summary_final(_summary("post", True))
    assert B.summary_final(_summary("post", False)), "a post state is over"
    assert B.summary_final(_summary("in", True)), "completed is over"
    assert not B.summary_final(_summary("in", False))
    assert not B.summary_final(_summary("pre", False))
    for junk in (None, {}, {"header": None}, {"header": {"competitions": []}},
                 {"header": {"competitions": [None]}}, "text", []):
        assert not B.summary_final(junk), junk


def test_a_final_copy_is_kept_half_an_hour_and_any_other_is_replaced():
    calls = []

    def fetch(league, eid, ttl=4):
        calls.append(ttl)
        return final if ttl == B.FINAL_SUMMARY_TTL_S else fresh

    final, fresh = _summary(), _summary()
    assert B._final_summary(fetch, "cfb", "401") is final and calls == [1800]
    calls.clear()
    final, fresh = _summary("in", False), _summary()
    got = B._final_summary(fetch, "cfb", "401")
    assert got is fresh and calls == [1800, 0], calls
    assert B.FINAL_SUMMARY_TTL_S == 1800


def test_a_fetcher_without_a_ttl_is_asked_plainly():
    calls = []

    def plain(league, eid):
        calls.append((league, eid))
        return _summary("in", False)
    assert B.summary_final(B._final_summary(plain, "nfl", "9")) is False
    assert calls == [("nfl", "9")]


def test_the_ingest_reads_through_the_rule_and_the_real_fetcher_takes_a_ttl():
    src = inspect.getsource(B.ingest_for_open)
    assert "_final_summary(fetch_summary, league, eid)" in src
    assert "payload = fetch_summary(league, eid)" not in src
    from engine.sources import espnplays
    assert "ttl" in inspect.signature(espnplays.fetch_summary).parameters


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
