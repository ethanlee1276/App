"""The Live tab follows the game reports' own picks, as it follows Most Likely and Edge (step AAS, 21 November).

Ethan, 2026-11-21: "on the live page, how we're able to see our most likely bets and edge bets that are
live and how those bets are doing while they're live, we should be able to see the same for game report
bets, and parlays and stuff like that, so you need to make that happen as well".

The reports' parlays were followed leg by leg already (engine/reportlive, "Our report parlays, live":
tests/test_a_reports_parlays_are_followed_live.py). A report's picks journal to their own book
(engine/reportbets.CATEGORY) and the tracker read the others only, so those went quiet at kickoff. They are
now a key of their own (`live_report`), read the way the Pick of the Day's is, drawn in a third panel under
Edge and Most Likely, and in a "Game report picks" group on each game's own picks rail; a member's.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gate, ledger, livepicks, reportbets      # noqa: E402

LT = __import__("test_the_live_tab_says_whose_bets_these_are")    # its node harness (a sibling test file)
PO = __import__("test_pbp_our_picks")                             # the rail's
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _conn():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ledger.SCHEMA)
    return conn


def _bet(conn, category, grade="", player="Malik Nabers", market="receptions", line=4.5, date="2099-W12"):
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, stake_units, category, status, ts, grade, "
        "hit_prob) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("nfl", date, player, market, "OVER", line, -150, 0.1, category, "open", "2099-11-22T15:00:00Z", grade, 0.66))
    conn.commit()


# --- the rows reach the board ---------------------------------------------------------------------
def test_a_report_pick_is_read_from_its_own_book_and_nowhere_else():
    assert livepicks.REPORT_TRACKER_CATEGORIES == (reportbets.CATEGORY,) == ("report",)
    assert reportbets.CATEGORY not in livepicks.TRACKER_CATEGORIES, \
        "a report's card pick is a Most Likely pick too: in the open-bet list it would draw twice"
    conn = _conn()
    _bet(conn, "report", grade="Our picks")
    today, _ = livepicks.open_bets_for(conn, "nfl", "2099-W12")
    assert today == [], "the report's book leaked into the Edge and Most Likely panels"
    mine, _ = livepicks.open_bets_for(conn, "nfl", "2099-W12", livepicks.REPORT_TRACKER_CATEGORIES)
    assert len(mine) == 1 and mine[0]["category"] == "report"


def test_the_board_carries_each_report_pick_with_where_its_report_posted_it():
    conn = _conn()
    _bet(conn, "report", grade="Our picks")
    _bet(conn, "report", grade="Matchup read", player="Cam Skattebo", market="rush_att", line=11.5)
    _bet(conn, "board", grade="top")                       # the same wager on the Most Likely board's book
    result = {"date": "2099-W12", "recommendations": [], "games": []}
    note = livepicks.attach_tracker(result, "nfl", conn=conn, progress={})
    got = {r["player"]: r for r in result["live_report"]}
    assert set(got) == {"Malik Nabers", "Cam Skattebo"}, got
    assert got["Malik Nabers"]["source"] == "Our picks" and got["Cam Skattebo"]["source"] == "Matchup read"
    assert all(r["category"] == "report" for r in got.values())
    assert [r["player"] for r in result["live_picks"]] == ["Malik Nabers"], "the Most Likely copy, once, in its own list"
    assert "2 report picks tracked" in note, note
    empty = {"date": "2099-W12", "recommendations": [], "games": []}
    livepicks.attach_tracker(empty, "nfl", conn=_conn(), progress={})
    assert empty.get("live_report") == [], "a day with no report pick still carries the key"


def test_a_row_the_journal_cannot_name_is_left_as_it_is():
    conn = _conn()
    rows = [{"player": "Nobody", "market": "receptions", "side": "OVER", "line": 3.5, "date": "2099-W12"}]
    assert livepicks.report_sources(conn, "nfl", rows) == rows and "source" not in rows[0]
    conn.close()
    assert livepicks.report_sources(conn, "nfl", rows) == rows, "a closed journal: the rows as they are"


def test_following_them_is_a_members():
    assert "live_report" in gate.PAID_KEYS
    out = gate.redact({"date": "2099-W12", "live_report": [{"player": "Malik Nabers"}], "games": [{"home": "NYG"}]},
                      "nfl_picks.json")
    assert not out.get("live_report"), "a report's picks are published free while their games run"
    assert out.get("games") == [{"home": "NYG"}], "the free facts stay free"


# --- the Live tab draws them --------------------------------------------------------------------
def _draw(rows=(), report=(), sport="nfl"):
    import json
    data = {"live_picks": list(rows), "live_potd": [], "live_report": list(report), "open_elsewhere": 0,
            "long_shots": [], "games": []}
    js = f"""
    const state = {{ sport: {json.dumps(sport)}, view: "live", data: {json.dumps(data)} }};
    const LEAGUE_LABEL = {{ nfl: "NFL", cfb: "CFB" }};
    const lgCode = (s) => LEAGUE_LABEL[s] || String(s || "").toUpperCase();
    {LT._fn("escapeHtml")}
    {LT._fn("emptySlate")}
    const icon = () => ""; const iconMark = () => "";
    const american = (o) => String(o); const teamName = (t) => String(t || "");
    const betMark = () => ""; const ridingAttrs = () => ""; const placedStamp = () => "";
    const gameLine = () => ""; const situationLine = () => ""; const progressBar = () => ""; const winProb = () => "";
    const pluralWord = (n, w) => (n === 1 ? w : w + "s");
    const plural = (n, w) => `${{n}} ${{n === 1 ? w : w + "s"}}`;
    const whenLabel = () => "today"; const buzzOnSettle = () => {{}};
    const liveTrackerRows = (r) => r;
    const tonightSignals = () => ({{ props: [], sharpBets: [], modelBets: [] }});
    const _els = {{ "live-picks": {{ innerHTML: "" }} }};
    const document = {{ getElementById: (id) => _els[id] || null }};
    const isWalled = () => false; const memberLockHTML = () => "";
    {LT._fn("trackerBetText")}
    {LT._fn("isLikelyBook")}
    {LT._fn("renderLivePicks")}
    renderLivePicks();
    console.log(JSON.stringify(_els["live-picks"].innerHTML));
    """
    return LT._node(js)


REPORT = {"player": "Malik Nabers", "market": "receptions", "market_label": "Receptions", "side": "OVER",
          "line": 4.5, "odds": -150, "stake_units": 0.1, "phase": "live", "status": "tracking", "current": 3,
          "category": "report", "source": "Our picks", "game": {"home": "NYG", "away": "WAS"}}


def test_a_report_pick_has_its_own_panel_under_edge_and_most_likely():
    html = _draw(rows=[dict(REPORT, category="board")], report=[REPORT])
    assert html.index("Open edge bets") < html.index("Open Most Likely bets") < html.index("Open game report picks")
    tail = html[html.index("Open game report picks"):]
    assert "Malik Nabers OVER 4.5 Receptions" in tail and "Our picks" in tail, tail
    assert "0.10u" not in tail, "a flat-stake report pick says no stake, as a Most Likely one does"
    assert "Our report parlays, live" in tail, "the panel points at the reports' parlays"


def test_a_tab_whose_only_open_bet_is_a_report_pick_still_draws_it():
    html = _draw(report=[REPORT])
    assert "Open game report picks" in html and "Malik Nabers" in html, html
    empty = _draw(rows=[dict(REPORT, category="main")])
    assert "No open NFL game report picks on today’s card" in empty, "the empty panel names its league"


# --- and so does each game's own rail -----------------------------------------------------------
def test_the_games_rail_lists_its_report_picks_above_its_tickets():
    got = PO._node(PO.GAME + """
      state.data.live_report = [{ player: "Pofele Ashlock", market: "rec_yds", market_label: "Receiving Yards",
        side: "over", line: 54.5, odds: -115, category: "report", status: "cleared", current: 61, game: here }];
      const withReport = pbpPropsHTML(d, "cfb");
      state.data = { live_report: state.data.live_report };
      const onlyReport = pbpPropsHTML(d, "cfb");
      state.data = {};
      return { withReport, onlyReport, none: pbpPropsHTML(d, "cfb") };""")
    if got is None:
        print("  SKIP node not installed"); return
    html = got["withReport"]
    assert html.index("Edge picks") < html.index("Game report picks") < html.index('<div data-rl="cfb|WYO|HAW"></div>')
    i = html.index("Game report picks")
    assert ">CLEARED<" in html[i:] and "now 61" in html[i:]
    assert "Game report picks" in got["onlyReport"] and "No Most Likely or edge picks on this game." in got["onlyReport"]
    assert "Game report picks" not in got["none"], "a game whose report posted no pick shows no empty head"


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
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
