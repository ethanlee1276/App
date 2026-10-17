"""The parlay checker's college read sees who plays around him, as the
college board's own number does.

Ethan, 2026-10-14, "do 1-11", to the call "College in the off-board read's
lineup and usage steps (step 43)": yes.

A college leg no board carries now runs the two steps the college board
runs before it prices a prop (engine/cfb/lineup.attach): college's own
depth order, ranked on catches (plus carries for a back) over the team's
games before tonight, with the board's injury lists and the books' pulled
list on it; and the QB-change card the college board published. Both are
priced by college's own measurement (engine/cfb/lineup's store, x1.00 until
college's fit adopts a case) and never by the NFL's table. The college
board hands its projection no usage role, so a college read takes none
either.

Found on the way and fixed for the board too: the college build keyed its
out list with bare normalize_name, so a ruled-out "D.J." went on it as
"d j" while the step looked for "dj", and his teammates never moved.

Every test runs on a throwaway history database and model store; nothing
reads data/history.db, the box's models or the network.

    python3 tests/test_the_college_read_sees_who_plays_around_him.py
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import askbot as AB                                   # noqa: E402
from engine import db as DB                                       # noqa: E402
from engine import projection as PJ                               # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import slipread as SR                                 # noqa: E402
from engine.cfb import lineup as L                                # noqa: E402

SR._record = lambda league: {}

DAYS = {2024: ["2024-09-07", "2024-09-14", "2024-09-21", "2024-09-28", "2024-10-05", "2024-10-12"],
        2025: ["2025-09-06", "2025-09-13", "2025-09-20", "2025-09-27", "2025-10-04", "2025-10-11"]}
TONIGHT = "2025-10-18"


def _rows(season, team, opp):
    """One team's season: D.J. Wideout the top receiver (6 catches), WR2
    (about 4), WR3 (2), a back (15 carries), QB1 throwing 30 a game."""
    out = []
    for i, d in enumerate(DAYS[season]):
        def log(player, pos, market, value):
            out.append({"sport": "cfb", "season": season, "period": d, "game_id": f"{team}-{d}",
                        "player": player, "team": team, "opponent": opp, "position": pos, "home": 1,
                        "market": market, "value": float(value)})
        wide = "D.J. Wideout" if team == "UGA" else f"{team} WR1"
        log(f"{team} QB1", "QB", "pass_att", 30)
        log(f"{team} QB1", "QB", "pass_yds", 240)
        log(f"{team} QB2", "QB", "pass_att", 2)
        log(f"{team} QB2", "QB", "pass_yds", 10)
        log(wide, "WR", "receptions", 6)
        log(wide, "WR", "rec_yds", 80)
        c = 4 + (i % 3) - 1
        log(f"{team} WR2", "WR", "receptions", c)
        log(f"{team} WR2", "WR", "rec_yds", c * 12)
        log(f"{team} WR3", "WR", "receptions", 2)
        log(f"{team} WR3", "WR", "rec_yds", 25)
        log(f"{team} RB1", "RB", "rush_att", 15)
        log(f"{team} RB1", "RB", "rush_yds", 70)
        log(f"{team} RB1", "RB", "receptions", 1)
    return out


def _history():
    path = str(_SANDBOX / f"cfb_{len(os.listdir(_SANDBOX))}.db")
    conn = DB.connect(path)
    rows = []
    for season in (2024, 2025):
        rows += _rows(season, "UGA", "OPP") + _rows(season, "VAN", "OPP")
    DB.upsert_player_logs(conn, rows)
    conn.commit()
    return path, conn


def _board():
    card = {"home": "UGA", "away": "VAN", "date": TONIGHT, "kickoff": f"{TONIGHT}T19:30:00Z",
            "spread": -14.5, "total": 52.5, "weather": {"dome": False, "temp_f": 60, "wind_mph": 5}}
    return {"date": TONIGHT, "games": [card], "recommendations": []}


WR2 = {"sport": "cfb", "player": "UGA WR2", "team": "UGA", "market": "receptions", "side": "over", "line": 3.5,
       "odds": -110, "game": "VAN @ UGA", "text": ""}
WHO = {"player": "UGA WR2", "team": "UGA", "position": "WR"}
WR1_OUT = {"injuries": [{"team": "UGA", "player": "DJ Wideout", "position": "WR", "status": "OUT"}]}
QB_CARD = {"team": "UGA", "starter": "UGA QB1", "status": "OUT", "replacement": "UGA QB2", "tier": "downgrade",
           "headline": "UGA QB1 (OUT) — UGA QB2 starts", "applied": 1.0, "note": "x",
           "detail": "UGA QB2 has thrown for 5.0 yards an attempt (12 attempts) against UGA QB1’s 8.0"}


def _measured(mates=None, qb=None):
    L.save({"seasons": [2022, 2023, 2024, 2025], "adopt_mates": mates or {}, "adopt_qb": qb or {}})


def _unmeasured():
    p = L._store()
    if p.exists():
        p.unlink()
    L._CACHE.clear()


def _read(conn, board):
    return SR.football(conn, board, "cfb", dict(WR2), dict(WHO))


def _lineup_step(row):
    """The projection's own Lineup step, as the pick page draws it."""
    return next(s["mult"] for s in row["chain"]["steps"] if s["key"] == "lineup")


def test_colleges_own_order_with_the_boards_lists_on_it():
    SR.clear_cache()
    _, conn = _history()
    board = _board()
    card = board["games"][0]
    lu = SR._cfb_lineup(conn, board, card, 2025, "UGA", "VAN")
    assert lu["UGA"]["basis"] == "cfb" and lu["UGA"]["last"] == 6, lu["UGA"]
    assert [o[0] for o in lu["UGA"]["order"]["WR"]] == ["D.J. Wideout", "UGA WR2", "UGA WR3"], "ranked on catches"
    assert lu["UGA"]["out"] == [] and lu["VAN"]["order"]["RB"][0][0] == "VAN RB1"
    card["scan"] = dict(WR1_OUT)
    assert SR._cfb_lineup(conn, board, card, 2025, "UGA", "VAN")["UGA"]["out"] == ["dj wideout"], \
        "ESPN's 'DJ' and the logs' 'D.J.' are the same man, under the key the step reads"
    card["scan"] = {"injuries": [{"team": "UGA", "player": "D.J. Wideout", "status": "QUESTIONABLE"}]}
    assert SR._cfb_lineup(conn, board, card, 2025, "UGA", "VAN")["UGA"]["maybe"] == ["dj wideout"]
    # Every book took his props down: the college build reads the game's own list.
    card["scan"] = {}
    card["pulled_players"] = ["D.J. Wideout"]
    assert SR._cfb_lineup(conn, board, card, 2025, "UGA", "VAN")["UGA"]["out"] == ["dj wideout"]


def test_unmeasured_nothing_moves_and_the_card_says_college_was_not_measured():
    _unmeasured()
    SR.clear_cache()
    _, conn = _history()
    board = _board()
    without = _read(conn, board)
    assert without and without["mate_card"] is None
    board["games"][0]["scan"] = dict(WR1_OUT)
    with_ = _read(conn, board)
    mc = with_["mate_card"]
    assert mc and mc["case"] == "above_new" and mc["out"] == ["D.J. Wideout"] and mc["applied"] == 1.0, mc
    assert "College has not been measured" in mc["note"], mc["note"]
    assert _lineup_step(with_) == 1.0 and with_["projection"] == without["projection"]


def test_measured_colleges_own_step_moves_the_read_never_the_nfls():
    _measured(mates={("receptions", "WR", "above_new"): 1.3})
    try:
        SR.clear_cache()
        _, conn = _history()
        board = _board()
        without = _read(conn, board)
        board["games"][0]["scan"] = dict(WR1_OUT)
        with_ = _read(conn, board)
        mc = with_["mate_card"]
        assert mc and mc["applied"] == 1.3 and "college" in mc["note"], mc
        assert _lineup_step(with_) == 1.3 and with_["projection"] > without["projection"], with_["chain"]
        # College adopted only receiving yards here: his catches read x1.00,
        # and never a number the NFL measured for the same spot.
        _measured(mates={("rec_yds", "WR", "above_new"): 1.3})
        SR.clear_cache()
        flat = _read(conn, board)
        assert _lineup_step(flat) == 1.0 and flat["projection"] == without["projection"]
    finally:
        _unmeasured()


def test_the_college_qb_card_is_priced_by_colleges_measurement():
    _measured(qb={("receptions", "WR", "downgrade"): 0.9})
    try:
        SR.clear_cache()
        _, conn = _history()
        board = _board()
        card = board["games"][0]
        without = _read(conn, board)
        assert without["qb_card"] is None
        card["qb_cards"] = [dict(QB_CARD)]
        ch = SR._qb_changes(card, "UGA", "VAN", "cfb")["UGA"]
        assert ch["league"] == "cfb" and ch["tier"] == "downgrade"
        assert "league" not in SR._qb_changes(card, "UGA", "VAN")["UGA"], "the NFL's reading is unchanged"
        with_ = _read(conn, board)
        qc = with_["qb_card"]
        assert qc and qc["applied"] == 0.9 and "college" in qc["note"], qc
        assert qc["detail"] == QB_CARD["detail"], "the build's own sample, as the NFL's read keeps it"
        assert _lineup_step(with_) == 0.9 and with_["projection"] < without["projection"]
        # A replacement nobody could rate prices nothing.
        card["qb_cards"] = [dict(QB_CARD, tier="unmeasured")]
        assert SR._qb_changes(card, "UGA", "VAN", "cfb")["UGA"]["tier"] is None
        flat = _read(conn, board)
        assert flat["qb_card"]["applied"] == 1.0 and _lineup_step(flat) == 1.0
        # The other side's quarterback is not his.
        card["qb_cards"] = [dict(QB_CARD, team="VAN", starter="VAN QB1", replacement="VAN QB2")]
        other = _read(conn, board)
        assert other["qb_card"] is None and _lineup_step(other) == 1.0
    finally:
        _unmeasured()


def test_a_replay_sees_the_order_as_of_its_date_and_no_report():
    SR.clear_cache()
    _, conn = _history()
    board = _board()
    card = board["games"][0]
    card["scan"] = dict(WR1_OUT)
    lu = SR._cfb_lineup(conn, board, card, 2025, "UGA", "VAN", asof=(2025, "2025-09-27"))
    assert lu["UGA"]["last"] == 3 and lu["UGA"]["out"] == [], lu["UGA"]
    assert [o[0] for o in lu["UGA"]["order"]["WR"]][0] == "D.J. Wideout"


def test_a_college_read_hands_the_projection_no_usage_role():
    SR.clear_cache()
    _, conn = _history()
    seen = {}
    real = PJ.build_projection

    def spy(*a, **k):
        seen["game"] = a[1]
        seen.update(k)
        return real(*a, **k)
    PJ.build_projection = spy
    try:
        row = _read(conn, _board())
    finally:
        PJ.build_projection = real
    assert row and row["projection"] is not None
    assert seen.get("usage") is None, "the college board's projection takes none"
    assert seen["game"].lineup["UGA"]["basis"] == "cfb", "college's own order reached the projection"


def test_the_college_build_keys_a_dotted_name_as_the_step_does():
    """The fix for the board itself: engine/cfb/lineup.attach marks the
    ruled-out "D.J." under the key engine/teammates reads, so the measured
    step finds him out and moves the receivers ranked below him."""
    from engine import teammates as T
    _, conn = _history()
    game = NS(home="UGA", away="VAN")
    slate = NS(games=[game], props=[])
    for spelled in ("D.J. Wideout", "DJ Wideout"):
        L.attach(conn, slate, [{"home": "UGA", "away": "VAN"}], [NS(team="UGA", player=spelled, status="OUT")],
                 2025, TONIGHT)
        assert game.lineup["UGA"]["out"] == ["dj wideout"], (spelled, game.lineup["UGA"]["out"])
        _m, _why, card = T.effect(NS(market="receptions", team="UGA", player="UGA WR2", position="WR"), game)
        assert card and card["case"] == "above_new" and card["out"] == ["D.J. Wideout"], (spelled, card)


def test_the_grader_says_who_is_out_around_him():
    SR.clear_cache()
    path, _conn = _history()
    board = _board()
    board["games"][0]["scan"] = dict(WR1_OUT)
    AB.HISTORY_DB = path
    try:
        card = SG.grade({"legs": [dict(WR2)], "total_odds": -110, "stake": 10, "book": "FanDuel"}, {"cfb": board})
    finally:
        AB.HISTORY_DB = None
    leg = card["legs"][0]
    assert leg["found"] == "read" and leg["prob"] is not None, leg.get("found")
    facts = {f["k"]: f["t"] for f in leg["why"]}
    assert "Around him" in facts and "D.J. Wideout" in facts["Around him"], facts


def test_the_runbook_says_so():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "The parlay checker's college read sees who plays around him" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
