"""UFC fights in the parlay checker, off the UFC card's own model.

Ethan, 2026-10-14, "do 1-11", to the call "UFC in the parlay checker? A
fight leg reads 'not on our board' today (step 38b)": yes.

A fight leg is read off the bout the UFC build priced (engine/slipfight):
who wins at the board's own chance, how in the model's own split of each
corner's wins, when in the shape the round prices assume. Two legs on one
bout are priced together off those outcomes, exactly, in the ticket's
chance, the 2,000-night replay and the pairs the card names. A bout the
board passed on before pricing gets no number, with its reason. The live
fight feed settles a fight leg once it names a winner, and, for a leg that
asks how or when, how and when it ended.

Every test builds its card with the UFC model itself (engine/ufc/model
.run_card) and its round prices off a throwaway database; nothing reads the
box's files or the network.

    python3 tests/test_ufc_fights_in_the_parlay_checker.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db                                             # noqa: E402
from engine import slipfight as SF                                # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import sliplive as SL                                 # noqa: E402
from engine.ufc import rounds as R                                # noqa: E402
from engine.ufc.model import run_card                             # noqa: E402

A, B = "Alex Stone", "Ben Rook"
BOUT = f"{A} vs {B}"


def _fighter(name, **over):
    d = {"name": name, "age": 29, "division": "lightweight", "archetype": "pressure", "ufc_fights": 8,
         "fights": 14, "slpm": 4.5, "sapm": 3.5, "kd_per100": 1.2, "td_per15": 1.0, "td_acc": 0.40,
         "tdd": 0.65, "ctrl_per15": 2.0, "sub_att_per15": 0.4, "ko_losses": 1, "ko_losses_last3": 0,
         "times_finished": 2, "r3_decay": 0.12, "red_flags": []}
    d.update(over)
    return d


def _card(round_prices=True):
    fights = [
        {"a": _fighter(A, slpm=6.0, sapm=2.5, kd_per100=2.0), "b": _fighter(B, ko_losses=3, ko_losses_last3=1),
         "prices": {"fighter_a": A, "fighter_b": B, "a_odds": -160, "b_odds": 140, "book": "fanduel"},
         "division": "lightweight"},
        {"a": None, "b": _fighter("Dan Hale"),
         "prices": {"fighter_a": "Carl Moss", "fighter_b": "Dan Hale", "a_odds": -120, "b_odds": 100},
         "division": "welterweight"},
    ]
    out = run_card(fights)
    if round_prices:
        conn = db.connect(":memory:")
        db.upsert_ufc_fights(conn, [
            {"fighter": f"F{i}", "fighter_id": "1", "comp_id": f"c{i}", "event_id": "e", "date": "2026-01-01",
             "opp": "X", "opp_id": "2", "result": "W", "method": "KO/TKO", "rnd": 1 + i % 3,
             "clock": f"{1 + i % 4}:00", "secs": 0.0, "rounds": 3, "division": "Lightweight"}
            for i in range(130)])
        conn.commit()
        assert R.attach(out, conn) == 1
    return dict(out, event_date="2026-10-18")


def _leg(market, side, line=0.0, team="", game=BOUT, odds=-110):
    return {"sport": "ufc", "player": "", "team": team, "game": game, "market": market, "side": side,
            "line": float(line), "odds": odds, "text": ""}


def _bout(board):
    return next(r for r in SF.bouts(board) if r["fight"] == BOUT)


def _p(board, leg):
    return SG.price_leg({"ufc": board}, leg)


def test_a_fighters_moneyline_is_the_boards_own_number():
    board = _card()
    bout = _bout(board)
    pick_a = bout["pick"] == A
    mine = bout["p_final"] if pick_a else 1.0 - bout["p_final"]
    a, b = _p(board, _leg("moneyline", "team", team=A, odds=-160)), _p(board, _leg("moneyline", "team", team=B))
    assert a["found"] == b["found"] == "fight" and a["league"] == "ufc" and a["game"] == BOUT
    assert abs(a["prob"] - mine) < 1e-9 and abs(a["prob"] + b["prob"] - 1.0) < 1e-9
    assert a["needs"] == SG.implied(-160) and a["opponent"] == B
    head = SG.why({"ufc": board}, a)[0]
    assert head["k"] == "Our model" and head["t"].startswith(f"{A} wins {round(a['prob'] * 100)}% by our model")
    # A surname, or an initial and a surname, finds the same fighter.
    assert _p(board, _leg("moneyline", "team", team="Stone"))["prob"] == a["prob"]
    assert _p(board, _leg("moneyline", "team", team="A. Stone"))["prob"] == a["prob"]


def test_how_and_when_are_read_off_the_bouts_own_outcomes():
    board = _card()
    ml = _p(board, _leg("moneyline", "team", team=A))["prob"]
    ko, sub, dec = (_p(board, _leg(m, "yes", team=A))["prob"] for m in ("win_ko", "win_sub", "win_dec"))
    assert abs(ko + sub + dec - ml) < 1e-9, "his methods are his wins, split"
    assert abs(_p(board, _leg("win_finish", "yes", team=A))["prob"] - (ko + sub)) < 1e-9
    yes, no = (_p(board, _leg("fight_distance", s))["prob"] for s in ("yes", "no"))
    assert abs(yes + no - 1.0) < 1e-9
    for x in (1.5, 2.5):
        over, under = (_p(board, _leg("fight_rounds", s, x))["prob"] for s in ("over", "under"))
        assert abs(over + under - 1.0) < 1e-9
    ends = [_p(board, _leg("fight_round", "yes", r))["prob"] for r in (1, 2, 3)]
    assert abs(sum(ends) - no) < 1e-9, "a finish lands in some round"
    # Near the board's own fair numbers (they read the model before the clamp).
    shown = {c["selection"]: c["p_model"] for c in _bout(board)["market_board"]}
    assert abs(_p(board, _leg("fight_rounds", "under", 1.5))["prob"] - shown["Under 1.5 rounds"]) < 0.02
    facts = {f["k"]: f["t"] for f in SG.why({"ufc": board}, _p(board, _leg("win_ko", "yes", team=A)))}
    assert "Fair number" in facts and "How it ends" in facts and "The board" in facts


def test_two_legs_on_one_fight_are_priced_together():
    board = _card()
    ml, other = _p(board, _leg("moneyline", "team", team=A)), _p(board, _leg("moneyline", "team", team=B))
    ko = _p(board, _leg("win_ko", "yes", team=A))
    dist = _p(board, _leg("fight_distance", "yes"))
    over = _p(board, _leg("fight_rounds", "over", 1.5))
    assert abs(SG.joint([ml, ko])[0] - ko["prob"]) < 1e-9, "by KO is a piece of winning"
    p, notes = SG.joint([ml, other])
    assert p == 0.0 and notes[0]["exclusive"] and notes[0]["why"].startswith("the same fight")
    assert SG.joint([dist, ko])[0] == 0.0
    both = SG.joint([ml, over])[0]
    assert 0.0 < both < min(ml["prob"], over["prob"]) and abs(both - ml["prob"] * over["prob"]) > 1e-4
    card = SG.grade({"legs": [_leg("moneyline", "team", team=A), _leg("fight_rounds", "over", 1.5)],
                     "total_odds": 200, "stake": 10, "book": "FanDuel"}, {"ufc": board})
    assert abs(card["ours"] - round(both, 4)) < 1e-4
    assert abs(card["sim"]["rate"] - both) < 0.04, "the replay draws one ending a night"
    # Another bout's leg multiplies, as another game's does.
    hale = _p(board, _leg("moneyline", "team", team="Dan Hale", game="Carl Moss vs Dan Hale"))
    assert hale["prob"] is None


def test_a_bout_the_board_passed_on_gets_no_number_and_says_why():
    board = _card()
    leg = _p(board, _leg("moneyline", "team", team="Carl Moss", game="Carl Moss vs Dan Hale"))
    assert leg["found"] == "fight" and leg["prob"] is None and leg["verdict"] == "unpriced"
    facts = SG.why({"ufc": board}, leg)
    assert facts and facts[0]["t"].startswith("No number on this fight: no dossier for Carl Moss")


def test_a_round_leg_needs_the_round_prices():
    board = _card(round_prices=False)
    assert _p(board, _leg("fight_rounds", "over", 1.5))["prob"] is None
    assert _p(board, _leg("fight_round", "yes", 2))["prob"] is None
    assert _p(board, _leg("fight_distance", "yes"))["prob"] is not None, "the distance is the model's own"
    priced = _card()
    assert _p(priced, _leg("fight_rounds", "over", 3.5))["prob"] is None, "no such number on a three-rounder"


def test_a_fight_not_on_the_card_is_not_on_our_board():
    board = _card()
    leg = _p(board, _leg("moneyline", "team", team="Nobody Here", game="Nobody Here vs Somebody Else"))
    assert leg["found"] == "" and leg["prob"] is None
    assert _p({}, _leg("moneyline", "team", team=A))["found"] == ""


def test_the_reader_and_the_cleaner_take_fight_legs():
    assert "ufc" in SG.SPORTS and "ufc" in SG.SCHEMA["properties"]["legs"]["items"]["properties"]["sport"]["enum"]
    for m in SF.MARKETS:
        assert m in SG.MARKETS and m in SG.MARKET_WORDS and m in SG.SYSTEM, m
    raw = {"is_bet_slip": True, "legs": [
        dict(_leg("moneyline", "team"), player=A),                 # the fighter under player: moved to team
        _leg("win_ko", "yes", team=A), _leg("fight_distance", "no"), _leg("fight_rounds", "over", 2.5),
        _leg("fight_round", "yes", 2),
        _leg("win_ko", "over", team=A), _leg("fight_round", "yes", 2.5), _leg("fight_rounds", "over", 0),
        dict(_leg("fight_distance", "yes"), game=""),               # no bout named at all
    ]}
    got = SG.clean_slip(raw)
    assert [l["market"] for l in got["legs"]] == ["moneyline", "win_ko", "fight_distance", "fight_rounds",
                                                  "fight_round"] and got["dropped"] == 4
    assert got["legs"][0]["team"] == A and got["legs"][0]["player"] == ""
    long = SG.clean_slip({"legs": [_leg("fight_distance", "yes", game="Valentina Shevchenko vs Alexandra Albu-Kowalski")]})
    assert long["legs"][0]["game"].endswith("Kowalski"), "a fight's label is longer than a game's"


def _feed(bouts, age=0.0):
    d = tempfile.mkdtemp()
    p = Path(d) / SF.LIVE_FILE
    p.write_text(json.dumps({"status": "card", "bouts": bouts}), encoding="utf-8")
    if age:
        t = time.time() - age
        os.utime(p, (t, t))
    return d


def _bout_feed(state, a_wins=None, method=None, rnd=0, clock=""):
    return {"id": "1", "status": {"state": state, "live": state == "in", "detail": "", "round": rnd,
                                  "clock": clock, "method": method},
            "fighters": [{"name": A, "winner": a_wins is True}, {"name": B, "winner": a_wins is False}]}


def test_the_live_feed_settles_each_kind_of_fight_leg():
    live = SL.Live({}, fast_dir=_feed([_bout_feed("post", True, "KO/TKO", 2, "3:12")]))

    def res(leg):
        return (live.state(dict(leg, league="ufc")) or {}).get("result")
    assert res(_leg("moneyline", "team", team=A)) == "won" and res(_leg("moneyline", "team", team=B)) == "lost"
    assert res(_leg("win_ko", "yes", team=A)) == "won" and res(_leg("win_dec", "yes", team=A)) == "lost"
    assert res(_leg("win_finish", "yes", team=A)) == "won" and res(_leg("win_ko", "yes", team=B)) == "lost"
    assert res(_leg("fight_distance", "yes")) == "lost" and res(_leg("fight_distance", "no")) == "won"
    assert res(_leg("fight_rounds", "over", 1.5)) == "won", "R2 3:12 is 1.64 rounds in"
    assert res(_leg("fight_rounds", "under", 2.5)) == "won" and res(_leg("fight_rounds", "over", 2.5)) == "lost"
    assert res(_leg("fight_round", "yes", 2)) == "won" and res(_leg("fight_round", "yes", 1)) == "lost"
    dec = SL.Live({}, fast_dir=_feed([_bout_feed("post", False, "DEC", 3, "5:00")]))
    assert dec.state(dict(_leg("fight_rounds", "over", 2.5), league="ufc"))["result"] == "won"
    assert dec.state(dict(_leg("fight_distance", "yes"), league="ufc"))["result"] == "won"


def test_the_feed_settles_nothing_it_has_not_said():
    """No winner named (a draw, a no contest, or a feed still filling in)
    settles nothing; a method leg waits for how it ended; a fight not yet
    started is "pre"; a stopped refresher's file is no state at all."""
    nobody = SL.Live({}, fast_dir=_feed([_bout_feed("post", None, None, 3, "5:00")]))
    st = nobody.state(dict(_leg("moneyline", "team", team=A), league="ufc"))
    assert st["state"] == "final" and "result" not in st and "settled by your book" in st["note"]
    how = SL.Live({}, fast_dir=_feed([_bout_feed("post", True, None, 2, "3:12")]))
    assert how.state(dict(_leg("moneyline", "team", team=A), league="ufc"))["result"] == "won"
    assert "result" not in how.state(dict(_leg("win_ko", "yes", team=A), league="ufc"))
    assert how.state(dict(_leg("win_ko", "yes", team=B), league="ufc"))["result"] == "lost", "the loser lost any way"
    pre = SL.Live({}, fast_dir=_feed([_bout_feed("pre")]))
    assert pre.state(dict(_leg("moneyline", "team", team=A), league="ufc")) == {"state": "pre", "home": A, "away": B}
    old = SL.Live({}, fast_dir=_feed([_bout_feed("post", True, "KO/TKO", 1, "1:00")], age=SL.FAST_FRESH_S + 60))
    assert old.state(dict(_leg("moneyline", "team", team=A), league="ufc")) is None


def test_a_saved_fight_slip_settles_off_the_feed():
    """The Live tab and the box's slip watch read a saved slip with no card
    behind it (the board moves on): the leg's own names find the bout."""
    live = SL.Live({}, fast_dir=_feed([_bout_feed("post", True, "KO/TKO", 2, "3:12")]))
    slip = SG.clean_slip({"legs": [_leg("moneyline", "team", team=A), _leg("fight_rounds", "over", 1.5)]})
    card = SG.grade(dict(slip, total_odds=200, stake=10), {}, live=live, brief=True)
    assert card["now"]["status"] == "won" and card["now"]["won"] == 2
    from engine import slipwatch as SW
    assert SW.settled({"result": "pending", "odds": 200}, card) == {"result": "win"}


def test_the_live_feed_keeps_how_a_bout_ended():
    from engine.ufc import live as UL
    done = UL._status_of({"status": {"period": 2, "displayClock": "3:12",
                                     "type": {"state": "post", "detail": "Final"},
                                     "result": {"name": "tko", "displayName": "KO/TKO"}}})
    assert done["method"] == "KO/TKO" and done["round"] == 2 and done["clock"] == "3:12"
    assert UL._status_of({"status": {"type": {"state": "post", "detail": "Final - Decision (Split)"}}})["method"] == "DEC"
    assert UL._status_of({"status": {"type": {"state": "in", "detail": "R1 KO threat"}}})["method"] is None


def test_the_checker_loads_the_card_beside_the_league_boards():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert src.count("boards = SG.with_fights(boards)") == 2, "the slip grader and the Live tab tracker"
    assert "SG.with_fights(boards)" in (ROOT / "engine" / "slipwatch.py").read_text(encoding="utf-8")
    assert SG.FIGHT_BOARD == "ufc.json"


def test_the_page_names_a_fight_leg():
    js = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
    assert 'fight: "Our UFC model"' in js and 'win_ko: "by KO/TKO"' in js
    for m in ("fight_distance", "fight_rounds", "fight_round"):
        assert f'l.market === "{m}"' in js, m
    assert SG._name(_leg("fight_rounds", "under", 2.5)) == f"{BOUT} under 2.5 rounds"
    assert SG._name(_leg("win_sub", "yes", team=A)) == f"{A} by submission"


def test_the_runbook_says_so():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "UFC fights in the parlay checker" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
