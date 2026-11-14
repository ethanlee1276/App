"""The game cards ask the loss miner's closures too (2026-11-14).

`engine.losspatterns` mines every settled bet with a stated chance, game
bets included, and `losspatterns.veto` enforces what it closes, with the
stopped shelves (`engine.shelfstop`) and the hypothesis lab's closures
behind it. Every prop board asks it, and so do college football's game
plays; the NFL's and MLB's game cards never did, so a convicted pocket of
spreads, totals or moneylines, or a whole stopped shelf, kept posting and
staking. The learning audit's second pass (LEARN2).

    python3 tests/test_game_bets_ask_the_loss_veto.py
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamebets as GB                      # noqa: E402
from engine import hypotheses as HY                    # noqa: E402
from engine import losspatterns as LP                  # noqa: E402
from engine import shelfstop as SS                     # noqa: E402

TMP = Path(tempfile.mkdtemp())
LP.DEFAULT_PATH = TMP / "losspatterns.json"
SS.DEFAULT_PATH = TMP / "shelfstop.json"
HY.DEFAULT_PATH = TMP / "hypotheses.json"


def _stores(closed=(), stopped=()):
    LP.DEFAULT_PATH.write_text(json.dumps({"closed": list(closed)}))
    SS.DEFAULT_PATH.write_text(json.dumps({"stopped": list(stopped)}))
    HY.DEFAULT_PATH.write_text(json.dumps({"hypotheses": []}))
    LP._cache.clear()
    SS._cache.clear()
    HY._cache.clear()


def _card(bet_type="spread", odds=-160, side="", **kw):
    d = {"bet_type": bet_type, "market": bet_type, "odds": odds, "win_prob": 0.6, "side": side,
         "team": "KC", "book": "DraftKings", "date": "2026-11-16", "kickoff": "2026-11-16T18:00:00Z",
         "recommended": True, "grade": "B", "stake_units": 0.5, "rest_days": 7, "body_clock": None}
    d.update(kw)
    return d


TODAY = dt.date(2026, 11, 14)
HEAVY = LP.odds_band(-160)


def test_a_game_card_in_a_closed_slice_is_shown_and_not_posted():
    _stores(closed=[{"sport": "nfl", "market": "spread", "dim": "odds", "value": HEAVY,
                     "reading": "ran 9 points under its claim"}])
    why = GB.loss_veto("nfl", _card(), today=TODAY)
    assert why and "blind spot" in why and HEAVY in why, why
    d = GB.apply_loss_veto("nfl", _card())
    assert d["recommended"] is False and d["grade"] == "Pass" and d["stake_units"] == 0.0
    assert d["loss_veto"] in d["warnings"]


def test_the_same_card_outside_the_slice_or_in_another_market_is_untouched():
    _stores(closed=[{"sport": "nfl", "market": "spread", "dim": "odds", "value": HEAVY}])
    assert GB.loss_veto("nfl", _card(odds=-110), today=TODAY) is None
    assert GB.loss_veto("nfl", _card(bet_type="total", side="Over"), today=TODAY) is None
    assert GB.loss_veto("mlb", _card(), today=TODAY) is None
    d = GB.apply_loss_veto("nfl", _card(odds=-110))
    assert d["recommended"] is True and d["grade"] == "B" and "loss_veto" not in d


def test_the_journals_side_is_the_one_asked():
    """A moneyline and a spread are journaled as an OVER on the team taken,
    a total as its own side (ledger.log_recommendations)."""
    _stores(closed=[{"sport": "nfl", "market": "total", "dim": "side", "value": "UNDER"}])
    assert GB.loss_veto("nfl", _card(bet_type="total", side="Under"), today=TODAY)
    assert GB.loss_veto("nfl", _card(bet_type="total", side="Over"), today=TODAY) is None
    _stores(closed=[{"sport": "nfl", "market": "moneyline", "dim": "side", "value": "OVER"}])
    assert GB.loss_veto("nfl", _card(bet_type="moneyline", side=""), today=TODAY)


def test_a_stopped_shelf_stops_its_game_cards():
    _stores(stopped=[{"sport": "nfl", "market": "moneyline", "roi": -0.081, "n": 240, "z": -2.4}])
    why = GB.loss_veto("nfl", _card(bet_type="moneyline"), today=TODAY)
    assert why and "This shelf is stopped: nfl moneyline" in why, why


def test_no_store_is_no_veto_and_a_broken_card_never_raises():
    for p in (LP.DEFAULT_PATH, SS.DEFAULT_PATH, HY.DEFAULT_PATH):
        p.unlink(missing_ok=True)
    LP._cache.clear()
    SS._cache.clear()
    HY._cache.clear()
    assert GB.loss_veto("nfl", _card(), today=TODAY) is None
    assert GB.loss_veto("nfl", {"bet_type": "spread", "odds": "x", "date": None}) is None
    assert GB.loss_veto("nfl", {"bet_type": "first_td"}) is None


def test_both_game_finishers_ask_it_last():
    for path, sport in ((ROOT / "engine" / "pipeline.py", "nfl"), (ROOT / "engine" / "mlb" / "pipeline.py", "mlb")):
        src = path.read_text(encoding="utf-8")
        lines = src[src.index("def _finish_bet("):].splitlines()
        body = [lines[0]]
        for ln in lines[1:]:
            if ln and not ln[0].isspace():
                break                                       # the function has ended
            body.append(ln)
        tail = next(ln.strip() for ln in reversed(body) if ln.strip())
        assert tail == f'return _apply_loss_veto("{sport}", d, g)', (path, tail)


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
