"""One bet, one chance; a pick our own read argues against keeps its seat
and says so (engine/likelyboard harmonize, warn_avoids).

Ethan, 2026-10-06, on the contradiction check: "yes 2" (show the record's
corrected chance everywhere) and "keep 3 with the warning".

Run directly: `python3 tests/test_one_bet_one_chance.py`
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import contradictions as C                         # noqa: E402
from engine import likelyboard as L                            # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _row(player="Bucky Irving", market="receptions", side="OVER", line=1.5, p=0.77, **kw):
    return dict(dict(player=player, market=market, side=side, line=line, model_prob=p, odds=-200, team="TB"),
                **kw)


def _result():
    ml = _row()
    mp = _row(p=0.70)
    board_row = _row(p=0.68, tier="strong", cal_note="picks like this over-claim",
                     checks={"model": True, "matchup": True, "market": True, "record": None},
                     check_notes={"matchup": "matchup read: Good matchup"})
    love = _row(player="Jordan Love", market="pass_yds", line=199.5, p=0.64, team="GB")
    love_board = dict(love, checks={"model": True, "matchup": False},
                      check_notes={"matchup": "matchup read leans the other way (Tough matchup)"})
    return {"most_likely": [ml, love], "matchup_picks": [{"td": [], "props": [mp]}],
            "likely_board": {"rows": [board_row, love_board], "held": []}}


def test_every_copy_of_a_bet_shows_the_boards_corrected_chance():
    res = _result()
    n = L.harmonize(res)
    ml, mp = res["most_likely"][0], res["matchup_picks"][0]["props"][0]
    assert ml["model_prob"] == mp["model_prob"] == 0.68 and n == 2
    assert ml["listed_prob"] == 0.77 and mp["listed_prob"] == 0.70, "the list's own number is kept"
    assert ml["cal_note"] == "picks like this over-claim"
    found = [f for f in C.scan(res) if f["kind"] == "TWO NUMBERS"]
    assert not found, found


def test_a_posted_pick_keeps_its_number_and_the_board_takes_it():
    res = _result()
    res["most_likely"][0]["locked"] = True
    L.harmonize(res)
    assert res["most_likely"][0]["model_prob"] == 0.77
    b = res["likely_board"]["rows"][0]
    assert b["model_prob"] == 0.77 and b["corrected_prob"] == 0.68


def test_a_pick_the_matchup_read_argues_against_stays_and_says_so():
    res = _result()
    L.harmonize(res)
    love = res["most_likely"][1]
    assert love in res["most_likely"], "kept"
    assert "leans the other way" in love["matchup_warning"]
    assert "leans the other way" in res["likely_board"]["rows"][1]["matchup_warning"]
    assert "matchup_warning" not in res["most_likely"][0]
    res["scan_reads"] = {"GB@CHI": {"players": [{"player": "Jordan Love", "read": "tough", "label": "Tough matchup",
                                                 "lean": ["pass_yds"]}]}}
    assert not [f for f in C.scan(res) if f["kind"] == "READ vs PICK"], "said on the card, not a contradiction"


def test_a_play_to_avoid_stays_and_says_so():
    res = _result()
    res["game_plans"] = [{"steps": [{"key": "avoid", "rows": [
        {"player": "Jordan Love", "market": "pass_yds", "side": "over",
         "why": "The over fights the matchup — CHI gives up the 3rd-fewest passing yards."}]}]}]
    n = L.warn_avoids(res)
    love = res["most_likely"][1]
    assert n >= 2 and love["avoid_warning"].startswith("The game plan lists this as a play to avoid: The over fights")
    assert "avoid_warning" not in res["most_likely"][0]
    assert not [f for f in C.scan(res) if f["kind"] == "AVOID vs PICK"]


def test_the_builds_run_it_before_the_journal():
    nfl = (ROOT / "nfl_build.py").read_text()
    assert nfl.index("_lb.harmonize(result)") < nfl.index("ml_logged = ledger.log_most_likely(")
    assert nfl.index("_gplan.attach(result, 'nfl')") < nfl.index("_lbw.warn_avoids(result)")
    lb = (ROOT / "engine" / "likelyboard.py").read_text()
    att = lb[lb.index("def attach("):lb.index("def journal(")]
    assert "harmonize(result)" in att
    assert "_lb.warn_avoids(out)" in (ROOT / "cfb_build.py").read_text()


def test_the_cards_draw_the_warning():
    js = (ROOT / "web" / "js" / "app.js").read_text()
    assert "${obWhyLine(r)}${pickWarnHTML(r)}" in js and "${pickWarnHTML(lk || r)}" in js
    fn = js[js.index("function pickWarnHTML("):js.index("function obCardHTML(")]
    assert "escapeHtml(" in fn and "matchup_warning" in fn and "avoid_warning" in fn


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
