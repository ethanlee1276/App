"""No parlay the site builds or suggests carries a tackle, sack or kicking leg (2026-11-14).

Ethan, 2026-11-14, of the game reports' parlays: "i dont wanna use tackle
picks or anything like that. and not kicker points either. so please dont
incluide those." One list (engine/parlays.NO_PARLAY_MARKETS), asked where
every leg of the two-leg tickets and of each game's tickets is made
(engine/twoleg._leg), by the parlay screen's own leg gate
(parlays._leg_eligible), and by the builder's "stacks well with"
(engine/parlaybuild.stacks). The props stay on the boards as singles.

    python3 tests/test_parlays_carry_no_tackle_or_kicker_legs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP                     # noqa: E402

from engine import parlaybuild as PB                     # noqa: E402
from engine import parlays as P                          # noqa: E402
from engine import twoleg as T                           # noqa: E402

GAME = {"home": "NYG", "away": "WAS", "date": "2099-11-12", "kickoff": "20:15", "spread": -2.5, "total": 40.5}


def _row(player, pos, market, line, p, odds=-200, team="NYG", **kw):
    opp = "WAS" if team == "NYG" else "NYG"
    r = {"player": player, "team": team, "opponent": opp, "home": "NYG", "away": "WAS", "position": pos,
         "market": market, "market_label": market, "side": "Over", "line": line, "odds": odds,
         "book": "DraftKings", "model_prob": p, "hit_prob": p, "has_market": True, "recommended": True,
         "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00"}
    r.update(kw)
    return r


KEEP = [_row("Malik Nabers", "WR", "receptions", 4.5, 0.72, -250),
        _row("Cam Skattebo", "RB", "rush_att", 11.5, 0.67),
        _row("Isaiah Likely", "TE", "receptions", 3.5, 0.70, -225),
        _row("Jayden Daniels", "QB", "rush_yds", 24.5, 0.68, team="WAS"),
        _row("Chig Okonkwo", "TE", "receptions", 2.5, 0.66, -190, team="WAS")]
DROP = [_row("Bobby Okereke", "LB", "tackles_ast", 6.5, 0.74, -180),
        _row("Graham Gano", "K", "kick_pts", 5.5, 0.70, -160),
        _row("Jake Moody", "K", "fg_made", 1.5, 0.69, -190, team="WAS"),
        _row("Frankie Luvu", "LB", "sacks", 0.5, 0.66, -150, team="WAS")]


def test_the_list_names_the_boards_three_and_their_other_spellings():
    for m in ("tackles_ast", "kick_pts", "fg_made", "tackles", "solo_tackles", "sacks", "kicking_points",
              "field_goals", "extra_points"):
        assert not P.parlay_market(m), m
        assert not P.parlay_market(m.upper() + " "), "read as the feeds spell it"
    for m in ("receptions", "rush_att", "anytime_td", "pts", "strikeouts", "sog", "assists", "blocks", "spread"):
        assert P.parlay_market(m), m


def test_no_leg_is_ever_made_of_one():
    for r in DROP:
        assert T._leg(r, r["model_prob"], "likely") is None, r["market"]
    assert T._leg(KEEP[0], 0.72, "likely") is not None


def test_each_games_tickets_and_the_two_leg_tickets_leave_them_off():
    board = {"date": "2099-W10", "games": [GAME], "most_likely": KEEP + DROP, "recommendations": KEEP + DROP}
    legs = {l["market"] for l in GP.legs_for(board, "nfl")}
    assert legs and not legs & P.NO_PARLAY_MARKETS, legs
    gp = GP.build(board, "nfl")
    on = {l["market"] for g in gp["games"] for t in g["threes"] for l in t["legs"]}
    on |= {b["leg"]["market"] for g in gp["games"] for t in g["threes"] for b in t.get("backups") or []}
    assert on and not on & P.NO_PARLAY_MARKETS, on
    for get in (T.likely_legs, T.edge_legs):
        got = {l["market"] for l in get(board, "nfl")}
        assert got and not got & P.NO_PARLAY_MARKETS, got


def test_the_screen_refuses_one_and_says_why():
    why = P._leg_eligible("nfl", dict(DROP[1], leg_basis="likely"), GAME, P.RULES["nfl"])
    assert "never rides on a parlay" in why and "kicking" in why, why
    assert "never rides on a parlay" not in P._leg_eligible("nfl", dict(KEEP[0], leg_basis="likely"), GAME,
                                                            P.RULES["nfl"])


def test_the_builder_never_suggests_one():
    picked = [dict(KEEP[0], p=0.72)]
    pool = [dict(r, p=r["model_prob"]) for r in DROP + KEEP[1:]]
    seen = {s["market"] for s in PB.stacks("nfl", picked, pool)}
    assert not seen & P.NO_PARLAY_MARKETS, seen


def test_every_leg_maker_goes_through_the_one_check():
    src = (ROOT / "engine" / "twoleg.py").read_text(encoding="utf-8")
    body = src[src.index("def _leg("):src.index("\ndef ", src.index("def _leg(") + 5)]
    assert "if not parlay_market(r.get(\"market\")):" in body
    gp = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert gp.count("T._leg(") == 3, "priced, pool and scorer legs are all made by twoleg._leg"


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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
