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

THE NINTH AND TENTH ARRIVED ON 2026-09-15, both written the same day,
and between them they broke the feature Ethan had asked for that
morning. `most_likely` and `pick_of_the_day` are on PAID_KEYS too:

    potd_report.py           printed "The board carries no Most Likely
                             rows at all" for five leagues at once, on a
                             box whose journal held a pick locked that
                             morning — which read as every board on the
                             site having gone empty
    launch._write_day_top_pick  ranked five stripped boards against each
                             other and published "no pick" every cycle,
                             on a card that cannot look any different on
                             a genuinely quiet day

The first one is why the second went unnoticed: the tool you would open
to check the card was reading the same empty file the card was.
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


def _prop(player="Puka Nacua", odds=-115, hit=0.62, rec=True, edge=0.05,
          conf=7.4, market="receptions"):
    return {"player": player, "market": market, "side": "over",
            "line": 64.5, "odds": odds, "hit_prob": hit, "edge": edge,
            "has_market": True, "recommended": rec, "confidence": conf,
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
    # Exactly what publish() leaves behind — through gate.redact itself,
    # not a hand-rolled imitation of it. The real strip keeps the key and
    # empties it ("0 picks tonight" is true and is not a paywall), which
    # is precisely why every reader downstream saw a legal empty list
    # rather than a KeyError.
    pub.write_text(json.dumps(gate.redact(board, pub.name)))
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
    assert pub.get("recommendations") == [], pub
    assert "recommendations" in pub, "the key survives; only the rows go"
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


# ------------------------------------------ which gate costs the most, always

def _band(n, **kw):
    """n props identical except for one field, so a single gate binds."""
    return [_prop(player=f"P{i}", **kw) for i in range(n)]


def test_a_thin_board_is_told_which_gate_costs_it_the_most():
    """The gap this tool had exactly where #164 needs it. The costliest
    gate was computed only when NOTHING survived, so at 5 of 286 — thin,
    which is the state Ethan actually opens this in — the screen went
    quiet about the one thing it had just worked out."""
    rows = _band(3) + _band(9, conf=3.0)   # 9 die on confidence alone
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    assert "SHOULD be recommended" in out, out
    assert "Costliest gate" in out, out


def test_the_costliest_gate_is_quoted_as_what_it_would_ADD():
    """"12 clear everything but this one" is not actionable when 3 of
    them already clear everything. The number worth arguing about is the
    9 you would gain."""
    rows = _band(3) + _band(9, conf=3.0)
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    line = [ln for ln in out.splitlines() if "Costliest gate" in ln]
    assert len(line) == 1, out
    assert "add 9 more" in line[0], line
    assert "to 12" in line[0], line


def test_no_gate_is_blamed_when_none_is_on_its_own_binding():
    """A prop refused by two gates is not evidence against either. Naming
    a costliest gate anyway would send the reader to loosen a bar that
    buys nothing."""
    out = _run(launch.why_empty, _paywalled(rows=_band(4)), "nfl")
    assert "No single gate is holding anything back" in out, out
    assert "Costliest gate" not in out, out


def test_an_empty_board_still_gets_the_binding_gate_sentence():
    """Unchanged, and the case the original code was written for."""
    out = _run(launch.why_empty, _paywalled(rows=_band(6, conf=3.0)), "nfl")
    assert "Binding gate" in out, out


# ------------------------------- a bar is scored over the props it saw

def test_a_bar_is_counted_over_the_eligible_pool_not_the_whole_board():
    """2026-09-09's real board read "credible (edge ≤ 5%) 75 / 173" with
    108 of that 173 sitting in markets the model refuses to price. The
    denominator hid the answer: there was no way to see how much of the
    98 over the ceiling was simply the shut yardage markets shouting."""
    rows = _band(3) + _band(9, market="rush_yds")
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    bar = [ln for ln in out.splitlines() if "grade ≠ Pass" in ln and "/" in ln]
    assert len(bar) == 1, out
    assert bar[0].split()[2] == "3", bar     # the 3 eligible, not the 12


def test_eligibility_is_still_scored_over_everything():
    """The two structural refusals are about the whole board by
    definition — "9 of 12 are in a shut market" is the fact, and scoring
    it over the eligible pool would make it 0 of 3 and say nothing."""
    rows = _band(3) + _band(9, market="rush_yds")
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    line = [ln for ln in out.splitlines()
            if "we can price at all" in ln and "/" in ln]
    assert line[0].split()[2] == "12", line


def test_the_report_says_which_denominator_it_is_using():
    """A number whose base is not stated is the thing that went wrong
    here. Both sections now name theirs."""
    rows = _band(3) + _band(9, market="rush_yds")
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    assert "Eligible at all:" in out, out
    assert "over the 3 eligible" in out, out
    assert "never a candidate" in out, out


def test_a_board_with_nothing_eligible_says_no_bar_was_consulted():
    """Otherwise it prints a column of "0 / 0" and invites the reader to
    tune bars that were never reached."""
    out = _run(launch.why_empty,
               _paywalled(rows=_band(6, market="rush_yds")), "nfl")
    assert "no bar has been consulted" in out, out
    assert "0 / 0" not in out, out


# ------------------------------------------- the market the model refuses

def test_a_shut_market_is_its_own_gate_and_not_the_graders_fault():
    """2026-09-09, the real board: 173 priced props, 164 graded Pass, and
    the report named "engine graded it" as the costliest gate. It is not.
    `engine/calibrate.SHUT_MARKETS` hard-refuses nfl:rush_yds (AUC 0.479
    against real closes) and nfl:rec_yds (0.47) — every prop in them dies
    before a threshold is consulted, and with no gate of their own their
    deaths landed on whichever numeric gate caught them."""
    rows = _band(3) + _band(9, market="rush_yds")
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    line = [ln for ln in out.splitlines()
            if ln.strip().endswith("market is one we can price at all")
            and "/" in ln]
    assert len(line) == 1, out
    assert line[0].split()[0] == "3", line          # 3 of 12 are priceable
    assert line[0].split()[2] == "12", line


def test_it_names_the_shut_markets_and_says_why_each_is_shut():
    """"calibration 172" is a mystery; "rushing yards is shut: AUC 0.479
    against real closes" is something to act on. The reason is quoted
    from calibrate, not paraphrased here, so the two cannot drift."""
    from engine.calibrate import shut_reason
    out = _run(launch.why_empty,
               _paywalled(rows=_band(9, market="rush_yds")), "nfl")
    assert "cannot price" in out, out
    assert "rush_yds" in out, out
    assert shut_reason("nfl", "rush_yds")[:40] in out, out


def test_the_shut_gate_is_never_offered_as_something_to_relax():
    """The advice the old report gave — "relaxing it alone would add 9
    more" — was advice to put rushing and receiving yards back on a board
    they were measured off. There is no bar here to lower."""
    rows = _band(3) + _band(9, market="rush_yds")
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    assert "Costliest gate" not in out, out
    assert "measured refusal, not a bar to lower" in out, out


def test_a_priceable_market_is_still_offered_as_relaxable():
    """The negative control: an ordinary threshold IS worth arguing
    about, and must keep saying so."""
    rows = _band(3) + _band(9, conf=3.0)
    out = _run(launch.why_empty, _paywalled(rows=rows), "nfl")
    assert "Costliest gate" in out, out
    assert "measured refusal" not in out, out


def test_the_shut_gate_sits_above_every_numeric_one():
    """Order is the finding, and it is now structural: the shut check is
    an ELIGIBILITY test, and eligibility is consulted before any bar.
    Below them, a shut prop is first counted as a grading failure or an
    edge failure, and the report then blames the bar that caught it."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    fn = src.split("def why_empty", 1)[1].split("\ndef ", 1)[0]
    assert fn.index("eligibility = [") < fn.index("bars = [")
    elig = fn[fn.index("eligibility = ["):fn.index("bars = [")]
    bars = fn[fn.index("bars = ["):fn.index("gates = eligibility + bars")]
    assert "we can price at all" in elig, elig
    assert "already started" in elig or "started" in elig, elig
    # And it is NOT a bar — a bar is a candidate measured and found
    # short, which a prop in a shut market never was.
    assert "we can price at all" not in bars, bars
    assert "grade ≠ Pass" in bars and "net edge > 0" in bars
    # The walk is eligibility first, by construction rather than by the
    # order somebody happened to type the list in.
    assert "gates = eligibility + bars" in fn


# ------------------------------- the day's top pick, and its own report

def _likely(player="Shohei Ohtani", odds=-130, fair=0.62):
    """One Most Likely row with a sharp witness behind its fair."""
    return {"player": player, "market": "moneyline", "side": "over",
            "odds": odds, "sharp_anchored": True, "sharp_fair": fair,
            "fair_prob": fair, "prob": fair, "evidence": "sharp",
            "team": "LAD", "opponent": "SD"}


def _paywalled_likely(sport="nfl", rows=None, day=None, below_bar=""):
    """A paywalled tree whose board carries the two keys the Pick of the
    Day features read: `most_likely` (the pool `potd_report` walks) and
    `pick_of_the_day` (what `_write_day_top_pick` ranks across leagues).
    BOTH are on `gate.PAID_KEYS`, which is the whole bug.

    Dated from the CLOCK, not from a fixed day: `_write_day_top_pick`
    compares the board's date against today's, so a frozen date here
    would make the test pass or fail by the calendar.
    """
    import time as _time
    rows = [_likely()] if rows is None else rows
    day = day or _time.strftime("%Y-%m-%d")
    tmp = pathlib.Path(tempfile.mkdtemp())
    rel = {"nfl": "recommendations.json",
           "mlb": "mlb_recommendations.json"}.get(sport, f"{sport}.json")
    pub = tmp / "web" / "data" / rel
    pub.parent.mkdir(parents=True, exist_ok=True)
    full = tmp / "data" / "built" / pub.name
    full.parent.mkdir(parents=True, exist_ok=True)
    top = dict(rows[0]) if rows else None
    if top and below_bar:
        top["below_bar"] = below_bar
    board = {"recommendations": [], "most_likely": rows, "counts": {},
             "games": [], "built_at": f"{day}T12:00:00",
             "pick_of_the_day": {"date": day, "pick": top}}
    full.write_text(json.dumps(board))
    pub.write_text(json.dumps(gate.redact(board, pub.name)))
    return tmp


def test_the_public_copy_loses_the_likelihood_board_too():
    """The premise, stated the same way as the one at the top of this
    file: if `most_likely` or `pick_of_the_day` ever stops being paid,
    this says so rather than letting the rest pass for a wrong reason."""
    tmp = _paywalled_likely()
    pub = json.loads((tmp / "web" / "data" / "recommendations.json").read_text())
    full = json.loads((tmp / "data" / "built" / "recommendations.json").read_text())
    assert pub.get("most_likely") == [], pub.get("most_likely")
    assert not (pub.get("pick_of_the_day") or {}).get("pick"), pub
    assert len(full["most_likely"]) == 1
    assert full["pick_of_the_day"]["pick"]


def test_the_potd_report_does_not_call_a_full_board_empty():
    """The sentence Ethan got back from the droplet, five times over —
    once per league — on a box whose journal held a pick locked that
    morning: "The board carries no Most Likely rows at all"."""
    import potd_report
    tmp = _paywalled_likely(rows=[_likely(player=f"P{i}") for i in range(3)])
    path = next(p for p in potd_report.board_paths("nfl", str(tmp / "web" / "data"))
                if os.path.exists(p))
    out = potd_report.report(potd_report._load(path), "nfl")
    assert "no Most Likely rows at all" not in out, out
    assert "3 row(s) considered" in out, out


def test_the_potd_report_on_the_stripped_copy_is_the_bug_reproduced():
    """The negative control that makes the assertion above mean
    something. Delete the private copy and the old reading comes back:
    no error, no complaint, just a confident report about nothing."""
    import potd_report
    tmp = _paywalled_likely(rows=[_likely(player=f"P{i}") for i in range(3)])
    (tmp / "data" / "built" / "recommendations.json").unlink()
    path = next(p for p in potd_report.board_paths("nfl", str(tmp / "web" / "data"))
                if os.path.exists(p))
    out = potd_report.report(potd_report._load(path), "nfl")
    assert "no Most Likely rows at all" in out, out


def test_the_day_top_pick_writer_reads_the_full_board():
    """`_write_day_top_pick` opened `ROOT / BOARD_FILES[sport]` — the
    public copy — so on the droplet it ranked five empty boards and
    published "no pick" every cycle. A below-bar lean is used because it
    is the one shape exempt from the journal lock, and the journal here
    is empty by construction (the suite must not read this box)."""
    tmp = _paywalled_likely(below_bar="the price drifted past the band")
    _run(launch._write_day_top_pick, tmp)
    got = json.loads((tmp / "web" / "data" / "day_top_pick.json").read_text())
    assert got.get("pick"), got
    assert got.get("sport") == "nfl", got


def test_the_day_top_pick_writer_on_the_stripped_copy_publishes_nothing():
    """Same negative control. This is what the droplet was writing every
    five minutes, and the card on the page cannot tell it from a quiet
    day — which is why it went unnoticed until the report beside it said
    the same thing five times."""
    tmp = _paywalled_likely(below_bar="the price drifted past the band")
    (tmp / "data" / "built" / "recommendations.json").unlink()
    _run(launch._write_day_top_pick, tmp)
    got = json.loads((tmp / "web" / "data" / "day_top_pick.json").read_text())
    assert not got.get("pick"), got


def test_the_writer_is_still_silent_on_a_healthy_cycle():
    """It runs inside the build loop, and a warning printed every five
    minutes is a warning nobody reads. The NameError it carried for
    three commits reached production behind exactly such a line."""
    tmp = _paywalled_likely(below_bar="the price drifted past the band")
    out = _run(launch._write_day_top_pick, tmp)
    assert out.strip() == "", out


def test_both_potd_readers_resolve_through_board_source():
    """Pinned on the CALL as well as the behaviour, for the same reason
    `--why-empty` and `--why-many` are above: the failure is a path built
    by hand, and the next reader copied from either of these should copy
    the resolution with it."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    fn = src.split("def _write_day_top_pick", 1)[1].split("\ndef ", 1)[0]
    assert "board_source(ROOT / BOARD_FILES[sport])" in fn, fn[:400]
    rep = open(os.path.join(ROOT, "potd_report.py"), encoding="utf-8").read()
    paths = rep.split("def board_paths", 1)[1].split("\ndef ", 1)[0]
    assert "gate.board_source" in paths, paths[:400]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
