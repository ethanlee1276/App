"""capture_lag: WHEN a bet was logged, as a mined dimension — every sport.

The triage bench drafted it and ranked it cheapest: the whole intraday
cascade (weather, lineups, scratches, the books' hardest repricing window)
lands between an early log and first pitch, and the journal's single
'same-day' horizon value could not see any of it. Every board's games
carry kickoffs off the odds events, so the clock is derived once, in
log_recommendations, for mlb, nba, wnba, nfl, cfb and ufc alike.

Alongside it: the restated record — the same graded picks re-sized on
today's staking scale, answering "what would the ROI read" without ever
editing a settled row.
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import losspatterns as lp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the band ----------------------------------------------------------------

def _flat(s):
    """Normalise the apostrophe so a copy guard checks words, not glyphs.

    The site's prose uses U+2019; a test that hardcodes either form breaks
    on the next pass through the copy in whichever direction it went."""
    return s.replace("\u2019", "'")


def test_the_lead_bands_cover_the_cascade():
    assert lp.lead_band(-5) == "after start"
    assert lp.lead_band(0) == "after start"
    assert lp.lead_band(15) == "<30m out"
    assert lp.lead_band(45) == "30-90m out"
    assert lp.lead_band(120) == "90m-3h out"
    assert lp.lead_band(240) == "3-6h out"
    assert lp.lead_band(900) == "6h+ out"
    assert lp.lead_band(None) is None
    assert lp.lead_band("garbage") is None


def test_minutes_until_reads_iso_and_refuses_bare_clocks():
    now = datetime.datetime(2026, 8, 4, 20, 0, 0)
    m = lp.minutes_until("2026-08-04T23:10:00Z", now=now)
    assert m == 190.0
    # A bare local clock has no date — guessing one would band bets into
    # the wrong pocket. (The NFL sample slate really carries "13:00".)
    assert lp.minutes_until("13:00", now=now) is None
    assert lp.minutes_until("", now=now) is None
    assert lp.minutes_until(None, now=now) is None


# --- the journal -------------------------------------------------------------
def _log_one(sport="mlb", kickoff="2099-01-01T23:10:00Z", on_rec=False):
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    rec = {"player": "Test Bat", "market": "hits", "side": "OVER",
           "line": 1.5, "odds": -110, "grade": "A", "stake_units": 1.0,
           "hit_prob": 0.57, "edge": 0.04, "confidence": 8.0,
           "recommended": True, "team": "NYY", "opponent": "BOS"}
    result = {"sport": sport, "date": "2099-01-01",
              "recommendations": [rec],
              "games": [{"home": "NYY", "away": "BOS", "kickoff": kickoff}]}
    if on_rec:
        rec["kickoff"] = kickoff
        result["games"] = []
    ledger.log_recommendations(conn, result)
    return conn


def test_a_journaled_bet_carries_its_lead_time():
    conn = _log_one()
    lead = conn.execute("SELECT lead_min FROM bets").fetchone()[0]
    assert lead is not None and lead > 0


def test_the_recs_own_clock_wins_and_absence_is_null_not_a_guess():
    conn = _log_one(on_rec=True)
    assert conn.execute("SELECT lead_min FROM bets").fetchone()[0] > 0
    conn2 = _log_one(kickoff="")
    assert conn2.execute("SELECT lead_min FROM bets").fetchone()[0] is None


def test_every_sports_journal_path_derives_the_same_clock():
    """One derivation site, all six sports — the kickoff map is built from
    the result's games regardless of which board produced it."""
    for sport in ("mlb", "nfl", "cfb", "nba", "wnba", "ufc"):
        conn = _log_one(sport=sport)
        lead = conn.execute("SELECT lead_min FROM bets").fetchone()[0]
        assert lead is not None, sport


def test_longshots_carry_the_clock_too():
    """Home runs are the volume AND the self-closed market — the dimension
    matters most exactly there."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_longshots(conn, {"sport": "mlb", "date": "2099-01-01",
                                "long_shots": [{
                                    "player": "Slugger", "market": "home_runs",
                                    "odds": 350, "book": "dk",
                                    "model_prob": 0.24, "grade": "Play",
                                    "game_kickoff": "2099-01-01T23:10:00Z"}]})
    assert conn.execute("SELECT lead_min FROM bets").fetchone()[0] > 0


# --- the miner ---------------------------------------------------------------
def test_the_miner_slices_by_lead_and_can_convict_a_pocket():
    """A last-minute pocket that runs hot must be findable — that is the
    whole reason the dimension exists."""
    recs = []
    for i in range(120):   # late bets: said 60%, hit 40% — a real pocket
        recs.append({"sport": "mlb", "market": "hits", "prob": 0.60,
                     "won": 1 if i < 48 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, lead_min=10)})
    for i in range(120):   # early bets: calibrated
        recs.append({"sport": "mlb", "market": "hits", "prob": 0.60,
                     "won": 1 if i < 72 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, lead_min=400)})
    out = lp.mine(recs)
    leads = [f for f in out["findings"] if f["dim"] == "lead"]
    assert any(f["value"] == "<30m out" for f in leads), out["findings"]


def test_the_veto_blocks_a_closed_lead_slice_and_spares_the_unknown():
    import json as _json
    path = tempfile.mktemp(suffix=".json")
    open(path, "w").write(_json.dumps({"findings": [], "closed": [
        {"sport": "mlb", "market": "hits", "dim": "lead",
         "value": "<30m out", "reading": "ran hot"}]}))
    hit = lp.veto("mlb", "hits", side="OVER", odds=-110, lead_min=10,
                  path=path)
    assert hit and "<30m out" in hit
    # A gate that does not know its clock is never falsely blocked.
    assert lp.veto("mlb", "hits", side="OVER", odds=-110, lead_min=None,
                   path=path) is None


def test_the_lab_can_propose_on_the_new_dimension():
    from engine import hypotheses as hyp
    assert "lead" in hyp.DIMS
    props = hyp.SCHEMA["properties"]["hypotheses"]["items"]
    assert "lead" in props["properties"] and "lead" in props["required"]


def test_every_gate_passes_its_clock_to_the_veto():
    """The clock the gate uses must be the clock the veto bands on.

    FOLLOWS A VARIABLE, and it has to. This checked for the literal
    `lead_min=minutes_until` until 2026-08-10, when the NBA/WNBA gate
    started computing the lead ONCE — a started-game refusal and the
    veto's capture-lag band read the same number, and two separate calls
    could disagree by a tick and put a bet in one bucket while refusing it
    in another. The literal check would have forced the worse code.

    So: whatever is handed to `lead_min=` must trace back to
    `minutes_until`, either inline or through a name assigned from it. A
    gate that passes an unrelated variable still fails, which is the
    property worth keeping.
    """
    import re
    for path in ("engine/betting.py", "engine/mlb/betting.py",
                 "engine/nba/pipeline.py", "engine/cfb/pipeline.py"):
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        m = re.search(r"lead_min=([\w.]+)", src)
        assert m, f"{path} never passes lead to the veto"
        arg = m.group(1)
        if arg.startswith("minutes_until"):
            continue
        assert re.search(rf"^\s*{re.escape(arg)}\s*=\s*minutes_until\(",
                         src, re.M), (
            f"{path} passes lead_min={arg}, which is not the clock")


# --- the restated record -----------------------------------------------------
def _graded_journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    rows = [
        # A solid main that won: restated stake 1u at -110 → +0.91u.
        ("mlb", "won", -110, 0.57, "A"),
        # A solid main that lost: -1u.
        ("mlb", "lost", -110, 0.57, "A"),
        # A homer that won at +350: dime cap → +0.35u.
        ("mlb", "won", 350, 0.24, "Play"),
        # A vig-eaten old pick today's Kelly refuses: excluded.
        ("mlb", "lost", -110, 0.50, "B+"),
        # Another sport, to prove the scope filter.
        ("wnba", "won", -110, 0.58, "A"),
    ]
    for i, (sport, status, odds, p, grade) in enumerate(rows):
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " odds, hit_prob, grade, stake_units, status, category,"
            " pnl_units) VALUES ('t',?,?,?,'hits','OVER',1.5,?,?,?,0.1,?,"
            "'main',0)",
            (sport, f"2026-07-{i + 1:02d}", f"P{i}", odds, p, grade, status))
    conn.commit()
    return conn


def test_the_restated_record_resizes_without_touching_history():
    conn = _graded_journal()
    r = ledger.restated_performance(conn)
    assert r["wins"] == 3 and r["losses"] == 1
    assert r["excluded"] == 1
    # The restatement follows the CURRENT rules, which since 2026-08-12
    # size on the price rather than on Kelly-times-grade. Every row here
    # is at a standard-ish price, so each restates near the base unit
    # instead of the old 1 / 1 / 0.1 / 1 spread.
    assert abs(r["units_staked"] - 3.42) < 0.05
    assert abs(r["net_units"] - 2.29) < 0.10
    # And the journal rows still say what was actually bet.
    assert {row[0] for row in conn.execute(
        "SELECT stake_units FROM bets")} == {0.1}


def test_the_restated_record_scopes_per_sport():
    conn = _graded_journal()
    r = ledger.restated_performance(conn, "wnba")
    assert (r["wins"], r["losses"]) == (1, 0)


def test_the_export_and_the_page_carry_the_restated_view():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    # THE CALL, NOT ITS EXACT ARGUMENT LIST. This pinned the whole line
    # including the closing paren, so it went red the moment the call
    # gained the `since=` that windows it with the record it is drawn
    # beside — a change that FIXED a real disagreement between two
    # numbers on one screen. The contract is that the export carries a
    # restated block, per sport as well as overall.
    assert '"restated": {"overall": restated_performance(conn' in src
    assert "restated_performance(conn, sp" in src
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recRestatedSection(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    # Apostrophe-agnostic: the guard is about the COPY, not about which
    # quote glyph it is set with. Hardcoding the curly form would break the
    # moment anyone straightened it and vice versa.
    fn = _flat(fn)
    # "sizing" became "model" when the restatement started replaying the
    # selection haircut as well as the stake — it re-prices now, not just
    # re-sizes, and the heading has to say which.
    for needle in (_flat("At today's model"), "receipts as bet", "Restated ROI",
                   "excluded"):
        assert needle in fn, needle
    # The all-refused case must SAY so rather than render as an absence.
    # `if (!r.settled) return ""` hid the single loudest thing this block
    # can report: that today's model would not have placed one of them.
    assert "refuses all" in fn, "the empty restatement needs its own copy"
    assert "record above is unchanged" in fn
    assert "recRestatedSection(d.restated, scoped ? scope : null)" in app
    assert "recRestatedSection(d.restated, scope)" in app


# --- and football's clock, which was never an instant ------------------------
#
# THIS FILE ALREADY KNEW. `test_minutes_until_reads_iso_and_refuses_bare_
# clocks` says a bare local clock has no date and adds, in a comment,
# "(The NFL sample slate really carries "13:00")" — and then every
# fixture below it uses a full ISO stamp, so the case the comment names
# was never once exercised. The consequence went unmeasured for the life
# of the journal: `lead_min` was NULL on every NFL and CFB pick ever
# logged, and doctor.py's learning-ladder check reported the dimension
# as one the miner can never convict on.
#
# The refusal underneath is right and is untouched. What changed is that
# nothing has to be guessed: the date sits two keys away in the same game
# row, and the zone is the documented Eastern `engine/fatigue` already
# does its body-clock arithmetic in. The join happens ABOVE
# `minutes_until`, in the journal.

from engine.fatigue import kickoff_instant                     # noqa: E402
from engine.ledger import _kickoff_map, _lead_min              # noqa: E402


def test_the_date_and_the_eastern_clock_make_an_instant():
    assert kickoff_instant("2026-09-13", "13:00") == "2026-09-13T13:00:00-04:00"
    # Daylight saving carried by the library rather than by a fixed
    # offset that is wrong for four months of a season.
    assert kickoff_instant("2026-01-11", "20:20") == "2026-01-11T20:20:00-05:00"


def test_an_iso_week_label_is_refused_rather_than_parsed():
    """A near-miss caught while writing this. `date.fromisoformat`
    accepts ISO WEEK dates on 3.11+, and an NFL board's own `date` is
    "2026-W01" — the slate label, sitting right beside the games and the
    obvious wrong thing to hand this. Parsed loosely it returns the
    Monday of ISO week 1, so a Week 1 pick would have journaled a lead
    time eight months in the past."""
    assert kickoff_instant("2026-W01", "13:00") is None


def test_it_refuses_every_half_of_the_join_it_does_not_have():
    assert kickoff_instant("", "20:20") is None
    assert kickoff_instant("2026-09-13", "") is None
    assert kickoff_instant("2026-09-13", "nonsense") is None
    assert kickoff_instant("2026-09-13", "99:99") is None


def test_a_football_board_now_yields_real_instants():
    kick = _kickoff_map({"games": [
        {"home": "SEA", "away": "NE", "date": "2026-09-09", "kickoff": "20:20"},
        {"home": "LA", "away": "SF", "date": "2026-09-10", "kickoff": "20:35"}]})
    assert kick["SEA"] == kick["NE"] == "2026-09-09T20:20:00-04:00"
    assert lp.minutes_until(kick["LA"]) is not None


def test_a_board_that_already_carries_an_instant_is_left_alone():
    """CFB stamps a full ISO kickoff and MLB a first pitch. Neither needs
    joining, and rewriting them would be the guess this avoids."""
    stamp = "2026-08-30T17:45:16.253866Z"
    kick = _kickoff_map({"games": [{"home": "UGA", "away": "CLEM",
                                    "date": "2026-08-30", "kickoff": stamp}]})
    assert kick["UGA"] == stamp


def test_every_row_shape_the_journal_meets_reaches_one_answer():
    """Three paths read three different keys and one of them read none:
    a prop carries `kickoff`, a long shot carries `game_kickoff`, and a
    game bet carries neither and leans on the board's map."""
    kick = {"SEA": "2026-09-09T20:20:00-04:00"}
    got = [_lead_min({"kickoff": "2026-09-09T20:20:00-04:00", "team": "SEA"}, kick),
           _lead_min({"game_kickoff": "20:20", "game_date": "2026-09-09"}),
           _lead_min({"team": "SEA", "home": "SEA", "away": "NE"}, kick)]
    assert all(v is not None for v in got), got
    assert max(got) - min(got) < 1.0, "the three paths disagree by minutes"
    assert _lead_min({"team": "SEA"}, {}) is None
    assert _lead_min({}, {}) is None


def test_a_game_bet_journals_its_capture_lag_too():
    """The market where a line moves MOST was the one path that did not
    journal the dimension at all — a spread taken on Tuesday and the
    same spread taken an hour before kickoff were the same row."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": "2026-W01",
        "games": [{"home": "SEA", "away": "NE", "date": "2099-09-09",
                   "kickoff": "20:20"}],
        "game_bets": [{"bet_type": "spread", "team": "SEA", "home": "SEA",
                       "away": "NE", "line": -3.5, "odds": -110,
                       "win_prob": 0.56, "edge": 0.05, "confidence": 7.0,
                       "grade": "Play", "stake_units": 1.0,
                       "recommended": True}],
        "recommendations": []})
    rows = conn.execute("SELECT market, lead_min FROM bets").fetchall()
    assert rows, "nothing journaled — the fixture stopped being a bet"
    for r in rows:
        assert r["lead_min"] is not None and r["lead_min"] > 0, r["market"]


def test_all_three_journal_paths_go_through_the_one_helper():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    assert src.count("_lead_min(") >= 4, \
        "a journal path grew its own capture-lag arithmetic again"
    i = src.index('"stake_dollars, status, leg, rest_days, body_clock')
    assert "lead_min" in src[i:i + 200], \
        "a game bet journals no capture lag again"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
