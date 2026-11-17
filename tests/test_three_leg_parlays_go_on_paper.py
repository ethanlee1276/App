"""A league's three-leg parlays go on paper while they hit under 25% (2026-11-17).

Ethan, asked whether the NFL's three-leg parlays (30 of 175 hit, 17%) should
keep posting or be tracked without posting while they hit under 25%: "ok".
What these hold:

  * the hold (engine/parlayhold): a league whose last WINDOW graded three-leg
    tickets, MIN_N at least, hit under 25% goes on paper; the NFL's starts as a
    standing hold from 17 November; the tickets graded since a hold began,
    RELEASE_N at least, hitting 25% bring it back by themselves; a league back
    is held again only on tickets graded after its release;
  * on paper, each game's tickets are still built and journaled under
    `game_three` and graded (engine/parlayledger reads `paper_threes` as well
    as `threes`), so the record keeps learning on them;
  * and posted nowhere: the board's `threes` are empty, each game says why
    in their place, the report's parlays section and the Report Picks page say
    it once, and the Record page's three-leg block says the league is on paper;
  * the nightly settle pass measures it beside the Most Likely holds.

Run directly: `python3 tests/test_three_leg_parlays_go_on_paper.py`
"""
import datetime as dt
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays, parlayhold, parlayledger  # noqa: E402

DAY = dt.date(2026, 11, 20)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    parlayledger.ensure_schema(c)
    return c


def _tickets(c, sport, won, lost, day="2026-11-01"):
    for i in range(won + lost):
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status) VALUES (?,?,?,?,?,?,?,1,0,1,0,?,?)",
                  (f"{day}T12:00:00", sport, day, f"{sport}-{day}-{i}", "same_game", 3, "A@B",
                   parlayhold.SOURCE, "won" if i < won else "lost"))
    c.commit()


def _path():
    return Path(tempfile.mkdtemp()) / "parlayhold.json"


def test_the_nfl_starts_on_paper_and_a_measured_league_joins_it():
    c, p = _conn(), _path()
    _tickets(c, "nba", 12, 48)        # 20% over 60: held
    _tickets(c, "nhl", 20, 40)        # 33%: posted
    _tickets(c, "mlb", 5, 30)         # under MIN_N: not judged
    out = parlayhold.refresh(c, p, today=DAY)
    held = {h["sport"]: h for h in out["holds"]}
    assert set(held) == {"nfl", "nba"}, held
    assert held["nfl"]["source"] == "standing" and held["nfl"]["since"] == "2026-11-17"
    assert held["nba"] == {"sport": "nba", "since": "2026-11-20", "n": 60, "won": 12, "source": "measured",
                           "since_n": 0, "since_won": 0}, held["nba"]
    assert parlayhold.held("NBA", p)["won"] == 12 and parlayhold.held("nhl", p) is None


def test_a_hold_comes_back_once_its_tickets_since_hit_a_quarter():
    c, p = _conn(), _path()
    _tickets(c, "nfl", 30, 145, day="2026-11-10")      # the record it was asked on
    _tickets(c, "nfl", 12, 38, day="2026-11-24")       # 24% since: still on paper
    out = parlayhold.refresh(c, p, today=DAY)
    h = parlayhold.held("nfl", p)
    assert h and (h["since_n"], h["since_won"]) == (50, 12), h
    assert not out["released"]
    _tickets(c, "nfl", 2, 0, day="2026-11-25")         # 14 of 52, 27%: back
    out = parlayhold.refresh(c, p, today=DAY + dt.timedelta(days=8))
    assert parlayhold.held("nfl", p) is None and [r["sport"] for r in out["released"]] == ["nfl"]
    # Back for good on its own words: only tickets after the release can hold it again.
    out = parlayhold.refresh(c, p, today=DAY + dt.timedelta(days=9))
    assert parlayhold.held("nfl", p) is None, "the old tickets do not put it back"
    _tickets(c, "nfl", 10, 45, day="2026-12-10")       # 18% after the release: on paper again
    parlayhold.refresh(c, p, today=DAY + dt.timedelta(days=21))
    again = parlayhold.held("nfl", p)
    assert again and again["source"] == "measured" and again["since"] == "2026-12-11", again


def test_the_reason_is_said_in_a_readers_words():
    nfl = parlayhold.words(dict(parlayhold.STANDING[0]))
    assert nfl == ("On paper, not posted: our three-leg parlays in the NFL have hit 30 of 175 (17%), under the 25% "
                   "they need. Each game's are still built and graded on the record, and they come back by "
                   "themselves once 50 graded since 17 November hit 25%."), nfl
    nba = parlayhold.words({"sport": "nba", "since": "2026-11-20", "n": 60, "won": 12, "source": "measured"})
    assert "have hit 12 of their last 60 (20%)" in nba and "since 20 November" in nba


def test_paper_tickets_are_journaled_and_graded_but_posted_nowhere():
    c = _conn()
    leg = lambda pl, m: {"player": pl, "team": "KC", "market": m, "side": "OVER", "line": 1.5, "odds": -150,
                         "book": "DraftKings", "p": 0.7}                                        # noqa: E731
    paper = {"legs": [leg("A", "receptions"), leg("B", "rush_att"), leg("C", "pass_yds")], "joint": 0.3,
             "take_dec": 3.5, "naive_dec": 3.4, "independent": 0.34}
    gp = {"games": [{"away": "DEN", "home": "KC", "game": "DEN@KC", "threes": [], "paper_threes": [paper],
                     "threes_paper": True, "threes_note": "On paper", "scorers": []}]}
    assert parlayledger.log_game_parlays(c, gp, "nfl", "2026-W12") == 1
    row = c.execute("SELECT source, n_legs, stake_units FROM parlays").fetchone()
    assert tuple(row) == ("game_three", 3, 0), tuple(row)
    assert [r["player"] for r in gameparlays.journal_rows(gp)] == ["A", "B", "C"], "its legs are graded too"


def test_the_build_moves_a_held_leagues_tickets_to_paper():
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    build = src[src.index("def build(board: dict, sport: str, now=None) -> dict:"):src.index("def paper_hold(")]
    assert "paper = paper_hold(sp)" in build
    assert 'x["paper_threes"], x["threes"] = x.get("threes") or [], []' in build
    assert 'x["threes_note"], x["threes_paper"] = paper["note"], True' in build
    assert '**({"threes_paper": paper} if paper else {}),' in build
    assert '"paper_threes": sum(len(x.get("paper_threes") or []) for x in out_games),' in build
    orig = parlayhold.DEFAULT_PATH
    try:
        parlayhold.DEFAULT_PATH = _path()          # nothing saved: the standing NFL hold alone
        assert gameparlays.paper_hold("nfl")["note"].startswith("On paper, not posted: our three-leg parlays in the NFL")
        assert gameparlays.paper_hold("nba") is None
    finally:
        parlayhold.DEFAULT_PATH = orig


def test_the_report_the_pages_and_the_record_say_it():
    from engine import gamereport
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    sec = src[src.index("def sec_parlays("):src.index("def parlay_sentence(")]
    assert ('    elif gp.get("threes_paper"):\n'
            '        # On paper while the league\'s three-leg record is under 25% (engine/parlayhold).\n'
            '        blocks += [_h("Three-leg parlays"), _p(gp.get("threes_note") or "")]') in sec
    assert callable(gamereport.sec_parlays)
    led = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
    assert 'keys = ("threes", "paper_threes") if kind == "three" else ("scorers",)' in led
    assert 'kinds["three"]["paper"] = {"since": h.get("since"), "note": parlayhold.words(h)}' in led
    rj = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert ": g.threes_paper ? `<p class=\"gr-note\">Three-leg parlays: on paper for now, built and graded but not " \
           "posted.</p>`" in rj
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert 'const paper = locked ? "" : ((d.game_parlays || {}).threes_paper || {}).note || "";' in rp
    assert '${paper ? `<p class="set-note">${escapeHtml(paper)}</p>` : ""}' in rp
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert '${b.paper && b.paper.note ? `<p class="rec-gp-close">${escapeHtml(b.paper.note)}</p>` : ""}' in rec
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = m.index("plh = parlayhold.refresh(lconn)")
    assert m.index("ph = paperhold.refresh(lconn)") < i, "beside the Most Likely holds, on the same fresh grades"
    assert 'verdicts["three-leg parlays on paper"] = parlayhold.verdict(plh)' in m


def test_the_record_carries_the_hold():
    c = _conn()
    _tickets(c, "nfl", 3, 7)
    orig = parlayhold.DEFAULT_PATH
    try:
        parlayhold.DEFAULT_PATH = _path()
        rec = parlayledger.game_parlay_record(c)
    finally:
        parlayhold.DEFAULT_PATH = orig
    three = rec["nfl"]["three"]
    assert (three["graded"], three["wins"]) == (10, 3)
    assert three["paper"]["since"] == "2026-11-17" and three["paper"]["note"].startswith("On paper, not posted")


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
