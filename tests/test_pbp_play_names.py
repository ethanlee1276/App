""""+19 reception" does not say who caught it.

Ethan, 2026-09-10: "lets make the play by play look better to. we should
show what player go what reception or yard you know what i mean, jot just
+19 reception." He was reading `SEA · Pass Reception +19 · 2nd & 7` — a
category, a number and a situation, with nobody in it.

WHY THE NAME WAS MISSING, and it is not an oversight. A basketball play
carries `participants[].athlete.id`, which `_athletes` resolves against
the box score — that is how a hoops row prints a name. The probe Ethan
ran against a live NFL game found no athlete id anywhere on a football
play; what it has is `teamParticipants`, a list of two, keyed by TEAM. So
on this side of the feed exactly one field links a play to a person: the
sentence ESPN wrote.

THE FIRST CUT SHIPPED THAT SENTENCE AND WAS WRONG TO. `docs/LAUNCH.md`
says of ESPN: "Assume no right", and this repo already had a test —
`test_prose_never_reaches_a_deep_file` — holding the module to composing
rows from the numbers beside the prose. Ethan drew the line himself: "Ok
dont use there exact sentence then. We can still use that idea tho too
push free information the public can view."

That line is the right one and it is the line the law draws: who caught a
pass is a fact, free to anyone; the paragraph about it is ESPN's writing.

SO IT IS A ROSTER MATCH, NOT A PARSE. `_football_players` is handed every
player in this game's box score — structured athlete records — and asks
which of that CLOSED LIST the sentence mentions. Nothing is extracted
from prose and nothing from it is kept: the input is a list of people
already in the payload as data, the output is which of them were on the
play, and the sentence is discarded in the same breath. A name that is
not on the team sheet cannot come out of the function, and two players
sharing a surname and an initial produce no name at all.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources.espnplays import (_football_players, _football_row,
                                      football_drives, football_plays)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
SRC = open(os.path.join(ROOT, "engine", "sources", "espnplays.py"),
           encoding="utf-8").read()

ROSTER = ("Sam Darnold", "Jaxon Smith-Njigba", "Kenneth Walker III",
          "Christian Gonzalez")
SAID = ("S.Darnold pass short right to J.Smith-Njigba for 19 yards "
        "(tackle by C.Gonzalez)")


def _payload(text=SAID, roster=ROSTER, event="Pass Reception"):
    return {
        "boxscore": {"players": [{"statistics": [{"athletes": [
            {"athlete": {"id": str(i), "displayName": n}}
            for i, n in enumerate(roster, 1)]}]}]},
        "drives": {"previous": [{
            "id": "d1",
            "team": {"abbreviation": "SEA", "displayName": "Seattle Seahawks"},
            "plays": [{"id": "p1", "statYardage": 19, "type": {"text": event},
                       "start": {"down": 2, "distance": 7}, "text": text}]}]}}


# --- who was on the play ----------------------------------------------------
def test_the_row_names_the_thrower_and_the_catcher():
    assert football_plays(_payload(), "nfl")[0]["players"] == \
        ["Sam Darnold", "Jaxon Smith-Njigba"]


def test_a_spelled_out_name_resolves_as_well_as_an_abbreviated_one():
    """College feeds write them out; the NFL abbreviates. Matching only
    the abbreviated form would have left every college play nameless."""
    got = _football_players(
        "Sam Darnold pass short right to Jaxon Smith-Njigba for 19 yards",
        ROSTER)
    assert got == ["Sam Darnold", "Jaxon Smith-Njigba"]


def test_a_rush_resolves_to_the_one_man_who_carried_it():
    assert _football_players("K.Walker III right guard for 5 yards", ROSTER) \
        == ["Kenneth Walker III"]


def test_they_come_back_in_the_order_the_play_ran():
    assert _football_players("J.Smith-Njigba 19 yd catch from S.Darnold",
                             ROSTER) == ["Jaxon Smith-Njigba", "Sam Darnold"]


def test_a_tackler_in_brackets_is_not_credited_with_the_carry():
    """"(tackle by C.Gonzalez)" would otherwise read as a second
    participant and the row would draw him beside the runner."""
    assert "Christian Gonzalez" not in _football_players(
        "K.Walker III right guard for 5 yards (tackle by C.Gonzalez)", ROSTER)


# --- what it refuses --------------------------------------------------------
def test_a_name_not_on_the_team_sheet_can_never_come_out():
    """The whole safety property. The input is a closed list."""
    assert _football_players("T.Brady pass to R.Gronkowski for 19 yards",
                             ROSTER) == []


def test_two_players_sharing_a_surname_and_an_initial_yield_neither():
    """ESPN abbreviates the first name, so "J.Smith" is genuinely
    ambiguous. A missing name reads as a plainer line; a wrong name reads
    exactly like a right one."""
    assert _football_players("J.Smith rushed for 3 yards",
                             ("Jaxon Smith", "Jamal Smith")) == []


def test_a_surname_inside_a_longer_one_does_not_match():
    assert _football_players("J.Browning sacked for -7 yards",
                             ("Jaylen Brown",)) == []


def test_a_play_with_no_sentence_leaves_the_key_off_rather_than_empty():
    """The rule `spot` follows on this row: a reader can tell "nobody
    resolved" from "an empty list"."""
    row = _football_row({"id": "p", "type": {"text": "Rush"},
                         "start": {}}, "SEA", roster=ROSTER)
    assert "players" not in row


def test_an_empty_roster_resolves_nobody_and_does_not_raise():
    assert _football_players(SAID, ()) == []
    assert _football_players(SAID, None) == []


# --- the sentence is not kept -----------------------------------------------
def test_no_part_of_espns_wording_reaches_the_row():
    """The rule `test_prose_never_reaches_a_deep_file` guards and the
    module header states. Names are facts; the paragraph is theirs."""
    row = football_plays(_payload(), "nfl")[0]
    flat = " ".join(str(v) for v in row.values())
    for word in ("pass short right", "tackle by", "for 19 yards"):
        assert word not in flat, f"ESPN's wording is on the row ({word})"
    assert "text" not in row and "desc" not in row


def test_the_deep_file_writer_still_carries_no_prose():
    """Belt and braces across the module boundary — the drive list is
    what gets written to disk and served."""
    doc = football_drives(_payload(), "nfl")
    flat = str(doc)
    assert "pass short right" not in flat and "tackle by" not in flat


def test_both_readers_resolve_against_the_same_roster():
    """The card's last-six strip and the page's drive list may not
    drift."""
    pay = _payload()
    assert football_plays(pay, "nfl")[0]["players"] == \
        football_drives(pay, "nfl")[0]["plays"][0]["players"]


def test_the_roster_is_built_once_per_payload_not_once_per_play():
    """`_athletes` walks the whole box score; a hundred and fifty plays a
    game is the expensive way to answer the same question."""
    for fn in ("def football_plays(", "def football_drives("):
        i = SRC.index(fn)
        block = SRC[i:SRC.index("\ndef ", i + 1)]
        assert block.count("_athletes(payload)") == 1
        assert block.index("_athletes(payload)") < block.index("_football_row(")


# --- the page draws it ------------------------------------------------------
def _row_fn():
    i = APP.index("const footballRow = (p) =>")
    return APP[i:APP.index("\n  };", i)]


def test_the_play_line_prints_the_names():
    assert "p.players" in _row_fn(), "the row still cannot name a player"


def test_a_pass_gets_an_arrow_and_nothing_else_does():
    """The arrow is the fact of a completion. On a penalty or a sack the
    row cannot vouch for a relationship, so it does not draw one."""
    fn = _row_fn()
    assert 'names.length === 2 && pass ? names.join(" → ")' in fn
    assert 'names.join(" · ")' in fn


def test_the_names_are_escaped_like_every_other_feed_string():
    fn = _row_fn()
    assert "map(escapeHtml)" in fn
    assert "${p.players}" not in fn


def test_the_old_line_survives_when_nobody_resolved():
    """Most of what this touches is a feed that resolved fine yesterday;
    a play with no names must not lose its category and its yards."""
    fn = _row_fn()
    assert 'who ? `<b>${who}</b> · ` : ""' in fn
    assert "escapeHtml(p.event)" in fn and "escapeHtml(yds)" in fn


def test_the_situation_and_the_flags_still_ride_the_row():
    fn = _row_fn()
    assert "escapeHtml(dd)" in fn and "${flag}" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
