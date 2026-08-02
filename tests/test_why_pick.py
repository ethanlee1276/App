"""Tracing ONE pick from the board to the Live tab.

"we also definitely still have props recommended from earlier that are live
right now but not showing on the live page. Carter Jensen over 1.5 total
bases is live but not showing"

--why-live could not answer this, because it only sees the JOURNAL. It
reported 56 open bets and Carter Jensen was not among them — so the
question was never "why isn't this journal row on the Live tab" but "why is
a pick shown on the board missing from the journal entirely".

Those are two different failures wearing one symptom, and I spent three
rounds reading code guessing between exposure caps, the Kelly floor and
build lag instead of making the app say which.

The gate that produces it: a prop can be `recommended: true` on the board
and still be skipped by log_recommendations — most often because Kelly
sized it at 0.00u. It then exists nowhere downstream. No journal row, no
Record entry, nothing on the Live tab while its game runs. The board says
"pick" and every other surface disagrees.

So the four skip conditions moved out of the loop into
``journal_skip_reason``, which the loop now calls. The report and the
behaviour cannot drift, which is the failure --why-empty had when its bar
said 0.3pt and the engine's said 1.0pt.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ledger import journal_skip_reason

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "web", "data", "mlb_recommendations.json")
SRC = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


# --- the predicate ----------------------------------------------------------
def test_a_staked_recommended_prop_is_journaled():
    assert journal_skip_reason(
        {"recommended": True, "stake_units": 1.0, "market": "hits"}) is None


def test_a_zero_stake_pick_is_named_as_the_reason():
    r = journal_skip_reason(
        {"recommended": True, "stake_units": 0.0, "market": "hits"})
    assert r and "0.00u" in r


def test_a_proxy_priced_pick_is_named():
    r = journal_skip_reason({"recommended": True, "stake_units": 1.0,
                             "market": "hits", "has_market": False})
    assert r and "no real book price" in r


def test_a_long_shot_is_named_as_routed_not_dropped():
    r = journal_skip_reason({"recommended": True, "stake_units": 1.0,
                             "market": "home_runs"})
    assert r and "own bucket" in r


def test_the_loop_uses_the_same_predicate_it_reports():
    """--why-empty's bar said 0.3pt while the engine used 1.0pt, and the
    funnel blamed an innocent gate for the difference. One predicate."""
    led = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    i = led.index("def log_recommendations(")
    block = led[i:i + 2000]
    assert "if journal_skip_reason(r, only_recommended):" in block
    assert 'if r.get("has_market") is False:' not in block, \
        "the loop still has its own inline copy of a gate"


# --- which skips actually strand a bet --------------------------------------
def test_only_a_zero_stake_or_proxy_price_strands_a_pick():
    from launch import _goes_nowhere
    assert _goes_nowhere(journal_skip_reason(
        {"recommended": True, "stake_units": 0.0, "market": "hits"}))
    assert _goes_nowhere(journal_skip_reason(
        {"recommended": True, "stake_units": 1.0, "market": "hits",
         "has_market": False}))


def test_a_long_shot_is_not_reported_as_stranded():
    """It is filed by log_longshots. The first version of this report said
    "the journal has no row for it" about a bet sitting in the journal two
    lines below its own output."""
    from launch import _goes_nowhere
    assert not _goes_nowhere(journal_skip_reason(
        {"recommended": True, "stake_units": 1.0, "market": "home_runs"}))


def test_a_non_recommended_prop_is_not_reported_as_stranded():
    from launch import _goes_nowhere
    assert not _goes_nowhere(journal_skip_reason(
        {"recommended": False, "grade": "Pass", "stake_units": 0.0,
         "market": "hits"}))


# --- end to end -------------------------------------------------------------
def _with_board(extra_rec):
    """Run --why-pick against a board carrying one injected row, then put
    the real board back."""
    backup = tempfile.mktemp(suffix=".json")
    shutil.copy(BOARD, backup)
    try:
        d = json.loads(open(BOARD, encoding="utf-8").read())
        d["recommendations"].append(extra_rec)
        open(BOARD, "w", encoding="utf-8").write(json.dumps(d))
        p = subprocess.run([sys.executable, "launch.py", "--why-pick",
                            extra_rec["player"]], cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-400:]
        return p.stdout
    finally:
        shutil.copy(backup, BOARD)
        os.unlink(backup)


def test_the_reported_case_is_reproduced_and_explained():
    """Recommended, real price, ordinary market, zero stake — the exact
    shape of the symptom."""
    out = _with_board({
        "player": "Carter Jensen", "team": "KC", "opponent": "DET",
        "market": "total_bases", "market_label": "Total Bases",
        "side": "OVER", "line": 1.5, "odds": -115, "grade": "A",
        "confidence": 8.1, "edge": 0.041, "stake_units": 0.0,
        "recommended": True, "has_market": True})
    assert "recommended on the board: True" in out
    assert "stake is 0.00u" in out
    assert "THIS IS THE GAP" in out


def test_a_properly_staked_pick_does_not_trigger_the_warning():
    """The control. Otherwise the test above only proves the string can be
    printed."""
    out = _with_board({
        "player": "Carter Jensen", "team": "KC", "opponent": "DET",
        "market": "total_bases", "market_label": "Total Bases",
        "side": "OVER", "line": 1.5, "odds": -115, "grade": "A",
        "confidence": 8.1, "edge": 0.041, "stake_units": 0.9,
        "recommended": True, "has_market": True})
    assert "passes every journal gate" in out
    assert "THIS IS THE GAP" not in out


def test_an_unknown_name_says_so_rather_than_reporting_nothing():
    p = subprocess.run([sys.executable, "launch.py", "--why-pick",
                        "Nobody At All"], cwd=ROOT, capture_output=True,
                       text=True, timeout=300)
    assert p.returncode == 0
    assert "NOT ON THE BUILT BOARD" in p.stdout
    assert "spelled differently" in p.stdout


def test_it_never_writes_to_the_journal():
    i = SRC.index("def why_pick(")
    block = SRC[i:SRC.index("def _near_dates(")]
    for verb in ("INSERT", "UPDATE", "DELETE", "commit()"):
        assert verb not in block, f"why_pick performs a {verb}"


def test_it_is_wired_to_a_flag():
    assert 'if "--why-pick" in argv:' in SRC
    assert "why_pick(who, sport)" in SRC


# --- a settled bet is not a missing bet -------------------------------------
def test_a_settled_bet_is_reported_as_settled_not_sent_hunting():
    """Ethan's real trace ended with:

        journal: main · 2026-08-01 · won · 0.11u
        ✗ not on the Live tab — run `--why-live` for the mapping reason.

    There was nothing to map. The Live tab holds OPEN bets, the bet had
    graded, and it left by design. Telling someone to hunt a mapping bug
    for a bet that simply won is the same confidently-wrong answer this
    whole family of reports exists to stop producing."""
    import io, contextlib
    from launch import _live_status
    rows = [{"date": "2026-08-01", "category": "main", "status": "won",
             "stake_units": 0.11}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _live_status([], "total_bases", rows)
    out = buf.getvalue()
    assert "SETTLED (won)" in out
    assert "why-live" not in out


def test_an_open_unmapped_bet_still_points_at_the_mapping_report():
    """The control: the ONE case where --why-live is the right next step
    must still say so."""
    import io, contextlib
    from launch import _live_status
    rows = [{"date": "2026-08-01", "category": "main", "status": "open",
             "stake_units": 1.0}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _live_status([], "total_bases", rows)
    assert "why-live" in buf.getvalue()


def test_a_bet_on_the_live_tab_says_so_before_anything_else():
    import io, contextlib
    from launch import _live_status
    live = [{"market": "total_bases", "status": "cleared", "phase": "live"}]
    rows = [{"date": "2026-08-01", "category": "main", "status": "open",
             "stake_units": 1.0}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _live_status(live, "total_bases", rows)
    out = buf.getvalue()
    assert "ON THE LIVE TAB" in out and "cleared" in out


def test_both_report_paths_share_one_verdict_function():
    """The skip path and the passes-every-gate path each printed their own
    version, and only one of them knew about settled bets."""
    assert SRC.count("_live_status(live, mkt, rows)") == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
