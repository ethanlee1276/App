"""An FBS host against a team with no abbreviation was a deleted game.

Ethan, 2026-08-31, on college football's opening weekend: "there was one
instance on saturday where i did see one live game but that was it.
there was also no picks."

One game, on the biggest Saturday of the year.

`parse_scoreboard` discarded any event whose two competitors did not
BOTH carry an `abbreviation`:

    if not home or not away or not home["abbr"] or not away["abbr"]:
        continue

ESPN's FBS scoreboard (groups=80) returns FBS hosts against non-FBS
visitors, and those visitors routinely arrive with a displayName and an
id but no abbreviation — they are not FBS teams, so the FBS feed carries
them thinly. Opening weekend is when that pairing is most concentrated:
most of the slate is FBS-vs-FCS. So the filter deleted most of the
Saturday and left the few FBS-vs-FBS games behind.

Nothing failed. No exception, no empty feed, no bad key — a real payload
came in, most of it was dropped inside a loop, and the board published
what survived as though that were the schedule. The `listed` vs `kept`
counter added the day before exists precisely to make this visible; this
is the fault it was built to catch.

THE FIX IS NOT TO STOP FILTERING. It is that an abbreviation is not the
only way to name a team. `espn:{id}` is already this codebase's fallback
key (`ingest.ESPN_KEY_PREFIX`, `cfbfastr`), so a side named that way
joins the same lookups as any other. Only an event with neither an
abbreviation nor an id is genuinely unidentifiable, and that still goes.

Run directly: `python3 tests/test_cfb_fcs_opponent.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.sources.cfbdata import _team_key, parse_scoreboard


def _ev(home, away):
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "team": home},
        {"homeAway": "away", "team": away}]}]}


FBS = {"abbreviation": "BAMA", "displayName": "Alabama", "id": "333"}
#: What an FCS visitor looks like in the FBS-group payload: named and
#: identified, but with no abbreviation.
FCS = {"abbreviation": "", "displayName": "Mercer", "id": "2579"}
NAMELESS = {"abbreviation": "", "displayName": "", "id": ""}


# --- the key ---------------------------------------------------------------
def test_an_abbreviation_is_used_when_there_is_one():
    assert _team_key(FBS) == "BAMA"


def test_the_espn_id_carries_a_side_with_no_abbreviation():
    assert _team_key(FCS) == "espn:2579"


def test_it_uses_the_prefix_the_rest_of_the_codebase_speaks():
    from engine.ingest import ESPN_KEY_PREFIX
    assert _team_key(FCS).startswith(ESPN_KEY_PREFIX)


def test_a_side_with_neither_has_no_key():
    assert _team_key(NAMELESS) == ""
    assert _team_key({}) == ""


# --- the game survives -----------------------------------------------------
def test_an_fbs_host_against_an_unabbreviated_visitor_is_kept():
    """THE ONE THAT WAS BEING DELETED, and on opening weekend that is
    most of the slate."""
    got = parse_scoreboard({"events": [_ev(FBS, FCS)]}, {})
    assert len(got) == 1, got


def test_the_kept_game_names_both_sides():
    g = parse_scoreboard({"events": [_ev(FBS, FCS)]}, {})[0]
    assert g["home"] == "BAMA"
    assert g["away"] == "espn:2579"
    assert g["away_name"] == "Mercer"


def test_a_genuinely_unidentifiable_side_is_still_dropped():
    """The filter is not removed, only stopped from firing on a team it
    could have named."""
    assert parse_scoreboard({"events": [_ev(FBS, NAMELESS)]}, {}) == []


def test_an_ordinary_matchup_is_unchanged():
    other = {"abbreviation": "UGA", "displayName": "Georgia", "id": "61"}
    g = parse_scoreboard({"events": [_ev(FBS, other)]}, {})[0]
    assert (g["home"], g["away"]) == ("BAMA", "UGA")


def test_a_saturday_of_mixed_matchups_keeps_them_all():
    """The shape of the bug at slate scale: before the fix a card of
    mostly FBS-vs-FCS came back nearly empty."""
    fcs2 = {"abbreviation": "", "displayName": "Austin Peay", "id": "2046"}
    uga = {"abbreviation": "UGA", "displayName": "Georgia", "id": "61"}
    events = [_ev(FBS, FCS), _ev(uga, fcs2), _ev(FBS, uga)]
    assert len(parse_scoreboard({"events": events}, {})) == 3


# --- the key is not the label ----------------------------------------------
def test_the_label_reads_as_names_not_as_an_espn_id():
    """`espn:2579` is a fine lookup key and a poor thing on a card."""
    g = parse_scoreboard({"events": [_ev(FBS, FCS)]}, {})[0]
    assert g["label"] == "Mercer @ Alabama"


def test_the_feeds_own_short_name_still_wins_when_present():
    ev = _ev(FBS, FCS)
    ev["shortName"] = "MER @ ALA"
    assert parse_scoreboard({"events": [ev]}, {})[0]["label"] == "MER @ ALA"


# --- and the counter that would have shown it ------------------------------
def test_the_build_still_counts_what_the_feed_listed():
    """`listed` vs `kept` is what makes a silent in-loop drop visible.
    This bug is the reason that counter exists."""
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'listed = len(board.get("events") or [])' in src
    assert 'out["feed"] = {"listed": listed, "kept": len(games)}' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
