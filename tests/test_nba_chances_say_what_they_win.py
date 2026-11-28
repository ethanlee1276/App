"""Decision 19: the NBA's Most Likely chances say what those picks win (step ACX).

Ethan, 23 November: "Okay, so for decision 19 I'd say do whatever you think.
All I want is picks that win the most on there, and we need to be truthful
about our shit."

The NBA's picks won more than they said (3,371 graded: said 61.2%, won
64.2%), on the overs and the unders alike, and more than the price said
too. Where our number and the price agree on a side, the record now learns
the chance those picks actually win — above both where it proves so — on
the same held-out bar as every correction (engine/likelycal.fit_agree).
One rule each: a record where agreeing picks win more than both numbers
passes and shows what they win; one where they win what the two say saves
nothing; it runs only where the record may raise a chance, and a switch
holds it; the board shows the number with a sentence that says why; a
raised pick is never read as a proven over-claim; the scout stacks on the
number the board shows; the nightly learning saves it and removes it when
it stops holding; the Record page says it.

Run directly: `python3 tests/test_nba_chances_say_what_they_win.py`
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
for _v in ("QB_LIKELY_CAL", "QB_LIKELY_CTX", "QB_LIKELY_AGREE", "QB_RECORD_RAISES", "QB_RECORD_AGREE"):
    os.environ.pop(_v, None)

from engine import boardlearn as B                                   # noqa: E402
from engine import ledger as LG                                      # noqa: E402
from engine import likelyboard as LB                                 # noqa: E402
from engine import likelycal as LC                                   # noqa: E402
from engine import likelyctx as CTX                                  # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)


def _sig(z):
    return 1.0 / (1.0 + math.exp(-z))


def _lg(p):
    return math.log(p / (1.0 - p))


def _picks(n_games=800, truth="agree", seed=19):
    """Two list picks a game. Each has a true chance; our number and the
    price are separate noisy reads of it, both pulled toward even money.
    ``truth="agree"``: they win their true chance, so where the two agree
    they win more than either says. ``truth="average"``: they win what the
    two numbers say together, so there is nothing to learn."""
    rng = random.Random(seed)
    out = []
    for g in range(n_games):
        for _ in range(2):
            side = "over" if rng.random() < 0.45 else "under"
            t = rng.gauss(0.75, 0.35)
            p = min(0.9, max(0.3, _sig(0.55 * t + rng.gauss(0, 0.18))))
            q = min(0.9, max(0.3, _sig(0.55 * t + rng.gauss(0, 0.18) + (0.05 if side == "over" else -0.05))))
            pt = _sig(t) if truth == "agree" else _sig((_lg(p) + _lg(q)) / 2)
            out.append({"day": f"2026-{10 + g // 200:02d}-{1 + (g // 8) % 28:02d}", "team": f"T{g}",
                        "player": f"P{g}-{len(out)}", "side": side, "p": round(p, 4), "q": q,
                        "won": rng.random() < pt})
    return out


def _odds(q):
    """The American price whose chance, its cut taken out, is ``q``."""
    imp = min(0.97, q * LC.DEVIG)
    return int(round(-100 * imp / (1 - imp))) if imp >= 0.5 else int(round(100 * (1 - imp) / imp))


def _rows(picks):
    """The fit's rows, as likelycal.journal_rows makes them."""
    return [{"group": f"list|{x['side']}", "p": x["p"], "q": LC.price_chance(_odds(x["q"])), "won": x["won"],
             "market": "pts", "game": f"{x['day']}|{x['team']}"} for x in picks]


def _ledger(picks, sport="nba"):
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    led = LG.connect(path)
    for x in picks:
        for cat in ("likely", "board"):
            led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, "
                        "hit_prob, status, category) VALUES (?,?,?,?,?,'pts',?,20.5,?,?,?,?)",
                        (sport, x["day"], x["day"], x["player"], x["team"], x["side"].upper(), _odds(x["q"]),
                         x["p"], "won" if x["won"] else "lost", cat))
    led.commit()
    return led


# --- the fit and its bar ------------------------------------------------------------------------
def test_where_agreeing_picks_win_more_than_both_numbers_it_passes_and_shows_what_they_win():
    rows = _rows(_picks())
    res = LC.fit_agree(None, "nba", rows=rows)
    assert res["passed"], res["held_out"]
    assert res["held_out"]["lo"] > 0 and res["held_out"]["corrected"] < res["held_out"]["raw"]
    assert set(res["groups"]) == {"list|both"}, "one fit a maker, overs and unders together"
    v = res["groups"]["list|both"]
    assert v["hit"] > max(v["claimed"], v["price"]) + 0.03, v
    assert abs(v["shown"] - v["hit"]) < 0.01, f"shown {v['shown']} against hit {v['hit']}"
    w = v["w"]
    for side in ("over", "under"):                            # each side shown what it won, near enough
        rs = [r for r in rows if r["group"] == f"list|{side}" and LC.agrees(r["p"], r["q"])]
        shown = sum(LC.agree_chance(r["p"], r["q"], w) for r in rs) / len(rs)
        assert abs(shown - sum(r["won"] for r in rs) / len(rs)) < 0.02, side
    assert LC.agree_chance(0.62, 0.63, w) > 0.66, "two agreeing reads: above both"
    assert w[1] >= 0 and w[2] >= 0, "a higher number from either never lowers ours"


def test_a_weight_held_at_zero_leaves_the_others_fitted_again():
    # Only our number matters here: the price's weight comes out at or under
    # zero, and the fit must still beat our raw number, never lose to it.
    rng = random.Random(7)
    rs = []
    for _ in range(1500):
        p = rng.uniform(0.55, 0.75)
        q = min(0.75, max(0.51, p + rng.gauss(0, 0.05)))
        rs.append({"p": p, "q": q, "won": rng.random() < _sig(_lg(p) + 0.14)})
    w = LC.fit_agree_one(rs)
    ll = lambda f: sum(LC._ll(f(r), r["won"]) for r in rs)  # noqa: E731
    assert ll(lambda r: LC.agree_chance(r["p"], r["q"], w)) < ll(lambda r: r["p"])
    assert w[1] > 0.3, w


def test_where_agreeing_picks_win_what_the_two_say_nothing_is_saved():
    res = LC.fit_agree(None, "nba", rows=_rows(_picks(truth="average")))
    assert res["held_out"]["n"] > 1000
    assert not res["passed"], res["held_out"]


def test_it_runs_only_where_the_record_may_raise_a_chance_and_the_switches_hold_it():
    assert LC.agree_on("nba") and LC.agree_on("nhl")
    assert not LC.agree_on("nfl") and not LC.agree_on("cfb") and not LC.agree_on("cbb")
    res = LC.fit_agree(None, "nfl", rows=_rows(_picks()))
    assert not res["passed"] and res["groups"] == {} and not res["on"]
    for var in ("QB_RECORD_AGREE", "QB_RECORD_RAISES"):
        os.environ[var] = "off"
        try:
            assert not LC.agree_on("nba"), var
        finally:
            os.environ.pop(var, None)
    assert LC.agrees(0.6, 0.55) and not LC.agrees(0.6, 0.45) and not LC.agrees(0.48, 0.6)
    assert not LC.agrees(0.6, None)


# --- the board ----------------------------------------------------------------------------------
W = [0.25, 0.8, 0.5]
AGREE = {"nba": {"groups": {"list|both": {"w": W, "n": 2900, "hit": 0.648, "claimed": 0.615, "price": 0.611,
                                          "shown": 0.648}}}}


def _row(prob=0.60, odds=-180, side="OVER"):
    return {"player": "X", "market": "pts", "side": side, "odds": odds, "model_prob": prob, "sources": ["likely"]}


def test_the_board_shows_the_agreement_number_and_says_why():
    rows = [_row(), _row(odds=120), _row(side="UNDER"), dict(_row(), sources=["matchup"])]
    assert LC.apply(rows, "nba", {}, AGREE) == 2
    r = rows[0]
    q = LC.price_chance(-180)
    assert r["model_prob"] == round(LC.agree_chance(0.60, q, W), 4) and r["model_prob"] > max(0.60, q)
    assert r["board_raw_prob"] == 0.60 and r["agree_from"] == 0.60 and r["cal_raised"] is True
    assert r["cal_note"] == ("Most Likely list picks where our number and the price agree have hit 65% of 2,900 "
                             "where we said 62% and the price (its cut taken out) 61%, so this shows "
                             f"{r['model_prob']:.0%} (our number 60%, its price {q:.0%})"), r["cal_note"]
    assert rows[1]["model_prob"] == 0.60 and "cal_note" not in rows[1], "a plus price disagrees: left to the k"
    assert rows[2]["model_prob"] == r["model_prob"], "the list's unders read the same fit"
    assert rows[3]["model_prob"] == 0.60, "no matchup fit saved: nothing moves"
    nfl = [_row()]
    assert LC.apply(nfl, "nfl", {}, {"nfl": AGREE["nba"]}) == 0 and nfl[0]["model_prob"] == 0.60


def test_the_agreement_number_replaces_the_k_and_keeps_what_the_k_would_show():
    store = {"nba": {"groups": {"list|over": {"k": 0.5, "n": 900, "hit": 0.66, "claimed": 0.61}}}}
    r = [_row(prob=0.58, odds=-200)]
    LC.apply(r, "nba", store, AGREE)
    q = LC.price_chance(-200)
    assert r[0]["agree_from"] == round(LC.shrink(0.58, q, 0.5, up=True), 4)
    assert r[0]["model_prob"] == round(LC.agree_chance(0.58, q, W), 4)
    # A caller that hands its own k store and no agreement store gets the k alone.
    r2 = [_row(prob=0.58, odds=-200)]
    LC.apply(r2, "nba", store)
    assert r2[0]["model_prob"] == round(LC.shrink(0.58, q, 0.5, up=True), 4) and "agree_from" not in r2[0]
    assert r2[0]["cal_raised"] is True, "raised toward its price"


def test_a_raised_pick_is_never_held_back_as_a_proven_over_claim():
    rows = [_row()]
    LC.apply(rows, "nba", {}, AGREE)
    checks = {"model": True, "matchup": False, "market": True, "record": None}
    assert LB.held_reason(rows[0], checks) is None, "the record says picks like it win MORE"
    lowered = dict(rows[0], cal_raised=False)
    assert LB.held_reason(lowered, checks).startswith("held back:"), "a lowered pick still is, as before"


def test_the_scout_stacks_on_the_number_the_board_shows():
    r = {"p": 0.60, "sources": ["likely"], "side": "OVER", "market": "pts"}
    q = LC.price_chance(-180)
    assert CTX._cal_base(r, q, {}, "nba", AGREE["nba"]["groups"]) == LC.agree_chance(0.60, q, W)
    cal = {"list|over": {"k": 0.5}}
    q2 = LC.price_chance(-250)
    assert CTX._cal_base(r, q2, cal, "nba") == LC.shrink(0.60, q2, 0.5, up=True) > 0.60, \
        "the NBA's raise toward the price, as the board shows it"
    assert CTX._cal_base(r, q2, cal, "nfl") == 0.60, "elsewhere only lowered"


# --- the nightly learning and the Record page ---------------------------------------------------
def test_the_nightly_learning_adopts_it_and_removes_it_when_it_stops_holding():
    rep = Path(tempfile.mkdtemp()) / "board_learning.json"
    lines = []
    ran = B.refresh(_ledger(_picks()), None, log=lines.append, sports=("nba",), path=rep)
    assert ran["nba"]["agree"]["passed"], ran["nba"]["agree"]
    assert set(LC.load_agree()["nba"]["groups"]) == {"list|both"}
    assert any("agreement correction adopted" in ln for ln in lines), lines
    assert json.loads(rep.read_text())["nba"]["agree"]["agreeing"] > 1000
    lines = []
    B.refresh(_ledger(_picks(truth="average")), None, log=lines.append, sports=("nba",), path=rep, force=True)
    assert "nba" not in LC.load_agree(), "the store holds what the record supports today"
    assert any("no longer proves its agreement correction" in ln for ln in lines), lines
    nfl = B.refresh(_ledger(_picks(), sport="nfl"), None, log=lambda *_: None, sports=("nfl",), path=rep)
    assert "agree" not in nfl["nfl"] and "nfl" not in LC.load_agree()
    # Switched off, a saved fit is neither refitted nor removed, and nothing says it was.
    LC.save_agree({"sport": "nba", "groups": {"list|both": {"w": W}}, "held_out": {}, "fitted_at": "x"})
    os.environ["QB_RECORD_AGREE"] = "off"
    try:
        lines = []
        off = B.refresh(_ledger(_picks(truth="average")), None, log=lines.append, sports=("nba",), path=rep,
                        force=True)
        assert "agree" not in off["nba"] and "nba" in LC.load_agree(), "kept for the day it is switched back on"
        assert not any("agreement" in ln for ln in lines), lines
    finally:
        os.environ.pop("QB_RECORD_AGREE", None)


def test_the_record_page_says_what_agreeing_picks_win():
    app = app_js()
    node = shutil.which("node")
    if not node:
        return
    i = app.index("function recBoardLearningSection(")
    fn = app[i:app.index("\nfunction ", i + 10)]
    base = {"at": "2026-11-24T03:00:00", "record": {"n": 3371, "won": 2164, "hit": 0.642, "said": 0.612,
                                                     "verdict": "beats its claim"},
            "slices": {}, "calibration": {"passed": False, "groups": {}}}
    on = dict(base, agree={"on": True, "passed": True, "agreeing": 2900,
                           "groups": {"list|both": {"n": 2900, "hit": 0.648, "claimed": 0.615, "price": 0.611,
                                                    "shown": 0.647}}})
    off = dict(base, agree={"on": True, "passed": False, "agreeing": 2900, "groups": {}})
    k = app.index("function recLg(")
    prog = ("const escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
            + app[k:app.index("\n}\n", k) + 3] + fn
            + f"\nconsole.log(recBoardLearningSection({json.dumps({'nba': on})}, 'nba'));"
            + f"\nconsole.log('OFF:' + recBoardLearningSection({json.dumps({'nba': off})}, 'nba'));"
            + f"\nconsole.log('NFL:' + recBoardLearningSection({json.dumps({'nfl': base})}, 'nfl'));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    html, rest = out.stdout.split("OFF:", 1)
    off_html, nfl_html = rest.split("NFL:", 1)
    assert "When our number and the price agree (2,900 graded picks)" in html
    assert ("list · both: hit 65% of 2,900 where we said 62% and the price 61% — now shown at what they win, "
            "65% on average") in html
    assert "Not proven on games the fit never saw — these picks keep the numbers above." in off_html
    assert "When our number and the price agree" not in nfl_html, "a league that never raises says nothing of it"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
