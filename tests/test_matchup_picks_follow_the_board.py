"""The matchup picks follow the board's corrected number (2026-11-15).

Ethan's QC paste (the picks audit, 15 November): the NFL board's own check
flagged five matchup picks — Keon Coleman, Dalton Kincaid and Mike
Washington Jr. unders at 50–53% with the projection over the line, Darren
Waller and Christian McCaffrey overs at 50%. Each was made at its own bar
(engine/matchpicks: 55% for yards and catches) on the model's number; the
board then corrected that bet's chance on the graded record and
likelyboard.harmonize wrote it back onto the pick, which stayed posted
under its own bar. Now a matchup pick under its bar after the correction,
or one the board held back, comes off the matchup picks, and the player's
card says why. A posted pick keeps its seat until its game.

    python3 tests/test_matchup_picks_follow_the_board.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import contradictions as C, likelyboard as LB                  # noqa: E402


def _pick(player, side, prob, line=26.5, **kw):
    return {"kind": "prop", "matchup_pick": True, "player": player, "team": "BUF", "opponent": "MIA",
            "market": "rec_yds", "side": side, "line": line, "odds": -115, "book": "DraftKings",
            "model_prob": prob, "projection": 29.6, **kw}


def _board_row(player, side, prob, line=26.5, **kw):
    return {"kind": "prop", "player": player, "team": "BUF", "market": "rec_yds", "side": side, "line": line,
            "model_prob": prob, "tier": "look", "tier_label": "Worth a look", **kw}


def _result():
    coleman = _pick("Keon Coleman", "UNDER", 0.58)
    kincaid = _pick("Dalton Kincaid", "UNDER", 0.57, line=39.5)
    waller = _pick("Darren Waller", "OVER", 0.56, line=28.5)
    allen = _pick("James Cook", "OVER", 0.62, line=21.5)
    posted = _pick("Khalil Shakir", "UNDER", 0.56, line=44.5, locked=True)
    reads = {"MIA@BUF": {"players": [
        {"player": "Keon Coleman", "team": "BUF", "read": "tough",
         "matchup_pick": {"market": "rec_yds", "side": "UNDER", "line": 26.5, "player": "Keon Coleman"}},
        {"player": "Darren Waller", "team": "BUF", "read": "good",
         "matchup_pick": {"market": "rec_yds", "side": "OVER", "line": 28.5, "player": "Darren Waller"}}]}}
    board = {"rows": [_board_row("Keon Coleman", "UNDER", 0.53), _board_row("James Cook", "OVER", 0.61, line=21.5),
                      _board_row("Khalil Shakir", "UNDER", 0.52, line=44.5)],
             "held": [_board_row("Darren Waller", "OVER", 0.50, line=28.5, tier="held",
                                 held_note="held back: the books' price gives it 50% — under 55%"),
                      _board_row("Dalton Kincaid", "UNDER", 0.53, line=39.5, tier="held",
                                 held_note="held back: a prop under 60% on the tightened NFL board")]}
    return {"most_likely": [], "td_scenarios": [], "scan_reads": reads, "likely_board": board,
            "matchup_picks": [{"game": "MIA@BUF", "td": [], "props": [coleman, kincaid, waller, allen, posted]}]}


def test_a_pick_corrected_under_its_bar_or_held_comes_off():
    res = _result()
    LB.harmonize(res)
    left = {r["player"]: r for r in res["matchup_picks"][0]["props"]}
    assert set(left) == {"James Cook", "Khalil Shakir"}, sorted(left)
    assert left["James Cook"]["model_prob"] == 0.61, "the board's number, still over the bar"
    assert left["Khalil Shakir"]["locked"], "a posted pick keeps its seat until its game"
    assert res["likely_board"]["matchup_picks_off"] == 3


def test_the_card_says_why():
    res = _result()
    LB.harmonize(res)
    cards = {x["player"]: x["matchup_pick"] for x in res["scan_reads"]["MIA@BUF"]["players"]}
    assert cards["Keon Coleman"]["tier"] == "held"
    assert "puts our chance at 53%, under the 55% a matchup pick needs" in cards["Keon Coleman"]["held_note"]
    assert cards["Darren Waller"]["held_note"].startswith("held back: the books' price gives it 50%")


def test_the_self_check_reads_no_matchup_pick_under_its_bar():
    res = _result()
    LB.harmonize(res)
    found = [f for f in C.scan({"matchup_picks": res["matchup_picks"]})
             if f["kind"] in ("UNDER 50%", "PROJECTION") and "Matchup picks" in f["text"]]
    # The one left is the posted pick at its seat; the five kinds the audit
    # flagged are gone.
    assert all("Khalil Shakir" == f["player"] for f in found), found


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
