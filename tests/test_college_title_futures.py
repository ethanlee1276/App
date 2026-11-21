"""College basketball's title futures (engine/ncaarace.futures_payload).

Ethan, 2026-11-14: "make it like nba cup and shit I want all the features
like this is a complete sport." The Futures page for college is the NCAA
tournament race's own run — every game left, the conference tournaments,
the selection and the bracket — set beside the books' prices for the
national title.

Guarded here:
  * the page's numbers are the race's, in the futures page's own shape,
    each school's chance at its automatic bid and the field named so;
  * a price sits beside our chance with the gap in points, and a book's
    runner is matched to a school by a name we have seen, never guessed;
  * nothing here can spend: the college build reads kept prices only, and
    the one-credit pull is futures_build.py cbb --odds, run on purpose;
  * the file is paid whole, written beside every race, and the page is
    open on college.

    python3 tests/test_college_title_futures.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import gate                                       # noqa: E402
from engine import ncaarace as NR                             # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _race():
    import test_the_ncaa_tournament_race as N
    out = N.built(sims=200)
    out["prior"] = {"season": 2025, "schools": 150}
    out["generated_at"] = "2026-11-14T09:00:00"
    return out


def test_the_title_market_is_one_credit():
    from engine.sources import oddsapi
    assert oddsapi.FUTURES_KEYS["cbb"] == "basketball_ncaab_championship_winner"
    src = (ROOT / "engine" / "sources" / "oddsapi.py").read_text()
    i = src.index("def fetch_outrights(")
    assert '"markets": "outrights"' in src[i:i + 1200] and '"regions": "us"' in src[i:i + 1200]


def test_the_page_is_the_races_own_run():
    race = _race()
    out = NR.futures_payload(race)
    rows = out["teams"]
    assert rows and [r["p_title"] for r in rows] == sorted((r["p_title"] for r in rows), reverse=True)
    top = rows[0]
    c = race["chances"][top["team"]]
    assert top["p_title"] == c["title"] and top["p_playoffs"] == c["field"] and top["p_division"] == c["auto"]
    assert top["name"] == f"School {top['team']}" and top["conference"]
    assert top["proj_wins_lo"] <= top["proj_wins"] <= top["proj_wins_hi"]
    assert top["proj_wins_lo"] >= top["wins"]
    assert out["labels"] == {"group": "Conf", "div": "Bid", "po": "Field"} and out["rows_shown"] == NR.FUTURES_ROWS
    assert out["trials"] == race["sims"] and out["fixtures_remaining"] == race["games_left"]
    assert "the same run as the Race page" in out["doctrine"] and "not from reading a price" in out["doctrine"]
    assert out["how"] == NR.FUTURES_HOW and out["season_totals"] == []
    assert out["priced"] == 0 and "title_odds" not in top
    assert 0 < out["prior_share"] < 1 and out["note"]
    assert NR.futures_payload(dict(race, prior={"season": 2025, "schools": 0}))["prior_share"] == 0


def test_a_price_sits_beside_our_chance():
    race = _race()
    a, b = [r["team"] for r in NR.futures_payload(race)["teams"][:2]]
    prices = {a: {"odds": 400, "book": "BookA", "implied": 0.2}, b: {"odds": 2500, "book": "BookB", "implied": 0.0385}}
    out = NR.futures_payload(race, prices)
    rows = {r["team"]: r for r in out["teams"]}
    assert out["priced"] == 2 and "price_note" not in out
    assert rows[a]["title_odds"] == 400 and rows[a]["title_book"] == "BookA"
    assert rows[a]["title_edge_pts"] == round((rows[a]["p_title"] - 0.2) * 100, 1)
    out = NR.futures_payload(race, {}, "no title prices kept yet — futures_build.py cbb --odds pulls them")
    assert out["price_note"].startswith("no title prices kept yet")


def test_a_runner_is_matched_by_a_name_we_have_seen_never_guessed():
    from engine import cbbteams
    from engine.sources import oddsapi
    keep = (cbbteams.cards, cbbteams.load, oddsapi.fetch_outrights)
    asked = []

    def fetch(sport, cache_only=False):
        asked.append((sport, cache_only))
        return [{"bookmakers": [{"title": "Book", "markets": [{"key": "outrights", "outcomes": [
            {"name": "Duke Blue Devils", "price": 500}, {"name": "UConn Huskies", "price": 700},
            {"name": "Mystery State Owls", "price": 9000}]}]}]}], None
    cbbteams.cards = lambda *a, **k: {"DUKE": {"name": "Duke Blue Devils"}, "MSU": {"name": "Michigan State Spartans"}}
    cbbteams.load = lambda *a, **k: {"UConn Huskies": "CONN"}
    oddsapi.fetch_outrights = fetch
    try:
        got, why = NR.title_prices()
    finally:
        cbbteams.cards, cbbteams.load, oddsapi.fetch_outrights = keep
    assert set(got) == {"DUKE", "CONN"} and why == ""
    assert got["DUKE"]["odds"] == 500 and got["DUKE"]["implied"] == round(1 / 6, 4)
    assert asked == [("cbb", True)], "kept prices only, unless asked"


def test_nothing_here_can_spend():
    import inspect
    import futures_build
    assert inspect.signature(NR.title_prices).parameters["cache_only"].default is True
    src = (ROOT / "engine" / "ncaarace.py").read_text()
    pub = src[src.index("def publish("):]
    assert "write_futures(out, p.with_name(\"futures_cbb.json\"), cache_only=True)" in pub
    assert futures_build.EXTRA == ("cbb",) and "cbb" not in futures_build.SPORTS, \
        "the loop's daily rebuild (launch._run_futures) never touches college"
    fb = (ROOT / "futures_build.py").read_text()
    assert "want = SPORTS + EXTRA if" in fb and "ncaarace.futures_from_race(" in fb


def test_it_is_paid_whole_written_beside_the_race_and_open_on_college():
    assert "futures_cbb.json" in gate.PAID_FILES
    hidden = APP[APP.index("const HIDDEN_VIEWS = {"):APP.index("\n};", APP.index("const HIDDEN_VIEWS = {"))]
    line = next(ln for ln in hidden.splitlines() if ln.strip().startswith("cbb:"))
    assert "futures" not in line and "longshots" in line
    table = APP[APP.index("function futuresTeamTable(d) {"):APP.index("const fxPct")]
    for part in ("d.rows_shown || 20", "t.name || t.team", 'lab.div || "Div"', 'lab.po || "Playoff"'):
        assert part in table, part
    assert "d.how ? escapeHtml(d.how)" in APP[APP.index("function futuresDoctrine(d) {"):APP.index("function futuresTeamTable")]
    race = _race()
    out = Path(tempfile.mkdtemp()) / "web" / "data" / "futures_cbb.json"
    line = NR.write_futures(race, out)
    assert line.startswith("futures: ") and "priced" in line
    full = json.loads(Path(gate.board_source(out)).read_text())
    assert full["teams"] and full["sport"] == "cbb"


def test_after_selection_sunday_every_school_listed_is_in():
    import test_the_ncaa_tournament_race as N
    games = N._tournament()
    day = NR.nights(N.SEASON)["r32"][0]
    race = NR.build(games, N.ratings(games, day), day, sims=100, seed=1)
    out = NR.futures_payload(race)
    assert out["teams"] and all(r["p_playoffs"] == 1.0 and r["p_division"] is None for r in out["teams"])
    assert abs(sum(r["p_title"] for r in out["teams"]) - 1.0) < 1e-6


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
