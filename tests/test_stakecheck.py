"""The staking audit, the defect that made it necessary, and the mistake
the audit itself made.

Ethan, 2026-08-08, reading the settled list on his phone: "We got .05
units back for a +100 bet. Our units per bet is too low or something
because that seems wrong."

HE WAS RIGHT, AND IT IS PROVABLE FROM ONE ROW. A +106 winner returning
+0.05u was staked 0.05/1.06 = 0.047u. `staking.MIN_STAKE_UNITS` is 0.1
and `to_units` floors every positive stake at it, so nothing in the
sizing path can emit 0.047. `correlation.apply_exposure_caps` was
multiplying stakes by a cap factor and re-rounding straight through the
floor. That bug is real, was found on a real main-category prop, and is
fixed.

THE CAP POLICY WENT THROUGH THREE VERSIONS IN ONE EVENING — per-game
proportional scaling, then trim-the-weakest, then one uniform factor with
the floor enforced by dropping. The last of those is the only one that
needs no ranking to be correct, which is why it is the one that stayed:
a uniform scale cannot move ROI, because net and staked move together.

AND THEN THE AUDIT'S OWN ERROR, which is the more useful lesson here.
`_rows` selected EVERY settled bet. It reported 2,582 and 888 across two
eras; the site's headline record is 292. The rest are measurement
buckets: `longshot` journals at a flat stake with zero dollar exposure,
`longshot_watch` is a calibration sample ledger.py calls "most of the
journal by volume and all of the noise in it". So three days of ROI
figures, a recommendation, and a shipped code change all described a
population that was mostly paper.

The tell was on screen the whole time: 1,787 of 2,582 bets priced at
+200 or longer is a home-run board, not a betting record. A second tell
was there too — the grade table summed to 446 of 888 rows, because it
iterated a hardcoded list of the grades I expected and silently dropped
the rest.

Both are guarded below. The empirical conclusions drawn before the fix
are void until re-measured; the arithmetic ones (a uniform factor is
ROI-neutral; 0.047 is below 0.1) never depended on the sample.

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
        "grade", "edge", "stake_units", "pnl_units", "status", "category",
        "projection", "line", "actual")


def _db(rows):
    """A throwaway ledger. Returns a path the caller must not keep."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, "
              + ", ".join(f"{k} {'REAL' if k in ('hit_prob','stake_units','pnl_units','edge','projection','line','actual') else 'INTEGER' if k == 'odds' else 'TEXT'}"
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
                category="main", projection=None, line=None, actual=None)
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


def test_the_exposure_caps_enforce_the_floor_they_scale_through():
    """Named so the next person finds it from the symptom. This is the
    only code between `to_units` and the journal that changes a stake.
    It may scale one — uniformly, which is ROI-neutral — but a stake that
    lands under the floor has to come OFF, not be rounded through it."""
    src = open(os.path.join(ROOT, "engine", "correlation.py"),
               encoding="utf-8").read()
    i = src.index("def apply_exposure_caps(")
    body = src[i:]
    assert "_uniform_factor(" in body, "the cap policy changed shape"
    assert "MIN_STAKE_UNITS" in body, (
        "the floor is not enforced here; a scaled stake can drop under it "
        "again, which is exactly what produced the 0.047u")


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


def test_the_grade_breakdown_prices_at_the_asked_for_stake_too():
    """THE COLUMN THE CAP DECISION TURNS ON. A trim harvests each grade at
    the stake the rules asked for, not the stake the old caps left behind,
    so ROI-as-staked cannot answer whether trimming that grade is a good
    idea. Both are printed; only the second is the trim's yield."""
    import contextlib
    import io
    rows = [_row(grade="A+", odds=-110, hit_prob=0.70, status="won",
                 pnl_units=0.23, stake_units=0.25),
            _row(grade="B+", odds=-110, hit_prob=0.56, status="lost",
                 pnl_units=-0.25, stake_units=0.25)]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    assert "IS THE GRADE PREDICTIVE?" in out
    assert "ROI at asked" in out and "ROI as staked" in out
    # Both grades present, each on its own line.
    assert any(l.strip().startswith("A+") for l in out.splitlines())
    assert any(l.strip().startswith("B+") for l in out.splitlines())


def test_a_grade_the_rules_would_not_size_shows_a_dash_not_a_zero():
    """A grade whose every bet lacks a hit_prob has no asked-for ROI. A
    printed 0.0% there reads as "this grade breaks even", which is a
    claim, and the honest output is that there is nothing to say."""
    import contextlib
    import io
    path = _db([_row(grade="A", hit_prob=None, status="won", pnl_units=0.05)])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    line = [l for l in buf.getvalue().splitlines() if l.strip().startswith("A ")]
    assert line and line[0].rstrip().endswith("—"), line


# --- the policy that replaced the trim --------------------------------------
def test_the_uniform_replay_preserves_every_ratio_it_keeps():
    """The property the live policy is chosen for, asserted on the replay
    so the two cannot drift apart. One factor across the slate cannot
    change the relationship between any two stakes."""
    rows = [_sim_row("A+", 0.09, 0.58, -110, "won"),      # 2.0u
            _sim_row("A", 0.09, 0.58, -110, "won")]       # 1.0u (grade cap)
    out = stakecheck.simulate_uniform(rows, cap=1.5)
    # 3.0u asked against 1.5u: factor 0.5, so 1.0u and 0.5u, both above
    # the floor, and the 2:1 relationship survives.
    assert out["kept"] == 2, out
    assert abs(out["staked"] - 1.5) < 1e-9, out["staked"]


def test_the_uniform_replay_drops_what_falls_under_the_floor():
    """The only thing that can move ROI in this policy, so it must be the
    only thing the replay does beyond scaling."""
    # Verified stakes: A+ at .58/-110 caps at 2.0u; a B+ at .525 is a
    # hairline edge that already floors at 0.1u before any scaling, so it
    # is the first thing a factor pushes through the floor. 60 A+ bets
    # put the slate 8x over, which is the shape the real board has.
    rows = ([_sim_row("A+", 0.09, 0.58, -110, "won")] * 60
            + [_sim_row("B+", 0.02, 0.525, -110, "lost")])
    out = stakecheck.simulate_uniform(rows, cap=15.0)
    assert out["dropped"] == 1, out
    assert out["kept"] == 60, out
    assert out["staked"] <= 15.0 + 1e-9


def test_the_uniform_replay_leaves_a_slate_inside_its_cap_untouched():
    rows = [_sim_row("A+", 0.09, 0.58, -110, "won")]      # 2.0u
    out = stakecheck.simulate_uniform(rows, cap=15.0)
    assert out["kept"] == 1 and out["dropped"] == 0
    assert abs(out["staked"] - 2.0) < 1e-9


def test_the_uniform_replay_does_not_select_on_the_outcome():
    """Same guard as the trim replay: flip every result, get the same
    survivors. A uniform scale has no way to see an outcome, and the
    floor drop reads only the stake — this proves neither started to."""
    base = [_sim_row("A+", 0.09, 0.58, -110, "won"),
            _sim_row("A", 0.06, 0.58, -110, "lost"),
            _sim_row("B+", 0.03, 0.60, -110, "won")]
    flipped = [dict(r, status=("lost" if r["status"] == "won" else "won"))
               for r in base]
    a = stakecheck.simulate_uniform(base, cap=2.0)
    b = stakecheck.simulate_uniform(flipped, cap=2.0)
    assert a["kept"] == b["kept"]
    assert abs(a["staked"] - b["staked"]) < 1e-9
    assert a["net"] != b["net"], "the outcomes did not reach the P&L at all"


def test_both_policies_are_reported_so_neither_is_taken_on_faith():
    """The trim was chosen, shipped, replayed, and replaced inside one
    evening. Printing both is how the next choice gets made on numbers
    rather than on whichever one is currently live."""
    import contextlib
    import io
    rows = [_row(grade="A+", odds=-110, hit_prob=0.70, status="won",
                 pnl_units=0.23, stake_units=0.25) for _ in range(30)]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    assert "uniform scale + floor drop" in out
    assert "trim the weakest" in out
    assert "as actually staked" in out


# --- the population, which is the thing I got wrong --------------------------
def test_only_real_money_counts_by_default():
    """THE ERROR THIS FILE EXISTS TO PREVENT REPEATING, made 2026-08-08
    and caught by Ethan's output rather than by me.

    The first version selected every settled row. It reported 2,582 and
    888 bets across two eras; the site's headline record is 292. The rest
    are measurement buckets — `longshot` journals at a flat stake with
    ZERO dollar exposure, and `longshot_watch` is a calibration sample
    that ledger.py itself calls "most of the journal by volume and all of
    the noise in it".

    So three days of ROI figures, a policy recommendation and a shipped
    code change all rested on a population that was mostly paper. The
    tell was on screen the whole time and I read past it: 1,787 of 2,582
    bets priced at +200 or longer is a home-run board, not a betting
    record."""
    rows = [_row(player="real", category="main", stake_units=0.25),
            _row(player="paper", category="longshot", stake_units=0.1),
            _row(player="noise", category="longshot_watch", stake_units=0.1)]
    path = _db(rows)
    try:
        got = stakecheck._rows(path, None, None)
        every = stakecheck._rows(path, None, None, measurement=True)
    finally:
        os.unlink(path)
    assert [r["player"] for r in got] == ["real"], got
    assert len(every) == 3


def test_the_default_matches_how_the_ledger_itself_scores_the_record():
    """Not a filter I invented. If ledger.py ever changes what counts,
    this test fails and the two are reconciled deliberately rather than
    drifting into two different truths about the same money."""
    led = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert "category='main' AND stake_units > 0" in led
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    assert "category='main' AND stake_units > 0" in src


def test_a_zero_stake_row_is_not_a_bet():
    """`stake_units > 0` is half the ledger's own definition. A row at
    zero stake moves the win-loss record and no money, so counting it
    drags every ROI toward nothing."""
    path = _db([_row(player="ghost", category="main", stake_units=0.0,
                     pnl_units=0.0, status="won"),
                _row(player="real", category="main", stake_units=0.25)])
    try:
        got = stakecheck._rows(path, None, None)
    finally:
        os.unlink(path)
    assert [r["player"] for r in got] == ["real"]


def test_the_sample_says_what_is_in_it_before_any_conclusion():
    """A census line at the top, unconditionally. The absence of one is
    exactly why the contamination survived three days of output — nothing
    on screen distinguished 3,470 rows from 292."""
    import contextlib
    import io
    path = _db([_row(player="real", category="main", stake_units=0.25)])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    assert "bucket(s): main 1" in buf.getvalue()


def test_including_measurement_buckets_says_so_loudly():
    """The flag exists for inspecting those buckets, which is legitimate.
    Reporting an ROI from them without a warning is not."""
    import contextlib
    import io
    path = _db([_row(player="real", category="main", stake_units=0.25),
                _row(player="paper", category="longshot", stake_units=0.1)])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None,
                                               measurement=True))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    assert "longshot 1" in out and "main 1" in out
    assert "Neither is money" in out


def test_the_grade_table_shows_every_grade_it_finds():
    """THE SECOND HALF OF THE SAME MISTAKE. The grade breakdown iterated
    a hardcoded list of the grades I expected, so 442 of 888 rows were
    silently absent and the column totals did not add up to the header —
    on screen, with nothing saying so.

    A report that omits what it did not anticipate is worse than one that
    crashes, because it looks complete."""
    import contextlib
    import io
    rows = [_row(player="a", grade="A+"), _row(player="b", grade="Watch"),
            _row(player="c", grade="C-"), _row(player="d", grade=None)]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    seen = out[out.index("IS THE GRADE PREDICTIVE?"):]
    for g in ("A+", "Watch", "C-", "?"):
        assert any(l.strip().startswith(g) for l in seen.splitlines()), \
            f"{g} is missing from the grade table"


def test_the_grade_table_accounts_for_every_bet():
    """The arithmetic that would have caught it without anyone noticing
    the missing names: the rows of the table must sum to the header."""
    import contextlib
    import io
    import re as _re
    rows = ([_row(player=f"a{i}", grade="A+") for i in range(3)]
            + [_row(player=f"z{i}", grade="Watch") for i in range(7)])
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    seen = buf.getvalue()
    seen = seen[seen.index("IS THE GRADE PREDICTIVE?"):]
    counts = [int(m.group(1)) for m in
              _re.finditer(r"^\s+\S+\s+(\d+)\s+\d+\.\d%", seen, _re.M)]
    assert sum(counts) == 10, (counts, seen)


# --- claimed against realized ------------------------------------------------
def test_the_calibration_line_compares_the_claim_to_the_outcome():
    """THE MEASUREMENT EVERYTHING ELSE WAS CIRCLING. Every other section
    asks how the money was distributed; this asks whether there was an
    edge to distribute.

    It became the point on 2026-08-09, when the real 292-bet record came
    back ordered flat > as-staked > asked-for. Sizing MORE per the rules
    lost more. That ordering is the signature of overconfidence: Kelly
    stakes in proportion to claimed edge, so an inflated claim gets a
    bigger stake on a bigger error."""
    import contextlib
    import io
    rows = ([_row(player=f"w{i}", hit_prob=0.60, status="won",
                  pnl_units=0.25) for i in range(4)]
            + [_row(player=f"l{i}", hit_prob=0.60, status="lost",
                    pnl_units=-0.25) for i in range(6)])
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    out = buf.getvalue()
    assert "CLAIMED vs REALIZED" in out
    line = [l for l in out.splitlines() if "every bet" in l][0]
    assert "60.0%" in line, line          # claimed
    assert "40.0%" in line, line          # realized 4/10
    assert "-20.0%" in line, line         # the gap, signed


def test_the_calibration_line_carries_its_own_noise_figure():
    """A gap without a standard error invites reading ten bets as a
    finding. On this record the current era is 95 bets, where one SE on a
    hit rate is about five points — most gaps that look damning are not."""
    import contextlib
    import io
    rows = [_row(player=f"w{i}", hit_prob=0.5,
                 status=("won" if i % 2 else "lost"),
                 pnl_units=0.1) for i in range(4)]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    line = [l for l in buf.getvalue().splitlines() if "every bet" in l][0]
    assert "±" in line, line
    # 4 bets at 50%: sqrt(.25/4) = 25.0%
    assert "25.0%" in line, line


def test_a_bet_with_no_claimed_probability_is_left_out_of_calibration():
    """Averaging a missing claim as zero would manufacture a gap the
    model never had."""
    import contextlib
    import io
    rows = [_row(player="has", hit_prob=0.6, status="won", pnl_units=0.25),
            _row(player="none", hit_prob=None, status="lost")]
    path = _db(rows)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    line = [l for l in buf.getvalue().splitlines() if "every bet" in l][0]
    assert line.split()[2] == "1", line   # one bet, not two


# --- fitting the overconfidence ----------------------------------------------
def _bias_db(bias=-0.10, n_old=197, n_new=95, seed=11):
    """A ledger with a KNOWN bias, so the fitter is checked against an
    answer rather than against a hope. A fitter that always reports an
    improvement is not a measurement."""
    import random
    rng = random.Random(seed)
    rows = []
    for label, d, n in (("old", "2026-07-28", n_old), ("new", "2026-08-06", n_new)):
        for i in range(n):
            claimed = rng.uniform(0.45, 0.70)
            o = rng.choice([-110, -120, 105, 130])
            dec = (1 + o / 100) if o > 0 else (1 + 100 / -o)
            won = rng.random() < claimed + bias
            rows.append(_row(date=d, player=f"{label}{i}", odds=o,
                             hit_prob=claimed, stake_units=0.3,
                             pnl_units=((dec - 1) * 0.3 if won else -0.3),
                             status="won" if won else "lost"))
    return _db(rows)


def _fit_out(path):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stakecheck.fit_report(stakecheck._rows(path, None, None))
    return buf.getvalue()


def test_the_fit_recovers_a_bias_it_was_not_told_about():
    """Ten points of overconfidence planted in the data; the correction is
    fitted on one era and the gap measured on the other. If the held-out
    gap does not close, the fitter is decoration."""
    path = _bias_db(bias=-0.10)
    try:
        out = _fit_out(path)
    finally:
        os.unlink(path)
    import re as _re
    line = [l for l in out.splitlines() if l.strip().startswith("gap")][0]
    before, after = [float(x) for x in _re.findall(r"([-+]\d+\.\d)%", line)]
    assert before < -8.0, line
    assert abs(after) < abs(before) / 2, f"the gap barely moved: {line}"


def test_the_fit_is_trained_and_tested_on_different_bets():
    """A correction fitted and scored on the same rows always looks like
    it worked. The eras never overlap — asserted on the source, because
    getting this wrong produces a number that is confidently meaningless."""
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    i = src.index("def fit_report(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert '< RESCALE_DAY' in body and '>= RESCALE_DAY' in body
    assert body.index("fit_correction(pairs") > body.index("train = [")
    # and the pairs handed to the fitter come from train, never test
    j = body.index("fit_correction(pairs")
    assert "pairs = [" in body[:j]
    assert "for r in train" in body[:j]


def test_the_fit_leaves_clean_data_alone():
    """A model claiming exactly what it delivers must not be 'corrected'.
    A fitter that finds a bias in unbiased data would send us chasing an
    artefact of its own search grid."""
    path = _bias_db(bias=0.0, seed=5)
    try:
        out = _fit_out(path)
    finally:
        os.unlink(path)
    import re as _re
    line = [l for l in out.splitlines() if l.strip().startswith("gap")][0]
    before, after = [float(x) for x in _re.findall(r"([-+]\d+\.\d)%", line)]
    assert abs(before) < 8.0, f"the planted data is not actually clean: {line}"


def test_the_fit_describes_the_correction_it_found():
    """The first version printed "temperature above 1 shrinks toward 50%"
    unconditionally. A constant bias is absorbed by the INTERCEPT and can
    leave the temperature below 1, so that line described the opposite of
    what had been fitted half the time."""
    path = _bias_db(bias=-0.10)
    try:
        out = _fit_out(path)
    finally:
        os.unlink(path)
    assert "temperature" in out and "intercept" in out
    # The wording must follow the sign, not a fixed sentence.
    assert ("moved DOWN" in out) or ("moved up" in out) or \
           ("no systematic shift" in out)


def test_the_fit_refuses_a_sample_too_small_to_mean_anything():
    path = _bias_db(bias=-0.10, n_old=10, n_new=5)
    try:
        out = _fit_out(path)
    finally:
        os.unlink(path)
    assert "Nothing fitted" in out


def test_the_fit_writes_nothing():
    """It is pointed at the money file and at the calibration store, and
    must touch neither. Applying a correction is a separate, deliberate
    act."""
    body = _code_only("fit_report")
    for verb in ("save", "write", "store", "set_"):
        assert verb not in body, f"fit_report calls {verb}"


def _code_only(func_name):
    """A function's CODE, with its docstring removed.

    Third time this trap has fired in this session. `spread_report`'s
    docstring says "using only columns the journal already stores", and a
    scan for the word "store" matched the explanation rather than a call.
    Scan the thing meant, never the prose about it."""
    import re as _re
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    i = src.index(f"def {func_name}(")
    body = src[i:src.index("\ndef ", i + 10)]
    return _re.sub(r'""".*?"""', "", body, flags=_re.S)


# --- is the spread too narrow? -----------------------------------------------
def _spread_db(model_sd, true_sd, n=300, seed=4):
    """A ledger where the model's spread and reality's are both KNOWN.
    The check has to tell them apart or it is not a check."""
    import random
    from statistics import NormalDist
    nd = NormalDist()
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        mu = rng.uniform(1.0, 2.0)
        line = mu + rng.choice([-0.4, -0.25, 0.25, 0.4])
        p = 1 - nd.cdf((line - mu) / model_sd)
        act = rng.gauss(mu, true_sd)
        won = act > line
        rows.append(_row(player=f"P{i}", market="total_bases", side="OVER",
                         odds=-110, hit_prob=p, projection=mu, line=line,
                         actual=act, status="won" if won else "lost",
                         pnl_units=0.27 if won else -0.3))
    return _db(rows)


def _spread_ratio(path):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stakecheck.spread_report(stakecheck._rows(path, None, None))
    line = [l for l in buf.getvalue().splitlines() if l.strip().startswith("ALL")]
    assert line, buf.getvalue()
    return float(line[0].split()[-1])


def test_an_honest_spread_reads_near_one():
    """A model whose distribution is right must not be accused of being
    too narrow. A check that always finds a defect finds nothing."""
    path = _spread_db(model_sd=0.9, true_sd=0.9)
    try:
        assert 0.85 <= _spread_ratio(path) <= 1.15
    finally:
        os.unlink(path)


def test_a_narrow_spread_is_caught_and_roughly_quantified():
    """Model believes 0.6, reality is 0.9 — a ratio of 1.5. The check
    should land near it, and the ratio is the temperature that would be
    needed to cover for the defect rather than fix it."""
    path = _spread_db(model_sd=0.6, true_sd=0.9)
    try:
        r = _spread_ratio(path)
    finally:
        os.unlink(path)
    assert 1.25 <= r <= 1.75, r


def test_a_too_wide_spread_is_caught_the_other_way():
    """The failure has two directions and only one of them is the one we
    suspect. A check that can only detect the expected answer is a
    thermometer that reads the same in every room."""
    path = _spread_db(model_sd=1.3, true_sd=0.9)
    try:
        r = _spread_ratio(path)
    finally:
        os.unlink(path)
    assert r < 0.9, r


def test_a_bet_sitting_on_its_own_line_is_dropped():
    """Backing a spread out of a probability divides by a z-score. At the
    line that z is ~0 and the implied sigma explodes, so one coin-flip
    bet could dominate a market's average."""
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    i = src.index("def spread_report(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "abs(z) <" in body, "no guard on a near-zero z-score"


def test_the_side_decides_which_tail_is_inverted():
    """hit_prob is the probability the BET hits, not the probability of
    going over. Inverting an UNDER with the OVER's formula flips the sign
    of the implied sigma and the row is silently discarded — losing every
    UNDER in the book from the measurement."""
    src = open(os.path.join(ROOT, "stakecheck.py"), encoding="utf-8").read()
    i = src.index("def spread_report(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert 'side == "OVER"' in body
    assert "inv_cdf(1 - float(p))" in body and "inv_cdf(float(p))" in body


def test_a_ledger_without_projections_says_so_rather_than_dividing_by_zero():
    path = _db([_row(player="x")])          # projection/line/actual all None
    import contextlib
    import io
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            stakecheck.spread_report(stakecheck._rows(path, None, None))
    finally:
        os.unlink(path)
    assert "nothing to check" in buf.getvalue()


def test_the_spread_check_writes_nothing():
    body = _code_only("spread_report")
    for verb in ("save", "write", "store", "set_"):
        assert verb not in body, f"spread_report calls {verb}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
