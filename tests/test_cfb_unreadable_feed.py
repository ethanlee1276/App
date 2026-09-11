"""An empty CFB board has two causes and the build recorded neither.

#82 asks what happened on 2026-08-29, the opening Saturday of the
college season, when the page showed nothing. It cannot be answered —
not because the evidence is hard to read, but because it was never
written down.

`cfbdata.parse_scoreboard` drops any event whose two competitors do not
both carry a team abbreviation, and it drops them without a word. So
`games == []` is the same value for two opposite situations:

    ESPN listed no games      -> the league's state. Nothing is wrong.
    ESPN listed sixty games   -> our parser is broken. Everything is.

Those need opposite responses, and the board could not tell them apart,
so it picked one and asserted it. That is this codebase's recurring
failure: a distinction that exists in the world, collapsed in the data,
then read back off as a finding.

ONE INTEGER FIXES IT — the event count taken BEFORE the filter runs.
This file pins that it is taken, published on the payload, said in the
status, said in the journal, and drawn on the page. Five places, because
the last time this happened the reason travelled four of the five steps
and stopped at the one a person actually looks at.

Nothing here is a theory about what happened on the droplet. The point
is that the next occurrence answers itself.

Run directly: `python3 tests/test_cfb_unreadable_feed.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- the premise, measured rather than assumed ----------------------------
def test_an_event_missing_an_abbreviation_is_discarded():
    from engine.sources import cfbdata
    payload = {"events": [{"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "", "displayName": "A"}},
        {"homeAway": "away", "team": {"abbreviation": "B", "displayName": "B"}},
    ]}]}]}
    assert cfbdata.parse_scoreboard(payload, {}) == []


def test_and_the_return_value_cannot_tell_you_it_happened():
    """Identical to an empty schedule. This is the whole bug."""
    from engine.sources import cfbdata
    assert cfbdata.parse_scoreboard({"events": []}, {}) == []


def test_a_well_formed_event_survives():
    from engine.sources import cfbdata
    payload = {"events": [{"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "BAMA",
                                      "displayName": "Alabama"}},
        {"homeAway": "away", "team": {"abbreviation": "UGA",
                                      "displayName": "Georgia"}},
    ]}]}]}
    assert len(cfbdata.parse_scoreboard(payload, {})) == 1


# --- the count is taken before the filter ---------------------------------
def test_the_build_reads_the_raw_payload_not_just_the_parsed_games():
    src = _src("cfb_build.py")
    assert "board = cfbdata.fetch_scoreboard(args.date)" in src
    assert 'listed = len(board.get("events") or [])' in src


def test_a_count_after_the_filter_would_be_the_same_number_as_games():
    """Guards the one way this fix gets silently undone: someone
    "simplifies" it to count the parsed list."""
    assert "listed = len(games)" not in _src("cfb_build.py")


# --- the payload carries it -----------------------------------------------
def test_the_board_publishes_both_numbers():
    assert 'out["feed"] = {"listed": listed, "kept": len(games)}' \
        in _src("cfb_build.py")


def test_published_and_not_merely_logged():
    """A log line is gone by the time anyone asks, and #82 is being asked
    the day after — exactly when the journal has rolled."""
    src = _src("cfb_build.py")
    at = src.index('out["feed"]')
    assert "Published, not merely printed" in src[max(0, at - 400):at]


# --- the status says which cause it was -----------------------------------
def test_there_is_a_distinct_status_for_a_feed_we_could_not_read():
    assert 'status="feed unreadable"' in _src("cfb_build.py")


def test_it_is_chosen_before_the_no_games_branch():
    """Order matters: with games listed, "no games today" and "offseason"
    are both false statements about the league."""
    src = _src("cfb_build.py")
    assert src.index("if listed:") < src.index('status="no games today"')


def test_the_note_says_the_fault_is_ours():
    assert "fault on our side, not an empty" in _src("cfb_build.py")


# --- the journal says it --------------------------------------------------
def test_refresh_cfb_has_a_word_for_the_third_cause():
    src = _src("launch.py")
    assert 'unreadable = ok and "listed, 0 readable" in tail' in src
    assert "EMPTY BOARD — feed listed games, parser read none" in src


def test_it_does_not_fall_through_to_refreshed():
    """The exact failure #82 records: exit 0, board written, and the
    journal saying "refreshed" while the board is empty."""
    src = _src("launch.py")
    at = src.index('unreadable = ok and "listed, 0 readable" in tail')
    word = src[at:src.index("return ok", at)]
    assert word.index("unreadable else") < word.index('"refreshed"')


def test_the_phrase_matched_is_one_the_build_actually_prints():
    """The half of this pairing that rots. Both sides, one test."""
    assert "listed, 0 readable" in _src("cfb_build.py")


# --- the page says it -----------------------------------------------------
def _empty_state():
    src = _src("web", "js", "app.js")
    at = src.index('el.innerHTML = state.data.status === "unreachable"')
    return src[at:src.index("// Nothing else to show", at)]


def test_the_empty_state_has_a_branch_for_it():
    assert 'state.data.status === "feed unreadable"' in _empty_state()


def test_it_does_not_tell_a_reader_nothing_is_scheduled():
    body = _empty_state()
    branch = body[body.index('"feed unreadable"'):]
    branch = branch[:branch.index('state.data.status === "not built"')]
    assert "Nothing is scheduled" not in branch
    assert "Games are on today" in branch


def test_the_page_says_the_fault_is_ours():
    assert "fault on our\n       side, not an empty slate" in _empty_state()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
