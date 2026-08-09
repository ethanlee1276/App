"""The staking audit, and the defect that made it necessary.

Ethan, 2026-08-08, reading the settled list on his phone: "We got .05
units back for a +100 bet. Our units per bet is too low or something
because that seems wrong."

HE WAS RIGHT, AND IT IS PROVABLE FROM ONE ROW. A +106 winner returning
+0.05u was staked 0.05/1.06 = 0.047u. `staking.MIN_STAKE_UNITS` is 0.1
and `to_units` floors every positive stake at it, so nothing in the
sizing path can emit 0.047. Something downstream of the floor shrinks
stakes, and it is `correlation.apply_exposure_caps`, which multiplied
stakes by a scaling factor and re-rounded without re-flooring. FIXED the
same day, to Ethan's call: over the cap now drops the weakest bets until
the rest fit at full size. The audit stays, because the settled history
was made under the old rule and is not restated.

THE SECOND HALF, from the history rather than the arithmetic:
GAME_CAP_U and SLATE_CAP_U were set on 2026-07-29 (commit 9a846b6),
when a unit was 1/20th of the bankroll. The unit scale was multiplied
by five on 2026-08-04 (commit 3f86208, "One scale for every stake"),
and the caps were not re-derived. Every stake got five times bigger
against a ceiling that did not move, so a cap built for the extreme
slate started catching the ordinary one. The caps themselves were left
alone — at the current scale 15u is 15% of bankroll on one night, which
is a defensible ceiling; it was the 75% it implied under the old scale
that was absurd. What changed is what happens when the ceiling is hit.

WHAT THIS FILE DOES NOT CLAIM. It does not assert that this explains
the -16.6% ROI. That is measurable and has not been measured: the
container this was written in carries a five-row stub ledger, not the
292-bet real one. `stakecheck.py` exists precisely so the question is
answered with Ethan's data instead of my inference, and the assertions
below are about the tool being arithmetically sound.

Run directly: `python3 tests/test_stakecheck.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import stakecheck
from engine.staking import MIN_STAKE_UNITS, to_units, kelly_units


COLS = ("date", "sport", "player", "market", "side", "odds", "hit_prob",
        "grade", "edge", "stake_units", "pnl_units", "status", "category")


def _db(rows):
    """A throwaway ledger. Returns a path the caller must not keep."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, "
              + ", ".join(f"{k} {'REAL' if k in ('hit_prob','stake_units','pnl_units','edge') else 'INTEGER' if k == 'odds' else 'TEXT'}"
                          for k in COLS) + ")")
    c.executemany(f"INSERT INTO bets ({','.join(COLS)}) VALUES "
                  f"({','.join('?' * len(COLS))})", rows)
    c.commit()
    c.close()
    return path


def _row(**kw):
    base = dict(date="2026-08-08", sport="mlb", player="X", market="hits",
                side="OVER", odds=106, hit_prob=0.52, grade="A", edge=0.05,
                stake_units=0.25, pnl_units=-0.25, status="lost",
                category="main")
    base.update(kw)
    return tuple(base[k] for k in COLS)


# --- the defect itself -------------------------------------------------------
def test_the_sizing_path_cannot_produce_the_stake_that_shipped():
    """THE PROOF, in two lines. Ask the sizing module for the smallest
    positive stake it will ever emit, and compare it to the stake the
    ledger actually carries. 0.047 is below the floor, so the floor was
    not the last thing to touch that number."""
    assert to_units(0.0000001, 106) == MIN_STAKE_UNITS
    assert kelly_units(0.501, 106) in (0.0, MIN_STAKE_UNITS) or \
        kelly_units(0.501, 106) >= MIN_STAKE_UNITS
    assert 0.047 < MIN_STAKE_UNITS


def test_the_exposure_caps_no_longer_scale_stakes():
    """Named so the next person finds it from the symptom. This is the
    only code between `to_units` and the journal that changes a stake,
    and it must not shrink one below the floor again."""
    src = open(os.path.join(ROOT, "engine", "correlation.py"),
               encoding="utf-8").read()
    i = src.index("def apply_exposure_caps(")
    body = src[i:]
    assert 'r["stake_units"] * factor' not in body, \
        "proportional scaling is back — that is what produced the 0.047u"
    assert "_trim(" in body, "the cap no longer trims"


def test_the_caps_predate_the_scale_change():
    """Not archaeology — the reason the cap binds on ordinary slates. If
    someone re-derives the caps for the current scale, these constants
    change and this test should be revisited deliberately."""
    from engine import correlation
    assert correlation.GAME_CAP_U == 5.0
    assert correlation.SLATE_CAP_U == 15.0
    from engine.staking import BANKROLL_UNITS
    assert BANKROLL_UNITS == 100.0, \
        "the unit scale moved again; the caps are stated in units"


# --- the tool ---------------------------------------------------------------
def test_it_never_writes_to_the_ledger():
    """It is pointed at the file the money lives in. It opens read-only
    and the mode is not decoration — a diagnostic that can corrupt its
    own subject is not a diagnostic."""
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    assert "mode=ro" in src and "uri=True" in src
    for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "conn.commit"):
        assert verb not in src, f"{verb} in a read-only tool"


def test_the_flat_control_pays_the_real_price():
    """The control is "same bets at 1u", not "same bets at even money" —
    a +180 winner returns 1.8u, and treating every win as 1.0u would
    understate the flat line and make the sizing look worse than it is."""
    net, staked = stakecheck._flat([
        {"status": "won", "odds": 180}, {"status": "lost", "odds": -110}])
    assert abs(net - 0.8) < 1e-9, net
    assert staked == 2.0


def test_the_flat_control_counts_a_loss_as_one_unit_not_the_price():
    """At -215 you risk 2.15 to win 1. Flat-staked means the STAKE is
    flat, so the loss is 1u; charging 2.15 would invent a bankroll rule
    the comparison is supposed to be free of."""
    net, staked = stakecheck._flat([{"status": "lost", "odds": -215}])
    assert net == -1.0 and staked == 1.0


def test_the_intended_stake_is_recomputed_not_guessed():
    """The whole tool rests on this: hit_prob and odds are both stored,
    so quarter-Kelly can be replayed exactly rather than estimated."""
    r = {"hit_prob": 0.60, "odds": 106, "grade": "A"}
    assert stakecheck.intended_stake(r) == kelly_units(0.60, 106, 0.25, 1.0)


def test_a_row_with_no_model_probability_is_skipped_not_invented():
    """An old bet with no hit_prob cannot be re-derived. Substituting the
    implied probability would make every such row show zero edge and zero
    intended stake, which reads as a finding and is an artefact."""
    assert stakecheck.intended_stake({"hit_prob": None, "odds": 106}) is None
    assert stakecheck.intended_stake({"hit_prob": 0.5, "odds": None}) is None


def test_the_grade_cap_is_honoured_in_the_replay():
    """A B+ bet cannot be staked past 0.5u however good Kelly thinks it
    is. Replaying without the cap would report a shortfall that the rules
    never asked for."""
    hot = {"hit_prob": 0.80, "odds": 200, "grade": "B+"}
    assert stakecheck.intended_stake(hot) <= 0.5


def test_the_price_cap_is_honoured_in_the_replay():
    """+200 and longer is dime territory whatever the model thinks — the
    receipts on home-run overs are why. Ignoring it in the replay would
    invent a shortfall on exactly the bets we deliberately keep small."""
    assert stakecheck.intended_stake(
        {"hit_prob": 0.80, "odds": 250, "grade": "A+"}) == 0.1


def test_the_eras_are_reported_apart():
    """Stakes before 2026-08-04 were sized on a 20-unit bankroll. Mixing
    them into one ROI compares two different rulers and answers nothing;
    restating them would be inventing a history we did not bet."""
    assert stakecheck.RESCALE_DAY == "2026-08-04"
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    assert "< RESCALE_DAY" in src and ">= RESCALE_DAY" in src


def test_it_runs_end_to_end_and_finds_the_sub_floor_stakes(capsys=None):
    import io
    import contextlib
    rows = [
        _row(player="Wells", odds=106, stake_units=0.047, pnl_units=0.05,
             status="won"),
        _row(player="Wells2", odds=105, stake_units=0.0857, pnl_units=0.09,
             status="won"),
        _row(player="Cole", odds=129, stake_units=0.24, pnl_units=-0.24),
        _row(player="BOS", odds=-215, stake_units=0.50, pnl_units=-0.50),
    ]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    assert "2 settled bet(s) staked under the documented minimum" in out, out
    assert "0.047u" in out
    assert "AS STAKED" in out and "AT FLAT 1u" in out


def test_an_empty_ledger_says_so_rather_than_dividing_by_zero():
    path = _db([])
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    assert "Nothing to measure" in buf.getvalue()


def test_open_bets_are_not_measured():
    """An unsettled bet has no pnl. Counting it as a zero would drag every
    ROI toward nothing."""
    path = _db([_row(status="open", pnl_units=None),
                _row(player="done", status="won", pnl_units=0.05)])
    try:
        got = stakecheck._rows(path, None, None)
    finally:
        os.unlink(path)
    assert len(got) == 1 and got[0]["player"] == "done"


# --- replaying the rule that shipped ----------------------------------------
def _sim_row(grade, edge, p, odds, status):
    return {"sport": "mlb", "date": "2026-08-08", "grade": grade,
            "edge": edge, "hit_prob": p, "odds": odds, "status": status}


def test_the_replay_keeps_the_strongest_bets_first():
    """The entire claim of trimming is that the model's own ranking picks
    a better subset than crowding does. If the replay kept them in ledger
    order it would be measuring nothing."""
    # Verified stakes: A+ at .58/-110 caps at 2.0u, B+ at .60/-110 at 0.5u.
    rows = [_sim_row("B+", 0.02, 0.60, -110, "lost"),
            _sim_row("A+", 0.09, 0.58, -110, "won")]
    out = stakecheck.simulate_trim(rows, cap=2.0)
    assert out["kept"] == 1 and out["dropped"] == 1, out
    assert out["net"] > 0, "it kept the B+ loser over the A+ winner"


def test_the_replay_never_exceeds_the_cap():
    rows = [_sim_row("A", 0.08, 0.62, -110, "won") for _ in range(40)]
    out = stakecheck.simulate_trim(rows, cap=15.0)
    assert out["staked"] <= 15.0 + 1e-9, out["staked"]
    assert out["dropped"] > 0, "a 40-bet slate did not exceed 15u"


def test_the_replay_does_not_select_on_the_outcome():
    """THE PROPERTY THAT MAKES IT A BACKTEST RATHER THAN A STORY. Flip
    every result and the same bets must be kept — the ranking is the
    pre-game grade and edge, and neither knows what happened."""
    base = [_sim_row("A+", 0.09, 0.58, -110, "won"),
            _sim_row("A", 0.06, 0.58, -110, "lost"),
            _sim_row("B+", 0.03, 0.60, -110, "won")]
    flipped = [dict(r, status=("lost" if r["status"] == "won" else "won"))
               for r in base]
    a = stakecheck.simulate_trim(base, cap=3.0)
    b = stakecheck.simulate_trim(flipped, cap=3.0)
    assert a["kept"] == b["kept"] and a["staked"] == b["staked"]
    assert a["net"] != b["net"], "the outcomes did not reach the P&L at all"


def test_each_slate_gets_its_own_budget():
    """The cap is per slate. Pooling two nights into one budget would
    drop a whole night's bets to fund the other."""
    two = ([dict(_sim_row("A", 0.08, 0.62, -110, "won"), date="2026-08-07")
            for _ in range(30)]
           + [dict(_sim_row("A", 0.08, 0.62, -110, "won"), date="2026-08-08")
              for _ in range(30)])
    out = stakecheck.simulate_trim(two, cap=15.0)
    assert out["slates"] == 2
    assert out["staked"] <= 30.0 + 1e-9 and out["staked"] > 15.0


def test_sports_are_separate_slates():
    """`apply_exposure_caps` runs once per pipeline, so an MLB night and
    a WNBA night each get their own 15u, exactly as they do live."""
    mixed = ([_sim_row("A", 0.08, 0.62, -110, "won") for _ in range(30)]
             + [dict(_sim_row("A", 0.08, 0.62, -110, "won"), sport="wnba")
                for _ in range(30)])
    assert stakecheck.simulate_trim(mixed, cap=15.0)["slates"] == 2


def test_a_bet_the_rules_would_not_size_is_not_replayed():
    """No hit_prob means no intended stake. Treating it as zero-stake and
    keeping it would inflate the kept count with bets carrying no money."""
    rows = [_sim_row("A", 0.08, None, -110, "won"),
            _sim_row("A", 0.08, 0.62, -110, "won")]
    assert stakecheck.simulate_trim(rows, cap=15.0)["kept"] == 1


def test_the_replay_is_honest_about_the_cap_it_cannot_simulate():
    """The 5u per-game cap needs to know which bets shared a fixture and
    the journal does not store one. Claiming to model it would overstate
    how many bets survive."""
    doc = stakecheck.simulate_trim.__doc__
    assert "game" in doc and "not a forecast" in doc


def test_the_replay_stops_at_the_budget_rather_than_packing_it():
    """It must model the rule that shipped, which drops from the weakest
    end until the total fits — so the survivors are the strongest PREFIX.
    Skipping a bet that does not fit and taking smaller, weaker ones
    behind it would fill the budget more efficiently and simulate a rule
    that is not in the code."""
    rows = [_sim_row("A+", 0.09, 0.58, -110, "won"),     # 2.0u
            _sim_row("B+", 0.03, 0.60, -110, "won")]     # 0.5u
    out = stakecheck.simulate_trim(rows, cap=1.0)
    assert out["kept"] == 0, "it packed the budget with the weaker bet"
    assert out["dropped"] == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
