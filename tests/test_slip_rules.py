"""The engine's parlay rules, which the reader's own slip obeyed.

THE SLIP LEFT on 2026-10-31 (Ethan: "get rid of the parlay button and the
parlay feature"); the rules below stay, because Ask's parlay checker and the
Parlays page's pairing (engine/twoleg, through `relate`) still run on them.

Ethan, 2026-09-01, closing the QA audit's open question ("the engine
enforces 3 legs + conflict detection, the user slip allows 8 and prices
them as independent"): "3 legs" — the slip follows the model's rule.

Three things are pinned. The cap is three on the device and in the
share. Every added pair goes through `engine.parlays.relate` via
`check_ticket` — a killed pair (same player twice, teammates splitting
one pie, a duplicate) is refused with the mechanism as the reason, a
merely correlated pair is allowed and named. And the client sends the
fields the clash taxonomy keys on (opponent, game date, home/away), so
"same game" can be told from "same club".

Run directly: `python3 tests/test_slip_rules.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlays as P                                # noqa: E402


def _leg(player, market, side="OVER", team="LA", opp="SF", date="2026-09-13"):
    return {"player": player, "market": market, "side": side, "team": team,
            "opponent": opp, "game_date": date, "line": 1.5, "odds": -110}


def test_the_same_player_twice_is_refused_with_the_reason():
    got = P.check_ticket("nfl", [_leg("Davante Adams", "rec_yds"),
                                 _leg("Davante Adams", "receptions")])
    assert got["ok"] is False and got["pair"] == [0, 1]
    assert "same player" in got["reason"], got["reason"]


def test_two_teammates_splitting_one_pie_is_refused():
    got = P.check_ticket("nfl", [_leg("Davante Adams", "rec_yds"),
                                 _leg("Puka Nacua", "rec_yds")])
    assert got["ok"] is False
    assert "teammates" in got["reason"] or "cannibal" in got["reason"], got


def test_legs_from_different_games_pass_and_the_cap_is_three():
    legs = [_leg("Davante Adams", "rec_yds"),
            _leg("Patrick Mahomes", "pass_yds", team="KC", opp="BUF"),
            _leg("Aaron Judge", "hits", team="NYY", opp="BOS")]
    assert P.check_ticket("nfl", legs)["ok"] is True
    four = legs + [_leg("Anyone Else", "rush_yds", team="DAL", opp="NYG")]
    got = P.check_ticket("nfl", four)
    assert got["ok"] is False and "3 legs" in got["reason"]
    assert P.MAX_LEGS == 3


def test_garbage_legs_never_raise():
    assert P.check_ticket("nfl", [None, "x", {"player": 5}, {}])["ok"] is True
    assert P.check_ticket("", [])["ok"] is True


def test_the_server_route_and_the_client_call_exist():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"/api/parlay/check"' in src and "def _parlay_check(" in src
    i = src.index("def _parlay_check(")
    assert "check_ticket(sport, clean)" in src[i:i + 1500]
    # The slip's client call left with the slip (2026-10-31).
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "async function slipCheck(" not in js and "function slipToggle(" not in js


def test_even_money_is_spelled_minus_100_on_both_sides():
    assert P.decimal_to_american(2.0) == -100
    # The Record page's two-leg rows spell a ticket's price the same way
    # (the slip, which did too, left on 2026-10-31).
    rec = open(os.path.join(ROOT, "web", "js", "record.js"), encoding="utf-8").read()
    i = rec.index("const tlAmerican = ")
    assert "dec > 2 ? Math.round((dec - 1) * 100)" in rec[i:i + 200]


def _hr(player, team="PHI", opp="CHC", date="2026-09-02", **kw):
    d = dict(player=player, team=team, opponent=opp, market="home_runs",
             market_label="Home Runs", side="OVER", line=0.5, odds=400,
             game_date=date)
    d.update(kw)
    return d


def test_an_hr_leg_is_welcome_on_the_slip():
    """Ethan, 2026-09-02: "Yes use hr" — the engine refuses the market on
    its own tickets, a person may put it on theirs."""
    assert P.check_ticket("mlb", [_hr("A"), _leg("Q", "strikeouts")])["ok"] is True


def test_two_hr_legs_from_one_team_in_one_game_are_refused_not_warned():
    """"... just not players on the same team in the same game." Before
    this the pair was allowed with a +0.19 warning and the slip printed
    the independent price."""
    got = P.check_ticket("mlb", [_hr("A"), _hr("B")])
    assert got["ok"] is False and got["pair"] == [0, 1]
    assert got["reason"] == P.SAME_LINEUP_HR_REASON
    assert "same team in the same game" in got["reason"]


def test_two_hr_legs_from_different_teams_in_one_game_are_allowed():
    got = P.check_ticket("mlb", [_hr("A", "PHI", "CHC"), _hr("B", "CHC", "PHI")])
    assert got["ok"] is True


def test_two_hr_legs_from_one_team_on_different_days_are_two_lineups():
    got = P.check_ticket("mlb", [_hr("A", date="2026-09-02"),
                                 _hr("B", date="2026-09-03")])
    assert got["ok"] is True


def test_the_hr_rule_is_by_market_not_by_team_alone():
    """Two teammates on hits / total bases keep the taxonomy's answer
    (a permitted, priced lineup stack) — Ethan's rule names home runs."""
    got = P.check_ticket("mlb", [_leg("A", "hits", team="PHI", opp="CHC"),
                                 _leg("B", "total_bases", team="PHI", opp="CHC")])
    assert got["ok"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
