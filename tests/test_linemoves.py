"""Tests for line-movement analysis (pure, no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import linemoves as lm
from engine.linemoves import analyze, record_snapshots, load_history
from engine.models import Prop, GameLog, SportsbookLine, RUSH_YDS

NOW = 10_000.0


def _snap(ts, book, line, player="RB One", market="rush_yds"):
    return {"ts": ts, "player": player, "market": market, "book": book,
            "line": line, "over_odds": -110}


def test_steam_when_books_move_together():
    rows = []
    for book in ("DraftKings", "FanDuel", "BetMGM"):
        rows.append(_snap(NOW - 3000, book, 70.5))
        rows.append(_snap(NOW - 600, book, 72.0))
    reports = analyze(rows, now=NOW)
    assert len(reports) == 1
    r = reports[0]
    assert r.open == 70.5 and r.current == 72.0 and r.direction == "up"
    assert r.steam is True


def test_single_book_move_is_not_steam():
    rows = [
        _snap(NOW - 3000, "DraftKings", 70.5), _snap(NOW - 600, "DraftKings", 72.0),
        _snap(NOW - 3000, "FanDuel", 70.5), _snap(NOW - 600, "FanDuel", 70.5),
        _snap(NOW - 3000, "BetMGM", 70.5), _snap(NOW - 600, "BetMGM", 70.5),
    ]
    reports = analyze(rows, now=NOW)
    assert len(reports) == 1
    assert reports[0].steam is False


def test_stale_moves_do_not_steam():
    # Both books moved, but hours ago — outside the steam window.
    rows = []
    for book in ("DraftKings", "FanDuel"):
        rows.append(_snap(NOW - 90_000, book, 70.5))
        rows.append(_snap(NOW - 80_000, book, 72.0))
    reports = analyze(rows, now=NOW, window_s=3600)
    assert reports and reports[0].steam is False
    assert reports[0].delta == 1.5


def test_unmoved_board_is_silent():
    # Cached re-records of an identical board must not fabricate movement.
    rows = [_snap(NOW - i * 600, "DraftKings", 70.5) for i in range(5)]
    assert analyze(rows, now=NOW) == []


def test_down_moves_report_direction():
    rows = [
        _snap(NOW - 3000, "DraftKings", 250.5, player="QB A", market="pass_yds"),
        _snap(NOW - 500, "DraftKings", 244.5, player="QB A", market="pass_yds"),
        _snap(NOW - 3000, "FanDuel", 250.5, player="QB A", market="pass_yds"),
        _snap(NOW - 500, "FanDuel", 245.5, player="QB A", market="pass_yds"),
    ]
    r = analyze(rows, now=NOW)[0]
    assert r.direction == "down" and r.steam is True and r.delta < 0


def test_record_skips_proxy_and_roundtrips(tmp_path=None):
    import tempfile, pathlib
    path = pathlib.Path(tempfile.mkdtemp()) / "hist.jsonl"
    prop = Prop("RB One", "GB", "CHI", "RB", RUSH_YDS,
                [GameLog(1, "X", 80)], 80, None,
                [SportsbookLine("DraftKings", 70.5, -110, -110),
                 SportsbookLine("proxy", 71.5, -110, -110)], "rb1")
    n = record_snapshots([prop], ts=NOW, path=path)
    assert n == 1  # proxy line skipped
    rows = load_history(path)
    assert len(rows) == 1 and rows[0]["book"] == "DraftKings"


def test_closing_lines_picks_the_last_pregame_number():
    """CLV needs the closing line: the last snapshot before the game starts,
    medianed across books so one outlier can't define the close."""
    import tempfile
    from pathlib import Path
    from engine.linemoves import record_snapshots, load_history, closing_lines
    from engine.models import Prop, SportsbookLine, GameLog, REC_YDS

    tmp = Path(tempfile.mkdtemp()) / "moves.jsonl"

    def prop_at(line, book="DraftKings"):
        return Prop(player="Ja'Marr Chase", team="CIN", opponent="PIT", position="WR",
                    market=REC_YDS, logs=[GameLog(week=1, opponent="X", value=70)],
                    career_avg=70, vs_opponent_avg=None,
                    lines=[SportsbookLine(book, line, -110, -110)])

    record_snapshots([prop_at(68.5)], ts=1000, path=tmp)
    record_snapshots([prop_at(74.5, "DraftKings")], ts=3000, path=tmp)
    record_snapshots([prop_at(75.5, "FanDuel")], ts=3000, path=tmp)
    record_snapshots([prop_at(99.0)], ts=9999, path=tmp)      # post-game, ignore

    rows = load_history(tmp)
    close = closing_lines(rows, before_ts=5000)
    assert close[("Ja'Marr Chase", "rec_yds")] == 75.0        # median of 74.5/75.5
    # Without a cutoff the latest snapshot wins (documents the cutoff's purpose).
    assert closing_lines(rows)[("Ja'Marr Chase", "rec_yds")] == 99.0


def _psnap(ts, book, odds, line=0.5, player="Slugger", market="home_runs"):
    return {"ts": ts, "player": player, "market": market, "book": book,
            "line": line, "over_odds": odds}


def test_price_movement_on_a_static_line():
    """MLB props often sit on a fixed 0.5/1.5 line and move through the
    JUICE — the line never budges, the odds do. That must count as
    movement (it's the only kind HR props ever show)."""
    rows = []
    for book in ("DraftKings", "FanDuel"):
        rows.append(_psnap(NOW - 3000, book, +150))
        rows.append(_psnap(NOW - 600, book, +115))    # over shortening hard
    r = analyze(rows, now=NOW)[0]
    assert r.delta == 0 and r.direction == "up" and r.steam is True
    assert r.open_odds == 150 and r.current_odds == 115
    assert r.prob_delta > 0.05


def test_static_price_and_line_stay_silent():
    rows = [_psnap(NOW - i * 600, "DraftKings", +150) for i in range(5)]
    assert analyze(rows, now=NOW) == []


def test_annotate_stamps_verdict_for_our_side():
    from engine.linemoves import annotate_recommendations

    rows = []
    for book in ("DraftKings", "FanDuel", "BetMGM"):
        rows.append(_snap(NOW - 3000, book, 70.5))
        rows.append(_snap(NOW - 600, book, 72.0))     # line up = toward Over
    reports = analyze(rows, now=NOW)

    over = {"player": "RB One", "market": "rush_yds", "side": "OVER",
            "has_market": True, "reasons": [], "warnings": []}
    under = {"player": "RB One", "market": "rush_yds", "side": "UNDER",
             "has_market": True, "reasons": [], "warnings": []}
    proxy = {"player": "RB One", "market": "rush_yds", "side": "OVER",
             "has_market": False, "reasons": [], "warnings": []}
    unmoved = {"player": "Nobody", "market": "rush_yds", "side": "OVER",
               "has_market": True, "reasons": [], "warnings": []}

    n = annotate_recommendations([over, under, proxy, unmoved], reports)
    assert n == 2
    # Same move, opposite meanings: agreement is a reason, a fade is a warning.
    assert over["line_move"]["verdict"] == "with" and over["line_move"]["steam"]
    assert any("Market moving toward the Over" in r for r in over["reasons"])
    assert under["line_move"]["verdict"] == "against"
    assert any("Market moving against the Under" in w for w in under["warnings"])
    # Proxy lines and unmoved props get no stamp — nothing is fabricated.
    assert "line_move" not in proxy and "line_move" not in unmoved


def test_todays_rows_drops_yesterdays_board():
    """MLB plays daily — yesterday's snapshot of the same player/market must
    never chain onto today's and fabricate movement between two games."""
    from engine.linemoves import todays_rows
    import datetime as dt
    noon = dt.datetime(2026, 7, 26, 12, 0).timestamp()
    rows = [_snap(noon - 20 * 3600, "DraftKings", 70.5),   # yesterday evening
            _snap(noon - 3600, "DraftKings", 72.0),
            _snap(noon - 600, "DraftKings", 72.0)]
    kept = todays_rows(rows, now=noon)
    assert len(kept) == 2
    assert analyze(kept, now=noon) == []                   # today never moved


def test_closing_lines_by_date_takes_each_days_last_snapshot():
    """The journal's free CLV source: each day gets ITS OWN close (the last
    snapshot that day), keyed by normalized player name."""
    import datetime as dt
    from engine.linemoves import closing_lines_by_date
    d1 = dt.datetime(2026, 7, 24, 12, 0).timestamp()
    d2 = dt.datetime(2026, 7, 25, 12, 0).timestamp()
    rows = [_snap(d1, "DraftKings", 70.5, player="RB Oné"),
            _snap(d1 + 7 * 3600, "DraftKings", 72.0, player="RB Oné"),   # day-1 close
            _snap(d2, "DraftKings", 68.5, player="RB Oné")]              # day 2 restarts
    closes = closing_lines_by_date(rows)
    assert closes[("rb one", "rush_yds", "2026-07-24")] == 72.0
    assert closes[("rb one", "rush_yds", "2026-07-25")] == 68.5


def test_annotate_price_move_reads_as_odds():
    from engine.linemoves import annotate_recommendations
    rows = [_psnap(NOW - 3000, "DraftKings", +150),
            _psnap(NOW - 600, "DraftKings", +115),
            _psnap(NOW - 3000, "FanDuel", +150),
            _psnap(NOW - 600, "FanDuel", +115)]
    rec = {"player": "Slugger", "market": "home_runs", "side": "OVER",
           "has_market": True, "reasons": [], "warnings": []}
    assert annotate_recommendations([rec], analyze(rows, now=NOW)) == 1
    assert rec["line_move"]["verdict"] == "with"
    assert any("Over price +150 → +115" in r for r in rec["reasons"])


# --- §4 first-mover attribution ---------------------------------------------
def _ladder(book_moves, t0=1_700_000_000):
    """book -> [(offset_s, over_odds)] into snapshot rows on one 1.5 line."""
    rows = []
    for book, moves in book_moves.items():
        for dt, odds in moves:
            rows.append({"player": "A B", "market": "hits", "ts": t0 + dt,
                         "line": 1.5, "over_odds": odds, "book": book})
    return rows, t0


def test_the_first_mover_is_the_book_that_left_its_open_first():
    """§4: "Which book moved first matters — the first mover took the
    smart money; the rest are copying." `last_move_ts` already existed
    and is the wrong end of the move for this question."""
    rows, t0 = _ladder({
        "Pinnacle":   [(0, -110), (60, -135), (600, -140)],
        "FanDuel":    [(0, -110), (300, -130), (700, -138)],
        "DraftKings": [(0, -112), (700, -112)],
    })
    r = lm.analyze(rows, now=t0 + 800)[0]
    assert r.first_mover == "Pinnacle"
    assert r.first_mover_lead_s == 240.0
    assert r.first_mover_sharp is True


def test_a_book_that_moved_the_other_way_is_not_the_first_mover():
    """It moved earliest and it moved AGAINST the eventual direction — a
    stale number being dragged back, not information arriving. Crediting
    it would invert the signal on exactly the props where a book was
    wrong early."""
    rows, t0 = _ladder({
        "DraftKings": [(0, -110), (30, +100)],       # drifts, earliest
        "Pinnacle":   [(0, -110), (120, -140)],      # shortens, with the move
        "FanDuel":    [(0, -110), (400, -135)],
    })
    r = lm.analyze(rows, now=t0 + 500)[0]
    assert r.direction == "up"
    assert r.first_mover == "Pinnacle", r.first_mover


def test_a_lone_mover_reports_no_lead():
    """A lead is a comparison. One book moving alone has no lead over
    anybody, and printing a large one would read as a strong signal when
    it is an absent second data point."""
    # TWO books, not three. With three, one mover leaves the consensus
    # median unmoved and `analyze` correctly reports nothing at all —
    # which is the existing filter working, and was my fixture being
    # wrong rather than the code.
    rows, t0 = _ladder({
        "Pinnacle": [(0, -110), (60, -160)],
        "FanDuel":  [(0, -110), (600, -110)],
    })
    r = lm.analyze(rows, now=t0 + 700)[0]
    assert r.first_mover == "Pinnacle"
    assert r.first_mover_lead_s == 0.0


def test_a_recreational_first_mover_is_not_flagged_sharp():
    rows, t0 = _ladder({
        "FanDuel":  [(0, -110), (60, -140)],
        "Pinnacle": [(0, -110), (300, -138)],
    })
    r = lm.analyze(rows, now=t0 + 400)[0]
    assert r.first_mover == "FanDuel"
    assert r.first_mover_sharp is False


def test_sharp_matching_survives_the_display_name_vs_api_key_gap():
    """The snapshots carry "Pinnacle"; oddsapi.SHARP_BOOKS carries
    "pinnacle". A strict comparison answers False forever, which looks
    like a finding about the market rather than a string bug."""
    assert lm._is_sharp("Pinnacle") is True
    assert lm._is_sharp("pinnacle") is True
    assert lm._is_sharp("Pinnacle Sports") is True
    assert lm._is_sharp("FanDuel") is False
    assert lm._is_sharp("") is False
    assert lm._is_sharp(None) is False


def test_first_mover_attribution_does_not_touch_the_grade():
    """DELIBERATE. `engine.quality.apply_movement` already gives movement
    veto power over the board — it can set grade="Pass" and stake 0 — on
    a signal whose predictive value has never been measured; movecheck.py
    exists to settle exactly that. Wiring a SECOND unmeasured movement
    signal into pricing would repeat the mistake with more confidence."""
    import inspect
    from engine import quality
    src = inspect.getsource(quality)
    for name in ("first_mover", "first_mover_sharp", "first_mover_lead_s"):
        assert name not in src, f"{name} reached the grader unmeasured"


# --- §4 the lineup-release move, baseball's unique tell ---------------------
def _card_rows(t0, before_over, after_over, before_under=-110,
               after_under=-110, book="FanDuel"):
    return [
        {"player": "A B", "market": "hits", "ts": t0, "line": 1.5,
         "over_odds": before_over, "under_odds": before_under, "book": book},
        {"player": "A B", "market": "hits", "ts": t0 + 900, "line": 1.5,
         "over_odds": after_over, "under_odds": after_under, "book": book},
    ]


def test_an_over_and_an_under_get_opposite_signs_from_one_price_move():
    """THE THING MOST WORTH GETTING RIGHT. `delta` is in implied
    probability of OUR side, so negative always means the market moved
    against us. Reading one sign for both sides would flag exactly the
    wrong half of the board — and it would look like a working detector
    the whole time."""
    t0 = 1_700_000_000
    rows = _card_rows(t0, -110, +130, -110, -160)
    over = lm.lineup_release_move(rows, "A B", "hits", 1.5, "OVER", t0 + 600)
    under = lm.lineup_release_move(rows, "A B", "hits", 1.5, "UNDER", t0 + 600)
    assert over["delta"] < 0 and over["against_us"] is True
    assert under["delta"] > 0 and under["against_us"] is False


def test_a_prop_that_does_not_straddle_the_card_returns_none():
    """A real answer, not a gap. A prop seen only before the card says
    nothing about what the card did to it, and returning a zero would
    bury the signal under props that were never observed after."""
    t0 = 1_700_000_000
    rows = _card_rows(t0, -110, +130)
    assert lm.lineup_release_move(
        rows, "A B", "hits", 1.5, "OVER", t0 + 9999) is None
    assert lm.lineup_release_move(
        rows, "A B", "hits", 1.5, "OVER", t0 - 9999) is None


def test_the_pair_straddling_the_card_is_the_tightest_one():
    """Using the day's median either side would fold in movement that has
    nothing to do with the card — which is most of the day."""
    t0 = 1_700_000_000
    rows = [
        {"player": "A B", "market": "hits", "ts": t0, "line": 1.5,
         "over_odds": +200, "book": "FanDuel"},          # morning, far off
        {"player": "A B", "market": "hits", "ts": t0 + 500, "line": 1.5,
         "over_odds": -110, "book": "FanDuel"},          # just before
        {"player": "A B", "market": "hits", "ts": t0 + 700, "line": 1.5,
         "over_odds": -120, "book": "FanDuel"},          # just after
        {"player": "A B", "market": "hits", "ts": t0 + 5000, "line": 1.5,
         "over_odds": -300, "book": "FanDuel"},          # late, far off
    ]
    r = lm.lineup_release_move(rows, "A B", "hits", 1.5, "OVER", t0 + 600)
    from engine.linemoves import _implied
    # The function rounds to 4dp, so compare at 4dp. A 1e-6 tolerance
    # here failed on correct output — the tightest pair WAS selected.
    assert r["before"] == round(_implied(-110), 4)
    assert r["after"] == round(_implied(-120), 4)
    assert r["gap_s"] == 200.0, "a wider pair than the straddling one"


def test_a_close_at_a_different_line_is_not_the_same_prop():
    """Same fault the CLV rebuild had: over 1.5 and over 2.5 are
    different bets, and reading one as the other inverts exactly the
    cases where the line moved."""
    t0 = 1_700_000_000
    rows = [
        {"player": "A B", "market": "hits", "ts": t0, "line": 1.5,
         "over_odds": -110, "book": "FanDuel"},
        {"player": "A B", "market": "hits", "ts": t0 + 900, "line": 2.5,
         "over_odds": +250, "book": "FanDuel"},
    ]
    assert lm.lineup_release_move(
        rows, "A B", "hits", 1.5, "OVER", t0 + 600) is None


def test_lineup_times_records_the_first_sighting_and_never_moves_it():
    """The boundary is the FIRST time we saw the card up. A later look
    must not overwrite it, or every extra poll drags the boundary later
    and shrinks the 'after' window toward nothing."""
    import tempfile
    from pathlib import Path
    from engine.mlb import lineuptimes
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    p = Path(path)
    try:
        lineuptimes.note_look("2026-08-09", 777, False, ts=1000.0, path=p)
        lineuptimes.note_look("2026-08-09", 777, True, ts=1600.0, path=p)
        lineuptimes.note_look("2026-08-09", 777, True, ts=9000.0, path=p)
        assert lineuptimes.posted_at("2026-08-09", 777, path=p) == 1600.0
        assert lineuptimes.is_usable("2026-08-09", 777, path=p) is True
    finally:
        os.unlink(path)


def test_a_first_sighting_with_no_previous_look_is_not_usable():
    """It is a real timestamp and a useless boundary — the true release
    could be any time before it. Treating it as precise would find
    'movement after lineups' everywhere, because most of the day's
    movement would land on the after side."""
    import tempfile
    from pathlib import Path
    from engine.mlb import lineuptimes
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    p = Path(path)
    try:
        lineuptimes.note_look("2026-08-09", 42, True, ts=1600.0, path=p)
        assert lineuptimes.posted_at("2026-08-09", 42, path=p) == 1600.0
        assert lineuptimes.is_usable("2026-08-09", 42, path=p) is False
        # And a gap wider than the useful window is equally unusable.
        lineuptimes.note_look("2026-08-09", 43, False, ts=0.0, path=p)
        lineuptimes.note_look("2026-08-09", 43, True, ts=20_000.0, path=p)
        assert lineuptimes.is_usable("2026-08-09", 43, path=p) is False
    finally:
        os.unlink(path)


def test_a_whole_poll_is_one_read_and_one_write():
    """MY REGRESSION, reported as "lineupwatch is taking forever to
    load". `note_look` loads and rewrites the entire store per call —
    fine for one game, quadratic for a slate: fifteen games meant fifteen
    reads and fifteen full rewrites of a file that grows by a row per
    game per day all season."""
    import tempfile
    from pathlib import Path
    from engine.mlb import lineuptimes
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    p = Path(path)
    writes = {"n": 0}
    real_save = lineuptimes._save
    lineuptimes._save = lambda d, pp=None: (writes.__setitem__("n", writes["n"] + 1),
                                            real_save(d, pp))[1]
    try:
        lineuptimes.note_looks("2026-08-09",
                               [(i, i % 2 == 0) for i in range(15)],
                               ts=1000.0, path=p)
        assert writes["n"] == 1, f"{writes['n']} writes for one poll"
        assert lineuptimes.posted_at("2026-08-09", 0, path=p) == 1000.0
        assert lineuptimes.posted_at("2026-08-09", 1, path=p) is None
    finally:
        lineuptimes._save = real_save
        os.unlink(path)


def test_a_posted_card_is_not_re_fetched_on_later_polls():
    """A card does not un-post, so the games already seen up need no
    boxscore at all — which turns the boundary bookkeeping from a cost
    into the thing that makes the poll cheap as the slate fills in."""
    import tempfile
    from pathlib import Path
    from engine.mlb import lineuptimes
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    p = Path(path)
    try:
        lineuptimes.note_looks("2026-08-09", [(1, True), (2, False)],
                               ts=1000.0, path=p)
        known = lineuptimes.already_posted("2026-08-09", path=p)
        assert known == {1}, known
        # A different day must not inherit today's answers.
        assert lineuptimes.already_posted("2026-08-10", path=p) == set()
    finally:
        os.unlink(path)


def test_the_installer_drives_three_distinct_agents():
    """Three runners now share one installer, and the failure mode is
    silent: a label pointing at the wrong script installs an agent that
    runs the nightly at 11am, or a lineup watch at 6am, and neither
    announces itself."""
    import pathlib
    sh = (pathlib.Path(__file__).resolve().parent.parent / "tools"
          / "install-nightly.sh").read_text()
    for label, script in (("com.qellysbook.nightly", "nightly"),
                          ("com.qellysbook.prekick", "prekick"),
                          ("com.qellysbook.lineups", "lineups")):
        assert label in sh, label
        assert (pathlib.Path(__file__).resolve().parent.parent / "tools"
                / f"{script}.sh").is_file(), f"tools/{script}.sh missing"
    # The plist and the chmod must BOTH follow the selected script. A
    # chmod hardcoded to nightly.sh leaves the other two non-executable,
    # which launchd reports as a permissions error nobody connects back
    # to the installer.
    assert 'tools/${SCRIPT}.sh</string>' in sh
    assert 'chmod +x "$REPO/tools/${SCRIPT}.sh"' in sh
    assert '${PRE:+prekick}' not in sh, "the two-way expansion is back"


def test_the_lineup_watch_polls_tighter_than_the_default():
    """The polling interval IS the precision of every boundary recorded.
    Skipping games whose cards are already up made a tight interval cheap,
    so the agent spends that saving on precision rather than pocketing
    it."""
    import pathlib
    sh = (pathlib.Path(__file__).resolve().parent.parent / "tools"
          / "lineups.sh").read_text()
    assert "--every 5" in sh
    assert "--watch" in sh
    # And it must report the harvest, or a day that recorded nothing
    # usable is invisible until someone runs a report by hand.
    assert "coverage()" in sh


def test_the_installer_prints_commands_that_act_on_what_it_installed():
    """After installing the lineup agent it printed:

        run it once now:  bash tools/install-nightly.sh --now
        read last night:  tail -40 logs/nightly-$(date +%F).log
        remove it:        bash tools/install-nightly.sh --remove

    All three were wrong for the agent just installed. `--now` execed
    nightly.sh whatever mode you asked for; the log named belongs to a
    different runner; and `--remove` alone removes the NIGHTLY agent,
    because the label comes from the flags preceding it — so following
    that line deletes the wrong one and leaves the intended one running.

    Guidance that names the wrong target is worse than none: it is
    confidently wrong at the moment you are least able to tell."""
    import pathlib
    sh = (pathlib.Path(__file__).resolve().parent.parent / "tools"
          / "install-nightly.sh").read_text()
    assert 'exec bash "$REPO/tools/${SCRIPT}.sh"' in sh, "--now still hardcoded"
    assert 'logs/${SCRIPT}-' in sh, "the log path is still one runner's"
    assert '$MODE--remove' in sh and '$MODE--now' in sh, "commands lose the mode"
    assert 'logs/nightly-\$(date' not in sh


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
