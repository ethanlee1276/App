"""No Pick of the Day on a day the league is not playing.

Ethan, 2026-09-19: *"the NFL page will throw out picks of the day on
days that we do not have NFL games going on. And it will be different
picks every time. So I feel like we're giving misleading information.
And we need to be looking at the NFL schedule and only giving out picks
of the days on days there's NFL games."*

He is right, and the cause was small and bad: `potd.disqualify` had
SEVEN refusals — a prop, no fair price, no real book, a sharp-only
quote, outside the payout band, an injury designation, the game already
started — and not one of them was "that game is not today".

The Most Likely board legitimately carries the whole upcoming week; that
is what a board is for. The DAY'S pick was drawn from it with no date
filter, so on a Wednesday it crowned a Sunday game. And it moved between
builds because the candidate pool was the entire week with the ordering
shifting underneath it — which a reader reads as a fresh call on a real
game, three days before anyone can watch it.

Run directly: `python3 tests/test_the_days_pick_is_for_a_game_today.py`
"""

import datetime as _dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import potd                                       # noqa: E402

#: A Wednesday afternoon. NAIVE UTC, which is what the builds pass —
#: `rules.clock_says_started` subtracts it from a naive kickoff instant
#: and raises on an aware one, so a test handing it an aware stamp would
#: be exercising a shape production never produces.
#:
#: No fixed date appears in an assertion; every expectation below is
#: derived from this instant.
NOW = _dt.datetime(2026, 9, 16, 18, 0)
TODAY = potd.slate_day(NOW)
SUNDAY = (_dt.date.fromisoformat(TODAY) + _dt.timedelta(days=4)).isoformat()
YESTERDAY = (_dt.date.fromisoformat(TODAY) - _dt.timedelta(days=1)).isoformat()


def _row(game_date=None, **kw):
    """A row that clears every OTHER bar, so a refusal can only be the
    one under test."""
    # Sharp-anchored, which is the tier `fair_prob` prices against
    # without falling back to the model (and `shortfall` then refuses a
    # model-only row anyway, which would mask the gate under test).
    row = {"kind": "game", "market": "moneyline", "pick": "PHI",
           "game_date": TODAY if game_date is None else game_date,
           "book": "dk", "odds": -140, "kickoff": "20:15",
           "sharp_anchored": True, "sharp_fair": 0.66, "win_prob": 0.66,
           "model_prob": 0.66, "implied_prob": 0.583}
    row.update(kw)
    return row


# --- the day is the first question asked -------------------------------
def test_a_game_today_is_still_eligible():
    """The gate has to let the real case through, or it is just an
    outage with a reason attached."""
    assert potd.disqualify(_row(), NOW) == ""


def test_a_game_later_this_week_cannot_be_todays_pick():
    """THE BUG. Sunday's game, seen on Wednesday."""
    assert potd.disqualify(_row(SUNDAY), NOW) == "the game is not today"


def test_a_game_yesterday_cannot_be_todays_pick_either():
    """The same gate from the other side — a board that failed to
    rebuild leaves yesterday's rows sitting there."""
    assert potd.disqualify(_row(YESTERDAY), NOW) == "the game is not today"


def test_a_row_that_cannot_prove_its_day_is_refused():
    """For the most prominent claim on the site, "I cannot tell" is a
    refusal rather than a shrug."""
    got = potd.disqualify(_row(""), NOW)
    assert "cannot show it is today" in got, got


def test_the_row_date_is_read_where_the_started_check_reads_it():
    """Both questions about a game — has it started, and is it even
    today — have to be asked of the same field, or a row can be current
    for one and stale for the other."""
    assert potd._row_day({"game_date": TODAY}) == TODAY
    assert potd._row_day({"date": TODAY}) == TODAY
    assert potd._row_day({"game_date": TODAY, "date": YESTERDAY}) == TODAY


# --- and the board says so rather than showing a pick ------------------
def test_a_week_of_upcoming_games_yields_no_pick_today():
    """The whole complaint, end to end: an NFL board mid-week carries
    Sunday's slate and must produce NO pick, not a rotating one."""
    rows = [_row(SUNDAY, pick=f"T{i}") for i in range(12)]
    out = potd.build(rows, "nfl", "2026-W03", now=NOW)
    assert out["pick"] is None, out["pick"]
    assert out["census"].get("the game is not today") == 12, out["census"]


def test_the_card_names_the_reason_instead_of_going_quiet():
    """A blank card and a declined day are different facts, and the
    page has to be able to tell a reader which one it is."""
    out = potd.build([_row(SUNDAY)], "nfl", "2026-W03", now=NOW)
    assert out.get("note"), out
    assert out["considered"] == 1, out


def test_the_same_board_gives_the_same_answer_every_build():
    """"it will be different picks every time" — with no day filter the
    pool was the whole week and the ordering moved under it. Two builds
    a minute apart must agree."""
    rows = [_row(SUNDAY, pick=f"T{i}") for i in range(8)]
    a = potd.build(rows, "nfl", "2026-W03", now=NOW)
    b = potd.build(rows, "nfl", "2026-W03",
                   now=NOW + _dt.timedelta(minutes=1))
    assert a["pick"] is None and b["pick"] is None


def test_todays_game_still_becomes_the_pick():
    """And a real game day still produces one — the gate must not be a
    silent outage on Sunday."""
    out = potd.build([_row()], "nfl", "2026-W03", now=NOW)
    assert out["pick"] is not None, out


def test_one_game_today_is_picked_out_of_a_week_of_others():
    """The realistic shape: a Thursday-night game on a board that also
    carries Sunday."""
    rows = [_row(SUNDAY, pick=f"T{i}") for i in range(10)] + [_row(pick="TNF")]
    out = potd.build(rows, "nfl", "2026-W03", now=NOW)
    assert out["pick"] is not None, out
    assert out["pick"]["pick"] == "TNF", out["pick"]


def test_a_caller_can_say_which_day_it_is_replaying():
    """`today` is threaded through `choose` rather than re-derived inside
    `disqualify`, so a replay (`potdbacktest`) can ask "what would this
    board have picked on THAT day" without lying about the clock.

    Found by mutation: dropping the argument was invisible, because the
    fallback recomputes the same value from `now`. A parameter nothing
    can exercise differently is a parameter that should not exist — so
    this pins the one thing it is for."""
    row = _row(SUNDAY)
    assert potd.disqualify(row, NOW) == "the game is not today"
    assert potd.disqualify(row, NOW, today=SUNDAY) == ""
    # Asserted on the CENSUS, not on whether a pick came out: the row
    # still has to clear every other bar, and which of those it trips is
    # not what this test is about.
    _p, _n, census = potd.choose([row], NOW)
    assert census.get("the game is not today") == 1, census
    _p, _n, census = potd.choose([row], NOW, today=SUNDAY)
    assert "the game is not today" not in census, census


# --- the clock it is measured on ---------------------------------------
def test_today_is_read_on_the_schedules_own_clock():
    """A bare "HH:MM" kickoff is already an Eastern clock
    (`fatigue.kickoff_instant`). A second timezone for the same question
    would put the card and the schedule a day apart on every late game:
    a 10pm Eastern Sunday kickoff is Monday in UTC."""
    late = _dt.datetime(2026, 9, 21, 2, 30, tzinfo=_dt.timezone.utc)
    assert potd.slate_day(late) == "2026-09-20", potd.slate_day(late)
    assert potd.POTD_TZ == "America/New_York"


def test_a_naive_timestamp_is_not_read_as_local_time():
    assert potd.slate_day(_dt.datetime(2026, 9, 21, 2, 30)) == "2026-09-20"


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
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
