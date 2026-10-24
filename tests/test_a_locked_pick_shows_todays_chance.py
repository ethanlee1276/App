"""A locked Most Likely pick shows today's chance, and the one it went up at.

Ethan, 2026-09-25, circling Jameson Williams UNDER 69.5 receiving yards:
the Model tile read 75% and a TOP tag, while the lock note under his name
said "Our chance has eased under 55% since this went up". "How can we
display our model is saying this has a 71% chance too hit but then say it
went under 55% in the other spot. Which number do I trust? ... We need
the models estimate to be constantly updating."

A locked pick carried the chance it was POSTED at, forever. It now keeps
its number, price and book as posted, and carries the model's chance at
that number off every build (`likely._prob_at`, the derivation a ladder
rung is priced with), today's projection beside it, and the posted
chance as `first_prob`. The note says both numbers.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}
RUNG = [{"book": "Novig", "line": 69.5, "over_odds": 300, "under_odds": -212}]


def _row(projection):
    return {"player": "Jameson Williams", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
            "market_label": "Rush Yards", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
            "has_market": True, "fair_prob": 0.50, "projection": projection, "ev_per_unit": 0.01,
            "reasons": ["because"], "recent_values": [55, 71, 48, 66], "game_date": "2026-09-27",
            "kickoff": "13:00", "hit_prob": 0.56, "raw_prob": 0.58, "alt_lines": RUNG,
            "alt_sharp_lines": []}


def _board(props, previous=None, now="2026-09-24T02:00:00Z"):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    turn: dict = {}
    try:
        rows = K.build(props, sport="nfl", fits=FITS, previous=previous, now=now, turnover=turn)
    finally:
        K.rankable = real
    return rows, turn


def _posted():
    b0, t0 = _board([_row(52.0)], now="2026-09-23T20:00:00Z")
    (r,) = b0
    assert (r["side"], r["line"]) == ("under", 69.5), r
    return b0, t0, r["model_prob"]


def test_the_chance_on_a_locked_pick_is_todays():
    b0, t0, then = _posted()
    prev = {"rows": b0, "day": t0.get("day") or {}, "earlier": []}
    b1, _ = _board([_row(90.0)], previous=prev)
    (r,) = b1
    assert r["locked"] and (r["side"], r["line"]) == ("under", 69.5), "the number stays as posted"
    assert r["model_prob"] < K.MIN_PROB < then, (r["model_prob"], then)
    assert r["first_prob"] == then, "the chance it went up at rides beside it"
    assert r["projection"] == 90.0, "today's projection, not the posted one"
    assert f"now {round(r['model_prob'] * 100)}%, down from {round(then * 100)}%" in r["lock_note"]


def test_a_pick_posted_at_the_main_number_reads_the_chance_a_fresh_pick_shows():
    # Box run, 2026-10-17: posted rushing-attempts picks read 84% (the raw
    # normal) beside the 54% the same number got as a fresh pick. At its own
    # main number a posted pick now carries the main line's shown chance,
    # and the other side its complement; a ladder stays one curve.
    row = dict(_row(70.0), side="over", line=62.5)
    shown = K._main_shown(row, "rush_yds", FITS)
    assert shown is not None
    assert K._prob_at(row, "rush_yds", "over", 62.5, FITS, main_as_shown=True) == round(shown, 4)
    assert K._prob_at(row, "rush_yds", "under", 62.5, FITS, main_as_shown=True) == round(1 - shown, 4)
    curve = [K._prob_at(row, "rush_yds", "over", x, FITS) for x in (57.5, 62.5, 67.5)]
    assert curve[0] >= curve[1] >= curve[2], curve
    src = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    i = src.index("    def now_prob(h):")
    assert "main_as_shown=True" in src[i:i + 400], "the board's posted picks ask for it"


def test_the_card_labels_it_now_and_shows_the_posted_chance():
    i = APP.index("function likelyCard(")
    card = APP[i:APP.index("\nfunction ", i + 10)]
    assert 'r.locked ? " now" : ""' in card
    assert "when posted</div>" in card


# ── a locked pick under the bar moves to its own fold ─────────────────────
# Ethan, asked where such a pick belongs: "Move it into a small 'posted…'".


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_page_bar_is_the_engines():
    assert f"const LIKELY_MIN_PROB = {K.MIN_PROB};" in APP


def test_a_dropped_pick_leaves_the_lists_for_its_fold():
    dropped = _fn("likelyDropped")
    assert "r.locked" in dropped and "< LIKELY_MIN_PROB" in dropped, "only a posted pick moves"
    for name in ("renderLikely", "renderLikelyTop"):
        body = _fn(name)
        assert ".filter((r) => !likelyDropped(r))" in body, name
        assert "likelyDroppedHTML(dropped)" in body, name
    assert "likelyDroppedHTML(droppedHere" in APP, "the game page too"
    # Still a live bet: its game's chip counts it.
    assert "likelyDropped" not in _fn("gamePickCounts")


def test_the_fold_names_it_and_shows_todays_chance():
    import json
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        return
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);"
               "const likelyRow=(r)=>`<row>${r.player} ${Math.round(r.model_prob*100)}%</row>`;"
               f"const LIKELY_MIN_PROB = {K.MIN_PROB};\n" + _fn("likelyDropped") + _fn("likelyDroppedHTML")
               + "\nconst xs=JSON.parse(process.argv[2]);"
               "process.stdout.write(JSON.stringify({flags: xs.map(likelyDropped),"
               " html: likelyDroppedHTML(xs.filter(likelyDropped)).replace(/<[^>]+>/g,' ')}));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    xs = [{"player": "Jameson Williams", "locked": True, "model_prob": 0.41, "first_prob": 0.75},
          {"player": "Held", "locked": True, "model_prob": 0.62},
          {"player": "Fresh", "model_prob": 0.50},
          {"player": "Unpriced", "locked": True}]
    out = subprocess.run(["node", path, json.dumps(xs)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = json.loads(out.stdout)
    assert got["flags"] == [True, False, False, False], got["flags"]
    text = " ".join(got["html"].split())
    assert text.startswith("Posted, but our chance has dropped 1"), text
    assert "Jameson Williams 41%" in text and "tracked and graded" in text
    assert "Held" not in text


def test_a_posted_pick_carries_todays_bigger_lines_or_none():
    # Box run, 2026-10-24: a posted under 19.5 still showed an under 14.5 at
    # -9900 that today's ladder refuses — last build's lines rode in on the
    # carried-forward row, and an empty answer today left them in place.
    b0, t0, _then = _posted()
    b0[0]["bigger_lines"] = [{"side": "under", "line": 14.5, "odds": -9900, "book": "DK", "prob": 0.64,
                              "worth_at": -178, "better": False}]
    prev = {"rows": b0, "day": t0.get("day") or {}, "earlier": []}
    (r,) = _board([_row(90.0)], previous=prev)[0]
    assert r["locked"] and "bigger_lines" not in r, r.get("bigger_lines")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
