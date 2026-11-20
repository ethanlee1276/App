"""A game's posted parlays stay posted until a leg breaks (ZQ, 2026-11-20).

Ethan, on How our reports did rows reading "Parlays 0 of 28" and "1 of 42":
"why do we have 30 parlays being made per game?? There should only be 3
parlays made per game".

Each build chose a game's tickets afresh, so a line moving a point reordered
them and the board posted another set: one NFL game posted 19 versions of its
three-leg tickets between Thursday and Sunday. What these hold:

  * `gameparlays.choose` with ``keep`` posts last build's tickets again, in
    their order, while each is still one this build would make: ahead of a
    likelier new one, at a line the books moved (a ticket is its legs' player,
    market and side), never once a leg is gone; a one-club ticket stays while
    it is still the likelier read; never fewer tickets than a fresh choice;
  * the report stage reads what each game posted from engine/reportkeep's file
    (`posted_from`) before any report is written; `from_report` posts the
    game's three-leg tickets with them first and `report_only` its
    scorer pairs, counting what it posted again and what it replaced
    (``posted_kept``, ``posted_replaced``), which the heartbeat sums;
  * it is all the build's working state (underscore keys), which
    engine/gate.publish never writes.

    python3 tests/test_a_games_posted_parlays_stay_until_a_leg_breaks.py
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
TP = __import__("test_the_parlays_are_made_of_the_reports_picks")
GAME = EG.GAME
KEY = f"{GAME['away']}@{GAME['home']}|{GAME['date']}"


def _legs():
    return [l for l in GP.legs_for(EG.board(), "nfl")]


def _ids(ts):
    return [GP.ident(t) for t in ts]


def _with(legs, player, **kw):
    out = copy.deepcopy(legs)
    for l in out:
        if l["player"] == player and l["market"] != "pass_cmp":
            l.update(kw)
    return out


def test_a_posted_ticket_stays_ahead_of_a_likelier_new_one():
    legs = _legs()
    first = GP.tickets_of("nfl", GAME, legs)["threes"]
    assert len(first) == GP.THREE_PER_GAME, first
    # Rachaad White's number climbs: a fresh choice would post another set.
    moved = _with(legs, "Rachaad White", p=0.80)
    fresh = GP.tickets_of("nfl", GAME, moved)["threes"]
    assert _ids(fresh) != _ids(first), "the board as it was: a point's move reorders the tickets"
    kept = GP.tickets_of("nfl", GAME, moved, posted={"threes": _ids(first)})["threes"]
    assert _ids(kept) == _ids(first), "the posted tickets, in their order, while each still holds"


def test_a_line_the_books_move_is_the_same_ticket_at_the_new_number():
    legs = _legs()
    first = GP.tickets_of("nfl", GAME, legs)["threes"]
    moved = _with(legs, "Malik Nabers", line=5.5, p=0.69, odds=-205)
    kept = GP.tickets_of("nfl", GAME, moved, posted={"threes": _ids(first)})["threes"]
    assert _ids(kept) == _ids(first)
    nabers = [l for t in kept for l in t["legs"] if l["player"] == "Malik Nabers"]
    assert nabers and all(l["line"] == 5.5 and l["odds"] == -205 for l in nabers), "the books' current number"


def test_a_leg_that_breaks_frees_only_its_own_place():
    legs = _legs()
    first = GP.tickets_of("nfl", GAME, legs)["threes"]
    gone = next(l["player"] for l in first[-1]["legs"] if all(l["player"] not in [m["player"] for m in t["legs"]]
                                                                  for t in first[:-1]))
    # Ruled out, taken down, or past the price cap: the leg is no longer a leg.
    left = [l for l in legs if l["player"] != gone]
    kept = GP.tickets_of("nfl", GAME, left, posted={"threes": _ids(first)})["threes"]
    assert _ids(kept)[:2] == _ids(first)[:2], "the tickets it is not on stay, in their places"
    assert all(gone not in [l["player"] for l in t["legs"]] for t in kept), "and its ticket gives way"
    assert len(kept) == len(first)


def _t(joint, *legs, need=0):
    return {"legs": [{"player": p, "team": team, "market": "receptions", "side": "OVER", "line": 2.5}
                     for p, team in legs], "joint": joint, "need_margin": need, "need_points": 0}


def test_never_fewer_tickets_than_a_fresh_choice():
    ab, cd, ac = _t(0.50, ("A", "X"), ("B", "Y")), _t(0.45, ("C", "Y"), ("D", "X")), _t(0.48, ("A", "X"), ("C", "Y"))
    assert GP.choose([ab, cd, ac], 2, shared=(0,)) == [ab, cd]
    # Keeping A with C would leave room for no second two-leg ticket: the fresh pair stands.
    assert GP.choose([ab, cd, ac], 2, shared=(0,), keep=[GP.ident(ac)]) == [ab, cd]
    assert GP.choose([ab, cd, ac], 1, shared=(0,), keep=[GP.ident(ac)]) == [ac], "one place: the posted one"


def test_a_one_club_ticket_stays_while_it_is_still_the_likelier_read():
    one, both = _t(0.40, ("A", "X"), ("B", "X")), _t(0.38, ("C", "X"), ("D", "Y"))
    edge = GP.side_bar()[0]
    assert 0.40 - 0.38 < edge, "not clearly the likelier: a fresh choice takes both sides"
    assert GP.choose([one, both], 1) == [both]
    kept = GP.choose([one, both], 1, keep=[GP.ident(one)])
    assert _ids(kept) == [GP.ident(one)], "posted, and still the likelier read"
    assert kept[0]["one_club"] and "2 points likelier than the best ticket with both sides" in kept[0]["caveats"][-1]
    behind = dict(one, joint=0.37)
    assert GP.choose([behind, both], 1, keep=[GP.ident(behind)]) == [both], "behind now: the data no longer says so"


def _board_with(posted=None):
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    if posted is not None:
        b[GP.POSTED_KEY] = posted
    GP.from_report(b, "nfl", GAME, TP.PICKS)
    GP.report_only(b)
    return b, GP.for_game(b, "NYG", "WAS")


def test_the_report_stage_posts_them_again_and_counts_what_it_kept():
    b, x = _board_with()
    assert "posted_kept" not in x, "nothing posted before: nothing to count"
    assert GP.SCORER_PAIRS_KEY not in b and GP.POSTED_KEY not in b, "working state, gone once used"
    was = {k: _ids(x.get(k) or []) for k in GP.POSTED_LISTS}
    # A football game posts no two-leg tickets (basketball's, ZT): its list is empty, never missing.
    assert set(was) == {"threes", "twos", "scorers"} and was["threes"] and was["scorers"] and was["twos"] == [], was
    b2, y = _board_with({KEY: copy.deepcopy(was)})
    assert {k: _ids(y.get(k) or []) for k in GP.POSTED_LISTS} == was
    n = sum(len(v) for v in was.values())
    assert (y["posted_kept"], y["posted_replaced"]) == (n, 0), (y.get("posted_kept"), y.get("posted_replaced"))
    # The scorer pairs, chosen again with the posted ones first: a reversed order holds.
    rev = dict(copy.deepcopy(was), scorers=list(reversed(was["scorers"])))
    _b3, z = _board_with({KEY: rev})
    assert _ids(z["scorers"]) == rev["scorers"], _ids(z["scorers"])
    assert b2["game_parlays"]["counts"]["scorers"] == len(z["scorers"])
    # A posted ticket on a player no longer on the board is counted as replaced.
    gone = {KEY: dict(copy.deepcopy(was), threes=[(("Nobody", "receptions", "OVER"), ("Else", "rush_yds", "OVER"),
                                                   ("Third", "rec_yds", "OVER"))])}
    _b4, w = _board_with(gone)
    assert w["posted_replaced"] == 1 and w["posted_kept"] == n - len(was["threes"]), (w["posted_kept"], n)


def test_what_was_posted_is_read_from_the_kept_file():
    _b, x = _board_with()
    path = Path(tempfile.mkdtemp()) / "reportkeep_nfl.json"
    path.write_text(json.dumps({"games": {KEY: {"at": "2099-11-12T12:00:00", "report": {}, "parlays": x},
                                          "MIA@BUF|2099-11-12": {"report": {}}}}), encoding="utf-8")
    got = GP.posted_from(path)
    assert set(got) == {KEY}, "a game kept without parlays posted none"
    assert got[KEY] == {k: _ids(x.get(k) or []) for k in GP.POSTED_LISTS}
    assert GP.posted_from(path.with_name("none.json")) == {}
    assert GP.posted_for({GP.POSTED_KEY: got}, GAME) == got[KEY] and GP.posted_for({}, GAME) == {}


def test_the_report_stage_reads_them_before_any_report_and_publish_never_writes_them():
    for name, start in (("gamereport.py", "        reports = []\n        for g, extra, met in prepared:"),
                        ("leaguereport.py", "        reports = []\n        for g, m, _more in prepared:")):
        src = (ROOT / "engine" / name).read_text(encoding="utf-8")
        at = src.index(start)
        assert src.rindex("_posted_before(result, sport, out)", 0, at) > src.rindex("log_changes(", 0, at), name
        assert at < src.index("_report_only(result)", at) < src.index("keep_started(result, reports, sport, out", at)
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    body = gr[gr.index("def _posted_before("):gr.index("def _report_only(")]
    assert "gameparlays.posted_from(reportkeep.path_for(sport, _full_dir_for(out)))" in body
    assert GP.POSTED_KEY.startswith("_") and GP.SCORER_PAIRS_KEY.startswith("_")
    gate = (ROOT / "engine" / "gate.py").read_text(encoding="utf-8")
    assert 'payload = {k: v for k, v in payload.items() if not str(k).startswith("_")}' in gate


def test_the_heartbeat_sums_what_the_games_posted_again():
    import launch as L
    games = [{"home": "A", "threes": [], "posted_kept": 7, "posted_replaced": 1},
             {"home": "B", "threes": [], "posted_kept": 3, "posted_replaced": 0},
             # A started game's kept entry is the record's now: not counted.
             {"home": "C", "threes": [], "kept": "Sun 1:00 PM ET", "posted_kept": 9, "posted_replaced": 9},
             {"home": "D", "threes": []}]
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": games, "counts": {"games": 4, "threes": 0}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
            for g in games:
                g.pop("posted_kept", None)
            with open(path, "w") as fh:
                json.dump(board, fh)
            none = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["posted"] == {"kept": 10, "replaced": 1}, got.get("posted")
    assert "posted" not in none, "a league with nothing posted before says nothing"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
