"""The off-board read sees who plays around him and how much he is used
(NFL): the build's lineup steps and the usage bridge, run on a leg no
board carries (engine/slipread.football, 2026-10-13).

Ethan, 2026-10-13: "add all of them", the fourth being the three inputs
the read priced without: a teammate at his position ruled out
(engine/teammates), his quarterback out or benched (engine/qbchange), his
measured volume role (engine/nflusage).

Every test runs on the read's synthetic two-season history with a second
back and a receiver added; nothing reads data/history.db or the network.

    python3 tests/test_the_off_board_read_sees_who_plays_around_him.py
"""

import importlib.util
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import askbot as AB                                   # noqa: E402
from engine import projection as PJ                               # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import slipread as SR                                 # noqa: E402

_spec = importlib.util.spec_from_file_location("_readtests", ROOT / "tests" / "test_an_off_board_leg_gets_our_read.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
SR._record = lambda league: {}


def _history():
    """The read's fixture plus a second Bills back behind RB BUF and a
    Bills receiver, both seasons. Named unlike the fixture's "RB BUF":
    the usage maps key a player on his initial, surname and team, and a
    second "R. Buf" would read as the first."""
    rng = random.Random(3)
    rows = []
    for season in (2025, 2026):
        weeks = range(1, 18) if season == 2025 else range(1, 6)
        for wk in weeks:
            p = f"{wk:03d}"
            c = rng.randint(5, 7)
            for m, v in (("carries", c), ("rush_att", c), ("rush_yds", round(c * 4.2, 1)), ("targets", 2),
                         ("receptions", 1), ("rec_yds", rng.randint(5, 20))):
                rows.append(T._row("nfl", season, p, "Zed Backup", "BUF", "MIA", "RB", m, v))
            for m, v in (("targets", rng.randint(6, 9)), ("receptions", rng.randint(4, 7)),
                         ("rec_yds", rng.randint(50, 90))):
                rows.append(T._row("nfl", season, p, "Wes Wideout", "BUF", "MIA", "WR", m, v))
    return T._nfl_db(extra=rows)


RB2 = {"sport": "nfl", "player": "Zed Backup", "team": "BUF", "market": "rush_yds", "side": "over", "line": 25.5,
       "odds": -110, "game": "MIA @ BUF", "text": ""}
WR = {"sport": "nfl", "player": "Wes Wideout", "team": "BUF", "market": "rec_yds", "side": "over", "line": 60.5,
      "odds": -110, "game": "MIA @ BUF", "text": ""}


def _who(player, pos):
    return {"player": player, "team": "BUF", "position": pos}


def test_his_measured_role_reaches_the_read():
    SR.clear_cache()
    _, conn = _history()
    role = SR._usage_role(conn, 2026, "RB BUF", "BUF", "rush_yds")
    assert role and role["opp_market"] == "carries" and role["opp_per_game"] > 10 and role["eff"] > 0, role
    assert SR._usage_role(conn, 2026, "RB BUF", "BUF", "rec_yds")["opp_market"] == "targets"
    assert SR._usage_role(conn, 2026, "Nobody", "BUF", "rush_yds") is None
    seen = {}
    real = PJ.build_projection

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    PJ.build_projection = spy
    try:
        row = SR.football(conn, T._nfl_board(), "nfl", dict(RB2, player="RB BUF"), _who("RB BUF", "RB"))
    finally:
        PJ.build_projection = real
    assert row and row["projection"] is not None
    assert seen.get("usage") == role, "the role the board would hand the projection"
    # As of a past week the role is read on the weeks before it.
    early = SR._usage_role(conn, 2026, "RB BUF", "BUF", "rush_yds", asof=(2026, "003"))
    assert early and early["n_weeks"] <= 2 and role["n_weeks"] >= early["n_weeks"]


def test_a_teammate_ruled_out_moves_the_read_and_the_card_says_so():
    SR.clear_cache()
    _, conn = _history()
    board = T._nfl_board()
    card = board["games"][0]
    lu = SR._lineup(conn, board, card, 2026, "BUF", "MIA")
    assert [o[0] for o in lu["BUF"]["order"]["RB"]] == ["RB BUF", "Zed Backup"], lu["BUF"]["order"]
    assert lu["BUF"]["last"] == 5 and lu["BUF"]["out"] == [] and lu["BUF"]["weeks"] == [1, 2, 3, 4, 5]
    without = SR.football(conn, board, "nfl", dict(RB2), _who("Zed Backup", "RB"))
    assert without["mate_card"] is None
    card["scan"] = {"injuries": [{"team": "BUF", "player": "RB BUF", "position": "RB", "status": "OUT"}]}
    assert SR._lineup(conn, board, card, 2026, "BUF", "MIA")["BUF"]["out"] == ["rb buf"]
    with_ = SR.football(conn, board, "nfl", dict(RB2), _who("Zed Backup", "RB"))
    mc = with_["mate_card"]
    assert mc and mc["case"] == "above_new" and "RB BUF" in mc["headline"] and mc["out"] == ["RB BUF"], mc
    assert with_["projection"] >= without["projection"]
    if mc["applied"] != 1.0:
        assert with_["projection"] > without["projection"], "a measured step that did not move the number"
    # Questionable: nothing applied, and the card says what happens if he sits.
    card["scan"] = {"injuries": [{"team": "BUF", "player": "RB BUF", "position": "RB", "status": "QUESTIONABLE"}]}
    maybe = SR.football(conn, board, "nfl", dict(RB2), _who("Zed Backup", "RB"))
    assert abs(maybe["projection"] - without["projection"]) < 1e-9
    assert maybe["mate_card"] and "questionable" in maybe["mate_card"]["headline"]
    # The books pulling his props counts as out; a board row's status too.
    card["scan"] = {"injuries": [], "pulled": ["RB BUF"]}
    assert SR._lineup(conn, board, card, 2026, "BUF", "MIA")["BUF"]["out"] == ["rb buf"]
    card["scan"] = {}
    board["recommendations"].append({"player": "RB BUF", "team": "BUF", "market": "rush_yds", "injury_status": "Doubtful"})
    assert SR._lineup(conn, board, card, 2026, "BUF", "MIA")["BUF"]["out"] == ["rb buf"]


def test_his_quarterback_out_moves_a_receivers_read():
    SR.clear_cache()
    _, conn = _history()
    board = T._nfl_board()
    card = board["games"][0]
    without = SR.football(conn, board, "nfl", dict(WR), _who("Wes Wideout", "WR"))
    assert without["qb_card"] is None
    pub = {"team": "BUF", "starter": "Josh Allen", "status": "OUT", "replacement": "Backup BUF", "tier": "downgrade",
           "headline": "Josh Allen (OUT) — Backup BUF starts", "applied": 0.897, "note": "x",
           "detail": "Backup BUF has thrown for 6.1 yards an attempt (120 attempts) against Josh Allen’s 7.9"}
    card["qb_cards"] = [pub]
    assert set(SR._qb_changes(card, "BUF", "MIA")) == {"BUF"}
    with_ = SR.football(conn, board, "nfl", dict(WR), _who("Wes Wideout", "WR"))
    qc = with_["qb_card"]
    assert qc and qc["tier"] == "downgrade" and qc["applied"] == 0.897 and "Backup BUF starts" in qc["headline"], qc
    assert qc["detail"] == pub["detail"], "the build's own sample, not a 'too few to rate' the read cannot know"
    assert abs(with_["projection"] / without["projection"] - 0.897) < 0.01, "the measured receivers' step"
    # A card on the other side of the game is not his.
    card["qb_cards"] = [dict(pub, team="MIA", starter="QB MIA")]
    other = SR.football(conn, board, "nfl", dict(WR), _who("Wes Wideout", "WR"))
    assert other["qb_card"] is None and abs(other["projection"] - without["projection"]) < 1e-9
    # A card with no tier or no starter is nothing to price.
    card["qb_cards"] = [dict(pub, tier=""), dict(pub, starter="")]
    assert SR._qb_changes(card, "BUF", "MIA") == {}


def test_a_replay_sees_the_order_and_the_role_as_of_its_week_and_no_report():
    SR.clear_cache()
    _, conn = _history()
    board = T._nfl_board()
    card = board["games"][0]
    card["scan"] = {"injuries": [{"team": "BUF", "player": "RB BUF", "position": "RB", "status": "OUT"}]}
    asof = SR._lineup(conn, board, card, 2026, "BUF", "MIA", asof=(2026, "003"))
    assert asof["BUF"]["last"] == 2 and asof["BUF"]["weeks"] == [1, 2] and asof["BUF"]["out"] == [], asof["BUF"]
    assert [o[0] for o in asof["BUF"]["order"]["RB"]] == ["RB BUF", "Zed Backup"]
    assert SR._nfl_week(conn, 2026) == 6 and SR._nfl_week(conn, 2026, asof=(2026, "003")) == 3
    from engine import slipreadfit as SRF
    rows = SRF.replay(conn, "nfl", [2026], markets=("rush_yds",))
    assert rows and all(0 < r["ours"] < 1 for r in rows)


def test_the_card_says_who_is_out_around_him():
    SR.clear_cache()
    path, conn = _history()
    board = T._nfl_board()
    board["games"][0]["scan"] = {"injuries": [{"team": "BUF", "player": "RB BUF", "position": "RB", "status": "OUT"}]}
    AB.HISTORY_DB = path
    try:
        card = SG.grade({"legs": [dict(RB2)], "total_odds": -110, "stake": 10, "book": "FanDuel"}, {"nfl": board})
    finally:
        AB.HISTORY_DB = None
    leg = card["legs"][0]
    assert leg["found"] == "read" and leg["prob"] is not None
    facts = {f["k"]: f["t"] for f in leg["why"]}
    assert "Around him" in facts and "RB BUF" in facts["Around him"], facts


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
