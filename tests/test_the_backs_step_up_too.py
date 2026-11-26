"""The backs step up too (step AHX, 26 November 2026).

Ethan, after the receivers' step (AHW): "keep going and do the same for running backs too". What a back had:

  * the teammate step lifted his rushing yards (x1.66 behind a starter just ruled out), his catches and his
    receiving yards, and never his CARRIES: engine/matefit had never measured the market, so the board priced a
    backup's carries at his own form while it raised his yards by two thirds. Measured now on the same four seasons
    and rule (python3 matefit.py, --snaps for the snap-ranked order the board uses): carries x1.72 to x1.74 behind
    a back just ruled out, x1.32 to x1.33 behind one already out, x1.07 behind one out below him, every case in
    three or four seasons of four. A teammate back is read for carries too (matefit --back: passes);
  * the matchup scan read a back only with a quarter of his team's carries this season, so the man behind a lead
    back who sits had no read unless a book priced him. With a lead back's share sitting, a back's share is read as
    his share of the carries left, and his read says it;
  * the short version's "Who steps up" says who took the carries in the games without him (step AHW's sentence,
    the carries the block already measured).

    python3 tests/test_the_backs_step_up_too.py
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


def test_carries_are_lifted_as_the_yards_are():
    from engine import matefit as F
    from engine import teammates as T
    assert ("rush_att", ("carries",), 3.5) in F.MARKETS["RB"]
    assert T.EFFECT[("rush_att", "RB", "above_new")] == 1.741
    assert T.EFFECT_SNAPS[("rush_att", "RB", "above_new")] == 1.723
    assert T.EFFECT_SNAPS[("rush_att", "RB", "above_cont")] == 1.331
    assert ("rush_att", "RB", "below_cont") not in T.EFFECT, "short of the rule on the target-ranked order"
    assert ("rush_att", "RB") in T.BACK_CELLS
    # The board's own step on a backup's carries prop, the starter ahead of him just ruled out.
    lu = {"order": {"RB": [["Kyren Williams", 0.7, 9, 10], ["Blake Corum", 0.3, 10, 10]], "WR": [], "TE": []},
          "out": [T._norm("Kyren Williams")], "maybe": [], "last": 10, "basis": "snaps", "seen": {}, "weeks": []}
    game = types.SimpleNamespace(lineup={"LA": lu})
    prop = types.SimpleNamespace(player="Blake Corum", market="rush_att", position="RB", team="LA",
                                 reset_applied=False)
    mult, why, card = T.effect(prop, game)
    assert mult == 1.723 and card["case"] == "above_new", (mult, card)
    assert "measured (×1.72)" in why, why


def _usage():
    from engine.gamescan import _key
    rows = {"Kyren Williams": ("RB", 0.60, 0.14, 10), "Blake Corum": ("RB", 0.22, 0.06, 10),
            "Ronnie Rivers": ("RB", 0.05, 0.01, 10), "Puka Nacua": ("WR", 0.0, 0.36, 10),
            "Tyler Higbee": ("TE", 0.0, 0.13, 10)}
    return {("LA", _key(n)): {"name": n, "position": p, "games": 9, "carry_share": cs, "tgt_share": ts,
                              "targets_pg": 3.0, "carries_pg": 15 * cs, "last_week": lw}
            for n, (p, cs, ts, lw) in rows.items()}


def test_the_next_back_up_has_a_read():
    from engine import gamescan as GS
    inj = [types.SimpleNamespace(team="LA", player="Kyren Williams", status="OUT", position="RB")]
    share, names = GS.room_left(_usage(), "LA", inj, "carries")
    assert names == ["Kyren Williams"] and abs(share - 0.60) < 1e-9, (share, names)
    keys = [r["player"] for r in GS.key_players(_usage(), ["LA"], inj) if r["team"] == "LA"]
    assert "Blake Corum" in keys and "Kyren Williams" not in keys, keys
    assert "Ronnie Rivers" not in keys, "5% of the carries is 12% of what is left: under the bar"
    calm = [r["player"] for r in GS.key_players(_usage(), ["LA"], []) if r["team"] == "LA"]
    assert "Blake Corum" not in calm, "with the lead back playing, 22% is not a key back's share"
    src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert 'left_carries = {t: room_left(usage, t, injuries, "carries") for t in teams}' in src
    assert '"kind": work' in src


def _rows_with_a_missed_game():
    import test_who_steps_up_when_receivers_sit as T
    rows = []
    for wk in range(1, 11):
        if wk != 8:
            rows += T._line(wk, "Kyren Williams", "RB", 3, 18, 20, 80)
        rows += T._line(wk, "Blake Corum", "RB", 2, 16 if wk == 8 else 5, 10, 75 if wk == 8 else 22)
        rows += T._line(wk, "Puka Nacua", "WR", 10, rec_yds=95)
    return rows


def test_the_short_version_says_who_took_the_carries():
    import test_who_steps_up_when_receivers_sit as T
    from engine import gamereport as GR
    from engine import stepup as S
    rows = [{"player": "Blake Corum", "team": "LA", "market": "rush_att",
             "mate_card": {"out": ["Kyren Williams"], "case": "above_new", "applied": 1.723}}]
    got = S.for_team(T._conn(_rows_with_a_missed_game()), 2026, 11, "LA", "Rams", [("Kyren Williams", "RB", "OUT")],
                     rows)
    f = next(x for x in got["found"] if x["kind"] == "carries")
    assert f["named"][0]["player"] == "Blake Corum" and f["named"][0]["per_game"] == 16.0, f
    c = GR.Ctx({"home": "LA", "away": "GB", "date": "2026-11-25", "kickoff": "20:00"}, {"date": "2026-W11"})
    c.stepup = {"LA": got}
    s = GR.stepup_sentence(c)
    assert ("Kyren Williams is out (78% of the carries this season); in week 8, the one game this season without "
            "Kyren Williams, the carries went to Blake Corum (16 carries for 75 yards; 5 carries a game when Kyren "
            "Williams plays)") in s, s
    assert "our numbers raise Blake Corum's carries by 72% for it." in s, s
    claims = [cl for _t, cl in got["lines"] if cl]
    assert any(cl["player"] == "Blake Corum" and cl["stat"] == "carries" for cl in claims), "graded after the game"


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
