"""A count is not a pick: the paywall keeps a board's numbers, and the UFC tab
tells a visitor what is locked rather than that nothing is there (USEREYES1,
18 November 2026).

Walking the UFC tab as a visitor: its Picks tile read "[object Object]". The
paywall empties every key named like a paid board at every depth
(engine/gate._strip), and UFC's `counts` holds `"picks": 3`, a number the
free tile prints; it went out as `{}`. The same page counted "Modeled 0,
Awaiting prices 0" on a card of twenty-one bouts (counted from the pass list,
which a visitor's copy no longer has), said "Nothing to pass on" over a list
of twenty-one fights it had locked, put the record's numbers in two tiles and
again in the ring under them, and said "weigh-in(s)". What these hold:

  * a whole number under a paid name passes the paywall; a list, a dict, a
    string and a float under one are emptied as before, and counted locked;
  * the UFC board counts the fights it modeled and the ones waiting on a
    price, free, and the tab reads those before its own count of the list;
  * a locked pass list says it is for members and how many fights it holds;
  * the record is the record tile and the ring; weigh-ins are counted in
    words ("40 weigh-ins").

    python3 tests/test_a_count_is_not_a_pick.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gate                                                      # noqa: E402

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def test_a_whole_number_under_a_paid_name_passes_and_a_board_does_not():
    board = {"sport": "ufc", "counts": {"fights": 21, "picks": 3, "passes": 18, "modeled": 9, "waiting": 12},
             "picks": [{"fighter": "A"}, {"fighter": "B"}, {"fighter": "C"}],
             "pass_list": [{"fighter": "D"}] * 18,
             "nested": {"picks": {"A": 1}, "near_misses": "A at +150", "correlation": 0.4}}
    out = gate.redact(board, "ufc.json")
    assert out["counts"] == board["counts"], out["counts"]
    assert out["picks"] == [] and out["pass_list"] == [], "the boards themselves are emptied"
    assert out["nested"]["picks"] == {} and out["nested"]["near_misses"] == {}, "a dict and a string still go"
    assert out["locked"]["picks"] == 3 and out["locked"]["pass_list"] == 18, out["locked"]
    assert "counts.picks" not in out["locked"], "a count is not reported as a locked board"
    assert board["counts"]["picks"] == 3 and len(board["picks"]) == 3, "the full board is untouched"


def test_the_ufc_board_counts_what_it_modeled_and_what_waits_on_a_price():
    src = (ROOT / "engine" / "ufc" / "model.py").read_text(encoding="utf-8")
    assert '"modeled": len(picks) + sum(p.get("reason_code") in ("gate", "clamp_kill") for p in passes),' in src
    assert '"waiting": sum(p.get("reason_code") == "no_price" for p in passes),' in src
    # And the rest of the card, so the tiles add up (18 November 2026: 21 bouts, 0 modeled, 10 waiting).
    assert '"thin": sum(p.get("reason_code") in ("no_dossier", "no_data") for p in passes)}}' in src
    assert "c.thin ? ` · ${c.thin} with too little on file to model` : \"\"" in MORE
    assert "const nModeled = c.modeled != null ? c.modeled" in MORE
    assert "const nWaiting = c.waiting != null ? c.waiting" in MORE
    assert 'statCardHTML("target", "Picks", Number(c.picks) || 0,' in MORE


def test_a_locked_pass_list_says_so_and_the_record_is_said_once():
    assert 'memberLockHTML("Why each fight was passed is for members",' in MORE
    assert ': panelEmpty("Nothing to pass on.")}' in MORE, "a member's empty list still says it"
    assert 'statCardHTML("star", "Graded", graded' not in MORE, "the ring's centre says how many graded"
    assert "open · units" not in MORE
    assert "weigh-in(s)" not in MORE and 'plural(w.unrecorded, "weigh-in")' in MORE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
