"""The comps count a band off a form-sorted index, not by walking every
past spot for every prop (engine/comps._BandIndex, decorate).

`decorate` asked `comp_record` once per priced prop, and each walked its
market's whole index — every past player-game since the logs begin — to
keep the ones inside a ±15% form band: 10.7 of the NFL pricing stage's 48
seconds at 09:16 on 8 November. What these hold:

  * every record is `comp_record`'s, to the digit — over, under, push, the
    rate, the band and the player's own count — across thousands of lines,
    forms and players, pushes included;
  * a spot exactly on either edge of the band is in it, as it always was,
    and one a hair outside is not;
  * an index of any size — a block exactly full, one over, one short —
    counts the same;
  * a replay's `before` cutoff, and a band that is not a number, are
    counted by `comp_record` itself;
  * `decorate` hangs exactly what it hung before on every card.

Run directly: `python3 tests/test_the_comps_count_a_band_without_walking_every_spot.py`
"""
import copy
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import comps as C                                       # noqa: E402
from engine import db                                               # noqa: E402


def _index(players=120, games=60, seed=3):
    rnd = random.Random(seed)
    out = []
    for p in range(players):
        mu = rnd.uniform(0.5, 90)
        for g in range(games):
            f = max(0.0, rnd.gauss(mu, mu * 0.2))
            v = float(max(0, round(rnd.gauss(f, 6))))           # integers: pushes on whole lines
            out.append(((2019 + g // 17, f"{g % 17 + 1:03d}"), f"P{p}", f, v))
    return out


def _cases(n, seed=5, players=120):
    rnd = random.Random(seed)
    lines = [x + 0.5 for x in range(0, 100)] + [float(x) for x in range(0, 100)]
    return [(rnd.choice(lines), rnd.uniform(0, 110), rnd.choice([None, f"P{rnd.randrange(players)}", "Nobody"]))
            for _ in range(n)]


def test_every_record_is_comp_records_to_the_digit():
    idx = _index()
    bi = C._BandIndex(idx)
    cases = _cases(2500)
    got = [bi.record(l, f, player=p) for l, f, p in cases]
    want = [C.comp_record(idx, l, f, player=p) for l, f, p in cases]
    assert got == want
    assert sum(1 for r in want if r) > 1500, "most cases clear the sample bar"
    assert any(r and r["push"] for r in want) and any(r and r["own"] for r in want), \
        "pushes and the player's own spots were exercised"
    for min_n in (1, 10, 400):
        assert [bi.record(l, f, min_n=min_n) for l, f, _p in cases[:300]] == \
               [C.comp_record(idx, l, f, min_n=min_n) for l, f, _p in cases[:300]]


def test_a_spot_on_either_edge_of_the_band_is_in_it():
    lo, hi = C._band(10.0)
    assert (lo, hi) == (8.5, 11.5)
    idx = [((2026, "001"), "Edge", lo, 12.0), ((2026, "002"), "Edge", hi, 3.0),
           ((2026, "003"), "Out", math.nextafter(lo, 0), 30.0), ((2026, "004"), "Out", math.nextafter(hi, 99), 0.0)]
    idx += [((2026, f"{k + 5:03d}"), f"Mid{k}", 10.0, float(k % 13)) for k in range(300)]
    bi = C._BandIndex(idx)
    for line in (2.5, 3.0, 6.0, 12.0, 11.5):
        assert bi.record(line, 10.0, min_n=1, player="Edge") == \
               C.comp_record(idx, line, 10.0, min_n=1, player="Edge"), line
    r = bi.record(5.5, 10.0, min_n=1, player="Edge")
    assert r["own"] == 2, "both edge spots counted, neither of the two a hair outside"


def test_an_index_of_any_size_counts_the_same():
    full = _index(players=40, games=20, seed=9)
    for size in (0, 1, C._BandIndex.BLOCK - 1, C._BandIndex.BLOCK, C._BandIndex.BLOCK + 1,
                 2 * C._BandIndex.BLOCK + 3, len(full)):
        idx = full[:size]
        bi = C._BandIndex(idx)
        for l, f, p in _cases(150, seed=size + 1, players=40):
            assert bi.record(l, f, min_n=1, player=p) == C.comp_record(idx, l, f, min_n=1, player=p), size


def test_a_replay_cutoff_and_a_band_that_is_not_a_number_go_to_comp_record():
    idx = _index(players=60, games=40)
    bi = C._BandIndex(idx)
    for before in ((2020, "009"), (2021, "001")):
        for l, f, p in _cases(200, players=60):
            assert bi.record(l, f, before=before, player=p) == C.comp_record(idx, l, f, before=before, player=p)
    # A NaN form makes a NaN band, which `comp_record` lets every spot
    # through; its record carries NaN, which never equals itself, so the
    # two are compared as text.
    import json
    nan = float("nan")
    got, want = bi.record(10.5, nan, min_n=1), C.comp_record(idx, 10.5, nan, min_n=1)
    assert json.dumps(got, sort_keys=True) == json.dumps(want, sort_keys=True)
    assert got["n"] == sum(1 for s in idx if s[3] != 10.5), "every spot let through, as before"


def _cards():
    rnd = random.Random(11)
    cards = []
    for k in range(400):
        market = rnd.choice(["hits", "total_bases"])
        p = f"Bat{rnd.randrange(30)}"
        cards.append({"player": p, "market": market, "line": rnd.choice([0.5, 1.5, 2.5, 1.0, 2.0]),
                      "side": rnd.choice(["OVER", "UNDER"]), "hit_prob": rnd.uniform(0.2, 0.8),
                      "recent_values": [float(rnd.randrange(0, 4)) for _ in range(rnd.choice([2, 5, 10]))]})
    cards.append({"player": "x", "market": None, "line": 1.5})
    return cards


def _population():
    conn = db.connect(":memory:")
    rnd = random.Random(7)
    rows = []
    for p in range(30):
        mu = 2.0 if p < 15 else 0.8
        for g in range(60):
            for market in ("hits", "total_bases"):
                rows.append({"sport": "mlb", "season": 2026, "period": f"2026-0{4 + g // 31}-{g % 31 + 1:02d}",
                             "game_id": f"g{p}-{g}", "player": f"Bat{p}", "team": "NYY", "opponent": "BOS",
                             "position": "", "home": 1, "market": market,
                             "value": max(0, round(rnd.gauss(mu * (1.6 if market == "total_bases" else 1), 0.9)))})
    db.upsert_player_logs(conn, rows)
    return conn


def test_decorate_hangs_exactly_what_it_hung_before():
    conn = _population()
    now = copy.deepcopy(_cards())
    was = copy.deepcopy(_cards())
    got = C.decorate(now, conn, "mlb")
    keep = C._BandIndex.record
    C._BandIndex.record = lambda self, line, form, band=C.FORM_BAND, before=None, min_n=C.MIN_COMPS, player=None: \
        C.comp_record(self.spots, line, form, band=band, before=before, min_n=min_n, player=player)
    try:
        want = C.decorate(was, conn, "mlb")
    finally:
        C._BandIndex.record = keep
    assert got == want and now == was
    assert got["matched"] > 100 and any("comps" in c for c in now)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
