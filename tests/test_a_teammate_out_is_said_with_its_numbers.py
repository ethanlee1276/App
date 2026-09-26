"""A teammate out: the matchup card says how much opens up, and whether
our number counts it.

Ethan, 2026-09-25: "if a WR2 or WR1 or sum is out, then other players will
see higher usage. That's useful information too, we need too make sure that
being implemented and being convayed too the user."

The model already moves the number for the case it measured
(engine/teammates: a teammate at HIS position ranked above him ruled out —
WR receptions ×1.18, RB rushing yards ×1.65 …), and each prop carries the
stats' own record of what happened when that teammate sat before
(engine/redistribute's ripple). The matchup card said none of it: "David
Njoku is out — his targets are open" beside a WR, a tight end's absence the
model never measured for receivers, with no number. `gamescan.mate_line` now
says the measured shift, the share left behind, and whether our projection
counts it; a cross-position absence nobody measured is shown as a note,
not counted toward the read.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402


class _Inj:
    def __init__(self, player, team, position, status="OUT"):
        self.player, self.team, self.position, self.status = player, team, position, status


def test_a_measured_shift_and_the_models_multiplier_are_both_said():
    m = {"name": "Rashee Rice", "pos": "WR", "same_pos": True, "share": 0.24, "per_game": 8.1,
         "ripple": {"out": "Rashee Rice", "measured": True, "delta": 0.06,
                    "text": "Rashee Rice out — over his 4 missed games, Worthy absorbed +6% of the targets"},
         "applied": {"receptions": 1.18, "rec_yds": 1.107}}
    text, counted = G.mate_line(m, "targets")
    assert counted
    assert text == ("Rashee Rice out — over his 4 missed games, Worthy absorbed +6% of the targets"
                    " · our projection counts it: +11% receiving yards, +18% catches"), text


def test_an_unmeasured_absence_says_the_share_it_leaves():
    same = {"name": "Keenan Allen", "pos": "WR", "same_pos": True, "share": 0.21, "per_game": 6.1}
    text, counted = G.mate_line(same, "targets")
    assert counted and text == "Keenan Allen (WR) is out — 21% of the targets (6.1 a game) to go around"
    thin = dict(same, ripple={"out": "Keenan Allen", "measured": False})
    assert "not enough games without him to measure who takes them" in G.mate_line(thin, "targets")[0]


def test_an_absence_across_positions_is_shown_not_counted():
    njoku = {"name": "David Njoku", "pos": "TE", "same_pos": False, "share": 0.18, "per_game": 5.5}
    text, counted = G.mate_line(njoku, "targets")
    assert not counted
    assert text.startswith("David Njoku (TE) is out — 18% of the targets (5.5 a game)")
    assert text.endswith("not in our number: no lift measured across positions")
    flat = {"name": "X", "pos": "WR", "same_pos": True,
            "ripple": {"measured": True, "delta": 0.004, "text": "X out — share did not move (+0.4%)"}}
    assert G.mate_line(flat, "targets") == ("X out — share did not move (+0.4%)", False), \
        "a measured non-move is not a reason, and it is not an across-positions absence"


def test_the_read_counts_it_only_when_it_is_counted():
    kw = dict(usage={"tgt_share": 0.19, "targets_pg": 6.0, "games": 3}, ratings={}, room={},
              scheme={}, split={}, tackling={}, line_out=[])
    x = G.player_read("Ladd McConkey", "LAC", "BUF", "WR", mates_out=[
        {"name": "David Njoku", "pos": "TE", "same_pos": False, "share": 0.18, "per_game": 5.5},
        {"name": "Keenan Allen", "pos": "WR", "same_pos": True, "share": 0.21, "per_game": 6.1}], **kw)
    assert any(t.startswith("Keenan Allen (WR) is out") for t in x["pro"]), x["pro"]
    assert any(t.startswith("David Njoku (TE) is out") for t in x["notes"]), x["notes"]
    assert not any("Njoku" in t for t in x["pro"])


def test_the_scan_hands_each_read_its_own_props_evidence():
    usage = {("LAC", G._key("Ladd McConkey")): {"name": "Ladd McConkey", "tgt_share": 0.19,
                                                "targets_pg": 6.0, "games": 3, "position": "WR"},
             ("LAC", G._key("Keenan Allen")): {"name": "Keenan Allen", "tgt_share": 0.21,
                                               "targets_pg": 6.1, "games": 3, "position": "WR"}}
    prop = {"player": "Ladd McConkey", "team": "LAC", "opponent": "BUF", "position": "WR",
            "market": "receptions", "side": "over", "line": 4.5, "odds": -120,
            "ripples": [{"out": "Keenan Allen", "measured": True, "delta": 0.07,
                         "text": "Keenan Allen out — over his 3 missed games, McConkey absorbed +7% of the targets"}],
            "mate_card": {"out": ["Keenan Allen"], "applied": 1.18, "headline": "Keenan Allen out ahead of him at WR"}}
    scan = G.scan_game("BUF", "LAC", ratings={}, charts={}, defenders_now={}, usage=usage,
                       injuries=[_Inj("Keenan Allen", "LAC", "WR")], props=[prop])
    (me,) = [p for p in scan["players"] if p["player"] == "Ladd McConkey"]
    line = next(t for t in me["pro"] if "Keenan Allen" in t)
    assert line == ("Keenan Allen out — over his 3 missed games, McConkey absorbed +7% of the targets"
                    " · our projection counts it: +18% catches"), line


def test_a_questionable_teammate_is_a_note_with_what_happens_if_he_sits():
    usage = {("LAC", G._key("Ladd McConkey")): {"name": "Ladd McConkey", "tgt_share": 0.19,
                                                "targets_pg": 6.0, "games": 3, "position": "WR"},
             ("LAC", G._key("Keenan Allen")): {"name": "Keenan Allen", "tgt_share": 0.21,
                                               "targets_pg": 6.1, "games": 3, "position": "WR"},
             ("LAC", G._key("Will Dissly")): {"name": "Will Dissly", "tgt_share": 0.13,
                                              "targets_pg": 3.9, "games": 3, "position": "TE"}}
    prop = {"player": "Ladd McConkey", "team": "LAC", "opponent": "BUF", "position": "WR",
            "market": "receptions", "side": "over", "line": 4.5, "odds": -120,
            "mate_card": {"out": [], "applied": 1.0,
                          "if_sits": {"who": ["Keenan Allen"], "mult": 1.18, "case": "above_new"}}}
    scan = G.scan_game("BUF", "LAC", ratings={}, charts={}, defenders_now={}, usage=usage,
                       injuries=[_Inj("Keenan Allen", "LAC", "WR", "QUESTIONABLE"),
                                 _Inj("Will Dissly", "LAC", "TE", "QUESTIONABLE")], props=[prop])
    (me,) = [p for p in scan["players"] if p["player"] == "Ladd McConkey"]
    assert "Keenan Allen (WR) is questionable — if he sits, our projection moves +18% catches" in me["notes"]
    assert "Will Dissly (TE) is questionable — 13% of the targets ride on it" in me["notes"]
    assert not any("questionable" in t for t in me["pro"]), "he may play: shown, never counted"


def test_a_player_is_never_his_own_teammate():
    """Droplet, 2026-09-25: "DJ Moore (WR) is questionable" on DJ Moore's
    own card, "David Njoku (TE) is out" on Njoku's, "Puka Nacua (WR) is
    out" on Nacua's. His own injury row is not a teammate's."""
    usage = {("LAC", G._key("Keenan Allen")): {"name": "Keenan Allen", "tgt_share": 0.21,
                                               "targets_pg": 6.1, "games": 3, "position": "WR"},
             ("LAC", G._key("Ladd McConkey")): {"name": "Ladd McConkey", "tgt_share": 0.19,
                                                "targets_pg": 6.0, "games": 3, "position": "WR"}}
    for status in ("OUT", "QUESTIONABLE"):
        prop = {"player": "Keenan Allen", "team": "LAC", "opponent": "BUF", "position": "WR",
                "market": "receptions", "side": "over", "line": 4.5, "odds": -120}
        scan = G.scan_game("BUF", "LAC", ratings={}, charts={}, defenders_now={}, usage=usage,
                           injuries=[_Inj("Keenan Allen", "LAC", "WR", status)], props=[prop])
        mine = [p for p in scan["players"] if p["player"] == "Keenan Allen"]
        if status == "OUT":
            # Ruled out: no read at all since 2026-09-26 (Zay Flowers,
            # test_a_player_who_is_not_playing_gets_no_read).
            assert not mine, mine
        else:
            (me,) = mine
            said = (me.get("pro") or []) + (me.get("con") or []) + (me.get("notes") or [])
            assert not any(t.startswith("Keenan Allen (") for t in said), (status, said)
            assert said and "himself — this read assumes he plays" in said[0] if me.get("notes") else True
        mc = [p for p in scan["players"] if p["player"] == "Ladd McConkey"]
        if mc:
            assert any("Keenan Allen" in t for t in (mc[0].get("pro") or []) + (mc[0].get("notes") or []))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
