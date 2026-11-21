"""A parlay leg the book does not back is no leg (step AAM, 21 November).

Ethan, 2026-11-21: "We want to dial in the 3-leg parlays ... Be more elite,
think outside the box, look at all the data, figure out what we can use to our
advantage to make better picks".

Read off every settled Most Likely pick the public day records hold: our number
ranks a game's legs well in the NBA and hockey, but where it sits far above the
book's own chance it is our error. The NFL's legs we rated 60% or better at
prices of -100 to -130 hit 40% (78, where we said 75%). So in football and the
NBA a player-prop leg counts at the lower of our chance and the book's fair one
(gameparlays.book_capped); and an NBA prop one play settles (over 1.5
rebounds, over 0.5 threes, under 0.5 blocks: 62% against 68% for the rest) is
kept off every ticket (gameparlays.ONE_PLAY_LEGS). Hockey is left as it is.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")


def _leg(p, odds, fair=None, market="receptions", side="OVER", line=3.5):
    out = {"player": "A Player", "team": "NYG", "market": market, "side": side, "line": line, "odds": odds, "p": p}
    if fair is not None:
        out["fair"] = fair
    return out


def test_a_football_or_nba_leg_counts_at_the_lower_of_ours_and_the_books():
    hot = _leg(0.72, -110)
    for sport in ("nfl", "cfb", "nba"):
        got = GP.book_capped(hot, sport)
        assert got["p"] == round((110 / 210) / GP.BOOK_DEVIG, 4) and got["p_own"] == 0.72 and got["p_raw"] == 0.72, got
    for sport in ("nhl", "mlb", "cbb", "wnba"):
        assert GP.book_capped(hot, sport) is hot, f"{sport}: left as it is"
    # The leg's own de-vigged fair chance speaks first; a leg under the book's is untouched.
    assert GP.book_capped(_leg(0.66, -110, fair=0.61), "nfl")["p"] == 0.61
    calm = _leg(0.62, -250)
    assert GP.book_capped(calm, "nfl") is calm, "the book rates it likelier than we do"
    # Nothing to read the book by: the leg as it is. And our number before the learned
    # correction stays the journal's (`p_raw` kept when legfit set it).
    bare = {"player": "B", "market": "receptions", "p": 0.7}
    assert GP.book_capped(bare, "nfl") is bare
    pulled = dict(_leg(0.70, -110), p_raw=0.74)
    assert GP.book_capped(pulled, "nfl")["p_raw"] == 0.74
    os.environ["QB_BOOK_AGREES"] = "off"
    try:
        assert GP.book_capped(hot, "nfl") is hot
    finally:
        os.environ.pop("QB_BOOK_AGREES", None)


def test_a_claim_far_above_a_near_even_price_is_no_leg_in_football_and_still_one_in_hockey():
    row = EG._ml("Hot Claim", "NYG", "WR", "receptions", "Over", 3.5, 0.72, -110, "Receptions")
    row.pop("implied_prob")
    board = {"date": "2099-W10", "games": [EG.GAME], "most_likely": [row], "recommendations": []}
    assert [l for l in GP.legs_for(board, "nfl") if l["player"] == "Hot Claim"] == [], \
        "72% at -110: the book says 50%, under the 60% floor"
    nhl = [l for l in GP.legs_for(board, "nhl") if l["player"] == "Hot Claim"]
    assert len(nhl) == 1 and nhl[0]["p"] == 0.72


def test_ethans_own_ticket_is_priced_on_the_books_chances_and_says_so():
    """Nabers 5+ receptions (-250), Skattebo 12+ rush attempts (-200), Daniels 25+
    rushing yards (-200): we said 72%, 67% and 68%; at their prices the books say
    68%, 64% and 64%. The ticket is priced on those, and its card says ours."""
    rows = [EG._ml("Malik Nabers", "NYG", "WR", "receptions", "Over", 4.5, 0.72, -250, "Receptions"),
            EG._ml("Cam Skattebo", "NYG", "RB", "rush_att", "Over", 11.5, 0.67, -200, "Rush Attempts"),
            EG._ml("Jayden Daniels", "WAS", "QB", "rush_yds", "Over", 24.5, 0.68, -200, "Rushing Yards")]
    for r in rows:
        r.pop("implied_prob")
    board = {"date": "2099-W10", "games": [EG.GAME], "most_likely": rows, "recommendations": []}
    legs = {l["player"]: l for l in GP.enrich(GP.legs_for(board, "nfl"), board)}
    book = {"Malik Nabers": (250 / 350) / GP.BOOK_DEVIG, "Cam Skattebo": (200 / 300) / GP.BOOK_DEVIG,
            "Jayden Daniels": (200 / 300) / GP.BOOK_DEVIG}
    for who, q in book.items():
        assert legs[who]["p"] == round(q, 4) and legs[who]["p_own"] in (0.72, 0.67, 0.68), legs[who]
    t = GP.ticket("nfl", [legs["Malik Nabers"], legs["Cam Skattebo"], legs["Jayden Daniels"]], EG.GAME)
    indep = 1.0
    for q in book.values():
        indep *= round(q, 4)
    assert indep - 0.001 <= t["joint"] < indep + 0.03, (t["joint"], indep)
    held = [c for c in t["caveats"] if c.startswith("Each leg counts at the lower of our chance and the book's")]
    assert held and "Malik Nabers 68% (ours 72%)" in held[0], t["caveats"]
    assert "p_own" in GP.LEG_KEYS and GP.slim(legs["Malik Nabers"])["p_own"] == 0.72


def test_an_nba_prop_one_play_settles_rides_no_ticket():
    one = GP.one_play_leg
    for m, s, l in (("reb", "OVER", 1.5), ("reb", "Over", 0.5), ("fg3m", "OVER", 0.5), ("blk", "UNDER", 0.5)):
        assert one("nba", {"market": m, "side": s, "line": l}), (m, s, l)
        assert GP.off_parlays("nba", {"market": m, "side": s, "line": l}) == "one_play"
    for m, s, l in (("reb", "OVER", 2.5), ("fg3m", "OVER", 1.5), ("fg3m", "UNDER", 0.5), ("blk", "UNDER", 1.5),
                    ("ast", "OVER", 0.5), ("stl", "UNDER", 1.5), ("blk", "OVER", 0.5)):
        assert not one("nba", {"market": m, "side": s, "line": l}), (m, s, l)
    assert not one("nhl", {"market": "reb", "side": "OVER", "line": 1.5}), "the NBA's alone"
    assert "one_play" in GP.OFF_PARLAY_WORDS
    os.environ["QB_ONE_PLAY_LEGS"] = "off"
    try:
        assert not one("nba", {"market": "reb", "side": "OVER", "line": 1.5})
    finally:
        os.environ.pop("QB_ONE_PLAY_LEGS", None)


def _nba_row(player, market, side, line, p, odds=-220):
    return {"player": player, "team": "BOS", "opponent": "NYK", "home": "BOS", "away": "NYK", "position": "F",
            "market": market, "market_label": market, "side": side, "line": line, "odds": odds, "book": "DraftKings",
            "model_prob": p, "implied_prob": p, "bettable": True, "game_date": "2099-11-12",
            "kickoff": "2099-11-12T19:30:00-05:00"}


def test_the_board_keeps_the_pick_and_the_census_says_why_it_is_no_leg():
    game = {"home": "BOS", "away": "NYK", "date": "2099-11-12", "kickoff": "19:30"}
    rows = [_nba_row("Bench Big", "reb", "Over", 1.5, 0.67), _nba_row("Rim Guard", "blk", "Under", 0.5, 0.68),
            _nba_row("Good Wing", "reb", "Over", 4.5, 0.66), _nba_row("Ball Mover", "ast", "Over", 1.5, 0.66)]
    board = {"date": "2099-11-12", "games": [game], "most_likely": rows, "recommendations": []}
    legs = {l["player"] for l in GP.legs_for(board, "nba")}
    assert legs == {"Good Wing", "Ball Mover"}, legs
    assert len(board["most_likely"]) == 4, "nothing is taken off the board"
    picks = [{"player": r["player"], "market": r["market"], "side": "OVER" if r["side"] == "Over" else "UNDER",
              "line": r["line"]} for r in rows]
    fates = GP._picks_census(board, "nba", game, picks, now=dt.datetime(2099, 11, 12, 12, 0))
    assert fates.get("our_rule") == 2 and fates.get("strong") == 2, fates


def test_the_record_behind_the_rules_is_in_their_words():
    assert GP.BOOK_AGREE_SPORTS == ("nfl", "cfb", "nba") and GP.BOOK_DEVIG == 1.045
    assert GP.ONE_PLAY_LEGS == {"nba": (("reb", "OVER", 1.5), ("fg3m", "OVER", 0.5), ("blk", "UNDER", 0.5))}
    for words in ("hit 40% (78 legs, where we said 75%)", "NFL   62.9% → 66.4% early, 62.0% → 62.9% late",
                  "NBA   66.8% → 69.3% early, 66.3% → 67.1% late", "Switch: QB_BOOK_AGREES=off",
                  "on the record they hit 62% (337 legs rated 60% or better", "QB_ONE_PLAY_LEGS=off"):
        assert words in SRC, words
    # The rule is applied where a leg meets its floor, after the league's learned correction.
    body = SRC[SRC.index("def legs_for("):SRC.index("def scorer_legs(")]
    assert body.index("leg = legfit.apply(leg, sport, \"three\", w, shift)") < body.index("leg = book_capped(leg, sport)") \
        < body.index("float(leg.get(\"p\") or 0) < floor")


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
