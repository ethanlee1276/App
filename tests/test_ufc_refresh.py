"""UFC has to be able to spend, or its card never exists.

The failure, seen live on a Friday night: the page said "no card" while
fights were happening. `refresh_ufc` passed `--cached-odds` on every
single call and `--odds` on none, so the event list was only ever READ
from a cache that nothing ever WROTE. `select_card` found no bouts, the
build wrote status "no_card", and it would have done so forever.

NBA carried exactly this bug and its fix is the template — hence a test
that compares them, because the next sport added will be copied from
whichever one the author happens to open.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fn(name):
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    start = src.index(f"def {name}(")
    end = src.index("\ndef ", start + 1)
    return src[start:end]


def test_ufc_can_actually_spend():
    fn = _fn("refresh_ufc")
    assert '"--odds"' in fn, "cached-only again: nothing will ever seed the cache"
    assert "_odds_affordable" in fn, "spending must go through the budgeter"


def test_ufc_still_falls_back_to_cache():
    # Between paced pulls the card must stay priced, not blank out.
    fn = _fn("refresh_ufc")
    assert '"--cached-odds"' in fn
    assert "_with_odds()" in fn


def test_the_paid_pull_is_recorded():
    # Without this the pacing clock never advances and UFC would pull on
    # every cycle — the opposite failure, and an expensive one.
    fn = _fn("refresh_ufc")
    assert "_paid_pull_baseline()" in fn
    assert "_finish_paid_pull(" in fn
    assert 'sport="ufc"' in fn, "UFC needs its own pacing clock, not the shared one"


def test_it_is_not_gated_on_a_card_it_cannot_have_yet():
    """The circular gate: MLB/NBA check games>0 because their slate comes
    from a free feed. UFC's card only exists once odds have been pulled, so
    the same gate would prevent the pull that creates it."""
    fn = _fn("refresh_ufc")
    assert "_slate_games" not in fn


def test_no_card_on_the_free_list_means_no_paid_pull():
    """Between cards the events list is empty and a paid pull buys
    nothing — which read as "the API never answered" and paused every
    other lane (2026-09-14). The card is read off the FREE events feed
    before the budgeter is asked; that is not the circular games>0 gate,
    which reads the priced output."""
    fn = _fn("refresh_ufc")
    assert "card = _ufc_card()" in fn
    assert "(_ufc_card_pending(quiet, card)\n             and _odds_affordable(" in fn
    gate = _fn("_ufc_card_pending") + _fn("_ufc_card")
    assert "list_events(" in gate and 'sport="ufc"' in gate
    assert "select_card(" in gate
    assert "return True" in _fn("_ufc_card_pending"), "an unknown card must not silence the pull"
    assert "_slate_games" not in gate and "UFC_OUT" not in gate


def test_the_card_is_bought_on_fight_night_only():
    """Ethan, 2026-10-30: "pulling credits just for those sports" that play
    that night. UFC's board has no games for the pacer to count, so the
    card's bouts are its games (`_ufc_tonight`), handed to the pacer's
    tonight rule; an unknown card or unreadable times say nothing."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    import launch
    fn = _fn("refresh_ufc")
    assert "tonight=_ufc_tonight(card)" in fn
    et = ZoneInfo("America/New_York")

    def at(*when):
        return dt.datetime(*when, tzinfo=et)

    card = [{"commence_time": at(2026, 11, 7, 19 + i % 4).astimezone(dt.timezone.utc)
             .isoformat().replace("+00:00", "Z")} for i in range(12)]
    wed, sat, sun_1am = (at(2026, 11, 4, 12).timestamp(), at(2026, 11, 7, 12).timestamp(),
                         at(2026, 11, 8, 1).timestamp())
    assert launch._ufc_tonight(card, wed) == 0, "fight week: nothing to buy yet"
    assert launch._ufc_tonight(card, sat) == 12
    assert launch._ufc_tonight(card, sun_1am) == 12, "the main card past midnight is still tonight's"
    assert launch._ufc_tonight(None, sat) is None
    assert launch._ufc_tonight([{"commence_time": "soon"}], sat) is None


def test_it_matches_the_nba_rotation_it_was_modelled_on():
    ufc, nba = _fn("refresh_ufc"), _fn("refresh_nba")
    for piece in ('"--odds"', '"--cached-odds"', "_odds_affordable",
                  "_paid_pull_baseline()", "_finish_paid_pull("):
        assert (piece in ufc) == (piece in nba), \
            f"{piece} present in one rotation but not the other"


def test_every_sport_writes_to_a_named_output_constant():
    # The hardcoded path in refresh_ufc is how it drifted out of the
    # rotation unnoticed — the others were all reachable by constant.
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    for const in ("MLB_OUT", "NFL_OUT", "NBA_OUT", "UFC_OUT"):
        assert re.search(rf"^{const} = ", src, re.M), f"{const} is not defined"
    assert '"web/data/ufc.json"' not in _fn("refresh_ufc")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
