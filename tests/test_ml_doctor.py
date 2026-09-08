"""`--ml-doctor`: what the books quote, what we publish, do they agree.

WHY A TOOL RATHER THAN ANOTHER PASTE. The same report has arrived four
times, always with a sportsbook open beside the site:

  2026-09-03  "These lines along with more are completely wrong, none of
              these teams are favored to win on any sports book."
  2026-09-08  "I don't want you too stop working until we display the
              right lines and prices the books show."
  2026-09-09  "FanDuel and draft kings show the lines in the screenshot
              yet we show a different line. That's wrong."
  2026-09-09  "i wanna focus on those moneyline props, they are still
              showing the wrong lines on the site like before"

Every time the answer needed the same three things side by side — the
book quotes in the cached pull, the price the board published, and
whether those are the same number — and every time they were dug out with
a one-off command that was then thrown away. Nothing on the machine could
show them together, which is why the question kept coming back with no
accumulated answer.

Two failures look identical on a phone and have opposite fixes, and
separating them is the whole point of the verdict at the bottom:

  * the pull holds -118 and we published -220 → the fault is ours, in
    the code between the two;
  * the pull itself holds -220 → the fault is the pull, and the age
    printed beside it says whether it is staleness or a bad match.

`odds_doctor` is the MLB twin and exists for the same reason, having
been "written after guessing wrong about it twice".
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import launch                                                # noqa: E402
from engine.sources import fetch as _fetch                   # noqa: E402


def _event(home="Minnesota Vikings", away="Green Bay Packers",
           books=(("fanduel", -125, 105), ("draftkings", -118, 100))):
    return {"home_team": home, "away_team": away,
            "commence_time": "2026-09-14T17:00:00Z",
            "bookmakers": [
                {"key": k, "markets": [{"key": "h2h", "outcomes": [
                    {"name": home, "price": h}, {"name": away, "price": a}]}]}
                for k, h, a in books]}


def _board(home_ml=-220, away_ml=180, ml_rows=True):
    return {"odds_status": {"checked": True, "board_moneylines": 1},
            "games": [{"home": "MIN", "away": "GB",
                       "home_ml": home_ml, "away_ml": away_ml}],
            "most_likely": ([{"market": "moneyline", "pick_label": "MIN ML",
                              "odds": home_ml, "book": "DraftKings",
                              "model_prob": 0.687, "prob_source": "market",
                              "priced_from": "board", "price_age_s": 109000}]
                            if ml_rows else [])}


def _run(events=None, board=None, full=None, sport="nfl"):
    """Stand up a tree, run the doctor, return everything it printed."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "cache").mkdir()
    (tmp / "web" / "data").mkdir(parents=True)
    if events is not None:
        (tmp / "cache" / f"odds_board_{sport}.json").write_text(
            json.dumps(events))
    if board is not None:
        (tmp / "web" / "data" / "recommendations.json").write_text(
            json.dumps(board))
    if full is not None:
        (tmp / "data" / "built").mkdir(parents=True)
        (tmp / "data" / "built" / "recommendations.json").write_text(
            json.dumps(full))
    old_root, old_cache = launch.ROOT, _fetch.CACHE_DIR
    launch.ROOT, _fetch.CACHE_DIR = tmp, tmp / "cache"
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch.ml_doctor(sport)
        return buf.getvalue()
    finally:
        launch.ROOT, _fetch.CACHE_DIR = old_root, old_cache


def test_a_published_price_shorter_than_the_whole_field_is_the_finding():
    """THE bug the tool exists to name. We publish the best price per
    side, so ours can beat one book and can never be worse than all of
    them. -220 on a board whose pull tops out at -118 did not come from
    shopping."""
    out = _run([_event()], _board(home_ml=-220))
    assert "SHORTER than anything in the pull" in out, out
    assert "MIN: board -220, pull's best -118 at DraftKings" in out, out


def test_agreement_says_so_and_says_why_a_phone_still_differs():
    """The other half of the answer, and the one that stops a true report
    being read as a bug. Our -118 will not match a phone showing -125,
    because we shop: the number is the longest across the field."""
    out = _run([_event()], _board(home_ml=-118, away_ml=105))
    assert "every published moneyline matches" in out, out
    assert "because we SHOP" in out, out
    assert "SHORTER" not in out


def test_the_sharp_book_is_skipped_exactly_as_the_parser_skips_it():
    """`parse_event_h2h` refuses the sharp reference — nobody here can
    bet it — so a doctor that counted it would compare the board against
    a number the board never had, and report a bug that is not there."""
    ev = _event(books=(("fanduel", -125, 105), ("pinnacle", -101, 150)))
    out = _run([ev], _board(home_ml=-125, away_ml=105))
    assert "Pinnacle" not in out, out
    assert "we publish -125 at FanDuel" in out, out
    assert "SHORTER" not in out, out


def test_it_reads_the_full_board_not_the_redacted_copy():
    """The mistake `gate.board_source` exists to stop, and the one this
    session made a fourth time: `web/data/` is the paywalled copy, and an
    empty `most_likely` there is the paywall working. A doctor reading it
    would report a healthy board as empty."""
    out = _run([_event()], _board(ml_rows=False), full=_board(ml_rows=True))
    assert "ML row MIN ML" in out, out
    assert "data/built" in out, out


def test_no_pull_is_reported_as_no_comparison_not_as_a_clean_bill():
    """A tool that reports a healthy system as broken costs more than no
    tool. So does one that reports an unchecked system as healthy — and
    that is the easier mistake to make, because silence reads as
    approval."""
    out = _run(None, _board())
    assert "no cached pull to compare against" in out
    assert "says nothing about whether the board is right" in out
    assert "matches the best price" not in out


def test_a_sport_it_cannot_check_is_refused_rather_than_half_run():
    out = _run([_event()], _board(), sport="mlb")
    assert "No moneyline doctor for 'mlb'" in out
    assert "nfl" in out and "cfb" in out


def test_the_freshness_counters_ride_along():
    """Staleness and a wrong number are the two explanations that keep
    getting confused, so the age of the payload is printed beside the
    prices rather than looked up separately."""
    board = _board()
    board["odds_status"]["board_shown_stale_prices"] = 3
    board["odds_status"]["board_shown_stale_age_s"] = 109000
    out = _run([_event()], board)
    assert "board_shown_stale_prices" in out and "3" in out
    assert "h old" in out                      # the pull's own age
    assert "age=30.3h" in out                  # and the row's


def test_the_flag_is_wired_and_the_board_map_covers_both_footballs():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--ml-doctor"' in src
    assert "ml_doctor(who)" in src
    assert set(launch.ML_DOCTOR_BOARDS) == {"nfl", "cfb"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
