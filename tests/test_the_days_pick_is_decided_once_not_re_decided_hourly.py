"""The day's pick is a judgement made once, not the last build's scraps.

Ethan, 2026-09-19: *"we haven't been getting any college football pick
of the days."*

MEASURED ON THE DROPLET, the same day. The college card's census, over
29 candidates:

    a player prop — the day’s pick is game markets only   17
    the game has already started                           8
    the price is not far enough off the fair               2
    the board itself says this did not clear its bar       2

Seventeen were never eligible (his own 2026-09-15 call: game markets
only). Of the twelve game rows that were, EIGHT had already kicked off
by the first afternoon build. A college Saturday runs noon to midnight
and the board rebuilds every forty-five minutes, so the pool the
selector sees shrinks all day — and the card a reader meets in the
evening is the last and worst reading of the day rather than the day's
call.

It is also the churn he reported on the NFL four days earlier — *"it
will be different picks every time"* — from the same cause.

THE FIX IS NOT A BIGGER POOL OR A LOWER BAR. It is that a judgement
already made, on a board where more of the slate was still open, is not
overwritten by a smaller one. `potd.carry` is that rule and this file is
its statement.

WHAT IT IS NOT. `ledger.relock_potd` holds a pick that was JOURNALED —
money moved, the row is in the book. This is deliberately weaker: it
holds a judgement, including a refusal, and only against a strictly
worse reading of the same day.

AND THE SECOND BUG THE SAME MORNING'S DIGGING FOUND, pinned at the
bottom: `pick_of_the_day` is a paid key, so an unsubscribed reader is
served `{}` — which is an object and truthy, so it slipped past the
guard written for a card-less board and the page printed "No pick
today." to somebody for whom a pick existed and was merely locked.

Run directly:
`python3 tests/test_the_days_pick_is_decided_once_not_re_decided_hourly.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import potd                                       # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _card(hour, open_n, pick=None, sport="cfb"):
    """A card as `build` writes one, at a given hour of one day."""
    return {"sport": sport, "date": "2026-09-19",
            "decided_at": f"2026-09-19T{hour:02d}:00:00Z",
            "generated_at": f"2026-09-19T{hour:02d}:00:00Z",
            "open_candidates": open_n, "considered": 29,
            "pick": pick}


def _bet(name="TOL"):
    return {"player": f"{name} ML", "market": "moneyline", "odds": -122}


def _near(why="the price is not far enough off the fair to be worth it"):
    return {"player": "TOL ML", "market": "moneyline", "odds": -194,
            "below_bar": why}


# --- what counts as a pick ---------------------------------------------
def test_a_near_miss_is_not_a_pick():
    """`build` puts the nearest thing in `pick` too, flagged. Reading
    `pick` alone would call every declining card a pick and freeze it for
    the day — the exact opposite of the bug being fixed."""
    assert potd.has_pick(_card(14, 12, _bet()))
    assert not potd.has_pick(_card(14, 12, _near()))
    assert not potd.has_pick(_card(14, 12, None))
    assert not potd.has_pick({})
    assert not potd.has_pick(None)


# --- the rule ----------------------------------------------------------
def test_a_later_decline_does_not_overwrite_the_mornings_reading():
    """THE BUG, in one assertion. The 14:00 board judged twelve open
    games; the 18:00 board had four left because eight kicked off. The
    reader must see the judgement that saw the day."""
    morning = _card(14, 12, _near())
    evening = _card(18, 4, _near("the board itself says this did not clear its bar"))
    got = potd.carry(evening, morning)
    assert got["open_candidates"] == 12, got
    assert got["decided_at"] == morning["decided_at"], got


def test_finding_a_real_pick_always_wins():
    """A decline must be overturnable. An evening game the morning board
    could not price is a real pick and has to reach the page."""
    morning = _card(14, 12, _near())
    evening = _card(18, 4, _bet("OSU"))
    assert potd.carry(evening, morning)["pick"] == _bet("OSU")


def test_a_pick_already_made_is_never_replaced_by_a_decline():
    """The day's call, made when it could still be placed. `relock` keeps
    the price with it; this keeps the call itself even if the journal
    write never happened.

    THE SECOND PAIR IS THE ONE THAT MATTERS, and mutation found it: with
    only the first, deleting `has_pick(prev)` from the rule still passed,
    because a morning reading normally has MORE of the slate open and the
    size comparison caught it by accident. A slate priced in stages
    breaks that coincidence — three games quoted at nine, fourteen by
    lunchtime — and then nothing but the pick itself holds the call."""
    assert potd.carry(_card(18, 4, _near()), _card(14, 12, _bet()))["pick"] \
        == _bet()
    thin_morning = _card(9, 3, _bet())
    full_noon = _card(12, 14, _near())
    assert potd.carry(full_noon, thin_morning)["pick"] == _bet(), \
        "a made call was thrown away by a board that merely saw more games"


def test_a_later_build_with_MORE_of_the_slate_open_is_taken():
    """The pool does not only shrink — a slate can be priced in stages,
    and a build that sees more of the day is a better reading whichever
    way the clock went."""
    early = _card(9, 3, _near())
    later = _card(11, 14, _near())
    assert potd.carry(later, early)["open_candidates"] == 14


def test_an_equal_reading_keeps_the_one_already_on_screen():
    """Ethan, 2026-09-15: "it will be different picks every time." Two
    readings of the same board must not churn the card."""
    a, b = _card(14, 12, _near()), _card(15, 12, _near("something else"))
    assert potd.carry(b, a)["decided_at"] == a["decided_at"]


def test_yesterdays_card_is_not_todays_judgement():
    """`date` is a WEEK LABEL for football, so the day comparison is
    `decided_at`'s — the one field both cards state, in UTC."""
    old = _card(14, 30, _bet())
    old["decided_at"] = "2026-09-18T14:00:00Z"
    assert potd.carry(_card(9, 2, _near()), old)["open_candidates"] == 2


def test_another_sports_card_is_never_carried_into_this_one():
    """One file per league, but one function for all five."""
    nfl = _card(14, 30, _bet(), sport="nfl")
    assert potd.carry(_card(18, 2, _near()), nfl)["sport"] == "cfb"


def test_no_previous_card_is_simply_todays():
    for prev in (None, {}, [], "nope"):
        assert potd.carry(_card(14, 12, _near()), prev)["open_candidates"] == 12


def test_a_carried_card_says_so_and_keeps_the_builds_own_clock():
    """A stale judgement presented as a fresh one is the failure this
    repo keeps paying for. `generated_at` stays honest about the build
    that published it; `carried` explains the gap."""
    got = potd.carry(_card(18, 4, _near()), _card(14, 12, _near()))
    assert got["generated_at"] == "2026-09-19T18:00:00Z", got
    assert "14:00" in got["carried"], got["carried"]
    assert "12" in got["carried"], got["carried"]


def test_a_card_that_was_not_carried_carries_no_excuse():
    assert "carried" not in potd.carry(_card(18, 4, _bet()), _card(14, 12, _near()))


# --- the numbers the rule reads ----------------------------------------
def test_the_card_records_when_it_was_decided_and_what_was_open():
    """`carry` compares two cards, so both numbers have to be ON the
    card — computed and not placed is this codebase's oldest bug."""
    card = potd.build([], "cfb", "2026-09-19")
    assert card["decided_at"].endswith("Z"), card["decided_at"]
    assert card["open_candidates"] == 0, card


def test_the_started_count_comes_off_the_census_by_a_shared_name():
    """A census key spelled by hand in one place and changed in the other
    is a silent zero — and a silent zero here means "no slate was open",
    which is the answer that loses the day's pick."""
    import inspect
    src = inspect.getsource(potd.build)
    assert "census.get(STARTED" in src, "the counter re-spells the reason"
    assert potd.STARTED in potd.HARD_REASONS
    # AND THE CONSTANT IS THE STRING `disqualify` ACTUALLY RETURNS. The
    # first version of this asserted only that the name existed and was
    # in the tuple, which a renamed constant satisfies while the census
    # key it is looked up by silently stops matching — a zero that means
    # "no slate was open" and loses the day's pick. Mutation caught it.
    # Everything the earlier refusals ask for, so the row reaches the
    # clock — `live` is the scoreboard's own flag and the same one
    # `rules.game_has_started` refuses a journal write on.
    started = {"game_date": "2026-09-19", "market": "moneyline",
               "bet_type": "moneyline", "team": "TOL", "odds": -122,
               "book": "fanduel", "sharp_anchored": True,
               "sharp_fair": 0.55, "implied_prob": 0.55, "live": True}
    assert potd.disqualify(dict(started, live=False),
                           today="2026-09-19") != potd.STARTED, \
        "the fixture never reaches the clock — an earlier bar refused it"
    assert potd.disqualify(started, today="2026-09-19") == potd.STARTED


def test_open_candidates_excludes_exactly_the_started_ones():
    """THROUGH `build`, WITH A REAL STARTED ROW — not by re-doing the
    subtraction here.

    Mutation is why. Renaming the constant is an equivalent mutant: both
    sides move together, which is exactly what the constant is for. The
    mutation that BITES is the census key hand-spelled, or mis-spelled,
    in `build` — and only a board that actually contains a started game
    can tell. Two rows, one on the clock: the count must be one."""
    day = "2026-09-19"
    base = {"game_date": day, "market": "moneyline", "bet_type": "moneyline",
            "team": "TOL", "odds": -122, "book": "fanduel",
            "sharp_anchored": True, "sharp_fair": 0.55, "implied_prob": 0.55}
    card = potd.build([dict(base, live=True), dict(base, team="OSU")],
                      "cfb", day)
    assert card["considered"] == 2, card
    assert card["census"].get(potd.STARTED) == 1, card["census"]
    assert card["open_candidates"] == 1, card


# --- where the previous card is read from ------------------------------
def test_the_previous_card_comes_from_the_UNREDACTED_board():
    """`web/data`'s copy has `pick_of_the_day` stripped — it is a paid
    key — so reading the published board would carry `{}` forward and
    this whole mechanism would quietly do nothing."""
    import inspect
    src = inspect.getsource(potd.previous_card)
    assert "built" in src, "it is reading the published copy"
    assert "web" not in src.split('"""')[-1], src


def test_a_previous_card_is_found_and_an_absent_one_costs_nothing():
    d = tempfile.mkdtemp()
    assert potd.previous_card("cfb", d) is None
    with open(os.path.join(d, "cfb.json"), "w", encoding="utf-8") as fh:
        json.dump({"pick_of_the_day": _card(14, 12, _near())}, fh)
    assert potd.previous_card("cfb", d)["open_candidates"] == 12
    # And the shapes that must not raise into a build.
    for junk in ("{ not json", '{"pick_of_the_day": {}}',
                 '{"pick_of_the_day": null}', '{"pick_of_the_day": []}', "[]"):
        with open(os.path.join(d, "cfb.json"), "w", encoding="utf-8") as fh:
            fh.write(junk)
        assert potd.previous_card("cfb", d) is None, junk
    assert potd.previous_card("nope", d) is None


def test_attach_consults_the_previous_card():
    """The rule has to be ON THE PATH the builds call, or it is a
    function nobody runs."""
    board = {"date": "2026-09-19", "sport": "cfb", "most_likely": []}
    potd.attach(board, "cfb", prev=_card(14, 12, _bet()))
    assert board["pick_of_the_day"]["pick"] == _bet(), board["pick_of_the_day"]


def test_attach_still_works_with_no_previous_board_on_disk():
    board = {"date": "2026-09-19", "sport": "cfb", "most_likely": []}
    note = potd.attach(board, "cfb", built_dir=tempfile.mkdtemp())
    assert board["pick_of_the_day"]["pick"] is None
    assert "pick of the day" in note.lower(), note


# --- and the paywalled card the page was mislabelling -------------------
def _render(code_only=False):
    i = APP.index("async function renderPickOfTheDay(")
    body = APP[i:APP.index("\nasync function ", i + 10)]
    if not code_only:
        return body
    # COMMENTS STRIPPED BEFORE ANY ORDERING CLAIM. The comment explaining
    # this very fix quotes the sentence the fix removes from the empty
    # case, so an assertion about where "No pick today." appears was
    # measuring the explanation rather than the code — the mistake
    # tests/test_a_rostered_player_is_findable_before_he_plays.py made
    # the same morning, and the mirror of the `clv_coverage` guard a
    # comment could satisfy.
    import re as _re
    body = _re.sub(r"(?s)/\*.*?\*/", " ", body)
    return _re.sub(r"(?m)^\s*//.*$", " ", body)


def test_an_empty_card_is_not_drawn_as_no_pick_today():
    """`pick_of_the_day` is in `gate.PAID_KEYS`, so an unsubscribed
    reader is served `{}`. `{}` is an object AND truthy, so it sailed
    through the guard written for a card-less board, fell to the no-pick
    branch and printed "No pick today." — on the most valuable slot on
    the page, to somebody for whom a pick existed and was merely locked.
    """
    code = _render(code_only=True)
    assert "Object.keys(got" in code, \
        "an empty card still renders as an engine verdict"
    k = code.index("Object.keys(got")
    assert 'host.innerHTML = ""' in code[k:k + 200], \
        "the empty card is detected and then drawn anyway"
    assert "No pick today." in code, "the no-pick wording went missing"
    assert code.index("No pick today.") > k, \
        "the empty check must come BEFORE the branch that would mislabel it"
    # And the reason is written down where the next reader will meet it.
    assert "PAID_KEYS" in _render(), "nothing says why an empty card happens"


def test_the_page_says_when_a_carried_card_was_decided():
    """BOTH BRANCHES, AND THE PLACEMENT. A carried card can be either a
    held PICK or a held decline, so the explanation has to reach both —
    and `carriedNote` being built is not the same as it being drawn.
    Mutation killed neither claim until they were separated: deleting the
    read left the const, and deleting the placement left the const too."""
    code = _render(code_only=True)
    # The declining branch reads it, ahead of the older fallbacks.
    assert "got.carried || got.relocked" in code, \
        "a held decline is drawn with the wrong reason, or none"
    # And the branch that names a bet places the note it builds.
    assert "const carriedNote" in code, "nothing computes the note"
    assert "${carriedNote}" in code, "the note is built and never placed"


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
