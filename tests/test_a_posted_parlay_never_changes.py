"""A game's posted parlays never change once posted, in every league (step ABB, 21 November 2026).

Ethan, the evening of 21 November, on the 76ers at Bucks report: "the pics are different from earlier
that I put in ... You can't keep changing shit ... I put in a bet that is no longer being recorded or
shown in the game reports, and that's a huge issue because it's losing, and it's losing me money, but
then you're recording that we're winning money ... make sure it's not affecting CFB or nfl or any other
sport."

Since ZQ (20 November) a posted ticket was posted again only while it was still one the newest build
would make, and at the books' newest number: a pick leaving the report's card, a leg the newest read no
longer backed or a rule changed in the day replaced it. Now a game's tickets, once posted, are posted
again every build exactly as they were (legs, lines, prices, chances), until the game starts; a build
only fills a place the game never filled. What these hold:

  * the kept file gives each game's tickets whole (`posted_from`), and `report_only` puts them back as
    posted (`hold_posted`) for every league's report stage;
  * a line the books moved, picks that left the report and a game no report rebuilt this build change
    nothing posted; a gap is filled, never past MAX_USES of a leg;
  * the turnover the heartbeat sums reads every posted ticket kept and none replaced;
  * QB_PARLAY_LOCK=off goes back to ZQ's rule.

    python3 tests/test_a_posted_parlay_never_changes.py
"""
from __future__ import annotations

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
SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")


def _build(board=None, posted=None, picks=None, report=True):
    b = board or EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    if posted is not None:
        b[GP.POSTED_KEY] = posted
    if report:
        GP.from_report(b, "nfl", GAME, TP.PICKS if picks is None else picks)
    GP.report_only(b)
    return b, GP.for_game(b, "NYG", "WAS")


def _posted(x):
    """What the next build reads, through the kept file as engine/reportkeep writes it."""
    path = Path(tempfile.mkdtemp()) / "reportkeep_nfl.json"
    path.write_text(json.dumps({"games": {KEY: {"at": "2099-11-12T12:00:00", "report": {}, "parlays": x}}}),
                    encoding="utf-8")
    return GP.posted_from(path)


def _as_posted(ts):
    return [[(l["player"], l["market"], l["side"], l["line"], l.get("odds"), l.get("p")) for l in t["legs"]] for t in ts]


def test_the_kept_file_gives_each_ticket_whole():
    _b, x = _build()
    got = _posted(x)[KEY][GP.POSTED_TICKETS]
    for kind in GP.LOCK_KINDS:
        assert _as_posted(got[kind]) == _as_posted(x.get(kind) or []), kind
    assert GP.LOCK_PLACES == {"threes": 3, "twos": 3, "scorers": 3}


def test_a_moved_line_and_picks_that_left_the_report_change_nothing_posted():
    _b, x = _build()
    was = {k: _as_posted(x.get(k) or []) for k in GP.LOCK_KINDS}
    assert was["threes"] and was["twos"] and was["scorers"], was
    # The next build: the books moved two of the posted legs' numbers, and the report now backs none of
    # its old picks but one.
    board = EG.board()
    for r in board["most_likely"]:
        if r["player"] in ("Malik Nabers", "Isaiah Likely"):
            r["line"] = float(r["line"]) + 1.0
            r["odds"] = -110
            r["model_prob"] = 0.58
    _b2, y = _build(board, posted=_posted(x), picks=TP.PICKS[:1])
    assert {k: _as_posted(y.get(k) or []) for k in GP.LOCK_KINDS} == was, "posted exactly as it was"
    assert (y["posted_kept"], y["posted_replaced"]) == (sum(len(v) for v in was.values()), 0)


def test_a_game_no_report_rebuilt_this_build_keeps_what_it_posted():
    _b, x = _build()
    was = _as_posted(x["threes"])
    _b2, y = _build(posted=_posted(x), report=False)
    assert _as_posted(y["threes"]) == was and y.get("threes_note") is None, y.get("threes_note")


def test_a_gap_is_filled_but_never_past_a_legs_uses():
    _b, x = _build()
    one = copy.deepcopy(x)
    one["threes"] = one["threes"][:1]                    # the game posted one three-leg ticket
    _b2, y = _build(posted=_posted(one))
    assert _as_posted(y["threes"][:1]) == _as_posted(one["threes"]), "the posted ticket first, as posted"
    uses: dict = {}
    for t in y["threes"]:
        for l in t["legs"]:
            k = (l["player"], l["market"], l["side"])
            uses[k] = uses.get(k, 0) + 1
    assert max(uses.values()) <= GP.MAX_USES, uses
    a = {"legs": [{"player": "A", "market": "m", "side": "OVER"}, {"player": "B", "market": "m", "side": "OVER"}]}
    b = {"legs": [{"player": "A", "market": "m", "side": "OVER"}, {"player": "C", "market": "m", "side": "OVER"}]}
    c = {"legs": [{"player": "A", "market": "m", "side": "OVER"}, {"player": "D", "market": "m", "side": "OVER"}]}
    assert GP._fits_beside([a], b) and not GP._fits_beside([a, b], c), "a leg rides two tickets at most"
    assert not GP._fits_beside([a], copy.deepcopy(a)), "the same two legs again is no new ticket"


def test_the_switch_goes_back_to_the_rule_before():
    _b, x = _build()
    board = EG.board()
    board["most_likely"] = [r for r in board["most_likely"] if r["player"] != "Malik Nabers"]
    os.environ["QB_PARLAY_LOCK"] = "off"
    try:
        _b2, y = _build(board, posted=_posted(x))
        assert not any(l["player"] == "Malik Nabers" for t in y["threes"] for l in t["legs"]), \
            "off: a ticket on a player off the board is replaced, as ZQ did"
    finally:
        os.environ.pop("QB_PARLAY_LOCK", None)
    _b3, z = _build(board, posted=_posted(x))
    assert _as_posted(z["threes"]) == _as_posted(x["threes"]), "on: it stays, as posted"


def test_the_record_says_every_parlay_posted_apart_from_the_set_it_counts():
    import sqlite3
    from engine import parlayledger as PL
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    for k, (start, status, pnl) in enumerate(((1, "lost", -1.0), (0, "won", 2.4), (0, "won", 2.1))):
        cur = c.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status, at_start,"
                        " pnl_units, modeled_joint) VALUES ('nba', '2026-11-21', ?, 'same_game', 2, 'PHI@MIL', 'game_two',"
                        " ?, ?, ?, 0.5)", (f"k{k}", status, start, pnl))
        for j in (1, 2):
            c.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, p_final, status)"
                      " VALUES (?, ?, ?, 'ast', 'OVER', 1.5, 0.7, ?)", (cur.lastrowid, j, f"P{k}{j}", status))
    c.commit()
    two = PL.game_parlay_record(c)["nba"]["two"]
    assert (two["graded"], two["wins"], two["not_counted"]) == (1, 0, 2)
    assert two["every"] == {"graded": 3, "wins": 2, "chance": 0.5, "net_units": 3.5}, two["every"]
    rec = __import__("test_the_record_grades_best_parlays_by_tier")
    got = rec._node("""return gpBlockHTML({ graded: 1, wins: 0, legs: {}, every: { graded: 3, wins: 2, chance: 0.5, net_units: 3.5 } },
                                   "two", "nba");""")
    if got is None:
        return
    words = " ".join(got.split())
    assert "Every one we posted, the ones replaced before their game too: 2 of 3 hit (we gave 50%) · 3.5" in words, words
    assert "since then a posted parlay stays as it was posted" in words


def test_every_leagues_report_stage_runs_it_and_the_words_are_there():
    body = SRC[SRC.index("def report_only("):SRC.index("def ", SRC.index("def report_only(") + 10)]
    assert body.index("if hold_posted(x, mine):") < body.index("x[\"posted_kept\"], x[\"posted_replaced\"] = _turnover(x, mine)")
    for name in ("gamereport.py", "leaguereport.py"):
        src = (ROOT / "engine" / name).read_text(encoding="utf-8")
        assert "_posted_before(result, sport, out)" in src and "_report_only(result)" in src, name
    for words in ("You can't keep\n#: changing shit", "Off without a deploy: ``sudo ./deploy/setenv.sh QB_PARLAY_LOCK off``"):
        assert words in SRC, words


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
