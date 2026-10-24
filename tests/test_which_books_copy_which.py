"""Which books copy which — the groups, the leaders, and the consensus that counts each opinion once.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 4: books that buy
the same number count as one opinion, not five, and a move at the leader
with the copies yet to follow is a stale line.

What these hold: agreement is counted per pair on every key both books
priced — the identical-line rate, and the over-price gap only where the
line matched; grouping is average linkage on one minus that rate, a pair
under 200 shared closes counts as far apart, and nothing merges at or past
the cut; a move is a line change at one book, signed; a leader is the book
whose moves its own group follows the same way inside 90 minutes, most
often, with the median lag; the consensus is read at the modal line, by
book and by group (a book in no group is its own); a group whose leader
sits on another number shows its copies as stale; the held-out test is
paired log loss over props with three groups or more on the line and
needs 2,000 of them; and the pick page says how many opinions price him.

Run directly: `python3 tests/test_which_books_copy_which.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import bookclusters as B                             # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _q(b, line, o=-110, u=-110):
    return {"book": b, "line": line, "over_odds": o, "under_odds": u}


def _closes(n=300):
    out = []
    for i in range(n):
        base = 50.5 + (i % 7)
        # a, b and c share a feed: identical lines; d hangs its own number.
        out.append([_q("a", base), _q("b", base, -112), _q("c", base), _q("d", base + (1 if i % 3 else 0))])
    return out


def test_agreement_is_counted_per_pair_and_the_gap_only_on_matching_lines():
    pairs = B.pair_agreement(_closes())
    assert pairs[("a", "b")]["shared"] == 300 and pairs[("a", "b")]["same"] == 1.0
    assert pairs[("a", "b")]["gap"] > 0 and pairs[("a", "c")]["gap"] == 0.0
    assert abs(pairs[("a", "d")]["same"] - 1 / 3) < 1e-3


def test_groups_merge_only_feeds_with_enough_evidence():
    g = B.groups(B.pair_agreement(_closes()))
    assert g == [["a", "b", "c"], ["d"]]
    thin = B.groups(B.pair_agreement(_closes(50)))
    assert thin == [["a"], ["b"], ["c"], ["d"]], "under 200 shared closes is not evidence of one feed"
    assert B.group_of(g) == {"a": 0, "b": 0, "c": 0, "d": 1}


def test_a_leader_is_who_its_own_group_follows_the_same_way():
    rows = [("2026-10-15T12:00:00Z", "i1", "a", 50.5), ("2026-10-15T12:00:00Z", "i1", "b", 50.5),
            ("2026-10-15T12:00:00Z", "i1", "d", 50.5),
            ("2026-10-15T13:00:00Z", "i1", "a", 52.5),          # a moves up …
            ("2026-10-15T13:20:00Z", "i1", "b", 52.5),          # … b follows in 20 minutes
            ("2026-10-15T13:25:00Z", "i1", "d", 51.5),          # d is another group: not a follow
            ("2026-10-15T18:00:00Z", "i1", "b", 51.5)]          # b drops alone, hours later
    mv = B.moves(rows)
    assert [(m[2], m[3]) for m in mv] == [("a", 1), ("b", 1), ("d", 1), ("b", -1)]
    lead = B.leaders(mv, [["a", "b"], ["d"]])
    assert lead == {"0": {"leader": "a", "follows": 1, "lag_min": 20.0}}


def test_the_consensus_counts_each_opinion_once_and_names_stale_copies():
    quotes = [_q("a", 60.5, -150, 120), _q("b", 60.5, -150, 120), _q("c", 60.5, -150, 120),
              _q("d", 60.5, 110, -130), _q("e", 61.5)]
    c = B.consensus(quotes, [["a", "b", "c"]])
    assert c["line"] == 60.5 and c["books"] == 4 and c["opinions"] == 2, "e is on another number; d is its own"
    assert c["by_book"] > c["by_group"], "three copies of one price no longer outvote d"
    assert B.consensus([_q("a", 60.5)], []) is None
    st = B.stale(quotes, [["a", "e"]], {"0": {"leader": "e", "follows": 9, "lag_min": 15}})
    assert st == [{"leader": "e", "line": 61.5, "behind": {"a": 60.5}, "lag_min": 15}]
    assert B.stale(quotes, [["a", "b"]], {"0": {"leader": "a", "follows": 3, "lag_min": 5}}) == [], \
        "a leader its copies already match leaves nothing stale"


def test_the_held_out_test_needs_three_groups_on_the_line_and_2000_props():
    groups = [["a", "b"], ["c"], ["d"]]
    case = ([_q("a", 60.5, -150, 120), _q("b", 60.5, -150, 120), _q("c", 60.5), _q("d", 60.5)], 70.0)
    r = B.consensus_test([case] * 50, groups)
    assert r["n"] == 50 and not r["holds"], "50 props is not 2,000"
    two = ([_q("a", 60.5), _q("c", 60.5)], 70.0)
    assert B.consensus_test([two] * 10, groups)["n"] == 0, "two groups on the line is not a test"


def test_the_pick_page_says_how_many_opinions_price_him():
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        board = {"recommendations": [{"player": "X", "market": "rec_yds",
                                      "all_lines": [_q("a", 60.5, -150, 120), _q("b", 60.5, -150, 120), _q("d", 60.5)]}]}
        unfit = B.pick_view(B.ideas_section([], [], board, "nfl"), "X", "rec_yds")
        assert unfit["opinions"] == 3 and unfit["measured"] is False, "before the fit, every book is its own opinion"
        B.save({"sport": "nfl", "groups": [["a", "b"], ["d"]], "leaders": {}, "consensus": {"n": 0},
                "test_seasons": [2024, 2025]})
        v = B.pick_view(B.ideas_section([], [], board, "nfl"), "X", "rec_yds")
        assert v["opinions"] == 2 and v["books"] == 3 and v["measured"] and v["groups"] == [["a", "b"]]
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["copies"] == "bookclusters"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps({'sections': {'copies': v}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "Which books copy which" in h and "3 books price 60.5 — 2 independent opinions" in h
    assert "<li>a · b</li>" in h and "Fair over, by opinion" in h


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
