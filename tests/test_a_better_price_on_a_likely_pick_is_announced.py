"""A Most Likely pick whose price gets better is announced in the feed.

Ethan, 2026-10-04: "do all of it" — the price-move alert. engine/feed now
keeps each build's Most Likely prices and announces a pick whose price got
two implied points better for the bettor, marked "worth it" when the new
price asks less than our chance minus the pick page's cushion. Checks: a
better price fires and a worse one does not; "worth it" follows the
cushion; the first build is silent; a watch on the player sees it.

Run directly: `python3 tests/test_a_better_price_on_a_likely_pick_is_announced.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import alerts, feed                                     # noqa: E402


def _board(odds_brown, odds_chase):
    return {"recommendations": [], "most_likely": [
        {"player": "Chase Brown", "team": "CIN", "opponent": "JAX", "market": "anytime_td",
         "market_label": "Anytime TD", "side": "OVER", "line": 0.5, "odds": odds_brown,
         "book": "Fanatics", "model_prob": 0.538},
        {"player": "Ja'Marr Chase", "team": "CIN", "opponent": "JAX", "market": "anytime_td",
         "side": "OVER", "line": 0.5, "odds": odds_chase, "book": "Fanatics", "model_prob": 0.473}]}


def test_a_better_price_fires_and_a_worse_one_does_not():
    prev = feed.likely_digest(_board(-145, 100))
    cur = feed.likely_digest(_board(-110, 115))
    ev = {e["player"]: e for e in feed.likely_diff(prev, cur, "nfl", "2026-10-04T12:00:00")}
    assert set(ev) == {"Chase Brown", "Ja'Marr Chase"}
    b = ev["Chase Brown"]
    assert b["kind"] == "likely_price" and b["frm"] == -145 and b["to"] == -110 and b["imp_delta"] < -0.02
    # -110 asks 52.4%, above our 53.8% less the 3-point cushion (50.8%):
    # better, but not yet inside what it is worth.
    assert b["worth"] is False


def test_worth_it_follows_the_cushion():
    prev = feed.likely_digest(_board(-145, 100))
    cur = feed.likely_digest(_board(-104, 125))
    ev = {e["player"]: e for e in feed.likely_diff(prev, cur, "nfl", "2026-10-04T12:00:00")}
    # -104 asks 51.0%; our 53.8% less 3 points is 50.8% → not yet worth it.
    assert ev["Chase Brown"]["worth"] is False
    # +125 asks 44.4%; our 47.3% less 3 points is 44.3% → just short too.
    assert ev["Ja'Marr Chase"]["worth"] is False
    cur = feed.likely_digest(_board(102, 130))
    ev = {e["player"]: e for e in feed.likely_diff(prev, cur, "nfl", "2026-10-04T12:05:00")}
    assert ev["Chase Brown"]["worth"] is True and ev["Ja'Marr Chase"]["worth"] is True


def test_a_worse_price_is_silent():
    prev = feed.likely_digest(_board(-110, 120))
    cur = feed.likely_digest(_board(-145, 100))
    assert feed.likely_diff(prev, cur, "nfl", "2026-10-04T12:00:00") == []


def test_the_first_build_is_silent_and_the_second_speaks():
    d = Path(tempfile.mkdtemp())
    path = d / "board.json"
    path.write_text(json.dumps(_board(-145, 100)), encoding="utf-8")
    assert feed.scan("nfl_test_likely", path, now="2026-10-04T12:00:00") == []
    path.write_text(json.dumps(_board(102, 130)), encoding="utf-8")
    got = [e for e in feed.scan("nfl_test_likely", path, now="2026-10-04T12:05:00") if e["kind"] == "likely_price"]
    assert len(got) == 2


def test_a_player_watch_sees_it():
    prev = feed.likely_digest(_board(-145, 100))
    ev = feed.likely_diff(prev, feed.likely_digest(_board(102, 130)), "nfl", "2026-10-04T12:00:00")
    assert any(alerts.matches(e, "player", alerts.normalize("player", "Chase Brown")[1]) for e in ev)
    assert any(alerts.matches(e, "team", alerts.normalize("team", "CIN")[1]) for e in ev)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
