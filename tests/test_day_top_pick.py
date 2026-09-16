"""One pick for the DAY, not one per league.

Ethan, 2026-09-15: "a model that picks one pick for the pick of the day,
which is a guaranteed lock for the day." Singular. `potd.build` chooses
one per SPORT, so a reader on the MLB page and a reader on the NFL page
were each shown a different "Pick of the Day" and neither was the day's.

WHAT THIS IS NOT is a second model. `potd.rank_key` already orders picks
on three quantities that know nothing about which sport produced them —
which witness stands behind the fair, the edge in points, the payout —
so the cross-league answer is that comparator over a longer list. These
tests hold that it stays that way: a cross-sport bar invented here would
be a second set of numbers measured on nothing.

Run directly: `python3 tests/test_day_top_pick.py`
"""

import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

TODAY = "2026-03-04"          # any day; never read from the clock


def _board(date=TODAY, **pick):
    """One published board carrying one pick of the day."""
    if not pick:
        return {"pick_of_the_day": {"date": date, "pick": None,
                                    "note": "the board had no rows"}}
    return {"pick_of_the_day": {"date": date, "pick": dict(pick)}}


def _sharp(odds=-130, fair=0.60, **extra):
    return dict(player="AAA", market="moneyline", odds=odds,
                sharp_anchored=True, sharp_fair=fair, fair_prob=fair,
                evidence="sharp", **extra)


def _model(odds=-130, fair=0.70, **extra):
    return dict(player="BBB", market="moneyline", odds=odds,
                model_prob=fair, fair_prob=fair, evidence="model", **extra)


# ── the comparison ──────────────────────────────────────────────────

def test_the_better_witness_wins_across_leagues_not_the_bigger_edge():
    """THE INVERSION THE WHOLE MODULE TURNS ON, now across boards. A
    model-only 10-point disagreement is a louder claim than a sharp
    book's 2, and much more often simply wrong. If this ever flips, the
    cross-league feature is handing every day to the weakest witness on
    the site."""
    got = potd.day_top_pick(
        {"nfl": _board(**_sharp()), "mlb": _board(**_model())}, TODAY)
    assert got["sport"] == "nfl", got["sport"]
    assert [r["sport"] for r in got["runners_up"]] == ["mlb"], got


def test_a_qualifying_pick_always_beats_a_below_bar_one():
    """`build` publishes its best available when nothing clears, so a
    below-bar row is on the board BY DESIGN. Letting one outrank a pick
    that cleared every gate would quietly undo the gates — and it would
    do it silently, because both cards look the same from here."""
    got = potd.day_top_pick({
        # The below-bar row is given the STRONGER witness on purpose:
        # tier alone would hand it the day.
        "nfl": _board(**_sharp(), below_bar="the price drifted"),
        "mlb": _board(**_model()),
    }, TODAY)
    assert got["sport"] == "mlb", got["sport"]
    assert not got["pick"].get("below_bar"), got["pick"]


def test_when_nothing_clears_anywhere_the_best_lean_is_shown_and_labelled():
    """The page is never blank — and never pretends. Same two states the
    per-league card has."""
    got = potd.day_top_pick(
        {"nfl": _board(**_sharp(), below_bar="the price drifted")}, TODAY)
    assert got["pick"]["below_bar"] == "the price drifted"
    assert "best available" in got.get("note", ""), got.get("note")


def test_the_league_travels_with_the_pick():
    """A top pick nobody can find is not one. The card names the league
    and the page opens it."""
    got = potd.day_top_pick({"cfb": _board(**_sharp())}, TODAY)
    assert got["sport"] == "cfb"
    assert got["pick"]["sport"] == "cfb", got["pick"]


def test_a_tie_on_every_measured_quantity_resolves_the_same_way_twice():
    """Two identical picks in different leagues must not depend on which
    board finished writing first. TOP_PICK_LEAGUES is the tiebreak, and it
    is an ORDER rather than a claim that one league's picks are better —
    that claim would be an assertion measured on nothing."""
    same = dict(market="moneyline", odds=-130, sharp_anchored=True,
                sharp_fair=0.60, fair_prob=0.60, evidence="sharp")
    a = potd.day_top_pick(
        {"mlb": _board(player="M", **same), "nfl": _board(player="N", **same)},
        TODAY)
    b = potd.day_top_pick(
        {"nfl": _board(player="N", **same), "mlb": _board(player="M", **same)},
        TODAY)
    assert a["sport"] == b["sport"] == "nfl", (a["sport"], b["sport"])


# ── the staleness refusal ───────────────────────────────────────────

def test_yesterdays_pick_is_never_todays_top_pick():
    """THE FAILURE THIS FEATURE WOULD OTHERWISE INVENT. Every board
    publishes on its own schedule, and a league out of season leaves a
    perfectly well-formed pick on disk from whenever it last ran.
    Nothing about that card looks wrong; only its date says so."""
    got = potd.day_top_pick(
        {"mlb": _board(date="2026-03-03", **_sharp())}, TODAY)
    assert got["pick"] is None, got["pick"]
    assert any("has not rebuilt today" in k for k in got["census"]), got["census"]


def test_a_board_with_no_date_at_all_is_refused_rather_than_trusted():
    """An older board predating the date field would otherwise sail
    through every check — the emptiest possible evidence read as
    agreement."""
    got = potd.day_top_pick({"mlb": {"pick_of_the_day": {
        "pick": _sharp()}}}, TODAY)
    assert got["pick"] is None, got["pick"]


def test_a_fresh_league_still_wins_when_a_stale_one_looks_stronger():
    """The refusal has to bite BEFORE the ranking, or a stale sharp pick
    beats a live model one every time and the top pick silently stops
    moving."""
    got = potd.day_top_pick({
        "nfl": _board(date="2026-03-01", **_sharp()),
        "mlb": _board(**_model()),
    }, TODAY)
    assert got["sport"] == "mlb", got["sport"]


# ── the claim locks ─────────────────────────────────────────────────

def _game(player="KC ML", team="KC", **extra):
    """A moneyline card, in the shape the journal rewrites."""
    return dict(player=player, team=team, market="moneyline", kind="game",
                odds=-130, sharp_anchored=True, sharp_fair=0.60,
                fair_prob=0.60, evidence="sharp", **extra)


def test_the_pick_a_league_locked_this_morning_is_the_one_that_competes():
    """THE PROPERTY THAT MAKES THE RECORD MEAN ANYTHING. The boards
    rebuild all day. Ranking whatever is on them at the moment this runs
    means the day’s top pick can be an MLB bet at noon and, after that
    bet lost, an NFL one at eight — with nothing anywhere recording the
    first claim. `ledger.log_pick_of_the_day` was given a lock for
    exactly that reason one level down; this honours it rather than
    inventing a second one that can disagree with it."""
    from engine import ledger
    board = {"nfl": _board(**_game())}
    key = ledger.potd_row_key(_game())
    assert key == ("KC", "moneyline", "OVER", 0.5), key
    got = potd.day_top_pick(board, TODAY, locked={"nfl": key})
    assert got["sport"] == "nfl", got


def test_a_board_that_changed_its_pick_does_not_get_to_substitute_it():
    """The league is showing something else now. The journaled one is
    what we said, so the board’s current favourite does not stand in."""
    got = potd.day_top_pick({"nfl": _board(**_game())}, TODAY,
                            locked={"nfl": ("BUF", "moneyline", "OVER", 0.5)})
    assert got["pick"] is None, got["pick"]
    assert any("changed its pick" in k for k in got["census"]), got["census"]


def test_a_league_with_nothing_locked_yet_cannot_win_the_day():
    """No journal row means no claim was made — most often because the
    league’s pick was below the bar, which is never recorded."""
    got = potd.day_top_pick({"nfl": _board(**_game())}, TODAY, locked={})
    assert got["pick"] is None, got["pick"]
    assert any("nothing locked" in k for k in got["census"]), got["census"]


def test_an_unreadable_lock_publishes_nothing_rather_than_an_unlocked_claim():
    """The launcher hands `{}` when the database cannot be read. Failing
    closed matters here: an unlocked claim looks identical on the page
    and cannot be graded afterwards."""
    got = potd.day_top_pick({"nfl": _board(**_game()), "mlb": _board(**_sharp())},
                            TODAY, locked={})
    assert got["pick"] is None, got["pick"]


def test_a_below_bar_lean_needs_no_lock_because_it_is_not_a_claim():
    """Nothing journals a below-bar row, so there is no lock for it to
    match — and the page still has to show the strongest thing available
    on a day when no league cleared its bar."""
    got = potd.day_top_pick(
        {"nfl": _board(**_game(below_bar="the price drifted"))},
        TODAY, locked={})
    assert got["pick"] is not None, got
    assert got["pick"]["below_bar"] == "the price drifted"


def test_omitting_the_lock_entirely_still_ranks_every_board():
    """`locked=None` is the unlocked mode the tests above this section
    use, and the callers that have no journal (the report CLI). It must
    stay distinguishable from `{}`, which means "read the lock, found
    nothing"."""
    got = potd.day_top_pick({"nfl": _board(**_game())}, TODAY)
    assert got["sport"] == "nfl", got


def test_the_journal_key_is_derived_in_exactly_one_place():
    """Two copies of a derivation that negates a spread and rewrites a
    moneyline as OVER 0.5 is how one book ends up right and another
    wrong — `game_row_keys`’ own stated lesson. The writer and this
    matcher must call the same function."""
    from engine import ledger
    body = inspect.getsource(ledger.log_pick_of_the_day)
    assert "potd_row_key(" in body, \
        "the journal no longer derives its key through the shared helper"
    chooser = inspect.getsource(potd.day_top_pick)
    assert "potd_row_key" in chooser, \
        "the chooser has started deriving journal keys of its own"


# ── it never goes quiet ─────────────────────────────────────────────

def test_a_day_with_no_top_pick_says_which_league_failed_and_why():
    """A census, not a shrug — the funnel `likely.build` keeps and the
    one `potd.choose` keeps, for the same reason."""
    got = potd.day_top_pick({"mlb": _board(), "nfl": {}}, TODAY)
    assert got["pick"] is None
    assert len(got["census"]) == 2, got["census"]
    assert any("mlb" in k for k in got["census"]), got["census"]
    assert any("nfl" in k for k in got["census"]), got["census"]


def test_a_board_that_threw_is_named_rather_than_skipped():
    got = potd.day_top_pick(
        {"mlb": {"pick_of_the_day_error": "KeyError: home"}}, TODAY)
    assert any("could not choose" in k for k in got["census"]), got["census"]


def test_the_log_line_is_never_empty_whatever_it_is_handed():
    """A cross-board step that prints nothing on a day it chose nothing
    is the failure `lineledger.record_note` and the rankings section
    were both dragged out of."""
    for arg in ({}, None, {"pick": None, "census": {"mlb: no board": 1}},
                potd.day_top_pick({"nfl": _board(**_sharp())}, TODAY),
                {"pick": {"odds": None}}):
        line = potd.top_pick_line(arg)
        assert line and line.strip(), arg
        assert line.startswith("top pick:"), line


def test_a_card_without_its_tier_is_not_described_as_none():
    """`_card` always sets `evidence`; a card assembled anywhere else
    might not, and "None fair 60%" in a build log reads like a measured
    absence rather than a missing field."""
    card = _sharp()
    card.pop("evidence")                  # as a card built elsewhere would be
    line = potd.top_pick_line({"sport": "nfl", "pick": card, "runners_up": []})
    assert "None fair" not in line, line
    assert "sharp fair" in line, line


# ── it reads the files the builds actually write ────────────────────

def test_every_league_it_ranks_has_a_registered_board_file():
    """THE BUG THIS EXISTS FOR, found an hour after shipping. The writer
    opened `web/data/{sport}.json` for all five leagues, and two of those
    files do not exist — the NFL writes `recommendations.json` and MLB
    `mlb_recommendations.json`; only cfb, nba and wnba happen to be named
    after their league. So the day’s top pick could never have come from
    the two leagues at the top of SPORT_PRIORITY, and the missing files
    were swallowed as "a league this box does not publish"."""
    import launch
    for sport in potd.TOP_PICK_LEAGUES:
        assert sport in launch.BOARD_FILES, \
            f"{sport} is ranked for the day’s top pick and has no board file"


def test_the_writer_reads_the_registry_rather_than_naming_files_itself():
    """A second list of board paths is how one of them goes stale in
    silence. `BOARD_FILES` is the launcher’s own registry and every
    other reader of the boards already uses it."""
    import launch
    body = inspect.getsource(launch._write_day_top_pick)
    assert "BOARD_FILES[" in body, \
        "the day’s top pick no longer reads the board registry"
    assert 'f"{sport}.json"' not in body, \
        "the writer is building board paths from the league code again"


# ── the writer actually runs ────────────────────────────────────────

def _run_writer(tmp, boards, journal=()):
    """`launch._write_day_top_pick` against a temp ROOT and a temp ledger.

    Returns ``(payload, printed, claims)``. The PRINTED half is the point: that
    function wraps itself in a bare `except Exception` and prints a
    warning, so every failure inside it looks like a quiet log line — and
    four separate bugs reached production through it in one day, the last
    of them a NameError I introduced while fixing the third.
    """
    import contextlib
    import importlib
    import io
    import json as _json
    import launch
    from engine import ledger as _ledger

    web = os.path.join(tmp, "web", "data")
    os.makedirs(web, exist_ok=True)
    for sport, payload in boards.items():
        rel = launch.BOARD_FILES[sport]
        path = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh)

    old_root, old_db = launch.ROOT, _ledger.DEFAULT_DB
    launch.ROOT = __import__("pathlib").Path(tmp)
    _ledger.DEFAULT_DB = __import__("pathlib").Path(tmp) / "ledger.db"
    try:
        with _ledger.connect() as conn:
            for row in journal:
                conn.execute(
                    "INSERT INTO bets (ts, sport, date, player, market, side, "
                    "line, odds, status, category) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    row)
            conn.commit()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launch._write_day_top_pick()
        out = os.path.join(web, "day_top_pick.json")
        payload = _json.load(open(out)) if os.path.exists(out) else None
        import datetime as _dt
        with _ledger.connect() as conn:
            claims = _ledger.top_pick_claims(conn, _dt.date.today().isoformat())
        return payload, buf.getvalue(), claims
    finally:
        launch.ROOT, _ledger.DEFAULT_DB = old_root, old_db
        importlib.invalidate_caches()


def test_the_writer_writes_a_file_and_says_nothing():
    """END TO END, WHICH NOTHING DID BEFORE. Every other test in this
    file exercises the chooser; the function that feeds it opened the
    wrong paths twice and then raised NameError on a variable I deleted,
    and each failure printed a warning nobody was reading. A test that
    calls it is the one that catches all three shapes."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    card = {"player": "KC ML", "team": "KC", "market": "moneyline",
            "kind": "game", "odds": -130, "sharp_anchored": True,
            "sharp_fair": 0.60, "fair_prob": 0.60, "evidence": "sharp"}
    with tempfile.TemporaryDirectory() as tmp:
        payload, printed, claims = _run_writer(
            tmp, {"nfl": {"pick_of_the_day": {"date": today, "pick": card}}},
            journal=[(today + "T00:00:00", "nfl", today, "KC", "moneyline",
                      "OVER", 0.5, -130, "open", "potd")])
    assert payload is not None, f"no file was written; it printed: {printed!r}"
    assert "⚠️" not in printed, printed
    assert payload["sport"] == "nfl", payload
    assert payload["pick"]["player"] == "KC ML", payload
    # AND THE CLAIM WAS LOGGED. The file is overwritten every cycle, so
    # this row is the only thing that survives the day — a writer that
    # published the headline without recording it would look completely
    # healthy and lose the history anyway.
    assert len(claims) == 1, claims
    assert claims[0]["sport"] == "nfl" and claims[0]["player"] == "KC", claims


def test_the_writer_reaches_the_nfl_and_mlb_board_files():
    """The two whose files are not named after their league. This is the
    bug of commit a0686df stated as a behaviour rather than as a source
    check — the writer opened web/data/{sport}.json, so these two were
    invisible and the census called them simply absent."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    card = {"player": "LAA ML", "team": "LAA", "market": "moneyline",
            "kind": "game", "odds": -120, "sharp_anchored": True,
            "sharp_fair": 0.58, "fair_prob": 0.58, "evidence": "sharp"}
    with tempfile.TemporaryDirectory() as tmp:
        payload, printed, claims = _run_writer(
            tmp, {"mlb": {"pick_of_the_day": {"date": today, "pick": card}}},
            journal=[(today + "T00:00:00", "mlb", today, "LAA", "moneyline",
                      "OVER", 0.5, -120, "open", "potd")])
    assert payload is not None, printed
    assert payload["sport"] == "mlb", payload


def test_the_headline_is_logged_when_it_changes_and_not_when_it_repeats():
    """The history that `day_top_pick.json` destroys every cycle. One row
    per change: a re-quote is the same claim at a new number, and
    `odds_history` is already the price tape."""
    from engine import ledger
    conn = ledger.connect(":memory:")
    card = {"player": "KC ML", "team": "KC", "market": "moneyline",
            "kind": "game", "odds": -130, "evidence": "sharp"}
    top = {"date": TODAY, "sport": "nfl", "pick": card}
    assert ledger.record_top_pick_claim(conn, top) == 1
    assert ledger.record_top_pick_claim(conn, top) == 0, "repeat was logged"
    repriced = {"date": TODAY, "sport": "nfl", "pick": dict(card, odds=-145)}
    assert ledger.record_top_pick_claim(conn, repriced) == 0, \
        "a re-quote is the same claim"
    moved = {"date": TODAY, "sport": "mlb",
             "pick": dict(card, player="LAA ML", team="LAA")}
    assert ledger.record_top_pick_claim(conn, moved) == 1
    assert len(ledger.top_pick_claims(conn, TODAY)) == 2


def test_a_day_with_no_top_pick_is_logged_as_a_claim_too():
    """"No top pick today" is what the page said. A log that recorded
    only the days with a pick would answer "how does the Top Pick do"
    without ever mentioning the days it declined to name one."""
    from engine import ledger
    conn = ledger.connect(":memory:")
    assert ledger.record_top_pick_claim(
        conn, {"date": TODAY, "sport": "", "pick": None,
               "note": "no league had a pick in the band"}) == 1
    rows = ledger.top_pick_claims(conn, TODAY)
    assert len(rows) == 1 and rows[0]["sport"] == "", rows
    assert "no league" in rows[0]["note"], rows


def test_the_claim_log_never_raises_into_the_cycle():
    """A history that cannot be written must not take down the page it is
    a history of."""
    from engine import ledger

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("disk gone")

    assert ledger.record_top_pick_claim(Broken(), {"date": TODAY}) == 0
    assert ledger.top_pick_claims(Broken(), TODAY) == []
    assert ledger.record_top_pick_claim(
        ledger.connect(":memory:"), {"pick": None}) == 0, "a dateless claim"


# ── it must stay a comparison ───────────────────────────────────────

def test_the_cross_league_chooser_invents_no_bar_of_its_own():
    """Every threshold this reasons about has to be one `potd` already
    measured. A cross-sport constant introduced here would be a second
    set of numbers to keep honest, fitted to nothing."""
    body = inspect.getsource(potd.day_top_pick)
    assert "rank_key" in body, "the shared comparator is no longer used"
    # THE FIRST VERSION OF THIS ASSERTION WAS VACUOUS — it ended in
    # `or "rank_key" in body`, which the line above had just proved, so
    # it could never fail. What it was reaching for is checkable
    # directly: the band this publishes must be potd's own constants,
    # not numbers typed again here.
    out = potd.day_top_pick({}, TODAY)
    assert out["band"] == [potd.MIN_ODDS, potd.effective_max_odds()], \
        out["band"]
    assert out["min_ev"] == potd.MIN_EV, out["min_ev"]


def test_an_empty_slate_is_a_fact_rather_than_an_exception():
    got = potd.day_top_pick({}, TODAY)
    assert got["pick"] is None
    assert got["note"], got


def test_the_payload_says_how_many_leagues_there_were_supposed_to_be():
    """`leagues_seen` alone cannot tell a complete answer from a partial
    one, and "nothing cleared in ANY league" is only true of a complete
    one. Ethan's 2026-09-16 board shipped a census of three leagues out
    of five and the page spoke for all five."""
    out = potd.day_top_pick({"cfb": {}, "nba": {}, "wnba": {}}, "2026-09-16")
    assert out["leagues_seen"] == 3
    assert out["leagues_expected"] == len(potd.TOP_PICK_LEAGUES) == 5


def test_a_league_handed_in_as_none_is_censused_rather_than_vanishing():
    """The shape `launch._write_day_top_pick` now hands over when a board
    file is missing. It used to `continue`, so the league never entered
    `boards`, never reached the loop, and left no trace anywhere."""
    out = potd.day_top_pick({"nfl": None, "cfb": {}}, "2026-09-16")
    assert out["leagues_seen"] == 2
    assert any("nfl" in k and "no board" in k for k in out["census"]), \
        out["census"]


def test_the_writer_never_drops_a_league_without_recording_it():
    """THE ROOT CAUSE OF ETHAN'S 2026-09-16 SCREENSHOT, pinned where it
    happened. `launch._write_day_top_pick` opened each board file and,
    on FileNotFoundError, ran a bare `continue` — so that league never
    entered `boards`, never reached `day_top_pick`'s loop, and left no
    census entry. The page then wrote "Nothing cleared the bar in any
    league today" from a census of three leagues out of five.

    ASKED OF THE SOURCE because the function opens real files, reads the
    ledger and writes into web/data; a test that ran it would be testing
    this box. What can be asked cheaply is the shape: that branch has to
    put SOMETHING into `boards` for the league, and `None` is enough
    because `day_top_pick` tallies anything that is not a dict.
    """
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parents[1] / "launch.py").read_text()
    i = src.index("except FileNotFoundError:")
    block = src[i:i + 1200]
    # Up to the next `except` or the end of the try, whichever is first.
    end = block.find("except Exception")
    if end > 0:
        block = block[:end]
    assert "boards[sport]" in block, (
        "the missing-board branch does not record the league \u2014 it will "
        "vanish from the census again:\n" + block)
    body = [ln.strip() for ln in block.splitlines()[1:]
            if ln.strip() and not ln.strip().startswith("#")]
    assert "continue" not in body, (
        "the bare `continue` is back; a dropped league leaves no trace")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
