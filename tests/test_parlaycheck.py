"""parlaycheck: does a published ticket hold together on its own terms?

The Parlay Zone picks a correlation prior from the legs' `team` and
`opponent` fields, and the SIGN of that prior depends on them. An MLB
pitcher's strikeout over beside a moneyline is +0.275 when the moneyline
is his own team and a kill when it is the opponent's — so one stale
roster entry turns a refusal into a published ticket that bets both ways,
with a confident mechanism sentence attached and nothing downstream to
notice.

These pin the audit that catches that shape. Fixtures are built by hand
rather than read off disk: a check whose verdict depends on whatever the
last build happened to write is not a check.

Run directly: `python3 tests/test_parlaycheck.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parlaycheck as pc                                      # noqa: E402


def _leg(player, team, opp, market="strikeouts", side="OVER"):
    return {"player": player, "team": team, "opponent": opp,
            "market": market, "side": side, "line": 4.5, "odds": 102}


def _ticket(legs, pairs, kind="A", rank=1):
    return {"rank": rank, "parlay_type": kind, "grade": "marginal",
            "qualified": True, "legs": legs, "pairs": pairs}


def _pair(a, b, rho, mech="managers leave winners in"):
    return {"a": a, "b": b, "rho": rho, "rho_priced": rho * 0.45,
            "rho_measured": False, "mechanism": mech}


# --- the shape it exists to catch -------------------------------------------
def test_a_positive_rho_between_opponents_is_reported():
    """The stale-roster signature. Mize priced as if he pitches for the team
    the moneyline backs, while his own fields say he faces them."""
    t = _ticket([_leg("Casey Mize", "DET", "SD"),
                 _leg("SD ML", "SD", "DET", market="moneyline")],
                [_pair("Casey Mize", "SD ML", 0.275)])
    bad = pc.audit_ticket(t)
    assert bad, "a positive prior between opponents went unreported"
    assert "OPPOSITE" in bad[0]
    assert "+0.28" in bad[0] or "+0.27" in bad[0]
    # The claimed mechanism is quoted, because that sentence is what a
    # reader believed.
    assert "managers leave winners in" in bad[0]


def test_the_same_ticket_is_clean_once_the_roster_is_right():
    """Positive control: with Mize actually on San Diego, this is §5.1's
    construction and must pass untouched."""
    t = _ticket([_leg("Casey Mize", "SD", "DET"),
                 _leg("SD ML", "SD", "DET", market="moneyline")],
                [_pair("Casey Mize", "SD ML", 0.275)])
    assert pc.audit_ticket(t) == []


def test_a_type_a_ticket_whose_legs_are_in_different_games_is_reported():
    t = _ticket([_leg("SP1", "PHI", "CHC"), _leg("SP2", "SEA", "TEX")],
                [_pair("SP1", "SP2", 0.0)], kind="A")
    bad = pc.audit_ticket(t)
    assert any("Type A" in b and "2 different matchups" in b for b in bad)


def test_a_type_b_ticket_that_shares_a_game_is_reported():
    """The mirror. A cross-game label means no correlation tax came off the
    price, so a same-game pair wearing it is priced too generously."""
    t = _ticket([_leg("SP1", "PHI", "CHC"), _leg("Bat1", "PHI", "CHC")],
                [_pair("SP1", "Bat1", 0.10)], kind="B")
    bad = pc.audit_ticket(t)
    assert any("Type B" in b for b in bad)


def test_a_negative_or_zero_rho_between_opponents_is_left_alone():
    """Opponents SHOULD relate negatively — that is the engine working, and
    flagging it would train a reader to ignore this tool."""
    t = _ticket([_leg("Casey Mize", "DET", "SD"),
                 _leg("SD ML", "SD", "DET", market="moneyline")],
                [_pair("Casey Mize", "SD ML", -0.10)])
    assert pc.audit_ticket(t) == []


def test_a_pair_naming_a_leg_that_is_not_on_the_ticket_does_not_crash():
    t = _ticket([_leg("SP1", "PHI", "CHC")],
                [_pair("SP1", "Ghost", 0.30)])
    assert pc.audit_ticket(t) == []


# --- the board level ---------------------------------------------------------
def _board(tmp: Path, tickets, verdict="2 tickets cleared."):
    p = tmp / "mlb_recommendations.json"
    p.write_text(json.dumps({"parlays": {"verdict": verdict,
                                         "tickets": tickets}}))
    return p


def test_a_clean_board_exits_zero_and_a_dirty_one_does_not():
    tmp = Path(tempfile.mkdtemp())
    clean = _board(tmp, [_ticket(
        [_leg("Casey Mize", "SD", "DET"),
         _leg("SD ML", "SD", "DET", market="moneyline")],
        [_pair("Casey Mize", "SD ML", 0.275)])])
    assert pc.audit_board("mlb", clean, quiet=True) == 0

    dirty = _board(tmp, [_ticket(
        [_leg("Casey Mize", "DET", "SD"),
         _leg("SD ML", "SD", "DET", market="moneyline")],
        [_pair("Casey Mize", "SD ML", 0.275)])])
    assert pc.audit_board("mlb", dirty, quiet=True) == 1


def test_an_unbuilt_or_unreadable_board_is_not_a_failure():
    """A sport that never built has nothing to audit. Reporting that as a
    problem is how a check gets ignored."""
    tmp = Path(tempfile.mkdtemp())
    missing = tmp / "nope.json"
    assert pc.audit_board("nfl", missing, quiet=True) == 0
    junk = tmp / "junk.json"
    junk.write_text("{not json")
    assert pc.audit_board("nfl", junk, quiet=True) == 0


def test_every_board_path_names_a_sport_the_engine_screens():
    from engine import parlays as P
    for sport in pc.BOARDS:
        assert sport in P.RULES, f"{sport} has no screen — the path is dead"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
