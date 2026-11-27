"""The Record page and the boards say their counts and markets in words (step AID, 27 November 2026).

A scan of every sentence the live site's public files carry found the slips a reader sees:

  * the Record page's account-health card: "57% of volume is pass_yds", and "mix in main-line bets (sides/totals)
    so pass_yds isn't 57% of your volume here" (also rush_att, kick_pts, pass_cmp): the journal's market id, not
    its name. The My Bets card, which ports the same score to the reader's own log, already said words;
  * the stale-price verdict: "hit rate 42.8% is -0.0 standard errors from the 42.8% break-even";
  * a replaced preregistration: "...re-asked of the model that will actually take the bets.. The terms above";
  * counts written "block(s)", "player(s) corrected", "bet(s) were left out", "4 measured market(s)";
  * a quarterback change: "1.0 runs a game for 1 yards".

Each is said as a person would say it now. Offline. Run directly: `python3 tests/test_the_record_page_says_it_in_words.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger, prereg, qbchange                         # noqa: E402


def _health(markets):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE bets (status, category, date, book, closing_line, line, side, market, stake_dollars)")
    for i, mk in enumerate(markets):
        c.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?)",
                  ("won" if i % 2 else "lost", "main", "2026-11-20", "DraftKings", None, 1.5, "OVER", mk, 25))
    return ledger.account_health(c)["books"][0]


def test_the_health_card_names_the_market():
    b = _health(["pass_yds"] * 6 + ["rush_att"] * 2 + ["moneyline"] * 2)
    assert "60% of volume is passing yards" in b["drivers"], b["drivers"]
    assert ("mix in main-line bets (sides/totals) so passing yards isn't 60% of your volume here"
            in b["actions"]), b["actions"]
    assert b["top_market"] == "pass_yds", "the data field keeps the id; only the words change"
    said = " ".join(b["drivers"] + b["actions"])
    assert "pass_yds" not in said and "_" not in said, said


def test_every_market_the_card_can_name_reads_as_words():
    for key, words in {"rush_att": "carries", "kick_pts": "kicking points", "pass_cmp": "completions",
                       "anytime_td": "anytime TD", "pass_td": "passing TDs", "total": "game total",
                       "rec_yds": "receiving yards"}.items():
        assert ledger._market_said(key) == words, (key, ledger._market_said(key))


def test_a_verdict_at_the_break_even_says_zero_not_minus_zero():
    conn = ledger.connect(":memory:")
    # 300 flags at -110: a break-even of 52.38%; 157 wins is 52.33%, a z of about -0.02.
    for i in range(300):
        won = i < 157
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, projection, hit_prob, edge, "
            "confidence, grade, stake_units, status, actual, pnl_units, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'stale')",
            ("2026-09-01T00:00:00", "nfl", "2026-09-01", f"P{i}", "rec_yds", "OVER", 50.5, "DraftKings", -110,
             0.0, 0.5, 0.012, 0.0, "", 0.1, "won" if won else "lost", 1.0 if won else 0.0,
             0.1 * (100 / 110) if won else -0.1))
    conn.commit()
    r = ledger.stale_verdict(conn)["nfl"]
    assert -0.05 < r["z"] < 0, r
    assert "is 0.0 standard errors from the 52.4% break-even" in r["why"], r["why"]
    assert "-0.0" not in r["why"]


def test_a_replaced_test_ends_its_reason_with_one_stop():
    test = dict(prereg.TD_EDGE_NFL, registered="2026-09-01", superseded_by="X", superseded_on="2026-10-20",
                superseded_why="the model was replaced. The claim is re-asked of the model that will take the bets.")
    test.pop("hash", None)
    out = prereg.verdict(test, [])
    assert out["status"] == "superseded", out
    assert "take the bets. The terms above are the ones that were frozen" in out["reading"], out["reading"]
    assert ".." not in out["reading"], out["reading"]


def test_counts_are_said_in_the_singular_and_the_plural():
    src = {p: (ROOT / "engine" / p).read_text(encoding="utf-8")
           for p in ("selectionfit.py", "playerfit.py", "prereg.py", "boards.py")}
    for p, s in src.items():
        for slip in ("block(s)", "player(s) corrected", "settled bet(s)", "market(s)"):
            assert slip not in s, (p, slip)
    assert "{k} block{'' if k == 1 else 's'}" in src["selectionfit.py"]
    assert "{len(players)} player{'' if len(players) == 1 else 's'} corrected" in src["playerfit.py"]
    assert "settled {'bet was' if one else 'bets were'} left out" in src["prereg.py"]
    assert "market{'s' if len(live) != 1 else ''}, walked forward" in src["boards.py"]


def test_a_quiet_date_counts_its_games():
    """The NBA board on Thanksgiving: "No NBA games on this date, but the season is running — 73 game(s) in the last
    10 days." College football's quiet date said it the same way."""
    nba = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    cfb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert "game(s) in the" not in nba and "game(s) in the" not in cfb
    assert "{recent} game{'' if recent == 1 else 's'} in the " in nba
    assert "{len(recent)} game{'' if len(recent) == 1 else 's'} in the last " in cfb


def test_the_nightly_write_up_is_handed_units_to_two_places():
    """The write-up narrates the numbers it is handed (engine/prose), and it was handed a pick's units unrounded:
    "returned less (+0.4435) than the win the market faded us on" on the Record page."""
    from engine import prose
    conn = ledger.connect(":memory:")
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, projection, hit_prob, edge, "
        "confidence, grade, stake_units, status, actual, pnl_units, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'main')",
        ("2026-11-20T18:00:00", "nfl", "2026-11-20", "A Player", "receptions", "UNDER", 4.5, "DraftKings", 122,
         3.9, 0.53871, 0.05, 0.0, "", 0.43, "won", 3.0, 0.52463))
    conn.commit()
    pick = prose.postmortem_pack(conn, "2026-11-20")["by_sport"]["nfl"]["picks"][0]
    assert pick["pnl_units"] == 0.52 and pick["stake_units"] == 0.43 and pick["hit_prob"] == 0.539, pick
    assert prose._round(None, 2) is None


def test_the_weekly_brief_counts_every_book_the_record_page_grades():
    """The weekly brief said "Nothing journaled yet" for hockey, college basketball, the WNBA and UFC: it counts the
    Edge, Long Shots and parlay books, and those leagues' graded picks are in Most Likely and the board. The same
    brief's overview said a WNBA market had closed itself, which takes graded picks."""
    from engine import prose
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    for i, status in enumerate(("won", "lost", "won")):
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,stake_units,status,category,pnl_units,"
            "hit_prob) VALUES ('nhl','2026-11-20',?,'sog','OVER',2.5,-150,'B',0.1,?,'likely',?,0.7)",
            (f"Skater {i}", status, 0.07 if status == "won" else -0.1))
    conn.commit()
    pack = prose.brief_pack(conn)
    assert pack["by_sport"]["nhl"]["posted_graded"] == 3, pack["by_sport"]["nhl"]
    assert pack["by_sport"]["nhl"]["record_page"]["graded"] == 0, "the Edge book's count is unchanged"
    assert "posted_graded" in pack["scope"]
    fb = prose._week_fallback(pack)
    assert fb("nhl") == "No Edge, Long Shots or parlay picks graded yet; the Record page grades 3 of its other picks.", fb("nhl")
    assert fb("cfb").startswith("Nothing journaled yet"), "a league with nothing anywhere still says so"


def test_the_other_counts_a_visitor_reads_say_it_too():
    """The sign-in throttle ("Try again in 1 minute(s)."), a pick card's sample reset ("Projecting from the 3
    game(s) since"), the stake block's variance reason and the Record lab's edge slices."""
    from engine import edgeslices, probation
    assert "1 graded game in this database" in probation.variance_reason(False, 1)
    assert "7 graded games in this database" in probation.variance_reason(False, 7)
    assert edgeslices.reading({"tested": [{}], "survivors": [], "alpha": 0.1}).startswith("1 slice tested, none")
    one = {"key": "odds", "value": "long", "auc_edge": 0.61, "q": 0.04}
    assert edgeslices.reading({"tested": [{}, {}, {}], "survivors": [one]}).startswith("1 of 3 slices survives: ")
    assert edgeslices.reading({"tested": [{}, {}, {}], "survivors": [one, one]}).startswith("2 of 3 slices survive: ")
    for p in ("accounts.py", "reset.py", "probation.py", "edgeslices.py"):
        s = (ROOT / "engine" / p).read_text(encoding="utf-8")
        for slip in ("minute(s)", "game(s)", "slice(s)"):
            assert slip not in s, (p, slip)


def test_a_quarterback_change_finds_the_passer_under_another_spelling():
    """The NFL board, 26 November: "Daniel Jones BENCHED -> Anthony Richardson Sr. ... has 0 pass attempts in our
    data — too few to rate". ESPN's depth chart adds the "Sr."; the weekly stats do not, and the lookup was exact,
    so a passer with hundreds of attempts was rated as if he had never thrown."""
    qb = {"teams": {"IND": {"starter": "Daniel Jones", "backup": None}},
          "passing": {"Daniel Jones": (400.0, 2600.0), "Anthony Richardson": (650.0, 4290.0)},
          "usual": {"IND": ["Daniel Jones"]},
          "profile": {"Anthony Richardson": {"games": 2, "carries_pg": 6.0, "rush_yds_pg": 31.0}}}
    ch = qbchange.changes(qb, [], {"IND": "Anthony Richardson Sr."})["IND"]
    assert ch["replacement"] == "Anthony Richardson Sr.", "the chart's name is the one the page says"
    assert ch["replacement_attempts"] == 650 and ch["replacement_ypa"] == 6.6, ch
    assert ch["replacement_profile"] == qb["profile"]["Anthony Richardson"], ch
    words = qbchange.detail(ch)
    assert words.startswith("Anthony Richardson Sr. has thrown for 6.6 yards an attempt (650 attempts) against "
                            "Daniel Jones’s 6.5"), words
    assert "too few to rate" not in words
    # Two passers under one loose name: neither is guessed.
    two = dict(qb, passing={"Daniel Jones": (400.0, 2600.0), "Anthony Richardson": (650.0, 4290.0),
                            "Anthony Richardson Jr.": (5.0, 30.0)})
    assert qbchange.changes(two, [], {"IND": "Anthony Richardson Sr."})["IND"]["replacement_attempts"] == 0


def test_a_quarterback_who_barely_runs_runs_for_1_yard():
    ch = {"starter": "A Starter", "replacement": "B Backup",
          "replacement_profile": {"games": 3, "carries_pg": 1.0, "rush_yds_pg": 1.2}}
    assert "1.0 runs a game for 1 yard" in qbchange.shape_words(ch)
    assert "1 yards" not in qbchange.shape_words(ch)
    ch["replacement_profile"]["rush_yds_pg"] = 55.0
    assert "1.0 runs a game for 55 yards" in qbchange.shape_words(ch)


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
