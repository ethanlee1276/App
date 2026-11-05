"""The rotation's news moves the NBA's minutes, by measured rules
(engine/nba/minutes, `hoops.NBA`, docs/NBA_LAB.md "The scout").

Ethan, 2026-11-04: "I want to make sure we're picking the right bets,
reading the right scripts, picking the right models ... everything's tuned
in." The scout's first measurement on two full seasons found three things
our number did not know, each written as a rule with its bar set before
its run (fitted on one season beside a level factor, judged on the other,
kept only if minutes AND points error fell in both):

  * his FIRST GAME BACK plays light, more so the longer he was out
    (x0.96 / 0.92 / 0.84 for 1 / 2-4 / 5+ missed), and his SECOND after
    two or more missed a little (x0.96, x0.97 since 2026-11-04: refitted
    beside the starting five's news, engine/nba/starters, which took over
    part of it);
  * a ROLE THAT JUST JUMPED (newest three 20%+ over the seven before)
    mostly holds: the base moves 40% of the way to the newest three — a
    role that dropped did not pass and moves nothing;
  * a REGULAR'S RETURN (24+ minutes, back from two or more missed) takes a
    quarter of his minutes back from the rest, by their base minutes.

The WNBA keeps all three off: measured on the NBA only.

Run directly: `python3 tests/test_the_nba_rotation_news_is_measured.py`
"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hoops                          # noqa: E402
from engine.nba import minutes as M               # noqa: E402
from engine.nba import pipeline as P              # noqa: E402
import nba_build as B                             # noqa: E402

NBA, WNBA = hoops.NBA, hoops.WNBA


def test_the_measured_values_are_the_nbas_and_the_wnba_keeps_them_off():
    assert (NBA.role_jump_ratio, NBA.role_jump_weight) == (1.20, 0.40)
    assert NBA.back_mult == ((1, 0.96), (4, 0.92), (float("inf"), 0.84))
    assert NBA.second_back_mult == 0.97 and NBA.return_share == 0.25
    assert (WNBA.role_jump_weight, WNBA.back_mult, WNBA.second_back_mult, WNBA.return_share) == (0.0, (), 1.0, 0.0)
    spec = hoops.LeagueTuning(key="x", name="x")
    assert (spec.role_jump_weight, spec.back_mult, spec.return_share) == (0.0, (), 0.0), "off by default"


def test_a_role_that_jumped_moves_the_base_toward_his_newest_three():
    jumped = [34, 33, 35, 24, 25, 23, 26, 24, 25, 24]
    assert M.role_jump(25.0, jumped) == round(25.0 + 0.4 * (34.0 - 25.0), 2)
    steady = [26, 25, 27, 24, 25, 23, 26, 24, 25, 24]
    assert M.role_jump(25.0, steady) == 25.0, "under 1.2x the seven before: nothing"
    dropped = [15, 16, 14, 30, 31, 29, 30, 30, 31, 29]
    assert M.role_jump(28.0, dropped) == 28.0, "a drop did not pass its test and moves nothing"
    assert M.role_jump(25.0, jumped[:5]) == 25.0, "six games or more to read a jump"
    assert M.role_jump(25.0, jumped, WNBA) == 25.0 and M.role_jump(None, jumped) is None


def test_his_first_and_second_games_back_play_light():
    assert [M.back_multiplier(n) for n in (0, 1, 2, 4, 5, 40)] == [1.0, 0.96, 0.92, 0.92, 0.84, 0.84]
    assert M.back_multiplier(0, True) == 0.97 and M.back_multiplier(3, True) == 0.92, \
        "a first game back reads its own table, not the second's"
    assert M.back_multiplier(None) == 1.0 and M.back_multiplier("x") == 1.0
    assert M.back_multiplier(6, tune=WNBA) == 1.0 and M.back_multiplier(0, True, WNBA) == 1.0
    # After the caps, so a return can never lift him past them.
    assert M.project_minutes(30.0, 0.0, True, False, "1day") == 30.0
    assert M.project_minutes(30.0, 0.0, True, False, "1day", missed_games=3) == 27.6
    assert M.project_minutes(30.0, 0.0, True, False, "1day", second_back=True) == 29.1
    capped = M.project_minutes(30.0, 0.0, True, False, "1day", vacancy_minutes=30.0, recent_high=31.0,
                               missed_games=1)
    assert capped == round((31.0 + NBA.vacancy_cap_over_high) * 0.96, 1)


def _prop(**kw):
    return dict({"player": "X", "market": "pts", "minutes": [30.0] * 12, "values": [15.0] * 12,
                 "is_starter": True, "spread": 0.0, "rest": "1day"}, **kw)


def test_the_projection_carries_them_and_the_card_says_so():
    a = P.project(_prop())
    b = P.project(_prop(missed_games=6))
    assert b["proj_min"] == round(a["proj_min"] * 0.84, 1)
    assert abs(b["projection"] / b["proj_min"] - a["projection"] / a["proj_min"]) < 0.01, "the rate is untouched"
    assert any("First game back after missing 6 games" in n for n in b["context"]), b["context"]
    c = P.project(_prop(return_minutes=2.0, return_names="Y"))
    assert c["proj_min"] == a["proj_min"] - 2.0
    assert any("A regular is back tonight (Y)" in n for n in c["context"]), c["context"]
    d = P.project(_prop(vacancy_minutes=3.0, return_minutes=1.0))
    assert d["proj_min"] == a["proj_min"] + 2.0, "a vacancy and a return share the one signed slot"
    e = P.project(_prop(minutes=[36.0, 35.0, 37.0] + [25.0] * 9))
    assert any("His minutes just jumped" in n for n in e["context"]), e["context"]
    assert not any("jumped" in n or "game back" in n or "is back" in n for n in a["context"])


def _h(team, days, mins=30.0):
    return {"team": team, "starter": True, "by_week": {d: {"min": mins, "pts": 10.0} for d in days},
            "minutes": [mins] * min(20, len(days)), "dates": sorted(days, reverse=True)[:20]}


CLUB = ["2026-10-%02d" % d for d in range(20, 31)]


def test_the_build_reads_who_missed_what_from_the_logs():
    hist = {"A": _h("BOS", CLUB), "B": _h("BOS", CLUB[:-3]), "C": _h("BOS", CLUB[:-4] + CLUB[-1:]),
            "D": _h("BOS", CLUB[:-1], mins=12.0), "E": _h("BOS", CLUB[-1:])}
    days = B.club_days(hist, "2026-11-01")
    assert days["BOS"][0] == "2026-10-30" and len(days["BOS"]) == len(CLUB)
    reads = {p: B.return_read(hist[p], days["BOS"], "2026-11-01") for p in hist}
    assert reads == {"A": (0, False), "B": (3, False), "C": (0, True), "D": (1, False), "E": (0, False)}, reads
    # A game logged with no minutes is a game he missed.
    hist["A"]["by_week"]["2026-10-30"]["min"] = 0.0
    assert B.return_read(hist["A"], days["BOS"], "2026-11-01") == (1, False)
    hist["A"]["by_week"]["2026-10-30"]["min"] = 30.0
    # Nothing on or after tonight counts.
    assert B.club_days(hist, "2026-10-25")["BOS"][0] == "2026-10-24"


def test_a_regulars_return_takes_minutes_back_from_the_rest():
    hist = {"A": _h("BOS", CLUB), "B": _h("BOS", CLUB[:-3]), "D": _h("BOS", CLUB[:-1], mins=12.0),
            "F": _h("BOS", CLUB[:-3], mins=14.0)}
    days = B.club_days(hist, "2026-11-01")
    priced = {"A", "B", "D", "F"}
    back = B.returning(hist, days, "2026-11-01", {}, priced)
    assert back == {"BOS": [("B", 30.0)]}, "a regular (24+), back from two or more, and priced; F is not a regular"
    assert B.returning(hist, days, "2026-11-01", {}, priced - {"B"}) == {}, "no price, no return"
    assert B.returning(hist, days, "2026-11-01", {"B": {"status": "Out"}}, priced) == {}, "ruled out, no return"
    got = B.return_for("A", "BOS", back, hist, {}, NBA.return_share)
    rot = {"A": 30.0, "B": 30.0, "D": 12.0}
    assert abs(got - round(0.25 * 30.0 * rot["A"] / sum(rot.values()), 2)) < 0.02, got
    assert B.return_for("B", "BOS", back, hist, {}, NBA.return_share) == 0.0, "never from the returning man"
    assert B.return_for("A", "BOS", back, hist, {}, 0.0) == 0.0, "share 0 (the WNBA): nothing"
    assert B.return_for("A", "NYK", back, hist, {}, NBA.return_share) == 0.0


def test_the_build_puts_them_on_every_prop():
    src = (ROOT / "nba_build.py").read_text()
    for key in ('"missed_games": _missed or 0', '"second_game_back": bool(_second)',
                '"return_minutes": _ret_min', "_back = returning(hist, _days, args.date, listed"):
        assert key in src, key


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
