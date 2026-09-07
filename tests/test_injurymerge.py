"""Two injury feeds, one answer.

Left open by 91c270e in its own words: "the ESPN injury feed that powers
the Injuries page is a SECOND source of truth for the same question, and
nothing reconciles it against the roster. If a player is on the ESPN
board and not designated by Sleeper, the roster will still call him
active."

The site was answering one question two ways on two pages and leaving the
reader to notice. Cade Mays was the reported case and he is the fixture
below: Sleeper had him Active with no weekly designation, ESPN had him
Out with a knee.

THE SAFETY PROPERTY, which most of this file is about: the merge only
ever ADDS severity. It can move a player from available to out; it can
never move one from out to available. Pricing a player who does not play
is a loss every time, while withholding one who does play costs a single
missed bet — the two errors are not the same size, so the merge is not
symmetric.

A returned player therefore comes back not by one feed overruling the
other, but by NEITHER objecting: ESPN's newest filing becomes a clearance
notice, which contributes nothing, and Sleeper's own answer stands alone.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import injurymerge as im                          # noqa: E402
from engine import rosters as r                               # noqa: E402


def _sleeper(name, team="DET", pos="WR", status="Active", desig=None, part=""):
    return {"full_name": name, "team": team, "position": pos,
            "status": status, "injury_status": desig,
            "injury_body_part": part, "depth_chart_order": 1}


def _espn(name, status, team="Detroit Lions", **kw):
    row = {"team": team, "player": name, "status": status,
           "injury": kw.get("injury"), "date": kw.get("date", "2026-08-14T12:00Z")}
    row.update({k: v for k, v in kw.items() if k not in ("injury", "date")})
    return row


def _merge(sleeper_players, espn_rows):
    blob = {str(i): p for i, p in enumerate(sleeper_players)}
    return im.apply(r.build_rosters(blob), espn_rows)


def _find(payload, name, team="DET"):
    for p in payload["teams"][team]["players"]:
        if p["player"] == name:
            return p
    raise AssertionError(f"{name} not in the payload")


# --- the reported case ------------------------------------------------------
def test_the_espn_only_injury_now_reaches_the_roster():
    """Cade Mays. Sleeper: Active, no designation. ESPN: Out, knee. Before
    this module the roster called him available."""
    out = _merge([_sleeper("Cade Mays", pos="G")],
                 [_espn("Cade Mays", "Out", injury="Knee")])
    row = _find(out, "Cade Mays")
    assert row["unavailable"] is True
    assert row["status"] == "Out"
    assert row["injury"] == "Knee"
    assert row["injury_source"] == "espn"


def test_the_detail_comes_across_too():
    """"Out" says fade him. "Out — knee, right, back Week 3" says whether
    to expect him next week, which is a different bet."""
    out = _merge([_sleeper("Cade Mays", pos="G")],
                 [_espn("Cade Mays", "Out", injury="Knee", side="Right",
                        return_date="2026-09-20", comment="Did not practice")])
    row = _find(out, "Cade Mays")
    assert row["injury_side"] == "Right"
    assert row["return_date"] == "2026-09-20"
    assert row["injury_note"] == "Did not practice"


def test_espn_detail_wins_over_sleepers_bare_body_part():
    """Sleeper stores a word; ESPN stores a phrase. The longer one is the
    one that tells a reader something."""
    out = _merge([_sleeper("Hurt Guy", desig="Out", part="Hamstring")],
                 [_espn("Hurt Guy", "Out", injury="Hamstring strain")])
    assert _find(out, "Hurt Guy")["injury"] == "Hamstring strain"


# --- the one-directional rule -----------------------------------------------
def test_espn_cannot_clear_a_sleeper_out():
    """THE SAFETY PROPERTY. Sleeper says Out, ESPN says Questionable.
    The merge keeps him out — the optimistic direction is the one that
    costs money."""
    out = _merge([_sleeper("Already Out", desig="Out")],
                 [_espn("Already Out", "Questionable")])
    assert _find(out, "Already Out")["unavailable"] is True


def test_a_clearance_notice_contributes_nothing():
    """ESPN "Active" with no injury is a cleared-to-play item, not a
    designation. It must not read as something to act on — and it must
    not clear a Sleeper Out either."""
    out = _merge([_sleeper("Back Soon", desig="Out")],
                 [_espn("Back Soon", "Active", injury=None)])
    row = _find(out, "Back Soon")
    assert row["unavailable"] is True
    assert row["injury_sources"] == ["sleeper"], "a return notice was indexed"


def test_a_returned_player_is_cleared_by_neither_feed_objecting():
    """The other half of the same rule: once Sleeper drops the
    designation AND ESPN's newest filing is a return, nobody is saying he
    is hurt, so he is available. No feed overrules the other."""
    out = _merge([_sleeper("Back Soon")],
                 [_espn("Back Soon", "Active", injury=None)])
    assert _find(out, "Back Soon")["unavailable"] is False


def test_a_healthy_player_with_no_filing_is_untouched():
    out = _merge([_sleeper("Healthy Guy")], [])
    row = _find(out, "Healthy Guy")
    assert row["unavailable"] is False and row["questionable"] is False
    assert row["injury_sources"] == ["sleeper"]


def test_a_roster_level_flag_survives_a_missing_designation():
    """Injured Reserve carries no weekly word, and `severity` ranks the
    empty string at 0. Letting that talk us out of `unavailable` would
    un-injure everyone on IR."""
    out = _merge([_sleeper("On IR", status="Injured Reserve")], [])
    assert _find(out, "On IR")["unavailable"] is True


# --- disagreement, reported rather than resolved silently -------------------
def test_a_gap_is_not_a_disagreement():
    """Sleeper silent + ESPN filed is the case this module EXISTS for.
    Flagging it as a conflict would raise an alarm on every player the
    merge helps, which is most of them."""
    out = _merge([_sleeper("Cade Mays", pos="G")],
                 [_espn("Cade Mays", "Out", injury="Knee")])
    assert _find(out, "Cade Mays")["injury_conflict"] is False


def test_two_claims_on_opposite_sides_is_a_disagreement():
    """Both feeds spoke and they disagree about whether he plays. That is
    worth a reader's attention and is not averaged away."""
    out = _merge([_sleeper("Already Out", desig="Out")],
                 [_espn("Already Out", "Questionable")])
    assert _find(out, "Already Out")["injury_conflict"] is True
    assert out["injury_merge"]["conflicts"] == 1


def test_different_words_for_the_same_verdict_are_not_a_disagreement():
    """Questionable and Day-To-Day are one answer in two vocabularies."""
    out = _merge([_sleeper("Q Both Ways", desig="Questionable")],
                 [_espn("Q Both Ways", "Day-To-Day", injury="Ankle")])
    row = _find(out, "Q Both Ways")
    assert row["injury_conflict"] is False
    assert row["questionable"] is True and row["unavailable"] is False


def test_every_row_records_which_feeds_spoke():
    """Provenance is the reason a reader can trust the number. A merged
    availability with no source is indistinguishable from a guess."""
    out = _merge([_sleeper("Cade Mays", pos="G"), _sleeper("Healthy Guy")],
                 [_espn("Cade Mays", "Out", injury="Knee")])
    assert _find(out, "Cade Mays")["injury_sources"] == ["sleeper", "espn"]
    assert _find(out, "Healthy Guy")["injury_sources"] == ["sleeper"]


# --- the join, which is where a merge quietly rots ---------------------------
def test_an_unmappable_team_is_dropped_not_guessed():
    """ESPN writes full club names and the roster keys on abbreviations.
    A fuzzy match would attach a real injury to the wrong club, which is
    worse than missing it."""
    out = _merge([_sleeper("Cade Mays", pos="G")],
                 [_espn("Cade Mays", "Out", team="Nowhere United")])
    assert _find(out, "Cade Mays")["unavailable"] is False
    assert out["injury_merge"]["espn_filings"] == 0


def test_the_join_is_on_team_AND_name():
    """Two players share a name often enough that a name-only join moves
    one man's knee onto another's."""
    out = _merge([_sleeper("Josh Allen", team="BUF", pos="QB")],
                 [_espn("Josh Allen", "Out", team="Jacksonville Jaguars",
                        injury="Shoulder")])
    assert _find(out, "Josh Allen", team="BUF")["unavailable"] is False


def test_unmatched_filings_are_counted_and_named():
    """The number worth watching. A filing that matches no rostered
    player means the join is rotting, and a silent merge would hide it
    behind a healthier-looking board."""
    out = _merge([_sleeper("Cade Mays", pos="G")],
                 [_espn("Cade Mays", "Out"), _espn("Nobody Here", "Out")])
    m = out["injury_merge"]
    assert m["matched"] == 1 and m["unmatched_count"] == 1
    assert any("Nobody Here" in s for s in m["unmatched"])


def test_the_newly_unavailable_count_is_what_the_merge_actually_added():
    out = _merge([_sleeper("Cade Mays", pos="G"),
                  _sleeper("Already Out", desig="Out")],
                 [_espn("Cade Mays", "Out"), _espn("Already Out", "Out")])
    assert out["injury_merge"]["newly_unavailable"] == 1


def test_the_team_unavailable_count_is_recomputed():
    """It is summed at build time, before the merge runs. Leaving it stale
    puts a team header that disagrees with the rows under it."""
    out = _merge([_sleeper("Cade Mays", pos="G"), _sleeper("Healthy Guy")],
                 [_espn("Cade Mays", "Out")])
    assert out["teams"]["DET"]["unavailable"] == 1


# --- severity ---------------------------------------------------------------
def test_the_severity_ladder_is_ordered():
    assert im.severity("") == 0 < im.severity("questionable") \
        < im.severity("doubtful") < im.severity("out") <= im.severity("ir")


def test_an_unreadable_status_ranks_at_zero_rather_than_guessing():
    """Because the merge is severity-only, a word nobody mapped
    contributes nothing instead of silently benching a player."""
    assert im.severity("Sore-ish") == 0
    out = _merge([_sleeper("Odd Word")], [_espn("Odd Word", "Sore-ish")])
    assert _find(out, "Odd Word")["unavailable"] is False


def test_severity_ignores_case_and_padding():
    assert im.severity("  OUT ") == im.severity("out")


# --- degrading -------------------------------------------------------------
def test_an_empty_board_leaves_the_roster_alone():
    out = _merge([_sleeper("Healthy Guy")], [])
    assert _find(out, "Healthy Guy")["unavailable"] is False
    assert out["injury_merge"]["espn_filings"] == 0


def test_a_payload_with_no_teams_is_returned_untouched():
    assert im.apply({}, [_espn("X", "Out")]) == {}


def test_junk_rows_do_not_break_the_index():
    assert im.espn_index([None, "nope", {}, {"player": "X"}]) == {}


# --- the page ---------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _row_fn():
    i = APP.index("function rosterPlayerHTML(")
    return APP[i:APP.index("\nfunction ", i + 1)]


def test_the_out_chip_needed_no_change_to_show_the_merged_answer():
    """The whole reported symptom — Cade Mays reading Active — is fixed by
    `unavailable` and `status`, which this chip already rendered. Worth
    pinning: if the chip ever stops reading those fields, the merge goes
    silent without any test of the merge itself failing."""
    fn = _row_fn()
    assert "p.unavailable ?" in fn and "p.status" in fn and "p.injury" in fn


def test_the_return_date_reaches_the_page():
    """ESPN supplies it and Sleeper does not. "Out" says fade him; "Out ·
    knee · back 09-20" says whether to expect him next week."""
    assert "p.return_date" in _row_fn()


def test_a_contested_row_says_so():
    """A merged availability that hides a disagreement is a number the
    reader cannot audit."""
    fn = _row_fn()
    assert "p.injury_conflict" in fn and "feeds disagree" in fn


def test_the_conflict_chip_explains_which_way_the_merge_went():
    """Seeing "feeds disagree" without knowing which one won tells a
    reader there is a problem and nothing about what was done with it."""
    i = APP.index("feeds disagree")
    block = APP[max(0, i - 400):i]
    assert "pessimistic" in block


def test_the_build_reports_what_the_merge_did():
    """A silent merge cannot be checked. The counts go to the terminal so
    a rotting name-join shows up as a rising unmatched number rather than
    as a quietly healthier-looking board."""
    fb = open(os.path.join(ROOT, "fantasy_build.py"), encoding="utf-8").read()
    assert "injurymerge" in fb
    assert "unmatched" in fb and "newly unavailable" in fb


def test_the_merge_never_fails_the_roster_build():
    """The roster is the product; the second opinion is an enhancement. A
    dead ESPN feed must leave Sleeper's answer standing."""
    fb = open(os.path.join(ROOT, "fantasy_build.py"), encoding="utf-8").read()
    i = fb.index("from engine import injurymerge as _im")
    block = fb[max(0, i - 400):i + 900]
    assert "try:" in block and "except Exception" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
