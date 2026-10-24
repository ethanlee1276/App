"""Every fit and every invention lands where the map says — checked against the code.

Ethan, 2026-10-17: "make sure all of our tools and data are being used
correctly and not just the ones you just added but ALL tools and data we
were and are using."

What these hold: the map (engine/wiremap) has no problem today; a new fitter
without a row is caught, a row that names a reader which never names it is
caught, and a failed fit the number path imports is caught; the gated rows
are exactly engine/ideagate's gates and the never-a-number inventions are
cards; the runner script for an engine fit counts as that fit; the lanes put
the projection on the number path; and the report says the gates and the
findings. No test touches the network.

Run directly: `python3 tests/test_every_fit_lands_where_it_says.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ideagate as G                                 # noqa: E402
from engine import wiremap as W                                  # noqa: E402


def test_the_map_and_the_code_agree_today():
    assert W.problems() == []
    assert {r[1] for r in W.FITS} <= set(W.LANDS)
    assert len({r[0] for r in W.FITS}) == len(W.FITS), "one row per fit"


def test_a_new_fit_without_a_row_is_caught():
    files = {"engine.newthingfit": "x", "newthingfit": "y", "engine.wxfit": "z", "wxfit": "w",
             "cfbdefensefit": "v", "engine.cfb.defensefit": "u", "standalonefit": "t"}
    g = {"newthingfit": ["engine.newthingfit"], "wxfit": ["engine.wxfit"], "cfbdefensefit": ["engine.cfb.defensefit"]}
    got = W.detected(files, g)
    assert "engine.newthingfit" in got and "standalonefit" in got
    assert "newthingfit" not in got and "wxfit" not in got and "cfbdefensefit" not in got, "a runner is its twin"
    old = W.FITS
    try:
        W.FITS = tuple(r for r in old if r[0] != "engine.wxfit")
        assert any(p.startswith("engine.wxfit: measures something") for p in W.problems())
    finally:
        W.FITS = old


def test_a_claimed_reader_must_name_the_fit():
    old = W.FITS
    try:
        W.FITS = tuple(r if r[0] != "engine.wxfit" else ("engine.wxfit", "number", ("engine.odds",), "x") for r in old)
        assert "engine.wxfit: says engine.odds reads it, and engine.odds never names it" in W.problems()
        W.FITS = old + (("engine.nosuchfit", "number", ("engine.projection",), "x"),)
        assert "engine.nosuchfit: in the map, not in the repo" in W.problems()
    finally:
        W.FITS = old


def test_a_failed_fit_on_the_number_path_is_caught():
    real = W.graph

    def tampered(files=None):
        g = real(files)
        g["engine.projection"] = list(g["engine.projection"]) + ["engine.cbfit"]
        return g
    try:
        W.graph = tampered
        assert any(p.startswith("engine.cbfit: failed its bar and the number path imports it") for p in W.problems())
    finally:
        W.graph = real
    assert W.problems() == []


def test_the_gated_rows_are_the_gates_and_the_rest_are_cards():
    gated = {r[0] for r in W.FITS if r[1] == "gated"}
    assert gated == {f"engine.{mod}" for _n, mod, *_x in G.GATES}
    cards = {r[0] for r in W.FITS if r[1] == "card"}
    assert {f"engine.{mod}" for _n, mod, *_x in G.NEVER} <= cards
    failed = {r[0] for r in W.FITS if r[1] == "failed"}
    assert {"engine.cbfit", "engine.tdinjfit", "engine.tdmanfit", "engine.tdtop", "defoutfit"} <= failed


def test_the_lanes_and_the_report():
    ln = W.lanes()
    assert ln["engine.projection"] == "number" and ln["engine.ideagate"] == "number"
    assert ln["engine.wiremap"] == "cli"
    text = W.report("nfl")
    assert "THE INVENTIONS' GATES — nfl" in text and "not measured yet" in text
    assert "FINDINGS FOR A PERSON" in text and "engine.haircut" in text
    assert "NO PROBLEMS: every fit lands where the map says" in text


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
