"""Every Most Likely pick is on the record, each once, and the Record
page's numbers add up.

Ethan, 2026-10-02, four Record-page screenshots: "make sure we are
recording everything and not missing anything and everything is recorded
correctly bc we honestly show too much and it feels like all these
numbers are not adding up and we are not telling the truth. No way we
have hit 12/13 TD picks bc I've seen more then that loose. And then we
show how it's making money but then all the numbers shows how we are
not."

What was wrong, and what this pins:

  * THE ONE BOARD WAS IN NO HEADLINE. Since 2026-09-26 the Most Likely
    picks a reader sees are the one board's (category `board`); the
    combined record and the scope chips counted the Most Likely list's
    books only, so the board's matchup picks and touchdown scenarios were
    nowhere above the tier table. Now they count — and a board pick the
    Most Likely book already holds (same pick, same side) counts once,
    at that book's row (`ledger.books_sql`).
  * THE PARTS ADD UP. The page draws the edge tile, a Most Likely tile
    (every pick once) and the combined one; the first two are the third,
    row for row.
  * THE TIER TABLE HAS ITS TOTAL, and its ROI is over stake at risk like
    every other ROI on the page (pushes out).
  * THE TD ROW IS SPLIT BY SIDE. "Anytime TD 12/13" pooled "he scores"
    with "he does not"; each side is its own row, and a shelf under its
    own bar says it is too few to read (the gate read the whole book's
    count).
  * "NaN DAYS". A board row from the matchup picks carried no game day,
    so it was filed under the week label; it takes its team's game day
    off the slate now, and the page measures windows over real days.
  * ZENO'S ALL-SPORTS TILE ON THE NFL PAGE is gone from league scopes,
    and his tile says the date of the Pikkit count.

Run directly: `python3 tests/test_every_pick_counts_once.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import ledger  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()

_INS = ("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, "
        "grade, stake_units, stake_dollars, status, category, pnl_units) "
        "VALUES ('t',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _bet(conn, cat, player, status, *, market="rec_yds", side="OVER", line=40.5, odds=-110,
         stake=0.1, prob=0.6, grade="", sport="nfl", date="2026-W04", day="2026-09-27"):
    win = stake * (100 / abs(odds) if odds < 0 else odds / 100)
    pnl = win if status == "won" else -stake if status == "lost" else 0.0
    conn.execute(_INS, (sport, date, day, player, market, side, line, odds, prob, grade,
                        stake, 0.0, status, cat, round(pnl, 4)))


def _journal():
    conn = ledger.connect(":memory:")
    # Edge picks: 2-1.
    _bet(conn, "main", "Edge A", "won", stake=1.0)
    _bet(conn, "main", "Edge B", "won", stake=1.0)
    _bet(conn, "paper", "Edge C", "lost", stake=1.0)
    # The Most Likely list's own book: one staked, one paper.
    _bet(conn, "likely_live", "Twin", "won", stake=0.25)
    _bet(conn, "likely", "Old Paper", "lost", stake=0.1, day="2026-09-14", date="2026-W02")
    # The one board: Twin is the same pick the staked book holds; the
    # other two are the board's own (a matchup pick, a scorer).
    _bet(conn, "board", "Twin", "won", grade="Top pick")
    _bet(conn, "board", "Matchup Only", "lost", grade="Strong")
    _bet(conn, "board", "Scorer", "lost", market="anytime_td", side="OVER", line=0.5, odds=150,
         grade="Worth a look", prob=0.42)
    # The OTHER SIDE of the twin's market is its own pick, not a twin.
    _bet(conn, "board", "Twin", "lost", side="UNDER", grade="Worth a look")
    # A long shot is in no headline book.
    _bet(conn, "longshot", "Long Shot", "won", odds=400)
    conn.commit()
    return conn


# --- the ledger -----------------------------------------------------------
def test_a_board_pick_the_most_likely_book_holds_counts_once():
    conn = _journal()
    p = ledger.performance(conn, "nfl", category=ledger.POOLED_BOOKS)
    # 3 edge + 2 Most Likely book + 3 board-only (Matchup Only, Scorer,
    # Twin UNDER). The board's Twin OVER is the staked row's pick.
    assert p["settled"] == 8, p["settled"]
    assert (p["wins"], p["losses"]) == (3, 5), (p["wins"], p["losses"])
    sql, args = ledger.books_sql(ledger.POOLED_BOOKS)
    twins = conn.execute(f"SELECT player, side, category FROM bets WHERE category='board' AND NOT {sql}",
                         args).fetchall()
    assert [tuple(r) for r in twins] == [("Twin", "OVER", "board")], [tuple(r) for r in twins]


def test_the_board_on_its_own_is_every_board_row():
    conn = _journal()
    assert ledger.performance(conn, "nfl", category=(ledger.BOARD_CATEGORY,))["settled"] == 4


def test_the_edge_tile_and_the_most_likely_tile_add_up_to_the_combined_one():
    conn = _journal()
    rep = ledger.pooled_report(conn, "nfl")
    e, lk, o = rep["edge"], rep["likely"], rep["overall"]
    assert e["settled"] + lk["settled"] == o["settled"] == 8
    assert e["wins"] + lk["wins"] == o["wins"] and e["losses"] + lk["losses"] == o["losses"]
    assert abs(e["net_units"] + lk["net_units"] - o["net_units"]) < 0.011
    assert abs(e["units_staked"] + lk["units_staked"] - o["units_staked"]) < 0.011
    assert lk["paper_bets"] == 4, "the paper Most Likely row and the three board-only rows"


def test_the_scope_chips_count_the_boards_picks_once():
    conn = _journal()
    jc = ledger.journaled_counts(conn)
    # 3 edge + 2 likely + 3 board-only + 0 for the twin; the long shot is
    # a recommended category too (RECOMMENDED_CATEGORIES).
    want = 3 + 2 + 3 + (1 if "longshot" in ledger.RECOMMENDED_CATEGORIES else 0)
    assert jc["by_sport"]["nfl"]["settled"] == want, (jc, want)
    assert jc["all"]["settled"] == want


def test_the_tier_table_prints_its_total_and_reads_roi_over_stake_at_risk():
    conn = _journal()
    _bet(conn, "board", "Pushed", "push", grade="Top pick")
    conn.commit()
    br = ledger.board_report(conn, sport="nfl")
    tot = br["total"]
    assert (tot["w"], tot["l"], tot["push"]) == (1, 3, 1), tot
    assert tot["settled"] == sum(t["settled"] for t in br["tiers"]) == br["settled"] == 4
    assert abs(tot["units"] - sum(t["units"] for t in br["tiers"])) < 1e-6
    top = next(t for t in br["tiers"] if t["tier"] == "Top pick")
    # Top pick: one win at -110 for 0.1u and one push. The push's stake was
    # never at risk, so it is not in the ROI's denominator.
    assert abs(top["roi"] - (0.1 * 100 / 110) / 0.1) < 1e-3, top
    assert br["first_day"] == "2026-09-27"


def test_a_scorer_market_is_split_by_side_and_a_thin_shelf_says_so():
    conn = ledger.connect(":memory:")
    for i in range(12):
        _bet(conn, "likely", f"No TD {i}", "won", market="anytime_td", side="UNDER", line=0.5,
             odds=-170, prob=0.64)
    _bet(conn, "likely", "Scores", "lost", market="anytime_td", side="OVER", line=0.5, odds=140, prob=0.45)
    for i in range(60):
        _bet(conn, "likely", f"Rec {i}", "won" if i % 3 else "lost")
    conn.commit()
    lk = ledger.likely_report(conn, sport="nfl")
    td = lk["by_market"]["anytime_td"]
    assert (td["w"], td["n"]) == (12, 13), "the pooled row is still there for every reader of it"
    assert td["sides"]["UNDER"]["w"] == 12 and td["sides"]["UNDER"]["n"] == 12
    assert td["sides"]["OVER"]["w"] == 0 and td["sides"]["OVER"]["n"] == 1
    assert td["enough"] is False, "13 settled is under the shelf's own bar, whatever the book's count"
    assert lk["by_market"]["rec_yds"]["enough"] is True
    assert "sides" not in lk["by_market"]["rec_yds"], "an over/under market is not split"
    assert lk["paper_settled"] == 73 and lk["money_settled"] == 0


def test_a_board_row_with_no_day_of_its_own_takes_its_games():
    conn = ledger.connect(":memory:")
    result = {"sport": "nfl", "date": "2030-W04",
              "games": [{"home": "BUF", "away": "MIA", "date": "2030-09-29", "kickoff": "13:00"}],
              "most_likely": [{"player": "Matchup Guy", "team": "MIA", "market": "rec_yds", "side": "OVER",
                               "line": 40.5, "odds": -120, "model_prob": 0.61, "book": "DraftKings"}]}
    n = ledger.log_most_likely(conn, result, depth=None, category="board", grade_label="Strong")
    assert n == 1
    row = conn.execute("SELECT date, game_day FROM bets WHERE player='Matchup Guy'").fetchone()
    assert tuple(row) == ("2030-W04", "2030-09-29"), tuple(row)


# --- the page ---------------------------------------------------------------
def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head)
            return APP[i:APP.index("\n}\n", i) + 2]
    raise AssertionError(name)


STUBS = ("const MINUS='\\u2212';const escapeHtml=(x)=>String(x==null?'':x);"
         "let _recMinGraded=30;const zenoMoney=(v)=>'$'+Number(v).toFixed(2);"
         "const pikkitBadgeHTML=()=>'[pikkit]';const trueMinus=(s)=>s;"
         "const toneOf=(v)=>v>0?'up':v<0?'down':'';const plural=(n,w)=>n+' '+w+(n===1?'':'s');"
         "const icon=()=>'';const marketWord=(m)=>({anytime_td:'Anytime TD',rec_yds:'Receiving Yards'})[m]||m;"
         "const pctRoundOr=(x)=>x==null?'—':Math.round(x*100)+'%';"
         "const SPORT_META={nfl:{name:'NFL'}};const recDisclosure=(t,b)=>'';"
         "const recTile=(l,v,s)=>`<tile>${l}|${v}|${s}</tile>`;const recLikelyGameLines=()=>'';\n")


def _node(body, call, arg):
    if not shutil.which("node"):
        return None
    path = os.path.join(tempfile.mkdtemp(), "h.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(STUBS + body + "\nconst a=JSON.parse(process.argv[2]);"
                 f"process.stdout.write(JSON.stringify({call}));")
    out = subprocess.run(["node", path, json.dumps(arg)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))


def test_the_record_page_draws_the_parts_beside_the_sum():
    rec = {"min_graded": 30,
           "likely_overall": {"settled": 520, "wins": 300, "losses": 220, "roi": -0.031, "net_units": -3.1},
           "pooled_overall": {"settled": 612, "wins": 350, "losses": 262, "roi": 0.012, "net_units": 1.7}}
    ov = {"settled": 92, "wins": 50, "losses": 42, "roi": 0.07, "net_units": 4.8}
    body = _fn("recFloor") + _fn("recordRibbonsHTML")
    page = _node(body, "recordRibbonsHTML(a.rec, a.ov, [], { parts: true })", {"rec": rec, "ov": ov})
    home = _node(body, "recordRibbonsHTML(a.rec, a.ov, [])", {"rec": rec, "ov": ov})
    if page is None:
        print("  SKIP node not installed"); return
    t = _text(page)
    a, b, c = (t.index("Edge picks · graded in public"), t.index("Most Likely · every pick once"),
               t.index("Combined · edge + Most Likely boards"))
    assert a < b < c, t
    assert "300-220" in t and "350-262" in t and "50-42" in t, t
    assert "edge +4.8u + Most Likely −3.1u" in t, t
    assert "Most Likely · every pick once" not in _text(home), "Home keeps its tiles; the split rides the combined one"
    assert "edge +4.8u + Most Likely −3.1u" in _text(home)


def test_zenos_tile_says_when_the_pikkit_count_was_taken():
    body = _fn("recFloor") + _fn("recordRibbonsHTML")
    z = {"overall": {"settled": 1389, "wins": 221, "losses": 1141, "pushes": 27, "profit": 8001.64,
                     "roi": 0.2607, "staked": 30692.9, "net_units": 800.16},
         "snapshot": {"as_of": "2026-09-26T21:00:00"}, "recent": []}
    got = _node(body, "recordRibbonsHTML({ zeno: a }, {}, [])", z)
    if got is None:
        return
    assert "Pikkit count as of Sep 26" in _text(got), _text(got)


def test_a_league_scope_drops_zenos_all_sports_tile_and_keeps_the_parts():
    rr = _fn("renderRecord")
    assert "? { ...d, combined: null, zeno: null," in rr
    assert "likely_overall: winO ? null : src.likely_overall } : d;" in rr
    assert "s.likely_overall = s.pooled.likely || null;" in _fn("adoptPooledRecord")


def test_a_week_label_in_the_curve_is_no_date():
    body = _fn("recRanges") + _fn("recRangesFor") + _fn("recRangeTotals") + _fn("recRangesClosed")
    curve = [{"date": "2026-09-07", "w": 1, "l": 0, "n": 1, "staked": 1, "cum_u": 0.9},
             {"date": "2026-09-14", "w": 0, "l": 1, "n": 1, "staked": 1, "cum_u": -0.1},
             {"date": "2026-W04", "w": 1, "l": 0, "n": 1, "staked": 1, "cum_u": 0.8}]
    got = _node(body, "{closed: recRangesClosed(a), win: recRangeTotals(a, '2026-09-10')}", curve)
    if got is None:
        return
    assert "NaN" not in json.dumps(got["closed"]), got["closed"]
    assert any("covers 7 days" in c[3] for c in got["closed"]), got["closed"]
    assert got["win"]["settled"] == 1, "the week-labelled row is in the whole record, not in a window"


def test_the_tier_table_draws_all_tiers():
    tier = lambda name, w, l: {"tier": name, "settled": w + l, "w": w, "l": l, "push": 0, "open": 0,
                                "claimed": 0.62, "actual": w / (w + l), "units": 0.0, "roi": -0.1}
    bd = {"settled": 300, "open": 5, "first_day": "2026-09-26",
          "tiers": [tier("Top pick", 22, 23), tier("Strong", 41, 34), tier("Worth a look", 84, 96)],
          "total": {"settled": 300, "w": 147, "l": 153, "push": 0, "open": 5, "claimed": 0.63,
                    "actual": 0.49, "units": -5.0, "roi": -0.17}}
    got = _node(_fn("recBoardSection"), "recBoardSection(a, 'nfl')", bd)
    if got is None:
        return
    t = _text(got)
    assert "All tiers" in t and "147–153" in t, t
    assert "since Sep 26" in t, t


def test_the_staked_section_splits_the_scorer_row_and_stops_asking_for_a_verdict_it_has():
    lk = {"sport": "nfl", "settled": 372, "open": 126, "wins": 243, "losses": 129, "roi": -0.006,
          "needed": 100, "enough": True, "verdict": "v", "bands": [],
          "calibration": {"n": 372, "claimed": 0.647, "actual": 0.653, "gap": 0.006, "real": False},
          "staked": True, "staked_sports": ["nfl"], "stake_units": 0.25,
          "paper_settled": 150, "money_settled": 222, "money_from": "2026-09-19",
          "by_market": {"anytime_td": {"n": 13, "w": 12, "claimed": 0.638, "actual": 0.923, "roi": 0.433,
                                       "enough": False, "needed": 40,
                                       "sides": {"UNDER": {"n": 12, "w": 12, "claimed": 0.66, "actual": 1.0,
                                                           "roi": 0.55, "enough": False},
                                                 "OVER": {"n": 1, "w": 0, "claimed": 0.45, "actual": 0.0,
                                                          "roi": -1.0, "enough": False}}}}}
    got = _node(_fn("recLikelySection"), "recLikelySection(a, 'nfl')", lk)
    if got is None:
        return
    t = _text(got)
    assert "Anytime TD · no TD" in t and "Anytime TD · scores" in t, t
    assert "12/13" not in t, "the pooled scorer row is not drawn beside its sides"
    assert "needed for a verdict" not in t, "372 settled is past the bar of 100"
    assert "150 were on paper and 222 had real money on them (from Sep 19)" in t, t
    assert 'title="12 settled — too few to read either way"' in got


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
