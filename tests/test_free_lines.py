"""The budget gates the PULL, not the read.

2026-09-09, the night of the season opener. The NFL board carried
18-hour-old per-event game prices while `odds_board_nfl_lines.json` sat
in the cache twelve minutes old, unread. `--ml-doctor` showed both
numbers side by side: `from=event age=18.3h` on every moneyline row, and
`pull ... 0.2 h old` above it.

The reason is in `launch.refresh_nfl`. `--board-odds` — the three-credit
whole-slate refresh — is reachable only when the expensive prop pull was
already declined, AND only when the pacer authorises the spend. On that
cycle it did not, so the build ran without it and never looked at the
payload something else had already paid for.

"You may not SPEND three credits" and "you may not READ the file we
already bought" had become the same sentence. They are not the same
sentence. Reading a file costs nothing.

So the pass runs either way — cache-only when the spend was declined —
and the thing that makes that safe is the freshness rule: this pass runs
AFTER the event pull, so it must never replace a price with an older one.
A refresh that makes a number older is not a refresh.
"""

import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import Game, Weather                      # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402


class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def _game(price_age_s=None):
    g = Game(home="MIN", away="GB", weather=Weather(),
             date="2026-09-13", kickoff="20:25")
    if price_age_s is not None:
        g.price_age_s = price_age_s
        g.home_ml, g.away_ml = -220, 200
        g.priced_from = "event"
    return g


def _ev():
    return {"home_team": "Minnesota Vikings", "away_team": "Green Bay Packers",
            "commence_time": "2026-09-13T20:25:00Z",
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": "Minnesota Vikings", "price": -118},
                                {"name": "Green Bay Packers", "price": 102}]}]}]}


def _apply(game, payload_age_s=600):
    slate = _Slate([game])
    tmp = pathlib.Path(tempfile.mkdtemp())
    real = O.CACHE_DIR
    O.CACHE_DIR = tmp
    path = tmp / "odds_board_nfl_lines.json"
    path.write_text(json.dumps([_ev()]))
    old = time.time() - payload_age_s
    os.utime(path, (old, old))
    try:
        res = O.apply_board_lines_to_slate(slate, api_key="k", cache_only=True)
    finally:
        O.CACHE_DIR = real
    return res, slate.games[0]


def test_an_eighteen_hour_price_is_replaced_by_a_twelve_minute_one():
    """THE case. The event pull left -220 on the game eighteen hours ago;
    the whole-slate payload on disk is twelve minutes old and says -118."""
    res, g = _apply(_game(price_age_s=18 * 3600), payload_age_s=12 * 60)
    assert (g.home_ml, g.away_ml) == (-118, 102), (g.home_ml, g.away_ml)
    assert g.priced_from == "board"
    assert res.older_than_attached == 0


def test_a_fresher_price_is_never_made_older():
    """The reverse, and the reason this pass is safe to run every time.
    It goes SECOND, so without the rule a cheap refresh on a cycle whose
    event pull was minutes old would be a downgrade wearing the word
    "refresh"."""
    res, g = _apply(_game(price_age_s=60), payload_age_s=6 * 3600)
    assert (g.home_ml, g.away_ml) == (-220, 200), (g.home_ml, g.away_ml)
    assert g.priced_from == "event"
    assert res.older_than_attached == 1
    assert res.moneylines == 0


def test_a_game_with_no_price_yet_takes_whatever_there_is():
    """Nothing to protect: an unpriced game is not made worse by a price
    of any age the show ceiling allows."""
    res, g = _apply(_game(), payload_age_s=6 * 3600)
    assert (g.home_ml, g.away_ml) == (-118, 102)
    assert res.moneylines == 1


def test_the_skip_is_counted_rather_than_silent():
    """A pass that did nothing and a pass that had nothing to add look
    identical from outside. The count is the difference."""
    res, _ = _apply(_game(price_age_s=60), payload_age_s=6 * 3600)
    assert res.older_than_attached == 1


def test_the_build_reads_the_cache_even_when_the_spend_was_declined():
    """The wiring. `--board-odds` still means "you may spend"; the pass
    itself runs whenever there is a payload to read, cache-only."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'if args.board_odds or _with_board_cache("nfl"):' in src
    assert "cache_only=not args.board_odds" in src


def test_it_does_not_claim_a_request_it_never_made():
    """"from 1 request" on a pass that made none is a small lie of the
    exact kind this file keeps having to unpick, and the difference is
    three credits against nothing."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'from the cached pull (no request)' in src
    assert "board_from_cache=not args.board_odds" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
