"""The backups step up, in the numbers and in the report (step AHW, 26 November 2026).

Ethan, after Packers at Rams (Puka Nacua and Davante Adams on injured reserve): "when there is alot of players out
we dont reccomend any props for the backups or anything like that and dont say anything about them or how there
usage could step up in the game reports ... show them as breakout canidates or tough matchups or anything".

Measured first (roomfit.py, 2016-2025, held out by season): when a fifth or more of a team's targets sits, the
receivers left beyond its top three beat our number more often than in other games, and the lift that closes it
(catches x1.16 and yards x1.24 at 20-35%, x1.32 and x1.42 at 35% or more) held in 7 to 9 seasons of 10. The top
three left came and went by season and are not priced. What holds:

  * engine/room: each regular's share of the targets this season, the share that sits tonight (fresh absences,
    10%+ of the targets), each one's rank among those left (recently active, so a tight end unseen since week 3 is
    not in the room), and the measured cell;
  * engine/teammates.effect carries the room's lift on the same card as the teammate step (case "room" when it is
    the only one), so the projection moves, the card says it, and the journal keeps it;
  * the "Who steps up" block says which lift moved each pick;
  * the matchup scan reads the next men up: a receiver's share is read as his share of the targets left, so
    Konata Mumpfield (8.7% of the Rams' targets) has a read with Puka Nacua out, and each read says its share of
    what is left;
  * the short version says who steps up, right after who is out.

    python3 tests/test_the_backups_step_up_in_the_report.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import room as R                                        # noqa: E402


def _w(week, name, pos, targets, team="LA"):
    return {"season": "2026", "week": str(week), "season_type": "REG", "team": team, "position": pos,
            "player_display_name": name, "targets": str(targets)}


def _weeks():
    """The Rams' weeks 1-10 as nflverse filed them (the real 2026 shares, rounded): Nacua out in week 10, Adams
    gone after week 6, Ferguson after week 3."""
    rows = []
    for wk in range(1, 11):
        if wk != 10 and wk not in (2, 3):
            rows.append(_w(wk, "Puka Nacua", "WR", 15))
        if wk <= 6:
            rows.append(_w(wk, "Davante Adams", "WR", 8))
        if wk <= 3:
            rows.append(_w(wk, "Terrance Ferguson", "TE", 4))
        rows += [_w(wk, "Kyren Williams", "RB", 5), _w(wk, "Tyler Higbee", "TE", 5),
                 _w(wk, "Konata Mumpfield", "WR", 3 + (wk == 10)), _w(wk, "Colby Parkinson", "TE", 3),
                 _w(wk, "Blake Corum", "RB", 2), _w(wk, "Davis Allen", "TE", 2)]
    return rows


OUT = ["Puka Nacua", "Davante Adams"]


def test_the_room_counts_what_sits_and_who_is_left():
    t = R.table(_weeks(), {"LA"}, 12)["LA"]
    assert t["weeks"] == list(range(1, 11))
    share, sat = R.vacated(t, OUT)
    assert [n for n, _s in sat] == ["Puka Nacua"], "Adams has not played in the last two games: already absorbed"
    assert 0.35 <= share < 0.45, share
    # 34% (13 targets a game) is the other cell: the same men lifted by its own measure.
    rows = [dict(r, targets="13") if r["player_display_name"] == "Puka Nacua" else r for r in _weeks()]
    t2 = R.table(rows, {"LA"}, 12)["LA"]
    assert R.lift(t2, OUT, "Colby Parkinson", "rec_yds")[0] == 1.24, R.vacated(t2, OUT)
    assert R.rank_left(t, OUT, "Kyren Williams") == 1
    assert R.rank_left(t, OUT, "Konata Mumpfield") == 3, "Ferguson, unseen since week 3, is not in tonight's room"
    assert R.rank_left(t, OUT, "Colby Parkinson") == 4
    assert R.rank_left(t, OUT, "Nobody Here") is None


def test_the_measured_cells_and_nothing_else():
    t = R.table(_weeks(), {"LA"}, 12)["LA"]
    assert R.lift(t, OUT, "Colby Parkinson", "rec_yds")[0] == 1.42
    assert R.lift(t, OUT, "Colby Parkinson", "receptions")[0] == 1.32
    assert R.lift(t, OUT, "Konata Mumpfield", "rec_yds")[0] == 1.0, "the third man left: mixed by season, not priced"
    assert R.lift(t, OUT, "Kyren Williams", "receptions")[0] == 1.0
    assert R.lift(t, OUT, "Colby Parkinson", "anytime_td")[0] == 1.0, "touchdowns were not measured"
    mult, info = R.lift(t, ["Davante Adams"], "Colby Parkinson", "rec_yds")
    assert mult == 1.0 and info is None, "nothing fresh sits"
    assert R.ROOM == {("receptions", "20"): 1.16, ("rec_yds", "20"): 1.24,
                      ("receptions", "35"): 1.32, ("rec_yds", "35"): 1.42}
    _m, info = R.lift(t, OUT, "Colby Parkinson", "rec_yds")
    words = R.words(info, "LA", "rec_yds")
    assert words.startswith("Puka Nacua out: ") and "Measured over ten seasons (2016-2025)" in words
    assert words.endswith("— applied (×1.42)"), words


def _prop(player, market, pos):
    return types.SimpleNamespace(player=player, market=market, position=pos, team="LA", reset_applied=False)


def _game():
    from engine import teammates as TM
    depth = TM.depth_table(_weeks(), {"LA"}, 12)
    slate = types.SimpleNamespace(props=[], games=[types.SimpleNamespace(home="LA", away="GB")])
    inj = [types.SimpleNamespace(team="LA", player=n, status="IR") for n in OUT]
    TM.stamp(slate, depth, inj)
    return slate.games[0]


def test_the_projection_carries_the_room_on_the_teammate_card():
    from engine import stepup as S
    from engine import teammates as TM
    g = _game()
    assert g.lineup["LA"]["room"]["players"]["Colby Parkinson"][1] == 10
    mult, why, card = TM.effect(_prop("Colby Parkinson", "rec_yds", "TE"), g)
    assert round(mult, 3) == 1.42 and card["case"] == "room" and card["room"]["applied"] == 1.42, (mult, card)
    assert why.startswith("Room: Puka Nacua out, ") and why.endswith("measured (×1.42)"), why
    assert S.mate_mult({"mate_card": card}) == 1.42, "the journal keeps it"
    # Mumpfield is lifted by the teammate step alone (the receiver behind two out), never twice.
    mult, _w2, card = TM.effect(_prop("Konata Mumpfield", "rec_yds", "WR"), g)
    assert card and card["case"] != "room" and "room" not in card, card
    # Nothing sits: no card at all.
    from engine import teammates as TM2
    calm = types.SimpleNamespace(home="LA", away="GB", lineup={"LA": dict(g.lineup["LA"], out=[])})
    assert TM2.effect(_prop("Colby Parkinson", "rec_yds", "TE"), calm)[0] == 1.0


def test_the_block_says_which_lift_moved_each_pick():
    from engine import stepup as S
    rows = [{"player": "Colby Parkinson", "team": "LA", "market": "rec_yds",
             "mate_card": {"out": ["Puka Nacua"], "case": "room", "applied": 1.42, "room": {"applied": 1.42}}},
            {"player": "Tutu Atwell", "team": "LA", "market": "receptions",
             "mate_card": {"out": ["Puka Nacua"], "case": "above_new", "applied": 1.19}}]
    kinds: dict = {}
    got = S.raised(rows, "LA", {S._key("Puka Nacua")}, kinds)
    assert got == {"Colby Parkinson": {"rec_yds": 1.42}, "Tutu Atwell": {"receptions": 1.19}}
    assert kinds == {"Colby Parkinson": {"rec_yds": "room"}, "Tutu Atwell": {"receptions": "mate"}}
    line = S._lift_line("Colby Parkinson", got["Colby Parkinson"], kinds["Colby Parkinson"])
    assert line == ("Our numbers raise Colby Parkinson's receiving yards ×1.42, the lift measured over ten seasons "
                    "(2016-2025) for the receivers left beyond a team's top three when a fifth or more of its "
                    "targets sit (engine/room), in every number we price on him"), line


def _usage():
    from engine.gamescan import _key
    shares = {"Puka Nacua": ("WR", 0.36, 9), "Davante Adams": ("WR", 0.20, 6), "Kyren Williams": ("RB", 0.14, 10),
              "Tyler Higbee": ("TE", 0.13, 10), "Konata Mumpfield": ("WR", 0.087, 10),
              "Colby Parkinson": ("TE", 0.087, 10), "Davis Allen": ("TE", 0.05, 10)}
    return {("LA", _key(n)): {"name": n, "position": p, "games": 9, "tgt_share": s, "targets_pg": 3.0,
                              "last_week": lw, "carry_share": 0.6 if n == "Kyren Williams" else 0.0}
            for n, (p, s, lw) in shares.items()}


def test_the_next_men_up_have_reads():
    from engine import gamescan as GS
    inj = [types.SimpleNamespace(team="LA", player=n, status="IR", position="WR") for n in OUT]
    share, names = GS.room_left(_usage(), "LA", inj)
    assert names == ["Puka Nacua"] and abs(share - 0.36) < 1e-9, (share, names)
    keys = [r["player"] for r in GS.key_players(_usage(), ["LA"], inj) if r["team"] == "LA"]
    assert "Konata Mumpfield" in keys and "Colby Parkinson" in keys, keys
    assert "Puka Nacua" not in keys and "Davis Allen" not in keys, keys
    # With nobody out the floor stands: 8.7% is not a key player's share.
    calm = [r["player"] for r in GS.key_players(_usage(), ["LA"], []) if r["team"] == "LA"]
    assert "Konata Mumpfield" not in calm, calm
    src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert "of what is left\")" in src and "left_room = {t: room_left(usage, t, injuries) for t in teams}" in src


def test_the_short_version_says_who_steps_up():
    from engine import gamereport as GR
    c = GR.Ctx({"home": "LA", "away": "GB", "date": "2026-11-25", "kickoff": "20:00"}, {"date": "2026-W12"})
    c.stepup = {"LA": {
        "found": [{"kind": "targets", "out": [("Puka Nacua", "WR", 0.36)], "vacated": 0.36, "weeks": [10],
                   "them": "that player",
                   "named": [{"player": "Konata Mumpfield", "pos": "WR", "per_game": 4.0, "with": 2.9,
                              "yards": 81.0},
                             {"player": "Kyren Williams", "pos": "RB", "per_game": 5.0, "with": 5.1,
                              "yards": 9.0}]}],
        "lift": {"Colby Parkinson": {"receptions": 1.32, "rec_yds": 1.42},
                 "Blake Corum": {"receptions": 1.32, "rec_yds": 1.42}}}}
    s = GR.stepup_sentence(c)
    assert s == ("Who steps up for the Rams: without Puka Nacua (36% of the targets this season), in week 10, the "
                 "one game this season without Puka Nacua, the targets went to Konata Mumpfield (4 targets, 81 yards; "
                 "2.9 a game otherwise) and Kyren Williams (5 targets, 9 yards; 5.1 a game otherwise); our numbers "
                 "raise Blake Corum's and Colby Parkinson's receiving yards ×1.42 and catches ×1.32 for it."), s
    c.stepup = {}
    assert GR.stepup_sentence(c) == ""
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    i = src.index("def sec_short(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("absent_sentence(c, outs)") < body.index("stepup_sentence(c)") < body.index("line_sentence(c)")


def test_the_step_up_block_hands_the_short_version_what_it_found():
    import test_who_steps_up_when_receivers_sit as T
    from engine import stepup as S
    got = S.for_team(T._conn(T._rams()), 2026, 12, "LA", "Rams", T.OUT, T.ROWS)
    assert got["found"][0]["kind"] == "targets" and got["found"][0]["weeks"] == [7]
    assert [n["player"] for n in got["found"][0]["named"]] == ["Tutu Atwell", "Colby Parkinson", "Kyren Williams"]
    assert got["found"][0]["named"][0] == {"player": "Tutu Atwell", "pos": "WR", "per_game": 9.0, "with": 4.0,
                                           "yards": 70.0}
    assert got["lift"] == {"Tutu Atwell": {"receptions": 1.19, "rec_yds": 1.12}}
    src = (ROOT / "engine" / "stepup.py").read_text(encoding="utf-8")
    assert 'setattr(c, "stepup", found)' in src


def test_college_says_who_steps_up_in_its_short_version_too():
    import test_who_steps_up_in_college as T
    from engine import gamereport as GR
    from engine import stepup as S
    got = S.for_cfb_team(T._indiana(), T.DAYS, "IND", "Indiana", T.OUT, T._rows(), before="2026-11-22",
                         positions={S._key("Riley Nowakowski"): "TE"}, season=2026)
    f = got["found"][0]
    assert (f["kind"], f["games"], f["when"]) == ("catches", 2, "Oct. 18 and Nov. 8"), f
    c = GR.Ctx({"home": "IND", "away": "PUR", "date": "2026-11-28", "kickoff": "12:00"}, {"date": "2026-11-28"},
               sport="cfb")
    c.stepup = {"IND": got}
    s = GR.stepup_sentence(c)
    assert s.startswith("Who steps up for "), s
    assert ("without Elijah Sarratt (43% of the catches this season), in the 2 games this season without Elijah "
            "Sarratt, the catches went to Omar Cooper Jr. (7 catches a game, 90 yards a game; 4 a game otherwise)"
            in s), s
    assert s.endswith("our numbers raise Omar Cooper Jr.'s receiving yards ×1.09 and catches ×1.12 for it."), s


def test_the_measurement_is_in_the_repo():
    src = (ROOT / "roomfit.py").read_text(encoding="utf-8")
    assert "THE CALIBRATING MULTIPLIER" in src and "NOBODY SAT: the control" in src
    assert "HOW OFTEN HE BEAT OUR NUMBER" in src


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
