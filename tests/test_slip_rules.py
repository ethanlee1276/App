"""The reader's own slip obeys the engine's parlay rules.

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
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "const SLIP_MAX = 3;" in js
    j = js.index("async function slipCheck(")
    body = js[j:j + 2000]
    assert 'fetch("/api/parlay/check"' in body and 'method: "POST"' in body
    assert "cur.legs.splice(i, 1)" in body, "a killed pair must come back off"
    assert "got.warnings" in body, "a correlated pair must be named"
    k = js.index("function slipToggle(r)")
    tog = js[k:k + 3000]
    assert 'opponent: r.opponent || ""' in tog and 'game_date: r.game_date || r.date || ""' in tog, \
        "legs must carry what engine/parlays.game_key keys on"
    assert "slipCheck(key)" in tog


def test_even_money_is_spelled_minus_100_on_both_sides():
    assert P.decimal_to_american(2.0) == -100
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = js.index("function slipAmerican()")
    assert "dec > 2 ? Math.round((dec - 1) * 100)" in js[i:i + 900]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
