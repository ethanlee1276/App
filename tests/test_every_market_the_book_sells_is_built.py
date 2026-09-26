"""Every NFL market the odds pull buys is built for the positions that hold it.

Ethan, 2026-09-23: "do another scan and make sure all the models aren't
being affected by issues where data isn't being used or being pulled."

The scan found three:

  * THE ODDS PULL BOUGHT FOUR STAT MARKETS FOR EVERY PLAYER and the board
    built one per position — a receiver's yards, a tight end's catches, a
    back's rushing yards. A receiver's catches line, a tight end's yards
    and a back's receiving line were paid for on every pull and thrown
    away, with the matchup ratings measured for exactly those pairings
    left with nothing to act on (engine/sources/nflverse.POSITION_MARKETS);
  * EVERY RECEIVER WAS "wr1" AND EVERY BACK "rb1", so the injury rule for
    an opponent's slot corner (a "wr2" or "slot" receiver) could never
    fire (engine/injuries.py);
  * PASSING TOUCHDOWNS HAD NO MATCHUP at all — measured, nothing predicted
    them, so the card shows the defence and the number is left alone
    (engine/defensevs, tests/test_the_matchup_model_is_measured_and_shown).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import nflverse as N                            # noqa: E402
from engine.sources import oddsapi as O                             # noqa: E402
from engine.models import (Prop, Injury, SportsbookLine, REC_YDS, RECEPTIONS, RUSH_YDS,  # noqa: E402
                           DefenseProfile)


def _rows(team, pos, name, vol, weeks=(1, 2, 3), **stats):
    col = {"QB": "attempts", "RB": "carries"}.get(pos, "targets")
    return [{"season_type": "REG", "week": str(w), "recent_team": team, "position": pos,
             "player_display_name": name, col: str(vol), **{k: str(v) for k, v in stats.items()}} for w in weeks]


def test_every_stat_market_the_pull_buys_has_a_position_that_builds_it():
    bought = set(O.NFL_ODDS_TO_MARKET.values())
    built = {m for markets in N.POSITION_MARKETS.values() for m, _r in markets}
    assert bought <= built, f"paid for and never built: {sorted(bought - built)}"
    held = {(pos, m) for pos, markets in N.POSITION_MARKETS.items() for m, _r in markets}
    for pair in (("WR", RECEPTIONS), ("TE", REC_YDS), ("RB", REC_YDS), ("RB", RECEPTIONS)):
        assert pair in held, f"{pair}: the book sells it and the matchup is measured for it"
    assert ("QB", RUSH_YDS) not in held, "measured weakest of all (0.536); stays off until it ranks"


def test_a_position_s_own_market_comes_first_and_the_rest_have_a_floor():
    assert [m for m, _r in N.POSITION_MARKETS["WR"]][0] == REC_YDS
    assert [m for m, _r in N.POSITION_MARKETS["TE"]][0] == RECEPTIONS
    assert [m for m, _r in N.POSITION_MARKETS["RB"]][0] == RUSH_YDS
    assert N.is_secondary("WR", RECEPTIONS) and N.is_secondary("RB", REC_YDS)
    assert not N.is_secondary("WR", REC_YDS) and not N.is_secondary("TE", RECEPTIONS)
    assert N.SECONDARY_FLOOR == {REC_YDS: 12.0, RECEPTIONS: 1.5}, "the college board's floors"


def test_receivers_and_backs_are_ranked_on_their_team():
    rows = (_rows("BUF", "WR", "Alpha", 10) + _rows("BUF", "WR", "Bravo", 7) + _rows("BUF", "WR", "Charlie", 4)
            + _rows("BUF", "WR", "Delta", 1) + _rows("BUF", "RB", "Echo", 18) + _rows("BUF", "RB", "Foxtrot", 6)
            + _rows("BUF", "TE", "Golf", 5) + _rows("BUF", "QB", "Hotel", 33))
    specs = N.top_players_for_week(rows, {"BUF"}, 4)
    role = {(s.player, s.market): (s.usage_role, s.position) for s in specs}
    assert role[("Alpha", REC_YDS)] == ("wr1", "WR") and role[("Bravo", REC_YDS)] == ("wr2", "WR")
    assert role[("Charlie", RECEPTIONS)] == ("wr3", "WR"), "every market of his carries his rank"
    assert ("Delta", REC_YDS) not in role, "the top three by volume, as before"
    assert role[("Echo", RUSH_YDS)] == ("rb1", "RB") and role[("Foxtrot", REC_YDS)] == ("rb2", "RB")
    assert role[("Golf", REC_YDS)] == ("te", "TE") and role[("Hotel", "pass_td")] == ("starter", "QB")


def test_the_slot_corner_rule_can_fire_now():
    from engine.injuries import evaluate_injuries
    inj = [Injury(player="Nickel Back", team="DET", position="CB", role="slot_cb", status="OUT")]

    def mult(role):
        p = Prop(player="W", team="NO", opponent="DET", position="WR", market=REC_YDS, logs=[],
                 career_avg=0.0, vs_opponent_avg=None, lines=[SportsbookLine("x", 50.5)], usage_role=role)
        return evaluate_injuries(p, inj).multiplier
    assert mult("wr2") > 1.0, "a number two receiver against a missing slot corner"
    assert mult("wr1") == 1.0


def test_a_third_receiver_reads_the_receiver_rating_in_the_fallback():
    from engine.matchup import _defense_factor
    d = DefenseProfile(team="DET", vs_wr1=1.2, vs_wr2=1.1, vs_rb_recv=0.8)
    p = Prop(player="W", team="NO", opponent="DET", position="WR", market=RECEPTIONS, logs=[],
             career_avg=0.0, vs_opponent_avg=None, lines=[], usage_role="wr3")
    assert _defense_factor(d, p) == (1.1, "vs receivers"), "not the pass-catching-backs number"
    p.usage_role, p.position = "rb2", "RB"
    assert _defense_factor(d, p)[0] == 0.8


def _row(market, pos, role, steps, book="FanDuel"):
    return {"market": market, "position": pos, "usage_role": role, "book": book,
            "chain": {"steps": [{"key": k, "mult": m} for k, m in steps.items()]}}


def test_the_droplet_check_names_a_step_that_moves_nothing():
    from engine import inputcheck as C
    rows = ([_row("rec_yds", "WR", "wr1", {"matchup": 1.05, "weather": 1.0, "trend": 1.0, "park": 1.0})] * 25
            + [_row("rush_yds", "RB", f"rb{1 + i % 2}", {"matchup": 1.0, "injury": 1.0}, book="proxy")
               for i in range(25)])
    got = C.findings("nfl", C.census(rows))
    assert "nfl rec_yds: 'Ballpark' moved none of 25 rows — wired in and reading nothing?" in got
    assert "nfl rec_yds: 'Weather' moved none of 25 rows — wired in and reading nothing?" in got
    assert not [x for x in got if "Recent-form" in x], "off by design is not a finding"
    assert not [x for x in got if "Injuries" in x], "a quiet injury report is normal"
    assert "nfl rush_yds: no row has a real book price (25 rows, all proxy)" in got
    assert "nfl rec_yds: every WR carries the role 'wr1' — the depth order is not reaching the model" in got
    assert not [x for x in got if "every RB" in x], "two roles among the backs"
    few = C.findings("nfl", C.census([_row("rec_yds", "WR", "wr1", {"park": 1.0})] * 5))
    assert few == [], "five rows say nothing"
    known = [_row("pass_td", "QB", "starter", {"matchup": 1.0, "weather": 1.0})] * 25
    assert C.findings("nfl", C.census(known)) == [], "measured and left out on purpose"
    text = "\n".join(C.report({"nfl": {"recommendations": rows + known}, "mlb": "unreadable — x"}))
    assert "LOOK AT THESE:" in text and "known: pass_td matchup" in text and "mlb: unreadable" in text


def test_homecheck_runs_it():
    import homecheck
    assert homecheck.CHECKS["inputs"][0] is homecheck.inputs and homecheck.CHECKS["inputs"][2] is True


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
