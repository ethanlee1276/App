"""An angle is said as measured, and only on its own side (step AIK, 27 November 2026).

The report's angles (engine/angles: where each defense gives up the most to the players this offense has) were
right 51 of 123 times live (41%), against 42% for an ordinary game. Replayed over 2022-2025, week by week from the
games before each, "where to look" angles beat the player's own average 39.9% of 2,431 times, against 42.8% for
every player in the same roles: they do not predict a player's game. So:

  * the angles section says so under them, with those numbers (gamereport.ANGLES_NOTE);
  * a pick card says a player's angle only on a pick that goes the angle's way (an over or a yes) in a market the
    angle points to. Before, an under could open on "this defense leaks yards to top receivers".

The names below are this test's own.

    python3 tests/test_an_angle_is_said_as_measured.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamereport as R                                   # noqa: E402

LEAK = "Top Receiver against the Visitors' coverage of No. 1 receivers: the Visitors give up 120 yards a game"


def _ctx():
    g = {"away": "VIS", "home": "HOM", "date": "2026-11-26"}
    return R.Ctx(g, {"games": [g], "scan_reads": {"VIS@HOM": {"players": []}}},
                 names={"VIS": "Visitors", "HOM": "Homers"}, sport="nfl")


def _pick(**kw):
    base = {"player": "Top Receiver", "team": "HOM", "market": "rec_yds", "market_label": "Receiving yards",
            "side": "Over", "line": 70.5, "model_prob": 0.6, "projection": 78.0}
    base.update(kw)
    return base


def test_an_angle_rides_a_pick_that_goes_its_way():
    angles = {"Top Receiver": (LEAK, "catches and yards")}
    assert R.card_why(_ctx(), _pick(), angles)[0] == LEAK
    assert R.card_why(_ctx(), _pick(market="receptions", line=5.5), angles)[0] == LEAK


def test_never_on_an_under_or_another_market():
    angles = {"Top Receiver": (LEAK, "catches and yards")}
    assert LEAK not in R.card_why(_ctx(), _pick(side="Under"), angles), "an under never opens on a leak to it"
    assert LEAK not in R.card_why(_ctx(), _pick(market="anytime_td", side="Yes", line=0.5), angles), \
        "a yards angle says nothing about a touchdown"
    td = {"Top Receiver": ("Top Receiver has 9 of their red-zone targets", "a touchdown")}
    assert R.card_why(_ctx(), _pick(market="anytime_td", side="Yes", line=0.5), td)[0].startswith("Top Receiver has 9")
    assert not R.card_why(_ctx(), _pick(market="anytime_td", side="No", line=0.5), td)
    assert R.ANGLE_MARKETS["rushing yards"] == ("rush_yds",)


def test_the_section_says_what_they_are_worth():
    note = R.ANGLES_NOTE
    assert "2022–2025" in note and "40% of the time" in note and "(43%)" in note, note
    assert "none of them moves our numbers" in note
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'blocks.append({"type": "note", "text": ANGLES_NOTE})' in src
    doc = (ROOT / "engine" / "angles.py").read_text(encoding="utf-8")
    assert "39.9% of 2,431, against 42.8%" in doc and "51 of 123" in doc, "the module keeps the measurement"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
