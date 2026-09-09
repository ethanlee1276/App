"""The paywall's two copies, and the tools that kept reading the wrong one.

`web/data/*.json` is the PUBLIC copy — `engine/gate.publish` strips every
key in `PAID_KEYS` from it, and `recommendations` is the first name on
that list. `data/built/*.json` is the full board. `gate.board_source`
exists to resolve one to the other, and its docstring already names three
tools that had to learn this the hard way:

    engine/parlays.arbitrate_slate   the one-parlay-per-slate cap was
                                     silently not enforced at all
    parlaycheck.py                   "every published ticket is
                                     internally consistent", having found
                                     no tickets
    launch.py --odds-doctor          counted priced games off the public
                                     copy and reported 0 of 15

`--boards` was the fourth ("The zero in the recs column is the paywall
again"). A diagnostic written on 2026-09-08 was the fifth. These are the
sixth, seventh and eighth, and they are the worst of the set, because
every one of them is a tool you open specifically to ask why the board
is thin:

    --why-many    walked an empty list and reported on nothing
    --why-empty   printed "has no analyzed props at all" over a board
                  holding 286 of them — a tool built to explain an empty
                  board inventing the emptiness it then explained
    --check       measured knowledge-tier coverage over zero reasons,
                  and its `if rows:` guard turned that into silence

None of them raised. That is the whole shape of this bug: the public
copy is valid JSON with a key missing, so every reader gets an empty
list and reports honestly on nothing.
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import sqlite3                                                # noqa: E402

import launch                                                # noqa: E402
from engine import gate, ledger                              # noqa: E402


def _empty_ledger():
    """A throwaway journal. The suite must not read the box it runs on,
    and `why_many` reads the ledger for its nightly baseline — patched at
    `connect` rather than at DEFAULT_DB, which binds at definition time
    (the trap tests/test_why_many.py documents)."""
    db = os.path.join(tempfile.mkdtemp(), "ledger.db")
    conn = sqlite3.connect(db)
    conn.executescript(ledger.SCHEMA)
    conn.commit()
    conn.close()
    return db


def _prop(player="Puka Nacua", odds=-115, hit=0.62, rec=True):
    return {"player": player, "market": "rec_yds", "side": "over",
            "line": 64.5, "odds": odds, "hit_prob": hit,
            "has_market": True, "recommended": rec, "confidence": 7.4,
            "grade": "Play", "reasons": ["Measured: 12-game usage baseline"]}


def _paywalled(sport="nfl", rows=None):
    """A tree in the state production is in: the public copy stripped of
    `recommendations`, the private copy holding them."""
    rows = [_prop()] * 3 if rows is None else rows
    tmp = pathlib.Path(tempfile.mkdtemp())
    rel = ("web/data/mlb_recommendations.json" if sport == "mlb"
           else "web/data/recommendations.json")
    pub = tmp / rel
    pub.parent.mkdir(parents=True, exist_ok=True)
    full = tmp / "data" / "built" / pub.name
    full.parent.mkdir(parents=True, exist_ok=True)
    board = {"recommendations": rows, "counts": {}, "games": []}
    full.write_text(json.dumps(board))
    # Exactly what publish() leaves behind: same file, paid keys gone.
    stripped = {k: v for k, v in board.items()
                if k not in gate.paid_keys_for(pub.name)}
    pub.write_text(json.dumps(stripped))
    return tmp


def _run(fn, tmp, *a, **kw):
    old, old_connect = launch.ROOT, ledger.connect
    db = _empty_ledger()
    launch.ROOT = tmp
    ledger.connect = lambda *a_, **k_: old_connect(db)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(*a, **kw)
        return buf.getvalue()
    finally:
        launch.ROOT, ledger.connect = old, old_connect


def test_the_public_copy_really_does_lose_the_picks():
    """The premise everything below rests on. If `recommendations` ever
    stops being a paid key this test says so, rather than the rest of
    the file quietly passing for the wrong reason."""
    tmp = _paywalled()
    pub = json.loads(
        (tmp / "web" / "data" / "recommendations.json").read_text())
    full = json.loads(
        (tmp / "data" / "built" / "recommendations.json").read_text())
    assert pub.get("recommendations") in (None, [])
    assert len(full["recommendations"]) == 3


# ------------------------------------------------------------- --why-empty

def test_why_empty_does_not_report_a_full_board_as_having_no_props():
    """The sentence this printed on every paywalled box: "has no analyzed
    props at all"."""
    out = _run(launch.why_empty, _paywalled(), "nfl")
    assert "no analyzed props at all" not in out, out
    assert "3 analyzed" in out, out


def test_why_empty_walks_the_funnel_on_the_rows_that_exist():
    out = _run(launch.why_empty, _paywalled(), "nfl")
    assert "Nacua" in out or "real price" in out, out


def test_why_empty_still_says_so_when_the_board_genuinely_is_empty():
    """The message is correct and must survive: a board with nothing in
    EITHER copy has nothing to explain, and saying that is the tool
    working."""
    out = _run(launch.why_empty, _paywalled(rows=[]), "nfl")
    assert "no analyzed props at all" in out, out


# -------------------------------------------------------------- --why-many

def test_why_many_counts_the_picks_that_are_actually_on_the_board():
    """It reported on nothing without raising, which is why nobody
    noticed: an empty list is a legal answer to every question it asks."""
    out = _run(launch.why_many, _paywalled(), "nfl")
    assert "3 prop(s) priced · 3 recommended" in out, out


def test_why_many_on_a_stripped_copy_would_have_said_zero_of_zero():
    """The negative control that makes the assertion above mean
    something: hand it only the public copy and the old reading is what
    comes back — no error, no empty-board branch, just a confident zero.
    That is why five tools carried this bug for weeks."""
    tmp = _paywalled()
    (tmp / "data" / "built" / "recommendations.json").unlink()
    out = _run(launch.why_many, tmp, "nfl")
    assert "0 prop(s) priced · 0 recommended" in out, out


def test_both_probes_resolve_through_board_source_not_by_hand():
    """Pinned on the CALL, because the failure is a path built by string
    concatenation that never learns. A future probe copying either of
    these should copy the resolution too."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    for name in ("def why_empty", "def why_many"):
        fn = src.split(name, 1)[1].split("\ndef ", 1)[0]
        assert "board_source(ROOT / rel)" in fn, name
        assert "p = ROOT / rel" not in fn, name


# ------------------------------------------------- the knowledge-tier check

def test_the_tier_check_reads_the_full_board():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("Are the knowledge tiers still labelling everything")
    block = src[i:i + 1600]
    assert "board_source(ROOT / _rel)" in block, block[:600]


def test_the_tier_check_is_loud_when_it_measured_nothing():
    """Its `if rows:` guard meant zero reasons rendered as a clean run.
    A check that stops checking leaves the screen looking exactly as it
    does when all is well — which is how this survived."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("Are the knowledge tiers still labelling everything")
    block = src[i:i + 3200]
    assert "nothing was measured" in block, block[-800:]
    assert "not the same" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
