"""Tests for injured-list awareness from the MLB transactions wire."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.sources.mlbstats import parse_transactions
from engine.mlb.transactions import il_status, just_returned


def _tx(player, date, desc, team_id=143):
    return {"person": {"fullName": player}, "date": date,
            "toTeam": {"id": team_id}, "typeDesc": "Status Change",
            "description": desc}


def test_parse_transactions_normalizes_the_payload():
    rows = parse_transactions({"transactions": [
        _tx("Bryce Harper", "2026-07-20",
            "Philadelphia Phillies placed 1B Bryce Harper on the 10-day "
            "injured list. Right wrist inflammation."),
        {"person": {}, "date": "2026-07-20", "description": "no name"},
    ]})
    assert len(rows) == 1
    assert rows[0]["player"] == "Bryce Harper" and rows[0]["team"] == "PHI"


def test_latest_il_move_wins():
    """Placed then activated = healthy; placed only = on the IL. The
    60-day transfer keeps a player ON the list."""
    txs = [
        _tx("Hurt Guy", "2026-07-10", "placed RHP Hurt Guy on the 15-day injured list"),
        _tx("Back Guy", "2026-07-05", "placed OF Back Guy on the 10-day injured list"),
        _tx("Back Guy", "2026-07-25", "activated OF Back Guy from the 10-day injured list"),
        _tx("Long Guy", "2026-06-01", "placed SS Long Guy on the 10-day injured list"),
        _tx("Long Guy", "2026-06-20", "transferred SS Long Guy to the 60-day injured list"),
        _tx("Traded Guy", "2026-07-15", "traded RHP Traded Guy to Seattle"),
    ]
    st = il_status(parse_transactions({"transactions": txs}), "2026-07-27")
    assert st["hurt guy"]["on_il"] is True
    assert st["back guy"]["on_il"] is False
    assert st["long guy"]["on_il"] is True
    assert "traded guy" not in st          # not an IL transaction


def test_just_returned_window():
    entry = {"on_il": False, "date": "2026-07-25"}
    assert just_returned(entry, "2026-07-27") is True
    assert just_returned(entry, "2026-08-10") is False
    assert just_returned({"on_il": True, "date": "2026-07-25"}, "2026-07-27") is False
    assert just_returned(None, "2026-07-27") is False


def test_il_player_is_never_recommended_and_leaves_the_hr_board():
    """End to end on the sample slate: mark a slate hitter as on the IL —
    his props flip to not-recommended with the IL warning, he vanishes
    from the HR watchlist, and the slate reports him."""
    from engine.mlb.pipeline import run_mlb_slate
    il = {"bryce harper": {"on_il": True, "date": "2026-07-20",
                           "team": "PHI", "detail": "10-day IL"}}
    r = run_mlb_slate("data/mlb_sample_slate.json", il_map=il)
    harper = [x for x in r["recommendations"] if x["player"] == "Bryce Harper"]
    assert harper, "sample slate should carry Bryce Harper"
    for x in harper:
        assert x["recommended"] is False
        assert any("injured list" in w.lower() for w in x["warnings"])
    watch = {w["player"] for w in r["longshot_watch"]}
    picks = {p["player"] for p in r["long_shots"]}
    assert "Bryce Harper" not in watch | picks
    assert r["injured_list"] == ["Bryce Harper"]


def test_recent_activation_carries_a_form_caveat():
    from engine.mlb.pipeline import run_mlb_slate
    import json
    slate_date = json.load(open("data/mlb_sample_slate.json"))["date"]
    il = {"bryce harper": {"on_il": False, "date": slate_date,
                           "team": "PHI", "detail": "activated"}}
    r = run_mlb_slate("data/mlb_sample_slate.json", il_map=il)
    harper = [x for x in r["recommendations"] if x["player"] == "Bryce Harper"]
    assert any(any("Activated from the IL" in w for w in x["warnings"])
               for x in harper)
    assert r["injured_list"] == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
