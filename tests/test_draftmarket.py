"""Rookies on the draft board — the market's call, labelled as the market's.

THE DEFECT THIS CLOSES. `build_draft_kit` projects last season's usage
forward, so a player with no usage rows was not on the board, and the
board's own notes disclosed it: "knows nothing about rookies (they are
not on it)". That was a fair disclosure while the board was a reading
aid. It stopped being only a disclosure when the mock draft simulator
began drafting FROM the board — `app.js` builds its pool from
`kit.board` — because then no rookie could be taken in a simulated draft
by anybody, ever. A twelve-team mock in August with no rookie in the
first four rounds is not a rehearsal of the draft you are about to do.

WHAT MAY HONESTLY BE SAID about a player we have never seen play is less
than a projection and more than nothing: the market drafts him at a rank,
and we know what OUR OWN board projects for the players around that rank.
So the placement is an interpolation over our numbers, indexed by the
market's opinion, and every row says so.

Sleeper is denied by this container's network policy, so these run
against fixtures shaped like its players blob — the same way
`fantasy_ranks` was built and is tested. The shape is fixed by
`fantasy_ranks.from_sleeper`, which is the only reader.

    python3 tests/test_draftmarket.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.draftmarket import (MARKET_DEPTH, MIN_ANCHORS, place_missing,
                                summary)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _board(pos="RB", n=8, top=18.0, step=1.5, rec_top=6.0, rec_step=0.4):
    return [{"player": f"Vet {pos}{i}", "team": "AAA", "position": pos,
             "proj": top - step * i, "rec_pg": rec_top - rec_step * i,
             "games": 14, "basis": "xfp"} for i in range(n)]


def _sleeper(first, last, pos, rank, exp=4, team="AAA"):
    return {"first_name": first, "last_name": last, "position": pos,
            "team": team, "search_rank": rank, "years_exp": exp}


def _blob(board, extras=()):
    """Our own board ranked in order, plus whatever the market adds."""
    out = {}
    for i, r in enumerate(board, 1):
        f, _, l = r["player"].partition(" ")
        out[f"p{i}"] = _sleeper(f, l, r["position"], i)
    for j, e in enumerate(extras):
        out[f"x{j}"] = e
    return out


# --- the placement itself ------------------------------------------------------
def test_a_player_the_market_drafts_and_we_cannot_see_gets_placed():
    board = _board()
    rows = place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4, exp=0)]))
    assert len(rows) == 1
    r = rows[0]
    assert r["player"] == "Rookie Back"
    assert r["rookie"] is True
    assert r["basis"] == "market" and r["source"] == "market"
    assert r["games"] == 0, "a placed player must not claim games he did not play"


def test_the_projection_is_ours_read_at_the_markets_rank():
    """Not the market's number — the market publishes a RANK, not points.
    Placed between our 4th and 5th ranked backs, he must land between
    their projections and nowhere else."""
    board = _board(n=8, top=18.0, step=1.5)   # 18.0, 16.5, 15.0, 13.5, 12.0 ...
    rows = place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4.5, exp=0)]))
    lo, hi = board[4]["proj"], board[3]["proj"]   # ranks 5 and 4
    assert lo < rows[0]["proj"] < hi, \
        f"{rows[0]['proj']} is not between our own ranks 4 and 5 ({lo}..{hi})"


def test_it_never_extrapolates_past_what_we_have_measured():
    """A rookie the market likes more than anyone we can see is placed
    LEVEL with our best, not above him. We have no evidence for "better
    than the best thing we have ever measured", and inventing the shape of
    a curve past its data is how a draft board grows a number nobody can
    defend."""
    board = _board(n=8, top=18.0, step=1.5)
    rows = place_missing(board, _blob(board, [
        _sleeper("Hyped", "Rookie", "RB", 0.5, exp=0),
        _sleeper("Forgotten", "Rookie", "RB", 500, exp=0)]))
    got = {r["player"]: r["proj"] for r in rows}
    assert got["Hyped Rookie"] == board[0]["proj"], "extrapolated above our best"
    assert got["Forgotten Rookie"] == board[-1]["proj"], "extrapolated below our worst"


def test_a_position_we_can_barely_see_places_nobody():
    """Two points define a line; below MIN_ANCHORS we would be drawing a
    projection curve through almost nothing and calling the result a
    number."""
    thin = _board(pos="TE", n=MIN_ANCHORS - 1)
    rows = place_missing(thin, _blob(thin, [
        _sleeper("Mystery", "Te", "TE", 2, exp=0)]))
    assert rows == [], f"placed a player off {MIN_ANCHORS - 1} anchors"


def test_the_market_depth_stops_before_the_list_becomes_noise():
    board = _board(n=8)
    deep = _sleeper("Practice", "Squad", "RB", 9999, exp=1)
    assert place_missing(board, _blob(board, [deep]), depth=5) == []
    assert len(place_missing(board, _blob(board, [deep]))) == 1
    assert MARKET_DEPTH > 192, \
        "shallower than a 12-team 16-round draft — real picks would be missed"


def test_someone_already_on_our_board_is_never_duplicated():
    """Measured against real data, 2026-08-20: seven of eight names in the
    first fixture were 2025 rookies who by now HAVE usage rows, and all
    seven were correctly skipped. The dedupe is the difference between
    adding a rookie class and doubling a board."""
    board = _board()
    f, _, l = board[2]["player"].partition(" ")
    rows = place_missing(board, _blob(board, [_sleeper(f, l, "RB", 3, exp=0)]))
    assert rows == [], "a player we already project was placed a second time"


# --- what a placed row may and may not claim -----------------------------------
def test_usage_columns_stay_empty_because_there_is_no_usage():
    """None, not zero. Zero reads as "measured zero carries" in a column
    headed with real measurements; None is an absence and the page prints
    a dash."""
    board = _board()
    r = place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4, exp=0)]))[0]
    for field in ("targets_pg", "carries_pg", "pass_att_pg"):
        assert r[field] is None, f"{field} claims a measurement: {r[field]!r}"


def test_receptions_are_carried_because_a_scoring_format_needs_them():
    """THE ONE EXCEPTION, and the bug it prevents. `_mockScoreBoard`
    computes a TE-premium bonus as `bonus x rec_pg` and reads a missing
    value as zero — so a placed tight end would be scored as though he
    catches nothing, in exactly the format where catching is the point.
    Measured in Chromium against the real board: with rec_pg carried the
    placed TEs move 6.9 -> 8.5 VORP in te_prem and pass a receiver; with
    it None they stayed at 6.9 while every measured TE rose."""
    board = _board(pos="TE", n=8, top=14.0, step=0.8,
                   rec_top=6.0, rec_step=0.4)
    r = place_missing(board, _blob(board, [
        _sleeper("Rookie", "Te", "TE", 4, exp=0)]))[0]
    assert isinstance(r["rec_pg"], (int, float)), \
        "rec_pg is absent — TE premium will score this player at zero catches"
    assert board[4]["rec_pg"] <= r["rec_pg"] <= board[2]["rec_pg"]
    assert round(r["rec_pg"], 2) == r["rec_pg"], "unrounded float into the payload"


def test_a_player_who_is_not_a_rookie_is_not_called_one():
    """Missing a whole season to injury produces the same empty board row
    as being new, and the two are not the same sentence."""
    board = _board()
    rows = place_missing(board, _blob(board, [
        _sleeper("Missed", "Theyear", "RB", 4, exp=6)]))
    assert rows[0]["rookie"] is False


# --- the failure modes that must stay quiet ------------------------------------
def test_an_unreachable_market_leaves_the_board_exactly_as_it_was():
    """Sleeper being down must cost the rookie class, never the board."""
    board = _board()
    assert place_missing(board, None) == []
    assert place_missing(board, {}) == []
    assert place_missing([], _blob(_board())) == []


def test_the_join_coverage_is_reported_so_a_silent_degrade_is_visible():
    """Every placement is interpolated between OUR players at THEIR market
    ranks, so it rests entirely on our names joining Sleeper's. A
    normaliser that stopped handling suffixes would not raise and would
    not empty the board — it would leave a few anchors per position and
    place rookies off a line through almost nothing."""
    board = _board()
    good = summary(place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4, exp=0)])))
    assert good["anchor_pct"] == 100.0 and good["anchored"] == len(board)
    # A blob that knows nobody we do: nothing placed, and the coverage says why.
    lonely = summary(place_missing(board, {
        "a": _sleeper("Rookie", "Back", "RB", 1, exp=0)}))
    assert lonely["placed"] == 0 and lonely["anchor_pct"] == 0.0
    assert lonely["board_seen"] == len(board), \
        "coverage does not record how much board went unmatched"


def test_summary_is_not_stale_from_a_previous_call():
    board = _board()
    summary(place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4, exp=0)])))
    after = summary(place_missing(board, None))
    assert after["board_seen"] == 0, "coverage carried over from an earlier build"


# --- the wiring, where the value actually lands --------------------------------
def test_placements_happen_before_replacement_level_is_computed():
    """The reason a missing rookie class distorts the board is not that
    the rookies are absent — it is that they move who is FREE. VORP is
    measured against the best player still on the wire, so eight backs
    drafted in the first ten rounds mean the tenth-round back our board
    called replacement was never available, and every RB's VORP was
    computed against a fiction. Measured on the real 2025 board: adding
    eight placements raised RB replacement 12.0 -> 12.9 and moved 141
    existing players' VORP."""
    src = _read("engine", "fantasy_draft.py")
    i = src.index("def build_draft_kit(")
    body = src[i:i + 3000]
    # The ASSIGNMENT, not the word: build_draft_kit's own docstring says
    # "replacement baselines" above any code, so a bare search for the
    # word finds the prose and passes whatever the code does.
    assert body.index("place_missing") < body.index("baselines: dict"), \
        "placement runs after replacement level — every VORP is then stale"


def test_a_placed_player_can_never_be_a_sleeper():
    """"Usage says buy" compares expected against actual. He has neither,
    so he is excluded explicitly rather than by the accident of carrying
    zeroes that happen to fail the gap test."""
    src = _read("engine", "fantasy_draft.py")
    i = src.index("sleepers = sorted(")
    assert '"market"' in src[i:i + 300], \
        "the sleepers filter no longer excludes market rows by name"


def test_the_page_says_whose_opinion_each_row_is():
    app = _read("web", "js", "app.js")
    assert "function marketLine(" in app, "the board never explains the placements"
    assert "dk-market" in app, "placed rows carry no marker"
    i = app.index("function marketLine(")
    body = app[i:app.index("\n}", i)]
    # Both states. An unreachable feed silently empties the rookie class
    # out of the mock draft's pool, which is worth saying out loud.
    assert "board_seen" in body, \
        "no branch for 'the feed never answered', which reads identically to 'nothing to add'"


def test_the_boards_own_note_no_longer_claims_rookies_are_absent():
    """It said "knows nothing about rookies (they are not on it)". Left
    standing beside a board that now lists them, that is simply false."""
    src = _read("engine", "fantasy_draft.py")
    i = src.index('"notes": [')
    notes = src[i:src.index("],", i)]
    assert "not on it" not in notes, "the note still says rookies are missing"
    assert "market" in notes, "the note never mentions where they came from"


# --- every surface that reads a board row -------------------------------------
# Putting rookies on the board put them on SIX other surfaces at once, and
# each had its own way of being wrong about a player who has never played.
# Found by walking every consumer rather than by waiting for a screenshot.


def test_a_placed_player_never_claims_he_averaged_zero():
    """ppg/xppg were 0.0 in the first cut, and zero is a MEASUREMENT.
    The calendar card prints "· {ppg} FPPG last season" for any non-null
    ppg, so a rookie would have been captioned as scoring nothing per game
    all last season. The dossier's stat() likewise drops a null row and
    prints a zero one — verified in Chromium: the market dossier now shows
    Proj/VORP/Tier and no "Last season" line at all, beside a veteran's
    that shows "Last season 24.1"."""
    board = _board()
    r = place_missing(board, _blob(board, [
        _sleeper("Rookie", "Back", "RB", 4, exp=0)]))[0]
    assert r["ppg"] is None and r["xppg"] is None, \
        "a zero here reads as 'measured zero points', which is a lie"
    app = _read("web", "js", "app.js")
    assert "r.ppg != null ?" in app, \
        "the calendar card no longer guards on null before captioning FPPG"


def test_the_live_draft_advice_says_whose_number_it_is():
    """The board discloses provenance in a sentence. The advice box has to
    do it in a chip, and it matters MORE there: somebody is on the clock
    with seconds to decide, and "Best available: +7.8" is a
    recommendation. `fantasy_pick.advice` therefore carries the flag
    through to every row it emits."""
    from engine import fantasy_pick
    board = [{"key": f"v{i}", "player": f"Vet {i}", "position": "RB",
              "vorp": 10.0 - i, "source": "usage"} for i in range(8)]
    board.append({"key": "rk", "player": "Rookie Runner", "position": "RB",
                  "vorp": 8.5, "source": "market"})
    order = ["v0", "v1", "rk"] + [f"v{i}" for i in range(2, 8)]
    ranks = {k: i + 1 for i, k in enumerate(order)}
    a = fantasy_pick.advice(
        {"settings": {"teams": 12, "rounds": 15}, "type": "snake",
         "draft_order": {"u1": 1}}, [], ranks, board, "u1",
        slots={"RB": 2, "WR": 2})
    flags = {r["player"]: r["market"] for r in a["board"]}
    assert flags.get("Rookie Runner") is True, "the flag is dropped in advice()"
    assert not any(v for k, v in flags.items() if k != "Rookie Runner"), \
        "measured players are being labelled as the market's call"
    assert a["market_rows"] == 1


def test_one_marker_reads_both_row_shapes():
    """Two different shapes reach the same chip: "Best available" reads
    raw kit rows (source:"market") and the advice box reads the server's
    rows (market:true). A marker that knew only one would go silently
    missing on whichever surface was refactored last."""
    app = _read("web", "js", "app.js")
    i = app.index("function mkt(")
    body = app[i:app.index("\n}", i)]
    assert 'source === "market"' in body and "market === true" in body, \
        "mkt() handles only one row shape"


def test_an_empty_game_log_does_not_promise_data_that_cannot_exist():
    """The old copy — "No game logs on this machine, the droplet and the
    laptop fill these in" — is true for a veteran whose logs live
    elsewhere and FALSE for a player who has never taken an NFL snap.
    Rookies are on this board now, so that promise would be made about
    players for whom no log exists anywhere. Both branches verified in
    Chromium."""
    app = _read("web", "js", "app.js")
    i = app.index("async function _ffDossierCharts(")
    body = app[i:i + 2200]
    assert 'source === "market"' in body, \
        "one empty state for two different silences"
    assert "has not played an NFL" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
