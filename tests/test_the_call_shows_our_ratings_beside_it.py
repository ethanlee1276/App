"""The call shows our own team ratings' pick beside it, tagged unproven, never followed.

Ethan, 2026-11-16, asked whether to show our own ratings' pick next to "Who we
think wins" anyway: "Yes". engine/gamereport.ratings_chance reads the home
side's chance by our team ratings alone (the slip checker's model,
engine/slipgame.model: each league's ratings, baseball's with tonight's
starters, hockey's expected goals) through the build's history connection,
or from the game's meta where the build already knows it. The call itself
still follows the price. The ratings' line sits right under the price's and
says why it is unproven, as far as that is measured (ratings_why): the NFL's
disagreement with the close carried nothing, baseball's ratings-alone
moneylines lost 12.4%, and a league engine/gamecal has not measured says so.
When the ratings pick the other team, the line says that too.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402

REPORT_JS = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
REPORT_CSS = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
NAMES = {"DET": "Lions", "GB": "Packers"}


def _ctx(sport="nfl", ratings=None, conn=None, **g):
    base = {"home": "DET", "away": "GB", "date": "2099-11-16", "home_ml": -160, "away_ml": 140}
    meta = {"ratings": {"p_home": ratings}} if ratings is not None else {}
    return R.Ctx(dict(base, **g), {}, sport=sport, names=NAMES, meta=meta, conn=conn)


def _items(sec):
    return next(b for b in sec["blocks"] if b["type"] == "list")["items"]


def test_the_ratings_line_sits_under_the_price_and_says_why_it_is_unproven():
    sec = R.sec_verdict(_ctx(ratings=0.62))
    win = sec["blocks"][0]
    assert win["team"] == "DET" and win["ratings"] == {"team": "DET", "name": "Lions", "chance": 0.62,
                                                        "same": True, "even": False}, win
    items = _items(sec)
    assert items[0].startswith("The Lions to win, a 60% chance by the books' moneyline"), items
    assert items[1] == ("Our team ratings alone: the Lions 62%. Unproven: where they've disagreed with the "
                        "closing line, the disagreement has carried nothing."), items[1]
    assert sec["blocks"][-1]["text"].startswith("The call follows the price"), "the note does not repeat the why"


def test_ratings_on_the_other_side_say_so_and_the_call_still_follows_the_price():
    sec = R.sec_verdict(_ctx(sport="mlb", ratings=0.40))
    win = sec["blocks"][0]
    assert win["team"] == "DET", "the call is the price's"
    assert win["ratings"]["team"] == "GB" and win["ratings"]["same"] is False
    assert _items(sec)[1] == ("Our team ratings alone: the Packers 60%, the other side from the price. Unproven: "
                              "bets on them alone against the price lost 12.4%."), _items(sec)[1]


def test_an_unmeasured_league_says_so_and_an_even_read_is_said_as_one():
    sec = R.sec_verdict(_ctx(sport="nba", ratings=0.5))
    assert sec["blocks"][0]["ratings"]["even"] is True
    assert _items(sec)[1] == ("Our team ratings alone: an even game. Unproven: they haven't been measured "
                              "against the price yet."), _items(sec)[1]


def test_a_measured_league_says_what_was_measured():
    import engine.gamecal as GC
    keep = GC.measured
    try:
        GC.measured = lambda sport, market: {"shrink": 0.0, "n": 412, "hit_rate": 0.5}
        assert R.ratings_why("cfb") == "over 412 graded games, their disagreements with the closing line carried nothing"
        GC.measured = lambda sport, market: {"shrink": 0.3, "n": 950}
        assert R.ratings_why("nhl") == "30% of a disagreement with the closing line has held up, over 950 graded games"
    finally:
        GC.measured = keep


def test_without_ratings_the_call_reads_as_before():
    sec = R.sec_verdict(_ctx())
    assert "ratings" not in sec["blocks"][0]
    assert not any(i.startswith("Our team ratings alone") for i in _items(sec))
    assert "the disagreement has carried nothing" in sec["blocks"][-1]["text"], "the NFL's own note stands"


def test_the_build_connection_reads_the_slip_model_with_baseball_starters():
    import engine.slipgame as SG
    seen, keep = {}, SG.model

    def fake(conn, league, home, away, g, today=None):
        seen.update(conn=conn, league=league, home=home, away=away, g=g, today=today)
        return {"p_home": 0.57}
    try:
        SG.model = fake
        g = {"pitchers": {"home": {"name": "Tarik Skubal", "xera": 2.4}, "away": {"name": "Jordan Love", "xera": 4.9}}}
        sec = R.sec_verdict(_ctx(sport="mlb", conn="the build's connection", **g))
    finally:
        SG.model = keep
    assert seen["conn"] == "the build's connection" and (seen["league"], seen["home"], seen["away"]) == ("mlb", "DET", "GB")
    assert seen["g"]["pitchers"]["home"]["xera"] == 2.4 and seen["today"] == "2099-11-16", seen
    assert sec["blocks"][0]["ratings"]["chance"] == 0.57
    # A model that refuses, or a connection that throws, writes no ratings line.
    try:
        SG.model = lambda *a, **k: {"refused": "we hold no 2099 results for DET"}
        assert "ratings" not in R.sec_verdict(_ctx(conn=object()))["blocks"][0]
        SG.model = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked"))
        assert "ratings" not in R.sec_verdict(_ctx(conn=object()))["blocks"][0]
    finally:
        SG.model = keep


def test_the_copy_and_the_page_carry_it():
    rep = {"title": "Packers at Lions", "sections": [R.sec_verdict(_ctx(ratings=0.47))]}
    text = R.to_text(rep)
    assert "  A lean: Lions — 60% to win\n  Our ratings alone (unproven): Packers 53%" in text, text
    assert "function winnerRatingsHTML(r, pct) {" in REPORT_JS and "${winnerRatingsHTML(b.ratings, pct)}" in REPORT_JS
    assert '<span class="gr-winner-tag">Unproven</span>' in REPORT_JS
    assert "Our ratings alone (unproven): ${r.even ? \"an even game\"" in REPORT_JS
    assert ".gr-winner-alt {" in REPORT_CSS and ".gr-winner-tag {" in REPORT_CSS


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
