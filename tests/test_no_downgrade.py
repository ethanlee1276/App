"""A build that could not reach its odds must not overwrite a good board.

2026-09-09, two hours before the season opener. A command I gave Ethan
ran the NFL build directly instead of through the launcher, so it could
not see the box's API key. The board it published had 286 props, none
priced, and no game prices at all — over one that had 173 matched props
and 21 priced games a minute earlier. It printed "Wrote
web/data/recommendations.json" and meant it.

`launch.refresh_nfl` has carried this rule since the prop flicker of
2026-09-01:

    # NEVER DOWNGRADE A BOARD THAT HAS PROPS.

It did not help, because a build run directly goes around the launcher. A
rule that holds on one path holds until somebody takes another path, and
that somebody was me. So it moves to `gate.publish`, the one door every
board of every sport goes through.

THE HARD PART IS NOT REFUSING — it is refusing the right thing. There are
two ways to publish a board with no prices and they are opposite events:

  * the books have not posted, or every cached price is past the show
    ceiling and was honestly refused. That board is TRUE and must be
    publishable; refusing it would leave stale prices on the page looking
    fresh, which is the failure the two ceilings exist to prevent.
  * the build could not reach its odds at all. That board is not a
    finding about the market, it is a report about our own plumbing.

The board records which happened in its own `odds_status`, so the guard
asks rather than guesses.
"""

import json
import os
import pathlib
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gate                                      # noqa: E402


def _priced(n=3, **status):
    st = {"checked": True, "matched": 173, "events": 21, "error": None}
    st.update(status)
    return {"sport": "nfl", "odds_status": st,
            "recommendations": [{"player": f"P{i}", "market": "rec_yds",
                                 "has_market": True, "book": "FanDuel"}
                                for i in range(n)]}


def _unpriced(n=3, **status):
    st = {"checked": True, "matched": 0, "events": 0,
          "error": "No Odds API key."}
    st.update(status)
    return {"sport": "nfl", "odds_status": st,
            "recommendations": [{"player": f"P{i}", "market": "rec_yds",
                                 "has_market": False, "book": ""}
                                for i in range(n)]}


def _tree():
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "web" / "data").mkdir(parents=True)
    return tmp, tmp / "web" / "data" / "recommendations.json"


def _publish(payload, pub):
    return gate.publish(payload, pub, "recommendations.json")


def _full(tmp):
    return tmp / "data" / "built" / "recommendations.json"


def test_a_keyless_build_cannot_overwrite_a_priced_board():
    """THE accident. The good board stays exactly as it was, on both
    copies, and nothing about the refused payload reaches disk."""
    tmp, pub = _tree()
    _publish(_priced(), pub)
    before = _full(tmp).read_text()
    _publish(_unpriced(), pub)
    assert _full(tmp).read_text() == before, "the good board was overwritten"
    kept = json.loads(pub.read_text())
    assert len(kept["recommendations"]) == 3
    assert all(r["has_market"] for r in kept["recommendations"])


def test_it_says_so_where_the_operator_is_already_looking():
    """A refusal nobody sees is the same failure in a quieter coat. It
    prints into the same build output as the "Odds API unavailable"
    warning that precedes it."""
    import contextlib, io
    tmp, pub = _tree()
    _publish(_priced(), pub)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _publish(_unpriced(), pub)
    out = buf.getvalue()
    assert "REFUSED to publish recommendations.json" in out, out
    assert "3 priced row(s)" in out, out
    assert "The existing board is KEPT" in out, out


def test_an_honestly_unpriced_board_still_publishes():
    """THE case that makes the guard safe. The books have not posted, or
    every cached price was past the show ceiling and honestly refused —
    the pull SUCCEEDED and found nothing to price. Refusing that would
    leave stale prices on the page looking fresh, which is exactly what
    the two ceilings exist to prevent."""
    tmp, pub = _tree()
    _publish(_priced(), pub)
    honest = _unpriced(error=None, matched=17, events=16)
    _publish(honest, pub)
    assert len(json.loads(_full(tmp).read_text())["recommendations"]) == 3
    assert not any(r["has_market"] for r in
                   json.loads(_full(tmp).read_text())["recommendations"])


def test_a_board_that_never_checked_its_odds_is_not_judged():
    """A board built with no odds pull asked for at all — the free
    schedule-only build — has nothing to report and is not a downgrade."""
    tmp, pub = _tree()
    _publish(_priced(), pub)
    _publish(_unpriced(checked=False), pub)
    assert not any(r["has_market"] for r in
                   json.loads(_full(tmp).read_text())["recommendations"])


def test_the_first_publish_is_never_refused():
    """Nothing to protect yet, and a guard that blocked a cold start
    would be a guard that stops the system existing."""
    tmp, pub = _tree()
    _publish(_unpriced(), pub)
    assert _full(tmp).is_file()


def test_a_board_that_was_already_unpriced_is_replaceable():
    """The guard protects PRICES, not boards. Two unpriced boards in a
    row is an ordinary week before the books post."""
    tmp, pub = _tree()
    _publish(_unpriced(), pub)
    _publish(_unpriced(n=5), pub)
    assert len(json.loads(_full(tmp).read_text())["recommendations"]) == 5


def test_a_board_that_gains_prices_is_never_blocked():
    tmp, pub = _tree()
    _publish(_unpriced(), pub)
    _publish(_priced(n=9), pub)
    assert len(json.loads(_full(tmp).read_text())["recommendations"]) == 9


def test_priced_counts_the_price_not_the_row():
    """A quiet slate publishes few picks and a finished one publishes
    none, so counting ROWS would refuse ordinary days. What cannot be
    ordinary is material on the board with none of it priced."""
    assert gate.priced_rows(_priced(4), "recommendations.json") == 4
    assert gate.priced_rows(_unpriced(4), "recommendations.json") == 0
    # A row naming a book counts even without the has_market stamp — the
    # likelihood board's game rows carry the book and not the flag.
    p = {"most_likely": [{"player": "MIN ML", "market": "moneyline",
                          "book": "FanDuel"}]}
    assert gate.priced_rows(p, "recommendations.json") == 1


def test_the_launcher_rule_is_named_where_it_now_lives():
    """It existed on one path and was skipped. If the comment ever loses
    the link back, the next person re-learns this at the same cost."""
    import inspect
    src = inspect.getsource(gate.would_downgrade)
    assert "NEVER DOWNGRADE A BOARD THAT HAS PROPS" in src
    assert "goes around the launcher" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
